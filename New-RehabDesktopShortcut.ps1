param([string]$PythonPath = '')
$ErrorActionPreference = 'Stop'
$taskLauncher = Join-Path $PSScriptRoot 'Start-Rehab.ps1'
$taskPython = if ($PythonPath) { (Resolve-Path -LiteralPath $PythonPath).Path } else { Join-Path $PSScriptRoot 'rehab_codex_single_camera_v2_1\.venv\Scripts\pythonw.exe' }
if (-not (Test-Path -LiteralPath $taskPython)) { throw 'Python environment not found. Supply -PythonPath with the verified project pythonw.exe.' }
$taskDesktop = [Environment]::GetFolderPath('Desktop')
$taskShortcutPath = Join-Path $taskDesktop '安康康复（最新版本）.lnk'
$taskShell = New-Object -ComObject WScript.Shell
$taskShortcut = $taskShell.CreateShortcut($taskShortcutPath)
$taskShortcut.TargetPath = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
$taskShortcut.Arguments = '-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "' + $taskLauncher + '" -PythonPath "' + $taskPython + '"'
$taskShortcut.WorkingDirectory = $PSScriptRoot
$taskVersion = & git -C $PSScriptRoot rev-parse --short HEAD
$taskShortcut.Description = '安康居家康复助手 · 当前工作区 · ' + $taskVersion
$taskShortcut.IconLocation = $taskPython + ',0'
$taskShortcut.WindowStyle = 7
$taskShortcut.Save()
$taskVerified = $taskShell.CreateShortcut($taskShortcutPath)
if ($taskVerified.Arguments -ne $taskShortcut.Arguments -or $taskVerified.WorkingDirectory -ne $PSScriptRoot) { throw 'Shortcut verification failed.' }
Write-Output $taskShortcutPath
Write-Output ('Version: ' + $taskVersion)
