"""209 Dow theory: a rising zigzag on closes is a rising trend (higher highs and higher lows) that stands until a close
below the last swing low; the last leg's give-back inside a third to two thirds is Dow's secondary correction; volume up vs
down; the falling mirror; the atom fills from history, publishes on a live quarter-hour close with the three frames and
the confirmation of the other indices, and carries facts only."""
from __future__ import annotations

import asyncio
import importlib.util
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from shared import dow_theory as dt  # noqa: E402

_spec = importlib.util.spec_from_file_location("atom_209", Path(__file__).resolve().parents[1] / "atom.py")
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)

FORBIDDEN = ("direction", "signal", "strength", "confidence", "weight", "score", "probability", "threshold",
             "depth", "readiness", "buy", "sell", "bullish", "bearish", "strong", "weak")
UP_RUN, DOWN_RUN, STEP_UP, STEP_DOWN = 5, 3, 2.0, 1.5


def zigzag(cycles: int, sign: float = 1.0, tail_down: int = 0) -> list[float]:
    """Waves of five steps of 2 one way and three of 1.5 back: every high and every low beyond the one before."""
    closes, price = [100.0], 100.0
    for _ in range(cycles):
        for _ in range(UP_RUN):
            price += sign * STEP_UP
            closes.append(price)
        for _ in range(DOWN_RUN):
            price -= sign * STEP_DOWN
            closes.append(price)
    for _ in range(UP_RUN):
        price += sign * STEP_UP
        closes.append(price)
    for _ in range(tail_down):
        price -= sign * STEP_DOWN
        closes.append(price)
    return closes


def rows(closes: list[float], step: float = 900.0, start: float = 1_800_000_000.0) -> list[tuple]:
    out, prev = [], closes[0]
    for i, c in enumerate(closes):
        out.append((start + i * step, prev, max(prev, c), min(prev, c), c, 200.0 if c > prev else 100.0))
        prev = c
    return out


def test_rising_zigzag_is_a_rising_trend_with_its_legs_and_a_secondary_correction():
    facts = dt.frame_facts(rows(zigzag(6, tail_down=3)))
    assert facts["available"] and facts["dow_trend"] == dt.RISING and facts["structure"] == dt.HH_HL
    assert facts["highs"] == "higher" and facts["lows"] == "higher" and facts["last_break"] is None
    assert facts["legs"] == 6                       # the leg of the first higher high and the five after it
    assert facts["retracement"] == 0.45 and facts["in_correction_zone"] is True   # 4.5 of a 10-point leg
    assert facts["volume_up_vs_down"] == 2.0


def test_a_close_below_the_last_swing_low_ends_the_trend_and_is_kept():
    closes = zigzag(6, tail_down=3)
    closes += [closes[-1] - 6.0, closes[-1] - 12.0]
    facts = dt.frame_facts(rows(closes))
    assert facts["dow_trend"] == dt.NONE and facts["legs"] == 0 and facts["trend_since"] is None
    assert facts["last_break"]["kind"] == dt.BREAK_DOWN and facts["retracement"] is None


def test_falling_mirror_and_too_few_bars():
    facts = dt.frame_facts(rows(zigzag(6, sign=-1.0, tail_down=2)))
    assert facts["dow_trend"] == dt.FALLING and facts["structure"] == dt.LH_LL
    assert facts["retracement"] == 0.3 and facts["in_correction_zone"] is False    # 3 of a 10-point leg: under a third
    early = dt.frame_facts(rows(zigzag(6, sign=-1.0, tail_down=1)))
    assert early["retracement"] < 0          # the newest low is not confirmed yet: the price is beyond the last leg's end
    assert dt.frame_facts(rows([1.0, 2.0, 3.0]))["available"] is False


class Bus:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    async def publish(self, name: str, payload: dict | None = None) -> None:
        self.events.append((name, payload or {}))

    def subscribe(self, name, handler) -> None:
        pass




def build():
    from core.contracts.atom import AtomContext
    bus = Bus()
    atom = mod.Atom()
    cfg = {"symbols": ["USTEC", "US500", "US30"], "confirmation_group": ["USTEC", "US500", "US30"],
           "groups": {"secondary": ["1m", "5m", "15m"], "sub": ["30m", "1h", "4h"], "primary": ["1d", "1w", "1mo"]},
           "ask_frame": "15m", "day_frame": "1d", "max_bars": 450, "pivot_span": 2}
    asyncio.run(atom.initialize(AtomContext(atom_id=209, config=cfg, logger=None, publish=bus.publish,
                                            subscribe=bus.subscribe, subscribe_all=lambda h: None)))
    asyncio.run(atom.start())
    return atom, bus


T0 = datetime(2026, 7, 15, 13, 30, tzinfo=timezone.utc).timestamp()        # Wednesday 09:30 New York (summer)


def feed(atom, symbol, frame, step, closes, history=True, end=T0):
    start = end - len(closes) * step
    for row in rows(closes, step=step, start=start):
        s, o, h, low, c, v = row
        asyncio.run(atom._on_candle({"symbol": symbol, "timeframe": frame, "period_start": s, "open": o, "high": h,
                                     "low": low, "close": c, "volume": v, "history": history}))


def _walk(value, keys, texts):
    if isinstance(value, dict):
        for k, v in value.items():
            keys.append(str(k))
            _walk(v, keys, texts)
    elif isinstance(value, list):
        for v in value:
            _walk(v, keys, texts)
    elif isinstance(value, str):
        texts.append(value)


def test_week_and_month_are_built_from_days_without_the_current_one():
    days = rows(zigzag(8), step=86400.0, start=datetime(2026, 5, 4, 21, tzinfo=timezone.utc).timestamp())
    now = days[-1][0] + 3600
    weeks = dt.aggregate(days, dt.WEEK, now)
    assert len(weeks) >= 8 and dt.broker_date(weeks[-1][0]).isocalendar()[1] < dt.broker_date(now).isocalendar()[1]
    first = weeks[0]
    in_first = [d for d in days if dt.broker_date(d[0]).isocalendar()[1] == dt.broker_date(first[0]).isocalendar()[1]]
    assert first[1] == in_first[0][1] and first[4] == in_first[-1][4] and first[2] == max(d[2] for d in in_first)
    months = dt.month_candles("USTEC", days, now)
    assert len(months) > 100                                           # the stored months reach back to 2012
    assert dt.broker_date(months[-1][0]).month < dt.broker_date(now).month
    assert dt.month_candles("NO_SEED", days, now) == dt.aggregate(days, dt.MONTH, now)


def test_score_counts_right_wrong_flat():
    out = dt.score([["a", dt.RISING, 10.0], ["a", dt.FALLING, 10.0], ["a", dt.RISING, 12.0], ["b", dt.FALLING, 13.0]], 12.0)
    assert out == {"a": {"right": 1, "wrong": 1, "flat": 1}, "b": {"right": 1, "wrong": 0, "flat": 0}}


def test_atom_publishes_nine_frames_groups_and_readings_and_scores_the_session_close():
    atom, bus = build()
    feed(atom, "USTEC", "1m", 60.0, zigzag(6))
    feed(atom, "USTEC", "5m", 300.0, zigzag(6))
    feed(atom, "USTEC", "4h", 14400.0, zigzag(6))
    feed(atom, "USTEC", "1d", 86400.0, zigzag(6))
    history = zigzag(6)
    feed(atom, "USTEC", "15m", 900.0, history)
    assert bus.events == []                                            # history only fills
    live = [history[-1] + k + 1.0 for k in range(26)]                  # closes 09:45 ... 16:00 New York, rising
    feed(atom, "USTEC", "15m", 900.0, live, history=False, end=T0 + 26 * 900)
    body = [p for n, p in bus.events if n == "structure.dow.state"][-1]
    assert set(body["frames"]) == {"1m", "5m", "15m", "30m", "1h", "4h", "1d", "1w", "1mo"}
    assert body["groups"]["secondary"] == {"frames": ["1m", "5m", "15m"], "agree": dt.RISING}
    readings = body["readings"]
    assert readings["secondary_agree"]["trend"] == dt.RISING and readings["four_hours"]["trend"] == dt.RISING
    assert readings["secondary_agree"]["measured"]["right"] == 144 and readings["four_hours"]["measured"]["right"] == 1197
    scored = atom._live["USTEC"]
    assert scored["secondary_agree"] == {"right": 25, "wrong": 0, "flat": 0, "days": 1}
    assert scored["four_hours"] == {"right": 25, "wrong": 0, "flat": 0, "days": 1}
    assert readings["secondary_agree"]["live"]["days"] == 1             # the 16:00 publish already carries it
    keys, texts = [], []
    _walk(body, keys, texts)
    assert not [k for k in keys if any(word in k.lower() for word in FORBIDDEN)]
    assert not [t for t in texts if any(word in t.lower() for word in FORBIDDEN)]
    state = asyncio.run(atom.snapshot())
    again = mod.Atom()
    asyncio.run(again.restore(state))
    assert again._live == atom._live
    assert "secondary_agree=25/25" in asyncio.run(atom.health_check()).message


def test_malformed_candle_is_counted():
    atom, bus = build()
    asyncio.run(atom._on_candle({"symbol": "USTEC", "timeframe": "15m", "period_start": None, "close": 1.0}))
    assert "dropped=1" in asyncio.run(atom.health_check()).message and bus.events == []