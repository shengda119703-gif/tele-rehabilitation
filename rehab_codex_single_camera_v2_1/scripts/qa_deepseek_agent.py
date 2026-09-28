"""Offscreen DeepSeek Agent UI verification; no real API request is made."""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'tests')]
from PySide6.QtGui import QFontDatabase, QFont
from PySide6.QtWidgets import QApplication
from app.ui.rehab_agent import RehabAgentDialog, ModelSettingsDialog
from app.ui.theme import STYLE
from test_automatic_plans import SCOPE

app = QApplication([])
app.setStyle('Fusion')
app.setStyleSheet(STYLE)
for font in ('msyh.ttc', 'msyhbd.ttc'):
    QFontDatabase.addApplicationFont(str(Path(os.environ.get('WINDIR', 'C:/Windows'))/'Fonts'/font))
app.setFont(QFont('Microsoft YaHei', 11))
output = ROOT/'qa-output'/'deepseek-agent'
output.mkdir(parents=True, exist_ok=True)
d = RehabAgentDialog(SCOPE)
d.show()
app.processEvents()
assert d.grab().save(str(output/'unconfigured.png'))
d.ask('我今天该练什么？')
d.receive(d.request_id, dict(
    scope=SCOPE,
    text='根据本机记录，今天还没有可用的训练安排，我们先完成一次身体评估。',
    local_text='当前范围没有可用于自动安排的有效评估。',
    actions=[dict(id='assessment', label='去做身体评估')],
    at='TEST', mode_label='界面测试 · 模拟两段式回复，未调用真实模型', shareable=False))
app.processEvents()
assert d.grab().save(str(output/'tool-result-simulated.png'))
settings = ModelSettingsDialog(parent=d)
assert settings.endpoint.isReadOnly()
assert settings.endpoint.text() == 'https://api.deepseek.com'
assert settings.model.text() == 'deepseek-flash'
settings.show()
app.processEvents()
assert settings.grab().save(str(output/'settings.png'))
settings.reject()
d.reject()
print('PASS: DeepSeek defaults, privacy copy, simulated two-pass display. No real model called.')
