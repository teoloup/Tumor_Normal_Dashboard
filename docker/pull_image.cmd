@echo off
setlocal

cd /d "%~dp0"
set "TNVD_DOCKER_IMAGE=%TNVD_DOCKER_IMAGE%"
if "%TNVD_DOCKER_IMAGE%"=="" set "TNVD_DOCKER_IMAGE=teoloup/tumor-normal-variant-dashboard:latest"

echo Tumor Normal Variant Dashboard Docker image pull
echo.
echo Docker image: %TNVD_DOCKER_IMAGE%
echo.

docker --version >nul 2>&1
if errorlevel 1 (
  echo Docker Desktop was not found in PATH.
  echo Install and start Docker Desktop, then run this setup again.
  pause
  exit /b 1
)

echo Pulling Docker image...
docker pull %TNVD_DOCKER_IMAGE%
if errorlevel 1 (
  echo Docker image pull failed.
  pause
  exit /b 1
)

echo.
echo Docker image pull completed.
echo The root launcher will use image %TNVD_DOCKER_IMAGE%.
pause
