import copy
from datetime import datetime, timezone

import pytest

from app.agent_statements import StatementSession, parse_statements
from app.silver_store import SilverStore
from test_automatic_plans import SCOPE

NOW = datetime(2026, 9, 29, 9, tzinfo=timezone.utc)


@pytest.mark.parametrize('text,subject,time,status', [
    ('昨天妈妈头晕', 'family', 'past', 'occurred'),
    ('我今天没头晕', 'self', 'current', 'negated'),
    ('如果我现在头晕怎么办', 'self', 'current', 'hypothetical'),
    ('我现在可能头晕', 'self', 'current', 'uncertain'),
    ('我昨天头晕', 'self', 'past', 'occurred'),
    ('我今天头晕', 'self', 'current', 'occurred'),
    ('头晕', 'unknown', 'unknown', 'occurred'),
    ('妈妈说我今天头晕', 'unknown', 'current', 'uncertain'),
    ('我和妈妈今天都头晕', 'unknown', 'current', 'occurred'),
    ('我今天不是没头晕', 'self', 'current', 'uncertain'),
    ('我今天头晕吗？', 'self', 'current', 'uncertain'),
    ('我今天不头晕', 'self', 'current', 'negated'),
    ('我今天想问问头晕', 'self', 'current', 'uncertain'),
    ('我今天头晕已经好了', 'self', 'current', 'uncertain'),
    ('我今天不舒服', 'self', 'current', 'occurred'),
    ('请帮我记录我今天头晕', 'self', 'current', 'occurred'),
])
def test_dimensions(text, subject, time, status):
    row = parse_statements(text, 'm1', NOW)[0]
    assert (row['subject'], row['time_scope'], row['status']) == (subject, time, status)


def session(tmp_path):
    care = SilverStore(tmp_path/'silver.sqlite3')
    return StatementSession(SCOPE, lambda: care), care


def confirm(s, result, index=0):
    return s.act(result['proposed_actions'][index]['id'])


def test_consent_persistence_receipt_and_targeted_correction(tmp_path):
    s, care = session(tmp_path)
    result = s.turn('我今天头晕，我今天腿疼', now=NOW)
    assert not care.records(SCOPE, 'agent_self_report')
    saved = confirm(s, result)
    assert saved['receipt']['status'] == 'saved'
    second = confirm(s, saved)
    assert second['receipt']['status'] == 'saved'
    records = copy.deepcopy(care.records(SCOPE, 'agent_self_report'))
    assert len(records) == 2
    assert all(r['evidence_method'] == 'SELF_REPORTED' and r['shared'] is False for r in records)
    assert all(r['consent']['method'] == 'explicit_button' and r['source_message_id'] for r in records)
    result = s.turn('我刚才说错了，没有头晕', now=NOW)
    assert len(result['proposed_actions']) == 1
    assert '头晕' in result['proposed_actions'][0]['summary']
    assert care.records(SCOPE, 'agent_self_report') == records
    result = confirm(s, result)
    assert result['receipt']['status'] == 'retracted'
    rows = care.records(SCOPE, 'agent_self_report')
    assert next(r for r in rows if r['claim']['symptom'] == '头晕')['status'] == 'RETRACTED'
    assert next(r for r in rows if r['claim']['symptom'] == '腿疼')['status'] == 'ACTIVE'
    old = next(r for r in records if r['claim']['symptom'] == '头晕')
    new = next(r for r in rows if r['claim']['symptom'] == '头晕')
    assert new['claim'] == old['claim'] and new['source_message_id'] == old['source_message_id']
    assert new['corrections'][0]['source_message_id'] != new['source_message_id']
    assert new['corrections'][0]['text'] == '我刚才说错了，没有头晕'
    reopened = StatementSession(SCOPE, lambda: care).turn('查看自报记录')
    assert '已撤回' in reopened['record_summary'] and '腿疼' in reopened['record_summary']


@pytest.mark.parametrize('text', ['昨天妈妈头晕', '我今天没头晕', '如果我今天头晕',
                               '我今天可能头晕', '头晕', '我头晕', '我明天头晕'])
def test_unaccepted_never_proposed_or_saved(tmp_path, text):
    s, care = session(tmp_path)
    result = s.turn(text, now=NOW)
    assert result['understanding'] and not result['proposed_actions']
    assert not care.records(SCOPE, 'agent_self_report')


def test_latest_message_only_no_fallback_to_older_fact(tmp_path):
    s, care = session(tmp_path)
    confirm(s, s.turn('我今天头晕', now=NOW))
    s.turn('昨天妈妈头晕', now=NOW)
    s.turn('我今天没头晕', now=NOW)
    result = s.turn('我刚才说错了', now=NOW)
    assert not result['proposed_actions']
    assert care.records(SCOPE, 'agent_self_report')[0]['status'] == 'ACTIVE'


def test_cancel_stale_tokens_and_scope(tmp_path):
    s, care = session(tmp_path)
    result = s.turn('我今天头晕', now=NOW)
    token = result['proposed_actions'][0]['id']
    s.act('cancel')
    with pytest.raises(ValueError):
        s.act(token)
    result = s.turn('我今天头晕', now=NOW)
    confirm(s, result)
    with pytest.raises(ValueError):
        confirm(s, result)
    other = StatementSession(dict(SCOPE, participant_id='another'), lambda: care)
    assert not other.turn('查看自报记录')['proposed_actions']
    with pytest.raises(ValueError):
        other.act(token)


def test_unknown_correction_asks_selection_and_pending_never_persisted(tmp_path):
    s, care = session(tmp_path)
    result = s.turn('我今天头晕，我今天腿疼', now=NOW)
    result = s.turn('我刚才说错了', now=NOW)
    assert len(result['proposed_actions']) == 2
    result = confirm(s, result)
    assert result['receipt']['status'] == 'discarded'
    assert not care.records(SCOPE, 'agent_self_report')


def test_privacy_invalidates_pending_and_does_not_open_store(tmp_path):
    def forbidden():
        pytest.fail('privacy turn touched store')
    s = StatementSession(SCOPE, forbidden)
    result = s.turn('我今天头晕', now=NOW)
    token = result['proposed_actions'][0]['id']
    assert s.turn('不要记录，我今天头晕', now=NOW) is None
    with pytest.raises(ValueError):
        s.act(token)
    assert not s.turn('我刚才说错了')['proposed_actions']


def test_revision_failure_keeps_record_intact(tmp_path):
    s, care = session(tmp_path)
    confirm(s, s.turn('我今天头晕', now=NOW))
    result = s.turn('我刚才说错了', now=NOW)
    row = care.records(SCOPE, 'agent_self_report')[0]
    care.save(SCOPE, 'agent_self_report', row, expected_revision=row['revision'])
    with pytest.raises(ValueError, match='更新'):
        confirm(s, result)
    assert care.records(SCOPE, 'agent_self_report')[0]['status'] == 'ACTIVE'


def test_save_failure_has_no_success_receipt_and_can_retry(tmp_path, monkeypatch):
    s, care = session(tmp_path)
    result = s.turn('我今天头晕', now=NOW)
    original = care.save
    def fail(*args, **kwargs):
        raise OSError('disk failure')
    monkeypatch.setattr(care, 'save', fail)
    with pytest.raises(OSError):
        confirm(s, result)
    assert not care.records(SCOPE, 'agent_self_report')
    monkeypatch.setattr(care, 'save', original)
    assert confirm(s, result)['receipt']['status'] == 'saved'


def test_past_date_and_mixed_subject_not_current(tmp_path):
    s, care = session(tmp_path)
    result = s.turn('我昨天头晕，妈妈今天腿疼', now=NOW)
    assert len(result['proposed_actions']) == 1
    confirm(s, result)
    claim = care.records(SCOPE, 'agent_self_report')[0]['claim']
    assert claim['time_scope'] == 'past' and claim['event_date'] == '2026-09-28'


def test_no_implicit_cross_turn_subject_or_time(tmp_path):
    s, care = session(tmp_path)
    s.turn('我今天头晕', now=NOW)
    assert not s.turn('腿疼', now=NOW)['proposed_actions']
    assert not s.turn('我腿疼', now=NOW)['proposed_actions']


@pytest.mark.parametrize('text', ['我今天提到头晕', '我今天说“头晕”这个词', '我今天头晕已经好了',
                                '我今天担心头晕', '我今天不头晕', '我昨天头晕现在好了'])
def test_no_keyword_admission(tmp_path, text):
    s, care = session(tmp_path)
    assert not s.turn(text, now=NOW)['proposed_actions']


@pytest.mark.parametrize('text', ['不记录，我今天头晕', '不用保存我今天头晕',
                                '别告诉家人，我今天头晕', '告诉家人我今天头晕'])
def test_all_privacy_routes_never_propose_save(tmp_path, text):
    s, care = session(tmp_path)
    assert s.turn(text) is None
    assert not s.pending and not s.last_claims and not care.records(SCOPE, 'agent_self_report')
