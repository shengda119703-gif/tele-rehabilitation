"""Actual local authorized RGB input comparison; public summary omits raw poses."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from tools.rehab_ml.common import file_hash,paths,read_json,write_json


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--shoulder-video',type=Path,required=True)
    parser.add_argument('--squat-video',type=Path,required=True)
    parser.add_argument('--analysis-consent',choices=['yes'],required=True)
    args=parser.parse_args()
    root=paths()['run']/('mediapipe-audit-'+uuid4().hex[:8]);root.mkdir()
    env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',TEMP=str(root),TMP=str(root),
        PYTHONPATH=os.pathsep.join([str(ROOT/'tests/rehab_backend'),str(ROOT/'rehab_codex_single_camera_v2_1'),str(ROOT)]))
    commands=[];outputs=[]
    def run(name,arguments):
        tick=time.perf_counter()
        value=subprocess.run([sys.executable,'-X','utf8','-B',*arguments],cwd=ROOT,env=env,
                             capture_output=True,text=True,encoding='utf-8',timeout=240)
        log=root/(name+'.txt');log.write_text(value.stdout+value.stderr,encoding='utf-8')
        commands.append(dict(name=name,exit_code=value.returncode,elapsed_s=time.perf_counter()-tick,
            log=str(log),log_sha256=file_hash(log),tail=(value.stdout+value.stderr)[-500:]))
        if value.returncode!=0: raise RuntimeError(name+'_did_not_complete')
        return json.loads(value.stdout.strip())['result'] if arguments[0].endswith('cli.py') else None
    try:
        run('unit',['-m','unittest','-v','test_mediapipe_video'])
        for label,video,exercise in [('shoulder',args.shoulder_video,'shoulder_abduction'),('squat',args.squat_video,'rehab_squat')]:
            base=run(label+'_yolo',['tools/rehab_ml/cli.py','extract-pose','--video',str(video),
                '--exercise',exercise,'--side','left','--analysis-consent','yes'])
            mp=run(label+'_mediapipe',['tools/rehab_ml/cli.py','extract-mediapipe-video','--video',str(video),
                '--exercise',exercise,'--side','left','--analysis-consent','yes','--output-dir',str(root/(label+'-mp'))])
            result=run(label+'_compare',['tools/rehab_ml/cli.py','compare-video-pose','--yolo-result',base['path'],
                '--mediapipe-result',mp['path'],'--output-dir',str(root/(label+'-comparison'))])
            a,b,c=read_json(base['path']),read_json(mp['path']),read_json(result['path'])
            outputs.append(dict(exercise_id=exercise,video_sha256=a['video_sha256'],
                yolo_result_sha256=file_hash(base['path']),mediapipe_result_sha256=file_hash(mp['path']),
                comparison_sha256=file_hash(result['path']),frames=c['frames'],
                yolo_observable_frames=a['observable_frames'],mediapipe_observable_frames=b['observable_frames'],
                yolo_v2_completed=a['v2_summary']['completed'],mediapipe_v2_completed=b['v2_summary']['completed'],
                yolo_timing=a['input_timing'],mediapipe_timing=b['input_timing'],mediapipe_runtime=b['runtime'],
                mediapipe_model=b['model'],mediapipe_inference_latency_ms=b['inference_latency_ms'],
                angle_disagreement=c['filtered_projected_angle_disagreement_deg'],
                parent_provenance_sha256=file_hash(Path(mp['path']).parent/'provenance.json'),
                owned_mediapipe_exit_confirmed=mp['owned_exit_confirmed']))
    except Exception as error:
        write_json(root/'verification-failure.json',dict(status='failed',error_type=type(error).__name__,
            commands=commands,completed_comparisons=outputs))
        raise
    summary=dict(run_id=root.name,commands=commands,results=outputs,passed=True,
        evidence_scope='two_authorized_private_RGB_clips_python_VIDEO_approximation_not_phone_or_accuracy',
        private_RGB_and_keypoints_published=False,independent_reference_available=False,
        clinical_accuracy=None,training_performed=False,apk_modified=False,
        implementation_sha256={p:file_hash(ROOT/p) for p in ['tools/rehab_ml/mediapipe_video.py',
            'tools/rehab_ml/pose_video_compare.py','tools/rehab_ml/verify_mediapipe_video.py',
            'tools/rehab_ml/target_domain.py','tools/rehab_ml/cli.py','tests/rehab_backend/test_mediapipe_video.py']})
    write_json(ROOT/'reports/rehab_backend/mediapipe_video_verification.json',summary)
    print(json.dumps({'run_id':root.name,'passed':True,'comparisons':len(outputs),'clinical_accuracy':None}))
    return 0


if __name__=='__main__':raise SystemExit(main())
