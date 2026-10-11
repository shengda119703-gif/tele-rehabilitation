"""Bounded engineering observations, never movement evidence or plan inputs.

Durations are measured in the process owning each span. Rates/ages use only
the host clock: no client/child monotonic subtraction or exposure-time claim.
Only fixed enums and numeric metadata are retained, not media, poses or text.
"""
from __future__ import annotations

from collections import deque
from contextlib import contextmanager
import math
import threading
import time

VERSION = 'rehab-session-diagnostics-1'
SAMPLE_LIMIT = 512
EVENT_LIMIT = 128
STAGES = ('create_request_ms', 'frame_request_ms', 'queue_wait_ms', 'decode_ms',
          'inference_ms', 'pose_roundtrip_ms', 'feature_ms', 'rules_ms',
          'temporal_ms', 'cue_ms', 'checkpoint_ms', 'control_ms',
          'pause_request_ms', 'resume_request_ms', 'finish_request_ms',
          'feedback_request_ms', 'final_commit_ms', 'report_ms', 'report_compute_ms',
          'report_roundtrip_ms', 'pose_result_age_ms', 'result_age_ms')
COUNTERS = ('accepted', 'duplicate', 'processed', 'latest_replaced',
            'epoch_discarded', 'terminal_discarded', 'input_failed', 'inference_cancelled', 'timeout',
            'commit_success', 'report_failed', 'report_ready', 'report_superseded',
            'report_timeout', 'report_cancelled', 'report_busy', 'report_deferred', 'report_preempted',
            'background_failure', 'unprocessed_at_finish')


def _number(value):
    if type(value) not in (float, int) or not math.isfinite(value) or value < 0:
        raise ValueError('finite_nonnegative_diagnostic_number_required')
    return float(value)


def percentiles(values, *, total=None):
    """Nearest-rank quantiles on the retained window, not whole-run quantiles."""
    ordered = sorted(_number(v) for v in values)
    result = dict(total_samples=len(ordered) if total is None else total,
                  retained_samples=len(ordered), p50_ms=None, p95_ms=None, max_ms=None)
    if ordered:
        result.update(p50_ms=ordered[max(0, math.ceil(.5*len(ordered))-1)],
                      p95_ms=ordered[max(0, math.ceil(.95*len(ordered))-1)], max_ms=ordered[-1])
    return result


class SessionTelemetry:
    def __init__(self, trace_id, session_id, protocol_version):
        self.trace_id, self.session_id, self.protocol_version = trace_id, session_id, protocol_version
        self.lock = threading.Lock()
        self.samples = {key: deque(maxlen=SAMPLE_LIMIT) for key in STAGES}
        self.totals = dict.fromkeys(STAGES, 0)
        self.counters = dict.fromkeys(COUNTERS, 0)
        self.events = deque(maxlen=EVENT_LIMIT)
        self.event_count = 0
        self.arrivals = {'accepted': deque(maxlen=SAMPLE_LIMIT), 'processed': deque(maxlen=SAMPLE_LIMIT)}
        self.queue_high_water = 0

    def observe(self, stage, duration_ms):
        if stage not in self.samples:
            raise ValueError('unknown_diagnostic_stage')
        value = _number(duration_ms)
        with self.lock:
            self.samples[stage].append(value)
            self.totals[stage] += 1

    @contextmanager
    def span(self, stage):
        if stage not in self.samples:
            raise ValueError('unknown_diagnostic_stage')
        started = time.perf_counter()
        try:
            yield
        finally:
            self.observe(stage, 1000*(time.perf_counter()-started))

    def event(self, kind, *, seq=None, control_epoch=None, terminal_epoch=None, count=1):
        if kind not in self.counters or type(count) is not int or count < 1:
            raise ValueError('fixed_diagnostic_event_required')
        record = dict(kind=kind, count=count)
        for key, value in (('seq', seq), ('control_epoch', control_epoch), ('terminal_epoch', terminal_epoch)):
            if value is not None:
                if type(value) is not int or value < 0:
                    raise ValueError('nonnegative_diagnostic_sequence_required')
                record[key] = value
        with self.lock:
            self.counters[kind] += count
            self.event_count += 1
            self.events.append(record)

    def arrival(self, kind, host_monotonic_s, *, queue_depth=0):
        if kind not in self.arrivals or type(queue_depth) is not int or not 0 <= queue_depth <= 1:
            raise ValueError('bounded_diagnostic_arrival_required')
        value = _number(host_monotonic_s)
        with self.lock:
            stamps = self.arrivals[kind]
            if stamps and value < stamps[-1]:
                raise ValueError('diagnostic_host_clock_went_backwards')
            stamps.append(value)
            self.queue_high_water = max(self.queue_high_water, queue_depth)

    def snapshot(self):
        # Copy bounded arrays under a short lock; percentile sorting is outside
        # it. A diagnostic reader cannot hold up a control or inference span.
        with self.lock:
            samples = {k: list(v) for k, v in self.samples.items()}
            totals, counters = dict(self.totals), dict(self.counters)
            events, event_count = [dict(v) for v in self.events], self.event_count
            arrivals = {k: list(v) for k, v in self.arrivals.items()}
            high_water = self.queue_high_water
        rates = {}
        for kind, stamps in arrivals.items():
            elapsed = stamps[-1]-stamps[0] if len(stamps) > 1 else 0.
            rates[kind] = dict(retained_arrivals=len(stamps), window_s=elapsed,
                               hz=(len(stamps)-1)/elapsed if elapsed > 0 else None)
        return dict(version=VERSION, available=True, trace_id=self.trace_id,
                    session_id=self.session_id, job_id=None, protocol_version=self.protocol_version,
                    retention='volatile_current_host_not_reconstructed_after_restart',
                    consistency='bounded_stage_snapshot_not_a_business_transaction',
                    percentile_method='nearest_rank_retained_window',
                    limits=dict(samples_per_stage=SAMPLE_LIMIT, events=EVENT_LIMIT,
                                stage_count=len(STAGES), arrival_samples_per_stream=SAMPLE_LIMIT),
                    stages={k: percentiles(v, total=totals[k]) for k, v in samples.items()},
                    temporal_model=dict(enabled=False, reason='candidate_not_active'),
                    counters=counters, events=events, total_events=event_count,
                    host_rates=rates, max_retained_queue_depth=high_water,
                    clock_basis='host_receipt_and_processing_not_capture_or_network_latency')
