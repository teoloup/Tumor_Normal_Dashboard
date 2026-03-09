@echo off
setlocal

cd /d "%~dp0"
set "TNVD_LAUNCH_MODE=docker"

if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" "dashboard\launcher.py"
) else (
  py -3 "dashboard\launcher.py"
)

if errorlevel 1 (
  echo.
  echo Failed to start the Docker-mode dashboard launcher.
  echo If needed, run setup_dashboard.cmd or setup_docker_dashboard.cmd first.
  pause
)
