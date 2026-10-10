"""Authenticated presentation adapter for the desktop's single product writer."""
import asyncio
import threading

from fastapi import HTTPException, Request
from .product import MobileProduct


class SharedProduct(MobileProduct):
    def __init__(self, backend, owner):
        self.backend, self.owner = backend, owner
        self.lock = threading.RLock()
        self.slots = threading.BoundedSemaphore(4)
        self.revoked = False

    def scope(self, source='LIVE_CAMERA'):
        return dict(participant_id=self.owner, source_kind=source, usage_context='SELF_USE')

    def call(self, uid, operation, payload=None, *, source='LIVE_CAMERA'):
        if self.revoked:
            raise HTTPException(401, '电脑已停止本次手机连接。')
        if not self.slots.acquire(blocking=False):
            raise HTTPException(429, '已有操作正在处理，请稍后刷新。')
        try:
            # The pairing binds the person; no browser field selects another owner.
            return self.backend.call(operation, self.owner, payload, self.scope(source))
        except TimeoutError as error:
            raise HTTPException(504, str(error)) from None
        except RuntimeError as error:
            raise HTTPException(400, str(error)) from None
        finally:
            self.slots.release()

    def close(self):
        self.revoked = True  # Do not close the desktop-owned worker.


DAILY_FIELDS = {
    'daily.dose': {'medId', 'date', 'time', 'status'},
    'daily.medSchedule': {'medId', 'times', 'start', 'end'},
    'daily.schedule': {'id', 'date', 'time', 'kind', 'name', 'planId', 'revision'},
    'daily.unschedule': {'id'},
    'daily.familyInvite': set(), 'daily.familyBind': {'code'},
    'daily.familyGrant': {'member', 'categories'}, 'daily.familyUnbind': {'member'},
}
CARE_FIELDS = {
    'care.overview': set(), 'care.next': set(),
    'care.prepare': {'requestId', 'intents', 'text'}, 'care.status': {'id'},
    'care.confirm': {'id', 'confirmationToken', 'confirmed'},
    'care.cancel': {'id', 'confirmationToken', 'confirmed'},
}


def install_unified(app, owner, shared, small_json):
    @app.get('/api/unified')
    async def snapshot(request: Request, source: str = 'LIVE_CAMERA'):
        uid = owner(request)
        if source not in ('LIVE_CAMERA', 'REPLAY_FILE'):
            raise HTTPException(400, '请选择电脑实时或手机录像记录。')
        data = await asyncio.to_thread(shared.call, uid, 'snapshot', source=source)
        return dict(snapshot=data, source=source, shared=True)

    @app.post('/api/unified/{operation}')
    async def operation(operation: str, request: Request, source: str = 'LIVE_CAMERA'):
        uid = owner(request)
        fields = {**DAILY_FIELDS, **CARE_FIELDS}
        if source not in ('LIVE_CAMERA', 'REPLAY_FILE') or operation not in fields:
            raise HTTPException(404, '未开放此操作。')
        payload = await small_json(request)
        if not isinstance(payload, dict) or set(payload) - fields[operation]:
            raise HTTPException(400, '操作包含不支持的字段。')
        try:
            return await asyncio.to_thread(shared.call, uid, operation, payload, source=source)
        except (KeyError, TypeError):
            raise HTTPException(400, '请检查填写的信息。') from None
