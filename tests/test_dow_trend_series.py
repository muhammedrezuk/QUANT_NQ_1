"""shared.dow_theory.trend_series (the backtest page's one-pass Dow) must say what frame_facts (the live atom 209) says at
every close: random walks and their prefixes, compared step by step."""
from __future__ import annotations

import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from shared import dow_theory as dt  # noqa: E402


def _bars(closes: list[float]) -> list[tuple]:
    out, prev = [], closes[0]
    for i, c in enumerate(closes):
        out.append((1_800_000_000.0 + i * 900, prev, max(prev, c), min(prev, c), c, 1.0))
        prev = c
    return out


def test_one_pass_dow_matches_the_live_calculation_at_every_close():
    rng = random.Random(20261022)
    for walk in range(12):
        closes, price = [], 100.0
        drift = rng.choice([-0.3, 0.0, 0.3])
        for _ in range(160):
            price += drift + rng.gauss(0, 1.5)
            closes.append(round(price, 2))
        trends, _ = dt.trend_series(closes)
        bars = _bars(closes)
        for end in range(2 * dt.PIVOT_SPAN + 1, len(closes) + 1, 7):
            assert trends[end - 1] == dt.frame_facts(bars[:end])["dow_trend"], (walk, end)


def test_a_break_is_kept_as_its_kind():
    closes, price = [100.0], 100.0                     # the Dow atom's own zigzag: five steps of 2 up, three of 1.5 back
    for _ in range(6):
        for step in [2.0] * 5 + [-1.5] * 3:
            price += step
            closes.append(price)
    closes += [closes[-1] - 6.0, closes[-1] - 12.0]   # a close below the last swing low
    trends, breaks = dt.trend_series(closes)
    assert dt.RISING in trends and trends[-1] == dt.NONE and breaks[-1] == dt.BREAK_DOWN
    assert trends[-1] == dt.frame_facts(_bars(closes))["dow_trend"]
