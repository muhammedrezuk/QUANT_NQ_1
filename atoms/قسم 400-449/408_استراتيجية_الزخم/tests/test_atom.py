# -*- coding: utf-8 -*-
"""الاستراتيجيّات على حقائق الأقسام (٢٠٢٦-١٠-١٠): حقيقة زخمٍ موجبة + قاع خارجيّ على بُعد 30 نقطة داخل جلسة
نيويورك ⟸ إعداد وموافقة شراء بوقفٍ خلف القاع وهدف 3R؛ وخارج الجلسة أو والمركز مفتوح ⟸ لا شيء."""
import asyncio
import importlib.util
import pathlib
import sys
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from core.contracts.atom import AtomContext  # noqa: E402
import shared.facts_strategy_atom as FSA  # noqa: E402

spec = importlib.util.spec_from_file_location("_t408", pathlib.Path(__file__).resolve().parents[1] / "atom.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

NY_OPEN = datetime(2026, 10, 8, 14, 0, tzinfo=timezone.utc).timestamp()      # 10:00 نيويورك
SAT = datetime(2026, 10, 10, 14, 0, tzinfo=timezone.utc).timestamp()


class _Log:
    def __getattr__(self, _):
        return lambda *a, **k: None


async def _run(at, positions, symbol="USTEC", close=31000.0, low=30969.0, factors=True, spread=1.0):
    FSA.FACT_DELAY_S = 0.0
    out, handlers = [], {}
    ctx = AtomContext(atom_id=408, config={}, logger=_Log(), publish=lambda n, p: _rec(out, n, p),
                      subscribe=lambda n, h: handlers.setdefault(n, []).append(h))
    atom = mod.Atom()
    atom._clock = lambda: at
    await atom.initialize(ctx)
    await atom.start()
    for h in handlers["platform.account.state"]:
        await h({"account_id": "A", "broker": "B"})
    for h in handlers["platform.positions.state"]:
        await h({"positions": positions})
    if spread is not None:            # ١٠-١٤: الهدف صافٍ بعد السبريد ⟸ تِكّةٌ بسبريدٍ مقيس قبل الزناد
        for h in handlers["market.tick.validated"]:
            await h({"symbol": symbol, "bid": close - spread / 2, "ask": close + spread / 2})
    for h in handlers["structure.external.state"]:
        await h({"symbol": symbol, "timeframe": "5m", "metadata": {"swing_low": low, "swing_high": close * 1.01}})
    for h in handlers["analysis.momentum.state"]:
        await h({"symbol": symbol, "timeframe": "15m", "metadata": {"roc": 0.12}})
        if factors:   # ١٠-١٠: الزخم بأغلبيّة عوامله — زخم الإطار الأكبر (الساعة) وتسارع موجب = 2 من 4
            await h({"symbol": symbol, "timeframe": "1h", "metadata": {"roc": 0.30}})
    if factors:
        for h in handlers["analysis.acceleration.state"]:
            await h({"symbol": symbol, "timeframe": "15m", "metadata": {"ratio": 0.4}})
    for h in handlers["market_data.candle_closed"]:
        await h({"symbol": symbol, "timeframe": "1m", "close": close, "period_start": at - 60})
    await asyncio.sleep(0.05)
    return out


async def _rec(out, name, payload):
    out.append((name, payload))


def test_buy_in_session_sends_setup_and_approval():
    out = asyncio.run(_run(NY_OPEN, []))
    approved = [p for n, p in out if n == "decision.approved.state"]
    setups = [p for n, p in out if n == "strategy.setup.proposed"]
    assert len(approved) == 1 and len(setups) == 1, out
    a = approved[0]
    assert a["decision_side"] == "buy" and a["strategy"] == "408"
    assert a["invalidation_price"] == 30968.0                     # خلف القاع بنقطة: مخاطرة 32 ضمن 15–45
    # ١٠-١٤ (ختم المالك «NQ»): 3R + 4×السبريد×1.25 ⟸ النسبة بعد السبريد ≥ 3 كما تطلب 555.
    assert abs(a["target_price"] - (31000.0 + 3 * 32.0 + 4 * 1.0 * 1.25)) < 1e-9
    reward, risk, cost = a["target_price"] - 31000.0, 31000.0 - a["invalidation_price"], 1.0
    assert (reward - cost) / (risk + cost) >= 3.0, (reward, risk)
    assert setups[0]["setup_owner"] == "408"


def test_bitcoin_trades_round_the_clock_with_bps_stop():
    # السبت: البتكوين بلا جلسات (أمر المالك ١٠-١٠ «7/24»)؛ قاعٌ على بعد 86 دولارًا من 86,000 = 10 نقاط أساس ⟸ داخل 5–15.
    out = asyncio.run(_run(SAT, [], symbol="BTCUSD", close=86000.0, low=85916.58))
    approved = [p for n, p in out if n == "decision.approved.state"]
    assert len(approved) == 1 and approved[0]["decision_side"] == "buy", out
    assert approved[0]["metadata"]["session"] == "24/7"


def test_single_factor_no_longer_trades():
    # الزناد وحده (معدّل تغيّر الربع ساعة) بلا عواملَ تكفي الأغلبيّة ⟸ لا صفقة (أمر المالك: «ما بيصير عامل واحد»).
    out = asyncio.run(_run(NY_OPEN, [], factors=False))
    assert not [n for n, _ in out if n == "decision.approved.state"]


def test_no_trade_without_a_measured_spread():
    # ١٠-١٤: بلا سبريدٍ مقيس لا هدفٌ صافٍ ⟸ لا إرسال (كانت 555 ستحجبه عند الإرسال).
    assert not [n for n, _ in asyncio.run(_run(NY_OPEN, [], spread=None)) if n == "decision.approved.state"]


def test_no_trade_on_weekend_or_open_position():
    assert not [n for n, _ in asyncio.run(_run(SAT, [])) if n == "decision.approved.state"]
    assert not [n for n, _ in asyncio.run(_run(NY_OPEN, [{"symbol": "USTEC"}])) if n == "decision.approved.state"]
