"""Deliberate exit of an isolated TEST process; never target an existing database."""
import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.rehab_ml.common import paths
from mobile_rehab.rehab_v2.service import SessionService
from app.rehab_v2.evidence import EvidenceFrame, MetricEvidence


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', type=Path, required=True)
    args = parser.parse_args()
    target = args.database.resolve()
    if not target.is_relative_to(paths()['run']) or target.exists():
        raise RuntimeError('Probe requires a new database under the dedicated run root')
    def plan(owner, request):
        return dict(plan_id='TEST-probe-plan', plan_revision=1, entry_key='shoulder_abduction:left',
                    reference=dict(owner=owner, fixture=True), plan=dict(exercise_id='shoulder_abduction'))
    service = SessionService(target, plan, internal_replay=True)
    owner = 'TEST-crash-owner'
    item = service.create(owner, dict(idempotency_key='probe', consent=True))
    runtime = service.runtimes[item['session_id']]
    seq, stamp = 0, 0.
    for value, count in ((0., 30), (70., 10), (0., 10), (70., 6)):
        for _ in range(count):
            seq, stamp = seq+1, stamp+.05
            evidence = MetricEvidence(value, 'degree', True, None, 'observed', stamp, stamp, 0.,
                                      tuple(runtime.engine.spec['required_joints']))
            frame = EvidenceFrame(seq, stamp, item['source_epoch'], 'one', 'coco17-v1', 'TEST-probe-model',
                                  (640, 480), {'raise_deg': evidence}, 'VALID')
            service.submit_evidence(owner, item['session_id'], 'frame-'+str(seq), frame)
    print(json.dumps(dict(session_id=item['session_id'])), flush=True)
    os._exit(27)


if __name__ == '__main__':
    main()
