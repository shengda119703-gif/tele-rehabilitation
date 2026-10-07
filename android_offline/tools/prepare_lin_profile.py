"""Build a portable TEST fixture from its generator, never from personal files."""
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/'rehab_codex_single_camera_v2_1'), str(ROOT), str(ROOT/'tools/ui-polish')]
os.environ.update(ANKANG_PRODUCT_DISABLE_MODEL='1', ANKANG_VOICE_DISABLED='1')
from test_lin_profile import OWNER, NAME, FAMILY, SCHEMA, FixtureClock, claim_directory, seed, scope
from app.product.backend import ProductBackend

VERSION = 'android-local-projection-1'
FIXTURE = 'test-lin-apk-v1'


def identifier(value):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, FIXTURE+'/'+value))


def local_report(job):
    r, s = job['result'], job['result']['summary']
    span = s.get('motion_range') or {}
    reps = []
    for rep in r.get('repetitions', []):
        start = rep.get('start_time_s', rep.get('start',{}).get('t',0))
        turn = rep.get('turn_time_s', rep.get('turn',{}).get('t',start))
        end = rep.get('end_time_s', rep.get('end',{}).get('t',turn))
        reps.append(dict(peak=rep.get('peak_angle_deg',rep.get('turn',{}).get('angle')),
            duration=end-start, outbound=turn-start, **{'return':end-turn}, time=end,
            targetMet=rep.get('target_status')=='MET' if job['mode']=='training' else None))
    return dict(contract=VERSION, synthetic=True, fixture=SCHEMA, origin='desktop-TEST-fixture',
        validRatio=s.get('valid_ratio',1), min=span.get('min_deg'), max=span.get('max_deg'),
        baseline=span.get('min_deg'), reps=reps, duration=s.get('observed_span_s',0),
        partial=s.get('partial',0), series=[], meanDuration=s.get('mean_cycle_s'))


def generate(data, backend, manifest):
    snapshot=backend.call('snapshot',OWNER,scope=scope('REPLAY_FILE'))
    exported=backend.call('lifecycle.export',OWNER,scope=scope('REPLAY_FILE'))
    owner, member = identifier('owner/'+OWNER), identifier('owner/'+FAMILY)
    replacements={OWNER:owner,FAMILY:member}
    kv={}
    for kind in ('profiles','records'):
        for path in (data/'desktop'/'product'/kind).glob('*.json'):
            row=json.loads(path.read_text(encoding='utf-8'))
            # Desktop attachment index is not a portable KV record; originals
            # are imported through the phone's owner-scoped IndexedDB port.
            if row['key'].startswith('attachments:'):
                continue
            kv[row['key']]=row['value']
    uid=hashlib.sha256(OWNER.encode()).hexdigest()[:32]
    jobs=[]
    for folder in (data/'phone'/'jobs'/uid).iterdir():
        j=json.loads((folder/'job.json').read_text(encoding='utf-8'))
        r=json.loads((folder/'result.json').read_text(encoding='utf-8'))
        if j.get('fixture')!=SCHEMA or not j.get('synthetic') or r.get('fixture')!=SCHEMA or not r.get('synthetic'):
            raise ValueError('Only generated TEST reports may be bundled')
        replacements[j['id']]=identifier('job/'+j['id'])
        j.pop('shared_database',None)
        j.update(result=r, video_available=False, measurement_version=VERSION)
        r.update(contract=VERSION,local_report=local_report(j),source_kind='FIXTURE_IMPORT')
        jobs.append(j)
    jobs.sort(key=lambda j:j['created_at'])
    original=snapshot['rehabilitation_ui']['rehab.get_training_plan']['records'][0]
    replacements[original['id']]=identifier('plan/REPLAY_FILE')
    items=[]
    for entry in original['items']:
        evidence=next(j for j in reversed(jobs) if j['mode']=='assessment' and
            j['exercise']==entry['exercise_id'] and j['side']==entry['side'])
        key=identifier('entry/'+entry['key'])
        items.append(dict(entry,key=key,assessment_id=evidence['id']))
        for j in jobs:
            if j['mode']=='training' and j['exercise']==entry['exercise_id'] and j['side']==entry['side']:
                j.update(plan_id=original['id'],entry_key=key)
    plan=dict(original,items=items,created_at=original['created_utc'],measurement_version=VERSION,synthetic=True,fixture=SCHEMA)
    plan.pop('progress',None)
    daily=snapshot['dailyProduct']
    daily['schedules']=[s for s in daily['schedules'] if s.get('scope',{}).get('source_kind','REPLAY_FILE')=='REPLAY_FILE']
    # Daily scopes may be represented by a context string; keep one set of four.
    daily['schedules']=list({(s['date'],s['time'],s['kind'],s['name']):s for s in daily['schedules']}.values())
    for s in daily['schedules']:
        if s['kind']=='training':s.update(planId=original['id'],revision=original['revision'])
    fixture=dict(schema=FIXTURE,synthetic=True,sourceFixture=SCHEMA,anchor=manifest['createdAt'],
        members=[member],familyMembers=snapshot['familyMembers'])
    state=dict(version=2,owner=OWNER,kv=kv,jobs=jobs,plans=[plan],daily=daily,migration=None,fixture=fixture)
    def remap(value):
        if isinstance(value,dict):return {remap(k):remap(v) for k,v in value.items()}
        if isinstance(value,list):return [remap(v) for v in value]
        if isinstance(value,str):
            if value in replacements:return replacements[value]
            for old,new in sorted(replacements.items(),key=lambda p:-len(p[0])):
                if value.startswith(('profile:','health:','tasks:','audit:','notifications:','family:','healthkit-revision:','sync-consent:','sync-summary:')):
                    value=value.replace(old,new)
            return value
        return value
    state=remap(state)
    state['fixture']['primaryOwner']=owner
    attachments=remap(exported['attachments'])
    return dict(schema=FIXTURE,name=NAME,synthetic=True,data=state,attachments=attachments)


if __name__=='__main__':
    qa=ROOT/'qa-output'
    qa.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='apk-lin-seed-',dir=qa) as folder:
        data=Path(folder)
        claim_directory(data)
        clock=FixtureClock()
        backend=ProductBackend(data/'desktop',bridge_factory=lambda:clock.bridge(data))
        try:
            manifest=seed(backend,data,clock)
            payload=generate(data,backend,manifest)
        finally:backend.close()
    output=ROOT/'android_offline/build/assets/lin-profile.json'
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(payload,ensure_ascii=False,allow_nan=False),encoding='utf-8')
    print(f'TEST Lin: {len(payload["data"]["jobs"])} history, {len(payload["attachments"])} attachments; {output.stat().st_size} bytes')
