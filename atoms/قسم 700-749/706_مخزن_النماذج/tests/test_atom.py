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
    "_atom706", _Path(__file__).resolve().parents[1] / "atom.py")
_mod = _ilu.module_from_spec(_spec)
sys.modules["_atom706"] = _mod
_spec.loader.exec_module(_mod)
Atom = _mod.Atom
EVENT_PERSIST = _mod.EVENT_PERSIST_REQUESTED
EVENT_LOAD = _mod.EVENT_LOAD_REQUESTED
EVENT_LOAD_RESPONSE = _mod.EVENT_LOAD_RESPONSE
EVENT_PERSISTED = _mod.EVENT_PERSISTED


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
        task = getattr(self.atom, "_flush_now_task", None)
        if task is not None and not task.done() and task is not asyncio.current_task():
            await task

    def make_context(self, cfg):
        return AtomContext(atom_id=706, config=cfg, logger=_NullLogger(),
                           publish=self.publish, subscribe=self.subscribe)


def _tmp_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.unlink(path)
    return path


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


async def _make(bus, db_path, keep_versions=10):
    atom = Atom()
    await atom.initialize(bus.make_context(
        {"db_path": db_path, "keep_versions_per_model": keep_versions}))
    await atom.start()
    _LIVE.append(atom)
    return atom


async def test_persist_then_load():
    print("\n--- test_persist_then_load ---")
    db = _tmp_db()
    try:
        bus = FakeEventBus()
        await _make(bus, db)
        await bus.publish(EVENT_PERSIST, {"model_name": "trend", "version": "v1",
                                          "data": {"w": [1, 2, 3]}, "timestamp": 5.0})
        conf = [p for n, p in bus.published if n == EVENT_PERSISTED]
        assert conf and conf[-1]["version"] == "v1", conf
        await bus.publish(EVENT_LOAD, {"request_id": "q1", "model_name": "trend"})
        resp = [p for n, p in bus.published if n == EVENT_LOAD_RESPONSE][-1]
        assert resp["found"] and resp["data"] == {"w": [1, 2, 3]}, resp
        print(f"OK — خزّن النموذج ثم حمّله: version={resp['version']} data={resp['data']}")
    finally:
        await _shutdown()
        _cleanup(db)


async def test_load_missing():
    print("\n--- test_load_missing ---")
    db = _tmp_db()
    try:
        bus = FakeEventBus()
        await _make(bus, db)
        await bus.publish(EVENT_LOAD, {"request_id": "q2", "model_name": "ghost"})
        resp = [p for n, p in bus.published if n == EVENT_LOAD_RESPONSE][-1]
        assert resp["found"] is False, resp
        print("OK — نموذج غير موجود: found=False (بلا انهيار)")
    finally:
        await _shutdown()
        _cleanup(db)


async def test_keep_versions_prune():
    print("\n--- test_keep_versions_prune ---")
    db = _tmp_db()
    try:
        bus = FakeEventBus()
        await _make(bus, db, keep_versions=2)
        for v in ("v1", "v2", "v3"):
            await bus.publish(EVENT_PERSIST, {"model_name": "trend", "version": v,
                                              "data": {"v": v}, "timestamp": 1.0})
        conn = sqlite3.connect(db)
        try:
            versions = sorted(r[0] for r in conn.execute(
                "SELECT version FROM model_versions WHERE model_name='trend'").fetchall())
        finally:
            conn.close()
        assert versions == ["v2", "v3"], versions
        print(f"OK — احتفاظ بآخر N نسخة فقط (keep=2): {versions}")
    finally:
        await _shutdown()
        _cleanup(db)


async def test_latest_version_loaded():
    print("\n--- test_latest_version_loaded ---")
    db = _tmp_db()
    try:
        bus = FakeEventBus()
        await _make(bus, db)
        for v in ("v1", "v2"):
            await bus.publish(EVENT_PERSIST, {"model_name": "trend", "version": v,
                                              "data": {"v": v}, "timestamp": 1.0})
        await bus.publish(EVENT_LOAD, {"model_name": "trend"})
        resp = [p for n, p in bus.published if n == EVENT_LOAD_RESPONSE][-1]
        assert resp["version"] == "v2", resp
        print("OK — تحميل بلا تحديد نسخة يرجّع الأحدث (v2)")
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
            {"db_path": db, "keep_versions_per_model": 10}))
        assert (await atom.health_check()).state == HealthState.UNHEALTHY
        await atom.start()
        # جاهز بلا أي نشاط بعد = HEALTHY برسالة جاهزية صادقة (أمر المالك: لا تعثّر كاذب)
        ready = await atom.health_check()
        assert ready.state == HealthState.HEALTHY, ready
        assert "READY_AWAITING_FIRST_MODEL_SAVE" in ready.message, ready.message
        assert ready.details["saved"] == 0 and ready.details["loaded"] == 0, ready.details
        await bus.publish(EVENT_PERSIST, {"model_name": "m", "version": "v1",
                                          "data": {}})
        assert (await atom.health_check()).state == HealthState.HEALTHY
        print("OK — الصحة: UNHEALTHY -> HEALTHY (جاهز، صفر نشاط) -> HEALTHY (بعد الحفظ)")
    finally:
        await _shutdown()
        _cleanup(db)


async def main():
    tests = [test_persist_then_load, test_load_missing, test_keep_versions_prune,
             test_latest_version_loaded, test_health_states]
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
