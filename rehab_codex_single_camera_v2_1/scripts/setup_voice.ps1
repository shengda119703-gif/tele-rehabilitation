param([string]$PythonPath='', [string]$IndexUrl='https://pypi.org/simple')
$ErrorActionPreference='Stop'
$taskVoiceRoot=Split-Path $PSScriptRoot -Parent
$taskVoicePython=if ($PythonPath) {$PythonPath} else {Join-Path $taskVoiceRoot '.venv/Scripts/python.exe'}
& $taskVoicePython -m pip install -r (Join-Path $taskVoiceRoot 'requirements.voice.txt') --index-url $IndexUrl
if ($LASTEXITCODE -ne 0) {throw 'Voice dependencies failed to install.'}
& $taskVoicePython (Join-Path $PSScriptRoot 'prepare_voice.py')
if ($LASTEXITCODE -ne 0) {throw 'Voice model verification failed.'}
