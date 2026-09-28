"""Offscreen conversation UI verification, explicitly simulated model replies."""
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
output = ROOT/'qa-output'/'agent-conversation'
output.mkdir(parents=True, exist_ok=True)
d = RehabAgentDialog(SCOPE)
d.show()
app.processEvents()
assert d.grab().save(str(output/'unconfigured.png'))
for question, reply in [('我是傻逼吗', '怎么突然这样说自己？刚才发生什么事了吗？'),
                        ('就是今天做什么都不顺', '听起来今天挺挫败的。愿意挑一件事说说吗？')]:
    d.ask(question)
    d.receive(d.request_id, dict(scope=SCOPE, text=reply, actions=[], at='TEST',
                                mode_label='界面测试 · 模拟回复，未调用真实模型', shareable=False))
    app.processEvents()
assert d.grab().save(str(output/'conversation-simulated.png'))
settings = ModelSettingsDialog(parent=d)
settings.show()
app.processEvents()
assert settings.grab().save(str(output/'settings.png'))
settings.reject()
d.reject()
print('PASS: unconfigured state, simulated multi-turn transcript, empty-key settings. No real model called.')
