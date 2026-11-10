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
    "_atom714", _Path(__file__).resolve().parents[1] / "atom.py")
_mod = _ilu.module_from_spec(_spec)
sys.modules["_atom714"] = _mod
_spec.loader.exec_module(_mod)
Atom = _mod.Atom
EVENT_DAY = _mod.EVENT_DAY
EVENT_OUT = _mod.EVENT_OUT
EVENT_PULSE = _mod.EVENT_PULSE

# ٢٠٢٦-١٠-٠٩ (ختم المالك «NQ» — الصيانة في استراحة السوق): الأرشفة في نافذة الصيانة وحدها.
# الإثنين ٢٠٢٦-١٠-٠٥ 17:30 بتوقيت نيويورك (21:30 غرينتش) داخل استراحة الوسيط اليوميّة.
IN_WINDOW = 1_791_235_800.0
DAY_S = 86_400.0
# الخميس ٢٠٢٦-١٠-٠٨ منتصف ليل غرينتش = 03:00 بتوقيت الجهاز — موعد نبض اليوم والسوق مفتوح.
DAY_PULSE_0300 = 1_791_417_600.0
# صفوفٌ قديمة (أقدم من يومٍ قبل النافذة) وحديثة (بعدها) — بدل 100/200/9,000,000 حول 1,000,000.
OLD_A, OLD_B = IN_WINDOW - 9 * DAY_S, IN_WINDOW - 8 * DAY_S
RECENT = IN_WINDOW + 3600.0


class _NullLogger:
    def debug(self, *a): pass
    def info(self, *a): pass
    def warning(self, *a): pass
    def error(self, *a): pass
    def critical(self, *a): pass


class FakeEventBus:
    """ناقل وهميّ ينادي المعالجات مباشرة — وينتظر الأرشفة المجدولة قبل أن يعود.

    منذ `3.3.0` لا تُنتظَر الأرشفة داخل المعالج بل تُجدوَل في مهمّة خلفيّة
    (كانت أسوأ مدّة معالجٍ في المنصّة: ٣٠٫٠١ ثانية). الانتظار هنا يقف مقام
    دورة الحلقة، لا أكثر: **أنّها خرجت من المعالج** يُختبَر وحده في
    `test_archive_leaves_the_handler`، وهناك بلا هذه المساعدة.
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

    async def publish(self, name, payload):
        self.published.append((name, payload))
        for h in self._handlers.get(name, []):
            r = h(payload)
            if inspect.isawaitable(r):
                await r
        atom = self.atom
        task = getattr(atom, "_archive_task", None) if atom is not None else None
        # الأرشفة نفسها تنشر تقريرها فتعود إلى هنا: لا تُنتظَر من داخلها.
        if task is not None and not task.done() and task is not asyncio.current_task():
            await task

    def make_context(self, cfg):
        return AtomContext(atom_id=714, config=cfg, logger=_NullLogger(),
                           publish=self.publish, subscribe=self.subscribe)


def _tmp():
    d = tempfile.mkdtemp()
    return d


def _make_source(path, table, time_col, rows):
    conn = sqlite3.connect(path)
    try:
        conn.execute("CREATE TABLE %s (id INTEGER PRIMARY KEY AUTOINCREMENT,"
                     " symbol TEXT, %s REAL)" % (table, time_col))
        conn.executemany("INSERT INTO %s (symbol, %s) VALUES (?,?)" % (table, time_col),
                         rows)
        conn.commit()
    finally:
        conn.close()


def _query_all(path, sql):
    conn = sqlite3.connect(path)
    try:
        return conn.execute(sql).fetchall()
    finally:
        conn.close()


def _count(path, table):
    conn = sqlite3.connect(path)
    try:
        return conn.execute("SELECT COUNT(*) FROM %s" % table).fetchone()[0]
    finally:
        conn.close()


async def _run(cfg):
    bus = FakeEventBus()
    atom = Atom()
    await atom.initialize(bus.make_context(cfg))
    await atom.start()
    return bus, atom


async def test_archive_leaves_the_handler():
    """الأرشفة لا تُنتظَر في معالج حدث — كانت أسوأ مدّة في المنصّة.

    مقيس ٢٠٢٦-٠٩-١٦ من عدّاد الناقل: **٧١٤ أسوأ مدّة معالجٍ على المنصّة كلّها
    — ٣٠٫٠١ ثانية** مقابل ميزانية ٠٫٠٥. والذرّة مشترِكة في `SYS_SECOND`، أي
    أنّ الحجب يقع على نبض النظام. هنا يُبطَّأ النقل عمدًا: المعالج يجب أن
    يعود قبله، والصفوف يجب أن تصل بعده. لا مساعدة من الناقل: `bus.atom = None`.
    """
    print("\n--- test_archive_leaves_the_handler ---")
    d = _tmp()
    src = os.path.join(d, "market_data.db")
    arch = os.path.join(d, "archive.db")
    try:
        _make_source(src, "market_data", "occurred_at",
                     [("NQ", OLD_A), ("NQ", OLD_B), ("NQ", RECENT)])
        bus, atom = await _run({
            "stores": [{"db_path": src, "table": "market_data",
                        "time_column": "occurred_at"}],
            "archive_db_path": arch, "archive_after_days": 1, "batch_limit": 100})
        bus.atom = None
        real = atom._run

        def slow_run(cutoff):
            time.sleep(0.4)
            return real(cutoff)

        atom._run = slow_run
        t0 = time.perf_counter()
        await bus.publish(EVENT_PULSE, {"official_time": IN_WINDOW})
        handler_ms = (time.perf_counter() - t0) * 1000
        assert handler_ms < 100, "المعالج انتظر الأرشفة: %.0f ms" % handler_ms
        assert atom._archive_task is not None, "ما جُدولت الأرشفة"
        await atom._archive_task
        assert _count(src, "market_data") == 1, "الأرشفة ما جرت خلف المعالج"
        print("OK — المعالج عاد في %.1f ms والأرشفة جرت خلفه" % handler_ms)
    finally:
        __import__("shutil").rmtree(d, ignore_errors=True)


async def test_archives_old_rows_and_deletes():
    print("\n--- test_archives_old_rows_and_deletes ---")
    d = _tmp()
    src = os.path.join(d, "market_data.db")
    arch = os.path.join(d, "archive.db")
    try:
        _make_source(src, "market_data", "occurred_at",
                     [("NQ", OLD_A), ("NQ", OLD_B), ("NQ", RECENT)])
        bus, _ = await _run({
            "stores": [{"db_path": src, "table": "market_data",
                        "time_column": "occurred_at"}],
            "archive_db_path": arch, "archive_after_days": 1, "batch_limit": 100})
        # cutoff = IN_WINDOW - 1day -> OLD_A, OLD_B old; RECENT stays
        await bus.publish(EVENT_PULSE, {"official_time": IN_WINDOW})
        assert _count(src, "market_data") == 1, "recent row stays in source"
        rep = [p for n, p in bus.published if n == EVENT_OUT][-1]
        assert rep["archive_path"] != arch and rep["active_archive_path"] == arch
        assert _count(rep["archive_path"], "market_data") == 2, "2 old rows archived"
        assert rep["rows"] == 2, rep
        print(f"OK — نقل الصفوف القديمة للأرشيف وحذفها من المصدر: {rep['per_table']}")
    finally:
        __import__("shutil").rmtree(d, ignore_errors=True)


async def test_respects_time_column():
    print("\n--- test_respects_time_column ---")
    d = _tmp()
    src = os.path.join(d, "trades.db")
    arch = os.path.join(d, "archive.db")
    try:
        # trades keyed by closed_at, NOT occurred_at (the old bug)
        _make_source(src, "trades", "closed_at", [("NQ", OLD_A), ("NQ", RECENT)])
        bus, _ = await _run({
            "stores": [{"db_path": src, "table": "trades",
                        "time_column": "closed_at"}],
            "archive_db_path": arch, "archive_after_days": 1, "batch_limit": 100})
        await bus.publish(EVENT_PULSE, {"official_time": IN_WINDOW})
        rep = [p for n, p in bus.published if n == EVENT_OUT][-1]
        assert _count(rep["archive_path"], "trades") == 1, "old closed trade archived via closed_at"
        assert _count(src, "trades") == 1
        print("OK — احترم time_column (closed_at للصفقات) — الإصلاح شغّال")
    finally:
        __import__("shutil").rmtree(d, ignore_errors=True)


async def test_guards_bad_identifier():
    print("\n--- test_guards_bad_identifier ---")
    d = _tmp()
    arch = os.path.join(d, "archive.db")
    try:
        bus, atom = await _run({
            "stores": [{"db_path": os.path.join(d, "x.db"),
                        "table": "bad; DROP TABLE x", "time_column": "occurred_at"}],
            "archive_db_path": arch, "archive_after_days": 1, "batch_limit": 100})
        await bus.publish(EVENT_PULSE, {"official_time": IN_WINDOW})
        h = await atom.health_check()
        assert "bad store spec" in (h.message or ""), h.message
        print("OK — حرس المعرّفات: اسم جدول خبيث اترفض (لا حقن SQL)")
    finally:
        __import__("shutil").rmtree(d, ignore_errors=True)


async def test_health_states():
    print("\n--- test_health_states ---")
    d = _tmp()
    src = os.path.join(d, "market_data.db")
    arch = os.path.join(d, "archive.db")
    try:
        _make_source(src, "market_data", "occurred_at", [("NQ", OLD_A)])
        cfg = {"stores": [{"db_path": src, "table": "market_data",
                           "time_column": "occurred_at"}],
               "archive_db_path": arch, "archive_after_days": 1, "batch_limit": 100}
        bus = FakeEventBus()
        atom = Atom()
        await atom.initialize(bus.make_context(cfg))
        assert (await atom.health_check()).state == HealthState.UNHEALTHY
        await atom.start()
        h = await atom.health_check()
        assert h.state == HealthState.DEGRADED, h.message
        assert "AWAITING_FIRST_PULSE" in (h.message or ""), h.message
        # ٢٠٢٦-١٠-٠٩: إقلاعٌ خارج النافذة ⟵ اللحاق مطلوبٌ ويُعلَن أنّه ينتظرها — لا تدهور ولا أرشفة
        await bus.publish(EVENT_PULSE, {"official_time": DAY_PULSE_0300})
        waiting = await atom.health_check()
        assert waiting.state == HealthState.HEALTHY and "NEVER_RAN" in waiting.message, waiting.message
        assert "صيانة: آخرها" in waiting.message and atom._runs == 0, waiting.message
        await bus.publish(EVENT_PULSE, {"official_time": IN_WINDOW + 3 * DAY_S})
        assert (await atom.health_check()).state == HealthState.HEALTHY and atom._runs == 1
        report = [p for n, p in bus.published if n == EVENT_OUT][-1]
        assert report["trigger"] == "NEVER_RAN", report
        print("OK — الصحة: UNHEALTHY -> DEGRADED(AWAITING_FIRST_PULSE) -> ينتظر النافذة -> HEALTHY")
    finally:
        __import__("shutil").rmtree(d, ignore_errors=True)


async def test_within_window_is_ready_not_degraded():
    print("\n--- test_within_window_is_ready_not_degraded ---")
    d = _tmp()
    src = os.path.join(d, "market_data.db")
    arch = os.path.join(d, "archive.db")
    try:
        _make_source(src, "market_data", "occurred_at", [("NQ", IN_WINDOW - 1000.0)])
        bus, atom = await _run({
            "stores": [{"db_path": src, "table": "market_data",
                        "time_column": "occurred_at"}],
            "archive_db_path": arch, "archive_after_days": 1, "batch_limit": 100})
        # آخر نجاح قبل ساعة — داخل نافذة 24 ساعة ⇒ اللحاق يقرّر ألّا يعمل، ولا تكرار في نافذة الصيانة
        await atom.restore({"last_success": IN_WINDOW - 3600.0})
        await bus.publish(EVENT_PULSE, {"official_time": IN_WINDOW})
        h = await atom.health_check()
        assert h.state == HealthState.HEALTHY, (h.state, h.message)
        assert "WITHIN_WINDOW" in (h.message or ""), h.message
        assert "READY" in (h.message or ""), h.message
        assert h.details["runs"] == 0, h.details
        assert not [p for n, p in bus.published if n == EVENT_OUT], \
            "داخل النافذة ⇒ لا أرشفة عند الإقلاع"
        print(f"OK — داخل النافذة: HEALTHY برسالة صادقة: {h.message}")
    finally:
        __import__("shutil").rmtree(d, ignore_errors=True)


async def test_manifest_config_obeys_its_own_schema():
    """الاختبار الذي كان ناقصًا — ودفعتُ ثمنه.

    بقيّة الاختبارات تمرّر `config` إلى الذرّة مباشرةً، فلا تمرّ بمدقّق
    المانيفست إطلاقًا. يوم ٢٠٢٦-٠٩-٠٩ أُضيف `fallback_time_column` إلى
    `config` بلا `config_schema` (وفيه `additionalProperties: false`)، فسقط
    تحقّق الذرّة عند الإقلاع ولم تعمل — **وسبعة اختبارات خضراء لم تلحظ**.
    """
    print("\n--- test_manifest_config_obeys_its_own_schema ---")
    import yaml
    try:
        import jsonschema
    except ImportError:
        print("SKIP — jsonschema غير متاح")
        return
    path = _Path(__file__).resolve().parents[1] / "manifest.yaml"
    manifest = yaml.safe_load(path.read_text(encoding="utf-8"))
    schema = manifest["config_schema"]
    jsonschema.validate(manifest["config"], schema)
    # ويجب أن يبقى الحارس عاضًّا: مفتاح مخترَع يُرفض
    bad = {k: v for k, v in manifest["config"].items()}
    bad["stores"] = [dict(bad["stores"][0], مفتاح_مخترع="x")]
    try:
        jsonschema.validate(bad, schema)
    except jsonschema.ValidationError:
        pass
    else:
        raise AssertionError("العقد صار يقبل أي مفتاح — الحارس لا يعضّ")
    keys = sorted(manifest["config"]["stores"][0].keys())
    print(f"OK — config يجتاز عقده ({len(manifest['config']['stores'])} مخازن،"
          f" مفاتيح: {keys}) والمفتاح المخترَع مرفوض")


async def test_fallback_time_column_rescues_null_rows():
    print("\n--- test_fallback_time_column_rescues_null_rows ---")
    d = _tmp()
    src = os.path.join(d, "trades.db")
    arch = os.path.join(d, "archive.db")
    try:
        conn = sqlite3.connect(src)
        conn.execute("CREATE TABLE trades (id INTEGER PRIMARY KEY AUTOINCREMENT,"
                     " kind TEXT, closed_at REAL, stored_at REAL)")
        # صفقة مغلقة قديمة، ومفتوحة قديمة بلا closed_at (٧٥ منها على الحيّ)،
        # ومفتوحة حديثة يجب أن تبقى.
        conn.executemany("INSERT INTO trades (kind, closed_at, stored_at) VALUES (?,?,?)",
                         [("CLOSED", OLD_A, OLD_A),
                          ("OPENED", None, OLD_B),
                          ("OPENED", None, RECENT)])
        conn.commit(); conn.close()

        bus, atom = await _run({
            "stores": [{"db_path": src, "table": "trades",
                        "time_column": "closed_at",
                        "fallback_time_column": "stored_at"}],
            "archive_db_path": arch, "archive_after_days": 1, "batch_limit": 100})
        await bus.publish(EVENT_PULSE, {"official_time": IN_WINDOW})
        left = [r[0] for r in _query_all(src, "SELECT kind FROM trades ORDER BY id")]
        assert left == ["OPENED"], left
        rep = [p for n, p in bus.published if n == EVENT_OUT][-1]
        assert rep["per_table"].get("trades") == 2, rep["per_table"]
        assert not atom._last_error, atom._last_error
        print(f"OK — الصفّ بلا closed_at أُرشف بساعة التخزين"
              f" · نُقل {rep['per_table']} · وبقي الحديث")
    finally:
        __import__("shutil").rmtree(d, ignore_errors=True)


async def test_corrupt_store_does_not_stop_the_others():
    print("\n--- test_corrupt_store_does_not_stop_the_others ---")
    d = _tmp()
    first = os.path.join(d, "market_data.db")
    broken = os.path.join(d, "analysis.db")
    last = os.path.join(d, "decisions.db")
    arch = os.path.join(d, "archive.db")
    try:
        _make_source(first, "market_data", "occurred_at", [("NQ", OLD_A)])
        _make_source(last, "decisions", "decided_at", [("NQ", OLD_A)])
        # قاعدة تالفة في المنتصف — كحال analysis.db الحيّة يوم ٢٠٢٦-٠٩-٠٧
        with open(broken, "wb") as handle:
            handle.write(b"NOT-A-SQLITE-DATABASE" * 64)
        bus, atom = await _run({
            "stores": [
                {"db_path": first, "table": "market_data", "time_column": "occurred_at"},
                {"db_path": broken, "table": "analysis", "time_column": "occurred_at"},
                {"db_path": last, "table": "decisions", "time_column": "decided_at"},
            ],
            "archive_db_path": arch, "archive_after_days": 1, "batch_limit": 100})
        await bus.publish(EVENT_PULSE, {"official_time": IN_WINDOW})
        rep = [p for n, p in bus.published if n == EVENT_OUT][-1]
        per_table = rep["per_table"]
        assert "market_data" in per_table, per_table
        assert "decisions" in per_table, "المخزن الذي بعد التالف لم يُؤرشف"
        assert "analysis" not in per_table, per_table
        assert "analysis" in atom._last_error, atom._last_error
        health = await atom.health_check()
        assert health.state.name == "DEGRADED", health.state
        print(f"OK — التالف عُزل: أُرشف {sorted(per_table)}"
              f" · والعطل معلَن: {atom._last_error[:60]}")
    finally:
        __import__("shutil").rmtree(d, ignore_errors=True)


async def main():
    tests = [test_archive_leaves_the_handler,
             test_archives_old_rows_and_deletes, test_respects_time_column,
             test_guards_bad_identifier, test_health_states,
             test_within_window_is_ready_not_degraded,
             test_corrupt_store_does_not_stop_the_others,
             test_fallback_time_column_rescues_null_rows,
             test_manifest_config_obeys_its_own_schema]
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
