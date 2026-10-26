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
    "_atom701", _Path(__file__).resolve().parents[1] / "atom.py")
_mod = _ilu.module_from_spec(_spec)
sys.modules["_atom701"] = _mod
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
        return AtomContext(atom_id=701, config=cfg, logger=_NullLogger(),
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
            "SELECT symbol, provider, bid, ask, occurred_at FROM market_data"
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


async def _make(bus, db_path, flush_size=1, retention_days=30):
    atom = Atom()
    await atom.initialize(bus.make_context(
        {"db_path": db_path, "flush_size": flush_size,
         "retention_days": retention_days}))
    await atom.start()
    _LIVE.append(atom)
    return atom


async def test_persists_price_to_disk():
    print("\n--- test_persists_price_to_disk ---")
    db = _tmp_db()
    try:
        bus = FakeEventBus()
        await _make(bus, db, flush_size=1)
        await bus.publish(EVENT_IN, {"symbol": "NQ100", "bid": 100.0, "ask": 100.5,
                                     "timestamp": 7.0, "provider": "MT5"})
        rows = _rows(db)
        assert len(rows) == 1, rows
        assert rows[0] == ("NQ100", "MT5", 100.0, 100.5, 7.0), rows[0]
        out = [p for n, p in bus.published if n == EVENT_OUT]
        assert out and out[-1]["rows"] == 1 and out[-1]["total"] == 1
        print(f"OK — كتب على القرص فعلاً: {rows[0]} · receipt={out[-1]}")
    finally:
        await _shutdown()
        _cleanup(db)


async def test_buffers_until_flush_size():
    print("\n--- test_buffers_until_flush_size ---")
    db = _tmp_db()
    try:
        bus = FakeEventBus()
        await _make(bus, db, flush_size=3)
        for i in range(2):
            await bus.publish(EVENT_IN, {"symbol": "NQ100", "bid": i, "ask": i})
        assert _rows(db) == [], "should still be buffered"
        await bus.publish(EVENT_IN, {"symbol": "NQ100", "bid": 2, "ask": 2})
        assert len(_rows(db)) == 3, "flush at size"
        print("OK — يخزّن بالدفعة (buffer) وينزل عند حجم الدفعة")
    finally:
        await _shutdown()
        _cleanup(db)


async def test_ignores_without_symbol():
    print("\n--- test_ignores_without_symbol ---")
    db = _tmp_db()
    try:
        bus = FakeEventBus()
        await _make(bus, db, flush_size=1)
        await bus.publish(EVENT_IN, {"bid": 1, "ask": 2})
        assert _rows(db) == []
        assert not [p for n, p in bus.published if n == EVENT_OUT]
        print("OK — سعر بلا symbol اتجاهل")
    finally:
        await _shutdown()
        _cleanup(db)


async def test_prune_on_day():
    print("\n--- test_prune_on_day ---")
    db = _tmp_db()
    try:
        bus = FakeEventBus()
        await _make(bus, db, flush_size=1, retention_days=1)
        await bus.publish(EVENT_IN, {"symbol": "NQ100", "bid": 1, "ask": 2,
                                     "timestamp": OLD_ROW})
        await bus.publish(EVENT_IN, {"symbol": "NQ100", "bid": 3, "ask": 4,
                                     "timestamp": IN_WINDOW})
        assert len(_rows(db)) == 2
        await bus.publish(EVENT_DAY, {"official_time": DAY_PULSE_0300})
        assert len(_rows(db)) == 2, "نبض اليوم (03:00) شذّب خارج النافذة"
        await bus.publish(EVENT_PULSE, {"official_time": IN_WINDOW})
        remaining = _rows(db)
        assert len(remaining) == 1 and remaining[0][4] == IN_WINDOW, remaining
        pruned = [p for n, p in bus.published if n == EVENT_OUT][-1]["pruned"]
        assert pruned == 1, pruned
        print(f"OK — احتفاظ (retention): حذف القديم، أبقى الحديث · pruned={pruned}")
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
        h = await atom.health_check()
        assert h.state == HealthState.UNHEALTHY, "not started -> UNHEALTHY"
        await atom.start()
        h = await atom.health_check()
        assert h.state == HealthState.DEGRADED, "started, nothing stored -> DEGRADED"
        await bus.publish(EVENT_IN, {"symbol": "NQ100", "bid": 1, "ask": 2})
        h = await atom.health_check()
        assert h.state == HealthState.HEALTHY, "after store -> HEALTHY"
        print("OK — الصحة: UNHEALTHY -> DEGRADED -> HEALTHY")
    finally:
        await _shutdown()
        _cleanup(db)


async def main():
    tests = [test_persists_price_to_disk, test_buffers_until_flush_size,
             test_ignores_without_symbol, test_prune_on_day, test_health_states]
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
