@echo off
setlocal

cd /d "%~dp0"

echo Tumor Normal Variant Dashboard setup

echo.
echo [1/5] Checking Python launcher...
where py >nul 2>&1
if errorlevel 1 (
  echo Python launcher 'py' was not found.
  echo Install Python 3 for Windows, then run this setup again.
  pause
  exit /b 1
)

echo.
echo [2/5] Creating virtual environment if needed...
if not exist ".venv\Scripts\python.exe" (
  py -3 -m venv .venv
  if errorlevel 1 (
    echo Failed to create the virtual environment.
    pause
    exit /b 1
  )
) else (
  echo Existing virtual environment found.
)

echo.
echo [3/5] Installing dashboard requirements...
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 (
  echo Failed while upgrading pip.
  pause
  exit /b 1
)

".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
  echo Failed while installing dashboard requirements.
  pause
  exit /b 1
)

echo.
echo [4/5] Preparing local runtime folder...
if not exist "local" mkdir "local"

echo.
echo [5/5] Ensuring local IGV.js is available...
if exist "local\igv.min.js" (
  echo Found local\igv.min.js
) else (
  echo Downloading igv.min.js...
  powershell -NoProfile -ExecutionPolicy Bypass -Command "try { Invoke-WebRequest -UseBasicParsing -Uri 'https://cdn.jsdelivr.net/npm/igv@3.5.4/dist/igv.min.js' -OutFile 'local\\igv.min.js' } catch { exit 1 }"
  if errorlevel 1 (
    echo Could not download igv.min.js automatically.
    echo You can still use the dashboard after placing igv.min.js manually in app\local\
  ) else (
    echo Downloaded local\igv.min.js
  )
)

echo.
echo Setup completed.
echo Next step: return to the repo root and double-click launch_dashboard.cmd
pause
