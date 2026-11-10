# -*- coding: utf-8 -*-
"""٢٠٢٦-١٠-٠٧ (ختم المالك «NQ» — فكّ الأقسام عن القرار): المسار الجديد كلّه على الذرّات الحقيقيّة.

بطاقة 414 (حقائق خام ⟵ قرارٌ بوقفه وهدفه) ⟵ 467 (الإرسال) ⟵ 555 (طالب الدخول) ⟵ طلب أمر
بوقف البطاقة وهدفها نفسيهما — لا وقفَ احتياطيّ ولا هدفَ مخترَع (أمر المالك ٢٠٢٦-٠٩-١٩).
اختبارات كلّ ذرّةٍ وحدها لا تقول إنّ الحلقات تتكلّم لغةً واحدة؛ هذا يقوله. والحمولات من
ناشريها الحقيقيّين (513 تحت `metadata` كما ينشرها حيًّا)."""
from __future__ import annotations

import asyncio
import importlib.util
import sys
import time
from pathlib import Path

import pytest
import yaml

from build_registry.paths import RegistryAtomRoot
from core.contracts.atom import AtomContext
from shared import account_limits, red_lines

ROOT = Path(__file__).resolve().parents[1]
ATOMS = RegistryAtomRoot(ROOT)
SYM, ACC, BROKER = "USTEC", "ACC", "BR"


@pytest.fixture(autouse=True)
def _window_open(monkeypatch):
    # 2026-10-17: 555 refuses entries outside 03:00-22:00 on the owner's clock (red lines); this chain test runs at whatever hour.
    monkeypatch.setattr(red_lines, "session_state", lambda epoch_s, symbol=None: (True, None))
    # 2026-10-25 (law 21): and not in the window's last hour, which reads the clock too
    monkeypatch.setattr(red_lines, "in_last_hour", lambda epoch_s, symbol=None: False)
    # 2026-10-23 (laws 7-10): 555 also refuses without 509's account limits; this chain test is about the chain, so they are
    # held clear here (the limits themselves are tested in 509 and in 555's own tests).
    monkeypatch.setattr(account_limits, "entry_block", lambda *a, **k: ("", {}))


class _Log:
    def __getattr__(self, _name):
        return lambda *a, **k: None


class Bus:
    """ناقلٌ يوصل كلّ حدثٍ لمشتركيه — كالنواة، بلا طوابير."""

    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []
        self.handlers: dict[str, list] = {}

    def subscribe(self, name, handler) -> None:
        self.handlers.setdefault(name, []).append(handler)

    async def publish(self, name, payload=None) -> None:
        body = payload or {}
        self.events.append((name, body))
        for handler in list(self.handlers.get(name, [])):
            await handler(body)

    def of(self, name) -> list[dict]:
        return [p for n, p in self.events if n == name]


async def _build(atom_id: str, bus: Bus):
    folder = next(ATOMS.glob(f"{atom_id}_*"))
    spec = importlib.util.spec_from_file_location(f"_chain414_{atom_id}", folder / "atom.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    sys.path.insert(0, str(folder))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(folder))
    manifest = yaml.safe_load((folder / "manifest.yaml").read_text(encoding="utf-8")) or {}
    config = dict(manifest.get("config") or {})
    if atom_id == "414":
        config["symbols"] = [SYM]
    atom = module.Atom()
    await atom.initialize(AtomContext(atom_id=int(atom_id), config=config, logger=_Log(),
                                      publish=bus.publish, subscribe=bus.subscribe,
                                      subscribe_all=lambda h: None))
    await atom.start()
    return atom


def _size_513(price: float) -> dict:
    """حمولة 513 كما ينشرها حيًّا — أرقامها تحت `metadata` (`555/tests` · `513/atom.py`)."""
    meta = {"method": "risk_percent_sizing", "lot": 1.0, "risk_amount": 100.0, "risk_pct": 1.0,
            "stop_distance": 35.0, "equity": 10000.0, "price": price, "buy_lot": None,
            "buy_stop": None, "sell_lot": None, "sell_stop": None, "tick_value": 0.01,
            "tick_size": 0.01, "spread": 1.0, "slippage_reserve": 0.0, "commission_per_lot": 0.0,
            "max_trade_loss": 100.0, "volume_step": 0.1, "volume_min": 0.1, "volume_max": 50.0}
    return {"account_id": ACC, "broker": BROKER, "symbol": SYM, "id": "position_sizing",
            "status": "OK", "approved": True, "reason": "", "timeframe": "", "warnings": [],
            "metadata": meta}


async def _chain():
    bus = Bus()
    card = await _build("414", bus)
    await _build("467", bus)
    entry = await _build("555", bus)
    at = float(int(time.time() // 300) * 300)          # إغلاق شمعة الزناد = الآن (لا شمعة متأخّرة)
    account = {"account_id": ACC, "broker": BROKER}
    for handler in (card._on_account, entry._on_account):
        await handler(dict(account))
    for handler in (card._on_positions, entry._on_positions):
        await handler({"account_id": ACC, "broker": BROKER, "positions": []})
    # ٢٠٢٦-١٠-٢٦ (ختم المالك «nq» بعد فحص المشروع): 555 يردّ حين لا يعرف — بلا نبضة ساعةٍ حديثة، أو بتقويمٍ مجهول.
    # فالسلسلة تُغذّى كما في الحيّ: نبضة 806 وحالة 109 معروفةٌ صافية.
    await entry._on_pulse({"official_time": at})
    await entry._on_calendar({"utc": at, "known": True, "status": "CLEAR", "blocked_currencies": []})
    await entry._on_size(_size_513(30015.0))
    # ٢٠٢٦-١٠-٠٨ (ختم المالك «صلح NQ»): كلّ حقيقة ببداية شمعتها كما تنشرها 151/153/201 — والبطاقة تنتظر
    # حقائق لحظة الزناد إن وقعت على حدّ ساعةٍ أو أربع ساعات (و`at` هنا = الآن، فقد يقع عليه).
    boundary = sys.modules["_chain414_414"].frame_boundary
    begin = {s: boundary(at, s) - s for s in (3600, 14400, 86400)}
    for frame, seconds in (("1h", 3600), ("4h", 14400)):
        await card._on_trend({"symbol": SYM, "timeframe": frame, "metadata": {
            "close": 30000.0, "ema_slow_value": 29500.0, "period_start": begin[seconds]}})
        for peer in ("US500", "US30"):
            await card._on_trend({"symbol": peer, "timeframe": frame, "metadata": {
                "close": 7000.0, "ema_slow_value": 6500.0, "period_start": begin[seconds]}})
    await card._on_vol({"symbol": SYM, "timeframe": "5m", "metadata": {"atr_14": 10.0, "period_start": at - 300}})
    await card._on_vol({"symbol": SYM, "timeframe": "1d", "metadata": {"atr_14": 400.0, "period_start": begin[86400]}})
    for frame, seconds in (("1h", 3600), ("4h", 14400)):
        await card._on_ladder({"symbol": SYM, "frames": {
            "5m": {"highs": [[30010.0, at - 1800]], "lows": [[29980.0, at - 900]]},
            "1h": {"highs": [[30200.0, at - 7200]], "lows": []}, "4h": {"highs": [], "lows": []}},
            "frame_closed": {"frame": frame, "period_start": begin[seconds]}})
    await card._on_session({"symbol": SYM, "owner_window": "london_peak", "window_at": at})
    await card._on_candle({"symbol": SYM, "timeframe": "5m", "period_start": at - 600, "close": 30005.0})
    await card._on_candle({"symbol": SYM, "timeframe": "5m", "period_start": at - 300, "close": 30015.0})
    return bus, entry


def test_card_approval_becomes_an_order_request_with_the_cards_own_levels():
    bus, entry = asyncio.run(_chain())
    assert bus.of("decision.approved.state"), bus.of("strategy.card.state")[-1:]
    assert bus.of("decision.gate.passed"), bus.of("decision.gate.blocked")[-1:]
    orders = bus.of("execution.order.requested")
    assert len(orders) == 1, (bus.of("execution.entry.state")[-1:], entry._reason_tally)
    order = orders[0]
    flat = {**order, **(order.get("metadata") or {})}
    stop = flat.get("stop_loss", flat.get("sl", flat.get("stop")))
    target = flat.get("take_profit", flat.get("tp", flat.get("target")))
    assert stop == pytest.approx(29980.0), flat           # وقف البطاقة: تحت قاع الارتداد
    assert target == pytest.approx(30200.0), flat         # هدف البطاقة: مستوى الساعة
    assert str(flat.get("side") or flat.get("decision_side")).lower() == "buy"
