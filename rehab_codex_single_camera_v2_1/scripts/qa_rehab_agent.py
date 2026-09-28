"""Render the actual native assistant with isolated SYNTHETIC/TEST evidence."""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'tests')]
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFontDatabase, QFont
from app.ui.main_window import MainWindow
from app.rehab_agent import answer
from app.storage import Storage
from test_product_navigation import PassiveRuntime
from test_automatic_plans import SCOPE, NOW, measured


app = QApplication([])
app.setStyle('Fusion')
for font in ('msyh.ttc', 'msyhbd.ttc'):
    QFontDatabase.addApplicationFont(str(Path(os.environ.get('WINDIR', 'C:/Windows'))/'Fonts'/font))
app.setFont(QFont('Microsoft YaHei', 11))
output = ROOT/'qa-output'/'rehab-agent'
output.mkdir(parents=True, exist_ok=True)
w = MainWindow(runtime=PassiveRuntime())
w.show()
app.processEvents()
assert w.grab().save(str(output/'desktop-entry.png'))
w._open_rehab_agent()
d = w.agent_dialog
# This scope and storage are only screenshot fixtures, never patient data.
d.scope = dict(SCOPE)
with tempfile.TemporaryDirectory() as directory:
    store = Storage(Path(directory)/'synthetic.sqlite3')
    try:
        d.receive(d.request_id, answer(store, SCOPE, '今天练什么', now=NOW))
        app.processEvents()
        assert d.grab().save(str(output/'no-assessment.png'))
        store.save_session(measured())
        d.receive(d.request_id, answer(store, SCOPE, '今天练什么', now=NOW))
        app.processEvents()
        assert d.grab().save(str(output/'proposal.png'))
    finally:
        store.close()
d.reject()
w._allow_close = True
w.close()
print('PASS: desktop entry, empty evidence, scoped synthetic proposal; no camera opened')
