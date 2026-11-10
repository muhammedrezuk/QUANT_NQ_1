"""معرفة الشركات والأسواق 122 — كلّ حقيقة على قواعد اختبارٍ مؤقّتة بأرقامٍ معروفة (أسعارٌ وجسرٌ وتاريخ)، لا الحيّة.

٢٠٢٦-١٠-٠٨ (ختم المالك «NQ» — المعرفة أوّلًا): الذرّة لا تتّصل بالإنترنت (أمر المالك «الأخبار من مكانٍ واحد») —
مواعيد الأرباح من جدولَي قاعدة الجسر يكتبهما بوت الأخبار. والذرّة تُحمَّل هنا من ملفّها مباشرةً (لا من السجلّ).
"""
import asyncio
import calendar
import importlib.util
import json
import re
import sqlite3
import sys
import time
from datetime import date
from pathlib import Path

import pytest

FOLDER = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOLDER))          # الوحدات الشقيقة تُستورد باسمها (المُقلِع يضيف مجلّد الذرّة)

from core.contracts.atom import AtomContext  # noqa: E402
from tests.learning_test_support import Bus, Logger  # noqa: E402

_SPEC = importlib.util.spec_from_file_location("atom_122_companies_under_test", FOLDER / "atom.py")
MODULE = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = MODULE
_SPEC.loader.exec_module(MODULE)
import companies_earnings as earnings  # noqa: E402

FORBIDDEN = ("direction", "signal", "strength", "confidence", "weight", "score", "probability",
             "threshold", "depth", "readiness", "buy", "sell", "bullish", "bearish", "strong", "weak")
OFFSET = 3 * 3600                        # وقت الخادم = غرينتش + 3 ساعات (مقيس على القاعدة الحيّة)
TICKERS = ["NVDA", "MSFT", "AAPL", "TSLA", "GOOGL", "AMD", "NFLX", "COST", "CSCO"]
# نصّ موقع ناسداك الحقيقيّ لإنفيديا (جلبٌ قراءةً ١٠-٠٨) — يُنقل كما هو في حقلٍ مسمًّى.
NVDA_TEXT = ("NVIDIA Corporation Common Stock is estimated to report earnings on  11/18/2026. The upcoming earnings "
             "date is derived from an algorithm based on a company's historical reporting dates. According to Zacks "
             "Investment Research, based on  13 analysts' forecasts, the consensus EPS forecast for the quarter is $2.47.")


def utc(text):
    return float(calendar.timegm(time.strptime(text, "%Y-%m-%d %H:%M")))


def bstart(day):
    """بداية يوم الوسيط صيفًا: منتصف ليله بوقت الخادم = 21:00 غرينتش من اليوم السابق."""
    return int(utc(day + " 00:00")) - OFFSET


NOW = utc("2026-10-08 15:00")            # الخميس 11:00 بتوقيت نيويورك — الجلسة الأمريكيّة مفتوحة
SERVER_DAY = int(utc("2026-10-08 00:00"))


def quote(ticker, symbol, bid, ask, prev, opened, age_s=30.0, bar=SERVER_DAY):
    return (ticker, symbol, bid, ask, None, int(NOW - age_s), opened, max(bid, ask), min(bid, ask), prev, bar,
            int(NOW - 20))


QUOTES = [quote("NVDA", "NVDA.NAS", 101.9, 102.1, 100.0, 101.0), quote("MSFT", "MSFT.NAS", 99.0, 99.0, 100.0, 99.5),
          quote("AAPL", "AAPL.NAS", 100.0, 100.0, 100.0, 100.0), quote("TSLA", "TSLA.NAS", 97.0, 97.0, 100.0, 98.0),
          ("GOOGL", "", None, None, None, None, None, None, None, None, None, int(NOW - 20)),
          quote("VIX", "VIX_V6", 16.1, 16.3, 16.7, 16.6), quote("DXY", "DXY_Z6", 101.4, 101.4, 101.2, 101.3)]


def make_stocks(path, rows=QUOTES, written=NOW - 20):
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE stock_quotes (ticker TEXT PRIMARY KEY, broker_symbol TEXT, bid REAL, ask REAL, "
                "last REAL, tick_time_utc INTEGER, day_open REAL, day_high REAL, day_low REAL, prev_close REAL, "
                "day_bar_server INTEGER, written_at_utc INTEGER)")
    con.execute("CREATE TABLE stocks_meta (key TEXT PRIMARY KEY, value TEXT)")
    con.executemany("INSERT INTO stock_quotes VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    con.executemany("INSERT INTO stocks_meta VALUES (?,?)", [
        ("written_at_utc", str(int(written))), ("server_offset_s", str(OFFSET)), ("tickers_found", "6"),
        ("tickers_written", "6"), ("server", "ICMarketsSC-Demo")])
    con.commit()
    con.close()
    return str(path)


CAL = [("NFLX", "2026-10-20", "after-hours", 0, 0.82, "Netflix … expected* … after market close", NOW - 3600, "nasdaq"),
       ("TSLA", "2026-10-21", "not-supplied", 1, 1.75, "", NOW - 3600, "nasdaq"),
       ("NVDA", "2026-11-18", "after-hours", 1, 2.47, NVDA_TEXT, NOW - 3600, "nasdaq"),
       ("AAPL", "2026-10-08", "pre-market", 0, 1.6, "", NOW - 3600, "nasdaq"),
       ("CSCO", "2026-10-06", "after-hours", 0, 0.9, "", NOW - 3600, "nasdaq"),
       ("COST", "2026-10-08", "time-pre-market", 0, 5.1, "", NOW - 3600, "nasdaq"),
       ("MSFT", "2026-10-28", "not-supplied", 1, 3.9, "", NOW - 3600, "nasdaq"),
       ("XOM", "2026-10-30", "pre-market", 0, 1.0, "", NOW - 3600, "nasdaq")]          # ليست من شركاتنا
HIST = [("NVDA", "2026-08-26", "Jul 2026", 2.22, 2.09, 6.22), ("NVDA", "2026-05-20", "Apr 2026", 1.87, 1.7, 10.0),
        ("NVDA", "2026-02-25", "Jan 2026", 1.57, 1.45, 8.28), ("NVDA", "2025-11-19", "Oct 2025", 1.24, 1.18, 5.08),
        ("NVDA", "2025-08-27", "Jul 2025", 1.05, 1.01, 3.96),                           # الخامس الأقدم لا يُقرأ
        ("COST", "2026-08-31", "Aug 2026", 5.0, 4.9, 2.04), ("MSFT", "2026-08-25", "Jun 2026", 3.6, 3.4, 5.88)]


def make_bridge(path, cal=CAL, hist=HIST, tables=("calendar", "history")):
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE calendar (id TEXT)")              # جدول الجسر القائم — لا يُقرأ هنا
    if "calendar" in tables:
        con.execute("CREATE TABLE earnings_calendar (ticker TEXT PRIMARY KEY, report_date TEXT, report_time TEXT, "
                    "is_estimated INTEGER, eps_consensus REAL, source_text TEXT, fetched_at_utc INTEGER, source TEXT)")
        con.executemany("INSERT INTO earnings_calendar VALUES (?,?,?,?,?,?,?,?)", cal)
    if "history" in tables:
        con.execute("CREATE TABLE earnings_history (ticker TEXT, date_reported TEXT, fiscal_qtr_end TEXT, eps REAL, "
                    "eps_consensus REAL, surprise_pct REAL, fetched_at_utc INTEGER, source TEXT, "
                    "PRIMARY KEY (ticker, date_reported))")
        con.executemany("INSERT INTO earnings_history VALUES (?,?,?,?,?,?,?,?)",
                        [row + (int(NOW - 3600), "nasdaq") for row in hist])
    con.commit()
    con.close()
    return str(path)


# شموع D1 معروفة (أيّام الوسيط) — الحركة: 08-24 +1.0101 · 08-25 +1 · 08-26 −0.9901 · 08-27 +3 · 08-28 +0.5 ·
# 08-31 +1 · 09-01 −2 · 09-02 +0.5 · وإغلاق 10-07 للمرجع.
D1 = [("2026-08-21", 990.0), ("2026-08-24", 1000.0), ("2026-08-25", 1010.0), ("2026-08-26", 1000.0),
      ("2026-08-27", 1030.0), ("2026-08-28", 1035.15), ("2026-08-31", 1045.5015), ("2026-09-01", 1024.59147),
      ("2026-09-02", 1029.7144273), ("2026-10-07", 30000.0)]


def make_history(path, d1=D1, m1=()):
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE candles_history (symbol TEXT NOT NULL, period TEXT NOT NULL, period_seconds INTEGER "
                "NOT NULL, period_start INTEGER NOT NULL, open REAL NOT NULL, high REAL NOT NULL, low REAL NOT NULL, "
                "close REAL NOT NULL, tick_volume INTEGER NOT NULL, PRIMARY KEY (symbol, period, period_start)) "
                "WITHOUT ROWID")
    con.executemany("INSERT INTO candles_history VALUES ('USTEC','D1',86400,?,?,?,?,?,1)",
                    [(bstart(day), c, c, c, c) for day, c in d1])
    con.executemany("INSERT INTO candles_history VALUES ('USTEC','M1',60,?,?,?,?,?,1)",
                    [(int(start), o, max(o, c), min(o, c), c) for start, o, c in m1])
    con.commit()
    con.close()
    return str(path)


async def make(tmp_path, monkeypatch, *, stocks=None, bridge=None, history=None, boot_delay=3600.0, now=NOW):
    for env in ("NQ_STOCKS_DB", "NQ_BRIDGE_DB", "QUANT_HISTORY_DB"):
        monkeypatch.delenv(env, raising=False)
    bus = Bus()
    atom = MODULE.Atom()
    cfg = {"symbol": "USTEC", "tickers": TICKERS, "stocks_db": stocks or str(tmp_path / "no_stocks.db"),
           "bridge_db": bridge or str(tmp_path / "no_bridge.db"), "history_db": history or str(tmp_path / "no_hist.db"),
           "boot_delay_s": boot_delay}
    await atom.initialize(AtomContext(122, cfg, Logger(), bus.publish, bus.subscribe))
    await atom.start()
    atom._clock = lambda: now
    return atom, bus


async def feed_nasdaq(atom):
    """دقيقةٌ من أمس (إغلاق 30000) ثمّ أوّل دقيقةٍ اليوم (افتتاح 30100) ثمّ آخر دقيقة (30240)."""
    await atom._on_candle({"symbol": "USTEC", "timeframe": "1m", "period_start": utc("2026-10-07 20:59"),
                           "open": 29990.0, "close": 30000.0})
    await atom._on_candle({"symbol": "USTEC", "timeframe": "1m", "period_start": utc("2026-10-07 22:00"),
                           "open": 30100.0, "close": 30150.0})
    await atom._on_candle({"symbol": "USTEC", "timeframe": "1m", "period_start": utc("2026-10-08 14:58"),
                           "open": 30230.0, "close": 30240.0})


def _walk(value, path=""):
    if isinstance(value, dict):
        for key, inner in value.items():
            yield "key", str(key), path
            if key != "nasdaq_source_text":           # نصّ الموقع يُنقل كما هو في حقلٍ مسمًّى
                yield from _walk(inner, path + "." + str(key))
    elif isinstance(value, list):
        for inner in value:
            yield from _walk(inner, path)
    elif isinstance(value, str):
        yield "text", value, path


async def test_moves_breadth_indexes_and_nasdaq(tmp_path, monkeypatch):
    atom, bus = await make(tmp_path, monkeypatch, stocks=make_stocks(tmp_path / "s.db"))
    await feed_nasdaq(atom)
    await atom.read_earnings(NOW)                                         # الجسر غائب ⟸ الأرباح وحدها غير متاحة
    payload = await atom.refresh_quotes(NOW)
    f = payload["facts"]
    nvda = f["companies"]["NVDA"]
    assert (nvda["price"], nvda["change_pct"], nvda["from_open_pct"]) == (102.0, 2.0, 0.99)
    assert nvda["tick_age_min"] == 0.5 and nvda["day_bar_date"] == "2026-10-08" and nvda["day_bar_is_today"] is True
    assert (f["rising_count"], f["falling_count"], f["unchanged_count"], f["change_n"]) == (1, 2, 1, 4)
    assert f["companies_avg_change_pct"] == -0.5
    assert (f["max_change_ticker"], f["max_change_pct"], f["min_change_ticker"], f["min_change_pct"]) == (
        "NVDA", 2.0, "TSLA", -3.0)
    assert (f["vix_level"], f["vix_change_pct"], f["dxy_level"], f["dxy_change_pct"]) == (16.2, -2.994, 101.4, 0.198)
    assert (f["vix_broker_symbol"], f["dxy_broker_symbol"]) == ("VIX_V6", "DXY_Z6")
    # الناسداك: 30240 ÷ إغلاق أمس 30000 ⟸ +0.8٪، ومن الافتتاح 30100 ⟸ +0.465٪؛ والفرق الخام −0.5 − 0.8.
    assert (f["nasdaq_change_pct"], f["nasdaq_from_open_pct"], f["nasdaq_day_open_source"]) == (
        0.8, 0.465, "candle_1m_first")
    assert f["nasdaq_prev_close_day"] == "2026-10-07" and f["nasdaq_last_age_min"] == 1.0
    assert f["nasdaq_same_day_as_stocks"] is True and f["companies_minus_nasdaq_pct"] == -1.3
    assert f["us_session_open"] is True and f["stock_prices_stale"] is False
    assert f["stocks_written_age_min"] == pytest.approx(0.3) and f["stocks_tickers_found"] == 6
    assert payload["status"] == "partial" and payload["symbol"] == "USTEC"
    assert payload["summary_ar"].startswith(
        "الشركات الآن: 1 صاعدة · 2 هابطة · 1 بلا تغيّر · الأعلى إنفيديا +2.0٪ · الأدنى تسلا −3.0٪ · الناسداك +0.8٪ · "
        "الخوف 16.2 (−3.0٪) · الدولار 101.4 (+0.2٪) · مواعيد الأرباح غير متاحة: قاعدة الجسر غير موجودة")
    assert bus.payloads("knowledge.companies.state")[-1] is payload
    await atom.stop()


async def test_symbol_missing_at_broker_and_missing_row(tmp_path, monkeypatch):
    atom, _ = await make(tmp_path, monkeypatch, stocks=make_stocks(tmp_path / "s.db"))
    f = (await atom.refresh_quotes(NOW))["facts"]
    assert f["companies"]["GOOGL"] == {"available": False, "unavailable_reason": "not_at_broker", "broker_symbol": None}
    assert f["companies"]["AMD"] == {"available": False, "unavailable_reason": "no_row_written"}
    assert f["stocks_missing_at_broker"] == ["GOOGL"]
    await atom.stop()
    rows = [r for r in QUOTES if r[0] != "VIX"] + [("VIX", "", None, None, None, None, None, None, None, None, None, 1)]
    atom, _ = await make(tmp_path, monkeypatch, stocks=make_stocks(tmp_path / "s2.db", rows))
    payload = await atom.refresh_quotes(NOW)
    assert payload["facts"]["vix_level"] is None and payload["facts"]["vix_unavailable_reason"] == "not_at_broker"
    assert "الخوف غير متاح (غير موجود عند الوسيط)" in payload["summary_ar"] and payload["facts"]["stocks_missing_at_broker"] == [
        "GOOGL", "VIX"]
    await atom.stop()


async def test_missing_or_broken_stocks_db_does_not_break(tmp_path, monkeypatch):
    atom, bus = await make(tmp_path, monkeypatch)
    payload = await atom.refresh_quotes(NOW)
    f = payload["facts"]
    assert payload["status"] == "unavailable" and f["stocks_unavailable_reason"] == "STOCKS_DB_MISSING"
    assert f["rising_count"] is None and f["companies"] == {} and f["vix_level"] is None
    assert payload["summary_ar"].startswith("أسعار الشركات غير متاحة: قاعدة أسعار الشركات غير موجودة")
    health = await atom.health_check()
    assert health.state.name == "DEGRADED" and "أخطاء قراءة=1" in health.message
    await atom.stop()
    broken = tmp_path / "broken.db"
    broken.write_bytes(b"not a database at all" * 50)
    atom, _ = await make(tmp_path, monkeypatch, stocks=str(broken))
    assert (await atom.refresh_quotes(NOW))["facts"]["stocks_unavailable_reason"] == "STOCKS_DB_READ_FAILED"
    await atom.stop()


async def test_earnings_calendar_surprises_and_upcoming(tmp_path, monkeypatch):
    atom, _ = await make(tmp_path, monkeypatch, stocks=make_stocks(tmp_path / "s.db"), bridge=make_bridge(tmp_path / "b.db"))
    await atom.read_earnings(NOW)
    payload = await atom.refresh_quotes(NOW)
    f = payload["facts"]
    nvda = f["earnings"]["NVDA"]
    assert (nvda["next_date"], nvda["days_to"], nvda["time"], nvda["date_is_estimated"], nvda["eps_consensus"]) == (
        "2026-11-18", 41, "after_hours", True, 2.47)
    assert nvda["nasdaq_source_text"] == NVDA_TEXT                      # نصّ الموقع كما هو
    assert (nvda["last_report_date"], nvda["last_surprise_pct"], nvda["last_eps"], nvda["last_eps_consensus"]) == (
        "2026-08-26", 6.22, 2.22, 2.09)
    assert [s["date_reported"] for s in nvda["surprises"]] == ["2026-08-26", "2026-05-20", "2026-02-25", "2025-11-19"]
    assert f["earnings"]["COST"]["time"] == "pre_market" and "XOM" not in f["earnings"]
    assert (f["next_earnings_ticker"], f["days_to_next_earnings"], f["next_earnings_time"]) == ("AAPL", 0, "pre_market")
    assert f["earnings_today_count"] == 2 and f["earnings_dates_estimated_n"] == 3 and f["earnings_with_date_n"] == 7
    assert [(r["ticker"], r["days_to"]) for r in f["earnings_this_week"]] == [("CSCO", -2), ("AAPL", 0), ("COST", 0)]
    assert [r["ticker"] for r in f["earnings_upcoming"]] == ["AAPL", "COST", "NFLX", "TSLA", "MSFT", "NVDA"]
    assert f["earnings_fetch_age_h"] == 1.0 and f["earnings_available"] is True and payload["status"] == "ok"
    assert ("الأرباح القادمة: أبل اليوم (قبل الافتتاح)، ثمّ كوستكو اليوم (قبل الافتتاح)، ثمّ نتفليكس بعد 12 يومًا "
            "(بعد الإغلاق)") in payload["summary_ar"]
    await atom.stop()


async def test_nasdaq_reaction_on_report_days_from_known_candles(tmp_path, monkeypatch):
    atom, _ = await make(tmp_path, monkeypatch, bridge=make_bridge(tmp_path / "b.db"),
                         history=make_history(tmp_path / "h.db", d1=D1[:-1]))
    # وقت إعلان إنفيديا 08-26 رُئي في جلبٍ سابق (بعد الإغلاق) — يُستعاد؛ وإعلاناتها الأقدم وإعلان كوستكو تُفترض بآخر
    # وقتٍ رُئي للشركة نفسها؛ ومايكروسوفت بلا وقتٍ قطّ (تقويمها «غير معلن»).
    await atom.restore({"observed_times": {"NVDA|2026-08-26": {"time": "after_hours"}}})
    await atom.read_history(NOW)
    await atom.read_earnings(NOW)
    f = (await atom.publish(NOW))["facts"]
    nvda = f["earnings"]["NVDA"]["nasdaq_reaction"]["reports"][0]
    assert (nvda["date"], nvda["time"], nvda["time_basis"], nvda["reaction_day"]) == (
        "2026-08-26", "after_hours", "observed", "2026-08-27")
    assert (nvda["nasdaq_move_report_day_pct"], nvda["nasdaq_move_next_day_pct"], nvda["nasdaq_reaction_move_pct"]) == (
        -0.99, 3.0, 3.0)
    cost = f["earnings"]["COST"]["nasdaq_reaction"]["reports"][0]
    assert (cost["time"], cost["time_basis"], cost["time_assumed_from"], cost["reaction_day"]) == (
        "pre_market", "assumed_latest_observed", "2026-10-08", "2026-08-31")
    assert cost["nasdaq_reaction_move_pct"] == 1.0 and cost["nasdaq_move_next_day_pct"] == -2.0
    msft = f["earnings"]["MSFT"]["nasdaq_reaction"]
    assert msft["reports"][0]["time_basis"] == "unknown" and msft["n"] == 0
    assert msft["reports"][0]["nasdaq_move_report_day_pct"] == 1.0
    agg = f["earnings_reaction_history"]
    # ردّ الفعل: 3.0 و1.0 · يوم الإعلان: 0.99 و1 و1 · اليوم التالي: 3 و2 و0.99 ·
    # العاديّة (08-24 و08-28 و09-02 — من أقدم إعلانٍ 2025-11-19 بلا أيّام الإعلانات وما يليها): 1.0101 و0.5 و0.5.
    assert (agg["reaction_abs_move_pct"], agg["reaction_n"]) == (2.0, 2)
    assert (agg["report_day_abs_move_pct"], agg["report_day_n"]) == (0.997, 3)
    assert (agg["next_day_abs_move_pct"], agg["next_day_n"]) == (1.997, 3)
    assert (agg["normal_day_abs_move_pct"], agg["normal_day_n"]) == (0.67, 3)
    assert (agg["time_observed_n"], agg["time_assumed_n"], agg["time_unknown_n"]) == (1, 4, 1)
    assert (agg["from_date"], agg["through_date"]) == ("2025-11-19", "2026-09-02")
    # إعلانات إنفيديا الأقدم خارج شموع الاختبار ⟸ بلا حركة، لا صفر.
    older = f["earnings"]["NVDA"]["nasdaq_reaction"]["reports"][1]
    assert older["nasdaq_move_report_day_pct"] is None and older["time_assumed_from"] == "2026-11-18"
    assert f["nasdaq_history_days_n"] == 8 and f["nasdaq_prev_close"] == pytest.approx(1029.7144273)
    await atom.stop()


async def test_bridge_missing_tables_locked_and_keep_last(tmp_path, monkeypatch):
    atom, _ = await make(tmp_path, monkeypatch, stocks=make_stocks(tmp_path / "s.db"),
                         bridge=make_bridge(tmp_path / "none.db", tables=()))
    await atom.read_earnings(NOW)
    payload = await atom.refresh_quotes(NOW)
    assert payload["facts"]["earnings_unavailable_reason"] == "EARNINGS_TABLES_MISSING" and payload["status"] == "partial"
    assert "جدولا الأرباح غير موجودين في قاعدة الجسر بعد" in payload["summary_ar"]
    assert payload["facts"]["rising_count"] == 1                          # والباقي يعمل
    await atom.stop()
    atom, _ = await make(tmp_path, monkeypatch, bridge=make_bridge(tmp_path / "half.db", tables=("calendar",)))
    await atom.read_earnings(NOW)
    f = (await atom.publish(NOW))["facts"]
    assert f["earnings_available"] is True and f["earnings_missing_tables"] == ["earnings_history"]
    assert f["earnings"]["NVDA"]["last_surprise_pct"] is None and f["next_earnings_ticker"] == "AAPL"
    path = make_bridge(tmp_path / "b.db")
    await atom.stop()
    atom, _ = await make(tmp_path, monkeypatch, bridge=path)
    await atom.read_earnings(NOW)
    holder = sqlite3.connect(path, timeout=0.1)
    holder.execute("BEGIN EXCLUSIVE")                                    # كاتبٌ يقفل الجسر لحظة القراءة
    try:
        await atom.read_earnings(NOW + 300)
    finally:
        holder.rollback()
        holder.close()
    f = (await atom.publish(NOW + 300))["facts"]
    assert f["earnings_available"] is True and f["earnings_last_read_error"] == "BRIDGE_DB_READ_FAILED"
    assert f["next_earnings_ticker"] == "AAPL" and atom._read_errors == 1
    await atom.stop()


async def test_payload_contract_first_ten_scalars_and_no_forbidden_words(tmp_path, monkeypatch):
    atom, _ = await make(tmp_path, monkeypatch, stocks=make_stocks(tmp_path / "s.db"),
                         bridge=make_bridge(tmp_path / "b.db"), history=make_history(tmp_path / "h.db"))
    await atom.read_history(NOW)
    await atom.read_earnings(NOW)
    await feed_nasdaq(atom)
    payload = await atom.refresh_quotes(NOW)
    assert set(payload) == {"id", "symbol", "status", "facts", "computed_at", "summary_ar", "source"}
    f = payload["facts"]
    assert list(f)[:10] == ["rising_count", "falling_count", "nasdaq_change_pct", "companies_avg_change_pct",
                            "companies_minus_nasdaq_pct", "vix_level", "vix_change_pct", "dxy_change_pct",
                            "next_earnings_ticker", "days_to_next_earnings"]
    for key, value in list(f.items())[:10]:
        assert value is not None and (isinstance(value, (int, float)) or len(value) <= 24), key
    assert "تقديريّة" in f["limits_ar"] and "بائتة خارج الجلسة" in f["limits_ar"]
    for kind, text, where in _walk(payload):
        words = set(re.split(r"[^a-z]+", text.lower()))
        assert not words & set(FORBIDDEN), (kind, where, text)
    json.dumps(await atom.snapshot())                                     # اللقطة تُحفظ JSON
    await atom.stop()


async def test_snapshot_restore_keeps_last_earnings_times_and_closes(tmp_path, monkeypatch):
    atom, _ = await make(tmp_path, monkeypatch, bridge=make_bridge(tmp_path / "b.db"),
                         history=make_history(tmp_path / "h.db"))
    await atom.read_history(NOW)
    await atom.read_earnings(NOW)
    await atom.publish(NOW)
    state = json.loads(json.dumps(await atom.snapshot()))
    await atom.stop()
    other, _ = await make(tmp_path, monkeypatch, now=NOW + 600)          # الجسر غائبٌ بعد الإقلاع
    await other.restore(state)
    assert other._observed["NFLX|2026-10-20"]["time"] == "after_hours" and "TSLA|2026-10-21" not in other._observed
    await other.read_earnings(NOW + 600)
    f = (await other.publish(NOW + 600))["facts"]
    assert f["earnings_available"] is True and f["earnings_last_read_error"] == "BRIDGE_DB_MISSING"
    assert f["next_earnings_ticker"] == "AAPL" and f["earnings_fetch_age_h"] == pytest.approx(1.2)
    assert f["nasdaq_prev_close"] == 30000.0 and f["nasdaq_prev_close_source"] == "history_d1"
    assert other._published == 2                                         # 1 محفوظة + 1 بعد الإقلاع
    await other.restore({"earnings": {"error": "X"}, "observed_times": "bad", "nasdaq": None, "published": "x"})
    assert other._earnings["companies"] and other._published == 0
    await other.stop()


async def test_pulses_cadence_boot_and_rejects(tmp_path, monkeypatch):
    atom, bus = await make(tmp_path, monkeypatch, stocks=make_stocks(tmp_path / "s.db"),
                           history=make_history(tmp_path / "h.db"), boot_delay=0.0)
    for _ in range(100):                                                  # القراءة الأولى عند الإقلاع (بلا تأجيل)
        if bus.payloads("knowledge.companies.state"):
            break
        await asyncio.sleep(0.02)
    assert len(bus.payloads("knowledge.companies.state")) == 1 and atom._history["error"] is None
    await atom._on_second({"official_time": NOW + 1})                      # أقلّ من دقيقة ⟸ لا قراءة
    assert len(bus.payloads("knowledge.companies.state")) == 1
    await atom._on_second({"official_time": NOW + 61})
    assert len(bus.payloads("knowledge.companies.state")) == 2
    await atom._on_5min({"official_time": NOW + 300})                     # الجسر والنشر؛ التاريخ لليوم مقروء
    assert len(bus.payloads("knowledge.companies.state")) == 3
    await atom._on_second("not a pulse")
    await atom._on_5min({"official_time": "x"})
    await atom._on_candle({"symbol": "USTEC", "timeframe": "1m", "period_start": NOW, "close": None})
    await atom._on_candle("not a candle")
    await atom._on_candle({"symbol": "US500", "timeframe": "1m", "period_start": NOW, "close": 1.0})   # ليس لنا
    await atom._on_candle({"symbol": "USTEC", "timeframe": "5m", "period_start": NOW, "close": 1.0})   # إطارٌ آخر
    assert atom._rejected == {"bad_pulse": 2, "bad_candle": 2} and atom._candles == 0
    health = await atom.health_check()
    assert "نشرات=3" in health.message and "مرميّات=bad_candle=2 bad_pulse=2" in health.message
    await atom.stop()


async def test_live_daily_candle_beats_history_and_weekend_is_stale(tmp_path, monkeypatch):
    atom, _ = await make(tmp_path, monkeypatch, history=make_history(
        tmp_path / "h.db", m1=[(utc("2026-10-08 12:00"), 30010.0, 30090.0)]))
    await atom.read_history(NOW)
    f = (await atom.publish(NOW))["facts"]
    # التاريخ وحده: إغلاق أمس D1 (30000) وآخر M1 قبل ثلاث ساعات ⟸ +0.3٪ ويُذكر عمره في السطر.
    assert (f["nasdaq_change_pct"], f["nasdaq_last_source"], f["nasdaq_day_open_source"]) == (
        0.3, "history_m1", "history_m1_first")
    assert f["nasdaq_last_age_min"] == 179.0 and "الناسداك +0.3٪ (يوم 2026-10-08، آخر سعرٍ قبل 3.0 س)" in (
        await atom.publish(NOW))["summary_ar"]
    await atom._on_candle({"symbol": "USTEC", "timeframe": "1d", "period_start": bstart("2026-10-07"), "close": 29900.0})
    assert (await atom.publish(NOW))["facts"]["nasdaq_prev_close_source"] == "candle_1d"
    await atom.stop()
    saturday = utc("2026-10-10 12:00")
    atom, _ = await make(tmp_path, monkeypatch, stocks=make_stocks(tmp_path / "s.db"), now=saturday)
    payload = await atom.refresh_quotes(saturday)
    assert payload["facts"]["us_session_open"] is False and payload["facts"]["companies"]["NVDA"]["day_bar_is_today"] is False
    assert payload["summary_ar"].endswith("أسعار الأسهم بائتة: خارج الجلسة الأمريكيّة")
    assert earnings.week_start(date(2026, 10, 10)) == date(2026, 10, 12)
    assert earnings.week_start(date(2026, 10, 8)) == date(2026, 10, 5)
    await atom.stop()
