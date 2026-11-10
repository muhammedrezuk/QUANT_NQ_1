import asyncio
import inspect
import os
import sqlite3
import sys
import tempfile

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from pathlib import Path as _Path
sys.path.insert(0, str(_Path(__file__).resolve().parents[4]))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.contracts.atom import AtomContext, HealthState  # noqa: E402
import importlib.util as _ilu  # noqa: E402

_spec = _ilu.spec_from_file_location(
    "_atom703", _Path(__file__).resolve().parents[1] / "atom.py")
_mod = _ilu.module_from_spec(_spec)
sys.modules["_atom703"] = _mod
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


class _NullLogger:
    def debug(self, *a): pass
    def info(self, *a): pass
    def warning(self, *a): pass
    def error(self, *a): pass
    def critical(self, *a): pass


class FakeEventBus:
    def __init__(self):
        self.published = []
        self._handlers = {}
        self.atom = None

    def subscribe(self, name, handler):
        self._handlers.setdefault(name, []).append(handler)
        # الذرّة تُعرِّف نفسها باشتراكها: معالجاتها توابعُ مربوطة فيها `__self__`.
        owner = getattr(handler, "__self__", None)
        if owner is not None:
            self.atom = owner

    async def publish(self, name, payload):
        self.published.append((name, payload))
        for h in self._handlers.get(name, []):
            r = h(payload)
            if inspect.isawaitable(r):
                await r
        # الكتابة لم تعد تُنتظَر في المعالج: تُنتظَر هنا، فيقف الانتظار مقام
        # دورة الحلقة. وأنّها خرجت من المعالج يُختبَر وحده بلا هذه المساعدة.
        # مهامّ «شغلةٌ واحدة تنتهي» التي تُجدوِلها الذرّة خارج مسار الحدث.
        # تُنتظَر بعد التسليم فيقف الانتظار مقام مرور الوقت — ولا تُنتظَر من
        # داخل إحداها (الدفعة تنشر فتعود إلى هنا، فتنتظر نفسها).
        current = asyncio.current_task()
        for _name in ("_flush_now_task", "_write_task", "_daily_task", "_clean_task"):
            task = getattr(self.atom, _name, None)
            if task is not None and not task.done() and task is not current:
                await task

    def make_context(self, cfg):
        return AtomContext(atom_id=703, config=cfg, logger=_NullLogger(),
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
            "SELECT account_id, symbol, side, volume, occurred_at FROM orders"
            " ORDER BY id").fetchall()
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


async def _make(bus, db_path, flush_size=1, retention_days=180):
    atom = Atom()
    await atom.initialize(bus.make_context(
        {"db_path": db_path, "flush_size": flush_size,
         "retention_days": retention_days}))
    await atom.start()
    _LIVE.append(atom)
    return atom


async def test_persists_order_with_account():
    print("\n--- test_persists_order_with_account ---")
    db = _tmp_db()
    try:
        bus = FakeEventBus()
        await _make(bus, db, flush_size=1)
        await bus.publish(EVENT_IN, {"account_id": "A1", "request_id": "r1", "symbol": "NQ100",
                                     "side": "BUY", "volume": 2.0, "timestamp": 5.0})
        rows = _rows(db)
        assert len(rows) == 1, rows
        assert rows[0] == ("A1", "NQ100", "BUY", 2.0, 5.0), rows[0]
        print(f"OK — خزّن الأمر مع account_id (قاعدة ٢٢): {rows[0]}")
    finally:
        await _shutdown()
        _cleanup(db)


async def test_account_isolation_query():
    print("\n--- test_account_isolation_query ---")
    db = _tmp_db()
    try:
        bus = FakeEventBus()
        await _make(bus, db, flush_size=1)
        await bus.publish(EVENT_IN, {"account_id": "A1", "request_id": "rA", "symbol": "NQ100", "side": "BUY"})
        await bus.publish(EVENT_IN, {"account_id": "A2", "request_id": "rB", "symbol": "NQ100", "side": "SELL"})
        conn = sqlite3.connect(db)
        try:
            a1 = conn.execute("SELECT side FROM orders WHERE account_id='A1'").fetchall()
            a2 = conn.execute("SELECT side FROM orders WHERE account_id='A2'").fetchall()
        finally:
            conn.close()
        assert a1 == [("BUY",)] and a2 == [("SELL",)], (a1, a2)
        print("OK — عزل الحسابات: كل حساب صفوفه لحاله (فلترة account_id)")
    finally:
        await _shutdown()
        _cleanup(db)


async def test_ignores_empty():
    print("\n--- test_ignores_empty ---")
    db = _tmp_db()
    try:
        bus = FakeEventBus()
        await _make(bus, db, flush_size=1)
        await bus.publish(EVENT_IN, {"side": "BUY"})
        assert _rows(db) == []
        print("OK — أمر بلا account_id ولا symbol اتجاهل")
    finally:
        await _shutdown()
        _cleanup(db)


async def test_prune_on_day():
    print("\n--- test_prune_on_day ---")
    db = _tmp_db()
    try:
        bus = FakeEventBus()
        await _make(bus, db, flush_size=1, retention_days=1)
        await bus.publish(EVENT_IN, {"account_id": "A1", "request_id": "old", "symbol": "NQ100",
                                     "timestamp": OLD_ROW})
        await bus.publish(EVENT_IN, {"account_id": "A1", "request_id": "new", "symbol": "NQ100",
                                     "timestamp": IN_WINDOW})
        await bus.publish(EVENT_DAY, {"official_time": DAY_PULSE_0300})
        assert len(_rows(db)) == 2, "نبض اليوم (03:00) شذّب خارج النافذة"
        await bus.publish(EVENT_PULSE, {"official_time": IN_WINDOW})
        remaining = _rows(db)
        assert len(remaining) == 1 and remaining[0][4] == IN_WINDOW, remaining
        print("OK — احتفاظ: حذف الأمر القديم، أبقى الحديث")
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
        # جاهز بلا أي أمر بعد = HEALTHY برسالة جاهزية صادقة (أمر المالك: لا تعثّر كاذب)
        ready = await atom.health_check()
        assert ready.state == HealthState.HEALTHY, ready
        assert "READY_AWAITING_FIRST_ORDER_STORE" in ready.message, ready.message
        assert ready.details["stored"] == 0, ready.details
        await bus.publish(EVENT_IN, {"account_id": "A1", "request_id": "health", "symbol": "NQ100"})
        assert (await atom.health_check()).state == HealthState.HEALTHY
        print("OK — الصحة: UNHEALTHY -> HEALTHY (جاهز، صفر مخزَّن) -> HEALTHY (مخزَّن)")
    finally:
        await _shutdown()
        _cleanup(db)


async def main():
    tests = [test_persists_order_with_account, test_account_isolation_query,
             test_ignores_empty, test_prune_on_day, test_health_states]
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
