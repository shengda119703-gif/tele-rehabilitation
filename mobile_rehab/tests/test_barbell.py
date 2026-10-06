"""Synthetic physics and target video tests, not accuracy evidence for human lifts."""
import copy
import json
import math

import cv2
import numpy as np
import pytest

from mobile_rehab.barbell import BarTracker, analyze_track, demo_report, validate_calibration


def calibration(mass=40.):
    return dict(size=[640, 480], reference_a=[.1,.1], reference_b=[.1,.6],
                target=[.5,.65], length_m=.48, mass_kg=mass, confirmed=True)


@pytest.mark.parametrize('field,value', [('mass_kg',-1), ('mass_kg',float('nan')),
    ('length_m',0), ('length_m',float('inf')), ('confirmed',False), ('target',[2,0]),
    ('size',[0,1080]), ('reference_b',[.1,.11])])
def test_invalid_calibration(field,value):
    c=calibration();c[field]=value
    with pytest.raises(ValueError):
        validate_calibration(c)


def test_quadratic_motion_recovers_velocity_acceleration_force_power():
    c=calibration()
    # One metre/s² constant upward acceleration, with 2 mm / pixel.
    samples=[dict(t=i/60,x=320.,y=400-.5*(i/60)**2/.002) for i in range(90)]
    r=analyze_track(samples,c)
    row=r['series'][40]
    assert row['velocity_m_s']==pytest.approx(40/60,abs=.002)
    assert row['acceleration_m_s2']==pytest.approx(1.,abs=.01)
    assert row['force_n']==pytest.approx(40*10.80665,abs=.5)
    assert row['power_w']==pytest.approx(40*10.80665*40/60,abs=.5)
    assert r['series'][0]['force_n'] is None
    assert r['summary']['bounded_segments']==0  # cropped moving edges cannot claim complete lift


def test_no_mass_keeps_speed_but_no_force_or_power():
    c=calibration(None)
    samples=[dict(t=i/60,x=320.,y=350-i) for i in range(90)]
    r=analyze_track(samples,c)
    assert r['series'][30]['velocity_m_s']==pytest.approx(.12,abs=.001)
    assert all(s['force_n'] is None and s['power_w'] is None for s in r['series'])


def test_stationary_missing_and_low_fps_do_not_fabricate_lifts():
    stationary=[dict(t=i/30,x=320.,y=300.) for i in range(60)]
    result=analyze_track(stationary,calibration())
    assert result['summary']['bounded_segments']==0
    assert result['series'][20]['force_n']==pytest.approx(40*9.80665,abs=.01)
    missing=[dict(t=i/30,x=None,y=None) for i in range(60)]
    result=analyze_track(missing,calibration())
    assert result['summary']['peak_power_w'] is None
    assert result['summary']['tracked_ratio']==0
    low=[dict(t=i/15,x=320.,y=350-i) for i in range(60)]
    assert all(s['force_n'] is None for s in analyze_track(low,calibration())['series'])


def test_missing_window_breaks_derivatives_and_never_joins_segments():
    r=demo_report()
    c=r['calibration']
    samples=[dict(t=s['t'],x=500.,y=700-250*(1-math.cos(math.pi*s['t']))) for s in r['series'][:180]]
    samples[70].update(x=None,y=None)
    result=analyze_track(samples,c)
    assert all(s['velocity_m_s'] is None for s in result['series'][65:76])
    assert result['series'][70]['height_m'] is None


def image_at(x,y,patch):
    image=np.zeros((480,640,3),dtype=np.uint8)
    image[y-12:y+13,x-12:x+13]=patch
    return image


def test_real_template_tracker_translation_and_no_reacquisition():
    patch=np.random.default_rng(4).integers(30,255,(25,25,3),dtype=np.uint8)
    tracker=BarTracker(calibration())
    for i in range(50):
        tracker.consume(image_at(320,312-i,patch),i/30)
    assert tracker.samples[-1]['y']==263
    assert tracker.report()['series'][20]['velocity_m_s']==pytest.approx(.06,abs=.001)
    tracker.consume(np.zeros((480,640,3),dtype=np.uint8),50/30)
    tracker.consume(image_at(320,260,patch),51/30)
    assert tracker.samples[-1]['y'] is None
    assert tracker.reason


def test_no_texture_and_dimension_mismatch_are_graceful():
    tracker=BarTracker(calibration())
    tracker.consume(np.zeros((480,640,3),dtype=np.uint8),0.)
    assert tracker.report()['summary']['tracked_ratio']==0
    tracker=BarTracker(calibration())
    tracker.consume(np.zeros((240,320,3),dtype=np.uint8),0.)
    assert '尺寸' in tracker.report()['stop_reason']


def test_demo_is_explicit_computed_and_repeatable():
    r=demo_report()
    assert r==demo_report()
    assert r['synthetic'] and r['source']=='SYNTHETIC / TEST'
    assert r['summary']['bounded_segments']==3
    assert .7<r['summary']['peak_velocity_m_s']<.8
    assert 290<r['summary']['peak_power_w']<330
    assert 20<r['summary']['last_vs_best_velocity_loss_pct']<40


def test_adapter_analyzes_marker_even_without_pose(tmp_path,monkeypatch):
    from mobile_rehab import fitness_analyzer
    from app.domain import PoseFrame
    class EmptyVision:
        def __init__(self,**kwargs): pass
        def infer(self,packet,**kwargs):
            return PoseFrame(packet.context,packet.seq,packet.time_s,(640,480),[],model_manifest_id='test-empty')
        def close(self): pass
    monkeypatch.setattr(fitness_analyzer,'VisionWorker',EmptyVision)
    c=calibration()
    patch=np.random.default_rng(3).integers(30,255,(25,25,3),dtype=np.uint8)
    writer=cv2.VideoWriter(str(tmp_path/'video.mp4'),cv2.VideoWriter_fourcc(*'mp4v'),30.,(640,480))
    assert writer.isOpened()
    for i in range(120):
        t=i/30
        height=50*(1-math.cos(math.pi*(t-1))) if 1<=t<=3 else 0
        writer.write(image_at(320,312-round(height),patch))
    writer.release()
    job=dict(id='synthetic-marker',mode='fitness',exercise='fitness_deadlift',side='left',barbell_calibration=c)
    (tmp_path/'job.json').write_text(json.dumps(job),encoding='utf-8')
    fitness_analyzer.analyze(tmp_path/'job.json')
    result=json.loads((tmp_path/'result.json').read_text(encoding='utf-8'))
    assert result['summary']['completed']==0
    assert result['barbell']['summary']['bounded_segments']==1
    assert result['barbell']['summary']['peak_power_w']>0
    assert not list(tmp_path.rglob('*.sqlite3'))
