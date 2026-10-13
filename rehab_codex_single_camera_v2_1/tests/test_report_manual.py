import os
from pathlib import Path
from PySide6.QtWidgets import QPushButton
from PySide6.QtTest import QTest
from test_product_window import desktop, wait


def test_report_archive_and_manual_entry_use_real_service(desktop):
    w, app = desktop
    w.navigate('health');wait(app,lambda:not w.pending)
    w._request('archive.save',{'name':'TEST 报告','fileName':'report.png','mediaType':'image/png','bytes':[1,2,3],'category':'体检报告','visibility':'private'})
    wait(app,lambda:not w.pending)
    assert any(a['name']=='TEST 报告' for a in w.snapshot['attachments'])
    assert not w.snapshot['history']['measurements']
    texts=[b.text() for b in w.findChildren(QPushButton)]
    assert '手动记录指标' in texts
    assert not any('识别健康图片' in s or '确认识别结果' in s for s in texts)
    assert 'assistantImage' not in w.interface_buttons
    w._open_manual_health();wait(app,lambda:not w.pending);QTest.qWait(120);app.processEvents()
    assert w.health_tabs.currentIndex()==0
    assert w.health_status_sections.currentIndex()==1
    index=w.metric_select.findData('weight');assert index>=0
    w.metric_select.setCurrentIndex(index);w.metric_value.setValue(63)
    w.metric_shared.setChecked(False);w._record_metric();wait(app,lambda:not w.pending)
    m=w.snapshot['history']['measurements'][0]
    assert m['value']==63 and m['unit']=='kg' and m['source']=='manual' and m['visibility']=='private'
    # Screenshots are isolated TEST state and actual Qt widget rendering.
    folder=Path(os.environ.get('ANKANG_REPORT_QA_DIR',str(Path.home()/'AppData/Local/AnkangChecks/report-manual-20261013/screenshots')))
    folder.mkdir(parents=True,exist_ok=True)
    scale=os.environ.get('QT_SCALE_FACTOR','1')
    for mode in ('light','dark'):
        w.product_theme.apply(mode)
        for size in ((800,600),(1100,760)):
            w.resize(*size);w.health_tabs.setCurrentIndex(2);app.processEvents()
            w.grab().save(str(folder/f'archive-{mode}-{size[0]}-scale{scale}.png'))
        w._open_manual_health();wait(app,lambda:not w.pending);QTest.qWait(120);app.processEvents()
        w.grab().save(str(folder/f'manual-{mode}-scale{scale}.png'))
