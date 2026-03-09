@echo off
setlocal

cd /d "%~dp0"

echo Tumor Normal Variant Dashboard Docker setup
echo.

docker --version >nul 2>&1
if errorlevel 1 (
  echo Docker Desktop was not found in PATH.
  echo Install and start Docker Desktop, then run this setup again.
  pause
  exit /b 1
)

if not exist "dashboard\local\docker_state" mkdir "dashboard\local\docker_state"
if not exist "data" mkdir "data"

echo Building Docker image...
docker build -t tumor-normal-variant-dashboard:latest .
if errorlevel 1 (
  echo Docker image build failed.
  pause
  exit /b 1
)

echo.
echo Docker setup completed.
echo Next step: double-click launch_dashboard_docker.cmd
pause
