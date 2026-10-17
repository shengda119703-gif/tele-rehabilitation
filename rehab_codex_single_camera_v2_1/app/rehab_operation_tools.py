"""Confirmed, owner-scoped rehabilitation program operations.
The LLM may propose operations, but this host validates and executes them only after explicit confirmation.
"""
from __future__ import annotations

import copy
import re
from datetime import date

from .assessment_batches import scope_key
from .exercises import exercise_spec
from .settings import default_plan
from .storage import Storage
from .training_plans import item_from_plan, validate_training_plan
from .product.daily_store import DailyStore


TOOLS = ('rehab.get_schedule', 'rehab.plan.change', 'rehab.schedule.upsert', 'rehab.schedule.remove')
PLAN_SETTING_FIELDS = {
    'target_reps', 'target_sets', 'rest_between_sets_s', 'target_angle_deg',
    'allowed_elbow_flexion_deg', 'allowed_trunk_tilt_deg',
    'lowering_tempo_min_s', 'lowering_tempo_max_s', 'use_of_hands',
    'needs_companion', 'sound_enabled', 'timing_plan',
}


class RehabOperationTools:
    def __init__(self, database, scope, daily: DailyStore, owner: str):
        self.database = database
        self.scope = scope_key(scope)
        if self.scope.get('participant_id') != owner:
            raise ValueError('康复操作用户范围不一致')
        self.daily = daily
        self.owner = owner

    def __call__(self, name, arguments):
        if not isinstance(arguments, dict):
            raise ValueError('康复程序操作参数无效')
        if name not in TOOLS:
            raise ValueError('未注册的康复程序工具')
        if name == 'rehab.get_schedule':
            return self._get_schedule()
        if name == 'rehab.plan.change':
            return self._plan_change(arguments)
        if name == 'rehab.schedule.upsert':
            return self._schedule_upsert(arguments)
        return self._schedule_remove(arguments)

    def _get_schedule(self):
        snapshot = self.daily.snapshot(self.owner, self.scope)
        entries = snapshot.get('schedules') or []
        return {
            'tool': 'rehab.get_schedule',
            'scope': dict(self.scope),
            'read_only': True,
            'status': 'found' if entries else 'empty',
            'records': entries[-50:],
        }

    def _open_plan(self, plan_id, expected_revision, *, readonly=True):
        if not isinstance(plan_id, str) or not re.fullmatch(r'[0-9a-f]{32}', plan_id):
            raise ValueError('计划编号无效')
        if type(expected_revision) is not int or expected_revision < 0:
            raise ValueError('计划版本无效')
        store = Storage(self.database, readonly=readonly)
        try:
            current = store.get_training_plan(plan_id)
            if not current or scope_key(current) != self.scope:
                raise ValueError('计划不存在或不属于当前用户与来源')
            if current.get('status') != 'ACTIVE':
                raise ValueError('只能修改当前有效的康复计划')
            if current.get('revision') != expected_revision:
                raise ValueError('计划已变化，请重新读取后再操作')
            return store, current
        except Exception:
            store.close()
            raise

    @staticmethod
    def _patch_plan(current, patch):
        if not isinstance(patch, dict):
            raise ValueError('计划修改内容无效')
        if set(patch) - {'name', 'add', 'update', 'remove'}:
            raise ValueError('计划修改字段无效')
        if current.get('doctor_publication') and any(patch.get(k) for k in ('add', 'update', 'remove')):
            raise ValueError('医生方案的动作与剂量须由医生重新审核发布，不能由本人确认修改')
        candidate = copy.deepcopy(current)
        if 'name' in patch:
            name = patch['name']
            if not isinstance(name, str) or not name.strip() or len(name.strip()) > 80:
                raise ValueError('计划名称无效')
            candidate['name'] = name.strip()

        items = list(candidate['items'])
        by_key = {item['key']: item for item in items}

        for key in patch.get('remove', []) or []:
            if not isinstance(key, str) or key not in by_key:
                raise ValueError('要删除的训练项目不存在')
            items = [item for item in items if item['key'] != key]
            by_key.pop(key, None)

        for change in patch.get('update', []) or []:
            if not isinstance(change, dict) or not isinstance(change.get('key'), str) or not isinstance(change.get('settings'), dict):
                raise ValueError('训练项目修改内容无效')
            key = change['key']
            old = by_key.get(key)
            if old is None:
                raise ValueError('要修改的训练项目不存在')
            if set(change['settings']) - PLAN_SETTING_FIELDS:
                raise ValueError('训练项目参数字段无效')
            merged = copy.deepcopy(old['settings'])
            merged.update(copy.deepcopy(change['settings']))
            rebuilt = item_from_plan({
                'exercise_id': old['exercise_id'],
                'side': old['side'],
                **merged,
            })
            items = [rebuilt if item['key'] == key else item for item in items]
            by_key[key] = rebuilt

        for change in patch.get('add', []) or []:
            if not isinstance(change, dict):
                raise ValueError('新增训练项目无效')
            eid, side = change.get('exercise_id'), change.get('side')
            if not isinstance(eid, str) or side not in ('left', 'right'):
                raise ValueError('新增训练项目的动作或侧别无效')
            spec = exercise_spec(eid)
            if not isinstance(change.get('settings', {}), dict):
                raise ValueError('新增训练项目参数无效')
            defaults = default_plan(eid)
            settings = {k: copy.deepcopy(defaults[k]) for k in PLAN_SETTING_FIELDS if k in defaults}
            settings.update(copy.deepcopy(change.get('settings') or {}))
            if set(settings) - PLAN_SETTING_FIELDS:
                raise ValueError('新增训练项目参数字段无效')
            rebuilt = item_from_plan({'exercise_id': eid, 'side': side, **settings})
            if rebuilt['key'] in by_key:
                raise ValueError('该动作与侧别已经存在于当前计划')
            items.append(rebuilt)
            by_key[rebuilt['key']] = rebuilt

        candidate['items'] = items
        return validate_training_plan(candidate)

    @staticmethod
    def _diff(before, after):
        before_items = {i['key']: i for i in before['items']}
        after_items = {i['key']: i for i in after['items']}
        return {
            'name': {'from': before['name'], 'to': after['name']} if before['name'] != after['name'] else None,
            'added': sorted(set(after_items) - set(before_items)),
            'removed': sorted(set(before_items) - set(after_items)),
            'updated': sorted(k for k in set(before_items) & set(after_items)
                              if before_items[k] != after_items[k]),
        }

    def _plan_change(self, args):
        store, current = self._open_plan(args.get('plan_id'), args.get('expected_revision'), readonly=args.get('commit') is not True)
        try:
            candidate = self._patch_plan(current, args.get('patch'))
            preview = {
                'status': 'preview',
                'plan_id': current['id'],
                'expected_revision': current['revision'],
                'next_revision': current['revision'] + 1,
                'before': {'name': current['name'], 'items': copy.deepcopy(current['items'])},
                'after': {'name': candidate['name'], 'items': copy.deepcopy(candidate['items'])},
                'diff': self._diff(current, candidate),
            }
            if args.get('commit') is not True:
                return preview
            saved = store.save_training_plan(candidate, expected_revision=current['revision'])
            return {
                'status': 'applied',
                'plan_id': saved['id'],
                'revision': saved['revision'],
                'diff': preview['diff'],
            }
        finally:
            store.close()

    def _validate_schedule_plan(self, plan_id, plan_revision):
        store, current = self._open_plan(plan_id, plan_revision, readonly=True)
        store.close()
        return current

    def _schedule_upsert(self, args):
        plan_id, plan_revision = args.get('plan_id'), args.get('plan_revision')
        current = self._validate_schedule_plan(plan_id, plan_revision)
        schedule_id = args.get('id')
        if schedule_id is not None and (not isinstance(schedule_id, str) or not schedule_id.strip()):
            raise ValueError('安排编号无效')
        day, clock = args.get('date'), args.get('time')
        if not isinstance(day, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', day):
            raise ValueError('训练日期无效')
        if not isinstance(clock, str) or not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d', clock):
            raise ValueError('训练时间无效')
        if date.fromisoformat(day) < date.today():
            raise ValueError('不能新增过去日期的康复安排')
        name = args.get('name') or current['name']
        payload = {
            'id': schedule_id,
            'date': day,
            'time': clock,
            'kind': 'training',
            'name': name,
            'planId': plan_id,
            'revision': plan_revision,
        }
        snapshot = self.daily.snapshot(self.owner, self.scope)
        existing = next((e for e in snapshot.get('schedules', []) if e.get('id') == schedule_id), None) if schedule_id else None
        if 'expected_existing' in args and args.get('expected_existing') != existing:
            raise ValueError('训练安排已变化，请重新读取后操作')
        preview = {
            'status': 'preview',
            'operation': 'rehab.schedule.upsert',
            'schedule': payload,
            'previous': existing,
        }
        if args.get('commit') is not True:
            return preview
        result = self.daily.apply(self.owner, 'daily.schedule', payload, self.scope,
                                  **({'expected_existing': args['expected_existing']} if 'expected_existing' in args else {}))
        return {'status': 'applied', 'operation': 'rehab.schedule.upsert', 'schedule': result['schedule']}

    def _schedule_remove(self, args):
        schedule_id = args.get('id')
        if not isinstance(schedule_id, str) or not schedule_id.strip():
            raise ValueError('安排编号无效')
        snapshot = self.daily.snapshot(self.owner, self.scope)
        existing = next((e for e in snapshot.get('schedules', []) if e.get('id') == schedule_id), None)
        if not existing:
            raise ValueError('安排不存在或已经变化')
        if 'expected_existing' in args and args.get('expected_existing') != existing:
            raise ValueError('训练安排已变化，请重新读取后操作')
        preview = {'status': 'preview', 'operation': 'rehab.schedule.remove', 'schedule': existing}
        if args.get('commit') is not True:
            return preview
        self.daily.apply(self.owner, 'daily.unschedule', {'id': schedule_id}, self.scope,
                         **({'expected_existing': args['expected_existing']} if 'expected_existing' in args else {}))
        return {'status': 'applied', 'operation': 'rehab.schedule.remove', 'schedule': existing}
