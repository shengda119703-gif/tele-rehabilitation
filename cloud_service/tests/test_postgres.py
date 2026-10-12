"""Real PostgreSQL concurrency tests, restricted to a dedicated QA database."""
from concurrent.futures import ThreadPoolExecutor
import os
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest
from sqlalchemy.engine import make_url

from cloud_service.app import BASE, create_app
from cloud_service.config import Settings
from cloud_service.database import Database, metadata
from cloud_service.security import bootstrap_doctor


@pytest.fixture
def postgres_app():
    url = os.environ.get("CLOUD_TEST_DATABASE_URL")
    if not url:
        pytest.skip("A dedicated PostgreSQL QA database is not configured")
    if make_url(url).database != "ankang_cloud_qa":
        pytest.fail("Refusing to mutate a database other than ankang_cloud_qa")
    db = Database(url)
    # Only isolated synthetic QA tables. Never run against production.
    with db.engine.begin() as connection:
        metadata.drop_all(connection)
    db.migrate()
    settings = Settings(url, "synthetic-test-secret-" * 3, ("http://testserver",), "test")
    bootstrap_doctor(db, settings, "1")
    app = create_app(settings, db)
    yield app
    db.engine.dispose()


def native_patient(app):
    c = TestClient(app, headers={"Origin": "http://testserver"})
    patient = c.post(BASE + "/auth/register", json={"username": "qa", "password": "1"}).json()["patient_id"]
    signed = c.post(BASE + "/auth/password/login", json={"username": "qa", "password": "1", "client_kind": "APK"}).json()
    return patient, signed


def test_concurrent_native_refresh_only_once(postgres_app):
    _, signed = native_patient(postgres_app)
    def attempt(_):
        with TestClient(postgres_app, headers={"X-Ankang-Client": "native"}) as c:
            return c.post(BASE + "/auth/refresh", json={"refresh_token": signed["refresh_token"]}).status_code
    with ThreadPoolExecutor(max_workers=4) as executor:
        statuses = list(executor.map(attempt, range(4)))
    assert statuses.count(200) == 1
    assert statuses.count(401) == 3


def test_concurrent_record_retries_one_fact(postgres_app):
    patient, signed = native_patient(postgres_app)
    payload = {"operation_id": str(uuid4()), "source_event_id": "qa-event", "installation_id": "qa-instance",
               "source_kind": "SELF_REPORT", "payload": {"title": "Synthetic QA record"}}
    def attempt(_):
        with TestClient(postgres_app, headers={"Authorization": "Bearer " + signed["access_token"]}) as c:
            r = c.post(BASE + "/patients/" + patient + "/record-events", json=payload)
            assert r.status_code == 201, r.text
            return r.json()
    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(attempt, range(4)))
    assert len({r["resource_id"] for r in results}) == 1
    assert sum(not r["idempotent"] for r in results) == 1
