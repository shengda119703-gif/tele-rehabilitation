"""Untrusted health backup input: bounded, scope-free, private on restore."""
import base64
from datetime import datetime
import math
import re

from fastapi import HTTPException

TAGS={'fatigue','dyspnea','poorSleep','edema','dizziness','medicationMissed','pain','moodLow','fall',
      'bpHigh','spo2Low','hrHigh','hrLow','glucoseHigh','glucoseLow','chestPain','neuroChange'}


def unpack(data,validate,categories):
    def fail():raise HTTPException(400,'备份格式不正确或超出资料限额')
    def text(v,limit=200):
        if not isinstance(v,str) or len(v)>limit:fail()
        return v
    def date(v):
        text(v,50)
        try:datetime.fromisoformat(v.replace('Z','+00:00'))
        except ValueError:fail()
        return v
    def number(v):
        if type(v) not in (int,float) or not math.isfinite(v) or abs(v)>1e8:fail()
        return v
    def array(v,limit):
        if not isinstance(v,list) or len(v)>limit:fail()
        return v
    try:
        if not isinstance(data,dict) or type(data.get('version')) is not int or data['version'] not in (1,2):fail()
        snapshot=data['snapshot']
        if snapshot['profile']['dataMode']!='personal':
            raise HTTPException(400,'演示档案不能恢复为个人健康档案')
        p=snapshot['profile']['profile']
        profile=validate('profile.save',{'profile':p})['profile']
        profile.update(mobility='unknown',usesCane=False,nightVision='unknown',cognition='unknown',familySharing='denied',
                       medications=[text(m,100) for m in array(p.get('medications',[]),200)])
        meds=[validate('medication.save',{'record':r})['record'] for r in array(p.get('medicationRecords',[]),200)]
        if len({r['id'] for r in meds})!=len(meds):fail()
        if 'medicationRecords' in p:profile['medicationRecords']=meds
        events=[]
        for e in array(snapshot['state']['events'],20000):
            kind=e['type'];stamp=date(e['timestamp']);ident=text(e['id'],160)
            if not ident:fail()
            if kind=='measurement':
                m=e['measurement'];sample=validate('health.record',m)
                value=dict(id=text(m['id'],160),timestamp=date(m['timestamp']),metric=sample['metric'],value=sample['value'],
                           unit=text(m['unit'],30),source='import',visibility='private')
                payload={'measurement':value}
            elif kind=='observation':
                o=e['observation'];day=date(o['date'])
                if not re.fullmatch(r'\d{4}-\d{2}-\d{2}',day):fail()
                tags=array(o['tags'],20)
                if any(t not in TAGS for t in tags):fail()
                status=o.get('status','occurred')
                if status not in ('occurred','negated','hypothetical','uncertain','near_miss'):fail()
                payload={'observation':dict(id=text(o['id'],160),date=day,text=text(o['text'],3000),tags=tags,
                                            status=status,source='import',visibility='private')}
            elif kind=='labResult':
                r=e['labResult']
                lab=dict(id=text(r['id'],160),timestamp=date(r['timestamp']),name=text(r['name'],100),
                         value=number(r['value']),unit=text(r['unit'],30),source='import',visibility='private')
                if r.get('referenceRange'):
                    lab['referenceRange']={k:number(v) for k,v in r['referenceRange'].items() if k in ('low','high')}
                payload={'labResult':lab}
            else:fail()
            events.append(dict(id=ident,type=kind,timestamp=stamp,source='import',**payload))
        if len({e['id'] for e in events})!=len(events):fail()
        chat=[]
        for m in array(snapshot['state'].get('chat',[]),10000):
            if m.get('persisted') is False or m.get('pending'):continue
            if m['role'] not in ('elder','agent'):fail()
            chat.append(dict(id=text(m['id'],160),role=m['role'],text=text(m['text'],8000),time=text(m['time'],50),persisted=True))
        attachments=[];total=0
        for a in array(data.get('attachments',[]),50):
            if data['version']==2:
                encoded=text(a['content'],12*1024*1024)
                raw=base64.b64decode(encoded,validate=True)
            else:
                values=array(a['bytes'],8*1024*1024)
                if any(type(x) is not int or not 0<=x<=255 for x in values):fail()
                raw=bytes(values)
            total+=len(raw)
            if len(raw)>8*1024*1024 or total>64*1024*1024:fail()
            if a['category'] not in categories:fail()
            ident=text(a['id'],36)
            if not re.fullmatch('[a-f0-9-]{36}',ident):fail()
            attachment=dict(id=ident,name=text(a['name'],100),category=a['category'],date=date(a['date']),
                            fileName='资料',mediaType=text(a['mediaType'],100),visibility='private',
                            content=base64.b64encode(raw).decode('ascii'))
            if a.get('trashedAt'):attachment['trashedAt']=date(a['trashedAt'])
            attachments.append(attachment)
        if len({a['id'] for a in attachments})!=len(attachments):fail()
        return dict(profile=profile,events=events,chat=chat,attachments=attachments)
    except (KeyError,TypeError,ValueError,AttributeError):fail()
