@echo off
setlocal

cd /d "%~dp0"

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
  echo Failed to start the dashboard launcher.
  echo If needed, run app\setup_native.cmd first or build the launcher EXE.
  pause
)

:done
