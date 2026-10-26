"""تسعير قرار الفائدة 121 — كلّ حقيقة بأرقامٍ محسوبة يدويًّا، على قاعدة جسرٍ مؤقّتة (لا الجسر الحيّ ولا الشبكة).

٢٠٢٦-١٠-٠٨ (ختم المالك «NQ» — «تسعير الفائدة حيًّا يحتاج ياهو NQ»، ثمّ «الأخبار من مكانٍ واحد»): الذرّة تقرأ
جدول الجسر `fed_futures` الذي يكتبه بوت الأخبار، ولا تتّصل بالإنترنت. أسعار اليوم المقيسة من الجهاز (~14:00 غرينتش):
ZQV26 96.115 · ZQX26 96.07 · ZQZ26 95.915 · ZQF27 95.85. وما بعدها (G27 95.84 · H27 95.80 · J27 95.78) قيمُ
اختبارٍ لا أسعارٌ مقيسة.
"""
import ast
import asyncio
import calendar
import importlib.util
import re
import sqlite3
import sys
import time
import urllib.request
from datetime import date
from pathlib import Path

import pytest

from core.contracts.atom import AtomContext, HealthState
from tests.learning_test_support import Bus, Logger

ATOM_DIR = Path(__file__).resolve().parents[1]
if str(ATOM_DIR) not in sys.path:
    sys.path.insert(0, str(ATOM_DIR))
import fed_pricing_chain as chain  # noqa: E402
import fed_pricing_facts as facts_text  # noqa: E402

FORBIDDEN = ("direction", "signal", "strength", "confidence", "weight", "score", "probability", "threshold",
             "depth", "readiness", "buy", "sell", "bullish", "bearish", "strong", "weak")
FIRST_TEN = ["next_fomc_date", "days_to_next_fomc", "expected_change_bp_next", "market_implied_hike_pct_next",
             "market_implied_cut_pct_next", "implied_rate_after_next", "expected_change_bp_second",
             "implied_rate_year_end", "quotes_age_minutes", "pricing_available"]
CONFIG = {
    "fomc_decision_days": ["2026-01-28", "2026-03-18", "2026-04-29", "2026-06-17", "2026-07-29", "2026-09-16",
                           "2026-10-28", "2026-12-09"],
    "fomc_tentative_days": ["2027-01-27", "2027-03-17", "2027-04-28", "2027-06-09", "2027-07-28", "2027-09-15",
                            "2027-10-27", "2027-12-08"],
    "fomc_schedule_source": "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm (read 2026-10-08)",
}
SCHEMA = ("CREATE TABLE fed_futures (symbol TEXT PRIMARY KEY, contract_month TEXT, price REAL, implied_rate REAL, "
          "market_time_utc INTEGER, fetched_at_utc INTEGER, source TEXT)")
MONTHS = {"ZQV26.CBT": "2026-10", "ZQX26.CBT": "2026-11", "ZQZ26.CBT": "2026-12", "ZQF27.CBT": "2027-01",
          "ZQG27.CBT": "2027-02", "ZQH27.CBT": "2027-03", "ZQJ27.CBT": "2027-04"}
PRICES = {"ZQV26.CBT": 96.115, "ZQX26.CBT": 96.07, "ZQZ26.CBT": 95.915, "ZQF27.CBT": 95.85,
          "ZQG27.CBT": 95.84, "ZQH27.CBT": 95.80}                       # الجاري وخمسة بعده — كما يكتب البوت
AGES_MIN = {"ZQV26.CBT": 4, "ZQX26.CBT": 6, "ZQZ26.CBT": 8, "ZQF27.CBT": 12, "ZQG27.CBT": 20,
            "ZQH27.CBT": 30, "ZQJ27.CBT": 30}
FETCHED_MIN = 2                                                        # البوت جلبها قبل دقيقتين


def utc(text):
    return float(calendar.timegm(time.strptime(text, "%Y-%m-%d %H:%M")))


NOW = utc("2026-10-08 14:00")         # الخميس


def _load():
    spec = importlib.util.spec_from_file_location("fed_pricing_atom_121_under_test", ATOM_DIR / "atom.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


MOD = _load()


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """أيّ طلبٍ حقيقيّ في الاختبار يُسجَّل ويُفشل الاختبار."""
    calls = []

    def guard(*args, **kwargs):
        calls.append(args)
        raise AssertionError("no network in tests")
    monkeypatch.setattr(urllib.request, "urlopen", guard)
    yield calls
    assert not calls, "اختبارٌ لمس الشبكة"


def make_bridge(path, prices=PRICES, now=NOW, rows=None, table=True):
    con = sqlite3.connect(path)
    if not table:
        con.execute("CREATE TABLE calendar (id INTEGER PRIMARY KEY)")
    else:
        con.execute(SCHEMA)
        if rows is None:
            rows = [(s, MONTHS[s], p, round(100 - p, 4), int(now - 60 * AGES_MIN[s]), int(now - 60 * FETCHED_MIN),
                     "yahoo") for s, p in prices.items()]
        con.executemany("INSERT INTO fed_futures VALUES (?,?,?,?,?,?,?)", rows)
    con.commit()
    con.close()
    return str(path)


async def _atom(monkeypatch, path, *, now=NOW, boot_delay_s=3600.0, config=None):
    monkeypatch.setenv("NQ_BRIDGE_DB", str(path))
    bus = Bus()
    atom = MOD.Atom()
    atom._clock = lambda: now
    await atom.initialize(AtomContext(121, {**CONFIG, "boot_delay_s": boot_delay_s, **(config or {})}, Logger(),
                                      bus.publish, bus.subscribe))
    await atom.start()
    return atom, bus


async def _target(atom, upper=4.0):
    await atom._on_monetary({"id": "monetary_policy_knowledge", "computed_at": NOW - 120,
                             "facts": {"fed_rate_current": upper}})


def _walk(value, path=""):
    if isinstance(value, dict):
        for key, inner in value.items():
            yield "key", str(key), path
            yield from _walk(inner, path + "." + str(key))
    elif isinstance(value, list):
        for inner in value:
            yield from _walk(inner, path)
    elif isinstance(value, str):
        yield "text", value, path


# ── رموز العقود والوقت ─────────────────────────────────────────────────────────
def test_contract_symbols_across_year():
    assert [chain.contract_symbol(2030, m)[2] for m in range(1, 13)] == list("FGHJKMNQUVXZ")
    assert chain.contract_symbol(2026, 11) == "ZQX26.CBT" and chain.contract_symbol(2029, 12) == "ZQZ29.CBT"
    assert chain.contract_symbol(2030, 1) == "ZQF30.CBT" and chain.month_add(2026, 12, 1) == (2027, 1)
    assert MOD.month_of("ZQX26.CBT", "2026-11") == "2026-11" and MOD.month_of("ZQF27.CBT", None) == "2027-01"
    assert MOD.month_of("ZQX26.CBT", "2026-12") is None and MOD.month_of("XYZ", None) is None   # الرمز يطابق الشهر
    # النافذة من الجدول: الجاري حتّى آخر شهرٍ فيه (والمنقضي لا يدخل).
    quotes = {"2026-09": {}, "2026-10": {}, "2027-03": {}}
    assert [chain.contract_symbol(*ym) for ym in facts_text.window(NOW, quotes)] == [
        "ZQV26.CBT", "ZQX26.CBT", "ZQZ26.CBT", "ZQF27.CBT", "ZQG27.CBT", "ZQH27.CBT"]
    late = facts_text.window(utc("2026-12-31 23:00"), {"2027-05": {}})
    assert [chain.contract_symbol(*ym) for ym in late] == ["ZQZ26.CBT", "ZQF27.CBT", "ZQG27.CBT", "ZQH27.CBT",
                                                           "ZQJ27.CBT", "ZQK27.CBT"]
    assert facts_text.window(NOW, {}) == [(2026, 10)] and len(facts_text.window(NOW, {"2099-01": {}})) == 12


def test_decision_time_is_two_pm_new_york():
    # صيفًا (−4) 18:00 غرينتش، وشتاءً (−5) 19:00 — بعد 2026-11-01 يعود التوقيت الشتويّ، وقبل 2026-03-08 شتويّ.
    assert chain.decision_utc(date(2026, 10, 28)) == utc("2026-10-28 18:00")
    assert chain.decision_utc(date(2026, 12, 9)) == utc("2026-12-09 19:00")
    assert chain.decision_utc(date(2026, 3, 18)) == utc("2026-03-18 18:00")
    assert chain.decision_utc(date(2026, 1, 28)) == utc("2026-01-28 19:00")
    schedule, bad = chain.build_schedule(["2026-10-28", "bad-day", "2026-10-28"], ["2026-10-28", "2027-01-27"])
    assert bad == 1 and [m["day"].isoformat() for m in schedule] == ["2026-10-28", "2027-01-27"]
    assert [m["tentative"] for m in schedule] == [False, True]


# ── الحساب بأرقام اليوم ────────────────────────────────────────────────────────
async def test_october_and_december_from_todays_quotes(tmp_path, monkeypatch):
    atom, bus = await _atom(monkeypatch, make_bridge(tmp_path / "brain.db"))
    await _target(atom, 4.0)
    payload = await atom.refresh(NOW)
    f = payload["facts"]
    assert payload["status"] == "ok" and payload["symbol"] == "USTEC" and f["pricing_available"] is True
    oct_, dec, jan = f["meetings"]
    # تشرين الأوّل (N=31، d=28، السريان من 29): تشرين الثاني بلا اجتماع ⟸ بعده = 100 − 96.07 = 3.93.
    # قبله = (3.885×31 − 3.93×3) ÷ 28 = (120.435 − 11.79) ÷ 28 = 108.645 ÷ 28 = 3.880178…
    # الفرق = (3.93 − 3.880178)×100 = +4.982 ن.أ ⟸ 5.0 · رفع 4.982 ÷ 25 = 19.93٪ ⟸ 19.9.
    assert oct_["date"] == "2026-10-28" and oct_["decision_utc"] == "2026-10-28T18:00Z"
    assert oct_["rate_before"] == pytest.approx(3.8802) and oct_["rate_after"] == pytest.approx(3.93)
    assert oct_["rate_before_method"] == "solved_backward" and oct_["rate_after_method"] == "month_average"
    assert oct_["expected_change_bp"] == 5.0 and oct_["market_implied_hike_pct"] == 19.9
    assert oct_["market_implied_cut_pct"] == 0.0 and oct_["market_implied_hike_50bp_pct"] == 0.0
    assert [c["symbol"] for c in oct_["contracts_used"]] == ["ZQV26.CBT", "ZQX26.CBT"]
    assert oct_["contracts_used"][0]["price"] == 96.115 and oct_["contracts_used"][0]["implied_rate"] == 3.885
    # كانون الأوّل (N=31، d=9): كانون الثاني فيه اجتماع ⟸ بعده = (4.085×31 − 3.93×9) ÷ 22 = 91.265 ÷ 22 = 4.148409…
    # الفرق = +21.84 ن.أ ⟸ 21.8 · رفع 87.36٪ ⟸ 87.4.
    assert dec["decision_utc"] == "2026-12-09T19:00Z" and dec["rate_before"] == pytest.approx(3.93)
    assert dec["rate_after"] == pytest.approx(4.1484) and dec["rate_after_method"] == "solved_forward"
    assert dec["expected_change_bp"] == 21.8 and dec["market_implied_hike_pct"] == 87.4
    # كانون الثاني 2027 (مبدئيّ): شباط بلا اجتماع ⟸ بعده = 4.16 (قيمة اختبار) · الفرق = +1.16 ⟸ 1.2 · 4.6٪.
    assert jan["tentative"] is True and jan["expected_change_bp"] == 1.2 and jan["market_implied_hike_pct"] == 4.6
    # الحقائق العشر الأولى
    assert f["next_fomc_date"] == "2026-10-28" and f["days_to_next_fomc"] == 20.2      # 20 يومًا و4 ساعات
    assert f["expected_change_bp_next"] == 5.0 and f["market_implied_hike_pct_next"] == 19.9
    assert f["market_implied_cut_pct_next"] == 0.0 and f["implied_rate_after_next"] == pytest.approx(3.93)
    assert f["expected_change_bp_second"] == 21.8
    assert f["implied_rate_year_end"] == pytest.approx(4.1484) and f["year_end_last_meeting_date"] == "2026-12-09"
    # عمر سعر السوق: أقدم عقدَي الاجتماع القادم (X26 قبل 6 د)؛ وعمر الجلب: البوت قبل دقيقتين.
    assert f["quotes_age_minutes"] == 6 and f["fetched_age_minutes"] == 2
    # الفرق عن وسط النطاق (4.00 الحدّ الأعلى ⟸ الوسط 3.875): 3.880178 − 3.875 = +0.52 ⟸ 0.5 ن.أ.
    assert f["fed_target_upper"] == 4.0 and f["fed_target_mid"] == 3.875
    assert f["implied_now_vs_target_mid_bp"] == 0.5 and oct_["rate_after_vs_target_mid_bp"] == 5.5
    assert dec["rate_after_vs_target_mid_bp"] == 27.3
    assert f["contracts_in_window"] == 6 and f["contracts_available"] == 6 and f["bridge_rows"] == 6
    assert f["contracts"][0]["source"] == "yahoo" and f["contracts"][0]["fetched_age_minutes"] == 2
    assert f["bridge_read_error"] is None and f["bridge_bad_rows"] == []
    assert payload["summary_ar"] == ("السوق يسعّر لاجتماع 28 تشرين الأوّل (بعد 20 يومًا): +5 ن.أ (رفع 20٪) · "
                                     "9 كانون الأوّل: +22 ن.أ (رفع 87٪) · الأسعار من ياهو قبل 6 د "
                                     "(جلبها بوت الأخبار قبل 2 د)")
    assert bus.payloads("knowledge.fed_pricing.state")[-1] is payload
    await atom.stop()


async def test_meeting_free_current_month_and_passed_meeting(tmp_path, monkeypatch):
    nov = utc("2026-11-15 15:00")
    atom, _ = await _atom(monkeypatch, make_bridge(tmp_path / "nov.db", {**PRICES, "ZQJ27.CBT": 95.78}, now=nov), now=nov)
    f = (await atom.refresh(nov))["facts"]
    # تشرين الثاني بلا اجتماع ⟸ السارية الآن = ضمنيّه 3.93 مباشرةً؛ وتشرين الأوّل المنقضي خارج النافذة.
    assert f["implied_rate_now"] == pytest.approx(3.93) and f["implied_rate_now_method"] == "month_average"
    assert f["next_fomc_date"] == "2026-12-09" and f["expected_change_bp_next"] == 21.8
    assert f["contracts"][0]["symbol"] == "ZQX26.CBT" and f["contracts_in_window"] == 6
    assert f["fed_target_upper"] is None and f["implied_now_vs_target_mid_bp"] is None   # لم يصل 118 بعد
    # يوم القرار بعد صدوره (18:00 غرينتش): تشرين الأوّل فيه اجتماعٌ مرّ ⟸ معادلته لا تُستعمل، والقادم كانون الأوّل.
    after = utc("2026-10-28 19:00")
    atom2, _ = await _atom(monkeypatch, make_bridge(tmp_path / "after.db", now=after), now=after)
    g = (await atom2.refresh(after))["facts"]
    assert g["next_fomc_date"] == "2026-12-09" and g["implied_rate_now"] == pytest.approx(3.93)
    assert g["expected_change_bp_next"] == 21.8
    await atom.stop()
    await atom2.stop()


async def test_missing_month_contract_solved_backward_or_declared(tmp_path, monkeypatch):
    prices = {k: v for k, v in PRICES.items() if k != "ZQX26.CBT"}
    atom, _ = await _atom(monkeypatch, make_bridge(tmp_path / "gap.db", prices))
    f = (await atom.refresh(NOW))["facts"]
    oct_ = f["meetings"][0]
    # بلا تشرين الثاني: شباط يثبّت بعد كانون الثاني = 4.16، ثمّ خلفيًّا:
    #   قبل كانون الثاني = (4.15×31 − 4.16×4) ÷ 27 = 112.01 ÷ 27 = 4.148519
    #   قبل كانون الأوّل = (4.085×31 − 4.148519×22) ÷ 9 = 3.929733
    #   قبل تشرين الأوّل = (3.885×31 − 3.929733×3) ÷ 28 = 3.880207 ⟸ الفرق +4.95 ⟸ 5.0 · 19.8٪.
    assert f["pricing_available"] is True and oct_["rate_after_method"] == "solved_backward"
    assert oct_["rate_before"] == pytest.approx(3.8802) and oct_["rate_after"] == pytest.approx(3.9297)
    assert oct_["expected_change_bp"] == 5.0 and oct_["market_implied_hike_pct"] == 19.8
    assert [c["symbol"] for c in oct_["contracts_used"]] == ["ZQF27.CBT", "ZQG27.CBT", "ZQV26.CBT", "ZQZ26.CBT"]
    assert f["expected_change_bp_second"] == 21.9                      # 4.148519 − 3.929733
    assert f["contracts_available"] == 5 and f["contracts_in_window"] == 6
    missing = [c for c in f["contracts"] if not c["available"]]
    assert [c["symbol"] for c in missing] == ["ZQX26.CBT"]
    # وبلا تشرين الأوّل أيضًا: لا يُحسب «قبل» الاجتماع القادم ⟸ غير متاح بسببه، ولا تخمين.
    worse = {k: v for k, v in prices.items() if k != "ZQV26.CBT"}
    atom2, _ = await _atom(monkeypatch, make_bridge(tmp_path / "worse.db", worse))
    payload = await atom2.refresh(NOW)
    g = payload["facts"]
    assert payload["status"] == "unavailable" and g["pricing_available"] is False
    assert g["pricing_unavailable_reason"] == "MISSING_CONTRACTS"
    assert g["pricing_unavailable_detail"] == "ZQV26.CBT ZQX26.CBT"
    assert g["expected_change_bp_next"] is None and g["expected_change_bp_second"] == 21.9
    assert "عقودٌ ناقصة" in payload["summary_ar"]
    await atom.stop()
    await atom2.stop()


async def test_cut_and_above_hundred_percent(tmp_path, monkeypatch):
    # تشرين الثاني 96.20 (3.80): قبل تشرين الأوّل = (120.435 − 3.80×3) ÷ 28 = 3.894107 ⟸ الفرق −9.41 ⟸ خفض 37.6٪.
    atom, _ = await _atom(monkeypatch, make_bridge(tmp_path / "cut.db", {**PRICES, "ZQX26.CBT": 96.20}))
    payload = await atom.refresh(NOW)
    f = payload["facts"]
    assert f["expected_change_bp_next"] == -9.4 and f["market_implied_cut_pct_next"] == 37.6
    assert f["market_implied_hike_pct_next"] == 0.0 and "-9 ن.أ (خفض 38٪)" in payload["summary_ar"]
    shares = chain.move_shares(30.0)                    # 30 ÷ 25 = 1.2 ⟸ رفع 100٪ ومنه 50 ن.أ 20٪
    assert (shares["market_implied_hike_pct"], shares["market_implied_hike_50bp_pct"]) == (100.0, 20.0)
    assert shares["market_implied_cut_pct"] == 0.0 and shares["priced_25bp_steps"] == 1.2
    assert chain.move_shares(-12.5)["market_implied_cut_pct"] == 50.0
    assert chain.move_shares(0.0)["market_implied_hike_pct"] == 0.0 and chain.move_shares(None)["market_implied_cut_pct"] is None
    row = {"expected_change_bp": 30.0, **shares}
    assert facts_text._move_ar(row) == "+30 ن.أ (رفع 100٪ ومنه 50 ن.أ 20٪)"
    await atom.stop()


def test_year_end_beyond_window_is_declared():
    schedule, _ = chain.build_schedule(CONFIG["fomc_decision_days"], CONFIG["fomc_tentative_days"])
    feb = utc("2027-02-10 12:00")
    months = chain.window_months(feb, 5)                 # شباط … تمّوز 2027 — واجتماع 8 كانون الأوّل خارجها
    path = chain.solve_path(months, {ym: 4.0 for ym in months}, schedule, feb)
    year = chain.year_end(path, schedule, feb)
    assert year == {"rate": None, "meeting": "2027-12-08", "reason": "MEETING_BEYOND_CONTRACT_WINDOW"}


# ── الجسر: غيابٌ أو تلفٌ أو قفل لا يكسر ────────────────────────────────────────
async def test_missing_bridge_table_or_file_is_named_not_a_crash(tmp_path, monkeypatch):
    atom, bus = await _atom(monkeypatch, make_bridge(tmp_path / "no_table.db", table=False))
    payload = await atom.refresh(NOW)
    f = payload["facts"]
    assert payload["status"] == "unavailable" and f["pricing_available"] is False
    assert f["pricing_unavailable_reason"] == "BRIDGE_TABLE_MISSING"
    assert f["pricing_unavailable_reason_ar"] == "جدول الجسر غير موجود بعد"
    assert f["next_fomc_date"] == "2026-10-28" and f["days_to_next_fomc"] == 20.2      # الجدول لا يحتاج الجسر
    assert f["quotes_age_minutes"] is None and f["contracts_available"] == 0
    assert payload["summary_ar"] == ("تسعير قرار الفائدة غير متاح: جدول الجسر غير موجود بعد · "
                                     "الاجتماع القادم 28 تشرين الأوّل بعد 20 يومًا")
    health = await atom.health_check()
    assert health.state == HealthState.DEGRADED and "أخطاء قراءة=1" in health.message
    atom2, _ = await _atom(monkeypatch, tmp_path / "absent.db")
    g = (await atom2.refresh(NOW))["facts"]
    assert g["pricing_unavailable_reason"] == "BRIDGE_FILE_MISSING" and g["pricing_available"] is False
    broken = tmp_path / "broken.db"
    broken.write_bytes(b"not a database at all" * 50)
    atom3, _ = await _atom(monkeypatch, broken)
    h = (await atom3.refresh(NOW))["facts"]
    assert h["pricing_unavailable_reason"] == "BRIDGE_READ_FAILED" and "not a database" in h["bridge_read_detail"]
    empty = tmp_path / "empty.db"
    make_bridge(empty, prices={})
    atom4, _ = await _atom(monkeypatch, empty)
    assert (await atom4.refresh(NOW))["facts"]["pricing_unavailable_reason"] == "NO_CONTRACTS_IN_BRIDGE"
    atom5, _ = await _atom(monkeypatch, make_bridge(tmp_path / "x.db"))
    assert (await atom5.refresh(NOW, ))["facts"]["pricing_available"] is True
    atom5._read = lambda path: (_ for _ in ()).throw(RuntimeError("boom"))           # قارئٌ يرمي ⟸ سببٌ معلن
    assert (await atom5.refresh(NOW))["facts"]["bridge_read_error"] == "BRIDGE_READ_FAILED"
    for a in (atom, atom2, atom3, atom4, atom5):
        await a.stop()


async def test_invalid_rows_are_flagged_and_skipped(tmp_path, monkeypatch):
    t = int(NOW - 300)
    rows = [("ZQV26.CBT", "2026-10", 96.115, 3.885, t, t, "yahoo"),
            ("ZQX26.CBT", "2026-11", None, 3.93, t, t, "yahoo"),          # السعر غائب ⟸ 100 − الضمنيّ = 96.07
            ("ZQZ26.CBT", "2026-12", 150.0, -50.0, t, t, "yahoo"),        # سعرٌ خارج 0–100
            ("ZQF27.CBT", "2027-02", 95.85, 4.15, t, t, "yahoo"),         # الرمز لا يطابق الشهر
            ("ZQG27.CBT", "2027-02", 95.84, 4.16, None, t, "yahoo"),      # بلا وقت سوق
            ("ZQH27.CBT", "2027-03", 95.80, 4.20, t, t, "yahoo")]
    atom, _ = await _atom(monkeypatch, make_bridge(tmp_path / "bad.db", rows=rows))
    f = (await atom.refresh(NOW))["facts"]
    assert f["bridge_bad_rows"] == ["ZQZ26.CBT", "ZQF27.CBT", "ZQG27.CBT"] and f["bridge_rows"] == 6
    by = {c["symbol"]: c for c in f["contracts"]}
    assert by["ZQX26.CBT"]["price"] == pytest.approx(96.07) and by["ZQX26.CBT"]["bridge_row_invalid"] is False
    assert by["ZQZ26.CBT"]["bridge_row_invalid"] is True and by["ZQZ26.CBT"]["available"] is False
    assert f["contracts_in_window"] == 6 and f["contracts_available"] == 3 and f["expected_change_bp_next"] == 5.0
    await atom.stop()


async def test_locked_bridge_keeps_last_quotes_with_their_ages(tmp_path, monkeypatch):
    path = make_bridge(tmp_path / "lock.db")
    atom, _ = await _atom(monkeypatch, path)
    assert (await atom.refresh(NOW))["facts"]["pricing_available"] is True
    holder = sqlite3.connect(path, timeout=0.1)
    holder.execute("BEGIN EXCLUSIVE")                   # البوت يكتب: القفل يمنع القراءة بعد مهلةٍ قصيرة
    try:
        f = (await atom.refresh(NOW + 600))["facts"]
    finally:
        holder.rollback()
        holder.close()
    assert f["bridge_read_error"] == "BRIDGE_READ_FAILED" and "locked" in f["bridge_read_detail"]
    assert f["pricing_available"] is True and f["quotes_age_minutes"] == 16 and f["fetched_age_minutes"] == 12
    await atom.stop()


async def test_unexpected_compute_error_is_declared_not_a_crash(tmp_path, monkeypatch):
    atom, bus = await _atom(monkeypatch, make_bridge(tmp_path / "c.db"))
    atom._read = lambda path: {"quotes": {"2026-10": {"price": None, "market_time": NOW}}}   # حالةٌ تالفة عمدًا
    payload = await atom.refresh(NOW)
    f = payload["facts"]
    assert payload["status"] == "unavailable" and f["pricing_unavailable_reason"] == "COMPUTE_FAILED"
    assert list(f)[:10] == FIRST_TEN and "TypeError" in f["pricing_unavailable_detail"]
    assert "تعذّر حساب التسعير" in payload["summary_ar"] and bus.payloads("knowledge.fed_pricing.state")
    assert (await atom.health_check()).state == HealthState.DEGRADED
    await atom.stop()


def test_atom_has_no_network_code():
    banned = {"socket", "requests", "urllib", "aiohttp", "httpx", "websockets", "http"}
    for path in [ATOM_DIR / "atom.py", *sorted(ATOM_DIR.glob("fed_pricing_*.py"))]:
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            names = [a.name for a in node.names] if isinstance(node, ast.Import) else (
                [node.module or ""] if isinstance(node, ast.ImportFrom) else [])
            assert not {n.split(".")[0] for n in names} & banned, (path.name, names)


# ── العقد والجدولة والحفظ ──────────────────────────────────────────────────────
async def test_payload_contract_first_ten_and_no_forbidden_words(tmp_path, monkeypatch):
    atom, _ = await _atom(monkeypatch, make_bridge(tmp_path / "ok.db"))
    await _target(atom)
    payload = await atom.refresh(NOW)
    assert set(payload) == {"id", "symbol", "status", "facts", "computed_at", "summary_ar", "source"}
    f = payload["facts"]
    assert list(f)[:10] == FIRST_TEN
    for key in FIRST_TEN:
        value = f[key]
        assert value is None or isinstance(value, (int, float, bool)) or (isinstance(value, str) and len(value) <= 24), key
    assert "federalreserve.gov" in f["fomc_schedule_source"] and "news bot" in payload["source"]
    assert f["fomc_tentative_dates"][0] == "2027-01-27" and len(f["limits_ar"]) == 4
    for kind, text, where in _walk(payload):
        words = set(re.split(r"[^a-z]+", text.lower()))
        assert not words & set(FORBIDDEN), (kind, where, text)
    failing, _ = await _atom(monkeypatch, make_bridge(tmp_path / "none.db", table=False))
    unavailable = await failing.refresh(NOW)
    assert list(unavailable["facts"])[:10] == FIRST_TEN
    for kind, text, where in _walk(unavailable):
        assert not set(re.split(r"[^a-z]+", text.lower())) & set(FORBIDDEN), (kind, where, text)
    await atom.stop()
    await failing.stop()


async def test_read_every_pulse_boot_read_and_config_path(tmp_path, monkeypatch):
    path = make_bridge(tmp_path / "pulse.db")
    reads = []
    atom, bus = await _atom(monkeypatch, path, boot_delay_s=0.0)
    atom._read = lambda p: reads.append(p) or MOD.read_bridge(p)
    for _ in range(100):                                 # القراءة الأولى عند الإقلاع (هنا بلا تأجيل)
        if bus.payloads("knowledge.fed_pricing.state"):
            break
        await asyncio.sleep(0.02)
    assert bus.payloads("knowledge.fed_pricing.state") and len(reads) <= 1
    before = len(reads)
    await atom._on_pulse({"official_time": NOW + 300})
    await atom._on_pulse({"official_time": NOW + 600})
    assert len(reads) == before + 2 and reads[-1] == path                     # كلّ SYS_5MIN قراءة
    assert bus.payloads("knowledge.fed_pricing.state")[-1]["facts"]["quotes_age_minutes"] == 16
    await atom._on_pulse("not a pulse")
    await atom._on_monetary({"facts": "x"})
    await atom._on_monetary({"facts": {"fed_rate_current": None}})
    assert atom._rejected == {"bad_pulse": 1, "bad_monetary": 1, "monetary_without_rate": 1}
    # مسار `config` حين لا متغيّر بيئة.
    monkeypatch.delenv("NQ_BRIDGE_DB")
    assert MOD.resolve_bridge_path(str(path)) == str(path)
    assert MOD.resolve_bridge_path(None).endswith(r"MetaQuotes\Terminal\Common\Files\nq_brain.db")
    await atom.stop()


async def test_snapshot_restore_keeps_last_quotes_and_ages(tmp_path, monkeypatch):
    atom, _ = await _atom(monkeypatch, make_bridge(tmp_path / "s.db"))
    await _target(atom, 4.0)
    await atom.refresh(NOW)
    health = await atom.health_check()
    assert health.state == HealthState.HEALTHY and "2026-10-28" in health.message and "عقود=6/6" in health.message
    state = await atom.snapshot()
    # بعد الإقلاع بساعة والجسر مقفلٌ لحظةً: آخر الأسعار المعروفة تبقى، وأعمارها تكبر معلنةً.
    later = NOW + 3600
    fresh, _ = await _atom(monkeypatch, tmp_path / "s.db", now=later)
    await fresh.restore(state)
    fresh._read = lambda path: {"error": "BRIDGE_READ_FAILED", "detail": "database is locked"}
    f = (await fresh.refresh(later))["facts"]
    assert f["pricing_available"] is True and f["expected_change_bp_next"] == 5.0
    assert f["quotes_age_minutes"] == 66 and f["fetched_age_minutes"] == 62 and f["contracts"][0]["age_minutes"] == 64
    assert f["fed_target_upper"] == 4.0 and f["implied_now_vs_target_mid_bp"] == 0.5
    assert "قبل 1 س" in (fresh._last or {}).get("summary_ar", "")
    # والجدول غائب: «غير متاح» بسببه، والأسعار المستعادة تبقى في التفاصيل بأعمارها ولا يُسعَّر منها.
    fresh._read = lambda path: {"error": "BRIDGE_TABLE_MISSING", "detail": "fed_futures"}
    g = (await fresh.refresh(later))["facts"]
    assert g["pricing_available"] is False and g["pricing_unavailable_reason"] == "BRIDGE_TABLE_MISSING"
    assert g["expected_change_bp_next"] is None and g["contracts"][0]["age_minutes"] == 64
    assert "kept with their ages: 6" in g["pricing_unavailable_detail"] and len(fresh._quotes) == 6
    # لقطة النسخة الأولى (مفاتيحها رموز العقود) تُستعاد بأشهرها، والتالف يُعدّ ويُترك.
    old = {"quotes": {"ZQV26.CBT": {"price": 96.115, "market_time": NOW - 240, "fetched_at": NOW},
                      "ZQX26.CBT": {"price": 150, "market_time": 1}, "X": "y"}, "last_fetch": {"ok": 6}}
    other, _ = await _atom(monkeypatch, tmp_path / "s.db")
    await other.restore(old)
    assert set(other._quotes) == {"2026-10"} and other._quotes["2026-10"]["symbol"] == "ZQV26.CBT"
    assert other._rejected == {"bad_snapshot_quote": 2}
    for a in (atom, fresh, other):
        await a.stop()
