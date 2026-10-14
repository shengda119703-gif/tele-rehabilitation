"""Anonymous, allowlisted APK downloads. Never exposes arbitrary server paths."""
import hashlib
from html import escape
import json
from pathlib import Path
import re

from fastapi.responses import FileResponse, HTMLResponse

from .security import DomainError


def install_downloads(app, directory: Path, website: Path):
    directory = directory.resolve()
    manifest = json.loads((directory / "android-downloads.json").read_text(encoding="utf-8"))
    if (manifest.get("schema") != "ankang-android-downloads-1" or manifest.get("support_wechat") != "AK2452409"
            or not isinstance(manifest.get("published_on"), str)
            or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", manifest["published_on"])
            or not isinstance(manifest.get("releases"), list) or not 1 <= len(manifest["releases"]) <= 10):
        raise ValueError("Invalid public APK manifest")
    releases = {}
    for item in manifest["releases"]:
        version = item.get("version", "")
        filename = item.get("file", "")
        if (not re.fullmatch(r"\d+\.\d+\.\d+", version) or filename != "ankang-" + version + ".apk"
                or version in releases or type(item.get("bytes")) is not int or item["bytes"] <= 0
                or not re.fullmatch(r"[A-Fa-f0-9]{64}", item.get("sha256", ""))
                or not isinstance(item.get("description"), str) or len(item["description"]) > 300):
            raise ValueError("Invalid public APK release")
        file = (directory / filename).resolve()
        if not file.is_relative_to(directory):
            raise ValueError("APK must remain within release directory")
        valid = file.is_file() and file.stat().st_size == item["bytes"]
        if valid:
            checksum = hashlib.sha256()
            with file.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1048576), b""):
                    checksum.update(chunk)
            valid = checksum.hexdigest() == item["sha256"].lower()
        releases[version] = {**item, "file_path": file, "available": valid,
                             "stat": file.stat() if valid else None}
    if manifest.get("default") not in releases:
        raise ValueError("Unknown default APK")
    selected = releases[manifest["default"]]

    def response_for(version):
        item = releases.get(version)
        if not item:
            raise DomainError(404, "APK_NOT_FOUND", "没有这个安装包版本")
        file = item["file_path"]
        if not item["available"] or not file.is_file():
            raise DomainError(503, "APK_UNAVAILABLE", "安装包暂不可用，请联系技术支持")
        stat = file.stat()
        if (stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns) != (item["stat"].st_size, item["stat"].st_mtime_ns, item["stat"].st_ctime_ns):
            raise DomainError(503, "APK_UNAVAILABLE", "安装包正在更新，请稍后下载")
        return FileResponse(file, filename=item["file"], media_type="application/vnd.android.package-archive",
                            headers={"X-APK-SHA256": item["sha256"].lower()}, stat_result=stat)

    @app.api_route("/download/android", methods=["GET", "HEAD"], include_in_schema=False)
    def default_apk():
        return response_for(manifest["default"])

    @app.api_route("/download/android/{version}", methods=["GET", "HEAD"], include_in_schema=False)
    def version_apk(version: str):
        return response_for(version)

    @app.get("/download/releases.json", include_in_schema=False)
    def public_releases():
        return {"schema": manifest["schema"], "default": manifest["default"],
                "support_wechat": manifest["support_wechat"], "releases": [
                    {k: v for k, v in item.items() if k not in {"file_path", "stat"}} | {"url": "/download/android/"+version}
                    for version, item in releases.items()]}

    @app.get("/download", include_in_schema=False)
    def download_page():
        html = (website / "download.html").read_text(encoding="utf-8")
        older = "".join('<li><a href="/download/android/' + escape(version) + '">Android ' + escape(version)
                + '</a><span>' + escape(item["description"]) + '</span></li>' for version, item in releases.items()
                if version != manifest["default"] and item["available"])
        values = {"VERSION": manifest["default"], "SIZE": f'{selected["bytes"]/1048576:.1f} MB',
                  "DESCRIPTION": selected["description"], "DATE": manifest["published_on"],
                  "SHA256": selected["sha256"].lower(), "WECHAT": manifest["support_wechat"]}
        for key, value in values.items():
            html = html.replace("{{"+key+"}}", escape(value))
        html = html.replace("{{OLDER_RELEASES}}", older)
        if not selected["available"]:
            html = html.replace('href="/download/android" class="download-button"',
                                'href="#support" class="download-button"')
            html = html.replace("下载 Android 安装包", "联系技术支持")
        return HTMLResponse(html)
