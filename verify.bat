@echo off
title Smart Traffic AI - Production Verification
cd /d "%~dp0"

if exist ".python\python.exe" (
    set "PYTHON_EXE=.python\python.exe"
) else (
    set "PYTHON_EXE=python"
)

echo Running production verification suite...
"%PYTHON_EXE%" scripts\verify_system_production.py
pause
