"""Synthetic geometry and loss tests; not clinical accuracy validation."""
from types import SimpleNamespace
from mobile_rehab.posture import measure, PostureEngine


def person():
    xy = [[200., 100.] for _ in range(17)]
    for i, p in {3:(210,80), 5:(200,150), 6:(300,150), 11:(210,300), 12:(290,300),
                 13:(210,420), 15:(210,550)}.items():
        xy[i] = list(p)
    return SimpleNamespace(xy=xy, conf=[1.]*17, track_key='a', bbox=[100,50,400,580])


def frame(t, p=None):
    return SimpleNamespace(time_s=t, people=[p or person()], size=(640,640),
                           schema_id='coco17-v1', coordinate_space='raw_image_pixels')


def test_frontal_and_sagittal_independent_metrics():
    p = person()
    assert measure(p,(640,640),'frontal','left')['shoulder_level'] == 0
    assert measure(p,(640,640),'sagittal','left')['knee_angle'] == 180
    p.conf[11] = 0
    result = measure(p,(640,640),'frontal','left')
    assert result['shoulder_level'] == 0 and result['trunk_lean'] is None
    assert 'pelvic_tilt' not in result


def test_missing_and_short_windows_do_not_invent_posture():
    engine = PostureEngine('posture_front','left')
    for t in (0,.1,.2,.3,.4,.5,.6,.7,.8,.9,4,4.1,4.2):
        engine.consume(frame(t))
    assert engine.summary()['valid_metrics'] == 0


def test_report_median_and_never_switch_to_bystander():
    engine = PostureEngine('posture_front','left')
    for n in range(31):
        engine.consume(frame(n/10))
    p = person()
    p.track_key = 'other'
    p.xy[5][1] += 100
    for n in range(31,70):
        engine.consume(frame(n/10,p))
    result = engine.summary()
    assert result['valid_metrics'] == 3
    assert result['metrics'][0]['value'] == 0
    assert result['metrics'][0]['sample_count'] == 31


def test_replay_decoder_eof_and_positive_geometry(tmp_path,monkeypatch):
    import cv2
    import json
    import numpy as np
    from mobile_rehab import posture_analyzer
    from mobile_rehab.server import save
    class TestVision:
        def __init__(self,**kw):pass
        def infer(self,packet):
            pose=frame(packet.time_s)
            pose.model_manifest_id='SYNTHETIC-TEST'
            return pose
        def close(self):pass
    monkeypatch.setattr(posture_analyzer,'VisionWorker',TestVision)
    writer=cv2.VideoWriter(str(tmp_path/'video.mp4'),cv2.VideoWriter_fourcc(*'mp4v'),10.,(640,640))
    assert writer.isOpened()
    for _ in range(40):writer.write(np.zeros((640,640,3),dtype=np.uint8))
    writer.release()
    save(tmp_path/'job.json',dict(id='test',owner='test',exercise='posture_front',side='left'))
    posture_analyzer.analyze(tmp_path/'job.json')
    result=json.loads((tmp_path/'result.json').read_text(encoding='utf-8'))
    assert result['summary']['valid_metrics']==3
    assert result['summary']['metrics'][0]['value']==0
    assert result['conditions']['model_manifest_id']=='SYNTHETIC-TEST'
