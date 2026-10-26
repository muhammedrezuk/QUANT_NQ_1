"""2026-10-17 (owner seal "NQ"): "the red news of the year are known -- the difference is only in MetaTrader". Our own color
reference (ForexFactory's colors; MetaTrader's Arabic names mapped to them) decides, whichever source sent the item:
MetaTrader grades the Fed statement MEDIUM -- it blocks; it grades crude oil HIGH -- it does not. An Arabic name of another
currency is not recolored. A USD title the reference lacks keeps the source's impact and is counted."""
import asyncio
import importlib.util
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE.parents[2]))
sys.path.insert(0, str(HERE))
_spec = importlib.util.spec_from_file_location("atom_109_colors", HERE / "atom.py")
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)

NOW = 1_800_000_000.0


def _atom():
    from core.contracts.atom import AtomContext
    cfg = yaml.safe_load((HERE / "manifest.yaml").read_text(encoding="utf-8"))["config"]
    events = []

    async def publish(name, payload):
        events.append((name, payload))

    atom = mod.Atom()
    asyncio.run(atom.initialize(AtomContext(atom_id=109, config=cfg, logger=None, publish=publish,
                                            subscribe=lambda *a: None, subscribe_all=lambda h: None)))
    asyncio.run(atom.start())
    return atom, events


def _feed(atom, items):
    for i, (title, currency, impact) in enumerate(items):
        asyncio.run(atom._on_calendar({"id": str(i), "title": title, "currency": currency, "impact_level": impact,
                                       "scheduled_at": NOW + 600 * (i + 1)}))


def test_reference_is_loaded_and_holds_the_known_reds():
    from shared import news_colors
    assert mod._reference_impact is not None
    ref = news_colors.reference()
    assert ref["currency"] == "USD" and ref["mt5_high_unmapped"] == []
    for title in ("Non-Farm Employment Change", "CPI m/m", "Core PCE Price Index m/m", "FOMC Statement",
                  "Federal Funds Rate", "Advance GDP q/q", "Fed Chair Testifies"):
        assert title in ref["red"]
    assert news_colors.color_of("Crude Oil Inventories", "USD") == "yellow"
    assert news_colors.color_of("بيان اللجنة الفيدرالية للسوق المفتوحة ", "USD") == "red"   # live title has a trailing space
    assert news_colors.color_of("قوائم الرواتب غير الزراعية", "EUR") is None


def test_metatrader_grades_are_replaced_by_our_colors():
    atom, events = _atom()
    _feed(atom, (("بيان اللجنة الفيدرالية للسوق المفتوحة ", "USD", "MEDIUM"),
                 ("التغيير في مخزون النفط الخام لإدارة معلومات الطاقة", "USD", "HIGH"),
                 ("محضر اجتماع اللجنة الفيدرالية للسوق المفتوحة", "USD", "MEDIUM"),
                 ("قوائم الرواتب غير الزراعية", "USD", "HIGH"),
                 ("عيد العمال", "USD", "UNKNOWN")))
    asyncio.run(atom._on_time({"official_time": NOW}))
    coming = [p for n, p in events if n == "market_data.calendar.state"][-1]["next_blocking"]
    assert [e["title"] for e in coming] == ["بيان اللجنة الفيدرالية للسوق المفتوحة",
                                            "محضر اجتماع اللجنة الفيدرالية للسوق المفتوحة", "قوائم الرواتب غير الزراعية"]
    assert coming[0]["source_impact_level"] == "MEDIUM" and coming[0]["impact_level"] == "HIGH"
    assert all(e["color_from"] == "reference" for e in coming)
    assert atom.reference_hits == 5 and atom.unreferenced_blocking_currency == 0


def test_forexfactory_titles_keep_their_colors_and_unknown_titles_keep_the_source():
    atom, events = _atom()
    _feed(atom, (("CPI m/m", "USD", "HIGH"), ("Philly Fed Manufacturing Index", "USD", "MEDIUM"),
                 ("Some New Speech", "USD", "HIGH"), ("مؤشر أسعار المستهلك على أساس شهري", "EUR", "HIGH")))
    asyncio.run(atom._on_time({"official_time": NOW}))
    coming = [p for n, p in events if n == "market_data.calendar.state"][-1]["next_blocking"]
    # 2026-10-23 (law 24): the red euro item now blocks too -- the euro pair -- with its source's color (the reference is USD)
    assert [(e["title"], e["color_from"]) for e in coming] == [("CPI m/m", "reference"), ("Some New Speech", "source"),
                                                              ("مؤشر أسعار المستهلك على أساس شهري", "source")]
    assert atom.unreferenced_blocking_currency == 1 and atom._unreferenced_titles == ["Some New Speech"]
    health = asyncio.run(atom.health_check())
    assert "خارج المرجع=1" in health.message and health.details["unreferenced_titles"] == ["Some New Speech"]


def test_restore_recolors_an_old_snapshot():
    atom, _ = _atom()
    old = {"events": [{"id": "a", "title": "بيان اللجنة الفيدرالية للسوق المفتوحة", "currency": "USD",
                       "impact_level": "MEDIUM", "scheduled_at": NOW + 600}], "announced": [], "source_seen": True}
    asyncio.run(atom.restore(old))
    event = atom._events["a"]
    assert event["impact_level"] == "HIGH" and event["source_impact_level"] == "MEDIUM" and atom._blocks_entry(event)
