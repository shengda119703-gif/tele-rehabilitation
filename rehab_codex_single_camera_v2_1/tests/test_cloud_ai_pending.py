"""Temporary SQLite queues and fictitious RPC replies; never contact an AI provider."""
from copy import deepcopy
from uuid import uuid4

import pytest

from app.cloud_account import CloudAccount, CloudError, ORIGIN


class MemoryVault:
    def __init__(self):
        self.value = dict(origin=ORIGIN, role='PATIENT', patient_id=str(uuid4()),
                          account_id=str(uuid4()), access_token='TEST access', refresh_token='TEST refresh')

    def read(self):
        return deepcopy(self.value)


@pytest.fixture
def environment(tmp_path):
    vault = MemoryVault()
    calls = []
    cloud = {'reply': lambda body: {'state': 'SUCCEEDED', 'answer': 'TEST answer'}}

    def request(path, method='GET', body=None, token=None):
        if path == '/auth/me':
            return {key: vault.value[key] for key in ('role', 'patient_id', 'account_id')}
        assert path == '/patients/' + vault.value['patient_id'] + '/ai/requests'
        assert method == 'POST'
        calls.append(deepcopy(body))
        return cloud['reply'](body)

    return CloudAccount(tmp_path, request, vault), cloud, calls, vault


def pending(client):
    with client.db() as db:
        return [dict(row) for row in db.execute('SELECT * FROM ai_pending ORDER BY patient_id')]


def fail(code='', status=0):
    raise CloudError('TEST ' + (code or 'network/timeout'), status, code)


@pytest.mark.parametrize('code', ['AI_NOT_CONFIGURED', 'AI_BUSY', 'AI_QUOTA_EXHAUSTED', 'AI_REJECTED'])
def test_no_dispatch_error_releases_pending_for_different_question(environment, code):
    client, cloud, calls, _ = environment
    cloud['reply'] = lambda body: fail(code, 503)
    with pytest.raises(CloudError) as error:
        client.ask_ai('TEST first')
    assert error.value.code == code
    assert pending(client) == []
    cloud['reply'] = lambda body: {'state': 'SUCCEEDED', 'answer': 'TEST second answer'}
    assert client.ask_ai('TEST second')['answer'] == 'TEST second answer'
    assert calls[0]['operation_id'] != calls[1]['operation_id']
    assert calls[1]['text'] == 'TEST second'


@pytest.mark.parametrize('state', ['SUCCEEDED', 'UNMETERED', 'UNKNOWN', 'REJECTED'])
def test_terminal_receipt_releases_pending(environment, state):
    client, cloud, _, _ = environment
    cloud['reply'] = lambda body: {'state': state, 'answer': None}
    assert client.ask_ai('TEST question')['state'] == state
    assert pending(client) == []


@pytest.mark.parametrize(('code', 'status'), [('', 0), ('', 504), ('AI_UNKNOWN', 502),
    ('IDEMPOTENCY_CONFLICT', 409), ('AUTH_REQUIRED', 403), ('VALIDATION_ERROR', 422)])
def test_ambiguous_error_preserves_original_operation_across_reopen(environment, code, status):
    client, cloud, calls, vault = environment
    cloud['reply'] = lambda body: fail(code, status)
    with pytest.raises(CloudError):
        client.ask_ai('TEST original')
    original = pending(client)
    reopened = CloudAccount(client.directory, client.request, vault)
    with pytest.raises(CloudError, match='原提问'):
        reopened.ask_ai('TEST different')
    assert len(calls) == 1
    assert pending(reopened) == original
    cloud['reply'] = lambda body: {'state': 'SUCCEEDED', 'answer': 'TEST recovered'}
    reopened.ask_ai()
    assert calls[1] == calls[0]
    assert pending(client) == []


@pytest.mark.parametrize('state', [None, 'RUNNING', 'PENDING', 'FAILED'])
def test_unresolved_receipt_keeps_pending(environment, state):
    client, cloud, calls, _ = environment
    cloud['reply'] = lambda body: {'state': state}
    client.ask_ai('TEST original')
    assert pending(client)[0]['operation_id'] == calls[0]['operation_id']
    with pytest.raises(CloudError, match='原提问'):
        client.ask_ai('TEST different')
    assert len(calls) == 1


@pytest.mark.parametrize('outcome', ['AI_BUSY', 'REJECTED'])
def test_cleanup_cannot_delete_newer_operation(environment, outcome):
    client, cloud, _, vault = environment
    newer = str(uuid4())

    def reply(body):
        with client.db() as db:
            db.execute('UPDATE ai_pending SET operation_id=?,text=? WHERE patient_id=?',
                       (newer, 'TEST newer', vault.value['patient_id']))
        if outcome == 'REJECTED':
            return {'state': outcome}
        fail(outcome, 429)

    cloud['reply'] = reply
    if outcome == 'REJECTED':
        client.ask_ai('TEST original')
    else:
        with pytest.raises(CloudError):
            client.ask_ai('TEST original')
    assert pending(client)[0]['operation_id'] == newer
    assert pending(client)[0]['text'] == 'TEST newer'


@pytest.mark.parametrize('outcome', ['AI_NOT_CONFIGURED', 'REJECTED'])
@pytest.mark.parametrize('change_patient', [False, True])
def test_account_change_does_not_retire_original_pending(environment, outcome, change_patient):
    client, cloud, _, vault = environment
    original = []

    def reply(body):
        original.extend(pending(client))
        vault.value['account_id'] = str(uuid4())
        if change_patient:
            vault.value['patient_id'] = str(uuid4())
        if outcome == 'REJECTED':
            return {'state': outcome}
        fail(outcome, 503)

    cloud['reply'] = reply
    with pytest.raises(CloudError):
        client.ask_ai('TEST original')
    assert pending(client) == original


@pytest.mark.parametrize('outcome', ['AI_QUOTA_EXHAUSTED', 'REJECTED'])
def test_cleanup_does_not_touch_other_patient_with_same_operation(environment, outcome):
    client, cloud, _, vault = environment
    other_patient = str(uuid4())

    def reply(body):
        with client.db() as db:
            db.execute('INSERT INTO ai_pending VALUES (?,?,?)', (other_patient, body['operation_id'], 'TEST other'))
        if outcome == 'REJECTED':
            return {'state': outcome}
        fail(outcome, 429)

    cloud['reply'] = reply
    if outcome == 'REJECTED':
        client.ask_ai('TEST original')
    else:
        with pytest.raises(CloudError):
            client.ask_ai('TEST original')
    rows = pending(client)
    assert len(rows) == 1
    assert rows[0]['patient_id'] == other_patient
    assert rows[0]['text'] == 'TEST other'
