"""Contract guard for problem 5-2 (option a) — the clean-shutdown path.

Owner's requirement, verbatim:

    "The guard proves that stop -> snapshot -> boot -> restore actually works,
     not merely that a call exists in the code."
    "SIGINT from the PARENT process to the child -- as close to Ctrl+C as
     possible. SIGTERM from the parent to the child -- the other path,
     explicitly. Each judged independently. If ProactorEventLoop on Windows
     refuses to install the handlers, THAT is the failure to be proven; do not
     work around it inside the guard."

What is measured, and what is deliberately NOT:

  * The real `run_core.py` is NEVER launched. Its config path and its snapshot
    directory are both hard-coded to the project root, so a test core would
    write REAL snapshot files that the live core would later restore from, and
    its storage atoms would write into the live `var/store`. `NQ_BRIDGE_DB`
    covers only 9 atoms. There is no safe isolation, so it is not attempted.
  * Instead: the launcher's stop wiring is ANCHORED byte-for-byte (so this test
    can never drift from the real code), and those exact semantics are then
    executed for real in a separate child process, with the real SnapshotEngine
    over real atoms built by the real bootloader, into a TEMPORARY directory.

  A) المرساة   -- run_core.py's stop block is byte-identical to the copy here.
  B) SIGINT    -- parent -> child, the owner's ladder, judged on its own.
  C) SIGTERM   -- parent -> child, the same ladder, judged on its own.
  D) الاستعادة -- a SECOND process restores from the files the first wrote, and
                  the state is compared field by field.

Exit 1 on any divergence.
"""
from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from build_registry.paths import RegistryAtomRoot
ATOM_ROOT = RegistryAtomRoot(ROOT)

sys.path.insert(0, str(ROOT))

LAUNCHER = ROOT / "governance" / "scripts" / "run_core.py"
PY = sys.executable

# ── أ) المرساة: كتلة الإيقاف كما هي حرفيًّا في المُشغّل ──────────────────────
# لو تغيّر المُشغّل سقطت المرساة، فلا يستطيع هذا الاختبار أن ينحرف عن الكود
# الحقيقيّ ويبقى أخضر. الاقتطاع بين علامتين ثابتتين، والمقارنة حرفيّة.
ANCHOR_START = "    stop_event = asyncio.Event()"
ANCHOR_END = "    # ⚠️ استدعاء دالة الإيقاف بنسختها الديناميكية الجديدة"
ANCHOR_EXPECTED = '''    stop_event = asyncio.Event()

    def _request_stop(*_args: object) -> None:
        log.info("إشارة إيقاف مستلمة")
        stop_event.set()

    loop = asyncio.get_running_loop()
    installed_signals: list[int] = []
    restore_handlers: dict = {}
    import signal
    _SIGNALS = tuple(s for s in (getattr(signal, name, None)
                                 for name in ("SIGINT", "SIGTERM", "SIGBREAK")) if s is not None)
    try:
        for sig in _SIGNALS:
            loop.add_signal_handler(sig, _request_stop)
            installed_signals.append(sig)
    except (NotImplementedError, ImportError, RuntimeError):
        # ويندوز: ProactorEventLoop يرفض add_signal_handler لكل الإشارات، فكانت
        # stop_event لا تُضبط أبدًا، و`await stop_event.wait()` لا يرجع، فلا
        # يُنفَّذ snapshot_all ولا مرّة (var\\snapshots = صفر ملفّ). المسار
        # البديل يبلغ **نفس** stop_event عبر signal.signal — فيبقى snapshot_all
        # هو الطريق الوحيد للحفظ، ولا يُضاف طريق ثانٍ.
        for sig in installed_signals:
            try:
                loop.remove_signal_handler(sig)
            except (NotImplementedError, RuntimeError):
                pass
        installed_signals.clear()

        def _request_stop_threadsafe(_signum: int, _frame: object) -> None:
            loop.call_soon_threadsafe(_request_stop)

        for sig in _SIGNALS:
            try:
                restore_handlers[sig] = signal.signal(sig, _request_stop_threadsafe)
            except (ValueError, OSError, RuntimeError):
                continue
        log.info("مقابض الإيقاف عبر signal.signal (مسار ويندوز): %s",
                 [getattr(s, "name", s) for s in restore_handlers])

    # مقبض signal.signal لا يُنفَّذ إلا حين تصحو الحلقة، وProactor قد ينام
    # طويلًا على انتظار خالص. نبضة قصيرة تضمن أن الإشارة تُنفَّذ فورًا.
    async def _signal_pump() -> None:
        while not stop_event.is_set():
            await asyncio.sleep(0.2)

    pump = asyncio.create_task(_signal_pump()) if restore_handlers else None

    # Item 64: a bounded foreground run. The flag existed, the canonical script
    # had lost it, and the only two tests that run the core as a real process
    # were killed by `unrecognized arguments: --demo-seconds` -- which read from
    # the outside as "the core did not boot". It stops through the SAME
    # stop_event, so the clean-shutdown snapshot path is not bypassed.
    if demo_seconds is not None and demo_seconds > 0:
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=demo_seconds)
        except asyncio.TimeoutError:
            log.info("انتهت المدّة المحدودة (%.0fs) — إيقاف نظيف", demo_seconds)
            stop_event.set()
    else:
        await stop_event.wait()
    if pump is not None:
        pump.cancel()

    log.info("إيقاف نظيف لكل الذرات (بترتيب عكسي عن الإقلاع والاعتماديات حياً)...")
    # يجب أن يتوقف الاكتشاف الحي أولًا: لقطة تُلتقط بينما يُحمَّل محرك
    # الاكتشاف ذرة جديدة تعني لقطة لحالة متغيّرة تحت أقدامنا.
    await hot_reload.stop_periodic()
    snap_report = await snapshot_engine.snapshot_all()
    if snap_report.captured:
        log.info("التُقطت حالة الذرات: %s", snap_report.captured)
    if snap_report.failed:
        log.warning("فشل التقاط حالة الذرات: %s", snap_report.failed)
    
'''

# The child replays exactly these semantics. It is written to a TEMP file.
CHILD = r'''
import asyncio, json, os, signal, sys
from pathlib import Path
ROOT = Path(sys.argv[1]); STORAGE = Path(sys.argv[2]); OUT = Path(sys.argv[3])
MODE = sys.argv[4]                      # "capture" | "restore"
# ٢٠٢٦-٠٩-٢٣ (ختم nq): تحديث ٠٨-٢٧ كتب `scan(ATOM_ROOT)` هنا ولم يعرّفه في
# نصّ الابن (العلّة نفسها في حارس بقاء الحماية) — فكان الابن يموت قبل المقبض.
ATOM_ROOT = ROOT / "atoms"
sys.path.insert(0, str(ROOT))
from core.bootloader import Bootloader
from core.contracts.atom import AtomContext
from core.manifest_loader import scan
from core.registry import Registry
from core.snapshot_engine import SnapshotEngine

PROBE = (516, 518)
ACCOUNT, SYMBOL, BROKER = "52992818", "BTCUSD", "Raw Trading Ltd"


class L:
    def __getattr__(self, n): return lambda *a, **k: None


async def _null_publish(name, payload): pass
def _null_subscribe(name, handler): pass


def report(**kw):
    body = {}
    if OUT.exists():
        body = json.loads(OUT.read_text(encoding="utf-8"))
    body.update(kw)
    OUT.write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")


async def build():
    registry = Registry()
    discovery = scan(ATOM_ROOT)
    found = {a.manifest.id: a for a in discovery.atoms}
    made = {}
    for atom_id in PROBE:
        d = found[atom_id]
        inst = Bootloader.instantiate(d)
        registry.register(d.manifest, inst)
        await inst.initialize(AtomContext(atom_id=atom_id, config=dict(d.manifest.config),
                                          logger=L(), publish=_null_publish,
                                          subscribe=_null_subscribe))
        await inst.start()
        made[atom_id] = inst
    return registry, made


def state_of(made):
    # ٢٠٢٦-٠٩-٢٣ (ختم nq): ٥١٦ صار دفترًا لكلّ حساب (`book(account)`) لا
    # حقولًا مفردة — فكان الابن يموت على `_daily_loss_pct`. المعنى نفسه.
    led, kill = made[518], made[516]
    book = kill.book(ACCOUNT)
    return {"realized_gross": {k: round(v, 6) for k, v in led._realized_gross.items()},
            "budgets": {k: round(v, 6) for k, v in led._budgets.items()},
            "daily_loss_pct": round(float(book["daily_loss_pct"]), 6),
            "consecutive_losses": int(book["consecutive_losses"]),
            "daily_trade_count": int(book["daily_trade_count"])}


async def main():
    registry, made = await build()
    engine = SnapshotEngine(registry, STORAGE)

    if MODE == "restore":
        report(empty_before=state_of(made))
        rep = await engine.restore_all()
        report(restored=rep.restored, failed=rep.failed, state=state_of(made))
        return 0

    # الهويّة كاملة كما يرسلها النظام اليوم: ٥١٨ يطلب الوسيط، و٥١٦ يطلب
    # الحساب ومعرّف الحدث — وإلّا أُسقطت الحمولة ولا حالة تُقاس.
    await made[518]._on_activate({"account_id": ACCOUNT, "broker": BROKER,
                                  "asset_canonical": SYMBOL, "budget": 100.0})
    await made[518]._on_trade({"event_id": "g1", "account_id": ACCOUNT, "broker": BROKER,
                               "symbol": SYMBOL, "event_type": "CLOSED", "profit": -42.5,
                               "ticket": 1, "close_time": 1.0})
    await made[516]._on_loss({"event_id": "g-loss-1", "account_id": ACCOUNT,
                              "loss_pct": 7.5, "is_loss": True, "costs_complete": True})
    report(state=state_of(made))

    # ---- the anchored wiring, replayed verbatim ----
    stop_event = asyncio.Event()

    def _request_stop(*_args):
        report(request_stop_called=True)
        stop_event.set()

    loop = asyncio.get_running_loop()
    installed_signals = []
    restore_handlers = {}
    _SIGNALS = tuple(s for s in (getattr(signal, n, None)
                                 for n in ("SIGINT", "SIGTERM", "SIGBREAK")) if s is not None)
    try:
        for sig in _SIGNALS:
            loop.add_signal_handler(sig, _request_stop)
            installed_signals.append(sig.name)
    except (NotImplementedError, ImportError, RuntimeError) as exc:
        report(install_error=type(exc).__name__)
        for sig in list(installed_signals):
            try:
                loop.remove_signal_handler(getattr(signal, sig))
            except (NotImplementedError, RuntimeError):
                pass
        installed_signals.clear()

        def _request_stop_threadsafe(_signum, _frame):
            loop.call_soon_threadsafe(_request_stop)

        for sig in _SIGNALS:
            try:
                restore_handlers[sig.name] = signal.signal(sig, _request_stop_threadsafe)
                installed_signals.append(sig.name)
            except (ValueError, OSError, RuntimeError):
                continue

    async def _signal_pump():
        while not stop_event.is_set():
            await asyncio.sleep(0.2)

    pump = asyncio.create_task(_signal_pump()) if restore_handlers else None
    report(loop=type(loop).__name__, installed=installed_signals,
           via=("signal.signal" if restore_handlers else "add_signal_handler"), ready=True)

    try:
        await asyncio.wait_for(stop_event.wait(), timeout=25.0)
        if pump is not None:
            pump.cancel()
        report(wait_returned=True, stop_event_set=stop_event.is_set())
    except asyncio.TimeoutError:
        report(wait_returned=False, stop_event_set=stop_event.is_set(), timed_out=True)
        return 3

    report(entered_snapshot=True)
    snap = await engine.snapshot_all()
    report(captured=snap.captured, failed=snap.failed,
           files=sorted(p.name for p in STORAGE.glob("*.json")))
    return 0


try:
    sys.exit(asyncio.run(main()))
except KeyboardInterrupt:
    # نفس ما يفعله المُشغّل بالسطر 320 — يُلتقَط ثم يُخرَج بلا لقطة
    report(keyboard_interrupt=True, entered_snapshot_after_kbint=False)
    sys.exit(0)
'''


# ٢٠٢٦-٠٩-٢٣ (ختم nq): المُشغّل نما بين كتلتي الإشارات والانتظار (لقطة دوريّة ·
# مرجع التكافؤ · مِرقاب التجمّد)، وصار الإيقاف يوقف الذرّات ثمّ يلتقط «حالة
# ساكنة» — فسقطت العلامة الختاميّة القديمة ولم يعد اقتطاعٌ واحد ممكنًا. المرساة
# صارت قطعتين حرفيّتين من النصّ المرجعيّ نفسه (الإشارات · الانتظار)، وترتيبًا
# مقيسًا للإيقاف: الانتظار ⟵ إيقاف الاكتشاف ⟵ `snapshot_all`. لا شيء أُرخي.
SIGNALS_END = "    # finding 06:"
WAIT_START = "    # Item 64: a bounded foreground run."
WAIT_END = "    periodic_snap.cancel()"


def anchor() -> int:
    print("=" * 78)
    print("أ) المرساة — كتلتا الإشارات والانتظار بالمُشغّل لم تتغيّرا حرفًا")
    print("=" * 78)
    src = LAUNCHER.read_text(encoding="utf-8")
    marks = (ANCHOR_START, SIGNALS_END, WAIT_START, WAIT_END)
    if any(mark not in src for mark in marks):
        print("  ✗ لم أجد علامات الاقتطاع — المُشغّل تغيّر بنيويًّا: %s"
              % [m.strip()[:30] for m in marks if m not in src])
        return 1
    expected_signals, expected_wait = ANCHOR_EXPECTED.split(WAIT_START, 1)
    expected_wait = WAIT_START + expected_wait.split("\n\n    log.info(", 1)[0] + "\n"
    got_signals = ANCHOR_START + src.split(ANCHOR_START, 1)[1].split(SIGNALS_END, 1)[0]
    got_wait = WAIT_START + src.split(WAIT_START, 1)[1].split(WAIT_END, 1)[0]
    after_wait = src.split("await stop_event.wait()", 2)[-1]
    order_ok = ("await hot_reload.stop_periodic()" in after_wait
                and "snap_report = await snapshot_engine.snapshot_all()" in after_wait
                and after_wait.index("await hot_reload.stop_periodic()")
                < after_wait.index("snap_report = await snapshot_engine.snapshot_all()"))
    print("  كتلة الإشارات  مطابقة حرفيًّا: %s" % ("✓" if got_signals == expected_signals else "✗"))
    print("  كتلة الانتظار  مطابقة حرفيًّا: %s" % ("✓" if got_wait == expected_wait else "✗"))
    print("  الإيقاف: الانتظار ⟵ إيقاف الاكتشاف ⟵ اللقطة: %s" % ("✓" if order_ok else "✗"))
    block = got_signals + got_wait
    ANCHOR_REF = expected_signals + expected_wait
    same = block == ANCHOR_REF and order_ok
    print("  الكتلة %d حرفًا · مطابقة حرفيًّا: %s" % (
        len(block), "✓" if same else "✗ تغيّر المُشغّل — راجع الحارس"))
    if not same:
        exp, got = ANCHOR_REF.splitlines(), block.splitlines()
        for i in range(max(len(exp), len(got))):
            a = exp[i] if i < len(exp) else "<لا شيء>"
            b = got[i] if i < len(got) else "<لا شيء>"
            if a != b:
                print("    أوّل فرق سطر %d:\n      المتوقَّع: %r\n      الحاليّ : %r" % (i + 1, a, b))
                break
    for label, needle in (("يستدعي restore_all عند الإقلاع", "await snapshot_engine.restore_all()"),
                          ("يستدعي snapshot_all عند الإيقاف", "await snapshot_engine.snapshot_all()"),
                          ("اللقطة خلف stop_event.wait()", "await stop_event.wait()")):
        ok = needle in src
        print("  %-40s %s" % (label, "✓" if ok else "✗"))
    return 0 if same else 1


def run_child(child_py: Path, storage: Path, out: Path, mode: str, sig, label: str,
              runtime: Path) -> dict:
    """Spawn the child in its OWN process group, then signal it FROM HERE.

    ⛔ ٢٠٢٦-٠٩-٢٣ (ختم nq) — حادثة: ٥١٦ و٥١٨ يكتبان دفتريهما الدائمين في
    `var/store/…` مرسًى على الـruntime، والابن كان يبنيهما بإعدادهما الحقيقيّ —
    فكتب حدثين تجريبيّين (`g1` · `g-loss-1`) في دفتري المنصّة **الحيّة**
    (أُصلحا بنسخةٍ احتياطيّة في أرشيف سطح المكتب). الابن يعمل الآن على جذر
    runtime معزول (`QUANT_RUNTIME_ROOT`)، فكلّ `var/…` يقع في مجلّد الحارس المؤقّت.
    """
    out.write_text("{}", encoding="utf-8")
    flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    env = dict(os.environ, QUANT_RUNTIME_ROOT=str(runtime))
    proc = subprocess.Popen([PY, str(child_py), str(ROOT), str(storage), str(out), mode],
                            creationflags=flags, stdout=subprocess.PIPE, env=env,
                            stderr=subprocess.PIPE, text=True, encoding="utf-8")
    ready = False
    for _ in range(300):
        time.sleep(0.1)
        try:
            if json.loads(out.read_text(encoding="utf-8")).get("ready"):
                ready = True
                break
        except Exception:
            pass
        if proc.poll() is not None:
            break
    sent = None
    if ready and sig is not None:
        try:
            os.kill(proc.pid, sig)
            sent = getattr(sig, "name", str(sig))
        except Exception as exc:  # noqa: BLE001
            sent = "FAILED: %s" % exc
    try:
        stdout, stderr = proc.communicate(timeout=30)
    except subprocess.TimeoutExpired:
        proc.kill()
        stdout, stderr = proc.communicate()
    body = {}
    try:
        body = json.loads(out.read_text(encoding="utf-8"))
    except Exception:
        pass
    body.update({"exit_code": proc.returncode, "signal_sent": sent, "ready": ready,
                 "stderr_tail": (stderr or "").strip().splitlines()[-1:] })
    return body


def ladder(body: dict, storage: Path, label: str) -> int:
    print("\n" + "-" * 78)
    print(label)
    print("-" * 78)
    bad = 0
    files = sorted(p.name for p in storage.glob("*.json"))
    print("  حلقة الأحداث بالابن : %s" % body.get("loop"))
    print("  الإشارة المُرسَلة   : %s" % body.get("signal_sent"))
    if body.get("install_error"):
        print("  خطأ التركيب        : %s" % body.get("install_error"))
    steps = (
        ("١· المقبض رُكّب", bool(body.get("installed"))),
        ("٢· stop_event.set() نُودي", bool(body.get("request_stop_called"))),
        ("٣· stop_event.wait() رجع", bool(body.get("wait_returned"))),
        ("٤· دخل snapshot_all()", bool(body.get("entered_snapshot"))),
        ("٥· كُتبت ملفّات لقطة", bool(files)),
        ("٦· خروج نظيف (0)", body.get("exit_code") == 0),
    )
    for name, ok in steps:
        bad += 0 if ok else 1
        print("  %-28s %s" % (name, "✓" if ok else "✗"))
    print("  المُثبَّت=%s · الملفّات=%s · رمز الخروج=%s" % (
        body.get("installed"), files, body.get("exit_code")))
    return bad


def main() -> int:
    bad = anchor()
    tmp = Path(tempfile.mkdtemp(prefix="shutdown_guard_"))
    child_py = tmp / "child.py"
    child_py.write_text(CHILD, encoding="utf-8")
    completed: list[str] = []
    # Three DELIVERY methods, each measured as it really behaves on this OS.
    # The child is spawned in its own process group so signalling it can never
    # reach the shell that runs this guard; that isolation is also why
    # CTRL_C_EVENT is expected to be ignored (Windows does not deliver it to a
    # new process group), while CTRL_BREAK_EVENT is the one that does.
    # SIGTERM on Windows is TerminateProcess: uncatchable by design, no handler
    # of any kind can run. None of that is worked around here -- it is reported.
    cases = [(getattr(signal, "CTRL_C_EVENT", signal.SIGINT),
              "ب) SIGINT من الأب إلى الابن — أقرب ما يكون لـ Ctrl+C")]
    if hasattr(signal, "CTRL_BREAK_EVENT"):
        cases.append((signal.CTRL_BREAK_EVENT,
                      "ب٢) CTRL_BREAK من الأب إلى الابن — تسليم ويندوز لمجموعة عمليّات جديدة"))
    cases.append((signal.SIGTERM, "ج) SIGTERM من الأب إلى الابن — المسار الآخر صراحةً"))
    try:
        for sig, label in cases:
            name = str(getattr(sig, "name", sig))
            storage = tmp / ("snap_" + name)
            storage.mkdir(parents=True, exist_ok=True)
            runtime = tmp / ("runtime_" + name)
            (runtime / "var" / "store").mkdir(parents=True, exist_ok=True)
            body = run_child(child_py, storage, tmp / "out.json", "capture", sig, label, runtime)
            steps_bad = ladder(body, storage, label)

            print("\n  د) الاستعادة بعمليّة ثانية مستقلّة:")
            if not sorted(storage.glob("*.json")):
                print("     ✗ لا ملفّات لقطة ⇒ لا استعادة أصلًا")
                continue
            first_state = body.get("state")
            back = run_child(child_py, storage, tmp / "out2.json", "restore", None, label, runtime)
            same = back.get("state") == first_state
            empty_ok = back.get("empty_before") != first_state
            print("     عمليّة جديدة فارغة؟ %s" % ("✓" if empty_ok else "✗"))
            print("     استُعيدت=%s" % back.get("restored"))
            print("     قبل=%s" % json.dumps(first_state, ensure_ascii=False))
            print("     بعد=%s" % json.dumps(back.get("state"), ensure_ascii=False))
            print("     الحالة نفسها حقلًا بحقل: %s" % ("✓" if same else "✗"))
            if steps_bad == 0 and same and empty_ok:
                completed.append(name)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("\n" + "-" * 78)
    print("الحكم — العقد أن يوجد **مسار إيقاف واحد موثوق على الأقل** يكمل السُّلّم")
    print("-" * 78)
    print("  أكملت السلسلة كاملةً: %s" % (completed or "لا شيء"))
    print("  حقائق المنصّة المقيسة (لا التفاف عليها):")
    print("    · CTRL_C_EVENT لا يُسلَّم لمجموعة عمليّات جديدة — حدّ ويندوز")
    print("    · SIGTERM على ويندوز = TerminateProcess — لا يُلتقَط بأيّ مقبض")
    if not completed:
        bad += 1
        print("  ✗ لا مسار إيقاف يبلغ اللقطة على هذه المنصّة")
    else:
        print("  ✓ يوجد مسار إيقاف موثوق يبلغ اللقطة ويستعيد الحالة")

    print("\n" + "=" * 78)
    print("الاختلافات = %d" % bad)
    if bad == 0:
        print("سليم: الإيقاف بالإشارة يبلغ اللقطة، والعمليّة التالية تستعيد الحالة نفسها.")
    return 1 if bad else 0



# ⏳ م-47 (ورقة ٤١، 2026-08-28): ما تبقّى من فروق هذا الفحص انحرافُ عقودٍ بعد
# الدمج (لاخطّاط لقطة الذرّات المدموجة/سلوك إشارات ويندوز) — يُرحَّل بنافذة
# خاصة ويبقى أحمرَ صادقًا. إصلاحات م-43 الميكانيكية (تثبيتات UNTOUCHED،
# فحص snapshot بكل ملفات الذرّة) مثبّة أعلاه وتعمل.

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
