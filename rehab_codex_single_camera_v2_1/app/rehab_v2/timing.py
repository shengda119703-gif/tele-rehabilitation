"""V2 provenance envelope around the existing observed-time algorithm.

No new dosage, time targets or count gates are introduced here. Peak-band
segmentation is retrospective after a complete observed cycle; live hold is
causal and is broken by missing observations. Standing uses the v2 protocol's
observed knee range, not the legacy personal knee/hip calibration.
"""
from ..movement_timing import TIMING_VERSION as ALGORITHM_VERSION

TIMING_VERSION = 'rehab-observed-timing-2'


def snapshot(timer, completion, *, time_basis, cycle_complete=False, reason=None):
    result = timer.snapshot(completion, cycle_complete=cycle_complete, reason=reason)
    result.update(version=TIMING_VERSION, algorithm_version=ALGORITHM_VERSION,
                  time_basis=time_basis, count_gate=False,
                  live_hold_method='consecutive_current_observations',
                  phase_timing_mode='after_observed_cycle',
                  observed_sample_count=len(timer.samples),
                  evidence_refs=dict(first=getattr(timer, 'first_ref', None),
                                     latest=getattr(timer, 'latest_ref', None),
                                     standing=getattr(timer, 'standing_ref', None),
                                     return_start=getattr(timer, 'return_ref', None),
                                     seated_rearm=getattr(timer, 'seated_ref', None)))
    if timer.sit_to_stand:
        result.update(method='protocol_standing_range_2',
                      phase_timing_mode='observed_standing_and_seated_rearm',
                      hold_anchor='protocol_standing_knee_range')
    else:
        result['hold_anchor'] = 'prescribed_projected_metric' if timer.target is not None else None
    return result
