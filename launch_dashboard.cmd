@echo off
setlocal

cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" "dashboard\launcher.py"
) else (
  py -3 "dashboard\launcher.py"
)

if errorlevel 1 (
  echo.
  echo Failed to start the dashboard launcher.
  echo If needed, create and populate the local virtual environment first.
  pause
)
