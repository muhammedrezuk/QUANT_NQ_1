import asyncio
import inspect
import os
import sqlite3
import sys
import tempfile
import time

import yaml

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from pathlib import Path as _Path
sys.path.insert(0, str(_Path(__file__).resolve().parents[4]))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.contracts.atom import AtomContext, HealthState  # noqa: E402
import importlib.util as _ilu  # noqa: E402

_spec = _ilu.spec_from_file_location(
    "_atom704", _Path(__file__).resolve().parents[1] / "atom.py")
_mod = _ilu.module_from_spec(_spec)
sys.modules["_atom704"] = _mod
_spec.loader.exec_module(_mod)
Atom = _mod.Atom
EVENT_DAY = _mod.EVENT_DAY
# ٢٠٢٦-١٠-٠٩ (ختم المالك «NQ» — الصيانة في استراحة السوق): التشذيب في نافذة الصيانة وحدها لا على
# نبض اليوم. الإثنين ٢٠٢٦-١٠-٠٥ منتصف ليل غرينتش = 03:00 بتوقيت الجهاز (نبض اليوم والسوق مفتوح)،
# وفي اليوم نفسه 17:30 نيويورك (21:30 غرينتش) داخل استراحة الوسيط.
EVENT_PULSE = "SYS_SECOND"
DAY_PULSE_0300 = 1_791_158_400.0
IN_WINDOW = 1_791_235_800.0
OLD_ROW = IN_WINDOW - 10 * 86_400.0
EVENT_OUT = _mod.EVENT_OUT

_WATCH = ["platform.trade_event", "execution.order.rejected", "emergency.halt"]


class _NullLogger:
    def debug(self, *a): pass
    def info(self, *a): pass
    def warning(self, *a): pass
    def error(self, *a): pass
    def critical(self, *a): pass


class _RecordingLogger(_NullLogger):
    """يلتقط ما يُنطَق — انحراف الساعة لا يُصحَّح، لكنّه لا يُبتلع."""

    def __init__(self):
        self.warnings = []

    def warning(self, *a):
        self.warnings.append(a)

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

    def make_context(self, cfg, logger=None):
        return AtomContext(atom_id=704, config=cfg, logger=logger or _NullLogger(),
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
            "SELECT event_name, account_id, symbol, occurred_at FROM timeline"
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


async def _make(bus, db_path, flush_size=1, retention_days=90):
    atom = Atom()
    await atom.initialize(bus.make_context(
        {"db_path": db_path, "watch_events": _WATCH,
         "flush_size": flush_size, "retention_days": retention_days}))
    await atom.start()
    _LIVE.append(atom)
    return atom


async def test_records_named_events():
    print("\n--- test_records_named_events ---")
    db = _tmp_db()
    try:
        bus = FakeEventBus()
        await _make(bus, db, flush_size=1)
        await bus.publish("platform.trade_event",
                          {"account_id": "A1", "symbol": "NQ100", "timestamp": 9.0})
        await bus.publish("emergency.halt", {"reason": "test"})
        rows = _rows(db)
        assert len(rows) == 2, rows
        assert rows[0] == ("platform.trade_event", "A1", "NQ100", 9.0), rows[0]
        assert rows[1][0] == "emergency.halt" and rows[1][1] is None, rows[1]
        print(f"OK — سجّل الأحداث باسمها + account_id لمّا يوجد: {rows}")
    finally:
        await _shutdown()
        _cleanup(db)


async def test_only_watched_events():
    print("\n--- test_only_watched_events ---")
    db = _tmp_db()
    try:
        bus = FakeEventBus()
        await _make(bus, db, flush_size=1)
        await bus.publish("some.random.event", {"symbol": "X"})
        assert _rows(db) == [], "unwatched event must not be recorded"
        print("OK — حدث خارج قائمة المراقبة ما انسجّل")
    finally:
        await _shutdown()
        _cleanup(db)


async def test_prune_on_day():
    print("\n--- test_prune_on_day ---")
    db = _tmp_db()
    try:
        bus = FakeEventBus()
        await _make(bus, db, flush_size=1, retention_days=1)
        await bus.publish("execution.order.rejected", {"symbol": "NQ100", "timestamp": OLD_ROW})
        await bus.publish("execution.order.rejected", {"symbol": "NQ100", "timestamp": IN_WINDOW})
        await bus.publish(EVENT_DAY, {"official_time": DAY_PULSE_0300})
        assert len(_rows(db)) == 2, "نبض اليوم (03:00) شذّب خارج النافذة"
        await bus.publish(EVENT_PULSE, {"official_time": IN_WINDOW})
        remaining = _rows(db)
        assert len(remaining) == 1 and remaining[0][3] == IN_WINDOW, remaining
        stat = [p for n, p in bus.published if n == EVENT_OUT][-1]
        assert stat["pruned"] == 1, stat
        print(f"OK — احتفاظ + تقرير يومي: {stat}")
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
            {"db_path": db, "watch_events": _WATCH, "flush_size": 1,
             "retention_days": 0}))
        assert (await atom.health_check()).state == HealthState.UNHEALTHY
        await atom.start()
        assert (await atom.health_check()).state == HealthState.DEGRADED
        await bus.publish("platform.trade_event", {"symbol": "NQ100"})
        assert (await atom.health_check()).state == HealthState.HEALTHY
        print("OK — الصحة: UNHEALTHY -> DEGRADED -> HEALTHY")
    finally:
        await _shutdown()
        _cleanup(db)


async def test_manifest_subscribes_matches_runtime_watch_events():
    """v5.1.0: manifest.yaml's declarative `subscribes:` and the atom's
    OWN `config.watch_events` are two hand-maintained lists in the same
    file -- nothing kept them in sync. Found drifted both ways: 4 names
    declared subscribed but never actually watched (dead declarations --
    events a debugger would wrongly expect to find recorded here), and 6
    real subscriptions (driven by watch_events) invisible to anything
    reading only `subscribes:` (dependency graphs, impact analysis)."""
    print("\n--- test_manifest_subscribes_matches_runtime_watch_events ---")
    manifest_path = _Path(__file__).resolve().parents[1] / "manifest.yaml"
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    declared = set(manifest["subscribes"])
    runtime = set(manifest["config"]["watch_events"]) | {_mod.EVENT_DAY, _mod.EVENT_PULSE}
    assert declared == runtime, {
        "declared_but_not_watched": sorted(declared - runtime),
        "watched_but_not_declared": sorted(runtime - declared)}
    print(f"OK — manifest.subscribes يطابق watch_events+{{{_mod.EVENT_DAY},{_mod.EVENT_PULSE}}} حرفياً ({len(declared)})")


async def test_archived_validation_failures_not_watched():
    """٢٠٢٦-١٠-٠٧ (ختم «NQ»): ناشرا فشل التحقّق في البنية والسيولة أُرشفا — فلا يُسمعان."""
    manifest_path = _Path(__file__).resolve().parents[1] / "manifest.yaml"
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    for dropped in ("structure.validation_failed", "liquidity.validation_failed"):
        assert dropped not in manifest["subscribes"], dropped
        assert dropped not in manifest["config"]["watch_events"], dropped
    assert "market_data.validation_failed" in manifest["config"]["watch_events"]


async def test_recorded_at_written_and_drift_spoken():
    """ساعة الاستلام تُكتب، والطابع المستقبليّ يُنطق ولا يُصحَّح."""
    print("\n--- test_recorded_at_written_and_drift_spoken ---")
    db = _tmp_db()
    logger = _RecordingLogger()
    try:
        bus = FakeEventBus()
        atom = Atom()
        await atom.initialize(bus.make_context(
            {"db_path": db, "flush_size": 1, "retention_days": 0,
             "watch_events": ["platform.trade_event"]}, logger=logger))
        await atom.start()
        future = time.time() + 10190.0
        await bus.publish("platform.trade_event",
                          {"symbol": "EURUSD", "timestamp": future,
                           "account_id": "A1"})
        conn = sqlite3.connect(db)
        try:
            occ, rec = conn.execute(
                "SELECT occurred_at, recorded_at FROM timeline").fetchone()
        finally:
            conn.close()
        assert abs(occ - future) < 1, "الطابع صُحِّح — والتصحيح تخمين"
        assert rec is not None and abs(rec - time.time()) < 60, rec
        assert atom.future_stamp_count == 1, atom.future_stamp_count
        assert logger.warnings, "الانحراف ما وصل السجلّ"
        # والتشذيب يعمل بساعة الاستلام لا بطابع الحمولة
        conn = sqlite3.connect(db)
        try:
            plan = " ".join(str(r[-1]) for r in conn.execute(
                "EXPLAIN QUERY PLAN " + _mod._PRUNE, (0.0,)))
        finally:
            conn.close()
        assert "SCAN" not in plan.upper(), "التشذيب يمسح الجدول كلّه: %s" % plan
        assert "idx_timeline_age" in plan, plan
        await atom.stop()
        print(f"OK — occurred_at كما جاء · recorded_at بساعتنا · نُطق"
              f" · خطّة التشذيب: {plan.strip()}")
    finally:
        for suffix in ("", "-wal", "-shm"):
            if os.path.exists(db + suffix):
                os.unlink(db + suffix)


async def main():
    tests = [test_recorded_at_written_and_drift_spoken, test_records_named_events, test_only_watched_events,
             test_prune_on_day, test_health_states,
             test_manifest_subscribes_matches_runtime_watch_events]
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
