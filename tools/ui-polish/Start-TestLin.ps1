param([int]$Port = 8876, [switch]$NoBrowser)
$ErrorActionPreference = 'Stop'
$taskRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '../..')).Path
$taskPython = Join-Path $taskRoot 'rehab_codex_single_camera_v2_1/.venv/Scripts/python.exe'
$taskScript = Join-Path $PSScriptRoot 'serve-review.py'
$taskData = Join-Path $taskRoot 'qa-output/test-lin-profile'
$taskUrl = 'http://127.0.0.1:' + $Port
if (-not (Test-Path -LiteralPath $taskPython)) { throw '找不到项目 Python 环境。' }
if ($Port -lt 1024 -or $Port -gt 65535 -or $Port -in @(1396, 8765)) { throw '请选择独立端口，不能占用正式入口。' }

function Test-LinService {
    try {
        $taskSession = New-Object Microsoft.PowerShell.Commands.WebRequestSession
        $null = Invoke-RestMethod ($taskUrl + '/api/pair') -Method Post -WebSession $taskSession -TimeoutSec 2 -ContentType 'application/json' -Headers @{'X-Rehab-Client'='mobile-v1'} -Body '{"code":"test-code"}'
        $taskSnapshot = Invoke-RestMethod ($taskUrl + '/api/unified') -WebSession $taskSession -TimeoutSec 4
        return $taskSnapshot.snapshot.profile.profile.name -eq 'TEST 林女士' -and $taskSnapshot.snapshot.profile.dataMode -eq 'demo'
    } catch { return $false }
}
if (-not (Test-LinService)) {
    if (Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue) { throw '端口已有其他服务，未关闭任何程序。请指定另一个独立端口。' }
    New-Item -ItemType Directory -Path (Split-Path -Parent $taskData) -Force | Out-Null
    $taskProcess = Start-Process -FilePath $taskPython -ArgumentList @('"'+$taskScript+'"', '--complete', '--port', $Port) -WorkingDirectory $taskRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $taskRoot 'qa-output/test-lin.stdout.log') -RedirectStandardError (Join-Path $taskRoot 'qa-output/test-lin.stderr.log')
    $taskDeadline = (Get-Date).AddSeconds(50)
    do {
        if (Test-LinService) { break }
        if ($taskProcess.HasExited) { throw '启动失败，查看 qa-output/test-lin.stderr.log；已有档案未删除。' }
        Start-Sleep -Milliseconds 500
    } while ((Get-Date) -lt $taskDeadline)
    if (-not (Test-LinService)) { throw '服务仍在初始化，请稍后重试；未终止其他进程。' }
}
Write-Output $taskUrl
Write-Output '连接码：test-code'
if (-not $NoBrowser) { Start-Process $taskUrl }
