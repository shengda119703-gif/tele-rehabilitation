@echo off
chcp 65001 >nul
cd /d "%~dp0"
"rehab_codex_single_camera_v2_1\.venv\Scripts\python.exe" -m mobile_rehab.server --stop
pause
