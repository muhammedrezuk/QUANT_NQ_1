"""The strategy search (the owner's paper of 2026-10-23) computes the structure stop from candles, because the years it
learns on (2018-2021) have no facts store. It must be the stop the engine reads from atom 202 in the store: on a month of
2023 every decision close in the Nasdaq window, both sides, gets the same stop (or none) both ways."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pytest  # noqa: E402

from backtest import combo_engine as ce  # noqa: E402

STORE = ce.STORE / "USTEC" / "2023-01-01_2024-01-01"


@pytest.mark.skipif(not (STORE / "index.json").exists(), reason="no 2023 facts store on this machine")
def test_candle_stop_is_the_store_stop():
    from shared import red_lines
    from shared.pips import from_pips
    facts = ce.Facts(STORE)
    t0, t1 = ce._epoch("2023-02-01"), ce._epoch("2023-03-01")
    bars = np.array(ce._bars_db("USTEC", "M5", t0, t1), dtype=float)
    moments, closes = bars[:, 0] + 300, bars[:, 4]
    inside = np.array([red_lines.session_state(float(m), "USTEC")[0] for m in moments])
    moments, closes = moments[inside], closes[inside]
    swings = []
    for period, ps in ce.SEARCH_SWING_FRAMES:
        sb = np.array(ce._bars_db("USTEC", period, t0 - ce.SEARCH_SWING_WARM_S, t1), dtype=float)
        swings.append(ce.confirmed_swings(sb[:, 2], sb[:, 3], sb[:, 0] + ps))
    lo, hi, pad = from_pips(20.0, "USTEC"), from_pips(45.0, "USTEC"), from_pips(1.0, "USTEC")
    cfg = {"method": "structure", "band": [20.0, 45.0], "pad": 1.0}
    total = same = 0
    for side in (1, -1):
        ours = ce.structure_stops(swings, moments, closes, side, lo, hi, pad)
        for m, price, mine in zip(moments, closes, ours):
            theirs = ce._stop(facts, cfg, "USTEC", side, float(m), float(price), 1.0, from_pips)
            total += 1
            if theirs is None:
                same += int(np.isnan(mine))
            else:
                same += int(not np.isnan(mine) and abs(mine - theirs) < 1e-6)
    assert total > 1000
    assert same == total, "%d of %d the same" % (same, total)        # 2026-10-23: 3,050 of 3,050
