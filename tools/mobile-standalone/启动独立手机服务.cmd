@echo off
chcp 65001 >nul
cd /d "%~dp0..\..\"
if not exist "rehab_codex_single_camera_v2_1\.venv\Scripts\python.exe" (
  echo 未找到项目 Python 环境，请先完成电脑版安装。
  pause
  exit /b 1
)
"rehab_codex_single_camera_v2_1\.venv\Scripts\python.exe" -c "import fastapi, uvicorn, imageio_ffmpeg" >nul 2>nul
if errorlevel 1 (
  echo 首次安装手机网页依赖...
  "rehab_codex_single_camera_v2_1\.venv\Scripts\python.exe" -m pip install -r mobile_rehab\requirements.txt
  if errorlevel 1 (
    echo 依赖安装失败，请检查网络后重试。
    pause
    exit /b 1
  )
)
if exist "ankang\route1-health-agent\node_modules\typescript\bin\tsc" (
  pushd "ankang\route1-health-agent"
  call npm.cmd run build:bridge
  if errorlevel 1 (
    echo 健康模块编译失败，请运行准备手机健康服务后重试。
    popd
    pause
    exit /b 1
  )
  popd
) else (
  echo 如需健康档案与管家，请先运行准备手机健康服务.cmd。
)
"rehab_codex_single_camera_v2_1\.venv\Scripts\python.exe" -m mobile_rehab.server --host 0.0.0.0 --port 8765
pause
