"""Decode compatibility fixtures, not action/clinical accuracy evidence."""
import queue
import threading

import cv2
import numpy as np
import pytest

from app.domain import Context
from app.source_worker import _capture


def run_capture(monkeypatch, timestamps, options=None):
    acknowledgements = queue.Queue()
    class Slot(queue.Queue):
        def cancel_join_thread(self):
            pass
    class Frames(Slot):
        def put(self, value, **kw):
            super().put(value, **kw)
            acknowledgements.put(value.seq)
    class Capture:
        index = -1
        released = False
        def isOpened(self):
            return True
        def read(self):
            self.index += 1
            if self.index >= len(timestamps):
                return False, None
            return True, np.zeros((40, 60, 3), dtype=np.uint8)
        def get(self, prop):
            return 30 if prop == cv2.CAP_PROP_FPS else timestamps[self.index]*1000
        def set(self, prop, value):
            return True
        def release(self):
            self.released = True
    cap = Capture()
    monkeypatch.setattr(cv2, 'VideoCapture', lambda *args: cap)
    frames, statuses = Frames(), Slot()
    _capture(dict(kind='REPLAY_FILE', path='fixture.mp4'),
             Context(1, 'rehab', 'fixture', 'REPLAY_FILE', 'TEST', 'run'),
             dict(speed=1000, **(options or {})), frames, statuses,
             queue.Queue(), acknowledgements, threading.Event())
    return list(frames.queue), list(statuses.queue), cap


def test_small_negative_phone_preroll_is_omitted_not_retimed(monkeypatch):
    frames, statuses, cap = run_capture(monkeypatch, [-1/30, 1/30, 2/30, 3/30])
    assert [p.time_s for p in frames] == pytest.approx([1/30, 2/30, 3/30])
    assert all(p.time_basis == 'opencv_media_pts' for p in frames)
    assert [p.seq for p in frames] == [1, 2, 3]
    skipped = next(s for s in statuses if s['status'] == 'REPLAY_PREROLL_SKIPPED')
    assert skipped['skipped_frames'] == 1
    assert skipped['raw_time_s'] == pytest.approx(-1/30)
    assert not any(s['status'] == 'ERROR' for s in statuses)
    assert cap.released


@pytest.mark.parametrize('times,options', [
    ([-1., .033], {}), ([float('nan'), .033], {}),
    ([0., 0.], {}), ([0., -.033], {}), ([.1, .05], {}),
    ([-.033, .033], {'seek_s': 1}),
    ([-.05]*5+[.033], {}),
])
def test_invalid_or_nonleading_times_still_fail(monkeypatch, times, options):
    frames, statuses, cap = run_capture(monkeypatch, times, options)
    assert any(s['status'] == 'ERROR' for s in statuses)
    assert cap.released


def test_normal_zero_origin_is_unchanged(monkeypatch):
    frames, statuses, _ = run_capture(monkeypatch, [0., .033, .067])
    assert [p.time_s for p in frames] == [0., .033, .067]
    assert not any(s['status'] in ('ERROR', 'REPLAY_PREROLL_SKIPPED') for s in statuses)
