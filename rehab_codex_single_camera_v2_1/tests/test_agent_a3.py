"""A3 contract tests. Synthetic semantic outputs are not live model accuracy tests."""
import copy
import json
import random

import pytest

from app.agent_grounding import GroundingError, validate_interpretation
from app.agent_state import ConversationState
from app.agent_statements import StatementSession
from app.silver_store import SilverStore
from test_automatic_plans import SCOPE
from statement_fixtures import CONFIG, interpretation, statement, source


def test_no_confirmation_no_write_for_arbitrary_grounded_text(tmp_path):
    care = SilverStore(tmp_path/'support.sqlite3')
    s = StatementSession(SCOPE, lambda: care, conversation_id='property')
    rng = random.Random(730)
    for _ in range(40):
        text = ''.join(rng.choice('甲乙🙂123 xyz') for _ in range(20))
        result = s.turn(text, config=CONFIG, transport=lambda c, m:
                        json.dumps(interpretation(text), ensure_ascii=False))
        assert len(result['proposed_actions']) == 1
        assert not care.records(SCOPE, 'agent_self_report')
    assert len(s.state.turns) <= 6 and len(s.state.events) <= 12


@pytest.mark.parametrize('text', ['我刚才说错了，其实没有发烧', '纠正一下，上面的描述不是真的', '那条自述有误，请撤回'])
def test_correction_equivalence_requires_ref_and_confirmation(tmp_path, text):
    care = SilverStore(tmp_path/'support.sqlite3')
    s = StatementSession(SCOPE, lambda: care)
    first = s.turn('我今天发烧', config=CONFIG, transport=lambda c, m: json.dumps(interpretation('我今天发烧')))
    saved = s.act(first['proposed_actions'][0]['id'])
    old = copy.deepcopy(care.records(SCOPE, 'agent_self_report')[0])
    target = old['id']
    payload = interpretation(text, act='correction', target=target)
    result = s.turn(text, config=CONFIG, transport=lambda c, m: json.dumps(payload))
    assert result['dialogue_act'] == 'correction'
    assert result['understanding'][0]['relation']['type'] == 'corrects'
    assert care.records(SCOPE, 'agent_self_report') == [old]
    assert result['proposed_actions'][0]['operation'] == 'retract'
    s.act(result['proposed_actions'][0]['id'])
    current = care.get(SCOPE, 'agent_self_report', target)
    assert current['status'] == 'RETRACTED' and current['claim'] == old['claim']
    assert current['corrections'][-1]['interpretation']['dialogue_act'] == 'correction'


@pytest.mark.parametrize('text', ['刚才发烧，现在好了', '此刻感觉恢复了', '现在比之前舒服多了', '已经没事了'])
def test_state_change_equivalence_never_retracts_prior(tmp_path, text):
    care = SilverStore(tmp_path/'support.sqlite3')
    s = StatementSession(SCOPE, lambda: care)
    result = s.turn('我今天发烧', config=CONFIG, transport=lambda c, m: json.dumps(interpretation('我今天发烧')))
    s.act(result['proposed_actions'][0]['id'])
    old = copy.deepcopy(care.records(SCOPE, 'agent_self_report')[0])
    result = s.turn(text, config=CONFIG, transport=lambda c, m: json.dumps(interpretation(text, act='state_change', target=old['id'])))
    assert result['dialogue_act'] == 'state_change'
    assert result['understanding'][0]['relation']['type'] == 'updates'
    assert all(x['operation'] == 'save' for x in result['proposed_actions'])
    assert care.get(SCOPE, 'agent_self_report', old['id']) == old
    s.act(result['proposed_actions'][0]['id'])
    assert care.get(SCOPE, 'agent_self_report', old['id']) == old
    assert len(care.records(SCOPE, 'agent_self_report')) == 2


@pytest.mark.parametrize('mutation', ['invented_ref', 'invented_diagnosis', 'action', 'raw_text', 'cross_window', 'reset'])
def test_grounding_rejects_unsupported_data(mutation):
    state = ConversationState(SCOPE, 'window-a')
    turn = state.new_turn('原话甲')
    packet = interpretation('原话甲')
    if mutation == 'invented_ref':
        packet['statements'][0]['context_refs'] = [{'kind':'event', 'id':'nonexistent'}]
    elif mutation == 'invented_diagnosis':
        packet['statements'][0]['proposition']['text'] = '无依据的医学诊断'
    elif mutation == 'action':
        packet['actions'] = ['save']
    elif mutation == 'raw_text':
        packet['statements'][0]['raw_text'] = '改写原话'
    else:
        claims = validate_interpretation(packet, turn, state)
        state.accept(turn, packet['dialogue_act'], claims)
        target = claims[0]['id']
        if mutation == 'reset':
            state.clear()
        else:
            state = ConversationState(SCOPE, 'window-b')
        turn = state.new_turn('后续甲')
        packet = interpretation('后续甲', act='state_change', target=target)
    with pytest.raises(GroundingError):
        validate_interpretation(packet, turn, state)


@pytest.mark.parametrize('act,relation', [('state_change', 'corrects'), ('correction', 'updates'),
                                       ('new_report', 'corrects'), ('follow_up', 'updates')])
def test_relation_type_cannot_grant_a_different_operation(act, relation):
    state = ConversationState(SCOPE, 'window')
    turn = state.new_turn('事件甲')
    claims = validate_interpretation(interpretation('事件甲'), turn, state)
    state.accept(turn, 'new_report', claims)
    payload = interpretation('事件乙', act=act, target=claims[0]['id'])
    payload['statements'][0]['relation']['type'] = relation
    with pytest.raises(GroundingError):
        validate_interpretation(payload, state.new_turn('事件乙'), state)


def test_current_ref_must_be_declared_and_fresh_even_if_id_was_once_real(tmp_path):
    state = ConversationState(SCOPE, 'window')
    turn = state.new_turn('事件甲')
    claims = validate_interpretation(interpretation('事件甲'), turn, state)
    state.accept(turn, 'new_report', claims)
    payload = interpretation('事件乙', act='correction', target=claims[0]['id'])
    missing = copy.deepcopy(payload)
    missing['statements'][0]['context_refs'] = []
    with pytest.raises(GroundingError):
        validate_interpretation(missing, state.new_turn('事件乙'), state)
    state.invalidate(claims[0]['id'])
    with pytest.raises(GroundingError):
        validate_interpretation(payload, state.new_turn('事件乙'), state)


@pytest.mark.parametrize('scope_change', [dict(participant_id='other'), dict(source_kind='REPLAY_FILE'), dict(usage_context='CONTROLLED_DEMO')])
def test_same_conversation_name_cannot_import_foreign_scope_refs(scope_change):
    first = ConversationState(SCOPE, 'same-name')
    turn = first.new_turn('来源甲')
    claims = validate_interpretation(interpretation('来源甲'), turn, first)
    first.accept(turn, 'new_report', claims)
    second = ConversationState(dict(SCOPE, **scope_change), 'same-name')
    with pytest.raises(GroundingError):
        validate_interpretation(interpretation('来源乙', act='correction', target=claims[0]['id']), second.new_turn('来源乙'), second)


def test_model_context_is_bounded_and_excludes_store_and_tokens(tmp_path):
    care = SilverStore(tmp_path/'support.sqlite3')
    s = StatementSession(SCOPE, lambda: care)
    packets = []
    def provider(config, messages):
        packet = json.loads(messages[-1]['content'])
        packets.append(packet)
        return json.dumps(interpretation(packet['current']['raw_text']))
    for i in range(15):
        result = s.turn('观察' + str(i), config=CONFIG, transport=provider)
        if i == 0:
            s.act(result['proposed_actions'][0]['id'])
    packet = packets[-1]
    assert len(packet['context']['turns']) == 6 and len(packet['context']['events']) <= 12
    encoded = json.dumps(packet)
    assert SCOPE['participant_id'] not in encoded and 'action_id' not in encoded and 'consent' not in encoded
    assert '观察0' not in encoded and 'revision' not in encoded
    s.list_records()
    assert len(s.state.events) <= 12  # read command never hydrates full DB history


def test_new_state_does_not_overwrite_concurrently_changed_prior(tmp_path):
    care = SilverStore(tmp_path/'support.sqlite3')
    s = StatementSession(SCOPE, lambda: care)
    result = s.turn('原话甲', config=CONFIG, transport=lambda *a: json.dumps(interpretation('原话甲')))
    s.act(result['proposed_actions'][0]['id'])
    old = care.records(SCOPE, 'agent_self_report')[0]
    result = s.turn('原话乙', config=CONFIG, transport=lambda *a: json.dumps(interpretation('原话乙', act='state_change', target=old['id'])))
    changed = care.save(SCOPE, 'agent_self_report', old, expected_revision=old['revision'])
    with pytest.raises(ValueError, match='更新'):
        s.act(result['proposed_actions'][0]['id'])
    assert care.records(SCOPE, 'agent_self_report') == [changed]


def test_tampered_ui_or_pending_payload_cannot_save(tmp_path):
    care = SilverStore(tmp_path/'support.sqlite3')
    s = StatementSession(SCOPE, lambda: care)
    result = s.turn('原话甲', config=CONFIG, transport=lambda *a: json.dumps(interpretation('原话甲')))
    token = result['proposed_actions'][0]['id']
    result['understanding'][0]['raw_text'] = 'UI forged'
    assert s.pending[token]['claim']['raw_text'] == '原话甲'
    s.pending[token]['claim']['raw_text'] = 'backend corruption'
    with pytest.raises(ValueError, match='变化'):
        s.act(token)
    assert not care.records(SCOPE, 'agent_self_report')


@pytest.mark.parametrize('variant', ['我今天没胃口', '我现在没有食欲', '现在不想吃东西'])
def test_semantic_equivalence_class_no_local_negation_override(tmp_path, variant):
    care = SilverStore(tmp_path/'support.sqlite3')
    s = StatementSession(SCOPE, lambda: care)
    result = s.turn(variant, config=CONFIG, transport=lambda *a: json.dumps(interpretation(variant)))
    assert result['dialogue_act'] == 'new_report'
    assert result['understanding'][0]['relation']['type'] == 'none'
    assert len(result['proposed_actions']) == 1 and not care.records(SCOPE, 'agent_self_report')


def test_denying_a_prior_state_can_be_saved_only_as_linked_later_state(tmp_path):
    care = SilverStore(tmp_path/'support.sqlite3')
    s = StatementSession(SCOPE, lambda: care)
    a = s.turn('观察甲', config=CONFIG, transport=lambda *x: json.dumps(interpretation('观察甲')))
    s.act(a['proposed_actions'][0]['id'])
    prior = care.records(SCOPE, 'agent_self_report')[0]
    b = s.turn('观察乙', config=CONFIG, transport=lambda *x: json.dumps(interpretation('观察乙', act='state_change', target=prior['id'], polarity='negated')))
    assert b['proposed_actions'][0]['operation'] == 'save'
    s.act(b['proposed_actions'][0]['id'])
    assert care.get(SCOPE, 'agent_self_report', prior['id']) == prior
    assert care.records(SCOPE, 'agent_self_report')[0]['claim']['proposition']['polarity'] == 'negated'


def test_uncertain_correction_does_not_propose_retraction(tmp_path):
    care = SilverStore(tmp_path/'support.sqlite3')
    s = StatementSession(SCOPE, lambda: care)
    first = s.turn('原话甲', config=CONFIG, transport=lambda *a: json.dumps(interpretation('原话甲')))
    target = first['understanding'][0]['id']
    result = s.turn('可能纠正甲', config=CONFIG, transport=lambda *a: json.dumps(interpretation('可能纠正甲', act='correction', target=target, certainty='uncertain')))
    assert not result['proposed_actions'] and not care.records(SCOPE, 'agent_self_report')
