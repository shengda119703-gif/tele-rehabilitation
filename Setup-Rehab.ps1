param(
    [switch]$IncludeLandmarks,
    [switch]$IncludeVoice,
    [string]$IndexUrl = 'https://pypi.org/simple'
)
$ErrorActionPreference = 'Stop'
$taskAppRoot = Join-Path $PSScriptRoot 'rehab_codex_single_camera_v2_1'
& (Join-Path $taskAppRoot 'scripts\setup.ps1') -IndexUrl $IndexUrl -PrepareModel
if ($IncludeLandmarks) {
    & (Join-Path $taskAppRoot 'scripts\setup_landmarks.ps1') -IndexUrl $IndexUrl
}
if ($IncludeVoice) {
    & (Join-Path $taskAppRoot 'scripts/setup_voice.ps1') -IndexUrl $IndexUrl
}
$taskAgentRoot = Join-Path $PSScriptRoot 'ankang\route1-health-agent'
if (-not (Get-Command node -ErrorAction SilentlyContinue)) { throw 'Node.js 22+ is required for the Ankang product services.' }
Push-Location -LiteralPath $taskAgentRoot
try {
    if (-not (Test-Path -LiteralPath 'node_modules\typescript\bin\tsc')) {
        & npm.cmd ci --no-audit --no-fund
        if ($LASTEXITCODE -ne 0) { throw 'Ankang dependency installation failed.' }
    }
    & node scripts/build-agent-bridge.cjs
    if ($LASTEXITCODE -ne 0) { throw 'Ankang product bridge build failed.' }
} finally {
    Pop-Location
}
Write-Output 'Setup completed. Use the workspace launcher to open Home Rehab.'
