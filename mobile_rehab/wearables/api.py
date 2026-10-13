"""Uses original authenticated owner closure. No owner/patient IDs from JSON are trusted."""
import asyncio
import json
from fastapi import Request
from fastapi.responses import JSONResponse
from .contracts import HealthError, UNITS
from .service import WearableService


def install_wearables(app, data_dir, owner):
    failure = None
    try:
        service = WearableService(data_dir/'wearables')
    except (HealthError, OSError) as exc:
        service, failure = None, exc.code if isinstance(exc, HealthError) else 'STORAGE_UNAVAILABLE'
    app.state.wearables = service

    @app.exception_handler(HealthError)
    async def health_error(request, exc):
        return JSONResponse(dict(code=exc.code, rehab_can_continue=True), status_code=exc.status)

    def available():
        if service is None:
            raise HealthError(failure or 'PROVIDER_UNAVAILABLE', 503)
        return service

    async def payload(request):
        raw = bytearray()
        async for part in request.stream():
            raw.extend(part)
            if len(raw)>1024*1024:
                raise HealthError('PAYLOAD_TOO_LARGE', 413)
        try:
            data = json.loads(raw)
        except (ValueError, UnicodeError, RecursionError):
            raise HealthError('PAYLOAD_SCHEMA_UNSUPPORTED', 400) from None
        if not isinstance(data, dict) or any(k in data for k in ('owner_user_id', 'owner', 'patient_id', 'participant_id')):
            raise HealthError('OWNER_OVERRIDE_FORBIDDEN', 400)
        return data

    def window(request):
        try:
            start, end = int(request.query_params.get('start_ms','0')), int(request.query_params.get('end_ms','7258118400000'))
        except ValueError:
            raise HealthError('TIME_WINDOW_INVALID', 400) from None
        if not 0 <= start < end <= 7258118400000:
            raise HealthError('TIME_WINDOW_INVALID', 400)
        return start, end

    @app.get('/api/health/capabilities')
    async def capabilities(request: Request):
        owner(request)
        return available().capabilities()

    @app.post('/api/health/oauth/{provider}/start')
    async def start(provider: str, request: Request):
        uid = owner(request)
        data = await payload(request)
        return await asyncio.to_thread(available().start, uid, provider, data.get('metrics'),
                                       data.get('connection_id'), data.get('reimport', False))

    @app.get('/api/health/oauth/{provider}/callback')
    async def callback(provider: str, request: Request):
        uid = owner(request)
        return await asyncio.to_thread(available().callback, uid, provider,
            request.query_params.get('state'), request.query_params.get('code'), 'error' in request.query_params)

    @app.get('/api/health/oauth-attempts/{aid}')
    async def attempt(aid: str, request: Request):
        return await asyncio.to_thread(available().store.attempt, owner(request), aid)

    @app.get('/api/health/connections')
    async def connections(request: Request):
        return await asyncio.to_thread(available().store.connections, owner(request))

    @app.post('/api/health/connections/{cid}/sync')
    async def sync(cid: str, request: Request):
        uid = owner(request)
        await payload(request)
        return await asyncio.to_thread(available().sync, uid, cid)

    @app.get('/api/health/sync-jobs/{jid}')
    async def job(jid: str, request: Request):
        data = await asyncio.to_thread(available().store.job, owner(request), jid)
        return {k:v for k,v in data.items() if k not in ('owner', 'worker_holder', 'lease_until')}

    @app.post('/api/health/connections/{cid}/upload-lease')
    async def lease(cid: str, request: Request):
        uid = owner(request)
        data = await payload(request)
        return await asyncio.to_thread(available().store.lease, uid, cid, data.get('installation_id'))

    @app.delete('/api/health/upload-leases/{lid}')
    async def stop_lease(lid: str, request: Request):
        await asyncio.to_thread(available().store.stop_lease, owner(request), lid)
        return dict(stopped=True, cloud_connection_revoked=False, rehab_can_continue=True)

    @app.post('/api/health/import-batches')
    async def batch(request: Request):
        uid = owner(request)
        data = await payload(request)
        connection = available().store.connection(uid,data.get('connection_id'),data.get('generation'))
        provider = available().provider(connection['provider'])
        from .contracts import SCOPES
        if not isinstance(data.get('events'),list):
            raise HealthError('PAYLOAD_SCHEMA_UNSUPPORTED',400)
        for event in data['events']:
            if not isinstance(event,dict) or not isinstance(event.get('record'),dict):
                raise HealthError('PAYLOAD_SCHEMA_UNSUPPORTED',400)
            kind = event['record'].get('kind')
            if not isinstance(kind, str):
                raise HealthError('PAYLOAD_SCHEMA_UNSUPPORTED', 400)
            kind = {'steps_delta':'steps_daily','heart_rate_summary':'heart_rate_sample'}.get(kind,kind)
            if SCOPES[connection['provider']].get(kind) not in provider.config.approved_scopes:
                raise HealthError('APPROVAL_PENDING',403)
        return await asyncio.to_thread(available().store.import_batch, uid, data.get('connection_id'),
            data.get('generation'), data.get('batch_id'), data.get('lease_id'), data.get('lease_token'), data.get('events'))

    @app.get('/api/health/import-batches/{bid}')
    async def receipt(bid: str, request: Request):
        return await asyncio.to_thread(available().store.receipt, owner(request), bid)

    @app.delete('/api/health/connections/{cid}')
    async def revoke(cid: str, request: Request):
        uid = owner(request)
        delete = request.query_params.get('delete_imported_copy') == 'yes'
        return await asyncio.to_thread(available().revoke, uid, cid, delete)

    @app.get('/api/health/summary')
    async def summary(request: Request):
        uid = owner(request)
        return await asyncio.to_thread(available().store.summary, uid, *window(request))

    @app.get('/api/health/records')
    async def records(request: Request):
        uid = owner(request)
        kind = request.query_params.get('kind')
        if kind is not None and kind not in UNITS:
            raise HealthError('PAYLOAD_SCHEMA_UNSUPPORTED', 400)
        rows = await asyncio.to_thread(available().store.records, uid, *window(request), kind)
        # Bounded output with a stable offset. Detailed server pagination remains a later enhancement.
        try:
            offset = int(request.query_params.get('offset', '0'))
        except ValueError:
            raise HealthError('PAYLOAD_SCHEMA_UNSUPPORTED', 400) from None
        if not 0 <= offset <= 1000000:
            raise HealthError('PAYLOAD_SCHEMA_UNSUPPORTED', 400)
        return dict(records=rows[offset:offset+500], next_offset=offset+500 if len(rows)>offset+500 else None)

    @app.get('/api/health/training-context')
    async def training_context(request: Request):
        uid = owner(request)
        start, end = window(request)
        if end-start > 7*86400000:
            raise HealthError('TIME_WINDOW_INVALID', 400)
        return await asyncio.to_thread(available().training_context, uid, start, end)

    @app.post('/callbacks/xiaomi/healthkit/notifications')
    async def notification(request: Request):
        event = await payload(request)
        return await asyncio.to_thread(available().notify_xiaomi, event, request.headers.get('x-notification-signature'))

    @app.post('/callbacks/huawei/healthkit/notifications')
    async def unsupported_huawei_notification(request: Request):
        # No guessed signature / insecure 204 connectivity success.
        raise HealthError('VENDOR_NOTIFICATION_CONTRACT_REQUIRED', 503)
