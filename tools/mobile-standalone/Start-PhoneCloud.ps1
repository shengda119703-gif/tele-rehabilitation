param([string]$HostAddress='127.0.0.1',[int]$Port=8770)
$ErrorActionPreference='Stop'
$taskRoot=(Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$taskPython=Join-Path $taskRoot 'rehab_codex_single_camera_v2_1/.venv/Scripts/python.exe'
if(-not(Test-Path -LiteralPath $taskPython)){throw 'Project Python environment is missing.'}
Push-Location $taskRoot
try { & $taskPython -m mobile_rehab.phone_cloud --host $HostAddress --port $Port --data-dir (Join-Path $taskRoot '.runtime/phone-cloud') } finally { Pop-Location }
