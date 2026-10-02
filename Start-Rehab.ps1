param([string]$PythonPath = '')
$ErrorActionPreference = 'Stop'
$taskRoot = Join-Path $PSScriptRoot 'rehab_codex_single_camera_v2_1'
$taskPython = if ($PythonPath) { $PythonPath } else { Join-Path $taskRoot '.venv\Scripts\pythonw.exe' }
if (-not (Test-Path -LiteralPath $taskPython)) {
    throw 'Project environment is missing. Run Setup-Rehab.ps1 first; add -IncludeLandmarks for wrist, ankle and finger tasks.'
}
$taskAgentRoot = Join-Path $PSScriptRoot 'ankang\route1-health-agent'
if (-not (Get-Command node -ErrorAction SilentlyContinue)) { throw 'Node.js 22+ is required. Install Node.js, then run Setup-Rehab.ps1.' }
if (-not (Test-Path -LiteralPath (Join-Path $taskAgentRoot 'node_modules\typescript\bin\tsc'))) {
    throw 'Ankang product dependencies are missing. Run Setup-Rehab.ps1 first.'
}
& node (Join-Path $taskAgentRoot 'scripts\build-agent-bridge.cjs')
if ($LASTEXITCODE -ne 0) { throw 'Ankang product bridge build failed; application was not started.' }
$taskRuntimeDir = Join-Path $taskRoot '.runtime'
New-Item -ItemType Directory -Path $taskRuntimeDir -Force | Out-Null
Start-Process -FilePath $taskPython -ArgumentList @('-m','app.main') -WorkingDirectory $taskRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $taskRuntimeDir 'app-stdout.log') -RedirectStandardError (Join-Path $taskRuntimeDir 'app-stderr.log')
