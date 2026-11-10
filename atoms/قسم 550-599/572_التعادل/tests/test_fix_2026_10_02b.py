# ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): التعادل يُقاس بسعر ميتاتريدر بجهة المركز
# (العرض للشراء، الطلب للبيع) لا بمنتصف سي‑تريدر، ولا يُرسل وقفًا في غير جهته من
# ذلك السعر بحدّ الوسيط — كان يُرسل فيردّه الوسيط 10016 (30 مرّة مقيسة).
import os
import sys

from pathlib import Path as _Path
sys.path.insert(0, str(_Path(__file__).resolve().parents[4]))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.contracts.atom import AtomContext  # noqa: E402
import importlib.util as _ilu  # noqa: E402

_spec = _ilu.spec_from_file_location(
    "_atom572_fix_b", _Path(__file__).resolve().parents[1] / "atom.py")
_mod = _ilu.module_from_spec(_spec)
sys.modules["_atom572_fix_b"] = _mod
_spec.loader.exec_module(_mod)
Atom = _mod.Atom
EVENT_OUT = _mod.EVENT_OUT
_mod.PLAN_GRACE_CYCLES = 1   # 2026-10-23 (law 6): primed away here; tested in `test_law6_2026_10_23.py`


class _Log:
    def __getattr__(self, _name):
        return lambda *a, **k: None


class _Bus:
    def __init__(self):
        self.published = []
        self.handlers = {}

    def subscribe(self, name, handler):
        self.handlers.setdefault(name, []).append(handler)

    async def publish(self, name, payload):
        self.published.append((name, payload))

    async def deliver(self, name, payload):
        for handler in self.handlers.get(name, []):
            await handler(payload)


async def _new(stops_level=0):
    bus = _Bus()
    atom = Atom()
    await atom.initialize(AtomContext(atom_id=572, config={"breakeven_at_r": 1.0}, logger=_Log(),
                                      publish=bus.publish, subscribe=bus.subscribe))
    await atom.start()
    await atom._on_plan({"tickets": []})
    await atom._on_specs({"symbols": [{"symbol": "XAUUSD", "tick_value": 1.0, "tick_size": 0.01,
                                       "point": 0.01, "stops_level": stops_level,
                                       "freeze_level": 0}]})
    return atom, bus


def _pos(current, side="BUY", entry=4000.0, stop=3999.0):
    return {"positions": [{"account_id": "A", "ticket": 9, "symbol": "XAUUSD", "side": side,
                           "volume": 0.1, "entry_price": entry, "current_price": current,
                           "stop_loss": stop, "take_profit": 0.0}]}


def _mt5(bid, ask):
    return {"provider": "MT5", "account_id": "A", "symbol": "XAUUSD", "bid": bid, "ask": ask,
            "price": (bid + ask) / 2.0}


def _outs(bus):
    return [p for n, p in bus.published if n == EVENT_OUT]


async def test_breakeven_waits_for_the_bid_not_the_ctrader_mid():
    atom, bus = await _new()
    await atom._on_positions(_pos(3999.9))                    # الخطر 1.0 من الدخول
    # منتصف سي‑تريدر عند +1.05 (= 1R) والعرض في ميتاتريدر عند +0.90 فقط.
    await bus.deliver("feed.ctrader.tick", {"provider": "CTRADER", "account_id": "A",
                                            "symbol": "XAUUSD", "bid": 4000.95,
                                            "ask": 4001.15, "price": 4001.05})
    await bus.deliver("feed.mt5.tick", _mt5(4000.90, 4001.20))
    assert not _outs(bus), "نُقل الوقف على سعرٍ غير سعر التنفيذ"
    await bus.deliver("feed.mt5.tick", _mt5(4001.00, 4001.30))  # العرض عند 1R
    out = _outs(bus)
    assert len(out) == 1 and out[0]["action"] == "MODIFY_SL", out
    assert out[0]["r_multiple"] == 1.0, out[0]


async def test_sell_side_measures_on_the_ask():
    atom, bus = await _new()
    await atom._on_positions(_pos(4000.1, side="SELL", entry=4000.0, stop=4001.0))
    await bus.deliver("feed.mt5.tick", _mt5(3998.80, 3999.10))   # الطلب عند 0.9R
    assert not _outs(bus)
    await bus.deliver("feed.mt5.tick", _mt5(3998.70, 3999.00))   # الطلب عند 1R
    out = _outs(bus)
    assert len(out) == 1 and out[0]["side"] == "SELL", out


async def test_a_stop_on_the_wrong_side_of_the_price_is_not_sent():
    """حدّ الوسيط 100 نقطة (1.00$): تعادلٌ صافٍ عند 3999.93 والطلب 3999.00 ⟸ المسافة
    0.93 دون الحدّ ⟸ يردّه الوسيط 10016 — فلا يُرسل، ويُعاد فحصه مع السعر التالي."""
    atom, bus = await _new(stops_level=100)
    await atom._on_positions(_pos(3999.00, side="SELL", entry=4000.0, stop=4001.0))
    assert not _outs(bus), "أُرسل وقفٌ يردّه الوسيط"
    assert atom._stop_invalid == 1
    await bus.deliver("feed.mt5.tick", _mt5(3998.50, 3998.80))   # المسافة 1.13 ≥ 1.01
    out = _outs(bus)
    assert len(out) == 1 and abs(out[0]["stop_loss"] - 3999.93) < 1e-9, out
    health = await atom.health_check()
    assert "وقف_لم_يُرسَل=1" in health.message, health.message
