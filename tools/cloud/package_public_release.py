"""Release an explicit source/asset allowlist, never repository environments/data."""
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parents[2]


def main():
    manifest = json.loads((ROOT / "public_web/build/web-manifest.json").read_text(encoding="utf-8"))
    files = subprocess.check_output(["git", "ls-files", "-z", "--", "cloud_service", "deploy/cloud", "mobile_rehab/static"], cwd=ROOT).decode().split("\0")
    files = [name for name in files if name]
    files += ["public_web/build/" + item["file"] for item in manifest["assets"].values()]
    files += ["public_web/build/" + name for name in ("index.html", "capture.html", "web-manifest.json")]
    for name in files:
        p = Path(name)
        if p.suffix in {".pem", ".sqlite3", ".mp4", ".apk", ".env", ".jks"} or ".runtime" in p.parts or "node_modules" in p.parts:
            raise SystemExit("Forbidden release input")
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    build = {"service": "ankang-cloud", "version": "0.1.3", "schema": 1, "git_commit": commit,
             "browser_version": manifest["version"], "browser_execution": manifest["execution_location"], "apk_unchanged": "0.3.1"}
    archive = ROOT / ".runtime/cloud-0.1.3.tar"
    with tarfile.open(archive, "w") as output:
        for name in sorted(set(files)):
            output.add(ROOT / name, arcname=name, recursive=False)
        payload = json.dumps(build, indent=2).encode()
        info = tarfile.TarInfo("BUILD.json")
        info.size = len(payload)
        output.addfile(info, io.BytesIO(payload))
    print(json.dumps({"files": len(set(files)), "bytes": archive.stat().st_size,
                      "sha256": hashlib.sha256(archive.read_bytes()).hexdigest(), "git_commit": commit}))


if __name__ == "__main__":
    main()
