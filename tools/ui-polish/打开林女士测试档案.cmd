@echo off
rem Developer-only synthetic TEST profile. Not a patient or doctor workbench entry.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Start-TestLin.ps1"
if errorlevel 1 pause
