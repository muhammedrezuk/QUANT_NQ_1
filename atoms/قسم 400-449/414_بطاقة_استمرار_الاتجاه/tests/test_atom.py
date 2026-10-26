"""بطاقة 414 — الحقائق الخام تدخل، والقرار بوقفه وهدفه يخرج؛ والمرفوضة تُؤرشف بسببها."""
import calendar
import time

import pytest

from shared import card_trend
from shared.owner_windows import owner_window
from tests.learning_test_support import make_atom

SYM = "USTEC"
# الأربعاء ٢٠٢٦-١٠-٠٧ 08:20 بتوقيت لندن (07:20 غرينتش) — داخل ذروة لندن.
AT = calendar.timegm(time.strptime("2026-10-07 07:20", "%Y-%m-%d %H:%M"))


async def _facts(atom, *, up=True, window_ok=True, open_symbols=(), peers_up=True):
    atom._clock = lambda: AT + 1.0          # الشمعة الثانية (إغلاقها AT) حيّة؛ الأولى زنادُها ماضٍ
    await atom._on_account({"account_id": "52992818", "broker": "RawTrading"})
    await atom._on_positions({"positions": [{"symbol": s} for s in open_symbols]})
    for frame in ("1h", "4h"):
        await atom._on_trend({"symbol": SYM, "timeframe": frame,
                              "metadata": {"close": 30000.0 if up else 29000.0, "ema_slow_value": 29500.0}})
        for peer in ("US500", "US30"):     # الأسواق المرتبطة في الجهة نفسها
            await atom._on_trend({"symbol": peer, "timeframe": frame,
                                  "metadata": {"close": 7000.0 if peers_up else 6000.0, "ema_slow_value": 6500.0}})
    await atom._on_vol({"symbol": SYM, "timeframe": "5m", "metadata": {"atr_14": 10.0}})
    await atom._on_vol({"symbol": SYM, "timeframe": "1d", "metadata": {"atr_14": 400.0}})
    # 5 د: قمّة 30010 مؤكَّدة ثمّ قاع 29980 بعدها (ارتداد)؛ والساعة: قمّة 30200 (≥ 3R وفي المتناول).
    await atom._on_ladder({"symbol": SYM, "frames": {
        "5m": {"highs": [[30010.0, AT - 1800]], "lows": [[29980.0, AT - 900]]},
        "1h": {"highs": [[30200.0, AT - 7200], [30020.0, AT - 3600]], "lows": []},
        "4h": {"highs": [], "lows": []}}})
    await atom._on_session({"symbol": SYM, "owner_window": "london_peak" if window_ok else None,
                            "window_at": AT})


async def _candle(atom, close, start):
    # ٢٠٢٦-١٠-٠٨ (ختم المالك «صلح NQ»): مدى الخمس دقائق يُنشر مع كلّ شمعة ببدايتها (153)، والبطاقة لا تقيّم
    # الزناد إلّا بمدى شمعته نفسها (تعريف القياس) — فيُغذّى هنا كما ينشره الحيّ.
    await atom._on_vol({"symbol": SYM, "timeframe": "5m", "metadata": {"atr_14": 10.0, "period_start": start}})
    await atom._on_candle({"symbol": SYM, "timeframe": "5m", "period_start": start, "close": close})


def test_owner_windows_follow_local_time():
    # الصيف: لندن 08:20 = 07:20 غرينتش · الشتاء: لندن 08:20 = 08:20 غرينتش.
    assert owner_window(AT) == "london_peak"
    winter = calendar.timegm(time.strptime("2026-01-14 08:20", "%Y-%m-%d %H:%M"))
    assert owner_window(winter) == "london_peak"
    assert owner_window(calendar.timegm(time.strptime("2026-01-14 07:20", "%Y-%m-%d %H:%M"))) is None
    # افتتاح أمريكا: 09:45 نيويورك = 13:45 غرينتش صيفًا.
    assert owner_window(calendar.timegm(time.strptime("2026-10-07 13:45", "%Y-%m-%d %H:%M"))) == "ny_open"
    # السبت لا نافذة.
    assert owner_window(calendar.timegm(time.strptime("2026-10-10 07:20", "%Y-%m-%d %H:%M"))) is None


def test_pure_card_levels():
    card = card_trend.evaluate(
        at=AT, close=30015.0, prev_close=30005.0,
        trend_1h={"close": 30000.0, "ema_slow_value": 29500.0},
        trend_4h={"close": 30000.0, "ema_slow_value": 29500.0},
        atr_5m=10.0, atr_1d=400.0,
        ladder={"5m": {"highs": [[30010.0, AT - 1800]], "lows": [[29980.0, AT - 900]]},
                "1h": {"highs": [[30200.0, AT - 7200], [30020.0, AT - 3600]], "lows": []}},
        window="london_peak", news_blocked=False)
    assert card["status"] == card_trend.OPEN and card["side"] == card_trend.BUY
    # الوقف أبعد من القاع (29980) ومن ضعفَي المدى (30015 − 20 = 29995) ⟸ 29980؛ الخطر 35.
    assert card["stop"] == pytest.approx(29980.0) and card["risk"] == pytest.approx(35.0)
    # 30020 أقرب من 3R (105) فيُتجاوز؛ 30200 = 185 ≥ 105 و≤ 1.5×400 ⟸ الهدف.
    assert card["target"] == pytest.approx(30200.0) and card["rr"] >= 3.0


@pytest.mark.asyncio
async def test_card_opens_and_approves_with_levels():
    _, atom, bus = await make_atom(414, {"symbols": [SYM]})
    await _facts(atom)
    await _candle(atom, 30005.0, AT - 600)          # تحت القمّة
    await _candle(atom, 30015.0, AT - 300)          # يغلق فوقها ⟸ كسر الهيكل
    cards = bus.payloads("strategy.card.state")
    assert cards[-1]["status"] == card_trend.OPEN
    assert "151_trend_1h" in cards[-1]["facts"] and "153_atr_5m" in cards[-1]["facts"]
    approved = bus.payloads("decision.approved.state")
    assert len(approved) == 1
    a = approved[0]
    assert a["approved"] is True and a["decision_side"] == "buy"
    assert a["invalidation_price"] == pytest.approx(29980.0) and a["target_price"] == pytest.approx(30200.0)
    for field in ("account_id", "broker", "symbol", "timeframe", "period_start", "decision_id"):
        assert a.get(field), field
    # النسبة الأساسيّة الصادقة للنافذة — للعلم على البطاقة (٢٠٢٦-١٠-٠٨).
    assert cards[-1]["base_rate"]["n"] == 136 and "ذروة لندن" in cards[-1]["base_rate_text"]
    setups = bus.payloads("strategy.setup.proposed")
    assert setups and setups[0]["setup_id"] == a["setup_id"] and setups[0]["strategy"] == "414"
    # الإعداد بعقد `shared/trade_setup` نفسه — يقرؤه 555 و465 بأسمائه (المالك والدخول وسببا الوقف والهدف).
    from shared.trade_setup import OK, validate_setup
    assert validate_setup(setups[0]) == OK
    assert setups[0]["setup_owner"] == "414" and setups[0]["entry_reference"] == pytest.approx(30015.0)
    assert setups[0]["invalidation_reason"] and setups[0]["target_reason"]


@pytest.mark.asyncio
async def test_archived_reasons_and_no_approval():
    for kwargs, expected in (({"window_ok": False}, card_trend.NO_WINDOW),
                             ({"open_symbols": (SYM,)}, "POSITION_OPEN")):
        _, atom, bus = await make_atom(414, {"symbols": [SYM]})
        await _facts(atom, **kwargs)
        await _candle(atom, 30005.0, AT - 600)
        await _candle(atom, 30015.0, AT - 300)
        assert bus.payloads("strategy.card.state")[-1]["status"] == expected
        assert not bus.payloads("decision.approved.state")


@pytest.mark.asyncio
async def test_frames_disagree_is_archived():
    _, atom, bus = await make_atom(414, {"symbols": [SYM]})
    await _facts(atom)
    await atom._on_trend({"symbol": SYM, "timeframe": "4h",
                          "metadata": {"close": 29000.0, "ema_slow_value": 29500.0}})
    await _candle(atom, 30005.0, AT - 600)
    await _candle(atom, 30015.0, AT - 300)
    assert bus.payloads("strategy.card.state")[-1]["status"] == card_trend.NO_DIRECTION
    assert not bus.payloads("decision.approved.state")


@pytest.mark.asyncio
async def test_correlation_must_agree():
    _, atom, bus = await make_atom(414, {"symbols": [SYM]})
    await _facts(atom, peers_up=False)          # الإس آند بي والداو تحت متوسّطهما والناسداك فوقه
    await _candle(atom, 30005.0, AT - 600)
    await _candle(atom, 30015.0, AT - 300)
    assert bus.payloads("strategy.card.state")[-1]["status"] == card_trend.PEERS_DISAGREE
    assert not bus.payloads("decision.approved.state")


@pytest.mark.asyncio
async def test_dow_is_no_longer_a_peer():
    # ٢٠٢٦-١٠-٠٨ (أمر المالك «الغِ الداو من الارتباط، بس الإس آند بي 500»): الداو ضدّنا لا يمنع، والإس آند بي وحده يحكم.
    assert card_trend.PEERS == ("US500",)
    _, atom, bus = await make_atom(414, {"symbols": [SYM]})
    await _facts(atom)
    for frame in ("1h", "4h"):
        await atom._on_trend({"symbol": "US30", "timeframe": frame,
                              "metadata": {"close": 6000.0, "ema_slow_value": 6500.0}})
    atom._trend.pop(("US30", "1h"), None)        # وغيابه لا يجعل الحقيقة ناقصة
    await _candle(atom, 30005.0, AT - 600)
    await _candle(atom, 30015.0, AT - 300)
    assert bus.payloads("strategy.card.state")[-1]["status"] == card_trend.OPEN
    assert len(bus.payloads("decision.approved.state")) == 1


@pytest.mark.asyncio
async def test_late_candle_after_a_cut_is_not_a_trigger():
    # بعد انقطاعٍ يُغلق باني الشموع شمعةَ ما قبل القطع عند أوّل تِكّةٍ بعد العودة — سعرها ماضٍ.
    _, atom, bus = await make_atom(414, {"symbols": [SYM]})
    await _facts(atom)
    atom._clock = lambda: AT + 1800.0       # نصف ساعة صمت
    await atom._on_session({"symbol": SYM, "owner_window": "london_peak", "window_at": AT + 1800.0})
    await _candle(atom, 30005.0, AT - 600)
    await _candle(atom, 30015.0, AT - 300)
    card = bus.payloads("strategy.card.state")[-1]
    assert card["status"] == "CANDLE_LATE" and card["late_s"] >= 1800.0
    assert not bus.payloads("decision.approved.state")


@pytest.mark.asyncio
async def test_old_candle_is_never_read_again():
    _, atom, bus = await make_atom(414, {"symbols": [SYM]})
    await _facts(atom)
    await _candle(atom, 30005.0, AT - 600)
    await _candle(atom, 30015.0, AT - 300)
    assert len(bus.payloads("decision.approved.state")) == 1
    cards = len(bus.payloads("strategy.card.state"))
    await _candle(atom, 30005.0, AT - 600)          # شمعةٌ أقدم تصل متأخّرة
    await _candle(atom, 30015.0, AT - 300)          # والشمعة نفسها مكرّرة
    assert len(bus.payloads("strategy.card.state")) == cards
    assert len(bus.payloads("decision.approved.state")) == 1
    assert atom._tally.get("CANDLE_OLD") == 2


@pytest.mark.asyncio
async def test_big_frame_facts_survive_a_restart_only_while_still_latest():
    # ٢٠٢٦-١٠-٠٨: حقيقة الأربع ساعات لا تُنشر إلّا عند إغلاق شمعتها — تُحفظ عبر الإقلاع ما دامت آخر مغلق.
    _, atom, bus = await make_atom(414, {"symbols": [SYM]})
    await _facts(atom)
    state = await atom.snapshot()
    _, fresh, _ = await make_atom(414, {"symbols": [SYM]})
    fresh._clock = lambda: AT + 1800.0                # نصف ساعة: الساعة والأربع ساعات واليوم صالحة
    await fresh.restore(state)
    assert (SYM, "4h") in fresh._trend and (SYM, "1d") in fresh._atr
    assert (SYM, "1h") in fresh._trend and (SYM, "5m") not in fresh._atr   # شمعة ٥ د مضت بعدها أخرى
    _, late, _ = await make_atom(414, {"symbols": [SYM]})
    late._clock = lambda: AT + 5 * 3600.0             # خمس ساعات: أُغلقت بعدها شمعة أربع ساعات أخرى
    await late.restore(state)
    assert (SYM, "4h") not in late._trend and (SYM, "1d") in late._atr


def test_missing_daily_range_is_a_missing_fact_not_an_open_target():
    card = card_trend.evaluate(
        at=AT, close=30015.0, prev_close=30005.0,
        trend_1h={"close": 30000.0, "ema_slow_value": 29500.0},
        trend_4h={"close": 30000.0, "ema_slow_value": 29500.0},
        atr_5m=10.0, atr_1d=None,
        ladder={"5m": {"highs": [[30010.0, AT - 1800]], "lows": [[29980.0, AT - 900]]},
                "1h": {"highs": [[30200.0, AT - 7200]], "lows": []}},
        window="london_peak", news_blocked=False)
    assert card["status"] == card_trend.FACT_MISSING and card["missing"] == "atr_1d"


@pytest.mark.asyncio
async def test_missing_peer_facts_is_not_a_trade():
    _, atom, bus = await make_atom(414, {"symbols": [SYM]})
    await _facts(atom)
    atom._trend.pop(("US500", "4h"), None)      # ٢٠٢٦-١٠-٠٨: الإس آند بي وحده المرتبط (كان الداو)
    await _candle(atom, 30005.0, AT - 600)
    await _candle(atom, 30015.0, AT - 300)
    assert bus.payloads("strategy.card.state")[-1]["status"] == card_trend.FACT_MISSING
    assert not bus.payloads("decision.approved.state")


# ── ٢٠٢٦-١٠-٠٨ (ختم المالك «صلح NQ»): حدود الإطارات — الحيّ = المقيس ─────────────────────────────
# حالة اليوم بعينها: الأربعاء 09:00 غرينتش (= 12:00 بتوقيت الجهاز) حدُّ ساعةٍ وأربع ساعات معًا. شمعة 5 د
# تُغلق مع شمعة الأربع ساعات، والقياس يقرأ الأربع ساعات الجديدة (هابطة) فيفتح بيعًا؛ والحيّ كان يقرأ القديمة.
AT4 = calendar.timegm(time.strptime("2026-10-07 09:00", "%Y-%m-%d %H:%M"))


async def _boundary_facts(atom, *, fresh_4h=False, window_at=AT4):
    atom._clock = lambda: AT4 + 1.0
    await atom._on_account({"account_id": "52992818", "broker": "RawTrading"})
    await atom._on_positions({"positions": []})
    await atom._on_trend({"symbol": SYM, "timeframe": "1h", "metadata": {
        "close": 29900.0, "ema_slow_value": 30100.0, "period_start": AT4 - 3600}})
    await atom._on_trend({"symbol": SYM, "timeframe": "4h", "metadata": {     # الأربع ساعات **القديمة**: صاعدة
        "close": 30200.0, "ema_slow_value": 30100.0, "period_start": AT4 - 2 * 14400}})
    if fresh_4h:
        await _new_4h(atom)
    for peer in ("US500", "US30"):
        for frame, seconds in (("1h", 3600), ("4h", 14400)):
            await atom._on_trend({"symbol": peer, "timeframe": frame, "metadata": {
                "close": 6000.0, "ema_slow_value": 6500.0, "period_start": AT4 - seconds}})
    await atom._on_vol({"symbol": SYM, "timeframe": "1d", "metadata": {"atr_14": 400.0}})
    ladder = {"5m": {"lows": [[30000.0, AT4 - 1800]], "highs": [[30060.0, AT4 - 900]]},
              "1h": {"highs": [], "lows": [[29700.0, AT4 - 7200]]}, "4h": {"highs": [], "lows": []}}
    for frame, seconds in (("1h", 3600), ("4h", 14400)):
        await atom._on_ladder({"symbol": SYM, "frames": ladder,
                               "frame_closed": {"frame": frame, "period_start": AT4 - seconds}})
    await atom._on_session({"symbol": SYM, "owner_window": "london_peak", "window_at": window_at})


async def _new_4h(atom):
    await atom._on_trend({"symbol": SYM, "timeframe": "4h", "metadata": {        # الأربع ساعات **الجديدة**: هابطة
        "close": 29990.0, "ema_slow_value": 30100.0, "period_start": AT4 - 14400}})


async def _boundary_candles(atom):
    await atom._on_candle({"symbol": SYM, "timeframe": "5m", "period_start": AT4 - 600, "close": 30010.0})
    await atom._on_vol({"symbol": SYM, "timeframe": "5m", "metadata": {"atr_14": 10.0, "period_start": AT4 - 300}})
    await atom._on_candle({"symbol": SYM, "timeframe": "5m", "period_start": AT4 - 300, "close": 29990.0})


def test_boundary_is_the_broker_aligned_4h_close():
    from shared.owner_windows import broker_day_offset_s
    assert AT4 % 3600 == 0
    assert (AT4 + broker_day_offset_s(AT4)) % 14400 == 0          # 09:00 غرينتش = حدّ أربع ساعات الوسيط
    assert owner_window(AT4) == "london_peak"


@pytest.mark.asyncio
async def test_boundary_candle_waits_for_the_new_4h_fact_then_opens():
    _, atom, bus = await make_atom(414, {"symbols": [SYM]})
    await _boundary_facts(atom)
    await _boundary_candles(atom)
    # الشمعة وصلت قبل حقيقة الأربع ساعات الجديدة ⟸ لا حكم بعد (كان: «الإطاران مختلفان» على القديمة).
    statuses = [c["status"] for c in bus.payloads("strategy.card.state")]
    assert statuses == ["CANDLE_LATE"], statuses
    assert SYM in atom._pending and atom._waited == 1
    await _new_4h(atom)
    card = bus.payloads("strategy.card.state")[-1]
    assert card["status"] == card_trend.OPEN and card["side"] == card_trend.SELL, card
    assert card["stop"] == pytest.approx(30060.0) and card["target"] == pytest.approx(29700.0)
    assert len(bus.payloads("decision.approved.state")) == 1 and SYM not in atom._pending


@pytest.mark.asyncio
async def test_boundary_with_fresh_facts_evaluates_at_once():
    _, atom, bus = await make_atom(414, {"symbols": [SYM]})
    await _boundary_facts(atom, fresh_4h=True)
    await _boundary_candles(atom)
    assert bus.payloads("strategy.card.state")[-1]["status"] == card_trend.OPEN and atom._waited == 0


@pytest.mark.asyncio
async def test_fact_that_never_arrives_is_fact_late_not_a_trade():
    _, atom, bus = await make_atom(414, {"symbols": [SYM]})
    await _boundary_facts(atom)
    await _boundary_candles(atom)
    await atom._expire(SYM, AT4)                                   # انقضت المهلة
    card = bus.payloads("strategy.card.state")[-1]
    assert card["status"] == "FACT_LATE" and "151:USTEC:4h" in card["late"], card
    assert not bus.payloads("decision.approved.state") and SYM not in atom._pending
    await _new_4h(atom)                                            # وصولها بعد المهلة لا يفتح شيئًا
    assert not bus.payloads("decision.approved.state")


@pytest.mark.asyncio
async def test_window_is_read_at_the_candles_own_moment():
    # حقيقة الوقت الأخيرة من قبل لحظة الزناد ⟸ تنتظر طبقة الوقت عند لحظتها (لا نافذة الشمعة السابقة).
    _, atom, bus = await make_atom(414, {"symbols": [SYM]})
    await _boundary_facts(atom, fresh_4h=True, window_at=AT4 - 5.0)
    await _boundary_candles(atom)
    assert atom._pending.get(SYM) and bus.payloads("strategy.card.state")[-1]["status"] == "CANDLE_LATE"
    await atom._on_session({"symbol": SYM, "owner_window": "london_peak", "window_at": AT4 + 0.2})
    assert bus.payloads("strategy.card.state")[-1]["status"] == card_trend.OPEN
