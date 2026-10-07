"""Complete fictional TEST account, isolated from every personal database.

Uses the normal product writers, report readers and plan rules. Never imports
patient footage, removes provenance, or overrides device/consent capabilities.
"""
from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OWNER = 'visual-test'
NAME = 'TEST 林女士'
FAMILY = 'visual-test-daughter'
SCHEMA = 'test-lin-profile-v1'
MARKER = 'fixture-manifest.json'
PROVENANCE = dict(synthetic=True, fixture=SCHEMA)
LOAD_SCHEMA = 'test-lin-load-v1'
FITNESS_IDS = ('fitness_squat', 'fitness_row')


def _checked_path(data: Path, workspace: Path) -> Path:
    data = data.resolve()
    allowed = (workspace / 'qa-output').resolve()
    if data == allowed or not data.is_relative_to(allowed):
        raise ValueError('TEST 档案只能保存在项目 qa-output 的独立子目录。')
    return data


def _read_manifest(data: Path) -> dict:
    value = json.loads((data/MARKER).read_text(encoding='utf-8'))
    if any(value.get(k) != v for k, v in dict(schema=SCHEMA, owner=OWNER, name=NAME, dataMode='demo', synthetic=True).items()):
        raise ValueError('目录不属于 TEST 林女士，拒绝覆盖。')
    return value


def claim_directory(data: Path, *, workspace: Path = ROOT) -> dict:
    """Only claim a new or previously marked folder underneath qa-output."""
    data = _checked_path(data, workspace)
    marker = data / MARKER
    if marker.exists():
        value = _read_manifest(data)
        if not value.get('complete'):
            raise ValueError('上次初始化未完成，请使用新的 qa-output 子目录，原数据保留。')
        return value
    if data.exists() and any(data.iterdir()):
        raise ValueError('拒绝写入已有、未标记的数据目录。')
    data.mkdir(parents=True, exist_ok=True)
    value = dict(schema=SCHEMA, owner=OWNER, name=NAME, dataMode='demo', synthetic=True, complete=False)
    from mobile_rehab.jsonio import write_json
    write_json(marker, value)
    return value


class FixtureClock:
    """Historical timestamps only during seed; ordinary live clock afterwards."""
    at = None

    def bridge(self, data: Path):
        from bridges.ankang.client import AgentBridge
        clock = self

        class SeedBridge(AgentBridge):
            def product(self, operation, owner_id='', payload=None, *, tool_handler=None):
                if clock.at is None:
                    return super().product(operation, owner_id, payload, tool_handler=tool_handler)
                return self._request('product', tool_handler=tool_handler, sessionId=owner_id,
                                     productOperation=operation, payload=payload or {}, now=clock.at.isoformat())

        return SeedBridge(data_dir=data / 'desktop' / 'product')


def scope(source, owner=OWNER):
    return dict(participant_id=owner, source_kind=source, usage_context='SELF_USE')


def identity(backend):
    profiles = backend.call('profile.list', '')
    current = next((p for p in profiles if p['ownerId'] == OWNER), None)
    if current is None or current['dataMode'] != 'demo' or current['profile']['name'] != NAME:
        raise ValueError('TEST 档案身份已变化，不重写该档案。')


def _health(backend, clock, now):
    from app.ui.product_dialogs import blank_health
    p = blank_health(NAME)
    p.update(age=68, sex='female', conditions=['高血压，按既有医嘱用药', '左肩抬举不便', '膝部晨起僵硬'],
             familyContact='女儿 · 林晓', familyPhone='通过家庭页面联系', elderPhone='站内联系',
             communityDoctorPhone='社区联系信息待绑定', mobility='independent', usesCane=False,
             nightVision='normal', cognition='stable')
    clock.at = now - timedelta(days=13)
    backend.call('profile.save', OWNER, dict(profile=p, dataMode='demo',
                 rehabGoal='抬手取物更轻松，保持独立起坐与步行。', currentState='完成肩部练习，日常起坐可独立完成。'))
    medicines = [
        dict(id='lin-bp', name='苯磺酸氨氯地平片', dose='5 mg · 1 片', purpose='既有降压医嘱', times='08:00', status='active'),
        dict(id='lin-calcium', name='碳酸钙 D3 片', dose='1 片', purpose='既有补充安排', times='19:30', status='active'),
        dict(id='lin-old-med', name='既往止痛药', dose='按既有医嘱', purpose='既往膝部不适', times='按需', status='stopped'),
    ]
    for med in medicines:
        backend.call('medication.save', OWNER, dict(record=med))
        if med['status'] == 'active':
            backend.call('daily.medSchedule', OWNER, dict(medId=med['id'], times=[med['times']],
                         start=(now.date()-timedelta(days=13)).isoformat(), end=''))
    # Every existing supported indicator has a dated series; no hardware claim.
    values = {
        'weight': ('kg', [62.4, 62.3, 62.2, 62.3, 62.2, 62.2, 62.1, 62.1, 62.2, 62.1, 62.0, 62.1, 62.0, 62.0]),
        'steps': ('步', [2800, 3100, 3000, 3350, 3500, 3400, 3600, 3800, 3650, 3950, 4100, 4050, 4200, 4300]),
        'sleepHours': ('小时', [6.2, 6.5, 6.3, 6.6, 6.5, 6.7, 6.8, 6.7, 6.9, 6.8, 7.0, 6.9, 7.1, 7.0]),
        'nightWakes': ('次', [2, 2, 2, 1, 2, 1, 1, 1, 1, 1, 1, 1, 1, 1]),
        'restingHr': ('bpm', [75, 74, 76, 73, 74, 72, 73, 72, 71, 72, 71, 70, 72, 71]),
        'spo2': ('%', [97, 98, 97, 98, 98, 97, 98, 98, 98, 97, 98, 98, 98, 98]),
        'systolic': ('mmHg', [138, 136, 137, 135, 134, 136, 133, 134, 132, 133, 131, 132, 130, 132]),
        'diastolic': ('mmHg', [84, 83, 84, 82, 82, 83, 81, 82, 80, 81, 80, 81, 80, 81]),
        'bloodGlucose': ('mmol/L', [5.8, 5.7, 5.8, 5.6, 5.7, 5.6, 5.6, 5.5, 5.6, 5.5, 5.6, 5.5, 5.5, 5.6]),
        'walkSpeed': ('m/s', [.82, .83, .83, .85, .84, .86, .86, .88, .87, .89, .90, .89, .91, .92]),
    }
    measurements = []
    for n in range(14):
        at = now - timedelta(days=13-n, minutes=10)
        for metric, (unit, sequence) in values.items():
            measurements.append(dict(id=f'lin-{metric}-{at.date().isoformat()}', timestamp=at.isoformat(),
                metric=metric, value=sequence[n], unit=unit, source='demo', confidence=1,
                visibility='family_ok', metadata=PROVENANCE))
        for med in medicines[:2]:
            scheduled = datetime.combine(at.date(), datetime.strptime(med['times'], '%H:%M').time(), now.tzinfo)
            if scheduled <= now:
                backend.call('daily.dose', OWNER, dict(medId=med['id'], date=at.date().isoformat(),
                             time=med['times'], status='skipped' if n == 3 and med['id'] == 'lin-calcium' else 'taken'))
    clock.at = now - timedelta(minutes=5)
    backend.call('device.import', OWNER, dict(ownerId=OWNER, source='demo', measurements=measurements))
    for days, text in [(6, '今天左肩抬手不太方便，穿外套慢一些。'),
                       (3, '今天做完练习有点累，休息后好了，没有疼痛。'),
                       (1, '今天能抬手取低处的物品，膝盖早上还有一点僵硬。'),
                       (0, '今天练习后没有疼痛，精神不错。')]:
        clock.at = now - timedelta(days=days, minutes=4)
        backend.call('chat', OWNER, dict(text=text))
    return values


def _session(source, eid, side, when, low, high, *, count=5, suffix='', training=None):
    from app.exercises import exercise_spec
    from app.settings import default_plan
    spec = exercise_spec(eid)
    sid = hashlib.sha256(f'{OWNER}/{source}/{eid}/{side}/{when.isoformat()}/{suffix}'.encode()).hexdigest()[:32]
    summary = dict(primary_metric=spec['metric'], primary_metric_label=spec['metric_label'],
                   completed=count, partial=0, observed_span_s=round(count*5.5+3, 1),
                   valid_ratio=.96, valid_sample_count=180, motion_range_valid=True,
                   motion_range=dict(min_deg=low, max_deg=high, range_deg=round(high-low, 1)))
    plan = dict(default_plan(eid), participant_id=OWNER, side=side,
                submode='training' if training else 'assessment')
    repetitions = []
    for n in range(count):
        repetitions.append(dict(number=n+1, primary_metric=spec['metric'], completion_status='COMPLETE',
            observation_status='VALID', metric_validity={spec['metric']: dict(valid=True, partial_observation=False)},
            target_status='MET' if training else 'NOT_SET', issues=[], peak_angle_deg=high, min_angle_deg=low,
            start_time_s=n*5.5, turn_time_s=n*5.5+2.5, end_time_s=(n+1)*5.5,
            movement_timing=dict(goals={}), **PROVENANCE))
    if training:
        plan.update(training['settings'], saved_plan_reference=training['reference'])
        summary.update(plan_completed=True, target_reps=count, target_sets=1, completed_sets=1)
    return dict(id=sid, scene_id='rehab', **scope(source), exercise_id=eid, side=side,
                submode=plan['submode'], status='FINISHED', start_utc=(when-timedelta(seconds=summary['observed_span_s'])).isoformat(),
                end_utc=when.isoformat(), measurement_contract=spec['measurement_contract'], view=spec['view'],
                summary=summary, repetitions=repetitions, source_ref='fixture:'+SCHEMA,
                model_manifest_id='fixture-geometry', measurement_type='2d_projection', clinical_rom=False,
                config_snapshot=dict(plan=plan, poses_consent=False), **PROVENANCE)


def _job(data, session, *, mode=None, result=None, when=None, exercise=None):
    from mobile_rehab.jsonio import write_json
    from app.automatic_plans import observed_quality
    uid = hashlib.sha256(OWNER.encode()).hexdigest()[:32]
    sid = session['id']
    at = when or session['end_utc']
    exercise = exercise or session['exercise_id']
    mode = mode or session['submode']
    job = dict(id=sid, owner=uid, exercise=exercise, side=session.get('side', 'left'), mode=mode,
               state='done', message='结果已保存', created_at=at, consent_at=at,
               participant_id=OWNER, shared_database=str(data/'desktop'/'home_rehab.sqlite3'), **PROVENANCE)
    if session.get('training_feedback'):
        job['feedback'] = session['training_feedback']
    if result is None:
        result = dict(session_id=sid, source_kind='REPLAY_FILE', usage_context='SELF_USE',
            summary=session['summary'], repetitions=session['repetitions'], finished_at=at,
            quality=observed_quality(session['repetitions']), processed_frames=180,
            measurement_type='2d_projection', clinical_rom=False, **PROVENANCE)
    folder = data/'phone'/'jobs'/uid/sid
    folder.mkdir(parents=True, exist_ok=True)
    if (folder/'job.json').exists():
        old = json.loads((folder/'job.json').read_text(encoding='utf-8'))
        if old.get('owner') != uid or old.get('fixture') != SCHEMA or old.get('synthetic') is not True:
            raise ValueError('拒绝覆盖非本 fixture 的动作报告。')
    write_json(folder/'job.json', job)
    write_json(folder/'result.json', result)


def _rehab(backend, data, now):
    from app.storage import Storage
    from app.assessment import build_body_profile
    from app.automatic_plans import generate_proposal, create_automatic_plan, program_progress
    rows = [('shoulder_abduction', 'left', 4., 105.), ('shoulder_abduction', 'right', 3., 138.),
            ('shoulder_flexion', 'left', 5., 116.), ('shoulder_flexion', 'right', 4., 143.),
            ('elbow_flexion', 'left', 8., 133.), ('elbow_flexion', 'right', 6., 138.),
            ('knee_extension', 'left', 9., 92.), ('knee_extension', 'right', 6., 96.),
            ('hip_flexion', 'left', 0., 67.), ('hip_flexion', 'right', 0., 71.),
            ('ankle_dorsiflexion', 'left', 0., 18.), ('ankle_dorsiflexion', 'right', 0., 21.),
            ('neck_flexion', 'left', 0., 29.), ('wrist_extension', 'left', 0., 43.)]
    store = Storage(data/'desktop'/'home_rehab.sqlite3')
    plans = {}
    try:
        for source in ('LIVE_CAMERA', 'REPLAY_FILE'):
            for n, (eid, side, low, high) in enumerate(rows):
                s = _session(source, eid, side, now-timedelta(days=5, minutes=60-n), low, high)
                store.save_session(s)
                if source == 'REPLAY_FILE':
                    _job(data, s)
            # Retest snapshots remain separate history, not inferred clinical recovery.
            for n, (eid, side, low, high) in enumerate(rows[:4]):
                s = _session(source, eid, side, now-timedelta(days=1, minutes=35-n), low, high+6,
                             suffix='follow-up')
                store.save_session(s)
                if source == 'REPLAY_FILE':
                    _job(data, s)
            sessions = store.list_sessions()
            profile = build_body_profile(sessions, OWNER, source, 'SELF_USE')
            proposal = generate_proposal(profile, sessions, now=now)
            plan = create_automatic_plan(proposal, dict(general_activity_ok=True, standing_support_ok=True,
                                                       companion_present=False), now=now-timedelta(minutes=40))
            plan = store.save_training_plan(plan, expected_revision=0)
            for n, entry in enumerate(plan['items'][:2]):
                assessed = next(r for r in profile['items'] if r['exercise_id'] == entry['exercise_id'] and r['side'] == entry['side'])
                span = assessed['motion_range']
                reference = dict(id=plan['id'], revision=plan['revision'], entry_key=entry['key'])
                s = _session(source, entry['exercise_id'], entry['side'], now-timedelta(minutes=30-n*8),
                             span['min_deg'], span['max_deg'], count=entry['settings']['target_reps'],
                             suffix='training', training=dict(settings=entry['settings'], reference=reference))
                store.save_session(s)
                s = store.save_training_feedback(s['id'], dict(pain=0, fatigue=2+n, reason='completed',
                    notes='按安排完成，抬手过程平稳。' if n == 0 else '完成后稍累，休息后缓解。'), expected_revision=0)
                # Fixture provenance stays attached even to normalized self-report metadata.
                s['training_feedback'].update(PROVENANCE)
                store.save_session(s)
                if source == 'REPLAY_FILE':
                    _job(data, s)
            progress = program_progress(plan, store.list_sessions())
            if progress['completed'] != 2 or progress['total'] != 4 or progress['blocked']:
                raise RuntimeError('TEST 计划未形成可继续的正常进度。')
            plans[source] = plan
            backend.daily.remember_plan(OWNER, plan)
            for days, time in [(0, '09:00'), (2, '09:00'), (4, '09:00')]:
                backend.call('daily.schedule', OWNER, dict(date=(now.date()+timedelta(days=days)).isoformat(),
                    time=time, kind='training', name=plan['name'], planId=plan['id'], revision=plan['revision']), scope(source))
            backend.call('daily.schedule', OWNER, dict(date=(now.date()+timedelta(days=6)).isoformat(),
                time='09:30', kind='assessment', name='肩部与下肢复评'), scope(source))
        return plans
    finally:
        store.close()


def _fitness_load_report(result, mass=20.):
    """Assumed TEST trajectories aligned to existing reps; not footage tracking."""
    from mobile_rehab.barbell import analyze_track
    eid = result['exercise']
    if eid not in FITNESS_IDS or result.get('fixture') != SCHEMA or result.get('synthetic') is not True:
        raise ValueError('器械补充只接受本 TEST 档案的两项健身记录。')
    repetitions = result['repetitions']
    if not repetitions or len(repetitions) != result['summary']['completed']:
        raise ValueError('动作记录不完整，未补充器械数据。')
    phases = []
    previous = 0.
    for rep in repetitions:
        start, turn, end = (float(rep[key]['t']) for key in ('start', 'turn', 'end'))
        if not all(math.isfinite(t) for t in (start, turn, end)) or not previous < start < turn < end:
            raise ValueError('动作时间不连续，未补充器械数据。')
        phases.append((start, turn, end))
        previous = end
    # 60 Hz fixture sampling with a 0.5 m reference spanning 500 pixels.
    # Squat lowers before rising; row rises before lowering. Each has rest bounds.
    travel = -.35 if eid == 'fitness_squat' else .20
    samples = []
    for n in range(math.ceil((phases[-1][2]+.5)*60)+1):
        t, height = n/60, 0.
        for start, turn, end in phases:
            if start <= t <= turn:
                height = travel*.5*(1-math.cos(math.pi*(t-start)/(turn-start)))
                break
            if turn < t <= end:
                height = travel*.5*(1+math.cos(math.pi*(t-turn)/(end-turn)))
                break
        samples.append(dict(t=t, x=500., y=600.-height*1000.))
    calibration = dict(size=[1000,1000], reference_a=[.1,.2], reference_b=[.1,.7],
                       target=[.5,.6], length_m=.5, mass_kg=mass, confirmed=True)
    report = analyze_track(samples, calibration, synthetic=True)
    if report['summary']['bounded_segments'] != len(repetitions):
        raise ValueError('器械上升次数与已有动作不一致，未写入。')
    report.update(PROVENANCE, fixture_load=LOAD_SCHEMA, participant_name=NAME,
                  trajectory=dict(source='fixture_cosine', travel_m=abs(travel), sample_hz=60))
    return report


def refresh_fitness_load(backend, data: Path, *, workspace: Path = ROOT):
    """Guarded, backed-up upgrade of exactly two TEST results; never adds jobs."""
    from mobile_rehab.jsonio import write_json
    data = _checked_path(data, workspace)
    manifest = _read_manifest(data)
    if not manifest.get('complete') or backend.data_dir.resolve() != (data/'desktop').resolve():
        raise ValueError('只接受已完成的独立 TEST 档案及匹配的读取器。')
    identity(backend)
    uid = hashlib.sha256(OWNER.encode()).hexdigest()[:32]
    updates, reports = [], []
    # Validate both targets and backups before any write, including resolved paths.
    for eid in FITNESS_IDS:
        sid = hashlib.sha256((SCHEMA+eid).encode()).hexdigest()[:32]
        folder = data/'phone'/'jobs'/uid/sid
        for path in (folder/'job.json', folder/'result.json', folder/'result.before-load-v1.json'):
            if not path.resolve().is_relative_to(data) or path.is_symlink():
                raise ValueError('报告路径越界，未写入。')
        job = json.loads((folder/'job.json').read_text(encoding='utf-8'))
        result = json.loads((folder/'result.json').read_text(encoding='utf-8'))
        if any(job.get(k) != v for k,v in dict(id=sid, owner=uid, participant_id=OWNER,
                mode='fitness', exercise=eid, state='done', **PROVENANCE).items()):
            raise ValueError('报告不属于 TEST 林女士，未写入。')
        if any(result.get(k) != v for k,v in dict(kind='fitness', exercise=eid, **PROVENANCE).items()):
            raise ValueError('结果来源已变化，未写入。')
        old = result.get('barbell')
        if old is not None:
            if old.get('fixture_load') != LOAD_SCHEMA or old.get('synthetic') is not True or old.get('fixture') != SCHEMA:
                raise ValueError('已有其他器械结果，未覆盖。')
            if old.get('calibration',{}).get('mass_kg') != 20. or old.get('participant_name') != NAME:
                raise ValueError('器械记录已修改，未覆盖。')
            reports.append(dict(exercise=eid, changed=False, summary=old['summary']))
            continue
        backup = folder/'result.before-load-v1.json'
        if backup.exists() and json.loads(backup.read_text(encoding='utf-8')) != result:
            raise ValueError('备份与原结果不一致，未覆盖。')
        barbell = _fitness_load_report(result)
        updated = dict(result, barbell=barbell, participant_name=NAME)
        updates.append((folder/'result.json', backup, result, updated))
        reports.append(dict(exercise=eid, changed=True, summary=barbell['summary']))
    for path, backup, original, updated in updates:
        # Refuse intervening edits between validation and the atomic replacement.
        if json.loads(path.read_text(encoding='utf-8')) != original:
            raise ValueError('报告刚被修改，原记录保留。')
        if not backup.exists():
            write_json(backup, original)
        write_json(path, updated)
    return reports


def _movement_reports(data, now):
    from app.domain import Context, PoseFrame, PosePerson
    from mobile_rehab.fitness import FitnessEngine, EXERCISES, VERSION as FITNESS_VERSION
    from mobile_rehab.posture import PostureEngine, TASKS, VERSION as POSTURE_VERSION
    context = Context(1, 'fitness', 'TEST-fixture', 'SYNTHETIC', 'TEST', 'lin-fixture')
    for eid, cycles, days in [('fitness_squat', 8, 2), ('fitness_row', 6, 4)]:
        engine = FitnessEngine(eid, 'left')
        a, b = 170., 65.
        cycle = [a]*12+[a+(b-a)*i/8 for i in range(1, 9)]+[b]*8+[b+(a-b)*i/8 for i in range(1, 9)]+[a]*10
        for n, degrees in enumerate(cycle*cycles):
            # Anatomically coherent side-view fixture, not degenerate test triangles.
            xy = [[480.,180.] for _ in range(17)]
            if eid == 'fitness_squat':
                flex = 180-degrees
                shin = math.radians(flex/4)
                thigh = math.radians(flex/4-flex)
                lean = math.radians(5+20*(170-degrees)/105)
                ankle = [550.,900.]
                knee = [ankle[0]+230*math.sin(shin), ankle[1]-230*math.cos(shin)]
                hip = [knee[0]+240*math.sin(thigh), knee[1]-240*math.cos(thigh)]
                shoulder = [hip[0]+210*math.sin(lean), hip[1]-210*math.cos(lean)]
                for offset in (0,1):
                    xy[5+offset],xy[11+offset],xy[13+offset],xy[15+offset]=shoulder[:],hip[:],knee[:],ankle[:]
                    xy[7+offset]=[shoulder[0]+50,shoulder[1]+80]
                    xy[9+offset]=[shoulder[0]+110,shoulder[1]+30]
            else:
                shoulder,elbow=[480.,370.],[490.,510.]
                r=math.radians(degrees)
                dx,dy=-10/math.hypot(10,140),-140/math.hypot(10,140)
                wrist=[elbow[0]+180*(dx*math.cos(r)-dy*math.sin(r)),
                       elbow[1]+180*(dx*math.sin(r)+dy*math.cos(r))]
                for offset in (0,1):
                    xy[5+offset],xy[7+offset],xy[9+offset]=shoulder[:],elbow[:],wrist[:]
                    xy[11+offset],xy[13+offset],xy[15+offset]=[370.,540.],[420.,740.],[430.,940.]
            engine.consume(PoseFrame(context, n+1, n*.1, (1000,1000),
                [PosePerson('lin', [100,100,900,900], xy, [1.]*17)], model_manifest_id='fixture-geometry'))
        at = (now-timedelta(days=days, minutes=90)).isoformat()
        sid = hashlib.sha256((SCHEMA+eid).encode()).hexdigest()[:32]
        result = dict(kind='fitness', exercise=eid, side='left', rule_version=FITNESS_VERSION,
            source_kind='REPLAY_FILE', usage_context='SELF_USE', finished_at=at, summary=engine.summary(),
            repetitions=engine.repetitions, series=engine.series, spec=EXERCISES[eid], barbell=None,
            processed_frames=engine.frames, conditions=dict(view='sagittal_user_selected', size=[1000,1000],
                model_manifest_id='fixture-geometry', schema='coco17-v1'),
            limitations=['仅观察二维投影，不测肌肉力量。'], **PROVENANCE)
        result.update(barbell=_fitness_load_report(result), participant_name=NAME)
        _job(data, dict(id=sid), mode='fitness', result=result, when=at, exercise=eid)
    for eid in TASKS:
        engine = PostureEngine(eid, 'left')
        for n in range(61):
            xy = [[200.,100.] for _ in range(17)]
            for i, point in {3:(221,80),5:(205,150),6:(305,154),11:(210,300),12:(290,302),
                             13:(213,420),15:(210,550)}.items():
                xy[i] = list(point)
            engine.consume(PoseFrame(context, n+1, n*.1, (640,640),
                [PosePerson('lin', [100,50,400,580], xy, [1.]*17)], model_manifest_id='fixture-geometry'))
        at = (now-timedelta(days=3, minutes=45)).isoformat()
        result = dict(kind='posture', rule_version=POSTURE_VERSION, source_kind='REPLAY_FILE',
            usage_context='SELF_USE', exercise=eid, side='left', finished_at=at, summary=engine.summary(),
            conditions=dict(view=TASKS[eid]['view'], size=[640,640], model_manifest_id='fixture-geometry', schema='coco17-v1'),
            limitations=['结果是画面中的体态投影，不作疾病诊断。'], **PROVENANCE)
        _job(data, dict(id=hashlib.sha256((SCHEMA+eid).encode()).hexdigest()[:32]),
             mode='posture', result=result, when=at, exercise=eid)


def _archives(backend, clock, now):
    files = [('身体信息摘要', '其他资料',
              f'{NAME}\n68 岁，女性\n近期体重 62.0 kg\n血压 132/81 mmHg，静息心率 71 bpm\n左肩抬手不便，日常起坐可独立完成。\n目标：抬手取物更轻松，保持独立起坐与步行。'),
             ('康复评估与训练汇总', '其他资料',
              f'{NAME}\n已保存肩、肘、髋、膝、踝、头颈与腕部活动记录。\n近期左肩外展二维活动范围 4–111°。\n当前安排 4 项，已完成 2 项；训练后疼痛 0/10，疲劳 2–3/10。\n角度为二维投影记录，不是临床关节活动度结论。'),
             ('目前用药清单', '病历资料',
              f'{NAME}\n苯磺酸氨氯地平片：既有医嘱，5 mg，08:00。\n碳酸钙 D3 片：既有安排，1 片，19:30。\n既往止痛药：已停用。\n本清单不用于新增或调整用药。')]
    clock.at = now-timedelta(minutes=3)
    for name, category, content in files:
        backend.call('archive.save', OWNER, dict(name=name, category=category, fileName=name+'.txt',
            mediaType='text/plain', visibility='private', bytes=list(content.encode('utf-8'))))


def _family(backend, clock, now):
    from app.ui.product_dialogs import blank_health
    p = blank_health('TEST 林晓')
    p.update(age=39, sex='female', conditions=['日常活动正常'], familyContact='母亲 · 林女士',
             familyPhone='站内联系', elderPhone='站内联系')
    clock.at = now-timedelta(minutes=2)
    backend.call('profile.save', FAMILY, dict(profile=p, dataMode='demo'))
    code = backend.call('daily.familyInvite', FAMILY)['code']
    backend.call('daily.familyBind', OWNER, dict(code=code))
    # Categories remain real local access controls; no external notification sent.
    backend.call('daily.familyGrant', OWNER, dict(member=FAMILY, categories=['health','rehab','medication']))
    backend.call('daily.familyGrant', FAMILY, dict(member=OWNER, categories=['health']))
    backend.call('health.record', FAMILY, dict(metric='weight', value=55.6, visibility='family_ok'))
    backend.call('chat', FAMILY, dict(text='今天陪妈妈完成练习，结束后一起散步。'))


def seed(backend, data: Path, clock: FixtureClock, *, now=None, workspace: Path = ROOT):
    """Idempotent restart: once complete, never refill or overwrite user edits."""
    data = _checked_path(data, workspace)
    manifest = _read_manifest(data)
    if backend.data_dir.resolve() != (data/'desktop').resolve():
        raise ValueError('写入器与 TEST 数据目录不一致。')
    if manifest.get('complete'):
        identity(backend)
        return manifest
    # Refuse preexisting profiles even if a copied marker claims this folder.
    if backend.call('profile.list', ''):
        raise ValueError('初始化只接受空档案库。')
    now = now or datetime.now().astimezone()
    if now.tzinfo is None or now > datetime.now().astimezone()+timedelta(seconds=2):
        raise ValueError('初始化日期必须带时区且不能在未来。')
    try:
        _health(backend, clock, now)
        clock.at = None
        plans = _rehab(backend, data, now)
        _movement_reports(data, now)
        _archives(backend, clock, now)
        _family(backend, clock, now)
        clock.at = None
        identity(backend)
        manifest.update(complete=True, createdAt=now.isoformat(), healthMeasurements=140,
                        assessmentPerSource=18, trainingPerSource=2, fitnessReports=2, postureReports=2,
                        planIds={source:p['id'] for source,p in plans.items()})
        from mobile_rehab.jsonio import write_json
        write_json(data/MARKER, manifest)
        return manifest
    finally:
        clock.at = None


if __name__ == '__main__':
    import argparse
    import os
    import sys
    parser = argparse.ArgumentParser(description='补充独立 TEST 林女士的两份器械报告。')
    parser.add_argument('--refresh-fitness', action='store_true', required=True)
    parser.add_argument('--data-root', type=Path, default=ROOT/'qa-output'/'test-lin-profile')
    args = parser.parse_args()
    data = _checked_path(args.data_root, ROOT)
    if not _read_manifest(data).get('complete'):
        raise ValueError('档案尚未完成，未写入。')
    sys.path[:0] = [str(ROOT/'rehab_codex_single_camera_v2_1'), str(ROOT)]
    os.environ['ANKANG_PRODUCT_DISABLE_MODEL'] = '1'
    os.environ['ANKANG_VOICE_DISABLED'] = '1'
    from app.product.backend import ProductBackend
    backend = ProductBackend(data/'desktop')
    try:
        print(json.dumps(refresh_fitness_load(backend, data), ensure_ascii=False, allow_nan=False))
    finally:
        backend.close()
