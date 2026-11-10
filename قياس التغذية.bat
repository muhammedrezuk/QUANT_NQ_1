@echo off
chcp 65001 >nul
REM -------------------------------------------------------------------
REM  chcp MUST stay on line 2.  cmd reads each line in the console OEM
REM  codepage as it reaches it, so any Arabic ABOVE this line is parsed
REM  as garbage and cmd tries to run the fragments as commands.
REM  Same hazard documented in scripts\py.bat and the command-room bat.
REM -------------------------------------------------------------------
setlocal
set PYTHONUTF8=1
cd /d "%~dp0"

REM  The bundled runtime, never the system python: the system one throws
REM  OSError [Errno 22] on the Arabic paths in this tree.
"%~dp0vendor\python\runtime\python.exe" "%~dp0tools\قياس_التغذية.py"

echo.
pause
