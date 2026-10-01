"""Minimal desktop adapter. All Agent behavior stays behind the existing bridge."""
from __future__ import annotations

import queue
import sys
import threading
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPlainTextEdit, QLineEdit, QPushButton


def create_bridge():
    # Source checkout is launched with the application directory as cwd.
    # Import the single repository bridge, never duplicate its wire protocol here.
    root = str(Path(__file__).resolve().parents[3])
    if root not in sys.path:
        sys.path.insert(0, root)
    from bridges.ankang.client import AgentBridge
    return AgentBridge()


def empty_profile():
    # Required Runtime defaults only: no rehabilitation profile or records are read.
    return dict(name='用户', age=0, conditions=[], medications=[], familyContact='', familyPhone='',
                mobility='unknown', usesCane=False, nightVision='unknown', cognition='unknown', familySharing='denied')


class AssistantWorker:
    """One serial worker owns the existing synchronous client and its sessions."""
    def __init__(self, factory):
        self.factory = factory
        self.jobs, self.results = queue.Queue(), queue.Queue()
        self.stopping = threading.Event()
        self.bridge = None
        self.in_flight = threading.Event()
        self.interrupted = False
        self.thread = threading.Thread(target=self._run, daemon=True, name='ankang-assistant')
        self.thread.start()

    def _run(self):
        sessions = set()
        try:
            while not self.stopping.is_set():
                job = self.jobs.get()
                if job is None or self.stopping.is_set():
                    break
                participant_id, text = job
                session_id = 'rehab:' + participant_id
                self.in_flight.set()
                try:
                    if self.bridge is None:
                        self.bridge = self.factory()
                    if self.stopping.is_set():
                        break
                    if session_id not in sessions:
                        self.bridge.open_session(session_id, empty_profile())
                        sessions.add(session_id)
                    result = self.bridge.process_turn(session_id, text)
                    self.results.put((participant_id, result, None))
                except Exception as error:
                    if self.bridge:
                        self.bridge.terminate()
                        self.bridge.close()
                        self.bridge = None
                    sessions.clear()
                    self.results.put((participant_id, None, str(error)))
                finally:
                    self.in_flight.clear()
        finally:
            if self.bridge:
                try:
                    if not self.interrupted:
                        self.bridge.timeout = 2
                        for session_id in sessions:
                            self.bridge.close_session(session_id)
                except Exception:
                    self.bridge.terminate()
                finally:
                    self.bridge.close()

    def shutdown(self):
        self.stopping.set()
        self.jobs.put(None)
        bridge = self.bridge
        if bridge and self.in_flight.is_set():
            self.interrupted = True
            bridge.terminate()


class AssistantDialog(QDialog):
    def __init__(self, parent=None, bridge_factory=create_bridge):
        super().__init__(parent)
        self.setWindowTitle('安康助手')
        self.resize(620, 520)
        self.participant_id = ''
        self.histories = {}
        self.busy = False
        self.last_result = None
        self.worker = AssistantWorker(bridge_factory)
        layout = QVBoxLayout(self)
        self.person = QLabel()
        self.person.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.person)
        note = QLabel('对话仅保留在本次应用会话中。')
        layout.addWidget(note)
        self.chat = QPlainTextEdit()
        self.chat.setReadOnly(True)
        self.chat.setAccessibleName('助手对话')
        layout.addWidget(self.chat)
        row = QHBoxLayout()
        self.input = QLineEdit()
        self.input.setPlaceholderText('输入想对助手说的话')
        self.input.setAccessibleName('助手输入')
        row.addWidget(self.input)
        self.send = QPushButton('发送')
        self.send.setAutoDefault(False)
        self.send.setDefault(False)
        row.addWidget(self.send)
        layout.addLayout(row)
        self.status = QLabel('')
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.send.clicked.connect(self._send)
        self.input.returnPressed.connect(self._send)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._poll)
        self.timer.start(30)

    def set_participant(self, participant_id):
        if participant_id != self.participant_id:
            self.participant_id = participant_id
            self.input.clear()
            self.last_result = None
            self._render()
        self.person.setText(f'当前用户：{participant_id}')
        self.send.setEnabled(bool(participant_id) and not self.busy)
        self.status.setText('正在处理…' if self.busy else '')

    def _render(self):
        self.chat.setPlainText('\n\n'.join(self.histories.get(self.participant_id, [])))
        self.chat.verticalScrollBar().setValue(self.chat.verticalScrollBar().maximum())

    def _send(self):
        text = self.input.text().strip()
        if self.busy or not text or not self.participant_id:
            return
        self.histories.setdefault(self.participant_id, []).append('你：' + text)
        self.input.clear()
        self.busy = True
        self.send.setEnabled(False)
        self.status.setText('正在处理…')
        self._render()
        self.worker.jobs.put((self.participant_id, text))

    def _poll(self):
        try:
            participant_id, result, error = self.worker.results.get_nowait()
        except queue.Empty:
            return
        self.busy = False
        self.send.setEnabled(bool(self.participant_id))
        if error:
            # The process/session was reset. Do not present old chat as current Agent context.
            self.histories.clear()
            self.last_result = None
            self.status.setText('助手不可用：' + error + '。本轮未完成，下次发送将开启新会话。')
        else:
            self.histories.setdefault(participant_id, []).append('安康：' + result['reply']['text'])
            self.status.setText('')
            if participant_id == self.participant_id:
                self.last_result = result
        self._render()

    def shutdown(self):
        self.timer.stop()
        self.send.setEnabled(False)
        self.worker.shutdown()
