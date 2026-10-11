"""Backend-only explicit arrangements bound to committed v2 assessments.

No shared exercise catalog, legacy assessment, automatic prescription or client
resource is changed. An arrangement reference is user-declared, not evidence
that a professional prescribed or approved it. The visual assessment only
qualifies this protocol's observed evidence, never clinical suitability.
"""
from __future__ import annotations

import copy
from contextlib import closing
from datetime import datetime, timezone, timedelta
import json
import sqlite3
from uuid import uuid4

from ..assessment_batches import scope_key
from ..automatic_plans import feedback_block
from ..domain import digest, dumps, utc_now
from .protocols import protocol, validated_plan
from .rounds import TrainingRounds
from .sessions import SessionError, SessionRepository, identifier
from .progress import plan_progress, eligibility_session

VERSION = 'rehab-explicit-plan-1'
PREFIX = 'v2plan-'
SETTINGS = {'target_reps', 'target_sets', 'target_angle_deg', 'rest_between_sets_s',
            'timing_plan', 'needs_companion', 'use_of_hands',
            'allowed_elbow_flexion_deg', 'allowed_trunk_tilt_deg'}
QUALITY_SETTINGS = {'allowed_elbow_flexion_deg': 'elbow_flexion_deg',
                    'allowed_trunk_tilt_deg': 'trunk_tilt_deg'}
MAX_ASSESSMENT_AGE = timedelta(days=7)  # Existing engineering review window, not clinical validity.


def _keys(value, allowed, required):
    if not isinstance(value, dict) or set(value)-allowed or not required <= set(value):
        raise SessionError('invalid_explicit_plan_fields', 400)


def _text(value, maximum):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise SessionError('invalid_explicit_plan_text', 400)
    return value.strip()


class BackendPlans:
    def __init__(self, service):
        self.service = service
        self.storage = service.storage_boundary

        def initialize(conn):
            exists = conn.execute("SELECT 1 FROM sqlite_master WHERE name='rehab_v2_plan_meta'").fetchone()
            if exists:
                if conn.execute('SELECT version FROM rehab_v2_plan_meta').fetchone()[0] != 1:
                    raise SessionError('unsupported_explicit_plan_schema', 503)
            else:
                backup = self.storage.path.with_name(self.storage.path.name+'.before-explicit-plans-'+uuid4().hex+'.bak')
                with closing(sqlite3.connect(backup)) as target:
                    conn.backup(target)
            conn.executescript('''
                BEGIN IMMEDIATE;
                CREATE TABLE IF NOT EXISTS rehab_v2_plan_meta(version INTEGER NOT NULL);
                INSERT INTO rehab_v2_plan_meta SELECT 1 WHERE NOT EXISTS(SELECT 1 FROM rehab_v2_plan_meta);
                CREATE TABLE IF NOT EXISTS rehab_v2_plans(
                    id TEXT PRIMARY KEY, owner TEXT NOT NULL, revision INTEGER NOT NULL, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS rehab_v2_plan_revisions(
                    id TEXT NOT NULL, owner TEXT NOT NULL, revision INTEGER NOT NULL, payload TEXT NOT NULL,
                    PRIMARY KEY(id,revision));
                CREATE TABLE IF NOT EXISTS rehab_v2_plan_operations(
                    owner TEXT NOT NULL, operation_key TEXT NOT NULL, request_digest TEXT NOT NULL,
                    receipt TEXT NOT NULL, PRIMARY KEY(owner,operation_key));
                CREATE INDEX IF NOT EXISTS rehab_v2_assessment_scope ON rehab_v2_sessions(
                    owner,json_extract(payload,'$.frozen_plan.plan.exercise_id'),
                    json_extract(payload,'$.frozen_plan.plan.side'),
                    json_extract(payload,'$.frozen_plan.plan.participant_id'),
                    json_extract(payload,'$.source.source_kind'),json_extract(payload,'$.source.usage_context'))
                    WHERE json_extract(payload,'$.frozen_plan.plan.submode')='assessment';
            ''')
        self.storage._call(initialize)

    def scope(self, owner):
        participant = self.service.participant_provider(owner)
        return scope_key(dict(participant_id=participant,
            source_kind='SYNTHETIC' if self.service.internal_replay else 'LIVE_CAMERA',
            usage_context='TEST' if self.service.internal_replay else 'SELF_USE'))

    @staticmethod
    def _row(conn, owner, pid):
        row = conn.execute('SELECT payload FROM rehab_v2_plans WHERE id=? AND owner=?', (pid, owner)).fetchone()
        if not row:
            raise SessionError('owned_explicit_plan_required', 404)
        return json.loads(row[0])

    def get(self, owner, pid):
        return self.storage._call(lambda conn: self._row(conn, owner, pid))

    def list(self, owner, limit=20):
        if type(limit) is not int or not 1 <= limit <= 100:
            raise SessionError('invalid_plan_page_size', 400)
        return self.storage._call(lambda conn: dict(items=[json.loads(row[0]) for row in conn.execute(
            'SELECT payload FROM rehab_v2_plans WHERE owner=? ORDER BY rowid DESC LIMIT ?', (owner, limit))],
            limit=limit, policy_version=VERSION, includes_archived=True, legacy_plans_separate=True))

    @staticmethod
    def _assessment(conn, owner, scope, eid, side, sid):
        item = SessionRepository._row(conn, owner, sid)
        source, frozen = item['source'], item['frozen_plan']
        plan, snapshot = frozen['plan'], item['snapshot'] or {}
        if (plan.get('submode'), plan.get('exercise_id'), plan.get('side'), plan.get('participant_id'),
            source.get('source_kind'), source.get('usage_context')) != (
                'assessment', eid, side, scope['participant_id'], scope['source_kind'], scope['usage_context']):
            raise SessionError('assessment_action_or_scope_mismatch')
        latest = conn.execute('''SELECT id FROM rehab_v2_sessions WHERE owner=?
            AND json_extract(payload,'$.frozen_plan.plan.submode')='assessment'
            AND json_extract(payload,'$.frozen_plan.plan.exercise_id')=?
            AND json_extract(payload,'$.frozen_plan.plan.side')=?
            AND json_extract(payload,'$.frozen_plan.plan.participant_id')=?
            AND json_extract(payload,'$.source.source_kind')=?
            AND json_extract(payload,'$.source.usage_context')=? ORDER BY rowid DESC LIMIT 1''',
            (owner, eid, side, scope['participant_id'], scope['source_kind'], scope['usage_context'])).fetchone()
        if not latest or latest[0] != sid:
            raise SessionError('newer_assessment_requires_plan_review')
        receipt = item.get('canonical_commit') or {}
        if (item['persistence_state'] != 'finalized' or item['end_reason'] not in ('completed', 'user_stopped')
                or not snapshot.get('baseline') or snapshot.get('completed', 0) < 1):
            raise SessionError('committed_observable_v2_assessment_required')
        if receipt.get('visual_snapshot_digest') != digest(snapshot):
            raise SessionError('assessment_evidence_digest_mismatch')
        if frozen.get('protocol') != protocol(eid, side) or snapshot.get('protocol') != frozen['protocol']:
            raise SessionError('assessment_protocol_changed')
        try:
            completed = datetime.fromisoformat(receipt['committed_at'])
            if completed.tzinfo is None:
                raise ValueError
            age = datetime.now(timezone.utc)-completed
        except (KeyError, ValueError, TypeError):
            raise SessionError('invalid_assessment_commit_time') from None
        if age < timedelta(0) or age > MAX_ASSESSMENT_AGE:
            raise SessionError('assessment_review_window_expired')
        return dict(session_id=sid, commit_id=receipt['commit_id'],
                    visual_snapshot_digest=receipt['visual_snapshot_digest'],
                    protocol_digest=digest(frozen['protocol']),
                    measurement_contract=copy.deepcopy(snapshot['measurement_contract']),
                    evidence_kind='committed_visual_assessment', clinical_suitability_assessed=False)

    def _build(self, conn, owner, payload, pid, revision):
        scope = self.scope(owner)
        rows = payload.get('items')
        if not isinstance(rows, list) or not 1 <= len(rows) <= 6:
            raise SessionError('explicit_plan_item_capacity', 400)
        arrangement = payload.get('arrangement')
        _keys(arrangement, {'reference', 'confirmed'}, {'reference', 'confirmed'})
        if arrangement['confirmed'] is not True:
            raise SessionError('existing_arrangement_confirmation_required')
        arrangement = dict(reference=_text(arrangement['reference'], 256), confirmed=True,
                           evidence_kind='self_report', independently_verified=False)
        entries, seen = [], set()
        for row in rows:
            _keys(row, {'exercise_id', 'side', 'assessment_session_id', 'settings'},
                  {'exercise_id', 'side', 'assessment_session_id', 'settings'})
            eid, side = row['exercise_id'], row['side']
            try:
                spec = protocol(eid, side)
            except (ValueError, TypeError):
                raise SessionError('unsupported_explicit_plan_action', 400) from None
            key = eid+':'+side
            if key in seen:
                raise SessionError('duplicate_explicit_plan_entry', 400)
            seen.add(key)
            settings = row['settings']
            _keys(settings, SETTINGS, {'target_reps', 'target_sets', 'needs_companion', 'use_of_hands'})
            # Preserve explicitly provided constraints only for a protocol that
            # can observe the corresponding metric. No quality limits are prescribed.
            if any(settings.get(limit) is not None and metric not in spec['optional_quality_metrics']
                   for limit, metric in QUALITY_SETTINGS.items()):
                raise SessionError('unsupported_explicit_quality_constraint', 400)
            if (type(settings['needs_companion']) is not bool or settings['use_of_hands'] not in
                    ('not_recorded', 'allowed', 'not_allowed', 'used_hands')):
                raise SessionError('explicit_support_arrangement_required', 400)
            try:
                engine = TrainingRounds(dict(settings, exercise_id=eid, side=side, submode='training'), source_epoch='validation')
                checked = engine.plan
            except (ValueError, TypeError, KeyError):
                raise SessionError('invalid_explicit_training_arrangement', 400) from None
            normalized = {k: copy.deepcopy(checked.get(k)) for k in SETTINGS}
            reference = self._assessment(conn, owner, scope, eid, side, identifier(row['assessment_session_id']))
            entries.append(dict(key=key, exercise_id=eid, side=side, measurement_contract=spec['metric_version'],
                                protocol_digest=digest(spec), settings=normalized, assessment_reference=reference))
        return dict(scope, id=pid, revision=revision, schema_version=1, policy_version=VERSION,
                    name=_text(payload.get('name'), 80), status='ACTIVE', items=entries,
                    arrangement=arrangement, record_origin='backend_explicit_arrangement',
                    automatic_dose=False, created_or_reviewed_at=utc_now())

    def save(self, owner, payload, *, pid=None, archive=False):
        allowed = {'idempotency_key', 'name', 'items', 'arrangement', 'expected_revision'}
        required = {'idempotency_key', 'expected_revision'} if archive else {'idempotency_key', 'name', 'items', 'arrangement'}
        _keys(payload, {'idempotency_key', 'expected_revision'} if archive else allowed, required)
        if pid is not None and ('expected_revision' not in payload or type(payload['expected_revision']) is not int):
            raise SessionError('explicit_plan_revision_required', 400)
        if pid is None and 'expected_revision' in payload:
            raise SessionError('unexpected_create_revision', 400)
        key = identifier(payload['idempotency_key'])
        fingerprint = digest(dict(operation='archive' if archive else 'save', plan_id=pid, payload=payload))
        def save(conn):
            conn.execute('BEGIN IMMEDIATE')
            prior = conn.execute('SELECT request_digest,receipt FROM rehab_v2_plan_operations WHERE owner=? AND operation_key=?',
                                 (owner, key)).fetchone()
            if prior:
                if prior[0] != fingerprint:
                    raise SessionError('idempotency_payload_conflict')
                return json.loads(prior[1])
            if pid is None:
                result = self._build(conn, owner, payload, PREFIX+uuid4().hex, 1)
            else:
                current = self._row(conn, owner, pid)
                if current['revision'] != payload['expected_revision']:
                    raise SessionError('plan_revision_conflict')
                if current['status'] != 'ACTIVE':
                    raise SessionError('explicit_plan_archived')
                if archive:
                    result = dict(current, revision=current['revision']+1, status='ARCHIVED', archived_at=utc_now())
                else:
                    result = self._build(conn, owner, payload, pid, current['revision']+1)
            encoded = dumps(result)
            conn.execute('INSERT INTO rehab_v2_plan_revisions VALUES(?,?,?,?)',
                         (result['id'], owner, result['revision'], encoded))
            conn.execute('INSERT INTO rehab_v2_plans VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET '
                         'revision=excluded.revision,payload=excluded.payload', (result['id'], owner, result['revision'], encoded))
            conn.execute('INSERT INTO rehab_v2_plan_operations VALUES(?,?,?,?)', (owner, key, fingerprint, encoded))
            return result
        return self.storage._call(save)

    def assessment(self, owner, request):
        _keys(request, {'idempotency_key', 'consent', 'submode', 'exercise_id', 'side', 'view'},
              {'idempotency_key', 'consent', 'submode', 'exercise_id', 'side', 'view'})
        try:
            spec = protocol(request['exercise_id'], request['side'], request['view'])
        except (ValueError, TypeError):
            raise SessionError('unsupported_assessment_protocol', 400) from None
        scope = self.scope(owner)
        plan, _ = validated_plan(dict(exercise_id=spec['exercise_id'], side=spec['side'], view=spec['view'],
                                     participant_id=scope['participant_id'], submode='assessment'))
        pid, key = 'v2assessment-'+uuid4().hex, spec['exercise_id']+':'+spec['side']
        return dict(plan_id=pid, plan_revision=1, entry_key=key, plan=plan, progress_scope=scope,
                    reference=dict(scope, id=pid, revision=1, entry_key=key,
                                   purpose='assessment_not_training_arrangement', protocol_digest=digest(spec)))

    def _check_assessments(self, owner, record):
        def check(conn):
            for entry in record['items']:
                ref = self._assessment(conn, owner, scope_key(record), entry['exercise_id'], entry['side'],
                                       entry['assessment_reference']['session_id'])
                if ref != entry['assessment_reference'] or digest(protocol(entry['exercise_id'], entry['side'])) != entry['protocol_digest']:
                    raise SessionError('frozen_assessment_or_protocol_changed')
        self.storage._call(check)

    def view(self, owner, pid):
        record = self.get(owner, pid)
        items = self.service.repository.plan_items(owner, pid, record['revision'])
        result = plan_progress(record, [], items)
        result['eligibility_rule_ref'] = VERSION
        result['input_compatible'] = scope_key(record) == self.scope(owner)
        try:
            if record['status'] != 'ACTIVE':
                raise SessionError('explicit_plan_archived')
            if not result['input_compatible']:
                raise SessionError('actual_input_does_not_match_plan_scope')
            self._check_assessments(owner, record)
            for item in self.service.repository.scope_items(owner, record):
                view = eligibility_session(item)
                if feedback_block(view):
                    raise SessionError('previous_discomfort_or_fatigue_requires_review')
                if any(view['training_feedback'].get(k) is None for k in ('pain', 'fatigue')):
                    raise SessionError('previous_training_feedback_required')
        except SessionError as error:
            result['blocked'] = result['blocked'] or error.code
        return dict(plan=record, progress=result, entry_support={entry['key']: dict(supported=True, reason=None) for entry in record['items']},
                    manual_confirmation_required=True, frontend_not_connected=True,
                    actual_input_required=self.scope(owner), clinical_suitability_assessed=False)

    def resolve(self, owner, request):
        result = self.view(owner, request['plan_id'])
        record, progress = result['plan'], result['progress']
        if type(request.get('expected_plan_revision')) is not int or request['expected_plan_revision'] != record['revision']:
            raise SessionError('plan_revision_conflict')
        if progress['blocked']:
            raise SessionError(progress['blocked'])
        if progress['next_key'] is None or request.get('entry_key') != progress['next_key']:
            raise SessionError('explicit_plan_order_or_completion_conflict')
        if request.get('training_plan_confirmed') is not True:
            raise SessionError('manual_training_plan_confirmation_required')
        entry = next(e for e in record['items'] if e['key'] == request['entry_key'])
        try:
            if request.get('view') is None:
                raise ValueError
            protocol(entry['exercise_id'], entry['side'], request['view'])
        except ValueError:
            raise SessionError('camera_view_confirmation_required', 400) from None
        reference = dict(scope_key(record), id=record['id'], revision=record['revision'], entry_key=entry['key'],
                         item=copy.deepcopy(entry), policy_version=VERSION, arrangement=record['arrangement'])
        plan = dict(entry['settings'], exercise_id=entry['exercise_id'], side=entry['side'], view=request['view'],
                    participant_id=record['participant_id'], submode='training', training_plan_confirmed=True,
                    assessment_reference=entry['assessment_reference'], saved_plan_reference=reference)
        return dict(plan_id=record['id'], plan_revision=record['revision'], entry_key=entry['key'], plan=plan,
                    reference=reference, progress_scope=scope_key(record), eligibility=VERSION, legacy_records_unchanged=True)
