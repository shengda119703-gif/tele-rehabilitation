"""Painting may evolve; native tab behavior must stay authoritative."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import pytest
from PySide6.QtCore import Qt, QAbstractAnimation
from PySide6.QtTest import QTest, QSignalSpy
from PySide6.QtWidgets import QApplication, QWidget
from app.ui.product_segments import SegmentTabs


@pytest.fixture
def segments():
    app=QApplication.instance() or QApplication([])
    tabs=SegmentTabs()
    for title in ('我的档案','身体记录','资料与图片','旧入口','全部记录与报告'):
        tabs.addTab(QWidget(), title)
    tabs.setTabVisible(3,False);tabs.setTabEnabled(2,False)
    tabs.resize(740,300);tabs.show();QTest.qWait(30)
    yield tabs,app
    tabs.close();tabs.deleteLater();app.processEvents()


def test_keyboard_keeps_native_hidden_disabled_and_single_signal(segments):
    tabs,app=segments;bar=tabs.tabBar();bar.setFocus()
    spy=QSignalSpy(tabs.currentChanged)
    QTest.keyClick(bar,Qt.Key_Right)
    assert tabs.currentIndex()==1 and spy.count()==1
    QTest.keyClick(bar,Qt.Key_Right)
    assert tabs.currentIndex()==4 and spy.count()==2
    assert bar.hasFocus()


def test_elastic_feedback_survives_fast_switch_and_resizes(segments,monkeypatch):
    monkeypatch.setenv('ANKANG_REDUCED_MOTION','0')
    tabs,app=segments;bar=tabs.tabBar()
    tabs.setCurrentIndex(1);QTest.qWait(70)
    assert bar._motion.state()==QAbstractAnimation.Running
    assert bar._thumb!=bar._destination()
    tabs.setCurrentIndex(4);QTest.qWait(340)
    assert bar._thumb==bar._destination()
    tabs.resize(640,300);QTest.qWait(30)
    assert bar._thumb==bar._destination()


def test_reduced_motion_and_disabled_pointer_do_not_change_selection(segments,monkeypatch):
    monkeypatch.setenv('ANKANG_REDUCED_MOTION','1')
    tabs,app=segments;bar=tabs.tabBar();tabs.setCurrentIndex(4)
    assert bar._motion.state()==QAbstractAnimation.Stopped and bar._thumb==bar._destination()
    before=tabs.currentIndex();bar.setEnabled(False)
    QTest.mouseClick(bar,Qt.LeftButton,pos=bar.tabRect(0).center())
    assert tabs.currentIndex()==before
