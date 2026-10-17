import json
import os
import sqlite3
from uuid import uuid4
import pytest
import threading
from concurrent.futures import ThreadPoolExecutor

from app.cloud_account import CloudAccount, CloudError, TokenVault, desktop_record, ORIGIN


class MemoryVault:
    def __init__(self): self.value = None
    def read(self): return json.loads(json.dumps(self.value)) if self.value else None
    def write(self, value): self.value = json.loads(json.dumps(value))
    def clear(self): self.value = None


class Server:
    def __init__(self):
        self.users = {name: str(uuid4()) for name in ('one', 'two')}
        self.actor = None
        self.token = 'first'
        self.records = []
        self.drop_reply = False
        self.refreshes = 0
    def __call__(self, path, method='GET', body=None, token=None):
        if path == '/auth/password/login':
            self.actor = body['username']
            return dict(account_id=str(uuid4()), patient_id=self.users[self.actor], username=self.actor,
                        role='PATIENT', access_token=self.token, refresh_token='refresh')
        if path == '/auth/refresh':
            self.refreshes += 1
            self.token = 'rotated'
            return dict(access_token=self.token, refresh_token='rotated-refresh')
        if token != self.token:
            raise CloudError('请重新登录', 401, 'AUTH_REQUIRED')
        if path == '/auth/me':
            return dict(patient_id=self.users[self.actor], role='PATIENT')
        if path.endswith('/record-events'):
            prior = next((r for r in self.records if r['operation'] == body['operation_id']), None)
            if not prior:
                prior = dict(id=str(uuid4()), payload=body['payload'], operation=body['operation_id'],
                             patient_id=self.users[self.actor], source_kind=body['source_kind'])
                self.records.append(prior)
            if self.drop_reply:
                self.drop_reply = False
                raise CloudError('回复丢失')
            return dict(status='COMMITTED', resource_id=prior['id'], idempotent=bool(prior))
        if '/records' in path:
            return dict(items=[r for r in self.records if r['patient_id'] == self.users[self.actor]])
        return dict(status='COMMITTED')


def setup(tmp_path):
    api, vault = Server(), MemoryVault()
    client = CloudAccount(tmp_path, api, vault)
    client.login('one', '1')
    client.bind('local-one')
    return client, api, vault


def test_ai_retry_preserves_understanding_purpose_and_operation(tmp_path):
    account, _, _ = setup(tmp_path)
    sent = []
    def question(text, operation, purpose='reply'):
        sent.append((text, operation, purpose))
        if len(sent) == 1:
            raise CloudError('TEST response lost')
        return {'state': 'SUCCEEDED', 'answer': '{"version":1}'}
    account.ai_question = question
    with pytest.raises(CloudError):
        account.ask_ai('TEST schema', purpose='understanding')
    with pytest.raises(CloudError, match='不能改变问答任务'):
        account.ask_ai('TEST schema', purpose='reply')
    assert len(sent) == 1
    assert account.ask_ai()['state'] == 'SUCCEEDED'
    assert sent[0] == sent[1] and sent[1][2] == 'understanding'
    with account.db() as db:
        assert db.execute('SELECT * FROM ai_pending').fetchone() is None
        assert db.execute("SELECT * FROM meta WHERE key LIKE 'ai-purpose:%'").fetchone() is None


def test_two_resolved_directory_instances_serialize_expired_token_rotation(tmp_path):
    """Fictitious tokens in a shared memory vault; no real credential or server."""
    account, server, vault = setup(tmp_path)
    other = CloudAccount(tmp_path / '.', server, vault)
    assert other.lock is account.lock
    old_request, release, second_started = threading.Event(), threading.Event(), threading.Event()
    old_calls = []
    original = server.__call__
    server.token = 'TEST-expired-server-access'
    def delayed(path, method='GET', body=None, token=None):
        if path == '/auth/me' and token == 'first':
            old_calls.append(token)
            old_request.set()
            assert release.wait(3)
        return original(path, method, body, token)
    account.request = other.request = delayed
    def read_other():
        second_started.set()
        return other.me()
    with ThreadPoolExecutor(max_workers=3) as pool:
        first = pool.submit(account.me)
        assert old_request.wait(3)
        second = pool.submit(read_other)
        assert second_started.wait(3)
        # UI session/consent reads must not wait for the network rotation lock.
        assert pool.submit(other.session).result(timeout=1)['patient_id'] == vault.value['patient_id']
        assert pool.submit(other.consent, 'local-one').result(timeout=1) is False
        release.set()
        assert first.result(timeout=3)['patient_id'] == second.result(timeout=3)['patient_id']
    assert old_calls == ['first'] and server.refreshes == 1
    assert account.session()['access_token'] == other.session()['access_token'] == 'rotated'


def test_two_token_vaults_share_atomic_encrypted_write_lock(tmp_path, monkeypatch):
    if os.name != 'nt':
        pytest.skip('DPAPI storage is a Windows native path')
    first = TokenVault(tmp_path / 'TEST-vault.dpapi')
    second = TokenVault(tmp_path / '.' / 'TEST-vault.dpapi')
    assert first.lock is second.lock
    patient = str(uuid4())
    # Exercise atomic file replacement with inert TEST bytes, never a real token.
    monkeypatch.setattr(TokenVault, '_crypt', staticmethod(lambda raw, encrypt: raw))
    values = [dict(origin=ORIGIN, role='PATIENT', patient_id=patient, marker='TEST-'+str(i)) for i in range(8)]
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda pair: pair[0].write(pair[1]), [(first if i%2 else second, value) for i,value in enumerate(values)]))
    assert first.read()['marker'] in {v['marker'] for v in values}
    assert not list(tmp_path.glob('*.tmp'))


def test_lost_ack_reopen_recovers_same_fact(tmp_path):
    client, api, vault = setup(tmp_path)
    payload = {'summary': {'max': None, 'completed': 3}, 'source': 'REPLAY_FILE'}
    document = client.queue('local-one', 'session:' + str(uuid4()), payload)
    api.drop_reply = True
    with pytest.raises(CloudError): client.sync()
    reopened = CloudAccount(tmp_path, api, vault)
    assert reopened.sync()['uploaded'] == 1
    assert reopened.sync()['uploaded'] == 0
    assert len(api.records) == 1
    with reopened.db() as db:
        row = db.execute('SELECT document,resource_id FROM outbox').fetchone()
    assert json.loads(row[0]) == document
    assert row[1] == api.records[0]['id']


def test_accounts_never_retarget_pending_records(tmp_path):
    client, api, _ = setup(tmp_path)
    client.queue('local-one', 'event', {'count': 2})
    client.login('two', '2')
    with pytest.raises(CloudError): client.bind('local-one')
    with pytest.raises(CloudError): client.queue('local-one', 'second', {})
    assert client.sync()['uploaded'] == 0
    assert api.records == []
    client.login('one', '1')
    assert client.sync()['uploaded'] == 1


def test_refresh_rotates_and_persists(tmp_path):
    client, api, vault = setup(tmp_path)
    api.token = 'expired'
    assert client.me()['patient_id'] == api.users['one']
    assert api.refreshes == 1
    assert vault.read()['access_token'] == 'rotated'
    client.me()
    assert api.refreshes == 1


def test_offline_queue_no_network_and_immutable_payload(tmp_path):
    client, api, _ = setup(tmp_path)
    def disconnected(*args, **kwargs): raise CloudError('断网')
    client.request = disconnected
    original = client.queue('local-one', 'event', {'count': 2})
    assert client.queue('local-one', 'event', {'count': 2}) == original
    with pytest.raises(CloudError): client.queue('local-one', 'event', {'count': 3})
    with pytest.raises(CloudError): client.sync()
    assert len(api.records) == 0


def test_future_schema_not_overwritten(tmp_path):
    path = tmp_path/'cloud-outbox-v1.sqlite3'
    with sqlite3.connect(path) as db: db.execute('PRAGMA user_version=99')
    before = path.read_bytes()
    with pytest.raises(CloudError): CloudAccount(tmp_path, vault=MemoryVault())
    assert path.read_bytes() == before


def test_only_saved_own_non_synthetic_results_and_no_raw_media():
    snapshot = dict(id='a', participant_id='p', status='FINISHED', source_kind='REPLAY_FILE',
                    usage_context='SELF_USE',
                    summary={'completed': 3, 'max': None}, raw_frames=['private'], poses=['private'])
    payload = desktop_record(snapshot, 'p')
    assert payload['result']['summary'] == snapshot['summary']
    assert 'poses' not in payload['result'] and 'raw_frames' not in payload['result']
    for changes in ({'participant_id': 'other'}, {'status': 'RUNNING'}, {'source_kind': 'SYNTHETIC'}, {'usage_context': 'DEMO'}):
        with pytest.raises(CloudError): desktop_record({**snapshot, **changes}, 'p')


@pytest.mark.skipif(os.name != 'nt', reason='Windows DPAPI')
def test_tokens_encrypted_at_rest(tmp_path):
    vault = TokenVault(tmp_path/'token.dpapi')
    value = dict(origin=ORIGIN, role='PATIENT', patient_id=str(uuid4()), access_token='very-private-token')
    vault.write(value)
    assert b'very-private-token' not in vault.path.read_bytes()
    assert vault.read() == value
    vault.clear()
    assert not vault.path.exists()


def test_first_use_cloud_login_available_without_local_upload_binding(tmp_path):
    from PySide6.QtWidgets import QApplication, QPushButton
    from app.ui.cloud_account import CloudAccountDialog
    app = QApplication.instance() or QApplication([])
    dialog = CloudAccountDialog(tmp_path, None, '', lambda: [], client=CloudAccount(tmp_path, vault=MemoryVault()))
    try:
        assert not dialog.confirm.isEnabled()
        assert any(b.text() == '登录' and b.isEnabled() for b in dialog.findChildren(QPushButton))
        dialog.confirm.setChecked(True)
        dialog.upload()
        assert dialog.future is None
        assert '确认' in dialog.status.text()
    finally:
        dialog.close()
        app.processEvents()
