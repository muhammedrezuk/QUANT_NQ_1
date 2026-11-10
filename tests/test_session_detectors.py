"""The three detectors of the session's turn (the owner's seal of 24/10, «نقيس الثلاثة قيس nq»): the Dow read from candles
equals atom 209's store (the example session has no store), the turn logic from the opening direction, a month end to end
with the paper's criterion written first and the example session, and the page's button."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pytest  # noqa: E402

from backtest import combo_engine as ce  # noqa: E402
from backtest import full_panel  # noqa: E402

STORE = ce.STORE.parent / "facts_store_quick" / "USTEC" / "2023-01-01_2024-01-01"
CALENDAR = Path.home() / "AppData" / "Roaming" / "MetaQuotes" / "Terminal" / "Common" / "Files" / "nq_calendar_history.db"


def test_a_turn_is_the_side_against_the_standing_direction():
    times = [1, 2, 3, 4, 5, 6, 7]
    # standing up: "up" again says nothing, "none" says nothing, "down" turns it, then "up" turns it back
    assert ce.detector_flips(1, times, [1, 0, -1, -1, 0, 1, 1]) == [(3, -1), (6, 1)]
    assert ce.detector_flips(-1, times, [-1, -1, -1, 0, 0, 0, -1]) == []


@pytest.mark.skipif(not (STORE / "index.json").exists(), reason="no 2023 store on this machine")
def test_dow_from_candles_is_the_store_reading(monkeypatch):
    from shared import red_lines
    t0, t1 = ce._epoch("2023-01-01"), ce._epoch("2024-01-01")
    ms, _ = ce.decision_moments("USTEC", "15m", t0, t1)
    ms = np.array([m for m in ms if red_lines.session_state(float(m), "USTEC")[0]])
    from_store, src = ce.dow4h_sides("USTEC", t0, t1, ms)
    assert src == "مخزن الذرّة 209"
    monkeypatch.setattr(ce, "_plan_store", lambda *a: (_ for _ in ()).throw(SystemExit("none")))
    from_candles, src2 = ce.dow4h_sides("USTEC", t0, t1, ms)
    assert src2 != src
    same = float((from_store == from_candles).mean())
    assert same >= 0.99, same                                  # 2026-10-24: 99.6 of 100 of 6,584 moments


@pytest.mark.skipif(not (STORE / "index.json").exists() or not CALENDAR.exists(), reason="no 2023 store or news history")
def test_a_month_end_to_end(tmp_path, monkeypatch):
    monkeypatch.setattr(ce, "CALENDAR_DB", CALENDAR)
    monkeypatch.setattr(ce, "OUT_ROOT", tmp_path)
    folder = ce.session_detectors({"symbol": "USTEC", "years": [["2023-02-01", "2023-03-01"]], "example": "2026-10-23"},
                                  log=lambda s: None)
    assert ce.DETECTORS_CRITERION in (folder / "الاختبار.md").read_text(encoding="utf-8")
    s = json.loads((folder / "summary.json").read_text(encoding="utf-8"))
    year = s["السنوات"]["2023"]
    assert s["kind"] == "detectors" and year["جلسات"] >= 15 and set(year["الكواشف"]) == set(ce.DETECTORS_AR)
    for k, d in year["الكواشف"].items():
        assert d["إشارات"] == d["صعودًا"] + d["نزولًا"] and 0 <= d["رجعت_خلال_نصف_ساعة"] <= d["إشارات"]
        for h in ("1h", "close"):
            assert 0 <= d[h]["أصاب"] <= 100 and 0 <= d[h]["السوق"] <= 100
    assert year["الكواشف"]["ema"]["إشارات"] > 0 and year["الكواشف"]["levels"]["إشارات"] > 0
    ex = s["المثال"]
    assert ex and ex["الجلسة"] and ex["مصدر_داو"] == "شموع الأربع ساعات بحساب داو المشترك"
    text = (folder / "النتيجة.md").read_text(encoding="utf-8")
    for part in ("الحكم بمعيار النجاح", "جلسة 2026-10-23 مثالًا", "السبق", "رجعت خلال نصف ساعة", "أشهر 2023"):
        assert part in text, part
    assert (folder / "الإشارات.csv").exists()


def test_the_page_button(tmp_path, monkeypatch):
    launched = []
    monkeypatch.setattr(full_panel, "RUNS_DIR", tmp_path)
    monkeypatch.setattr(full_panel, "REGISTRY", tmp_path / "panel_runs.json")
    monkeypatch.setattr(full_panel, "_launch", lambda name, args, row: launched.append((name, args, row)) or {"ok": True, "name": name})
    assert full_panel.handle_full("POST", "/gov/backtest/full/detectors/start", {})["ok"]
    name, args, row = launched[0]
    assert args[:2] == ["backtest.combo_engine", "--session-detectors"] and row["mode"] == "detectors"
    spec = json.loads((tmp_path / name / "spec.json").read_text(encoding="utf-8"))
    assert spec["years"] == [["2022-01-01", "2023-01-01"], ["2023-01-01", "2024-01-01"]] and spec["example"] == "2026-10-23"
    full_panel._save_registry([{"name": name, "pid": 4242, "status": "running", "mode": "detectors"}])
    monkeypatch.setattr(full_panel, "_alive", lambda pid: True)
    assert not full_panel.handle_full("POST", "/gov/backtest/full/detectors/start", {})["ok"] and len(launched) == 1
