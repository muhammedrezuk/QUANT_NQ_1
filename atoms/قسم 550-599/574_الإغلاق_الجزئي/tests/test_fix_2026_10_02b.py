# ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): الإدارة تقيس بسعر ميتاتريدر بجهة المركز،
# ولا ترسل وقفًا في غير جهته، ولا تقسّم هدفًا ثلثُه داخل كلفة الدورة.
#
# الحالة المقيسة: US30 التذكرة 1976793832 (2026-09-30) — دخول 51356.0، هدف 51359.25
# (3.25 نقطة)، وقف 51271.28 (85.9 نقطة). منتصف سي‑تريدر بلغ الثلث فأُغلق 0.3 لوت
# عند 51354.3 (−0.51$)، ونُقل الوقف إلى 51356.0 فردّه الوسيط 10016 مرّتين.
import os
import sys

from pathlib import Path as _Path
sys.path.insert(0, str(_Path(__file__).resolve().parents[4]))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.contracts.atom import AtomContext  # noqa: E402
import importlib.util as _ilu  # noqa: E402

_spec = _ilu.spec_from_file_location(
    "_atom574_fix_b", _Path(__file__).resolve().parents[1] / "atom.py")
_mod = _ilu.module_from_spec(_spec)
sys.modules["_atom574_fix_b"] = _mod
_spec.loader.exec_module(_mod)
Atom = _mod.Atom
EVENT_OUT = _mod.EVENT_OUT

CFG = {"partial_at_r": 1.0, "partial_fraction": 0.5, "min_partial_lot": 0.01}


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


async def _new():
    bus = _Bus()
    atom = Atom()
    await atom.initialize(AtomContext(atom_id=574, config=dict(CFG), logger=_Log(),
                                      publish=bus.publish, subscribe=bus.subscribe))
    await atom.start()
    # مواصفات الوسيط الحيّة للمؤشّرات (symbol_specs_v2، قراءةً فقط اليوم).
    await atom._on_specs({"symbols": [
        {"symbol": sym, "volume_min": 0.1, "volume_step": 0.1, "tick_value": 0.01,
         "tick_size": 0.01, "point": 0.01, "stops_level": 0, "freeze_level": 0}
        for sym in ("US30", "USTEC")]})
    return atom, bus


def _us30(current, volume=1.0, ticket=1976793832):
    return {"positions": [{"account_id": "A", "ticket": ticket, "symbol": "US30",
                           "side": "BUY", "volume": volume, "entry_price": 51356.0,
                           "current_price": current, "stop_loss": 51271.28,
                           "take_profit": 51359.25}]}


def _mt5(bid, ask, symbol="US30"):
    return {"provider": "MT5", "account_id": "A", "symbol": symbol, "bid": bid, "ask": ask,
            "price": (bid + ask) / 2.0}


def _ctrader(price, symbol="US30"):
    return {"provider": "CTRADER", "account_id": "A", "symbol": symbol,
            "bid": price - 0.5, "ask": price + 0.5, "price": price}


def _outs(bus, action=None):
    rows = [p for n, p in bus.published if n == EVENT_OUT]
    return [p for p in rows if action is None or p.get("action") == action]


async def test_us30_first_third_waits_for_the_mt5_bid_not_the_ctrader_mid():
    atom, bus = await _new()
    await atom._on_positions(_us30(51355.3))                 # دورة ٦٠٩: العرض بعد الدخول
    await bus.deliver("feed.mt5.tick", _mt5(51354.3, 51355.0))
    # منتصف سي‑تريدر عند 51357.15 (= الثلث وأكثر) — كان يُطلق الإغلاق وهو بالخسارة.
    await bus.deliver("feed.ctrader.tick", _ctrader(51357.15))
    assert not _outs(bus, "CLOSE_PARTIAL"), "أُغلق الثلث على منتصف سي‑تريدر والعرض تحت الدخول"
    # العرض نفسه يبلغ الثلث (51356 + 3.25/3 = 51357.083) ⟸ الآن فقط.
    await bus.deliver("feed.mt5.tick", _mt5(51357.10, 51357.80))
    closes = _outs(bus, "CLOSE_PARTIAL")
    assert len(closes) == 1 and closes[0]["volume"] == 0.3, closes
    assert closes[0]["target_progress"] >= 1 / 3 - 1e-9, closes[0]


async def test_breakeven_is_not_sent_on_the_wrong_side_of_the_bid():
    atom, bus = await _new()
    await atom._on_positions(_us30(51357.10))                # المرحلة الأولى على العرض
    assert len(_outs(bus, "CLOSE_PARTIAL")) == 1
    # نقص الحجم والعرض هبط تحت الدخول: وقفٌ عند 51356.0 يردّه الوسيط 10016.
    await atom._on_positions(_us30(51355.9, volume=0.7))
    assert not _outs(bus, "MODIFY_SL"), "أُرسل وقفٌ فوق العرض"
    assert atom._stop_invalid == 1
    # يعود العرض فوق الدخول بنقطةٍ وأكثر ⟸ يخرج الوقف المؤجَّل.
    await bus.deliver("feed.mt5.tick", _mt5(51356.40, 51357.10))
    stops = _outs(bus, "MODIFY_SL")
    assert len(stops) == 1 and stops[0]["stop_loss"] == 51356.0, stops


async def test_a_target_whose_third_is_inside_the_round_trip_cost_is_single_target():
    """USTEC (مقيس: هدف 2.19 مقابل وقف 24) والسبريد الحيّ 0.9 ⟸ الثلث 0.73 داخل الكلفة."""
    atom, bus = await _new()
    await bus.deliver("feed.mt5.tick", _mt5(20000.0, 20000.9, symbol="USTEC"))
    pos = {"positions": [{"account_id": "A", "ticket": 1966045088, "symbol": "USTEC",
                          "side": "BUY", "volume": 1.0, "entry_price": 20000.9,
                          "current_price": 20000.0, "stop_loss": 19976.9,
                          "take_profit": 20003.09}]}
    await atom._on_positions(pos)
    for bid in (20001.7, 20002.5, 20003.2):                  # الثلث ثمّ الثلثان ثمّ الهدف
        await bus.deliver("feed.mt5.tick", _mt5(bid, bid + 0.9, symbol="USTEC"))
        pos["positions"][0]["current_price"] = bid           # ودورة ٦٠٩ بالسعر نفسه
        await atom._on_positions(pos)
    assert not _outs(bus), _outs(bus)
    assert atom._single_target == 1
    health = await atom.health_check()
    assert "هدف_واحد=1" in health.message, health.message


async def test_a_normal_target_keeps_the_owner_thirds_plan():
    """US30 بسبريده الحيّ 0.7: الثلث 1.083 فوق الكلفة ⟸ خطّة المالك كما هي."""
    atom, bus = await _new()
    await bus.deliver("feed.mt5.tick", _mt5(51355.3, 51356.0))
    await atom._on_positions(_us30(51355.3))
    await atom._on_positions(_us30(51357.10))
    await atom._on_positions(_us30(51358.20, volume=0.7))    # الثاني: نصف الباقي
    await atom._on_positions(_us30(51359.30, volume=0.4))    # الثالث: الكلّ
    actions = [(p["action"], p.get("volume"), p.get("stop_loss")) for p in _outs(bus)]
    assert actions[0] == ("CLOSE_PARTIAL", 0.3, None), actions
    # ٢٠٢٦-١٠-٢٦ (ختم المالك «NQ»: «يضاف سبريد»): التعادل الدخول ومعه السبريد الحاضر 0.7 (الداو بلا عمولة).
    assert ("MODIFY_SL", None, 51356.7) in actions, actions
    assert ("CLOSE_PARTIAL", 0.3, None) in actions[2:], actions
    assert actions[-1][0] == "CLOSE", actions
    assert atom._single_target == 0


async def test_pending_stop_counts_position_cycles_not_ticks():
    """تِكّات ميتاتريدر كثيرة: لا تُستنفد مهلة «الجزء لم يُغلق» قبل دورة النقصان."""
    atom, bus = await _new()
    await atom._on_positions(_us30(51357.10))
    for i in range(40):
        await bus.deliver("feed.mt5.tick", _mt5(51357.2 + i * 0.01, 51357.9 + i * 0.01))
    assert atom._stop_withheld == 0, "احتُجز الوقف بعدّ التِّكّات"
    await atom._on_positions(_us30(51357.6, volume=0.7))
    assert len(_outs(bus, "MODIFY_SL")) == 1


async def test_single_target_decision_survives_restore():
    atom, bus = await _new()
    await bus.deliver("feed.mt5.tick", _mt5(20000.0, 20000.9, symbol="USTEC"))
    await atom._on_positions({"positions": [{"account_id": "A", "ticket": 5, "symbol": "USTEC",
                                             "side": "BUY", "volume": 1.0, "entry_price": 20000.9,
                                             "current_price": 20000.0, "stop_loss": 19976.9,
                                             "take_profit": 20003.09}]})
    snap = await atom.snapshot()
    fresh, _bus2 = await _new()
    await fresh.restore(snap)
    assert fresh._tracked["5"]["single"] is True and fresh._tracked["5"]["done"] is True
