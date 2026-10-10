"""Independent black-box care checks over real loopback HTTP, with isolated TEST data.

Bootstrap uses the existing public profile/plan constructors; assertions use only HTTP.
No fake business responses, database inspection, camera, cloud, or live profile access.
Run with the repository's verified Python environment. Exit 1 means observed failures.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'rehab_codex_single_camera_v2_1')]
OWNER = 'TEST-blackbox-primary'


def serve(data: Path, port: int, owner: str):
    os.environ['ANKANG_PRODUCT_DISABLE_MODEL'] = '1'
    os.environ['ANKANG_VOICE_DISABLED'] = '1'
    import uvicorn
    from app.product.backend import ProductBackend
    from app.storage import Storage
    from app.settings import default_plan
    from app.training_plans import item_from_plan, new_training_plan
    from mobile_rehab.server import create_app
    from mobile_rehab.unified import SharedProduct
    data.mkdir(parents=True, exist_ok=True)
    backend = ProductBackend(data / 'desktop')
    try:
        if not (data / 'fixture-ready.json').exists():
            for who in (OWNER, 'TEST-blackbox-other'):
                profile = dict(name=who, age=65, conditions=[], medications=[], familyContact='',
                               familyPhone='', elderPhone='', communityDoctorPhone='',
                               mobility='unknown', usesCane=False, nightVision='unknown',
                               cognition='unknown', familySharing='denied')
                backend.call('profile.save', who, {'profile': profile})
            # This is a manually saved TEST plan, without synthetic clinical measurements.
            scope = dict(participant_id=OWNER, source_kind='LIVE_CAMERA', usage_context='SELF_USE')
            store = Storage(data / 'desktop' / 'home_rehab.sqlite3')
            try:
                plan = store.save_training_plan(new_training_plan(scope, 'TEST 已有训练',
                         [item_from_plan(default_plan('shoulder_abduction'))]), expected_revision=0)
            finally:
                store.close()
            (data / 'fixture-ready.json').write_text(json.dumps({'planId': plan['id']}), encoding='utf-8')
        app = create_app(data / 'phone', pair_key='test-code', shared=SharedProduct(backend, owner))
        server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=port, log_level='warning'))
        def stop_listener():
            for line in sys.stdin:
                if line.strip() == 'STOP':
                    server.should_exit = True
                    break
        threading.Thread(target=stop_listener, daemon=True).start()
        server.run()
    finally:
        backend.close()


def redacted(value):
    if isinstance(value, dict):
        return {k: ('<redacted TEST credential>' if k in ('confirmationToken', 'requestSignature')
                    else redacted(v)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [redacted(v) for v in value]
    return value


class Run:
    def __init__(self, output: Path):
        import httpx
        self.httpx = httpx
        self.output = output.resolve()
        self.output.mkdir(parents=True, exist_ok=False)
        # SQLite fixture lives outside the synchronized repository directory.
        # Output is retained in qa-output; no existing user database is reused.
        self.data = Path(tempfile.mkdtemp(prefix='ankang-care-blackbox-'))
        self.cases, self.requests, self.reproductions = [], [], []
        self.process, self.client, self.log = None, None, None
        self.completed, self.fatal_error = False, None
        self.sequence = 0
        self.started = datetime.now(timezone.utc).isoformat()

    def start(self, owner=OWNER):
        with socket.socket() as s:
            s.bind(('127.0.0.1', 0))
            self.port = s.getsockname()[1]
        self.log = (self.output / ('server-' + str(self.port) + '.log')).open('w', encoding='utf-8')
        self.process = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), '--serve',
                        '--data', str(self.data), '--port', str(self.port), '--owner', owner],
                        cwd=ROOT, stdin=subprocess.PIPE, stdout=self.log, stderr=self.log,
                        text=True, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        self.client = self.httpx.Client(base_url=f'http://127.0.0.1:{self.port}',
                                       headers={'X-Rehab-Client': 'mobile-v1'}, timeout=30)
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise RuntimeError('Test server exited; inspect its isolated log.')
            try:
                if self.client.get('/api/unified').status_code == 401:
                    return
            except self.httpx.TransportError:
                pass
            time.sleep(.15)
        raise RuntimeError('Test server did not start within 30 seconds.')

    def stop(self):
        if self.client:
            self.client.close()
            self.client = None
        if self.process and self.process.poll() is None:
            self.process.stdin.write('STOP\n')
            self.process.stdin.flush()
            self.process.wait(timeout=20)
        if self.log:
            self.log.close()
        self.process = None

    def request(self, method, path, payload=None):
        response = self.client.request(method, path, **({'json': payload} if payload is not None else {}))
        try:
            body = response.json()
        except ValueError:
            body = response.text[:1000]
        self.requests.append(dict(method=method, path=path, input=redacted(payload),
                                  status=response.status_code, output=redacted(body)))
        return response.status_code, body

    def post(self, operation, payload=None, code=200):
        status, body = self.request('POST', '/api/unified/' + operation, payload or {})
        assert status == code, f'expected HTTP {code}; actual {status}: {body}'
        return body

    def pair(self):
        assert self.request('POST', '/api/pair', {'code': 'test-code'})[0] == 200

    def snapshot(self):
        code, result = self.request('GET', '/api/unified')
        assert code == 200, result
        return result['snapshot']

    def daily(self):
        return self.snapshot()['dailyProduct']

    def case(self, title, expected, check):
        begin, first = time.monotonic(), len(self.requests)
        try:
            evidence = check()
            status = 'PASS'
        except Exception as e:
            evidence, status = f'{type(e).__name__}: {e}', 'FAIL'
        item = dict(id=f'BB-{len(self.cases)+1:03}', title=title, expected=expected,
                    status=status, evidence=redacted(evidence), request_range=[first, len(self.requests)],
                    elapsed_ms=round((time.monotonic()-begin)*1000))
        self.cases.append(item)
        print(json.dumps(item, ensure_ascii=False), flush=True)

    def prepare(self, intents=None, text=None, request_id=None):
        self.sequence += 1
        payload = {'requestId': request_id or f'TEST-blackbox-{self.sequence}'}
        payload.update({'intents': intents} if text is None else {'text': text})
        return self.post('care.prepare', payload)

    def confirm(self, workflow, **kwargs):
        payload = dict(id=workflow['id'], confirmationToken=workflow['confirmationToken'], confirmed=True)
        payload.update(kwargs)
        return self.post('care.confirm', payload)

    def dose(self, clock='08:00', med='TEST-med-A', day=None):
        return dict(kind='record_dose', medId=med, date=day or date.today().isoformat(),
                    time=clock, status='taken')

    def move(self, clock='16:00'):
        return dict(kind='reschedule_rehab', scheduleId='TEST-schedule',
                    date=date.today().isoformat(), time=clock)

    def schedule(self, clock='14:00', id='TEST-schedule'):
        return self.post('daily.schedule', dict(id=id, date=date.today().isoformat(), time=clock,
                         kind='training', name=self.plan['name'], planId=self.plan['id'],
                         revision=self.plan['revision']))

    def medicine(self, dose='按原说明'):
        record = dict(id='TEST-med-A', name='TEST 药物 A', dose=dose, purpose='', times='', status='active')
        code, body = self.request('POST', '/api/product/medication.save', {'record': record})
        assert code == 200, body

    def tests(self):
        day = date.today().isoformat()
        self.case('未配对拒绝访问', '401', lambda: require(self.request('GET', '/api/unified')[0] == 401))
        self.case('错误连接码', '401', lambda: require(self.request('POST', '/api/pair', {'code':'bad'})[0] == 401))
        self.pair()
        def csrf():
            self.client.headers.pop('X-Rehab-Client')
            try:
                require(self.request('POST', '/api/unified/care.overview', {})[0] == 403)
            finally:
                self.client.headers['X-Rehab-Client'] = 'mobile-v1'
        self.case('缺少客户端保护标记', '403', csrf)
        self.medicine()
        self.post('daily.medSchedule', dict(medId='TEST-med-A',times=['08:00','12:00','20:00'],start=day,end=''))
        code, body = self.request('POST', '/api/product/medication.save', {'record':dict(
            id='TEST-med-B',name='TEST 药物 B',dose='按原说明',purpose='',times='',status='active')})
        assert code == 200, body
        self.post('daily.medSchedule', dict(medId='TEST-med-B',times=['09:00'],start=day,end=''))
        self.plan = self.snapshot()['rehabilitation_ui']['rehab.get_training_plan']['records'][0]
        self.schedule()
        def overview():
            value = self.post('care.overview')
            require(len(value['doses']) == 4 and all(d['status']=='unrecorded' for d in value['doses']), value)
            require(not self.daily()['doses'], 'read created a dose')
            return value
        self.case('今天安排保留未记录状态', '4 次未记录，查询不写服药事实', overview)
        self.case('无评估的下一项查询', 'available=false，不伪造可执行状态',
                  lambda: require(self.post('care.next')['available'] is False))
        w = self.prepare([self.dose(), self.move()], request_id='TEST-compound')
        self.case('复合提议不写业务数据', 'awaiting_confirmation；服药为空、训练仍14:00',
                  lambda: require(w['status']=='awaiting_confirmation' and not self.daily()['doses']
                                  and self.daily()['schedules'][0]['time']=='14:00', w))
        self.case('重复 requestId 复用提议', '相同工作流 id', lambda: require(
                  self.prepare([self.dose(),self.move()],request_id='TEST-compound')['id']==w['id']))
        self.case('同 requestId 更换操作拒绝', '400', lambda: self.post('care.prepare',
                  {'requestId':'TEST-compound','intents':[self.dose('12:00')]}, code=400))
        for title, payload in [
            ('伪造确认凭据',dict(id=w['id'],confirmationToken='forged',confirmed=True)),
            ('confirmed=false',dict(id=w['id'],confirmationToken=w['confirmationToken'],confirmed=False)),
            ('确认夹带其他 owner',dict(id=w['id'],confirmationToken=w['confirmationToken'],confirmed=True,owner='other'))]:
            def rejected_confirmation(p=payload):
                before=self.daily()
                value=self.post('care.confirm',p,code=400)
                require(self.daily()==before,'rejected confirmation wrote business data')
                return value
            self.case(title, '400 且不执行', rejected_confirmation)
        self.case('跨来源确认拒绝', '400', lambda: require(self.request('POST',
                   '/api/unified/care.confirm?source=REPLAY_FILE',dict(id=w['id'],
                   confirmationToken=w['confirmationToken'],confirmed=True))[0]==400))
        self.case('查询状态不提供确认凭据', '无 confirmationToken/requestSignature', lambda: require(
                  not {'confirmationToken','requestSignature'} & self.post('care.status',{'id':w['id']}).keys()))
        def concurrent():
            payload=dict(id=w['id'],confirmationToken=w['confirmationToken'],confirmed=True)
            # Two independent HTTP connections use the same paired cookie.
            cookie = dict(self.client.cookies)
            def send(_):
                with self.httpx.Client(base_url=f'http://127.0.0.1:{self.port}',cookies=cookie,
                                      headers={'X-Rehab-Client':'mobile-v1'},timeout=30) as c:
                    response=c.post('/api/unified/care.confirm',json=payload)
                    return response.status_code,response.json()
            with ThreadPoolExecutor(max_workers=2) as pool:
                results=list(pool.map(send,range(2)))
            self.requests.append({'method':'PARALLEL POST','path':'/api/unified/care.confirm',
                                  'input':redacted(payload),'output':redacted(results)})
            require(all(code==200 and value['status']=='succeeded' for code,value in results),results)
            actual=self.daily()
            require(len(actual['doseAudit'])==1 and actual['schedules'][0]['time']=='16:00',actual)
            s=actual['schedules'][0]
            require(s['id']=='TEST-schedule' and s['planId']==self.plan['id'] and s['revision']==self.plan['revision'],s)
            return {'statuses':[v['status'] for _,v in results],'doseAudit':len(actual['doseAudit']),'schedule':s}
        self.case('并发双确认执行一次且保留原计划', '两请求成功；仅1条服药审计、原训练改16:00', concurrent)
        self.case('完成后重复确认', 'succeeded，审计仍1条', lambda: require(
                  self.confirm(w)['status']=='succeeded' and len(self.daily()['doseAudit'])==1))
        cancel = self.prepare([self.dose('12:00')])
        def cancelled():
            value=self.post('care.cancel',dict(id=cancel['id'],confirmationToken=cancel['confirmationToken'],confirmed=True))
            require(value['status']=='cancelled',value)
            return self.post('care.confirm',dict(id=cancel['id'],confirmationToken=cancel['confirmationToken'],confirmed=True),code=400)
        self.case('取消后禁止执行', 'cancelled；确认400', cancelled)
        invalid = [
            ('未支持的开药', [dict(kind='prescribe',name='TEST 药物')]),
            ('不存在的药物', [self.dose(med='missing')]),
            ('不在服药安排中的时刻', [self.dose('10:00')]),
            ('未来已服用', [self.dose(day=(date.today()+timedelta(days=1)).isoformat())]),
            ('无效日期', [self.dose(day='2026-02-30')]),
            ('无效时间', [self.dose('25:00')]),
            ('嵌套附加字段', [dict(self.dose(),dose='2倍')]),
            ('不存在的训练安排', [dict(self.move(),scheduleId='missing')]),
            ('同次服药重复', [self.dose(),self.dose()]),
            ('超出四项上限', [self.dose()]*5),
        ]
        for title,intents in invalid:
            self.sequence+=1
            def rejected_prepare(i=intents,seq=self.sequence):
                before=self.daily()
                value=self.post('care.prepare',{'requestId':f'TEST-invalid-{seq}','intents':i},code=400)
                require(self.daily()==before,'rejected proposal wrote business data')
                return value
            self.case(title, '400，无新业务写入', rejected_prepare)
        # Real business failure: insert a conflicting schedule AFTER preparation.
        self.schedule()
        partial=self.prepare([self.dose('12:00'),self.move('17:00')])
        self.schedule('17:00',id='TEST-conflict')
        def partial_check():
            value=self.confirm(partial)
            require(value['status']=='partially_succeeded' and [s['status'] for s in value['steps']]==['succeeded','failed'],value)
            require(len(self.daily()['doseAudit'])==2,self.daily())
            return value
        self.case('第二步真实业务失败', '第一步保存；第二步失败；报告部分成功', partial_check)
        def retry_partial():
            self.post('daily.unschedule',{'id':'TEST-conflict'})
            value=self.confirm(partial)
            actual=self.daily()
            require(value['status']=='succeeded' and len(actual['doseAudit'])==2
                    and actual['schedules'][0]['time']=='17:00',value)
            return {'workflow':value,'auditCount':len(actual['doseAudit'])}
        self.case('消除冲突后重试未完成项', '第二步成功；服药审计仍2条', retry_partial)
        stale=self.prepare([self.dose('20:00')])
        self.medicine('TEST 说明已修改')
        def stale_med():
            value=self.confirm(stale)
            require(value['status']=='failed' and 'TEST-med-A|'+day+'|20:00' not in self.daily()['doses'],value)
            return value
        self.case('确认前药物档案变化', 'failed，不写原提议', stale_med)
        self.medicine()
        stale=self.prepare([self.dose('20:00')])
        self.post('daily.dose',dict(medId='TEST-med-A',date=day,time='20:00',status='skipped'))
        def stale_dose():
            value=self.confirm(stale)
            require(value['status']=='failed' and self.daily()['doses']['TEST-med-A|'+day+'|20:00']['status']=='skipped',value)
            return value
        self.case('确认前服药记录变化', 'failed，不覆盖已更新的 skipped', stale_dose)
        stale=self.prepare([self.move('18:00')])
        self.schedule('15:00')
        self.case('确认前训练安排变化', 'failed，保留15:00', lambda: require(
                  self.confirm(stale)['status']=='failed' and self.daily()['schedules'][0]['time']=='15:00'))
        self.schedule('14:00')
        # Independent semantic expectations: unsupported/ambiguous meaning must clarify.
        texts = [
            ('明确服药记录','记录今天08:00的TEST 药物 A已服用',True),
            ('明确训练改期','今天14:00的训练改到今天16:00',True),
            ('明确跨日改期','今天14:00的训练改到明天16:00',True),
            ('否定已服药','记录今天08:00的TEST 药物 A没吃',False),
            ('无需改期','今天14:00的训练无需改到16:00',False),
            ('假设改期','如果今天14:00的训练改到16:00',False),
            ('父亲的安排','爸爸今天14:00的训练改到16:00',False),
            ('他人的安排','他今天14:00的训练改到16:00',False),
            ('具名第三人的安排','张三今天14:00的训练改到16:00',False),
            ('朋友的安排','我朋友今天14:00的训练改到16:00',False),
            ('引用示例','例如今天14:00的训练改到16:00',False),
            ('问句','今天14:00的训练改到16:00吗？',False),
            ('没有明确药名','记录今天08:00的药已服用',False),
            ('没有明确日期','记录08:00的TEST 药物 A已服用',False),
            ('没有明确时刻','记录今天的TEST 药物 A已服用',False),
            ('无日期午夜','今天14:00的训练改到晚上12点',False),
            ('分钟不完整','今天14:00的训练改到下午四点一刻',False),
            ('上午与16点冲突','今天14:00的训练改到上午16:00',False),
            ('中午四点含糊','今天14:00的训练改到中午四点',False),
            ('新增剂量信息','记录今天08:00的TEST 药物 A已服用两倍剂量',False),
            ('一并要求增加剂量','记录今天08:00的TEST 药物 A已服用，然后把剂量加倍',False),
            ('一并取消另一安排','今天14:00的训练改到16:00，然后取消明天的训练',False),
        ]
        for title,text,can_propose in texts:
            def semantic(t=text, allowed=can_propose):
                before=self.daily()
                value=self.prepare(text=t)
                require(self.daily()==before,'prepare wrote business facts')
                require(value['status']==('awaiting_confirmation' if allowed else 'needs_clarification'),
                        {'input':t,'status':value['status'],'steps':value['steps'],'reply':value['reply']})
                return {'input':t,'status':value['status'],'steps':value['steps']}
            self.case('语言：'+title,'明确命令可提议；其他应先澄清；均不写数据',semantic)
        for title,text in [(title,text) for title,text,allowed in texts if title in (
                '具名第三人的安排','朋友的安排','上午与16点冲突','中午四点含糊','新增剂量信息')]:
            def chat_semantic(t=text):
                before=self.daily()
                code,value=self.request('POST','/api/product/chat',{'text':t})
                require(code==200,value)
                require(self.daily()==before,'chat wrote business facts without confirmation')
                care=value['turn'].get('care')
                require(not care or care.get('workflow',{}).get('status')!='awaiting_confirmation',
                        {'input':t,'care':care,'reply':value['turn'].get('reply')})
                return {'input':t,'care':care,'reply':value['turn'].get('reply')}
            self.case('聊天语义：'+title,'澄清或走原理解路径，不产生错误的可确认提议',chat_semantic)
        # Follow each observed error through explicit confirmation in isolated TEST data.
        # These are reproductions, separate from the independent PASS/FAIL denominator.
        for text in ('张三今天14:00的训练改到16:00','今天14:00的训练改到中午四点'):
            self.schedule('14:00')
            proposed=self.prepare(text=text)
            if proposed['status']=='awaiting_confirmation':
                done=self.confirm(proposed)
                self.reproductions.append(dict(input=text,proposal=proposed,confirmation=done,
                                               actual=self.daily()['schedules']))
        self.schedule('14:00')
        text='记录今天08:00的TEST 药物 A已服用两倍剂量'
        proposed=self.prepare(text=text)
        if proposed['status']=='awaiting_confirmation':
            done=self.confirm(proposed)
            self.reproductions.append(dict(input=text,proposal=proposed,confirmation=done,
                                           actual=self.daily()['doses']['TEST-med-A|'+day+'|08:00']))
        # The explicit erroneous-dose reproduction legitimately adds one audit entry.
        expected_final_audit=len(self.daily()['doseAudit'])+1
        for title,text,expect_care in [
            ('聊天查安排','今天有什么安排？',True),
            ('聊天提议','记录今天08:00的TEST 药物 A已服用',True),
            ('单发确认','确认',False),
            ('安全路径','我胸痛，今天14:00的训练改到16:00',False),
        ]:
            def chat(t=text,want=expect_care):
                before=self.daily()
                code,value=self.request('POST','/api/product/chat',{'text':t})
                require(code==200,value)
                require(bool(value['turn'].get('care'))==want,value['turn'])
                require(self.daily()==before,'chat changed daily facts')
                return {'care':value['turn'].get('care'),'reply':value['turn'].get('reply')}
            self.case(title,'按现有入口返回；无未经确认的业务写入',chat)
        def privacy():
            marker='TEST-private-blackbox-9987'
            code,value=self.request('POST','/api/product/chat',{'text':marker+' 记录今天08:00的TEST 药物 A已服用','private':True})
            require(code==200 and value['turn'].get('care') is None,value)
            code,backup=self.request('GET','/api/product-backup')
            require(code==200 and marker not in json.dumps(backup,ensure_ascii=False),backup)
            require('confirmationToken' not in json.dumps(backup.get('careAudit',[])),backup.get('careAudit'))
            return {'privateCare':None,'markerInBackup':False,'auditTokens':False}
        self.case('不记录聊天和导出凭据边界','private 不进入 care；导出无私密标记和确认凭据',privacy)
        pending=self.prepare([self.dose('09:00',med='TEST-med-B')])
        self.stop()
        self.start('TEST-blackbox-other')
        self.pair()
        self.case('跨用户拿旧 id 查询', '400',lambda: self.post('care.status',{'id':pending['id']},code=400))
        self.case('跨用户拿旧凭据执行','400',lambda: self.post('care.confirm',dict(id=pending['id'],
                  confirmationToken=pending['confirmationToken'],confirmed=True),code=400))
        self.stop()
        self.start()
        self.pair()
        self.case('重开后待确认任务保留','原id仍待确认且未写入',lambda: require(
                  self.post('care.status',{'id':pending['id']})['status']=='awaiting_confirmation'
                  and 'TEST-med-B|'+day+'|09:00' not in self.daily()['doses']))
        def lost_reply():
            before=len(self.daily()['doseAudit'])
            payload=json.dumps(dict(id=pending['id'],confirmationToken=pending['confirmationToken'],confirmed=True)).encode()
            cookie='; '.join(k+'='+v for k,v in self.client.cookies.items())
            wire=(f'POST /api/unified/care.confirm HTTP/1.1\r\nHost: 127.0.0.1:{self.port}\r\n'
                  f'X-Rehab-Client: mobile-v1\r\nCookie: {cookie}\r\nContent-Type: application/json\r\n'
                  f'Content-Length: {len(payload)}\r\nConnection: close\r\n\r\n').encode()+payload
            with socket.create_connection(('127.0.0.1',self.port),timeout=5) as s:
                s.sendall(wire)
                s.shutdown(socket.SHUT_WR)
                # Deliberately close without receiving the real HTTP response.
            self.requests.append(dict(method='RAW POST / close without recv',path='/api/unified/care.confirm',
                                      input={'id':pending['id'],'confirmed':True}))
            deadline=time.monotonic()+10
            while time.monotonic()<deadline:
                if self.post('care.status',{'id':pending['id']})['status']=='succeeded':break
                time.sleep(.1)
            require(len(self.daily()['doseAudit'])==before+1,'no committed dose after disconnected client')
            require(self.confirm(pending)['status']=='succeeded' and len(self.daily()['doseAudit'])==before+1)
            return {'clientReadResponse':False,'auditDeltaAfterReplay':1}
        self.case('丢失真实确认响应后重试','已提交可查询，重试不重复记药',lost_reply)
        self.stop()
        self.start()
        self.pair()
        self.case('完成后重开并重试',f'succeeded，服药审计仍{expected_final_audit}条',lambda: require(
                  self.confirm(pending)['status']=='succeeded' and len(self.daily()['doseAudit'])==expected_final_audit))
        self.case('确认期限元数据','expiresAt-createdAt=15分钟；不等同实际过期测试',lambda: require(
                  (datetime.fromisoformat(pending['expiresAt'].replace('Z','+00:00'))-
                   datetime.fromisoformat(pending['createdAt'].replace('Z','+00:00'))).total_seconds()==900))

    def save(self):
        result=dict(startedAt=self.started,finishedAt=datetime.now(timezone.utc).isoformat(),
                    completed=self.completed,fatalError=self.fatal_error,
                    baseline=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
                    counts={s:sum(c['status']==s for c in self.cases) for s in ('PASS','FAIL')},
                    fixturePath=str(self.data),
                    scope='real localhost HTTP -> Python ProductBackend -> Node AgentBridge -> isolated SQLite',
                    cases=self.cases,reproductions=redacted(self.reproductions),requests=self.requests)
        (self.output/'results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        return result


def require(condition, actual=None):
    assert condition, json.dumps(redacted(actual),ensure_ascii=False) if actual is not None else 'expected condition was false'
    return actual if actual is not None else '符合预期'


def main():
    if hasattr(sys.stdout,'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    p=argparse.ArgumentParser()
    p.add_argument('--serve',action='store_true')
    p.add_argument('--data',type=Path)
    p.add_argument('--port',type=int)
    p.add_argument('--owner',default=OWNER)
    p.add_argument('--output',type=Path)
    a=p.parse_args()
    if a.serve:
        serve(a.data,a.port,a.owner)
        return 0
    output=a.output or ROOT/'qa-output'/('care-blackbox-'+datetime.now().strftime('%Y%m%d-%H%M%S'))
    run=Run(output)
    try:
        run.start()
        run.tests()
        run.completed=True
    except Exception as error:
        run.fatal_error=f'{type(error).__name__}: {error}'
        raise
    finally:
        run.stop()
        result=run.save()
        print(json.dumps({'output':str(run.output),'counts':result['counts']},ensure_ascii=False),flush=True)
    return int(result['counts']['FAIL']>0)


if __name__=='__main__':
    raise SystemExit(main())
