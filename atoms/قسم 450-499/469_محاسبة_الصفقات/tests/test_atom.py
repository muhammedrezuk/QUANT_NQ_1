"""اختبارات 469 — محاسبة الصفقات.

٢٠٢٦-١٠-٠٨ (ختم المالك «NQ» — المعرفة أوّلًا): كلّ دفترٍ هنا في `tmp_path`، ويُبنى بـ`CardStore` الحقيقيّ
(مخطّط 465 نفسه: `cards` و`card_writes` وحقل «حقيقة»)، ولا يُقرأ الدفتر الحيّ من اختبارٍ أبدًا.
"""
import asyncio
import calendar
import importlib.util
import re
import sqlite3
import sys
import time
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[4]
FOLDER = Path(__file__).resolve().parents[1]
for _path in (str(ROOT), str(FOLDER)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

_spec = importlib.util.spec_from_file_location("_t469", FOLDER / "atom.py")
m = importlib.util.module_from_spec(_spec)
sys.modules["_t469"] = m
_spec.loader.exec_module(m)

import accountability_groups as groups  # noqa: E402
import accountability_ledger as ledger  # noqa: E402
import accountability_text as report  # noqa: E402
from core.contracts.atom import AtomContext, HealthState  # noqa: E402
from shared.trade_card import CardStore, STATE_CLOSED, STATE_EXPIRED  # noqa: E402

FACT = "حقيقة"
# الأربعاء ٢٠٢٦-١٠-٠٧: 07:20 غرينتش داخل ذروة لندن، و13:45 داخل افتتاح أمريكا.
LONDON = calendar.timegm(time.strptime("2026-10-07 07:20", "%Y-%m-%d %H:%M"))
NY = calendar.timegm(time.strptime("2026-10-07 13:45", "%Y-%m-%d %H:%M"))
FORBIDDEN = {"direction", "signal", "strength", "confidence", "weight", "score", "probability",
             "threshold", "depth", "readiness", "buy", "sell", "bullish", "bearish", "strong", "weak"}


class _NullLogger:
    def __getattr__(self, name):
        return lambda *args, **kwargs: None


class FakeBus:
    def __init__(self):
        self.published = []
        self.subscribed = []

    def subscribe(self, name, handler):
        self.subscribed.append((name, handler))

    async def publish(self, name, payload=None):
        self.published.append((name, payload))

    def payloads(self, name):
        return [p for n, p in self.published if n == name]


def _add(store, *, symbol="USTEC", side="sell", opened_at=LONDON, closed_at=None,
         entry=None, stop=None, target=None, fill=None, exit_price=None, sent_stop=None,
         sent_target=None, profit=0.0, risk=100.0, peak=None, worst=None, overshoot=None,
         body=None, facts=None, state=STATE_CLOSED):
    """صفقةٌ كما يكتبها 465 و552 و563 على بطاقتها — بـ`CardStore` الحقيقيّ."""
    card_no, fresh = store.open_card(symbol, "52992818", "Raw Trading Ltd", side, at=opened_at, body={})
    assert fresh
    stop_points = abs(entry - stop) if entry is not None and stop is not None else None
    fields = {"entry": entry, "stop": stop, "target": target, "stop_points": stop_points,
              "fill_price": fill, "exit_price": exit_price, "sent_stop": sent_stop,
              "sent_target": sent_target, "risk_amount": risk, "ticket": "T%d" % card_no,
              "stop_overshoot": overshoot}
    if peak is not None:
        fields.update(peak_points=peak, worst_points=worst, peak_r=round(peak / stop_points, 4),
                      worst_r=round(worst / stop_points, 4))
    store.update(card_no, fields, body=body, at=opened_at)
    if facts:
        store.notes([(card_no, author, FACT, value, opened_at) for author, value in facts.items()])
    store.note(card_no, "151", "رأي", "الاتجاه · شراء · +100 · up · قوّة=50", at=opened_at)
    store.set_state(card_no, state, at=closed_at or opened_at + 600,
                    outcome="WIN" if profit > 0 else "LOSS" if profit < 0 else "BREAKEVEN",
                    profit=profit)
    return card_no


def _store(tmp_path, name="cards.db"):
    store = CardStore(str(tmp_path / name))
    store.ensure()
    return store


WIN_BODY = {"setup_id": "414:USTEC:1791300000", "setup_type": "TREND_CONTINUATION_PULLBACK",
            "invalidation_reason": "فوق قمّة الارتداد على ٥ د (30025.00)",
            "target_reason": "أقرب مستوى ساعة/٤ ساعات بنسبة 1:3.0"}
LOSS_BODY = {"setup_id": "410:LIQUIDITY_RAID:XAUUSD:1791300000", "setup_type": "LIQUIDITY_RAID",
             "invalidation_reason": "تحت قاع الكنس", "target_reason": "أقرب سيولة مقابلة"}


def _winner(store, closed_at=LONDON + 900):
    """بيع ناسداك: الهدف 3R، ذهب معنا 1.3R وضدّنا 0.2R، وخرج الثلث الأوّل عند 1R ⟸ +33$ على خطر 100$."""
    return _add(store, side="sell", opened_at=LONDON, closed_at=closed_at, entry=30000.0,
                stop=30030.0, target=29910.0, fill=30000.0, exit_price=29970.0, sent_stop=30030.0,
                sent_target=29910.0, profit=33.0, risk=100.0, peak=39.0, worst=-6.0, body=WIN_BODY,
                facts={"153": "التذبذب · atr_14=12.5 · period_start=1791300000",
                       "151": "الاتجاه · close=30010.0 · ema_slow_value=30100.0"})


def _loser(store, closed_at=NY + 900):
    """شراء ذهب: ضرب الوقف وتجاوزه بدولار ⟸ −110$ على خطر 100$ = −1.1R."""
    return _add(store, symbol="XAUUSD", side="buy", opened_at=NY, closed_at=closed_at,
                entry=4000.0, stop=3990.0, target=4030.0, fill=4000.5, exit_price=3989.5,
                sent_stop=3990.5, sent_target=4030.5, profit=-110.0, risk=100.0, peak=2.0,
                worst=-11.0, overshoot=1.0, body=LOSS_BODY)


def _build(path, min_sample=10, top=10):
    return report.build_payload(str(path), time.time(), min_sample, top, 5.0)


def _offending(obj, path="$"):
    """كلّ مفتاحٍ أو نصٍّ في الحمولة يحمل كلمةً ممنوعة (أو جمعها) بالكلمة الكاملة."""
    found = []

    def bad(value):
        words = re.findall(r"[a-z]+", str(value).lower())
        return any(w in FORBIDDEN or (w.endswith("s") and w[:-1] in FORBIDDEN) for w in words)

    if isinstance(obj, dict):
        for key, value in obj.items():
            if bad(key):
                found.append("%s.%s" % (path, key))
            found += _offending(value, "%s.%s" % (path, key))
    elif isinstance(obj, (list, tuple)):
        for index, value in enumerate(obj):
            found += _offending(value, "%s[%d]" % (path, index))
    elif isinstance(obj, str) and bad(obj):
        found.append("%s=%s" % (path, obj[:60]))
    return found


# ------------------------------------------------------------- شرح صفقة رابحة وخاسرة


def test_winning_trade_explained_with_numbers(tmp_path):
    store = _store(tmp_path)
    card_no = _winner(store)
    payload = _build(tmp_path / "cards.db")
    last = payload["facts"]["last_trade"]
    assert payload["status"] == "ok" and last["card_no"] == card_no
    assert last["side"] == "short" and last["side_ar"] == "بيع" and last["window"] == "london_peak"
    assert last["strategy"] == "414:TREND_CONTINUATION_PULLBACK"
    assert last["result_r"] == pytest.approx(0.33)
    assert last["exit_move_r"] == pytest.approx(1.0)            # (30000 − 29970) ÷ 30
    assert last["recorded_share"] == pytest.approx(0.33)        # ثلث العقد وحده على البطاقة
    assert last["max_favorable_r"] == pytest.approx(1.3) and last["max_adverse_r"] == pytest.approx(0.2)
    assert last["thirds_reached"] == 1                          # 39 ÷ 90 = 0.43 من مسافة الهدف
    assert last["exit_kind"] == "first_third" and last["exit_target_frac"] == pytest.approx(1 / 3, abs=1e-4)
    # الحقائق باسم صاحبها، بلا مفتاح اللحظة (بداية الشمعة ليست حقيقة سوق).
    assert last["entry_facts"] == {"151": "الاتجاه · close=30010.0 · ema_slow_value=30100.0",
                                   "153": "التذبذب · atr_14=12.5"}
    text = last["explain_ar"]
    for piece in ("بيع USTEC بناها بطاقة استمرار الاتّجاه (TREND_CONTINUATION_PULLBACK)",
                  "الوقف: فوق قمّة الارتداد على ٥ د (30025.00)", "الهدف: أقرب مستوى ساعة/٤ ساعات",
                  "ذهب السعر معنا 1.30R وضدّنا 0.20R (على الوقف المرسَل)",
                  "بلغت الهدف الأوّل (ثلث المسافة)",
                  "خرج عند ثلث المسافة (الهدف الأوّل)", "⟸ +0.33R (+33.00$)", "حصّة 0.33 من العقد",
                  "عند الدخول 2 حقيقة: 151 الاتجاه · close=30010.0"):
        assert piece in text, piece
    assert payload["summary_ar"].startswith("آخر صفقة: بيع USTEC (بطاقة استمرار الاتّجاه")


def test_losing_trade_explained_and_totals(tmp_path):
    store = _store(tmp_path)
    _winner(store)
    card_no = _loser(store)
    facts = _build(tmp_path / "cards.db")["facts"]
    last = facts["last_trade"]
    assert last["card_no"] == card_no and last["side"] == "long" and last["window"] == "ny_open"
    assert last["result_r"] == pytest.approx(-1.1)
    assert last["exit_move_r"] == pytest.approx(-1.1)           # (3989.5 − 4000.5) ÷ 10
    assert last["recorded_share"] == pytest.approx(1.0)         # العقد كلّه
    assert last["thirds_reached"] == 0 and last["exit_kind"] == "stop"
    # من التنفيذ 4000.5 والوقف المرسَل 3990.5: الذروة 4002 = +0.15R، والحضيض 3989 = −1.15R.
    assert last["excursion_basis"] == "sent"
    assert last["max_favorable_r"] == pytest.approx(0.15) and last["max_adverse_r"] == pytest.approx(1.15)
    text = last["explain_ar"]
    for piece in ("شراء XAUUSD بناها السيولة (LIQUIDITY_RAID)", "الوقف: تحت قاع الكنس",
                  "المرسَل: دخول 4000.5 · وقف 3990.5 · هدف 4030.5",
                  "ذهب السعر معنا 0.15R وضدّنا 1.15R (على الوقف المرسَل)",
                  "لم تبلغ أقصى حركةٍ معنا الهدفَ الأوّل", "خرج على الوقف",
                  "⟸ -1.10R (-110.00$)", "لا حقائق أقسامٍ مختومة"):
        assert piece in text, piece
    assert "حصّة" not in text
    totals = facts["totals"]
    assert (totals["n"], totals["wins"], totals["win_rate_pct"]) == (2, 1, 50.0)
    assert totals["total_usd"] == pytest.approx(-77.0) and totals["total_r"] == pytest.approx(-0.77)
    assert totals["max_drawdown_r"] == pytest.approx(1.1) and totals["max_drawdown_usd"] == pytest.approx(110.0)
    assert set(facts["by_strategy"]) == {"414:TREND_CONTINUATION_PULLBACK", "410:LIQUIDITY_RAID"}
    assert facts["by_window"]["london_peak"]["wins"] == 1 and facts["by_window"]["ny_open"]["wins"] == 0
    assert facts["by_side"]["long"]["total_r"] == pytest.approx(-1.1)
    assert facts["by_symbol"]["XAUUSD"]["n"] == 1 and facts["by_symbol"]["XAUUSD"]["small_sample"]
    assert facts["trades_partial_recorded"] == 1 and facts["trades_with_entry_facts"] == 1
    assert "منها 1 سُجّل على بطاقتها جزءٌ من العقد وحده" in _build(tmp_path / "cards.db")["summary_ar"]


def test_excursion_and_thirds_follow_what_was_sent(tmp_path):
    """البطاقة 86468 من الدفتر الحيّ بأرقامها: وقف التحليل 182 والمرسَل 543، وهدف التحليل 612 والمرسَل 3,136."""
    card = {"side": "sell", "entry": 83265.16, "stop": 83447.64, "target": 82652.87,
            "stop_points": 182.480373, "peak_points": 334.4683, "worst_points": -299.3408,
            "peak_r": 1.8329, "worst_r": -1.6404, "fill_price": 83221.18, "exit_price": 83321.2,
            "sent_stop": 83764.02931232, "sent_target": 80085.338239, "profit": -17.0,
            "risk_amount": 90.06, "card_no": 86468, "symbol": "BTCUSD", "state": "CLOSED"}
    trade = ledger.derive_trade(card)
    assert trade["excursion_basis"] == "sent"
    assert trade["max_favorable_r"] == pytest.approx(0.5351, abs=1e-3)   # (83265.16 − 334.47 → 82930.69) من 83221.18
    assert trade["max_adverse_r"] == pytest.approx(0.6324, abs=1e-3)
    assert trade["thirds_reached"] == 0                                  # 290 من 3,136 نقطة
    assert trade["result_r"] == pytest.approx(-17.0 / 90.06, abs=1e-4)
    assert trade["recorded_share"] is None                              # خروجٌ أقرب من 0.2R: لا قسمة
    # خرج 100 نقطة فوق التنفيذ: −0.18R — ليس تعادلًا وإن كان −0.03 فقط من مسافة هدفٍ بعيد.
    assert trade["exit_kind"] == "other" and trade["exit_move_r"] == pytest.approx(-0.1842, abs=1e-3)
    view = report.last_trade_view(trade, {})
    assert "خرج عند -0.18R من سعر التنفيذ (-0.03 من مسافة الهدف)" in view["explain_ar"]
    # بلا تنفيذٍ على البطاقة ⟸ أساس التحليل كما كتبه 465.
    bare = ledger.derive_trade({**card, "fill_price": None})
    assert bare["excursion_basis"] == "analysis"
    assert bare["max_favorable_r"] == pytest.approx(1.8329) and bare["max_adverse_r"] == pytest.approx(1.6404)
    assert bare["thirds_reached"] == 1                                   # 334 من 612 نقطة
    assert bare["exit_kind"] == "unknown"


def test_expired_card_with_realized_profit_counts_as_trade(tmp_path):
    store = _store(tmp_path)
    _add(store, profit=-50.0, state=STATE_EXPIRED)
    _add(store, profit=20.0)
    facts = _build(tmp_path / "cards.db")["facts"]
    assert facts["trades_closed"] == 2 and facts["trades_by_state"] == {"EXPIRED": 1, "CLOSED": 1}


# ------------------------------------------------------------- الأثلاث والفئات والعيّنة الصغيرة


def _fact_book(tmp_path):
    """30 صفقة: المدى 1..30 (الأدنى −1R، الأوسط +0.5R، الأعلى +2R) والجلسة نصًّا، و5 بحقيقةٍ نادرة."""
    store = _store(tmp_path)
    for i in range(1, 31):
        r = -1.0 if i <= 10 else 0.5 if i <= 20 else 2.0
        session = "london" if i <= 12 else "ny" if i <= 24 else "asia"
        _add(store, opened_at=LONDON + i * 1000, profit=r * 100.0, facts={
            "153": "التذبذب · atr_14=%d · period_start=%d" % (i, LONDON),
            "158": "الجلسات · session_name=%s" % session,
            "151": "الاتجاه · direction=up · close=1.0",
            "152": "الزخم · state=bullish"})
    for i in range(5):
        _add(store, opened_at=LONDON + 50000 + i * 1000, profit=10.0,
             facts={"999": "نادر · rare=%d" % i})
    return _build(tmp_path / "cards.db")


def test_numeric_facts_split_in_terciles_from_their_own_values(tmp_path):
    facts = _fact_book(tmp_path)["facts"]
    atr = facts["by_fact"]["153.atr_14"]
    assert atr["kind"] == "number" and atr["n"] == 30 and atr["bounds"] == [10.0, 20.0]
    low, mid, high = (atr["groups"][k] for k in ("low", "mid", "high"))
    assert (low["n"], low["wins"], low["avg_r"]) == (10, 0, -1.0)
    assert (mid["n"], mid["wins"], mid["avg_r"]) == (10, 10, 0.5)
    assert (high["n"], high["wins"], high["avg_r"], high["win_rate_pct"]) == (10, 10, 2.0, 100.0)
    assert not any(g["small_sample"] for g in atr["groups"].values())
    assert "153.period_start" not in facts["by_fact"]           # لحظةٌ لا حقيقة


def test_text_facts_by_value_and_small_sample_never_ranked(tmp_path):
    facts = _fact_book(tmp_path)["facts"]
    session = facts["by_fact"]["158.session_name"]["groups"]
    assert session["london"]["n"] == 12 and session["london"]["avg_r"] == pytest.approx(-0.75)
    assert session["ny"]["n"] == 12 and session["ny"]["avg_r"] == pytest.approx(1.0)
    assert session["asia"]["n"] == 6 and session["asia"]["small_sample"]
    rare = facts["by_fact"]["999.rare"]
    assert rare["n"] == 5 and all(g["small_sample"] for g in rare["groups"].values())
    gaps = facts["fact_gaps"]
    assert [g["fact"] for g in gaps] == ["153.atr_14", "158.session_name"]
    assert gaps[0]["avg_r_gap"] == pytest.approx(3.0)
    assert (gaps[0]["highest_avg_r_group"], gaps[0]["lowest_avg_r_group"]) == ("high", "low")
    # آسيا (+2R على 6 صفقات) خارج الترتيب: الفرق بين نيويورك ولندن وحدهما.
    assert gaps[1]["avg_r_gap"] == pytest.approx(1.75)
    assert (gaps[1]["highest_avg_r_group"], gaps[1]["lowest_avg_r_group"]) == ("ny", "london")
    assert facts["trades_with_entry_facts"] == 35


def test_forbidden_fact_keys_and_values_are_withheld_and_counted(tmp_path):
    payload = _fact_book(tmp_path)
    facts = payload["facts"]
    assert "151.direction" not in facts["by_fact"] and "152.state" not in facts["by_fact"]
    assert facts["facts_withheld"] == 60                        # 30 جهة + 30 قيمة ممنوعة
    assert "151.close" in facts["by_fact"]                      # الباقي من السطر نفسه يبقى
    assert "أكثر عاملٍ يفرّق: التذبذب 153.atr_14" in payload["summary_ar"]


def test_summary_says_small_sample_when_nothing_ranks(tmp_path):
    store = _store(tmp_path)
    for i in range(3):
        _add(store, opened_at=LONDON + i * 1000, profit=10.0 * (i - 1),
             facts={"153": "التذبذب · atr_14=%d" % i})
    payload = _build(tmp_path / "cards.db")
    assert payload["facts"]["fact_gaps"] == []
    assert "عيّنة صغيرة بعد" in payload["summary_ar"]


def test_summary_without_any_stamped_fact(tmp_path):
    store = _store(tmp_path)
    _loser(store)
    assert "لا صفقة مغلقة تحمل حقائق الأقسام بعد" in _build(tmp_path / "cards.db")["summary_ar"]


def test_pure_helpers():
    assert groups.max_drawdown([1.0, -2.0, 0.5, -1.0, 3.0]) == pytest.approx(2.5)
    assert groups.max_drawdown([]) == 0.0
    assert groups.tercile_bounds([float(v) for v in range(1, 31)]) == (10.0, 20.0)
    assert groups.tercile_bounds([5.0]) == (5.0, 5.0)
    assert ledger.thirds_reached(10.0, 30.0) == 1                # ثلثٌ تمامًا
    assert ledger.thirds_reached(19.9, 30.0) == 1
    assert ledger.thirds_reached(20.0, 30.0) == 2
    assert ledger.thirds_reached(45.0, 30.0) == 3
    assert ledger.thirds_reached(-5.0, 30.0) == 0
    assert ledger.thirds_reached(None, 30.0) is None and ledger.thirds_reached(5.0, 0.0) is None
    kinds = [ledger.exit_kind(f, r, None) for f, r in (
        (0.01, 0.03), (0.34, 1.0), (0.66, 2.0), (1.0, 3.0), (0.5, 1.5), (-0.03, -0.18), (None, None))]
    assert kinds == ["breakeven", "first_third", "second_third", "target", "other", "other", "unknown"]
    assert ledger.exit_kind(0.34, 1.0, 0.5) == "stop"
    assert ledger.strategy_of({}) == "none"
    assert ledger.is_clean("buyside_pool=3") and not ledger.is_clean("signals=2")


# ------------------------------------------------------------- غياب القاعدة لا يكسر


def test_missing_or_broken_ledger_is_a_fact_not_a_crash(tmp_path):
    with pytest.raises(ledger.LedgerUnavailable):
        _build(tmp_path / "absent.db")
    junk = tmp_path / "junk.db"
    junk.write_bytes(b"not a database at all" * 10)
    with pytest.raises(ledger.LedgerUnavailable):
        _build(junk)
    empty = tmp_path / "empty.db"
    sqlite3.connect(str(empty)).close()
    with pytest.raises(ledger.LedgerUnavailable):
        _build(empty)


def test_empty_ledger_reports_zero(tmp_path):
    _store(tmp_path)
    payload = _build(tmp_path / "cards.db")
    assert payload["facts"]["trades_closed"] == 0 and payload["facts"]["last_trade"] is None
    assert payload["summary_ar"].startswith("لا صفقة مغلقة في الدفتر بعد")


def test_reading_never_writes_the_ledger(tmp_path):
    store = _store(tmp_path)
    _winner(store)
    before = (tmp_path / "cards.db").read_bytes()
    _build(tmp_path / "cards.db")
    assert (tmp_path / "cards.db").read_bytes() == before


# ------------------------------------------------------------- الحمولة بلا حقول ممنوعة


def test_payloads_carry_no_forbidden_field(tmp_path):
    for name in ("a", "b"):
        (tmp_path / name).mkdir()
    store = _store(tmp_path / "a")
    _winner(store)
    _loser(store)
    payloads = [_build(tmp_path / "a" / "cards.db"), _fact_book(tmp_path / "b"),
                report.unavailable_payload("الدفتر غير موجود", time.time())]
    for payload in payloads:
        assert set(payload) == {"id", "status", "facts", "computed_at", "summary_ar", "source"}
        assert payload["id"] == "trade_accountability"
        assert _offending(payload) == []


# ------------------------------------------------------------- الذرّة: الأحداث والصحّة واللقطة


async def _atom(tmp_path, store_path):
    bus = FakeBus()
    atom = m.Atom()
    config = {"store_path": str(store_path), "boot_delay_s": 0.0, "close_settle_s": 0.0,
              "min_sample": 10, "top_gaps": 10}
    await atom.initialize(AtomContext(469, config, _NullLogger(), bus.publish, bus.subscribe))
    return atom, bus


async def _drain(atom):
    for _ in range(50):
        if not atom._tasks:
            return
        await asyncio.gather(*list(atom._tasks), return_exceptions=True)


@pytest.mark.asyncio
async def test_atom_publishes_at_boot_hour_and_after_close(tmp_path):
    store = _store(tmp_path)
    _winner(store)
    atom, bus = await _atom(tmp_path, tmp_path / "cards.db")
    assert {name for name, _ in bus.subscribed} == {"SYS_HOUR", "decision.card.closed"}
    await atom.start()
    await _drain(atom)
    assert len(bus.payloads("knowledge.accountability.state")) == 1          # الإقلاع
    await atom._on_hour({"hour": 14})
    await _drain(atom)
    card_no = _loser(store)
    await atom._on_card_closed({"card_no": card_no, "symbol": "XAUUSD"})
    await atom._on_card_closed({"card_no": card_no, "symbol": "XAUUSD"})     # يُدمج في الحساب نفسه
    await atom._on_card_closed("bad")
    await atom._on_card_closed({"symbol": "XAUUSD"})
    await _drain(atom)
    published = bus.payloads("knowledge.accountability.state")
    assert len(published) == 3 and published[-1]["facts"]["last_trade"]["card_no"] == card_no
    assert atom._dropped == 2 and atom._closes_seen == 2 and atom._coalesced == 1
    health = await atom.health_check()
    assert health.state == HealthState.HEALTHY
    assert "يعرف 2 صفقة مغلقة: 1 رابحة" in health.message and "آخرها البطاقة %d" % card_no in health.message
    await atom.stop()


@pytest.mark.asyncio
async def test_atom_survives_missing_ledger(tmp_path):
    atom, bus = await _atom(tmp_path, tmp_path / "nowhere" / "cards.db")
    await atom.start()
    await _drain(atom)
    payload = bus.payloads("knowledge.accountability.state")[-1]
    assert payload["status"] == "unavailable" and payload["facts"]["available"] is False
    assert "غير موجود" in payload["facts"]["unavailable_reason"]
    health = await atom.health_check()
    assert health.state == HealthState.DEGRADED and "غير متاح" in health.message
    assert not (tmp_path / "nowhere").exists()                  # القراءة لا تُنشئ شيئًا
    await atom.stop()


@pytest.mark.asyncio
async def test_atom_survives_a_computation_error(tmp_path, monkeypatch):
    def broken(*args, **kwargs):
        raise TypeError("صفٌّ شاذّ")
    monkeypatch.setattr(report, "build_payload", broken)
    atom, bus = await _atom(tmp_path, tmp_path / "cards.db")
    await atom.start()
    await _drain(atom)
    payload = bus.payloads("knowledge.accountability.state")[-1]
    assert payload["status"] == "unavailable" and "TypeError" in payload["facts"]["unavailable_reason"]
    assert atom._failed == 1 and (await atom.health_check()).state == HealthState.DEGRADED
    await atom.stop()


@pytest.mark.asyncio
async def test_stop_cancels_pending_work(tmp_path):
    atom, bus = await _atom(tmp_path, tmp_path / "cards.db")
    atom._boot_delay = 60.0
    await atom.start()
    assert atom._tasks
    await atom.stop()
    for _ in range(5):
        await asyncio.sleep(0)
    assert not atom._tasks and not bus.payloads("knowledge.accountability.state")


@pytest.mark.asyncio
async def test_snapshot_restore_round_trip(tmp_path):
    store = _store(tmp_path)
    _winner(store)
    atom, _ = await _atom(tmp_path, tmp_path / "cards.db")
    await atom.start()
    await _drain(atom)
    state = await atom.snapshot()
    fresh, _ = await _atom(tmp_path, tmp_path / "cards.db")
    await fresh.restore(state)
    assert await fresh.snapshot() == state
    fresh._running = True
    assert "يعرف 1 صفقة مغلقة" in (await fresh.health_check()).message
    with pytest.raises(ValueError):
        await fresh.restore("bad")
    with pytest.raises(ValueError):
        await fresh.restore({"published": "many"})
    await atom.stop()


def test_manifest_matches_code():
    manifest = yaml.safe_load((FOLDER / "manifest.yaml").read_text(encoding="utf-8"))
    assert manifest["id"] == 469 and manifest["name"] == "Trade Accountability"
    assert manifest["version"] == m.ATOM_VERSION
    assert manifest["publishes"] == ["knowledge.accountability.state"]
    assert set(manifest["subscribes"]) == {"SYS_HOUR", "decision.card.closed"}
    assert manifest["config"]["store_path"] == "var/store/trade_cards.db"
    assert set(manifest["config"]) == set(manifest["config_schema"]["properties"])
