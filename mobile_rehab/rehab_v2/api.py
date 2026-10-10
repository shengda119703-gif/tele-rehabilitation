from __future__ import annotations

import asyncio

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

from .service import SessionService
from app.rehab_v2.sessions import SessionError


def install_rehab_v2(app, database, owner, small_json, plan_resolver):
    service = SessionService(database, plan_resolver)
    app.state.rehab_v2 = service

    @app.exception_handler(SessionError)
    async def session_error(request, error):
        return JSONResponse(dict(detail=error.code), status_code=error.status)

    @app.post('/api/rehab/v2/sessions')
    async def create(request: Request):
        uid = owner(request)
        payload = await small_json(request)
        return await asyncio.to_thread(service.create, uid, payload)

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
        return await asyncio.to_thread(service.finish, uid, sid, payload)

    @app.get('/api/rehab/v2/sessions/{sid}')
    async def state(sid: str, request: Request):
        return await asyncio.to_thread(service.get, owner(request), sid)

    @app.get('/api/rehab/v2/sessions/{sid}/commit')
    async def commit(sid: str, request: Request):
        return await asyncio.to_thread(service.commit, owner(request), sid)

    @app.post('/api/rehab/v2/sessions/{sid}/feedback')
    async def feedback(sid: str, request: Request):
        uid, payload = owner(request), await small_json(request)
        return await asyncio.to_thread(service.feedback, uid, sid, payload)

    return service
