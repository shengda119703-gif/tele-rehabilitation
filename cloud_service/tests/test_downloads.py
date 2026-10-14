"""Download fixtures are isolated bytes, never actual patient data."""
import hashlib
import json
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from cloud_service.app import create_app
from cloud_service.config import Settings


class NoDatabase:
    def __getattr__(self, name):
        raise AssertionError("Anonymous downloads must not access the database")


@pytest.fixture
def download_bundle(tmp_path):
    manifest = json.loads((Path(__file__).parents[1]/"static/android-downloads.json").read_text(encoding="utf-8"))
    packets = {}
    for i, item in enumerate(manifest["releases"]):
        data = b"PK"+bytes([i+1])*1024
        (tmp_path/item["file"]).write_bytes(data)
        item["bytes"] = len(data)
        item["sha256"] = hashlib.sha256(data).hexdigest()
        packets[item["version"]] = data
    (tmp_path/"android-downloads.json").write_text(json.dumps(manifest), encoding="utf-8")
    return tmp_path, manifest, packets


def application(bundle):
    return create_app(Settings("sqlite://", "download-test-secret-"*3, ("http://testserver",), "test"),
                      NoDatabase(), download_assets=bundle)


def test_public_page_does_not_require_cookie_database_or_inline_scripts(download_bundle):
    directory, _, _ = download_bundle
    c = TestClient(application(directory))
    page = c.get("/download")
    assert page.status_code == 200
    assert "AK2452409" in page.text and "版本 0.4.1" in page.text and "{{" not in page.text
    assert '<a href="/download/android"' in page.text
    assert 'href="/account?next=/"' in page.text and 'href="/care"' in page.text
    assert "新版医患工作台需服务更新" in page.text
    assert "script-src 'self'" in page.headers["content-security-policy"]
    assert "unsafe-inline" not in page.headers["content-security-policy"]
    assert not page.headers.get("set-cookie")
    for resource in ("download.css", "download.js"):
        assert c.get("/cloud-static/"+resource).status_code == 200


def test_default_apk_attachment_head_range_and_compatibility_version(download_bundle):
    directory, manifest, packets = download_bundle
    c = TestClient(application(directory))
    for url, version in (("/download/android", "0.4.1"), ("/download/android/0.3.1", "0.3.1")):
        full = c.get(url)
        assert full.status_code == 200 and full.content == packets[version]
        assert full.headers["content-type"] == "application/vnd.android.package-archive"
        assert full.headers["content-disposition"] == f'attachment; filename="ankang-{version}.apk"'
        assert full.headers["x-apk-sha256"] == hashlib.sha256(packets[version]).hexdigest()
        head = c.head(url)
        assert head.status_code == 200 and head.content == b""
        assert head.headers["content-length"] == str(len(packets[version]))
        part = c.get(url, headers={"Range": "bytes=0-15"})
        assert part.status_code == 206 and part.content == packets[version][:16]
    public = c.get("/download/releases.json").json()
    assert public["default"] == "0.4.1" and public["support_wechat"] == "AK2452409"
    assert all(r["available"] for r in public["releases"])
    assert "file_path" not in str(public) and "stat" not in public["releases"][0]
    assert c.get("/download/android/9.9.9").status_code == 404
    assert c.get("/download/android?file=../../.runtime/server-key.pem").content == packets["0.4.1"]


def test_corrupt_or_missing_apk_is_not_served(download_bundle):
    directory, manifest, _ = download_bundle
    file = directory/manifest["releases"][0]["file"]
    file.write_bytes(b"damaged")
    c = TestClient(application(directory))
    assert c.get("/download/android").status_code == 503
    assert not c.get("/download/releases.json").json()["releases"][0]["available"]
    assert 'href="#support" class="download-button"' in c.get("/download").text
    file.unlink()
    assert c.get("/download/android").status_code == 503


def test_apk_changed_after_startup_is_refused(download_bundle):
    directory, manifest, _ = download_bundle
    c = TestClient(application(directory))
    file = directory/manifest["releases"][0]["file"]
    file.write_bytes(b"changed after validation")
    assert c.get("/download/android").status_code == 503


@pytest.mark.parametrize("field,value", [("file", "../../private.pem"), ("version", "../../private"), ("sha256", "bad"), ("bytes", -1)])
def test_untrusted_manifest_is_rejected(download_bundle, field, value):
    directory, manifest, _ = download_bundle
    manifest["releases"][0][field] = value
    (directory/"android-downloads.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="Invalid public APK release"):
        application(directory)
