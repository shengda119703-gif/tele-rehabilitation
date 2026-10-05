from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QCheckBox

from .widgets import VideoCanvas
from .video_pair import VideoPairPanel


class CameraTestDialog(QDialog):
    stop_requested = Signal()

    def __init__(self, device_name, parent=None, *, mirror=True, dual_view=None):
        super().__init__(parent)
        self.setWindowTitle('摄像头测试')
        self.setWindowModality(Qt.WindowModality.WindowModal)
        self.resize(760, 560)
        self.setMinimumSize(580, 420)
        self.dual_view = dual_view
        if dual_view:
            self.resize(1060, 680)
            self.setMinimumSize(700, 520)
        self._released = False
        self.stopping = False
        self.last_packet = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        title = QLabel(device_name)
        title.setObjectName('sectionTitle')
        title.setWordWrap(True)
        layout.addWidget(title)
        self.status = QLabel('正在打开摄像头…')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.canvas = VideoCanvas()
        self.canvas.mirror = mirror
        self.canvas.caption = '正在连接摄像头'
        self.canvas.subcaption = '首次连接可能需要几秒'
        self.video_pair = VideoPairPanel(self.canvas)
        self.video_pair.configure(bool(dual_view), (dual_view or {}).get('primary_view', 'frontal'))
        layout.addWidget(self.video_pair, 1)
        self.details = QLabel('只测试'+('两路' if dual_view else '')+'画面，不记录评估、不保存视频')
        self.details.setObjectName('muted')
        layout.addWidget(self.details)
        footer = QHBoxLayout()
        self.mirror_toggle = QCheckBox('镜像预览')
        self.mirror_toggle.setChecked(mirror)
        self.mirror_toggle.toggled.connect(self._set_mirror)
        footer.addWidget(self.mirror_toggle)
        self.frame_info = QLabel()
        self.frame_info.setObjectName('muted')
        footer.addWidget(self.frame_info, 1)
        self.stop_button = QPushButton('关闭摄像头')
        self.stop_button.setObjectName('primary')
        self.stop_button.clicked.connect(self.request_stop)
        footer.addWidget(self.stop_button)
        layout.addLayout(footer)

    def _set_mirror(self, checked):
        self.video_pair.set_mirror(checked)

    def render(self, data):
        if self.stopping:
            return
        packet = data.get('packet')
        if data.get('error'):
            self.show_error(data['error'])
        elif packet is not None and packet.context == data.get('context') and data['state'] == 'PREVIEW':
            self.last_packet = packet
            fresh = self.video_pair.render(data, mirror=self.mirror_toggle.isChecked(), enabled=bool(self.dual_view),
                                           primary_view=(self.dual_view or {}).get('primary_view', 'frontal'))
            self.status.setText(('已收到两路画面，请核对正面与侧面位置' if self.dual_view else '已收到画面，请确认能看清自己')
                                if fresh else '两路画面尚未就绪，请检查设备和接收时间')
            h, w = packet.image.shape[:2]
            fps = packet.received_fps
            self.frame_info.setText(f'{w} × {h} · '+('帧率统计中' if fps is None else f'{fps:.1f} 帧/秒'))
        elif data['state'] != 'PREVIEW':
            self.last_packet = None
            self.video_pair.clear()
            self.frame_info.clear()
            self.canvas.caption = '正在连接摄像头' if data['state'] == 'CONNECTING' else '摄像头未连接'
            self.status.setText('正在打开摄像头…' if data['state'] == 'CONNECTING' else '没有取得画面，请关闭后检查设备并重试')

    def show_error(self, text):
        self.last_packet = None
        self.stopping = False
        self.status.setText(text)
        self.canvas.caption = '暂时无法显示画面'
        self.canvas.subcaption = '关闭后检查权限、占用或连接，再重试'
        self.video_pair.clear()
        self.frame_info.clear()
        self.stop_button.setText('关闭摄像头 / 重试关闭')
        self.stop_button.setEnabled(True)

    def request_stop(self):
        if self._released or self.stopping:
            return
        self.stopping = True
        self.last_packet = None
        self.status.setText('正在关闭摄像头…')
        self.video_pair.clear()
        self.frame_info.clear()
        self.stop_button.setEnabled(False)
        self.stop_requested.emit()

    def finish_close(self):
        self._released = True
        self.video_pair.clear()
        self.accept()

    def reject(self):
        self.request_stop()

    def closeEvent(self, event):
        if self._released:
            event.accept()
        else:
            event.ignore()
            self.request_stop()
