"""Local, immutable rehabilitation candidates. Requested motion is never a label."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import time
import urllib.error
import urllib.request

VERSION = 'rehab-ltx2-v1'
DEFAULT_ROOT = Path('E:/ai-video-lab/datasets/rehab_synthetic_v1')
PHASES = ('ready', 'outbound', 'endpoint_or_hold', 'return', 'rest_or_other')
PROFILES = {
    'pilot01': 'One fictional adult woman with short dark hair, an average build, a plain teal short-sleeved shirt and dark trousers, in a light beige home room with a wooden floor.',
    'pilot02': 'One fictional adult man with gray short hair, a stocky build, a plain burgundy short-sleeved shirt and gray trousers, in a pale blue home room with a light floor.',
    'pilot03': 'One fictional adult woman with tied-back brown hair, a tall slim build, a plain mustard short-sleeved shirt and navy trousers, in a plain off-white room with a gray floor.',
    'pilot04': 'One fictional adult man with short black hair, a medium build, a plain green short-sleeved shirt and black trousers, in a plain warm-gray room with a wooden floor.',
}
MOTIONS = {
    'shoulder_abduction': {
        'A': 'Begin standing with both arms relaxed down. Raise only the anatomical LEFT arm sideways, toward the RIGHT side of this frontal image, to approximately shoulder height with the elbow comfortably straight. Pause briefly and lower the same arm completely back to the starting position. Remain still at the end. The other arm stays relaxed down. One complete slow raising and lowering sequence.',
        'B': 'Begin with both arms down. Very slowly raise only the anatomical LEFT arm sideways toward image RIGHT to a comfortable height near the shoulder. Slowly lower it completely to the starting position and remain still. The other arm stays down. One slow complete sequence.',
        'C': 'Begin with both arms down. Raise the anatomical LEFT arm sideways toward image RIGHT near shoulder height, hold it visibly still for about two seconds, then lower it completely and remain still. The other arm stays down.',
        'D': 'Begin with both arms down. Slowly raise only the anatomical LEFT arm sideways toward image RIGHT to a comfortable mid-height. Keep that arm raised in this intermediate position until the video ends. The other arm stays relaxed down. The arm does not return to its starting position during this clip.',
        'E': 'Stand quietly facing the camera throughout. Both arms remain relaxed down beside the body. Only natural breathing and tiny posture adjustments occur. Stay in the same position for the whole clip.',
        'F': 'Begin with both arms down. Raise the anatomical LEFT upper arm sideways toward image RIGHT while visibly bending that elbow, then lower the arm fully. Keep the other arm down. The elbow bend is clearly visible during the raising and hold.',
    },
    'elbow_flexion': {
        'A': 'Start with the left arm comfortably straight down. Keeping the upper arm beside the torso, bend the left elbow so the forearm rises toward the shoulder. Pause briefly, then lower the forearm to the comfortable starting position. One complete sequence.',
        'D': 'Start with the left arm down. Bend the left elbow halfway, keeping the upper arm beside the torso. Keep the elbow bent until the video ends, without returning.',
        'E': 'Stand quietly in side profile with both arms relaxed down, breathing naturally. Remain in this position throughout.',
    },
    'knee_extension': {
        'A': 'Sit upright on a stable plain chair, left side toward the camera, feet initially resting on the floor. Slowly extend the left knee so that foot moves forward, pause comfortably, then bend the knee and return the foot to its starting position. The thigh and torso remain stable. One complete sequence.',
        'D': 'Sit upright on a stable chair with feet initially on the floor. Partly straighten the left knee and keep the foot forward until the clip ends, without returning.',
        'E': 'Sit quietly on a stable plain chair, both feet resting on the floor and hands on the thighs. Breathe naturally and remain seated throughout.',
    },
    'sit_to_stand': {
        'A': 'Begin seated still on a stable plain chair, both feet flat on the floor. Lean forward naturally and stand up, remain fully standing briefly, then lower back onto the same chair and remain seated. Hands may extend forward for balance but do not push on a support. One complete sequence.',
        'D': 'Begin seated on a stable chair with both feet flat. Lean forward and begin rising slightly, then return to the chair without reaching a fully standing position.',
        'E': 'Sit quietly on the stable chair, both feet on the floor, hands on the thighs. Do not stand up during the clip.',
    },
}


def digest(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def canonical(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def write_new(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)


def replace_json(path: Path, value):
    """Atomically publish a mutable index; raw artifacts stay exclusive-create."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=path.name+'.', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def immutable_json(path, value):
    if path.exists():
        if json.loads(path.read_text(encoding='utf-8')) != value:
            raise ValueError('Existing immutable artifact differs: '+str(path))
    else:
        write_new(path, value)


def revision(attempt):
    if type(attempt) is not int or not 1 <= attempt <= 99:
        raise ValueError('Attempt must be between 1 and 99')
    return '' if attempt == 1 else f'_r{attempt:02d}'


def same_media_timeline(saved, actual):
    """Keep every media PTS/pixel/origin check, independent of decoder version."""
    fields=('schema_version','video_sha256','width','height','frame_count','time_basis','presentation_s','frames')
    origin=('origin','video_stream_index','stream_start_time_s','stream_start_pts','stream_time_base','discarded_packets','pixel_format','full_decode_verified')
    return (all(saved.get(k)==actual.get(k) for k in fields)
            and all(saved.get('provenance',{}).get(k)==actual.get('provenance',{}).get(k) for k in origin))


@contextmanager
def generation_lock(root):
    """One orchestrator per dataset; a dead observer can reconnect saved handles."""
    import psutil
    path=root/'manifests/generation.lock'
    current=psutil.Process()
    value={'pid':current.pid,'create_time':current.create_time()}
    if path.exists():
        previous=json.loads(path.read_text(encoding='utf-8'))
        try:
            owner=psutil.Process(previous['pid'])
            alive=abs(owner.create_time()-previous['create_time'])<.001 and owner.is_running()
        except psutil.NoSuchProcess:
            alive=False
        if alive:
            raise RuntimeError('Dataset already has a live generation observer; inspect its log')
        path.unlink()
    write_new(path,value)
    try:
        yield
    finally:
        if path.exists() and json.loads(path.read_text(encoding='utf-8'))==value:
            path.unlink()


def reconnect_queue(base, root):
    queue=api(base,'/queue')
    ids={row[1] for row in queue['queue_running']+queue['queue_pending']}
    saved={}
    for path in (root/'manifests/jobs').glob('*.json'):
        state=json.loads(path.read_text(encoding='utf-8'))
        if state.get('prompt_id') in ids:
            saved[state['prompt_id']]=state
    if ids-set(saved):
        raise RuntimeError('Generation queue contains unowned handles; inspect before starting')
    for handle in ids:
        state=saved[handle]
        execute(base,root,state['name'],state['workflow'])


def api(base, route, payload=None):
    req = urllib.request.Request(base+route, data=None if payload is None else json.dumps(payload).encode(), headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req, timeout=30) as response:
        raw = response.read()
        return json.loads(raw) if raw else {}


def workflow(key, name, seed, frames, image=None, *, end_guide=False):
    # Same pinned split-connector GGUF loader and AV sampler as the verified lab.
    nodes = {}
    def add(number, kind, **inputs):
        nodes[str(number)] = {'class_type':kind, 'inputs':inputs}
        return [str(number), 0]
    model=add(1,'LabLTXGGUFLoader',unet_name='ltx-2-19b-distilled_Q4_K_M.gguf',connector_name='ltx-2-19b-embeddings_connector_distill_bf16.safetensors')
    positive=add(3,'LabLoadConditioning',name=key)
    negative=add(4,'ConditioningZeroOut',conditioning=positive)
    add(5,'LTXVConditioning',positive=positive,negative=negative,frame_rate=30.0)
    video=add(6,'EmptyLTXVLatentVideo',width=640,height=384,length=frames,batch_size=1)
    if image:
        reference=add(21,'LoadImage',image=image)
        video=add(22,'LTXVImgToVideoInplace',vae=['16',0],image=reference,latent=video,strength=1.0,bypass=False)
    audio_vae=add(7,'VAELoader',vae_name='LTX2_audio_vae_bf16.safetensors')
    audio=add(8,'LTXVEmptyLatentAudio',frames_number=frames,frame_rate=30.0,batch_size=1,audio_vae=audio_vae)
    latent=add(9,'LTXVConcatAVLatent',video_latent=video,audio_latent=audio)
    guider=add(10,'CFGGuider',model=model,positive=['5',0],negative=['5',1],cfg=1.0)
    noise=add(11,'RandomNoise',noise_seed=seed)
    sampler=add(12,'KSamplerSelect',sampler_name='euler_ancestral')
    sigmas=add(13,'ManualSigmas',sigmas='1.0, 0.99375, 0.9875, 0.98125, 0.975, 0.909375, 0.725, 0.421875, 0.0')
    sampled=add(14,'SamplerCustomAdvanced',noise=noise,guider=guider,sampler=sampler,sigmas=sigmas,latent_image=latent)
    separated=add(15,'LTXVSeparateAVLatent',av_latent=sampled)
    cached=add(19,'LabCacheLatent',samples=separated,name=name)
    vae=add(16,'VAELoader',vae_name='LTX2_video_vae_bf16.safetensors')
    images=add(17,'VAEDecodeTiled',samples=cached,vae=vae,tile_size=512,overlap=64,temporal_size=32,temporal_overlap=8)
    add(18,'LabSaveMP4',images=images,fps=30,name=name,crop_height=0)
    if end_guide:
        from .guidance import with_first_last_reference
        return with_first_last_reference(nodes,frames=frames)
    return nodes


def execute(base, root, name, graph):
    directory=root/'manifests/jobs'
    directory.mkdir(parents=True,exist_ok=True)
    path=directory/(name+'.json')
    if path.exists():
        state=json.loads(path.read_text(encoding='utf-8'))
        if state['workflow_sha256'] != canonical(graph):
            raise ValueError('Existing job has different workflow; use a new revision/name')
        if not state.get('prompt_id'):
            raise RuntimeError('Submission outcome unknown; inspect server before resubmission')
        if state.get('status')=='success' and state.get('history',{}).get('status',{}).get('status_str')=='success':
            return state
    else:
        state={'name':name,'workflow_sha256':canonical(graph),'workflow':graph,'created_unix':time.time(),'status':'submission_pending'}
        write_new(path,state)
        result=api(base,'/prompt',{'prompt':graph,'client_id':'rehab-synthetic-v1'})
        state.update(prompt_id=result['prompt_id'],status='submitted')
        replace_json(path,state)
    while True:
        try:
            history=api(base,'/history/'+state['prompt_id'])
            if state['prompt_id'] in history:
                record=history[state['prompt_id']]
                state.update(status=record['status']['status_str'],history=record)
                state.setdefault('finished_unix',time.time())
                replace_json(path,state)
                if state['status']!='success':
                    raise RuntimeError('Comfy job failed; retained authoritative history '+str(path))
                print(json.dumps({'job':name,'status':'success','wall_seconds':round(state['finished_unix']-state['created_unix'],2)}),flush=True)
                return state
            queue=api(base,'/queue')
            ids={row[1] for row in queue['queue_running']+queue['queue_pending']}
            if state['prompt_id'] not in ids:
                raise RuntimeError('Job handle absent from both queue and history; inspect rather than restart')
            print(json.dumps({'job':name,'prompt_id':state['prompt_id'],'running_s':round(time.time()-state['created_unix'])}),flush=True)
        except (urllib.error.URLError, TimeoutError) as error:
            print(json.dumps({'job':name,'observation_retry':str(error)}),flush=True)
        time.sleep(15)


def prompt(action, scenario, profile=None):
    framing='A single continuous stationary wide shot of one adult person in a plain room. Entire body, both hands and both feet remain visible with generous room for the full arm span. Stable realistic anatomy, constant person and clothing. No cuts, no camera motion, no text, no counters, no graphics. '
    if profile:
        return framing+profile+' Seen directly from the front. Both arms are relaxed down. Stand quietly with natural breathing throughout. Plain unmarked clothes and walls.'
    camera='Directly frontal view throughout. ' if action=='shoulder_abduction' else 'A fixed view from the LEFT side throughout, face and toes pointing RIGHT. '
    return framing+camera+MOTIONS[action][scenario]


def initialize(root):
    for folder in ('references','raw','manifests','splits','annotations','pose_yolo17','pose_mediapipe33','features','runs','reports'):
        (root/folder).mkdir(parents=True,exist_ok=True)
    path=root/'manifests/dataset.json'
    if not path.exists():
        write_new(path,{'schema_version':'rehab_synthetic/v1','dataset_id':'rehab_synthetic_v1','stage':'pilot','split_freeze':None,'samples':[]})
    config=root/'manifests/generation_protocol.json'
    if not config.exists():
        write_new(config,{'version':VERSION,'phases':PHASES,'pilot_profiles':PROFILES,'motions':MOTIONS,'pilot_scenarios':['A','D','E'],'default_frames':241,'fps':30,'width':640,'height':384,'formal_freeze':'pending pilot human review','target_formal':{'source_groups':10,'train_groups':6,'val_groups':2,'test_groups':2,'qualified_samples':60},'training_labels_from_prompts':False})


def verify_models(lab, root):
    lock=lab/'models.lock.json'
    records=json.loads(lock.read_text(encoding='utf-8'))
    receipt={'lock_sha256':digest(lock),'models':[],'verified_unix':time.time()}
    for model in records:
        path=Path(model['target'])
        actual=digest(path)
        if actual!=model['sha256']:
            raise ValueError('Model hash mismatch: '+str(path))
        receipt['models'].append({'path':str(path),'sha256':actual,'size':path.stat().st_size,'mtime_ns':path.stat().st_mtime_ns})
        print(json.dumps({'verified_model':path.name}),flush=True)
    target=root/'manifests/model-verification.json'
    if target.exists():
        previous=json.loads(target.read_text(encoding='utf-8'))
        if previous['lock_sha256']!=receipt['lock_sha256'] or previous['models']!=receipt['models']:
            raise ValueError('Existing immutable model receipt differs; inspect before using a new dataset revision')
        print(json.dumps({'model_verification':'matches_existing_immutable_receipt'}),flush=True)
        return previous
    write_new(target,receipt)
    return receipt


def generate(lab, root, base, group, scenario=None, *, attempt=1, reference_attempt=1, end_guide=False):
    import av
    receipt=json.loads((root/'manifests/model-verification.json').read_text(encoding='utf-8'))
    for item in receipt['models']:
        stat=Path(item['path']).stat()
        if (stat.st_size,stat.st_mtime_ns)!=(item['size'],item['mtime_ns']):
            raise ValueError('Pinned model changed since verification')
    is_reference=scenario is None
    if is_reference and end_guide:
        raise ValueError('End guidance requires an independently screened reference image')
    prompt_version=VERSION
    suffix=revision(attempt)
    text=prompt('shoulder_abduction',scenario or 'A',PROFILES[group] if is_reference else None)
    if is_reference and attempt > 1:
        prompt_version+='-reference-wide-v2'
        text=('A stationary camera far away, about five metres from one person, in a large plain room. '
              +PROFILES[group]+' Seen directly from the front, standing quietly. '
              'Both arms hang straight down beside the body, both hands next to the thighs. '
              'The person occupies only the central sixty percent of image height. '
              'A large clear floor margin surrounds both fully visible feet and shoes, with ample empty wall above the head and on both sides. '
              'Distant full-body composition. Natural realistic anatomy, plain unmarked clothes and walls, no text or graphics. '
              'Keep both hands relaxed down beside the thighs throughout this quiet standing shot.')
    reference=None
    reference_record=None
    if not is_reference:
        reference_record=json.loads((root/'references'/(group+revision(reference_attempt)+'.json')).read_text(encoding='utf-8'))
        if reference_record.get('structural_review',{}).get('status')!='usable_as_initial_condition':
            raise ValueError('Reference requires an explicit structural screen before motion generation')
        source=Path(reference_record['image_path'])
        if digest(source)!=reference_record['image_sha256']:
            raise ValueError('Original reference image changed')
        if reference_record['video'].get('path') and digest(Path(reference_record['video']['path']))!=reference_record['video']['sha256']:
            raise ValueError('Original reference video changed')
        target=lab/'ComfyUI/input'/('rehab_ref_'+reference_record['image_sha256'][:20]+'.png')
        if not target.exists():
            shutil.copy2(source,target)
        if digest(target)!=reference_record['image_sha256']:
            raise ValueError('Reference changed')
        reference=target.name
    name=f'rehab_{group}_{scenario or "reference"}_v1'+suffix
    if end_guide:
        name+='_endguide'
    if reference_record:
        name+='_ref'+reference_record['image_sha256'][:12]
    result_path=root/'manifests'/(name+'.json')
    key='rehab_'+hashlib.sha256((prompt_version+text).encode()).hexdigest()[:24]
    seed=2026101900+list(PROFILES).index(group)*100+({'A':1,'B':2,'C':3,'D':4,'E':5,'F':6}.get(scenario,0))+(attempt-1)*10000
    graph=workflow(key,name,seed,97 if is_reference else 241,reference,end_guide=end_guide)
    if result_path.exists():
        record=json.loads(result_path.read_text(encoding='utf-8'))
        provenance=record['generation']
        if (provenance['prompt_version']!=prompt_version or provenance['prompt_sha256']!=hashlib.sha256(text.encode()).hexdigest()
                or provenance['workflow_sha256']!=canonical(graph) or provenance['model_sha256']!=receipt['models'][0]['sha256']
                or digest(Path(record['video']['path']))!=record['video']['sha256']):
            raise ValueError('Completed candidate changed; inspect or use a new revision')
        if not is_reference:
            from .video import probe_video
            actual=probe_video(record['video']['path'])
            saved=json.loads(Path(record['video']['timeline_path']).read_text(encoding='utf-8'))
            if not same_media_timeline(saved,actual) or digest(Path(record['video']['timeline_path']))!=record['video']['timeline_sha256']:
                raise ValueError('Completed candidate timeline changed')
            index=json.loads((root/'manifests/dataset.json').read_text(encoding='utf-8'))
            if [row for row in index['samples'] if row['sample_id']==name]!=[record]:
                raise ValueError('Completed candidate manifest entry changed or missing')
        elif digest(Path(record['image_path']))!=record['image_sha256']:
            raise ValueError('Completed reference image changed')
        return record
    conditioning=lab/'ComfyUI/output/conditioning'/(key+'.pt')
    if not conditioning.exists():
        api(base,'/free',{'unload_models':True,'free_memory':True})
        text_graph={'101':{'class_type':'DualCLIPLoaderGGUF','inputs':{'clip_name1':'gemma-3-12b-it-Q4_K_M.gguf','clip_name2':'ltx-2-19b-embeddings_connector_distill_bf16.safetensors','type':'ltxv'}},'102':{'class_type':'CLIPTextEncode','inputs':{'clip':['101',0],'text':text}},'103':{'class_type':'LabSaveConditioning','inputs':{'conditioning':['102',0],'name':key}}}
        execute(base,root,key,text_graph)
        api(base,'/free',{'unload_models':True,'free_memory':True})
    job=execute(base,root,name,graph)
    source=lab/'ComfyUI/output/sports'/(name+'.mp4')
    destination=root/('references' if is_reference else 'raw')/(name+'.mp4')
    if not destination.exists():
        shutil.copy2(source,destination)
    if digest(destination)!=digest(source):
        raise ValueError('Immutable video copy mismatch')
    record={
        'schema_version':'rehab_synthetic/v1','sample_id':name,
        'source_group_id':group,'reference_group_id':group,'lineage_ids':['identity:'+group],
        'split':'train','stage':'pilot','scenario':scenario,'status':'pending',
        'exercise_id':'shoulder_abduction','anatomical_side':'unknown','requested_side':'left',
        'camera':'front','support_condition':'unknown',
        'video':{'path':str(destination),'sha256':digest(destination),'width':640,'height':384,
                 'frame_count':97 if is_reference else 241},
        'generation':{
            'prompt_version':prompt_version,'prompt':text,
            'prompt_sha256':hashlib.sha256(text.encode()).hexdigest(),'seed':seed,
            'model_sha256':receipt['models'][0]['sha256'],
            'model_verification_path':str(root/'manifests/model-verification.json'),
            'workflow_sha256':canonical(graph),
            'workflow_job_path':str(root/'manifests/jobs'/(name+'.json')),
            'conditioning_key':key,'generation_wall_seconds':job['finished_unix']-job['created_unix']},
        'requested_scenario_is_not_a_label':True}
    if end_guide:
        from .guidance import guidance_contract
        record['generation']['guidance']=guidance_contract(241)
    if is_reference:
        from .video import probe_video
        actual=probe_video(destination)
        if (actual['width'],actual['height'],actual['frame_count'])!=(640,384,97):
            raise ValueError('Actual reference shape differs from requested preview')
        with av.open(str(destination)) as container:
            first=next(container.decode(video=0))
            image_path=root/'references'/(group+suffix+'.png')
            if image_path.exists():
                from PIL import Image
                import numpy as np
                if not np.array_equal(np.asarray(Image.open(image_path).convert('RGB')),first.to_ndarray(format='rgb24')):
                    raise ValueError('Existing reference pixels differ from source frame')
            else:
                first.to_image().save(image_path)
            record.update(image_path=str(image_path),image_sha256=digest(image_path),source_frame_pts=first.pts,source_frame_time_base=str(first.time_base),structural_review={'status':'pending','role':None})
        immutable_json(root/'references'/(group+suffix+'.json'),record)
    else:
        from .video import probe_video
        timeline=root/'manifests/timelines'/(name+'.json')
        probe=probe_video(destination,timeline_path=None if timeline.exists() else timeline)
        if timeline.exists():
            saved=json.loads(timeline.read_text(encoding='utf-8'))
            if not same_media_timeline(saved,probe):
                raise ValueError('Existing timeline differs from actual source decode')
        if (probe['width'],probe['height'],probe['frame_count'])!=(640,384,241):
            raise ValueError('Actual dimensions or frame count differ from requested native candidate')
        if any(abs((b-a)-1/30)>1e-6 for a,b in zip(probe['presentation_s'],probe['presentation_s'][1:])):
            raise ValueError('Actual PTS cadence differs from 30fps')
        if end_guide:
            from .guidance import validate_decoded_result
            validate_decoded_result(probe,frames=241)
        record['video'].update(width=probe['width'],height=probe['height'],frame_count=probe['frame_count'])
        record['video'].update(timeline_path=str(timeline),timeline_sha256=digest(timeline))
        record['lineage_ids'].extend(['reference:'+reference_record['image_sha256'],'reference_video:'+reference_record['video']['sha256']])
        manifest_path=root/'manifests/dataset.json'
        manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
        record.update(side='unknown',view='front')
        existing=[item for item in manifest['samples'] if item['sample_id']==name]
        if existing and existing!=[record]:
            raise ValueError('Existing manifest entry differs from candidate')
        if not existing:
            manifest['samples'].append(record)
            replace_json(manifest_path,manifest)
    write_new(result_path,record)
    print(json.dumps({'candidate':name,'video':str(destination),'human_review':'pending'}),flush=True)
    return record


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('command',choices=['init','verify-models','references','pilot','review'])
    parser.add_argument('--root',type=Path,default=DEFAULT_ROOT)
    parser.add_argument('--lab',type=Path,default=Path('E:/ai-video-lab'))
    parser.add_argument('--base',default='http://127.0.0.1:8188')
    parser.add_argument('--groups',nargs='+',choices=list(PROFILES),default=list(PROFILES))
    parser.add_argument('--attempt',type=int,default=1)
    parser.add_argument('--reference-attempt',type=int,default=1)
    parser.add_argument('--end-guide',action='store_true',help='Experimental same-reference last-frame guidance; no motion correctness guarantee')
    parser.add_argument('--scenarios',nargs='+',choices=list('ABCDEF'),default=['A','D','E'])
    parser.add_argument('--port',type=int,default=8190)
    args=parser.parse_args()
    initialize(args.root)
    if args.command=='verify-models':
        verify_models(args.lab,args.root)
    elif args.command=='review':
        from .review import serve
        serve(args.root,port=args.port)
    elif args.command in ('references','pilot'):
        with generation_lock(args.root):
            reconnect_queue(args.base,args.root)
            for group in args.groups:
                for scenario in ([None] if args.command=='references' else args.scenarios):
                    generate(args.lab,args.root,args.base,group,scenario,attempt=args.attempt,reference_attempt=args.reference_attempt,end_guide=args.end_guide)
            api(args.base,'/free',{'unload_models':True,'free_memory':True})


if __name__=='__main__':
    main()
