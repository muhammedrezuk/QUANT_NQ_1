# ٢٠٢٦-١٠-٠٥ (ختم المالك «nq اعتمدناها»): الإدارة على مستويات التحليل.
#   · أوّل مستوىً في الطريق يحقّق 1:3: ثلث العقد، والوقف إلى الدخول.
#   · المستوى التالي: نصف الباقي، والوقف إلى المستوى الأوّل.
#   · الثلث الأخير إلى أبعد مستوى (هدف الأمر)، ووقفه يتبع قيعان/قمم الربع ساعة ويضيق فقط.
import os
import sys
import time

from pathlib import Path as _Path
sys.path.insert(0, str(_Path(__file__).resolve().parents[4]))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.contracts.atom import AtomContext  # noqa: E402
from shared.structure_exits import StructureBook  # noqa: E402
import shared.structure_exits as _se  # noqa: E402
import importlib.util as _ilu  # noqa: E402

_spec = _ilu.spec_from_file_location(
    "_atom574_levels", _Path(__file__).resolve().parents[1] / "atom.py")
_mod = _ilu.module_from_spec(_spec)
sys.modules["_atom574_levels"] = _mod
_spec.loader.exec_module(_mod)
Atom = _mod.Atom
EVENT_OUT = _mod.EVENT_OUT
import partial_levels  # noqa: E402

CFG = {"partial_at_r": 1.0, "partial_fraction": 0.5, "min_partial_lot": 0.01}
PAST = time.time() - 3600.0


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


def _ladder(highs_1h, lows_15m=()):
    return {"symbol": "XAUUSD", "frames": {
        "1h": {"highs": [[p, PAST] for p in highs_1h], "lows": []},
        "15m": {"highs": [], "lows": [[p, at] for p, at in lows_15m]}}}


async def _new(with_ladder=True):
    bus = _Bus()
    atom = Atom()
    await atom.initialize(AtomContext(atom_id=574, config=dict(CFG), logger=_Log(),
                                      publish=bus.publish, subscribe=bus.subscribe))
    await atom.start()
    await atom._on_specs({"symbols": [
        {"symbol": sym, "volume_min": vmin, "volume_step": vmin, "tick_value": tv,
         "tick_size": 0.01, "point": 0.01, "stops_level": 0, "freeze_level": 0}
        for sym, vmin, tv in (("XAUUSD", 0.01, 1.0), ("US30", 0.1, 0.01))]})
    await bus.deliver("feed.mt5.tick", {"account_id": "A", "symbol": "XAUUSD",
                                        "bid": 4000.0, "ask": 4000.1})
    if with_ladder:
        await bus.deliver("structure.levels.state", _ladder([4020.0, 4035.0, 4040.0, 4060.0, 4100.0]))
    return atom, bus


def _gold(current, volume=0.3, stop=3990.0, ticket=1):
    return {"positions": [{"account_id": "A", "ticket": ticket, "symbol": "XAUUSD",
                           "side": "BUY", "volume": volume, "entry_price": 4000.0,
                           "current_price": current, "stop_loss": stop,
                           "take_profit": 4100.0}]}


def _outs(bus, action=None):
    return [p for n, p in bus.published if n == EVENT_OUT and (action is None or p.get("action") == action)]


def test_exit_levels_farthest_target_and_one_r_spacing(monkeypatch):
    """الهدف أبعد مستوىً ≥1:3، ومستوىً لا يبعد عن سابقه 1R واحدٌ لا اثنان."""
    monkeypatch.setattr(_se, "TARGET_PICK", "far")   # ١٠-٠٧: الافتراض «أقرب مستوى ≥1:3» — هنا «الأبعد» صراحةً
    book = StructureBook()
    book.on_ladder(_ladder([4020.0, 4035.0, 4040.0, 4060.0, 4100.0]))
    levels = book.exit_levels(symbol="XAUUSD", side="buy", entry=4000.0, stop=3990.0,
                              spread=0.1, until=time.time())
    prices = [p for p, _f, _a, _r in levels]
    # 4020 دون 1:3 · 4040 على بعد 5 من 4035 (أقلّ من 1R=10) فيُدمج · 4100 الأبعد آخرًا.
    assert prices == [4035.0, 4060.0, 4100.0], prices
    # ومستوىً وُلد بعد اللحظة لا يدخل.
    late = book.exit_levels(symbol="XAUUSD", side="buy", entry=4000.0, stop=3990.0,
                            spread=0.1, until=PAST - 1.0)
    assert late == []


def test_price_discovery_builds_3r_6r_9r_legs_only_above_all_known_highs(monkeypatch):
    """٢٠٢٦-١٠-٠٦ (ختم المالك «حلّ القمّة التاريخيّة. NQ»): كلّ القمم المعروفة تحت الدخول ⟸ محطّات 3R·6R·9R."""
    monkeypatch.setattr(_se, "TARGET_PICK", "far")   # ١٠-٠٧: الافتراض «أقرب مستوى ≥1:3» — هنا «الأبعد» صراحةً
    book = StructureBook()
    book.on_ladder(_ladder([3950.0, 3980.0], lows_15m=[(3992.0, PAST)]))
    levels = book.exit_levels(symbol="XAUUSD", side="buy", entry=4000.0, stop=3990.0,
                              spread=0.1, until=time.time())
    # ١٥:٤x بختم المالك: محطّةٌ واحدة عند 3R ثمّ تتبّع، و9R سقف الأمر.
    assert [f for _p, f, _a, _r in levels] == ["discovery"] * 2, levels
    assert [r for _p, _f, _a, r in levels] == [3.0, 9.0]
    for price, _f, _a, multiple in levels:
        net = (price - 4000.0 - 0.1) / (10.0 + 0.1)
        assert net >= multiple, (price, net)
    # قمّةٌ واحدة فوق الدخول دون 1:3 ⟸ مستوىً حقيقيّ في الطريق، فلا محطّات (القاعدة القديمة).
    book.on_ladder(_ladder([3950.0, 4015.0]))
    assert book.exit_levels(symbol="XAUUSD", side="buy", entry=4000.0, stop=3990.0,
                            spread=0.1, until=time.time()) == []
    # سلّمٌ فارغ حتى اللحظة ليس قمّةً تاريخيّة بل جهلٌ بالبنية.
    assert StructureBook().exit_levels(symbol="XAUUSD", side="buy", entry=4000.0, stop=3990.0,
                                       spread=0.1, until=time.time()) == []


def test_price_discovery_exits_carry_the_9r_target_and_the_flag(monkeypatch):
    """على الناسداك (إذن الاتّجاه اليوميّ للذهب وحده)."""
    monkeypatch.setattr(_se, "TARGET_PICK", "far")   # ١٠-٠٧: الافتراض «أقرب مستوى ≥1:3» — هنا «الأبعد» صراحةً
    book = StructureBook()
    book.on_ladder(dict(_ladder([3950.0, 3980.0], lows_15m=[(3992.0, PAST)]), symbol="USTEC",
                        daily_closes=_closes(True)))
    why, setup = book.exits(symbol="USTEC", side="buy", entry=4000.0, spread=0.1,
                            pad=2.0, now=time.time())
    assert why == "", (why, setup)
    assert setup["invalidation_price"] == 3990.0
    assert setup["evidence"]["price_discovery"] is True
    assert setup["evidence"]["target_frame"] == "discovery"
    assert setup["target_price"] > 4000.0 + 9 * 10.1


def _closes(rising=True):
    """إغلاقات يوميّة — إذن الاتّجاه اليوميّ على الناسداك منذ ١٠-٠٦ 17:3x (ختم المالك «NQ»)."""
    now = time.time()
    return [[now - (30 - i) * 86400.0, 30000.0 + (i if rising else -i) * 50.0] for i in range(25)]


def _ustec(highs_1h, lows_15m=(), lows_5m=(), highs_5m=()):
    frames = {"1h": {"highs": [[p, PAST] for p in highs_1h], "lows": []},
              "15m": {"highs": [], "lows": [[p, at] for p, at in lows_15m]}}
    if lows_5m or highs_5m:
        frames["5m"] = {"highs": [[p, at] for p, at in highs_5m], "lows": [[p, at] for p, at in lows_5m]}
    return {"symbol": "USTEC", "frames": frames, "daily_closes": _closes(True)}


def test_nasdaq_stop_and_trail_on_5m_with_15m_fallback():
    """٢٠٢٦-١٠-٠٦ (ختم المالك «NQ»): وقف الناسداك خلف آخر قاع خمس دقائق، والتتبّع عليها؛
    وسلّمٌ بلا خمس دقائق بعدُ يعود إلى الربع ساعة. والذهب على الربع ساعة كما كان."""
    book = StructureBook()
    book.on_ladder(_ustec([31000.0], lows_15m=[(31110.0, PAST)]))
    assert book.stop_frame("USTEC") == "15m"
    why, setup = book.exits(symbol="USTEC", side="buy", entry=31250.0, spread=1.0, pad=1.0, now=time.time())
    assert why == "" and setup["invalidation_price"] == 31109.0, (why, setup)
    book.on_ladder(_ustec([31000.0], lows_15m=[(31110.0, PAST)],
                          lows_5m=[(31200.0, PAST), (31225.0, PAST + 1)], highs_5m=[(31290.0, PAST)]))
    assert book.stop_frame("USTEC") == "5m"
    why, setup = book.exits(symbol="USTEC", side="buy", entry=31250.0, spread=1.0, pad=1.0, now=time.time())
    assert why == "" and setup["invalidation_price"] == 31224.0, (why, setup)
    assert setup["evidence"]["stop_frame"] == "5m" and setup["invalidation_source"] == "201:5m:swing_low"
    # وقف 26 ⟸ محطّة 3R ثمّ سقف 9R قريبان (لا 1,230 نقطة).
    assert setup["target_price"] < 31250.0 + 9 * 27 * 1.01 + 2
    assert book.trail_level(symbol="USTEC", side="buy", price=31300.0, until=time.time()) == 31225.0
    assert book.stop_frame("XAUUSD") == "15m"


def test_nasdaq_rides_both_sides_station_3r_then_far_level_capped_at_9r(monkeypatch):
    # ١٠-٠٧: ركوب الموجة والهدف اليوميّ مطفآن افتراضًا (الأثلاث وحدها، الهدف من الساعة و4س) — يُختبران بتشغيلهما.
    monkeypatch.setattr(_se, "RIDE_SYMBOLS", frozenset({"USTEC"}))
    monkeypatch.setattr(_se, "TARGET_FRAMES", ("1h", "4h", "1d"))
    monkeypatch.setattr(_se, "TARGET_PICK", "far")   # ١٠-٠٧: الافتراض «أقرب مستوى ≥1:3» — هنا «الأبعد» صراحةً
    """٢٠٢٦-١٠-٠٦ 16:1x (ختم المالك «NQ»): بيعٌ كان هدفه أبعد قاعٍ يوميّ 22,782.90 ⟸ محطّة 3R وسقف 9R."""
    book = StructureBook()
    book.on_ladder({"symbol": "USTEC", "frames": {
        "1h": {"highs": [], "lows": [[31100.0, PAST]]},
        "1d": {"highs": [], "lows": [[22782.9, PAST]]},
        "15m": {"highs": [[31290.0, PAST]], "lows": []}}, "daily_closes": _closes(False)})
    levels = book.exit_levels(symbol="USTEC", side="sell", entry=31260.0, stop=31291.0,
                              spread=1.0, until=time.time())
    assert [f for _p, f, _a, _r in levels] == ["ride", "ride_cap"], levels
    station, cap = levels[0][0], levels[1][0]
    assert 31260.0 - 3 * 32 * 1.01 - 2 < station < 31260.0 - 3 * 32
    assert 31260.0 - 9 * 32 * 1.01 - 2 < cap < 31260.0 - 9 * 32
    why, setup = book.exits(symbol="USTEC", side="sell", entry=31260.0, spread=1.0, pad=1.0, now=time.time())
    assert why == "" and setup["target_price"] == cap and setup["evidence"]["target_frame"] == "ride_cap", (why, setup)
    # مستوىً حقيقيّ دون السقف (≈5R) يبقى الهدف، والمحطّة 3R قبله.
    book.on_ladder({"symbol": "USTEC", "frames": {"1h": {"highs": [], "lows": [[31100.0, PAST]]}}})
    levels = book.exit_levels(symbol="USTEC", side="sell", entry=31260.0, stop=31291.0,
                              spread=1.0, until=time.time())
    assert [(round(p, 2), f) for p, f, _a, _r in levels][-1] == (31100.0, "1h"), levels
    assert levels[0][1] == "ride" and len(levels) == 2
    # والذهب على «أبعد مستوى» كما كان.
    gold = StructureBook()
    gold.on_ladder(_ladder([4020.0, 4035.0, 4040.0, 4060.0, 4100.0]))
    assert [p for p, *_ in gold.exit_levels(symbol="XAUUSD", side="buy", entry=4000.0, stop=3990.0,
                                             spread=0.1, until=time.time())] == [4035.0, 4060.0, 4100.0]


def test_nasdaq_setup_against_the_daily_trend_is_refused():
    """اتّجاه اليوم يقرّر الجهة: شراءٌ في يومٍ هابط يُرفض باسمه."""
    book = StructureBook()
    book.on_ladder(dict(_ustec([31000.0], lows_15m=[(31110.0, PAST)]), daily_closes=_closes(False)))
    why, _detail = book.exits(symbol="USTEC", side="buy", entry=31250.0, spread=1.0, pad=1.0, now=time.time())
    assert why == "STRUCTURE_TREND_AGAINST", why


def test_min_stop_pips_per_symbol():
    # ٢٠٢٦-١٠-١٧ (ختم المالك «nq»: «بِب على كلّ السستم، ما في شي اسمه نقاط أساس»): الحدّ بالبِب لكلّ رمز.
    from shared.trade_setup import min_stop_pips
    assert min_stop_pips("USTEC") == 9.0 and min_stop_pips("ustec") == 9.0
    # ١٠-١٧ «nq» بأرقام المالك: الذهب 15 · البتكوين 50 · الداو 10 · كلّ العملات 5.
    assert min_stop_pips("US30") == 10.0 and min_stop_pips("XAUUSD") == 15.0 and min_stop_pips("BTCUSD") == 50.0
    assert min_stop_pips("EURUSD") == 5.0 and min_stop_pips("USDJPY") == 5.0 and min_stop_pips("US500") == 8.0
    assert min_stop_pips(None) == 10.0


async def test_level_plan_thirds_on_levels_then_structural_trail(monkeypatch):
    # ٢٠٢٦-١٠-٠٦: الذهب صار في «أمّن ثمّ احجز» (`PROTECT_SYMBOLS`) — خطّة المستويات تُختبر بإطفائه.
    monkeypatch.setattr(partial_levels, "PROTECT_SYMBOLS", frozenset())
    monkeypatch.setattr(partial_levels, "LEVEL_PLAN_ON", True)   # ١٠-٠٧: مطفأة افتراضًا
    monkeypatch.setattr(_se, "TARGET_PICK", "far")   # ١٠-٠٧: الافتراض «أقرب مستوى ≥1:3» — هنا «الأبعد» صراحةً
    atom, bus = await _new()
    await atom._on_positions(_gold(4000.05))
    st = atom._tracked["1"]
    assert st["levels"] == [4035.0, 4060.0], st["levels"]
    assert ("management.level_plan.state", {"tickets": ["1"]}) in bus.published
    assert not _outs(bus), "أُرسل شيءٌ قبل أوّل مستوى"

    # ١) أوّل مستوى (4035 = 3.5R): ثلث العقد، والوقف إلى التعادل بعد أن يُرى الحجم ناقصًا.
    await atom._on_positions(_gold(4035.0))
    closes = _outs(bus, "CLOSE_PARTIAL")
    assert len(closes) == 1 and closes[0]["volume"] == 0.1, closes
    assert not _outs(bus, "MODIFY_SL"), "تحرّك الوقف قبل أن يُغلق الجزء"
    await atom._on_positions(_gold(4036.0, volume=0.2))
    be = _outs(bus, "MODIFY_SL")
    assert len(be) == 1 and be[0]["reason"] == _mod.REASON_BREAKEVEN and 4000.0 <= be[0]["stop_loss"] < 4001.0, be

    # ٢) المستوى الثاني (4060): نصف الباقي، والوقف إلى المستوى الأوّل.
    await atom._on_positions(_gold(4060.0, volume=0.2, stop=be[0]["stop_loss"]))
    closes = _outs(bus, "CLOSE_PARTIAL")
    assert len(closes) == 2 and closes[1]["volume"] == 0.1, closes
    await atom._on_positions(_gold(4061.0, volume=0.1, stop=be[0]["stop_loss"]))
    lock = _outs(bus, "MODIFY_SL")[-1]
    assert lock["stop_loss"] == 4035.0 and lock["reason"] == partial_levels.REASON_LOCK_LEVEL, lock

    # ٣) الثلث الأخير: قاعٌ مؤكَّد جديد على الربع ساعة (4055) — الوقف يتبعه بكلفة العبور.
    await bus.deliver("structure.levels.state",
                      _ladder([4020.0, 4035.0, 4040.0, 4060.0, 4100.0],
                              lows_15m=[(3995.0, PAST), (4055.0, time.time() - 5.0)]))
    await atom._on_positions(_gold(4070.0, volume=0.1, stop=4035.0))
    trail = _outs(bus, "MODIFY_SL")[-1]
    assert trail["reason"] == partial_levels.REASON_TRAIL and 4035.0 < trail["stop_loss"] < 4055.0, trail
    # ولا يتّسع ولا يُكرَّر: الدورة التالية بالسعر نفسه لا ترسل شيئًا.
    sent = len(_outs(bus, "MODIFY_SL"))
    await atom._on_positions(_gold(4069.0, volume=0.1, stop=trail["stop_loss"]))
    assert len(_outs(bus, "MODIFY_SL")) == sent
    # وتحديث السلّم لا يبدّل خطّة صفقةٍ مفتوحة.
    assert atom._tracked["1"]["levels"] == [4035.0, 4060.0]

    # ٤) الهدف (4100): خروجٌ كامل.
    await atom._on_positions(_gold(4100.0, volume=0.1, stop=trail["stop_loss"]))
    assert _outs(bus, "CLOSE")[-1]["volume"] == 0.1


def _nq_ladder(lows_5m):
    return {"symbol": "USTEC", "daily_closes": _closes(True), "frames": {
        "1h": {"highs": [[31000.0, PAST]], "lows": []},
        "15m": {"highs": [], "lows": [[31110.0, PAST]]},
        "5m": {"highs": [[31300.0, PAST]], "lows": [[p, at] for p, at in lows_5m]}}}


def _nq(current, volume=1.2, stop=31207.56):
    return {"positions": [{"account_id": "A", "ticket": 5, "symbol": "USTEC", "side": "BUY",
                           "volume": volume, "entry_price": 31277.4, "current_price": current,
                           "stop_loss": stop, "take_profit": 31876.42}]}


async def test_nasdaq_protect_be_at_1r_then_third_and_lock_1r_at_2r_then_trail_5m(monkeypatch):
    monkeypatch.setattr(partial_levels, "PROTECT_SYMBOLS", frozenset({"USTEC", "BTCUSD", "XAUUSD"}))  # ١٠-٠٧: مطفأ افتراضًا
    """٢٠٢٦-١٠-٠٦ (ختم المالك «NQ» بعد «وصل لا ربح دبل ستوب… لا أمن ولا حجز من أرباح»)."""
    atom, bus = await _new(with_ladder=False)
    await atom._on_specs({"symbols": [{"symbol": "USTEC", "volume_min": 0.1, "volume_step": 0.1,
                                       "tick_value": 0.01, "tick_size": 0.01, "point": 0.01,
                                       "stops_level": 0, "freeze_level": 0}]})
    await bus.deliver("feed.mt5.tick", {"account_id": "A", "symbol": "USTEC", "bid": 31277.0, "ask": 31278.0})
    await bus.deliver("structure.levels.state", _nq_ladder([(31207.0, PAST)]))
    await atom._on_positions(_nq(31300.0))
    assert abs(atom._tracked["5"]["risk"] - 69.84) < 1e-6 and not _outs(bus)
    # ١) +1R (31,350 = +72.6): الوقف إلى التعادل بلا إغلاق.
    await atom._on_positions(_nq(31350.0))
    be = _outs(bus, "MODIFY_SL")
    assert len(be) == 1 and be[0]["reason"] == partial_levels.REASON_PROTECT_BE, be
    assert 31277.4 <= be[0]["stop_loss"] < 31278.5 and not _outs(bus, "CLOSE_PARTIAL")
    await atom._on_positions(_nq(31351.0, stop=be[0]["stop_loss"]))
    assert len(_outs(bus, "MODIFY_SL")) == 1, "أُعيد التعادل"
    # ٢) +2R (31,420): ثلث المتبقّي، ثمّ الوقف إلى +1R بعد أن يُرى الحجم ناقصًا.
    await atom._on_positions(_nq(31420.0, stop=be[0]["stop_loss"]))
    closes = _outs(bus, "CLOSE_PARTIAL")
    assert len(closes) == 1 and abs(closes[0]["volume"] - 0.4) < 1e-9, closes
    assert len(_outs(bus, "MODIFY_SL")) == 1, "تحرّك الوقف قبل أن يُغلق الثلث"
    await atom._on_positions(_nq(31421.0, volume=0.8, stop=be[0]["stop_loss"]))
    lock = _outs(bus, "MODIFY_SL")[-1]
    assert lock["reason"] == partial_levels.REASON_PROTECT_LOCK and abs(lock["stop_loss"] - 31347.24) < 1e-6, lock
    # ٣) قاعُ خمس دقائق جديد (31,395): الوقف يتبعه، ولا يتّسع.
    await bus.deliver("structure.levels.state", _nq_ladder([(31207.0, PAST), (31395.0, time.time() - 5.0)]))
    await atom._on_positions(_nq(31440.0, volume=0.8, stop=31347.24))
    trail = _outs(bus, "MODIFY_SL")[-1]
    assert trail["reason"] == partial_levels.REASON_TRAIL and 31347.24 < trail["stop_loss"] < 31395.0, trail
    # والمرحلة تُحفظ: إقلاعٌ لا يعيد الثلث.
    fresh, _b = await _new(with_ladder=False)
    await fresh.restore(await atom.snapshot())
    assert fresh._tracked["5"]["protect"] == 2


async def test_trail_from_entry_on_higher_low_before_1r(monkeypatch):
    monkeypatch.setattr(partial_levels, "PROTECT_SYMBOLS", frozenset({"USTEC", "BTCUSD", "XAUUSD"}))  # ١٠-٠٧: مطفأ افتراضًا
    """٢٠٢٦-١٠-٠٦ 20:1x (ختم المالك «nq»): قاعٌ أعلى مؤكَّد (31,231) والوقف 31,207 ⟸ يُشدّ قبل +1R."""
    atom, bus = await _new(with_ladder=False)
    await atom._on_specs({"symbols": [{"symbol": "USTEC", "volume_min": 0.1, "volume_step": 0.1,
                                       "tick_value": 0.01, "tick_size": 0.01, "point": 0.01,
                                       "stops_level": 0, "freeze_level": 0}]})
    await bus.deliver("feed.mt5.tick", {"account_id": "A", "symbol": "USTEC", "bid": 31277.0, "ask": 31278.0})
    await bus.deliver("structure.levels.state", _nq_ladder([(31207.0, PAST)]))
    await atom._on_positions(_nq(31300.0))
    assert not _outs(bus)
    await bus.deliver("structure.levels.state", _nq_ladder([(31207.0, PAST), (31231.25, time.time() - 5.0)]))
    await atom._on_positions(_nq(31330.0))
    trail = _outs(bus, "MODIFY_SL")
    assert len(trail) == 1 and trail[0]["reason"] == partial_levels.REASON_TRAIL, trail
    assert 31207.56 < trail[0]["stop_loss"] < 31231.25
    # ثمّ +1R: التعادل فوقه (أضيق) يُرسل؛ ولا يتّسع بعدها.
    await atom._on_positions(_nq(31350.0, stop=trail[0]["stop_loss"]))
    assert _outs(bus, "MODIFY_SL")[-1]["reason"] == partial_levels.REASON_PROTECT_BE


async def test_bitcoin_sell_at_1_28r_moves_to_breakeven(monkeypatch):
    monkeypatch.setattr(partial_levels, "PROTECT_SYMBOLS", frozenset({"USTEC", "BTCUSD", "XAUUSD"}))  # ١٠-٠٧: مطفأ افتراضًا
    """صفقة المالك: بيع بتكوين 0.18 على 86,211.69 بوقف 86,728.21 — بلغ 85,550 (+661 ≈ 1.28R)."""
    atom, bus = await _new(with_ladder=False)
    await atom._on_specs({"symbols": [{"symbol": "BTCUSD", "volume_min": 0.01, "volume_step": 0.01,
                                       "tick_value": 0.01, "tick_size": 0.01, "point": 0.01,
                                       "stops_level": 0, "freeze_level": 0}]})
    await bus.deliver("feed.mt5.tick", {"account_id": "A", "symbol": "BTCUSD", "bid": 85550.0, "ask": 85560.0})
    await bus.deliver("structure.levels.state", {"symbol": "BTCUSD", "frames": {
        "1h": {"highs": [], "lows": [[84537.01, PAST], [83849.35, PAST]]},
        "15m": {"highs": [[86700.0, PAST]], "lows": []}}})
    pos = {"positions": [{"account_id": "A", "ticket": 7, "symbol": "BTCUSD", "side": "SELL", "volume": 0.18,
                          "entry_price": 86211.69, "current_price": 85560.0, "stop_loss": 86728.21,
                          "take_profit": 57693.44}]}
    await atom._on_positions(pos)
    be = _outs(bus, "MODIFY_SL")
    assert be and be[-1]["reason"] == partial_levels.REASON_PROTECT_BE, be
    # ٢٠٢٦-١٠-٢٦ (ختم المالك «NQ»: «يضاف سبريد»): البيع يُؤمَّن تحت الدخول بالسبريد الحاضر 10 (البتكوين بلا عمولة).
    assert abs(be[-1]["stop_loss"] - (86211.69 - 10.0)) < 1e-6 and not _outs(bus, "CLOSE_PARTIAL")


async def test_single_level_and_other_symbols_stay_on_thirds():
    """هدفٌ بلا مستوىً وسيط، أو رمزٌ بلا بنية: الأثلاث كما كانت."""
    atom, bus = await _new(with_ladder=False)
    await bus.deliver("structure.levels.state", _ladder([4100.0]))
    await atom._on_positions(_gold(4000.05))
    assert atom._tracked["1"]["levels"] == []
    await atom._on_positions({"positions": [{"account_id": "A", "ticket": 9, "symbol": "US30",
                                             "side": "BUY", "volume": 1.0, "entry_price": 100.0,
                                             "current_price": 100.0, "stop_loss": 90.0,
                                             "take_profit": 130.0}]})
    assert atom._tracked["9"]["levels"] == []
    # الأثلاث: ثلث الطريق إلى الهدف (1:3 ⟸ 1R) يُغلق الثلث كما كان.
    await atom._on_positions(_gold(4033.4))
    assert _outs(bus, "CLOSE_PARTIAL")[0]["volume"] == 0.1


async def test_plan_waits_for_the_ladder_then_falls_back_to_thirds(monkeypatch):
    monkeypatch.setattr(partial_levels, "LEVEL_PLAN_ON", True)  # ١٠-٠٧: مطفأة افتراضًا
    """بلا سلّم لا خطّة ولا أثلاث قبلها — وبعد مهلتها الأثلاث، فلا صفقة بلا إدارة."""
    atom, bus = await _new(with_ladder=False)
    for _ in range(partial_levels.PLAN_WAIT_CYCLES):
        await atom._on_positions(_gold(4040.0))
    assert atom._tracked["1"]["levels"] is None and not _outs(bus)
    await atom._on_positions(_gold(4040.0))
    assert atom._tracked["1"]["levels"] == [] and atom._plan_timeouts == 1
    await atom._on_positions(_gold(4040.0))
    assert _outs(bus, "CLOSE_PARTIAL"), "لم تعد الأثلاث بعد المهلة"


async def test_plan_survives_restart(monkeypatch):
    monkeypatch.setattr(partial_levels, "LEVEL_PLAN_ON", True)  # ١٠-٠٧: مطفأة افتراضًا
    monkeypatch.setattr(_se, "TARGET_PICK", "far")   # ١٠-٠٧: الافتراض «أقرب مستوى ≥1:3» — هنا «الأبعد» صراحةً
    atom, bus = await _new()
    await atom._on_positions(_gold(4000.05))
    state = await atom.snapshot()
    fresh, _bus2 = await _new(with_ladder=False)
    await fresh.restore(state)
    assert fresh._tracked["1"]["levels"] == [4035.0, 4060.0]
