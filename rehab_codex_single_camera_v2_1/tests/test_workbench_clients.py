"""Fictitious TEST payloads in temporary stores; no camera, person, model or remote server."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from cloud_service.app import BASE, create_app
from cloud_service.config import Settings
from cloud_service.database import Database
from cloud_service.security import bootstrap_doctor
from cloud_service.tests.test_accounts import client as web_client, login
from cloud_service.tests.test_workbench import plan_body, publish, adoption
from app.cloud_account import CloudAccount, CloudError
from app.exercises import exercise_spec
from app.product.backend import ProductBackend
from app.storage import Storage
from test_cloud_account import MemoryVault
from test_saved_training_plans import assessment
from app.assessment import build_body_profile
from app.training_plans import prepare_training_plan


OWNER = 'TEST-workbench-local-person'
SCOPE = {'participant_id': OWNER, 'source_kind': 'LIVE_CAMERA', 'usage_context': 'SELF_USE'}


class LocalHTTP:
    def __init__(self, app):
        self.client = TestClient(app, headers={'X-Ankang-Client': 'native'})
        self.offline = False
        self.lose_ack = ''

    def __call__(self, path, method='GET', body=None, token=None):
        if self.offline:
            raise CloudError('TEST disconnected')
        headers = {'Authorization': 'Bearer ' + token} if token else {}
        response = self.client.request(method, BASE + path, json=body, headers=headers)
        value = response.json()
        if not response.is_success:
            raise CloudError(value.get('message', 'TEST request failed'), response.status_code, value.get('code', ''))
        if method == 'POST' and self.lose_ack and path.endswith(self.lose_ack):
            self.lose_ack = ''
            raise CloudError('TEST saved, acknowledgement lost')
        return value


@pytest.fixture
def environment(tmp_path):
    settings = Settings('sqlite:///' + str(tmp_path / 'server.sqlite3'), 'x' * 40, ('http://testserver',), 'test')
    database = Database(settings.database_url)
    database.migrate()
    bootstrap_doctor(database, settings, '1')
    app = create_app(settings, database)
    http, vault = LocalHTTP(app), MemoryVault()
    account = CloudAccount(tmp_path / 'local/cloud-account', http, vault)
    account.register('test-native', '1')
    account.login('test-native', '1')
    account.bind(OWNER)
    account.consent(OWNER, True)
    account.grant(True)
    doctor = web_client(app)
    assert login(doctor, 'doctor').is_success
    store = Storage(tmp_path / 'local/home_rehab.sqlite3')
    backend = ProductBackend(tmp_path / 'local')
    backend.call('profile.save', OWNER, {'profile': {'name': 'TEST fictitious patient', 'age': 35, 'conditions': [], 'medications': []}}, SCOPE)
    now = datetime.now(timezone.utc)
    record = assessment(**SCOPE, id='TEST-assessment', start_utc=(now-timedelta(minutes=2)).isoformat(), end_utc=(now-timedelta(minutes=1)).isoformat(), test_fixture=True)
    store.save_session(record)
    yield account, http, vault, doctor, store, backend, tmp_path
    backend.close()
    store.close()
    database.engine.dispose()


def test_actual_backend_saved_snapshot_rehab_feedback_revision_and_doctor_projection(environment):
    account, http, vault, doctor, store, backend, directory = environment
    patient = account.session()['patient_id']
    snapshot = backend.call('snapshot', OWNER, {}, SCOPE)
    account.queue_product(OWNER, snapshot)
    training = {**store.get_session('TEST-assessment'), 'id': 'TEST-training', 'submode': 'training', 'training_feedback': {'pain': 0, 'fatigue': 1, 'revision': 1}}
    store.save_session(training)
    account.queue_rehab(OWNER, store)
    http.lose_ack = '/record-events'
    with pytest.raises(CloudError):
        account.sync()
    reopened = CloudAccount(directory / 'local/cloud-account', http, vault)
    reopened.sync()
    rows = doctor.get(BASE + '/patients/' + patient + '/records/latest').json()['items']
    assert {r['payload']['kind'] for r in rows} == {'profile', 'assessment', 'training'}
    assert all(r['payload']['owner_id'] == OWNER for r in rows)
    assert all('raw_frames' not in json.dumps(r) and 'chat' not in json.dumps(r) for r in rows)
    training['training_feedback'].update(fatigue=2, revision=2)
    store.save_session(training)
    reopened.queue_rehab(OWNER, store)
    reopened.sync()
    current = doctor.get(BASE + '/patients/' + patient + '/records/latest').json()['items']
    updated = next(r for r in current if r['payload']['kind'] == 'training')
    assert updated['payload']['revision'] == 2
    assert updated['payload']['result']['training_feedback']['fatigue'] == 2
    reopened.queue_rehab(OWNER, store)
    assert reopened.sync()['uploaded'] == 0


def test_durable_messages_offline_reopen_lost_reply_and_unread_read_cursor(environment):
    account, http, vault, doctor, store, backend, directory = environment
    patient = account.session()['patient_id']
    http.offline = True
    operation = str(uuid4())
    with pytest.raises(CloudError):
        account.send(operation, 'TEST follow-up question, fictitious')
    http.offline = False
    reopened = CloudAccount(directory / 'local/cloud-account', http, vault)
    http.lose_ack = '/messages'
    with pytest.raises(CloudError):
        reopened.sync_messages()
    restarted = CloudAccount(directory / 'local/cloud-account', http, vault)
    assert len(restarted.sync_messages()['items']) == 1
    reply = doctor.post(BASE + '/patients/' + patient + '/messages', json={'operation_id': str(uuid4()), 'text': 'TEST doctor answer, no human recipient'})
    assert reply.is_success
    value = restarted.messages()
    assert value['unread_count'] == 1
    restarted.mark_read(value['items'][-1]['sequence'])
    assert restarted.messages()['unread_count'] == 0
    http.offline = True
    assert restarted.messages()['offline'] is True
    http.offline = False
    restarted.register('test-other', '1')
    restarted.login('test-other', '1')
    assert restarted.messages()['items'] == []
    with pytest.raises(CloudError):
        restarted.bind(OWNER)


def test_published_plan_validates_real_local_contract_persists_and_recovers_acceptance(environment):
    account, http, vault, doctor, store, backend, directory = environment
    patient = account.session()['patient_id']
    plan = publish(doctor, patient)
    http.lose_ack = '/accept'
    with pytest.raises(CloudError):
        account.adopt(plan, 0, OWNER, SCOPE, store)
    assert store.list_training_plans(SCOPE) == []
    saved = store.list_training_plans(SCOPE, include_archived=True)
    assert len(saved) == 1 and saved[0]['revision'] == 1
    assert saved[0]['items'][0]['exercise_id'] == 'shoulder_abduction'
    reopened = CloudAccount(directory / 'local/cloud-account', http, vault)
    receipt = reopened.adopt(plan, 0, OWNER, SCOPE, store)
    assert receipt['status'] == 'COMMITTED' and receipt['idempotent'] is True
    assert len(store.list_training_plans(SCOPE)) == 1
    assert reopened.current()['local_validation']['local_plan_id'] == saved[0]['id']


def test_unsupported_stale_wrong_scope_and_new_failed_assessment_block_adoption(environment):
    account, http, vault, doctor, store, backend, directory = environment
    plan = publish(doctor, account.session()['patient_id'])
    bad = json.loads(json.dumps(plan))
    bad['items'][0]['exercise_id'] = 'TEST-nonexistent'
    with pytest.raises(ValueError):
        account.adopt(bad, 0, OWNER, SCOPE, store)
    with pytest.raises(CloudError):
        account.adopt(plan, 0, OWNER, {**SCOPE, 'participant_id': 'other'}, store)
    old = store.get_session('TEST-assessment')
    old['end_utc'] = (datetime.now(timezone.utc)-timedelta(days=8)).isoformat()
    old['start_utc'] = (datetime.now(timezone.utc)-timedelta(days=8, minutes=1)).isoformat()
    store.save_session(old)
    with pytest.raises((CloudError, ValueError), match='过期'):
        account.adopt(plan, 0, OWNER, SCOPE, store)
    failed_time = datetime.now(timezone.utc).isoformat()
    failed = {**old, 'id': 'TEST-latest-failed', 'end_utc': failed_time, 'start_utc': failed_time, 'summary': {'valid_ratio': 0, 'valid_sample_count': 0}}
    store.save_session(failed)
    latest = build_body_profile(store.list_sessions(), **SCOPE)
    selected = next(item for item in latest['items'] if item['exercise_id'] == 'shoulder_abduction' and item['side'] == 'left')
    assert selected['session_id'] == failed['id'] and selected['status'] == 'UNAVAILABLE'
    with pytest.raises(ValueError, match='有效评估'):
        account.adopt(plan, 0, OWNER, SCOPE, store)
    assert store.list_training_plans(SCOPE) == []


def expire_assessment(store):
    record = store.get_session('TEST-assessment')
    record['end_utc'] = (datetime.now(timezone.utc)-timedelta(days=8)).isoformat()
    record['start_utc'] = (datetime.now(timezone.utc)-timedelta(days=8, minutes=1)).isoformat()
    store.save_session(record)


def test_pending_intent_survives_local_insert_failure_and_cannot_be_restored_active(environment, monkeypatch):
    account, http, vault, doctor, store, backend, directory = environment
    plan = publish(doctor, account.session()['patient_id'])
    original = store.save_training_plan
    monkeypatch.setattr(store, 'save_training_plan', lambda *a, **kw: (_ for _ in ()).throw(OSError('TEST interrupted disk insert')))
    with pytest.raises(OSError):
        account.adopt(plan, 0, OWNER, SCOPE, store)
    assert store.list_training_plans(SCOPE, include_archived=True) == []
    with account.db() as db:
        frozen = json.loads(db.execute('SELECT document FROM plan_acceptance').fetchone()[0])
    monkeypatch.setattr(store, 'save_training_plan', original)
    # Recover the exact prepared local ID first; a failed network reply keeps it disabled.
    http.lose_ack = '/accept'
    with pytest.raises(CloudError):
        account.adopt(plan, 0, OWNER, SCOPE, store)
    pending = store.get_training_plan(frozen['pending_record']['id'])
    assert pending['status'] == 'PENDING_DOCTOR'
    with pytest.raises(ValueError, match='未确认'):
        store.set_training_plan_archived(pending['id'], SCOPE, False, expected_revision=pending['revision'])
    with pytest.raises(ValueError):
        original(pending, expected_revision=pending['revision'])
    assert account.adopt(plan, 0, OWNER, SCOPE, store)['local_status'] == 'ACTIVE'


def test_lost_acceptance_reply_recovers_after_assessment_expires_without_activation(environment):
    account, http, vault, doctor, store, backend, directory = environment
    plan = publish(doctor, account.session()['patient_id'])
    http.lose_ack = '/accept'
    with pytest.raises(CloudError):
        account.adopt(plan, 0, OWNER, SCOPE, store)
    expire_assessment(store)
    reopened = CloudAccount(directory / 'local/cloud-account', http, vault)
    result = reopened.adopt(plan, 0, OWNER, SCOPE, store)
    assert result['status'] == 'COMMITTED' and result['idempotent'] is True
    assert result['local_status'] == 'NEEDS_REVIEW'
    assert store.list_training_plans(SCOPE) == []


def test_stale_acceptance_intent_is_retired_and_fresh_approval_uses_new_revision(environment):
    account, http, vault, doctor, store, backend, directory = environment
    patient = account.session()['patient_id']
    old = publish(doctor, patient)
    account.accept(old, 0, str(uuid4()), adoption(old)['local_validation'])
    with pytest.raises(CloudError) as caught:
        account.adopt(old, 0, OWNER, SCOPE, store)
    assert caught.value.status == 412
    assert store.list_training_plans(SCOPE) == []
    with account.db() as db:
        assert db.execute('SELECT count(*) FROM plan_acceptance').fetchone()[0] == 0
    result = account.adopt(old, 1, OWNER, SCOPE, store)
    assert result['local_status'] == 'ACTIVE'
    assert len(store.list_training_plans(SCOPE)) == 1


def test_old_lost_reply_is_not_activated_after_another_device_accepts_newer_plan(environment):
    account, http, vault, doctor, store, backend, directory = environment
    patient = account.session()['patient_id']
    old = publish(doctor, patient)
    http.lose_ack = '/accept'
    with pytest.raises(CloudError):
        account.adopt(old, 0, OWNER, SCOPE, store)
    newer = publish(doctor, patient)
    account.accept(newer, 1, str(uuid4()), adoption(newer)['local_validation'])
    result = account.adopt(old, 0, OWNER, SCOPE, store)
    assert result['idempotent'] is True and result['local_status'] == 'SUPERSEDED'
    assert store.list_training_plans(SCOPE) == []


def test_original_training_prepare_rechecks_age_and_latest_failed_assessment(environment):
    account, http, vault, doctor, store, backend, directory = environment
    cloud = publish(doctor, account.session()['patient_id'])
    assert account.adopt(cloud, 0, OWNER, SCOPE, store)['local_status'] == 'ACTIVE'
    plan = store.list_training_plans(SCOPE)[0]
    key = plan['items'][0]['key']
    prepare_training_plan(plan, key, build_body_profile(store.list_sessions(), **SCOPE))
    expire_assessment(store)
    with pytest.raises(ValueError, match='过期'):
        prepare_training_plan(plan, key, build_body_profile(store.list_sessions(), **SCOPE))
    old = store.get_session('TEST-assessment')
    failed = {**old, 'id': 'TEST-new-failed', 'start_utc': datetime.now(timezone.utc).isoformat(), 'end_utc': datetime.now(timezone.utc).isoformat(), 'summary': {'valid_ratio': 0, 'valid_sample_count': 0}}
    store.save_session(failed)
    with pytest.raises(ValueError, match='有效评估'):
        prepare_training_plan(plan, key, build_body_profile(store.list_sessions(), **SCOPE))


def test_paired_product_backend_sync_and_adopt_use_bound_actual_store(environment, monkeypatch):
    account, http, vault, doctor, store, backend, directory = environment
    import app.cloud_account as cloud_module
    monkeypatch.setattr(cloud_module, 'CloudAccount', lambda path: account)
    assert backend.call('workbench.identity', OWNER, {}, SCOPE)['connected'] is True
    result = backend.call('workbench.sync', OWNER, {}, SCOPE)
    assert result['uploaded'] == 2
    patient = account.session()['patient_id']
    kinds = doctor.get(BASE + '/patients/' + patient + '/records/latest').json()['items']
    assert {row['payload']['kind'] for row in kinds} == {'profile', 'assessment'}
    cloud = publish(doctor, patient)
    result = backend.call('workbench.adopt', OWNER, {'plan_id': cloud['id'], 'expected_version': cloud['version'], 'expected_current_revision': 0}, SCOPE)
    assert result['local_status'] == 'ACTIVE'
    assert store.list_training_plans(SCOPE)[0]['doctor_publication']['id'] == cloud['id']
    with pytest.raises(RuntimeError, match='本人档案'):
        backend.call('workbench.messages', 'TEST-other-owner', {}, SCOPE)
