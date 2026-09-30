"""Mechanical grounding invariants; semantic labels deliberately come from a model fixture."""
import ast
import copy
import inspect
import json

import pytest

from app import agent_extraction, agent_grounding, agent_statements
from app.agent_state import ConversationState
from app.agent_grounding import validate_interpretation, GroundingError
from app.agent_statements import StatementSession
from app.silver_store import SilverStore
from statement_fixtures import CONFIG, interpretation, source
from test_automatic_plans import SCOPE


@pytest.mark.parametrize('text', ['我今天没胃口', '今天我没睡好', '我现在不舒服', '此刻头部有沉重感', '昨天我跌了一跤', '体感：甲乙🙂47'])
def test_wording_never_changes_grounded_semantic_labels(text):
    state = ConversationState(SCOPE, 'window')
    packet = interpretation(text)
    claims = validate_interpretation(packet, state.new_turn(text), state)
    assert claims[0]['dialogue_act'] == 'new_report'
    assert claims[0]['proposition']['text'] == text
    assert claims[0]['subject']['value'] == 'self'  # validator doesn't reclassify Chinese


@pytest.mark.parametrize('field', ['action', 'diagnosis', 'severity', 'admissible', 'record_id', 'revision', 'notification'])
def test_schema_rejects_authority_and_inference_fields(field):
    state = ConversationState(SCOPE, 'window')
    packet = interpretation('来源文字')
    packet['statements'][0][field] = 'invented'
    with pytest.raises(GroundingError):
        validate_interpretation(packet, state.new_turn('来源文字'), state)


def test_follow_up_inherits_real_context_but_not_fabricated_values():
    state = ConversationState(SCOPE, 'window')
    turn = state.new_turn('先前原话')
    claims = validate_interpretation(interpretation('先前原话'), turn, state)
    state.accept(turn, 'new_report', claims)
    target = claims[0]['id']
    packet = interpretation('补充原话', act='follow_up', target=target)
    packet['statements'][0]['subject']['source'] = source('先前原话', 'event', target)
    valid = validate_interpretation(packet, state.new_turn('补充原话'), state)
    assert valid[0]['relation']['target_event_id'] == target
    packet['statements'][0]['subject']['value'] = 'family'
    with pytest.raises(GroundingError):
        validate_interpretation(packet, state.new_turn('补充原话'), state)


def test_expired_message_ref_and_scope_owned_turn_are_rejected():
    state = ConversationState(SCOPE, 'window')
    first = state.new_turn('旧原话')
    state.accept(first, 'chat', [])
    for i in range(7):
        state.accept(state.new_turn(str(i)), 'chat', [])
    packet = interpretation('新原话')
    packet['statements'][0]['context_refs'] = [dict(kind='message', id=first['id'])]
    with pytest.raises(GroundingError):
        validate_interpretation(packet, state.new_turn('新原话'), state)
    foreign = ConversationState(dict(SCOPE, participant_id='other'), 'window')
    with pytest.raises(GroundingError):
        validate_interpretation(interpretation('新原话'), foreign.new_turn('新原话'), state)


@pytest.mark.parametrize('failure', ['unconfigured', 'timeout', 'invalid_json', 'invalid_schema'])
def test_failures_no_fallback_no_write(tmp_path, failure):
    care = SilverStore(tmp_path/'support.sqlite3')
    session = StatementSession(SCOPE, lambda: care)
    def transport(*args):
        if failure == 'timeout':
            raise TimeoutError()
        return 'bad' if failure == 'invalid_json' else '{"actions":["save"]}'
    result = session.turn('任何表达', config=None if failure == 'unconfigured' else CONFIG, transport=transport)
    assert not result['proposed_actions'] and not care.records(SCOPE, 'agent_self_report')


def test_production_understanding_has_no_regex_or_old_semantic_functions():
    for module in (agent_extraction, agent_grounding, agent_statements):
        tree = ast.parse(inspect.getsource(module))
        assert not any(isinstance(n, ast.Import) and any(x.name == 're' for x in n.names) for n in ast.walk(tree))
        assert not any(isinstance(n, ast.Name) and n.id in {
            'FAMILY', 'TIMES', 'HYPOTHETICAL', 'UNCERTAIN', 'MENTION', 'NEGATION', 'CORRECTION', 'SYMPTOMS', '_dimensions'
        } for n in ast.walk(tree))
    assert not hasattr(agent_extraction, 'validate_statements')


def test_same_turn_state_change_graph_no_forward_ref(tmp_path):
    from statement_fixtures import statement
    state = ConversationState(SCOPE, 'window')
    text = '先前的情况；当前的情况'
    a = statement(text, time='past', proposition='先前的情况')
    b = statement(text, proposition='当前的情况')
    b['relation'] = dict(type='updates', target=dict(kind='statement', id=0))
    payload = dict(dialogue_act='state_change', statements=[a, b])
    claims = validate_interpretation(payload, state.new_turn(text), state)
    assert claims[1]['relation']['target_event_id'] == claims[0]['id']
    b['relation']['target']['id'] = 1
    with pytest.raises(GroundingError):
        validate_interpretation(payload, state.new_turn(text), state)


@pytest.mark.parametrize('content', ['{"dialogue_act":"chat","dialogue_act":"new_report","statements":[]}', '['*2000 + ']'*2000], ids=['duplicate_keys', 'nested_array'])
def test_duplicate_fields_and_deep_json_fail_closed(content, tmp_path):
    care = SilverStore(tmp_path/'support.sqlite3')
    session = StatementSession(SCOPE, lambda: care)
    result = session.turn('来源', config=CONFIG, transport=lambda *a: content)
    assert result['extraction_status'] in {'unavailable', 'needs_clarification'}
    assert not session.pending and not care.records(SCOPE, 'agent_self_report')
