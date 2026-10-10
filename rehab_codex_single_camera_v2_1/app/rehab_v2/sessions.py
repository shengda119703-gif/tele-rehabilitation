from __future__ import annotations

import copy
from contextlib import closing
import json
from pathlib import Path
from uuid import uuid4

from ..domain import digest, dumps, utc_now
from ..training import validate_training_feedback


class SessionError(ValueError):
    def __init__(self, code, status=409):
        self.code, self.status = code, status
        super().__init__(code)


def identifier(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 128:
        raise SessionError('invalid_idempotency_or_event_key', 400)
    return value


class SessionRepository:
    """Opt-in namespace on the existing Storage owning thread, not a new DB engine.

    SQLite user_version=4 stays unchanged for legacy consumers. This namespace
    owns its own schema version and only initializes when v2 is explicitly used.
    Facts/reps/terminal snapshot/receipt share a transaction. Derived reports do
    not determine whether the training fact committed.
    """
    def __init__(self, storage):
        if storage.readonly:
            raise SessionError('readonly_storage', 400)
        self.storage = storage

        def initialize(conn):
            exists = conn.execute("SELECT 1 FROM sqlite_master WHERE name='rehab_v2_meta'").fetchone()
            if exists:
                version = conn.execute('SELECT version FROM rehab_v2_meta').fetchone()[0]
                if version not in (1, 2):
                    raise SessionError('unsupported_session_schema')
            if not exists or version == 1:
                # Consistent SQLite backup, including WAL state, before adding a namespace.
                import sqlite3
                backup = storage.path.with_name(storage.path.name+'.before-rehab-v2-'+uuid4().hex+'.bak')
                with closing(sqlite3.connect(backup)) as target:
                    conn.backup(target)
            conn.executescript('''
                BEGIN IMMEDIATE;
                CREATE TABLE IF NOT EXISTS rehab_v2_meta(version INTEGER NOT NULL);
                INSERT INTO rehab_v2_meta SELECT 1 WHERE NOT EXISTS(SELECT 1 FROM rehab_v2_meta);
                CREATE TABLE IF NOT EXISTS rehab_v2_sessions(
                    id TEXT PRIMARY KEY, owner TEXT NOT NULL, create_key TEXT NOT NULL,
                    request_digest TEXT NOT NULL, payload TEXT NOT NULL, UNIQUE(owner,create_key));
                CREATE TABLE IF NOT EXISTS rehab_v2_operations(
                    owner TEXT NOT NULL, session_id TEXT NOT NULL, operation TEXT NOT NULL,
                    operation_key TEXT NOT NULL, request_digest TEXT NOT NULL, receipt TEXT NOT NULL,
                    PRIMARY KEY(owner,session_id,operation,operation_key));
                CREATE TABLE IF NOT EXISTS rehab_v2_frames(
                    session_id TEXT NOT NULL, event_id TEXT NOT NULL, seq INTEGER NOT NULL,
                    request_digest TEXT NOT NULL, status TEXT NOT NULL, reason TEXT,
                    PRIMARY KEY(session_id,event_id), UNIQUE(session_id,seq));
                CREATE TABLE IF NOT EXISTS rehab_v2_repetitions(
                    session_id TEXT NOT NULL, rep_index INTEGER NOT NULL, payload TEXT NOT NULL,
                    PRIMARY KEY(session_id,rep_index));
                CREATE TABLE IF NOT EXISTS rehab_v2_audit(
                    session_id TEXT NOT NULL, ordinal INTEGER NOT NULL, kind TEXT NOT NULL,
                    payload TEXT NOT NULL, PRIMARY KEY(session_id,ordinal));
                CREATE TABLE IF NOT EXISTS rehab_v2_feedback(
                    session_id TEXT NOT NULL, revision INTEGER NOT NULL, payload TEXT NOT NULL,
                    PRIMARY KEY(session_id,revision));
                CREATE TABLE IF NOT EXISTS rehab_v2_reports(
                    session_id TEXT PRIMARY KEY, state TEXT NOT NULL, payload TEXT, error TEXT);
                CREATE TABLE IF NOT EXISTS rehab_v2_plan_contributions(
                    ordinal INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL UNIQUE,
                    owner TEXT NOT NULL, plan_id TEXT NOT NULL,
                    plan_revision INTEGER NOT NULL, entry_key TEXT NOT NULL,
                    committed_at TEXT NOT NULL, payload TEXT NOT NULL,
                    UNIQUE(session_id,plan_id,plan_revision,entry_key));
                CREATE INDEX IF NOT EXISTS rehab_v2_contribution_plan
                    ON rehab_v2_plan_contributions(owner,plan_id,plan_revision,entry_key,ordinal);
                CREATE INDEX IF NOT EXISTS rehab_v2_contribution_history
                    ON rehab_v2_plan_contributions(owner,ordinal);
                CREATE INDEX IF NOT EXISTS rehab_v2_contribution_scope
                    ON rehab_v2_plan_contributions(owner,
                        json_extract(payload,'$.scope.participant_id'),
                        json_extract(payload,'$.scope.source_kind'),
                        json_extract(payload,'$.scope.usage_context'),
                        json_extract(payload,'$.exercise_id'),json_extract(payload,'$.side'),ordinal)
                    WHERE json_extract(payload,'$.progress_eligible')=1;
            ''')
            # Additive namespace migration. Old final receipts and visual
            # snapshots remain byte-for-byte unchanged; projection is separate.
            if not exists or version == 1:
                for row in conn.execute('SELECT payload FROM rehab_v2_sessions ORDER BY rowid').fetchall():
                    item = json.loads(row[0])
                    if item['persistence_state'] == 'finalized':
                        self._contribute(conn, item)
                conn.execute('UPDATE rehab_v2_meta SET version=2')
        storage._call(initialize)

    @staticmethod
    def _contribute(conn, item):
        from .progress import contribution
        value = contribution(item)
        conn.execute('INSERT OR IGNORE INTO rehab_v2_plan_contributions '
                     '(session_id,owner,plan_id,plan_revision,entry_key,committed_at,payload) VALUES(?,?,?,?,?,?,?)',
                     (item['session_id'], item['owner'], value['plan_id'], value['plan_revision'],
                      value['entry_key'], value['committed_at'], dumps(value)))
        row = conn.execute('SELECT payload FROM rehab_v2_plan_contributions WHERE session_id=?',
                           (item['session_id'],)).fetchone()
        if json.loads(row[0]) != value:
            raise SessionError('immutable_plan_contribution_conflict')
        return value

    @staticmethod
    def _row(conn, owner, sid):
        row = conn.execute('SELECT payload FROM rehab_v2_sessions WHERE id=? AND owner=?', (sid, owner)).fetchone()
        if not row:
            raise SessionError('session_not_found', 404)
        return json.loads(row[0])

    @staticmethod
    def _save(conn, item):
        conn.execute('UPDATE rehab_v2_sessions SET payload=? WHERE id=?', (dumps(item), item['session_id']))

    @staticmethod
    def _sync_repetitions(conn, sid, summary):
        """Extend only draft timing, never re-decide an already confirmed rep.

        Sit-to-stand is confirmed at standing. Its hold/return observations
        arrive later, before finalization. Materialized repetition rows must
        match the terminal snapshot, without writing another count event.
        All callers hold the same fact transaction and reject finalized rows.
        """
        old = {row[0]: json.loads(row[1]) for row in conn.execute(
            'SELECT rep_index,payload FROM rehab_v2_repetitions WHERE session_id=?', (sid,))}
        reps = summary['repetitions']
        indices = [rep['rep_index'] for rep in reps]
        if len(set(indices)) != len(indices) or not set(old).issubset(indices):
            raise SessionError('confirmed_repetition_fact_changed')
        if summary['completed'] != sum(rep['completion_status'] == 'COMPLETE' for rep in reps):
            raise SessionError('confirmed_repetition_count_mismatch')
        timing_fields = {'movement_timing', 'rise_time_s', 'lowering_time_s'}
        for rep in reps:
            previous = old.get(rep['rep_index'])
            if previous is not None:
                original = {key: value for key, value in previous.items() if key not in timing_fields}
                current = {key: value for key, value in rep.items() if key not in timing_fields}
                if original != current:
                    raise SessionError('confirmed_repetition_fact_changed')
            conn.execute('INSERT INTO rehab_v2_repetitions VALUES(?,?,?) '
                         'ON CONFLICT(session_id,rep_index) DO UPDATE SET payload=excluded.payload',
                         (sid, rep['rep_index'], dumps(rep)))

    @staticmethod
    def _audit(conn, sid, kind, payload):
        ordinal = conn.execute('SELECT COALESCE(MAX(ordinal),0)+1 FROM rehab_v2_audit WHERE session_id=?', (sid,)).fetchone()[0]
        conn.execute('INSERT INTO rehab_v2_audit VALUES(?,?,?,?)', (sid, ordinal, kind, dumps(payload)))

    def get(self, owner, sid):
        return self.storage._call(lambda conn: self._row(conn, owner, sid))

    def lookup_create(self, owner, key, request_digest):
        def lookup(conn):
            row = conn.execute('SELECT request_digest,payload FROM rehab_v2_sessions WHERE owner=? AND create_key=?', (owner, identifier(key))).fetchone()
            if not row:
                return None
            if row[0] != request_digest:
                raise SessionError('idempotency_payload_conflict')
            return json.loads(row[1])
        return self.storage._call(lookup)

    def create(self, owner, key, request_digest, frozen_plan, source):
        def create(conn):
            conn.execute('BEGIN IMMEDIATE')
            row = conn.execute('SELECT request_digest,payload FROM rehab_v2_sessions WHERE owner=? AND create_key=?', (owner, key)).fetchone()
            if row:
                if row[0] != request_digest:
                    raise SessionError('idempotency_payload_conflict')
                return json.loads(row[1])
            sid = uuid4().hex
            item = dict(session_id=sid, owner=owner, created_at=utc_now(), create_key=key,
                        create_request_digest=request_digest, frozen_plan=copy.deepcopy(frozen_plan),
                        source=copy.deepcopy(source), source_epoch=uuid4().hex, revision=0,
                        run_state='preparing', persistence_state='draft', end_reason=None,
                        observation_state='missing', terminal_epoch=0, control_epoch=0,
                        accepted_last_seq=-1, processed_last_seq=-1, persisted_evidence_seq=-1,
                        accepted_count=0, processed_count=0, dropped_intervals=[],
                        snapshot=None, canonical_commit=None, feedback_revision=0,
                        feedback_status='missing', derived_report_state='not_requested',
                        clinical_accuracy=None, policy_version='rehab-protocol-2.0')
            conn.execute('INSERT INTO rehab_v2_sessions VALUES(?,?,?,?,?)', (sid, owner, key, request_digest, dumps(item)))
            self._audit(conn, sid, 'create', dict(create_key=key, request_digest=request_digest))
            return item
        return self.storage._call(create)

    def lookup_operation(self, owner, sid, operation, key, request_digest):
        def lookup(conn):
            self._row(conn, owner, sid)
            row = conn.execute('SELECT request_digest,receipt FROM rehab_v2_operations WHERE owner=? AND session_id=? AND operation=? AND operation_key=?',
                               (owner, sid, operation, identifier(key))).fetchone()
            if not row:
                return None
            if row[0] != request_digest:
                raise SessionError('idempotency_payload_conflict')
            return json.loads(row[1])
        return self.storage._call(lookup)

    def accept_frame(self, owner, sid, event_id, seq, request_digest):
        def accept(conn):
            conn.execute('BEGIN IMMEDIATE')
            item = self._row(conn, owner, sid)
            row = conn.execute('SELECT request_digest,status,reason FROM rehab_v2_frames WHERE session_id=? AND event_id=?', (sid, identifier(event_id))).fetchone()
            if row:
                if row[0] != request_digest:
                    raise SessionError('frame_payload_conflict')
                return dict(duplicate=True, status=row[1], reason=row[2], session=item)
            if item['run_state'] not in ('preparing', 'active', 'recovering'):
                raise SessionError('session_not_accepting_frames')
            if item['accepted_count'] >= 24000:
                raise SessionError('formal_session_frame_limit', 429)
            if type(seq) is not int or seq < 0 or seq <= item['accepted_last_seq']:
                raise SessionError('old_or_invalid_frame_seq')
            conn.execute('INSERT INTO rehab_v2_frames VALUES(?,?,?,?,?,?)', (sid, event_id, seq, request_digest, 'accepted', None))
            item['accepted_last_seq'] = seq
            item['accepted_count'] += 1
            self._save(conn, item)
            return dict(duplicate=False, status='accepted', session=item)
        return self.storage._call(accept)

    def checkpoint(self, owner, sid, summary, *, seq=None, frame_status=None, reason=None, cue=None):
        def checkpoint(conn):
            conn.execute('BEGIN IMMEDIATE')
            item = self._row(conn, owner, sid)
            if item['persistence_state'] == 'finalized':
                return item
            if seq is not None:
                conn.execute('UPDATE rehab_v2_frames SET status=?,reason=? WHERE session_id=? AND seq=?',
                             (frame_status, reason, sid, seq))
                if frame_status == 'processed':
                    item['processed_last_seq'] = max(item['processed_last_seq'], seq)
                    item['processed_count'] += 1
                    item['persisted_evidence_seq'] = max(item['persisted_evidence_seq'], seq)
                else:
                    item['dropped_intervals'] = (item['dropped_intervals'] + [dict(from_seq=seq, to_seq=seq, reason=reason)])[-1024:]
            item['snapshot'] = copy.deepcopy(summary)
            item['observation_state'] = summary['observation_state']
            if item['run_state'] != 'finishing':
                item['run_state'] = summary['run_state']
            previous_cue = item.get('current_cue')
            if cue and (not previous_cue or previous_cue['cue_id'] != cue['cue_id']):
                self._audit(conn, sid, 'cue_issued', cue)
            elif previous_cue and not cue:
                self._audit(conn, sid, 'cue_cancelled', dict(cue_id=previous_cue['cue_id'], reason='evidence_or_phase_changed'))
            item['current_cue'] = cue
            self._sync_repetitions(conn, sid, summary)
            self._save(conn, item)
            return item
        return self.storage._call(checkpoint)

    def control(self, owner, sid, operation, key, request_digest, expected_revision, summary):
        def control(conn):
            conn.execute('BEGIN IMMEDIATE')
            item = self._row(conn, owner, sid)
            row = conn.execute('SELECT request_digest,receipt FROM rehab_v2_operations WHERE owner=? AND session_id=? AND operation=? AND operation_key=?',
                               (owner, sid, operation, key)).fetchone()
            if row:
                if row[0] != request_digest:
                    raise SessionError('idempotency_payload_conflict')
                return json.loads(row[1])
            if item['persistence_state'] == 'finalized' or item['run_state'] == 'finishing':
                raise SessionError('terminal_or_finishing_session')
            if type(expected_revision) is not int or expected_revision != item['revision']:
                raise SessionError('control_revision_conflict')
            expected_state = 'paused' if operation == 'resume' else None
            if expected_state and item['run_state'] != expected_state:
                raise SessionError('not_paused')
            if operation == 'pause' and item['run_state'] == 'paused':
                raise SessionError('already_paused')
            item.update(run_state=summary['run_state'], snapshot=summary, revision=item['revision']+1,
                        control_epoch=item['control_epoch']+1, current_cue=None)
            self._sync_repetitions(conn, sid, summary)
            receipt = dict(operation=operation, session_id=sid, revision=item['revision'], run_state=item['run_state'])
            conn.execute('INSERT INTO rehab_v2_operations VALUES(?,?,?,?,?,?)', (owner, sid, operation, key, request_digest, dumps(receipt)))
            self._audit(conn, sid, operation, receipt)
            self._save(conn, item)
            return receipt
        return self.storage._call(control)

    def freeze(self, owner, sid, key, request_digest, expected_revision, reason):
        def freeze(conn):
            conn.execute('BEGIN IMMEDIATE')
            item = self._row(conn, owner, sid)
            row = conn.execute('SELECT request_digest,receipt FROM rehab_v2_operations WHERE owner=? AND session_id=? AND operation=? AND operation_key=?',
                               (owner, sid, 'finish', key)).fetchone()
            if row:
                if row[0] != request_digest:
                    raise SessionError('idempotency_payload_conflict')
                return item
            # A different key cannot create a second fact after finalization.
            if item['persistence_state'] == 'finalized':
                conn.execute('INSERT INTO rehab_v2_operations VALUES(?,?,?,?,?,?)', (owner, sid, 'finish', key, request_digest, dumps(item['canonical_commit'])))
                return item
            if type(expected_revision) is not int or expected_revision != item['revision']:
                raise SessionError('control_revision_conflict')
            if reason not in ('completed', 'user_stopped', 'interrupted', 'input_failed', 'discomfort'):
                raise SessionError('invalid_end_reason', 400)
            if item['run_state'] == 'finishing':
                conn.execute('INSERT INTO rehab_v2_operations VALUES(?,?,?,?,?,?)', (owner, sid, 'finish', key, request_digest,
                             dumps(dict(status='finishing', session_id=sid, accepted_last_seq=item['finish_last_seq']))))
                return item
            item.update(run_state='finishing', finish_last_seq=item['accepted_last_seq'], requested_end_reason=reason,
                        finish_key=key, finish_request_digest=request_digest)
            conn.execute('INSERT INTO rehab_v2_operations VALUES(?,?,?,?,?,?)', (owner, sid, 'finish', key, request_digest,
                         dumps(dict(status='finishing', session_id=sid, accepted_last_seq=item['accepted_last_seq']))))
            self._save(conn, item)
            self._audit(conn, sid, 'freeze_boundary', dict(accepted_last_seq=item['accepted_last_seq']))
            return item
        return self.storage._call(freeze)

    def finalize(self, owner, sid, summary, reason):
        def finalize(conn):
            conn.execute('BEGIN IMMEDIATE')
            item = self._row(conn, owner, sid)
            if item['persistence_state'] == 'finalized':
                return item['canonical_commit']
            self._sync_repetitions(conn, sid, summary)
            pending = conn.execute("SELECT seq,event_id FROM rehab_v2_frames WHERE session_id=? AND status='accepted'", (sid,)).fetchall()
            for seq, event_id in pending:
                conn.execute("UPDATE rehab_v2_frames SET status='unprocessed',reason='finish_boundary_timeout' WHERE session_id=? AND event_id=?", (sid, event_id))
                item['dropped_intervals'].append(dict(from_seq=seq, to_seq=seq, reason='finish_boundary_timeout'))
            receipt = dict(commit_id=uuid4().hex, session_id=sid, status='finalized', committed_at=utc_now(),
                           end_reason=reason, completed_reps=summary['completed'],
                           accepted_last_seq=item['accepted_last_seq'], processed_last_seq=item['processed_last_seq'],
                           persisted_evidence_seq=item['persisted_evidence_seq'],
                           visual_snapshot_digest=digest(summary), plan_progress='unique_v2_contribution_committed')
            item.update(run_state='ended', persistence_state='finalized', end_reason=reason, snapshot=summary,
                        canonical_commit=receipt, terminal_epoch=item['terminal_epoch']+1, revision=item['revision']+1,
                        current_cue=None, derived_report_state='pending')
            conn.execute("UPDATE rehab_v2_operations SET receipt=? WHERE owner=? AND session_id=? AND operation='finish'", (dumps(receipt), owner, sid))
            conn.execute('INSERT OR IGNORE INTO rehab_v2_reports VALUES(?,?,?,?)', (sid, 'pending', None, None))
            value = self._contribute(conn, item)
            self._audit(conn, sid, 'plan_contribution', dict(contribution_id=value['contribution_id'],
                        plan_completed=value['plan_completed'], policy_version=value['policy_version']))
            self._audit(conn, sid, 'finalize', receipt)
            self._save(conn, item)
            return receipt
        return self.storage._call(finalize)

    def feedback(self, owner, sid, key, request_digest, expected_revision, feedback):
        value = validate_training_feedback(feedback)
        def save(conn):
            conn.execute('BEGIN IMMEDIATE')
            item = self._row(conn, owner, sid)
            row = conn.execute("SELECT request_digest,receipt FROM rehab_v2_operations WHERE owner=? AND session_id=? AND operation='feedback' AND operation_key=?", (owner, sid, key)).fetchone()
            if row:
                if row[0] != request_digest:
                    raise SessionError('idempotency_payload_conflict')
                return json.loads(row[1])
            if item['persistence_state'] != 'finalized':
                raise SessionError('feedback_requires_finalized_session')
            if type(expected_revision) is not int or expected_revision != item['feedback_revision']:
                raise SessionError('feedback_revision_conflict')
            revision = item['feedback_revision']+1
            payload = dict(value, revision=revision, recorded_at=utc_now(), session_id=sid)
            conn.execute('INSERT INTO rehab_v2_feedback VALUES(?,?,?)', (sid, revision, dumps(payload)))
            conn.execute('INSERT INTO rehab_v2_operations VALUES(?,?,?,?,?,?)', (owner, sid, 'feedback', key, request_digest, dumps(payload)))
            item.update(feedback_revision=revision, feedback_status='recorded', latest_feedback=payload)
            item['derived_report_state'] = 'pending'
            conn.execute("UPDATE rehab_v2_reports SET state='pending' WHERE session_id=?", (sid,))
            self._audit(conn, sid, 'feedback', payload)
            self._save(conn, item)
            return payload
        return self.storage._call(save)

    def report_state(self, owner, sid, state, payload=None, error=None, *, expected_feedback_revision=None):
        def save(conn):
            item = self._row(conn, owner, sid)
            if item['persistence_state'] != 'finalized':
                raise SessionError('report_requires_committed_fact')
            if expected_feedback_revision is not None and item['feedback_revision'] != expected_feedback_revision:
                return False  # Do not overwrite a newer feedback-derived report.
            conn.execute('UPDATE rehab_v2_reports SET state=?,payload=?,error=? WHERE session_id=?',
                         (state, dumps(payload) if payload else None, error, sid))
            item['derived_report_state'] = state
            self._save(conn, item)
            return True
        return self.storage._call(save)

    def report_work(self, *, include_failed=False, limit=16):
        def work(conn):
            states = ('pending', 'failed') if include_failed else ('pending',)
            placeholders = ','.join('?' for _ in states)
            return [(row[0], row[1]) for row in conn.execute(
                'SELECT s.owner,s.id FROM rehab_v2_reports r JOIN rehab_v2_sessions s ON r.session_id=s.id '
                f'WHERE r.state IN ({placeholders}) ORDER BY s.id LIMIT ?', (*states, limit))]
        return self.storage._call(work)

    def recover_unfinished(self):
        def recover(conn):
            conn.execute('BEGIN IMMEDIATE')
            recovered = []
            for row in conn.execute('SELECT owner,payload FROM rehab_v2_sessions').fetchall():
                owner, item = row[0], json.loads(row[1])
                if item['persistence_state'] != 'draft':
                    continue
                sid = item['session_id']
                snapshot = item['snapshot'] or dict(completed=0, repetitions=[], run_state='ended', phase='ENDED', observation_state='unavailable')
                current = snapshot.get('current')
                if current:
                    partial = dict(current, completion_status='UNASSESSABLE', target_status='UNKNOWN',
                        quality_status='UNASSESSABLE', quality_assessable=False,
                        reason='process_restart_interrupted', end_time_s=None)
                    snapshot.setdefault('repetitions', []).append(partial)
                snapshot.update(run_state='ended', phase='ENDED', current=None,
                                movement_timing_live=None, pending_input_gap=None,
                                recovery='process_restart_interrupted')
                self._sync_repetitions(conn, sid, snapshot)
                # Confirmed repetitions already persisted survive. Unconfirmed halves never resume.
                receipt = dict(commit_id=uuid4().hex, session_id=sid, status='finalized', committed_at=utc_now(),
                               end_reason='interrupted', completed_reps=snapshot['completed'],
                               accepted_last_seq=item['accepted_last_seq'], processed_last_seq=item['processed_last_seq'],
                               persisted_evidence_seq=item['persisted_evidence_seq'], visual_snapshot_digest=digest(snapshot),
                               plan_progress='unique_v2_contribution_committed')
                item.update(run_state='ended', persistence_state='finalized', end_reason='interrupted', snapshot=snapshot,
                            canonical_commit=receipt, terminal_epoch=item['terminal_epoch']+1,
                            revision=item['revision']+1, current_cue=None, derived_report_state='pending')
                pending = conn.execute("SELECT seq FROM rehab_v2_frames WHERE session_id=? AND status='accepted'", (sid,)).fetchall()
                for pending_row in pending:
                    item['dropped_intervals'].append(dict(from_seq=pending_row[0], to_seq=pending_row[0], reason='process_restart_unprocessed'))
                conn.execute("UPDATE rehab_v2_frames SET status='unprocessed',reason='process_restart' WHERE session_id=? AND status='accepted'", (sid,))
                conn.execute("UPDATE rehab_v2_operations SET receipt=? WHERE session_id=? AND operation='finish'", (dumps(receipt), sid))
                conn.execute('INSERT OR IGNORE INTO rehab_v2_reports VALUES(?,?,?,?)', (sid, 'pending', None, None))
                self._contribute(conn, item)
                self._audit(conn, sid, 'restart_recovery', receipt)
                self._save(conn, item)
                recovered.append(sid)
            return recovered
        return self.storage._call(recover)

    def plan_contribution(self, owner, sid):
        def get(conn):
            self._row(conn, owner, sid)
            row = conn.execute('SELECT payload FROM rehab_v2_plan_contributions WHERE session_id=? AND owner=?',
                               (sid, owner)).fetchone()
            return json.loads(row[0]) if row else None
        return self.storage._call(get)

    def plan_items(self, owner, plan_id, revision):
        """Latest committed attempt per entry. Feedback joins are read-only."""
        if not isinstance(plan_id, str) or type(revision) is not int or revision < 1:
            raise SessionError('invalid_plan_identity', 400)
        def get(conn):
            rows = conn.execute('''
                SELECT s.payload,c.payload FROM rehab_v2_plan_contributions c
                JOIN rehab_v2_sessions s ON s.id=c.session_id AND s.owner=c.owner
                WHERE c.owner=? AND c.plan_id=? AND c.plan_revision=? AND NOT EXISTS(
                    SELECT 1 FROM rehab_v2_plan_contributions newer WHERE
                        newer.owner=c.owner AND newer.plan_id=c.plan_id AND newer.plan_revision=c.plan_revision
                        AND newer.entry_key=c.entry_key AND
                        newer.ordinal>c.ordinal)
                ORDER BY c.entry_key LIMIT 107
            ''', (owner, plan_id, revision)).fetchall()
            if len(rows) > 106:
                raise SessionError('plan_entry_capacity_exceeded', 503)
            return [dict(json.loads(row[0]), plan_contribution=json.loads(row[1])) for row in rows]
        return self.storage._call(get)

    def scope_items(self, owner, scope):
        """Latest known feedback per actual person/action, across plan versions.

        JSON predicates retain the original namespace layout. This bounded six
        action-side result must not omit previous-plan discomfort during a new
        plan's eligibility check. It never grants progress to a different plan.
        """
        from ..assessment_batches import scope_key
        scope = scope_key(scope)
        def get(conn):
            rows = conn.execute('''
                SELECT s.payload,c.payload FROM rehab_v2_plan_contributions c
                JOIN rehab_v2_sessions s ON s.id=c.session_id AND s.owner=c.owner
                WHERE c.owner=? AND json_extract(c.payload,'$.scope.participant_id')=?
                    AND json_extract(c.payload,'$.scope.source_kind')=?
                    AND json_extract(c.payload,'$.scope.usage_context')=?
                    AND json_extract(c.payload,'$.progress_eligible')=1 AND NOT EXISTS(
                    SELECT 1 FROM rehab_v2_plan_contributions newer WHERE newer.owner=c.owner
                        AND json_extract(newer.payload,'$.scope.participant_id')=json_extract(c.payload,'$.scope.participant_id')
                        AND json_extract(newer.payload,'$.scope.source_kind')=json_extract(c.payload,'$.scope.source_kind')
                        AND json_extract(newer.payload,'$.scope.usage_context')=json_extract(c.payload,'$.scope.usage_context')
                        AND json_extract(newer.payload,'$.exercise_id')=json_extract(c.payload,'$.exercise_id')
                        AND json_extract(newer.payload,'$.side')=json_extract(c.payload,'$.side')
                        AND json_extract(newer.payload,'$.progress_eligible')=1 AND
                        newer.ordinal>c.ordinal)
                ORDER BY c.session_id LIMIT 7
            ''', (owner, scope['participant_id'], scope['source_kind'], scope['usage_context'])).fetchall()
            if len(rows) > 6:
                raise SessionError('pilot_action_capacity_exceeded', 503)
            return [dict(json.loads(row[0]), plan_contribution=json.loads(row[1])) for row in rows]
        return self.storage._call(get)

    def history(self, owner, *, limit=20, before=None):
        if type(limit) is not int or not 1 <= limit <= 100:
            raise SessionError('invalid_history_page_size', 400)
        def get(conn):
            parameters, clause = [owner], ''
            if before is not None:
                self._row(conn, owner, before)
                anchor = conn.execute('SELECT ordinal FROM rehab_v2_plan_contributions WHERE owner=? AND session_id=?',
                                      (owner, before)).fetchone()
                if not anchor:
                    raise SessionError('history_cursor_not_finalized', 400)
                clause = ' AND c.ordinal<?'
                parameters.append(anchor[0])
            rows = conn.execute('SELECT s.payload,c.payload FROM rehab_v2_plan_contributions c '
                'JOIN rehab_v2_sessions s ON s.id=c.session_id AND s.owner=c.owner '
                'WHERE c.owner=?'+clause+' ORDER BY c.ordinal DESC LIMIT ?',
                (*parameters, limit+1)).fetchall()
            items = []
            for row in rows[:limit]:
                item, value = json.loads(row[0]), json.loads(row[1])
                items.append(dict(session_id=item['session_id'], created_at=item['created_at'],
                    end_reason=item['end_reason'], source=item['source'], persistence_state=item['persistence_state'],
                    observation_state=item['observation_state'], feedback_status=item['feedback_status'],
                    feedback_revision=item['feedback_revision'], latest_feedback=item.get('latest_feedback'),
                    derived_report_state=item['derived_report_state'], contribution=value,
                    facts_url='/api/rehab/v2/sessions/'+item['session_id']))
            return dict(items=items, next_cursor=items[-1]['session_id'] if len(rows)>limit else None,
                        history_version='committed-rehab-v2-1', not_legacy_assessment_history=True)
        return self.storage._call(get)

    def audit_view(self, owner, sid):
        def view(conn):
            self._row(conn, owner, sid)
            return dict(frames=[dict(row) for row in conn.execute('SELECT event_id,seq,status,reason FROM rehab_v2_frames WHERE session_id=? ORDER BY seq', (sid,))],
                        repetitions=[json.loads(row[0]) for row in conn.execute('SELECT payload FROM rehab_v2_repetitions WHERE session_id=? ORDER BY rep_index', (sid,))],
                        audit=[dict(kind=row[0], payload=json.loads(row[1])) for row in conn.execute('SELECT kind,payload FROM rehab_v2_audit WHERE session_id=? ORDER BY ordinal', (sid,))])
        return self.storage._call(view)

    def pending_frames(self, owner, sid):
        def count(conn):
            self._row(conn, owner, sid)
            return conn.execute("SELECT COUNT(*) FROM rehab_v2_frames WHERE session_id=? AND status='accepted'", (sid,)).fetchone()[0]
        return self.storage._call(count)
