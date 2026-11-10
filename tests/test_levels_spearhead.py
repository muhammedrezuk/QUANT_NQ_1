"""The trader's levels and his two scenarios as one spearhead inside the live combination (the owner's paper of 2026-10-23):
the two scenarios on candles, the map fixed at the opening from the past only (last week on a Monday, the round numbers),
the triggers on real Nasdaq days inside the window, the engine's run with them, and the page's button."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pytest  # noqa: E402

from backtest import combo_engine as ce  # noqa: E402
from backtest import full_panel  # noqa: E402


def _sig(closes, highs, lows, scenario, level=100.0):
    return ce.level_signals(np.array(closes, float), np.array(highs, float), np.array(lows, float), level, scenario).tolist()


def test_break_and_hold_both_ways():
    assert _sig([99, 99.5, 101], [99.6, 99.8, 101.5], [98.5, 99, 99.4], "break") == [0, 0, 1]
    assert _sig([101, 100.5, 99], [101.5, 101, 100.6], [100.6, 100.2, 98.8], "break") == [0, 0, -1]
    assert _sig([101, 102, 103], [101.5, 102.5, 103.5], [100.5, 101.5, 102.5], "break") == [0, 0, 0]      # no crossing


def test_false_break_both_ways():
    assert _sig([101, 101, 100.5], [101.5, 101.5, 101], [100.5, 100.5, 99.5], "false") == [0, 0, 1]       # wick below, back
    assert _sig([101, 99.5, 100.5], [101.5, 100.5, 100.8], [100.5, 99.2, 99.4], "false") == [0, 0, 1]     # one close below
    assert _sig([99, 99, 99.5], [99.5, 99.5, 100.5], [98.5, 98.5, 99], "false") == [0, 0, -1]             # the owner's example
    assert _sig([101, 99.5, 99.0], [101.5, 100.5, 99.8], [100.5, 99.2, 98.5], "false") == [0, 0, 0]       # it stayed below


def test_the_map_at_the_opening():
    day = 86400.0
    monday = datetime(2023, 3, 13, 13, 30, tzinfo=timezone.utc).timestamp()           # 09:30 in New York, a Monday
    # D1 candles start the evening before their trading date (the broker's day); last week = 6-10 March
    d1 = [(datetime(2023, 3, d, 22, 0, tzinfo=timezone.utc).timestamp() - day, 0.0, 12000 + d, 11000 + d, 11500.0)
          for d in (1, 2, 3, 6, 7, 8, 9, 10)]
    lv = dict(ce.trader_levels("USTEC", monday, [], d1, 14950.0))
    assert lv["w_high"] == 12010 and lv["w_low"] == 11006
    got = ce.trader_levels("USTEC", monday, [], d1, 14950.0)
    assert ("round", 14900.0) in got and ("round_strong", 15000.0) in got


THIRDS = [(1.0, 1 / 3), (2.0, 1 / 3), (3.0, 1 / 3)]


def test_the_target_is_just_before_the_next_level():
    # a buy at 100, risk 20, cost 1.5, pad 1: the next level above is 170 -> the last target 169 = 3.45 R, the rest as they are
    tg, why = ce._next_level_targets(THIRDS, [90.0, 170.0, 250.0], 1, 100.0, 20.0, 1.5, 1.0, 3.0)
    assert why == "level" and tg[:2] == THIRDS[:2] and tg[2][0] == pytest.approx(69.0 / 20.0)
    # the mirror for a sell: the next level below 100 is 30 -> 31
    tg, why = ce._next_level_targets(THIRDS, [130.0, 30.0], -1, 100.0, 20.0, 1.5, 1.0, 3.0)
    assert why == "level" and tg[2][0] == pytest.approx(69.0 / 20.0)


def test_no_trade_when_the_next_level_leaves_under_three_after_the_cost():
    # (reward − cost) ÷ (risk + cost) = (65 − 1.5) ÷ 21.5 = 2.95 < 3 -> no trade, though 65 is 3.25 R before the cost
    assert ce._next_level_targets(THIRDS, [166.0], 1, 100.0, 20.0, 1.5, 1.0, 3.0) == (None, None)
    # a level just ahead blocks the trade even with a far one behind it
    assert ce._next_level_targets(THIRDS, [110.0, 400.0], 1, 100.0, 20.0, 1.5, 1.0, 3.0) == (None, None)


def test_no_level_ahead_keeps_three():
    tg, why = ce._next_level_targets(THIRDS, [80.0, 60.0], 1, 100.0, 20.0, 1.5, 1.0, 3.0)
    assert why == "none_ahead" and tg == THIRDS


CALENDAR = Path.home() / "AppData" / "Roaming" / "MetaQuotes" / "Terminal" / "Common" / "Files" / "nq_calendar_history.db"
STORE = ce.STORE.parent / "facts_store_quick" / "USTEC" / "2023-01-01_2024-01-01"


@pytest.mark.skipif(not ce.HISTORY_DB.exists(), reason="no candle history on this machine")
def test_triggers_live_in_the_window_and_the_map_is_the_past():
    from shared import red_lines
    t0, t1 = ce._epoch("2023-02-06"), ce._epoch("2023-02-11")
    for scenario in ("break", "false"):
        for candle in ("M5", "M1"):
            t, s, k = ce.level_triggers("USTEC", t0, t1, {"scenario": scenario, "candle": candle})
            assert len(t) > 0, (scenario, candle)
            assert set(s.tolist()) <= {1, -1} and set(k.tolist()) <= set(ce.TRADER_LEVEL_AR)
            for when in t.tolist():
                inside, opened = red_lines.session_state(when - 1, "USTEC")
                assert inside and opened is not None and when > opened


@pytest.mark.skipif(not (STORE / "index.json").exists() or not CALENDAR.exists(), reason="no 2023 store or news history")
def test_the_engine_runs_the_spearhead(monkeypatch):
    monkeypatch.setattr(ce, "CALENDAR_DB", CALENDAR)
    spec = json.loads(json.dumps({**ce.LIVE_COMBO, "symbol": "USTEC", "from": "2023-02-01", "to": "2023-04-01",
                                  "store": str(STORE)}))
    spec["stop"]["band"] = [20.0, 45.0]
    spec["entry"] = {"levels": {"scenario": "break", "candle": "M5"}, "within_min": 15}
    res = ce.run(ce.merged(spec), log=lambda s: None)
    done = res["trades"]["التوليفة"]
    assert done and all(t.get("level") in ce.TRADER_LEVEL_AR for t in done)
    base = json.loads(json.dumps(spec))
    base.pop("entry")
    plain = ce.run(ce.merged(base), log=lambda s: None)["trades"]["التوليفة"]
    assert plain and all("level" not in t for t in plain)
    nxt = json.loads(json.dumps(spec))
    nxt["target_from"] = dict(ce.NEXT_LEVEL_TARGET, pad_pips=1.0)
    got = ce.run(ce.merged(nxt), log=lambda s: None)
    rows = got["trades"]["التوليفة"]
    assert all(t["target_from"] in ce.TARGET_FROM_AR and t["target_r"] >= 3.0 for t in rows)
    assert got["skipped"]["التوليفة"].get("target_below_three", 0) > 0


@pytest.mark.skipif(not (STORE / "index.json").exists() or not CALENDAR.exists(), reason="no 2023 store or news history")
def test_a_month_end_to_end(tmp_path, monkeypatch):
    monkeypatch.setattr(ce, "CALENDAR_DB", CALENDAR)
    monkeypatch.setattr(ce, "OUT_ROOT", tmp_path)
    folder = ce.levels_plan({"symbol": "USTEC", "years": [["2023-02-01", "2023-03-01"]]}, log=lambda s: None)
    test_md = (folder / "الاختبار.md").read_text(encoding="utf-8")
    assert ce.LEVELS_CRITERION in test_md                                   # the paper's step 10, word for word
    s = json.loads((folder / "summary.json").read_text(encoding="utf-8"))
    assert s["kind"] == "levels" and len(s["التجارب"]) == len(ce.LEVELS_VARIANTS) and len(s["الشروط"]) == len(ce.LEVELS_VARIANTS) - 1
    assert len(list((folder / "التجارب").glob("*/النتيجة.md"))) == len(ce.LEVELS_VARIANTS)
    text = (folder / "النتيجة.md").read_text(encoding="utf-8")
    for part in ("الحكم بمعيار النجاح", "كلّ سنة بشكل المالك", "كم صفقةً أخذت كلّ جلسة", "لكلّ نوع مستوى", "وقف في أوّل 5 دقائق",
                 "رُدّت لأنّ المستوى التالي أقرب",
                 "سقوط الحساب", "العشوائيّ"):
        assert part in text, part


STORE_2022 = ce.STORE.parent / "facts_store_quick" / "USTEC" / "2022-01-01_2023-01-01"


@pytest.mark.skipif(not (STORE_2022 / "index.json").exists() or not CALENDAR.exists(), reason="no 2022 store or news history")
def test_the_map_target_is_the_days_own_map(monkeypatch):
    """The owner's «قيس»: the next level from the trader's map alone -- the very map that fires the spearhead."""
    from shared import red_lines
    monkeypatch.setattr(ce, "CALENDAR_DB", CALENDAR)
    spec = json.loads(json.dumps({**ce.LIVE_COMBO, "symbol": "USTEC", "from": "2022-01-01", "to": "2023-01-01",
                                  "store": str(STORE_2022), "reference_random": False}))
    spec["stop"]["band"] = [20.0, 45.0]
    spec["entry"] = {"levels": {"scenario": "break", "candle": "M1"}, "within_min": 15}
    spec["target_from"] = dict(ce.NEXT_LEVEL_MAP_TARGET, pad_pips=1.0)
    got = ce.run(ce.merged(spec), log=lambda s: None)
    rows = got["trades"]["التوليفة"]
    assert got["skipped"]["التوليفة"].get("target_below_three", 0) > 0
    t0, t1 = ce._epoch(spec["from"]), ce._epoch(spec["to"])
    minutes = ce.load_minutes("USTEC", t0 - 86400, t1 + 3 * 86400)
    m15, d1 = ce._bars_db("USTEC", "M15", t0 - 40 * 86400, t1), ce._bars_db("USTEC", "D1", t0 - 60 * 86400, t1)
    rows_ = (m15, np.array([r[0] for r in m15]) + 900, d1, np.array([r[0] for r in d1]) + 86400)
    checked = 0
    for t in rows:
        assert t["target_from"] in ce.TARGET_FROM_AR and t["target_r"] >= 3.0
        if t["target_from"] != "level":
            continue
        at = datetime.strptime(t["opened"], "%Y-%m-%d %H:%M").replace(tzinfo=timezone(timedelta(hours=3))).timestamp()
        side = 1 if t["side"] == "شراء" else -1
        risk = abs(t["entry"] - t["stop"])
        target = t["entry"] + side * t["target_r"] * risk
        levels = ce._map_levels("USTEC", at, minutes, {}, rows_)
        ahead = sorted((lv - t["entry"]) * side for lv in levels if (lv - t["entry"]) * side > 0)
        # one pip before the next map level (the record keeps the target to 0.01 of the risk, so 0.005 x risk of rounding)
        assert ahead and abs((target - t["entry"]) * side - (ahead[0] - 1.0)) <= 0.005 * risk + 0.02
        checked += 1
    assert checked >= 1                    # 2026-10-23: one such trade in 2022 (the 3:1 rule leaves very few)


def test_the_page_button(tmp_path, monkeypatch):
    launched = []
    monkeypatch.setattr(full_panel, "RUNS_DIR", tmp_path)
    monkeypatch.setattr(full_panel, "REGISTRY", tmp_path / "panel_runs.json")
    monkeypatch.setattr(full_panel, "_launch", lambda name, args, row: launched.append((name, args, row)) or {"ok": True, "name": name})
    got = full_panel.handle_full("POST", "/gov/backtest/full/levels/start", {})
    assert got["ok"], got
    name, args, row = launched[0]
    assert args[:2] == ["backtest.combo_engine", "--levels-plan"] and row["mode"] == "levels"
    spec = json.loads((tmp_path / name / "spec.json").read_text(encoding="utf-8"))
    assert spec["symbol"] == "USTEC" and spec["years"] == [["2022-01-01", "2023-01-01"], ["2023-01-01", "2024-01-01"]]
    assert "variants" not in spec
    full_panel._save_registry([{"name": name, "pid": 4242, "status": "running", "mode": "levels"}])
    monkeypatch.setattr(full_panel, "_alive", lambda pid: True)
    assert not full_panel.handle_full("POST", "/gov/backtest/full/levels/start", {})["ok"] and len(launched) == 1
    full_panel._save_registry([])
    assert full_panel.handle_full("POST", "/gov/backtest/full/levels/start", {"target": "map"})["ok"]
    spec = json.loads((tmp_path / launched[-1][0] / "spec.json").read_text(encoding="utf-8"))
    assert spec["variants"] == "map"
    full_panel._save_registry([])
    assert full_panel.handle_full("POST", "/gov/backtest/full/levels/start", {"target": "notime"})["ok"]
    assert json.loads((tmp_path / launched[-1][0] / "spec.json").read_text(encoding="utf-8"))["variants"] == "notime"


@pytest.mark.skipif(not (STORE / "index.json").exists() or not CALENDAR.exists(), reason="no 2023 store or news history")
def test_a_month_without_the_time_law(tmp_path, monkeypatch):
    """The owner (24/10): «قيس بلا قاعدة وقت يكفي» -- for knowledge; the trades still close at the window's end."""
    import csv as _csv

    from shared import red_lines
    monkeypatch.setattr(ce, "CALENDAR_DB", CALENDAR)
    monkeypatch.setattr(ce, "OUT_ROOT", tmp_path)
    folder = ce.levels_plan({"symbol": "USTEC", "years": [["2023-02-01", "2023-04-01"]], "variants": "notime"}, log=lambda s: None)
    s = json.loads((folder / "summary.json").read_text(encoding="utf-8"))
    assert s["للمعرفة"] and s["الحكم"].startswith("قياسٌ للمعرفة") and s["الشروط"] == {}
    with_law, without = (s["التجارب"]["2023|%s" % v[0]]["التوليفة"] for v in ce.NOTIME_VARIANTS)
    assert without["الإحصاء"]["صفقات"] > with_law["الإحصاء"]["صفقات"]           # the law was what held them back
    text = (folder / "النتيجة.md").read_text(encoding="utf-8")
    for part in ("قياسٌ للمعرفة", "ما أُغلق عند نهاية نافذة نيويورك", "بساعة الدخول", "كلّ سنة بشكل المالك", "سقوط الحساب"):
        assert part in text, part
    assert "الحكم بمعيار النجاح" not in text and "بلا معيار نجاح" in (folder / "الاختبار.md").read_text(encoding="utf-8")
    # nothing stays open past the window: every trade ends by the asset's red line (the first minute past it at the latest)
    rows = list(_csv.DictReader((folder / "الصفقات.csv").open(encoding="utf-8-sig")))
    assert rows
    for t in rows:
        opened = datetime.strptime(t["opened"], "%Y-%m-%d %H:%M").replace(tzinfo=timezone(timedelta(hours=3))).timestamp()
        assert float(t["minutes"]) * 60 <= red_lines.seconds_to_red_line(opened, "USTEC", None) + 61, (t["opened"], t["minutes"])


@pytest.mark.skipif(not (STORE / "index.json").exists() or not CALENDAR.exists(), reason="no 2023 store or news history")
def test_a_month_with_the_map_target(tmp_path, monkeypatch):
    monkeypatch.setattr(ce, "CALENDAR_DB", CALENDAR)
    monkeypatch.setattr(ce, "OUT_ROOT", tmp_path)
    folder = ce.levels_plan({"symbol": "USTEC", "years": [["2023-02-01", "2023-03-01"]], "variants": "map"}, log=lambda s: None)
    s = json.loads((folder / "summary.json").read_text(encoding="utf-8"))
    assert [x[0] for x in s["الترتيب"]] == [v[0] for v in ce.LEVELS_MAP_VARIANTS] and len(s["الشروط"]) == 4
    assert "خريطة المتداول وحدها" in (folder / "الاختبار.md").read_text(encoding="utf-8")
    assert "رُدّت لأنّ المستوى التالي أقرب" in (folder / "النتيجة.md").read_text(encoding="utf-8")
