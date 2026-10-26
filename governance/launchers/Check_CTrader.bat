@echo off
rem ٢٠٢٦-٠٩-١٦: كان يجرّب "venv\Scripts\python.exe" ثم يسقط إلى "py -3".
rem و"venv" غير موجودة (المفسّر الحيّ في vendor\python\runtime)، و"py -3" قد
rem لا يكون منصَّبًا — فيغلق الزرّ بلا رسالة. الترتيب الآن يبدأ بالمفسّر الفعليّ.
cd /d "%~dp0\..\.."
set PYTHONUTF8=1
if exist "vendor\python\runtime\python.exe" (
  "vendor\python\runtime\python.exe" governance\scripts\check_ctrader.py
) else if exist "venv\Scripts\python.exe" (
  "venv\Scripts\python.exe" governance\scripts\check_ctrader.py
) else (
  py -3 governance\scripts\check_ctrader.py
)
pause
