"""2026-10-26 (owner's law, seal "NQ"): the open symbols are the system's alone -- the owner's manual position does not make
its symbol "open" for this card (as 415). Refusing an entry on a pair the owner holds is 555's, its one place."""
import importlib.util
from pathlib import Path

import pytest

from tests.learning_test_support import make_atom

_spec = importlib.util.spec_from_file_location("_t414_base", Path(__file__).resolve().parent / "test_atom.py")
base = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(base)
SYM = base.SYM


async def _run(rows):
    _, atom, bus = await make_atom(414, {"symbols": [SYM]})
    await base._facts(atom)
    await atom._on_positions({"positions": rows})
    await base._candle(atom, 30005.0, base.AT - 600)
    await base._candle(atom, 30015.0, base.AT - 300)
    return bus


@pytest.mark.asyncio
async def test_the_owners_position_does_not_make_its_symbol_open():
    bus = await _run([{"symbol": SYM, "ticket": 2036216648, "magic": 0}])
    assert bus.payloads("strategy.card.state")[-1]["status"] == base.card_trend.OPEN
    assert len(bus.payloads("decision.approved.state")) == 1


@pytest.mark.asyncio
async def test_the_systems_position_still_does():
    bus = await _run([{"symbol": SYM, "ticket": 1, "magic": 20260801}])
    assert bus.payloads("strategy.card.state")[-1]["status"] == "POSITION_OPEN"
    assert not bus.payloads("decision.approved.state")
