import asyncio
import inspect
import json
import os
import sqlite3
import sys
import tempfile
import time

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from pathlib import Path as _Path
sys.path.insert(0, str(_Path(__file__).resolve().parents[4]))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.contracts.atom import AtomContext, HealthState  # noqa: E402
import importlib.util as _ilu  # noqa: E402

_spec = _ilu.spec_from_file_location(
    "_atom712", _Path(__file__).resolve().parents[1] / "atom.py")
_mod = _ilu.module_from_spec(_spec)
sys.modules["_atom712"] = _mod
_spec.loader.exec_module(_mod)
Atom = _mod.Atom
EVENT_IN = _mod.EVENT_IN
EVENT_DAY = _mod.EVENT_DAY
# ٢٠٢٦-١٠-٠٩ (ختم المالك «NQ» — الصيانة في استراحة السوق): التشذيب في نافذة الصيانة وحدها لا على
# نبض اليوم. الإثنين ٢٠٢٦-١٠-٠٥ منتصف ليل غرينتش = 03:00 بتوقيت الجهاز (نبض اليوم والسوق مفتوح)،
# وفي اليوم نفسه 17:30 نيويورك (21:30 غرينتش) داخل استراحة الوسيط.
EVENT_PULSE = "SYS_SECOND"
DAY_PULSE_0300 = 1_791_158_400.0
IN_WINDOW = 1_791_235_800.0
OLD_ROW = IN_WINDOW - 10 * 86_400.0
EVENT_OUT = _mod.EVENT_OUT
_TABLE = "analysis"


class _NullLogger:
    def debug(self, *a): pass
    def info(self, *a): pass
    def warning(self, *a): pass
    def error(self, *a): pass
    def critical(self, *a): pass


class FakeEventBus:
    """ناقل وهميّ ينادي المعالجات مباشرة — وينتظر دفعة الامتلاء قبل أن يعود.

    منذ `2.8.0` لا تُكتب دفعة الامتلاء داخل المعالج بل في مهمّة خلفيّة، كما
    خرجت الدورة الهادئة قبلها. فلو عاد `publish` هنا بلا انتظارٍ لأصبح كلّ
    اختبارٍ يقرأ القاعدة بعده سباقًا مع الجدولة. الانتظار هنا يقف مقام دورة
    الحلقة، لا أكثر: **أنّها خرجت من المعالج** يُختبَر وحده في
    `test_size_flush_leaves_the_handler`، وهناك بلا هذه المساعدة.
    """

    def __init__(self):
        self.published = []
        self._handlers = {}
        self.atom = None

    def subscribe(self, name, handler):
        self._handlers.setdefault(name, []).append(handler)
        owner = getattr(handler, "__self__", None)
        if owner is not None:
            self.atom = owner
            self._owner = owner  # لا يمسحه اختبارٌ يضع `bus.atom = None`

    async def publish(self, name, payload):
        self.published.append((name, payload))
        handlers = self._handlers.get(name, [])
        # ٢٠٢٦-١٠-٠٧ (ختم «NQ»): الذرّة لم تعد تشترك في `EVENT_IN` (ناشره أُرشف)،
        # فحمولة التحليل تُسلَّم لمعالج التخزين مباشرةً كي يبقى منطق المخزن مختبَرًا.
        owner = getattr(self, "_owner", None)
        if name == EVENT_IN and not handlers and owner is not None:
            handlers = [owner._on_event]
        for h in handlers:
            r = h(payload)
            if inspect.isawaitable(r):
                await r
        # مهامّ «شغلةٌ واحدة تنتهي» التي تُجدوِلها الذرّة خارج مسار الحدث.
        # تُنتظَر بعد التسليم فيقف الانتظار مقام مرور الوقت — ولا تُنتظَر من
        # داخل إحداها (الدفعة تنشر فتعود إلى هنا، فتنتظر نفسها).
        current = asyncio.current_task()
        for _name in ("_flush_now_task", "_write_task", "_daily_task", "_clean_task"):
            task = getattr(self.atom, _name, None)
            if task is not None and not task.done() and task is not current:
                await task

    def make_context(self, cfg, logger=None):
        return AtomContext(atom_id=712, config=cfg, logger=logger or _NullLogger(),
                           publish=self.publish, subscribe=self.subscribe)


class _RecordingLogger(_NullLogger):
    """يلتقط ما يُنطَق — العطل الصامت كان علّة ٢٠٢٦-٠٩-٠٧."""

    def __init__(self):
        self.errors = []

    def error(self, *a):
        self.errors.append(a)


def _break_database(path, atom=None):
    """يجعل الملف غير قاعدة — يسلك مسار ``except sqlite3.Error`` نفسه الذي
    سلكه التلف الحيّ (``database disk image is malformed``).

    ⚠️ ومنذ الاتّصال المعمَّر: الذرّة تمسك الملف، وعلى ويندوز لا يُحذف ملفٌّ
    ممسوك. فيُطرح اتّصالها أوّلًا — وهذا هو الواقع نفسه لا التفافٌ عليه:
    التلف يقع من خارج الذرّة، وأوّل ما تكتشفه هو **الكتابة التالية**. وذاك
    بالضبط ما يُختبَر بعد السطر: تُعلن غير جاهزة وتنطق ولا تبتلع.
    """
    if atom is not None:
        with atom._conn_lock:
            atom._close_connection()
    for suffix in ("-wal", "-shm", ""):
        target = path + suffix
        if os.path.exists(target):
            os.unlink(target)
    with open(path, "wb") as handle:
        handle.write(b"NOT-A-SQLITE-DATABASE" * 64)


def _tmp_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.unlink(path)
    return path


def _rows(db_path):
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute(
            "SELECT symbol, occurred_at FROM %s ORDER BY id" % _TABLE).fetchall()
    finally:
        conn.close()


# الذرّات الحيّة في الاختبار الجاري. الاتصال معمَّر، فالقاعدة تبقى ممسوكة حتى
# `stop()` — وعلى ويندوز لا يُحذف ملفٌّ ممسوك.
_LIVE: list = []


async def _shutdown():
    while _LIVE:
        atom = _LIVE.pop()
        try:
            await atom.stop()
        except Exception:  # noqa: BLE001 — التنظيف لا يُسقط اختبارًا
            pass


def _cleanup(db):
    for suffix in ("", "-wal", "-shm"):
        if os.path.exists(db + suffix):
            try:
                os.unlink(db + suffix)
            except OSError:
                pass


async def _make(bus, db_path, flush_size=1, retention_days=90):
    atom = Atom()
    await atom.initialize(bus.make_context(
        {"db_path": db_path, "flush_size": flush_size,
         "retention_days": retention_days}))
    await atom.start()
    _LIVE.append(atom)
    return atom


async def test_persists_symbol_fact():
    print("\n--- test_persists_symbol_fact ---")
    db = _tmp_db()
    try:
        bus = FakeEventBus()
        await _make(bus, db, flush_size=1)
        await bus.publish(EVENT_IN, {"symbol": "NQ100", "trend": "UP", "timestamp": 8.0})
        rows = _rows(db)
        assert rows == [("NQ100", 8.0)], rows
        print(f"OK — خزّن الحقيقة (رمز + وقت + payload كامل): {rows[0]}")
    finally:
        await _shutdown()
        _cleanup(db)


async def test_ignores_without_symbol():
    print("\n--- test_ignores_without_symbol ---")
    db = _tmp_db()
    try:
        bus = FakeEventBus()
        await _make(bus, db, flush_size=1)
        await bus.publish(EVENT_IN, {"trend": "UP"})
        assert _rows(db) == []
        print("OK — حدث بلا symbol اتجاهل")
    finally:
        await _shutdown()
        _cleanup(db)


async def test_prune_on_day():
    print("\n--- test_prune_on_day ---")
    db = _tmp_db()
    try:
        bus = FakeEventBus()
        atom = await _make(bus, db, flush_size=1, retention_days=1)
        await bus.publish(EVENT_IN, {"symbol": "NQ100", "timestamp": OLD_ROW})
        await bus.publish(EVENT_IN, {"symbol": "NQ100", "timestamp": IN_WINDOW})
        await bus.publish(EVENT_DAY, {"official_time": DAY_PULSE_0300})
        assert len(_rows(db)) == 2, "نبض اليوم (03:00) شذّب خارج النافذة"
        await bus.publish(EVENT_PULSE, {"official_time": IN_WINDOW})
        # الدورة الهادئة صارت خارج المعالج (VACUUM = ٢٥٢ ث مقابل ميزانية ٥٠ ms)
        await atom._daily_task
        remaining = _rows(db)
        assert len(remaining) == 1 and remaining[0][1] == IN_WINDOW, remaining
        print("OK — احتفاظ: حذف القديم أبقى الحديث")
    finally:
        await _shutdown()
        _cleanup(db)


async def test_health_states():
    print("\n--- test_health_states ---")
    db = _tmp_db()
    try:
        bus = FakeEventBus()
        atom = Atom()
        await atom.initialize(bus.make_context(
            {"db_path": db, "flush_size": 1, "retention_days": 0}))
        assert (await atom.health_check()).state == HealthState.UNHEALTHY
        await atom.start()
        _LIVE.append(atom)
        assert (await atom.health_check()).state == HealthState.DEGRADED
        await bus.publish(EVENT_IN, {"symbol": "NQ100"})
        assert (await atom.health_check()).state == HealthState.HEALTHY
        print("OK — الصحة: UNHEALTHY -> DEGRADED -> HEALTHY")
    finally:
        await _shutdown()
        _cleanup(db)


async def test_write_failure_marks_store_unready_and_speaks():
    print("\n--- test_write_failure_marks_store_unready_and_speaks ---")
    db = _tmp_db()
    try:
        bus = FakeEventBus()
        logger = _RecordingLogger()
        atom = Atom()
        await atom.initialize(bus.make_context(
            {"db_path": db, "flush_size": 1, "retention_days": 0}, logger=logger))
        await atom.start()
        _LIVE.append(atom)
        await bus.publish(EVENT_IN, {"symbol": "NQ100", "timestamp": 1.0})
        assert atom._store_ready is True
        _break_database(db, atom)
        await bus.publish(EVENT_IN, {"symbol": "NQ100", "timestamp": 2.0})
        assert atom._store_ready is False, "بقي المخزن «جاهزًا» بعد فشل كتابة"
        assert atom.store_failure_count >= 1, atom.store_failure_count
        assert logger.errors, "العطل ما وصل السجلّ — صمت كصمت ٠٩-٠٧"
        assert atom._buffer, "الصفّ الفاشل ضاع بدل أن يبقى في البفر"
        print(f"OK — فشل الكتابة: ready=False · فشل={atom.store_failure_count}"
              f" · نُطق في السجلّ ({len(logger.errors)})")
    finally:
        for suffix in ("", "-wal", "-shm"):
            if os.path.exists(db + suffix):
                os.unlink(db + suffix)


async def test_buffer_capped_by_bytes():
    print("\n--- test_buffer_capped_by_bytes ---")
    db = _tmp_db()
    original = _mod.MAX_BUFFER_BYTES
    _mod.MAX_BUFFER_BYTES = 20000
    try:
        bus = FakeEventBus()
        atom = await _make(bus, db, flush_size=100000)  # لا flush: البفر ينمو حرًّا
        big = "ط" * 2000
        for i in range(60):
            await bus.publish(EVENT_IN, {"symbol": "NQ100", "timestamp": float(i),
                                         "blob": big})
        assert atom._buffer_bytes <= _mod.MAX_BUFFER_BYTES, atom._buffer_bytes
        assert atom.dropped_count > 0, "السقف البايتي ما عضّ"
        recomputed = sum(atom._row_bytes(r) for r in atom._buffer)
        assert recomputed == atom._buffer_bytes, (recomputed, atom._buffer_bytes)
        print(f"OK — البفر محدود: {atom._buffer_bytes} بايت ≤ {_mod.MAX_BUFFER_BYTES}"
              f" · مُسقَط={atom.dropped_count} · محاسبة البايت مطابقة")
    finally:
        _mod.MAX_BUFFER_BYTES = original
        await _shutdown()
        _cleanup(db)


async def test_snapshot_is_bounded():
    print("\n--- test_snapshot_is_bounded ---")
    db = _tmp_db()
    original = _mod.SNAPSHOT_MAX_BYTES
    _mod.SNAPSHOT_MAX_BYTES = 20000
    try:
        bus = FakeEventBus()
        atom = await _make(bus, db, flush_size=100000)
        big = "ط" * 2000
        for i in range(60):
            await bus.publish(EVENT_IN, {"symbol": "NQ100", "timestamp": float(i),
                                         "blob": big})
        state = await atom.snapshot()
        wire = len(json.dumps(state, ensure_ascii=False, default=str).encode("utf-8"))
        assert state["snapshot_bytes"] <= _mod.SNAPSHOT_MAX_BYTES, state["snapshot_bytes"]
        assert state["snapshot_omitted"] > 0, "اللقطة أخذت البفر كلّه"
        assert len(state["buffer"]) < len(atom._buffer)
        # الأحدث هو ما يُحفظ: آخر صفّ في اللقطة = آخر صفّ في البفر (ثلاثيًّا —
        # ساعة الاستلام لا تُصدَّر)
        assert tuple(state["buffer"][-1]) == atom._buffer[-1][:3]
        assert all(len(row) == 3 for row in state["buffer"]), "اللقطة صدّرت ساعة الاستلام"
        twin = Atom()
        await twin.initialize(bus.make_context(
            {"db_path": db, "flush_size": 1, "retention_days": 0}))
        await twin.restore(state)
        assert len(twin._buffer) == len(state["buffer"])
        print(f"OK — اللقطة محدودة: {wire} بايت على السلك"
              f" · محذوف={state['snapshot_omitted']} · restore قبِلها")
    finally:
        _mod.SNAPSHOT_MAX_BYTES = original
        await _shutdown()
        _cleanup(db)


async def test_store_retry_is_throttled():
    print("\n--- test_store_retry_is_throttled ---")
    db = _tmp_db()
    try:
        bus = FakeEventBus()
        atom = await _make(bus, db, flush_size=1)
        await bus.publish(EVENT_IN, {"symbol": "NQ100", "timestamp": 1.0})
        _break_database(db, atom)
        await bus.publish(EVENT_IN, {"symbol": "NQ100", "timestamp": 2.0})
        assert atom._store_ready is False
        calls = {"n": 0}
        real = atom._ensure_store

        def counting():
            calls["n"] += 1
            return real()

        atom._ensure_store = counting
        for i in range(30):
            await bus.publish(EVENT_IN, {"symbol": "NQ100", "timestamp": 10.0 + i})
        assert calls["n"] == 0, f"فتح المخزن {calls['n']} مرّة رغم الخنق"
        assert atom.dropped_count >= 30, atom.dropped_count
        atom._store_retry_at = 0.0
        await bus.publish(EVENT_IN, {"symbol": "NQ100", "timestamp": 99.0})
        assert calls["n"] == 1, calls["n"]
        print(f"OK — الخنق: ٣٠ حدثًا بلا محاولة فتح، ثم محاولة واحدة"
              f" بعد انقضاء المهلة · مُسقَط={atom.dropped_count}")
    finally:
        for suffix in ("", "-wal", "-shm"):
            if os.path.exists(db + suffix):
                os.unlink(db + suffix)


async def test_recovers_after_store_repaired():
    print("\n--- test_recovers_after_store_repaired ---")
    db = _tmp_db()
    try:
        bus = FakeEventBus()
        atom = await _make(bus, db, flush_size=1)
        await bus.publish(EVENT_IN, {"symbol": "NQ100", "timestamp": 1.0})
        _break_database(db, atom)
        await bus.publish(EVENT_IN, {"symbol": "NQ100", "timestamp": 2.0})
        assert atom._store_ready is False
        # «الإصلاح»: القاعدة التالفة تُزاح وتُبنى نظيفة **تحت الذرّة وهي حيّة** —
        # فالمقصود أنّها تتعافى بلا إعادة تشغيل. لا `_shutdown()` هنا: إيقافها
        # يُثبت شيئًا آخر. واتّصالها مطروحٌ أصلًا منذ `_break_database`.
        _cleanup(db)
        atom._store_retry_at = 0.0
        await bus.publish(EVENT_IN, {"symbol": "NQ100", "timestamp": 3.0})
        assert atom._store_ready is True, "ما تعافى بعد إصلاح القاعدة"
        stamps = [row[1] for row in _rows(db)]
        assert 3.0 in stamps, stamps
        health = await atom.health_check()
        assert health.state == HealthState.HEALTHY, health.message
        print(f"OK — تعافى بلا إعادة تشغيل: صفوف={stamps} · صحّة={health.message}")
    finally:
        await _shutdown()
        _cleanup(db)


async def test_cap_moves_rows_to_archive_instead_of_destroying_them():
    """أمر المالك ٢٠٢٦-٠٩-١٠: ما يخرجه السقف يُرحَّل ولا يُتلف."""
    print("\n--- test_cap_moves_rows_to_archive_instead_of_destroying_them ---")
    db = _tmp_db()
    arch = db + ".archive.db"
    try:
        bus = FakeEventBus()
        atom = Atom()
        await atom.initialize(bus.make_context(
            {"db_path": db, "flush_size": 1, "retention_days": 0,
             "max_rows": 2, "archive_db_path": arch}))
        await atom.start()
        _LIVE.append(atom)
        for i in range(5):
            await bus.publish(EVENT_IN, {"symbol": "S%d" % i, "timestamp": float(i)})
        await atom._flush_and_report(None)
        left = {r[0] for r in _rows(db)}
        conn = sqlite3.connect(arch)
        try:
            moved = {r[0] for r in conn.execute("SELECT symbol FROM analysis")}
        finally:
            conn.close()
        assert moved, "ما رُحّل شيء رغم تجاوز السقف"
        assert left | moved == {"S0", "S1", "S2", "S3", "S4"}, (left, moved)
        assert not (left & moved), "صفّ في المخزن والأرشيف معًا"
        assert "S0" in moved, moved
        # ملاحظة: `_limit_state` لقطةُ آخر نداء لا مجموعَ الجولات — وهذا المخزن
        # ينادي الإنفاذ مع كل دفعة، فآخر نداء قد لا يجد ما يقصّ. الشاهد على
        # الترحيل هو محتوى الأرشيف نفسه أعلاه.
        assert len(moved) + len(left) == 5, (left, moved)
        await atom.stop()
        print(f"OK — بقي {sorted(left)} ورُحّل {sorted(moved)} · لا صفّ أُتلف")
    finally:
        for base in (db, arch):
            for suffix in ("", "-wal", "-shm"):
                if os.path.exists(base + suffix):
                    os.unlink(base + suffix)


async def test_archive_failure_blocks_destruction():
    """تعذُّر الأرشيف يوقف الإنفاذ — لا يُتلف صفٌّ لأنّ الأرشيف غاب."""
    print("\n--- test_archive_failure_blocks_destruction ---")
    db = _tmp_db()
    blocked = _tmp_db()
    try:
        with open(blocked, "wb") as handle:
            handle.write(b"NOT-A-SQLITE-DATABASE" * 64)
        bus = FakeEventBus()
        logger = _RecordingLogger()
        atom = Atom()
        await atom.initialize(bus.make_context(
            {"db_path": db, "flush_size": 1, "retention_days": 0,
             "max_rows": 2, "archive_db_path": blocked}, logger=logger))
        await atom.start()
        _LIVE.append(atom)
        for i in range(5):
            await bus.publish(EVENT_IN, {"symbol": "T%d" % i, "timestamp": float(i)})
        await atom._flush_and_report(None)
        assert len(_rows(db)) == 5, "أُتلفت صفوف رغم غياب الأرشيف"
        assert atom._limit_state.get("archive_error"), atom._limit_state
        assert logger.errors, "تعذُّر الأرشيف ما وصل السجلّ"
        await atom.stop()
        print(f"OK — الأرشيف متعذّر ⇒ بقيت الخمسة، والسبب منطوق:"
              f" {atom._limit_state.get('archive_error')[:44]}")
    finally:
        for base in (db, blocked):
            for suffix in ("", "-wal", "-shm"):
                if os.path.exists(base + suffix):
                    os.unlink(base + suffix)


async def test_shipped_config_destroys_and_does_not_archive():
    """حكم المالك ٢٠٢٦-٠٩-١٠: هذا المخزن **يُتلف** ولا يُرحّل.

    القدرة موجودة في الذرّة (الاختباران أعلاه يبرهنانها)، لكن المانيفست
    المسلَّم لا يفعّلها عمدًا: نموّ ~٢٫٢ جيجا/يوم ومحتوى لحظيّ يُعاد من
    السوق. هذا الاختبار يحرس القرار من تفعيلٍ عرضيّ لاحق.
    """
    print("\n--- test_shipped_config_destroys_and_does_not_archive ---")
    import yaml
    path = _Path(__file__).resolve().parents[1] / "manifest.yaml"
    cfg = yaml.safe_load(path.read_text(encoding="utf-8"))["config"]
    assert "archive_db_path" not in cfg, (
        "فُعِّل الترحيل في مانيفست ٧١٢ — وحكم المالك: إتلاف. "
        "إن كان بأمره الجديد فعدّل هذا الاختبار معه.")
    # والسلوك المقابل: بلا المفتاح، ما يخرجه السقف يُمحى ولا يُرحَّل
    db = _tmp_db()
    try:
        bus = FakeEventBus()
        atom = Atom()
        await atom.initialize(bus.make_context(
            {"db_path": db, "flush_size": 1, "retention_days": 0, "max_rows": 2}))
        await atom.start()
        _LIVE.append(atom)
        for i in range(5):
            await bus.publish(EVENT_IN, {"symbol": "D%d" % i, "timestamp": float(i)})
        await atom._flush_and_report(None)
        left = [r[0] for r in _rows(db)]
        assert len(left) == 2, left
        assert not atom._limit_state.get("archived"), atom._limit_state
        await atom.stop()
        print(f"OK — المانيفست المسلَّم بلا أرشيف · والسقف أتلف فبقي {left}")
    finally:
        for suffix in ("", "-wal", "-shm"):
            if os.path.exists(db + suffix):
                os.unlink(db + suffix)


async def test_daily_cycle_never_blocks_the_handler():
    """`VACUUM` لا يقع في مسار الحدث — مقيس ٢٥١٬٨٨٧ ms مقابل ميزانية ٥٠."""
    print("\n--- test_daily_cycle_never_blocks_the_handler ---")
    db = _tmp_db()
    try:
        bus = FakeEventBus()
        atom = await _make(bus, db, flush_size=1, retention_days=1)
        bus.atom = None  # لا انتظار من الناقل: المعالج وحده يُقاس
        await bus.publish(EVENT_IN, {"symbol": "NQ100", "timestamp": 1000.0})
        slow = {"ran": False}
        real = _mod.enforce_limits

        def slow_enforce(*a, **kw):
            if kw.get("shrink"):
                time.sleep(0.4)          # يمثّل VACUUM الطويل
                slow["ran"] = True
            return real(*a, **kw)

        _mod.enforce_limits = slow_enforce
        try:
            t0 = time.perf_counter()
            await bus.publish(EVENT_PULSE, {"official_time": IN_WINDOW})
            handler_ms = (time.perf_counter() - t0) * 1000
            assert handler_ms < 100, "المعالج انتظر الدورة: %.0f ms" % handler_ms
            assert atom._daily_task is not None, "ما جُدولت الدورة"
            await atom._daily_task
            assert slow["ran"], "الدورة ما جرت"
        finally:
            _mod.enforce_limits = real
        print(f"OK — المعالج عاد في {handler_ms:.1f} ms والدورة جرت خلفه")
    finally:
        await atom.stop()
        for suffix in ("", "-wal", "-shm"):
            if os.path.exists(db + suffix):
                os.unlink(db + suffix)


async def test_vacuum_gets_the_database_to_itself():
    """‏⛔ حارس الانحدار الذي قتل المنصّة ليلة ٢٠٢٦-٠٩-١٨.

    `2.9.0` عمَّر الاتّصال، و`enforce_limits` تفتح **اتّصالها الثاني**؛ وفي
    الدورة اليوميّة تُنادى بـ`shrink=True` أي **`VACUUM`** — وهو يطلب حصريّة
    القاعدة كلّها. فما دام مقبض الذرّة مفتوحًا لا ينالها:

        ٠٣:٠٠:٠٥  ٧١٢ معطّل: database is locked | analysis.db
        ٠٣:٠١:١٢  handler timeout subscriber=707
        … ثمّ صمتَ السجلّ ووقفت المنصّة ٠٣:٢٩

    ولم يكشفه اختبارٌ واحد من تسعة عشر، لأنّ أيًّا منها لم يُجرِ `VACUUM`
    **واتّصال الذرّة مفتوح**.

    ⚠️ **ولا يُقاس بأن ينجح `VACUUM` على قاعدةٍ صغيرة** — كتبتُه هكذا أوّلًا
    فنجت منه الطفرة: قاعدةٌ صغيرة وWAL فارغ يمضيان ولو بقي مقبضٌ مفتوح.
    يُقاس بالشرط الذي توثّقه `storage_policy` نصًّا — «`TRUNCATE` checkpoint
    يفشل ما دام للوحة قارئ دائم» — أي: **لا مقبض للذرّة لحظة النداء**.
    """
    print("\n--- test_vacuum_gets_the_database_to_itself ---")
    db = _tmp_db()
    try:
        bus = FakeEventBus()
        atom = await _make(bus, db, flush_size=1, retention_days=1)
        await bus.publish(EVENT_IN, {"symbol": "NQ100", "timestamp": 1000.0})

        seen = {}
        real = _mod.enforce_limits

        def watching(path, table, **kwargs):
            # اللحظة الحاسمة: أمقبضُ الذرّة مفتوحٌ بينما يعمل الإنفاذ؟
            seen[bool(kwargs.get("shrink"))] = atom._conn
            return real(path, table, **kwargs)

        _mod.enforce_limits = watching
        try:
            # المسار الساخن: حذفٌ فقط — يجوز بقاء الاتّصال، وهو المقصود.
            await asyncio.to_thread(atom._enforce_limits_exclusive, False)
            assert seen.get(False) is not None, \
                "المسار الساخن سلّم الاتّصال — فعاد فتحٌ وإغلاق لكلّ دورة"
            # الدورة الهادئة: `wal_checkpoint(TRUNCATE)` و`VACUUM` يطلبان
            # القاعدة لأنفسهما، و`storage_policy` توثّق أنّ القارئ الدائم
            # يُفشل `TRUNCATE`. فلا يجوز أن يبقى مقبضنا.
            await asyncio.to_thread(atom._enforce_limits_exclusive, True)
            assert True in seen, "الدورة الهادئة لم تُنادِ الإنفاذ أصلًا"
            assert seen[True] is None, \
                "‏⛔ الانحدار عاد: الاتّصال المعمَّر مفتوح أثناء VACUUM"
        finally:
            _mod.enforce_limits = real

        assert "locked" not in (atom._last_error or "").lower(), atom._last_error
        # وبعد الإنفاذ تعود الذرّة للكتابة بلا إعادة تشغيل: الاتّصال يُعاد فتحه.
        await bus.publish(EVENT_IN, {"symbol": "NQ100", "timestamp": 2000.0})
        assert len(_rows(db)) == 2, _rows(db)
        print("OK — الساخن يُبقي الاتّصال · الهادئ يسلّمه · والكتابة استأنفت")
    finally:
        await _shutdown()
        _cleanup(db)


async def test_size_flush_leaves_the_handler():
    """دفعة الامتلاء تخرج من المعالج كما خرجت الدورة الهادئة.

    مقيس ٢٠٢٦-٠٩-١٦ من عدّاد الناقل: ٧١٢ سجّل **٣٬٣٧٢ تجاوزًا لميزانية
    ٠٫٠٥ ث وأسوأ مدّة ٧٫٠٤ ثانية** — والسبب أنّ بلوغ الحجم كان يُنتظَر داخل
    المعالج. هنا تُبطَّأ الكتابة عمدًا: المعالج يجب أن يعود قبلها، والصفوف
    يجب أن تصل بعدها. لا مساعدة من الناقل الوهميّ: `bus.atom = None`.
    """
    print("\n--- test_size_flush_leaves_the_handler ---")
    db = _tmp_db()
    try:
        bus = FakeEventBus()
        atom = await _make(bus, db, flush_size=1, retention_days=1)
        bus.atom = None
        real = atom._flush

        def slow_flush():
            time.sleep(0.4)
            return real()

        atom._flush = slow_flush
        t0 = time.perf_counter()
        await bus.publish(EVENT_IN, {"symbol": "NQ100", "timestamp": 1000.0})
        handler_ms = (time.perf_counter() - t0) * 1000
        assert handler_ms < 100, "المعالج انتظر الدفعة: %.0f ms" % handler_ms
        assert atom._flush_now_task is not None, "ما جُدولت الدفعة"
        await atom._flush_now_task
        rows = _rows(db)
        assert len(rows) == 1, rows
        print("OK — المعالج عاد في %.1f ms والدفعة كُتبت خلفه: %s" % (handler_ms, rows))
    finally:
        await atom.stop()
        for suffix in ("", "-wal", "-shm"):
            if os.path.exists(db + suffix):
                os.unlink(db + suffix)


async def test_prune_uses_an_index_not_a_full_scan():
    print("\n--- test_prune_uses_an_index_not_a_full_scan ---")
    db = _tmp_db()
    try:
        bus = FakeEventBus()
        await _make(bus, db, flush_size=1, retention_days=1)
        await bus.publish(EVENT_IN, {"symbol": "NQ100", "timestamp": 1000.0})
        conn = sqlite3.connect(db)
        try:
            plan = " ".join(str(r[-1]) for r in conn.execute(
                "EXPLAIN QUERY PLAN " + _mod._PRUNE, (0.0,)))
        finally:
            conn.close()
        assert "SCAN" not in plan.upper(), "التشذيب يمسح الجدول كلّه: %s" % plan
        assert "idx_analysis_age" in plan, plan
        print(f"OK — خطّة التشذيب: {plan.strip()}")
    finally:
        await _shutdown()
        _cleanup(db)


async def test_rows_without_payload_stamp_are_still_pruned():
    print("\n--- test_rows_without_payload_stamp_are_still_pruned ---")
    db = _tmp_db()
    try:
        bus = FakeEventBus()
        atom = await _make(bus, db, flush_size=1, retention_days=1)
        # حدث بلا `timestamp` — مقيس ٢٠٢٦-٠٩-٠٩ أنّ ١٨٪ من صفوف القاعدة الحيّة
        # كذلك، وكانت لا تُشذَّب أبدًا فتتراكم إلى الأبد.
        await bus.publish(EVENT_IN, {"symbol": "NQ100", "trend": "UP"})
        rows = _rows(db)
        assert rows == [("NQ100", None)], rows
        conn = sqlite3.connect(db)
        try:
            recorded = conn.execute("SELECT recorded_at FROM analysis").fetchone()[0]
        finally:
            conn.close()
        assert recorded is not None, "ساعة الاستلام ما كُتبت"
        # يوم الاحتفاظ يمرّ: الصفّ بلا طابع حمولة يجب أن يسقط بساعة استلامه
        await bus.publish(EVENT_DAY, {"official_time": recorded + 2 * 86400.0})
        await atom._daily_task
        assert _rows(db) == [], "الصفّ بلا طابع نجا من التشذيب — يتراكم أبدًا"
        print(f"OK — صفّ بلا timestamp: recorded_at={recorded:.0f}"
              f" وشُذّب بساعة الاستلام")
    finally:
        await _shutdown()
        _cleanup(db)


async def test_buffer_drops_by_receive_clock_not_payload_stamp():
    print("\n--- test_buffer_drops_by_receive_clock_not_payload_stamp ---")
    db = _tmp_db()
    try:
        bus = FakeEventBus()
        atom = await _make(bus, db, flush_size=100000)
        # طابع حمولة قديم بعشر سنوات — ساعة الوسيط لا تقصّ شيئًا
        for i in range(5):
            await bus.publish(EVENT_IN, {"symbol": "NQ100", "timestamp": 1.0 + i})
        atom._trim_buffer()
        assert len(atom._buffer) == 5, "قصّ بطابع الحمولة — والطابع ليس ساعتنا"
        assert atom.dropped_count == 0, atom.dropped_count
        # ساعة الاستلام المحلّية هي التي تقصّ
        aged = [row[:4] + (row[4] - (_mod.BUFFER_MAX_AGE_S + 1.0),)
                for row in atom._buffer[:3]]
        atom._buffer = aged + atom._buffer[3:]
        atom._trim_buffer()
        assert len(atom._buffer) == 2, len(atom._buffer)
        assert atom.dropped_count == 3, atom.dropped_count
        recomputed = sum(atom._row_bytes(r) for r in atom._buffer)
        assert recomputed == atom._buffer_bytes, (recomputed, atom._buffer_bytes)
        print(f"OK — الزمن يقصّ بساعة الاستلام: بقي {len(atom._buffer)}"
              f" · مُسقَط={atom.dropped_count} · طابع الحمولة لا أثر له")
    finally:
        await _shutdown()
        _cleanup(db)


async def test_restore_trims_inherited_giant_snapshot():
    print("\n--- test_restore_trims_inherited_giant_snapshot ---")
    db = _tmp_db()
    original = _mod.MAX_BUFFER_BYTES
    _mod.MAX_BUFFER_BYTES = 40000
    try:
        bus = FakeEventBus()
        atom = Atom()
        await atom.initialize(bus.make_context(
            {"db_path": db, "flush_size": 1, "retention_days": 0}))
        # لقطة موروثة بالشكل القديم (ثلاثي) وأضخم من السقف بكثير
        giant = [["NQ100", float(i), "ط" * 2000] for i in range(200)]
        await atom.restore({"buffer": giant, "stored_count": 7, "dropped_count": 0})
        assert atom._buffer_bytes <= _mod.MAX_BUFFER_BYTES, atom._buffer_bytes
        assert len(atom._buffer) < len(giant), len(atom._buffer)
        assert all(len(row) == 5 for row in atom._buffer), "ما اختُتمت ساعتا الاستلام"
        assert atom.stored_count == 7
        print(f"OK — لقطة موروثة قُصّت عند الاستعادة: {len(giant)} ← "
              f"{len(atom._buffer)} صفّ · {atom._buffer_bytes} بايت")
    finally:
        _mod.MAX_BUFFER_BYTES = original
        await _shutdown()
        _cleanup(db)


async def test_snapshot_size_at_measured_row_size():
    print("\n--- test_snapshot_size_at_measured_row_size ---")
    db = _tmp_db()
    try:
        bus = FakeEventBus()
        atom = await _make(bus, db, flush_size=100000)
        # صفّ التحليل المقيس ٢٠٢٦-٠٨-١٨ = ٢٨ كيلوبايت
        blob = "ط" * 28000
        for i in range(400):
            await bus.publish(EVENT_IN, {"symbol": "NQ100", "timestamp": float(i),
                                         "blob": blob})
        state = await atom.snapshot()
        wire = len(json.dumps(state, ensure_ascii=False, default=str).encode("utf-8"))
        assert wire <= 4 * 1024 * 1024, wire
        print(f"OK — بصفّ ٢٨ ك.ب و{len(atom._buffer)} صفًّا في البفر:"
              f" اللقطة على السلك = {wire/1048576:.2f} م.ب"
              f" (محذوف={state['snapshot_omitted']})")
    finally:
        await _shutdown()
        _cleanup(db)


async def main():
    tests = [test_persists_symbol_fact, test_ignores_without_symbol,
             test_prune_on_day, test_health_states,
             test_write_failure_marks_store_unready_and_speaks,
             test_buffer_capped_by_bytes, test_snapshot_is_bounded,
             test_store_retry_is_throttled, test_recovers_after_store_repaired,
             test_cap_moves_rows_to_archive_instead_of_destroying_them,
             test_archive_failure_blocks_destruction,
             test_shipped_config_destroys_and_does_not_archive,
             test_daily_cycle_never_blocks_the_handler,
             test_vacuum_gets_the_database_to_itself,
             test_size_flush_leaves_the_handler,
             test_prune_uses_an_index_not_a_full_scan,
             test_rows_without_payload_stamp_are_still_pruned,
             test_buffer_drops_by_receive_clock_not_payload_stamp,
             test_restore_trims_inherited_giant_snapshot,
             test_snapshot_size_at_measured_row_size]
    failed = []
    for t in tests:
        try:
            await t()
        except AssertionError as e:
            failed.append((t.__name__, str(e))); print(f"FAILED: {t.__name__}: {e}")
        except Exception as e:
            failed.append((t.__name__, repr(e))); print(f"ERROR: {t.__name__}: {e!r}")
    print("\n" + "=" * 60)
    if failed:
        print(f"فشل {len(failed)} من أصل {len(tests)}"); sys.exit(1)
    print(f"نجح كل الاختبارات ({len(tests)}/{len(tests)})")


if __name__ == "__main__":
    asyncio.run(main())


async def test_no_subscription_to_archived_analysis_event():
    """٢٠٢٦-١٠-٠٧ (ختم «NQ»): ناشر analysis.raw.completed أُرشف — فلا اشتراك فيه."""
    db = _tmp_db()
    try:
        bus = FakeEventBus()
        await _make(bus, db, flush_size=1)
        assert EVENT_IN not in bus._handlers
        assert EVENT_DAY in bus._handlers and _mod.EVENT_PULSE in bus._handlers
    finally:
        await _shutdown()
        _cleanup(db)
