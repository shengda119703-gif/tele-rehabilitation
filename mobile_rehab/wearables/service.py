"""Finite sync jobs and secure authorization, independent of all rehab control paths."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json
import os
import secrets
import time
from .config import load_config
from .contracts import HealthError, SCOPES, canonical, digest, opaque, zone
from .providers import Provider, Transport, verify_xiaomi_notification
from .store import Store


class WearableService:
    def __init__(self, root, configs=None, token_key=None, transport=None):
        self.configs = configs if configs is not None else load_config()
        self.store = Store(root / 'wearables.sqlite3', token_key if token_key is not None else os.environ.get('ANKANG_HEALTH_TOKEN_KEY', ''))
        self.transport = transport or Transport()
        self.pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix='wearable-sync')
        self.closed = False
        self.worker_id = secrets.token_hex(16)
        # An interrupted complete-window read is retried from its start; staged partial pages were never visible.
        with self.store.db() as db:
            db.execute("UPDATE jobs SET status='queued',error='WORKER_LEASE_EXPIRED' WHERE status='running' AND (lease_until IS NULL OR lease_until<?)",(time.time(),))
            pending = db.execute("SELECT owner,id,connection_id FROM jobs WHERE status='queued'").fetchall()
        for job in pending:
            try:
                c = self.store.connection(job['owner'], job['connection_id'])
                self.provider(c['provider'])
                self.pool.submit(self.run, job['owner'], job['id'])
            except HealthError:
                pass  # Pending evidence remains inspectable; no unconfigured network calls.

    def close(self):
        self.closed = True
        self.pool.shutdown(wait=True, cancel_futures=True)
        self.transport.close()

    def provider(self, name):
        config = self.configs.get(name)
        if config is None:
            raise HealthError('PROVIDER_UNAVAILABLE', 404)
        reason = config.reason()
        if reason:
            raise HealthError(reason, 503)
        if not self.store.cipher:
            raise HealthError('TOKEN_VAULT_UNAVAILABLE', 503)
        return Provider(config, self.transport)

    def capabilities(self):
        providers = []
        for name, config in self.configs.items():
            reason = config.reason() or (None if self.store.cipher else 'TOKEN_VAULT_UNAVAILABLE')
            providers.append(dict(provider=name, configured=reason is None, status=reason or 'USER_AUTH_REQUIRED',
                metrics=[dict(kind=k, contract_available=True, approval_granted=s in config.approved_scopes)
                         for k,s in SCOPES[name].items()],
                unavailable_metrics=[] if name == 'xiaomi' else ['heart_rate_sample', 'sleep_session', 'exercise_session'],
                cloud_live_sampling=False, subscription_available=config.subscription_enabled and name == 'xiaomi'))
        return dict(version='wearable-history-1', providers=providers, rehab_can_continue=True,
                    native_readers_connected=False, team_proxy_binding=False, apple_existing_route_unchanged=True)

    def start(self, owner, name, metrics=None, connection_id=None, reimport=False):
        p = self.provider(name)
        metrics = metrics if metrics is not None else list(SCOPES[name])[:4]
        if (not isinstance(metrics, list) or not metrics or len(metrics)>8 or
                any(not isinstance(k,str) or k not in SCOPES[name] for k in metrics) or type(reimport) is not bool):
            raise HealthError('PAYLOAD_SCHEMA_UNSUPPORTED', 400)
        requested = sorted({SCOPES[name][k] for k in metrics if SCOPES[name][k] in p.config.approved_scopes})
        if not requested:
            raise HealthError('APPROVAL_PENDING')
        attempt = self.store.create_attempt(owner, name, {'scopes': requested, 'reimport': reimport}, connection_id)
        return dict(attempt_id=attempt['attempt_id'],
                    authorization_url=p.authorize_url(requested, attempt['state'], attempt['nonce']),
                    expires_in=600, status='pending', rehab_can_continue=True)

    def callback(self, owner, name, state, code=None, denied=False):
        p = self.provider(name)
        attempt = self.store.consume_attempt(owner, name, state)
        try:
            if denied:
                raise HealthError('USER_AUTH_DENIED')
            opaque(code)
            identity, tokens, granted = p.token(code=code, auth_nonce=attempt['nonce'])
            return self.store.finish_attempt(attempt, identity, tokens, granted, p.config.timezone,
                                             reimport=json.loads(attempt['requested'])['reimport'])
        except HealthError as exc:
            self.store.fail_attempt(attempt['id'], exc.code)
            raise

    def access_token(self, owner, cid, generation):
        holder, deadline = secrets.token_hex(12), time.monotonic()+35
        while time.monotonic()<deadline:
            with self.store.db() as db:
                c = self.store.checked(db, owner, cid, generation)
                token = self.store.decrypt(c['tokens'])
                if token['expires_at'] > time.time()+60:
                    return token['access_token']
                if not token.get('refresh_token'):
                    raise HealthError('USER_AUTH_REQUIRED', 403)
                if c['refresh_holder'] and (c['refresh_until'] or 0)>time.time():
                    waiting = True
                else:
                    waiting = False
                    db.execute('UPDATE connections SET refresh_holder=?,refresh_until=? WHERE id=?',
                               (holder, time.time()+120, cid))
            if waiting:
                time.sleep(.05)
                continue
            try:
                p = self.provider(c['provider'])
                identity, new_token, granted = p.token(refresh=token['refresh_token'])
                if identity and digest(c['provider']+'\0'+identity) != c['identity_hash']:
                    raise HealthError('IDENTITY_MISMATCH')
                with self.store.db() as db:
                    current = self.store.checked(db, owner, cid, generation)
                    if current['revision'] != c['revision'] or current['refresh_holder'] != holder:
                        raise HealthError('STALE_CONNECTION_GENERATION')
                    encrypted = self.store.encrypt(dict(new_token, identity=token['identity']))
                    db.execute('''UPDATE connections SET tokens=?,scopes=?,revision=revision+1,
                                  refresh_holder=NULL,refresh_until=NULL WHERE id=?''',
                               (encrypted, canonical(sorted(granted)), cid))
                return new_token['access_token']
            finally:
                with self.store.db() as db:
                    db.execute('UPDATE connections SET refresh_holder=NULL,refresh_until=NULL WHERE id=? AND refresh_holder=?', (cid, holder))
        raise HealthError('TOKEN_REFRESH_BUSY', 503)

    def sync(self, owner, cid):
        c = self.store.connection(owner, cid)
        self.provider(c['provider'])
        if self.closed:
            raise HealthError('SERVICE_CLOSED', 503)
        recovered = self.store.recover_expired_worker(owner, cid)
        jid, created = self.store.enqueue(owner, cid)
        if created or recovered == jid:
            self.pool.submit(self.run, owner, jid)
        return dict(job_id=jid, status=self.store.job(owner, jid)['status'], coalesced=not created,
                    rehab_can_continue=True)

    def run(self, owner, jid):
        report = {}
        try:
            job = self.store.job(owner, jid)
            if job['status'] not in ('queued', 'running'):
                return
            # Cross-process claim; a repeated explicit sync reuses this job, not a second worker.
            with self.store.db() as db:
                changed = db.execute("UPDATE jobs SET status='running',worker_holder=?,lease_until=? WHERE id=? AND status='queued'",
                                     (self.worker_id,time.time()+180,jid)).rowcount
            if not changed:
                return
            c = self.store.connection(owner, job['connection_id'], job['generation'])
            report = job['report']
            p = self.provider(c['provider'])
            tz = zone(c['timezone'])
            today = datetime.now(tz).date()
            for kind, scope in SCOPES[c['provider']].items():
                if self.closed:
                    raise HealthError('SERVICE_CLOSED')
                latest = self.store.connection(owner, c['id'], c['generation'])
                # Read current permission after refresh as well as before and at snapshot commit.
                token = self.access_token(owner, c['id'], c['generation'])
                latest = self.store.connection(owner, c['id'], c['generation'])
                granted = json.loads(latest['scopes'])
                if scope not in granted or scope not in p.config.approved_scopes:
                    report[kind] = dict(status='SCOPE_MISSING')
                    continue
                current = sorted(p.permissions(token,granted))
                if current != granted:
                    with self.store.db() as db:
                        self.store.checked(db,owner,c['id'],c['generation'])
                        db.execute('UPDATE connections SET scopes=?,revision=revision+1 WHERE id=?',(canonical(current),c['id']))
                    granted=current
                if scope not in granted or scope not in p.config.approved_scopes:
                    report[kind] = dict(status='SCOPE_MISSING')
                    continue
                # Seven source-local days initially; then reconcile the latest three local days.
                with self.store.db() as db:
                    prior = db.execute("SELECT report FROM jobs WHERE connection_id=? AND id<>? AND status IN ('completed','partial')", (c['id'],jid)).fetchall()
                existed = any(json.loads(r['report']).get(kind,{}).get('status') in ('OK','NO_RECORDS') for r in prior)
                frozen = report.setdefault('_windows', {})
                if kind not in frozen:
                    frozen[kind] = [str(today), 3 if existed else 7]
                    self.store.set_job(owner,jid,'running',report,worker_holder=self.worker_id)
                anchor = datetime.strptime(frozen[kind][0], '%Y-%m-%d').date()
                lookback = frozen[kind][1]
                count = sum(w['records'] for w in report.get('_committed_windows',[]) if w['kind']==kind)
                pages = 0
                try:
                    for offset in range(lookback-1, -1, -1):
                        day = anchor-timedelta(days=offset)
                        start = int(datetime.combine(day, datetime.min.time(), tz).timestamp()*1000)
                        end = int(datetime.combine(day+timedelta(days=1), datetime.min.time(), tz).timestamp()*1000)
                        staged = []
                        self.store.heartbeat(owner,jid,self.worker_id)
                        for records, cursor in p.pages(kind, start, end, token):
                            self.store.heartbeat(owner,jid,self.worker_id)
                            pages += 1
                            staged.extend(records)
                            if len(staged)>50000:
                                raise HealthError('RECORD_LIMIT_EXCEEDED', 502)
                        if p.permissions(token,granted) != set(granted):
                            raise HealthError('SCOPE_CHANGED')
                        # Empty vendor response alone cannot prove deletion or App cloud-upload state.
                        if not staged:
                            continue
                        receipt = self.store.snapshot(owner, c['id'], c['generation'], kind, 'cloud',
                            start, end, job['sequence'], staged, granted, job_id=jid,worker_holder=self.worker_id)
                        report['_committed_windows'] = self.store.job(owner,jid)['report'].get('_committed_windows',[])
                        count += receipt['records']
                    report[kind] = dict(status='OK' if count else 'NO_RECORDS', records=count, pages=pages,
                        last_successful_sync_ms=int(time.time()*1000), lookback_days=lookback,
                        coverage='read_completed_nonempty_windows' if count else 'empty_response_upload_state_unknown', parser=p.name)
                except HealthError as exc:
                    report[kind] = dict(status=exc.code, records_committed=count, pages=pages, coverage='partial_or_unknown')
                self.store.set_job(owner, jid, 'running', report,worker_holder=self.worker_id)
            status = 'completed' if all(r['status'] in ('OK', 'NO_RECORDS', 'SCOPE_MISSING') for k,r in report.items() if not k.startswith('_')) else 'partial'
            self.store.set_job(owner, jid, status, report,worker_holder=self.worker_id)
        except HealthError as exc:
            try:
                self.store.set_job(owner, jid, 'failed', report, exc.code,worker_holder=self.worker_id)
            except HealthError:
                pass  # Revocation already durably cancelled the job; disk failure must not fabricate ACK.
        except Exception:
            try:
                self.store.set_job(owner, jid, 'failed', report, 'INTERNAL_SYNC_ERROR',worker_holder=self.worker_id)
            except HealthError:
                pass

    def revoke(self, owner, cid, delete_copy=False):
        old = self.store.connection(owner, cid, active=False)
        result = self.store.revoke(owner, cid, delete_copy)
        # New data stops immediately; remote revocation is a separate bounded attempt.
        success = False
        try:
            if old['tokens']:
                p = self.provider(old['provider'])
                success = p.revoke(self.store.decrypt(old['tokens'])['access_token'])
        except HealthError:
            pass
        self.store.remote_revoked(owner, cid, result['generation'], success)
        return self.store.public_connection(self.store.connection(owner, cid, active=False))

    def notify_xiaomi(self, event, signature):
        p = self.provider('xiaomi')
        if not p.config.subscription_enabled:
            raise HealthError('SUBSCRIPTION_NOT_CONFIGURED', 503)
        event_id = verify_xiaomi_notification(p.config.client_secret, event, signature)
        queued = self.store.notification('xiaomi', event['openId'], str(event['eventType']), event_id)
        # metaData is deliberately ignored. Only bounded original windows are re-read.
        for owner, cid in queued:
            self.sync(owner, cid)
        return dict(accepted=True)

    def training_context(self, owner, start, end):
        records = self.store.records(owner, start, end)
        samples = [r for r in records if r['kind'] == 'heart_rate_sample' and start <= r['start_ms'] < end]
        if samples:
            first = min(samples, key=lambda r:({'cloud':0,'official_local':1,'health_connect':2}[r['ingestion_route']], r['connection_id']))
            samples = [r for r in samples if (r['connection_id'], r['ingestion_route']) == (first['connection_id'], first['ingestion_route'])]
        return dict(start_ms=start, end_ms=end, heart_rate_samples=samples, interpolation=False,
            reference_version='wearable-training-background-1', training_completion_affected=False,
            plan_dose_affected=False, rehab_can_continue=True)
