"""Official cloud read contracts, bounded transport, strict parser and no redirects.

Contract sources/version evidence live in docs/wearables/provider_contracts.md.
"""
import base64
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import secrets
import struct
import time
from urllib.parse import urlencode, urlsplit
import httpx
from .contracts import HealthError, SCOPES, UNITS, opaque, timestamp, zone

BASES = {'xiaomi': 'https://hlthopen.io.mi.com', 'huawei': 'https://health-api.cloud.huawei.com'}
TOKEN = {'xiaomi': 'https://account.xiaomi.com/oauth2/token',
         'huawei': 'https://oauth-login.cloud.huawei.com/oauth2/v3/token'}
ALLOWED_HOSTS = {'hlthopen.io.mi.com', 'account.xiaomi.com', 'open.account.xiaomi.com',
                 'health-api.cloud.huawei.com', 'oauth-login.cloud.huawei.com'}
XIAOMI_TYPES = {'steps_daily': 'com.xiaomi.steps.total', 'heart_rate_sample': 'com.xiaomi.heart_rate.delta',
                'sleep_session': 'com.xiaomi.sleep.health', 'weight_sample': 'com.xiaomi.weight.instantaneous',
                'spo2_sample': 'com.xiaomi.spo2.instantaneous'}


def nonce(clock=None):
    minute = int((time.time() if clock is None else clock) // 60)
    return base64.urlsafe_b64encode(secrets.token_bytes(8) + struct.pack('>I', minute)).decode().rstrip('=')


class Transport:
    def __init__(self, client=None, sleeper=time.sleep):
        self.client = client or httpx.Client(timeout=httpx.Timeout(15, connect=5), follow_redirects=False, trust_env=False)
        self.owned_client = client is None
        self.sleeper = sleeper

    def close(self):
        if self.owned_client:
            self.client.close()

    def request(self, method, url, *, headers=None, params=None, data=None, body=None, retry=False):
        target = urlsplit(url)
        if target.scheme != 'https' or target.hostname not in ALLOWED_HOSTS or target.username or target.port not in (None, 443):
            raise HealthError('VENDOR_ADDRESS_INVALID', 400)
        for attempt in range(3 if retry else 1):
            deadline = time.monotonic()+20
            h = dict(headers or {})
            if target.hostname == 'hlthopen.io.mi.com':
                h['X-Client-Nonce'] = nonce()  # New per HTTP attempt, not per business job.
            try:
                with self.client.stream(method, url, headers=h, params=params, data=data, json=body) as response:
                    raw = bytearray()
                    for part in response.iter_bytes():
                        if time.monotonic()>deadline:
                            raise HealthError('NETWORK_RETRYABLE',503)
                        raw.extend(part)
                        if len(raw) > 4*1024*1024:
                            raise HealthError('PAYLOAD_TOO_LARGE', 502)
                    status = response.status_code
                    if status in (429, 500, 502, 503, 504):
                        raise HealthError('RATE_LIMITED' if status == 429 else 'NETWORK_RETRYABLE', 503)
                    if status in (401, 403):
                        raise HealthError('USER_AUTH_REQUIRED' if status == 401 else 'SCOPE_MISSING', 403)
                    if not 200 <= status < 300:
                        raise HealthError('VENDOR_HTTP_ERROR', 502)
                    # Xiaomi's explicitly documented legacy prefix is not arbitrary text stripping.
                    if target.hostname == 'account.xiaomi.com' and raw.startswith(b'&&&START&&&'):
                        raw = raw[len(b'&&&START&&&'):].lstrip()
                    try:
                        result = json.loads(raw)
                    except (ValueError, UnicodeError):
                        raise HealthError('PAYLOAD_SCHEMA_UNSUPPORTED', 502) from None
                    if not isinstance(result, dict):
                        raise HealthError('PAYLOAD_SCHEMA_UNSUPPORTED', 502)
                    if result.get('error') or result.get('errorCode') or ('code' in result and result['code'] not in (0, '0')):
                        raise HealthError('VENDOR_BUSINESS_ERROR', 502)
                    return result
            except httpx.HTTPError:
                error = HealthError('NETWORK_RETRYABLE', 503)
            except HealthError as exc:
                error = exc
            if not retry or error.code not in ('RATE_LIMITED', 'NETWORK_RETRYABLE') or attempt == 2:
                raise error from None
            self.sleeper(min(2.0, .2*2**attempt + secrets.randbelow(100)/1000))


class Provider:
    def __init__(self, config, transport):
        self.config, self.transport = config, transport
        self.name = config.provider

    def authorize_url(self, requested, state, auth_nonce):
        approved = set(self.config.approved_scopes)
        if not requested or not set(requested) <= approved or not set(requested) <= set(SCOPES[self.name].values()):
            raise HealthError('SCOPE_MISSING', 400)
        params = dict(client_id=self.config.client_id, redirect_uri=self.config.redirect_uri,
                      response_type='code', state=state, scope=' '.join(requested))
        if self.name == 'xiaomi':
            params['scope_provider'] = 'healthkit'
            base = 'https://account.xiaomi.com/oauth2/authorize'
        else:
            params.update(access_type='offline', scope='openid ' + params['scope'], nonce=auth_nonce)
            base = 'https://oauth-login.cloud.huawei.com/oauth2/v3/authorize'
        return base + '?' + urlencode(params)

    def token(self, *, code=None, refresh=None, auth_nonce=None):
        data = dict(client_id=self.config.client_id, client_secret=self.config.client_secret,
                    grant_type='refresh_token' if refresh else 'authorization_code')
        if refresh:
            data['refresh_token'] = refresh
        else:
            data.update(code=code, redirect_uri=self.config.redirect_uri)
        url = ('https://account.xiaomi.com/oauth2/refresh/token' if refresh and self.name == 'xiaomi' else TOKEN[self.name])
        result = self.transport.request('POST', url, data=data)  # Never retry a one-time code exchange.
        if (not isinstance(result.get('access_token'), str) or not result['access_token']
                or type(result.get('expires_in')) is not int or not 0 < result['expires_in'] <= 366*86400
                or not isinstance(result.get('scope'), str)):
            raise HealthError('PAYLOAD_SCHEMA_UNSUPPORTED', 502)
        granted = set(result['scope'].split())
        if self.name == 'xiaomi':
            identities = {opaque(result[k]) for k in ('openId', 'open_id') if result.get(k)}
            if len(identities) > 1 or not identities and not refresh:
                raise HealthError('IDENTITY_MISMATCH')
            identity = next(iter(identities), None)
        else:
            identity = None
            if result.get('id_token'):
                info = self.transport.request('POST', 'https://oauth-login.cloud.huawei.com/oauth2/v3/tokeninfo',
                                              data={'id_token': result['id_token']})
                if (info.get('iss') != 'https://accounts.huawei.com' or info.get('aud') != self.config.client_id
                        or type(info.get('exp')) is not int or info['exp'] <= time.time()
                        or info.get('alg') != 'RS256' or auth_nonce and info.get('nonce') != auth_nonce):
                    raise HealthError('IDENTITY_MISMATCH')
                identity = opaque(info.get('sub'))
            if not identity and not refresh:
                raise HealthError('IDENTITY_MISMATCH')
        token = dict(access_token=result['access_token'], refresh_token=result.get('refresh_token') or refresh,
                     expires_at=time.time()+result['expires_in'], scopes=sorted(granted))
        return identity, token, granted

    def headers(self, token):
        h = {'Authorization': 'Bearer ' + token, 'X-Client-ID': self.config.client_id,
             'X-Trace-Id': secrets.token_hex(12)}
        if self.name == 'huawei':
            if self.config.region != 'CN' or not self.config.api_version:
                raise HealthError('REGION_MISMATCH')
            h.update({'x-version': self.config.api_version, 'x-caller-trace-id': h.pop('X-Trace-Id')})
        return h

    def permissions(self, token, token_scopes):
        if self.name != 'xiaomi':
            return set(token_scopes)
        result = self.transport.request('GET', BASES[self.name]+'/healthkit/profile/authorize',
            headers=self.headers(token),params={'clientId':self.config.client_id},retry=True)
        if not isinstance(result.get('authInfo'),list):
            raise HealthError('PAYLOAD_SCHEMA_UNSUPPORTED',502)
        granted = set()
        for entry in result['authInfo']:
            if not isinstance(entry,dict) or entry.get('scopeType') not in ('read','write') or type(entry.get('scopeId')) not in (int,str):
                raise HealthError('PAYLOAD_SCHEMA_UNSUPPORTED',502)
            if entry['scopeType']=='read':
                granted.add(str(entry['scopeId']))
        return granted & set(token_scopes)

    def pages(self, kind, start, end, token):
        if kind not in SCOPES[self.name] or not start < end or end-start > 7*86400000:
            raise HealthError('VENDOR_CONTRACT_REQUIRED')
        tz = zone(self.config.timezone)
        first = datetime.fromtimestamp(start/1000, timezone.utc).astimezone(tz)
        last = datetime.fromtimestamp((end-1)/1000, timezone.utc).astimezone(tz)
        if self.name == 'huawei':
            # Only verified CN daily steps contract; x-version is operator-supplied approved value.
            offset = first.strftime('%z')
            if first.strftime('%z') != last.strftime('%z'):
                raise HealthError('TIMEZONE_WINDOW_SPLIT_REQUIRED')
            payload = self.transport.request('POST', BASES[self.name]+'/healthkit/v2/sampleSet:dailyPolymerize',
                headers=self.headers(token), body=dict(dataTypes=['com.huawei.continuous.steps.delta'],
                    startDay=first.strftime('%Y%m%d'), endDay=last.strftime('%Y%m%d'), timeZone=offset), retry=True)
            yield parse_huawei_steps(payload, self.config.timezone), None
            return
        if kind == 'steps_daily':
            endpoint = '/healthkit/aggregate/dailies'
            params = dict(startDay=first.strftime('%Y%m%d'), endDay=last.strftime('%Y%m%d'),
                          dataTypes=XIAOMI_TYPES[kind], zoneName=self.config.timezone)
        else:
            endpoint = ('/healthkit/sportRecords/all' if kind == 'exercise_session' else
                        '/healthkit/healthRecords' if kind == 'sleep_session' else '/healthkit/dataSources/dataPoints')
            params = dict(startTime=str(start), endTime=str(end-1))
            if kind != 'exercise_session':
                params['dataTypeName'] = XIAOMI_TYPES[kind]
        seen = set()
        for page in range(100):
            payload = self.transport.request('GET', BASES[self.name]+endpoint,
                headers=self.headers(token), params=params, retry=True)
            cursor = payload.get('cursor')
            # Official cloud JSON may encode long cursor as a number: Python keeps it exact.
            if type(cursor) is int:
                cursor = str(cursor)
            if cursor is not None:
                opaque(cursor, required=False)
            more = payload.get('hasMore', bool(cursor))
            if type(more) is not bool or more and (not cursor or cursor in seen):
                raise HealthError('CURSOR_INVALID', 502)
            yield parse_xiaomi(payload, kind, self.config.timezone), cursor if more else None
            if not more:
                return
            seen.add(cursor)
            params['cursor'] = cursor
        raise HealthError('PAGE_LIMIT_EXCEEDED', 502)

    def revoke(self, token):
        if self.name == 'xiaomi':
            result = self.transport.request('POST', 'https://open.account.xiaomi.com/user/unbindOAuth2Grained',
                data={'client_id': self.config.client_id, 'client_secret': self.config.client_secret, 'access_token': token})
            return result.get('code') == 0
        result = self.transport.request('POST', 'https://oauth-login.cloud.huawei.com/oauth2/v3/revoke', data={'token': token})
        return result == {}


def fields(point):
    values = point.get('value')
    if not isinstance(values, list):
        raise HealthError('PAYLOAD_SCHEMA_UNSUPPORTED', 502)
    out = {}
    for f in values:
        if not isinstance(f, dict) or not isinstance(f.get('fieldName'), str) or f['fieldName'] in out:
            raise HealthError('PAYLOAD_SCHEMA_UNSUPPORTED', 502)
        populated = [f[k] for k in ('integerValue', 'longValue', 'floatValue', 'stringValue') if k in f]
        if len(populated) != 1:
            raise HealthError('PAYLOAD_SCHEMA_UNSUPPORTED', 502)
        out[f['fieldName']] = populated[0]
    return out


def grouped(payload, sets, points):
    if not isinstance(payload.get('group'), list):
        raise HealthError('PAYLOAD_SCHEMA_UNSUPPORTED', 502)
    result = []
    for group in payload['group']:
        if not isinstance(group, dict) or not isinstance(group.get(sets), list):
            raise HealthError('PAYLOAD_SCHEMA_UNSUPPORTED', 502)
        for data in group[sets]:
            if not isinstance(data, dict) or not isinstance(data.get(points), list):
                raise HealthError('PAYLOAD_SCHEMA_UNSUPPORTED', 502)
            for point in data[points]:
                if not isinstance(point, dict):
                    raise HealthError('PAYLOAD_SCHEMA_UNSUPPORTED', 502)
                result.append((point, data))
    return result


def base_record(point, kind, timezone_name, store, origin, time_unit, parser):
    if not isinstance(point, dict):
        raise HealthError('PAYLOAD_SCHEMA_UNSUPPORTED', 502)
    return dict(kind=kind, unit=UNITS[kind], start_ms=timestamp(point.get('startTime'), time_unit),
        end_ms=timestamp(point.get('endTime'), time_unit), timezone=point.get('zoneName') or timezone_name,
        source_store_id=str(store or 'vendor-fused'), source_record_id=None,
        original_data_origin=str(origin or 'vendor-fused'),
        version=str(timestamp(point['modifyTime'], time_unit)) if 'modifyTime' in point else '0',
        parser_version=parser, details={'source_time_unit': time_unit,
            'original_start': str(point['startTime']), 'original_end': str(point['endTime']),
            'timezone_origin': 'vendor' if point.get('zoneName') else 'connection_declared'})


def parse_xiaomi(payload, kind, timezone_name):
    if kind in ('sleep_session', 'exercise_session'):
        key = 'healthRecords' if kind == 'sleep_session' else 'sportRecords'
        if not isinstance(payload.get(key), list):
            raise HealthError('PAYLOAD_SCHEMA_UNSUPPORTED', 502)
        points = [(p, {}) for p in payload[key]]
    else:
        points = grouped(payload, 'dataSet', 'dataPoints')
    result = []
    for p, data in points:
        if kind != 'exercise_session' and p.get('dataTypeName') != XIAOMI_TYPES[kind]:
            raise HealthError('PAYLOAD_SCHEMA_UNSUPPORTED', 502)
        r = base_record(p, kind, timezone_name, data.get('sourceId') or p.get('originDataSourceId'),
                        p.get('originDataSourceId'), 'millisecond', 'xiaomi-cloud-2026-10-13-1')
        if kind == 'exercise_session':
            r['value'] = p.get('sportTime')  # Effective seconds, never fill from elapsed time.
            r['source_record_id'] = str(p['sportId']) if p.get('sportId') else None
            r['details']['activity'] = p.get('sportKey', 'unknown')
        else:
            f = fields(p)
            key = {'steps_daily': 'steps', 'heart_rate_sample': 'bpm', 'sleep_session': 'all_sleep_duration',
                   'weight_sample': 'weight', 'spo2_sample': 'spo2'}[kind]
            if key not in f:
                raise HealthError('PAYLOAD_SCHEMA_UNSUPPORTED', 502)
            r['value'] = f[key]
            if kind == 'sleep_session':
                r['start_ms'] = timestamp(f.get('bedtime'), 'millisecond')
                r['end_ms'] = timestamp(f.get('wakeup_time'), 'millisecond')
                r['details'].update({k:v for k,v in f.items() if k.startswith('sleep_') or k == 'awake_count'})
                r['details']['sleep_day_rule'] = 'wake-local-date-1'
        result.append(r)
    return result


def parse_huawei_steps(payload, timezone_name):
    result = []
    for p, data in grouped(payload, 'sampleSet', 'samplePoints'):
        if p.get('dataTypeName') != 'com.huawei.continuous.steps.total':
            raise HealthError('PAYLOAD_SCHEMA_UNSUPPORTED', 502)
        r = base_record(p, 'steps_daily', timezone_name, data.get('dataCollectorId'),
                        p.get('originalDataCollectorId'), 'nanosecond', 'huawei-cn-daily-2026-09-07-1')
        f = fields(p)
        if 'steps' not in f:
            raise HealthError('PAYLOAD_SCHEMA_UNSUPPORTED', 502)
        r['value'] = f['steps']
        result.append(r)
    return result


def verify_xiaomi_notification(secret, event, signature):
    if not isinstance(event, dict):
        raise HealthError('NOTIFICATION_SIGNATURE_INVALID', 403)
    try:
        # Only these fields are signed. Never trust metaData as a fact, URL, range or owner.
        message = '_'.join(str(event[k]) for k in ('openId', 'eventType', 'subType', 'eventTime'))
        supplied = opaque(signature)
        wanted = hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(wanted, supplied):
            raise ValueError()
        opaque(event['openId'])
        if len(message)>4000:
            raise ValueError()
        return digest_event(message)
    except (KeyError, ValueError, HealthError):
        raise HealthError('NOTIFICATION_SIGNATURE_INVALID', 403) from None


def digest_event(message):
    return hashlib.sha256(message.encode()).hexdigest()
