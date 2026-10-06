"""Check the native Windows lock; programmatic button clicks cannot detect it."""
import ctypes
import sys

import pytest
from PySide6.QtCore import QEvent, QObject
from PySide6.QtWidgets import QApplication
from test_product_window import desktop, wait


class ModalEvents(QObject):
    def __init__(self, parent):
        super().__init__(parent)
        self.events = []

    def eventFilter(self, obj, event):
        if event.type() in (QEvent.WindowBlocked, QEvent.WindowUnblocked):
            self.events.append(event.type())
        return False


@pytest.mark.parametrize('opener,attribute', [
    ('_automatic_plan', 'automatic_dialog'),
    ('_plan_library', 'plan_library_dialog'),
])
def test_embedded_plan_releases_native_modal_lock(desktop, opener, attribute):
    w, app = desktop
    if sys.platform != 'win32' or app.platformName() != 'windows':
        pytest.skip('Requires the native Windows platform, not offscreen Qt')
    enabled = ctypes.windll.user32.IsWindowEnabled
    enabled.argtypes = [ctypes.c_void_p]
    enabled.restype = ctypes.c_bool
    w.navigate('rehab')
    wait(app, lambda: not w.pending)
    monitor = ModalEvents(w)
    w.windowHandle().installEventFilter(monitor)
    for _ in range(2):
        w.legacy.busy = 0
        getattr(w, opener)()
        app.processEvents()
        dialog = getattr(w.legacy, attribute)
        assert dialog is not None and not dialog.isWindow()
        assert QApplication.activeModalWidget() is None
        assert enabled(int(w.winId())), 'Native parent remained disabled'
        # PassiveRuntime never replies; release only its presentation busy state.
        for command, count in list(w.legacy.pending_commands.items()):
            for _ in range(count):
                w.legacy.runtime.messages.put(dict(kind='command_done', command=command))
        wait(app, lambda: not w.legacy.busy)
        dialog.set_busy(False)
        wait(app, lambda: dialog.close_button.isEnabled())
        dialog.close_button.click()
        wait(app, lambda: getattr(w.legacy, attribute) is None and not w.pending)
        assert enabled(int(w.winId()))
    assert monitor.events.count(QEvent.WindowBlocked) == 2
    assert monitor.events.count(QEvent.WindowUnblocked) == 2
