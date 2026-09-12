"""Offscreen synthetic UI evidence; no camera or personal database is accessed."""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'tests')]
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import QApplication
from app.ui.automatic_plans import AutomaticPlanDialog
from app.ui.training import TrainingFeedbackDialog
from app.ui.theme import STYLE
from app.automatic_plans import program_progress
from test_automatic_plans import SCOPE, measured, proposal, record, execution

app = QApplication([])
app.setStyle('Fusion')
app.setStyleSheet(STYLE)
for font in ('msyh.ttc', 'msyhbd.ttc'):
    QFontDatabase.addApplicationFont(str(Path(os.environ.get('WINDIR', 'C:/Windows'))/'Fonts'/font))
output = ROOT/'qa-output'/'automatic-v018'
output.mkdir(parents=True, exist_ok=True)
sessions = [measured('shoulder_flexion'), measured('shoulder_abduction'), measured('knee_extension')]
p, r = proposal(sessions), record(sessions)
d = AutomaticPlanDialog(SCOPE)
d.receive(dict(kind='automatic_proposal', proposal=p))
d.show()
app.processEvents()
assert not d.general.isChecked()
assert d.grab().save(str(output/'proposal.png'))
d.receive(dict(kind='automatic_progress', record=r, progress=program_progress(r, [])))
app.processEvents()
assert d.primary.isEnabled()
assert d.grab().save(str(output/'sequence.png'))
s = execution(r, training_feedback={})
d.receive(dict(kind='automatic_progress', record=r, progress=program_progress(r, [s])))
app.processEvents()
assert d.feedback_button.isVisible() and not d.primary.isEnabled()
assert d.grab().save(str(output/'feedback-recovery.png'))
d.close()
feedback = TrainingFeedbackDialog(s)
feedback.show()
app.processEvents()
assert feedback.grab().save(str(output/'comfort-feedback.png'))
feedback.close()
print('PASS: proposal / sequence / missing-feedback recovery / explicit comfort shortcut; SYNTHETIC / TEST only')
