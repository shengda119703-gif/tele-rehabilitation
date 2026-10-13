"""Versioned, strict data semantics. Never guess timestamp magnitude or units."""
from datetime import datetime, timezone
import hashlib
import json
import math
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

UNITS = {'steps_daily': 'count', 'steps_delta': 'count', 'heart_rate_sample': 'bpm',
         'heart_rate_summary': 'bpm', 'sleep_session': 'minute',
         'exercise_session': 'second', 'weight_sample': 'kg', 'spo2_sample': '%'}
SCOPES = {'xiaomi': {'steps_daily': '200016', 'heart_rate_sample': '200007',
                    'sleep_session': '200009', 'exercise_session': '200004',
                    'weight_sample': '200010', 'spo2_sample': '200008'},
          'huawei': {'steps_daily': 'https://www.huawei.com/healthkit/step.read'}}


class HealthError(Exception):
    def __init__(self, code, status=409):
        self.code, self.status = code, status
        super().__init__(code)


def canonical(value):
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)
    except (ValueError,TypeError,RecursionError):
        raise HealthError('PAYLOAD_SCHEMA_UNSUPPORTED',400) from None


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def opaque(value, required=True):
    # JSON numbers beyond IEEE-754 exactness must arrive as strings at native/API boundaries.
    if not isinstance(value, str) or len(value) > 1000 or (required and not value):
        raise HealthError('PAYLOAD_SCHEMA_UNSUPPORTED', 400)
    return value


def timestamp(value, unit):
    if type(value) is int:
        n = value
    elif isinstance(value, str) and value.isdecimal() and len(value) <= 24:
        n = int(value)
    else:
        raise HealthError('PAYLOAD_SCHEMA_UNSUPPORTED', 400)
    scale = {'second': 1, 'millisecond': 1000, 'nanosecond': 1000000000}.get(unit)
    if scale is None or not 0 <= n // scale <= 7258118400:
        raise HealthError('PAYLOAD_SCHEMA_UNSUPPORTED', 400)
    # Preserve source nanoseconds separately; public comparisons use exact integer ms.
    return n * 1000 // scale


def zone(name):
    try:
        return ZoneInfo(opaque(name))
    except (ZoneInfoNotFoundError, ValueError):
        raise HealthError('TIMEZONE_REQUIRED', 400) from None


def local_day(ms, name):
    return datetime.fromtimestamp(ms / 1000, timezone.utc).astimezone(zone(name)).date().isoformat()


def normalize(record):
    if not isinstance(record, dict) or not isinstance(record.get('kind'),str) or record.get('kind') not in UNITS:
        raise HealthError('PAYLOAD_SCHEMA_UNSUPPORTED', 400)
    r = dict(record)
    kind = r['kind']
    if r.get('unit') != UNITS[kind]:
        raise HealthError('UNIT_UNSUPPORTED', 400)
    for key in ('start_ms', 'end_ms', 'version'):
        if key == 'version':
            if not isinstance(r.get(key), str) or not r[key].isdecimal():
                raise HealthError('PAYLOAD_SCHEMA_UNSUPPORTED', 400)
        elif type(r.get(key)) is not int or not 0 <= r[key] <= 7258118400000:
            raise HealthError('PAYLOAD_SCHEMA_UNSUPPORTED', 400)
    if r['end_ms'] < r['start_ms']:
        raise HealthError('PAYLOAD_SCHEMA_UNSUPPORTED', 400)
    value = r.get('value')
    if value is not None:
        if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
            raise HealthError('PAYLOAD_SCHEMA_UNSUPPORTED', 400)
        if kind.startswith('steps') and (type(value) is not int or value > 1000000):
            raise HealthError('PAYLOAD_SCHEMA_UNSUPPORTED', 400)
        if kind in ('heart_rate_sample', 'spo2_sample') and not 0 < value <= (300 if kind.startswith('heart') else 100):
            raise HealthError('PAYLOAD_SCHEMA_UNSUPPORTED', 400)
    r['source_store_id'] = opaque(r.get('source_store_id'))
    r['original_data_origin'] = opaque(r.get('original_data_origin', 'unknown'))
    if r.get('source_record_id') is not None:
        r['source_record_id'] = opaque(r['source_record_id'])
    r['day'] = local_day(r['end_ms'] if kind == 'sleep_session' else r['start_ms'], r.get('timezone'))
    r['details'] = r.get('details', {})
    if not isinstance(r['details'], dict) or len(canonical(r)) > 32000:
        raise HealthError('PAYLOAD_SCHEMA_UNSUPPORTED', 400)
    r['parser_version'] = opaque(r.get('parser_version', 'normalized-1'))
    return r
