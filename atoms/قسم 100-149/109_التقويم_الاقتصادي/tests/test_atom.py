import asyncio
import inspect
import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from pathlib import Path as _Path
sys.path.insert(0, str(_Path(__file__).resolve().parents[4]))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.contracts.atom import AtomContext, HealthState  # noqa: E402
import importlib.util as _ilu  # noqa: E402

_spec = _ilu.spec_from_file_location(
    "_atom109", _Path(__file__).resolve().parents[1] / "atom.py")
_mod = _ilu.module_from_spec(_spec)
sys.modules["_atom109"] = _mod
_spec.loader.exec_module(_mod)
Atom = _mod.Atom
EVENT_UPCOMING = _mod.EVENT_UPCOMING
EVENT_WINDOW = _mod.EVENT_WINDOW


class _NullLogger:
    def debug(self, *a): pass
    def info(self, *a): pass
    def warning(self, *a): pass
    def error(self, *a): pass
    def critical(self, *a): pass


class FakeEventBus:
    def __init__(self):
        self.published = []
        self._handlers = {}

    def subscribe(self, name, handler):
        self._handlers.setdefault(name, []).append(handler)

    async def publish(self, name, payload):
        self.published.append((name, payload))
        for h in self._handlers.get(name, []):
            r = h(payload)
            if inspect.isawaitable(r):
                await r

    def make_context(self):
        # الاختبارات القديمة كُتبت قبل التصفية (3.4.0)، فتُعطَّل صراحةً
        # هنا: بلا ذلك يسري افتراضيّ الكود — وهو نسخةُ حكم المالك — فيحكم
        # اختباراتٍ لم تُكتب له.
        return AtomContext(atom_id=109, config={"source_event": "market.calendar",
                           "alert_before_seconds": 900.0, "keep_past_seconds": 3600.0,
                           "min_impact": "LOW", "blocking_currencies": [],
                           "blocking_titles": []}, logger=_NullLogger(),
                           publish=self.publish, subscribe=self.subscribe)


async def _make(bus):
    atom = Atom()
    await atom.initialize(bus.make_context())
    await atom.start()
    return atom


async def test_announces_in_window_once():
    print("\n--- test_announces_in_window_once ---")
    bus = FakeEventBus()
    await _make(bus)
    # 3.12.0 (٢٣/١٠): القائمة الفارغة صارت «كلّ العملات» وحدثٌ بلا عملة لا يحجب — فالحدث يحمل عملته.
    await bus.publish("market.calendar", {"id": "cpi", "title": "US CPI", "currency": "USD",
                      "scheduled_at": 10000.0, "impact_level": "HIGH"})
    await bus.publish("SYS_SECOND", {"official_time": 8000.0})  # 2000s away > 900 window
    assert not [p for n, p in bus.published if n == EVENT_UPCOMING], "not yet in window"
    await bus.publish("SYS_SECOND", {"official_time": 9200.0})  # 800s away, in window
    ann = [p for n, p in bus.published if n == EVENT_UPCOMING]
    assert len(ann) == 1 and ann[0]["title"] == "US CPI"
    assert abs(ann[0]["seconds_until"] - 800.0) < 1e-6, ann[0]
    win = [p for n, p in bus.published if n == EVENT_WINDOW]
    assert win and win[-1]["in_event_window"] is True
    await bus.publish("SYS_SECOND", {"official_time": 9300.0})  # still in window
    assert len([p for n, p in bus.published if n == EVENT_UPCOMING]) == 1, "announced once"
    print(f"OK — أعلن الحدث داخل النافذة مرّة (بوقت SYS_SECOND): seconds_until={ann[0]['seconds_until']}")


async def test_drops_past_events():
    print("\n--- test_drops_past_events ---")
    bus = FakeEventBus()
    atom = await _make(bus)
    await bus.publish("market.calendar", {"id": "old", "title": "Old", "scheduled_at": 100.0})
    await bus.publish("SYS_SECOND", {"official_time": 100000.0})  # far past + keep
    assert len(atom._events) == 0, "past event dropped"
    print("OK — الحدث الماضي (تجاوز keep_past) اتشال")


async def test_impact_filter():
    print("\n--- test_impact_filter ---")
    bus = FakeEventBus()
    atom = Atom()
    await atom.initialize(AtomContext(atom_id=109, config={"source_event": "market.calendar",
                          "alert_before_seconds": 900.0, "keep_past_seconds": 3600.0,
                          "min_impact": "HIGH"}, logger=_NullLogger(),
                          publish=bus.publish, subscribe=bus.subscribe))
    await atom.start()
    await bus.publish("market.calendar", {"id": "low", "title": "minor",
                      "scheduled_at": 10000.0, "impact_level": "LOW"})
    assert len(atom._events) == 0, "below min_impact dropped"
    await bus.publish("market.calendar", {"id": "hi", "title": "major",
                      "scheduled_at": 10000.0, "impact_level": "HIGH"})
    assert len(atom._events) == 1
    print("OK — مرشّح الأثر: LOW اتجاهل (min=HIGH)، HIGH اتتبّع")


async def test_health_states():
    print("\n--- test_health_states ---")
    bus = FakeEventBus()
    atom = Atom()
    await atom.initialize(bus.make_context())
    assert (await atom.health_check()).state == HealthState.UNHEALTHY
    await atom.start()
    assert (await atom.health_check()).state == HealthState.DEGRADED  # no time
    await bus.publish("SYS_SECOND", {"official_time": 100.0})
    await bus.publish("market.calendar", {"id": "x", "title": "E", "scheduled_at": 10000.0})
    assert (await atom.health_check()).state == HealthState.HEALTHY
    print("OK — الصحة: UNHEALTHY -> DEGRADED(NO_TIME) -> HEALTHY")


async def main():
    tests = [test_announces_in_window_once, test_drops_past_events, test_impact_filter,
             test_health_states]
    failed = []
    for t in tests:
        try:
            await t()
        except AssertionError as e:
            failed.append((t.__name__, str(e))); print(f"FAILED: {t.__name__}: {e}")
        except Exception as e:
            failed.append((t.__name__, repr(e))); print(f"ERROR: {t.__name__}: {e!r}")
    print("\n" + "=" * 60)
    if failed:
        print(f"فشل {len(failed)} من أصل {len(tests)}"); sys.exit(1)
    print(f"نجح كل الاختبارات ({len(tests)}/{len(tests)})")


if __name__ == "__main__":
    asyncio.run(main())


# ٢٠٢٦-٠٩-١٦ — بعد اختبار طفرات: نجت طفرتان، إحداهما تُعيد علّة
# أُصلحت في 3.2.0 بلا أن يصرخ اختبار واحد.


async def test_event_due_exactly_now_is_announced():
    """`remaining == 0` — الحدث حان وقته الآن بالضبط.

    طفرة `0 <= remaining` ← `0 < remaining` نجت: حدثٌ توقيته يطابق
    النبضة الزمنيّة تمامًا كان سيُبتلع بلا إعلان، ثمّ يُحذف بعدها
    بوصفه ماضيًا. وهذا ليس نادرًا: النبضة ثانويّة والتوقيتات مستديرة.
    """
    bus = FakeEventBus()
    await _make(bus)
    await bus.publish("market.calendar", {"id": "cpi", "title": "CPI",
                                          "scheduled_at": 1000.0,
                                          "impact_level": "HIGH"})
    await bus.publish("SYS_SECOND", {"official_time": 1000.0})   # الحدّ بالضبط
    announced = [p for n, p in bus.published if n == EVENT_UPCOMING]
    assert announced, "حدث وقته الآن يجب أن يُعلن"
    assert announced[-1]["seconds_until"] == 0.0, announced[-1]["seconds_until"]
    print("OK — الحدث الذي حان وقته الآن يُعلن")


async def test_keep_past_seconds_is_honoured_not_ignored():
    """يحرس إصلاح 3.2.0: `keep_past_seconds` يُستعمل فعلًا.

    طفرة `cutoff = self._keep_past_s` ← `cutoff = 0.0` تُعيد العلّة
    بالضبط: عيار معلَن في المانيفست ومقروء في `initialize` ثمّ
    مُتجاهَل، والحدث يُنسى لحظة مروره. نجت الطفرة من كلّ اختبار.
    """
    bus = FakeEventBus()
    atom = await _make(bus)
    await bus.publish("market.calendar", {"id": "nfp", "title": "NFP",
                                          "scheduled_at": 1000.0,
                                          "impact_level": "HIGH"})
    await bus.publish("SYS_SECOND", {"official_time": 1001.0})   # مرّ بثانية
    assert "nfp" in atom._events, "داخل نافذة keep_past — يبقى"
    await bus.publish("SYS_SECOND", {"official_time": 1000.0 + 3600.0})
    assert "nfp" in atom._events, "عند حدّ النافذة بالضبط — يبقى"
    await bus.publish("SYS_SECOND", {"official_time": 1000.0 + 3601.0})
    assert "nfp" not in atom._events, "بعد النافذة — يُحذف"
    print("OK — keep_past_seconds محترم، والحدّ نفسه داخل النافذة")

async def test_calendar_state_heartbeat_republishes_but_window_does_not():
    """الحالة تُعاد وحدثُ النافذة لا — الفرق الدلاليّ محفوظ.

    `market_data.calendar.state` كان يُنشر عند التغيّر وحده:
    `published=4` مقابل `duplicate=1088` في تشغيلة كاملة. فـ454 أُعيد
    تحميله ساخنًا اليوم فحجب 1,199 قرارًا من 1,199 بـ`calendar_unknown`.

    و`calendar_window` حدثُ **حدوث** (دخلنا نافذة أو خرجنا) — إعادته
    تكذب بأنّ شيئًا وقع، فلا يُعاد.
    """
    print("\n--- test_calendar_state_heartbeat_republishes_but_window_does_not ---")
    bus = FakeEventBus()
    atom = Atom()
    await atom.initialize(AtomContext(
        atom_id=109,
        config={"source_event": "market.calendar", "alert_before_seconds": 900.0,
                "keep_past_seconds": 3600.0, "min_impact": "LOW",
                "state_heartbeat_s": 30.0},
        logger=_NullLogger(), publish=bus.publish, subscribe=bus.subscribe))
    await atom.start()
    states = lambda: [p for n, p in bus.published if n == _mod.EVENT_STATE]
    windows = lambda: [p for n, p in bus.published if n == EVENT_WINDOW]

    await bus.publish("SYS_SECOND", {"official_time": 1000.0})   # أوّل حالة + نبضة
    s0, w0 = len(states()), len(windows())
    assert s0 >= 1 and w0 >= 1, (s0, w0)

    await bus.publish("SYS_SECOND", {"official_time": 1010.0})   # داخل النبض
    assert len(states()) == s0, "لا إعادة داخل النبض"

    await bus.publish("SYS_SECOND", {"official_time": 1031.0})   # مرّ النبض
    assert len(states()) == s0 + 1, "الحالة تُعاد"
    assert len(windows()) == w0, "حدث النافذة لا يُعاد"
    assert atom.heartbeats_sent == 1, atom.heartbeats_sent
    body = states()[-1]
    assert body["utc"] == 1031.0, "الحالة المُعادة تحمل وقتها"
    assert body["status"] == "UNKNOWN", body["status"]
    print("OK — الحالة تُعاد وحدث النافذة لا يُعاد")


async def test_calendar_zero_heartbeat_keeps_change_only():
    """صفر = السلوك قبل 3.3.0."""
    print("\n--- test_calendar_zero_heartbeat_keeps_change_only ---")
    bus = FakeEventBus()
    atom = Atom()
    await atom.initialize(AtomContext(
        atom_id=109,
        config={"source_event": "market.calendar", "alert_before_seconds": 900.0,
                "keep_past_seconds": 3600.0, "min_impact": "LOW",
                "state_heartbeat_s": 0.0},
        logger=_NullLogger(), publish=bus.publish, subscribe=bus.subscribe))
    await atom.start()
    await bus.publish("SYS_SECOND", {"official_time": 1000.0})
    n = len([p for nm, p in bus.published if nm == _mod.EVENT_STATE])
    for t in (1100.0, 1200.0, 9000.0):
        await bus.publish("SYS_SECOND", {"official_time": t})
    assert len([p for nm, p in bus.published if nm == _mod.EVENT_STATE]) == n
    assert atom.heartbeats_sent == 0
    print("OK — نبض صفر: لا إعادة")

# ٢٠٢٦-٠٩-١٦ — حكم المالك في أمرين: «نحن نشتغل على اخبار usd» ثمّ
# «بعدها بس اخبارة قوية الحمراء». وهذه الاختبارات تحرس الحكمين معًا،
# وتحرس معهما الفصل بين المعرفة والحجب.


async def _filtered(bus, currencies=("USD",), impact="HIGH"):
    atom = Atom()
    await atom.initialize(AtomContext(
        atom_id=109,
        config={"source_event": "market.calendar", "alert_before_seconds": 900.0,
                "keep_past_seconds": 3600.0, "min_impact": "LOW",
                "state_heartbeat_s": 0.0,
                "blocking_currencies": list(currencies),
                "blocking_min_impact": impact,
                # الأسماء تُعطَّل صراحةً: هذا الاختبار يفحص التصفية
                # بالأثر. وبلا تعطيلٍ صريح يسري افتراضيّ الكود ويحكم.
                "blocking_titles": []},
        logger=_NullLogger(), publish=bus.publish, subscribe=bus.subscribe))
    await atom.start()
    return atom


async def _news(bus, cur, impact, at=1000.0, ident=None):
    await bus.publish("market.calendar",
                      {"id": ident or f"{cur}-{impact}-{at}",
                       "title": f"خبر {cur}", "currency": cur,
                       "impact_level": impact, "scheduled_at": at})


def _blocked(bus):
    rows = [p for n, p in bus.published if n == _mod.EVENT_STATE]
    return rows[-1]["in_event_window"] if rows else None


async def test_brazilian_low_news_no_longer_blocks_the_market():
    """الحالة التي أمر بها المالك بعينها: خبرٌ برازيليّ LOW لا يحجب.

    كان يمنع الذهب وناسداك والبتكوين ساعةً كاملة — وكلّها مقوَّمة
    بالدولار. مقيس قبل التغيير: 86 حدثًا من 138 بعملات غير الدولار.
    """
    print("\n--- test_brazilian_low_news_no_longer_blocks_the_market ---")
    bus = FakeEventBus()
    atom = await _filtered(bus)
    await _news(bus, "BRL", "LOW", at=1000.0)
    await bus.publish("SYS_SECOND", {"official_time": 900.0})   # داخل نافذة 900ث
    assert _blocked(bus) is False, "البرازيليّ لا يحجب"
    assert "BRL-LOW-1000.0" in atom._events, "ويبقى متتبَّعًا — المعرفة لا تُحذف"
    print("OK — الخبر البرازيليّ يُعرف ولا يحجب")


async def test_usd_red_news_blocks():
    """أخبار الدولار الحمراء تحجب — وهو المقصود."""
    print("\n--- test_usd_red_news_blocks ---")
    bus = FakeEventBus()
    await _filtered(bus)
    await _news(bus, "USD", "HIGH", at=1000.0)
    await bus.publish("SYS_SECOND", {"official_time": 900.0})
    assert _blocked(bus) is True, "الأحمر الأمريكيّ يحجب"
    print("OK — USD/HIGH يحجب")


async def test_usd_but_not_red_does_not_block():
    """أمر المالك الثاني: «بس اخبارة قوية الحمراء» — فـLOW أمريكيّ لا يحجب."""
    print("\n--- test_usd_but_not_red_does_not_block ---")
    bus = FakeEventBus()
    atom = await _filtered(bus)
    await _news(bus, "USD", "LOW", at=1000.0)
    await _news(bus, "USD", "MEDIUM", at=1001.0)
    await bus.publish("SYS_SECOND", {"official_time": 900.0})
    assert _blocked(bus) is False, "الدولار غير الأحمر لا يحجب"
    assert len(atom._events) == 2, "ويبقى متتبَّعًا"
    assert atom.non_blocking_tracked == 2 and atom.blocking_tracked == 0
    print("OK — USD/LOW و USD/MEDIUM يُعرفان ولا يحجبان")


async def test_both_filters_must_pass_together():
    """العملة **و** الأثر — لا أحدهما. أربع توليفات في اختبار واحد."""
    print("\n--- test_both_filters_must_pass_together ---")
    for cur, impact, should_block in (("USD", "HIGH", True),
                                      ("USD", "LOW", False),
                                      ("EUR", "HIGH", False),
                                      ("EUR", "LOW", False)):
        bus = FakeEventBus()
        await _filtered(bus)
        await _news(bus, cur, impact, at=1000.0)
        await bus.publish("SYS_SECOND", {"official_time": 900.0})
        assert _blocked(bus) is should_block, (cur, impact, _blocked(bus))
    print("OK — الحجب يحتاج العملة والأثر معًا")


async def test_empty_filters_restore_previous_behaviour():
    """قائمة فارغة وأثر فارغ = كلّ العملات وكلّ الآثار — باب الرجعة."""
    print("\n--- test_empty_filters_restore_previous_behaviour ---")
    bus = FakeEventBus()
    await _filtered(bus, currencies=(), impact="")
    await _news(bus, "BRL", "LOW", at=1000.0)
    await bus.publish("SYS_SECOND", {"official_time": 900.0})
    assert _blocked(bus) is True, "بلا عيارين يحجب كلّ شيء كما قبل 3.4.0"
    print("OK — العيارات الفارغة تُعيد السلوك السابق")


async def test_missing_currency_does_not_block_but_is_counted():
    """حدثٌ بلا عملة لا يحجب — وإغلاق السوق على مجهول أسوأ من تفويته.

    ولا يُكتم: العدّاد معلن في رسالة الصحّة كي يُرى إن صار كثيرًا.
    (مقيس على لقطة اليوم: صفر حدثٍ بلا عملة من 138.)
    """
    print("\n--- test_missing_currency_does_not_block_but_is_counted ---")
    bus = FakeEventBus()
    atom = await _filtered(bus)
    await bus.publish("market.calendar", {"id": "x", "title": "بلا عملة",
                                          "impact_level": "HIGH",
                                          "scheduled_at": 1000.0})
    await bus.publish("SYS_SECOND", {"official_time": 900.0})
    assert _blocked(bus) is False, "المجهول لا يحجب"
    assert atom.unknown_currency_tracked == 1
    health = await atom.health_check()
    assert "بلا عملة=1" in health.message, health.message
    print("OK — بلا عملة: لا يحجب ويُعدّ ويُعلَن")


async def test_unknown_impact_on_blocking_currency_does_block():
    """أثرٌ مجهول بعملةٍ حاجبة **يحجب** — الكتم هنا أخطر من الحجب.

    خبر دولارٍ لم يُصنَّف قد يكون أحمر، فيُعامل معاملة الأحمر.
    """
    print("\n--- test_unknown_impact_on_blocking_currency_does_block ---")
    bus = FakeEventBus()
    await _filtered(bus)
    await bus.publish("market.calendar", {"id": "u", "title": "غير مصنّف",
                                          "currency": "USD",
                                          "impact_level": "???",
                                          "scheduled_at": 1000.0})
    await bus.publish("SYS_SECOND", {"official_time": 900.0})
    assert _blocked(bus) is True, "المجهول بعملة حاجبة يحجب"
    print("OK — أثر مجهول بعملة حاجبة يحجب")


async def test_blocking_rule_is_declared_in_state_and_health():
    """من يرى الحجب يرى بأيّ قاعدةٍ حُجب — لا رقمًا بلا سبب."""
    print("\n--- test_blocking_rule_is_declared_in_state_and_health ---")
    bus = FakeEventBus()
    atom = await _filtered(bus)
    await _news(bus, "USD", "HIGH", at=1000.0)
    await _news(bus, "BRL", "LOW", at=1001.0)
    await bus.publish("SYS_SECOND", {"official_time": 900.0})
    body = [p for n, p in bus.published if n == _mod.EVENT_STATE][-1]
    assert body["blocking_currencies"] == ["USD"], body
    assert body["blocking_min_impact"] == "HIGH", body
    health = await atom.health_check()
    assert "يحجب USD/HIGH (1 من 2)" in health.message, health.message
    print("OK — القاعدة معلنة في الحالة وفي رسالة الصحّة")

async def test_restore_recounts_the_blocking_split():
    """الاستعادة تُعيد قسمة الحاجب/غير الحاجب — لا تتركها صفرًا.

    العدّادات تُحسب في `_on_calendar`، والاستعادة تملأ `_events` مباشرة
    فتتجاوزه. ظهر ذلك حيًّا لحظة نشر 3.4.0: رسالة الصحّة قالت
    `tracked=138 · يحجب USD/HIGH (0 من 0)` — عدّادٌ يناقض جاره على
    السطر نفسه.
    """
    print("\n--- test_restore_recounts_the_blocking_split ---")
    bus = FakeEventBus()
    atom = await _filtered(bus)
    await atom.restore({"events": [
        {"id": "a", "title": "أمريكيّ أحمر", "currency": "USD",
         "impact_level": "HIGH", "scheduled_at": 1000.0},
        {"id": "b", "title": "أمريكيّ منخفض", "currency": "USD",
         "impact_level": "LOW", "scheduled_at": 1001.0},
        {"id": "c", "title": "برازيليّ", "currency": "BRL",
         "impact_level": "HIGH", "scheduled_at": 1002.0},
        {"id": "d", "title": "بلا عملة", "impact_level": "HIGH",
         "scheduled_at": 1003.0},
    ], "announced": [], "source_seen": True, "valid_received": 4,
        "now_utc": 900.0})
    assert len(atom._events) == 4
    assert atom.blocking_tracked == 1, atom.blocking_tracked
    assert atom.non_blocking_tracked == 3, atom.non_blocking_tracked
    assert atom.unknown_currency_tracked == 1
    health = await atom.health_check()
    assert "يحجب USD/HIGH (1 من 4)" in health.message, health.message
    assert "بلا عملة=1" in health.message, health.message
    print("OK — الاستعادة تُعيد القسمة ولا تترك عدّادًا يكذب")

# ٢٠٢٦-٠٩-١٦ (ختم NQ) — قائمة أسماء حاجبة تحلّ محلّ التصنيف.
# اعتراض المالك: «مبيعات تجزئة متوسّط وليس عالي تأثير» · «مخزن نفط خام
# على النفط مو على ناسدك». وتصنيف مصدرنا يخالف ForexFactory في خمسة من
# سبعة، واثنان مقلوبان.

_FOMC_TITLES = ["قرار سعر فائدة", "بيان اللجنة الفيدرالية",
                "التوقعات الاقتصادية للجنة", "المؤتمر الصحفي للجنة"]


async def _by_titles(bus, titles=None, impact=""):
    atom = Atom()
    await atom.initialize(AtomContext(
        atom_id=109,
        config={"source_event": "market.calendar", "alert_before_seconds": 900.0,
                "keep_past_seconds": 900.0, "min_impact": "LOW",
                "state_heartbeat_s": 0.0, "blocking_currencies": ["USD"],
                "blocking_min_impact": impact,
                "blocking_titles": _FOMC_TITLES if titles is None else titles},
        logger=_NullLogger(), publish=bus.publish, subscribe=bus.subscribe))
    await atom.start()
    return atom


async def _titled(bus, title, impact, cur="USD", at=1000.0, ident=None):
    await bus.publish("market.calendar", {"id": ident or title[:20] + str(at),
                                          "title": title, "currency": cur,
                                          "impact_level": impact,
                                          "scheduled_at": at})


async def test_medium_fomc_events_still_block():
    """«بيان اللجنة» و«التوقّعات» MEDIUM عندنا و High عند ForexFactory.

    وهذا سبب أن تكون الأسماء **بديلًا** لا إضافة: لو طُبّق التصنيف
    معها لسقط هذان، وهما من أعنف ما يحرّك الذهب وناسداك.
    """
    print("\n--- test_medium_fomc_events_still_block ---")
    for title in ("بيان اللجنة الفيدرالية للسوق المفتوحة",
                  "التوقعات الاقتصادية للجنة الفيدرالية للسوق المفتوحة"):
        bus = FakeEventBus()
        await _by_titles(bus)
        await _titled(bus, title, "MEDIUM", at=1000.0)
        await bus.publish("SYS_SECOND", {"official_time": 900.0})
        assert _blocked(bus) is True, (title, "MEDIUM يجب أن يحجب بالاسم")
    print("OK — بيان اللجنة وتوقّعاتها يحجبان رغم MEDIUM")


async def test_owner_objections_no_longer_block():
    """اعتراضا المالك بعينهما: مبيعات التجزئة ومخزون النفط.

    كلاهما `HIGH` في مصدرنا — ولو بقي التصنيف أساسًا للحجب لبقيا
    يحجبان. مخزون النفط `Low` عند ForexFactory.
    """
    print("\n--- test_owner_objections_no_longer_block ---")
    for title in ("مبيعات التجزئة على أساس شهري",
                  "مبيعات التجزئة الأساسية على أساس شهري",
                  "التغيير في مخزون النفط الخام لإدارة معلومات الطاقة"):
        bus = FakeEventBus()
        await _by_titles(bus)
        await _titled(bus, title, "HIGH", at=1000.0)
        await bus.publish("SYS_SECOND", {"official_time": 900.0})
        assert _blocked(bus) is False, (title, "HIGH عندنا لكنّه لا يحجب بالاسم")
    print("OK — مبيعات التجزئة ومخزون النفط لم يعودا يحجبان")


async def test_philadelphia_events_are_not_caught_by_fomc_patterns():
    """ستّة أحداث تحمل «الاحتياطي الفيدرالي» ولا يلتقطها نمط.

    المطابقة بالاحتواء تُغري بالتقاط ما لا يُقصد — فحُرِست.
    """
    print("\n--- test_philadelphia_events_are_not_caught_by_fomc_patterns ---")
    for title in ("مؤشر فيلادلفيا التصنيعي لبنك الإحتياطي الفيدرالي",
                  "توظيف فيلادلفيا لبنك الإحتياطي الفيدرالي",
                  "ظروف أعمال فيلادلفيا لبنك الإحتياطي الفيدرالي",
                  "الأسعار المدفوعة لفيلادلفيا لبنك الإحتياطي الفيدرالي",
                  "الطلبيات الجديدة لفيلادلفيا لبنك الإحتياطي الفيدرالي",
                  "مؤشر كابيكس فيلادلفيا لبنك الإحتياطي الفيدرالي"):
        bus = FakeEventBus()
        await _by_titles(bus)
        await _titled(bus, title, "HIGH", at=1000.0)
        await bus.publish("SYS_SECOND", {"official_time": 900.0})
        assert _blocked(bus) is False, (title, "فيلادلفيا لا تُلتقط")
    print("OK — أحداث فيلادلفيا الستّة لا يلتقطها نمط")


async def test_titles_replace_impact_they_do_not_add_to_it():
    """الأسماء بديل لا إضافة: حدثٌ باسمٍ حاجب وتصنيفٍ منخفض **يحجب**."""
    print("\n--- test_titles_replace_impact_they_do_not_add_to_it ---")
    bus = FakeEventBus()
    await _by_titles(bus, impact="HIGH")      # التصنيف موجود ويجب تجاهله
    await _titled(bus, "قرار سعر فائدة بنك الإحتياطي الفيدرالي", "LOW", at=1000.0)
    await bus.publish("SYS_SECOND", {"official_time": 900.0})
    assert _blocked(bus) is True, "الاسم يحكم ولو كان التصنيف منخفضًا"
    print("OK — الاسم يتقدّم على التصنيف")


async def test_currency_still_gates_before_title():
    """العملة تبقى شرطًا أوّل: اسمٌ حاجب بعملةٍ غير حاجبة لا يحجب."""
    print("\n--- test_currency_still_gates_before_title ---")
    bus = FakeEventBus()
    await _by_titles(bus)
    await _titled(bus, "قرار سعر فائدة المركزيّ الأوروبيّ", "HIGH",
                  cur="EUR", at=1000.0)
    await bus.publish("SYS_SECOND", {"official_time": 900.0})
    assert _blocked(bus) is False, "العملة تُصفّي قبل الاسم"
    print("OK — العملة شرطٌ سابق للاسم")


async def test_empty_titles_fall_back_to_impact():
    """قائمة أسماء فارغة = يعود التصنيف حكمًا — باب الرجعة."""
    print("\n--- test_empty_titles_fall_back_to_impact ---")
    bus = FakeEventBus()
    await _by_titles(bus, titles=[], impact="HIGH")
    await _titled(bus, "مبيعات التجزئة على أساس شهري", "HIGH", at=1000.0)
    await bus.publish("SYS_SECOND", {"official_time": 900.0})
    assert _blocked(bus) is True, "بلا أسماء يعود التصنيف"
    print("OK — الأسماء الفارغة تُعيد حكم التصنيف")

_FOMC_BILINGUAL = _FOMC_TITLES + ["Federal Funds Rate", "FOMC Statement",
                                  "FOMC Economic Projections",
                                  "FOMC Press Conference"]


async def test_english_titles_block_when_source_switches():
    """616 v1.6.0 صار يُفضّل ForexFactory وعناوينه إنجليزيّة.

    لو بقيت الأنماط عربيّة وحدها لانكسر الحجب **صامتًا** يوم بدّل
    المصدر — ولا شيء يصرخ: الذرّة تعمل، والعدّادات ترتفع، والبوّابة
    تُفتح على قرار الفائدة الفيدراليّ.
    """
    print("\n--- test_english_titles_block_when_source_switches ---")
    for title in ("Federal Funds Rate", "FOMC Statement",
                  "FOMC Economic Projections", "FOMC Press Conference"):
        bus = FakeEventBus()
        await _by_titles(bus, titles=_FOMC_BILINGUAL)
        await _titled(bus, title, "HIGH", at=1000.0)
        await bus.publish("SYS_SECOND", {"official_time": 900.0})
        assert _blocked(bus) is True, (title, "العنوان الإنجليزيّ يجب أن يحجب")
    print("OK — أسماء ForexFactory الأربعة تحجب")


async def test_both_languages_work_side_by_side():
    """العربيّة والإنجليزيّة معًا — لا بديلًا عن الأخرى.

    المصدر قد يسقط إلى تقويم المنصّة بعد ثمانية أيّام بلا جلب، فيعود
    العنوان عربيًّا. القائمة تغطّي الحالتين بلا تعديل كود.
    """
    print("\n--- test_both_languages_work_side_by_side ---")
    bus = FakeEventBus()
    await _by_titles(bus, titles=_FOMC_BILINGUAL)
    await _titled(bus, "قرار سعر فائدة بنك الإحتياطي الفيدرالي", "HIGH",
                  at=1000.0, ident="ar")
    await _titled(bus, "Federal Funds Rate", "HIGH", at=1000.0, ident="ff-1")
    await bus.publish("SYS_SECOND", {"official_time": 900.0})
    assert _blocked(bus) is True
    print("OK — اللغتان تعملان جنبًا إلى جنب")


async def test_english_patterns_do_not_catch_philly_fed():
    """`Philly Fed Manufacturing Index` لا يلتقطه نمط — نظير فيلادلفيا العربيّ."""
    print("\n--- test_english_patterns_do_not_catch_philly_fed ---")
    for title in ("Philly Fed Manufacturing Index", "Philly Fed Employment",
                  "FOMC Member Speaks", "Fed Chair Powell Testifies"):
        bus = FakeEventBus()
        await _by_titles(bus, titles=_FOMC_BILINGUAL)
        await _titled(bus, title, "HIGH", at=1000.0)
        await bus.publish("SYS_SECOND", {"official_time": 900.0})
        assert _blocked(bus) is False, (title, "لا يُلتقط")
    print("OK — فيلادلفيا وخطابات الأعضاء لا تُلتقط بالإنجليزيّة")


async def test_dual_source_duplicates_do_not_widen_the_window():
    """الحدث الواحد من مصدرين يحجب نافذةً واحدة لا نافذتين.

    مقيس على لقطة الذرّة: 189 حدثًا من مصدرين، والأنماط الثمانية
    تلتقط ثمانية أحداث — كلّها في 21:00 و21:30. فالازدواج يضخّم
    `tracked` ولا يوسّع الحجب دقيقةً.
    """
    print("\n--- test_dual_source_duplicates_do_not_widen_the_window ---")
    bus = FakeEventBus()
    atom = await _by_titles(bus, titles=_FOMC_BILINGUAL)
    await _titled(bus, "قرار سعر فائدة بنك الإحتياطي الفيدرالي", "HIGH",
                  at=2000.0, ident="ar-1")
    await _titled(bus, "Federal Funds Rate", "HIGH", at=2000.0, ident="ff-1")
    # النافذة تبدأ عند `scheduled - alert_before` بالضبط = 1100،
    # وتنتهي عند `scheduled + keep_past` = 2900. والحدّان داخلها.
    await bus.publish("SYS_SECOND", {"official_time": 1099.0})   # قبلها بثانية
    assert _blocked(bus) is False, "خارج النافذة: مفتوح"
    await bus.publish("SYS_SECOND", {"official_time": 1100.0})   # الحدّ نفسه
    assert _blocked(bus) is True, "بداية النافذة بالضبط: محجوب"
    await bus.publish("SYS_SECOND", {"official_time": 2900.0})   # الحدّ الآخر
    assert _blocked(bus) is True, "آخر النافذة بالضبط: ما زال محجوبًا"
    await bus.publish("SYS_SECOND", {"official_time": 2901.0})   # بعدها بثانية
    assert _blocked(bus) is False, "النافذة تُغلق في موعدها رغم الازدواج"
    assert atom.blocking_tracked == 2, "حدثان محسوبان"
    print("OK — نسختا الحدث تحجبان نافذةً واحدة")

async def test_window_is_closed_on_both_sides_of_the_event():
    """«15 دقيقة قبل خبر **وبعد** خبر» — النصفان معًا.

    كان الشرط `0 <= remaining` فينتهي الحجب في لحظة وقوع الخبر، بينما
    أعنف دقائق السوق هي التي **تلي** الإعلان. و`keep_past_seconds` كان
    يُبقي الحدث في الذاكرة ولا يحجب به — فنصف أمر المالك لم يكن منفَّذًا،
    ولا عدّاد يكشفه.

    الحدث عند 2000 · قبل 900 · بعد 900 ⇒ النافذة [1100 , 2900].
    """
    print("\n--- test_window_is_closed_on_both_sides_of_the_event ---")
    bus = FakeEventBus()
    await _by_titles(bus, titles=_FOMC_BILINGUAL)
    await _titled(bus, "Federal Funds Rate", "HIGH", at=2000.0, ident="ff-x")
    for now, expected, why in ((1099.0, False, "قبل النافذة بثانية"),
                               (1100.0, True,  "بداية النافذة بالضبط"),
                               (2000.0, True,  "لحظة الخبر"),
                               (2001.0, True,  "بعد الخبر بثانية — النصف المنسيّ"),
                               (2899.0, True,  "قبل نهايتها بثانية"),
                               (2900.0, True,  "نهايتها بالضبط"),
                               (2901.0, False, "بعدها بثانية")):
        await bus.publish("SYS_SECOND", {"official_time": now})
        assert _blocked(bus) is expected, (now, why, _blocked(bus))
    print("OK — النافذة مغلقة الطرفين: قبل الخبر وبعده")

async def test_each_side_uses_its_own_dial():
    """جانب «قبل» عياره و«بعد» عياره — لا يتبادلان.

    طفرة نجت من كلّ اختباراتي: استبدال `keep_past_s` بـ`alert_before_s`
    في حدّ النافذة الخلفيّ. لم يكشفها شيء لأنّ العيارين متساويان (900)
    في كلّ إعداداتي — فقيمتان متطابقتان لا تفرّقان بين مرجعين.

    هنا: قبل = 900 · بعد = 300. فالنافذة [1100 , 2300] لا [1100 , 2900].
    """
    print("\n--- test_each_side_uses_its_own_dial ---")
    bus = FakeEventBus()
    atom = Atom()
    await atom.initialize(AtomContext(
        atom_id=109,
        config={"source_event": "market.calendar", "alert_before_seconds": 900.0,
                "keep_past_seconds": 300.0, "min_impact": "LOW",
                "state_heartbeat_s": 0.0, "blocking_currencies": ["USD"],
                "blocking_min_impact": "", "blocking_titles": _FOMC_BILINGUAL},
        logger=_NullLogger(), publish=bus.publish, subscribe=bus.subscribe))
    await atom.start()
    await _titled(bus, "Federal Funds Rate", "HIGH", at=2000.0, ident="ff-y")
    for now, expected, why in ((1099.0, False, "قبل بـ901 — خارج"),
                               (1100.0, True,  "قبل بـ900 — الحدّ الأماميّ"),
                               (2300.0, True,  "بعد بـ300 — الحدّ الخلفيّ"),
                               (2301.0, False, "بعد بـ301 — خارج"),
                               (2899.0, False, "لو استُعمل عيار «قبل» لكان محجوبًا")):
        await bus.publish("SYS_SECOND", {"official_time": now})
        assert _blocked(bus) is expected, (now, why, _blocked(bus))
    print("OK — كل جانب بعياره: 900 أمامًا و300 خلفًا")

async def test_defaults_carry_the_owner_ruling_when_config_never_arrives():
    """حكم المالك يسري ولو لم يبلغ `config` الذرّة الحيّة.

    مقيس ٢٠٢٦-٠٩-١٦ من مصدرين: `atom.py` يُعاد تحميله ساخنًا فور حفظه،
    و**`config` من المانيفست لا يصل بلا إقلاع**. فبقيت الذرّة تحجب بكلّ
    أخبار الدولار (78 من 241) بينما المالك ختم أن يحجب الفيدراليّ وحده
    — أمرٌ نُفِّذ على القرص ولم يبلغ السوق.

    فالافتراضيّ نسخةٌ من حكمه، ولا يكذب: رسالة الصحّة تقول «افتراضيّ».
    """
    print("\n--- test_defaults_carry_the_owner_ruling_when_config_never_arrives ---")
    bus = FakeEventBus()
    atom = Atom()
    await atom.initialize(AtomContext(
        atom_id=109,
        config={"source_event": "market.calendar", "alert_before_seconds": 900.0,
                "keep_past_seconds": 900.0, "min_impact": "LOW"},   # بلا عيارَي الحجب
        logger=_NullLogger(), publish=bus.publish, subscribe=bus.subscribe))
    await atom.start()
    assert atom._using_default_currencies and atom._using_default_titles
    assert atom._blocking_currencies == frozenset({"USD"})
    assert len(atom._blocking_titles) == 8

    await _titled(bus, "Federal Funds Rate", "HIGH", at=1000.0, ident="a")
    await _titled(bus, "التغيير في مخزون النفط الخام", "HIGH", at=1001.0, ident="b")
    await bus.publish("SYS_SECOND", {"official_time": 900.0})
    assert _blocked(bus) is True, "الفيدراليّ يحجب بالافتراضيّ"

    health = await atom.health_check()
    assert "افتراضيّ" in health.message, ("لا يُكتم مصدر الحكم", health.message)
    print("OK — الافتراضيّ يحمل حكم المالك ويُعلن أنّه افتراضيّ")


async def test_explicit_empty_list_is_an_owner_choice_not_a_gap():
    """قائمة فارغة صريحة = «احجب بكلّ العملات» — لا تُدهس بالافتراضيّ.

    الفرق بين «لم يُذكر العيار» و«ذُكر فارغًا» قرارٌ لا صدفة، ولذلك
    يُفحص `in cfg` لا `.get(...) or`.
    """
    print("\n--- test_explicit_empty_list_is_an_owner_choice_not_a_gap ---")
    bus = FakeEventBus()
    atom = Atom()
    await atom.initialize(AtomContext(
        atom_id=109,
        config={"source_event": "market.calendar", "alert_before_seconds": 900.0,
                "keep_past_seconds": 900.0, "min_impact": "LOW",
                "blocking_currencies": [], "blocking_titles": []},
        logger=_NullLogger(), publish=bus.publish, subscribe=bus.subscribe))
    await atom.start()
    assert not atom._using_default_currencies and not atom._using_default_titles
    assert atom._blocking_currencies == frozenset()
    assert atom._blocking_titles == ()
    await _titled(bus, "خبر برازيليّ", "LOW", cur="BRL", at=1000.0)
    await bus.publish("SYS_SECOND", {"official_time": 900.0})
    assert _blocked(bus) is True, "بلا عيارات يحجب كلّ شيء — قرار صريح"
    health = await atom.health_check()
    # ٢٠٢٦-٠٩-١٩ — كان الفحص `"افتراضيّ" not in message` وهو خلطٌ بين
    # عيارين: قائمتا العملات والأسماء ذُكرتا صراحةً، و`require_forward_horizon`
    # لم يُذكر فيسري افتراضيّ الكود ويُعلن. فالفحص يفرّق بينهما الآن.
    assert "يحجب" not in health.message, "بلا عيارَي حجبٍ لا تُعلَن قاعدة حجب"
    assert atom._using_default_horizon is True
    assert "(يوقف الدخول عند انقضائه) [افتراضيّ]" in health.message, health.message
    print("OK — الفارغ الصريح قرارٌ محترم، والافتراضيّ يُنسب لعياره وحده")


# ٢٠٢٦-٠٩-١٨ — الأفق: إلى أين تمتدّ معرفتنا.
#
# كانت `known` تُجاب بعدّادٍ تراكميّ يُستعاد من اللقطة (مقيس 104,921)،
# فالذرّة تعلن `CLEAR` و`allow_new_entries: true` بثقةٍ كاملة ولو مات
# جسر الأخبار منذ أيّام. ومقيس يوم كتابة هذه الاختبارات: 422 حدثًا
# استُقبلت، وواحدٌ فقط أمامنا — ست عشرة ساعة ثمّ عمًى لا يقوله أحد.

_STATE_EVENT = _mod.EVENT_STATE


def _ctx109(bus, **overrides):
    config = {"source_event": "market.calendar", "alert_before_seconds": 900.0,
              "keep_past_seconds": 3600.0, "min_impact": "LOW",
              "blocking_currencies": [], "blocking_titles": []}
    config.update(overrides)
    return AtomContext(atom_id=109, config=config, logger=_NullLogger(),
                       publish=bus.publish, subscribe=bus.subscribe)


async def _atom109(bus, **overrides):
    atom = Atom()
    await atom.initialize(_ctx109(bus, **overrides))
    await atom.start()
    return atom


def _last_state(bus):
    states = [p for n, p in bus.published if n == _STATE_EVENT]
    assert states, "لا حالة منشورة"
    return states[-1]


async def test_state_carries_the_knowledge_horizon():
    """`CLEAR` لساعةٍ ليس `CLEAR` ليوم — والفرق لا يُقرأ من الحالة وحدها."""
    print("\n--- test_state_carries_the_knowledge_horizon ---")
    bus = FakeEventBus()
    await _atom109(bus)
    await bus.publish("market.calendar", {"id": "a", "title": "US CPI",
                      "scheduled_at": 50000.0, "impact_level": "HIGH"})
    await bus.publish("market.calendar", {"id": "b", "title": "ECOFIN",
                      "scheduled_at": 90000.0, "impact_level": "LOW"})
    await bus.publish("SYS_SECOND", {"official_time": 40000.0})
    state = _last_state(bus)
    assert state["horizon_utc"] == 90000.0, state
    assert state["horizon_seconds"] == 50000.0, state
    assert state["tracked"] == 2, state
    print("OK — الأفق مع الحالة: %.1f ساعة" % (state["horizon_seconds"] / 3600.0))


async def test_horizon_is_none_when_nothing_is_ahead():
    """لا حدث = `None` لا صفرًا: الصفر يُقرأ «الآن» وهو كذب."""
    print("\n--- test_horizon_is_none_when_nothing_is_ahead ---")
    bus = FakeEventBus()
    await _atom109(bus, keep_past_seconds=0.0)
    await bus.publish("market.calendar", {"id": "a", "title": "US CPI",
                      "scheduled_at": 1000.0, "impact_level": "HIGH"})
    await bus.publish("SYS_SECOND", {"official_time": 9000.0})  # مضى وقُلّم
    state = _last_state(bus)
    assert state["horizon_utc"] is None, state
    assert state["horizon_seconds"] is None, state
    assert state["tracked"] == 0, state
    print("OK — بلا حدثٍ أمامنا: الأفق None")


async def test_expired_horizon_closes_the_door_by_default():
    """**ختم NQ ٢٠٢٦-٠٩-١٩:** انقضاء الأفق يُغلق باب الدخول.

    كُتب هذا الاختبار أوّلًا ليحرس العكس — «الشارة تصفرّ والباب يبقى
    مفتوحًا» — لأنّ العيار عُرض مطفأً بانتظار حكم المالك. ثمّ ختمه،
    فانقلب المحروس: الافتراضيّ الآن **يوقف الدخول**، والشارة تصفرّ معه.
    """
    print("\n--- test_expired_horizon_closes_the_door_by_default ---")
    bus = FakeEventBus()
    atom = await _atom109(bus, keep_past_seconds=0.0)
    await bus.publish("market.calendar", {"id": "a", "title": "US CPI",
                      "scheduled_at": 1000.0, "impact_level": "HIGH"})
    await bus.publish("SYS_SECOND", {"official_time": 9000.0})
    health = await atom.health_check()
    assert health.state == HealthState.DEGRADED, health.message
    assert "أفق" in health.message, health.message
    state = _last_state(bus)
    assert state["known"] is False, state
    assert state["status"] == "UNKNOWN", state
    assert state["allow_new_entries"] is False, "لا نتداول عميانًا عن الأخبار"
    print("OK — الأفق انقضى فأُغلق الباب: " + health.message)


async def test_explicit_false_keeps_the_door_open_and_says_so():
    """والرجعة كلمةٌ في المانيفست: `false` صريحة قرارُ مالكٍ لا فراغ.

    لهذا الفحص `in cfg` لا `.get(..., افتراضيّ)` — وإلّا لدهس افتراضيّ
    الكود قرارَه ولم يبقَ له باب رجعة.
    """
    print("\n--- test_explicit_false_keeps_the_door_open_and_says_so ---")
    bus = FakeEventBus()
    atom = await _atom109(bus, keep_past_seconds=0.0,
                          require_forward_horizon=False)
    await bus.publish("market.calendar", {"id": "a", "title": "US CPI",
                      "scheduled_at": 1000.0, "impact_level": "HIGH"})
    await bus.publish("SYS_SECOND", {"official_time": 9000.0})
    assert atom._using_default_horizon is False
    state = _last_state(bus)
    assert state["status"] == "CLEAR", state
    assert state["allow_new_entries"] is True, state
    health = await atom.health_check()
    assert health.state == HealthState.DEGRADED, "الشارة تصفرّ في الحالتين"
    assert "لا يحجب — بقرارٍ صريح" in health.message, health.message
    print("OK — الباب مفتوح بقرارٍ صريح، والشارة تقوله: " + health.message)


async def test_dial_turns_an_expired_horizon_into_unknown():
    """العيار في يد المالك: انقضاء الأفق يصير `UNKNOWN` فيوقف 454 الدخول."""
    print("\n--- test_dial_turns_an_expired_horizon_into_unknown ---")
    bus = FakeEventBus()
    await _atom109(bus, keep_past_seconds=0.0, require_forward_horizon=True)
    await bus.publish("market.calendar", {"id": "a", "title": "US CPI",
                      "scheduled_at": 1000.0, "impact_level": "HIGH"})
    await bus.publish("SYS_SECOND", {"official_time": 9000.0})
    state = _last_state(bus)
    assert state["known"] is False, state
    assert state["status"] == "UNKNOWN", state
    assert state["allow_new_entries"] is False, state
    print("OK — بالعيار: UNKNOWN ودخولٌ موقوف")


async def test_dial_does_not_blind_an_atom_that_still_knows_the_future():
    """العيار لا يُطفئ المعرفة القائمة: حدثٌ أمامنا = `known` صادقة."""
    print("\n--- test_dial_does_not_blind_an_atom_that_still_knows_the_future ---")
    bus = FakeEventBus()
    await _atom109(bus, require_forward_horizon=True)
    await bus.publish("market.calendar", {"id": "a", "title": "US CPI",
                      "scheduled_at": 50000.0, "impact_level": "HIGH"})
    await bus.publish("SYS_SECOND", {"official_time": 40000.0})
    state = _last_state(bus)
    assert state["known"] is True, state
    assert state["status"] == "CLEAR", state
    print("OK — الأفق أمامنا فالمعرفة قائمة")


async def test_horizon_is_tested_at_the_moment_it_expires():
    """الحدّ يُختبر عنده: `horizon > now` لا `>=`.

    حدثٌ موعده الآن بالضبط ليس معرفةً بالمستقبل — وهو الفرق بين
    `> 0` و`>= 0` في شرط العيار.
    """
    print("\n--- test_horizon_is_tested_at_the_moment_it_expires ---")
    bus = FakeEventBus()
    atom = await _atom109(bus, keep_past_seconds=3600.0, require_forward_horizon=True)
    await bus.publish("market.calendar", {"id": "a", "title": "US CPI",
                      "scheduled_at": 1000.0, "impact_level": "HIGH"})
    await bus.publish("SYS_SECOND", {"official_time": 1000.0})  # الأفق = الآن
    state = _last_state(bus)
    assert state["horizon_seconds"] == 0.0, state
    assert state["known"] is False, "موعدٌ حلّ الآن ليس معرفةً بما بعده"
    # والشارة تقرأ الحدّ نفسه: `horizon <= now` لا `<`. الحدث ما زال
    # متتبَّعًا (`keep_past` يُبقيه ساعة) فالفرق هنا حقيقيّ لا مكافئ.
    health = await atom.health_check()
    assert health.state == HealthState.DEGRADED, health.message
    assert health.details["blind"] is True, health.details
    print("OK — الأفق عند اللحظة نفسها ليس معرفة، والشارة تقولها")


async def test_health_counts_blocking_from_tracked_not_from_a_lifetime_counter():
    """`(16 من 422)` بينما المتتبَّع حدثٌ واحد — رقمُ دورةٍ ماضية يُقرأ حالةً.

    المصدر يعيد إرسال تقويمه كاملًا، فيُقبل الماضي ويرفع العدّاد ثمّ
    يُقلَّم في الثانية التالية. العدّ الآن من `_events` وحدها.
    """
    print("\n--- test_health_counts_blocking_from_tracked_not_from_a_lifetime_counter ---")
    bus = FakeEventBus()
    atom = await _atom109(bus, keep_past_seconds=0.0,
                          blocking_currencies=["USD"], blocking_titles=[])
    for index in range(5):
        await bus.publish("market.calendar", {
            "id": "past%d" % index, "title": "US CPI", "currency": "USD",
            "scheduled_at": 1000.0 + index, "impact_level": "HIGH"})
    await bus.publish("SYS_SECOND", {"official_time": 9000.0})  # تقليم الماضي كلّه
    await bus.publish("market.calendar", {"id": "next", "title": "ECOFIN",
                      "currency": "EUR", "scheduled_at": 50000.0,
                      "impact_level": "LOW"})
    await bus.publish("SYS_SECOND", {"official_time": 9001.0})
    health = await atom.health_check()
    assert "(0 من 1)" in health.message, health.message
    assert atom.blocking_tracked == 5, "العدّاد التراكميّ يبقى للسجلّ"
    print("OK — الرسالة تعدّ المتتبَّع: " + health.message)