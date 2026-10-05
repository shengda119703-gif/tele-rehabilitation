"""Authenticated phone adapter, reusing the partner's Ankang domain service."""
import asyncio
import base64
import json
import math
import re
import threading
from pathlib import Path
from urllib.parse import quote

from fastapi import HTTPException, Request
from fastapi.responses import Response
from bridges.ankang.client import AgentBridge
from .core import ROOT

METRICS = [('steps','活动步数','步'),('walkSpeed','步行速度','m/s'),('sleepHours','睡眠时长','小时'),
           ('nightWakes','夜间醒来','次'),('restingHr','静息心率','bpm'),('weight','体重','kg'),
           ('spo2','血氧','%'),('systolic','收缩压','mmHg'),('diastolic','舒张压','mmHg'),('bloodGlucose','血糖','mmol/L')]
ALLOWED = {'profile.save','health.record','chat','medication.save','medication.status','task.status',
           'notification.plan','notification.ack'}
CATEGORIES = ['体检报告','就诊记录','检验检查','影像资料','病历资料','其他资料']


class MobileProduct:
    def __init__(self, root):
        self.root = Path(root)
        self.lock = threading.RLock()
        self.bridge = None

    def call(self, uid, operation, payload=None):
        with self.lock:
            if not self.bridge:
                try:
                    self.bridge = AgentBridge(data_dir=self.root, timeout=45,
                        script=ROOT/'mobile_rehab/product_host.cjs', env={'TZ':'Asia/Shanghai'})
                except (RuntimeError, OSError):
                    raise HTTPException(503, '健康服务尚未准备，请在电脑运行“准备手机健康服务.cmd”') from None
            try:
                return self.bridge.product(operation, uid, payload)
            except TimeoutError:
                self.close()
                raise HTTPException(504, '健康服务响应超时，请重试') from None
            except (RuntimeError, BrokenPipeError) as e:
                if self.bridge._process.poll() is not None:
                    self.close()
                    raise HTTPException(503, '健康服务已停止，请重试') from None
                if '请先建立当前用户健康档案' in str(e):
                    raise HTTPException(409, '请先完善健康档案') from None
                if 'Attachment not found' in str(e):
                    raise HTTPException(404,'找不到资料，可能已移入回收站') from None
                if '当前已有健康档案' in str(e):
                    raise HTTPException(409,'当前已有健康档案，不能覆盖恢复') from None
                raise HTTPException(400, str(e)) from None

    def close(self):
        with self.lock:
            if self.bridge:
                self.bridge.close()
                self.bridge = None

    def edit_profile(self, uid, data):
        with self.lock:
            try:
                old = self.call(uid, 'snapshot')['profile']['profile']
            except HTTPException as e:
                if e.status_code != 409:
                    raise
                old = dict(medications=[], mobility='unknown', usesCane=False,
                           nightVision='unknown', cognition='unknown', familySharing='denied')
            return self.call(uid, 'profile.save', {'profile':{**old, **data['profile']}})

    def save_archive(self, uid, data):
        with self.lock:
            current = self.call(uid, 'snapshot')
            attachments = current.get('attachments', [])+self.call(uid,'archive.trash.list')
            if len(attachments) >= 50 or sum(x.get('size', 0) for x in attachments)+len(data['bytes']) > 64*1024*1024:
                raise HTTPException(507, '当前档案资料空间已满')
            return self.call(uid, 'archive.save', data)


def validate(operation, value):
    if operation not in ALLOWED:
        raise HTTPException(404, '未开放此操作')
    if not isinstance(value, dict):
        raise HTTPException(400, '请求格式不正确')
    def text(key, length=200, required=False, source=value):
        v = source.get(key, '')
        if not isinstance(v, str) or len(v)>length or (required and not v.strip()):
            raise HTTPException(400, '请核对填写内容')
        return v.strip()
    if operation == 'profile.save':
        p = value.get('profile')
        if not isinstance(p,dict): raise HTTPException(400,'请填写健康档案')
        age=p.get('age')
        if type(age) is not int or not 0<=age<=130: raise HTTPException(400,'请填写实际年龄')
        conditions=p.get('conditions',[])
        if not isinstance(conditions,list) or len(conditions)>20 or any(not isinstance(x,str) or len(x)>100 for x in conditions):
            raise HTTPException(400,'健康情况过长')
        # Never allow profile editing to replace medication/consent through hidden fields.
        return {'profile':dict(name=text('name',40,True,p),age=age,conditions=conditions,
            familyContact=text('familyContact',40,source=p),familyPhone=text('familyPhone',30,source=p),
            communityDoctorPhone=text('communityDoctorPhone',30,source=p),elderPhone=text('elderPhone',30,source=p))}
    if operation == 'health.record':
        metric=value.get('metric');n=value.get('value')
        if metric not in {m[0] for m in METRICS} or type(n) not in (int,float) or not math.isfinite(n) or not 0<=n<=100000:
            raise HTTPException(400,'请核对指标和数值')
        return dict(metric=metric,value=n,visibility='private')
    if operation == 'chat':
        message = text('text',1900,True)
        return dict(text=('不要记录：' if value.get('private') is True else '')+message)
    if operation == 'medication.save':
        r=value.get('record')
        if not isinstance(r,dict): raise HTTPException(400,'请填写药物信息')
        if r.get('status','active') not in ('active','stopped'): raise HTTPException(400,'药物状态无效')
        return {'record':dict(id=text('id',100,True,r),name=text('name',100,True,r),dose=text('dose',100,source=r),
                              purpose=text('purpose',200,source=r),times=text('times',100,source=r),status=r.get('status','active'))}
    if operation == 'medication.status':
        if value.get('status') not in ('active','stopped'): raise HTTPException(400,'药物状态无效')
        return dict(id=text('id',100,True),status=value['status'])
    if operation == 'task.status':
        if value.get('status') not in ('pending','in_progress','completed','dismissed'): raise HTTPException(400,'任务状态无效')
        return dict(id=text('id',160,True),status=value['status'])
    if operation == 'notification.ack': return dict(id=text('id',160,True))
    return {}


def install_product(app, data_dir, owner, small_json, backend=None):
    product = backend or MobileProduct(data_dir/'ankang')
    app.state.product = product

    @app.get('/api/product')
    async def snapshot(request: Request):
        uid=owner(request)
        try:
            data=await asyncio.to_thread(product.call,uid,'snapshot')
        except HTTPException as e:
            if e.status_code==409: return dict(needs_profile=True,metrics=METRICS,categories=CATEGORIES)
            raise
        return dict(needs_profile=False,snapshot=data,metrics=METRICS,categories=CATEGORIES,assistant='local',
                    external_model=False)

    @app.post('/api/product/{operation}')
    async def operation(operation: str, request: Request):
        uid=owner(request)
        raw=bytearray()
        async for chunk in request.stream():
            raw.extend(chunk)
            if len(raw)>16384:raise HTTPException(413,'请求内容过长')
        try:value=json.loads(raw)
        except (ValueError,UnicodeError,RecursionError):raise HTTPException(400,'请求格式不正确') from None
        data=validate(operation,value)
        if operation == 'profile.save':
            return await asyncio.to_thread(product.edit_profile, uid, data)
        return await asyncio.to_thread(product.call,uid,operation,data)

    @app.get('/api/product-backup')
    async def backup(request: Request):
        data=await asyncio.to_thread(product.call,owner(request),'lifecycle.export')
        data['version']=2
        data['kind']='mobile-health-backup'
        for attachment in data['attachments']:
            attachment['content']=base64.b64encode(bytes(attachment.pop('bytes'))).decode('ascii')
        return Response(json.dumps(data,ensure_ascii=False),media_type='application/json',
                        headers={'Content-Disposition':'attachment; filename="health-backup.json"'})

    @app.post('/api/product-restore')
    async def restore(request: Request):
        uid=owner(request)
        if request.query_params.get('confirm')!='yes':raise HTTPException(400,'请确认恢复本人健康备份')
        try:
            await asyncio.to_thread(product.call,uid,'snapshot')
        except HTTPException as e:
            if e.status_code!=409:raise
        else:raise HTTPException(409,'当前已有健康档案，不能覆盖恢复；请使用已配对的新浏览器')
        raw=bytearray()
        async for chunk in request.stream():
            raw.extend(chunk)
            if len(raw)>100*1024*1024:raise HTTPException(413,'备份文件最多 100 MB')
        try:data=json.loads(raw)
        except (ValueError,UnicodeError,RecursionError):raise HTTPException(400,'请选择导出的 JSON 健康备份') from None
        from .backup import unpack
        payload=await asyncio.to_thread(unpack,data,validate,CATEGORIES)
        return await asyncio.to_thread(product.call,uid,'mobile.restore',payload)

    @app.post('/api/product-archive')
    async def archive(request: Request):
        uid=owner(request)
        # A separate binary route avoids JSON byte arrays in the browser and large JSON requests.
        if request.query_params.get('consent')!='yes': raise HTTPException(400,'请确认保存本次资料')
        category=request.query_params.get('category','其他资料')
        name=request.query_params.get('name','')
        if category not in CATEGORIES or not 1<=len(name.strip())<=100: raise HTTPException(400,'请填写资料名称与分类')
        media=request.headers.get('content-type','').split(';')[0]
        if media not in ('application/pdf','image/jpeg','image/png','video/mp4','text/plain'):
            raise HTTPException(400,'支持 PDF、JPG、PNG、MP4 或文本资料')
        raw=bytearray()
        async for chunk in request.stream():
            raw.extend(chunk)
            if len(raw)>8*1024*1024: raise HTTPException(413,'资料最多 8 MB')
        if not raw: raise HTTPException(400,'资料为空')
        return await asyncio.to_thread(product.save_archive,uid,dict(name=name.strip(),category=category,
            fileName='资料',mediaType=media,bytes=list(raw),visibility='private'))

    @app.post('/api/product-share')
    async def share(request: Request):
        uid = owner(request)
        data = await small_json(request)
        if data.get('consent') is not True:
            raise HTTPException(400, '请确认分享健康指标、在用药物和评估训练摘要')
        from .care import body_summary
        snapshot = await asyncio.to_thread(product.call, uid, 'snapshot')
        payload = body_summary(app.state.jobs, uid)
        # Purpose-limited snapshot: no chat, conditions, contacts, archives, audits or owner ID.
        latest = {}
        for row in sorted(snapshot['state']['healthData']['measurements'], key=lambda x:x['timestamp'], reverse=True):
            latest.setdefault(row['metric'], {k:row[k] for k in ('metric','value','unit','timestamp')})
        payload['health'] = dict(measurements=list(latest.values()), medications=[
            {k:r.get(k,'') for k in ('name','dose','times')} for r in
            snapshot['profile']['profile'].get('medicationRecords', []) if r['status']=='active'])
        return app.state.care.issue(uid, 'share', 7*86400, payload)

    @app.get('/api/product-archive/{ident}')
    async def read_archive(ident: str, request: Request):
        if not re.fullmatch('[a-f0-9-]{36}',ident): raise HTTPException(404,'找不到资料')
        result=await asyncio.to_thread(product.call,owner(request),'archive.read',dict(id=ident))
        extension={'application/pdf':'.pdf','image/jpeg':'.jpg','image/png':'.png','video/mp4':'.mp4','text/plain':'.txt'}.get(result['mediaType'],'.bin')
        name='health-'+re.sub(r'[\x00-\x1f\\/:*?"<>|]','_',result['name'])[:80]+extension
        # Download only: uploaded content is never interpreted as executable same-origin HTML.
        return Response(bytes(result['bytes']),media_type='application/octet-stream',
                        headers={'Content-Disposition':f'attachment; filename="health-document{extension}"; filename*=UTF-8\'\'{quote(name,safe="")}'})

    @app.get('/api/product-trash')
    async def trash(request: Request):
        return await asyncio.to_thread(product.call,owner(request),'archive.trash.list')

    @app.post('/api/product-archive/{ident}/{action}')
    async def archive_action(ident: str, action: str, request: Request):
        uid=owner(request)
        if not re.fullmatch('[a-f0-9-]{36}',ident) or action not in ('trash','restore'):
            raise HTTPException(404,'找不到资料操作')
        data=await small_json(request)
        if data.get('confirm') is not True:
            raise HTTPException(400,'请确认本次资料操作')
        return await asyncio.to_thread(product.call,uid,'archive.'+action,dict(id=ident))

    @app.get('/api/product-rehab')
    async def rehab_context(request: Request):
        uid=owner(request)
        from .care import body_summary
        data=body_summary(app.state.jobs,uid)
        # Exact records only; never suggest an unverified normal ROM or diagnosis.
        return dict(latest=data['latest'][:12],total=data['total'],training_count=data['training_count'],
                    next_step=data['next_step'],source='current-mobile-profile')
