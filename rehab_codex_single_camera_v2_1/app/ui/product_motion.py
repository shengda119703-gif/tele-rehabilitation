"""Small, interruptible transitions tied to actual UI state, never to inferred progress."""
import os
from PySide6.QtCore import QObject, QEvent, QRect, QPropertyAnimation, QEasingCurve, QSettings, Qt
from PySide6.QtWidgets import QFrame, QGraphicsOpacityEffect


def reduced_motion():
    return os.environ.get('ANKANG_REDUCED_MOTION') == '1' or QSettings('Ankang', 'ProductUI').value('reducedMotion', False, type=bool)


class SelectionRail(QObject):
    """One marker travels between native, keyboard accessible navigation buttons."""
    def __init__(self, parent):
        super().__init__(parent)
        self.target = None
        self.mark = QFrame(parent)
        self.mark.setObjectName('productSelectionRail')
        self.mark.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.mark.hide()
        self.animation = QPropertyAnimation(self.mark, b'geometry', self)
        self.animation.setDuration(300)
        self.animation.setEasingCurve(QEasingCurve.OutCubic)

    def select(self, target):
        if self.target is not None:
            self.target.removeEventFilter(self)
        self.target = target
        if target is None:
            self.animation.stop(); self.mark.hide(); return
        target.installEventFilter(self)
        self.position(True)

    def position(self, animate=False):
        if self.target is None: return
        target = self.target
        point = target.mapTo(self.mark.parentWidget(), target.rect().topLeft())
        destination = QRect(point.x(), point.y(), target.width(), target.height())
        start = self.mark.geometry()
        visible = self.mark.isVisible()
        self.animation.stop()
        self.mark.show(); self.mark.stackUnder(target)
        if animate and visible and not reduced_motion():
            # Rubber Segment stretch/catch/settle adapted to native navigation.
            # The original buttons retain focus, clicks and enabled semantics.
            self.animation.setKeyValueAt(.38,start.united(destination))
            self.animation.setKeyValueAt(.78,destination.adjusted(0,-2,0,2))
            self.animation.setStartValue(start); self.animation.setEndValue(destination); self.animation.start()
        else:
            self.mark.setGeometry(destination)

    def eventFilter(self, obj, event):
        if event.type() in (QEvent.Resize, QEvent.Move, QEvent.Show): self.position()
        return False


def reveal_receipt(widget):
    """A real response receipt settles once; it never indicates success by itself."""
    if reduced_motion() or not widget.isVisible(): return
    animation = getattr(widget, '_receipt_animation', None)
    if animation is None:
        effect = QGraphicsOpacityEffect(widget); widget.setGraphicsEffect(effect)
        animation = QPropertyAnimation(effect, b'opacity', widget)
        animation.setDuration(180); animation.setEasingCurve(QEasingCurve.OutCubic)
        widget._receipt_animation = animation
    animation.stop(); animation.setStartValue(.45); animation.setEndValue(1.0); animation.start()
