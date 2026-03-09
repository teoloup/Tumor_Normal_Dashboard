@echo off
setlocal

cd /d "%~dp0"

echo Building Tumor Normal Variant Dashboard launcher executable
echo.

where py >nul 2>&1
if errorlevel 1 (
  echo Python launcher 'py' was not found.
  echo Install Python 3 for Windows, then run this build again.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo Creating local virtual environment...
  py -3 -m venv .venv
  if errorlevel 1 (
    echo Failed to create the virtual environment.
    pause
    exit /b 1
  )
)

echo Installing PyInstaller...
".venv\Scripts\python.exe" -m pip install --upgrade pip pyinstaller
if errorlevel 1 (
  echo Failed to install PyInstaller.
  pause
  exit /b 1
)

echo Cleaning previous build output...
if exist "build" rmdir /s /q "build"
if exist "dist" rmdir /s /q "dist"

echo Running PyInstaller...
".venv\Scripts\pyinstaller.exe" --clean dashboard\launcher.spec
if errorlevel 1 (
  echo PyInstaller build failed.
  pause
  exit /b 1
)

echo.
echo Build completed.
echo Launcher folder:
echo   %cd%\dist\Tumor_Normal_Variant_Dashboard_Launcher
echo.
echo Executable:
echo   %cd%\dist\Tumor_Normal_Variant_Dashboard_Launcher\Tumor_Normal_Variant_Dashboard_Launcher.exe
pause
