@echo off
chcp 65001 >nul
setlocal
set "agent_app=%~dp0rehab_codex_single_camera_v2_1"
set "agent_python=%REHAB_PYTHON%"
if not defined agent_python set "agent_python=%agent_app%\.venv\Scripts\python.exe"
if not exist "%agent_python%" set "agent_python=%~dp0..\.agent-test-env\Scripts\python.exe"
if not exist "%agent_python%" (
  echo 未找到运行环境。请安装项目依赖，或通过 REHAB_PYTHON 指定 Python 程序路径。
  pause
  exit /b 1
)
if not exist "%agent_app%\app\main.py" (
  echo 找不到应用代码，请把此启动文件保留在仓库根目录。
  pause
  exit /b 1
)
set "QT_QPA_PLATFORM=windows"
cd /d "%agent_app%"
"%agent_python%" -m app.main --data-dir qa-output/manual-agent-deepseek
if errorlevel 1 (
  echo.
  echo 启动失败，请保留上方错误信息以便排查。
  pause
)
endlocal
