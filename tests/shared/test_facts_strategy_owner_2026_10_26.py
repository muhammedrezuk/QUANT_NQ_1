"""2026-10-26 (owner's law, seal "NQ"): for the seven fact strategies (404-410) the open symbols are the system's alone --
the owner's manual position does not make its symbol "open" (as 414 and 415). Refusing an entry on his pair is 555's."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from shared.facts_strategy_atom import FactsStrategy  # noqa: E402


class _S(FactsStrategy):
    STRATEGY = "404"


async def test_the_owners_position_does_not_open_its_symbol():
    s = _S()
    await s._on_positions({"positions": [{"symbol": "ustec", "ticket": 2036216648, "magic": 0},
                                         {"symbol": "xauusd", "ticket": 1, "magic": 20260801},
                                         {"symbol": "eurusd", "ticket": 2}]})
    assert s._positions_seen is True and s._open == {"XAUUSD", "EURUSD"}
