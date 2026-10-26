@echo off
rem ÑÍáÉ ÇáÈØÇŞÉ — ßíİ ÊõÈäì æãÊì ÊãÑø Úáì 555 Ëãø ÇáÌÓÑ Ëãø ÇáãÎÇÒä
cd /d "%~dp0\..\.."
set PYTHONUTF8=1
if exist "vendor\python\runtime\python.exe" (
  "vendor\python\runtime\python.exe" governance\scripts\card_journey.py
) else if exist "venv\Scripts\python.exe" (
  "venv\Scripts\python.exe" governance\scripts\card_journey.py
) else (
  py -3 governance\scripts\card_journey.py
)
pause
