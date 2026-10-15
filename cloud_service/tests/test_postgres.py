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


def test_family_invite_single_use_across_workers_and_private_defaults(postgres_app):
    app=postgres_app
    clients=[]
    for name in ("qa-family-a","qa-family-b","qa-family-c"):
        c=TestClient(app,headers={"X-Ankang-Client":"native"})
        ident=c.post(BASE+"/auth/register",json={"username":name,"password":"1"}).json()["patient_id"]
        signed=c.post(BASE+"/auth/password/login",json={"username":name,"password":"1","client_kind":"APK"}).json()
        c.headers["Authorization"]="Bearer "+signed["access_token"]
        clients.append((c,BASE+"/patients/"+ident+"/family"))
    a,ap=clients[0]
    code=a.post(ap+"/invite",json={}).json()["code"]
    with ThreadPoolExecutor(2) as pool:
        statuses=list(pool.map(lambda pair:pair[0].post(pair[1]+"/bind",json={"code":code}).status_code,clients[1:]))
    assert sorted(statuses)==[200,400]
    state=a.get(ap).json()
    assert len(state["familyMembers"])==1
    assert all(row==[] for row in state["grants"].values())
    assert state["familyMembers"][0]["categories"]==[]


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


def workbench_native(postgres_app):
    patient, signed = native_patient(postgres_app)
    headers = {"X-Ankang-Client": "native", "Authorization": "Bearer " + signed["access_token"]}
    with TestClient(postgres_app, headers=headers) as client:
        response = client.put(BASE + "/patients/" + patient + "/doctor-access",
            json={"enabled": True, "expected_version": 0})
        assert response.status_code == 200, response.text
    return patient, headers


def test_concurrent_workbench_messages_retry_and_unique_server_sequences(postgres_app):
    patient, headers = workbench_native(postgres_app)
    path = BASE + "/patients/" + patient + "/messages"
    value = {"operation_id": str(uuid4()), "text": "TEST synthetic concurrent message"}
    def send(body):
        with TestClient(postgres_app, headers=headers) as client:
            response = client.post(path, json=body)
            assert response.status_code == 201, response.text
            return response.json()
    with ThreadPoolExecutor(max_workers=4) as pool:
        retries = list(pool.map(send, [value] * 4))
    assert len({reply["resource_id"] for reply in retries}) == 1
    assert sum(not reply["idempotent"] for reply in retries) == 1
    values = [{"operation_id": str(uuid4()), "text": "TEST independent " + str(i)} for i in range(4)]
    with ThreadPoolExecutor(max_workers=4) as pool:
        distinct = list(pool.map(send, values))
    assert sorted(reply["item"]["sequence"] for reply in distinct) == [2, 3, 4, 5]
    with TestClient(postgres_app, headers=headers) as client:
        items = client.get(path).json()["items"]
    assert [item["sequence"] for item in items] == [1, 2, 3, 4, 5]


def test_concurrent_workbench_current_plan_only_one_acceptance(postgres_app):
    from cloud_service.tests.test_accounts import login
    from cloud_service.tests.test_workbench import adoption, publish
    patient, headers = workbench_native(postgres_app)
    doctor = TestClient(postgres_app, headers={"Origin": "http://testserver"})
    assert login(doctor, "doctor").status_code == 200
    plan = publish(doctor, patient)
    path = BASE + "/patients/" + patient + "/plans/" + plan["id"] + "/accept"
    requests = [adoption(plan) for _ in range(2)]
    def accept(body):
        with TestClient(postgres_app, headers=headers) as client:
            response = client.post(path, json=body)
            return body, response.status_code, response.json()
    with ThreadPoolExecutor(max_workers=2) as pool:
        replies = list(pool.map(accept, requests))
    assert sorted(status for _, status, _ in replies) == [200, 412]
    winner = next(value for value, status, _ in replies if status == 200)
    with TestClient(postgres_app, headers=headers) as client:
        retry = client.post(path, json=winner)
        assert retry.status_code == 200 and retry.json()["idempotent"]
        current = client.get(BASE + "/patients/" + patient + "/plans/current").json()
        assert current["current_revision"] == 1 and current["plan"]["id"] == plan["id"]
