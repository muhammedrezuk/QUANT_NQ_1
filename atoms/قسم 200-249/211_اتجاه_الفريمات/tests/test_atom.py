"""211 frame direction: three rising candles in a row turn a frame up and it stays up until three falling candles in a
row; inside candles change nothing; history candles fill without publishing; a live close publishes every frame of that
symbol; the week is built from the days; malformed candles are counted, not published."""
from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from shared import direction_rule as rule  # noqa: E402

_spec = importlib.util.spec_from_file_location("atom_211", Path(__file__).resolve().parents[1] / "atom.py")
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)

START = 1_800_000_000.0
STEP = 900.0


class Ctx:
    def __init__(self, config: dict) -> None:
        self.config = config
        self.handlers: dict = {}
        self.published: list = []

    def subscribe(self, name, handler) -> None:
        self.handlers[name] = handler

    async def publish(self, name, payload) -> None:
        self.published.append((name, payload))


def candle(i: int, high: float, low: float, frame: str = "15m", history: bool = False, symbol: str = "USTEC") -> dict:
    step = mod.FRAME_S[frame]
    return {"symbol": symbol, "timeframe": frame, "period_start": START + i * step, "open": (high + low) / 2,
            "high": high, "low": low, "close": (high + low) / 2, "volume": 1.0, "history": history}


def run_atom(candles: list[dict], config: dict | None = None) -> Ctx:
    ctx = Ctx(config or {"symbols": ["USTEC"], "frames": ["15m", "1d", "1w"], "day_frame": "1d", "max_bars": 450, "run": 3})
    atom = mod.Atom()

    async def go() -> None:
        await atom.initialize(ctx)
        await atom.start()
        for c in candles:
            await ctx.handlers[mod.EVENT_CANDLE](c)
        health = await atom.health_check()
        ctx.health = health

    asyncio.run(go())
    return ctx


def test_rule_turns_up_after_three_rising_and_down_after_three_falling():
    highs = [10, 11, 12, 13, 12.5, 12, 11, 10]
    lows = [9, 10, 11, 12, 11.5, 11, 10, 9]
    assert rule.directions(highs, lows, 3).tolist() == [0, 0, 0, 1, 1, 1, -1, -1]


def test_an_inside_candle_breaks_a_sequence_and_one_news_candle_flips_nothing():
    highs = [10, 11, 12, 11.5, 13, 14, 15, 9]          # an inside candle at 3; a single wide drop at the end
    lows = [9, 10, 11, 11.2, 12, 13, 14, 5]
    state = rule.directions(highs, lows, 3).tolist()
    assert state[3] == 0 and state[6] == 1 and state[7] == 1


def test_history_fills_silently_and_a_live_close_publishes_every_frame():
    hist = [candle(i, 100 + i, 99 + i, history=True) for i in range(10)]
    ctx = run_atom(hist + [candle(10, 111, 110)])
    assert len(ctx.published) == 1
    name, body = ctx.published[0]
    assert name == mod.EVENT_OUT and body["symbol"] == "USTEC" and body["run"] == 3
    assert set(body["frames"]) == {"15m", "1d", "1w"}
    assert body["frames"]["15m"]["trend"] == "up" and body["frames"]["15m"]["since_bars"] == 8
    assert body["frames"]["1d"]["trend"] is None and body["frames"]["1d"]["bars"] == 0


def test_falling_candles_turn_the_frame_down():
    rising = [candle(i, 100 + i, 99 + i, history=True) for i in range(6)]
    falling = [candle(6 + i, 104 - i, 103 - i, history=i < 3) for i in range(4)]
    ctx = run_atom(rising + falling)
    body = ctx.published[-1][1]
    assert body["frames"]["15m"]["trend"] == "down" and body["frames"]["15m"]["since_bars"] == 2


def test_the_week_is_built_from_the_days():
    days = [candle(i, 100 + i, 99 + i, frame="1d", history=True) for i in range(40)]
    ctx = run_atom(days + [candle(40, 141, 140, frame="1d")])
    week = ctx.published[-1][1]["frames"]["1w"]
    assert week["bars"] >= 4 and week["trend"] == "up"


def test_malformed_candles_are_counted_and_other_symbols_ignored():
    bad = {"symbol": "USTEC", "timeframe": "15m", "period_start": START, "open": None, "high": 1, "low": 1, "close": 1}
    other = candle(0, 10, 9, symbol="XAUUSD")
    ctx = run_atom([bad, other])
    assert ctx.published == [] and "dropped=1" in ctx.health.message
