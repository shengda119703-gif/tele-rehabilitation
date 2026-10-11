import os
from pathlib import Path
import subprocess
import sys
import json
import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtWidgets import QApplication, QLineEdit
from app.deepseek_config import config_path, load_key
from app.ui.deepseek_developer import DeepSeekDeveloperDialog


@pytest.mark.skipif(sys.platform != 'win32', reason='Windows desktop launcher regression')
def test_redirected_pythonw_can_restart_bridge(tmp_path):
    root = Path(__file__).resolve().parents[2]
    pythonw = Path(sys.executable).with_name('pythonw.exe')
    if not pythonw.exists():
        pytest.skip('pythonw unavailable')
    probe = tmp_path / 'reload.py'
    result = tmp_path / 'result.json'
    probe.write_text(
        'import sys,json,traceback\nfrom pathlib import Path\n'
        f'sys.path.insert(0,{str(root)!r})\n'
        'from bridges.ankang.client import AgentBridge\n'
        'out=[]\ntry:\n'
        ' for i in range(3):\n'
        f'  with AgentBridge(data_dir={str(tmp_path / "product")!r}) as b:\n'
        "   assert isinstance(b.product('profile.list'),list)\n"
        '  out.append("ok")\n'
        'except Exception:\n out.append(traceback.format_exc())\n'
        f'Path({str(result)!r}).write_text(json.dumps(out),encoding="utf-8")\n',
        encoding='utf-8')
    def quote(path):
        return "'" + str(path).replace("'", "''") + "'"
    command = (
        f'$p=Start-Process -FilePath {quote(pythonw)} '
        f'-ArgumentList {quote(chr(34) + str(probe) + chr(34))} -WindowStyle Hidden '
        f'-RedirectStandardOutput {quote(tmp_path / "stdout.log")} '
        f'-RedirectStandardError {quote(tmp_path / "stderr.log")} -PassThru; '
        'if (-not $p.WaitForExit(20000)) { $p.Kill(); exit 1 }; exit $p.ExitCode')
    subprocess.run(['powershell.exe', '-NoProfile', '-Command', command],
                   check=True, capture_output=True, timeout=30)
    assert json.loads(result.read_text(encoding='utf-8')) == ['ok', 'ok', 'ok']


def test_dialog_persistence_masking_and_clear(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv('APPDATA', str(tmp_path))
    app = QApplication.instance() or QApplication([])
    dialog = DeepSeekDeveloperDialog()
    credential = 'synthetic-development-credential'
    dialog.key_input.setText(credential)
    assert dialog.key_input.echoMode() == QLineEdit.Password
    assert credential not in dialog.key_input.displayText()
    dialog.save_button.click()
    assert load_key() == credential
    assert config_path().is_relative_to(tmp_path)
    # A fresh process reads the saved file, without printing the credential.
    result = subprocess.run([sys.executable, '-c',
        'from app.deepseek_config import load_key; assert bool(load_key())'],
        capture_output=True, text=True, check=True)
    reopened = DeepSeekDeveloperDialog()
    assert reopened.key_input.text() == credential
    assert credential not in reopened.key_input.displayText()
    reopened.clear_button.click()
    assert load_key() == ''
    assert not config_path().exists()
    assert credential not in result.stdout + result.stderr + capsys.readouterr().out


def test_adapter_local_priority_fixed_endpoint_clear_and_environment(tmp_path, monkeypatch):
    monkeypatch.setenv('APPDATA', str(tmp_path))
    root = Path(__file__).resolve().parents[2]
    adapter = root / 'ankang/route1-health-agent/scripts/rehab-model.cjs'
    script = r'''
      const assert = require('node:assert/strict');
      const fs = require('node:fs');
      const {createRehabModel} = require(process.argv[1]);
      const file = process.argv[2];
      delete process.env.ANKANG_REHAB_LLM_API_KEY;
      assert.equal(createRehabModel(() => {}), undefined);
      fs.mkdirSync(require('node:path').dirname(file), {recursive:true});
      fs.writeFileSync(file, JSON.stringify({api_key:'synthetic-local'}));
      process.env.ANKANG_REHAB_LLM_API_KEY = 'synthetic-environment';
      process.env.ANKANG_REHAB_LLM_URL = 'https://ignored.invalid';
      process.env.ANKANG_REHAB_LLM_MODEL = 'ignored';
      let expected = 'synthetic-local';
      global.fetch = async (url, options) => {
        assert.equal(String(url), 'https://api.deepseek.com/chat/completions');
        assert.equal(JSON.parse(options.body).model, 'deepseek-flash');
        assert.equal(options.headers.Authorization, 'Bearer ' + expected);
        return {ok:true, json:async()=>({choices:[{message:{content:'OK'}}]})};
      };
      (async () => {
        await createRehabModel(() => {}).describe('连接测试', {});
        fs.unlinkSync(file);
        expected = 'synthetic-environment';
        await createRehabModel(() => {}).describe('连接测试', {});
        global.fetch = async () => { throw new Error(expected); };
        await assert.rejects(createRehabModel(() => {}).describe('连接测试', {}),
          error => error.message === '康复模型连接失败或超时' && !error.message.includes(expected));
        delete process.env.ANKANG_REHAB_LLM_API_KEY;
        assert.equal(createRehabModel(() => {}), undefined);
      })().catch(() => { process.exitCode = 1; });
    '''
    result = subprocess.run(['node', '-e', script, str(adapter), str(config_path())],
                            capture_output=True, text=True)
    assert result.returncode == 0
    assert not result.stdout and not result.stderr
