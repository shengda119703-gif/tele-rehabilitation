"""Serve the existing phone-local product; no server-side model execution."""
import json
import hashlib
from pathlib import Path

from fastapi import Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse

from .security import DomainError


def install_public_web(app, directory: Path, current_account):
    manifest_path = directory / "web-manifest.json"
    if not manifest_path.is_file():
        return False
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema") != "ankang-public-web-1":
        raise ValueError("Unknown public web bundle")
    directory = directory.resolve()
    for name in ("index.html", "capture.html"):
        if (not (directory / name).is_file()
                or hashlib.sha256((directory / name).read_bytes()).hexdigest() != manifest["pages"].get(name)):
            raise ValueError("Missing public web page")

    def fixed_file(file):
        def serve():
            return FileResponse(file)
        return serve

    # An explicit build manifest, never a catch-all pointing at the repository.
    for url, info in manifest["assets"].items():
        relative = info["file"]
        path = (directory / relative).resolve()
        if (not (url == "/catalog.json" or url.startswith(("/static/", "/local/", "/vendor/", "/models/", "/web/"))) or ".." in Path(relative).parts
                or not path.is_relative_to(directory) or not path.is_file()
                or path.suffix in {".pem", ".sqlite3", ".mp4", ".env", ".apk"}
                or "lin-profile.json" in relative or "fitness-demo.json" in relative
                or hashlib.sha256(path.read_bytes()).hexdigest() != info["sha256"]):
            raise ValueError("Invalid public asset manifest")

        app.add_api_route(url, fixed_file(path), methods=["GET"], include_in_schema=False)

    def product(request: Request):
        try:
            account = current_account(request)
        except DomainError as error:
            if error.status == 401:
                return RedirectResponse("/account?next=/", status_code=303)
            raise
        if account["role"] != "PATIENT":
            return RedirectResponse("/care", status_code=303)
        filename = "capture.html" if request.url.path == "/capture" else "index.html"
        html = (directory / filename).read_text(encoding="utf-8")
        identity = json.dumps(account, ensure_ascii=False).replace("<", "\\u003c")
        # Public identity only. Session cookie stays HttpOnly; no access/refresh token.
        html = html.replace("<head>", '<head><script id="ankang-web-identity" type="application/json">'
                            + identity + "</script>", 1)
        return HTMLResponse(html)

    app.add_api_route("/", product, methods=["GET"], include_in_schema=False)
    app.add_api_route("/capture", product, methods=["GET"], include_in_schema=False)
    return True
