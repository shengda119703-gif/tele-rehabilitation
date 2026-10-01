import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import queue
import time
import threading
import pytest
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from app.ui.main_window import MainWindow
from app.ui.ankang_assistant import AssistantDialog

class PassiveRuntime:
    def __init__(self):
        self.messages, self.views = queue.Queue(), queue.Queue()
    def command(self, *args, **kwargs):
        pass

class FakeBridge:
    def __init__(self):
        self.sessions = {}
        self.gate = threading.Event()
        self.gate.set()
        self.closed = False
    def open_session(self, session, profile):
        self.sessions[session] = 0
        assert profile['medications'] == []
    def process_turn(self, session, text):
        self.gate.wait(3)
        self.sessions[session] += 1
        return {'reply': {'text': f'{text} reply {self.sessions[session]}'}, 'revision': self.sessions[session]}
    def close_session(self, session):
        pass
    def terminate(self):
        self.gate.set()
    def close(self):
        self.closed = True

def wait_until(app, predicate):
    end = time.monotonic() + 8
    while not predicate() and time.monotonic() < end:
        app.processEvents()
        QTest.qWait(10)
    assert predicate()

@pytest.fixture
def desktop():
    app = QApplication.instance() or QApplication([])
    w = MainWindow(runtime=PassiveRuntime())
    w.show()
    yield w, app
    w._allow_close = True
    w.close()
    if w.assistant_dialog:
        w.assistant_dialog.worker.thread.join(timeout=5)
        assert not w.assistant_dialog.worker.thread.is_alive()
    app.processEvents()


def test_entry_enter_click_and_participant_switch_do_not_cross_sessions(desktop):
    w, app = desktop
    bridge = FakeBridge()
    w.assistant_dialog = AssistantDialog(w, bridge_factory=lambda: bridge)
    QTest.mouseClick(w.assistant_nav, Qt.MouseButton.LeftButton)
    d = w.assistant_dialog
    assert d.isVisible()
    original = w.participant_id
    d.input.setText('合成第一轮')
    bridge.gate.clear()
    QTest.keyClick(d.input, Qt.Key.Key_Return)
    QTest.mouseClick(d.send, Qt.MouseButton.LeftButton)
    assert d.busy and d.isVisible() and w.isVisible()
    w.participant.setText('synthetic-other')
    w._apply_participant()
    assert not d.chat.toPlainText()
    bridge.gate.set()
    wait_until(app, lambda: not d.busy)
    assert not d.chat.toPlainText()
    d.input.setText('另一位用户')
    d.send.click()
    wait_until(app, lambda: not d.busy)
    assert 'reply 1' in d.chat.toPlainText() and '第一轮' not in d.chat.toPlainText()
    w.participant.setText(original)
    w._apply_participant()
    d.input.setText('合成第二轮')
    d.send.click()
    wait_until(app, lambda: not d.busy)
    assert 'reply 2' in d.chat.toPlainText() and '另一位' not in d.chat.toPlainText()
    assert sorted(bridge.sessions.values()) == [1, 2]
    d.close()
    w._show_assistant()
    assert 'reply 2' in d.chat.toPlainText()


def test_missing_node_shows_error_without_closing_main_window(desktop):
    w, app = desktop
    def fail():
        raise FileNotFoundError('Node executable missing')
    w.assistant_dialog = AssistantDialog(w, bridge_factory=fail)
    w._show_assistant()
    d = w.assistant_dialog
    d.input.setText('合成测试')
    d.send.click()
    wait_until(app, lambda: not d.busy)
    assert 'Node executable missing' in d.status.text()
    assert '新会话' in d.status.text() and d.send.isEnabled()
    assert w.isVisible()
