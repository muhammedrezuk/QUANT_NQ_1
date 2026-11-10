# -*- coding: utf-8 -*-
"""The owner's direction rule (2026-10-22, «NQ»): every frame is up or down -- never sideways, never neutral.

His words: «صاعد يعني السعر عم يزيد مع شموع عم تنبنى، واقف على دعم وعم يشكّل اتّجاه صاعد وماشي فيه؛ وهابط على مدّة معيّنة عم
يهبط السعر بالتتالي» · «يعني شموع صاعدة وشموع هابطة» · «ما في شي اسمه أحيانًا أو عرضيّ أو حياد».

A rising candle makes a higher high AND a higher low than the candle before it; a falling candle a lower high AND a lower
low. A frame turns up after `run` rising candles in a row and stays up until `run` falling candles in a row turn it down
(and the mirror). Inside and outside candles break a sequence and change nothing, so one news candle never flips a frame.
One calculation for the backtest and the live atom, so what is measured is what is shown.
"""
from __future__ import annotations

import numpy as np

UP, DOWN, UNKNOWN = 1, -1, 0
WORD = {UP: "صاعد", DOWN: "هابط", UNKNOWN: "—"}
DEFAULT_RUN = 3


def candle_steps(highs: np.ndarray, lows: np.ndarray) -> np.ndarray:
    """+1 for a rising candle, -1 for a falling one, 0 otherwise (the first candle has no step)."""
    h = np.asarray(highs, dtype=float)
    lo = np.asarray(lows, dtype=float)
    steps = np.zeros(len(h), dtype=np.int8)
    if len(h) > 1:
        rising = (h[1:] > h[:-1]) & (lo[1:] > lo[:-1])
        falling = (h[1:] < h[:-1]) & (lo[1:] < lo[:-1])
        steps[1:] = np.where(rising, UP, np.where(falling, DOWN, 0))
    return steps


def directions(highs: np.ndarray, lows: np.ndarray, run: int = DEFAULT_RUN) -> np.ndarray:
    """The frame's state after each closed candle: UP or DOWN, UNKNOWN only before the first sequence of `run`."""
    run = max(1, int(run))
    steps = candle_steps(highs, lows)
    state = np.zeros(len(steps), dtype=np.int8)
    current, ups, downs = UNKNOWN, 0, 0
    for i, s in enumerate(steps):
        ups = ups + 1 if s == UP else 0
        downs = downs + 1 if s == DOWN else 0
        if ups >= run:
            current = UP
        elif downs >= run:
            current = DOWN
        state[i] = current
    return state


def since(state: np.ndarray) -> np.ndarray:
    """How many candles each state has lasted, counting the candle itself."""
    out = np.zeros(len(state), dtype=np.int64)
    for i in range(len(state)):
        out[i] = out[i - 1] + 1 if i and state[i] == state[i - 1] else 1
    return out
