param(
    [string]$PythonPath = '',
    [int]$Width = 1440,
    [int]$Height = 940,
    [ValidateSet('light','dark','high-contrast')][string]$Theme = 'light',
    [ValidateSet('windows','offscreen')][string]$Platform = 'windows',
    [string]$OutputRoot = 'qa-output/ui-env/qt'
)
$ErrorActionPreference = 'Stop'
$taskRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '../..')).Path
$taskPython = if ($PythonPath) { $PythonPath } else { Join-Path $taskRoot '.venv-ui-polish/Scripts/python.exe' }
if (-not (Test-Path -LiteralPath $taskPython)) { throw 'Missing QA environment. See tools/ui-polish/README.md; pass -PythonPath to reuse an existing environment.' }
$taskOldPlatform = $env:QT_QPA_PLATFORM
$taskOldScale = $env:QT_SCALE_FACTOR
Push-Location -LiteralPath $taskRoot
try {
    $env:QT_QPA_PLATFORM = $Platform
    $env:QT_SCALE_FACTOR = '1'
    $taskTool = Join-Path $taskRoot 'rehab_codex_single_camera_v2_1/tools/validate_product_visual.py'
    & $taskPython $taskTool --width $Width --height $Height --theme $Theme --phase ux-audit --output-root $OutputRoot
    if ($LASTEXITCODE -ne 0) { throw "Qt capture failed ($LASTEXITCODE); preserve failure logs and screenshots." }
} finally {
    $env:QT_QPA_PLATFORM = $taskOldPlatform
    $env:QT_SCALE_FACTOR = $taskOldScale
    Pop-Location
}
