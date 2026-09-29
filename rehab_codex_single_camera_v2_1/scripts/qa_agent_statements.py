"""Native offscreen A-stage closed loop, with isolated synthetic self reports."""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFont, QFontDatabase
from app.agent_statements import StatementSession
from app.silver_store import SilverStore
from app.ui.rehab_agent import RehabAgentDialog
from app.ui.theme import STYLE

app = QApplication([])
app.setStyle('Fusion')
app.setStyleSheet(STYLE)
for font in ('msyh.ttc', 'msyhbd.ttc'):
    QFontDatabase.addApplicationFont(str(Path(os.environ.get('WINDIR', 'C:/Windows'))/'Fonts'/font))
app.setFont(QFont('Microsoft YaHei', 11))
output = ROOT/'qa-output'/'agent-statements'
output.mkdir(parents=True, exist_ok=True)
with tempfile.TemporaryDirectory() as directory:
    care = SilverStore(Path(directory)/'synthetic.sqlite3')
    scope = dict(participant_id='SYNTHETIC-UI-QA', source_kind='SYNTHETIC', usage_context='TEST')
    session = StatementSession(scope, lambda: care)
    d = RehabAgentDialog(scope)
    d.requested.connect(lambda text, rid: d.receive(rid, session.turn(text)))
    d.operation_requested.connect(lambda token, rid: d.receive(rid, session.act(token)))
    d.show()
    d.ask('我今天头晕')
    app.processEvents()
    assert d.grab().save(str(output/'01-confirm.png'))
    assert not care.records(scope, 'agent_self_report')
    d.action_row.itemAt(0).widget().click()
    app.processEvents()
    assert d.grab().save(str(output/'02-saved.png'))
    d.ask('我刚才说错了，没有头晕')
    app.processEvents()
    assert d.grab().save(str(output/'03-correction.png'))
    d.action_row.itemAt(0).widget().click()
    d.ask('查看自报记录')
    app.processEvents()
    assert d.grab().save(str(output/'04-reopened.png'))
    assert care.records(scope, 'agent_self_report')[0]['status'] == 'RETRACTED'
    d.reject()
print('PASS: actual local parse/confirm/save/retract/reopen; synthetic TEST scope; no model or camera.')
