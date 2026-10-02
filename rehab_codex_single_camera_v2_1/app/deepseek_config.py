"""Developer-only credential storage, outside the source checkout."""
import json
import os
import tempfile
from pathlib import Path


def config_path():
    base = Path(os.environ['APPDATA']) if os.environ.get('APPDATA') else Path.home() / '.config'
    target = (base / 'tele-rehabilitation' / 'deepseek.json').resolve()
    if target.is_relative_to(Path(__file__).resolve().parents[2]):
        raise ValueError('Private configuration must be outside the checkout')
    return target


def load_key():
    try:
        value = json.loads(config_path().read_text(encoding='utf-8')).get('api_key', '')
        return value.strip() if isinstance(value, str) else ''
    except (OSError, ValueError, AttributeError):
        return ''


def save_key(key):
    key = key.strip()
    if not key or any(char.isspace() for char in key):
        raise ValueError('Invalid API key')
    target = config_path()
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary = tempfile.mkstemp(dir=target.parent, prefix='.deepseek-')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump({'api_key': key}, stream)
        os.chmod(temporary, 0o600)
        os.replace(temporary, target)
    finally:
        Path(temporary).unlink(missing_ok=True)


def clear_key():
    config_path().unlink(missing_ok=True)
