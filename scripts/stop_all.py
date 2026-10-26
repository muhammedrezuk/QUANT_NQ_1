"""إيقاف كل خدمات QUANT_NQ — إغلاق نظيف ثمّ تحقّق بالقياس.

سبب إعادة الكتابة (٢٠٢٦-٠٩-٠١، مقيس):
النسخة السابقة كانت تعرف ستّة منافذ فقط `{8010, 8020, 8090, 8092, 8093,
`governance/app.py`). فبقيت عمليّتان تعملان بعد «تمّ الإيقاف»، واحتاجتا
إطفاءً يدويًّا. وكانت تعلن النجاح بلا تحقّق: تطبع «تمّ» ولو بقي المنفذ
مشغولًا — وهذا أسوأ من الفشل الصريح لأنّه يخفيه.

ما تغيّر:
1. المنافذ الثمانية كاملة.
2. مسحة ثانية بالمسار: أي عمليّة بايثون تنفّذ ملفًّا داخل جذر المشروع
   تُلتقط حتّى لو لم تستمع على منفذ (مشغّل · عامل · بقايا).
3. تحقّق بعد الإيقاف: تُعاد قراءة المنافذ، ولا يُعلَن النجاح إلّا إذا
   تحرّرت كلّها فعلًا. وإلّا خرج بالرمز 1 وسمّى ما بقي بالرقم.
4. لا تلمس `QUANT_NQ_NEWS` — مشروع شقيق ببيئته وزرّه. تُبلّغ عنه فقط.
"""
from __future__ import annotations
import json
import os
import socket
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NEWS_ROOT = ROOT.parent / "QUANT_NQ_NEWS"
#: عمليّاتٌ بالمشروع ليست خدماتٍ حيّة — لا تُوقف مع النظام (انظر المسحة الثانية في `main`).
_NOT_SERVICES = ("backtest.full_replay", "backtest.calibration_loop", "جلب_تاريخ_سي_تريدر",
                 # ١٧/١٠: أداة الباك تست الاحترافيّة — بناء مخزن الحقائق والتوليفة عمليّاتٌ خلفيّة طويلة لا خدمات (أوقفها إيقاف 20:30)
                 "backtest.facts_store", "backtest.combo_engine")

# ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): الإغلاق النظيف لم يحدث ولا مرّة — 19 إقلاعًا
# منذ ٢٠٢٦-٠٩-٢٤ وصفر سطر «إشارة إيقاف مستلمة» في سجلّ النواة. النواة في نافذتها
# الخاصّة، و`os.kill(pid, CTRL_BREAK_EVENT)` يخاطب مجموعةً في كونسول المُرسِل فيرجع
# بلا خطأ ولا يصل (مقيس على نواةٍ معزولة: «إرسال CTRL_BREAK» ثمّ terminate بعد 10 ث،
# رمز خروج 15، صفر لقطة). فصار الزرّ يطلب أوّلًا من النواة أن توقف نفسها بملفّ تحكّم
# تقرؤه كلّ ثانية (`governance/scripts/run_core.py` — `_StopRequestWatch`)، وينتظر
# إقرارها ثمّ موتها النظيف، ولا يقول «نظيف» إلّا إذا كتبت النواة أنّها التقطت لقطاتها.
# وما لا يجيب (نواة أقدم · حلقة ميتة · لا نواة) يمضي في المسار السابق حرفًا.
STOP_REQUEST_FILE = "core_stop.request.json"
STOP_STATUS_FILE = "core_stop.status.json"
#: الإقرار يُكتب من خيطٍ يقرأ الملفّ كلّ ثانية — خمس ثوانٍ خمسة أضعافه.
ACK_WAIT_S = 5.0
#: الإغلاق الحيّ يوقف العمليّة الباردة (مهلتها 45 ث) ثمّ ~190 ذرّة ثمّ اللقطة.
GRACE_S = float(os.environ.get("NQ_STOP_GRACE_S") or 90.0)
#: ما يُعرف به المُقلِع في سطر أوامر النواة.
CORE_ENTRYPOINTS = ("run_core.py", "run_forex.py")

#: كل منافذ النظام. 8091 و8099 كانتا الناقصتين.
PORTS = {
    8010: "نواة الفوركس",
    8090: "لوحة الفوركس",
    8092: "حوكمة الفوركس",
    8098: "منصّة تلغرام",
    8099: "قفل المشرف",
}


def listening(port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(0.20)
        return s.connect_ex(("127.0.0.1", port)) == 0


def _ancestors(proc, psutil) -> set[int]:
    """أنا وآبائي — لا نقتل أنفسنا ولا الطرفيّة التي أطلقتنا."""
    out = {proc.pid}
    try:
        for p in proc.parents():
            out.add(p.pid)
    except Exception:
        pass
    return out


def _send_ctrl_break(pid: int) -> bool:
    """أرسل CTRL_BREAK_EVENT على ويندوز — يُلتقط بمقبض SIGBREAK."""
    if os.name != "nt":
        return False
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        # CTRL_BREAK_EVENT = 1 (ويندوز)
        # signal.SIGBREAK = 21 (بايثون) — لكن الصحيح هو CTRL_BREAK_EVENT = 1
        PROCESS_ALL_ACCESS = 0x1F0FFF
        handle = kernel32.OpenProcess(PROCESS_ALL_ACCESS, False, pid)
        if not handle:
            return False
        try:
            import signal
            # CTRL_BREAK_EVENT = 1 (ويندوز) — ليس SIGBREAK = 21
            os.kill(pid, signal.CTRL_BREAK_EVENT)
            return True
        finally:
            kernel32.CloseHandle(handle)
    except Exception:
        return False


# ── الإيقاف النظيف عبر ملفّ التحكّم (٢٠٢٦-١٠-٠٢، ختم المالك «صلح كامل nq») ──────

def _is_core(proc) -> bool:
    try:
        cmd = " ".join(proc.cmdline()).lower()
    except Exception:
        return False
    return any(name in cmd for name in CORE_ENTRYPOINTS)


def _control_dirs(cores, psutil) -> list[Path]:
    """أين تقرأ النواة طلبها: `<مرسى الحالة>/control` — كما يحلّه المُقلِع.

    المرسى من مالك الجذور نفسه (`shared.runtime_paths.core_state_root`)، ومن بيئة
    النواة نفسها إن أمكن قراءتها (`QUANT_CORE_STATE_ROOT`) — فلا يُخمَّن مسار.
    """
    found: list[Path] = []
    try:
        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
        from shared.runtime_paths import core_state_root
        found.append(Path(core_state_root(code_root=ROOT)) / "control")
    except Exception:
        pass
    for proc in cores:
        try:
            value = (proc.environ().get("QUANT_CORE_STATE_ROOT") or "").strip()
        except Exception:
            continue
        if value and Path(value).is_absolute():
            found.append(Path(value) / "control")
    unique: list[Path] = []
    for path in found:
        if all(os.path.normcase(str(path)) != os.path.normcase(str(u)) for u in unique):
            unique.append(path)
    return unique


def _read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _write_json_atomic(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(".%s.%d.tmp" % (path.name, os.getpid()))
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


# ── علامة «إيقاف النظام» للنوافذ (٢٠٢٦-١٠-٢٦، ختم المالك «nq») ───────────────
# بعد إطفاء ٢٦/١٠ بقيت نافذتا «غرفة القيادة» والفوركس الجانبيّة واقفتين عند «اضغط
# أيّ مفتاح». المشرف يُقتل هنا بـterminate فيخرج برمز 15، وهو رمز كلّ قتلٍ بهذه
# المكتبة لا علامة إيقافٍ نظيف (والمشرف لا يعيد رمزًا خاصًّا: `main()` يرجع بلا
# رمز)؛ وأداة الفوركس في النافذة الجانبيّة خرجت قبل ساعات. فتكتب الأداة قبل أن
# توقف شيئًا علامةً مؤرَّخة في مجلّد التحكّم، والزرّ يقرؤها قبل إقلاع برنامجه وبعد
# خروجه: إن تغيّرت فالخروج من هذا الزرّ، فتُغلق النافذة بلا توقّف. وإن غابت أو
# ثبتت تتوقّف النافذة كما كانت، كي يقرأ المالك رسالة الخطأ.
STOP_MARK_FILE = "stop_all.mark"


def write_stop_mark() -> Path | None:
    """يكتب العلامة ذرّيًّا في `<جذر التشغيل>/var/control/` ويعيد مسارها، أو None.

    محتواها سطرٌ واحد من رقمين: الوقت بالنانوثانية ورقم هذه العمليّة — أرقامٌ
    وحدها كي يقرأها `set /p` في الزرّ ويقارنها بلا تنصيص. والقارئ قد يمسك الملفّ
    لحظةً فيُرفض الاستبدال، فتُعاد المحاولة. ولا تمنع الإيقاف أبدًا: فشلها يُقال
    ويمضي الإيقاف، والنوافذ حينها تتوقّف كما كانت.
    """
    try:
        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
        from shared.runtime_paths import runtime_var
        path = runtime_var("control", STOP_MARK_FILE, code_root=ROOT)
    except Exception as exc:  # المكان لا يُخمَّن
        print(f"  تعذّر تحديد مكان علامة الإيقاف ({type(exc).__name__}: {exc}) — النافذتان تبقيان مفتوحتين")
        return None
    token = f"{time.time_ns()} {os.getpid()}"
    tmp = path.with_name(".%s.%d.tmp" % (path.name, os.getpid()))
    last: Exception | None = None
    for _ in range(20):
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp.write_text(token, encoding="ascii")
            os.replace(tmp, path)
            return path
        except OSError as exc:
            last = exc
            time.sleep(0.05)
    print(f"  تعذّرت كتابة علامة الإيقاف في {path}: {last} — النافذتان تبقيان مفتوحتين")
    return None


def _graceful_core_stop(targets: dict[int, str], psutil) -> set[int]:
    """يطلب من النواة أن توقف نفسها، وينتظر إقرارها ثمّ موتها. يعيد ما مات منها.

    لا إقرار خلال `ACK_WAIT_S` ⟵ مجموعة فارغة، والمسار السابق كما كان حرفًا.
    """
    cores = []
    for pid in sorted(targets):
        try:
            proc = psutil.Process(pid)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
        if _is_core(proc):
            cores.append(proc)
    if not cores:
        return set()
    request = {"request_id": uuid.uuid4().hex, "pids": [p.pid for p in cores],
               "requested_at": time.time(), "by": "scripts/stop_all.py"}
    written = []
    for directory in _control_dirs(cores, psutil):
        try:
            _write_json_atomic(directory / STOP_REQUEST_FILE, request)
            written.append(directory)
        except OSError as exc:
            print(f"  تعذّرت كتابة طلب الإيقاف في {directory}: {exc}")
    if not written:
        return set()
    print(f"  طلب إغلاقٍ نظيف للنواة PID={[p.pid for p in cores]} عبر ملفّ التحكّم: "
          + " · ".join(str(d) for d in written))

    acked: dict[int, Path] = {}
    deadline = time.monotonic() + ACK_WAIT_S
    while time.monotonic() < deadline and len(acked) < len(cores):
        for directory in written:
            status = _read_json(directory / STOP_STATUS_FILE)
            if isinstance(status, dict) and status.get("request_id") == request["request_id"]:
                try:
                    acked[int(status.get("pid"))] = directory
                except (TypeError, ValueError):
                    pass
        if len(acked) < len(cores):
            time.sleep(0.2)
    if not acked:
        print(f"  لم تُقرّ النواة الطلب خلال {ACK_WAIT_S:.0f} ث (نسخة أقدم أو عمليّة عالقة)"
              " — المسار السابق")
        return set()

    waiting = [p for p in cores if p.pid in acked]
    print(f"  أقرّت النواة PID={sorted(acked)} — انتظار إغلاقها النظيف حتى {GRACE_S:.0f} ث")
    started = time.monotonic()
    gone, alive = psutil.wait_procs(waiting, timeout=GRACE_S)
    took = time.monotonic() - started
    for proc in gone:
        status = _read_json(acked[proc.pid] / STOP_STATUS_FILE) or {}
        if status.get("request_id") == request["request_id"] and status.get("stage") == "stopped":
            captured, failed = status.get("captured") or [], status.get("failed") or []
            print(f"  ✓ إغلاق نظيف PID={proc.pid} خلال {took:.1f} ث — لقطة ساكنة لـ{len(captured)} ذرّة"
                  + (f" · فشلت لقطة {failed}" if failed else ""))
        else:
            print(f"  ⚠ خرجت النواة PID={proc.pid} بلا إعلان إغلاقٍ نظيف — **اللقطة غير مؤكَّدة**")
    for proc in alive:
        print(f"  ✗ النواة PID={proc.pid} لم تُكمل إغلاقها خلال {GRACE_S:.0f} ث"
              " — تُكمَل بالمسار السابق (**اللقطة النظيفة غير مضمونة**)")
    return {proc.pid for proc in gone}


def main() -> int:
    try:
        import psutil
    except ImportError:
        print("psutil غير مثبت — شغّل زرّ التهيئة.")
        return 1

    # ٢٠٢٦-١٠-٢٦: العلامة قبل أيّ إيقاف — النافذتان تقرآنها حين يخرج برنامجاهما.
    write_stop_mark()

    me = psutil.Process()
    protected = _ancestors(me, psutil)
    targets: dict[int, str] = {}

    # ── مسحة ١: بالمنافذ ────────────────────────────────────────────
    for c in psutil.net_connections(kind="tcp"):
        if c.laddr and c.laddr.port in PORTS and c.pid and c.pid not in protected:
            targets.setdefault(c.pid, PORTS[c.laddr.port])

    # ── مسحة ٢: بالمسار — تلتقط ما لا يستمع على منفذ ───────────────
    root_s = str(ROOT).lower()
    news_s = str(NEWS_ROOT).lower()
    for p in psutil.process_iter(["pid", "name", "cmdline"]):
        pid = p.info["pid"]
        if pid in protected or pid in targets:
            continue
        if not (p.info["name"] or "").lower().startswith("python"):
            continue
        cmd = " ".join(p.info["cmdline"] or []).lower()
        if news_s in cmd:          # المشروع الشقيق — لا يُلمس
            continue
        # ٢٠٢٦-١٠-٠٦ (تفويض المالك «NQ صلاحية كاملة»): الاختبار التاريخيّ والعيار المستمرّ وأداة جلب
        # التاريخ ليست خدماتٍ حيّة — عمليّاتٌ مستقلّة لا منفذ لها ولا تمسّ المنصّة، وإيقافها له زرّه
        # في صفحة «باك تست». مقيس: إقلاع 01:35 قتل الجلب في منتصفه (رمز 15)، وكان سيقتل تجارب العيار.
        if any(mark in cmd for mark in _NOT_SERVICES):
            continue
        if root_s in cmd:
            targets[pid] = "عمليّة بالمشروع"

    if not targets:
        print("لا توجد خدمات QUANT_NQ عاملة.")
    else:
        # ── ٠: النواة توقف نفسها أوّلًا (ملفّ التحكّم) — وما بقي يمضي كما كان ──
        # النواة توقف عمليّتها الباردة بنفسها، فلا يُلمس شيءٌ قبل أن تنتهي.
        try:
            stopped_clean = _graceful_core_stop(targets, psutil)
        except Exception as exc:  # الطلب النظيف لا يمنع الإيقاف أبدًا
            print(f"  تعذّر طلب الإغلاق النظيف ({type(exc).__name__}: {exc}) — المسار السابق")
            stopped_clean = set()
        if stopped_clean:
            targets = {pid: label for pid, label in targets.items()
                       if pid not in stopped_clean and psutil.pid_exists(pid)}
        procs = []
        alive = []
        # ── ويندوز: أرسل CTRL_BREAK_EVENT أولاً (يُلتقط بمقبض SIGBREAK) ──
        if not targets:
            pass
        elif os.name == "nt":
            for pid, label in sorted(targets.items()):
                try:
                    proc = psutil.Process(pid)
                    # ٢٠٢٦-٠٩-٠٤ (ختم NQ): كانت العمليّة تُضاف إلى `procs` **فقط** عند
                    # نجاح إرسال CTRL_BREAK. و`os.kill(pid, CTRL_BREAK_EVENT)` على
                    # ويندوز يخاطب مجموعةَ عمليّات لا عمليّةً، فلا ينجح إلّا مع رئيس
                    # مجموعة — وأبناء `governance/app.py` ليسوا كذلك، فيُرمى OSError
                    # ويُرجَع False. النتيجة: مَن فشلت إشارته يخرج من القائمة، فلا
                    # يصله `terminate()` أصلًا — الاحتياط يحمي مَن لا يحتاجه وحده.
                    # مقيس ٢٠٢٦-٠٩-٠٤ ٠٢:٢٥: طُبعت ستّ رسائل «إرسال CTRL_BREAK» ثمّ
                    # «تمّ الإيقاف» ولم تمت عمليّة واحدة، وخمسة منافذ بقيت تستمع.
                    # الآن: تُضاف دائمًا، ويُعلَن ما إذا وصلت الإشارة أم لا.
                    delivered = _send_ctrl_break(pid)
                    print(f"  إرسال CTRL_BREAK إلى PID={pid:<7} {label}"
                          f"{'' if delivered else '  (لم تصل الإشارة — سيُستعمل terminate)'}")
                    procs.append(proc)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            # انتظر ١٠ ثوانٍ للإغلاق النظيف (يُنفَّذ snapshot_all)
            _, alive = psutil.wait_procs(procs, timeout=10)
            if alive:
                print(f"  {len(alive)} عمليات لم تستجب لـ CTRL_BREAK — إرسال terminate()")
                for proc in alive:
                    try:
                        proc.terminate()
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass
                _, alive = psutil.wait_procs(alive, timeout=5)
        else:
            # ── لينكس/ماك: terminate() كالمعتاد ─────────────────────
            for pid, label in sorted(targets.items()):
                try:
                    proc = psutil.Process(pid)
                    print(f"  إيقاف PID={pid:<7} {label}")
                    proc.terminate()
                    procs.append(proc)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            _, alive = psutil.wait_procs(procs, timeout=8)
        
        # ── إنهاء قسريّ لمن لم يستجب ────────────────────────────────
        for proc in alive:
            try:
                print(f"  لم يستجب — إنهاء قسريّ PID={proc.pid}")
                proc.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        psutil.wait_procs(alive, timeout=4)

    # ── التحقّق: لا نُعلن النجاح إلّا بالقياس ────────────────────────
    print()
    still = {port: name for port, name in PORTS.items() if listening(port)}
    if still:
        print("  ✗ منافذ ما زالت مشغولة:")
        for port, name in sorted(still.items()):
            owner = ""
            for c in psutil.net_connections(kind="tcp"):
                if c.laddr and c.laddr.port == port and c.pid:
                    owner = f" (PID {c.pid})"
                    break
            print(f"      {port}  {name}{owner}")
        return 1

    print("  ✓ المنافذ الثمانية كلّها حرّة — النظام متوقّف.")

    # ── المشروع الشقيق: تبليغ لا إطفاء ──────────────────────────────
    news = [p.info["pid"] for p in psutil.process_iter(["pid", "cmdline"])
            if news_s in " ".join(p.info["cmdline"] or []).lower()]
    if news:
        print()
        print(f"  ملاحظة: بوت الأخبار يعمل ({len(news)} عمليّة) ولم يُلمس —")
        print("  مشروع شقيق ببيئته الخاصّة. إطفاؤه من نافذته أو من مجلّده.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
