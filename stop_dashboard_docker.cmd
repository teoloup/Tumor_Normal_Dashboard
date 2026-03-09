@echo off
setlocal

set "CONTAINER_NAME=tumor_normal_variant_dashboard"

docker rm -f %CONTAINER_NAME% >nul 2>&1
if errorlevel 1 (
  echo No running container named %CONTAINER_NAME% was found.
) else (
  echo Stopped and removed %CONTAINER_NAME%.
)

pause
