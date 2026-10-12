import json
import os
import sqlite3
from uuid import uuid4
import pytest

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
        if '/records?' in path:
            return dict(items=[r for r in self.records if r['patient_id'] == self.users[self.actor]])
        return dict(status='COMMITTED')


def setup(tmp_path):
    api, vault = Server(), MemoryVault()
    client = CloudAccount(tmp_path, api, vault)
    client.login('one', '1')
    client.bind('local-one')
    return client, api, vault


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
