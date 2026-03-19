@echo off
setlocal

cd /d "%~dp0"
set "TNVD_LAUNCH_MODE=docker"

if exist "Tumor_Normal_Variant_Dashboard_Launcher.exe" (
  "Tumor_Normal_Variant_Dashboard_Launcher.exe"
  goto :done
)

if exist "app\.venv\Scripts\python.exe" (
  "app\.venv\Scripts\python.exe" "app\launcher.py"
) else (
  py -3 "app\launcher.py"
)

if errorlevel 1 (
  echo.
  echo Failed to start the Docker-mode dashboard launcher.
  echo If needed, build the launcher EXE or use the Python launcher from app\launcher.py.
  pause
)

:done
