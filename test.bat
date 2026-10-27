@echo off
title Smart Traffic AI - Test Suite
cd /d "%~dp0"

if exist ".python\python.exe" (
    set "PYTHON_EXE=.python\python.exe"
) else (
    set "PYTHON_EXE=python"
)

echo Running unit test suite...
"%PYTHON_EXE%" -m unittest discover tests
pause
