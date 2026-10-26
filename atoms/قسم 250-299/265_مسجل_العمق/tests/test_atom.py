# -*- coding: utf-8 -*-
"""مسجّل العمق: آخر حقيقةٍ لكلّ (رمز · محلّل)، وآخر دفترٍ خام لكلّ رمز (أفضل `book_levels` في كلّ جهة)، في الدقيقة —
تُكتب عند بدء الدقيقة التالية وعند الإيقاف. الوقت من ختم الحدث لا من الساعة (الدستور ١٣)."""
import asyncio
import importlib.util
import json
import pathlib
import sqlite3
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from core.contracts.atom import AtomContext  # noqa: E402

spec = importlib.util.spec_from_file_location("_t265", pathlib.Path(__file__).resolve().parents[1] / "atom.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class _Log:
    def __getattr__(self, _):
        return lambda *a, **k: None


def _run(d, steps, config=None):
    async def run():
        handlers = {}
        ctx = AtomContext(atom_id=265, config={"data_dir": d, **(config or {})}, logger=_Log(),
                          publish=lambda *a: None, subscribe=lambda n, h: handlers.setdefault(n, []).append(h))
        atom = mod.Atom()
        await atom.initialize(ctx)
        await atom.start()
        for event, payload in steps:
            for h in handlers[event]:
                await h(payload)
        health = await atom.health_check()
        await atom.shutdown()
        con = sqlite3.connect(str(pathlib.Path(d) / "depth_facts.db"))
        try:
            facts = con.execute("select minute, symbol, analyzer, facts from depth_facts order by minute").fetchall()
            books = con.execute("select minute, symbol, best_bid, best_ask, bid_levels_total, ask_levels_total, "
                                "bids, asks from depth_book order by minute").fetchall()
        finally:
            con.close()
        return facts, books, health
    return asyncio.run(run())


def test_last_fact_per_minute_is_written():
    steps = [("liquidity.ofi.state", {"symbol": "USTEC", "timestamp": t, "metadata": {"ofi": v}})
             for v, t in ((1.0, 600.0), (2.0, 630.0), (3.0, 665.0))]
    steps.append(("liquidity.ofi.state", {"symbol": "USTEC", "metadata": {"ofi": 9.0}}))   # بلا ختم وقت ⟸ لا يُكتب
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        facts, books, _ = _run(d, steps)
    assert [(r[0], r[1], r[2]) for r in facts] == [(10, "USTEC", "ofi"), (11, "USTEC", "ofi")]
    assert json.loads(facts[0][3])["m.ofi"] == 2.0 and json.loads(facts[1][3])["m.ofi"] == 3.0
    assert books == []


def test_raw_book_last_per_minute_cut_to_book_levels():
    ladder = [[100.0 - i, 1.0 + i] for i in range(15)]
    steps = [
        ("market.depth", {"symbol": "ustec", "timestamp": 600.0, "bids": ladder, "asks": ladder,
                          "best_bid": 100.0, "best_ask": 100.5, "bid_levels_total": 15, "ask_levels_total": 15}),
        ("market.depth", {"symbol": "USTEC", "timestamp": 650.0, "bids": ladder[1:], "asks": ladder,
                          "best_bid": 99.0, "best_ask": 100.5, "bid_levels_total": 14, "ask_levels_total": 15}),
        ("market.depth", {"symbol": "USTEC", "timestamp": 700.0, "bids": "bad", "asks": []}),   # شكلٌ خاطئ ⟸ يُتجاهل
        ("liquidity.depth.state", {"symbol": "USTEC", "timestamp": 725.0, "metadata": {"imbalance": 0.2}}),
    ]
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        facts, books, health = _run(d, steps, {"book_levels": 3})
    assert len(books) == 1
    minute, symbol, bb, ba, bt, at, bids, asks = books[0]
    assert (minute, symbol, bb, ba, bt, at) == (10, "USTEC", 99.0, 100.5, 14, 15)    # الأخير في دقيقته
    assert json.loads(bids) == ladder[1:4] and json.loads(asks) == ladder[:3]       # أفضل ثلاثة في كلّ جهة
    assert [(r[0], r[2]) for r in facts] == [(12, "depth")]
    assert health.details["book_seen"] == 2 and "book_written=1" in health.message
