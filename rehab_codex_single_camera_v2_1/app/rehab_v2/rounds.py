from __future__ import annotations

from .engine import ProtocolEngine


class TrainingRounds(ProtocolEngine):
    """Versioned orchestration of explicitly supplied dose, never a generator.

    It uses ProtocolEngine's confirmed reps and independent targets/quality.
    Sit-to-stand counts at standing but completes a set after observed recovery.
    The original TrainingEngine/automatic eligibility/progress remain unchanged.
    """
    def __init__(self, plan, **kw):
        for key, maximum in (('target_reps', 999), ('target_sets', 20)):
            if type(plan.get(key)) is not int or not 1 <= plan[key] <= maximum:
                raise ValueError('explicit_bounded_training_dose_required')
        rest = plan.get('rest_between_sets_s')
        if rest is not None and (type(rest) not in (int, float) or not 0 <= rest <= 1800):
            raise ValueError('invalid_rest_arrangement')
        super().__init__(plan, **kw)
        self.training_stage = 'ACTIVE'
        self.completed_sets = 0
        self.set_start_count = 0
        self.sets = []
        self.rest_started_s = None
        self.paused_from_stage = None

    def process(self, frame):
        if self.training_stage not in ('ACTIVE', 'RECOVERY'):
            return self._reject('training_stage_not_accepting_evidence')
        accepted = super().process(frame)
        if self.completed-self.set_start_count >= self.plan['target_reps']:
            if self.spec['exercise_id'] == 'sit_to_stand' and self.phase != 'SEATED_READY':
                self.training_stage = 'RECOVERY'
            else:
                self.completed_sets += 1
                self.sets.append(dict(number=self.completed_sets, confirmed_reps=self.completed-self.set_start_count,
                                      end_time_s=frame.time_s, completion_status='COMPLETE',
                                      quality_does_not_rewrite_rep_count=True))
                if self.completed_sets >= self.plan['target_sets']:
                    self.training_stage = 'COMPLETE'
                else:
                    self.rest_started_s = frame.time_s
                    super().pause('between_sets')
                    self.training_stage = 'RESTING'
        return accepted

    def pause(self, reason='user_pause'):
        self.paused_from_stage = self.training_stage
        super().pause(reason)
        self.training_stage = 'PAUSED'

    def resume(self, *, preserve_baseline=False, source_time_s=None):
        prior = self.paused_from_stage if self.training_stage == 'PAUSED' else self.training_stage
        if prior == 'RESTING':
            rest = self.plan.get('rest_between_sets_s') or 0.
            if source_time_s is None or source_time_s-self.rest_started_s+1e-8 < rest:
                raise ValueError('prescribed_rest_not_finished')
            self.set_start_count = self.completed
        if prior == 'COMPLETE':
            raise ValueError('training_already_complete')
        super().resume(preserve_baseline=False)
        self.training_stage = 'ACTIVE'
        self.paused_from_stage = None

    def finish(self, reason='user_stopped'):
        super().finish(reason)
        self.training_stage = 'FINISHED'

    def summary(self):
        value = super().summary()
        value['training'] = dict(stage=self.training_stage, completed_sets=self.completed_sets,
                                 target_sets=self.plan['target_sets'], target_reps=self.plan['target_reps'],
                                 sets=self.sets, rest_started_s=self.rest_started_s,
                                 prescribed_rest_s=self.plan.get('rest_between_sets_s'),
                                 plan_complete=self.completed_sets == self.plan['target_sets'],
                                 progress_policy='confirmed_sets-2-not-legacy-progress')
        return value
