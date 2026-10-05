"""Native tabs with a continuous selection well inspired by React Bits RubberSegment.

Only painting changes. Qt still owns selection, focus, accessibility and input.
"""
from math import sin, pi
from PySide6.QtCore import QSize, QRectF, Qt, QVariantAnimation
from PySide6.QtGui import QPainter, QPalette, QPen
from PySide6.QtWidgets import QTabBar, QTabWidget
from .product_motion import reduced_motion


class SegmentBar(QTabBar):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setExpanding(False)
        self.setDrawBase(False)
        self.setUsesScrollButtons(True)
        self.setElideMode(Qt.ElideNone)
        self._thumb = QRectF()
        self._start = QRectF()
        self._end = QRectF()
        self._layout_signature = None
        self._motion = QVariantAnimation(self)
        self._motion.setDuration(300)
        self._motion.setStartValue(0.0)
        self._motion.setEndValue(1.0)
        self._motion.valueChanged.connect(self._travel)
        self.currentChanged.connect(self._select)
        self.setProperty('segmented', True)

    def tabSizeHint(self, index):
        size = super().tabSizeHint(index)
        return QSize(max(size.width(), self.fontMetrics().horizontalAdvance(self.tabText(index)) + 32), max(44, size.height()))

    def _destination(self):
        index = self.currentIndex()
        return QRectF(self.tabRect(index)).adjusted(3, 4, -3, -4) if index >= 0 and self.isTabVisible(index) else QRectF()

    def _select(self, *_):
        end = self._destination()
        self._motion.stop()
        if end.isEmpty() or self._thumb.isEmpty() or not self.isVisible() or reduced_motion():
            self._thumb = end
            self.update()
            return
        self._start = QRectF(self._thumb)
        self._end = end
        self._motion.start()

    def _travel(self, value):
        # The leading edge arrives first; the trailing edge catches up and settles.
        # Rapid switches restart from the actual painted position, without callbacks.
        t = float(value)
        ease = lambda v: 1 - (1 - min(1, max(0, v))) ** 3
        lead, trail = ease(t / .6), ease((t - .18) / .82)
        forward = self._end.center().x() >= self._start.center().x()
        left_t, right_t = (trail, lead) if forward else (lead, trail)
        left = self._start.left() + (self._end.left() - self._start.left()) * left_t
        right = self._start.right() + (self._end.right() - self._start.right()) * right_t
        settle = 2 * sin(pi * min(1, max(0, (t - .7) / .3)))
        if forward: left += settle
        else: right -= settle
        self._thumb = QRectF(left, self._end.top(), max(0, right - left), self._end.height())
        self.update()

    def tabLayoutChange(self):
        super().tabLayoutChange()
        if hasattr(self, '_motion'):
            # ContentTabs changes its active pane height on selection. Qt emits
            # tabLayoutChange even when tab geometry is unchanged; that must not
            # cancel the selection feedback. Real resize/hide/reflow still snaps.
            signature = tuple((self.isTabVisible(i), self.tabRect(i)) for i in range(self.count()))
            if signature != self._layout_signature:
                self._layout_signature = signature
                self._motion.stop()
                self._thumb = self._destination()
            self.update()

    def showEvent(self, event):
        super().showEvent(event)
        self._thumb = self._destination()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        palette = self.palette()
        visible = [i for i in range(self.count()) if self.isTabVisible(i)]
        if not visible:
            return
        track = QRectF(self.tabRect(visible[0]))
        for i in visible[1:]:
            track = track.united(QRectF(self.tabRect(i)))
        painter.setPen(Qt.NoPen)
        painter.setBrush(palette.color(QPalette.AlternateBase))
        painter.drawRoundedRect(track, 9, 9)
        if not self._thumb.isEmpty():
            painter.setBrush(palette.color(QPalette.Base))
            painter.drawRoundedRect(self._thumb, 6, 6)
        for i in visible:
            enabled = self.isEnabled() and self.isTabEnabled(i)
            group = QPalette.Active if enabled else QPalette.Disabled
            painter.setPen(palette.color(group, QPalette.Text if i == self.currentIndex() else QPalette.WindowText))
            font = self.font(); font.setBold(i == self.currentIndex()); painter.setFont(font)
            painter.drawText(self.tabRect(i), Qt.AlignCenter, self.tabText(i))
        if self.hasFocus() and self.currentIndex() >= 0:
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(palette.color(QPalette.Text), 1.5))
            painter.drawRoundedRect(self._destination().adjusted(1, 1, -1, -1), 5, 5)


class SegmentTabs(QTabWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTabBar(SegmentBar(self))
