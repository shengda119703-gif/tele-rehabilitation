"""Native A-stage keyboard/presentation QA; isolated SYNTHETIC/TEST only."""
import argparse
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from PySide6.QtCore import Qt, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFont, QFontDatabase
from app.agent_statements import StatementSession
from app.agent_conversation import converse
from app.silver_store import SilverStore
from app.ui.rehab_agent import RehabAgentDialog
from app.ui.theme import STYLE

parser = argparse.ArgumentParser()
parser.add_argument('--output', type=Path, default=ROOT/'qa-output'/'agent-statements')
output = parser.parse_args().output
output.mkdir(parents=True, exist_ok=True)
app = QApplication([])
app.setStyle('Fusion')
app.setStyleSheet(STYLE)
for font in ('msyh.ttc', 'msyhbd.ttc'):
    QFontDatabase.addApplicationFont(str(Path(os.environ.get('WINDIR', 'C:/Windows'))/'Fonts'/font))
app.setFont(QFont('Microsoft YaHei', 11))
with tempfile.TemporaryDirectory() as directory:
    care = SilverStore(Path(directory)/'synthetic.sqlite3')
    scope = dict(participant_id='SYNTHETIC-UI-QA', source_kind='SYNTHETIC', usage_context='TEST')
    session = [StatementSession(scope, lambda: care)]
    d = RehabAgentDialog(scope)
    sends = []
    def respond(text, rid):
        sends.append(text)
        result = session[0].turn(text)
        if result is None:
            result = converse(None, scope, text)
        QTimer.singleShot(0, lambda: d.receive(rid, result))
    d.requested.connect(respond)
    d.operation_requested.connect(lambda token, rid: d.receive(rid, session[0].act(token)))
    d.reset_requested.connect(lambda _: session.__setitem__(0, StatementSession(scope, lambda: care)))
    d.show()
    app.processEvents()
    def capture(name):
        app.processEvents()
        assert d.isVisible()
        assert d.grab().save(str(output/name))
    def enter(text):
        before = len(sends)
        d.input.setFocus()
        d.input.setText(text)
        QTest.keyClick(d.input, Qt.Key_Return)
        QTest.qWait(20)
        assert d.isVisible() and len(sends) == before+1 and not d.input.text()
    for text, name in (('昨天妈妈头晕', '01-family.png'), ('我今天没头晕', '02-negated.png'),
                       ('我头晕', '03-three-enter-turns.png')):
        enter(text)
        assert not d.proposals
        assert '未写入自报记录' not in d.browser.toPlainText()
        capture(name)
    assert len(sends) == 3 and not care.records(scope, 'agent_self_report')
    d.clear_conversation()
    enter('我今天头晕')
    assert len(d.proposals) == 1
    capture('04-one-proposal.png')
    d.clear_conversation()
    enter('我今天头晕，我今天腿疼')
    assert len(d.proposals) == 2
    capture('05-two-proposals.png')
    d.action_row.itemAt(0).widget().click()
    assert '已保存到本机' in d.browser.toPlainText()
    assert '记录号：' not in d.browser.toPlainText()
    capture('06-saved.png')
    enter('我刚才说错了，没有头晕')
    capture('07-correction.png')
    d.action_row.itemAt(0).widget().click()
    assert '已撤回这一条' in d.browser.toPlainText()
    assert care.records(scope, 'agent_self_report')[0]['status'] == 'RETRACTED'
    capture('08-retracted.png')
    d.clear_conversation()
    enter('不要记录，我今天头晕')
    assert '隐私与执行状态' in d.browser.toPlainText() and not d.proposals
    capture('09-no-record.png')
    d.clear_conversation()
    enter('告诉家人我今天头晕')
    assert '隐私与执行状态' in d.browser.toPlainText() and not d.proposals
    assert d.allowed_actions == {'silver'}
    capture('10-family-not-sent.png')
    d.reject()
print('PASS: 10 native screenshots; three consecutive Return rounds; real local confirm/save/retract; no network/camera.')
