# ٢٠٢٦-١٠-٠٧ (ختم المالك «nq»): «صفقة 1/3: هدف أوّل نقل وقف على دخول وإغلاق ثلث عقد، هدف ثاني إغلاق نصف باقي
# من عقد، هدف ثالث خروج — 50 مرّة شرحتها… ثبّتها بكلّ مكان، ما في غيرها… على كل رموز».
# الافتراض: الأثلاث وحدها لكلّ الرموز — لا خطّة مستويات ولا تأمين عند 1R ولا تتبّع؛ والهدف من الساعة و4س بلا سقف.
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_levels_2026_10_05 import (PAST, _closes, _mod, _new, _outs, partial_levels)  # noqa: E402,F401
from shared.structure_exits import StructureBook  # noqa: E402


def _nq(current, volume=1.2, stop=31207.56):
    return {"positions": [{"account_id": "A", "ticket": 11, "symbol": "USTEC", "side": "BUY",
                           "volume": volume, "entry_price": 31277.4, "current_price": current,
                           "stop_loss": stop, "take_profit": 31487.4}]}


async def _nasdaq():
    atom, bus = await _new(with_ladder=False)
    await atom._on_specs({"symbols": [{"symbol": "USTEC", "volume_min": 0.1, "volume_step": 0.1,
                                       "tick_value": 0.01, "tick_size": 0.01, "point": 0.01,
                                       "stops_level": 0, "freeze_level": 0}]})
    await bus.deliver("feed.mt5.tick", {"account_id": "A", "symbol": "USTEC", "bid": 31277.0, "ask": 31278.0})
    await bus.deliver("structure.levels.state", {"symbol": "USTEC", "daily_closes": _closes(True), "frames": {
        "1h": {"highs": [[31600.0, PAST]], "lows": []},
        "5m": {"highs": [[31300.0, PAST]], "lows": [[31207.0, PAST], [31260.0, time.time() - 5.0]]}}})
    return atom, bus


async def test_defaults_are_thirds_only():
    assert partial_levels.PROTECT_SYMBOLS == frozenset() and partial_levels.LEVEL_PLAN_ON is False


async def test_nasdaq_trade_runs_the_owner_thirds_exactly():
    """هدف 31,487.4 (210 نقطة = 3R): الأوّل 31,347.4 · الثاني 31,417.4 · الثالث 31,487.4."""
    atom, bus = await _nasdaq()
    await atom._on_positions(_nq(31300.0))
    assert atom._tracked["11"]["levels"] == []                 # لا خطّة مستويات
    assert ("management.level_plan.state", {"tickets": ["11"]}) in bus.published   # ٥٧٢ يتنحّى
    # قاعٌ أعلى على 5د (31,260) وربحٌ دون الهدف الأوّل: الوقف لا يتحرّك (لا تتبّع، لا تعادل عند 1R).
    await atom._on_positions(_nq(31340.0))
    assert not _outs(bus), _outs(bus)
    # ١) الهدف الأوّل: ثلث العقد، ثمّ الوقف إلى الدخول بعد أن يُرى الحجم ناقصًا.
    await atom._on_positions(_nq(31347.5))
    assert [round(o["volume"], 2) for o in _outs(bus, "CLOSE_PARTIAL")] == [0.4]
    assert not _outs(bus, "MODIFY_SL")
    await atom._on_positions(_nq(31348.0, volume=0.8))
    be = _outs(bus, "MODIFY_SL")
    assert len(be) == 1 and be[0]["reason"] == _mod.REASON_BREAKEVEN and 31277.4 <= be[0]["stop_loss"] < 31278.5, be
    # ٢) الهدف الثاني: نصف الباقي، ثمّ الوقف إلى الهدف الأوّل.
    await atom._on_positions(_nq(31417.5, volume=0.8, stop=be[0]["stop_loss"]))
    assert [round(o["volume"], 2) for o in _outs(bus, "CLOSE_PARTIAL")] == [0.4, 0.4]
    await atom._on_positions(_nq(31418.0, volume=0.4, stop=be[0]["stop_loss"]))
    lock = _outs(bus, "MODIFY_SL")[-1]
    assert abs(lock["stop_loss"] - 31347.4) < 1e-6, lock
    # ٣) الهدف الثالث: خروجٌ كامل.
    await atom._on_positions(_nq(31487.5, volume=0.4, stop=31347.4))
    assert _outs(bus, "CLOSE")[-1]["volume"] == 0.4


def test_target_is_the_nearest_level_giving_3r_or_more():
    """١٠-٠٧ (ختم المالك «nq» على (ب)): الهدف أقرب مستوى يعطي 1:3 فأكثر — لا الأبعد.
    دخول 4000 · وقف 3990: 4020 دون 1:3 · **4035 أوّل ما يعطي 3.46** · 4060 و4100 أبعد فلا تُؤخذ."""
    book = StructureBook()
    book.on_ladder({"symbol": "XAUUSD", "frames": {"1h": {"highs": [[p, PAST] for p in
                                                             (4020.0, 4035.0, 4040.0, 4060.0, 4100.0)],
                                                            "lows": []}}})
    levels = book.exit_levels(symbol="XAUUSD", side="buy", entry=4000.0, stop=3990.0,
                              spread=0.1, until=time.time())
    assert [p for p, *_ in levels] == [4035.0], levels
    # وفي «منطقة بلا مستوى سابق» الهدف 3R وحده.
    book.on_ladder({"symbol": "XAUUSD", "frames": {"1h": {"highs": [[3950.0, PAST]], "lows": []}}})
    levels = book.exit_levels(symbol="XAUUSD", side="buy", entry=4000.0, stop=3990.0,
                              spread=0.1, until=time.time())
    assert [(f, r) for _p, f, _a, r in levels] == [("discovery", 3.0)], levels


def test_target_from_hour_and_four_hour_not_daily_and_no_cap():
    """بيع ناسداك: قاعٌ يوميّ 22,782.90 لا يدخل؛ والهدف قاع الساعة 31,100 (≈5R) كما هو بلا سقف ولا محطّة."""
    book = StructureBook()
    book.on_ladder({"symbol": "USTEC", "daily_closes": _closes(False), "frames": {
        "1h": {"highs": [], "lows": [[31100.0, PAST]]},
        "1d": {"highs": [], "lows": [[22782.9, PAST]]},
        "15m": {"highs": [[31290.0, PAST]], "lows": []}}})
    levels = book.exit_levels(symbol="USTEC", side="sell", entry=31260.0, stop=31291.0,
                              spread=1.0, until=time.time())
    assert [(p, f) for p, f, _a, _r in levels] == [(31100.0, "1h")], levels
    why, setup = book.exits(symbol="USTEC", side="sell", entry=31260.0, spread=1.0, pad=1.0, now=time.time())
    assert why == "" and setup["target_price"] == 31100.0, (why, setup)
