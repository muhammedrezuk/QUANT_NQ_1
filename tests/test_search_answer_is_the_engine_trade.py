"""The strategy search's answer at a moment (the owner's paper of 2026-10-23: «لو دخلنا الآن بوقف البنية وثلاثة أهداف
بالأثلاث، فكم كان الصافي بوحدة المخاطرة بعد الكلفة؟») must be the trade the measuring tool itself makes there. The engine
runs a month of 2023 with a trade at every moment (independent, seeded random sides, the store's stop, unscaled 20-45);
every one of its trades is found among the search's answers with the same result (both leave out the no-trade days,
law 22)."""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402

from backtest import combo_engine as ce  # noqa: E402

STORE = ce.STORE / "USTEC" / "2023-01-01_2024-01-01"
#: the conftest moves APPDATA away from the live machine; the news history is only read here (read-only connection)
CALENDAR = Path.home() / "AppData" / "Roaming" / "MetaQuotes" / "Terminal" / "Common" / "Files" / "nq_calendar_history.db"


@pytest.mark.skipif(not (STORE / "index.json").exists() or not CALENDAR.exists(),
                    reason="no 2023 facts store or news history on this machine")
def test_every_engine_trade_is_the_search_answer(monkeypatch):
    from collections import defaultdict
    monkeypatch.setattr(ce, "CALENDAR_DB", CALENDAR)

    from shared import market_clock, red_lines
    from shared.pips import to_pips
    spec = ce.merged({"symbol": "USTEC", "from": "2023-02-01", "to": "2023-03-01", "store": str(STORE),
                      "decision_frame": "5m", "independent": True, "scale_with_price": False, "reference_random": False,
                      "stop": {"method": "structure", "band": [20.0, 45.0], "pad": 1.0}})
    done = ce.run(spec, log=lambda s: None)["trades"]["التوليفة"]
    assert len(done) > 40                        # 2026-10-23: 55 (the time law and the 20-45 band leave few)
    t0, t1 = ce._epoch(spec["from"]), ce._epoch(spec["to"])
    rules = ce._search_cfg({"symbol": "USTEC"})
    news = ce.news_times({"on": True, "colors": ["red"], "currencies": sorted({red_lines.USD, *red_lines.currencies_of("USTEC")})},
                         t0, t1)
    got = ce._search_answers("USTEC", t0, t1, rules, news, defaultdict(int))
    answers = {}
    for s in (1, -1):
        for tr in got[s]:
            if tr is not None:
                rec = ce._record(tr, {"symbol": "USTEC", "risk_pct": rules["risk_pct"]}, to_pips)
                answers[(rec["opened"], rec["side"])] = rec
    matched = 0
    for t in done:
        at = datetime.strptime(t["opened"], "%Y-%m-%d %H:%M").replace(tzinfo=timezone(timedelta(hours=3))).timestamp()
        mine = answers.get((t["opened"], t["side"]))
        assert mine is not None, "the engine traded %s %s, the search has no answer" % (t["opened"], t["side"])
        assert not market_clock.no_trade_day(at)           # 2026-10-23: the engine bans the no-trade days too (law 22)
        for key in ("r", "reached", "exit", "stop", "minutes"):
            assert mine[key] == t[key], (t["opened"], t["side"], key, mine[key], t[key])
        matched += 1
    assert matched == len(done) > 40
