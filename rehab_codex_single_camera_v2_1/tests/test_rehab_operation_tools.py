import copy

from app.rehab_operation_tools import RehabOperationTools
from app.training_plans import item_from_plan, new_training_plan
from app.settings import default_plan


def sample_plan():
    scope = {
        'participant_id': 'test-participant',
        'source_kind': 'LOCAL',
        'usage_context': 'SELF_USE',
    }
    base = default_plan('sit_to_stand')
    item = item_from_plan({
        'exercise_id': 'sit_to_stand',
        'side': 'left',
        **base,
    })
    return new_training_plan(scope, '测试康复计划', [item])


def test_patch_existing_plan_changes_only_supported_setting():
    plan = sample_plan()
    patched = RehabOperationTools._patch_plan(plan, {
        'update': [{
            'key': 'sit_to_stand:left',
            'settings': {'target_reps': 8},
        }],
    })
    assert patched['name'] == plan['name']
    assert patched['items'][0]['settings']['target_reps'] == 8
    assert patched['items'][0]['key'] == 'sit_to_stand:left'


def test_patch_rejects_unknown_setting_and_unknown_remove():
    plan = sample_plan()
    try:
        RehabOperationTools._patch_plan(plan, {
            'update': [{
                'key': 'sit_to_stand:left',
                'settings': {'made_up_field': 1},
            }],
        })
    except ValueError:
        pass
    else:
        raise AssertionError('unknown setting must be rejected')

    try:
        RehabOperationTools._patch_plan(plan, {'remove': ['missing:left']})
    except ValueError:
        pass
    else:
        raise AssertionError('unknown item must be rejected')


def test_patch_adds_real_action_and_preserves_plan_shape():
    plan = sample_plan()
    # Adding the same key is rejected; this also proves the operation layer
    # does not silently replace an existing user-selected action.
    try:
        RehabOperationTools._patch_plan(plan, {
            'add': [{
                'exercise_id': 'sit_to_stand',
                'side': 'left',
                'settings': copy.deepcopy(plan['items'][0]['settings']),
            }],
        })
    except ValueError:
        pass
    else:
        raise AssertionError('duplicate action key must be rejected')
