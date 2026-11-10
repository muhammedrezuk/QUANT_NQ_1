# ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): صيانة الوقف بسعر ميتاتريدر بجهة المركز،
# ولا وقفَ يُرسل في غير جهته من ذلك السعر — كان الوسيط يردّه 10016.
import os
import sys

from pathlib import Path as _Path
sys.path.insert(0, str(_Path(__file__).resolve().parents[4]))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.contracts.atom import AtomContext  # noqa: E402
import importlib.util as _ilu  # noqa: E402

_spec = _ilu.spec_from_file_location(
    "_atom577_fix_b", _Path(__file__).resolve().parents[1] / "atom.py")
_mod = _ilu.module_from_spec(_spec)
sys.modules["_atom577_fix_b"] = _mod
_spec.loader.exec_module(_mod)
Atom = _mod.Atom
EVENT_MANAGE = _mod.EVENT_MANAGE


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


async def _new(config=None):
    bus = _Bus()
    atom = Atom()
    await atom.initialize(AtomContext(atom_id=577, config=config or {}, logger=_Log(),
                                      publish=bus.publish, subscribe=bus.subscribe))
    await atom.start()
    # قيمة النقطة وسقف الصفقة من ٥١٣، والنقطة وحدّ الوسيط من ٦١٨ (الحيّ: 0.01 و0).
    await atom._on_size({"symbol": "XAUUSD", "metadata": {"tick_value": 1.0, "tick_size": 0.01,
                                                          "max_trade_loss": 100.0}})
    await bus.deliver("market.symbol_specs", {"symbols": [
        {"symbol": "XAUUSD", "point": 0.01, "tick_size": 0.01, "stops_level": 0,
         "freeze_level": 0}]})
    return atom, bus


def _pos(current, side="BUY"):
    # خسارة الوقف 0.2 × 10 × 100 = 200$ > سقف 105$ ⟸ يُضيَّق إلى 3995.0 (شراء).
    stop = 3990.0 if side == "BUY" else 4010.0
    return {"account_id": "A1", "symbol": "XAUUSD", "ticket": 11, "side": side,
            "volume": 0.2, "entry_price": 4000.0, "current_price": current,
            # ٢٠٢٦-١٠-٢٦ (قانون صفقات المالك): مركزٌ للمنظومة بسحرها — كان 7، وسحرٌ غير سحرها صار صفقةَ مالكٍ لا تُدار.
            "stop_loss": stop, "take_profit": 4030.0 if side == "BUY" else 3970.0,
            "magic": 20260801, "commission": 0.0, "swap": 0.0}


def _sent(bus):
    return [p for n, p in bus.published if n == EVENT_MANAGE]


async def test_tightened_stop_beyond_the_bid_is_not_sent_until_it_is_valid():
    atom, bus = await _new()
    await atom._on_positions({"positions": [_pos(3994.0)]})   # العرض تحت 3995 بالفعل
    assert not _sent(bus), "أُرسل وقفٌ فوق العرض — يردّه الوسيط 10016"
    assert atom._stop_invalid == 1 and 11 not in atom._capped
    await atom._on_positions({"positions": [_pos(3996.0)]})   # عاد العرض فوقه
    out = _sent(bus)
    assert len(out) == 1 and abs(out[0]["stop_loss"] - 3995.0) < 1e-9, out


async def test_ticks_come_from_mt5_with_the_position_side_price():
    atom, bus = await _new()
    assert "feed.mt5.tick" in bus.handlers and "feed.ctrader.tick" not in bus.handlers
    seen = []

    async def capture(pos):
        seen.append((pos["side"], pos["current_price"]))

    atom._cap_risk = capture
    atom._trail_structure = capture
    await atom._on_positions({"positions": [_pos(3994.0), dict(_pos(4006.0, "SELL"), ticket=12)]})
    seen.clear()
    await bus.deliver("feed.mt5.tick", {"provider": "MT5", "account_id": "A1",
                                        "symbol": "XAUUSD", "bid": 4001.0, "ask": 4001.5,
                                        "price": 4001.25})
    assert ("BUY", 4001.0) in seen and ("SELL", 4001.5) in seen, seen
