"""Actual owned routes and durable job identity; fixtures do not measure human motion."""
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from mobile_rehab.server import Jobs, create_app


HEADERS = {'X-Rehab-Client': 'mobile-v1', 'Content-Type': 'application/octet-stream'}
URL = '/api/jobs?exercise=shoulder_abduction&side=left&consent=yes'


def test_lost_upload_reply_can_be_queried_without_a_second_job(tmp_path):
    app = create_app(tmp_path, pair_key='TEST-only', runner=lambda item: None)
    operation = str(uuid4())
    with TestClient(app, headers=HEADERS) as client:
        client.post('/api/pair', json={'code': 'TEST-only'})
        created = client.post(URL, content=b'TEST not a video' * 5,
                              headers={'X-Rehab-Upload-Operation': operation})
        assert created.status_code == 200
        job_id = created.json()['id']
        # Deliberately ignore the POST reply; recover the same durable identity.
        receipt = client.get('/api/uploads/' + operation)
        assert receipt.status_code == 200
        assert receipt.json()['id'] == job_id
        assert receipt.json()['upload_operation'] == operation
        assert receipt.json()['exercise'] == 'shoulder_abduction'
        assert receipt.json()['side'] == 'left'
        assert receipt.json()['mode'] == 'assessment'
        assert receipt.json()['video_available'] is True
        duplicate = client.post(URL, content=b'different TEST bytes' * 5,
                                headers={'X-Rehab-Upload-Operation': operation})
        assert duplicate.status_code == 409
        assert len(client.get('/api/jobs').json()) == 1
        with TestClient(app, headers=HEADERS) as other:
            other.post('/api/pair', json={'code': 'TEST-only'})
            assert other.get('/api/uploads/' + operation).status_code == 404
    restored = Jobs(app.state.jobs.root, runner=lambda item: None)
    try:
        original = next(iter(restored.items.values()))
        assert restored.upload_receipt(operation, original['owner'])['id'] == job_id
    finally:
        restored.close()


def test_upload_query_auth_format_and_missing_are_distinct(tmp_path):
    app = create_app(tmp_path, pair_key='TEST-only', runner=lambda item: None)
    with TestClient(app, headers=HEADERS) as client:
        assert client.get('/api/uploads/' + str(uuid4())).status_code == 401
        client.post('/api/pair', json={'code': 'TEST-only'})
        assert client.get('/api/uploads/not-a-valid-key').status_code == 400
        assert client.get('/api/uploads/' + str(uuid4())).status_code == 404
        assert client.post(URL, content=b'x' * 40,
                           headers={'X-Rehab-Upload-Operation': 'bad'}).status_code == 400
        assert client.get('/api/jobs').json() == []


def test_parallel_reservations_keep_one_durable_identity(tmp_path):
    jobs = Jobs(tmp_path, runner=lambda item: None)
    operation = str(uuid4())
    try:
        def reserve(_):
            try:
                return jobs.reserve('TEST-owner', 'shoulder_abduction', 'left',
                                    upload_operation=operation, metadata={'mode': 'assessment'})['id']
            except HTTPException as error:
                return error.status_code
        with ThreadPoolExecutor(max_workers=6) as pool:
            results = list(pool.map(reserve, range(6)))
        identities = [result for result in results if isinstance(result, str)]
        assert len(identities) == 1
        assert results.count(409) == 5
        assert len(list(tmp_path.glob('*/*/job.json'))) == 1
        assert jobs.upload_receipt(operation, 'TEST-owner')['id'] == identities[0]
        with pytest.raises(HTTPException) as raised:
            jobs.upload_receipt(operation, 'another-owner')
        assert raised.value.status_code == 404
    finally:
        jobs.close()


def test_failed_durable_write_does_not_create_an_in_memory_receipt(tmp_path, monkeypatch):
    jobs = Jobs(tmp_path, runner=lambda item: None)
    operation = str(uuid4())
    try:
        def fail_write(*args, **kwargs):
            raise OSError('TEST storage failure')
        monkeypatch.setattr('mobile_rehab.server.save', fail_write)
        with pytest.raises(OSError):
            jobs.reserve('TEST-owner', 'shoulder_abduction', 'left', upload_operation=operation)
        assert jobs.items == {}
        with pytest.raises(HTTPException) as raised:
            jobs.upload_receipt(operation, 'TEST-owner')
        assert raised.value.status_code == 404
    finally:
        jobs.close()
