from __future__ import annotations

import asyncio

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

from .service import SessionService
from app.rehab_v2.sessions import SessionError
from app.rehab_v2.storage_boundary import StorageFault


def install_rehab_v2(app, database, owner, small_json, plan_resolver, *, plan_reader=None, participant_provider=None):
    service = SessionService(database, plan_resolver, plan_reader=plan_reader, participant_provider=participant_provider)
    app.state.rehab_v2 = service
    from .practice import install_formal_practice
    try:
        install_formal_practice(app, service, owner, small_json)
    except Exception:
        service.close()
        raise

    @app.exception_handler(SessionError)
    async def session_error(request, error):
        body = dict(detail=error.code)
        if isinstance(error, StorageFault):
            body['storage_fault'] = error.public
        return JSONResponse(body, status_code=error.status)

    @app.get('/api/rehab/v2/sessions')
    async def history(request: Request, limit: int = 20, before: str | None = None):
        return await asyncio.to_thread(service.history, owner(request), limit=limit, before=before)

    @app.get('/api/rehab/v2/plans/{plan_id}')
    async def plan(plan_id: str, request: Request):
        return await asyncio.to_thread(service.plan, owner(request), plan_id)

    @app.post('/api/rehab/v2/plans')
    async def save_plan(request: Request):
        uid, payload = owner(request), await small_json(request)
        return await asyncio.to_thread(service.save_plan, uid, payload)

    @app.get('/api/rehab/v2/plans')
    async def plans(request: Request, limit: int = 20):
        return await asyncio.to_thread(service.plans_list, owner(request), limit)

    @app.post('/api/rehab/v2/plans/{plan_id}/revise')
    async def revise_plan(plan_id: str, request: Request):
        uid, payload = owner(request), await small_json(request)
        return await asyncio.to_thread(service.save_plan, uid, payload, plan_id=plan_id)

    @app.post('/api/rehab/v2/plans/{plan_id}/archive')
    async def archive_plan(plan_id: str, request: Request):
        uid, payload = owner(request), await small_json(request)
        return await asyncio.to_thread(service.save_plan, uid, payload, plan_id=plan_id, archive=True)

    @app.post('/api/rehab/v2/sessions')
    async def create(request: Request):
        uid = owner(request)
        payload = await small_json(request)
        return await asyncio.to_thread(service.create, uid, payload)

    @app.post('/api/rehab/v2/timing-comparisons')
    async def timing_comparison(request: Request):
        uid, payload = owner(request), await small_json(request)
        return await asyncio.to_thread(service.compare_timing, uid, payload)

    @app.post('/api/rehab/v2/sessions/{sid}/frames')
    async def frame(sid: str, request: Request):
        uid = owner(request)
        if request.headers.get('content-type', '').split(';')[0] != 'image/jpeg':
            raise HTTPException(415, 'jpeg_camera_frame_required')
        event_id = request.headers.get('x-rehab-event-id')
        seq = request.headers.get('x-rehab-seq', '')
        if not seq.isdigit() or len(seq) > 10:
            raise HTTPException(400, 'valid_frame_seq_required')
        encoded = bytearray()
        async for chunk in request.stream():
            encoded.extend(chunk)
            if len(encoded) > 512*1024:
                raise HTTPException(413, 'frame_size_exceeded')
        return await asyncio.to_thread(service.submit_jpeg, uid, sid, event_id, int(seq), bytes(encoded))

    @app.post('/api/rehab/v2/sessions/{sid}/pause')
    async def pause(sid: str, request: Request):
        uid, payload = owner(request), await small_json(request)
        return await asyncio.to_thread(service.control, uid, sid, 'pause', payload)

    @app.post('/api/rehab/v2/sessions/{sid}/resume')
    async def resume(sid: str, request: Request):
        uid, payload = owner(request), await small_json(request)
        return await asyncio.to_thread(service.control, uid, sid, 'resume', payload)

    @app.post('/api/rehab/v2/sessions/{sid}/finish')
    async def finish(sid: str, request: Request):
        uid, payload = owner(request), await small_json(request)
        receipt = await asyncio.to_thread(service.request_finish, uid, sid, payload)
        return JSONResponse(receipt, status_code=202 if receipt['status'] == 'finishing' else 200)

    @app.get('/api/rehab/v2/sessions/{sid}')
    async def state(sid: str, request: Request):
        return await asyncio.to_thread(service.get, owner(request), sid)

    @app.get('/api/rehab/v2/sessions/{sid}/commit')
    async def commit(sid: str, request: Request):
        return await asyncio.to_thread(service.commit, owner(request), sid)

    @app.get('/api/rehab/v2/sessions/{sid}/diagnostics')
    async def diagnostics(sid: str, request: Request):
        return await asyncio.to_thread(service.diagnostics, owner(request), sid)

    @app.post('/api/rehab/v2/sessions/{sid}/feedback')
    async def feedback(sid: str, request: Request):
        uid, payload = owner(request), await small_json(request)
        return await asyncio.to_thread(service.feedback, uid, sid, payload)

    return service
