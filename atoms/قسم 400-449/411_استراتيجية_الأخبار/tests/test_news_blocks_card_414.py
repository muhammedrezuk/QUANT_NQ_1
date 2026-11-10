# -*- coding: utf-8 -*-
"""٢٠٢٦-١٠-٠٧ (ختم المالك «NQ» — فكّ الأقسام عن القرار): حظر الخبر العالي يبلغ القرار — على المسار الجديد.

خلفُ `test_fix_2026_10_02.py` (أُرشف مع فلتر القرار 454 الذي كان يقيس عليه). هنا **411 الحقيقيّ
والبطاقة 414 الحقيقيّة** على ناقلٍ يوصل النشرة إلى مشتركها:
  ١· خبرٌ عالي الأثر بعد 10 دقائق ⟸ البطاقة تُؤرشف «منع خبر» ولا موافقة (قانون المالك: لا مقامرة على خبر).
  ٢· خبرٌ عالي الأثر بعد 40 دقيقة ⟸ لا نافذة ولا منع (خارج الـ15 دقيقة) والبطاقة تُفتح.
والأساس الزمنيّ واحد كما في الحيّ: `published_at` ثوانٍ غرينتش، وإغلاق شمعة الزناد غرينتش."""
import importlib.util as _ilu
import sys
import time
from pathlib import Path as _Path

import yaml

_ROOT = _Path(__file__).resolve().parents[4]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from build_registry.paths import RegistryAtomRoot  # noqa: E402
from core.contracts.atom import AtomContext  # noqa: E402

_DIR411 = _Path(__file__).resolve().parents[1]
_DIR414 = next(RegistryAtomRoot(_ROOT).glob("414_*"))
SYMBOL = "USTEC"


def _load(name, path):
    spec = _ilu.spec_from_file_location(name, path)
    mod = _ilu.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


M411 = _load("_atom411_news_card", _DIR411 / "atom.py")
M414 = _load("_atom414_news_card", _DIR414 / "atom.py")


def _config(folder):
    return dict(yaml.safe_load((folder / "manifest.yaml").read_text(encoding="utf-8"))["config"] or {})


class _Log:
    def __getattr__(self, name):
        return lambda *a, **k: None


class Bus:
    def __init__(self):
        self.handlers, self.out = {}, []

    def subscribe(self, name, handler):
        self.handlers.setdefault(name, []).append(handler)

    async def publish(self, name, payload):
        self.out.append((name, payload))
        for handler in list(self.handlers.get(name, [])):
            await handler(payload)

    def of(self, name):
        return [p for n, p in self.out if n == name]


async def _wire(monkeypatch):
    monkeypatch.setenv("QUANT_REPLAY_NO_WARM", "1")      # لا تسخين من قرص الجهاز الحيّ
    bus = Bus()
    a411, a414 = M411.Atom(), M414.Atom()
    await a411.initialize(AtomContext(411, _config(_DIR411), _Log(), bus.publish, bus.subscribe))
    await a414.initialize(AtomContext(414, {**_config(_DIR414), "symbols": [SYMBOL]}, _Log(),
                                      bus.publish, bus.subscribe))
    await a411.start()
    await a414.start()
    at = float(int(time.time() // 300) * 300)
    await a414._on_account({"account_id": "52992818", "broker": "Raw Trading Ltd"})
    await a414._on_positions({"positions": []})
    # ٢٠٢٦-١٠-٠٨ (ختم المالك «صلح NQ»): كلّ حقيقة ببداية شمعتها كما تنشرها 151/153/201 — والبطاقة تنتظر
    # حقائق لحظة الزناد إن وقعت على حدّ ساعةٍ أو أربع ساعات (و`at` هنا = الآن، فقد يقع عليه).
    begin = {s: M414.frame_boundary(at, s) - s for s in (3600, 14400, 86400)}
    for frame, seconds in (("1h", 3600), ("4h", 14400)):
        await a414._on_trend({"symbol": SYMBOL, "timeframe": frame, "metadata": {
            "close": 30000.0, "ema_slow_value": 29500.0, "period_start": begin[seconds]}})
        for peer in ("US500", "US30"):
            await a414._on_trend({"symbol": peer, "timeframe": frame, "metadata": {
                "close": 7000.0, "ema_slow_value": 6500.0, "period_start": begin[seconds]}})
    await a414._on_vol({"symbol": SYMBOL, "timeframe": "5m", "metadata": {"atr_14": 10.0, "period_start": at - 300}})
    await a414._on_vol({"symbol": SYMBOL, "timeframe": "1d", "metadata": {"atr_14": 400.0, "period_start": begin[86400]}})
    for frame, seconds in (("1h", 3600), ("4h", 14400)):
        await a414._on_ladder({"symbol": SYMBOL, "frames": {
            "5m": {"highs": [[30010.0, at - 1800]], "lows": [[29980.0, at - 900]]},
            "1h": {"highs": [[30200.0, at - 7200]], "lows": []}, "4h": {"highs": [], "lows": []}},
            "frame_closed": {"frame": frame, "period_start": begin[seconds]}})
    await a414._on_session({"symbol": SYMBOL, "owner_window": "london_peak", "window_at": at})
    return a414, bus, at


async def _card_after_news(monkeypatch, minutes_ahead):
    a414, bus, at = await _wire(monkeypatch)
    now = time.time()
    await bus.publish("market_data.news_received", {
        "headline": "FOMC rate decision (%d min)" % minutes_ahead, "source": "test",
        "symbols": [SYMBOL], "impact_level": "HIGH", "published_at": now + minutes_ahead * 60.0})
    await bus.publish("market.tick.validated", {
        "account_id": "52992818", "broker": "Raw Trading Ltd", "provider": "CTRADER",
        "symbol": SYMBOL, "bid": 30015.0, "ask": 30016.0, "price": 30015.5,
        "timestamp": now, "exchange_timestamp": now})
    await a414._on_candle({"symbol": SYMBOL, "timeframe": "5m", "period_start": at - 600, "close": 30005.0})
    await a414._on_candle({"symbol": SYMBOL, "timeframe": "5m", "period_start": at - 300, "close": 30015.0})
    return bus.of("strategy.card.state")[-1], bus


async def test_high_impact_10_minutes_ahead_blocks_the_card(monkeypatch):
    card, bus = await _card_after_news(monkeypatch, 10)
    windows = bus.of("news.trading_window.state")
    assert windows, "411 لم ينشر نافذة"
    w = windows[-1]
    assert w["window_start"] == w["source_timestamp"] - 15 * 60 and w["window_end"] == w["source_timestamp"] + 15 * 60, w
    assert card["status"] == "NEWS_BLACKOUT", card
    assert not bus.of("decision.approved.state")


async def test_high_impact_40_minutes_ahead_does_not_block(monkeypatch):
    card, bus = await _card_after_news(monkeypatch, 40)
    assert not bus.of("news.trading_window.state"), "40 دقيقة خارج نافذة الـ15"
    assert card["status"] == "OPEN", card
    assert len(bus.of("decision.approved.state")) == 1
