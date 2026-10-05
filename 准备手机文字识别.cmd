@echo off
chcp 65001 >nul
cd /d "%~dp0"
"rehab_codex_single_camera_v2_1\.venv\Scripts\python.exe" -m pip install -r mobile_rehab\requirements.ocr.txt
if errorlevel 1 (
  echo 文字识别依赖安装失败。
  pause
  exit /b 1
)
echo 本地资料文字识别已准备，刷新健康资料页面即可。
pause
