@echo off
rem ط¨ط·ط§ظ‚ط§طھ ط§ظ„طµظپظ‚ط§طھ â€” طھظ‚ط±ط£ ط§ظ„ط³ط¬ظ„ظ‘ ظˆطھظپطھط­ طµظپط­ط© ط¨ط£ظٹظ‘ ظ…طھطµظپظ‘ط­
cd /d "%~dp0\..\.."
set PYTHONUTF8=1
if exist "vendor\python\runtime\python.exe" (
  "vendor\python\runtime\python.exe" governance\scripts\cards_report.py
) else if exist "venv\Scripts\python.exe" (
  "venv\Scripts\python.exe" governance\scripts\cards_report.py
) else (
  py -3 governance\scripts\cards_report.py
)
pause