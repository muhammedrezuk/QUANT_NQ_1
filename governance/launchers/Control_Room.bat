@echo off
cd /d "%~dp0\..\.."
set PYTHONUTF8=1
REM 2026-10-02 owner seal - full fix nq: local mode, same as the main launcher
REM in the project root. The core API then binds 127.0.0.1 only, never 0.0.0.0.
set QUANT_LOCAL_MODE=1
if not defined NQ_BRIDGE_DB set "NQ_BRIDGE_DB=%APPDATA%\MetaQuotes\Terminal\Common\Files\nq_brain.db"
if not exist "venv\Scripts\python.exe" (
  py -3 -m venv venv
  if errorlevel 1 exit /b 1
)
"venv\Scripts\python.exe" -c "import pytest,pytest_asyncio" >nul 2>&1
if errorlevel 1 (
  "venv\Scripts\python.exe" -m pip install -r governance\setup\requirements.txt
  if errorlevel 1 exit /b 1
)
rem %* يمرّر الوسائط: «غرفة القيادة.bat --stop» يوقف النواة صراحةً
"venv\Scripts\python.exe" governance\app.py %*
pause
