@echo off
setlocal
cd /d "%~dp0"
set "SRC_CORNER_PASS_TEST="
set "SRC_GIVE_AND_GO_TEST=1"
if not exist Client.exe (
  echo Client.exe not found. Put this file in the repository root.
  pause
  exit /b 1
)
echo Start Simulator, connect, then start BLUE Medusa in this Client.
echo Use default stationary ball and blue robots 1 and 2. Do not start another strategy.
echo This is a single trial. Restart BLUE Medusa to retry after resetting the scene.
Client.exe
if errorlevel 1 pause
endlocal
