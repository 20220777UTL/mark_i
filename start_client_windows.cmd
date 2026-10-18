@echo off
setlocal
cd /d "%~dp0"
set "PYTHONHOME="
if exist "%~dp0Python312\python.exe" set "PYTHONHOME=%~dp0Python312"
set "PYTHONPATH="
set "PYTHONIOENCODING=utf-8"
set "SRC_PRELIM="
set "SRC_SIMPLE_PASS="
set "SRC_KICK_CALIBRATION="
set "SRC_CORNER_PASS_TEST="
set "SRC_GIVE_AND_GO_TEST="
if not exist "PythonScripts\.venv\Scripts\python.exe" (
  echo Create PythonScripts .venv with Python 3.12.10 first. See README.md.
  pause
  exit /b 1
)
start "SRC Preliminary Client" /D "%~dp0" "%~dp0Client.exe"
endlocal
