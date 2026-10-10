from __future__ import annotations

from uuid import uuid4

from ..guidance import GuidancePolicy


class CueEvents:
    """Backend event envelope; no playback, LLM or second quality-rule engine."""
    policy_version = 'rehab-cue-events-2'

    def __init__(self, session_id):
        self.session_id = session_id
        self.policy = GuidancePolicy()
        self.current = None
        self.last_emission, self.last_key = None, None
        self.history = []

    def cancel(self, reason):
        if self.current:
            self.history.append(dict(cue_id=self.current['cue_id'], event='cancel', reason=reason))
        self.current = None

    def update(self, engine, frame, *, emission_monotonic):
        spec, plan, phase = engine.spec, engine.plan, engine.phase
        if (engine.run_state in ('paused', 'ended') or engine.observation_state in ('missing', 'unavailable')
                or getattr(engine, 'training_stage', None) in ('COMPLETE', 'RESTING', 'FINISHED')):
            self.cancel('state_or_evidence_invalid')
            return None
        if self.current and (phase not in self.current['valid_phases']
                             or frame.time_s > self.current['expires_at_source_s']
                             or self.current['calibration_epoch'] != engine.calibration_epoch):
            self.cancel('phase_epoch_or_ttl')
        summary = dict(phase=phase, training={'stage': 'ACTIVE'},
                       current_issues=engine.current_issues,
                       message='当前已观察到超出安排的姿势' if engine.current_issues else '')
        if spec['exercise_id'] == 'rehab_squat':
            key = 'start' if phase == 'WAIT_READY' else 'return' if phase == 'LOWERING' else 'move'
            instruction = {'start': '保持站姿，准备好后屈膝。', 'move': '缓慢屈膝，到舒适范围。',
                           'return': '缓慢伸膝，回到站姿。'}[key]
            result = dict(cue_key=key, instruction=instruction, level='action')
        else:
            result = self.policy.render(dict(context=(self.session_id, engine.calibration_epoch),
                                              state='ONLINE', summary=summary,
                                              current_measurement_valid=True), plan, now=frame.time_s)
        key = result.get('cue_key') or result.get('level')
        if result.get('level') == 'adjust' and engine.current_issues:
            key = 'adjust:'+engine.current_issues[0]['rule_id']
        if not key:
            return self.current
        changed = key != self.last_key
        cooldown = plan['feedback_cooldown_s'] if result.get('level') == 'adjust' else 2.
        if not changed and self.last_emission is not None and emission_monotonic-self.last_emission < cooldown:
            return self.current
        self.cancel('superseded')
        self.current = dict(cue_id=uuid4().hex, cue_key=key, session_id=self.session_id,
                            exercise_id=spec['exercise_id'], side=spec['side'],
                            calibration_epoch=engine.calibration_epoch,
                            evidence_refs=[dict(seq=frame.seq, metric=(engine.current_issues[0]['metric']
                                                                      if result.get('level') == 'adjust'
                                                                      and engine.current_issues else spec['metric']))],
                            evidence_time_s=frame.time_s, observed_phase=phase, valid_phases=[phase],
                            priority=60 if result.get('level') == 'adjust' else 20,
                            expires_at_source_s=frame.time_s+2., ttl_after_emission_ms=2000,
                            requires_response=False, policy_version=self.policy_version,
                            instruction=result['instruction'])
        self.last_emission, self.last_key = emission_monotonic, key
        self.history.append(dict(self.current, event='emit'))
        self.history = self.history[-256:]
        return self.current

    def query(self, *, source_time_s, emission_age_ms, phase, calibration_epoch):
        value = self.current
        if value and (source_time_s > value['expires_at_source_s'] or emission_age_ms > value['ttl_after_emission_ms']
                      or phase not in value['valid_phases'] or calibration_epoch != value['calibration_epoch']):
            self.cancel('query_expired')
        return self.current
