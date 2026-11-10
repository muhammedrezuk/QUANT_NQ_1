"""The strategy search (the owner's paper of 2026-10-23): one hypothetical trade's arithmetic by the thirds and the red
lines, the backtest page's button (two exam years, taught from 2018, one run at a time), and a short run end to end that
writes the owner's files and teaches nothing the exam can see."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402

from backtest import combo_engine as ce  # noqa: E402
from backtest import full_panel  # noqa: E402

THIRDS = [(1.0, 1 / 3), (2.0, 1 / 3), (3.0, 1 / 3)]
COST = 1.5 / 20.0                                       # 1.5 on a risk of 20, in risk units


def _walk(highs, lows, closes=None, left=10_000.0):
    t = [60.0 * (k + 1) for k in range(len(highs))]
    closes = closes or [(h + l) / 2 for h, l in zip(highs, lows)]
    return ce.search_trade(1, 0.0, 100.0, 80.0, left, "session_end", (t, highs, lows, closes), THIRDS, 1, 2, 1.0, 1.5)


def test_all_three_targets():
    tr = _walk([105, 125, 145, 165], [99, 104, 124, 144])
    assert tr.exit == "target" and tr.stage == 3
    assert tr.result_r() == pytest.approx(2.0 - COST)


def test_the_full_stop():
    tr = _walk([101, 90], [79, 85])
    assert tr.exit == "stop" and tr.stage == 0
    assert tr.result_r() == pytest.approx(-1.0 - COST)


def test_first_target_then_back_to_the_entry():
    tr = _walk([121, 110], [101, 99.9])
    assert tr.exit == "stop" and tr.stage == 1
    assert tr.result_r() == pytest.approx(1 / 3 - COST)


def test_a_minute_that_reaches_both_is_a_stop():
    tr = _walk([121], [79])
    assert tr.exit == "stop" and tr.result_r() == pytest.approx(-1.0 - COST)


def test_closed_whole_at_the_red_line():
    tr = _walk([105, 108, 112], [99, 101, 104], closes=[104, 106, 110], left=150.0)
    assert tr.exit == "session_end" and tr.exit_at == 150.0          # at the red line itself (since 2026-10-25), not the next minute
    assert tr.result_r() == pytest.approx((106 - 100) / 20.0 - COST)


def test_the_page_button(tmp_path, monkeypatch):
    launched = []
    monkeypatch.setattr(full_panel, "RUNS_DIR", tmp_path)
    monkeypatch.setattr(full_panel, "REGISTRY", tmp_path / "panel_runs.json")
    monkeypatch.setattr(full_panel, "_launch", lambda name, args, row: launched.append((name, args, row)) or {"ok": True, "name": name})
    got = full_panel.handle_full("POST", "/gov/backtest/full/strategy/start", {})
    assert got["ok"], got
    name, args, row = launched[0]
    assert args[:2] == ["backtest.combo_engine", "--strategy-search"] and row["mode"] == "strategy"
    spec = json.loads((tmp_path / name / "spec.json").read_text(encoding="utf-8"))
    assert spec["symbol"] == "USTEC" and spec["train_from"] == "2018-01-01"
    assert spec["exams"] == [["2022-01-01", "2023-01-01"], ["2023-01-01", "2024-01-01"]]     # one falling, one rising
    full_panel._save_registry([{"name": name, "pid": 4242, "status": "running", "mode": "strategy"}])
    monkeypatch.setattr(full_panel, "_alive", lambda pid: True)
    again = full_panel.handle_full("POST", "/gov/backtest/full/strategy/start", {})
    assert not again["ok"] and len(launched) == 1


CALENDAR = Path.home() / "AppData" / "Roaming" / "MetaQuotes" / "Terminal" / "Common" / "Files" / "nq_calendar_history.db"


@pytest.mark.skipif(not ce.HISTORY_DB.exists() or not CALENDAR.exists(), reason="no candle or news history on this machine")
def test_a_short_search_end_to_end(tmp_path, monkeypatch):
    monkeypatch.setattr(ce, "CALENDAR_DB", CALENDAR)
    monkeypatch.setattr(ce, "OUT_ROOT", tmp_path)
    folder = ce.strategy_search({"symbol": "USTEC", "train_from": "2021-09-01", "exams": [["2022-01-01", "2022-02-01"]]},
                                log=lambda s: None)
    for name in ("summary.json", "النتيجة.md", "الاختبار.md"):
        assert (folder / name).exists(), name
    s = json.loads((folder / "summary.json").read_text(encoding="utf-8"))
    year = s["السنوات"]["2022"]
    assert s["kind"] == "strategy" and s["الحكم"] in ("نعم", "لا")
    assert set(year["الشروط"]) == {"صافٍ_موجب", "فوق_العشوائيّ", "صفر_سقوط", "صفقات_تكفي"}
    assert year["صفوف_التعلّم"] > 0 and year["صفوف_الامتحان"] > 0
    assert year["آخر_ما_رآه_التعلّم"] < year["أوّل_الامتحان"]       # nothing taught reaches into the exam
    text = (folder / "النتيجة.md").read_text(encoding="utf-8")
    for part in ("الحكم بمعيار النجاح", "كلّ سنة بشكل المالك", "هدف أوّل", "كم نزل قبل الربح", "سقوط الحساب", "عشوائيّ"):
        assert part in text, part
