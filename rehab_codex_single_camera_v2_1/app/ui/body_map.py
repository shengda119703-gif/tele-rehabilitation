from __future__ import annotations

from PySide6.QtCore import Qt, Signal, QRectF, QPointF
from PySide6.QtGui import QPainter, QPen, QColor, QPixmap
from PySide6.QtWidgets import QWidget, QPushButton, QSizePolicy

from ..settings import ROOT
from ..exercise_instructions import JOINT_LABELS


# Display coordinates only: these do not enter pose analysis or side selection.
ANCHORS = {
    'neck': (.50, .174, 'left', .10),
    'shoulder': (.335, .21, 'left', .235),
    'elbow': (.30, .355, 'left', .38),
    'wrist': (.225, .465, 'left', .53),
    'finger': (.80, .53, 'right', .615),
    'trunk': (.50, .37, 'right', .30),
    'hip': (.59, .51, 'right', .46),
    'knee': (.59, .67, 'right', .77),
    'ankle': (.62, .878, 'right', .925),
}


class BodyMap(QWidget):
    """An illustrated menu, not a clinical anatomical locator."""
    joint_selected = Signal(str)

    def __init__(self, parent=None, *, image_path=None):
        super().__init__(parent)
        self.setMinimumSize(350, 350)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setAccessibleName('点击身体部位选择动作')
        self.pixmap = QPixmap(str(image_path or ROOT/'assets/navigation/body-front-v1.png'))
        self.labels, self.markers = {}, {}
        for joint in ANCHORS:
            for collection, text, name in ((self.labels, JOINT_LABELS[joint], 'bodyLabel'),
                                           (self.markers, '+', 'bodyMarker')):
                button = QPushButton(text, self)
                button.setObjectName(name)
                button.setCheckable(True)
                button.setCursor(Qt.CursorShape.PointingHandCursor)
                button.setAccessibleName('选择'+JOINT_LABELS[joint]+('图标' if name == 'bodyMarker' else ''))
                button.clicked.connect(lambda checked=False, j=joint: self.joint_selected.emit(j))
                collection[joint] = button
        self.setStyleSheet('''
            QPushButton#bodyLabel { background: white; color: #493e5c; border: 1px solid #ded8eb;
                border-radius: 10px; padding: 0; font-size: 15px; font-weight: 600; }
            QPushButton#bodyMarker { background: #f8f5ff; color: #7048df; border: 2px solid #b5a0ee;
                border-radius: 17px; padding: 0; font-size: 20px; font-weight: 600; min-height: 0; }
            QPushButton#bodyLabel:checked, QPushButton#bodyMarker:checked {
                background: #7048df; color: white; border-color: #7048df; }
            QPushButton#bodyLabel:hover, QPushButton#bodyMarker:hover { border: 2px solid #7048df; }
            QPushButton#bodyLabel:focus, QPushButton#bodyMarker:focus { border: 3px solid #3d247c; }
        ''')

    def select_joint(self, joint):
        for key in ANCHORS:
            self.labels[key].setChecked(key == joint)
            self.markers[key].setChecked(key == joint)

    def image_rect(self):
        # Leave two dedicated label lanes so both names and markers remain usable.
        height = min(self.height()-12, (self.width()-130)*1.5)
        width = height/1.5
        return QRectF((self.width()-width)/2, (self.height()-height)/2, width, height)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        rect = self.image_rect()
        for joint, (x, y, lane, label_y) in ANCHORS.items():
            cx, cy = rect.left()+x*rect.width(), rect.top()+y*rect.height()
            self.markers[joint].setGeometry(round(cx-17), round(cy-17), 34, 34)
            lx = 4 if lane == 'left' else self.width()-82
            ly = max(2, min(self.height()-42, round(rect.top()+label_y*rect.height()-20)))
            self.labels[joint].setGeometry(lx, ly, 78, 40)

    def paintEvent(self, event):
        colors=getattr(self,'_care_colors',{})
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        if not self.pixmap.isNull():
            painter.drawPixmap(self.image_rect(), self.pixmap, QRectF(self.pixmap.rect()))
        else:
            painter.setPen(QColor(colors.get('secondary','#756a86')))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, '请选择部位名称')
        painter.setPen(QPen(QColor(colors.get('border','#b7a6d8')), 1.2))
        for joint, (_, _, lane, _) in ANCHORS.items():
            label = self.labels[joint].geometry()
            marker = self.markers[joint].geometry()
            painter.drawLine(QPointF(label.right() if lane == 'left' else label.left(), label.center().y()),
                             QPointF(marker.center()))
