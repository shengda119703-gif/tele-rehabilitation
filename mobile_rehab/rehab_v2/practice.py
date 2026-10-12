"""Independent B01/B02 records on the ORIGINAL formal Storage writer.

A guided record is not a camera session, assessment or plan contribution. Plan
qualification uses the existing assessment/progress functions inside the same
transaction. No second patient database, new dose or measurement gate exists.
"""
from __future__ import annotations

import copy
from contextlib import closing
from datetime import datetime
import json
import sqlite3
from uuid import uuid4

from fastapi import HTTPException, Request
from app.assessment_batches import scope_key
from app.automatic_plans import feedback_block
from app.domain import digest, dumps, utc_now
from app.rehab_v2.plans import BackendPlans
from app.rehab_v2.progress import eligibility_session, plan_progress
from app.rehab_v2.protocols import protocol
from app.rehab_v2.sessions import SessionError, SessionRepository
from ..practice import exact, key, feedback_snapshot, feedback_operation, stopped

POLICY = 'formal-arrangement-guided-1'
PROVIDER = 'hosted-rehab-v2-guided-1'
CONFIRMATIONS = ('manual_arrangement_confirmed', 'support_ready', 'companion_present')
START_FIELDS = ('operation_id', 'plan_id', 'plan_revision', 'entry_key') + CONFIRMATIONS


def reject(code, message, category='EXECUTION_BLOCK', status=409):
    raise HTTPException(status, dict(code=code, message=message, category=category,
        applies_to='GUIDED_PRACTICE', policy_version=POLICY))


def grant():
    return dict(allowed=True, code='FORMAL_ARRANGEMENT_GUIDED_ALLOWED', category=None,
        applies_to='GUIDED_PRACTICE', policy_version=POLICY,
        grants_formal_measurement=False, grants_plan_contribution=False,
        clinical_suitability_assessed=False)


class FormalPractices:
    def __init__(self, service):
        self.service, self.storage = service, service.storage_boundary

        def initialize(conn):
            meta = conn.execute("SELECT 1 FROM sqlite_master WHERE name='rehab_v2_practice_meta'").fetchone()
            if meta:
                versions = [row[0] for row in conn.execute('SELECT version FROM rehab_v2_practice_meta')]
                if versions != [1]:
                    raise SessionError('unsupported_formal_practice_schema', 503)
            else:
                # SQLite's consistent backup includes committed WAL contents.
                backup = self.storage.path.with_name(self.storage.path.name+'.before-guided-'+uuid4().hex+'.bak')
                with closing(sqlite3.connect(backup)) as target:
                    conn.backup(target)
            conn.executescript('''BEGIN IMMEDIATE;
                CREATE TABLE IF NOT EXISTS rehab_v2_practice_meta(version INTEGER NOT NULL);
                INSERT INTO rehab_v2_practice_meta SELECT 1 WHERE NOT EXISTS(SELECT 1 FROM rehab_v2_practice_meta);
                CREATE TABLE IF NOT EXISTS rehab_v2_guided_practices(
                    owner TEXT NOT NULL, id TEXT NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(owner,id));
                CREATE TABLE IF NOT EXISTS rehab_v2_practice_links(
                    owner TEXT NOT NULL, session_id TEXT NOT NULL, journey_id TEXT NOT NULL,
                    operation_id TEXT NOT NULL, request_digest TEXT NOT NULL, payload TEXT NOT NULL,
                    PRIMARY KEY(owner,session_id), UNIQUE(owner,operation_id));
            ''')
        self.storage._call(initialize)

    def context(self, owner):
        scope = self.service.plans.scope(owner)
        return dict(provider=PROVIDER, owner_scope=owner, participant_id=scope['participant_id'],
            source_context='GUIDED_PRACTICE:'+scope['usage_context'], policy_version=POLICY,
            arrangement_source_context=scope['source_kind']+':'+scope['usage_context'])

    @staticmethod
    def _read(conn, owner, identity):
        key(identity)
        row = conn.execute('SELECT payload FROM rehab_v2_guided_practices WHERE owner=? AND id=?',
                           (owner, identity)).fetchone()
        if not row:
            reject('OWNED_PRACTICE_REQUIRED', '未找到本人的这次跟练。', 'AUTHORIZATION', 404)
        return json.loads(row[0])

    @staticmethod
    def _write(conn, owner, item):
        conn.execute('UPDATE rehab_v2_guided_practices SET payload=? WHERE owner=? AND id=?',
                     (dumps(item), owner, item['id']))

    def _items(self, conn, owner):
        return [json.loads(row[0]) for row in conn.execute(
            'SELECT payload FROM rehab_v2_guided_practices WHERE owner=? ORDER BY rowid DESC', (owner,))]

    def _decision(self, conn, owner, ref, entry_key, confirmations, *, initial=False):
        """Original facts/qualification; guided navigation is independently typed.

        A set completed by self report advances ONLY the saved guided sequence.
        It never changes the original next_key or grants a formal camera start.
        """
        record = BackendPlans._row(conn, owner, ref['id'])
        if record['revision'] != ref['revision'] or record['status'] != 'ACTIVE':
            reject('ARRANGEMENT_CHANGED', '原安排已变化；已发生的练习仍可保存。')
        if scope_key(record) != self.service.plans.scope(owner):
            reject('ARRANGEMENT_SCOPE_CHANGED', '这份安排不属于当前本人或输入。', 'AUTHORIZATION')
        entry = next((e for e in record['items'] if e['key'] == entry_key), None)
        if not entry:
            reject('ARRANGEMENT_ENTRY_CHANGED', '原训练条目需要核对。')
        # Use the exact original functions, not a client ALLOWED flag or a
        # second writer call from this owning-writer callback (deadlock).
        for row in record['items']:
            original = self.service.plans._assessment(conn, owner, scope_key(record),
                row['exercise_id'], row['side'], row['assessment_reference']['session_id'])
            if original != row['assessment_reference'] or digest(protocol(row['exercise_id'], row['side'])) != row['protocol_digest']:
                raise SessionError('frozen_assessment_or_protocol_changed')
        joined = [dict(json.loads(r[0]), plan_contribution=json.loads(r[1])) for r in conn.execute(
            'SELECT s.payload,c.payload FROM rehab_v2_plan_contributions c JOIN rehab_v2_sessions s '
            'ON s.id=c.session_id AND s.owner=c.owner WHERE c.owner=? ORDER BY c.ordinal DESC', (owner,))]
        latest, seen, scoped, scope_seen = [], set(), [], set()
        for item in joined:
            c = item['plan_contribution']
            if c['plan_id'] == record['id'] and c['plan_revision'] == record['revision'] and c['entry_key'] not in seen:
                seen.add(c['entry_key']); latest.append(item)
            action = (c['exercise_id'], c['side'])
            if c['progress_eligible'] and c['scope'] == scope_key(record) and action not in scope_seen:
                scope_seen.add(action); scoped.append(item)
        progress = plan_progress(record, [], latest)
        if progress['blocked']:
            reject('FORMAL_PROGRESS_BLOCKED', '上一项需要核对感受或安排。已发生的练习仍可保存。')
        for item in scoped:
            view = eligibility_session(item)
            if feedback_block(view):
                reject('TRAINING_STOP_RECORDED', '最近训练记录了不适，请先核对安排。')
            if any(view['training_feedback'].get(k) is None for k in ('pain', 'fatigue')):
                reject('PREVIOUS_TRAINING_FEEDBACK_REQUIRED', '请先补充上一项训练感受。')
        if initial and progress['next_key'] != entry_key:
            reject('FORMAL_START_POSITION_CHANGED', '当前训练位置已变化，请返回安排核对。')
        for old in self._items(conn, owner):
            if old['context']['participant_id'] == record['participant_id'] and stopped(old) and (
                    old['plan_ref']['id'] == record['id'] or
                    (old['exercise_id'], old['side']) == (entry['exercise_id'], entry['side'])):
                reject('PRACTICE_STOP_RECORDED', '本项已记录不适，请先停止并核对安排。')
        for name, message in (('manual_arrangement_confirmed', '请确认采用本人的这份安排。'),
                              ('support_ready', '请按本项安排准备好支撑。')):
            if confirmations.get(name) is not True:
                reject(name.upper()+'_REQUIRED', message, 'MISSING_INPUT')
        if entry['settings']['needs_companion'] and confirmations.get('companion_present') is not True:
            reject('COMPANION_REQUIRED', '本项安排需要陪同者在场。', 'MISSING_INPUT')
        return record, copy.deepcopy(entry)

    def _project(self, conn, owner, item):
        result = copy.deepcopy(item)
        result.update(execution_allowed=False, execution_reason=None, continuation=None)
        same_scope = item['context'] == self.context(owner)
        if item['state'] == 'PRACTICING':
            try:
                if not same_scope:
                    reject('PRACTICE_SCOPE_CHANGED', '当前本人已变化；可以核对并保存原记录。', 'AUTHORIZATION')
                _, entry = self._decision(conn, owner, item['plan_ref'], item['plan_ref']['entry_key'], item['start_payload'])
                if entry['settings'] != item['settings']:
                    reject('ARRANGEMENT_SETTINGS_CHANGED', '原安排内容需要重新核对。')
                result.update(execution_allowed=True, execution_decision=grant())
            except (SessionError, HTTPException) as error:
                detail = error.detail if isinstance(error, HTTPException) else dict(code=error.code, message='本项安排暂不可继续；已发生的练习仍可保存。', category='EXECUTION_BLOCK')
                result.update(execution_reason=detail.get('message'), execution_decision=detail)
        if same_scope:
            result['continuation'] = self._following(conn, owner, item)
        links = []
        for row in conn.execute('SELECT payload FROM rehab_v2_practice_links WHERE owner=? AND journey_id=?', (owner, item['journey_id'])):
            link = json.loads(row[0]); visual = SessionRepository._row(conn, owner, link['session_id'])
            links.append(dict(link, persistence_state=visual['persistence_state'],
                canonical_commit=copy.deepcopy(visual['canonical_commit']),
                save_state='COMMITTED' if visual['persistence_state'] == 'finalized' else
                    'ACCEPTED' if visual['persistence_state'] == 'finishing' else 'LOCAL_DRAFT'))
        result['visual_session_refs'] = links
        result['saved_parts'] = dict(practice_records='COMMITTED' if item['state'] == 'COMMITTED' else 'LOCAL_DRAFT',
            visual_facts=None if not links else 'COMMITTED' if all(l['save_state'] == 'COMMITTED' for l in links) else
                'ACCEPTED' if any(l['save_state'] == 'ACCEPTED' for l in links) else 'LOCAL_DRAFT',
            feedback='COMMITTED' if item.get('practice_feedback', {}).get('revision', 0) > 0 else None)
        return result

    def create(self, owner, value):
        exact(value, START_FIELDS); key(value['operation_id'])
        if not isinstance(value['plan_id'], str) or not isinstance(value['entry_key'], str) or type(value['plan_revision']) is not int or value['plan_revision'] < 1 or any(type(value[k]) is not bool for k in CONFIRMATIONS):
            reject('INVALID_PRACTICE_START', '请核对原安排和确认内容。', 'MISSING_INPUT', 400)
        def save(conn):
            conn.execute('BEGIN IMMEDIATE')
            old = conn.execute('SELECT payload FROM rehab_v2_guided_practices WHERE owner=? AND id=?', (owner, value['operation_id'])).fetchone()
            if old:
                item = json.loads(old[0])
                if item['start_payload'] != value:
                    reject('START_KEY_CONFLICT', '本次编号已用于另一份安排。', 'TECHNICAL')
                return self._project(conn, owner, item)
            ref = dict(id=value['plan_id'], revision=value['plan_revision'], entry_key=value['entry_key'])
            record, entry = self._decision(conn, owner, ref, ref['entry_key'], value, initial=True)
            if any(r['state'] == 'PRACTICING' and r['context'] == self.context(owner) for r in self._items(conn, owner)):
                reject('ORIGINAL_PRACTICE_OPEN', '上次跟练尚未结束，请先返回原记录。', 'TECHNICAL')
            item = dict(schema_version=2, id=value['operation_id'], journey_id=value['operation_id'],
                context=self.context(owner), state='PRACTICING', start_payload=copy.deepcopy(value),
                created_at=utc_now(), plan_ref=ref, exercise_id=entry['exercise_id'], side=entry['side'],
                settings=entry['settings'], record_origin='GUIDED_PRACTICE', guidance_policy=POLICY, execution_grant=grant(),
                confirmed_count=None, formal_plan_contribution=None, visual_session_ref=None, finish_payload=None,
                arrangement_sequence=copy.deepcopy(record['items']), sequence_index=record['items'].index(entry),
                set_index=1, sequence_policy=POLICY, successor_id=None, journey_closed=False)
            conn.execute('INSERT INTO rehab_v2_guided_practices VALUES(?,?,?)', (owner, item['id'], dumps(item)))
            return self._project(conn, owner, item)
        return self.storage._call(save)

    def get(self, owner, identity):
        return self.storage._call(lambda c: self._project(c, owner, self._read(c, owner, identity)))

    def list(self, owner):
        return self.storage._call(lambda c: [self._project(c, owner, r) for r in self._items(c, owner)])

    def finish(self, owner, identity, value):
        exact(value, ('operation_id', 'count', 'elapsed_ms', 'reason', 'feedback')); key(value['operation_id'])
        if value['count'] is not None and (type(value['count']) is not int or not 0 <= value['count'] <= 10000):
            reject('INVALID_SELF_REPORT', '请填写本组实际总次数，或留空。', 'MISSING_INPUT', 400)
        if type(value['elapsed_ms']) is not int or not 0 <= value['elapsed_ms'] <= 86400000 or value['reason'] not in ('ended', 'completed_set', 'discomfort'):
            reject('INVALID_PRACTICE_END', '结束内容需要核对。', 'MISSING_INPUT', 400)
        exact(value['feedback'], ('pain', 'fatigue'))
        self._values(dict(value['feedback'], note=None))
        def save(conn):
            conn.execute('BEGIN IMMEDIATE'); item = self._read(conn, owner, identity)
            if item['finish_payload']:
                if item['finish_payload'] != value:
                    reject('FINISH_PAYLOAD_CONFLICT', '本组已有结束记录，请核对原内容。', 'TECHNICAL')
                return self._project(conn, owner, item)
            item.update(state='COMMITTED', ended_at=utc_now(), finish_payload=copy.deepcopy(value),
                self_reported_count=value['count'], count_scope='set_total',
                elapsed_source='frontend_active_time_not_observed_hold',
                record_origin='SELF_RECORDED' if value['count'] is not None else 'GUIDED_PRACTICE',
                journey_closed=value['reason'] != 'completed_set')
            # Receipt timestamps describe record boundaries, NOT active exercise
            # or visual coverage. Mode-event authority is a later contract step.
            item['mode_segments'] = []
            self._write(conn, owner, item); return self._project(conn, owner, item)
        return self.storage._call(save)

    def _following(self, conn, owner, item):
        if item['state'] != 'COMMITTED' or item['journey_closed'] or item['finish_payload']['reason'] != 'completed_set':
            return None
        if item['successor_id']:
            return dict(kind='existing', successor_id=item['successor_id'], rest_remaining_ms=0)
        index, group, kind = item['sequence_index'], item['set_index']+1, 'next_set'
        if group > item['settings']['target_sets']:
            index, group, kind = index+1, 1, 'next_action'
        if index >= len(item['arrangement_sequence']):
            return None
        entry = copy.deepcopy(item['arrangement_sequence'][index])
        confirmations = item['start_payload'] if kind == 'next_set' else dict(manual_arrangement_confirmed=True)
        try:
            _, original = self._decision(conn, owner, item['plan_ref'], entry['key'], confirmations)
            if original != entry:
                reject('ARRANGEMENT_SETTINGS_CHANGED', '原安排内容需要重新核对。')
            decision = dict(allowed=True, category=None, message=None, companion_required=entry['settings']['needs_companion'])
        except (SessionError, HTTPException) as error:
            detail = error.detail if isinstance(error, HTTPException) else dict(code=error.code, category='EXECUTION_BLOCK', message='原安排暂不可继续。')
            decision = dict(detail, allowed=False, companion_required=entry['settings']['needs_companion'])
        rest = item['settings'].get('rest_between_sets_s') if kind == 'next_set' else None
        elapsed = (datetime.fromisoformat(utc_now())-datetime.fromisoformat(item['ended_at'])).total_seconds()
        return dict(kind=kind, successor_id=None, entry=entry, set_index=group, sequence_index=index,
            decision=decision, rest_seconds=rest, rest_remaining_ms=max(0, round((rest-elapsed)*1000)) if rest is not None else None,
            rest_time_basis='owning_server_receipt_utc', scope='guided_navigation_only')

    def continue_group(self, owner, identity, value):
        exact(value, ('operation_id',)+CONFIRMATIONS); key(value['operation_id'])
        if any(type(value[k]) is not bool for k in CONFIRMATIONS):
            reject('INVALID_PRACTICE_START', '请核对下一项的支撑和陪同。', 'MISSING_INPUT', 400)
        def save(conn):
            conn.execute('BEGIN IMMEDIATE'); previous = self._read(conn, owner, identity)
            old = conn.execute('SELECT payload FROM rehab_v2_guided_practices WHERE owner=? AND id=?', (owner, value['operation_id'])).fetchone()
            if old:
                item = json.loads(old[0])
                if item.get('predecessor_id') != identity or item.get('continue_payload') != value:
                    reject('CONTINUE_KEY_CONFLICT', '继续编号已用于另一份内容。', 'TECHNICAL')
                return self._project(conn, owner, item)
            following = self._following(conn, owner, previous)
            if not following or following.get('successor_id'):
                reject('NO_NEXT_GROUP', '本组没有待开始的下一项。')
            if following['rest_remaining_ms']:
                reject('REST_PENDING', '按原安排休息后再继续。', 'MISSING_INPUT')
            if any(r['state'] == 'PRACTICING' and r['context'] == self.context(owner) for r in self._items(conn, owner)):
                reject('ORIGINAL_PRACTICE_OPEN', '请先返回原练习。', 'TECHNICAL')
            entry = following['entry']; _, checked = self._decision(conn, owner, previous['plan_ref'], entry['key'], value)
            if checked != entry:
                reject('ARRANGEMENT_SETTINGS_CHANGED', '原安排内容需要核对。')
            ref = dict(previous['plan_ref'], entry_key=entry['key'])
            start = dict(operation_id=value['operation_id'], plan_id=ref['id'], plan_revision=ref['revision'], entry_key=entry['key'],
                         **{k:value[k] for k in CONFIRMATIONS})
            item = {k:copy.deepcopy(previous[k]) for k in ('schema_version', 'journey_id', 'context', 'arrangement_sequence', 'sequence_policy', 'guidance_policy')}
            item.update(id=value['operation_id'], state='PRACTICING', start_payload=start, created_at=utc_now(), plan_ref=ref,
                exercise_id=entry['exercise_id'], side=entry['side'], settings=entry['settings'],
                sequence_index=following['sequence_index'], set_index=following['set_index'], successor_id=None,
                predecessor_id=identity, continue_payload=copy.deepcopy(value), journey_closed=False, finish_payload=None,
                record_origin='GUIDED_PRACTICE', execution_grant=grant(), confirmed_count=None, formal_plan_contribution=None, visual_session_ref=None)
            previous['successor_id'] = item['id']; self._write(conn, owner, previous)
            conn.execute('INSERT INTO rehab_v2_guided_practices VALUES(?,?,?)', (owner, item['id'], dumps(item)))
            return self._project(conn, owner, item)
        return self.storage._call(save)

    def close_journey(self, owner, identity, value):
        exact(value, ('operation_id',)); key(value['operation_id'])
        def save(conn):
            conn.execute('BEGIN IMMEDIATE'); item = self._read(conn, owner, identity)
            if item.get('close_payload'):
                if item['close_payload'] != value:
                    reject('CLOSE_KEY_CONFLICT', '本次已结束，请查看原记录。', 'TECHNICAL')
            else:
                if item['state'] != 'COMMITTED' or item['successor_id']:
                    reject('GROUP_STATE_CHANGED', '请先核对当前组记录。', 'TECHNICAL')
                item.update(journey_closed=True, journey_closed_at=utc_now(), close_payload=copy.deepcopy(value)); self._write(conn, owner, item)
            return self._project(conn, owner, item)
        return self.storage._call(save)

    def link(self, owner, identity, value):
        exact(value, ('operation_id', 'session_id')); key(value['operation_id'])
        if not isinstance(value['session_id'], str) or not value['session_id'] or len(value['session_id']) > 128:
            reject('INVALID_VISUAL_REFERENCE', '测量编号需要核对。', 'MISSING_INPUT', 400)
        def save(conn):
            conn.execute('BEGIN IMMEDIATE'); item = self._read(conn, owner, identity)
            fingerprint = digest(dict(practice_id=identity, payload=value))
            old = conn.execute('SELECT request_digest,payload FROM rehab_v2_practice_links WHERE owner=? AND operation_id=?', (owner, value['operation_id'])).fetchone()
            if old:
                if old[0] != fingerprint:
                    reject('LINK_KEY_CONFLICT', '关联编号已用于另一项记录。', 'TECHNICAL')
                return json.loads(old[1])
            visual = SessionRepository._row(conn, owner, value['session_id']); frozen = visual['frozen_plan']; plan = frozen['plan']
            original_scope = item['context']['arrangement_source_context']
            if (frozen['plan_id'], frozen['plan_revision'], frozen['entry_key'], plan['submode'], plan['participant_id'], plan['exercise_id'], plan['side']) != (
                    item['plan_ref']['id'], item['plan_ref']['revision'], item['plan_ref']['entry_key'], 'training',
                    item['context']['participant_id'], item['exercise_id'], item['side']) or (
                    visual['source']['source_kind']+':'+visual['source']['usage_context'] != original_scope) or any(plan.get(k) != v for k,v in item['settings'].items()):
                reject('VISUAL_BINDING_MISMATCH', '测量与本次本人、动作或安排不一致。', 'AUTHORIZATION')
            prior = conn.execute('SELECT journey_id FROM rehab_v2_practice_links WHERE owner=? AND session_id=?', (owner, value['session_id'])).fetchone()
            if prior:
                reject('VISUAL_ALREADY_LINKED', '这项测量已关联原跟练旅程。', 'TECHNICAL')
            receipt = dict(status='COMMITTED', operation_id=value['operation_id'], practice_id=identity,
                journey_id=item['journey_id'], session_id=value['session_id'], source_epoch=visual['source_epoch'],
                context=copy.deepcopy(item['context']), association_scope='journey_not_self_reported_set_total',
                linked_at=utc_now(), no_measurement_or_contribution_rewrite=True)
            conn.execute('INSERT INTO rehab_v2_practice_links VALUES(?,?,?,?,?,?)', (owner, value['session_id'], item['journey_id'], value['operation_id'], fingerprint, dumps(receipt)))
            return receipt
        return self.storage._call(save)

    @staticmethod
    def _values(values):
        exact(values, ('pain', 'fatigue', 'note'))
        if any(v is not None and (type(v) is not int or not 0 <= v <= 10) for v in (values['pain'], values['fatigue'])) or (
                values['note'] is not None and (not isinstance(values['note'], str) or not values['note'].strip() or len(values['note']) > 500)):
            reject('INVALID_FEEDBACK', '请填写真实感受，或留空。', 'MISSING_INPUT', 400)

    def feedback(self, owner, identity, value=None, operation=None):
        if value is None:
            return self.storage._call(lambda c: feedback_operation(self._read(c, owner, identity), operation) if operation else feedback_snapshot(self._read(c, owner, identity)))
        exact(value, ('operation_id', 'expected_revision', 'values')); key(value['operation_id']); self._values(value['values'])
        if type(value['expected_revision']) is not int or value['expected_revision'] < 0 or all(v is None for v in value['values'].values()):
            reject('INVALID_FEEDBACK', '请填写真实感受，可以稍后再填。', 'MISSING_INPUT', 400)
        def save(conn):
            conn.execute('BEGIN IMMEDIATE'); item = self._read(conn, owner, identity)
            if item['state'] != 'COMMITTED':
                reject('PRACTICE_NOT_COMMITTED', '请先确认本组保存。', 'TECHNICAL')
            feedback = item.get('practice_feedback', dict(revision=0, operations=[]))
            prior = next((r for r in feedback['operations'] if r['operation_id'] == value['operation_id']), None)
            if prior:
                if (prior['expected_revision'], prior['values']) != (value['expected_revision'], value['values']):
                    reject('FEEDBACK_KEY_CONFLICT', '填写编号已用于另一份内容。', 'TECHNICAL')
                return feedback_operation(item, value['operation_id'])
            if feedback['revision'] != value['expected_revision']:
                reject('FEEDBACK_REVISION_CONFLICT', '另一处更新了感受，请先核对。', 'TECHNICAL')
            if len(feedback['operations']) >= 100:
                reject('FEEDBACK_CAPACITY', '感受修改记录空间已满，原内容保留。', 'TECHNICAL', 507)
            receipt = dict(operation_id=value['operation_id'], expected_revision=value['expected_revision'], revision=feedback['revision']+1,
                values=copy.deepcopy(value['values']), saved_at=utc_now())
            item['practice_feedback'] = dict(revision=receipt['revision'], values=receipt['values'], saved_at=receipt['saved_at'], operations=feedback['operations']+[receipt])
            self._write(conn, owner, item); return feedback_operation(item, value['operation_id'])
        return self.storage._call(save)


def install_formal_practice(app, service, owner, small_json):
    import asyncio
    practices = FormalPractices(service)
    app.state.formal_practices = practices

    @app.get('/api/rehab/v2/practice/context')
    def context(request: Request):
        return practices.context(owner(request))

    @app.get('/api/rehab/v2/practice')
    async def history(request: Request):
        return await asyncio.to_thread(practices.list, owner(request))

    @app.post('/api/rehab/v2/practice')
    async def start(request: Request):
        uid, value = owner(request), await small_json(request)
        return await asyncio.to_thread(practices.create, uid, value)

    @app.get('/api/rehab/v2/practice/{identity}')
    async def record(identity: str, request: Request):
        return await asyncio.to_thread(practices.get, owner(request), identity)

    for path, method in (('finish', practices.finish), ('continue', practices.continue_group),
                         ('close-journey', practices.close_journey), ('visual-link', practices.link), ('feedback', practices.feedback)):
        # Register a closure, not a user-supplied callable/query parameter.
        def endpoint(bound):
            async def execute(identity: str, request: Request):
                uid, value = owner(request), await small_json(request)
                return await asyncio.to_thread(bound, uid, identity, value)
            return execute
        app.add_api_route('/api/rehab/v2/practice/{identity}/'+path, endpoint(method), methods=['POST'])

    @app.get('/api/rehab/v2/practice/{identity}/feedback')
    async def feedback(identity: str, request: Request):
        return await asyncio.to_thread(practices.feedback, owner(request), identity)

    @app.get('/api/rehab/v2/practice/{identity}/feedback/operations/{operation}')
    async def feedback_receipt(identity: str, operation: str, request: Request):
        return await asyncio.to_thread(practices.feedback, owner(request), identity, operation=operation)

    return practices
