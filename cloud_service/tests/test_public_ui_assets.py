"""Public packaging must preserve approved nested UI assets, not TEST data."""
import hashlib
import importlib.util
import json
from pathlib import Path


def test_five_module_public_resources_include_nested_visuals_and_exclude_private_files(tmp_path, monkeypatch):
    root = Path(__file__).resolve().parents[2]
    spec = importlib.util.spec_from_file_location("public_ui_builder", root / "tools/cloud/build_public_web.py")
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    source = tmp_path / "source"
    (source / "local").mkdir(parents=True)
    # Packaging test only: never execute these inputs or represent them as inference.
    for name in ("product.js", "model-policy.js"):
        (source / "local" / name).write_text("/* TEST packaging input */")
    (source / "catalog.json").write_text('{"rehab":[]}')
    (source / "lin-profile.json").write_text('{"TEST":"must not publish"}')
    monkeypatch.setattr(builder, "SOURCE", source)
    monkeypatch.setattr(builder, "OUTPUT", tmp_path / "public")
    builder.build()
    manifest = json.loads((builder.OUTPUT / "web-manifest.json").read_text(encoding='utf-8'))
    required = [
        "assets/home-v36/athlete-cutout.png",
        "assets/rehab-v51/abduction.jpg",
        "assets/rehab-v51/extension.jpg",
        "assets/rehab-v51/flexion.jpg",
        "medication-v121/my-drugs.svg",
        "medication-v121/dose-records.svg",
    ]
    for name in required:
        item = manifest["assets"]["/static/" + name]
        original = (root / "mobile_rehab/static" / name).read_bytes()
        assert (builder.OUTPUT / item["file"]).read_bytes() == original
        assert item["sha256"] == hashlib.sha256(original).hexdigest()
    assert "/lin-profile.json" not in manifest["assets"]
    assert not any(name.endswith((".md", ".sqlite3", ".env", ".pem")) for name in manifest["assets"])
    assert manifest["fixture_data_included"] is False
    for name in ("home-v36", "rehab-v51", "health-v131", "medication-v121", "family-v10"):
        assert "/static/" + name + ".js" in manifest["assets"]
    assert '/web/browser-account.js' in (builder.OUTPUT / "index.html").read_text(encoding='utf-8')
