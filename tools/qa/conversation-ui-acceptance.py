"""Actual native/browser offline chat flow, isolated TEST data and owned processes."""
import argparse
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
    monkeypatch=MonkeyPatch();fixture=desktop.__wrapped__(Path(tempfile.mkdtemp(prefix='conversation-ui-')),monkeypatch)
    try:
        w,app=next(fixture);w.navigate('assistant');wait(app,lambda:not w.pending)
        before=len(w.snapshot['state']['events'])
        w.chat_input.setPlainText('你喜欢我吗');w._send_chat();wait(app,lambda:not w.pending)
        metadata=w.snapshot['state']['chat'][-1].get('conversation')
        assert metadata=={'provider':'local','status':'unavailable','reason':'not_configured'},metadata
        assert '未配置 DeepSeek · 本地回复' in w.chat.toPlainText()
        assert len(w.snapshot['state']['events'])==before
        for theme in ('light','dark'):
            w.product_theme.apply(theme)
            for width,height in ((1024,720),(1440,900)):
                w.resize(width,height);app.processEvents()
                assert w.chat.grab().save(str(output/f'qt-chat-{theme}-{width}.png'))
        (output/'native-results.json').write_text(json.dumps(dict(completed=True,metadata=metadata,eventsUnchanged=True,images=4),ensure_ascii=False,indent=2),encoding='utf-8')
    finally:
        try:next(fixture)
        except StopIteration:pass
        monkeypatch.undo()
    run=Run(output/'service')
    try:
        run.start();run.pair()
        result=subprocess.run(['node',str(ROOT/'tools/qa/conversation-web-acceptance.cjs'),f'http://127.0.0.1:{run.port}',str(output)],cwd=ROOT,capture_output=True,text=True,encoding='utf-8',timeout=120)
        (output/'browser.log').write_text(result.stdout+result.stderr,encoding='utf-8')
        if result.returncode:raise RuntimeError('Browser acceptance failed; inspect browser.log')
        (output/'results.json').write_text(json.dumps(dict(completed=True,nativeImages=4,browser=json.loads(result.stdout)),ensure_ascii=False,indent=2),encoding='utf-8')
        print(result.stdout)
    finally:run.stop()


if __name__=='__main__':main()
