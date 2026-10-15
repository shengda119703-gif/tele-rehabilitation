"""Qt-local B01/B02 records on the original SQLite owning writer.

An arrangement is not a measured session. No readiness, repetition, assessment
or formal dose contribution is inferred here. The original automatic-plan and
measurement policies remain authoritative on their respective paths.
"""
from __future__ import annotations

import copy
import json
import os
from datetime import datetime
from uuid import UUID

from .assessment import build_body_profile, session_value
from .assessment_batches import scope_key
from .automatic_plans import feedback_block, validate_automatic_use
from .domain import digest, dumps, utc_now
from .training_plans import _selected_item, validate_training_plan

PROVIDER = 'qt-local-1'
POLICY = 'qt-saved-arrangement-guided-1'


def flow_enabled():
    """Client start-path rollback only; old owned facts remain readable/saveable."""
    return os.environ.get('ANKANG_REHAB_EXPERIENCE', 'smooth') != 'legacy'


class PracticeError(ValueError):
    def __init__(self, code, message, category='TECHNICAL'):
        super().__init__(message)
        self.code, self.category = code, category


def identity(value):
    try:
        if not isinstance(value, str) or str(UUID(value)) != value:
            raise ValueError()
    except (ValueError, AttributeError):
        raise PracticeError('INVALID_OPERATION', '练习编号无效。')
    return value


def exact(value, fields):
    if not isinstance(value, dict) or set(value) != set(fields):
        raise PracticeError('INVALID_PAYLOAD', '练习内容含未知或缺失字段。')


def context(scope):
    return dict(scope_key(scope), provider=PROVIDER, policy_version=POLICY)


def owner(scope):
    return PROVIDER + ':' + digest(scope_key(scope))


def _table(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS guided_practices(
        owner TEXT NOT NULL, id TEXT NOT NULL, payload TEXT NOT NULL,
        PRIMARY KEY(owner,id))''')


def records(conn, scope):
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='guided_practices'").fetchone():
        return []
    return [json.loads(r[0]) for r in conn.execute(
        'SELECT payload FROM guided_practices WHERE owner=? ORDER BY rowid DESC', (owner(scope),))]


def read(conn, scope, record_id):
    identity(record_id)
    item = next((r for r in records(conn, scope) if r['id'] == record_id), None)
    if item is None:
        raise PracticeError('NOT_FOUND', '未找到当前用户与来源的练习记录。', 'AUTHORIZATION')
    return item


def stopped(item):
    finish = item.get('finish_payload') or {}
    return (finish.get('reason') == 'discomfort'
            or feedback_block({'training_feedback': finish.get('feedback')})
            or any(feedback_block({'training_feedback': op['values']})
                   for op in item.get('practice_feedback', {}).get('operations', [])))


def decision(conn, scope, plan_id, revision, entry_key, confirmations):
    scope = scope_key(scope)
    result = dict(allowed=False, code=None, category='EXECUTION_BLOCK',
                  applies_to='GUIDED_PRACTICE', message=None, policy_version=POLICY,
                  companion_required=False, formal_measurement_allowed=None)

    def denied(code, message, category='EXECUTION_BLOCK'):
        return dict(result, code=code, message=message, category=category)

    if type(revision) is not int or revision < 1:
        return denied('ARRANGEMENT_REVISION_REQUIRED', '请重新选择已保存的安排。', 'MISSING_INPUT')
    row = conn.execute('SELECT payload FROM training_plans WHERE id=?', (plan_id,)).fetchone()
    plan = json.loads(row[0]) if row else None
    if not plan or scope_key(plan) != scope:
        return denied('ARRANGEMENT_NOT_OWNED', '安排不属于当前用户与来源。', 'AUTHORIZATION')
    if plan.get('revision') != revision or plan.get('status') != 'ACTIVE':
        return denied('ARRANGEMENT_CHANGED', '安排已变化，请重新核对。')
    try:
        canonical = validate_training_plan(plan)
        entry = _selected_item(plan, entry_key, scope)
        original = next(i for i in canonical['items'] if i['key'] == entry_key)
        if entry['settings'] != original['settings']:
            return denied('ARRANGEMENT_SETTINGS_CHANGED', '原安排内容需要重新核对。')
    except (ValueError, KeyError, TypeError, StopIteration):
        return denied('ARRANGEMENT_INVALID', '动作定义或原安排需要重新核对。')
    row = conn.execute('SELECT payload FROM participants WHERE id=?', (scope['participant_id'],)).fetchone()
    person = json.loads(row[0]) if row else {}
    result['companion_required'] = entry['settings']['needs_companion'] or person.get('support') == 'assisted'
    past = records(conn, scope)
    if any(stopped(p) and (p['plan_ref']['id'] == plan_id or
                          (p['exercise_id'], p['side']) == (entry['exercise_id'], entry['side'])) for p in past):
        return denied('PRACTICE_STOP_RECORDED', '本项已记录不适，请先停止并核对安排。')
    sessions = [json.loads(r[0]) for r in conn.execute('SELECT payload FROM sessions')]
    relevant = [s for s in sessions if all(session_value(s, k) == v for k, v in scope.items())
                and session_value(s, 'submode') == 'training'
                and (session_value(s, 'exercise_id'), session_value(s, 'side')) ==
                (entry['exercise_id'], entry['side'])]
    latest = max(relevant, key=lambda s: (s.get('end_utc') or '', s.get('id') or ''), default=None)
    if latest and feedback_block(latest):
        return denied('TRAINING_STOP_RECORDED', '最近训练记录了不适，请先核对安排。')
    if plan.get('record_origin') == 'assessment_rules':
        try:
            validate_automatic_use(plan, entry_key, build_body_profile(sessions, **scope), sessions, person or None)
        except ValueError as error:
            return denied('AUTOMATIC_POLICY_BLOCK', str(error))
    elif plan.get('record_origin', 'manual') != 'manual':
        return denied('ARRANGEMENT_ORIGIN_UNKNOWN', '安排来源尚未核实。')
    if confirmations.get('arrangement_confirmed') is not True:
        return denied('ARRANGEMENT_CONFIRMATION_REQUIRED', '请确认采用本人的这份已有安排。', 'MISSING_INPUT')
    if confirmations.get('support_ready') is not True:
        return denied('SUPPORT_CONFIRMATION_REQUIRED', '请按原安排准备好支撑。', 'MISSING_INPUT')
    if result['companion_required'] and confirmations.get('companion_present') is not True:
        return denied('COMPANION_REQUIRED', '本项安排需要陪同者在场。', 'MISSING_INPUT')
    return dict(result, allowed=True, code='SAVED_ARRANGEMENT_ALLOWED', category=None,
                entry=copy.deepcopy(entry), record_origin=plan.get('record_origin', 'manual'),
                name=plan['name'])


def project(conn, scope, item):
    result = copy.deepcopy(item)
    result.update(execution_allowed=False, execution_decision=None)
    if item['state'] == 'PRACTICING':
        ref = item['plan_ref']
        checked = decision(conn, scope, ref['id'], ref['revision'], ref['entry_key'], item['start_payload'])
        result.update(execution_allowed=checked['allowed'],
                      execution_decision={k: v for k, v in checked.items() if k != 'entry'})
    result['continuation'] = continuation(conn, scope, item)
    return result


def continuation(conn, scope, item):
    """Navigation permission is not measured or formal plan progress.

    Each committed group remains immutable. Only explicit group completion can
    offer a successor, derived from the original frozen saved arrangement.
    """
    if (item.get('schema_version', 1) < 2 or item['state'] != 'COMMITTED'
            or item.get('journey_closed') or (item.get('finish_payload') or {}).get('reason') != 'completed_set'):
        return None
    if item.get('successor_id'):
        return dict(kind='existing', successor_id=item['successor_id'], rest_remaining_ms=0)
    index = item['sequence_index']; sequence = item['arrangement_sequence']
    set_index = item['set_index'] + 1
    kind = 'next_set'
    if set_index > item['settings']['target_sets']:
        index += 1; set_index = 1; kind = 'next_action'
    if index >= len(sequence):
        return None
    entry = copy.deepcopy(sequence[index]); ref = item['plan_ref']
    confirmations = item['start_payload'] if kind == 'next_set' else dict(arrangement_confirmed=True)
    checked = decision(conn, scope, ref['id'], ref['revision'], entry['key'], confirmations)
    rest = item['settings']['rest_between_sets_s'] if kind == 'next_set' else None
    # Receipt wall time is from this owning local host; never compare server and
    # client monotonic clocks or claim resting is observed movement/holding.
    elapsed = (datetime.fromisoformat(utc_now()) - datetime.fromisoformat(item['ended_at'])).total_seconds()
    remaining = max(0, round((rest - elapsed) * 1000)) if rest is not None else None
    return dict(kind=kind, successor_id=None, entry=entry, sequence_index=index,
                set_index=set_index, decision=checked, rest_seconds=rest, rest_remaining_ms=remaining,
                rest_time_basis='owning_host_receipt_utc', scope='guided_navigation_only')


def _new_record(scope, value, checked, sequence, sequence_index, set_index, journey_id=None):
    entry = checked['entry']
    return dict(schema_version=2, id=value['operation_id'], journey_id=journey_id or value['operation_id'],
                context=context(scope), state='PRACTICING', start_payload=copy.deepcopy(value),
                created_at=utc_now(), plan_ref=dict(id=value['plan_id'], revision=value['plan_revision'],
                                                   entry_key=value['entry_key']),
                arrangement_ref=dict(id=value['plan_id'], revision=value['plan_revision'],
                                     entry_key=value['entry_key'], kind=checked['record_origin']),
                exercise_id=entry['exercise_id'], side=entry['side'], settings=copy.deepcopy(entry['settings']),
                execution_grant={k: v for k, v in checked.items() if k != 'entry'},
                arrangement_sequence=copy.deepcopy(sequence), sequence_index=sequence_index, set_index=set_index,
                sequence_policy='qt-guided-sequence-1', journey_closed=False, successor_id=None,
                record_origin='GUIDED_PRACTICE', visual_session_ref=None, confirmed_count=None,
                formal_plan_ref=None, assessment_ref=None, formal_plan_contribution=None,
                draft=dict(revision=0, elapsed_ms=0, count=None, operations=[]), finish_payload=None)


def prepare(conn, scope, plan_id, revision, entry_key):
    checked = decision(conn, scope, plan_id, revision, entry_key, {})
    row = conn.execute('SELECT payload FROM training_plans WHERE id=?', (plan_id,)).fetchone()
    plan = json.loads(row[0]) if row else None
    if plan and scope_key(plan) != scope_key(scope):
        plan = None
    entry = next((i for i in (plan or {}).get('items', []) if i['key'] == entry_key), None)
    past = records(conn, scope)
    active = next((r for r in past if r['state'] == 'PRACTICING'), None)
    if active is None:
        active = next((r for r in past if r['plan_ref']['id'] == plan_id
                       and r['plan_ref']['revision'] == revision and not r.get('successor_id')
                       and continuation(conn, scope, r) is not None), None)
    return dict(context=context(scope), plan_ref=dict(id=plan_id, revision=revision, entry_key=entry_key),
                entry=copy.deepcopy(entry) if checked['category'] in (None, 'MISSING_INPUT') else None,
                name=(plan or {}).get('name'), decision=checked,
                open_record=project(conn, scope, active) if active else None)


def create(conn, scope, value):
    exact(value, ('operation_id', 'plan_id', 'plan_revision', 'entry_key',
                  'arrangement_confirmed', 'support_ready', 'companion_present'))
    identity(value['operation_id'])
    if any(type(value[k]) is not bool for k in ('arrangement_confirmed', 'support_ready', 'companion_present')):
        raise PracticeError('CONFIRMATION_REQUIRED', '请明确确认安排、支撑和陪同情况。', 'MISSING_INPUT')
    conn.execute('BEGIN IMMEDIATE')
    _table(conn)
    previous = records(conn, scope)
    old = next((r for r in previous if r['id'] == value['operation_id']), None)
    if old:
        if old['start_payload'] != value:
            raise PracticeError('START_KEY_CONFLICT', '练习编号已用于另一份内容。')
        return project(conn, scope, old)
    checked = decision(conn, scope, value['plan_id'], value['plan_revision'], value['entry_key'], value)
    if not checked['allowed']:
        raise PracticeError(checked['code'], checked['message'], checked['category'])
    if any(r['state'] == 'PRACTICING' for r in previous):
        raise PracticeError('ORIGINAL_PRACTICE_OPEN', '请先返回并结束上次练习。')
    plan = json.loads(conn.execute('SELECT payload FROM training_plans WHERE id=?', (value['plan_id'],)).fetchone()[0])
    sequence = validate_training_plan(plan)['items']
    index = next(i for i, entry in enumerate(sequence) if entry['key'] == value['entry_key'])
    item = _new_record(scope, value, checked, sequence, index, 1)
    conn.execute('INSERT INTO guided_practices VALUES (?,?,?)', (owner(scope), item['id'], dumps(item)))
    return project(conn, scope, item)


def _write(conn, scope, item):
    conn.execute('UPDATE guided_practices SET payload=? WHERE owner=? AND id=?',
                 (dumps(item), owner(scope), item['id']))


def continue_practice(conn, scope, record_id, value):
    exact(value, ('operation_id', 'arrangement_confirmed', 'support_ready', 'companion_present'))
    identity(value['operation_id'])
    if any(type(value[k]) is not bool for k in ('arrangement_confirmed', 'support_ready', 'companion_present')):
        raise PracticeError('CONFIRMATION_REQUIRED', '请核对下一项的支撑和陪同情况。', 'MISSING_INPUT')
    conn.execute('BEGIN IMMEDIATE')
    previous = read(conn, scope, record_id)
    existing = next((r for r in records(conn, scope) if r['id'] == value['operation_id']), None)
    if existing:
        if existing.get('predecessor_id') != record_id or existing.get('continue_payload') != value:
            raise PracticeError('CONTINUE_KEY_CONFLICT', '继续编号已用于另一份内容。')
        return project(conn, scope, existing)
    following = continuation(conn, scope, previous)
    if not following or following.get('successor_id'):
        raise PracticeError('NO_NEXT_GROUP', '本组没有待开始的下一项，请查看原记录。')
    if any(r['state'] == 'PRACTICING' for r in records(conn, scope)):
        raise PracticeError('ORIGINAL_PRACTICE_OPEN', '请先返回并结束上次练习。')
    ref = previous['plan_ref']; entry = following['entry']
    checked = decision(conn, scope, ref['id'], ref['revision'], entry['key'], value)
    if not checked['allowed']:
        raise PracticeError(checked['code'], checked['message'], checked['category'])
    if checked['entry'] != entry:
        raise PracticeError('ARRANGEMENT_SETTINGS_CHANGED', '原安排内容已变化，请重新核对。')
    if following['rest_remaining_ms']:
        raise PracticeError('REST_PENDING', '按原安排休息后再继续。', 'MISSING_INPUT')
    payload = dict(value, plan_id=ref['id'], plan_revision=ref['revision'], entry_key=entry['key'])
    item = _new_record(scope, payload, checked, previous['arrangement_sequence'],
                       following['sequence_index'], following['set_index'], previous['journey_id'])
    item.update(predecessor_id=record_id, continue_payload=copy.deepcopy(value))
    previous['successor_id'] = item['id']
    _write(conn, scope, previous)
    conn.execute('INSERT INTO guided_practices VALUES (?,?,?)', (owner(scope), item['id'], dumps(item)))
    return project(conn, scope, item)


def close_journey(conn, scope, record_id, value):
    exact(value, ('operation_id',)); identity(value['operation_id'])
    conn.execute('BEGIN IMMEDIATE')
    item = read(conn, scope, record_id)
    if item.get('close_payload'):
        if item['close_payload'] != value:
            raise PracticeError('CLOSE_KEY_CONFLICT', '本次已结束，请查看原记录。')
        return project(conn, scope, item)
    if item['state'] != 'COMMITTED' or item.get('successor_id'):
        raise PracticeError('GROUP_STATE_CHANGED', '请先核对当前组记录。')
    item.update(journey_closed=True, journey_closed_at=utc_now(), close_payload=copy.deepcopy(value))
    _write(conn, scope, item)
    return project(conn, scope, item)


def _count(value):
    if value is not None and (type(value) is not int or not 0 <= value <= 10000):
        raise PracticeError('INVALID_COUNT', '请填写本组实际总次数，或留空。', 'MISSING_INPUT')


def _elapsed(value):
    if type(value) is not int or not 0 <= value <= 86400000:
        raise PracticeError('INVALID_ELAPSED', '练习页面时间无效。')


def save_draft(conn, scope, record_id, value):
    exact(value, ('operation_id', 'expected_revision', 'elapsed_ms', 'count'))
    identity(value['operation_id']); _elapsed(value['elapsed_ms']); _count(value['count'])
    conn.execute('BEGIN IMMEDIATE')
    item = read(conn, scope, record_id)
    if item['state'] != 'PRACTICING':
        raise PracticeError('PRACTICE_ENDED', '本次练习已经结束，请查看原记录。')
    draft = item['draft']
    old = next((r for r in draft['operations'] if r['operation_id'] == value['operation_id']), None)
    if old:
        if old != value:
            raise PracticeError('DRAFT_KEY_CONFLICT', '草稿编号已用于另一份内容。')
        return project(conn, scope, item)
    if type(value['expected_revision']) is not int or value['expected_revision'] != draft['revision']:
        raise PracticeError('DRAFT_REVISION_CONFLICT', '原练习草稿已更新，请先核对。')
    if value['elapsed_ms'] < draft['elapsed_ms'] or len(draft['operations']) >= 100:
        raise PracticeError('DRAFT_BOUNDARY_INVALID', '草稿时间或修改次数需要核对；原记录保留。')
    item['draft'] = dict(revision=draft['revision'] + 1, elapsed_ms=value['elapsed_ms'],
                         count=value['count'], operations=draft['operations'] + [copy.deepcopy(value)])
    _write(conn, scope, item)
    return project(conn, scope, item)


def finish(conn, scope, record_id, value):
    exact(value, ('operation_id', 'count', 'elapsed_ms', 'reason', 'feedback'))
    identity(value['operation_id']); _count(value['count']); _elapsed(value['elapsed_ms'])
    if value['reason'] not in ('ended', 'completed_set', 'discomfort'):
        raise PracticeError('INVALID_END_REASON', '请核对结束方式。')
    exact(value['feedback'], ('pain', 'fatigue'))
    if any(n is not None and (type(n) is not int or not 0 <= n <= 10) for n in value['feedback'].values()):
        raise PracticeError('INVALID_FEEDBACK', '请填写真实感受，或留空。', 'MISSING_INPUT')
    conn.execute('BEGIN IMMEDIATE')
    item = read(conn, scope, record_id)
    if item['finish_payload']:
        if item['finish_payload'] != value:
            raise PracticeError('FINISH_KEY_CONFLICT', '本次已保存，请核对原结束记录。')
        return project(conn, scope, item)
    if value['elapsed_ms'] < item['draft']['elapsed_ms']:
        raise PracticeError('ELAPSED_BEFORE_DRAFT', '结束时间早于已保存草稿，请核对原记录。')
    item.update(state='COMMITTED', ended_at=utc_now(), finish_payload=copy.deepcopy(value),
                self_reported_count=value['count'], count_scope='set_total', set_index=item.get('set_index', 1),
                elapsed_source='frontend_active_time_not_observed_hold',
                record_origin='SELF_RECORDED' if value['count'] is not None else 'GUIDED_PRACTICE')
    if value['reason'] != 'completed_set': item['journey_closed'] = True
    item['mode_segments'] = [dict(mode='GUIDED', start=item['created_at'], end=item['ended_at'],
                                 reason='allowed_saved_arrangement', time_basis='sqlite_receipt_time',
                                 source='GUIDED_PRACTICE', set_index=item.get('set_index', 1))]
    _write(conn, scope, item)
    return project(conn, scope, item)


def execute(store, command, scope, args):
    """Called only by Runtime, never from a Qt paint/event handler."""
    scope = scope_key(scope)
    def run(conn):
        if command == 'practice_prepare':
            return prepare(conn, scope, args['id'], args['revision'], args['entry_key'])
        if command == 'practice_start':
            return create(conn, scope, args['payload'])
        if command == 'practice_get':
            return project(conn, scope, read(conn, scope, args['id']))
        if command == 'practice_draft':
            return save_draft(conn, scope, args['id'], args['payload'])
        if command == 'practice_finish':
            return finish(conn, scope, args['id'], args['payload'])
        if command == 'practice_continue':
            return continue_practice(conn, scope, args['id'], args['payload'])
        if command == 'practice_close_journey':
            return close_journey(conn, scope, args['id'], args['payload'])
        if command == 'practice_history':
            return [project(conn, scope, r) for r in records(conn, scope)]
        raise PracticeError('UNKNOWN_COMMAND', '不支持的练习操作。')
    return store._call(run)
