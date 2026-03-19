@echo off
setlocal

cd /d "%~dp0"
set "TNVD_DOCKER_IMAGE=%TNVD_DOCKER_IMAGE%"
if "%TNVD_DOCKER_IMAGE%"=="" set "TNVD_DOCKER_IMAGE=teoloup/tumor-normal-variant-dashboard:latest"

echo Building Docker image %TNVD_DOCKER_IMAGE%
echo.

docker --version >nul 2>&1
if errorlevel 1 (
  echo Docker Desktop was not found in PATH.
  echo Install and start Docker Desktop, then run this build again.
  pause
  exit /b 1
)

docker build -f Dockerfile -t %TNVD_DOCKER_IMAGE% ..
if errorlevel 1 (
  echo Docker image build failed.
  pause
  exit /b 1
)

echo.
echo Docker image build completed.
pause
