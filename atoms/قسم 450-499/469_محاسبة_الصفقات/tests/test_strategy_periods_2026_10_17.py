"""2026-10-17 (owner seal, step 20): every strategy's months, weeks, this week and today, by the owner's (Turkey) date of
the close -- a close at 22:30 UTC on the last day of a month belongs to the next month in Turkey."""
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from accountability_groups import strategy_periods  # noqa: E402


def at(iso: str) -> float:
    return datetime.fromisoformat(iso).replace(tzinfo=timezone.utc).timestamp()


def test_months_weeks_today_on_the_owners_dates():
    trades = [{"strategy": "408", "closed_at": at("2026-09-30T22:30"), "profit_usd": 10.0, "result_r": 1.0, "card_no": 1},
              {"strategy": "408", "closed_at": at("2026-10-16T10:00"), "profit_usd": -5.0, "result_r": -0.5, "card_no": 2},
              {"strategy": "408", "closed_at": at("2026-10-17T06:00"), "profit_usd": 7.0, "result_r": 0.7, "card_no": 3},
              {"strategy": "410", "closed_at": None, "profit_usd": 1.0, "result_r": 0.1, "card_no": 4}]
    out = strategy_periods(trades, 3, at("2026-10-17T07:00"))
    assert out["date_zone"] == "Europe/Istanbul" and out["today"] == "2026-10-17"
    s = out["408"]
    assert list(s["by_month"]) == ["2026-10"] and s["by_month"]["2026-10"]["n"] == 3
    assert s["today"]["n"] == 1 and s["today"]["total_usd"] == 7.0
    assert s["this_week"]["n"] == 2 and s["this_week"]["total_usd"] == 2.0
    assert "410" not in out                                       # a card without a close time is not a closed trade
