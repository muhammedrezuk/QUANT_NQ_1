# -*- coding: utf-8 -*-
"""
غرفة القيادة — تطبيق سطح المكتب القديم (ليس عقد الإطلاق الرسمي).

العقد الرسمي هو زرا الفوركس والكريبتو المستقلان. هذه الأداة باقية للتشخيص
والتوافق فقط. دبل-كليك واحد → يشغّل النواة (:8010) + خادم الحوكمة (:8090) إن ما كانوا شغّالين،
ثم يفتح اللوحة بنافذة تطبيق أصلية (WebView2). عند إغلاق النافذة يوقف ما شغّله هو فقط.

القاعدة (شفافية): سجلّ النواة والخادم يظهر بنافذة هذا المشغّل — لا شيء مخفي.
"""
import ctypes
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent          # جذر المشروع
# نفرض مفسّر المشروع لتشغيل النواة/الخادم — فيه المكتبات. بايثون النظام يُسقِط النواة.
# ٢٠٢٦-٠٩-٠١: كان يعرف `venv/` وحدها. والنسخة المتنقّلة على جهاز جديد لا تبني
# `venv` أصلًا — تبني `vendor/python/runtime/` (مفسّر المشروع المضمّن). فكان
# المشغّل يسقط إلى `sys.executable`، وهو صحيح حين يأتي عبر `scripts\py.bat`
# وخاطئ تمامًا إن شُغّل بأي طريق آخر: بايثون نظامٍ عارٍ ⇒ لا نواة ولا لوحة.
# الترتيب صريح الآن: مفسّرنا المضمّن، ثم venv، ثم الحالي.
_RUNTIME_PY = ROOT / "vendor" / "python" / "runtime" / "python.exe"
_VENV_PY = ROOT / "venv" / "Scripts" / "python.exe"
PYEXE = (str(_RUNTIME_PY) if _RUNTIME_PY.exists()
         else str(_VENV_PY) if _VENV_PY.exists() else sys.executable)
CORE = ROOT / "governance" / "scripts" / "run_core.py"
SERVER = ROOT / "governance" / "server.py"

# ٢٠٢٦-٠٩-٠٣ (بند ٨): غرفة القيادة تُقِلع من جذر المشروع، فبدون هذه المتغيّرات
# كان النواة واللوحة يتشعبان: اللوحة تقرأ `<runtime>/var` والمحرّك يكتب
# `PROJECT_ROOT/var/forex` — قِيس وانفصل المتحوّلان. تُضبط هنا بالـsetdefault
# (يد المالك تتقدّم)، وتُورَّث لكل عمليّة تُقلع أدناه عبر `dict(os.environ)`.
_FOREX_RUNTIME = ROOT / "forex_runtime"
if _FOREX_RUNTIME.is_dir():
    os.environ.setdefault("QUANT_RUNTIME_ROOT", str(_FOREX_RUNTIME))
    os.environ.setdefault("QUANT_CORE_STATE_ROOT", str(_FOREX_RUNTIME / "var"))
    # ٢٠٢٦-٠٩-٠٦ (مقيس — تدقيق طرف ثالث قال «نسخة ميتة لا تُحمَّل»، والقياس
    # يقول العكس): `scripts/run_forex.py` حُدِّث إلى جذر واحد للذرّات بحكم
    # المالك «لازم يكون في نسخة وحدة بس»، وهذا الملفّ — وهو ما يناديه
    # `غرفة القيادة.bat` — بقي يشير إلى نسخة الرَنتايم. فالمُطلِقان يحمّلان
    # شجرتين مختلفتين، والفارق مقيس على أربع ذرّات مخاطر وتنفيذ:
    #   506: بلا سحب الخرق ولا إعادة الوزن  (المزلاج يبقى أبديًّا)
    #   513: بلا `risk_base_equity`          (السقف يتبع الرصيد لا 10,000)
    #   516: بلا `auto_rearm` ولا تصفير العدّاد (زرّ المالك معطّل)
    #   551: بلا مدى 80–95 ولا بدل الانزلاق ولا حارس المئة
    # أي أن الإقلاع من غرفة القيادة كان يُلغي إصلاحات اليوم كلّها بصمت.
    # المصدر واحد الآن في المُطلِقَين معًا.
    os.environ.setdefault("QUANT_ATOMS_ROOT", str(ROOT / "atoms"))
    os.environ.setdefault("QUANT_CORE_CONFIG", str(ROOT / "config" / "core_forex.yaml"))
    os.environ.setdefault("QUANT_CORE_DOMAIN", "forex")
    os.environ.setdefault("QUANT_ANALYSIS_SETTINGS_DB",
                          str(_FOREX_RUNTIME / "var" / "store" / "analysis_settings.db"))

# ٢٠٢٦-٠٩-٢٣ — المرسى السابع كان معلّقًا على الزرّ وحده. إصلاح ٢٠٢٦-٠٩-٠٧
# («٣٥٬٤٨٥ خطأ مسار») وُضع في `غرفة القيادة.bat` حيث ظهر العطل، لا في
# المشرف حيث تسكن المراسي الستّة — فصار كلُّ إطلاقٍ لا يمرّ بالزرّ يفقده.
#
# ⚠️ والارتداد اليوم **ليس مكسورًا** — مقيس ٢٠٢٦-٠٩-٢٣: مانيفستات ٥٧٥
# و٦٠٩ و٦١١ تحمل المسار **المطلق مكتوبًا بيد** إلى ملفّ هذا الجهاز
# تحت `AppData/Roaming/MetaQuotes`. فالعطل ليس مسارًا ضائعًا بل مسارَ
# **جهازٍ بعينه محفورًا في عقد أربع ذرّات**: نقلُ المشروع إلى مستخدمٍ
# آخر يُسقطها. وهذا المتغيّر هو المخرج — يُضبط هنا مرّةً، فتستطيع
# المانيفستات أن تحمل قيمةً محايدة بدل اسم صاحب الجهاز.
#
# وهو خارج كتلة `_FOREX_RUNTIME` عمدًا: جسر ميتاتريدر يسكن مجلّد
# `Common\Files` المشترك، لا شجرة الرَنتايم — فلا يتعلّق بوجودها.
# و`setdefault` تُبقي يدَ المالك مقدَّمة: قيمةٌ من البيئة أو من الزرّ تفوز.
_MT5_COMMON = os.environ.get("APPDATA")
if _MT5_COMMON:
    os.environ.setdefault(
        "NQ_BRIDGE_DB",
        str(Path(_MT5_COMMON) / "MetaQuotes" / "Terminal" / "Common" / "Files"
            / "nq_brain.db"))
TELEGRAM = ROOT / "governance" / "telegram.py"          # ٦١٠ — المنصّة المتنقّلة
# ٢٠٢٦-٠٩-٠٣ (المالك): كانت تقرأ `PROJECT_ROOT/var/...` بينما خادم الحوكمة
# يقرأ `<runtime>/var/governance/telegram.json` — ضبطُ المنصّة من اللوحة كان
# لا يصل هذا المشغّل أبدًا.
try:
    sys.path.insert(0, str(ROOT / "governance"))
    from runtime_paths import telegram_conf_path as _tg_conf
    TELEGRAM_CONF = _tg_conf()
except Exception:  # noqa: BLE001
    TELEGRAM_CONF = ROOT / "var" / "governance" / "telegram.json"
CORE_PORT, GOV_PORT, TG_PORT = 8010, 8090, 8098
GOV2_PORT = 8092    # خادم الحوكمة الثاني، يُقلعه مُطلِق السوق من «غرفة القيادة» — يُوقف هنا ولا يُقلع

# ٢٠٢٦-٠٩-٠٩ (أمر المالك «امسح»): أُزيل إقلاع السوق الثاني — نواته (:8020)
# ولوحته (:8091) وشجرته `crypto_runtime` و`scripts/run_governance.py` الذي
# لم يكن يُستدعى إلا لأجلها. سوق واحد: الفوركس.
# ⚠️ ٢٠٢٦-١٠-٢٦ (فحص المشروع): `scripts/run_governance.py` لم يُزَل — يُقلعه `scripts/launch_market.py` على 8092 من نافذة
# «غرفة القيادة»، خادمَ حوكمةٍ ثانيًا بالشيفرة نفسها. فصار `--stop` أدناه يوقفه (`GOV2_PORT`) ولا يُقلعه.
URL = f"http://127.0.0.1:{GOV_PORT}"

_started: list[subprocess.Popen] = []                  # ما شغّلناه نحن فقط (لإيقافه عند الإغلاق)

# ── الإيقاف الصريح: المسار النظيف أوّلًا (البند ٦٢ · حكم المالك ٢٠٢٦-٠٨-١٥) ──
# كان `--stop` يقتل بـ`taskkill /F` فورًا، فلا تُكتب لقطة قطّ — و**١٧ ذرّة**
# تحفظ لقطتها، فيها إيقاف المالك وتجميده (٥٥٢/٥٥٠/٥١٩) وكتاب الاتجاه (٥٨١)
# ودفاتر الحدود (٥٠٦/٥٠٧/٦٥٨/٦٦٦).
#
# والسبب لم يكن اختيار `taskkill`: كل خدمة تُشغَّل بنافذة خاصّة (أدناه)، وحدث
# الكونسول لا يعبر إلى نافذة أخرى — والاستدعاء المباشر **يرجع True ولا يفعل
# شيئًا** (مقيس). فالإرسال يتمّ من عمليّة ساعية قصيرة العمر، لأنّ الحدث يصيب
# كل من على تلك النافذة ومنهم المُرسِل، و`SetConsoleCtrlHandler(NULL, TRUE)`
# يحجب CTRL+C وحده لا CTRL+BREAK (مقيس: ماتت عمليّتا قياس بـ0xC000013A).
#
# المهلة مشتقّة من القياس لا من الهواء: نواة حقيقيّة ٢١٢ ذرّة، ثمانية إيقافات،
# الإرسال 0.08s والموت 0.53–0.98s (الذيل)، و١٧ لقطة/1162 بايت في كل مرّة، ولا
# يطول بطول العمر (10s/45s/120s ⇒ 0.59/0.67/0.53). فالسقف عشرة أضعاف الذيل:
# الانتظار ثوانيَ زائدة لا يكلّف شيئًا، والقتل المبكّر يفقد اللقطة كلّها.
STOP_TIMEOUT_S = 10.0
_COURIER_TIMEOUT_S = 5.0
_STILL_ACTIVE = 259
_PROCESS_QUERY_LIMITED = 0x1000
_CREATE_NO_WINDOW = 0x08000000
# كان `ROOT/var/snapshots` بينما النواة تكتب `var/forex/snapshots` (core_forex.yaml)
# — فالعدّاد في `--stop` كان يقرأ مجلّدًا لا لقطة فيه ويعلن «لا لقطات» كذبًا.
sys.path.insert(0, str(ROOT / "governance"))
try:
    from runtime_paths import core_state_root as _core_state_root
except Exception as exc:  # noqa: BLE001 — بلا شجرة shared/ لا نخمّن مرسًى
    raise RuntimeError(
        "تعذّر تحميل shared/runtime_paths (مالك الجذور) من "
        f"{ROOT / 'governance'} — لا يُقبل حدسُ مرسى اللقطات: {exc}") from exc
SNAPSHOTS_DIR = _core_state_root() / "forex" / "snapshots"

_COURIER_SOURCE = '''
import ctypes, sys, time
from pathlib import Path
pid, flag = int(sys.argv[1]), Path(sys.argv[2])
k32 = ctypes.windll.kernel32
k32.FreeConsole()
if not k32.AttachConsole(pid):
    raise SystemExit(2)
flag.write_text("attached", encoding="utf-8")   # نُعلن الوصول قبل أن تقتلنا إشارتنا
k32.GenerateConsoleCtrlEvent(1, 0)              # CTRL_BREAK لكل من على هذه النافذة
time.sleep(2.0)
'''


def _alive(pid: int) -> bool:
    handle = ctypes.windll.kernel32.OpenProcess(_PROCESS_QUERY_LIMITED, False, pid)
    if not handle:
        return False
    code = ctypes.c_ulong()
    ok = ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
    ctypes.windll.kernel32.CloseHandle(handle)
    return bool(ok) and code.value == _STILL_ACTIVE


def _snapshot_state() -> tuple[int, float]:
    try:
        files = list(SNAPSHOTS_DIR.glob("*.json"))
    except OSError:
        return 0, 0.0
    return len(files), max((f.stat().st_mtime for f in files), default=0.0)


def _ring_ctrl_break(pid: int) -> tuple[bool, str]:
    """يوقظ المسار النظيف بالنواة. يرجع (وصل الساعي؟، الشرح)."""
    box = Path(tempfile.mkdtemp(prefix="stop62_"))
    script, flag = box / "courier.py", box / "attached.txt"
    try:
        script.write_text(_COURIER_SOURCE, encoding="utf-8")
        try:
            subprocess.run([PYEXE, str(script), str(pid), str(flag)],
                           creationflags=_CREATE_NO_WINDOW, capture_output=True,
                           timeout=_COURIER_TIMEOUT_S)
        except subprocess.TimeoutExpired:
            return flag.exists(), "الساعي تجاوز مهلته"
        if flag.exists():
            return True, ""
        return False, "الساعي لم يصل إلى نافذة العمليّة"
    except OSError as exc:
        return False, "تعذّر تشغيل الساعي: %s" % exc
    finally:
        try:
            for item in box.iterdir():
                item.unlink()
            box.rmdir()
        except OSError:
            pass


def _stop_process(pid: int, name: str) -> dict:
    """إيقاف عمليّة واحدة: النظيف أوّلًا، والقسريّ **معلَنًا** لا صامتًا.

    حكمه الصريح: «لا أقبل جعل `taskkill /F` مجرّد fallback صامت؛ إذا وصلنا إليه
    فهذا يعني أنّ اللقطة النظيفة لم تُضمَن، ويجب أن يظهر ذلك بوضوح في السجلّ».
    """
    started = time.monotonic()
    before_count, before_stamp = _snapshot_state()
    record = {"name": name, "pid": pid, "result": "", "reason": "",
              "waited_s": 0.0, "snapshots": None}
    if not _alive(pid):
        record.update(result="already_gone", reason="العمليّة غير موجودة أصلًا")
        return record

    reached, why = _ring_ctrl_break(pid)
    if reached:
        deadline = time.monotonic() + STOP_TIMEOUT_S
        while time.monotonic() < deadline:
            if not _alive(pid):
                after_count, after_stamp = _snapshot_state()
                record.update(result="clean_stop", waited_s=round(time.monotonic() - started, 2),
                              snapshots="%d ملفّ%s" % (after_count,
                                                       "" if after_stamp <= before_stamp
                                                       else " (كُتبت الآن)"))
                return record
            time.sleep(0.1)
        record["reason"] = ("لم تمت خلال %.0f ثانية — **اللقطة النظيفة غير مضمونة**"
                            % STOP_TIMEOUT_S)
    else:
        record["reason"] = "%s — **اللقطة النظيفة غير مضمونة**" % why

    subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True)
    after_count, after_stamp = _snapshot_state()
    record.update(result="forced_stop", waited_s=round(time.monotonic() - started, 2),
                  snapshots="%d ملفّ%s" % (after_count,
                                           "" if after_stamp <= before_stamp else " (كُتبت الآن)"))
    return record


# ── النواة: الإغلاق النظيف بملفّ التحكّم، ثمّ أبناؤها (٢٠٢٦-١٠-٢٦، فحص المشروع، ختم المالك «nq») ──
# كان `--stop` يوقف النواة كغيرها: إشارةٌ ثمّ قتلٌ قسريّ بعد عشر ثوانٍ (`STOP_TIMEOUT_S`) وبلا أبنائها. والإغلاق النظيف يحتاج
# حتّى تسعين ثانية: توقف النواة عمليّتها الباردة (مهلتها 45 ث) ثمّ ذرّاتها ثمّ تكتب لقطتها. والعمليّة الباردة ابنةٌ لا تموت بموت
# أمّها (`engine/cold_host.py`: `spawn` و`daemon=False`)، فالقتل القسريّ يتركها يتيمة. الآن كأداة الإيقاف `scripts/stop_all.py` —
# بكودها نفسه لا بنسخةٍ منه: طلبٌ بملفّ التحكّم، وانتظار إقرار النواة ثمّ موتها النظيف حتّى مهلتها؛ وما لا يُقرّ يمضي في المسار
# السابق معلَنًا كما كان. ثمّ يُوقف من بقي حيًّا من أبنائها، ومنهم العمليّة الباردة — إلّا عمليّات القياس، فليست خدمات.
_STOP_TOOL = ROOT / "scripts" / "stop_all.py"
_CHILD_WAIT_S = 5.0


def _load_stop_tool():
    """أداة الإيقاف نفسها، تُحمَّل من ملفّها — لا تُنسخ دوالّها هنا فتفترق النسختان يومًا."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("nq_stop_all", _STOP_TOOL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _stop_children(children: list, psutil, skip_marks: tuple) -> str:
    """يوقف من بقي حيًّا من أبناء النواة بعد خروجها: إنهاءٌ ثمّ قتلٌ لمن لم يستجب، معلَنًا."""
    alive = []
    for child in children:
        try:
            # بايثون وحده، كمسحة أداة الإيقاف الثانية: مضيف نافذة الأوامر ابنٌ أيضًا، ويخرج وحده حين لا يبقى عليها أحد.
            if not child.is_running() or not child.name().lower().startswith("python"):
                continue
            cmd = " ".join(child.cmdline()).lower()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
        if any(mark.lower() in cmd for mark in skip_marks):
            continue
        alive.append(child)
    if not alive:
        return "لم يبقَ من أبنائها أحد"
    for child in alive:
        try:
            child.terminate()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    _, left = psutil.wait_procs(alive, timeout=_CHILD_WAIT_S)
    for child in left:
        try:
            child.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    psutil.wait_procs(left, timeout=3)
    return "بقي من أبنائها %d بعدها فأُوقف%s" % (len(alive), (" (منها %d قسرًا)" % len(left)) if left else "")


def _stop_core(pid: int, name: str) -> dict:
    """النواة: طلب الإغلاق النظيف بملفّ التحكّم أوّلًا، ثمّ المسار السابق لمن لم يُقرّ، ثمّ أبناؤها الباقون."""
    try:
        import psutil
    except ImportError:
        record = _stop_process(pid, name)
        record["children"] = "تعذّر فحص أبنائها: مكتبة العمليّات غير موجودة"
        return record
    started = time.monotonic()
    before_count, before_stamp = _snapshot_state()
    try:
        core = psutil.Process(pid)
        children = core.children(recursive=True)
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        core, children = None, []
    tool, dirs, gone = None, [], set()
    if core is not None:
        try:
            tool = _load_stop_tool()
            dirs = tool._control_dirs([core], psutil)     # من بيئة النواة نفسها، قبل أن تموت
            gone = tool._graceful_core_stop({pid: name}, psutil)
        except Exception as exc:  # noqa: BLE001 — الطلب النظيف لا يمنع الإيقاف أبدًا
            print("[مشغّل] تعذّر طلب الإغلاق النظيف (%s) — المسار السابق" % type(exc).__name__, flush=True)
            gone = set()
    if pid in gone:
        status = {}
        for directory in dirs:
            found = tool._read_json(directory / tool.STOP_STATUS_FILE)
            try:
                if isinstance(found, dict) and int(found.get("pid") or 0) == pid:
                    status = found
                    break
            except (TypeError, ValueError):
                continue
        clean = status.get("stage") == "stopped"
        after_count, after_stamp = _snapshot_state()
        record = {"name": name, "pid": pid, "result": "clean_stop" if clean else "exited_unconfirmed",
                  "reason": "" if clean else "خرجت بلا إعلان إغلاقٍ نظيف — **اللقطة غير مؤكَّدة**",
                  "waited_s": round(time.monotonic() - started, 2),
                  "snapshots": "%d ملفّ%s" % (after_count, "" if after_stamp <= before_stamp else " (كُتبت الآن)")}
    else:
        record = _stop_process(pid, name)
        record["waited_s"] = round(time.monotonic() - started, 2)   # ومعها انتظار الإقرار، لا ما بعده وحده
    record["children"] = _stop_children(children, psutil, tuple(getattr(tool, "_NOT_SERVICES", ())))
    return record


def _port_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.4)
        return s.connect_ex(("127.0.0.1", port)) == 0


def _wait_port(port: int, name: str, timeout: float = 40.0) -> bool:
    t0 = time.time()
    while time.time() - t0 < timeout:
        if _port_open(port):
            return True
        time.sleep(0.5)
    print(f"[مشغّل] ⚠ انتهت مهلة انتظار {name} (منفذ {port})", flush=True)
    return False


def _spawn(script: Path, name: str, args: tuple[str, ...] = ()) -> None:
    env = dict(os.environ, PYTHONUTF8="1")
    print(f"[مشغّل] ▶ تشغيل {name} …", flush=True)
    # نافذة أوامر خاصّة لكل خدمة: تبقى حيّة بعد إغلاق نافذة اللوحة، ويبقى
    # سجلّها ظاهرًا للمالك — تشغيل مستمرّ بلا إخفاء.
    flags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0) if os.name == "nt" else 0
    p = subprocess.Popen([PYEXE, str(script), *args], cwd=str(ROOT), env=env,
                         creationflags=flags)
    _started.append(p)


def _ensure(port: int, script: Path, name: str, args: tuple[str, ...] = ()) -> None:
    if _port_open(port):
        print(f"[مشغّل] ✓ {name} شغّال أصلًا (منفذ {port}) — إعادة استخدامه", flush=True)
        return
    _spawn(script, name, args)
    _wait_port(port, name)


def _ensure_telegram() -> None:
    """٦١٠ — تشغيل المنصّة المتنقّلة، وفقط إن كان توكنها بخزنة الأسرار.

    بلا توكن لا تُشغَّل أصلًا: منصّة بلا مفتاح ضجيج، لا ميزة. وسطران بالنافذة
    يقولان للمالك ما الناقص بالضبط — لا صمت ولا خطأ مزعج كل إقلاع.
    نسأل المنصّة نفسها عن مصدر توكنها بدل تكرار المنطق هنا: مصدر حكم واحد.
    """
    if _port_open(TG_PORT):
        print("[مشغّل] ✓ تلغرام (٦١٠) شغّال أصلًا — إعادة استخدامه", flush=True)
        return
    ok, why = False, "تعذّر فحص الخزنة"
    try:
        sys.path.insert(0, str(ROOT))
        from governance.telegram import token_from_vault
        token, why = token_from_vault()
        ok = bool(token)
        del token                       # لا يبقى بذاكرة المشغّل
    except Exception as exc:            # noqa: BLE001
        why = str(exc)
    if not ok:
        print(f"[مشغّل] ○ تلغرام (٦١٠) غير مفعّل — {why}", flush=True)
        print("        الخطوات كاملة داخل نافذته، أو بزرّ «فحص منصّة تلغرام» باللوحة.", flush=True)
        return
    _spawn(TELEGRAM, "تلغرام (٦١٠)")


def _news_bot_running(news_root: Path) -> bool:
    """قفل البوت (`data/bot.lock`، قفل نظامٍ يمسكه البوت طول حياته) ممسوك ⟸ البوت يعمل. فحصٌ لا يمسك القفل."""
    lock_path = news_root / os.getenv("NEWS_BOT_DATA_DIR", "data") / "bot.lock"
    if os.name != "nt" or not lock_path.is_file():
        return False
    import msvcrt
    try:
        with open(lock_path, "a+") as handle:
            handle.seek(0)
            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                return True
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
    except OSError:
        return False
    return False


def _ensure_news_bot() -> None:
    """بوت الأخبار (مشروع QUANT_NQ_NEWS المجاور) — من نفس المشغّل.

    أمر المالك ٢٠٢٦-٠٨-٢٠: «خلّي بوت الأخبار يشتغل من بوت لوحة القيادة —
    كلهم من مكان واحد». مشروع مستقلّ ببيئته الخاصّة، فيُشغَّل ببايثونه هو
    وبمجلّده هو — لا نخلط بيئتين.

    بلا توكن لا يُشغَّل: نسخة بلا مفتاح تموت فورًا وتترك نافذة خطأ بلا فائدة.
    والنسخة المكرّرة يمنعها قفل البوت نفسه (`app/single_instance.py`).
    """
    news_root = ROOT.parent / "QUANT_NQ_NEWS"
    news_py = news_root / ".venv" / "Scripts" / "python.exe"
    news_main = news_root / "main.py"
    if not (news_main.is_file() and news_py.exists()):
        print("[مشغّل] ○ بوت الأخبار غير موجود — تخطّي", flush=True)
        return
    env_file = news_root / ".env"
    if not env_file.is_file():
        print("[مشغّل] ○ بوت الأخبار: ما في ملفّ .env — لم يُشغَّل", flush=True)
        print("        افتح «بوت الأخبار.bat» بمجلّده مرّة واحدة لتحطّ التوكن.", flush=True)
        return
    try:
        raw = env_file.read_text(encoding="utf-8", errors="ignore")
        line = next((l for l in raw.splitlines() if l.startswith("BOT_TOKEN=")), "")
        token_len = len(line.split("=", 1)[1].strip()) if "=" in line else 0
    except OSError:
        token_len = 0
    if token_len < 20:
        print("[مشغّل] ○ بوت الأخبار: التوكن غير مضبوط داخل .env — لم يُشغَّل", flush=True)
        return
    # ٢٠٢٦-١٠-١٢ (المالك: «لمّا توقّف السستم بيضلّ نافذتين، ثمّ تشغّله بيفتح نافذتين مرّة ثانية — عم يتكدّس»): الإيقاف لا يلمس
    # البوت (stop_all، بندها ٤)، فكان كلّ إقلاعٍ يفتح نسخةً ثانية يرفضها قفل البوت فتخرج — وتبقى نافذتها (تبويبٌ في الطرفيّة) مفتوحة.
    # الآن: إن كان قفل البوت ممسوكًا فالبوت يعمل ⟸ لا نافذة جديدة.
    if _news_bot_running(news_root):
        print("[مشغّل] ✓ بوت الأخبار يعمل أصلًا — لا نافذة جديدة", flush=True)
        return
    print("[مشغّل] ▶ تشغيل بوت الأخبار …", flush=True)
    flags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0) if os.name == "nt" else 0
    p = subprocess.Popen([str(news_py), str(news_main)], cwd=str(news_root),
                         env=dict(os.environ, PYTHONUTF8="1"), creationflags=flags)
    _started.append(p)


def _shutdown() -> None:
    """إغلاق النافذة يغلق النافذة وحدها. النواة تبقى تعمل.

    كان هنا terminate() لكل ما شُغّل، فكان إغلاق اللوحة يقتل النواة ومعها
    التداول والمراقبة — والمالك لا يقصد الإطفاء حين يغلق نافذة. النظام
    الدائم لا يُوقفه إغلاق شاشة؛ الإيقاف صار فعلًا صريحًا وحده.
    """
    if _started:
        print("[مشغّل] أُغلقت النافذة — النواة وخادم الحوكمة ما زالا يعملان.", flush=True)
        # ٢٠٢٦-١٠-٢٦ (فحص المشروع، ختم المالك «nq»): كان يطبع «غرفة القيادة.bat --stop»، وزرّ غرفة القيادة لا يمرّر كلمته —
        # فمن اتّبع السطر أقلع المنظومة بدل أن يوقفها. الإيقاف زرّه «إيقاف النظام» في جذر المشروع.
        print("[مشغّل] لإيقافهما صراحةً: زرّ «إيقاف النظام» في مجلّد المشروع — لا «غرفة القيادة»، فهي تُقلع ولا توقف.",
              flush=True)


def _stop_all() -> int:
    """إيقاف صريح بأمر المالك — لا يقع أبدًا كأثر جانبيّ لإغلاق نافذة."""
    import urllib.request
    stopped = []
    # ٢٠٢٦-١٠-٢٦: ومعها خادم الحوكمة الثاني (8092) — تُقلعه «غرفة القيادة» عبر مُطلِق السوق، وكان هذا الإيقاف لا يعرفه.
    for port, name in ((TG_PORT, "تلغرام (٦١٠)"), (GOV_PORT, "خادم الحوكمة"), (GOV2_PORT, "خادم الحوكمة الثاني"),
                       (CORE_PORT, "النواة")):
        if not _port_open(port):
            print(f"[مشغّل] {name} متوقّف أصلًا (منفذ {port}).", flush=True)
            continue
        seen = set()
        for line in subprocess.run(["netstat", "-ano", "-p", "TCP"], capture_output=True,
                                   text=True, shell=False).stdout.splitlines():
            parts = line.split()
            if len(parts) >= 5 and parts[1].endswith(f":{port}") and parts[3] == "LISTENING":
                seen.add(int(parts[4]))
        if not seen:
            print(f"[مشغّل] {name}: ما لقيت عمليّة تستمع على {port}.", flush=True)
            stopped.append(f"{name} (تعذّر)")
            continue
        for pid in sorted(seen):
            record = _stop_core(pid, name) if port == CORE_PORT else _stop_process(pid, name)
            mark = "🟢" if record["result"] == "clean_stop" else (
                "⚪" if record["result"] == "already_gone" else "🔴")
            print("[مشغّل] %s %s · %s · PID %d · انتظار %.2fs · لقطات: %s%s%s"
                  % (mark, name, record["result"], record["pid"], record["waited_s"],
                     record["snapshots"] or "—",
                     ("" if not record["reason"] else " · السبب: " + record["reason"]),
                     ("" if not record.get("children") else " · " + record["children"])),
                  flush=True)
            stopped.append("%s %s" % (name, record["result"]))
    print("[مشغّل] أُوقف: " + (" · ".join(stopped) if stopped else "لا شيء"), flush=True)
    return 0


def _backtest_only() -> int:
    """٢٠٢٦-١٠-٢٢ (ختم المالك «NQ»): «أيّ قياس … على صفحة الباك تست من قلب السستم … بدّي قياس يمشي من هنيك ويشتغل حتّى لو
    المنظومة مطفية أو شغّالة». صفحة الباك تست وحدها: خادم الحوكمة (8090) ونافذةٌ مفتوحة على الباك تست — لا نواة ولا تداول ولا
    تلغرام ولا بوت أخبار. ولا يمسك قفل 8099: فإقلاع «غرفة القيادة» بعده يُقلع النواة كاملةً ويعيد استعمال الخادم نفسه."""
    print("=" * 54, flush=True)
    print("  صفحة الباك تست وحدها — بلا نواة ولا تداول", flush=True)
    print("=" * 54, flush=True)
    _ensure(GOV_PORT, SERVER, "خادم الحوكمة")
    url = f"{URL}/?tab=backtest&v={int(time.time())}"
    try:
        import webview  # pywebview
        webview.create_window("صفحة الباك تست", url, width=1600, height=950, min_size=(1024, 640),
                              background_color="#0d1119", text_select=True)
        webview.start()
    except Exception as exc:  # noqa: BLE001 — بلا نافذة تُفتح الصفحة بالمتصفّح
        print(f"[مشغّل] ✗ تعذّر فتح النافذة: {exc} — تُفتح بالمتصفّح: {url}", flush=True)
        try:
            import webbrowser
            webbrowser.open(url)
        except Exception:  # noqa: BLE001
            pass
        input("اضغط Enter للخروج…")
    print("[مشغّل] أُغلقت النافذة — خادم الحوكمة ما زال يعمل، والقياس الجاري يكمل على الجهاز.", flush=True)
    return 0


def main() -> None:
    if os.name == "nt":
        os.system("chcp 65001 >nul")        # عرض العربي بنافذة الأوامر (من بايثون لتفادي لغبطة الـbat)
    if "--stop" in sys.argv:
        raise SystemExit(_stop_all())
    if "--backtest-only" in sys.argv:
        raise SystemExit(_backtest_only())
    # قفل نسخة واحدة: لو التطبيق شغّال مسبقًا، لا نفتح نسخة ثانية (يمنع التكرار عند الدبل-كليك المزدوج)
    lock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        lock.bind(("127.0.0.1", 8099))
        lock.listen(1)
    except OSError:
        print("[مشغّل] التطبيق شغّال مسبقًا — لن تُفتح نسخة ثانية.", flush=True)
        return
    print("=" * 54, flush=True)
    print("  غرفة القيادة — QUANT_NQ  (تطبيق سطح المكتب)", flush=True)
    print("=" * 54, flush=True)
    _ensure(CORE_PORT, CORE, "النواة")
    _ensure(GOV_PORT, SERVER, "خادم الحوكمة")
    _ensure_telegram()
    _ensure_news_bot()

    try:
        import webview  # pywebview
    except Exception as e:  # noqa: BLE001
        print(f"[مشغّل] ✗ pywebview غير متاح: {e}", flush=True)
        print(f"        افتح يدويًّا: {URL}", flush=True)
        input("اضغط Enter للخروج…")
        _shutdown()
        return

    # ٢٠٢٦-٠٩-١٠: كان هنا فرعٌ يفتح نافذة ثانية للوحة الكريبتو على 8091.
    # أُزيل ثابتاه مع مسح قسم الكريبتو (أمر المالك «امسح») وبقي الاستخدام،
    # فانهار المُشغّل بـ`NameError: CRYPTO_GOV_PORT` **قبل رسم النافذة** —
    # فبقيت الخدمات كلّها تعمل (8010 · 8090 · 8098) والمالك بلا لوحة إطلاقًا،
    # وهو أعلى إنذار في هذا المشروع: اللوحة هي المنتج لا الطرفية.
    # سوق واحد ⟵ نافذة واحدة.
    stamp = int(time.time())        # رابط فريد كل تشغيل → يتخطّى أي نسخة WebView مخزّنة
    windows = [("غرفة القيادة — الفوركس", f"{URL}/?v={stamp}")]
    for title, win_url in windows:
        print(f"[مشغّل] ✓ فتح النافذة على {win_url}", flush=True)
        webview.create_window(
            title,
            win_url,
            width=1600, height=950, min_size=(1024, 640),
            background_color="#0d1119",
            text_select=True,  # المكتبة بتعطّل تحديد النص افتراضيًّا — المالك بدو يحدّد وينسخ (خطأ/رقم/سجل)
        )
    try:
        webview.start()          # يحجب حتى إغلاق النافذة
    except Exception as exc:     # noqa: BLE001
        # ٢٠٢٦-٠٩-٠١: كان الفشل هنا يسقط في `finally` فيُوقف كل الخدمات
        # ويخرج المشغّل **بلا نافذة وبلا كلمة**. أشهر سببٍ على جهاز جديد:
        # WebView2 Runtime غير منصَّب — `pywebview` يستورد بنجاح ثم يفشل عند
        # فتح النافذة. حارسٌ لا يقول لماذا سقط ليس حارسًا: يُشرح السبب،
        # وتبقى الخدمات شغّالة، ويُفتح المتصفّح بدل النافذة فلا يضيع اليوم.
        print("=" * 62, flush=True)
        print(f"[مشغّل] ✗ تعذّر فتح نافذة سطح المكتب: {exc}", flush=True)
        print("        الأرجح أن WebView2 Runtime غير منصَّب على هذا الجهاز.", flush=True)
        print("        نزّله من موقع مايكروسوفت باسم:", flush=True)
        print("          Microsoft Edge WebView2 Runtime (Evergreen Standalone)", flush=True)
        print("        والخدمات تعمل الآن، فتُفتح اللوحتان بالمتصفّح بدلها:", flush=True)
        for _title, _url in windows:
            print(f"          {_url}", flush=True)
        try:
            import webbrowser
            for _title, _url in windows:
                webbrowser.open(_url)
        except Exception:  # noqa: BLE001 — المتصفّح ترفٌ لا شرط
            pass
        print("=" * 62, flush=True)
        # ٢٠٢٦-١٠-٢٦: كان «لإيقاف الخدمات والخروج»، والإغلاق لا يوقف خدمةً (حكم `_shutdown`).
        input("اضغط Enter للخروج — الخدمات تبقى تعمل…")
        _shutdown()
        return
    _shutdown()


if __name__ == "__main__":
    main()
