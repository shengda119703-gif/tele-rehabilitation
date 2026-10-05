"""Bounded sharing-lock retries for atomic local JSON on Windows."""
import json
from pathlib import Path
import time
from uuid import uuid4


def write_json(path, data):
    path = Path(path)
    temp = path.with_name(path.name + '.' + uuid4().hex + '.tmp')
    try:
        temp.write_text(json.dumps(data, ensure_ascii=False, allow_nan=False), encoding='utf-8')
        for attempt in range(5):
            try:
                temp.replace(path)
                return
            except PermissionError:
                if attempt == 4:
                    raise
                time.sleep(.02)
    finally:
        temp.unlink(missing_ok=True)


def read_json(path, *, optional=False):
    for attempt in range(5):
        try:
            return Path(path).read_text(encoding='utf-8')
        except FileNotFoundError:
            if optional:
                return None
            raise
        except PermissionError:
            if attempt == 4:
                if optional:
                    return None
                raise
            time.sleep(.02)
