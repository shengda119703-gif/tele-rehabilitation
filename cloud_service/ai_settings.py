"""Doctor-owned provider configuration; secrets never enter public responses.

The credential lives outside release/static directories in a mode-0600 file,
inside a service-owned mode-0700 directory. Environment credentials remain a
fallback until an explicit saved configuration (including disable) exists.
"""
from dataclasses import replace
import json
import os
from pathlib import Path
import stat
import tempfile
import threading
import time
from urllib.request import Request, HTTPRedirectHandler, build_opener

from fastapi import Request as APIRequest
from pydantic import BaseModel, ConfigDict, Field

from .security import DomainError, audited, throttle


class SettingsInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    key: str | None = Field(default=None, max_length=256, repr=False)
    model: str | None = Field(default=None, max_length=80)
    tariff: dict | None = None


class EmptyInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class AISettings:
    def __init__(self, fallback, path=None):
        self.fallback = fallback
        self.path = Path(path) if path is not None else None
        self.lock = threading.RLock()
        self.checked = None
        self.connection = "NOT_VERIFIED"
        self.checked_config = None
        self.config()  # Fail closed on unreadable/corrupt private configuration.

    def config(self):
        with self.lock:
            if self.path is None or not self.path.exists() and not self.path.is_symlink():
                return self.fallback
            try:
                info = self.path.lstat()
                if not stat.S_ISREG(info.st_mode) or info.st_size > 4096:
                    raise ValueError()
                if os.name == "posix" and (info.st_mode & 0o077 or info.st_uid != os.geteuid()):
                    raise ValueError()
                data = json.loads(self.path.read_text(encoding="utf-8"))
                if not (data.get('version') == 1 and set(data) == {"version", "key", "model"}
                        or data.get('version') == 2 and set(data) == {"version", "key", "model", "tariff"}):
                    raise ValueError()
                self.validate_key(data["key"])
                legacy_tariff = self.fallback.tariff if data['model'] == self.fallback.model else None
                return replace(self.fallback, key=data["key"], model=data["model"], tariff=data.get('tariff', legacy_tariff))
            except (OSError, ValueError, TypeError):
                raise DomainError(503, "AI_SETTINGS_UNAVAILABLE", "智能服务配置暂时无法读取，请联系管理员") from None

    @staticmethod
    def validate_key(key):
        if not isinstance(key, str) or key and (not 16 <= len(key) <= 256 or not key.isascii() or any(c.isspace() or ord(c) < 33 or ord(c) > 126 for c in key)):
            raise DomainError(422, "AI_KEY_INVALID", "请填写完整的 API Key，不要包含空格或换行")

    def status(self):
        with self.lock:
            config = self.config()
            same = self.checked_config == (config.key, config.model)
            return {"configured": bool(config.key), "model": config.model,
                    "source": "SERVER_FILE" if self.path is not None and self.path.exists() else "ENVIRONMENT" if config.key else "DISABLED",
                    "configuration_writable": self.path is not None,
                    "provider_connection": self.connection if same else "NOT_VERIFIED",
                    "last_checked_at": self.checked if same else None,
                    "monthly_tokens": config.monthly_tokens, "monthly_calls": config.monthly_calls,
                    "max_output_tokens": config.max_output_tokens, "tariff": config.tariff}

    def save(self, value):
        if self.path is None:
            raise DomainError(503, "AI_SETTINGS_READ_ONLY", "服务器尚未启用安全配置目录，请联系技术人员")
        with self.lock:
            old = self.config()
            key = old.key if value.key is None else value.key
            self.validate_key(key)
            try:
                model = value.model or old.model
                tariff = value.tariff if 'tariff' in value.model_fields_set else old.tariff if model == old.model else None
                config = replace(old, key=key, model=model, tariff=tariff)
            except ValueError:
                raise DomainError(422, "AI_MODEL_INVALID", "请选择支持的模型") from None
            temporary = None
            try:
                folder = self.path.parent
                folder.mkdir(mode=0o700, parents=True, exist_ok=True)
                if folder.is_symlink():
                    raise OSError()
                if os.name == "posix":
                    info = folder.stat()
                    if info.st_uid != os.geteuid() or info.st_mode & 0o077:
                        raise OSError()
                fd, temporary = tempfile.mkstemp(prefix=".settings-", dir=folder)
                with os.fdopen(fd, "w", encoding="utf-8") as stream:
                    json.dump({"version": 2, "key": config.key, "model": config.model, "tariff": config.tariff}, stream)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, self.path)
                temporary = None
                if os.name == 'posix':
                    directory_fd = os.open(folder, os.O_RDONLY | os.O_DIRECTORY)
                    try:
                        os.fsync(directory_fd)
                    finally:
                        os.close(directory_fd)
                # mkstemp creates mode 0600, before any credential bytes exist.
                self.checked = self.checked_config = None
                self.connection = "NOT_VERIFIED"
            except OSError:
                raise DomainError(503, "AI_SETTINGS_UNAVAILABLE", "智能服务配置未保存，请联系技术人员检查服务器目录权限") from None
            finally:
                if temporary is not None:
                    Path(temporary).unlink(missing_ok=True)
            return self.status()

    def mark(self, config, connection):
        with self.lock:
            self.checked_config = (config.key, config.model)
            self.checked = int(time.time())
            self.connection = connection


def probe_provider(config):
    """Non-billable model-list check. Never sends patient information."""
    class NoRedirect(HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            return None
    request = Request("https://api.deepseek.com/models", headers={"Authorization": "Bearer " + config.key})
    with build_opener(NoRedirect()).open(request, timeout=12) as response:
        body = response.read(262145)
    if len(body) > 262144:
        raise ValueError("Provider response exceeds limit")
    return config.model in {item.get("id") for item in json.loads(body).get("data", []) if isinstance(item, dict)}


def install_ai_settings(app, db, caller, base, store, probe=None):
    probe = probe or probe_provider

    def doctor(request, write=False):
        with db.transaction() as connection:
            actor, _ = caller(request, connection, write=write, doctor=True)
        return actor

    @app.get(base + "/care/ai/settings")
    def get_settings(request: APIRequest):
        doctor(request)
        return store.status()

    @app.put(base + "/care/ai/settings")
    def save_settings(value: SettingsInput, request: APIRequest):
        actor = doctor(request, True)
        throttle(db, app.state.settings.secret, [("ai-settings:" + actor["id"], 20, 3600)])
        result = store.save(value)
        with db.transaction() as connection:
            audited(connection, actor["id"], "ai.settings.save", "deepseek")
        return result

    @app.post(base + "/care/ai/check")
    def check_settings(value: EmptyInput, request: APIRequest):
        actor = doctor(request, True)
        config = store.config()
        if not config.key:
            raise DomainError(503, "AI_NOT_CONFIGURED", "请先保存 API Key")
        throttle(db, app.state.settings.secret, [("ai-check:" + actor["id"], 12, 3600)])
        try:
            available = probe(config)
            store.mark(config, "MODELS_VERIFIED" if available else "FAILED")
        except Exception:
            available = False
            store.mark(config, "FAILED")
        with db.transaction() as connection:
            audited(connection, actor["id"], "ai.settings.check", "deepseek")
        return {**store.status(), "message": "密钥和模型可用；可到康复管家提问" if available else "连接未通过，请检查密钥、账户余额和模型权限后重试"}
