"""Portable local-ingestion reference implementation; NOT an Android SDK reader.

Page cache + upload events + source cursor commit together. A server receipt is a
different commit. User/installation/connection-generation changes cannot reuse it.
"""
from pathlib import Path
import json
import sqlite3
from uuid import uuid4
from .contracts import HealthError, canonical, digest, normalize, opaque


class LocalOutbox:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.db() as db:
            version = db.execute('PRAGMA user_version').fetchone()[0]
            if version not in (0, 1):
                raise HealthError('STORAGE_VERSION_UNSUPPORTED', 503)
            if not version:
                db.executescript('''
                CREATE TABLE bindings(scope TEXT PRIMARY KEY, owner TEXT, connection_id TEXT, generation INTEGER,
                    installation_id TEXT, active INTEGER);
                CREATE TABLE cursors(scope TEXT, kind TEXT, token TEXT, phase TEXT, page_cursor TEXT,
                    PRIMARY KEY(scope,kind));
                CREATE TABLE cache(scope TEXT, kind TEXT, store_id TEXT, source_id TEXT, version TEXT,
                    deleted INTEGER, record TEXT, PRIMARY KEY(scope,kind,store_id,source_id));
                CREATE TABLE outbox(scope TEXT, event_id TEXT, event TEXT, batch_id TEXT,
                    status TEXT, PRIMARY KEY(scope,event_id));
                CREATE TABLE batches(id TEXT PRIMARY KEY, scope TEXT, payload TEXT, receipt TEXT);
                PRAGMA user_version=1;
                ''')

    def db(self):
        # Delegate connection/transaction/error handling, without creating the server schema.
        from .store import Store
        instance = object.__new__(Store)
        instance.path = self.path
        return instance.db()

    def bind(self, owner, cid, generation, installation_id):
        if type(generation) is not int or generation<1:
            raise HealthError('STALE_CONNECTION_GENERATION')
        scope = digest(canonical([opaque(owner), opaque(cid), generation, opaque(installation_id)]))
        with self.db() as db:
            # This single local cache belongs to one current authenticated installation scope.
            db.execute('UPDATE bindings SET active=0')
            db.execute('INSERT INTO bindings VALUES(?,?,?,?,?,1) ON CONFLICT(scope) DO UPDATE SET active=1',
                       (scope, owner, cid, generation, installation_id))
        return scope

    @staticmethod
    def checked(db, scope):
        row = db.execute('SELECT * FROM bindings WHERE scope=? AND active=1', (scope,)).fetchone()
        if not row:
            raise HealthError('LOCAL_BINDING_INACTIVE', 403)
        return dict(row)

    def stop(self, scope):
        with self.db() as db:
            db.execute('UPDATE bindings SET active=0 WHERE scope=?', (scope,))

    def bootstrap_token(self, scope, kind, changes_token):
        opaque(changes_token)
        with self.db() as db:
            self.checked(db, scope)
            # Caller must obtain the official changes token BEFORE reading the initial snapshot.
            # Preserve past cache/outbox on expiry or restricted re-snapshot.
            db.execute("""INSERT INTO cursors VALUES(?,?,?,'snapshot',NULL) ON CONFLICT(scope,kind)
                DO UPDATE SET token=excluded.token,phase='snapshot',page_cursor=NULL""",
                       (scope, kind, changes_token))

    def commit_page(self, scope, kind, events, *, expected_cursor, next_cursor, snapshot=False, complete=False):
        if not isinstance(events,list) or len(events)>200:
            raise HealthError('PAYLOAD_SCHEMA_UNSUPPORTED', 400)
        with self.db() as db:
            self.checked(db, scope)
            cursor = db.execute('SELECT * FROM cursors WHERE scope=? AND kind=?', (scope,kind)).fetchone()
            if not cursor or (cursor['phase'] == 'snapshot') != snapshot:
                raise HealthError('LOCAL_CURSOR_PHASE_INVALID')
            actual = cursor['page_cursor'] if snapshot else cursor['token']
            if actual != expected_cursor:
                raise HealthError('LOCAL_CURSOR_CONFLICT')
            if not complete and (not next_cursor or next_cursor == actual):
                raise HealthError('CURSOR_INVALID')
            for e in events:
                r = normalize(e.get('record'))
                source_id = opaque(r.get('source_record_id'))
                if r['kind'] != kind or e.get('route') not in ('health_connect','official_local') or type(e.get('deleted',False)) is not bool:
                    raise HealthError('PAYLOAD_SCHEMA_UNSUPPORTED', 400)
                deleted = e.get('deleted',False)
                old = db.execute('SELECT * FROM cache WHERE scope=? AND kind=? AND store_id=? AND source_id=?',
                                 (scope,kind,r['source_store_id'],source_id)).fetchone()
                if old and (int(old['version']) > int(r['version']) or int(old['version']) == int(r['version']) and old['deleted'] and not deleted):
                    continue
                if old and int(old['version']) == int(r['version']) and old['record'] != canonical(r):
                    raise HealthError('SOURCE_VERSION_CONFLICT')
                event_id = digest(canonical([scope, kind, r['source_store_id'],source_id,r['version'],deleted]))
                event = dict(event_id=event_id,route=e['route'],record=r,deleted=deleted)
                previous = db.execute('SELECT event FROM outbox WHERE scope=? AND event_id=?',(scope,event_id)).fetchone()
                if previous and previous['event'] != canonical(event):
                    raise HealthError('IDEMPOTENCY_CONFLICT')
                db.execute('INSERT INTO outbox VALUES(?,?,?,NULL,\'pending\') ON CONFLICT(scope,event_id) DO NOTHING',
                           (scope,event_id,canonical(event)))
                db.execute('''INSERT INTO cache VALUES(?,?,?,?,?,?,?) ON CONFLICT(scope,kind,store_id,source_id)
                    DO UPDATE SET version=excluded.version,deleted=excluded.deleted,record=excluded.record''',
                    (scope,kind,r['source_store_id'],source_id,r['version'],int(deleted),canonical(r)))
            if snapshot:
                db.execute('UPDATE cursors SET phase=?,page_cursor=? WHERE scope=? AND kind=?',
                           ('changes' if complete else 'snapshot', next_cursor, scope,kind))
            else:
                opaque(next_cursor)
                db.execute('UPDATE cursors SET token=? WHERE scope=? AND kind=?',(next_cursor,scope,kind))

    def next_batch(self, scope):
        with self.db() as db:
            binding = self.checked(db, scope)
            old = db.execute('SELECT payload FROM batches WHERE scope=? AND receipt IS NULL ORDER BY rowid LIMIT 1', (scope,)).fetchone()
            if old:
                return json.loads(old['payload'])
            rows = db.execute("SELECT * FROM outbox WHERE scope=? AND status='pending' AND batch_id IS NULL ORDER BY rowid LIMIT 200",(scope,)).fetchall()
            if not rows:
                return None
            bid = uuid4().hex
            payload = dict(batch_id=bid, connection_id=binding['connection_id'], generation=binding['generation'],
                           events=[json.loads(r['event']) for r in rows])
            db.execute('INSERT INTO batches VALUES(?,?,?,NULL)',(bid,scope,canonical(payload)))
            db.executemany('UPDATE outbox SET batch_id=? WHERE scope=? AND event_id=?',[(bid,scope,r['event_id']) for r in rows])
            return payload

    def acknowledge(self, scope, receipt):
        with self.db() as db:
            self.checked(db, scope)
            batch = db.execute('SELECT * FROM batches WHERE id=? AND scope=?',(receipt.get('batch_id'),scope)).fetchone()
            if not batch or receipt.get('status') != 'committed' or not isinstance(receipt.get('items'),list):
                raise HealthError('SERVER_RECEIPT_INVALID')
            expected = {e['event_id'] for e in json.loads(batch['payload'])['events']}
            received = [i.get('event_id') for i in receipt['items']]
            if (len(received) != len(set(received)) or set(received) != expected or
                    any(i.get('status') not in ('accepted','duplicate','stale') for i in receipt['items'])):
                raise HealthError('SERVER_RECEIPT_INVALID')
            if batch['receipt'] and batch['receipt'] != canonical(receipt):
                raise HealthError('SERVER_RECEIPT_INVALID')
            db.execute('UPDATE outbox SET status=\'acknowledged\' WHERE scope=? AND batch_id=?',(scope,batch['id']))
            db.execute('UPDATE batches SET receipt=? WHERE id=?',(canonical(receipt),batch['id']))

    def inspect(self, scope):
        with self.db() as db:
            b = self.checked(db, scope)
            return dict(connection_id=b['connection_id'],generation=b['generation'],
                pending=db.execute("SELECT COUNT(*) FROM outbox WHERE scope=? AND status='pending'",(scope,)).fetchone()[0],
                cursors=[dict(r) for r in db.execute('SELECT kind,phase,page_cursor FROM cursors WHERE scope=?',(scope,))])
