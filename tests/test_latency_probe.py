"""مئينات `تِكّة ← قرار` — نظّارة تقول «لا أعرف» خيرٌ من نظّارة تخمّن.

**ختم المالك ٢٠٢٦-٠٩-١٠:** «لوحات يعني نظّارة بشوف فيها نظام. إذا نظّارتك
بتكذب…» — فالمئين وحده لا يكفي: يُعرض **ومعه** عتبته وحجم عيّنته ونافذتها،
وإلّا كان تخمينًا بلباس رقم.

⛔ **وما يمنع الكذب هنا ثلاثة:**

١) قرارٌ بلا تِكّة معروفة **لا يُحسب صفرًا** — يُعدّ في `orphan_decisions`.
٢) تِكّةٌ لم تبلغ قرارًا **لا تُحسب** — تُنسى بالعمر وتُعدّ في `expired`.
٣) العيّنة **نافذة متحرّكة** — مئينٌ على تاريخٍ من الإقلاع يصف ماضيًا ميتًا،
   وهو الخطأ الذي دفعتُ ثمنه في موازنة الأحمال قبل هذا اليوم.

والقياس بلا لمس النواة المختومة: الأثر (`trace_id`) يورَّث من الأب للابن
أصلًا، فيكفي قراءته من مرور الأحداث.
"""

from __future__ import annotations

import pytest

from transport.latency_probe import LatencyProbe, percentile

# حدث التِكّة القانونيّ الذي يعرّفه §٢٩ — هو نفسه الذي يفتح الأثر على الناقل
# الحيّ، فلا يقيس الاختبار عقدًا غير الذي يعمل به النظام.
TICK = "market_data.price_received"
DECISION = "decision.dispatch.state"


def _probe(**kwargs) -> LatencyProbe:  # noqa: ANN003
    # ٢٠٢٦-٠٩-١٨ (ختم المالك): المسبار صار يفتح على **اسمٍ كامل** لا بادئة،
    # كي لا يُفتَح أثرُ «تِكّة ← قرار» بحدثٍ دوريّ. فتُعلن الاختبارات تِكّتها.
    kwargs.setdefault("tick_events", (TICK,))
    return LatencyProbe(**kwargs)


def _pair(probe: LatencyProbe, trace: str, symbol: str, seconds: float,
          *, t0: float = 100.0) -> None:
    probe.observe(TICK, {"trace_id": trace, "symbol": symbol}, at=t0)
    probe.observe(DECISION, {"trace_id": trace}, at=t0 + seconds)


# ── المئين ──────────────────────────────────────────────────────────────

def test_percentile_interpolates_and_does_not_round() -> None:
    assert percentile([], 0.5) == 0.0
    assert percentile([0.4], 0.99) == 0.4
    assert percentile([0.0, 1.0], 0.5) == pytest.approx(0.5)


def test_a_measured_pair_lands_in_its_symbol() -> None:
    probe = _probe()
    _pair(probe, "T1", "USTEC", 0.020)
    snap = probe.snapshot()
    assert set(snap["symbols"]) == {"USTEC"}
    assert snap["symbols"]["USTEC"]["samples"] == 1
    assert snap["symbols"]["USTEC"]["p50_s"] == pytest.approx(0.020, abs=1e-4)


def test_symbols_are_measured_apart() -> None:
    """رمزٌ بطيء لا يلوّث مئين رمزٍ سريع."""
    probe = _probe()
    for index in range(20):
        _pair(probe, "F%d" % index, "USTEC", 0.010, t0=100.0 + index)
        _pair(probe, "S%d" % index, "XAUUSD", 0.400, t0=100.0 + index)
    snap = probe.snapshot()["symbols"]
    assert snap["USTEC"]["p95_s"] == pytest.approx(0.010, abs=1e-3)
    assert snap["XAUUSD"]["p95_s"] == pytest.approx(0.400, abs=1e-3)


# ── ما لا يُحسب ─────────────────────────────────────────────────────────

def test_a_decision_without_a_known_tick_is_counted_not_measured() -> None:
    """⛔ الخطر الأكبر: احتساب القرار اليتيم صفرًا يجعل المئين كاذبًا نحو الصفر."""
    probe = _probe()
    probe.observe(DECISION, {"trace_id": "مجهول"}, at=5.0)
    snap = probe.snapshot()
    assert snap["orphan_decisions"] == 1
    assert snap["closed"] == 0
    assert snap["symbols"] == {}, "دخل قرارٌ يتيم في العيّنة"


def test_a_tick_that_never_decided_is_forgotten_and_counted() -> None:
    probe = _probe(expiry_s=5.0)
    probe.observe(TICK, {"trace_id": "T", "symbol": "USTEC"}, at=0.0)
    probe.observe(TICK, {"trace_id": "U", "symbol": "USTEC"}, at=100.0)  # يُشغّل الكنس
    snap = probe.snapshot()
    assert snap["expired"] >= 1, snap
    assert snap["closed"] == 0


def test_a_payload_without_a_trace_is_ignored_silently() -> None:
    probe = _probe()
    probe.observe(TICK, {"symbol": "USTEC"}, at=1.0)
    probe.observe(DECISION, {}, at=2.0)
    assert probe.snapshot()["opened"] == 0


def test_a_non_dict_payload_never_raises() -> None:
    probe = _probe()
    probe.observe(TICK, None, at=1.0)
    probe.observe(DECISION, "نصّ", at=2.0)
    assert probe.snapshot()["opened"] == 0


def test_an_unrelated_event_touches_nothing() -> None:
    probe = _probe()
    probe.observe("storage.decisions_saved", {"trace_id": "X"}, at=1.0)
    assert probe.snapshot()["opened"] == 0


def test_the_first_tick_of_a_trace_is_the_start() -> None:
    """تِكّتان بالأثر نفسه: البداية أوّلهما، وإلّا قِيس جزءُ الطريق."""
    probe = _probe()
    probe.observe(TICK, {"trace_id": "T", "symbol": "USTEC"}, at=10.0)
    probe.observe(TICK, {"trace_id": "T", "symbol": "USTEC"}, at=10.5)
    probe.observe(DECISION, {"trace_id": "T"}, at=11.0)
    assert probe.snapshot()["symbols"]["USTEC"]["p50_s"] == pytest.approx(1.0, abs=1e-3)


# ── حدود الذاكرة معلنة ──────────────────────────────────────────────────

def test_the_open_map_is_capped_and_the_overflow_is_counted() -> None:
    """خريطة بلا سقف تسريبٌ صامت في عملية تعمل أيامًا."""
    probe = _probe(max_open=4, expiry_s=10_000.0)
    for index in range(10):
        probe.observe(TICK, {"trace_id": "T%d" % index, "symbol": "USTEC"}, at=1.0)
    snap = probe.snapshot()
    assert snap["open_now"] <= 4
    assert snap["overflow"] >= 1, "تجاوز السقف بلا عدّ"


def test_the_sample_window_slides_and_is_reported() -> None:
    """§ الموازنة: مئينٌ على ماضٍ ميت يحكم على ما انتهى."""
    probe = _probe(sample_cap=8)
    for index in range(30):
        _pair(probe, "T%d" % index, "USTEC", 0.005, t0=100.0 + index)
    snap = probe.snapshot()["symbols"]["USTEC"]
    assert snap["samples"] == 8, "النافذة لم تنزلق"
    assert "window_s" in snap


# ── ⛔ النافذة تصف ما في اليد لا عمر التشغيلة ───────────────────────────
#
# **العطب المقيس على النواة الحيّة ٢٠٢٦-٠٩-١٠:** كان `_window_start` يُضبط
# مرّةً عند أوّل عيّنة ثمّ «يُحدَّث» بـ`now - self._span(symbol)` — و`_span`
# هو `now - _window_start` نفسه، فالسطر يُسند القيمة إلى ذاتها. **عمليّةٌ
# لاغية.** فقرأتُ على النواة الحيّة:
#
#     window_s = 3,633 ث   بينما الصندوق يحمل آخر 4,096 عيّنة (~400 ث)
#
# والأداة كانت صادقةً في **قيمة** المئين كاذبةً في **مداه** — فحسبتُ أنّ
# `p99 = 10.79` يصف ساعةً كاملة، وهو يصف سبع دقائق فيها نوبةٌ واحدة.
# ورقمٌ بمدًى كاذب يرسل القارئ إلى حكمٍ خاطئ بثقةٍ كاملة.
#
# وسبعة عشر اختبارًا خضراء لم تكشفه: أقربها فحص `"window_s" in snap` —
# فحص **وجود المفتاح** لا قيمته. الحرّاس أدناه يفحصون القيمة.

def test_the_window_describes_the_retained_samples_not_the_whole_run() -> None:
    """⛔ الحارس الذي كان غائبًا: قيمة النافذة لا وجود مفتاحها."""
    probe = _probe(sample_cap=8)
    for index in range(200):                      # 200 عيّنة، صندوقٌ يسع 8
        _pair(probe, "T%d" % index, "USTEC", 0.005, t0=100.0 + index)
    snap = probe.snapshot(at=300.0)["symbols"]["USTEC"]
    assert snap["samples"] == 8
    # أقدم عيّنةٍ باقية أُغلقت عند 100 + 192 + 0.005 ≈ 292.005
    assert snap["window_s"] < 20.0, (
        "النافذة تصف عمر التشغيلة لا العيّنات الباقية: %s" % snap["window_s"])


def test_the_window_stops_growing_once_the_bucket_is_full() -> None:
    """النموّ الأبديّ هو عرَض العطب — يُقاس على بُعدٍ زمنيّ **واحد**.

    ⚠️ ووقعتُ في الفخّ وأنا أكتب الحارس: قارنتُ أوّلًا لقطةً عند 200 بأخرى
    عند 400 فرأيتُ «نموًّا» ليس نموًّا — بُعدُ المراقبة تحرّك 200 ثانية
    والعيّنات 192. المقارنة العادلة تُقاس من آخر عيّنةٍ في الحالتين.
    """
    probe = _probe(sample_cap=8)
    for index in range(8):
        _pair(probe, "A%d" % index, "USTEC", 0.005, t0=100.0 + index)
    first = probe.snapshot(at=108.0)["symbols"]["USTEC"]["window_s"]
    for index in range(100):                      # مئة عيّنة أخرى تُزيح ما قبلها
        _pair(probe, "B%d" % index, "USTEC", 0.005, t0=200.0 + index)
    second = probe.snapshot(at=300.0)["symbols"]["USTEC"]["window_s"]
    assert second <= first + 0.1, (
        "النافذة نمت رغم إزاحة العيّنات: %.1f ⟵ %.1f" % (first, second))
    assert second < 12.0, "النافذة ما زالت تحمل ما أُزيح: %.1f" % second


def test_a_quiet_symbol_shows_its_window_growing() -> None:
    """والعكس صحيحٌ أيضًا: رمزٌ صمت يجب أن يُظهر نافذةً تتّسع.

    وإلّا بدا قياسٌ عمره ساعة كأنّه لحظيّ — وهو الكذب المقابل.
    """
    probe = _probe(sample_cap=8)
    _pair(probe, "T", "USTEC", 0.005, t0=100.0)
    near = probe.snapshot(at=110.0)["symbols"]["USTEC"]["window_s"]
    far = probe.snapshot(at=700.0)["symbols"]["USTEC"]["window_s"]
    assert near < 11.0 and far > 500.0, (near, far)


def test_the_breach_count_has_a_windowed_twin_that_can_be_divided() -> None:
    """⛔ عدّادان بمرجعين مختلفين أعطياني نسبةً مستحيلة.

    قرأتُ حيًّا `over_limit = 40,060` مقابل `samples = 32,126` فحسبتُ
    **124.7%** — وهو ليس خطأً في العدّ بل في القسمة: التراكميّ منذ الإقلاع
    لا يُقسَم على نافذة. فصار للنافذة عدّادها.
    """
    probe = _probe(limit_s=0.1, sample_cap=8)
    for index in range(50):
        _pair(probe, "S%d" % index, "USTEC", 0.5, t0=100.0 + index)
    snap = probe.snapshot(at=200.0)["symbols"]["USTEC"]
    assert snap["over_limit"] == 50, "التراكميّ يجب أن يعدّ الخمسين كلّها"
    assert snap["over_limit_window"] <= snap["samples"], (
        "عدّاد النافذة تجاوز عيّناتها — مرجعان مختلطان من جديد")
    assert snap["over_limit_window"] == 8


def test_a_clean_window_reports_zero_breaches_in_it() -> None:
    """والتراكميّ يبقى شاهدًا على ما مضى ولا يُمحى."""
    probe = _probe(limit_s=0.1, sample_cap=8)
    for index in range(8):
        _pair(probe, "BAD%d" % index, "USTEC", 0.5, t0=100.0 + index)
    for index in range(8):
        _pair(probe, "OK%d" % index, "USTEC", 0.01, t0=200.0 + index)
    snap = probe.snapshot(at=300.0)["symbols"]["USTEC"]
    assert snap["over_limit_window"] == 0, "النافذة نظيفة ومع ذلك تُبلّغ خرقًا"
    assert snap["over_limit"] == 8, "التراكميّ نسي ما وقع فعلًا"


# ── العرض لا يكذب ───────────────────────────────────────────────────────

def test_every_number_carries_its_sample_and_limit() -> None:
    probe = _probe()
    _pair(probe, "T", "USTEC", 0.03)
    entry = probe.snapshot()["symbols"]["USTEC"]
    for field in ("samples", "window_s", "p50_s", "p95_s", "p99_s",
                  "max_s", "limit_s", "over_limit"):
        assert field in entry, field


def test_no_samples_means_no_symbol_row_at_all() -> None:
    """صفر عيّنة لا يُعرض صفرَ زمن — لا يُعرض أصلًا."""
    assert _probe().snapshot()["symbols"] == {}


def test_breaches_are_counted_against_the_declared_limit() -> None:
    probe = _probe(limit_s=0.1)
    for index in range(5):
        _pair(probe, "ok%d" % index, "USTEC", 0.05, t0=100.0 + index)
    for index in range(3):
        _pair(probe, "bad%d" % index, "USTEC", 0.25, t0=200.0 + index)
    entry = probe.snapshot()["symbols"]["USTEC"]
    assert entry["over_limit"] == 3
    assert entry["limit_s"] == 0.1
    assert entry["max_s"] == pytest.approx(0.25, abs=1e-3)


# ── الوصل بالناقل الحيّ — بلا لمس النواة المختومة ───────────────────────

def test_the_bus_measures_tick_to_decision_without_a_core_change() -> None:
    """الأثر يورَّث من الأب للابن أصلًا، فيكفي قراءته من مرور الأحداث."""
    import asyncio

    from transport.owned_event_bus import OwnedEventBus

    async def run() -> dict:
        bus = OwnedEventBus()
        seen: list = []

        async def decide(payload: dict) -> None:
            # الابن يرث `trace_id` من الأب داخل الناقل نفسه.
            await bus.publish(DECISION, {"symbol": payload.get("symbol")},
                              publisher="اختبار")
            seen.append(payload.get("symbol"))

        bus.subscribe(TICK, decide, subscriber="قرار")
        for index in range(6):
            await bus.publish(TICK, {"symbol": "USTEC", "sequence": index},
                              publisher="تغذية")
        await bus.drain(timeout_s=10.0)
        stats = bus.transport_stats()
        await bus.close()
        return stats

    stats = asyncio.run(run())
    latency = stats["latency"]
    assert latency["opened"] >= 6, latency
    assert "limit_s" in latency and latency["limit_s"] > 0
    # قد لا يُغلق كلّ أثر داخل مهلة الاختبار، لكن ما أُغلق يُعرض بعيّنته.
    for entry in latency["symbols"].values():
        assert entry["samples"] > 0
        assert entry["window_s"] >= 0


def test_a_slow_subscriber_is_named_not_just_its_event() -> None:
    """§٢٤ — النواة تعدّ التجاوز باسم الحدث، وهذا يسمّي **مَن** أبطأه.

    حدثٌ واحد يصل خمسة مشترِكين: عدّادٌ باسم الحدث يتّهم الحدث، ويترك
    الأربعة الأبرياء والمذنب في سلّة واحدة.
    """
    import asyncio

    from transport.owned_event_bus import OwnedEventBus

    async def run() -> dict:
        bus = OwnedEventBus()

        async def slow(_payload: dict) -> None:
            await asyncio.sleep(0.08)          # فوق ميزانية 0.05

        async def quick(_payload: dict) -> None:
            return None

        bus.subscribe(TICK, slow, subscriber="المشترك_البطيء")
        bus.subscribe(TICK, quick, subscriber="المشترك_السريع")
        for _ in range(3):
            await bus.publish(TICK, {"symbol": "USTEC"}, publisher="تغذية")
        await bus.drain(timeout_s=15.0)
        stats = bus.transport_stats()
        await bus.close()
        return stats

    stats = asyncio.run(run())
    overrun = stats["overrun_by_subscriber"]
    assert overrun.get("المشترك_البطيء", 0) >= 1, overrun
    assert overrun.get("المشترك_السريع", 0) == 0, (
        "اتُّهم المشترك السريع: %s" % overrun)
    assert stats["overrun_worst_by_subscriber"]["المشترك_البطيء"] >= 0.05
    assert stats["overrun_budget_s"] == 0.05, "الميزانية لا تطابق ميزانية النواة"


def test_closing_the_bus_also_shuts_down_its_thread_pools() -> None:
    """⛔ عطبٌ قِسته: التجاوز كان يُسقط تنظيف الأب.

    `EventBus.close()` **متزامنة** وتُغلق `_realtime_executor` و
    `_handler_executor`، و`OwnedEventBus.close()` كانت `async def` ولا
    تناديها — فكلّ ناقل يترك بِركتَي خيوطٍ حيّتين.

    وثمنه: مجموعة الاختبارات صارت ٣ فشل بدل ٢ بعد إضافة اختباراتٍ تبني
    نواقل، والساقط `test_ctrader_622_contract…` يمرّ وحده. خيوطٌ متراكمة
    تُزعزع اختبارًا حسّاسًا للزمن — واختبارٌ يُفشل جارَه أسوأ من غيابه.
    """
    import asyncio

    from transport.owned_event_bus import OwnedEventBus

    async def run() -> tuple:
        bus = OwnedEventBus()
        pools = (bus._realtime_executor, bus._handler_executor)
        await bus.close()
        return pools

    realtime, handler = asyncio.run(run())
    assert realtime._shutdown is True, "بِركة الزمن الحقيقيّ بقيت حيّة"
    assert handler._shutdown is True, "بِركة المعالجات بقيت حيّة"


def test_the_percentile_holds_at_both_ends_of_the_list() -> None:
    """⛔ طفرةٌ نجت: `upper = min(lower + 1, len - 1)` ⟵ `max` (سطر 63).

    الفرق لا يظهر إلّا عند **الطرف**: عند `fraction=1.0` يصير `lower` آخر
    فهرس، فـ`min` تُبقيه في المدى و`max` تدفعه خارجه ⟶ `IndexError`. وكلّ
    اختباراتي كانت تسأل عن 0.5 و0.95 و0.99 — أي وسط القائمة دائمًا.
    """
    ordered = [1.0, 2.0, 3.0, 4.0, 5.0]
    assert percentile(ordered, 1.0) == 5.0, "المئين المئة ليس الأكبر"
    assert percentile(ordered, 0.0) == 1.0, "المئين صفر ليس الأصغر"
    assert percentile([7.0], 1.0) == 7.0
    assert percentile([7.0], 0.0) == 7.0
    for fraction in (0.0, 0.25, 0.5, 0.75, 0.99, 1.0):
        value = percentile(ordered, fraction)
        assert ordered[0] <= value <= ordered[-1], (fraction, value)


# ── ختم المالك ٢٠٢٦-٠٩-١٨: المسبار لا يستطيع الكذب على تعريف تِكّة ← قرار ──

def test_only_the_legal_tick_event_opens_a_trace() -> None:
    """بادئة `market_data.` تفتح على اثني عشر حدثًا، منها حالاتٌ دوريّة لا
    تِكّات. فأثرٌ يفتحه حدثٌ دوريّ ويغلقه القرار يقيس انتظارًا لا معالجة —
    ولا يصلح دليلًا معماريًّا."""
    probe = _probe()
    for intruder in ("market_data.quality.state", "market_data.feed.state",
                     "market_data.calendar.state", "market_data.candle_closed",
                     "market_data.state", "market_data.depth_updated"):
        probe.observe(intruder, {"symbol": "USTEC", "trace_id": "t-%s" % intruder})
    assert probe.opened == 0, "حدثٌ ليس تِكّةً فتح أثرًا"
    probe.observe(TICK, {"symbol": "USTEC", "trace_id": "t-real"})
    assert probe.opened == 1


def test_the_default_opener_is_one_exact_name_not_a_prefix() -> None:
    from transport.latency_probe import DEFAULT_TICK_EVENTS, DEFAULT_TICK_PREFIXES
    assert DEFAULT_TICK_EVENTS == ("market_data.price_received",)
    assert DEFAULT_TICK_PREFIXES == (), "بقيت بادئةٌ تفتح الأثر"


def test_every_closed_sample_carries_its_full_identity() -> None:
    """لا يُحكم على ذيلٍ بلا عيّنته: من فتحه ومتى، ومن أغلقه ومتى."""
    probe = _probe()
    probe.observe(TICK, {"symbol": "US500", "trace_id": "t-1"})
    probe.observe("decision.dispatch.state", {"symbol": "US500", "trace_id": "t-1"})
    worst = probe.worst_samples()
    assert len(worst) == 1
    row = worst[0]
    for key in ("trace_id", "symbol", "open_event", "open_t",
                "decision_event", "decision_t", "elapsed_s"):
        assert key in row, key
    assert row["open_event"] == TICK
    assert row["trace_id"] == "t-1"
    assert row["symbol"] == "US500"
    # اسم الحدث المُغلِق جزءٌ من الهويّة التي ختمها المالك — لا يُستنتج.
    assert row["decision_event"] == "decision.dispatch.state"


def test_the_worst_list_keeps_the_slowest_and_is_bounded() -> None:
    probe = _probe()
    probe.worst_cap = 3
    for index in range(20):
        trace = "t%d" % index
        probe.observe(TICK, {"symbol": "X", "trace_id": trace})
        probe.observe("decision.room.state", {"symbol": "X", "trace_id": trace},
                      at=probe._open[trace][0] + index * 0.01)
    worst = probe.worst_samples()
    assert len(worst) == 3
    assert worst[0]["elapsed_s"] >= worst[-1]["elapsed_s"]
