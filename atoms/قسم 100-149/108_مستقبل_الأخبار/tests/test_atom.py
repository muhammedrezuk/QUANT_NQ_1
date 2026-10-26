import asyncio
import inspect
import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from pathlib import Path as _Path
sys.path.insert(0, str(_Path(__file__).resolve().parents[4]))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.contracts.atom import AtomContext, HealthState  # noqa: E402
import importlib.util as _ilu  # noqa: E402

_spec = _ilu.spec_from_file_location(
    "_atom108", _Path(__file__).resolve().parents[1] / "atom.py")
_mod = _ilu.module_from_spec(_spec)
sys.modules["_atom108"] = _mod
_spec.loader.exec_module(_mod)
Atom = _mod.Atom
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

    def subscribe(self, name, handler):
        self._handlers.setdefault(name, []).append(handler)

    async def publish(self, name, payload):
        self.published.append((name, payload))
        for h in self._handlers.get(name, []):
            r = h(payload)
            if inspect.isawaitable(r):
                await r

    def make_context(self):
        return AtomContext(atom_id=108, config={"source_event": "market.news",
                           "recent_size": 50}, logger=_NullLogger(),
                           publish=self.publish, subscribe=self.subscribe)


async def _make(bus):
    atom = Atom()
    await atom.initialize(bus.make_context())
    await atom.start()
    return atom


def _out(bus):
    return [p for n, p in bus.published if n == EVENT_OUT]


async def test_normalizes_no_invented_score():
    print("\n--- test_normalizes_no_invented_score ---")
    bus = FakeEventBus()
    await _make(bus)
    await bus.publish("market.news", {"id": "n1", "headline": "CPI beats",
                      "impact_level": "H", "symbols": ["EURUSD"]})  # no sentiment
    s = _out(bus)[-1]
    assert s["headline"] == "CPI beats" and s["impact_level"] == "HIGH"
    assert s["sentiment_score"] is None, "must NOT invent sentiment"
    print(f"OK — وحّد الأثر (H→HIGH)، وما اخترع sentiment (null): {s['impact_level']}")


async def test_dedupe():
    print("\n--- test_dedupe ---")
    bus = FakeEventBus()
    atom = await _make(bus)
    ev = {"id": "n9", "headline": "Fed holds"}
    await bus.publish("market.news", ev)
    await bus.publish("market.news", ev)
    assert len(_out(bus)) == 1 and atom._rejected.get("duplicate") == 1
    print("OK — نفس الخبر (id) ما اتنشر مرّتين")


async def test_ignores_no_headline():
    print("\n--- test_ignores_no_headline ---")
    bus = FakeEventBus()
    atom = await _make(bus)
    await bus.publish("market.news", {"id": "x", "source": "wire"})  # no headline
    assert not _out(bus) and atom._rejected.get("shape") == 1
    print("OK — خبر بلا عنوان اترفض")


async def test_616_row_id_collision_is_not_a_false_duplicate():
    """Item 21/27 of the 27-atom review ("same event name, two conflicting
    shapes -- between two atoms, not within one"): market.news producers
    each read their OWN database with its OWN independent row-id sequence.
    Before the fix, a producer put that raw row id straight into "id", so
    two unrelated, distinct headlines that both sat at row 1 collided in
    this atom's dedup key (self._seen_keys) and the second one silently
    vanished as a "duplicate". This is an end-to-end check using the
    REAL 616 producer code, not a hand-simulated 616 payload."""
    # ٢٠٢٦-١٠-٠١ (ختم المالك «Nq»): كان هذا الفحص يشغّل ٦١٥ و٦١٦ الحقيقيَّين معًا
    # (`next(rglob("615_*/atom.py"))`)، و٦١٥ أُرشفت بأمر المالك إلى سطح المكتب في
    # التزام d77a5c0 (٢٠٢٦-٠٩-١٩، «ختم NQ — أرشفة ٦١٥»)، والتزامُها نفسه سجّل أنّ هذا
    # الملفّ انكسر بها (StopIteration). فبقي ٦١٦ المنتجَ الحيّ الوحيد لـ`market.news`.
    # الشرط نفسه يبقى بالصرامة نفسها: ٦١٦ الحقيقيّ (صفّه ١) أمام ناشرٍ بالشكل الخام
    # القديم (`"id": 1`، كما كان المنتجون قبل الإصلاح). لو رجع ٦١٦ إلى رقم الصفّ الخام
    # لتصادم المفتاحان و`duplicate=1` فيسقط الفحص.
    print("\n--- test_616_row_id_collision_is_not_a_false_duplicate ---")
    import importlib.util as ilu
    import sqlite3
    import tempfile
    # م-36 (ورقة ٤١، 2026-08-28): المساران كانا من عهد التخطيط المسطح — بعد
    # التقسيم أقسامًا صارا بقسم آخر؛ يُوجدان بالبحث من جذر المستودع.
    _root = _Path(__file__).resolve().parents[4]
    root616 = next(_root.rglob("616_*/atom.py")).parent

    def load(name, folder):
        spec = ilu.spec_from_file_location(name, folder / "atom.py")
        mod = ilu.module_from_spec(spec)
        sys.modules[name] = mod
        spec.loader.exec_module(mod)
        return mod

    mod616 = load("_cross21_616", root616)

    class _Log:
        def __getattr__(self, n): return lambda *a, **k: None

    shared_bus = FakeEventBus()
    atom108 = await _make(shared_bus)

    # ٦١٦ يقدّم `NQ_BRIDGE_DB` على `db_path` — يُزاح هنا كي لا يقرأ الفحصُ الجسرَ الحيّ
    # ولا يكتب مؤشّره بجواره.
    saved_env = os.environ.pop("NQ_BRIDGE_DB", None)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            db616 = os.path.join(tmp, "news616.db")
            con = sqlite3.connect(db616)
            con.execute("CREATE TABLE news (id INTEGER PRIMARY KEY, headline TEXT, link TEXT, "
                        "source TEXT, sentiment_score REAL, impact_level TEXT, symbols TEXT, "
                        "published_at REAL, written_at REAL)")
            con.execute("INSERT INTO news (id, headline, link, source, published_at, written_at) "
                        "VALUES (1,'From 616 bridge','u616','src616',2000.0,2000.0)")
            con.commit(); con.close()

            # ناشرٌ آخر بالشكل الخام: رقم صفّه ١ من قاعدته المستقلّة.
            await shared_bus.publish("market.news", {
                "id": 1, "headline": "From raw-row-id source", "link": "uraw",
                "source": "srcraw", "published_at": 1000.0, "written_at": 1000.0})

            atom616 = mod616.Atom()
            await atom616.initialize(mod616.AtomContext(
                atom_id=616, config={"db_path": db616, "poll_interval_s": 0.0, "batch_limit": 10},
                logger=_Log(), publish=shared_bus.publish, subscribe=shared_bus.subscribe))
            assert atom616._db_path == db616, atom616._db_path
            await atom616.start()

            await atom616._read_all()
            await atom616.stop()
    finally:
        if saved_env is not None:
            os.environ["NQ_BRIDGE_DB"] = saved_env

    ids616 = [p.get("id") for n, p in shared_bus.published
              if n == "market.news" and p.get("headline") == "From 616 bridge"]
    assert ids616 == ["616:1"], ("معرّف ٦١٦ يجب أن يكون مُسمًّى بالذرّة", ids616)
    out = _out(shared_bus)
    headlines = {item["headline"] for item in out}
    assert atom108._rejected.get("duplicate", 0) == 0, (
        "تصادم رقم الصفّ بين ٦١٦ ومصدرٍ آخر رُفض كتكرار -- خبر حقيقي ضاع بصمت: %r" % atom108._rejected)
    assert "From raw-row-id source" in headlines and "From 616 bridge" in headlines, (
        "كلا الخبرين (٦١٦ ومصدرٌ آخر، نفس رقم الصفّ ١ بقاعدتين مستقلّتين) يجب أن يصلا كلاهما: %r"
        % headlines)
    print("OK — تصادم رقم صفّ بين ٦١٦ ومصدرٍ آخر لا يُفقَد كتكرار كاذب")


async def test_health_states():
    print("\n--- test_health_states ---")
    bus = FakeEventBus()
    atom = Atom()
    await atom.initialize(bus.make_context())
    assert (await atom.health_check()).state == HealthState.UNHEALTHY
    await atom.start()
    assert (await atom.health_check()).state == HealthState.DEGRADED
    await bus.publish("market.news", {"id": "n1", "headline": "x"})
    assert (await atom.health_check()).state == HealthState.HEALTHY
    print("OK — الصحة: UNHEALTHY -> DEGRADED(UNAVAILABLE) -> HEALTHY")


async def main():
    tests = [test_normalizes_no_invented_score, test_dedupe, test_ignores_no_headline,
             test_616_row_id_collision_is_not_a_false_duplicate,
             test_health_states]
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


async def test_sentiment_bounds_are_inclusive_at_the_edges():
    """`-1.0` و`+1.0` قيمتان مشروعتان — الحدّ داخل المدى لا خارجه.

    طفرة `-1.0 <= score <= 1.0` ← `-1.0 < score < 1.0` نجت: خبرٌ
    بمشاعر سلبيّة أو إيجابيّة **قصوى** — وهو أشدّ ما يحرّك السوق —
    كان سيُرمى، بينما 0.5 يمرّ. الاختبارات كانت تستعمل قيمًا في وسط
    المدى فلا تفرّق.
    """
    bus = FakeEventBus()
    await _make(bus)
    for score in (-1.0, 1.0):
        await bus.publish("market.news", {"headline": f"خبر {score}",
                                          "sentiment_score": score,
                                          "timestamp": 100.0 + score})
    rows = _out(bus)
    assert len(rows) == 2, ("الطرفان مقبولان", len(rows))
    assert {r.get("sentiment_score") for r in rows} == {-1.0, 1.0}
    # وما تجاوز المدى يُرفض
    await bus.publish("market.news", {"headline": "خارج المدى",
                                      "sentiment_score": 1.01, "timestamp": 200.0})
    last = _out(bus)[-1]
    assert last.get("sentiment_score") is None, ("خارج المدى لا يُنسب رقمًا", last)
    print("OK — ±1.0 مقبولان وما تجاوزهما لا يُنسب")