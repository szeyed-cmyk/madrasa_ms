@echo off
rem The login page shows Demo sign-in accounts by default. For a real school set DEMO_LOGINS=false.
rem For a sample school that resets on every start, double-click start-demo.bat instead.
rem Madrasa & School Admin System - Windows starter (Command Prompt).
rem Double-click this file, or run from the "Madrasa Admin Project" folder:  start.bat
rem On the first start: creates the "venv" folder with py and installs the pinned packages.
rem See HowToSetup.md, section 2.
setlocal
cd /d "%~dp0"

if not exist "venv\Scripts\python.exe" (
  where py >nul 2>&1
  if errorlevel 1 (
    echo The Python launcher "py" was not found.
    echo Install Python 3.11 or newer from https://www.python.org/downloads/ and run this file again.
    pause
    exit /b 1
  )
  echo Creating the virtual environment with py ...
  py -3 -m venv venv
  if errorlevel 1 (
    echo Could not create the virtual environment. See HowToSetup.md, Troubleshooting.
    pause
    exit /b 1
  )
)

"venv\Scripts\python.exe" -c "import uvicorn, fastapi, sqlalchemy" >nul 2>&1
if errorlevel 1 (
  echo Installing the pinned packages from requirements.lock ...
  "venv\Scripts\python.exe" -m pip install --disable-pip-version-check --require-hashes -r requirements.lock
  if errorlevel 1 (
    echo Package installation failed. Check your internet connection and try again.
    pause
    exit /b 1
  )
)

"venv\Scripts\python.exe" main.py
pause
