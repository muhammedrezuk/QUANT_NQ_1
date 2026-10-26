@echo off
chcp 65001 >nul
REM ---------------------------------------------------------------------
REM  chcp MUST stay on line 2 (see the control room button).
REM  2026-10-22 (owner seal NQ): the backtest page alone -- the governance
REM  server (8090) and a window on the backtest tab. No core, no trading,
REM  no telegram, no news bot. Works while the system is stopped; the
REM  control room button afterwards still boots the core in full.
REM ---------------------------------------------------------------------
setlocal
set PYTHONUTF8=1
set QUANT_LOCAL_MODE=1
if not defined QUANT_CORE_DOMAIN set "QUANT_CORE_DOMAIN=forex"

cd /d "%~dp0"

echo.
echo   صفحة الباك تست وحدها — بلا نواة ولا تداول.
echo   القياس يُطلق من زرّها ويعمل على الجهاز ولو أُغلقت النافذة.
echo.

call scripts\py.bat scripts\log_button.py "backtest_only" START >nul 2>&1
call scripts\py.bat governance\app.py --backtest-only
set CODE=%ERRORLEVEL%
echo.
pause
endlocal & exit /b %CODE%
