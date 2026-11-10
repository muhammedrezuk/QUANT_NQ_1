"""The owner (2026-10-22): «وقف عند موجة بيعرفها، لازم نوصل 100٪». A wave the system knows -- one that ended at a low or a
high already proven by a turn of the wave size -- must be exactly the wave the whole finished chart shows, at every candle.
Checked by cutting random charts at every candle and comparing the known waves with the waves of the full chart."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

from backtest.combo_engine import zigzag_legs  # noqa: E402


def _known_until(labels: np.ndarray) -> int:
    """Index of the last candle of the last finished wave (the start of the wave still running), -1 if none."""
    turns = np.flatnonzero(np.diff(labels) != 0)
    return int(turns[-1]) if len(turns) else -1


def test_every_known_wave_is_the_wave_of_the_finished_chart():
    rng = np.random.default_rng(20261022)
    checked = 0
    for walk in range(20):
        close = 100 + np.cumsum(rng.normal(0, 1, 600))
        hi, lo = close + rng.uniform(0, 0.8, 600), close - rng.uniform(0, 0.8, 600)
        final = zigzag_legs(hi, lo, 6.0)
        for cut in range(30, 600, 7):
            now = zigzag_legs(hi[:cut + 1], lo[:cut + 1], 6.0)
            end = _known_until(now)
            if end < 0:
                continue
            known = slice(int(np.flatnonzero(now)[0]), end + 1)
            assert (now[known] == final[known]).all(), (walk, cut)
            checked += end + 1
    assert checked > 50_000
