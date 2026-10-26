"""415 the comprehensive combination: Dow four hours rising and the EMA 5/10/50 order rising on the quarter hour, inside the
window with a swing low 32 pips under the close, send a buy setup and its approval with the stop behind the low and a 3R
net target; the mirror sells; disagreement, a stop under the Nasdaq 20-pip floor, an open position, the fifteen-minute
wait, a stale Dow reading, history candles and the owner's switch send nothing."""
from __future__ import annotations

import asyncio
import importlib.util
import json
import pathlib
import sys
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from core.contracts.atom import AtomContext  # noqa: E402
from shared import strategy_switch  # noqa: E402

_spec = importlib.util.spec_from_file_location("atom_415", pathlib.Path(__file__).resolve().parents[1] / "atom.py")
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)

START = datetime(2026, 10, 14, 14, 45, tzinfo=timezone.utc).timestamp()     # Wednesday, 11:00 New York at the close
M = START + 900.0


class _Log:
    def __getattr__(self, _):
        return lambda *a, **k: None


def _closes(last: float, sign: float, n: int = 160) -> list[float]:
    return [last - sign * 2.0 * (n - 1 - i) for i in range(n)]


async def _run(sign=1.0, dow="rising", dow_start=START, swing=30969.0, positions=(), close=31000.0, history_only=False,
               closed_before=None, symbol="USTEC"):
    mod.FACT_DELAY_S = 0.0
    out, handlers = [], {}

    async def publish(name, payload):
        out.append((name, payload))

    ctx = AtomContext(atom_id=415, config={"seed_history": False}, logger=_Log(), publish=publish,
                      subscribe=lambda n, h: handlers.setdefault(n, []).append(h))
    atom = mod.Atom()
    atom._clock = lambda: M + 2.0
    await atom.initialize(ctx)
    await atom.start()
    for h in handlers["platform.account.state"]:
        await h({"account_id": "A", "broker": "B"})
    if closed_before is not None:
        atom._clock = lambda: M + 2.0 - closed_before
        for h in handlers["platform.positions.state"]:
            await h({"positions": [{"symbol": symbol}]})
            await h({"positions": []})
        atom._clock = lambda: M + 2.0
    for h in handlers["platform.positions.state"]:
        await h({"positions": [{"symbol": s} for s in positions]})
    for h in handlers["market.tick.validated"]:
        await h({"symbol": symbol, "bid": close - 0.5, "ask": close + 0.5})
    for h in handlers["structure.external.state"]:
        await h({"symbol": symbol, "timeframe": "5m", "metadata": {"swing_low": swing, "swing_high": swing}})
    for h in handlers["structure.dow.state"]:
        await h({"symbol": symbol, "timeframe": "15m", "period_start": dow_start,
                 "readings": {"four_hours": {"frames": ["4h"], "trend": dow}}})
    closes = _closes(close, sign)
    for i, c in enumerate(closes):
        live = i == len(closes) - 1 and not history_only
        for h in handlers["market_data.candle_closed"]:
            await h({"symbol": symbol, "timeframe": "15m", "close": c, "period_start": START - 900.0 * (len(closes) - 1 - i),
                     "history": not live})
    await asyncio.sleep(0.05)
    return out, atom


def _sent(out, name="decision.approved.state"):
    return [p for n, p in out if n == name]


def test_dow_and_emas_rising_send_a_buy_behind_the_swing_low_with_a_net_3r_target():
    out, atom = asyncio.run(_run())
    approved, setups = _sent(out), _sent(out, "strategy.setup.proposed")
    assert len(approved) == 1 and len(setups) == 1, (out, atom._tally, atom._last)
    a = approved[0]
    assert a["decision_side"] == "buy" and a["strategy"] == "415" and a["timeframe"] == "15m"
    assert a["invalidation_price"] == 30968.0                       # one pip behind the low: 32.5 pips from the ask
    entry, risk, spread = 31000.5, 32.5, 1.0                        # built on the ask, the price the gate will send at
    assert abs(a["target_price"] - (entry + 3 * risk + 4 * spread * 1.25 + 4 * 0.1 * risk)) < 1e-9
    moved = entry + 0.1 * risk          # 2026-10-19: the price ran a tenth of the stop toward the target before the send
    reward, risk_at_send = a["target_price"] - moved, moved - a["invalidation_price"]
    assert (reward - spread) / (risk_at_send + spread) >= 3.0       # the gate (555) still passes it
    assert setups[0]["setup_owner"] == "415" and setups[0]["evidence"]["dow_4h"] == "rising"
    assert setups[0]["evidence"]["ema_5_10_50_15m"] == "rising"
    assert atom._tally == {"SENT": 1}


def test_the_mirror_sells_behind_the_swing_high():
    out, _ = asyncio.run(_run(sign=-1.0, dow="falling", swing=31031.0))
    approved = _sent(out)
    assert len(approved) == 1 and approved[0]["decision_side"] == "sell"
    assert approved[0]["invalidation_price"] == 31032.0


def test_emas_against_dow_send_nothing():
    out, atom = asyncio.run(_run(sign=-1.0, dow="rising"))
    assert not _sent(out) and atom._tally == {"EMA_NOT_SAME_WAY": 1}


def test_dow_without_a_trend_sends_nothing():
    out, atom = asyncio.run(_run(dow="none"))
    assert not _sent(out) and atom._tally == {"DOW_NO_TREND": 1}


def test_a_stale_dow_reading_is_not_used():
    out, atom = asyncio.run(_run(dow_start=START - 900.0))
    assert not _sent(out) and atom._tally == {"DOW_NOT_FRESH": 1}


def test_a_nasdaq_stop_under_twenty_pips_is_no_trade():
    out, atom = asyncio.run(_run(swing=30985.0))                  # 16 pips: under the owner's 20 floor
    assert not _sent(out) and atom._tally == {"NO_STOP_IN_BAND": 1}


def test_an_open_position_or_the_wait_after_a_close_sends_nothing():
    out, atom = asyncio.run(_run(positions=("USTEC",)))
    assert not _sent(out) and atom._tally == {"POSITION_OPEN": 1}
    out, atom = asyncio.run(_run(closed_before=600.0))
    assert not _sent(out) and atom._tally == {"WAIT_AFTER_CLOSE": 1}
    out, _ = asyncio.run(_run(closed_before=1200.0))
    assert len(_sent(out)) == 1


def test_nothing_new_in_the_last_hour_of_the_window():
    """2026-10-25 (owner seal, law 21): «ما تفتح صفقات جديدة» in the window's last hour -- 15:00 New York for the Nasdaq."""
    global START, M
    saved = START, M
    START = datetime(2026, 10, 14, 18, 45, tzinfo=timezone.utc).timestamp()     # the quarter hour closing at 15:00 New York
    M = START + 900.0
    try:
        out, atom = asyncio.run(_run(dow_start=START))
        assert not _sent(out) and atom._tally == {"LAST_HOUR": 1}, atom._tally
    finally:
        START, M = saved


def test_history_candles_warm_the_emas_but_never_decide():
    out, atom = asyncio.run(_run(history_only=True))
    assert not _sent(out) and atom._tally == {} and len(atom._bars["USTEC"]) == 160


def test_the_owners_switch_pauses_the_card(tmp_path, monkeypatch):
    switch = tmp_path / "strategy_switch.json"
    switch.write_text(json.dumps({"active": ["404"]}), encoding="utf-8")
    monkeypatch.setattr(strategy_switch, "PATH", switch)
    out, atom = asyncio.run(_run())
    assert not _sent(out) and atom._tally == {"PAUSED_BY_OWNER": 1}
    other = tmp_path / "strategy_switch_on.json"
    other.write_text(json.dumps({"active": ["415"]}), encoding="utf-8")
    monkeypatch.setattr(strategy_switch, "PATH", other)
    out, _ = asyncio.run(_run())
    assert len(_sent(out)) == 1


def test_ema_order_matches_the_backtest_rule():
    assert mod.ema_order(_closes(100.0, 1.0, 149)) == "none"       # under 150 bars: no reading
    assert mod.ema_order(_closes(100.0, 1.0)) == "rising"
    assert mod.ema_order(_closes(100.0, -1.0)) == "falling"
    assert mod.ema_order([100.0] * 160) == "none"
