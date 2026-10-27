@echo off
title Smart Traffic AI - Server
cd /d "%~dp0"

echo =================================================================
echo   SMART TRAFFIC DENSITY PREDICTION USING IOT ^& DNN
echo   B.E. Final Year Computer Science Thesis Project
echo =================================================================
echo.

if exist ".python\python.exe" (
    set "PYTHON_EXE=.python\python.exe"
) else (
    set "PYTHON_EXE=python"
)

echo Starting Flask Server with %PYTHON_EXE%...
"%PYTHON_EXE%" run.py
pause
