"""Versioned manual training arrangements, separate from live setup/consent."""
from __future__ import annotations

import copy
import math
import re
from uuid import uuid4

from .assessment import build_training_reference
from .assessment_batches import scope_key
from .exercises import exercise_spec
from .settings import default_plan
from .movement_timing import timing_for_plan


PRESCRIPTION_FIELDS = (
    'target_reps', 'target_sets', 'rest_between_sets_s', 'target_angle_deg',
    'allowed_elbow_flexion_deg', 'allowed_trunk_tilt_deg',
    'lowering_tempo_min_s', 'lowering_tempo_max_s', 'use_of_hands',
    'needs_companion', 'sound_enabled', 'timing_plan',
)


def prescription_settings(value, exercise_id):
    if not isinstance(value, dict):
        raise ValueError('训练安排内容无效')
    defaults = default_plan(exercise_id)
    result = {key: copy.deepcopy(value.get(key, defaults[key])) for key in PRESCRIPTION_FIELDS}
    for key, maximum in (('target_reps', 999), ('target_sets', 20)):
        if type(result[key]) is not int or not 1 <= result[key] <= maximum:
            raise ValueError('训练次数应为 1–999，组数应为 1–20 的整数')
    for key, maximum in (('rest_between_sets_s', 1800), ('target_angle_deg', 180),
                         ('allowed_elbow_flexion_deg', 180), ('allowed_trunk_tilt_deg', 90),
                         ('lowering_tempo_min_s', 60), ('lowering_tempo_max_s', 60)):
        number = result[key]
        if number is not None and (type(number) not in (int, float) or not math.isfinite(number)
                                   or not 0 <= number <= maximum):
            raise ValueError('计划中的角度或时间超出可填写范围，请重新核对；未指定时留空')
    low, high = result['lowering_tempo_min_s'], result['lowering_tempo_max_s']
    if low is not None and high is not None and low > high:
        raise ValueError('节奏最短时间不能大于最长时间')
    if exercise_id != 'sit_to_stand' and (low is not None or high is not None):
        raise ValueError('下降节奏安排当前只用于坐站，请清除不适用的设置')
    for key in ('needs_companion', 'sound_enabled'):
        if type(result[key]) is not bool:
            raise ValueError('陪同和提示音设置应为明确的开关')
    if result['use_of_hands'] not in ('not_recorded', 'allowed', 'not_allowed', 'used_hands'):
        raise ValueError('扶物安排无效，请重新选择')
    result['timing_plan'] = timing_for_plan(dict(result, exercise_id=exercise_id))
    return result


def item_from_plan(plan):
    if not isinstance(plan, dict):
        raise ValueError('请选择一个训练项目')
    eid, side = plan.get('exercise_id'), plan.get('side')
    spec = exercise_spec(eid)
    if side not in ('left', 'right'):
        raise ValueError('请选择本人左侧或右侧')
    return {'key': eid+':'+side, 'exercise_id': eid, 'side': side,
            'measurement_contract': spec['measurement_contract'],
            'settings': prescription_settings(plan, eid)}


def validate_training_plan(value):
    if not isinstance(value, dict) or type(value.get('schema_version')) is not int or value['schema_version'] != 1:
        raise ValueError('计划格式无效，请重新打开计划库')
    scope = scope_key(value)
    pid, name = value.get('id'), value.get('name')
    if not isinstance(pid, str) or not re.fullmatch(r'[0-9a-f]{32}', pid):
        raise ValueError('计划编号无效')
    if not isinstance(name, str) or not name.strip() or len(name.strip()) > 80:
        raise ValueError('请填写 1–80 字的计划名称')
    entries = value.get('items')
    if not isinstance(entries, list) or not 1 <= len(entries) <= 106:
        raise ValueError('请至少添加一个训练项目，最多 106 项')
    items, seen = [], set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError('训练项目内容无效')
        eid = entry.get('exercise_id')
        spec = exercise_spec(eid)
        if entry.get('measurement_contract') != spec['measurement_contract']:
            raise ValueError('项目的测量定义已变化，请编辑并核对该项目后再保存')
        settings = entry.get('settings')
        if not isinstance(settings, dict) or any(k not in settings for k in PRESCRIPTION_FIELDS if k != 'timing_plan'):
            raise ValueError('项目安排不完整，请重新填写；不会自动补入训练目标')
        row = item_from_plan(dict(settings, exercise_id=eid, side=entry.get('side')))
        if entry.get('key') != row['key'] or row['key'] in seen:
            raise ValueError('训练项目侧别无效或重复，请逐项核对')
        seen.add(row['key'])
        items.append(row)
    result = dict(scope, id=pid, name=name.strip(), items=items, schema_version=1, record_origin='manual')
    if value.get('record_origin') == 'assessment_rules':
        from .automatic_plans import validate_metadata
        result.update(record_origin='assessment_rules', automatic=copy.deepcopy(value.get('automatic')))
        result['automatic'] = validate_metadata(result)
    return result


def new_training_plan(scope, name, items):
    result = validate_training_plan(dict(scope_key(scope), id=uuid4().hex, name=name,
                                         items=copy.deepcopy(items), schema_version=1))
    result.update(revision=0, status='ACTIVE')
    return result


def _selected_item(record, entry_key, scope):
    if (not isinstance(record, dict) or record.get('status') != 'ACTIVE'
            or scope_key(record) != scope_key(scope)):
        raise ValueError('计划已归档或不属于当前用户与来源，请重新选择')
    entry = next((i for i in record['items'] if i['key'] == entry_key), None)
    if entry is None:
        raise ValueError('计划中没有当前训练项目，请重新选择')
    if entry['measurement_contract'] != exercise_spec(entry['exercise_id'])['measurement_contract']:
        raise ValueError('训练项目的测量定义已变化，请重新编辑并核对计划')
    return entry


def _reference(record, entry):
    result = dict(scope_key(record), schema_version=1, id=record['id'], revision=record['revision'],
                name=record['name'], entry_key=entry['key'], item=copy.deepcopy(entry),
                record_origin=record.get('record_origin', 'manual'), session_overrides={})
    if result['record_origin'] == 'assessment_rules':
        result['automatic'] = copy.deepcopy(record['automatic'])
    return result


def prepare_training_plan(record, entry_key, profile):
    entry = _selected_item(record, entry_key, profile)
    reference = build_training_reference(profile, entry['exercise_id'], entry['side'])
    if reference.get('status') != 'ASSESSED' or not reference.get('session_id'):
        raise ValueError('此项目当前没有有效评估，请先评估或补测，再使用计划')
    if (reference.get('conditions') or {}).get('measurement_contract') != entry['measurement_contract']:
        raise ValueError('评估与当前测量定义不一致，请重新评估后再使用计划')
    plan = default_plan(entry['exercise_id'])
    plan.update(prescription_settings(entry['settings'], entry['exercise_id']))
    plan.update(participant_id=record['participant_id'], side=entry['side'], submode='training',
                assessment_reference=reference, training_plan_confirmed=False,
                saved_plan_reference=_reference(record, entry))
    return plan


def validate_saved_binding(record, supplied, execution, scope):
    """Rebuild provenance at start; a modified live plan remains an explicit override."""
    if (not isinstance(record, dict) or not isinstance(supplied, dict)
            or supplied.get('id') != record.get('id')
            or type(supplied.get('revision')) is not int or supplied['revision'] != record.get('revision')):
        raise ValueError('保存的计划已更新，请回到计划库重新选择并确认')
    entry = _selected_item(record, supplied.get('entry_key'), scope)
    if (execution.get('exercise_id'), execution.get('side'), execution.get('participant_id')) != (
            entry['exercise_id'], entry['side'], record['participant_id']):
        raise ValueError('来源计划与当前用户、动作或侧别不一致，请重新选择')
    settings = prescription_settings(execution, entry['exercise_id'])
    saved = prescription_settings(entry['settings'], entry['exercise_id'])
    reference = _reference(record, entry)
    reference['session_overrides'] = {k: {'saved': copy.deepcopy(saved[k]), 'used': copy.deepcopy(v)}
                                      for k, v in settings.items() if v != saved[k]}
    return reference


def training_plan_view(record, profile):
    """Annotate current availability, without changing the saved arrangement."""
    result = copy.deepcopy(record)
    for entry in result['items']:
        spec = exercise_spec(entry['exercise_id'])
        entry['exercise_label'] = spec['label']
        try:
            prepare_training_plan(record, entry['key'], profile)
        except ValueError as exc:
            entry.update(available=False, availability_reason=str(exc))
        else:
            entry.update(available=True, availability_reason='可准备；仍需确认本次计划与机位')
    return result
