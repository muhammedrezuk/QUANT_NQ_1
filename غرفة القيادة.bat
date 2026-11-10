@echo off
chcp 65001 >nul
REM ---------------------------------------------------------------------
REM  chcp MUST stay on line 2.  cmd parses each line in the console OEM
REM  codepage as it reaches it, so any Arabic ABOVE this line is read as
REM  garbage and cmd tries to run the fragments as commands.
REM  Measured 2026-09-01: an Arabic REM on line 2 produced
REM      "'..' is not recognized as an internal or external command"
REM  on every single press.  Same hazard documented in scripts\py.bat.
REM ---------------------------------------------------------------------
setlocal
set PYTHONUTF8=1
set QUANT_LOCAL_MODE=1

REM ---------------------------------------------------------------------
REM  Bridge anchor — measured 2026-09-07.  Without these two lines the
REM  forex atoms 611/618/619 fell back to the RELATIVE default var/bridge.db
REM  and runtime_paths anchored it on the WRONG runtime, producing
REM      C:\...\QUANT_NQ\crypto_runtime\var\bridge.db  (does not exist)
REM  35,485 times in errors-20260907.log alone -> 619 never published the
REM  account, so 581 logged "فكرة بلا مدخلات ... ميزانية=0.0" and no OPEN
REM  command was ever written.  Last trade: 09-06 16:57.
REM  Every other launcher (governance\launchers\*.bat) already sets this;
REM  this button was the only one that did not.
REM ---------------------------------------------------------------------
REM  ٢٠٢٦-٠٩-٢٣: مرسى الجسر انتقل إلى `governance/app.py` مع المراسي
REM  الستّة الأخرى — تعريفٌ واحد لا تعريفان. هذا الزرّ لا يُطلق غير
REM  `app.py`، والمشرف يضبطه بـsetdefault فيبقى تقدُّم يد المالك.
if not defined QUANT_CORE_DOMAIN set "QUANT_CORE_DOMAIN=forex"

cd /d "%~dp0"
REM ---------------------------------------------------------------------
REM  ٢٠٢٦-١٠-٢٦ (ختم المالك «nq») — علامة زرّ «إيقاف النظام». أداة الإيقاف
REM  scripts\stop_all.py تكتبها قبل أن توقف شيئًا، في مجلّد التحكّم من جذر التشغيل
REM  (المكان نفسه الذي يحسبه shared\runtime_paths.py). تُقرأ قبل إقلاع البرنامج
REM  وبعد خروجه: إن تغيّرت فالخروج من زرّ الإيقاف، فتُغلق النافذة بلا توقّف.
REM  وإن ثبتت أو غابت فالخروج خطأٌ أو بيد المالك: تتوقّف النافذة كما كانت.
REM ---------------------------------------------------------------------
set "NQ_STOP_MARK=%~dp0forex_runtime\var\control\stop_all.mark"
if defined QUANT_RUNTIME_ROOT set "NQ_STOP_MARK=%QUANT_RUNTIME_ROOT%\var\control\stop_all.mark"
REM  ٢٠٢٦-١٠-٢٦: النافذة الجانبيّة تدخل هذا الملفّ نفسه بالقسم :forex_wait آخره.
if "%~1"==":forex_wait" goto :forex_wait

REM  If the platform is already up, app.py refuses a second instance and
REM  exits 0.  Without the branch below the window closed instantly and
REM  the button looked dead (owner report 2026-09-01).
REM ---------------------------------------------------------------------
REM  ٢٠٢٦-٠٩-١٠ (ختم NQ) — كان الفحص على 8090 (منفذ الحوكمة)، وهو الخطأ:
REM  لوحة المالك ليست صفحة متصفّح بل **نافذة WebView2** يفتحها app.py،
REM  و app.py هو نفسه المشرف على 8099.  فمتى شُغّلت الخدمات بلا app.py
REM  (يدويًّا أو من جلسة أخرى) صار 8090 مفتوحًا و 8099 مغلقًا، فيقول هذا
REM  الزرّ «المنصّة تعمل أصلًا» ويفتح المتصفّح ثم يخرج — **بلا نافذة**.
REM  فيضغط المالك زرّه ولا ترجع لوحته.  مقيس ٢٠٢٦-٠٩-١٠ ٠٤:٢٠:
REM      8010 ✅  8090 ✅  8098 ✅  8099 ❌   ولا نافذة عند المالك.
REM  الصحيح: الفحص على وجود **النافذة** (8099).  وإن غابت يُشغَّل app.py،
REM  وهو يفحص كل منفذ ويعيد استخدام ما يعمل («شغّال أصلًا — إعادة
REM  استخدامه») فلا يوقف نواةً ولا يعيد تشغيل شيء.
REM ---------------------------------------------------------------------
REM ---------------------------------------------------------------------
REM  ٢٠٢٦-١٠-٢٦ (ختم المالك «nq»: «ضيفة مع زرة لوحة قيادة ياقلع») — أوّل ما يُضغط
REM  الزرّ: منفذ الفوركس 8092. أُقلعت المنظومة ٢٥/١٠ 22:30 من هذا الزرّ و8092 لا
REM  يسمع، لأنّ مشرف اللوحة لا يرفعه. فإن لم يسمع: نافذةٌ جانبيّة (القسم :forex_wait
REM  آخر الملفّ) تنتظر النواة ثمّ تشغّل الفوركس الموحّد. وإن سمع: يُترك كما هو.
REM  ثمّ يكمل الزرّ عمله كما كان: فحص 8099، ثمّ مشرف اللوحة.
REM ---------------------------------------------------------------------
netstat -ano | findstr /r /c:"TCP.*:8092 .*LISTENING" >nul
if errorlevel 1 (
  echo.
  echo   منفذ الفوركس 8092 لا يسمع — أشغّل الفوركس الموحّد في نافذةٍ جانبيّة بعد أن تسمع النواة.
  echo.
  start "الفوركس الموحّد — بعد النواة" cmd /c ""%~f0" :forex_wait"
) else (
  echo   منفذ الفوركس 8092 يسمع — يُترك كما هو.
)

netstat -ano | findstr /r /c:"TCP.*127.0.0.1:8099.*LISTENING" >nul
if not errorlevel 1 (
  echo.
  echo   اللوحة مفتوحة أصلًا — نافذتها شغّالة ولا تُفتح نسخة ثانية.
  echo   إن كانت النافذة مخفيّة فابحث عنها بشريط المهام.
  echo.
  ping -n 4 127.0.0.1 >nul
  endlocal & exit /b 0
)

netstat -ano | findstr /r /c:"TCP.*127.0.0.1:8090.*LISTENING" >nul
if not errorlevel 1 (
  echo.
  echo   الخدمات شغّالة والنافذة مفقودة — أُرجعها لك الآن.
  echo   لا يُعاد تشغيل شيء: النواة والحوكمة تُستخدمان كما هما.
  echo.
)

call :stop_mark_read NQ_STOP_BEFORE
call scripts\py.bat scripts\log_button.py "control_room" START >nul 2>&1
call scripts\py.bat governance\app.py
set CODE=%ERRORLEVEL%
call :stop_mark_changed
if not errorlevel 1 goto closed_by_stop
echo.
if "%CODE%"=="0" (
  echo   غرفة القيادة أُغلقت طبيعيًّا.
) else (
  echo   غرفة القيادة خرجت بالرمز %CODE%.
)
echo.
pause
endlocal & exit /b %CODE%

REM ---------------------------------------------------------------------
REM  ٢٠٢٦-١٠-٢٦ (ختم المالك «nq») — الخروج من زرّ «إيقاف النظام»: أداة الإيقاف
REM  قتلت المشرف (رمزه 15 عندها)، فلا رسالة خطأٍ تُقرأ. تُغلق النافذة وحدها،
REM  ويبقى رمز البرنامج رمزَ الخروج كما كان.
REM ---------------------------------------------------------------------
:closed_by_stop
endlocal & exit /b %CODE%

REM ---------------------------------------------------------------------
REM  ٢٠٢٦-١٠-٢٦ (ختم المالك «nq») — النافذة الجانبيّة. تنتظر النواة 8010 وخادم
REM  اللوحة 8090، وكلاهما يرفعه مشرف اللوحة، ثمّ تشغّل الفوركس الموحّد كما يشغّله
REM  زرّه: scripts\launch_market.py --market forex. والأداة لا تشغّل شيئًا على منفذٍ
REM  يسمع، فلا يبقى لها إلّا 8092 (وتلغرام إن غاب). لا توقف شيئًا ولا تعيد تشغيل شيء.
REM  وتنتظر الخادم أيضًا لأنّ الأداة ترفع على 8010 و8090 برنامجين غير برنامجَي المشرف:
REM  لو سبقتْه لأقلعتهما هي. وحدّ الانتظار عشر دقائق.
REM ---------------------------------------------------------------------
:forex_wait
call :stop_mark_read NQ_STOP_BEFORE
echo.
echo   الفوركس الموحّد: أنتظر النواة 8010 وخادم اللوحة 8090 ...
set /a FX_TRIES=0
:forex_wait_loop
call :stop_mark_changed
if not errorlevel 1 goto forex_closed_by_stop
netstat -ano | findstr /r /c:"TCP.*:8010 .*LISTENING" >nul
if errorlevel 1 goto forex_not_yet
netstat -ano | findstr /r /c:"TCP.*:8090 .*LISTENING" >nul
if errorlevel 1 goto forex_not_yet
goto forex_go
:forex_not_yet
set /a FX_TRIES+=1
if %FX_TRIES% geq 300 goto forex_timeout
ping -n 3 127.0.0.1 >nul
goto forex_wait_loop
:forex_go
echo   النواة والخادم يسمعان — أشغّل الفوركس الموحّد الآن.
call scripts\py.bat scripts\log_button.py "control_room_forex" START >nul 2>&1
call scripts\py.bat scripts\launch_market.py --market forex
set FX_CODE=%ERRORLEVEL%
call :stop_mark_changed
if not errorlevel 1 goto forex_closed_by_stop
echo.
echo   انتهى الفوركس الموحّد — سطر المنفذ 8092 فوق يقول إن كان جاهزًا.
echo   لا تُغلق هذه النافذة: حوكمة الفوركس 8092 تعمل منها، كما في زرّها.
echo.
if not "%FX_CODE%"=="0" goto forex_pause
REM ---------------------------------------------------------------------
REM  ٢٠٢٦-١٠-٢٦ (ختم المالك «nq») — كانت هنا «اضغط أيّ مفتاح» بعد النجاح أيضًا،
REM  فبقيت النافذة واقفةً بعد زرّ «إيقاف النظام»: أداة الفوركس خرجت منذ ساعات،
REM  وحوكمة 8092 تعمل في هذه النافذة. الآن تنتظر النافذة بخفّة: علامة الإيقاف كلّ
REM  خمس ثوانٍ، والمنفذ 8092 كلّ نصف دقيقة. إن تغيّرت العلامة خرجت بلا توقّف،
REM  فتُغلق النافذة حين توقف الأداة 8092. وإن سقط 8092 بلا علامة: رسالةٌ ثمّ
REM  «اضغط أيّ مفتاح» كي يقرأ المالك ما فوقها.
REM ---------------------------------------------------------------------
echo   تُغلق هذه النافذة وحدها حين تضغط «إيقاف النظام».
echo.
set /a FX_HOLD=0
:forex_hold_loop
ping -n 6 127.0.0.1 >nul
call :stop_mark_changed
if not errorlevel 1 goto forex_closed_by_stop
set /a FX_HOLD+=1
if %FX_HOLD% lss 6 goto forex_hold_loop
set /a FX_HOLD=0
netstat -ano | findstr /r /c:"TCP.*:8092 .*LISTENING" >nul
if not errorlevel 1 goto forex_hold_loop
call :stop_mark_changed
if not errorlevel 1 goto forex_closed_by_stop
echo.
echo   حوكمة الفوركس 8092 توقّفت ولم يُضغط «إيقاف النظام» — اقرأ ما فوق.
echo.
set FX_CODE=1
:forex_pause
pause
endlocal & exit /b %FX_CODE%
:forex_closed_by_stop
endlocal & exit /b 0
:forex_timeout
echo.
echo   مرّت عشر دقائق ولم تسمع النواة 8010 أو خادم اللوحة 8090 — لم أشغّل الفوركس.
echo   شغّل زرّ «تشغيل الفوركس الموحّد» بيدك بعد أن تعمل غرفة القيادة.
echo.
pause
endlocal & exit /b 1

REM ---------------------------------------------------------------------
REM  ٢٠٢٦-١٠-٢٦ (ختم المالك «nq») — قراءة علامة الإيقاف.
REM  :stop_mark_read اسم   يضع في المتغيّر أوّل سطرٍ من العلامة، أو يتركه فارغًا
REM                        إن غابت. سطرٌ من رقمين (وقتٌ ورقم عمليّة) فلا تنصيص.
REM  :stop_mark_changed    رمز 0 إن تغيّرت العلامة عمّا قُرئ في NQ_STOP_BEFORE،
REM                        و1 إن ثبتت أو غابت.
REM ---------------------------------------------------------------------
:stop_mark_read
set "%~1="
if exist "%NQ_STOP_MARK%" set /p "%~1=" <"%NQ_STOP_MARK%"
exit /b 0
:stop_mark_changed
call :stop_mark_read NQ_STOP_NOW
if not defined NQ_STOP_NOW exit /b 1
if "%NQ_STOP_NOW%"=="%NQ_STOP_BEFORE%" exit /b 1
exit /b 0
