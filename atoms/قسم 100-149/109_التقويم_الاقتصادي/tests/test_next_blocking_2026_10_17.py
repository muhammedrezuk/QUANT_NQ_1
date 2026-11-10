"""2026-10-17 (owner seal, steps 8 and 14): the state carries the coming blocking news with the time left to each and its
red line (6 minutes either side). Since 14:55 (owner seal): every red (HIGH) USD item blocks, not only the Fed titles;
a medium one, another currency or a ForexFactory "NONE" (holiday) does not."""
import asyncio
import importlib.util
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE.parents[2]))
sys.path.insert(0, str(HERE))
_spec = importlib.util.spec_from_file_location("atom_109_next", HERE / "atom.py")
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)


def test_next_blocking_lists_the_coming_fed_events_with_their_red_lines():
    from core.contracts.atom import AtomContext
    cfg = yaml.safe_load((HERE / "manifest.yaml").read_text(encoding="utf-8"))["config"]
    # 2026-10-23 (sealed red lines, laws 24-25): 15 minutes either side, and every currency blocks (an empty list).
    assert cfg["alert_before_seconds"] == 900.0 and cfg["keep_past_seconds"] == 900.0
    assert cfg["blocking_min_impact"] == "HIGH" and cfg["blocking_titles"] == [] and cfg["blocking_currencies"] == []
    events = []

    async def publish(name, payload):
        events.append((name, payload))

    atom = mod.Atom()
    asyncio.run(atom.initialize(AtomContext(atom_id=109, config=cfg, logger=None, publish=publish,
                                            subscribe=lambda *a: None, subscribe_all=lambda h: None)))
    asyncio.run(atom.start())
    now = 1_800_000_000.0
    items = (("Federal Funds Rate", "USD", "HIGH"), ("CPI m/m", "USD", "HIGH"), ("Philly Fed Index", "USD", "MEDIUM"),
             ("German ZEW", "EUR", "HIGH"), ("Bank Holiday", "USD", "NONE"), ("FOMC Press Conference", "USD", "HIGH"))
    for i, (title, currency, impact) in enumerate(items):
        asyncio.run(atom._on_calendar({"id": str(i), "title": title, "currency": currency, "impact_level": impact,
                                       "scheduled_at": now + 600 * (i + 1)}))
    asyncio.run(atom._on_time({"official_time": now}))
    state = [p for n, p in events if n == "market_data.calendar.state"][-1]
    coming = state["next_blocking"]
    # the red euro item is listed since 2026-10-23 (it blocks the euro pair); the medium and the holiday still do not
    assert [e["title"] for e in coming] == ["Federal Funds Rate", "CPI m/m", "German ZEW", "FOMC Press Conference"]
    assert coming[0]["seconds_until"] == 600.0 and coming[0]["red_line_from"] == now + 600 - 900
