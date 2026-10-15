"""Trace the existing TEST HTTP case without changing clocks or production rules.

Every run owns an isolated TestClient database. A requested delay is real wall
time before JPEG acceptance, never a replacement capture timestamp. Failure
logs and traces are retained; this is not a patient or camera-accuracy test.
"""
from __future__ import annotations

import argparse
import copy
from io import StringIO
import json
from pathlib import Path
import sys
import time
import unittest
from unittest.mock import patch
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'rehab_codex_single_camera_v2_1'))
sys.path.insert(0, str(ROOT / 'tests/rehab_backend'))
from app.rehab_v2.engine import ProtocolEngine
from mobile_rehab.rehab_v2.service import SessionService
from tools.rehab_ml.common import file_hash, git, paths, utc_now, write_json


def run_probe(*, delay_before_seq=0, delay_s=0., case='receive'):
    from test_timing_comparison import TimingComparisonHttpTests

    if not 0 <= delay_before_seq <= 64 or not 0 <= delay_s <= 2.:
        raise ValueError('TEST delay outside declared bounds')
    if bool(delay_before_seq) != bool(delay_s):
        raise ValueError('TEST delay requires both sequence and seconds')
    root = paths()['run'] / ('timing-http-probe-' + uuid4().hex[:8])
    root.mkdir()
    trace, invalidations, services, delayed = [], [], [], []
    original_process = ProtocolEngine.process
    original_invalidate = ProtocolEngine.invalidate
    original_submit = SessionService.submit_jpeg
    original_init = SessionService.__init__

    def initialize(service, *args, **kwargs):
        original_init(service, *args, **kwargs)
        services.append(service)

    def process(engine, frame):
        previous_time = engine.last_t
        before = dict(phase=engine.phase, run_state=engine.run_state,
                      baseline=copy.deepcopy(engine.baseline), completed=engine.completed)
        value = frame.metrics.get(engine.spec['metric'])
        result = original_process(engine, frame)
        trace.append(dict(session_id=engine.session_id, seq=frame.seq, time_s=frame.time_s,
                          dt_s=None if previous_time is None else frame.time_s-previous_time,
                          metric=None if value is None else copy.deepcopy(value.__dict__),
                          before=before, after=dict(phase=engine.phase, run_state=engine.run_state,
                              baseline=copy.deepcopy(engine.baseline), completed=engine.completed,
                              holds=copy.deepcopy(engine.holds), repetitions=copy.deepcopy(engine.repetitions),
                              diagnostics=copy.deepcopy(engine.diagnostics)), accepted=result))
        return result

    def invalidate(engine, reason, *, keep_baseline=False):
        invalidations.append(dict(session_id=engine.session_id, after_seq=engine.last_seq,
                                  after_time_s=engine.last_t, phase=engine.phase, reason=reason,
                                  keep_baseline=keep_baseline))
        return original_invalidate(engine, reason, keep_baseline=keep_baseline)

    def submit(service, owner, sid, event_id, seq, encoded):
        if seq == delay_before_seq:
            started = time.monotonic()
            time.sleep(delay_s)
            delayed.append(dict(session_id=sid, before_seq=seq,
                                requested_s=delay_s, elapsed_s=time.monotonic()-started))
        return original_submit(service, owner, sid, event_id, seq, encoded)

    stream = StringIO()
    started = time.perf_counter()
    with patch.object(SessionService, '__init__', initialize), \
         patch.object(SessionService, 'submit_jpeg', submit), \
         patch.object(ProtocolEngine, 'process', process), \
         patch.object(ProtocolEngine, 'invalidate', invalidate):
        method = ('test_actual_receive_clock_gap_is_persisted_without_confirming_hidden_return'
                  if case == 'host-gap' else 'test_actual_authenticated_host_endpoint_and_default_off_routes')
        test = TimingComparisonHttpTests(method)
        if case == 'receive':
            test.recorded_clock = False  # Reproduce the original wall-clock positive fixture.
        result = unittest.TextTestRunner(stream=stream, verbosity=2).run(unittest.TestSuite([test]))
    # Retain the primary evidence before computing optional diagnostics.
    write_json(root/'trace.json', dict(frames=trace, invalidations=invalidations))
    write_json(root/'test_output.json', dict(output=stream.getvalue()))
    summary = dict(run_id=root.name, created_at=utc_now(), head=git('rev-parse', 'HEAD'),
                   input='original authenticated HTTP TEST case; white JPEG and TEST geometry provider',
                   clock='unchanged server time.monotonic receive clock',
                   evidence_clock='TEST recorded seq * .05' if case == 'recorded' else 'actual server receive time',
                   case=case,
                   injected_delay=delayed, test_success=result.wasSuccessful(),
                   tests_run=result.testsRun, failures=len(result.failures), errors=len(result.errors),
                   elapsed_s=time.perf_counter()-started, frames_traced=len(trace),
                   max_dt_s=max((row['dt_s'] or 0. for row in trace), default=None),
                   invalidations=invalidations,
                   resources=[dict(closed=s.closed, resources_released=s.resources_released,
                                   inference_process_released=s.inference_worker.process is None,
                                   report_process_released=s.report_executor.process is None)
                              for s in services],
                   clinical_accuracy=None, original_failed_run='verification-f28dac51',
                   original_failure_root_cause_proven=False,
                   source_sha256={str(p.relative_to(ROOT)).replace('\\', '/'):file_hash(p) for p in (
                       Path(__file__), ROOT/'tests/rehab_backend/test_timing_comparison.py',
                       ROOT/'mobile_rehab/rehab_v2/service.py',
                       ROOT/'rehab_codex_single_camera_v2_1/app/rehab_v2/engine.py')})
    summary['artifacts'] = {name:dict(path=str(root/name), sha256=file_hash(root/name))
                            for name in ('trace.json', 'test_output.json')}
    write_json(root/'summary.json', summary)
    print(json.dumps(summary, ensure_ascii=False))
    return 0 if result.wasSuccessful() else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--delay-before-seq', type=int, default=0)
    parser.add_argument('--delay-s', type=float, default=0.)
    parser.add_argument('--case', choices=('receive','recorded','host-gap'), default='receive')
    args = parser.parse_args()
    return run_probe(delay_before_seq=args.delay_before_seq, delay_s=args.delay_s, case=args.case)


if __name__ == '__main__':
    raise SystemExit(main())
