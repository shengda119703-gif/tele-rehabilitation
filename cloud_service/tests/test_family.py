"""Isolated fictitious accounts only; never access a provider or production DB."""
from concurrent.futures import ThreadPoolExecutor
import json
import time

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import select, update

from cloud_service.app import BASE
from cloud_service.database import accounts, audit, schema
from cloud_service.family import invites, links, summaries
from cloud_service.security import digest
from cloud_service.tests.test_accounts import setup, client, register, login


def path(ident, tail=""):
    return BASE + "/patients/" + ident + "/family" + tail


def users(setup):
    a, b, c = [client(setup[0]) for _ in range(3)]
    ids = [register(who, name).json()["patient_id"] for who, name in zip((a,b,c), ("alice","bob","carol"))]
    for who, name in zip((a,b,c), ("alice","bob","carol")):
        assert login(who, name).status_code == 200
    return (a,b,c), ids


def link(a, aid, b, bid):
    result = a.post(path(aid,"/invite"),json={})
    assert result.status_code == 200, result.text
    code = result.json()["code"]
    assert b.post(path(bid,"/bind"),json={"code":code.lower()}).status_code == 200
    return code


def document(**changes):
    return {"name":"TEST fictitious name","health":[{"timestamp":"2026-10-15T04:00:00Z","text":"TEST shareable health"}],
        "rehab":[{"timestamp":"2026-10-15T04:00:00Z","text":"TEST rehabilitation summary"}],
        "doses":[{"medName":"TEST fictitious medicine","date":"2026-10-15","time":"08:00","status":"unrecorded"}],**changes}


def test_same_account_cross_client_link_defaults_private_and_no_clinical_mutation(setup):
    (a,b,c),(aid,bid,cid) = users(setup)
    code=link(a,aid,b,bid)
    for who, own, other in ((a,aid,bid),(b,bid,aid)):
        state=who.get(path(own)).json()
        assert state["grants"] == {other:[]}
        assert state["familyMembers"][0]["ownerId"] == other
        assert all(state["familyMembers"][0][key] == [] for key in ("categories","health","rehab","doses"))
    assert c.get(path(cid)).json()["familyMembers"] == []
    another=client(setup[0]);assert login(another,"alice").status_code==200
    assert another.get(path(aid)).json()["familyMembers"][0]["ownerId"]==bid
    assert b.post(path(bid,"/bind"),json={"code":code}).json()["idempotent"] is True
    assert c.post(path(cid,"/bind"),json={"code":code}).status_code==400
    with setup[1].engine.connect() as con:
        assert con.execute(select(invites.c.code_hash)).scalar()==digest(code)
        assert code not in json.dumps([dict(r) for r in con.execute(select(audit)).mappings()])


def test_expiry_replacement_self_and_malformed_invite(setup):
    (a,b,_),(aid,bid,_) = users(setup)
    first=a.post(path(aid,"/invite"),json={}).json()["code"]
    second=a.post(path(aid,"/invite"),json={}).json()["code"]
    assert b.post(path(bid,"/bind"),json={"code":first}).status_code==400
    assert a.post(path(aid,"/bind"),json={"code":second}).status_code==400
    for code in ("../alice", "0000000G", "short", "a"*100):
        assert b.post(path(bid,"/bind"),json={"code":code}).status_code==422
    with setup[1].transaction() as con:
        con.execute(update(invites).where(invites.c.owner==aid).values(expires_at=int(time.time())-1))
    assert b.post(path(bid,"/bind"),json={"code":second}).status_code==400


def test_categories_independent_revocation_filters_and_prunes_summary(setup):
    (a,b,c),(aid,bid,cid) = users(setup)
    link(a,aid,b,bid)
    assert a.put(path(aid,"/summary"),json=document()).status_code==200
    assert b.get(path(bid)).json()["familyMembers"][0]["health"]==[]
    assert a.post(path(aid,"/grant"),json={"member":bid,"categories":["health"]}).status_code==200
    # A grant alone cannot resurrect a formerly unshared summary.
    assert b.get(path(bid)).json()["familyMembers"][0]["health"]==[]
    assert a.put(path(aid,"/summary"),json=document()).status_code==200
    view=b.get(path(bid)).json()["familyMembers"][0]
    assert view["categories"]==["health"] and view["health"][0]["text"]=="TEST shareable health"
    assert view["rehab"]==view["doses"]==[]
    assert a.get(path(aid)).json()["familyMembers"][0]["categories"]==[]
    assert b.get(BASE+"/patients/"+aid+"/records").status_code==404
    assert c.get(path(cid)).json()["familyMembers"]==[]
    assert a.post(path(aid,"/grant"),json={"member":bid,"categories":[]}).status_code==200
    assert b.get(path(bid)).json()["familyMembers"][0]["health"]==[]
    with setup[1].engine.connect() as con:
        assert con.scalar(select(summaries.c.document).where(summaries.c.owner==aid))["health"]==[]


def test_unbind_removes_both_directions_and_consumed_invite_cannot_relink(setup):
    (a,b,_),(aid,bid,_) = users(setup)
    code=link(a,aid,b,bid)
    a.post(path(aid,"/grant"),json={"member":bid,"categories":["rehab","medication"]})
    assert b.post(path(bid,"/unbind"),json={"member":aid}).status_code==200
    assert a.get(path(aid)).json()["familyMembers"]==b.get(path(bid)).json()["familyMembers"]==[]
    assert b.post(path(bid,"/bind"),json={"code":code}).status_code==400
    link(a,aid,b,bid)
    assert a.get(path(aid)).json()["grants"]=={bid:[]}


@pytest.mark.parametrize("tail,method,body",[("","GET",None),("/invite","POST",{}),("/summary","PUT",document())])
def test_requires_self_patient_not_doctor_or_other_user(setup,tail,method,body):
    (a,b,_),(aid,bid,_) = users(setup)
    kwargs={} if body is None else {"json":body}
    assert b.request(method,path(aid,tail),**kwargs).status_code==404
    doctor=client(setup[0]);login(doctor,"doctor")
    assert doctor.request(method,path(aid,tail),**kwargs).status_code==404
    anon=client(setup[0]);assert anon.request(method,path(aid,tail),**kwargs).status_code==401
    if method!="GET":
        a.headers.pop("X-CSRF-Token")
        assert a.request(method,path(aid,tail),**kwargs).status_code==403


@pytest.mark.parametrize("body",[{"categories":["chat"]},{"categories":["health","health"]},{"categories":["health"],"owner":"WRONG"}])
def test_grant_rejects_unknown_or_extra_fields(setup,body):
    (a,b,_),(aid,bid,_) = users(setup)
    link(a,aid,b,bid)
    assert a.post(path(aid,"/grant"),json={"member":bid,**body}).status_code==422


def test_native_bearer_and_bounded_summary_contract(setup):
    (a,_,_),(aid,_,_) = users(setup)
    native=TestClient(setup[0],headers={"X-Ankang-Client":"native"})
    reply=native.post(BASE+"/auth/password/login",json={"username":"alice","password":"1","client_kind":"APK"}).json()
    native.headers["Authorization"]="Bearer "+reply["access_token"]
    assert native.post(path(aid,"/invite"),json={}).status_code==200
    assert a.put(path(aid,"/summary"),json=document(health=[document()["health"][0]]*11)).status_code==422
    assert a.put(path(aid,"/summary"),json={**document(),"private_chat":"secret"}).status_code==422
    assert a.post(path(aid,"/grant"),json={"member":aid,"categories":[]}).status_code==404


def test_concurrent_single_use_and_additive_v4_migration(setup):
    (a,b,c),(aid,bid,cid)=users(setup)
    code=a.post(path(aid,"/invite"),json={}).json()["code"]
    with ThreadPoolExecutor(2) as pool:
        statuses=list(pool.map(lambda pair:pair[0].post(path(pair[1],"/bind"),json={"code":code}).status_code,[(b,bid),(c,cid)]))
    assert sorted(statuses)==[200,400]
    with setup[1].transaction() as con:
        before=[dict(r) for r in con.execute(select(accounts)).mappings()]
        con.execute(update(schema).values(version=4))
    setup[1].migrate()
    with setup[1].engine.connect() as con:
        assert before==[dict(r) for r in con.execute(select(accounts)).mappings()]
        from cloud_service.database import SCHEMA_VERSION
        assert con.scalar(select(schema.c.version))==SCHEMA_VERSION
        assert len(con.execute(select(links)).all())==2
