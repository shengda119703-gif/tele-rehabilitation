from __future__ import annotations

import copy
from concurrent.futures import Future
import json
from pathlib import Path
import queue
import sqlite3
import threading

from .domain import dumps, utc_now
from .participants import legacy_participant, validate_participant


class Storage:
    """One owning SQLite thread. Critical writes always return a commit result."""
    def __init__(self, path, readonly=False):
        self.path, self.readonly = Path(path), readonly
        self.jobs = queue.Queue()
        self.ready = Future()
        self.closed = False
        self.thread = threading.Thread(target=self._run, name='sqlite-writer', daemon=True)
        self.thread.start()
        self.ready.result(timeout=10)

    def _run(self):
        conn = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            existed = self.path.exists()
            conn = sqlite3.connect(self.path.as_uri()+'?mode=ro', uri=True) if self.readonly else sqlite3.connect(self.path)
            conn.row_factory = sqlite3.Row
            conn.execute('PRAGMA busy_timeout=4000')
            version = conn.execute('PRAGMA user_version').fetchone()[0]
            if version not in (0, 1, 2, 3, 4):
                raise RuntimeError('数据库版本高于本程序支持范围，原数据已保留')
            if not self.readonly:
                if version < 4 and existed:
                    backup_path = self.path.with_name(self.path.name+'.before-v4-'+utc_now().replace(':', '-')+'.bak')
                    with sqlite3.connect(backup_path) as backup:
                        conn.backup(backup)
                if version == 0 and existed:
                    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                    if tables:
                        raise RuntimeError('发现未知旧数据库，已备份；需要显式迁移，未覆盖原表')
                conn.executescript('''
                    BEGIN IMMEDIATE;
                    CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY, start_utc TEXT, scene_id TEXT, payload TEXT NOT NULL);
                    CREATE TABLE IF NOT EXISTS config_snapshots(session_id TEXT PRIMARY KEY, payload TEXT NOT NULL);
                    CREATE TABLE IF NOT EXISTS repetitions(session_id TEXT, ordinal INTEGER, payload TEXT NOT NULL, PRIMARY KEY(session_id,ordinal));
                    CREATE TABLE IF NOT EXISTS activity_intervals(session_id TEXT, ordinal INTEGER, payload TEXT NOT NULL, PRIMARY KEY(session_id,ordinal));
                    CREATE TABLE IF NOT EXISTS tasks(session_id TEXT, ordinal INTEGER, payload TEXT NOT NULL, PRIMARY KEY(session_id,ordinal));
                    CREATE TABLE IF NOT EXISTS events(id TEXT PRIMARY KEY, status TEXT NOT NULL, payload TEXT NOT NULL);
                    CREATE TABLE IF NOT EXISTS scene_profiles(id TEXT PRIMARY KEY, payload TEXT NOT NULL);
                    CREATE TABLE IF NOT EXISTS devices(id TEXT PRIMARY KEY, payload TEXT NOT NULL);
                    CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY, at_utc TEXT NOT NULL, action TEXT NOT NULL, payload TEXT NOT NULL);
                    CREATE TABLE IF NOT EXISTS participants(id TEXT PRIMARY KEY, revision INTEGER NOT NULL, payload TEXT NOT NULL);
                    CREATE TABLE IF NOT EXISTS assessment_batches(id TEXT PRIMARY KEY, participant_id TEXT NOT NULL, revision INTEGER NOT NULL, payload TEXT NOT NULL);
                    CREATE TABLE IF NOT EXISTS training_plans(id TEXT PRIMARY KEY, participant_id TEXT NOT NULL, revision INTEGER NOT NULL, status TEXT NOT NULL, payload TEXT NOT NULL);
                    CREATE INDEX IF NOT EXISTS training_plans_participant ON training_plans(participant_id);
                    PRAGMA user_version=4;
                    COMMIT;
                ''')
                conn.commit()
            self.ready.set_result(True)
        except Exception as exc:
            self.ready.set_exception(exc)
            if conn is not None:
                conn.close()
            return
        while True:
            job = self.jobs.get()
            if job is None:
                break
            fn, future = job
            try:
                result = fn(conn)
                conn.commit()
                future.set_result(result)
            except Exception as exc:
                conn.rollback()
                future.set_exception(exc)
        conn.close()

    def _call(self, fn):
        if self.closed:
            raise RuntimeError('数据库已关闭')
        future = Future()
        self.jobs.put((fn, future))
        return future.result(timeout=15)

    def close(self):
        if not self.closed:
            self.closed = True
            self.jobs.put(None)
            self.thread.join(timeout=6)
            if self.thread.is_alive():
                raise RuntimeError('数据库线程尚未结束')

    @staticmethod
    def authorized_snapshot(snapshot):
        item = copy.deepcopy(snapshot)
        if not item.get('config_snapshot', {}).get('poses_consent', False):
            item.pop('poses', None)
        item.pop('raw_frames', None)
        return item

    def save_session(self, snapshot):
        item = self.authorized_snapshot(snapshot)
        def save(c):
            c.execute('INSERT OR REPLACE INTO sessions VALUES (?,?,?,?)',
                      (item['id'], item.get('start_utc'), item.get('scene_id'), dumps(item)))
            c.execute('INSERT OR REPLACE INTO config_snapshots VALUES (?,?)',
                      (item['id'], dumps(item.get('config_snapshot', {}))))
            for table, key in (('repetitions', 'repetitions'), ('activity_intervals', 'intervals'), ('tasks', 'tasks')):
                c.execute(f'DELETE FROM {table} WHERE session_id=?', (item['id'],))
                c.executemany(f'INSERT INTO {table} VALUES (?,?,?)',
                              [(item['id'], i, dumps(r)) for i, r in enumerate(item.get(key, []))])
            for event in item.get('events', []):
                # Never overwrite a user's ACK / RESOLVED with an old run snapshot.
                c.execute('INSERT OR IGNORE INTO events VALUES (?,?,?)', (event['id'], event['status'], dumps(event)))
            return item['id']
        return self._call(save)

    def get_session(self, sid):
        row = self._call(lambda c: c.execute('SELECT payload FROM sessions WHERE id=?', (sid,)).fetchone())
        return json.loads(row['payload']) if row else None

    def get_assessment_batch(self, batch_id):
        def get(c):
            if not c.execute("SELECT 1 FROM sqlite_master WHERE name='assessment_batches' AND type='table'").fetchone():
                return None
            row = c.execute('SELECT payload FROM assessment_batches WHERE id=?', (batch_id,)).fetchone()
            return json.loads(row[0]) if row else None
        return self._call(get)

    def current_assessment_batch(self, scope):
        from .assessment_batches import scope_key
        key = scope_key(scope)
        def get(c):
            if not c.execute("SELECT 1 FROM sqlite_master WHERE name='assessment_batches' AND type='table'").fetchone():
                return None
            for row in c.execute('SELECT payload FROM assessment_batches WHERE participant_id=? ORDER BY rowid DESC', (key['participant_id'],)):
                batch = json.loads(row[0])
                if batch['status'] == 'ACTIVE' and scope_key(batch) == key:
                    return batch
            return None
        return self._call(get)

    def create_assessment_batch(self, scope, items):
        from .assessment_batches import new_batch, scope_key
        batch = new_batch(scope, items)
        def save(c):
            c.execute('BEGIN IMMEDIATE')
            for row in c.execute('SELECT payload FROM assessment_batches WHERE participant_id=?', (batch['participant_id'],)):
                previous = json.loads(row[0])
                if previous['status'] == 'ACTIVE' and scope_key(previous) == scope_key(batch):
                    raise ValueError('当前已有评估清单，请继续或先结束该轮评估')
            c.execute('INSERT INTO assessment_batches VALUES (?,?,?,?)',
                      (batch['id'], batch['participant_id'], batch['revision'], dumps(batch)))
            return batch
        return self._call(save)

    def change_assessment_batch(self, batch_id, action, *, expected_revision, entry_key=None, reason=None):
        from .assessment_batches import batch_view
        if type(expected_revision) is not int or expected_revision < 1:
            raise ValueError('评估清单版本无效，请重新打开')
        if action not in ('skip', 'restore', 'close'):
            raise ValueError('未知评估清单操作')
        if action == 'skip' and (not isinstance(reason, str) or not reason.strip() or len(reason.strip()) > 500):
            raise ValueError('请填写跳过原因，最多 500 字')
        def change(c):
            c.execute('BEGIN IMMEDIATE')
            row = c.execute('SELECT payload FROM assessment_batches WHERE id=?', (batch_id,)).fetchone()
            batch = json.loads(row[0]) if row else None
            if batch is None or batch['status'] != 'ACTIVE' or batch['revision'] != expected_revision:
                raise ValueError('评估清单已更新或已结束，请重新打开')
            sessions = [json.loads(r[0]) for r in c.execute('SELECT payload FROM sessions')]
            view = batch_view(batch, sessions)
            if any(i['status'] == 'IN_PROGRESS' for i in view['items']):
                raise ValueError('请先结束并保存当前评估')
            if action == 'close':
                batch.update(status='CLOSED', closed_utc=utc_now())
            else:
                item = next((i for i in batch['items'] if i['key'] == entry_key), None)
                resolved = next((i for i in view['items'] if i['key'] == entry_key), None)
                if item is None or (action == 'skip' and resolved['status'] == 'ASSESSED'):
                    raise ValueError('请选择待测或需补测项目；不能用跳过覆盖已评估结果')
                item['skip_reason'] = reason.strip() if action == 'skip' else None
            batch['revision'] += 1
            c.execute('UPDATE assessment_batches SET revision=?,payload=? WHERE id=?',
                      (batch['revision'], dumps(batch), batch_id))
            c.execute('INSERT INTO audit(at_utc,action,payload) VALUES (?,?,?)',
                      (utc_now(), 'assessment_batch_'+action, dumps({'id': batch_id, 'entry_key': entry_key, 'reason': reason})))
            return batch
        return self._call(change)

    def list_sessions(self):
        return self._call(lambda c: [json.loads(r[0]) for r in c.execute('SELECT payload FROM sessions ORDER BY start_utc DESC')])

    def get_training_plan(self, plan_id):
        def get(c):
            if not c.execute("SELECT 1 FROM sqlite_master WHERE name='training_plans' AND type='table'").fetchone():
                return None
            row = c.execute('SELECT payload FROM training_plans WHERE id=?', (plan_id,)).fetchone()
            return json.loads(row[0]) if row else None
        return self._call(get)

    def list_training_plans(self, scope, *, include_archived=False):
        from .assessment_batches import scope_key
        key = scope_key(scope)
        def collect(c):
            if not c.execute("SELECT 1 FROM sqlite_master WHERE name='training_plans' AND type='table'").fetchone():
                return []
            values = [json.loads(row[0]) for row in c.execute(
                'SELECT payload FROM training_plans WHERE participant_id=? ORDER BY rowid DESC', (key['participant_id'],))]
            return [value for value in values if scope_key(value) == key
                    and (include_archived or value['status'] == 'ACTIVE')]
        return self._call(collect)

    def save_training_plan(self, value, *, expected_revision, status='ACTIVE'):
        from .assessment_batches import scope_key
        from .training_plans import validate_training_plan
        item = validate_training_plan(copy.deepcopy(value))
        if status not in ('ACTIVE', 'PENDING_DOCTOR'):
            raise ValueError('训练方案保存状态无效')
        if type(expected_revision) is not int or expected_revision < 0:
            raise ValueError('计划版本无效，请重新打开计划库')
        def save(c):
            c.execute('BEGIN IMMEDIATE')
            row = c.execute('SELECT revision,payload FROM training_plans WHERE id=?', (item['id'],)).fetchone()
            if (row[0] if row else 0) != expected_revision:
                raise ValueError('计划已更新，请重新打开；本次草稿尚未保存')
            previous = json.loads(row[1]) if row else {}
            if previous.get('status') == 'PENDING_DOCTOR' and status == 'ACTIVE':
                raise ValueError('医生方案尚未确认，不能从普通编辑入口激活')
            if previous and scope_key(previous) != scope_key(item):
                raise ValueError('计划不属于当前用户与来源，不能改变所属范围')
            if previous.get('status') == 'ARCHIVED':
                raise ValueError('请先恢复已归档计划，再进行编辑')
            at = utc_now()
            item.update(revision=expected_revision+1, status=status,
                        created_utc=previous.get('created_utc') or at, updated_utc=at)
            c.execute('INSERT OR REPLACE INTO training_plans VALUES (?,?,?,?,?)',
                      (item['id'], item['participant_id'], item['revision'], item['status'], dumps(item)))
            c.execute('INSERT INTO audit(at_utc,action,payload) VALUES (?,?,?)',
                      (at, 'save_training_plan', dumps({'id': item['id'], 'revision': item['revision']})))
            return item
        return self._call(save)

    def activate_pending_training_plan(self, plan_id, scope, *, expected_revision):
        from .assessment_batches import scope_key
        def activate(c):
            c.execute('BEGIN IMMEDIATE')
            row = c.execute('SELECT payload FROM training_plans WHERE id=?', (plan_id,)).fetchone()
            value = json.loads(row[0]) if row else None
            if not value or scope_key(value) != scope_key(scope) or value['revision'] != expected_revision:
                raise ValueError('待确认医生方案已变化，请重新核对')
            if value['status'] == 'ACTIVE':
                return value
            if value['status'] != 'PENDING_DOCTOR':
                raise ValueError('此方案不是待确认医生方案')
            value.update(status='ACTIVE', updated_utc=utc_now())
            c.execute('UPDATE training_plans SET status=?,payload=? WHERE id=?', ('ACTIVE', dumps(value), plan_id))
            c.execute('INSERT INTO audit(at_utc,action,payload) VALUES (?,?,?)', (utc_now(), 'activate_doctor_plan', dumps({'id': plan_id, 'revision': expected_revision})))
            return value
        return self._call(activate)

    def set_training_plan_archived(self, plan_id, scope, archived, *, expected_revision):
        from .assessment_batches import scope_key
        key = scope_key(scope)
        if type(archived) is not bool or type(expected_revision) is not int or expected_revision < 1:
            raise ValueError('计划操作或版本无效')
        def change(c):
            c.execute('BEGIN IMMEDIATE')
            row = c.execute('SELECT payload FROM training_plans WHERE id=?', (plan_id,)).fetchone()
            previous = json.loads(row[0]) if row else None
            if previous is None or scope_key(previous) != key:
                raise ValueError('计划不存在或不属于当前用户与来源')
            if previous.get('status') == 'PENDING_DOCTOR':
                raise ValueError('医生方案尚未确认，不能从归档入口恢复或激活')
            if previous['revision'] != expected_revision:
                raise ValueError('计划已更新，请重新打开后操作')
            status = 'ARCHIVED' if archived else 'ACTIVE'
            if previous['status'] == status:
                return previous
            previous.update(status=status, revision=expected_revision+1, updated_utc=utc_now())
            c.execute('UPDATE training_plans SET revision=?,status=?,payload=? WHERE id=?',
                      (previous['revision'], status, dumps(previous), plan_id))
            c.execute('INSERT INTO audit(at_utc,action,payload) VALUES (?,?,?)',
                      (utc_now(), 'archive_training_plan' if archived else 'restore_training_plan',
                       dumps({'id': plan_id, 'revision': previous['revision']})))
            return previous
        return self._call(change)

    def get_participant(self, participant_id):
        def get(c):
            if not c.execute("SELECT 1 FROM sqlite_master WHERE name='participants' AND type='table'").fetchone():
                return None  # Read-only v1 database, never migrate through a read.
            row = c.execute('SELECT payload FROM participants WHERE id=?', (participant_id,)).fetchone()
            return json.loads(row[0]) if row else None
        return self._call(get)

    def list_participants(self):
        def collect(c):
            tables = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            people = {r[0]: json.loads(r[1]) for r in c.execute('SELECT id,payload FROM participants')} if 'participants' in tables else {}
            # Old records remain untouched. Unregistered IDs are shown as such,
            # not silently converted into populated personal profiles.
            for table in ('sessions', 'scene_profiles'):
                if table not in tables:
                    continue
                for row in c.execute(f'SELECT payload FROM {table}'):
                    item = json.loads(row[0])
                    pid = (item.get('participant_id') or item.get('config_snapshot', {}).get('plan', {}).get('participant_id')
                           or item.get('plan', {}).get('participant_id'))
                    if isinstance(pid, str) and pid.strip() and pid not in people:
                        people[pid] = legacy_participant(pid)
            return sorted(people.values(), key=lambda p: (p['display_name'].casefold(), p['participant_id']))
        return self._call(collect)

    def save_participant(self, profile, *, expected_revision):
        item = validate_participant(copy.deepcopy(profile))
        if type(expected_revision) is not int or expected_revision < 0:
            raise ValueError('档案版本无效，请重新打开档案')
        def save(c):
            c.execute('BEGIN IMMEDIATE')
            row = c.execute('SELECT revision,payload FROM participants WHERE id=?', (item['participant_id'],)).fetchone()
            if (row[0] if row else 0) != expected_revision:
                raise ValueError('档案已更新，请关闭后重新打开；本次填写尚未保存')
            previous = json.loads(row[1]) if row else {}
            at = utc_now()
            item.update(revision=expected_revision+1, record_origin='manual',
                        created_utc=previous.get('created_utc') or at, updated_utc=at)
            c.execute('INSERT OR REPLACE INTO participants VALUES (?,?,?)',
                      (item['participant_id'], item['revision'], dumps(item)))
            c.execute('INSERT INTO audit(at_utc,action,payload) VALUES (?,?,?)',
                      (at, 'save_participant', dumps({'participant_id': item['participant_id'], 'revision': item['revision']})))
            return item
        return self._call(save)

    def recover_unfinished(self):
        def recover(c):
            count = 0
            for row in c.execute('SELECT id,payload FROM sessions').fetchall():
                item = json.loads(row['payload'])
                if item.get('status') == 'RUNNING':
                    item.update(status='INTERRUPTED', stop_reason='unexpected_exit', end_utc=None,
                                recovered_utc=utc_now(), recovery_note='上次非正常退出；仅保留当时成功写入的记录，未补造结束时间或动作。')
                    c.execute('UPDATE sessions SET payload=? WHERE id=?', (dumps(item), row['id']))
                    count += 1
            return count
        return self._call(recover)

    def save_training_feedback(self, sid, feedback, *, expected_revision):
        from .training import validate_training_feedback
        value = validate_training_feedback(copy.deepcopy(feedback))
        if type(expected_revision) is not int or expected_revision < 0:
            raise ValueError('训练感受版本无效，请重新打开报告')
        def save(c):
            c.execute('BEGIN IMMEDIATE')
            row = c.execute('SELECT payload FROM sessions WHERE id=?', (sid,)).fetchone()
            if row is None:
                raise ValueError('报告不存在，训练感受未保存')
            session = json.loads(row[0])
            mode = session.get('submode') or (session.get('config_snapshot') or {}).get('plan', {}).get('submode')
            if session.get('scene_id') != 'rehab' or mode != 'training' or session.get('status') not in ('FINISHED', 'INTERRUPTED'):
                raise ValueError('只能为已结束的训练填写感受')
            previous = session.get('training_feedback') or {}
            if previous.get('revision', 0) != expected_revision:
                raise ValueError('训练感受已更新，请重新打开报告；本次填写尚未保存')
            value.update(revision=expected_revision+1, recorded_utc=utc_now())
            session['training_feedback'] = value
            c.execute('UPDATE sessions SET payload=? WHERE id=?', (dumps(session), sid))
            return session
        return self._call(save)

    def delete_session(self, sid):
        def delete(c):
            for table in ('config_snapshots', 'repetitions', 'activity_intervals', 'tasks'):
                c.execute(f'DELETE FROM {table} WHERE session_id=?', (sid,))
            c.execute('DELETE FROM sessions WHERE id=?', (sid,))
            c.execute('INSERT INTO audit(at_utc,action,payload) VALUES (?,?,?)', (utc_now(), 'delete_session', dumps({'id': sid})))
        self._call(delete)

    def save_event(self, event):
        return self._call(lambda c: c.execute('INSERT OR IGNORE INTO events VALUES (?,?,?)',
                          (event['id'], event.get('status', 'OPEN'), dumps(event))).rowcount)

    def list_events(self, unresolved=False):
        query = "SELECT payload FROM events WHERE status!='RESOLVED'" if unresolved else 'SELECT payload FROM events'
        return self._call(lambda c: [json.loads(r[0]) for r in c.execute(query+' ORDER BY rowid DESC')])

    def transition_event(self, eid, status, operator, note):
        def change(c):
            row = c.execute('SELECT payload FROM events WHERE id=?', (eid,)).fetchone()
            if row is None:
                raise ValueError('事件不存在')
            item = json.loads(row[0])
            expected = {'ACKNOWLEDGED': ('OPEN',), 'CLAIMED': ('ACKNOWLEDGED',), 'RESOLVED': ('ACKNOWLEDGED', 'CLAIMED')}
            if item['status'] not in expected.get(status, ()) or not operator.strip():
                raise ValueError('请先查看事件，再记录处理结果')
            if status == 'RESOLVED' and not note.strip():
                raise ValueError('关闭事件需要填写处理结果')
            at = utc_now()
            item.update(status=status)
            item[{'ACKNOWLEDGED': 'human_ack_time', 'CLAIMED': 'human_claim_time', 'RESOLVED': 'human_resolved_time'}[status]] = at
            item.setdefault('history', []).append({'status': status, 'at_utc': at, 'operator': operator, 'note': note})
            c.execute('UPDATE events SET status=?,payload=? WHERE id=?', (status, dumps(item), eid))
            return item
        return self._call(change)

    def save_profile(self, profile):
        return self._call(lambda c: c.execute('INSERT OR REPLACE INTO scene_profiles VALUES (?,?)',
                          (profile['profile_id'], dumps(profile))).rowcount)

    def get_profile(self, pid):
        row = self._call(lambda c: c.execute('SELECT payload FROM scene_profiles WHERE id=?', (pid,)).fetchone())
        return json.loads(row[0]) if row else None

    def save_device(self, ref, descriptor):
        return self._call(lambda c: c.execute('INSERT OR REPLACE INTO devices VALUES (?,?)', (ref, dumps(descriptor))).rowcount)

    def save_camera_preference(self, descriptor):
        from .camera_selection import camera_preference
        # A reserved device-binding row, not a scene profile or patient record.
        # No schema migration and no stale capture index is persisted.
        return self.save_device('preference:camera:v1', camera_preference(descriptor))

    def get_camera_preference(self):
        from .camera_selection import camera_preference
        row = self._call(lambda c: c.execute('SELECT payload FROM devices WHERE id=?',
                                            ('preference:camera:v1',)).fetchone())
        return camera_preference(json.loads(row[0])) if row else None

    def save_camera_pair_preference(self, devices):
        from .dual_camera import checked_devices
        return self.save_device('preference:camera-pair:v1', checked_devices(devices))

    def get_camera_pair_preference(self):
        from .dual_camera import checked_devices
        row = self._call(lambda c: c.execute('SELECT payload FROM devices WHERE id=?',
                                            ('preference:camera-pair:v1',)).fetchone())
        return checked_devices(json.loads(row[0])) if row else None

    def audit(self, action, payload):
        return self._call(lambda c: c.execute('INSERT INTO audit(at_utc,action,payload) VALUES (?,?,?)',
                                              (utc_now(), action, dumps(payload))).rowcount)
