# -*- coding: utf-8 -*-
"""حرّاس القطع المبكّر — ما يجوز قطعه، وما يُمنع قطعه منعًا.

الخطر الوحيد في هذه الآليّة أن تبتلع فعلًا لا قيمة: أمرًا أو تنفيذًا أو نبضة.
فهذه الحرّاس تثبت الحدّ قبل أن يُفتح الوضع الحاسم.
"""
from __future__ import annotations

import pytest

from engine import NQEngine
from engine.cutoff import (VERDICT_CHANGED, VERDICT_CUT, VERDICT_EXEMPT,
                           CutoffLedger, fingerprint, is_pure)
from transport.owned_event_bus import OwnedEventBus


# ── عقد النقاء: ما هو قيمةٌ وما هو فعل ──────────────────────────────────────

@pytest.mark.parametrize("name", [
    "analysis.trend.state", "risk.position_size.state", "decision.scored.state",
    "market.symbol_specs.synced", "portfolio.book.snapshot",
])
def test_derived_values_are_pure(name: str) -> None:
    assert is_pure(name) is True


@pytest.mark.parametrize("name", [
    # أفعالٌ لها أثرٌ جانبيّ — لا تُقطع أبدًا مهما تطابقت حمولتها
    "execution.order.built", "execution.order.submit.state", "decision.buy.state",
    "decision.sell.state", "execution.cancel.state", "risk.final_decision.state",
    "analysis.settings.command", "bridge.send.state", "execution.execute.state",
    # ونبضات الوقت: غايتها الإطلاق لا القيمة
    "SYS_SECOND", "SYS_5MIN", "SYS_15MIN", "SYS_HOUR", "SYS_DAY",
    # وما ليس حالةً أصلًا
    "market.tick", "feed.mt5.tick", "market_data.candle_closed",
])
def test_actions_and_beats_are_never_pure(name: str) -> None:
    assert is_pure(name) is False


def test_exempt_names_are_never_judged() -> None:
    ledger = CutoffLedger(mode="shadow")
    for _ in range(3):
        assert ledger.evaluate("execution.order.built",
                               {"symbol": "XAUUSD", "lot": 0.5}) == VERDICT_EXEMPT
        assert ledger.evaluate("SYS_SECOND", {}) == VERDICT_EXEMPT
    assert ledger.cut == 0 and ledger.changed == 0
    assert ledger.exempt == 6


# ── الحكم على القيمة ────────────────────────────────────────────────────────

def test_first_value_is_changed_then_identical_is_cut() -> None:
    ledger = CutoffLedger(mode="shadow")
    body = {"symbol": "XAUUSD", "trend": "up", "score": 0.72}
    assert ledger.evaluate("analysis.trend.state", body) == VERDICT_CHANGED
    assert ledger.evaluate("analysis.trend.state", dict(body)) == VERDICT_CUT
    assert ledger.evaluate("analysis.trend.state", dict(body)) == VERDICT_CUT
    assert ledger.evaluate("analysis.trend.state",
                           {**body, "score": 0.73}) == VERDICT_CHANGED


def test_identity_and_time_fields_never_block_a_cut() -> None:
    """لولا نزع الهويّة لما تساوت بصمتان أبدًا ولما قُطع شيء."""
    ledger = CutoffLedger(mode="shadow")
    base = {"symbol": "EURUSD", "value": 1.0}
    ledger.evaluate("analysis.x.state", {**base, "event_id": "a", "timestamp": 1.0,
                                         "trace_id": "t1", "seq": 1})
    verdict = ledger.evaluate("analysis.x.state", {**base, "event_id": "b", "timestamp": 2.0,
                                                  "trace_id": "t2", "seq": 2})
    assert verdict == VERDICT_CUT


def test_scopes_do_not_collide() -> None:
    """رمزان مختلفان لا يقطع أحدهما الآخر — ولو تطابقت قيمتاهما."""
    ledger = CutoffLedger(mode="shadow")
    body = {"trend": "up"}
    assert ledger.evaluate("analysis.trend.state", {**body, "symbol": "XAUUSD"}) == VERDICT_CHANGED
    assert ledger.evaluate("analysis.trend.state", {**body, "symbol": "BTCUSD"}) == VERDICT_CHANGED
    assert ledger.evaluate("analysis.trend.state", {**body, "symbol": "XAUUSD"}) == VERDICT_CUT


def test_nan_is_stable_and_nested_values_count() -> None:
    ledger = CutoffLedger(mode="shadow")
    nan = float("nan")
    ledger.evaluate("a.state", {"symbol": "X", "v": nan, "d": {"k": [1, 2]}})
    assert ledger.evaluate("a.state", {"symbol": "X", "v": nan, "d": {"k": [1, 2]}}) == VERDICT_CUT
    assert ledger.evaluate("a.state", {"symbol": "X", "v": nan, "d": {"k": [1, 3]}}) == VERDICT_CHANGED


def test_fingerprint_ignores_identity_only() -> None:
    a = fingerprint({"symbol": "X", "v": 1, "event_id": "1", "timestamp": 9.0})
    b = fingerprint({"symbol": "X", "v": 1, "event_id": "2", "timestamp": 8.0})
    c = fingerprint({"symbol": "X", "v": 2, "event_id": "1", "timestamp": 9.0})
    assert a == b and a != c


def test_ledger_bounds_its_memory() -> None:
    ledger = CutoffLedger(mode="shadow", max_keys=50)
    for i in range(500):
        ledger.evaluate("a.state", {"symbol": "S%d" % i, "v": i})
    assert len(ledger._last) <= 50


# ── السلوك داخل المحرّك ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_shadow_mode_delivers_exactly_what_off_delivers() -> None:
    """الظِّلّ يحكم ويعدّ — وتسليمه مطابقٌ حرفًا لتسليم المحرّك بلا قطع.

    ٢٠٢٦-٠٩-١٧: أوّل صياغةٍ لهذا الحارس افترضت خمس تسليماتٍ لخمس نشرات، فسقط —
    لأنّ المحرّك يدمج حالات الإيقاع أصلًا (§١٦). فالمقارنة الصحيحة ليست بعددٍ
    متوقَّع بل **بالمحرّك نفسه مطفأ القطع**: أيّ فرقٍ بينهما عيب.
    """
    async def run(mode: str) -> tuple[list[dict], dict]:
        engine = NQEngine(cold_bus=OwnedEventBus(worker_count=1), cutoff_mode=mode)
        seen: list[dict] = []

        async def handler(payload: dict) -> None:
            seen.append({k: v for k, v in payload.items()
                         if k in ("symbol", "trend", "score")})

        engine.subscribe("analysis.trend.state", handler, subscriber="301")
        for score in (1, 1, 1, 2, 2):
            await engine.publish("analysis.trend.state",
                                 {"symbol": "XAUUSD", "trend": "up", "score": score},
                                 publisher="101")
            await engine.drain()
        stats = engine.transport_stats()["engine"]
        await engine.close()
        return seen, stats

    off_seen, off_stats = await run("off")
    shadow_seen, shadow_stats = await run("shadow")

    assert shadow_seen == off_seen, "الظِّلّ غيّر التسليم — وهذا ممنوع"
    assert shadow_stats["cutoff_suppressed"] == 0
    # ومع ذلك يعرف كم كان سيقطع: ثلاث قيمٍ مكرّرة من خمس
    assert shadow_stats["cutoff"]["cut"] == 3
    assert shadow_stats["cutoff"]["changed"] == 2
    assert shadow_stats["cutoff"]["cut_ratio"] == 0.6
    assert off_stats["cutoff"]["judged"] == 0


@pytest.mark.asyncio
async def test_enforce_suppresses_only_unchanged_values() -> None:
    engine = NQEngine(cold_bus=OwnedEventBus(worker_count=1), cutoff_mode="enforce")
    seen: list[dict] = []

    async def handler(payload: dict) -> None:
        seen.append(dict(payload))

    # مشترِكٌ خارج نطاق الإيقاع (١٥٠–٤٩٩) كي يُسلَّم كلّ حدثٍ وحده، فيُقاس
    # أثر القطع نقيًّا لا مخلوطًا بالدمج.
    engine.subscribe("analysis.trend.state", handler, subscriber="601")
    for score in (1, 1, 2):
        await engine.publish("analysis.trend.state",
                             {"symbol": "XAUUSD", "s": score}, publisher="101")
        await engine.drain()
    assert [p["s"] for p in seen] == [1, 2], seen
    assert engine.transport_stats()["engine"]["cutoff_suppressed"] == 1
    await engine.close()


@pytest.mark.asyncio
async def test_enforce_never_suppresses_money_or_beats() -> None:
    """الحارس الأهمّ: أمرٌ مكرّرٌ حرفيًّا يصل مرّتين، ونبضةٌ فارغة تصل كلّ مرّة."""
    engine = NQEngine(cold_bus=OwnedEventBus(worker_count=1), cutoff_mode="enforce")
    orders: list[dict] = []
    beats: list[dict] = []

    async def on_order(payload: dict) -> None:
        orders.append(dict(payload))

    async def on_beat(payload: dict) -> None:
        beats.append(dict(payload))

    engine.subscribe("execution.order.built", on_order, subscriber="601")
    engine.subscribe("SYS_SECOND", on_beat, subscriber="150")
    for _ in range(4):
        await engine.publish("execution.order.built",
                             {"symbol": "XAUUSD", "lot": 0.5, "side": "SELL"}, publisher="552")
        await engine.publish("SYS_SECOND", {}, publisher="1")
    await engine.drain()
    assert len(orders) == 4, "أمرٌ ابتُلع — عطلٌ ماليّ"
    assert len(beats) == 4, "نبضةٌ ابتُلعت — الساعة تتوقّف"
    assert engine.transport_stats()["engine"]["cutoff_suppressed"] == 0
    await engine.close()


# ── سقف الحجب: القطع لا يُجوّع حارس الطزاجة ─────────────────────────────────

def test_a_static_value_passes_once_after_the_hold_ceiling() -> None:
    """⛔ أخطر ما في القطع ليس الأداء: `live_analysis` يعلن STATE_STALE لكلّ
    نطاقٍ لم يُنشَر منذ `stale_after` (أدناها 0.5 ث) ⟵ القسم STALE ⟵ 456
    يرفض ⟵ صفر أمر. فالساكن يمرّ مرّةً كلّما طال حجبه."""
    import time as _t
    ledger = CutoffLedger(mode="enforce", max_hold_s=0.05)
    body = {"symbol": "XAUUSD", "v": 1}
    assert ledger.evaluate("a.state", body) == VERDICT_CHANGED
    assert ledger.evaluate("a.state", dict(body)) == VERDICT_CUT
    deadline = _t.perf_counter() + 1.0
    verdict = VERDICT_CUT
    while _t.perf_counter() < deadline:
        verdict = ledger.evaluate("a.state", dict(body))
        if verdict == VERDICT_CHANGED:
            break
    assert verdict == VERDICT_CHANGED, "قيمةٌ ساكنة حُجبت إلى الأبد"
    assert ledger.stats()["held_open"] >= 1


def test_zero_ceiling_holds_forever_as_before() -> None:
    ledger = CutoffLedger(mode="enforce", max_hold_s=0.0)
    body = {"symbol": "X", "v": 1}
    ledger.evaluate("a.state", body)
    for _ in range(50):
        assert ledger.evaluate("a.state", dict(body)) == VERDICT_CUT
    assert ledger.stats()["held_open"] == 0


def test_the_ceiling_never_resurrects_a_command() -> None:
    ledger = CutoffLedger(mode="enforce", max_hold_s=0.001)
    for _ in range(5):
        assert ledger.evaluate("execution.order.built", {"symbol": "X"}) == VERDICT_EXEMPT
    assert ledger.stats()["held_open"] == 0


def test_the_ceiling_memory_is_bounded_with_the_ledger() -> None:
    ledger = CutoffLedger(mode="enforce", max_keys=20, max_hold_s=1.0)
    for index in range(300):
        ledger.evaluate("a.state", {"symbol": "S%d" % index, "v": index})
    assert len(ledger._last) <= 20
    assert len(ledger._passed_at) <= 20, "خريطة السقف تسرّبت"


# ── التعلّم: ما لا يتكرّر لا يُدفع ثمن فحصه ──────────────────────────────────

def test_an_always_changing_event_is_dropped_from_judging() -> None:
    """`analysis.trend.state`: صفر قطعٍ من 19,980 — ودفعُ 8.32 م.ث لكلّ واحدةٍ
    منها خسارةٌ صافية. فبعد عيّنةٍ كافية يُترك الاسم نهائيًّا."""
    ledger = CutoffLedger(mode="enforce", learn_after=50, learn_floor=0.02)
    for index in range(200):
        ledger.evaluate("analysis.trend.state", {"symbol": "X", "v": index})
    stats = ledger.stats()
    assert "analysis.trend.state" in stats["skipped_events"]
    assert stats["skipped"] >= 140, stats["skipped"]


def test_a_repeating_event_is_never_dropped() -> None:
    ledger = CutoffLedger(mode="enforce", learn_after=50, learn_floor=0.02)
    for _ in range(200):
        ledger.evaluate("decision.filter.position.state", {"symbol": "X", "ok": True})
    stats = ledger.stats()
    assert stats["skipped_events"] == []
    assert stats["cut"] >= 140


def test_learning_off_keeps_judging_everything() -> None:
    ledger = CutoffLedger(mode="enforce", learn_after=0)
    for index in range(300):
        ledger.evaluate("a.state", {"symbol": "X", "v": index})
    assert ledger.stats()["skipped"] == 0


def test_a_skipped_event_is_never_suppressed() -> None:
    """المتروك يمرّ دائمًا — لا يُكتم بالخطأ."""
    ledger = CutoffLedger(mode="enforce", learn_after=20, learn_floor=0.5)
    for index in range(60):
        ledger.evaluate("a.state", {"symbol": "X", "v": index})
    assert ledger._skip
    for _ in range(10):
        assert ledger.evaluate("a.state", {"symbol": "X", "v": 1}) == VERDICT_CHANGED
