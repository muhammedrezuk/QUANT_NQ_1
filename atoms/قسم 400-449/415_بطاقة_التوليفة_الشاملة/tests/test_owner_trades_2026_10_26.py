"""2026-10-26 (owner's law and answer, seal "NQ"): the card's open symbols are the system's own -- the owner's manual trade
neither holds the card nor starts its wait after a close (the entry gate 555 alone refuses a symbol carrying his trade)."""
import asyncio
import importlib.util
import sys
from pathlib import Path

_spec = importlib.util.spec_from_file_location("_t415_owner", Path(__file__).resolve().parent / "test_atom.py")
T = importlib.util.module_from_spec(_spec)
sys.modules["_t415_owner"] = T
_spec.loader.exec_module(T)


def _atom():
    atom = T.mod.Atom()
    atom._clock = lambda: 1000.0
    return atom


def test_the_owners_trade_is_not_an_open_symbol_and_its_close_starts_no_wait():
    atom = _atom()
    asyncio.run(atom._on_positions({"positions": [{"symbol": "USTEC", "magic": 0}]}))
    assert atom._open == set()
    asyncio.run(atom._on_positions({"positions": []}))
    assert "USTEC" not in atom._closed_at


def test_the_systems_trade_still_holds_and_waits():
    atom = _atom()
    asyncio.run(atom._on_positions({"positions": [{"symbol": "USTEC", "magic": 20260801}, {"symbol": "USTEC", "magic": 0}]}))
    assert atom._open == {"USTEC"}
    asyncio.run(atom._on_positions({"positions": [{"symbol": "USTEC", "magic": 0}]}))
    assert atom._closed_at.get("USTEC") == 1000.0 and atom._open == set()
