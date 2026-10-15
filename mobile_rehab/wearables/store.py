"""Independent SQLite namespace, atomic receipts/snapshots and revocation generations."""
from contextlib import contextmanager
from pathlib import Path
import secrets
import sqlite3
import time
from uuid import uuid4
from .contracts import HealthError, canonical, digest, normalize, opaque, UNITS


class Store:
    def __init__(self, path, token_key=''):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.cipher = None
        if token_key:
            try:
                from cryptography.fernet import Fernet
                self.cipher = Fernet(token_key.encode())
            except (ImportError, ValueError):
                raise HealthError('TOKEN_VAULT_UNAVAILABLE', 503) from None
        with self.db() as db:
            version = db.execute('PRAGMA user_version').fetchone()[0]
            if version not in (0, 1):
                raise HealthError('STORAGE_VERSION_UNSUPPORTED', 503)
            if version == 0:
                db.executescript('''
                CREATE TABLE connections(id TEXT PRIMARY KEY, owner TEXT NOT NULL, provider TEXT NOT NULL,
                  identity_hash TEXT NOT NULL, logical_source_id TEXT NOT NULL, generation INTEGER NOT NULL,
                  active INTEGER NOT NULL, scopes TEXT NOT NULL, timezone TEXT NOT NULL, tokens BLOB,
                  revision INTEGER NOT NULL DEFAULT 1, refresh_holder TEXT, refresh_until REAL,
                  remote_revoke TEXT, deleted_copy INTEGER NOT NULL DEFAULT 0,
                  UNIQUE(owner,provider,identity_hash));
                CREATE TABLE attempts(id TEXT PRIMARY KEY, owner TEXT, provider TEXT, state_hash TEXT UNIQUE,
                  expires REAL, status TEXT, requested TEXT, connection_id TEXT, expected_identity TEXT,
                  expected_generation INTEGER, nonce TEXT, created REAL, error TEXT);
                CREATE TABLE jobs(id TEXT PRIMARY KEY, owner TEXT, connection_id TEXT, generation INTEGER,
                  sequence INTEGER UNIQUE, status TEXT, created REAL, report TEXT, error TEXT,
                  worker_holder TEXT, lease_until REAL);
                CREATE TABLE sequences(id INTEGER PRIMARY KEY AUTOINCREMENT);
                CREATE TABLE snapshots(id TEXT PRIMARY KEY, connection_id TEXT, generation INTEGER, kind TEXT,
                  route TEXT, start_ms INTEGER, end_ms INTEGER, sequence INTEGER, scopes TEXT, complete INTEGER);
                CREATE TABLE records(id TEXT PRIMARY KEY, connection_id TEXT, logical_source_id TEXT,
                  route TEXT, kind TEXT, store_id TEXT, source_id TEXT, source_version TEXT,
                  start_ms INTEGER, end_ms INTEGER, day TEXT, payload TEXT, deleted INTEGER,
                  snapshot_id TEXT, event_id TEXT, UNIQUE(connection_id,route,event_id));
                CREATE INDEX records_owner_lookup ON records(connection_id,kind,start_ms,end_ms);
                CREATE INDEX snapshots_lookup ON snapshots(connection_id,kind,route,sequence);
                CREATE TABLE receipts(id TEXT PRIMARY KEY, owner TEXT, connection_id TEXT, payload_hash TEXT,
                  receipt TEXT, created REAL);
                CREATE TABLE leases(id TEXT PRIMARY KEY, owner TEXT, connection_id TEXT, generation INTEGER,
                  installation_id TEXT, token_hash TEXT, active INTEGER);
                CREATE TABLE notifications(id TEXT PRIMARY KEY, connection_id TEXT, generation INTEGER,
                  event_type TEXT, received REAL, status TEXT);
                CREATE TABLE links(id TEXT PRIMARY KEY, owner TEXT, start_ms INTEGER, end_ms INTEGER,
                  session_id TEXT, UNIQUE(owner,session_id));
                PRAGMA user_version=1;
                ''')

    @contextmanager
    def db(self):
        try:
            db = sqlite3.connect(self.path, timeout=10)
        except sqlite3.Error:
            raise HealthError('STORAGE_UNAVAILABLE', 503) from None
        db.row_factory = sqlite3.Row
        try:
            db.execute('PRAGMA foreign_keys=ON')
            db.execute('PRAGMA busy_timeout=10000')
            db.execute('BEGIN IMMEDIATE')
            yield db
            db.commit()
        except sqlite3.Error as exc:
            db.rollback()
            code = 'LOCAL_STORAGE_FULL' if getattr(exc, 'sqlite_errorcode', None) == sqlite3.SQLITE_FULL else 'STORAGE_UNAVAILABLE'
            raise HealthError(code, 507 if code == 'LOCAL_STORAGE_FULL' else 503) from None
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def encrypt(self, data):
        if not self.cipher:
            raise HealthError('TOKEN_VAULT_UNAVAILABLE', 503)
        return self.cipher.encrypt(canonical(data).encode())

    def decrypt(self, data):
        if not self.cipher:
            raise HealthError('TOKEN_VAULT_UNAVAILABLE', 503)
        try:
            import json
            return json.loads(self.cipher.decrypt(data))
        except Exception:
            raise HealthError('TOKEN_VAULT_UNAVAILABLE', 503) from None

    @staticmethod
    def checked(db, owner, cid, generation=None, active=True):
        if generation is not None and (type(generation) is not int or generation < 1):
            raise HealthError('STALE_CONNECTION_GENERATION')
        row = db.execute('SELECT * FROM connections WHERE id=? AND owner=?', (cid, owner)).fetchone()
        if not row:
            raise HealthError('CONNECTION_NOT_FOUND', 404)
        if active and not row['active']:
            raise HealthError('CONNECTION_REVOKED')
        if generation is not None and row['generation'] != generation:
            raise HealthError('STALE_CONNECTION_GENERATION')
        return dict(row)

    def connection(self, owner, cid, generation=None, active=True):
        with self.db() as db:
            return self.checked(db, owner, cid, generation, active)

    def bind(self, db, owner, provider, identity, tokens, scopes, timezone, *, reimport=False):
        identity_hash = digest(provider + '\0' + opaque(identity))
        old = db.execute('SELECT * FROM connections WHERE owner=? AND provider=? AND identity_hash=?',
                         (owner, provider, identity_hash)).fetchone()
        if old and old['deleted_copy'] and not reimport:
            raise HealthError('REIMPORT_CONFIRMATION_REQUIRED')
        cid = old['id'] if old else uuid4().hex
        logical = old['logical_source_id'] if old else uuid4().hex
        generation = old['generation'] + 1 if old else 1
        encrypted = self.encrypt(dict(tokens, identity=identity))
        db.execute('''INSERT INTO connections(id,owner,provider,identity_hash,logical_source_id,generation,
                    active,scopes,timezone,tokens) VALUES(?,?,?,?,?,?,1,?,?,?)
                    ON CONFLICT(id) DO UPDATE SET generation=excluded.generation, active=1,
                    scopes=excluded.scopes, timezone=excluded.timezone,tokens=excluded.tokens,
                    revision=connections.revision+1, refresh_holder=NULL, refresh_until=NULL,
                    remote_revoke=NULL, deleted_copy=0''',
                   (cid, owner, provider, identity_hash, logical, generation, canonical(sorted(scopes)), timezone, encrypted))
        db.execute('UPDATE leases SET active=0 WHERE connection_id=?', (cid,))
        return cid

    def create_attempt(self, owner, provider, requested, expected_cid=None):
        aid, state, nonce = uuid4().hex, secrets.token_hex(32), secrets.token_hex(32)
        with self.db() as db:
            old = self.checked(db, owner, expected_cid, active=False) if expected_cid else None
            if old and old['provider'] != provider:
                raise HealthError('IDENTITY_MISMATCH')
            # A second explicit attempt invalidates an earlier not-yet-consumed attempt for this owner/provider.
            db.execute("UPDATE attempts SET status='superseded' WHERE owner=? AND provider=? AND status='pending'", (owner, provider))
            db.execute('INSERT INTO attempts VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (aid, owner, provider, digest(state), time.time()+600, 'pending', canonical(requested), None,
                 old['identity_hash'] if old else None, old['generation'] if old else None, nonce, time.time(), None))
        return dict(attempt_id=aid, state=state, nonce=nonce)

    def consume_attempt(self, owner, provider, state):
        with self.db() as db:
            row = db.execute('SELECT * FROM attempts WHERE state_hash=?', (digest(opaque(state)),)).fetchone()
            if not row or row['owner'] != owner or row['provider'] != provider or row['status'] != 'pending' or row['expires'] < time.time():
                raise HealthError('AUTH_STATE_INVALID', 400)
            db.execute("UPDATE attempts SET status='exchanging' WHERE id=?", (row['id'],))
            return dict(row)

    def attempt(self, owner, aid):
        with self.db() as db:
            row = db.execute('SELECT id,status,connection_id,error FROM attempts WHERE id=? AND owner=?', (aid, owner)).fetchone()
            if not row:
                raise HealthError('AUTH_ATTEMPT_NOT_FOUND', 404)
            return dict(row)

    def finish_attempt(self, attempt, identity, tokens, scopes, timezone, reimport=False):
        with self.db() as db:
            row = db.execute('SELECT * FROM attempts WHERE id=?', (attempt['id'],)).fetchone()
            if not row or row['status'] != 'exchanging' or row['expires'] < time.time():
                raise HealthError('AUTH_STATE_INVALID', 400)
            if row['expected_identity']:
                old = db.execute('SELECT * FROM connections WHERE owner=? AND provider=? AND identity_hash=?',
                    (row['owner'], row['provider'], row['expected_identity'])).fetchone()
                if digest(row['provider']+'\0'+identity) != row['expected_identity']:
                    raise HealthError('IDENTITY_MISMATCH')
                if old['generation'] != row['expected_generation']:
                    raise HealthError('STALE_CONNECTION_GENERATION')
            # Also prevent another process/new attempt superseding this exchanging callback.
            newer = db.execute('SELECT 1 FROM attempts WHERE owner=? AND provider=? AND created>?',
                               (row['owner'], row['provider'], row['created'])).fetchone()
            if newer:
                raise HealthError('AUTH_STATE_INVALID', 400)
            cid = self.bind(db, row['owner'], row['provider'], identity, tokens, scopes, timezone, reimport=reimport)
            db.execute("UPDATE attempts SET status='connected',connection_id=? WHERE id=?", (cid, row['id']))
        return self.public_connection(self.connection(row['owner'], cid))

    def fail_attempt(self, aid, code):
        with self.db() as db:
            db.execute("UPDATE attempts SET status='failed',error=? WHERE id=? AND status='exchanging'", (code, aid))

    @staticmethod
    def public_connection(row):
        import json
        return dict(connection_id=row['id'], provider=row['provider'], logical_source_id=row['logical_source_id'],
                    generation=row['generation'], active=bool(row['active']), granted_scopes=json.loads(row['scopes']),
                    timezone=row['timezone'], remote_revoke=row['remote_revoke'], rehab_can_continue=True)

    def connections(self, owner):
        with self.db() as db:
            return [self.public_connection(dict(r)) for r in db.execute('SELECT * FROM connections WHERE owner=?', (owner,))]

    def enqueue(self, owner, cid):
        with self.db() as db:
            c = self.checked(db, owner, cid)
            old = db.execute("SELECT id FROM jobs WHERE connection_id=? AND generation=? AND status IN ('queued','running')",
                             (cid, c['generation'])).fetchone()
            if old:
                return old['id'], False
            seq = db.execute('INSERT INTO sequences DEFAULT VALUES').lastrowid
            jid = uuid4().hex
            db.execute('INSERT INTO jobs(id,owner,connection_id,generation,sequence,status,created,report,error) VALUES(?,?,?,?,?,?,?,?,?)',
                       (jid, owner, cid, c['generation'], seq, 'queued', time.time(), '{}', None))
            return jid, True

    def recover_expired_worker(self, owner, cid):
        with self.db() as db:
            c = self.checked(db, owner, cid)
            old = db.execute("SELECT id FROM jobs WHERE connection_id=? AND generation=? AND status='running' AND (lease_until IS NULL OR lease_until<?)",
                             (cid, c['generation'], time.time())).fetchone()
            if old:
                db.execute("UPDATE jobs SET status='queued',worker_holder=NULL,lease_until=NULL,error='WORKER_LEASE_EXPIRED' WHERE id=?", (old['id'],))
                return old['id']
        return None

    def job(self, owner, jid):
        import json
        with self.db() as db:
            row = db.execute('SELECT * FROM jobs WHERE id=? AND owner=?', (jid, owner)).fetchone()
            if not row:
                raise HealthError('SYNC_JOB_NOT_FOUND', 404)
            r = dict(row)
            r['report'] = json.loads(r['report'])
            return r

    def set_job(self, owner, jid, status, report=None, error=None, worker_holder=None):
        with self.db() as db:
            row = db.execute('SELECT * FROM jobs WHERE id=? AND owner=?', (jid, owner)).fetchone()
            if not row:
                raise HealthError('SYNC_JOB_NOT_FOUND', 404)
            self.checked(db, owner, row['connection_id'], row['generation'])
            if worker_holder is not None and row['worker_holder'] != worker_holder:
                raise HealthError('STALE_SYNC_WORKER')
            db.execute('UPDATE jobs SET status=?,report=?,error=? WHERE id=?', (status, canonical(report or {}), error, jid))

    def heartbeat(self, owner, jid, holder):
        with self.db() as db:
            job = db.execute('SELECT * FROM jobs WHERE owner=? AND id=?', (owner,jid)).fetchone()
            if not job or job['status'] != 'running' or job['worker_holder'] != holder:
                raise HealthError('STALE_SYNC_WORKER')
            self.checked(db,owner,job['connection_id'],job['generation'])
            db.execute('UPDATE jobs SET lease_until=? WHERE id=?',(time.time()+180,jid))

    def snapshot(self, owner, cid, generation, kind, route, start, end, sequence, records, scopes, job_id=None, worker_holder=None):
        if type(start) is not int or type(end) is not int or type(sequence) is not int or not 0 <= start < end <= 7258118400000 or sequence<1:
            raise HealthError('PAYLOAD_SCHEMA_UNSUPPORTED',400)
        normalized = [normalize(r) for r in records]
        if (kind not in UNITS or route not in ('cloud', 'health_connect', 'official_local') or len(records)>50000
                or any(r['kind'] != kind or not start <= r['start_ms'] < end for r in normalized)):
            raise HealthError('PAYLOAD_SCHEMA_UNSUPPORTED', 400)
        with self.db() as db:
            c = self.checked(db, owner, cid, generation)
            if canonical(sorted(scopes)) != c['scopes']:
                raise HealthError('SCOPE_CHANGED')
            previous = db.execute('''SELECT MAX(sequence) FROM snapshots WHERE connection_id=? AND kind=?
                                     AND route=? AND start_ms=? AND end_ms=? AND complete=1''',
                                  (cid, kind, route, start, end)).fetchone()[0]
            if previous is not None and sequence <= previous:
                return dict(status='stale', records=0)
            sid = uuid4().hex
            db.execute('INSERT INTO snapshots VALUES(?,?,?,?,?,?,?,?,?,1)',
                       (sid, cid, generation, kind, route, start, end, sequence, c['scopes']))
            for index, r in enumerate(normalized):
                db.execute('INSERT INTO records VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                    (uuid4().hex, cid, c['logical_source_id'], route, kind, r['source_store_id'],
                     r.get('source_record_id'), r['version'], r['start_ms'], r['end_ms'], r['day'],
                     canonical(r), 0, sid, None))
            if job_id is not None:
                import json
                job = db.execute('SELECT * FROM jobs WHERE id=? AND owner=? AND connection_id=? AND generation=?',
                    (job_id,owner,cid,generation)).fetchone()
                if (not job or job['status'] != 'running' or job['sequence'] != sequence
                        or worker_holder is not None and job['worker_holder'] != worker_holder):
                    raise HealthError('STALE_SYNC_JOB')
                report = json.loads(job['report'])
                report.setdefault('_committed_windows', []).append(dict(kind=kind,start_ms=start,end_ms=end,
                    snapshot_id=sid,records=len(normalized)))
                db.execute('UPDATE jobs SET report=? WHERE id=?',(canonical(report),job_id))
            return dict(status='committed', records=len(normalized), snapshot_id=sid)

    def lease(self, owner, cid, installation_id):
        opaque(installation_id)
        lid, token = uuid4().hex, secrets.token_hex(32)
        with self.db() as db:
            c = self.checked(db, owner, cid)
            db.execute('UPDATE leases SET active=0 WHERE connection_id=? AND installation_id=?', (cid, installation_id))
            db.execute('INSERT INTO leases VALUES(?,?,?,?,?,?,1)', (lid, owner, cid, c['generation'], installation_id, digest(token)))
        return dict(lease_id=lid, lease_token=token, generation=c['generation'])

    def stop_lease(self, owner, lid):
        with self.db() as db:
            db.execute('UPDATE leases SET active=0 WHERE id=? AND owner=?', (lid, owner))

    def import_batch(self, owner, cid, generation, batch_id, lease_id, lease_token, events):
        opaque(batch_id)
        if not isinstance(events, list) or not 1 <= len(events) <= 200:
            raise HealthError('PAYLOAD_SCHEMA_UNSUPPORTED', 400)
        request_hash = digest(canonical(dict(cid=cid, generation=generation, events=events, lease_id=lease_id)))
        with self.db() as db:
            c = self.checked(db, owner, cid, generation)
            lease = db.execute('SELECT * FROM leases WHERE id=? AND owner=? AND connection_id=?', (lease_id, owner, cid)).fetchone()
            if (not lease or not lease['active'] or lease['generation'] != generation
                    or not secrets.compare_digest(lease['token_hash'], digest(opaque(lease_token)))):
                raise HealthError('UPLOAD_LEASE_INVALID', 403)
            previous = db.execute('SELECT * FROM receipts WHERE id=?', (batch_id,)).fetchone()
            if previous:
                if previous['owner'] != owner or previous['payload_hash'] != request_hash:
                    raise HealthError('IDEMPOTENCY_CONFLICT')
                import json
                return json.loads(previous['receipt'])
            items = []
            for e in events:
                if not isinstance(e, dict):
                    raise HealthError('PAYLOAD_SCHEMA_UNSUPPORTED', 400)
                event_id = opaque(e.get('event_id'))
                route = e.get('route')
                if route not in ('health_connect', 'official_local'):
                    raise HealthError('INGESTION_ROUTE_INVALID', 400)
                r = normalize(e.get('record'))
                if not r.get('source_record_id'):
                    raise HealthError('STABLE_SOURCE_ID_REQUIRED', 400)
                # Per-metric permissions remain enforced for imported vendor data.
                from .contracts import SCOPES
                import json
                permission_kind = {'steps_delta':'steps_daily','heart_rate_summary':'heart_rate_sample'}.get(r['kind'],r['kind'])
                scope = SCOPES[c['provider']].get(permission_kind)
                if scope is None or scope not in json.loads(c['scopes']):
                    raise HealthError('SCOPE_MISSING', 403)
                deleted = e.get('deleted', False)
                if type(deleted) is not bool:
                    raise HealthError('PAYLOAD_SCHEMA_UNSUPPORTED', 400)
                old_event = db.execute('SELECT payload,deleted FROM records WHERE connection_id=? AND route=? AND event_id=?',
                                       (cid, route, event_id)).fetchone()
                if old_event:
                    if old_event['payload'] != canonical(r) or old_event['deleted'] != deleted:
                        raise HealthError('IDEMPOTENCY_CONFLICT')
                    status = 'duplicate'
                else:
                    old = db.execute('''SELECT source_version,deleted,payload FROM records WHERE connection_id=? AND route=?
                         AND kind=? AND store_id=? AND source_id=? AND snapshot_id IS NULL''',
                         (cid, route, r['kind'], r['source_store_id'], r['source_record_id'])).fetchall()
                    latest = max(old, key=lambda x: (int(x['source_version']), x['deleted'])) if old else None
                    if latest and (int(latest['source_version']) > int(r['version']) or
                                   int(latest['source_version']) == int(r['version']) and latest['deleted'] and not deleted):
                        status = 'stale'
                    elif latest and int(latest['source_version']) == int(r['version']) and latest['payload'] != canonical(r):
                        raise HealthError('SOURCE_VERSION_CONFLICT')
                    else:
                        status = 'accepted'
                        db.execute('INSERT INTO records VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                          (uuid4().hex, cid, c['logical_source_id'], route, r['kind'], r['source_store_id'],
                           r['source_record_id'], r['version'], r['start_ms'], r['end_ms'], r['day'], canonical(r),
                           int(deleted), None, event_id))
                items.append(dict(event_id=event_id, status=status))
            receipt = dict(batch_id=batch_id, status='committed', items=items)
            db.execute('INSERT INTO receipts VALUES(?,?,?,?,?,?)', (batch_id, owner, cid, request_hash, canonical(receipt), time.time()))
        return receipt

    def receipt(self, owner, bid):
        import json
        with self.db() as db:
            row = db.execute('SELECT * FROM receipts WHERE owner=? AND id=?', (owner, bid)).fetchone()
            if not row:
                raise HealthError('IMPORT_BATCH_NOT_FOUND', 404)
            return json.loads(row['receipt'])

    def records(self, owner, start=0, end=7258118400000, kind=None):
        import json
        with self.db() as db:
            # Historical imported copies remain readable after disconnect. New writes cannot.
            rows = db.execute('''SELECT r.*,c.provider,c.active,c.scopes FROM records r JOIN connections c
                ON c.id=r.connection_id WHERE c.owner=? AND c.deleted_copy=0 AND r.start_ms<? AND r.end_ms>=?
                AND (? IS NULL OR r.kind=?) ORDER BY r.start_ms''', (owner, end, start, kind, kind)).fetchall()
            snapshots = db.execute('''SELECT s.* FROM snapshots s JOIN connections c ON c.id=s.connection_id
                WHERE c.owner=? AND complete=1''', (owner,)).fetchall()
        visible = []
        stable = {}
        for r in rows:
            if r['snapshot_id']:
                covering = [s for s in snapshots if s['connection_id'] == r['connection_id'] and s['kind'] == r['kind']
                            and s['route'] == r['route'] and s['start_ms'] <= r['start_ms'] < s['end_ms']]
                if covering and max(covering, key=lambda s:s['sequence'])['id'] != r['snapshot_id']:
                    continue
                visible.append(r)
            else:
                key = (r['connection_id'], r['route'], r['kind'], r['store_id'], r['source_id'])
                old = stable.get(key)
                if old is None or (int(r['source_version']), r['deleted']) > (int(old['source_version']), old['deleted']):
                    stable[key] = r
        visible += [r for r in stable.values() if not r['deleted']]
        result = []
        for r in visible:
            result.append(dict(json.loads(r['payload']), record_id=r['id'], connection_id=r['connection_id'],
                logical_source_id=r['logical_source_id'], provider=r['provider'], ingestion_route=r['route'],
                connection_active=bool(r['active'])))
        return result

    def summary(self, owner, start, end):
        rows = self.records(owner, start, end)
        groups = {}
        for r in rows:
            groups.setdefault((r['kind'], r['day']), []).append(r)
        result = []
        for (kind, day), records in sorted(groups.items()):
            # Conservative one primary per owner/metric/day, even if IDs differ across routes.
            rank = {'cloud': 0, 'official_local': 1, 'health_connect': 2}
            primary = min(records, key=lambda r:(rank[r['ingestion_route']], r['connection_id']))
            chosen = [r for r in records if (r['connection_id'], r['ingestion_route']) ==
                       (primary['connection_id'], primary['ingestion_route'])]
            # An endpoint's daily total is authoritative, not a summable delta.
            values = [r['value'] for r in chosen if r.get('value') is not None]
            value = (max(chosen, key=lambda r:(int(r['version']),r['start_ms'])).get('value') if kind == 'steps_daily'
                     else sum(values) if kind in ('steps_delta', 'sleep_session', 'exercise_session') and values
                     else None)
            overlap = False
            if kind in ('sleep_session','exercise_session'):
                ordered = sorted(chosen,key=lambda r:r['start_ms'])
                overlap = any(a['end_ms']>b['start_ms'] for a,b in zip(ordered,ordered[1:]))
                if overlap:
                    value=None
            result.append(dict(kind=kind, day=day, value=value, unit=UNITS[kind],
                record_count=len(chosen), records=[r['record_id'] for r in chosen],
                primary_connection_id=primary['connection_id'], primary_route=primary['ingestion_route'],
                alternative_records=len(records)-len(chosen), policy_version='one-source-per-metric-day-1',
                availability='OVERLAPPING_SOURCE_INTERVALS' if overlap else 'OK' if value is not None else 'VALUE_UNKNOWN_OR_DETAIL_ONLY',
                last_measurement_ms=max(r['end_ms'] for r in chosen)))
        daily_days = {r['day'] for r in result if r['kind']=='steps_daily'}
        # Never present daily totals plus deltas as two additive totals for the same day.
        result = [r for r in result if r['kind']!='steps_delta' or r['day'] not in daily_days]
        return dict(days=result, rehab_can_continue=True)

    def revoke(self, owner, cid, delete_copy=False):
        with self.db() as db:
            c = self.checked(db, owner, cid, active=False)
            if c['active']:
                db.execute("UPDATE connections SET active=0,generation=generation+1,remote_revoke='pending',revision=revision+1 WHERE id=?", (cid,))
            db.execute('UPDATE leases SET active=0 WHERE connection_id=?', (cid,))
            db.execute("UPDATE jobs SET status='cancelled',error='CONNECTION_REVOKED' WHERE connection_id=? AND status IN ('queued','running')", (cid,))
            if delete_copy:
                db.execute('DELETE FROM records WHERE connection_id=?', (cid,))
                db.execute('DELETE FROM snapshots WHERE connection_id=?', (cid,))
                db.execute('UPDATE connections SET deleted_copy=1 WHERE id=?', (cid,))
        return self.public_connection(self.connection(owner, cid, active=False))

    def remote_revoked(self, owner, cid, generation, success):
        with self.db() as db:
            self.checked(db, owner, cid, generation, active=False)
            # Do not overwrite tokens/status of a concurrently reconnected identity.
            db.execute('UPDATE connections SET remote_revoke=?,tokens=NULL WHERE id=? AND active=0',
                       ('confirmed' if success else 'unconfirmed', cid))

    def notification(self, provider, identity, event_type, event_id):
        with self.db() as db:
            rows = db.execute('SELECT * FROM connections WHERE provider=? AND identity_hash=?',
                              (provider, digest(provider+'\0'+identity))).fetchall()
            queued = []
            for c in rows:
                nid = digest(c['id']+'\0'+event_id)
                old = db.execute('SELECT 1 FROM notifications WHERE id=?', (nid,)).fetchone()
                if old:
                    continue
                db.execute('INSERT INTO notifications VALUES(?,?,?,?,?,?)',
                    (nid, c['id'], c['generation'], event_type, time.time(), 'pending' if c['active'] else 'ignored_revoked'))
                if c['active']:
                    queued.append((c['owner'], c['id']))
            return queued
