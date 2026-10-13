"""Reproducible TEST-only screenshots and browser acceptance; never opens a camera."""
import argparse
from datetime import date
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'rehab_codex_single_camera_v2_1'),str(ROOT/'rehab_codex_single_camera_v2_1/tests')]
from ankang_care_blackbox import Run


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);args=parser.parse_args()
    output=Path(args.output).resolve();output.mkdir(parents=True,exist_ok=False)
    from pytest import MonkeyPatch
    from test_product_window import desktop,wait
    from test_product_care_controls import proposal
    monkeypatch=MonkeyPatch();fixture=desktop.__wrapped__(Path(tempfile.mkdtemp(prefix='agent-ui-')),monkeypatch)
    try:
        w,app=next(fixture);proposal(w);w.navigate('assistant');wait(app,lambda:not w.pending)
        for theme in ('light','dark'):
            w.product_theme.apply(theme);w.care_controls.open.click();app.processEvents()
            for scale in (1,1.25):
                w.care_controls.dialog.resize(int(640*scale),int(480*scale));app.processEvents()
                assert w.care_controls.dialog.grab().save(str(output/f'qt-{theme}-{scale}.png'))
            w.care_controls.dialog.close()
    finally:
        try:next(fixture)
        except StopIteration:pass
        monkeypatch.undo()
    run=Run(output/'service')
    try:
        run.start();run.pair();day=date.today().isoformat()
        status,_=run.request('POST','/api/product/medication.save',{'record':dict(id='TEST-browser',name='TEST 网页确认药',dose='既有说明',status='active')});assert status==200
        run.post('daily.medSchedule',dict(medId='TEST-browser',times=['08:00'],start=day,end=''))
        result=subprocess.run(['node',str(ROOT/'tools/qa/agent-web-acceptance.cjs'),f'http://127.0.0.1:{run.port}',str(output)],cwd=ROOT,capture_output=True,text=True,encoding='utf-8',timeout=120)
        (output/'browser.log').write_text(result.stdout+result.stderr,encoding='utf-8')
        if result.returncode:raise RuntimeError('Browser acceptance failed; inspect browser.log')
        snapshot=run.snapshot();assert snapshot['dailyProduct']['doses']['TEST-browser|'+day+'|08:00']['status']=='taken'
        assert len(snapshot['dailyProduct']['doseAudit'])==1
        (output/'results.json').write_text(json.dumps(dict(completed=True,browser=json.loads(result.stdout),savedDoses=1,qtImages=4),ensure_ascii=False,indent=2),encoding='utf-8')
        print(result.stdout)
    finally:run.stop()


if __name__=='__main__':main()
