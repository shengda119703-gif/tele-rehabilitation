import json

import pytest

from app.agent_extraction import extract_statements, validate_statements, ExtractionError
from app.agent_statements import StatementSession
from app.agent_conversation import ModelConfig, ModelError
from app.silver_store import SilverStore
from test_automatic_plans import SCOPE

CONFIG = ModelConfig('https://api.deepseek.com', 'deepseek-flash', 'synthetic-not-a-key', True)


def row(text, concept, **changes):
    value = dict(subject='self', time_scope='current', statement_type='other', concept=concept,
                 polarity='affirmed', certainty='certain', raw_text=text, evidence_span=text)
    value.update(changes)
    return value


@pytest.mark.parametrize('concept', ['发烧', '咳嗽', '睡不好', '胃口不好', '睡得很差', '心情差', '头有点沉', '浑身像棉花一样'])
def test_open_concepts_without_medical_dictionary(tmp_path, concept):
    text = '我今天' + concept
    care = SilverStore(tmp_path/'support.sqlite3')
    s = StatementSession(SCOPE, lambda: care)
    calls = []
    def transport(config, messages):
        calls.append(messages)
        return json.dumps({'statements': [row(text, concept)]}, ensure_ascii=False)
    result = s.turn(text, config=CONFIG, transport=transport)
    assert len(calls) == 1 and calls[0][-1] == {'role': 'user', 'content': text}
    assert len(calls[0]) == 2  # no history, database, or stored records
    assert not care.records(SCOPE, 'agent_self_report')
    assert len(result['proposed_actions']) == 1
    result = s.act(result['proposed_actions'][0]['id'])
    assert result['receipt']['status'] == 'saved'
    claim = care.records(SCOPE, 'agent_self_report')[0]['claim']
    assert claim['concept'] == concept and claim['raw_text'] == text
    assert claim['evidence_span'] == text and 'symptom' not in claim
    assert claim['statement_type'] == 'other'


@pytest.mark.parametrize('text,concept,changes', [
    ('妈妈今天发烧', '发烧', {'subject':'family'}),
    ('如果我明天发烧', '发烧', {'time_scope':'future', 'polarity':'hypothetical'}),
    ('我今天没有咳嗽', '咳嗽', {'polarity':'negated'}),
    ('我今天可能发烧', '发烧', {'certainty':'uncertain'}),
    ('昨天摔了一跤', '摔了一跤', {'subject':'unknown', 'time_scope':'past'}),
    ('我头有点沉', '头有点沉', {'time_scope':'unknown'}),
])
def test_nonadmissible_dimensions(text, concept, changes):
    claims = validate_statements(text, {'statements':[row(text, concept, **changes)]}, 'm')
    assert len(claims) == 1 and not claims[0]['admissible']


@pytest.mark.parametrize('text,model_row', [
    ('妈妈今天发烧', row('妈妈今天发烧', '发烧')),
    ('我今天没有咳嗽', row('我今天没有咳嗽', '咳嗽')),
    ('如果我明天发烧', row('如果我明天发烧', '发烧')),
    ('我今天可能发烧', row('我今天可能发烧', '发烧')),
    ('我发烧', row('我发烧', '发烧')),
    ('我今天会发烧', row('我今天会发烧', '会发烧')),
    ('我今天头有点沉', row('我今天头有点沉', '高血压')),
    ('我今天有点发烧', row('我今天有点发烧', '发烧')),
    ('我今天没有咳嗽', row('我今天咳嗽', '咳嗽')),
    ('如果我今天发烧，应该怎么办', row('我今天发烧', '发烧')),
    ('我今天没咳嗽', row('我今天没咳嗽', '没咳嗽')),
    ('我今天完全不咳嗽', row('我今天完全不咳嗽', '完全不咳嗽')),
    ('我今天从没发烧', row('我今天从没发烧', '从没发烧')),
    ('我今天无咳嗽', row('我今天无咳嗽', '无咳嗽')),
    ('我今天不咳嗽', row('我今天不咳嗽', '不咳嗽')),
    ('我今天不咳嗽', row('我今天不咳嗽', '我今天不咳嗽')),
    ('我今天感觉像发烧', row('我今天感觉像发烧', '发烧')),
    ('我今天发烧，只是开玩笑', row('我今天发烧', '发烧')),
    ('我今天发烧，是不是这样', row('我今天发烧', '发烧')),
    ('我今天说“发烧”这个词', row('我今天说“发烧”这个词', '发烧')),
    ('我今天没有咳嗽但是头有点沉', row('我今天没有咳嗽但是头有点沉', '头有点沉')),
])
def test_dishonest_or_incomplete_model_output_rejected(text, model_row):
    with pytest.raises(ExtractionError):
        validate_statements(text, {'statements':[model_row]}, 'm')


@pytest.mark.parametrize('payload', [None, [], {'statements':'wrong'}, {'statements':[], 'actions':['save']},
                                    {'statements':[{'concept':'发烧'}]}])
def test_schema_is_closed(payload):
    with pytest.raises(ExtractionError):
        validate_statements('我今天发烧', payload, 'm')


@pytest.mark.parametrize('failure', ['unconfigured', 'timeout', 'invalid', 'empty'])
def test_failure_never_falls_back_or_writes(tmp_path, failure):
    care = SilverStore(tmp_path/'support.sqlite3')
    s = StatementSession(SCOPE, lambda: care)
    def transport(*args):
        if failure == 'timeout':
            raise ModelError('temporary failure')
        return 'invalid' if failure == 'invalid' else '{"statements": []}'
    result = s.turn('我今天头晕', config=None if failure == 'unconfigured' else CONFIG, transport=transport)
    if failure == 'empty':
        assert result is None
    else:
        assert not result['proposed_actions'] and '暂不可用' in result['main_text']
    assert not s.pending and not care.records(SCOPE, 'agent_self_report')


def test_bare_negative_lexical_expression_asks_without_word_exception():
    with pytest.raises(ExtractionError):
        validate_statements('我今天没胃口', {'statements':[row('我今天没胃口', '没胃口')]}, 'm')
    claims = validate_statements('我今天胃口不好', {'statements':[row('我今天胃口不好', '胃口不好')]}, 'm')
    assert claims[0]['admissible']


def test_past_open_event_retains_past_date_and_unknown_subject_asks(tmp_path):
    from datetime import datetime, timezone
    text = '我昨天摔了一跤'
    claims = validate_statements(text, {'statements':[row(text, '摔了一跤', time_scope='past', statement_type='event')]},
                                 'm', datetime(2026, 9, 29, tzinfo=timezone.utc))
    assert claims[0]['admissible'] and claims[0]['event_date'] == '2026-09-28'
    assert claims[0]['time_scope'] == 'past'


@pytest.mark.parametrize('text', ['不要记录，我今天发烧', '别告诉家人我今天发烧', '告诉家人我今天发烧'])
def test_privacy_precedes_extraction_and_storage(text):
    def forbidden(*args, **kwargs):
        pytest.fail('protected input must not reach network/store')
    s = StatementSession(SCOPE, forbidden)
    assert s.turn(text, config=CONFIG, transport=forbidden) is None
    assert s.network == 'not_sent' and not s.pending


def test_failed_next_turn_invalidates_old_confirmation(tmp_path):
    s = StatementSession(SCOPE, lambda: SilverStore(tmp_path/'support.sqlite3'))
    result = s.turn('我今天发烧', config=CONFIG, transport=lambda *a: json.dumps({'statements':[row('我今天发烧','发烧')]}))
    token = result['proposed_actions'][0]['id']
    s.turn('我今天咳嗽', config=CONFIG, transport=lambda *a: 'wrong')
    with pytest.raises(ValueError, match='失效'):
        s.act(token)
    assert not s.last_claims


@pytest.mark.parametrize('key,value', [('concept','严重肺炎'), ('admissible',False), ('subject','family'), ('text','改写后的事实')])
def test_save_rechecks_cached_candidate(tmp_path, key, value):
    care = SilverStore(tmp_path/'support.sqlite3')
    s = StatementSession(SCOPE, lambda: care)
    result = s.turn('我今天发烧', config=CONFIG, transport=lambda *a: json.dumps({'statements':[row('我今天发烧','发烧')]}))
    token = result['proposed_actions'][0]['id']
    s.pending[token]['claim'][key] = value
    with pytest.raises(ValueError, match='不能保存'):
        s.act(token)
    assert not care.records(SCOPE, 'agent_self_report')


def test_old_symptom_record_read_and_retract_without_rewriting_claim(tmp_path):
    import copy
    care = SilverStore(tmp_path/'support.sqlite3')
    claim = dict(id='legacy', source_message_id='old-message', symptom='头晕', text='我今天头晕',
                 subject='self', time_scope='current', status='occurred', admissible=True,
                 event_date='2026-09-28', time_text='我今天头晕', certainty='explicit')
    item = dict(id='legacy', claim=claim, source_message_id='old-message', status='ACTIVE',
                evidence_method='SELF_REPORTED', origin='AGENT_USER_STATEMENT', corrections=[])
    original = copy.deepcopy(care.save(SCOPE, 'agent_self_report', item))
    s = StatementSession(SCOPE, lambda: care)
    result = s.turn('查看自报记录')
    assert '头晕' in result['record_summary']
    receipt = s.act(result['proposed_actions'][0]['id'])['receipt']
    assert receipt['status'] == 'retracted' and receipt['revision'] == original['revision']+1
    stored = care.get(SCOPE, 'agent_self_report', 'legacy')
    assert stored['claim'] == original['claim'] and stored['corrections']


@pytest.mark.parametrize('changed', [{'action':'save'}, {'admissible':True}, {'severity':'severe'}, {'diagnosis':'肺炎'}])
def test_model_cannot_supply_authority_or_inference(changed):
    value = row('我今天发烧', '发烧') | changed
    with pytest.raises(ExtractionError):
        validate_statements('我今天发烧', {'statements':[value]}, 'm')


def test_batch_limits_duplicate_and_partial_failure():
    value = row('我今天发烧', '发烧')
    for rows in ([value]*2, [value]*9, [value, row('我今天咳嗽', '肺炎')]):
        with pytest.raises(ExtractionError):
            validate_statements('我今天发烧，我今天咳嗽', {'statements':rows}, 'm')


def test_extraction_has_no_history_and_preserves_provider_error_privacy():
    s = StatementSession(SCOPE, lambda: pytest.fail('no store'))
    result = s.turn('我今天头有点沉', config=CONFIG, transport=lambda *a: 'invalid')
    assert result['privacy_status']['network'] == 'may_have_been_sent'
    assert result['shareable'] is False and not result['proposed_actions']
    result = s.turn('我今天头有点沉')
    assert result['privacy_status']['network'] == 'not_sent'
