from __future__ import annotations

from collections import deque
from dataclasses import asdict
import math
from statistics import median

from .protocols import validated_plan
from .timing import TIMING_VERSION, snapshot as timing_snapshot
from ..movement_timing import MovementTiming


class ProtocolEngine:
    """Versioned causal rules; count, target and assessability are independent.

    Observed dwell is never accumulated through missing, stale or predicted data.
    A short gap keeps context, but a turn hidden inside that gap is not inferred.
    """
    def __init__(self, plan, *, source_epoch, session_id=''):
        self.plan, self.spec = validated_plan(plan)
        self.source_epoch, self.session_id = source_epoch, session_id
        self.calibration_epoch = 0
        self.last_seq, self.last_t = -1, None
        self.last_good_t, self.last_value, self.last_track = None, None, None
        self.signature = None
        self.baseline = None
        self.ready_values = deque(maxlen=120)
        self.holds = {}
        self.phase, self.run_state = 'WAIT_READY', 'preparing'
        self.observation_state = 'missing'
        self.repetitions, self.current = [], None
        self.gap, self.pause_reason = False, None
        self.latest = None
        self.diagnostics = {'rejected': {}, 'missing_frames': 0}
        self.issue_starts = {}
        self.current_issues = []
        self.timing_history = deque(maxlen=128)
        self.timing = self.standing_timing = self.standing_rep = None
        self.pending_input_gap = None

    def note_input_gap(self, seq, stamp, reason):
        # A dropped pending frame may be newer than an in-flight valid frame.
        # Break continuity at the next processed prefix beyond that sequence,
        # not by retroactively invalidating the earlier in-flight observation.
        if self.pending_input_gap is None or seq > self.pending_input_gap['seq']:
            self.pending_input_gap = dict(seq=seq, time_s=stamp, reason=reason)

    def _timing_ref(self, seq, stamp):
        return dict(seq=seq, source_epoch=self.source_epoch, time_s=stamp)

    def _add_timing(self, timer, stamp, value, standing, seq):
        timer.add(stamp, value, at_standing=standing)
        ref = self._timing_ref(seq, stamp)
        if getattr(timer, 'first_ref', None) is None:
            timer.first_ref = ref
        timer.latest_ref = ref

    def _timing_snapshot(self, timer, completion, *, cycle_complete=False, reason=None):
        return timing_snapshot(timer, completion, cycle_complete=cycle_complete, reason=reason,
                               time_basis=self.signature[4] if self.signature else None)

    def _break_timing(self, stamp, reason):
        self.timing_history.clear()
        for timer in (self.timing, self.standing_timing):
            if timer is not None:
                timer.break_continuity(stamp, reason)
        self._update_timing()

    def _update_timing(self):
        if self.current is not None and self.timing is not None:
            self.current['movement_timing'] = self._timing_snapshot(self.timing, 'PARTIAL')
        if self.standing_timing is not None and self.standing_rep is not None:
            self.standing_rep['movement_timing'] = self._timing_snapshot(self.standing_timing, 'COMPLETE')

    def _close_standing_timing(self, reason=None, *, cycle_complete=False):
        if self.standing_timing is not None and self.standing_rep is not None:
            result = self._timing_snapshot(self.standing_timing, 'COMPLETE',
                                          cycle_complete=cycle_complete, reason=reason)
            self.standing_rep['movement_timing'] = result
            self.standing_rep['lowering_time_s'] = result['return_s']['value']
        self.standing_timing = self.standing_rep = None

    def _timing_observation(self, frame, value):
        standing = self.spec['exercise_id'] == 'sit_to_stand' and value <= self.spec['standing_max_deg']
        self.timing_history.append((frame.time_s, value, standing, frame.seq))
        cutoff = frame.time_s-max(2., self.plan['dwell_s']+self.plan['max_gap_s']+.5)
        while len(self.timing_history) > 1 and self.timing_history[1][0] < cutoff:
            self.timing_history.popleft()
        timer = self.timing or self.standing_timing
        if timer is not None:
            self._add_timing(timer, frame.time_s, value, standing, frame.seq)
        self._update_timing()

    def timing_live(self):
        timer = self.timing or self.standing_timing
        if (timer is None or self.latest is None or self.pending_input_gap is not None or self.run_state in ('paused', 'ended')
                or self.observation_state in ('missing', 'unavailable')):
            return None
        return dict(timer.live(), version=TIMING_VERSION)

    @property
    def completed(self):
        return sum(r['completion_status'] == 'COMPLETE' for r in self.repetitions)

    def _reject(self, reason):
        counts = self.diagnostics['rejected']
        counts[reason] = counts.get(reason, 0) + 1
        return False

    def _held(self, name, condition, stamp, duration):
        if not condition:
            self.holds.pop(name, None)
            return False
        return stamp - self.holds.setdefault(name, stamp) + 1e-8 >= duration

    def _partial(self, reason):
        if self.current is not None:
            if self.timing is not None:
                self.current['movement_timing'] = self._timing_snapshot(self.timing, 'UNASSESSABLE', reason=reason)
            self.repetitions.append(dict(self.current, completion_status='UNASSESSABLE',
                                         end_time_s=self.last_t, reason=reason, target_status='UNKNOWN',
                                         quality_status='UNASSESSABLE', quality_assessable=False))
            self.current = None
        self.timing = None

    def invalidate(self, reason, *, keep_baseline=False):
        self._break_timing(self.last_t, reason)
        self._partial(reason)
        self._close_standing_timing(reason)
        self.pending_input_gap = None
        self.holds.clear()
        self.ready_values.clear()
        self.issue_starts.clear()
        self.current_issues = []
        self.phase, self.run_state = 'WAIT_READY', 'recovering'
        self.last_value, self.last_good_t, self.gap = None, None, False
        self.latest = None
        self.observation_state = 'missing'
        if not keep_baseline:
            self.baseline = None
            self.calibration_epoch += 1

    def pause(self, reason='user_pause'):
        if self.run_state == 'ended':
            raise ValueError('terminal_session')
        self.invalidate(reason, keep_baseline=True)
        self.pause_reason, self.run_state = reason, 'paused'

    def resume(self, *, preserve_baseline=False):
        if self.run_state != 'paused':
            raise ValueError('not_paused')
        self.invalidate('resume', keep_baseline=preserve_baseline)
        self.pause_reason = None

    def finish(self, reason='user_stopped'):
        if self.pending_input_gap is not None:
            self._break_timing(self.pending_input_gap['time_s'], self.pending_input_gap['reason'])
            self.pending_input_gap = None
        self._partial(reason)
        self._close_standing_timing(reason)
        self.timing_history.clear()
        self.run_state, self.phase = 'ended', 'ENDED'
        self.holds.clear()

    def _ready_posture(self, value):
        if self.spec['exercise_id'] == 'sit_to_stand':
            return value >= self.spec['seated_min_deg']
        return value <= self.spec['ready_max_deg']

    def _new_rep(self, stamp):
        self.current = dict(rep_index=len(self.repetitions)+1, start_time_s=stamp,
                            calibration_epoch=self.calibration_epoch, peak_excursion_deg=0.,
                            peak_metric_deg=0.,
                            evidence_refs=[], metric_validity={}, issues=[],
                            quality_evaluated=False, observed_turn=False,
                            completion_status='PARTIAL', target_status='UNKNOWN')
        seated = self.spec['exercise_id'] == 'sit_to_stand'
        self.timing = MovementTiming(direction=-1 if seated else 1,
                                     max_gap_s=self.plan['max_gap_s'],
                                     target=self.plan['target_angle_deg'],
                                     goals=self.plan['timing_plan'], sit_to_stand=seated)
        # Replay only the observed departure dwell and its preceding sample.
        # Ready time is not part of a repetition's movement time.
        start = self.holds.get('depart', stamp)
        history = list(self.timing_history)
        first = next((i for i, sample in enumerate(history) if sample[0] >= start), len(history))
        for t, value, standing, seq in history[max(0, first-1):]:
            self._add_timing(self.timing, t, value, standing, seq)
        self._update_timing()

    def _collect(self, frame, excursion):
        rep = self.current
        if rep is None:
            return
        rep['peak_excursion_deg'] = max(rep['peak_excursion_deg'], excursion)
        rep['peak_metric_deg'] = max(rep['peak_metric_deg'], frame.metrics[self.spec['metric']].value)
        # Bounded references; exact per-frame provenance belongs in the session checkpoints.
        if len(rep['evidence_refs']) < 256:
            rep['evidence_refs'].append(dict(seq=frame.seq, source_epoch=frame.source_epoch,
                                            time_s=frame.time_s))
        for name, threshold_key in (('elbow_flexion_deg', 'allowed_elbow_flexion_deg'),
                                     ('trunk_tilt_deg', 'allowed_trunk_tilt_deg')):
            if self.phase not in ('RAISING', 'PEAK_OR_HOLD'):
                continue
            limit = self.plan[threshold_key]
            if limit is None:
                continue
            evidence = frame.metrics.get(name)
            valid = (evidence is not None and evidence.observable(self.plan['max_age_ms'])
                     and evidence.observed_at_s == frame.time_s and evidence.unit == 'degree'
                     and tuple(evidence.required_joints) == tuple(self.spec['optional_quality_metrics'].get(name, ())))
            old = rep['metric_validity'].get(name, {'valid': True, 'reason': None})
            rep['metric_validity'][name] = dict(valid=old['valid'] and valid,
                                                reason=old['reason'] or (None if valid else 'missing_quality_evidence'))
            rep['quality_evaluated'] = True
            if not valid or evidence.value <= limit:
                self.issue_starts.pop(name, None)
                continue
            start = self.issue_starts.setdefault(name, frame.time_s)
            if frame.time_s - start + 1e-8 >= self.plan['issue_hold_s']:
                if name not in {item['metric'] for item in rep['issues']}:
                    rep['issues'].append(dict(metric=name, measured_value=evidence.value,
                                              configured_limit=limit, evidence_time_s=frame.time_s,
                                              evidence_seq=frame.seq, rule_id=name.removesuffix('_deg')))
                self.current_issues.append(dict(metric=name, measured_value=evidence.value,
                                                configured_limit=limit, evidence_time_s=frame.time_s,
                                                evidence_seq=frame.seq, rule_id=name.removesuffix('_deg')))

    def _complete(self, stamp):
        rep = self.current
        seated = self.spec['exercise_id'] == 'sit_to_stand'
        if seated:
            self.timing.mark_standing(stamp)
            self.timing.standing_ref = self._timing_ref(self.last_seq, stamp)
        rep['movement_timing'] = self._timing_snapshot(self.timing, 'COMPLETE', cycle_complete=not seated)
        if seated:
            rep.update(rise_time_s=rep['movement_timing']['outbound_s']['value'], lowering_time_s=None)
            self.standing_timing, self.standing_rep = self.timing, rep
        self.timing = None
        target = self.plan['target_angle_deg']
        target_value = rep['peak_excursion_deg'] if self.spec['exercise_id'] == 'sit_to_stand' else rep['peak_metric_deg']
        assessable = (rep['quality_evaluated'] and
                      all(item['valid'] for item in rep['metric_validity'].values()))
        rep.update(end_time_s=stamp, completion_status='COMPLETE',
                   target_status=('NOT_SET' if target is None else 'MET'
                                  if target_value >= target else 'NOT_MET'),
                   quality_assessable=assessable,
                   quality_status=('ISSUES_OBSERVED' if rep['issues'] else 'NO_CONFIGURED_ISSUE_OBSERVED'
                                   if assessable else 'UNASSESSABLE'),
                   plan_progress='confirmed_rep_only', eligibility='not_evaluated_by_counter')
        self.repetitions.append(rep)
        self.current = None
        self.issue_starts.clear()

    def process(self, frame):
        if self.run_state in ('paused', 'ended'):
            return self._reject('paused_or_terminal')
        if frame.source_epoch != self.source_epoch:
            return self._reject('source_epoch_mismatch')
        if (frame.seq <= self.last_seq or not math.isfinite(frame.time_s)
                or (self.last_t is not None and frame.time_s <= self.last_t)):
            return self._reject('old_seq_or_time')
        if frame.coordinate_space != 'raw_image_pixels' or frame.schema_id not in ('coco17-v1', 'mediapipe33-v1'):
            return self._reject('unsupported_input_domain')
        if frame.time_basis not in ('mapped_source_seconds', 'nominal_video_seconds', 'opencv_media_pts'):
            return self._reject('unsupported_time_basis')
        if not frame.model_manifest_id or min(frame.size) <= 0:
            return self._reject('missing_model_or_size')
        signature = (frame.source_ref, frame.schema_id, frame.model_manifest_id, frame.size, frame.time_basis)
        if self.signature is not None and signature != self.signature:
            self.invalidate('measurement_contract_changed')
        self.signature = signature
        if (self.last_track is not None and frame.track_key is not None
                and frame.track_key != self.last_track):
            self.invalidate('participant_changed')
        if frame.track_key is not None:
            self.last_track = frame.track_key
        if self.last_good_t is not None and frame.time_s - self.last_good_t > self.plan['max_gap_s']:
            self.invalidate('long_evidence_gap', keep_baseline=True)
        self.last_seq, self.last_t = frame.seq, frame.time_s
        if self.pending_input_gap is not None and frame.seq > self.pending_input_gap['seq']:
            self._break_timing(frame.time_s, self.pending_input_gap['reason'])
            self.pending_input_gap = None
            self.gap = True
            self.holds.clear()
            self.ready_values.clear()
            self.issue_starts.clear()
        self.current_issues = []
        evidence = frame.metrics.get(self.spec['metric'])
        valid = evidence is not None and evidence.observable(self.plan['max_age_ms']) and frame.track_key is not None
        if not valid:
            self.observation_state = 'missing'
            self.latest = None
            self.gap = True
            self._break_timing(frame.time_s, 'missing_interval')
            self.holds.clear()
            self.ready_values.clear()
            self.issue_starts.clear()
            self.diagnostics['missing_frames'] += 1
            if self.current is not None:
                self.current['metric_validity'][self.spec['metric']] = dict(valid=False, reason='missing_interval')
            return True
        value = evidence.value
        if (not 0 <= value <= 180 or evidence.unit != self.spec['unit'] or evidence.observed_at_s != frame.time_s
                or tuple(evidence.required_joints) != tuple(self.spec['required_joints'])):
            self.observation_state = 'unavailable'
            self.latest = None
            self.gap = True
            self._break_timing(frame.time_s, 'invalid_metric_contract')
            self.holds.clear()
            self.ready_values.clear()
            return self._reject('invalid_metric_contract')
        self.observation_state = ('partially_observable' if any(
            frame.metrics.get(k) is None or not frame.metrics[k].observable(self.plan['max_age_ms'])
            for k in self.spec['optional_quality_metrics']) else 'observable')
        self.latest = asdict(evidence)
        if self.gap and self.last_value is not None:
            seated_action = self.spec['exercise_id'] == 'sit_to_stand'
            delta = value-self.last_value
            hidden_turn = ((seated_action and self.phase == 'RISING' and delta > self.plan['turn_delta_deg'])
                           or (not seated_action and self.phase in ('RAISING', 'PEAK_OR_HOLD')
                               and delta < -self.plan['turn_delta_deg'])
                           or (not seated_action and self.phase == 'LOWERING'
                               and delta > self.plan['turn_delta_deg']))
            if hidden_turn:
                self.invalidate('hidden_motion_boundary', keep_baseline=True)
        self.gap = False
        self.last_good_t, self.last_value = frame.time_s, value
        self._timing_observation(frame, value)
        if self.phase == 'WAIT_READY':
            posture = self._ready_posture(value)
            if posture:
                self.ready_values.append((frame.time_s, value))
            else:
                self.ready_values.clear()
            stable = (len(self.ready_values) >= 2 and
                      max(v for _, v in self.ready_values)-min(v for _, v in self.ready_values) <= 5.)
            if self._held('ready', posture and stable, frame.time_s, self.plan['ready_s']):
                self.baseline = dict(raw_value=median(v for _, v in self.ready_values), unit='degree',
                                     time_s=frame.time_s, reference=self.spec['baseline_reference'],
                                     quality='observed_posture_and_stability',
                                     calibration_epoch=self.calibration_epoch)
                self.phase = 'SEATED_READY' if self.spec['exercise_id'] == 'sit_to_stand' else 'REST'
                self.run_state = 'active'
                self.holds.clear()
            return True
        seated = self.spec['exercise_id'] == 'sit_to_stand'
        excursion = self.baseline['raw_value'] - value if seated else value - self.baseline['raw_value']
        dwell, stamp = self.plan['dwell_s'], frame.time_s
        if self.phase in ('REST', 'SEATED_READY'):
            if self._held('depart', excursion >= self.spec['excursion_min_deg'], stamp, dwell):
                self._new_rep(stamp)
                self.phase = 'RISING' if seated else 'RAISING'
                self.holds.clear()
        self._collect(frame, excursion)
        if seated:
            if self.phase == 'RISING' and self._held('stand', value <= self.spec['standing_max_deg'], stamp, dwell):
                self.current['observed_turn'] = True
                self._complete(stamp)
                self.phase = 'STANDING_REACHED'
                self.holds.clear()
            elif self.phase == 'STANDING_REACHED' and value > self.spec['standing_max_deg'] + 5:
                self.phase = 'LOWERING'
                if self.standing_timing is not None:
                    self.standing_timing.mark_return(stamp)
                    self.standing_timing.return_ref = self._timing_ref(frame.seq, stamp)
                    self._update_timing()
            elif self.phase == 'LOWERING' and self._held('seated', self._ready_posture(value), stamp, dwell):
                if self.standing_timing is not None:
                    self.standing_timing.seated_ref = self._timing_ref(frame.seq, stamp)
                self._close_standing_timing(cycle_complete=True)
                self.phase = 'SEATED_READY'
                self.holds.clear()
        elif self.current is not None:
            if self.phase == 'RAISING':
                turn = excursion < self.current['peak_excursion_deg'] - self.plan['turn_delta_deg']
                if self._held('turn', turn, stamp, dwell):
                    self.current['observed_turn'] = True
                    self.phase = 'LOWERING'
                    self.holds.clear()
            if self.phase == 'LOWERING' and self._held('return', abs(excursion) <= self.plan['return_tolerance_deg'], stamp, dwell):
                self._complete(stamp)
                self.phase = 'REST'
                self.holds.clear()
        return True

    def summary(self):
        return dict(protocol=self.spec, run_state=self.run_state, phase=self.phase,
                    observation_state=self.observation_state, calibration_epoch=self.calibration_epoch,
                    baseline=self.baseline, repetitions=self.repetitions, completed=self.completed,
                    current=self.current, metric=self.latest, diagnostics=self.diagnostics,
                    current_issues=self.current_issues,
                    movement_timing_version=TIMING_VERSION,
                    movement_timing_live=self.timing_live(),
                    last_movement_timing=(self.repetitions[-1].get('movement_timing')
                                          if self.repetitions else None),
                    pending_input_gap=self.pending_input_gap,
                    measurement_contract=dict(signature=self.signature, coordinate_space='raw_image_pixels',
                                              metric_version=self.spec['metric_version'],
                                              preprocess_version='causal-ema-schema-0.3.0',
                                              view=self.spec['view'], side=self.spec['side']),
                    target_result_separate=True, quality_result_separate=True,
                    eligibility='unchanged_requires_existing_plan_validation')
