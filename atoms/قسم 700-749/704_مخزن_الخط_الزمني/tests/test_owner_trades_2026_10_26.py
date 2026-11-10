"""2026-10-26 (owner's law, seal "NQ"): the owner's position appearing or vanishing is not kept in the timeline and not
counted -- by the one distinction in `shared/owner_trades.py`. Only those two events carry his trade: any other event is
the system's, even with a foreign magic (552 refuses a system order whose magic is 0), so it is kept as before."""
import importlib.util
import inspect
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.contracts.atom import AtomContext  # noqa: E402

_spec = importlib.util.spec_from_file_location("_t704_owner", Path(__file__).resolve().parents[1] / "atom.py")
m = importlib.util.module_from_spec(_spec)
sys.modules["_t704_owner"] = m
_spec.loader.exec_module(m)

APPEARED = "platform.position.appeared"
VANISHED = "platform.position.vanished"
REJECTED = "execution.order.rejected"


class L:
    def __getattr__(self, n):
        return lambda *a, **k: None


class B:
    def __init__(self):
        self.h = {}

    def subscribe(self, n, h):
        self.h.setdefault(n, []).append(h)

    async def publish(self, n, p):
        for h in self.h.get(n, []):
            r = h(p)
            if inspect.isawaitable(r):
                await r


async def _with_atom(body):
    fd, db = tempfile.mkstemp(suffix=".db"); os.close(fd); os.unlink(db)
    b = B(); a = m.Atom()
    await a.initialize(AtomContext(atom_id=704, config={"db_path": db, "watch_events": [APPEARED, VANISHED, REJECTED],
                                                        "flush_size": 1, "retention_days": 90},
                                   logger=L(), publish=b.publish, subscribe=b.subscribe))
    await a.start()
    try:
        await body(a, b)
        conn = sqlite3.connect(db)
        try:
            return a, conn.execute("SELECT event_name, symbol FROM timeline ORDER BY id").fetchall()
        finally:
            conn.close()
    finally:
        await a.stop()
        for suffix in ("", "-wal", "-shm"):
            if os.path.exists(db + suffix):
                os.unlink(db + suffix)


def _row(ticket, symbol, magic):
    row = {"ticket": ticket, "symbol": symbol, "side": "BUY", "volume": 20, "account_id": "52992818", "timestamp": 9.0}
    if magic is not None:
        row["magic"] = magic
    return row


async def test_the_owners_position_is_not_kept_nor_counted():
    async def body(a, b):
        await b.publish(APPEARED, _row(2036216648, "USTEC", 0))
        await b.publish(VANISHED, _row(2036216648, "USTEC", 0))
    a, rows = await _with_atom(body)
    assert rows == [] and a.recorded_count == 0


async def test_the_systems_position_is_kept_as_before():
    async def body(a, b):
        await b.publish(APPEARED, _row(1, "XAUUSD", 20260801))
        await b.publish(APPEARED, _row(2, "EURUSD", None))               # no magic known: the system's, as before
    a, rows = await _with_atom(body)
    assert rows == [(APPEARED, "XAUUSD"), (APPEARED, "EURUSD")] and a.recorded_count == 2


async def test_another_event_with_a_foreign_magic_is_still_kept():
    async def body(a, b):
        await b.publish(REJECTED, {"symbol": "NQ100", "magic": 0, "reason": "MISSING_MAGIC", "timestamp": 9.0})
    a, rows = await _with_atom(body)
    assert rows == [(REJECTED, "NQ100")] and a.recorded_count == 1
