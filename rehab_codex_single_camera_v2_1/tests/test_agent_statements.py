import copy

import pytest

from statement_fixtures import StatementSession
from app.silver_store import SilverStore
from test_automatic_plans import SCOPE


def session(tmp_path):
    care = SilverStore(tmp_path/'support.sqlite3')
    return StatementSession(SCOPE, lambda: care), care


def confirm(s, result):
    return s.act(result['proposed_actions'][0]['id'])


def test_consent_persistence_receipt_and_targeted_correction(tmp_path):
    s, care = session(tmp_path)
    first = s.turn('我今天头晕，我今天腿疼')
    assert not care.records(SCOPE, 'agent_self_report')
    confirm(s, confirm(s, first))
    original = copy.deepcopy(care.records(SCOPE, 'agent_self_report'))
    result = s.turn('我刚才说错了，没有头晕')
    assert len(result['proposed_actions']) == 1
    assert care.records(SCOPE, 'agent_self_report') == original
    assert confirm(s, result)['receipt']['status'] == 'retracted'
    rows = care.records(SCOPE, 'agent_self_report')
    assert next(r for r in rows if r['claim']['proposition']['text'] == '头晕')['status'] == 'RETRACTED'
    assert next(r for r in rows if r['claim']['proposition']['text'] == '腿疼')['status'] == 'ACTIVE'
    assert all(r['claim'] == next(old['claim'] for old in original if old['id'] == r['id']) for r in rows)
    assert '已撤回' in s.list_records()['record_summary']


@pytest.mark.parametrize('text', ['昨天妈妈头晕', '我今天没头晕', '如果我今天头晕', '我今天可能头晕', '头晕', '我头晕', '我明天头晕'])
def test_nonadmissible_interpretations_never_saved(tmp_path, text):
    s, care = session(tmp_path)
    result = s.turn(text)
    assert result['understanding'] and not result['proposed_actions']
    assert not care.records(SCOPE, 'agent_self_report')


def test_cancel_new_turn_clear_and_foreign_session_invalidate_tokens(tmp_path):
    s, care = session(tmp_path)
    for change in (lambda: s.act('cancel'), lambda: s.turn('我头晕'), s.clear):
        result = s.turn('我今天头晕')
        token = result['proposed_actions'][0]['id']
        change()
        with pytest.raises(ValueError):
            s.act(token)
    token = s.turn('我今天头晕')['proposed_actions'][0]['id']
    other = StatementSession(dict(SCOPE, participant_id='other'), lambda: care)
    with pytest.raises(ValueError):
        other.act(token)
    assert not other.list_records()['proposed_actions']


def test_revision_conflict_no_overwrite(tmp_path):
    s, care = session(tmp_path)
    confirm(s, s.turn('我今天头晕'))
    result = s.turn('我刚才说错了')
    row = care.records(SCOPE, 'agent_self_report')[0]
    care.save(SCOPE, 'agent_self_report', row, expected_revision=row['revision'])
    with pytest.raises(ValueError, match='更新'):
        confirm(s, result)
    assert care.get(SCOPE, 'agent_self_report', row['id'])['status'] == 'ACTIVE'


def test_write_failure_retry_and_no_fake_receipt(tmp_path, monkeypatch):
    s, care = session(tmp_path)
    result = s.turn('我今天头晕')
    original = care.save
    def fail(*args, **kwargs):
        raise OSError('disk failure')
    monkeypatch.setattr(care, 'save', fail)
    with pytest.raises(OSError):
        confirm(s, result)
    assert not care.records(SCOPE, 'agent_self_report')
    monkeypatch.setattr(care, 'save', original)
    assert confirm(s, result)['receipt']['status'] == 'saved'


@pytest.mark.parametrize('text', ['不要记录，我今天头晕', '别告诉家人，我今天头晕', '告诉家人我今天头晕'])
def test_privacy_clears_context_and_pending_before_network(tmp_path, text):
    s, care = session(tmp_path)
    token = s.turn('我今天头晕')['proposed_actions'][0]['id']
    def forbidden(*args):
        pytest.fail('privacy veto must run before model call')
    assert s.turn(text, transport=forbidden) is None
    assert not s.state.turns and not s.state.events and not s.pending
    with pytest.raises(ValueError):
        s.act(token)


@pytest.mark.parametrize('version', ['A1', 'A2'])
def test_legacy_record_read_and_retract_without_migration(tmp_path, version):
    s, care = session(tmp_path)
    claim = dict(id='legacy', source_message_id='old', text='我今天头晕', subject='self', time_scope='current',
                 status='occurred', event_date='2026-09-29', time_text='我今天头晕', admissible=True)
    claim['symptom' if version == 'A1' else 'concept'] = '头晕'
    item = dict(id='legacy', claim=claim, source_message_id='old', status='ACTIVE', evidence_method='SELF_REPORTED', corrections=[])
    original = care.save(SCOPE, 'agent_self_report', item)
    result = s.list_records()
    assert not s.state.events  # Reading saved history does not upload/hydrate it.
    confirm(s, result)
    stored = care.get(SCOPE, 'agent_self_report', 'legacy')
    assert stored['claim'] == original['claim'] and stored['status'] == 'RETRACTED'
