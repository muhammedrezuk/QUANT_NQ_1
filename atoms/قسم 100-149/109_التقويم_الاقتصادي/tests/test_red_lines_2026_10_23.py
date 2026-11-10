"""2026-10-23 (owner's sealed red lines, laws 24-26): a red item of *any* currency opens a window 15 minutes before it and
15 minutes after, and the state names the currencies inside their window now (`blocked_currencies`) so the red line blocks an
asset by its own currencies; a medium (orange) item and an item without a currency block nothing; each currency's nearest
red item stays in `next_blocking` even past the first five."""
import asyncio
import importlib.util
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE.parents[2]))
sys.path.insert(0, str(HERE))
_spec = importlib.util.spec_from_file_location("atom_109_red_lines", HERE / "atom.py")
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)

NOW = 1_800_000_000.0
STATE = "market_data.calendar.state"


def build(items):
    """The atom on its real manifest config, fed `items` (title, currency, impact, minutes from NOW)."""
    from core.contracts.atom import AtomContext
    cfg = yaml.safe_load((HERE / "manifest.yaml").read_text(encoding="utf-8"))["config"]
    events = []

    async def publish(name, payload):
        events.append((name, payload))

    atom = mod.Atom()
    asyncio.run(atom.initialize(AtomContext(atom_id=109, config=cfg, logger=None, publish=publish,
                                            subscribe=lambda *a: None, subscribe_all=lambda h: None)))
    asyncio.run(atom.start())
    for i, (title, currency, impact, minutes) in enumerate(items):
        asyncio.run(atom._on_calendar({"id": str(i), "title": title, "currency": currency, "impact_level": impact,
                                       "scheduled_at": NOW + 60 * minutes}))
    return atom, events


def state_at(atom, events, moment):
    asyncio.run(atom._on_time({"official_time": moment}))
    return [p for n, p in events if n == STATE][-1]


def test_a_red_euro_item_opens_a_15_minute_window_on_both_sides():
    atom, events = build([("German ZEW", "EUR", "HIGH", 60)])
    item = NOW + 3600
    assert state_at(atom, events, item - 901)["blocked_currencies"] == []
    first = state_at(atom, events, item - 900)
    assert first["blocked_currencies"] == ["EUR"] and first["in_event_window"] is True and first["status"] == "BLOCKED"
    assert state_at(atom, events, item + 900)["blocked_currencies"] == ["EUR"]
    assert state_at(atom, events, item + 901)["blocked_currencies"] == []


def test_two_currencies_at_once_are_both_named():
    atom, events = build([("CPI m/m", "USD", "HIGH", 10), ("BoE Rate", "GBP", "HIGH", 12)])
    assert state_at(atom, events, NOW)["blocked_currencies"] == ["GBP", "USD"]


def test_orange_and_currency_less_items_block_nothing():
    atom, events = build([("Retail Sales", "EUR", "MEDIUM", 5), ("Unnamed red", "", "HIGH", 5)])
    body = state_at(atom, events, NOW)
    assert body["blocked_currencies"] == [] and body["in_event_window"] is False and body["next_blocking"] == []


def test_each_currencys_nearest_red_item_stays_listed_past_the_first_five():
    items = [("JPY item %d" % i, "JPY", "HIGH", 30 + i) for i in range(6)] + [("NFP", "USD", "HIGH", 300)]
    atom, events = build(items)
    coming = state_at(atom, events, NOW)["next_blocking"]
    assert len(coming) == 6 and coming[-1]["title"] == "NFP" and coming[-1]["red_line_from"] == NOW + 300 * 60 - 900
