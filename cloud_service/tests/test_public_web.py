import hashlib
import json

from fastapi.testclient import TestClient
import pytest

from cloud_service.app import BASE, create_app
from cloud_service.config import Settings
from cloud_service.database import Database
from cloud_service.security import bootstrap_doctor


@pytest.fixture
def public_app(tmp_path):
    assets = tmp_path / "public"
    assets.mkdir()
    for name in ("index.html", "capture.html"):
        (assets / name).write_text('<html><head></head><body>existing-product</body></html>', encoding="utf-8")
    (assets / "catalog.json").write_text('{"rehab":[]}', encoding="utf-8")
    manifest = {"schema": "ankang-public-web-1", "pages": {name: hashlib.sha256((assets / name).read_bytes()).hexdigest() for name in ("index.html", "capture.html")}, "assets": {"/catalog.json": {
        "file": "catalog.json", "sha256": hashlib.sha256((assets / "catalog.json").read_bytes()).hexdigest()}}}
    (assets / "web-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    settings = Settings("sqlite:///" + str(tmp_path / "cloud.sqlite3"), "x" * 40, ("http://testserver",), "test")
    db = Database(settings.database_url)
    db.migrate()
    bootstrap_doctor(db, settings, "1")
    app = create_app(settings, db, web_assets=assets)
    yield app, assets, settings, db
    db.engine.dispose()


def test_public_product_requires_web_patient_and_never_embeds_tokens(public_app):
    c = TestClient(public_app[0], headers={"Origin": "http://testserver"}, follow_redirects=False)
    assert c.get("/").headers["location"] == "/account?next=/"
    assert c.get("/capture").status_code == 303
    assert c.get("/account").status_code == 200
    assert c.post(BASE + "/auth/register", json={"username": "alice", "password": "1"}).status_code == 201
    session = c.post(BASE + "/auth/password/login", json={"username": "alice", "password": "1"}).json()
    html = c.get("/")
    assert html.status_code == 200
    assert session["patient_id"] in html.text and "existing-product" in html.text
    assert "access_token" not in html.text and "csrf_token" not in html.text
    assert c.cookies.get("ankang-session") not in html.text
    assert "worker-src 'self' blob:" in html.headers["content-security-policy"]
    assert "wasm-unsafe-eval" in html.headers["content-security-policy"]
    assert c.get("/capture").status_code == 200
    c.headers["X-CSRF-Token"] = session["csrf_token"]
    assert c.post(BASE + "/auth/logout", json={}).is_success
    assert c.get("/").status_code == 303


def test_doctor_root_goes_to_care_and_assets_are_explicit(public_app):
    c = TestClient(public_app[0], headers={"Origin": "http://testserver"}, follow_redirects=False)
    assert c.post(BASE + "/auth/password/login", json={"username": "doctor", "password": "1"}).is_success
    assert c.get("/").headers["location"] == "/care"
    assert c.get("/catalog.json?file=../../AGENTS.md").json() == {"rehab": []}
    for path in ("/lin-profile.json", "/fitness-demo.json", "/web-manifest.json", "/.runtime/server-key.pem", "/models/other.pt"):
        assert c.get(path).status_code == 404
    capabilities = c.get(BASE + "/capabilities").json()
    assert capabilities["public_user_web"] and capabilities["browser_analysis"] == "LOCAL_CPU"
    assert not capabilities["server_models"] and not capabilities["incremental_sync"]


def test_tampered_bundle_fails_closed(public_app):
    _, assets, settings, db = public_app
    (assets / "catalog.json").write_text("changed", encoding="utf-8")
    with pytest.raises(ValueError, match="Invalid public asset"):
        create_app(settings, db, web_assets=assets)
