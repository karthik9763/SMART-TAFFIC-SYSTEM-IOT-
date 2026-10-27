# PowerShell launcher for Smart Traffic AI
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

Write-Host "=================================================================" -ForegroundColor Cyan
Write-Host "  SMART TRAFFIC DENSITY PREDICTION USING IOT & DNN" -ForegroundColor Cyan
Write-Host "  B.E. Final Year Computer Science Thesis Project" -ForegroundColor Cyan
Write-Host "=================================================================" -ForegroundColor Cyan
Write-Host ""

$PythonExe = if (Test-Path ".\.python\python.exe") { ".\.python\python.exe" } else { "python" }

Write-Host "Starting Flask Server using $PythonExe..." -ForegroundColor Green
& $PythonExe run.py
