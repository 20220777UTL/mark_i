@echo off
setlocal
cd /d "%~dp0"
set "SRC_CORNER_PASS_TEST="
set "SRC_GIVE_AND_GO_TEST=1"
for %%F in (Client.exe Medusa.exe MedusaCore.dll PythonScripts\Config.py PythonScripts\Play\Test\Test_GiveAndGo.py PythonScripts\Play\Test\Test_CornerPassShot.py PythonScripts\WorldModel\PowerCalculator.py PythonScripts\CppPackage\CppPackage.pyd data\power_curve\active_curve.json) do (
  if not exist "%%F" (
    echo ERROR: Missing %%F
    echo Use the complete repository and preserve your working Windows runtime.
    pause
    exit /b 1
  )
)
findstr /C:"SRC_GIVE_AND_GO_TEST" PythonScripts\Config.py >nul
if errorlevel 1 (
  echo ERROR: Config.py has no full-flow test entry. Update the test branch.
  pause
  exit /b 1
)
tasklist /FI "IMAGENAME eq Client.exe" /NH 2>nul | find /I "Client.exe" >nul
if not errorlevel 1 (
  echo ERROR: A Client is already running. Close it and its test Medusa before retrying.
  pause
  exit /b 1
)
echo Start Simulator, connect, then start BLUE Medusa in this Client.
echo Use default stationary ball and blue robots 1 and 2. Do not start another strategy.
echo This is a single trial. Restart BLUE Medusa to retry after resetting the scene.
Client.exe
if errorlevel 1 pause
endlocal
