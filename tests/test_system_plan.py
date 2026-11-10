"""The system as it is (the owner, 25/10: «قيس شغلات سستم»): the account limits read from 509's saved snapshot, a short run of
two pairs end to end -- each pair with its own stop band, pad and cost, the pairs together on one account with the saved
limits, the Nasdaq beside the night of 23-24/10 -- and the page's button."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402

from backtest import combo_engine as ce  # noqa: E402
from backtest import full_panel  # noqa: E402

CALENDAR = Path.home() / "AppData" / "Roaming" / "MetaQuotes" / "Terminal" / "Common" / "Files" / "nq_calendar_history.db"
QUICK = ce.STORE.parent / "facts_store_quick"


def test_the_limits_come_from_509s_saved_snapshot(tmp_path, monkeypatch):
    snap = tmp_path / "509.json"
    snap.write_text(json.dumps({"settings": {"initial_balance": 9000.0, "pair_risk_pct": 0.5, "pair_daily_pct": 1.5,
                                             "daily_pct": 4.0, "total_pct": 8.0, "pairs": {}}}), encoding="utf-8")
    monkeypatch.setattr(ce, "LIMITS_SNAPSHOT", snap)
    limits, src = ce.saved_account_limits()
    assert limits["initial_balance"] == 9000.0 and src == "لقطة الذرّة 509 المحفوظة"
    monkeypatch.setattr(ce, "LIMITS_SNAPSHOT", tmp_path / "none.json")
    limits, src = ce.saved_account_limits()
    assert limits["initial_balance"] == 10000.0 and src.startswith("القيم الأولى")


@pytest.mark.skipif(not (QUICK / "XAUUSD" / "2023-01-01_2024-01-01" / "index.json").exists() or not CALENDAR.exists(),
                    reason="no 2023 quick stores or news history on this machine")
def test_two_pairs_a_month_end_to_end(tmp_path, monkeypatch):
    monkeypatch.setattr(ce, "CALENDAR_DB", CALENDAR)
    monkeypatch.setattr(ce, "OUT_ROOT", tmp_path)
    folder = ce.system_plan({"symbols": ["USTEC", "XAUUSD"], "years": [["2023-02-01", "2023-03-01"]]}, log=lambda s: None)
    s = json.loads((folder / "summary.json").read_text(encoding="utf-8"))
    assert s["kind"] == "system" and s["للمعرفة"] and set(s["الحساب_معًا"]["2023"]) == set(ce.SYSTEM_GROUPS)
    gold = s["التجارب"]["XAUUSD|2023"]
    assert gold["الكلفة"] == ce.SYSTEM_COST_PIPS["XAUUSD"] and gold["الوقف"] == [21.0, 62.0]
    together = s["الحساب_معًا"]["2023"]["التوليفة"]
    each = sum(s["التجارب"]["%s|2023" % k]["التوليفة"]["الإحصاء"]["صفقات"] for k in ("USTEC", "XAUUSD"))
    assert together["taken"] + together["skipped"] == each                     # one account holds both pairs' trades
    text = (folder / "النتيجة.md").read_text(encoding="utf-8")
    for part in ("الأزواج السبعة معًا", "كلّ زوجٍ وكلّ سنة بشكل المالك", "الناسداك بجانب قياسَي", "ما أغلقته نهاية النافذة",
                 "أشهر 2023 — الذهب", "قياسٌ للمعرفة"):
        assert part in text, part
    assert "حدود الحساب" in (folder / "الاختبار.md").read_text(encoding="utf-8")


def test_the_page_button(tmp_path, monkeypatch):
    launched = []
    monkeypatch.setattr(full_panel, "RUNS_DIR", tmp_path)
    monkeypatch.setattr(full_panel, "REGISTRY", tmp_path / "panel_runs.json")
    monkeypatch.setattr(full_panel, "_launch", lambda name, args, row: launched.append((name, args, row)) or {"ok": True, "name": name})
    assert full_panel.handle_full("POST", "/gov/backtest/full/system/start", {})["ok"]
    name, args, row = launched[0]
    assert args[:2] == ["backtest.combo_engine", "--system-plan"] and row["mode"] == "system"
    spec = json.loads((tmp_path / name / "spec.json").read_text(encoding="utf-8"))
    assert spec["symbols"] == list(ce.SYSTEM_SYMBOLS) and spec["years"] == [["2022-01-01", "2023-01-01"], ["2023-01-01", "2024-01-01"]]
    full_panel._save_registry([{"name": name, "pid": 4242, "status": "running", "mode": "system"}])
    monkeypatch.setattr(full_panel, "_alive", lambda pid: True)
    assert not full_panel.handle_full("POST", "/gov/backtest/full/system/start", {})["ok"] and len(launched) == 1
