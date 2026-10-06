@echo off
chcp 65001 >nul
cd /d "%~dp0..\..\"
"rehab_codex_single_camera_v2_1\.venv\Scripts\python.exe" -m pip install -r mobile_rehab\requirements.voice.txt
if errorlevel 1 (
  echo 语音依赖安装失败。
  pause
  exit /b 1
)
"rehab_codex_single_camera_v2_1\.venv\Scripts\python.exe" -m mobile_rehab.prepare_voice
if errorlevel 1 (
  echo 模型准备失败。可继续使用手机键盘语音输入。
  pause
  exit /b 1
)
echo 手机录音识别已准备，刷新管家页面即可。
pause
