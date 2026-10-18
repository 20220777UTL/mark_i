@echo off
setlocal
cd /d "%~dp0"
set "PYTHONHOME="
set "PYTHONPATH="
"PythonScripts\.venv\Scripts\python.exe" PythonScripts/tools/prelim_scene.py
pause
