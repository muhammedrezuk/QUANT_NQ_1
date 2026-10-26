# -*- coding: utf-8 -*-
"""٢٠٢٦-١٠-١٢: الشمعة تُغلق في وقتها على نبض الثانية (لا عند أوّل تِكّةٍ بعدها)، وسعرها العرض حين `price_source: bid`."""
import asyncio
import importlib.util
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from core.contracts.atom import AtomContext  # noqa: E402

spec = importlib.util.spec_from_file_location("_t103ot", pathlib.Path(__file__).resolve().parents[1] / "atom.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class _Log:
    def __getattr__(self, _):
        return lambda *a, **k: None


def test_candle_closes_on_time_with_bid_price():
    async def run():
        out = []

        async def pub(n, p):
            out.append((n, p))
        ctx = AtomContext(atom_id=103, config={"timeframes": ["1m"], "price_source": "bid"}, logger=_Log(),
                          publish=pub, subscribe=lambda n, h: None)
        atom = mod.Atom()
        await atom.initialize(ctx)
        await atom.start()
        for ts, bid in ((1_790_000_050.0, 100.0), (1_790_000_070.0, 101.0)):
            await atom._on_tick({"symbol": "NQ", "account_id": "A", "broker": "B", "bid": bid, "ask": bid + 1.0,
                                 "timestamp": ts})
        await atom._on_pulse({"official_time": 1_790_000_100.5})      # قبل المهلة ⟸ لا إغلاق
        assert not out
        await atom._on_pulse({"official_time": 1_790_000_101.2})      # بعد نهاية الدقيقة + ثانية ⟸ تُغلق بلا تِكّة
        assert len(out) == 1
        c = out[0][1]
        assert (c["open"], c["high"], c["close"], c["period_start"]) == (100.0, 101.0, 101.0, 1_790_000_040.0)
        assert c["close"] == 101.0 and atom.closed_on_time == 1
        await atom._on_tick({"symbol": "NQ", "account_id": "A", "broker": "B", "bid": 102.0, "ask": 103.0,
                             "timestamp": 1_790_000_110.0})        # تِكّة الفترة التالية لا تُعيد نشر المغلقة
        assert len(out) == 1
    asyncio.run(run())
