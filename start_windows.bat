@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  py -m venv .venv
  if errorlevel 1 goto fail
)
.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
if errorlevel 1 goto fail
.venv\Scripts\python.exe setup_local.py
if errorlevel 1 goto fail
.venv\Scripts\python.exe run.py
pause
exit /b
:fail
echo Setup failed. See README.md for the manual PyCharm commands.
pause
exit /b 1
