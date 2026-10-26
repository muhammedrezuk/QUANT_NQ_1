"""2026-10-26 (owner's law, seal "NQ"): the owner's position appearing or vanishing is not written to the trades log and
not counted -- by the one distinction in `shared/owner_trades.py`. The system's are written as before."""
import importlib.util
import inspect
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from core.contracts.atom import AtomContext  # noqa: E402

_spec = importlib.util.spec_from_file_location("_t720_owner", Path(__file__).resolve().parents[1] / "atom.py")
m = importlib.util.module_from_spec(_spec)
sys.modules["_t720_owner"] = m
_spec.loader.exec_module(m)


class L:
    def __getattr__(self, n):
        return lambda *a, **k: None


class B:
    def __init__(self):
        self.e = []
        self.h = {}

    def subscribe(self, n, h):
        self.h.setdefault(n, []).append(h)

    async def publish(self, n, p):
        self.e.append((n, p))
        for h in self.h.get(n, []):
            r = h(p)
            if inspect.isawaitable(r):
                await r


async def _new(tmp):
    b = B(); a = m.Atom()
    cfg = {"dir": tmp, "file_prefix": "trades", "state_tail": 12, "max_lines_per_day": 20000}
    await a.initialize(AtomContext(atom_id=720, config=cfg, logger=L(), publish=b.publish, subscribe=b.subscribe))
    await a.start()
    return a, b


def _lines(tmp):
    path = Path(tmp) / ("trades-%s.log" % time.strftime("%Y%m%d"))
    return path.read_text(encoding="utf-8").splitlines() if path.exists() else []


def _row(ticket, symbol, magic, **extra):
    row = {"ticket": ticket, "symbol": symbol, "side": "BUY", "volume": 20, "entry_price": 21000.5,
           "account_id": "52992818", "timestamp": time.time(), **extra}
    if magic is not None:
        row["magic"] = magic
    return row


async def test_the_owners_position_is_not_logged_nor_counted():
    tmp = tempfile.mkdtemp()
    a, b = await _new(tmp)
    await b.publish(m.EVENT_APPEARED, _row(2036216648, "USTEC", 0))
    await b.publish(m.EVENT_VANISHED, _row(2036216648, "USTEC", 0, profit=655.8))
    assert _lines(tmp) == [] and a.events_in == 0
    assert not [p for n, p in b.e if n == m.EVENT_STATE]
    assert (await a.health_check()).details["events_in"] == 0


async def test_the_systems_position_is_logged_as_before():
    tmp = tempfile.mkdtemp()
    a, b = await _new(tmp)
    await b.publish(m.EVENT_APPEARED, _row(1, "XAUUSD", 20260801))
    await b.publish(m.EVENT_VANISHED, _row(1, "XAUUSD", 20260801, profit=-1.2))
    await b.publish(m.EVENT_APPEARED, _row(2, "EURUSD", None))           # no magic known: the system's, as before
    text = "\n".join(_lines(tmp))
    assert "ظهر مركزٌ على المنصّة: شراء XAUUSD" in text and "اختفى مركزٌ من المنصّة: شراء XAUUSD" in text
    assert "ظهر مركزٌ على المنصّة: شراء EURUSD" in text
    assert a.events_in == 3
