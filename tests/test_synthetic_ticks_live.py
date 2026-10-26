#!/usr/bin/env python3
"""زرع تِكّات صناعيّة على 622 — من المقبس إلى `market.tick`.

يبني الأربع الحقيقيّة على ناقل النواة (622 · 624 · 623 · 613) ويحقن رسائل
FIX **بمستوى البايتات** في مقبس مزيّف، لا حمولات جاهزة. فيُقاس ما يخرج من
آخر السلسلة، ويُثبت أن المسار كلّه صحيح لا كل ذرّة وحدها.

الحالات المزروعة تشمل ما كان يُكتم قبل هذه النافذة: قمّة لم تتغيّر · سبريد
مقلوب · جانب ناقص · دفتر خالٍ.
"""
from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import shared.fix_session as fx                     # noqa: E402
import transport                                     # noqa: E402
from core.contracts.atom import AtomContext          # noqa: E402
from core.event_bus import EventBus                  # noqa: E402

SECTION = ROOT / "atoms" / "قسم 600-649"
SOH = "\x01"


def load(folder: str, name: str):
    # ذرّات القسم تستورد ملفّاتها المساعدة بمسار محلّيّ (622 ⇢
    # `ctrader_stream_state`)، فمجلّد الذرّة يدخل المسار قبل التحميل.
    sys.path.insert(0, str(SECTION / folder))
    spec = importlib.util.spec_from_file_location(name, SECTION / folder / "atom.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class FakeSocket:
    """مقبس مزيّف: يتصرّف كـ`StreamSession` ويطعم بايتات خامًا."""

    def __init__(self) -> None:
        self._buffer = b""
        self.connected = True
        self.sent: list[bytes] = []

    def connect(self) -> None:
        self.connected = True

    def feed(self, data: bytes) -> None:
        self._buffer += data

    def drain(self) -> bytes:
        data, self._buffer = self._buffer, b""
        return data

    def send(self, data: bytes) -> None:
        self.sent.append(data)

    def stats(self) -> dict[str, Any]:
        return {"connected": self.connected, "pending_bytes": len(self._buffer)}

    def close(self) -> None:
        self.connected = False


def wire(msg_type: str, fields: list[tuple[int, Any]],
         sending: str = "20260907-12:00:00.000") -> bytes:
    """رسالة FIX كاملة بطول جسم وتدقيق — كما يرسلها cServer."""
    body = f"35={msg_type}{SOH}49=cServer{SOH}56=live4{SOH}34=1{SOH}52={sending}{SOH}"
    body += "".join(f"{tag}={value}{SOH}" for tag, value in fields)
    head = f"8=FIX.4.4{SOH}9={len(body)}{SOH}"
    raw = head + body
    checksum = sum(raw.encode("latin-1")) % 256
    return (raw + f"10={checksum:03d}{SOH}").encode("latin-1")


def entry(side: str, entry_id: str, price: Any, size: Any,
          action: str | None = None) -> list[tuple[int, Any]]:
    rows: list[tuple[int, Any]] = []
    if action is not None:
        rows.append((fx.TAG_MD_UPDATE_ACTION, action))
    rows.append((fx.TAG_MD_ENTRY_TYPE, side))
    rows.append((fx.TAG_MD_ENTRY_ID, entry_id))
    if price is not None:
        rows.append((fx.TAG_MD_ENTRY_PX, price))
    if size is not None:
        rows.append((fx.TAG_MD_ENTRY_SIZE, size))
    return rows


async def scenario() -> tuple[list[dict], list[dict], list[dict]]:
    bus = EventBus()
    m622 = load("622_تغذية_FIX_سي_تريدر", "_live622")
    m624 = load("624_باني_دفتر_العمق", "_live624")
    m623 = load("623_ناقل_التغذية", "_live623")
    m613 = load("613_تغذية_السوق", "_live613")

    def ctx(atom_id: int, config: dict) -> AtomContext:
        return AtomContext(
            atom_id=atom_id, config=config, logger=_Log(),
            publish=lambda n, p=None, _a=atom_id: bus.publish(n, p, publisher=str(_a)),
            subscribe=lambda n, h, _a=atom_id: bus.subscribe(n, h, subscriber=str(_a)),
            subscribe_all=lambda h, _a=atom_id: bus.subscribe_all(h, subscriber=str(_a)))

    raw_out: list[dict] = []
    depth_out: list[dict] = []
    tick_out: list[dict] = []

    async def on_raw(p): raw_out.append(p)
    async def on_depth(p): depth_out.append(p)
    async def on_tick(p): tick_out.append(p)

    bus.subscribe("feed.ctrader.raw", on_raw, subscriber="probe")
    bus.subscribe("market.depth", on_depth, subscriber="probe")
    bus.subscribe("market.tick", on_tick, subscriber="probe")

    feed = m622.Atom()
    await feed.initialize(ctx(622, _CFG_622))
    socket = FakeSocket()
    feed._stream = socket
    feed._session = fx.FixSession("live4", "cServer", "QUOTE", "6175701")
    feed._session.logged_on = True
    feed._running = True
    feed._account = "6175701"
    feed._broker = "Raw Trading Ltd"
    feed._by_id = {"1": "BTCUSD"}
    feed._by_name = {"BTCUSD": "1"}

    book = m624.Atom()
    await book.initialize(ctx(624, {"state_every": 1000}))
    await book.start()

    maker = m623.Atom()
    await maker.initialize(ctx(623, {"state_every": 1000}))
    await maker.start()

    router = m613.Atom()
    await router.initialize(ctx(613, _CFG_613))
    await router.start()

    plan = [
        ("لقطة: عرض 100 / طلب 101", "W",
         [(fx.TAG_MD_REQ_ID, "MD-1"), (fx.TAG_NO_MD_ENTRIES, 2)]
         + entry("0", "b1", "100.0", "5") + entry("1", "a1", "101.0", "5")),
        ("تغيّر حجم بلا تغيّر قمّة", "X",
         [(fx.TAG_MD_REQ_ID, "MD-1"), (fx.TAG_NO_MD_ENTRIES, 1)]
         + entry("0", "b1", "100.0", "40", action="1")),
        ("سبريد مقلوب: طلب 99 تحت عرض 100", "X",
         [(fx.TAG_MD_REQ_ID, "MD-1"), (fx.TAG_NO_MD_ENTRIES, 1)]
         + entry("1", "a1", "99.0", "5", action="1")),
        ("حذف الطلب ⇒ جانب ناقص", "X",
         [(fx.TAG_MD_REQ_ID, "MD-1"), (fx.TAG_NO_MD_ENTRIES, 1)]
         + entry("1", "a1", None, None, action="2")),
        ("حذف العرض ⇒ دفتر خالٍ", "X",
         [(fx.TAG_MD_REQ_ID, "MD-1"), (fx.TAG_NO_MD_ENTRIES, 1)]
         + entry("0", "b1", None, None, action="2")),
    ]

    for label, msg_type, fields in plan:
        socket.feed(wire(msg_type, fields))
        await feed._pump()
        await bus.drain(timeout_s=3.0)
        print(f"  زُرعت: {label}")

    await book.stop()
    await maker.stop()
    await router.stop()
    return raw_out, depth_out, tick_out


class _Log:
    def info(self, *a, **k): pass
    def warning(self, *a, **k): pass
    def error(self, *a, **k): pass
    def debug(self, *a, **k): pass


_CFG_622 = {
    "host": "x", "port": 1, "use_tls": False, "sender_comp_id": "live4",
    "target_comp_id": "cServer", "sub_id": "QUOTE", "username": "6175701",
    "identity_account_id": "6175701", "broker": "Raw Trading Ltd",
    "password_secret_key": "k", "symbols": ["BTCUSD"], "market_depth": 0,
    "heartbeat_s": 30, "poll_interval_s": 0.005, "reconnect_backoff_s": 5,
    "tick_stale_after_s": 30, "depth_stale_after_s": 30,
    "specs_stale_after_s": 600, "dead_after_s": 120,
}

_CFG_613 = {
    "routes": {"feed.mt5.tick": "market.tick", "feed.ctrader.tick": "market.tick",
               "feed.replay.tick": "market.tick"},
    "provider_timeout_s": 30, "max_input_silence_seconds": 60,
    "preferred_provider": "CTRADER", "analyst_sources": ["CTRADER"],
    "broker_display_route": "market.broker_tick",
}


def main() -> int:
    print("زرع تِكّات صناعيّة — من مقبس 622 إلى market.tick\n")
    raw, depth, ticks = asyncio.run(scenario())
    print(f"\nخام من 622   : {len(raw)}")
    print(f"عمق من 624   : {len(depth)}")
    print(f"تِكّة من 613  : {len(ticks)}\n")
    for t in ticks:
        print(f"   seq={t.get('sequence')} bid={t.get('bid')} ask={t.get('ask')} "
              f"price={t.get('price')} top_changed={t.get('top_changed')} "
              f"empty={t.get('book_empty')}")

    assert len(raw) == 5, f"622 نشر {len(raw)} من 5 رسائل"
    assert len(depth) == 5, f"624 بنى {len(depth)} من 5"
    assert len(ticks) == 5, f"613 مرّر {len(ticks)} من 5 — كُتمت حالة"

    assert ticks[0]["bid"] == 100.0 and ticks[0]["ask"] == 101.0
    assert ticks[0]["price"] == 100.5
    assert ticks[1]["top_changed"] is False, "تغيّر الحجم يخرج بعلامته"
    assert ticks[2]["ask"] == 99.0 and ticks[2]["bid"] == 100.0, "سبريد مقلوب عبر"
    assert ticks[3]["ask"] is None and ticks[3]["price"] is None, "لا وسط مُلفَّق"
    assert ticks[4]["book_empty"] is True, "الدفتر الخالي أُعلن"
    for t in ticks:
        assert t.get("provider") == "CTRADER"
        assert "sequence_gap" in t and "out_of_order" in t, "التتبّع وصل"

    print("\n✅ المسار صحيح: 5 رسائل FIX ⇒ 5 خام ⇒ 5 عمق ⇒ 5 تِكّة · بلا كتم واحدة")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
