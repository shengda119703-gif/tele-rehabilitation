@echo off
chcp 65001 >nul
cd /d "%~dp0ankang\route1-health-agent"
where node >nul 2>nul
if errorlevel 1 (
  echo 请先安装 Node.js 22 或更新版本，再运行本文件。
  pause
  exit /b 1
)
if not exist "node_modules\typescript\bin\tsc" (
  call npm.cmd ci
  if errorlevel 1 (
    echo 安装依赖失败，请检查网络。
    pause
    exit /b 1
  )
)
call npm.cmd run build:bridge
if errorlevel 1 (
  echo 健康服务准备失败，请保留窗口错误信息。
  pause
  exit /b 1
)
echo 健康服务已准备。请重新启动手机康复网页。
pause
