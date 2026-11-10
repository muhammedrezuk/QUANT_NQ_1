# ٢٠٢٦-١٠-٠٨ (ختم المالك «nq»): عيبان في الأثلاث الحيّة قيسا بتشغيل الذرّة الحقيقيّة:
#   ١. قصُّ الحجم إلى خطوته بقسمةٍ عائمة: ‎0.3 / 0.1 = 2.9999… فيُقصّ إلى 0.2 — عقد 0.9
#      كان يُغلق 0.2 ثمّ 0.3 ثمّ 0.4 بدل 0.3 لكلّ ثلث (٢٧ حجمًا من ١٠٠ على خطوة 0.1).
#   ٢. نقلُ الوقف لا يُقارَن بالقائم عند الوسيط: وقفٌ شُدَّ يدويًّا إلى 20010 ثمّ بلغ
#      السعر الهدف الأوّل فخرج وقف التعادل 20000 فأرخاه — «الوقف لا يُوسَّع» (٠٩-١٨).
import os
import sys

from pathlib import Path as _Path
sys.path.insert(0, str(_Path(__file__).resolve().parents[4]))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.contracts.atom import AtomContext  # noqa: E402
import importlib.util as _ilu  # noqa: E402

_spec = _ilu.spec_from_file_location(
    "_atom574_fix_1008", _Path(__file__).resolve().parents[1] / "atom.py")
_mod = _ilu.module_from_spec(_spec)
sys.modules["_atom574_fix_1008"] = _mod
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


async def _new():
    bus = _Bus()
    atom = Atom()
    await atom.initialize(AtomContext(atom_id=574, config=dict(CFG), logger=_Log(),
                                      publish=bus.publish, subscribe=bus.subscribe))
    await atom.start()
    # مواصفة الناسداك كما ينشرها الوسيط: أصغر لوت 0.1 وخطوته 0.1.
    await atom._on_specs({"symbols": [
        {"symbol": "USTEC", "volume_min": 0.1, "volume_step": 0.1, "tick_value": 0.01,
         "tick_size": 0.01, "point": 0.01, "stops_level": 0, "freeze_level": 0}]})
    return atom, bus


def _nq(current, volume, stop, side="BUY", ticket=1008):
    entry = 20000.0
    target = 20090.0 if side == "BUY" else 19910.0
    return {"positions": [{"account_id": "A", "ticket": ticket, "symbol": "USTEC",
                           "side": side, "volume": volume, "entry_price": entry,
                           "current_price": current, "stop_loss": stop,
                           "take_profit": target}]}


def _outs(bus, action):
    return [p for n, p in bus.published if n == EVENT_OUT and p.get("action") == action]


async def _walk_thirds(volume):
    """شراء ناسداك: دخول 20000 · وقف 19970 · هدف 20090 ⟸ الأثلاث 20030 · 20060 · 20090."""
    atom, bus = await _new()
    await atom._on_positions(_nq(20030.0, volume, 19970.0))
    first = _outs(bus, "CLOSE_PARTIAL")[-1]["volume"]
    left = round(volume - first, 2)
    await atom._on_positions(_nq(20031.0, left, 19970.0))          # المنصّة ترى الإغلاق
    await atom._on_positions(_nq(20060.0, left, 20000.0))
    second = _outs(bus, "CLOSE_PARTIAL")[-1]["volume"]
    left2 = round(left - second, 2)
    await atom._on_positions(_nq(20061.0, left2, 20000.0))
    await atom._on_positions(_nq(20090.0, left2, 20030.0))
    last = _outs(bus, "CLOSE")[-1]["volume"]
    return (first, second, last), [s["stop_loss"] for s in _outs(bus, "MODIFY_SL")]


async def test_thirds_of_0_9_lot_are_0_3_each():
    volumes, stops = await _walk_thirds(0.9)
    assert volumes == (0.3, 0.3, 0.3), volumes                  # كان (0.2, 0.3, 0.4)
    assert stops == [20000.0, 20030.0], stops                   # تعادل ثمّ الهدف الأوّل


async def test_thirds_of_2_1_lot_are_0_7_each():
    volumes, _ = await _walk_thirds(2.1)
    assert volumes == (0.7, 0.7, 0.7), volumes                  # كان (0.6, 0.7, 0.8)


async def test_thirds_of_3_3_lot_unchanged():
    volumes, stops = await _walk_thirds(3.3)                    # كان صحيحًا ويبقى
    assert volumes == (1.1, 1.1, 1.1) and stops == [20000.0, 20030.0], (volumes, stops)


async def test_floor_still_never_rounds_up():
    # السماح يصلح القسمة العائمة ولا يرفع الحجم: ثلث 1.0 = 0.33 ⟸ 0.3 لا 0.4.
    atom, bus = await _new()
    await atom._on_positions(_nq(20030.0, 1.0, 19970.0))
    assert _outs(bus, "CLOSE_PARTIAL")[-1]["volume"] == 0.3


async def test_breakeven_does_not_loosen_a_tighter_held_stop():
    atom, bus = await _new()
    await atom._on_positions(_nq(20010.0, 0.9, 19970.0))
    # المالك شدّ الوقف يدويًّا إلى 20010، ثمّ بلغ السعر الهدف الأوّل.
    await atom._on_positions(_nq(20030.0, 0.9, 20010.0))
    assert _outs(bus, "CLOSE_PARTIAL")[-1]["volume"] == 0.3
    await atom._on_positions(_nq(20031.0, 0.6, 20010.0))
    assert not _outs(bus, "MODIFY_SL"), "أُرخي الوقف القائم 20010 إلى التعادل 20000"
    assert atom._stop_kept == 1 and "20010" in atom._last_kept, atom._last_kept
    # الهدف الثاني يطلب 20030 — أشدّ من القائم ⟸ يُرسَل.
    await atom._on_positions(_nq(20060.0, 0.6, 20010.0))
    await atom._on_positions(_nq(20061.0, 0.3, 20010.0))
    assert [s["stop_loss"] for s in _outs(bus, "MODIFY_SL")] == [20030.0]
    health = await atom.health_check()
    assert "القائم_أشدّ=1" in health.message, health.message


async def test_sell_breakeven_does_not_loosen_a_tighter_held_stop():
    atom, bus = await _new()
    await atom._on_positions(_nq(19990.0, 0.9, 20030.0, side="SELL"))
    await atom._on_positions(_nq(19970.0, 0.9, 19990.0, side="SELL"))
    assert _outs(bus, "CLOSE_PARTIAL")[-1]["volume"] == 0.3
    await atom._on_positions(_nq(19969.0, 0.6, 19990.0, side="SELL"))
    assert not _outs(bus, "MODIFY_SL") and atom._stop_kept == 1


async def test_looser_held_stop_still_moves_to_breakeven():
    # القائم أرخى من التعادل (الوقف الأصليّ) ⟸ ينتقل كما أمر المالك، بلا تغيير.
    atom, bus = await _new()
    await atom._on_positions(_nq(20030.0, 0.9, 19970.0))
    await atom._on_positions(_nq(20031.0, 0.6, 19970.0))
    assert [s["stop_loss"] for s in _outs(bus, "MODIFY_SL")] == [20000.0]
    assert atom._stop_kept == 0
