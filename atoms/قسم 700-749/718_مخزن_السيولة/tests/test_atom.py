import asyncio
import inspect
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
    "_atom718", _Path(__file__).resolve().parents[1] / "atom.py")
_mod = _ilu.module_from_spec(_spec)
sys.modules["_atom718"] = _mod
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
_TABLE = "liquidity"


class _NullLogger:
    def debug(self, *a): pass
    def info(self, *a): pass
    def warning(self, *a): pass
    def error(self, *a): pass
    def critical(self, *a): pass


class FakeEventBus:
    """ناقل وهميّ ينادي المعالجات — وينتظر الدفعة المجدولة قبل أن يعود.

    منذ `2.3.0` لا تُنتظَر الكتابة داخل المعالج. الانتظار هنا يقف مقام دورة
    الحلقة: العقد يسأل «هل كُتب؟» لا «متى؟». وأنّها خرجت من المعالج يُختبَر
    وحده في `test_write_leaves_the_handler`، وهناك بلا هذه المساعدة.
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
        # فحمولة السيولة تُسلَّم لمعالج التخزين مباشرةً كي يبقى منطق المخزن مختبَرًا.
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

    def make_context(self, cfg):
        return AtomContext(atom_id=718, config=cfg, logger=_NullLogger(),
                           publish=self.publish, subscribe=self.subscribe)


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


# الذرّات الحيّة في الاختبار الجاري. الاتصال معمَّر منذ `2.3.0`، فالقاعدة
# تبقى ممسوكة حتى `stop()` — وعلى ويندوز لا يُحذف ملفٌّ ممسوك.
_LIVE: list = []


async def _make(bus, db_path, flush_size=1, retention_days=90):
    atom = Atom()
    await atom.initialize(bus.make_context(
        {"db_path": db_path, "flush_size": flush_size,
         "retention_days": retention_days}))
    await atom.start()
    _LIVE.append(atom)
    return atom


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


async def test_write_leaves_the_handler():
    """الكتابة لا تُنتظَر في معالج حدث.

    مقيس ٢٠٢٦-٠٩-١٦ من ثواني العامل (قاسه قسم التغذية): ٧١٨ يستهلك **٩٫٨٪
    من طاقة عاملٍ كامل بـ١٧٫٢ تسليمة/ث — ٥٫٧ م.ث للحدث** مقابل ٠٫٩٤ م.ث
    لذرّةٍ مجاورة. هنا تُبطَّأ الكتابة عمدًا: المعالج يجب أن يعود قبلها،
    والصفّ يجب أن يصل بعدها. لا مساعدة من الناقل: `bus.atom = None`.
    """
    print("\n--- test_write_leaves_the_handler ---")
    db = _tmp_db()
    try:
        bus = FakeEventBus()
        atom = await _make(bus, db, flush_size=1)
        bus.atom = None
        real = atom._flush

        def slow_flush():
            time.sleep(0.4)
            return real()

        atom._flush = slow_flush
        t0 = time.perf_counter()
        await bus.publish(EVENT_IN, {"symbol": "NQ100", "timestamp": 8.0})
        handler_ms = (time.perf_counter() - t0) * 1000
        assert handler_ms < 100, "المعالج انتظر الكتابة: %.0f ms" % handler_ms
        assert atom._flush_now_task is not None, "ما جُدولت الدفعة"
        await atom._flush_now_task
        assert _rows(db) == [("NQ100", 8.0)], _rows(db)
        print("OK — المعالج عاد في %.1f ms والكتابة جرت خلفه" % handler_ms)
    finally:
        await _shutdown()
        _cleanup(db)


async def test_connection_is_reused_not_reopened_per_write():
    """اتّصالٌ واحد معمَّر — لا اتّصالٌ جديد لكلّ كتابة.

    الكلفة ليست الاستعلام بل دورة نظام الملفات: إنشاء `-wal` و`-shm` ثمّ
    نقطة تفتيش ومحوهما عند كلّ إغلاق. مقيسة ٢٠٢٦-٠٩-٠٩ في ٧٠٧: **٣٣٫٥٣ م.ث
    باتّصالٍ جديد مقابل ٤٫٤٩ بمعمَّر**، وقاس قسم التغذية النمط نفسه في ٦٠١
    (**٧٫٥٥ مقابل ٠٫٠٤**). الحارس يعدّ فتحَ الاتصالات: ثلاث كتابات ⇒ فتحةٌ
    واحدة، والاتصال نفسه باقٍ بعدها.
    """
    print("\n--- test_connection_is_reused_not_reopened_per_write ---")
    db = _tmp_db()
    try:
        bus = FakeEventBus()
        atom = await _make(bus, db, flush_size=1)
        real_connect = atom._connect
        opens = {"n": 0}

        def counting_connect():
            opens["n"] += 1
            return real_connect()

        atom._connect = counting_connect
        for i in range(3):
            await bus.publish(EVENT_IN, {"symbol": "NQ100", "timestamp": float(i)})
        assert opens["n"] == 1, "فُتح اتّصال %d مرّة لثلاث كتابات" % opens["n"]
        assert atom._conn is not None, "الاتصال أُغلق بعد الكتابة"
        assert len(_rows(db)) == 3, _rows(db)
        print("OK — ثلاث كتابات بفتحةٍ واحدة، والاتصال باقٍ")
    finally:
        await _shutdown()
        _cleanup(db)


async def test_persists_symbol_fact():
    print("\n--- test_persists_symbol_fact ---")
    db = _tmp_db()
    try:
        bus = FakeEventBus()
        await _make(bus, db, flush_size=1)
        await bus.publish(EVENT_IN, {"symbol": "NQ100", "pool": "ABOVE", "timestamp": 8.0})
        rows = _rows(db)
        assert rows == [("NQ100", 8.0)], rows
        print(f"OK — خزّن السيولة (رمز + وقت + payload كامل): {rows[0]}")
    finally:
        await _shutdown()
        _cleanup(db)


async def test_ignores_without_symbol():
    print("\n--- test_ignores_without_symbol ---")
    db = _tmp_db()
    try:
        bus = FakeEventBus()
        await _make(bus, db, flush_size=1)
        await bus.publish(EVENT_IN, {"pool": "ABOVE"})
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
        await _make(bus, db, flush_size=1, retention_days=1)
        await bus.publish(EVENT_IN, {"symbol": "NQ100", "timestamp": OLD_ROW})
        await bus.publish(EVENT_IN, {"symbol": "NQ100", "timestamp": IN_WINDOW})
        await bus.publish(EVENT_DAY, {"official_time": DAY_PULSE_0300})
        assert len(_rows(db)) == 2, "نبض اليوم (03:00) شذّب خارج النافذة"
        await bus.publish(EVENT_PULSE, {"official_time": IN_WINDOW})
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
        assert (await atom.health_check()).state == HealthState.DEGRADED
        await bus.publish(EVENT_IN, {"symbol": "NQ100"})
        assert (await atom.health_check()).state == HealthState.HEALTHY
        print("OK — الصحة: UNHEALTHY -> DEGRADED -> HEALTHY")
    finally:
        await atom.stop()
        await _shutdown()
        _cleanup(db)


async def main():
    tests = [test_write_leaves_the_handler,
             test_connection_is_reused_not_reopened_per_write,
             test_persists_symbol_fact, test_ignores_without_symbol,
             test_prune_on_day, test_health_states]
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


async def test_no_subscription_to_archived_liquidity_event():
    """٢٠٢٦-١٠-٠٧ (ختم «NQ»): ناشر market.liquidity.updated أُرشف — فلا اشتراك فيه."""
    db = _tmp_db()
    try:
        bus = FakeEventBus()
        await _make(bus, db, flush_size=1)
        assert EVENT_IN not in bus._handlers
        assert EVENT_DAY in bus._handlers and _mod.EVENT_PULSE in bus._handlers
    finally:
        await _shutdown()
        _cleanup(db)
