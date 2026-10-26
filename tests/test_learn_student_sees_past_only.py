"""The owner (2026-10-22): «لا تغشّشه وتعطيه بيانات يشوفها». The student's readings at a candle must be the same whether
the chart goes on after it or stops there -- cut random charts at many candles and compare every column before the cut."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

from backtest.combo_engine import learn_frame_features  # noqa: E402


def test_no_reading_changes_when_the_future_is_cut_off():
    rng = np.random.default_rng(22)
    close = 1000 + np.cumsum(rng.normal(0, 2, 900))
    hi, lo = close + rng.uniform(0, 1.5, 900), close - rng.uniform(0, 1.5, 900)
    full = learn_frame_features(hi, lo, close, 12.0)
    for cut in (260, 333, 512, 777):
        part = learn_frame_features(hi[:cut + 1], lo[:cut + 1], close[:cut + 1], 12.0)
        for name, values in part.items():
            a, b = values, full[name][:cut + 1]
            same = (a == b) | (np.isnan(a) & np.isnan(b)) if a.dtype.kind == "f" else (a == b)
            assert same.all(), (name, cut, int(np.flatnonzero(~same)[0]))
