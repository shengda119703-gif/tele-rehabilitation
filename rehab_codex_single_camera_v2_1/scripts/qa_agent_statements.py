"""Native A3 offline QA: synthetic model outputs, real grounding/store/Qt events."""
import argparse
import copy
import json
import os
from pathlib import Path
import sys
import tempfile

os.environ['QT_QPA_PLATFORM'] = 'offscreen'
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'tests')]
from PySide6.QtCore import Qt, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFont, QFontDatabase
from app.agent_statements import StatementSession
from app.agent_conversation import converse
from app.silver_store import SilverStore
from app.ui.rehab_agent import RehabAgentDialog
from app.ui.theme import STYLE
from statement_fixtures import CONFIG, interpretation, transport

parser = argparse.ArgumentParser()
parser.add_argument('--output', type=Path, default=ROOT/'qa-output'/'agent-a3')
output = parser.parse_args().output
output.mkdir(parents=True, exist_ok=True)
app = QApplication([])
app.setStyle('Fusion')
app.setStyleSheet(STYLE)
for font in ('msyh.ttc', 'msyhbd.ttc'):
    QFontDatabase.addApplicationFont(str(Path(os.environ.get('WINDIR', 'C:/Windows'))/'Fonts'/font))
app.setFont(QFont('Microsoft YaHei', 11))
captures = []
with tempfile.TemporaryDirectory() as directory:
    care = SilverStore(Path(directory)/'synthetic.sqlite3')
    scope = dict(participant_id='A3-SYNTHETIC-QA', source_kind='SYNTHETIC', usage_context='TEST')
    d = RehabAgentDialog(scope, config=CONFIG)
    session = [StatementSession(scope, lambda: care, d.conversation_id)]
    sends = []
    provider = [transport]
    config = [CONFIG]
    def respond(text, rid):
        sends.append(text)
        result = session[0].turn(text, config=config[0], transport=provider[0])
        if result is None:
            result = converse(None, scope, text)
        QTimer.singleShot(0, lambda: d.receive(rid, result))
    def operation(token, rid):
        result = session[0].list_records() if token == 'list' else session[0].act(token)
        d.receive(rid, result)
    def reset(_):
        session[0].clear()
        session[0] = StatementSession(scope, lambda: care)
    d.requested.connect(respond)
    d.operation_requested.connect(operation)
    d.reset_requested.connect(reset)
    d.show()
    app.processEvents()
    def capture(name):
        app.processEvents()
        assert d.isVisible()
        assert d.grab().save(str(output/name))
        captures.append(name)
    def enter(text):
        before = len(sends)
        d.input.setFocus()
        d.input.setText(text)
        QTest.keyClick(d.input, Qt.Key_Return)
        QTest.qWait(20)
        assert d.isVisible() and len(sends) == before+1 and not d.input.text()
    for text, name in (('昨天妈妈头晕','01-family.png'), ('我今天没头晕','02-negation.png'), ('我头晕','03-three-enters.png')):
        enter(text)
        assert not d.proposals
        capture(name)
    assert len(sends) == 3
    for index, text in enumerate(('我今天没胃口', '我今天没睡好', '我今天不舒服'), 4):
        d.clear_conversation()
        enter(text)
        assert len(d.proposals) == 1 and not care.records(scope, 'agent_self_report')
        capture(f'{index:02}-open-statement.png')
    d.clear_conversation()
    enter('我今天发烧')
    d.action_row.itemAt(0).widget().click()
    old = copy.deepcopy(care.records(scope, 'agent_self_report')[0])
    capture('07-original-saved.png')
    provider[0] = lambda c, m: json.dumps(interpretation(json.loads(m[-1]['content'])['current']['raw_text'],
                                                       act='state_change', target=old['id']))
    enter('刚才发烧，现在好了')
    assert all(p['operation'] == 'save' for p in d.proposals.values())
    assert care.get(scope, 'agent_self_report', old['id']) == old
    capture('08-state-change-proposed.png')
    d.action_row.itemAt(0).widget().click()
    assert len(care.records(scope, 'agent_self_report')) == 2
    assert care.get(scope, 'agent_self_report', old['id']) == old
    capture('09-state-change-saved.png')
    provider[0] = lambda c, m: json.dumps(interpretation(json.loads(m[-1]['content'])['current']['raw_text'],
                                                       act='correction', target=old['id']))
    enter('我刚才说错了，其实没有发烧')
    assert all(p['operation'] == 'retract' for p in d.proposals.values())
    capture('10-correction-proposed.png')
    d.action_row.itemAt(0).widget().click()
    assert care.get(scope, 'agent_self_report', old['id'])['status'] == 'RETRACTED'
    assert sum(r['status'] == 'ACTIVE' for r in care.records(scope, 'agent_self_report')) == 1
    capture('11-correction-receipt.png')
    d.clear_conversation()
    enter('我刚才说错了，其实没有发烧')
    assert not d.proposals and '核验' in d.browser.toPlainText()
    capture('12-expired-reference.png')
    for index, text in enumerate(('不要记录，我今天发烧', '告诉家人我今天发烧'), 13):
        d.clear_conversation()
        enter(text)
        assert not d.proposals and '隐私与执行状态' in d.browser.toPlainText()
        capture(f'{index:02}-privacy.png')
    d.clear_conversation()
    config[0] = None
    enter('我今天头有点沉')
    assert not d.proposals and '暂不可用' in d.browser.toPlainText()
    capture('15-unavailable.png')
    d.ask('查看自报记录')
    assert '已撤回' in d.browser.toPlainText() and '后续状态' in d.browser.toPlainText()
    capture('16-history-and-relations.png')
    d.reject()
print(f'PASS: {len(captures)} native screenshots; synthetic semantic provider; real save/update/retract; three Return rounds; no network/camera.')
