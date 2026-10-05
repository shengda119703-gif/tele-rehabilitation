"""Bound, read-only Agent tools over existing rehabilitation business readers."""
from pathlib import Path

from .assessment import build_body_profile, session_value, session_conditions, COMPARISON_NOTE
from .assessment_batches import scope_key
from .automatic_plans import program_progress, validate_automatic_use
from .exercises import exercise_spec, EXERCISE_IDS
from .storage import Storage
from .training_plans import training_plan_view


TOOLS = ('rehab.get_training_plan', 'rehab.get_recent_assessments', 'rehab.get_training_history')


def pick(value, keys):
    return {key: value.get(key) for key in keys}


class RehabReadTools:
    """Scope comes from the desktop, never from model arguments. No write methods."""
    def __init__(self, database, scope):
        self.database = Path(database).resolve()
        self.scope = scope_key(scope)

    def __call__(self, name, arguments):
        return self._read(name, arguments)

    def desktop_snapshot(self):
        """Full scoped UI readers; keep Agent argument contracts and result limits unchanged."""
        return {name: self._read(name, {}, desktop=True) for name in TOOLS}

    def _read(self, name, arguments, *, desktop=False):
        if name not in TOOLS or not isinstance(arguments, dict) or set(arguments) - {'exercise_id', 'joint'}:
            raise ValueError('Unknown read-only rehab tool or arguments')
        exercise = arguments.get('exercise_id')
        if exercise is not None:
            exercise_spec(exercise)
        joint = arguments.get('joint')
        if joint is not None and joint not in {exercise_spec(e)['joint'] for e in EXERCISE_IDS}:
            raise ValueError('Unknown joint')
        result = dict(tool=name, scope=dict(self.scope), read_only=True, status='empty', records=[])
        if not self.database.is_file():
            return result
        store = Storage(self.database, readonly=True)
        try:
            sessions = [s for s in store.list_sessions() if s.get('scene_id') == 'rehab'
                        and all(session_value(s, k) == v for k, v in self.scope.items())]
            if name == TOOLS[0]:
                profile = build_body_profile(sessions, **self.scope)
                plans = store.list_training_plans(self.scope)
                # Saved ACTIVE plans, latest first. Do not generate or accept a proposal.
                for plan in plans if desktop else plans[:3]:
                    view = training_plan_view(plan, profile)
                    progress = program_progress(plan, sessions)
                    ready, reason = False, progress['blocked']
                    next_item = next((i for i in view['items'] if i['key'] == progress['next_key']), None)
                    if next_item and not reason:
                        ready, reason = next_item['available'], next_item['availability_reason']
                        if ready and plan.get('record_origin') == 'assessment_rules':
                            try:
                                # Existing pure validation recomputes evidence but never saves a new plan.
                                validate_automatic_use(plan, next_item['key'], profile, sessions,
                                                       store.get_participant(self.scope['participant_id']))
                            except ValueError as error:
                                ready, reason = False, str(error)
                    result['records'].append(dict(
                        **pick(view, ('id', 'revision', 'name', 'status', 'record_origin', 'created_utc')),
                        items=[pick(i, ('key', 'exercise_id', 'exercise_label', 'side', 'settings',
                                        'available', 'availability_reason')) for i in view['items']],
                        progress=progress, has_next=bool(next_item), next_available=ready,
                        availability_reason=reason))
            elif name == TOOLS[1]:
                profile = build_body_profile(sessions, **self.scope)
                items = [i for i in profile['items'] if i.get('session_id')
                         and (not exercise or i['exercise_id'] == exercise)
                         and (not joint or i['joint'] == joint)]
                if desktop:
                    # Reuse the same assessment interpretation for each saved assessment,
                    # including invalid records; never compare incompatible conditions here.
                    items = []
                    for s in sessions:
                        if session_value(s,'submode')!='assessment' or not s.get('end_utc') or s.get('status') not in ('FINISHED','INTERRUPTED','COMPLETED'):
                            continue
                        values=[i for i in build_body_profile([s], **self.scope)['items'] if i.get('session_id')]
                        if not values:
                            eid=session_value(s,'exercise_id')
                            if eid not in EXERCISE_IDS:continue
                            # Keep non-measurement attempts in history without granting assessment evidence.
                            values=[dict(session_id=s['id'],exercise_id=eid,exercise_label=exercise_spec(eid)['label'],
                                side=session_value(s,'side'),start_utc=s.get('start_utc'),end_utc=s['end_utc'],
                                status='NOT_ASSESSED',reason='没有自动评估依据，请查看原报告',
                                measurement_note='引导活动记录不作为自动评估依据' if s.get('measurement_mode')=='guided_timed' else '请核对原测量条件',
                                conditions=session_conditions(s))]
                        items.extend(values)
                items.sort(key=lambda i: i.get('end_utc') or '', reverse=True)
                for item in items if desktop else items[:6]:
                    row = pick(item, ('exercise_id', 'exercise_label', 'side', 'status', 'reason',
                                      'session_id', 'start_utc', 'end_utc', 'motion_range',
                                      'primary_metric', 'valid_ratio', 'completed', 'measurement_note'))
                    source = next(s for s in sessions if s['id'] == item['session_id'])
                    row['measurement_mode'] = source.get('measurement_mode')
                    # Keep comparison provenance; omit file/device identifiers from model context.
                    row['conditions'] = pick(item.get('conditions') or {}, (
                        'measurement_contract', 'view', 'rule_version', 'schema_id',
                        'model_manifest_id', 'capture_mode', 'coordinate_space'))
                    result['records'].append(row)
                result['comparison_note'] = COMPARISON_NOTE
                result['comparison_performed'] = False
            else:
                rows = [s for s in sessions if session_value(s, 'submode') == 'training'
                        and s.get('end_utc') and (not exercise or session_value(s, 'exercise_id') == exercise)
                        and (not joint or exercise_spec(session_value(s, 'exercise_id'))['joint'] == joint)]
                rows.sort(key=lambda s: s.get('end_utc') or '', reverse=True)
                for session in rows if desktop else rows[:5]:
                    eid = session_value(session, 'exercise_id')
                    result['records'].append(dict(
                        **pick(session, ('id', 'start_utc', 'end_utc', 'status', 'measurement_mode', 'stop_reason')),
                        exercise_id=eid, exercise_label=exercise_spec(eid)['label'],
                        side=session_value(session, 'side'),
                        summary=pick(session.get('summary') or {}, (
                            'completed', 'partial', 'invalid', 'completed_sets', 'plan_completed', 'valid_ratio')),
                        training_feedback=pick(session.get('training_feedback') or {}, (
                            'pain', 'fatigue', 'reason', 'notes', 'record_origin', 'revision', 'updated_utc'))))
                    if desktop:
                        result['records'][-1]['plan_reference']=pick(session_value(session,'saved_plan_reference') or {}, ('id','revision','entry_key'))
            result['status'] = 'found' if result['records'] else 'empty'
            return result
        finally:
            store.close()
