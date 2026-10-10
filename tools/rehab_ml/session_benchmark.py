"""Real baseline YOLO and ASGI lifecycle timings on isolated empty JPEGs.

Measures backend engineering paths, not people, cameras, network or accuracy.
The standard model and dependencies are untouched; no candidate is enabled.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from io import BytesIO
import json
from pathlib import Path
import tempfile
import time
from uuid import uuid4

from .common import ROOT, file_hash, paths, write_json


def benchmark_sessions(frames=20):
    if type(frames) is not int or not 8 <= frames <= 60:
        raise ValueError('session_benchmark_requires_8_to_60_frames')
    import yaml
    from fastapi import FastAPI, HTTPException, Request
    from fastapi.testclient import TestClient
    from PIL import Image
    from mobile_rehab.rehab_v2.api import install_rehab_v2
    from app.rehab_v2.telemetry import percentiles

    declared = yaml.safe_load((ROOT/'configs/rehab_ml/backend.yaml').read_text(encoding='utf-8'))['performance_predeclared']
    run = paths()['run']/('session-performance-'+uuid4().hex[:8])
    run.mkdir()
    def plan(owner, request):
        return dict(plan_id='TEST-service-performance', plan_revision=1, entry_key='shoulder_abduction:left',
                    reference=dict(record_origin='manual', fixture=True),
                    plan=dict(exercise_id='shoulder_abduction', side='left', target_reps=1,
                              target_sets=1, submode='training'))
    @asynccontextmanager
    async def lifespan(app):
        yield
        app.state.rehab_v2.close()
    app = FastAPI(lifespan=lifespan)
    def owner(request: Request):
        if request.cookies.get('test-performance-auth') != 'TEST-owned':
            raise HTTPException(401, 'authentication_required')
        return 'TEST-engineering-owner'
    async def small_json(request):
        body = await request.body()
        if len(body) > 4096:
            raise HTTPException(413)
        return json.loads(body)
    buffer = BytesIO()
    Image.new('RGB', (320, 240), 'white').save(buffer, format='JPEG')
    encoded = buffer.getvalue()
    with tempfile.TemporaryDirectory(dir=run) as directory:
        service = install_rehab_v2(app, Path(directory)/'isolated.sqlite3', owner, small_json, plan)
        with TestClient(app) as client:
            client.cookies.set('test-performance-auth', 'TEST-owned')
            base = '/api/rehab/v2/sessions'
            created = client.post(base, json=dict(idempotency_key='create', consent=True))
            created.raise_for_status()
            sid = created.json()['session_id']
            endpoint = base+'/'+sid
            http = dict(frame=[], state=[], diagnostics=[], pause=[], resume=[], finish=[])
            queue_peaks = []
            memory_samples = []
            revision = 0
            for seq in range(1, frames+1):
                started = time.perf_counter()
                response = client.post(endpoint+'/frames', content=encoded,
                    headers={'content-type': 'image/jpeg', 'x-rehab-event-id': 'frame-'+str(seq), 'x-rehab-seq': str(seq)})
                http['frame'].append(1000*(time.perf_counter()-started))
                response.raise_for_status()
                deadline = time.monotonic()+45.
                while True:
                    started = time.perf_counter()
                    response = client.get(endpoint)
                    http['state'].append(1000*(time.perf_counter()-started))
                    response.raise_for_status()
                    item = response.json()
                    if item['processed_count'] >= seq:
                        break
                    if item['persistence_state'] == 'finalized' or time.monotonic() >= deadline:
                        raise RuntimeError('real_pose_benchmark_did_not_process_requested_frame')
                    time.sleep(.01)
                started = time.perf_counter()
                diagnostic = client.get(endpoint+'/diagnostics')
                http['diagnostics'].append(1000*(time.perf_counter()-started))
                diagnostic.raise_for_status()
                observation = diagnostic.json()
                queue_peaks.append(observation['max_retained_queue_depth'])
                memory_samples.append(observation['memory'])
                for operation in ('pause', 'resume'):
                    started = time.perf_counter()
                    response = client.post(endpoint+'/'+operation, json=dict(idempotency_key=operation+str(seq),
                                                                            expected_revision=revision))
                    http[operation].append(1000*(time.perf_counter()-started))
                    response.raise_for_status()
                    revision = response.json()['revision']
            started = time.perf_counter()
            response = client.post(endpoint+'/finish', json=dict(idempotency_key='finish', expected_revision=revision))
            http['finish'].append(1000*(time.perf_counter()-started))
            response.raise_for_status()
            receipt = response.json()
            diagnostic = client.get(endpoint+'/diagnostics').json()
            runtime = service.runtimes[sid]
            with runtime.telemetry.lock:
                samples = {key: list(value) for key, value in runtime.telemetry.samples.items()}
            from .inventory import doctor
            environment = doctor()
            result = dict(run_id=run.name, benchmark='isolated_asgi_real_yolo_empty_jpeg',
                hardware=environment, declared_budgets=declared, frames=frames, image_size=[320, 240],
                clinical_accuracy=None, fixture='empty_image_and_manual_plan_not_reference_motion',
                load='one_producer_waiting_each_result_controls_between_frames',
                diagnostics=diagnostic, http={key: percentiles(value) for key, value in http.items()},
                warm_stages={key: percentiles(samples[key][1:]) for key in
                             ('decode_ms', 'inference_ms', 'pose_roundtrip_ms', 'result_age_ms')},
                cold_first={key: samples[key][0] if samples[key] else None for key in
                            ('decode_ms', 'inference_ms', 'pose_roundtrip_ms', 'result_age_ms')},
                control_http_budget_met=max(percentiles(http[key])['p95_ms'] for key in ('pause', 'resume'))
                                        <= declared['control_response_p95_ms'],
                max_retained_queue_depth=max(queue_peaks), final_commit=receipt,
                memory_samples=memory_samples, memory_sampling='after_each_processed_frame_not_peak_measurement',
                pose_model=dict(device='cpu', imgsz=640,
                    weights_sha256=file_hash(ROOT/'rehab_codex_single_camera_v2_1/assets/models/yolo11n-pose.pt')),
                exclusions=['phone', 'camera', 'network_before_receipt', 'target_motion_accuracy',
                            'multiple_clients', 'full_load_stream', 'candidate_tcn_runtime'])
    result['shutdown'] = dict(resources_released=service.resources_released,
                              pose_process_retained=service.inference_worker.process is not None,
                              frame_consumer_alive=service.worker.is_alive(),
                              report_consumer_alive=service.report_worker.is_alive())
    output = run/'summary.json'
    write_json(output, result)
    summary = dict(result, raw_summary=str(output), raw_summary_sha256=file_hash(output))
    write_json(ROOT/'reports/rehab_backend/session_performance.json', summary)
    return summary
