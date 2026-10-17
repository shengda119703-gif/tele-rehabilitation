"""Package only public resources from the validated phone-local build."""
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "android_offline" / "build" / "assets"
OUTPUT = ROOT / "public_web" / "build"


def build():
    if not (SOURCE / "local" / "product.js").is_file():
        raise SystemExit("Prepare the original Android assets first")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    assets = {}

    def copy(source, relative):
        target = OUTPUT / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        assets["/" + relative] = {"file": relative, "sha256": hashlib.sha256(target.read_bytes()).hexdigest()}

    for directory in ("vendor", "models"):
        for file in (SOURCE / directory).rglob("*"):
            if file.is_file():
                copy(file, file.relative_to(SOURCE).as_posix())
    for file in (ROOT / "android_offline" / "web").iterdir():
        if file.is_file() and file.name not in {"index.html", "app.js", "style.css", "ocr.js"} and file.suffix in {".js", ".css"}:
            copy(file, "local/" + file.name)
    copy(SOURCE / "local" / "product.js", "local/product.js")
    copy(SOURCE / "local" / "model-policy.js", "local/model-policy.js")
    copy(SOURCE / "catalog.json", "catalog.json")
    static = ROOT / "mobile_rehab" / "static"
    copy(static / 'assets/rehab-library-v1/catalogue.json', 'static/assets/rehab-library-v1/catalogue.json')
    for file in static.rglob("*"):
        if "rehab-candidates-v10" in file.relative_to(static).parts or file.name.startswith("rehab-image-review"):
            continue
        if file.is_file() and file.suffix in {".js", ".css", ".svg", ".png", ".jpg", ".jpeg", ".webp"}:
            copy(file, "static/" + file.relative_to(static).as_posix())
    copy(ROOT / "public_web" / "browser-account.js", "web/browser-account.js")
    adapters = ["/local/engine.js", "/local/product.js", "/local/store.js", "/web/browser-account.js",
                "/local/motion.js", "/local/lin-profile.js", "/local/practice.js", "/local/model-policy.js",
                "/local/deepseek.js", "/local/cloud.js", "/local/account.js", "/local/assessment-run.js", "/local/local-api.js"]
    scripts = "".join('<script src="' + name + '"></script>' for name in adapters)
    pages = {}
    for name, output in (("unified.html", "index.html"), ("index.html", "capture.html")):
        html = (ROOT / "mobile_rehab" / "static" / name).read_text(encoding="utf-8")
        generated = html.replace("<head>", "<head>" + scripts, 1)
        (OUTPUT / output).write_text(generated, encoding="utf-8")
        pages[output] = hashlib.sha256((OUTPUT / output).read_bytes()).hexdigest()
    version = json.loads((ROOT / "android_offline" / "package.json").read_text(encoding="utf-8"))["version"]
    manifest = {"schema": "ankang-public-web-1", "version": version, "execution_location": "BROWSER_LOCAL_CPU",
                "assets": assets, "pages": pages, "ui_source": "mobile_rehab/static", "fixture_data_included": False}
    (OUTPUT / "web-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"assets": len(assets), "pages": len(pages), "fixture_data_included": False,
                      "bytes": sum((OUTPUT / item["file"]).stat().st_size for item in assets.values())}))


if __name__ == "__main__":
    build()
