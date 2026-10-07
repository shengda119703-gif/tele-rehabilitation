@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\ui-polish\Start-TestLin.ps1"
if errorlevel 1 pause
