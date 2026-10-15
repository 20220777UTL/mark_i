@echo off
setlocal
cd /d "%~dp0"
set "SRC_CORNER_PASS_TEST="
set "SRC_GIVE_AND_GO_TEST=1"
for %%F in (Client.exe Medusa.exe MedusaCore.dll PythonScripts\Config.py PythonScripts\Play\Test\Test_GiveAndGo.py PythonScripts\Play\Test\Test_Goalie2022.py PythonScripts\Play\Test\Test_CornerPassShot.py PythonScripts\WorldModel\PowerCalculator.py PythonScripts\WorldModel\Flags.py PythonScripts\RoleMatch_LuaStyle\Skills\Skill.py PythonScripts\CppPackage\CppPackage.pyd data\power_curve\active_curve.json) do (
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
findstr /C:"def SmartGoTo(" PythonScripts\RoleMatch_LuaStyle\Skills\Skill.py >nul
if errorlevel 1 (
  echo ERROR: SmartGoTo wrapper is missing. Update the complete test branch.
  pause
  exit /b 1
)
tasklist /FI "IMAGENAME eq Client.exe" /NH 2>nul | find /I "Client.exe" >nul
if not errorlevel 1 (
  echo ERROR: A Client is already running. Close it and its test Medusa before retrying.
  pause
  exit /b 1
)
echo Start Simulator and connect. Use the default stationary ball.
echo BLUE: robots 1 and 2 attack right. YELLOW: goalie 0 defends right.
echo Set opposing team sides and a running referee state: FORCE_START.
echo Start YELLOW Medusa first; wait for its YELLOW Test_Goalie2022 startup log.
echo Then start BLUE Medusa; its log must say BLUE Test_GiveAndGo.
echo This is a single trial. Stop both strategies and reset the scene before retrying.
echo Native Windows execution has not been verified on this computer.
Client.exe
if errorlevel 1 pause
endlocal
