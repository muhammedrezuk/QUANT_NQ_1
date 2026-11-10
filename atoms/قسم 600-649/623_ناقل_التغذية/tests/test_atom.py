"""اختبارات صانع التِكّة 623 — العقد: كل قمّة دفتر تِكّة، بلا حكم."""
from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location(
    "atom_623", Path(__file__).resolve().parents[1] / "atom.py")
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)


class Bus:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    async def publish(self, name: str, payload: dict | None = None) -> None:
        self.events.append((name, payload or {}))

    def subscribe(self, name: str, handler: Any) -> None:
        pass

    def of(self, name: str) -> list[dict]:
        return [p for n, p in self.events if n == name]


def build(state_every: int = 1000):
    from core.contracts.atom import AtomContext
    bus = Bus()
    atom = mod.Atom()
    ctx = AtomContext(atom_id=623, config={"state_every": state_every},
                      logger=None, publish=bus.publish, subscribe=bus.subscribe,
                      subscribe_all=lambda h: None)
    asyncio.run(atom.initialize(ctx))
    asyncio.run(atom.start())
    return atom, bus


def depth(best_bid, best_ask, seq: int = 1, **extra) -> dict:
    return {"provider": "CTRADER", "account_id": "52992818",
            "broker": "Raw Trading Ltd", "symbol": "BTCUSD",
            "timestamp": 1788790000.0 + seq, "sequence": seq,
            "sequence_gap": 0, "out_of_order": False, "fabric_gap": False,
            "exchange_timestamp": 1788790000.0 + seq,
            "best_bid": best_bid, "best_ask": best_ask,
            "bids": [], "asks": [], **extra}


def feed(atom, payload):
    asyncio.run(atom._on_depth(payload))


def test_top_becomes_a_tick():
    atom, bus = build()
    feed(atom, depth(100.0, 101.0))
    tick = bus.of("feed.ctrader.tick")[-1]
    assert tick["bid"] == 100.0 and tick["ask"] == 101.0
    assert tick["price"] == 100.5
    print("OK — القمّة تصير تِكّة")


def test_unchanged_top_still_emits():
    """الحجم تحت القمّة قد يتبدّل — وذلك شأن ذرّات السيولة لا شأن التغذية."""
    atom, bus = build()
    feed(atom, depth(100.0, 101.0, seq=1))
    feed(atom, depth(100.0, 101.0, seq=2))
    out = bus.of("feed.ctrader.tick")
    assert len(out) == 2, "قمّة ثابتة ليست سببًا للكتم"
    assert out[0]["top_changed"] is True and out[1]["top_changed"] is False
    print("OK — قمّة لم تتغيّر تخرج ومعها علامتها")


def test_crossed_spread_passes_untouched():
    atom, bus = build()
    feed(atom, depth(101.0, 99.0))
    tick = bus.of("feed.ctrader.tick")[-1]
    assert tick["bid"] == 101.0 and tick["ask"] == 99.0
    print("OK — السبريد المقلوب يعبر")


def test_one_sided_book_has_no_fabricated_price():
    atom, bus = build()
    feed(atom, depth(100.0, None))
    tick = bus.of("feed.ctrader.tick")[-1]
    assert tick["ask"] is None and tick["price"] is None
    print("OK — لا وسط مُلفَّق من طرف واحد")


def test_empty_book_is_declared():
    atom, bus = build()
    feed(atom, depth(None, None, book_empty=True))
    tick = bus.of("feed.ctrader.tick")[-1]
    assert tick["book_empty"] is True and tick["price"] is None
    print("OK — الدفتر الخالي يصل من يقرّر")


def test_identity_and_tracking_survive():
    atom, bus = build()
    feed(atom, depth(100.0, 101.0, seq=9))
    tick = bus.of("feed.ctrader.tick")[-1]
    for key in ("account_id", "broker", "provider", "sequence",
                "sequence_gap", "out_of_order", "fabric_gap",
                "exchange_timestamp"):
        assert key in tick, f"حقل ضاع: {key}"
    assert tick["sequence"] == 9
    print("OK — الهويّة والتتبّع يعبران")


def test_counts_match_and_health_green():
    atom, bus = build()
    for i in range(5):
        feed(atom, depth(100.0 + i, 101.0 + i, seq=i + 1))
    health = asyncio.run(atom.health_check())
    assert atom._received == atom._emitted == 5
    assert health.state.name == "HEALTHY" and "emitted=5" in health.message
    print("OK — الوارد يساوي الصادر")


def test_tick_gap_is_unhealthy():
    atom, bus = build()
    atom._received, atom._emitted = 10, 7
    health = asyncio.run(atom.health_check())
    assert health.state.name == "UNHEALTHY" and "TICK_GAP" in health.message
    print("OK — الفقد عجز لا تعثّر")


def test_missing_symbol_is_counted():
    atom, bus = build()
    feed(atom, {"best_bid": 1.0, "best_ask": 2.0})
    assert bus.of("feed.ctrader.tick") == [] and atom._malformed == 1
    print("OK — بلا رمز لا تُشتقّ تِكّة، ويُحصى العجز")


def test_state_event_every_n():
    atom, bus = build(state_every=3)
    for i in range(6):
        feed(atom, depth(100.0 + i, 101.0 + i, seq=i + 1))
    assert len(bus.of("feed.relay.state")) == 2
    print("OK — حالة كل ٣ تِكّات")


def test_snapshot_restore_roundtrip():
    atom, bus = build()
    for i in range(4):
        feed(atom, depth(100.0 + i, 101.0 + i, seq=i + 1))
    snap = asyncio.run(atom.snapshot())
    fresh, _ = build()
    asyncio.run(fresh.restore(snap))
    assert fresh._received == 4 and fresh._emitted == 4
    print("OK — اللقطة تعود كما هي")


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
    print("\n623: كل الاختبارات خضراء")
