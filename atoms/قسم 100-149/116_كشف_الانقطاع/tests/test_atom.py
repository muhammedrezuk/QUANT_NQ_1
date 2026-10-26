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
    "_atom116", _Path(__file__).resolve().parents[1] / "atom.py")
_mod = _ilu.module_from_spec(_spec)
sys.modules["_atom116"] = _mod
_spec.loader.exec_module(_mod)
Atom = _mod.Atom
EVENT_INTERRUPTED = _mod.EVENT_INTERRUPTED
EVENT_RECOVERED = _mod.EVENT_RECOVERED
# يُقرأ من الذرّة نفسها لا يُكتب هنا: لو تغيّر المصدر المعتمد يتبعه الاختبار
ANALYST_SOURCE = _mod._ANALYST_SOURCE


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
        return AtomContext(atom_id=116, config={"max_silence_seconds": 10.0},
                           logger=_NullLogger(),
                           publish=self.publish, subscribe=self.subscribe)


async def _make(bus):
    atom = Atom()
    await atom.initialize(bus.make_context())
    await atom.start()
    return atom


def _events(bus, name):
    return [p for n, p in bus.published if n == name]


async def test_interrupt_and_recover():
    print("\n--- test_interrupt_and_recover ---")
    bus = FakeEventBus()
    await _make(bus)
    # baseline pulse + a feed tick keep it alive
    await bus.publish("SYS_SECOND", {"official_time": 100.0})
    await bus.publish(ANALYST_SOURCE, {"symbol": "NQ"})       # last_activity=100
    await bus.publish("SYS_SECOND", {"official_time": 105.0})  # 5s silence < 10 -> ok
    assert not _events(bus, EVENT_INTERRUPTED)
    await bus.publish("SYS_SECOND", {"official_time": 120.0})  # 20s silence > 10 -> interrupt
    itr = _events(bus, EVENT_INTERRUPTED)
    assert len(itr) == 1 and itr[0]["timestamp"] == 120.0, itr
    await bus.publish("SYS_SECOND", {"official_time": 121.0})  # still silent, no dup
    assert len(_events(bus, EVENT_INTERRUPTED)) == 1, "interrupt fires once"
    await bus.publish(ANALYST_SOURCE, {"symbol": "NQ"})        # activity resumes
    await bus.publish("SYS_SECOND", {"official_time": 122.0})  # recovered
    assert _events(bus, EVENT_RECOVERED), "recovery signalled"
    print("OK — كشف الانقطاع (بوقت SYS_SECOND، بلا time.time) + التعافي")


async def test_secondary_feed_does_not_mask_analyst_silence():
    """٢٠٢٦-٠٩-١٠ (ختم NQ): ميتاتريدر النابض لا يستر صمت سي‑تريدر.

    قبل 4.0.0 كان المصدران يتقاسمان عدّاد نشاط واحدًا، فهذا الاختبار
    بعينه كان يمرّ بلا انقطاع — وميتاتريدر أعلى معدّلًا (66 مقابل 24
    مقيسة ٢٠٢٦-٠٩-١٠)، فسقوط سي‑تريدر ما كان يُعلَن أبدًا.
    """
    print("\n--- test_secondary_feed_does_not_mask_analyst_silence ---")
    bus = FakeEventBus()
    atom = await _make(bus)
    await bus.publish("SYS_SECOND", {"official_time": 100.0})
    await bus.publish(ANALYST_SOURCE, {"symbol": "NQ"})       # سي‑تريدر حيّ عند 100
    # ميتاتريدر ينبض بلا انقطاع بينما سي‑تريدر صامت
    for tick in (105.0, 110.0, 115.0, 120.0):
        await bus.publish("feed.mt5.tick", {"symbol": "NQ"})
        await bus.publish("SYS_SECOND", {"official_time": tick})
    itr = _events(bus, EVENT_INTERRUPTED)
    assert itr, "صمت سي‑تريدر يجب أن يُعلَن ولو كان ميتاتريدر ينبض"
    body = itr[0]
    assert body["analyst_source"] == ANALYST_SOURCE, body
    # ميتاتريدر حديث العهد والمعتمد صامت — والفرق بينهما هو ما كان مكتومًا
    mt5_age = body["sources"]["feed.mt5.tick"]
    analyst_age = body["sources"][ANALYST_SOURCE]
    assert mt5_age <= 5.0, ("نشاط ميتاتريدر مُعلن لا مكتوم", body["sources"])
    assert analyst_age >= 10.0, body["sources"]
    assert analyst_age > mt5_age, body["sources"]
    state = await atom.health_check()
    assert state.state == HealthState.DEGRADED
    assert "ctrader" in state.message, state.message
    print("OK — ميتاتريدر لا يغطّي على صمت سي‑تريدر، وحال المصدرين معلنة")


async def test_analyst_tick_revives_immediately_without_waiting_for_clock():
    """نبضة سي‑تريدر تُحيي الحارس **فورًا** — لا عند النبضة الزمنيّة التالية.

    طفرة نجت من اختباراتي: قلب `if source == _ANALYST_SOURCE` إلى `!=`
    في `_on_feed`. لم يكشفها اختبار واحد لأنّ كلّ اختباراتي كانت تنشر
    `SYS_SECOND` بعد التِكّة، و`_on_time` يصحّح الحالة فيستر الطفرة.

    وأثرها حيّ: التعافي من انقطاع كان سيتأخّر إلى النبضة التالية
    بينما التغذية عادت فعلًا — والأسوأ أنّ نبضة **ميتاتريدر** كانت
    ستُحيي الحارس، وهو العمى نفسه الذي أُصلح في 4.0.0.
    """
    print("\n--- test_analyst_tick_revives_immediately_without_waiting_for_clock ---")
    bus = FakeEventBus()
    atom = await _make(bus)
    await bus.publish("SYS_SECOND", {"official_time": 100.0})
    await bus.publish(ANALYST_SOURCE, {"symbol": "NQ"})
    await bus.publish("SYS_SECOND", {"official_time": 130.0})   # صمت 30ث
    assert _events(bus, EVENT_INTERRUPTED), "الانقطاع يُعلن أوّلًا"
    before = len(_events(bus, EVENT_RECOVERED))

    # تِكّة ميتاتريدر وحدها: لا تُحيي — ولا نبضة زمنيّة بعدها
    await bus.publish("feed.mt5.tick", {"symbol": "NQ"})
    assert len(_events(bus, EVENT_RECOVERED)) == before, "ميتاتريدر لا يُحيي"

    # تِكّة سي‑تريدر وحدها: تُحيي في اللحظة، بلا SYS_SECOND
    await bus.publish(ANALYST_SOURCE, {"symbol": "NQ"})
    assert len(_events(bus, EVENT_RECOVERED)) == before + 1, "المعتمد يُحيي فورًا"
    assert atom._state == "ACTIVE"
    print("OK — المعتمد وحده يُحيي، وفورًا بلا انتظار الساعة")


async def test_thresholds_are_tested_at_the_boundary_itself():
    """`elapsed == stale_after` و`elapsed == dead_after` — الحدّ نفسه.

    طفرتان نجتا: `>` ← `>=` في كلا الشرطين. الاختبارات كانت تستعمل
    قيمًا في وسط النطاق (5ث و20ث و100ث) فلا تفرّق بين العلامتين.
    والفرق ثانيةٌ واحدة تقلب `ACTIVE` إلى `STALE` — أي إنذار انقطاع
    كاذب على تغذية سليمة، أو العكس.

    العقد المقصود: العتبة **ليست** انقطاعًا؛ ما يتجاوزها هو الانقطاع.
    """
    print("\n--- test_thresholds_are_tested_at_the_boundary_itself ---")
    bus = FakeEventBus()
    atom = await _make(bus)
    # config الاختبار: stale=10 و dead=20 (ضِعف الافتراضيّ)
    await bus.publish("SYS_SECOND", {"official_time": 1000.0})
    await bus.publish(ANALYST_SOURCE, {"symbol": "NQ"})

    await bus.publish("SYS_SECOND", {"official_time": 1010.0})   # elapsed = 10 = العتبة
    assert atom._state == "ACTIVE", "عند العتبة بالضبط: لم ينقطع بعد"
    assert not _events(bus, EVENT_INTERRUPTED), "لا إنذار عند الحدّ نفسه"

    await bus.publish("SYS_SECOND", {"official_time": 1010.5})   # 10.5 > 10
    assert atom._state == "STALE", "تجاوز العتبة بنصف ثانية = انقطاع"

    await bus.publish("SYS_SECOND", {"official_time": 1020.0})   # elapsed = 20 = حدّ الموت
    assert atom._state == "STALE", "عند حدّ الموت بالضبط: ما زال STALE"

    await bus.publish("SYS_SECOND", {"official_time": 1020.5})   # 20.5 > 20
    assert atom._state == "DEAD", "تجاوز حدّ الموت = DEAD"
    print("OK — العتبتان تُختبران عندهما: 10 و20 لا تنقلان الحالة، وما بعدهما ينقل")


async def test_secondary_feed_alone_is_never_seen():
    """مصدر ثانويّ وحده لا يجعل الحارس يرى: الحكم للمعتمد."""
    print("\n--- test_secondary_feed_alone_is_never_seen ---")
    bus = FakeEventBus()
    atom = await _make(bus)
    await bus.publish("SYS_SECOND", {"official_time": 100.0})
    await bus.publish("feed.mt5.tick", {"symbol": "NQ"})
    await bus.publish("SYS_SECOND", {"official_time": 101.0})
    health = await atom.health_check()
    assert health.state == HealthState.DEGRADED, health.message
    assert health.message.startswith("NEVER_SEEN"), health.message
    print("OK — ميتاتريدر وحده = NEVER_SEEN لا ACTIVE")


async def test_no_false_interrupt_before_baseline():
    print("\n--- test_no_false_interrupt_before_baseline ---")
    bus = FakeEventBus()
    await _make(bus)
    await bus.publish("SYS_SECOND", {"official_time": 1000.0})  # first pulse = baseline
    assert not _events(bus, EVENT_INTERRUPTED), "no false interrupt on first pulse"
    print("OK — أول نبضة = خط أساس، بلا إنذار كاذب")


async def test_health_states():
    print("\n--- test_health_states ---")
    bus = FakeEventBus()
    atom = Atom()
    await atom.initialize(bus.make_context())
    assert (await atom.health_check()).state == HealthState.UNHEALTHY
    await atom.start()
    assert (await atom.health_check()).state == HealthState.DEGRADED  # no time yet
    await bus.publish("SYS_SECOND", {"official_time": 100.0})
    await bus.publish(ANALYST_SOURCE, {"symbol": "NQ"})
    await bus.publish("SYS_SECOND", {"official_time": 101.0})
    assert (await atom.health_check()).state == HealthState.HEALTHY
    await bus.publish("SYS_SECOND", {"official_time": 200.0})  # silence -> interrupted
    assert (await atom.health_check()).state == HealthState.DEGRADED
    print("OK — الصحة: UNHEALTHY -> DEGRADED(NO_TIME) -> HEALTHY -> DEGRADED(انقطاع)")


async def main():
    tests = [test_interrupt_and_recover, test_no_false_interrupt_before_baseline,
             test_health_states, test_secondary_feed_does_not_mask_analyst_silence,
             test_secondary_feed_alone_is_never_seen,
             test_analyst_tick_revives_immediately_without_waiting_for_clock,
             test_thresholds_are_tested_at_the_boundary_itself,
             test_state_heartbeat_republishes_without_faking_an_event,
             test_zero_heartbeat_keeps_change_only_behaviour]
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


# ٢٠٢٦-١٠-٠١ (ختم المالك «Nq»): كان هنا `if __name__ == "__main__": asyncio.run(main())` — والتزام
# 1490bca (ختم NQ ٢٠٢٦-٠٩-١٦، نبض الحالة) أضاف فحوص النبض **تحته** وأدرج أسماءها في `main` أعلاه،
# فالتشغيل المباشر (وهو ما يفعله governance/scripts/test_atoms.py لملفٍّ بلا `def test_` متزامن) كان
# يقع هنا قبل تعريفها: `NameError: test_state_heartbeat_republishes_without_faking_an_event` — فشل=1
# في المشغّل وpytest أخضر. نقطة الدخول الوحيدة الآن آخر الملفّ، و`main` هناك يضمّ الفحوص العشرة كلّها.


async def _hb_atom(bus, heartbeat):
    """ذرّة بعتبة صمتٍ بعيدة: الحالة تبقى ACTIVE فلا يختلط النبض بالتغيّر."""
    atom = Atom()
    await atom.initialize(AtomContext(
        atom_id=116,
        config={"max_silence_seconds": 10000.0, "dead_after_seconds": 20000.0,
                "state_heartbeat_s": heartbeat},
        logger=_NullLogger(), publish=bus.publish, subscribe=bus.subscribe))
    await atom.start()
    return atom


def _state_rows(bus):
    return [p for n, p in bus.published if n == _mod.EVENT_STATE]


async def test_state_heartbeat_republishes_without_faking_an_event():
    """نبض الحالة يعيد بثّ الحالة الراهنة ولا يدّعي انقطاعًا ولا تعافيًا.

    العلّة المقيسة ٢٠٢٦-٠٩-١٦: `market_data.feed.state` يُنشر عند التغيّر
    وحده — نشرتان في تشغيلة كاملة. فـ454 (فلتر القرار) أُعيد تحميله
    ساخنًا فسقط إلى `feed_unknown` في 1,199 قرارًا من 1,199، وحجبه
    صحيح تصميمًا: قرارٌ على تغذية مجهولة الحال أسوأ من لا قرار.

    والنبض يعيد **الحالة** ولا يخترع حدثًا: `interruption_count` لا
    يتحرّك، ولا يُنشر `feed_interrupted` ولا `feed_recovered`.
    """
    print("\n--- test_state_heartbeat_republishes_without_faking_an_event ---")
    bus = FakeEventBus()
    atom = await _hb_atom(bus, 30.0)
    await bus.publish("SYS_SECOND", {"official_time": 1000.0})
    await bus.publish(ANALYST_SOURCE, {"symbol": "NQ"})
    await bus.publish("SYS_SECOND", {"official_time": 1001.0})   # أوّل نبضة
    base = len(_state_rows(bus))
    hb0 = atom.heartbeats_sent

    await bus.publish("SYS_SECOND", {"official_time": 1010.0})   # داخل النبض
    assert len(_state_rows(bus)) == base, "داخل النبض ولا تغيّر: لا إعادة"

    await bus.publish("SYS_SECOND", {"official_time": 1031.0})   # 30ث مرّت
    assert len(_state_rows(bus)) == base + 1, "النبض يعيد بثّ الحالة"
    assert atom.heartbeats_sent == hb0 + 1, atom.heartbeats_sent
    assert atom._interruption_count == 0, "النبض لا يخترع انقطاعًا"
    assert not _events(bus, EVENT_INTERRUPTED)
    assert not _events(bus, EVENT_RECOVERED)
    body = _state_rows(bus)[-1]
    assert body["status"] == "ACTIVE" and body["analyst_source"] == ANALYST_SOURCE
    assert body["timestamp"] == 1031.0, "الحالة المُعادة تحمل وقتها فيُرى عمرها"
    print("OK — النبض يعيد الحالة ولا يزوّر حدثًا")


async def test_heartbeat_boundary_is_tested_at_the_threshold():
    """`now - last == heartbeat` يُبثّ — الحدّ نفسه لا وسطه."""
    print("\n--- test_heartbeat_boundary_is_tested_at_the_threshold ---")
    bus = FakeEventBus()
    atom = await _hb_atom(bus, 30.0)
    await bus.publish("SYS_SECOND", {"official_time": 1000.0})
    await bus.publish(ANALYST_SOURCE, {"symbol": "NQ"})
    await bus.publish("SYS_SECOND", {"official_time": 1001.0})   # يضبط المرجع
    base = len(_state_rows(bus))
    await bus.publish("SYS_SECOND", {"official_time": 1030.999})
    assert len(_state_rows(bus)) == base, "دون الحدّ بجزء من الألف: لا نبض"
    await bus.publish("SYS_SECOND", {"official_time": 1031.0})
    assert len(_state_rows(bus)) == base + 1, "عند الحدّ بالضبط: نبض"
    print("OK — 29.999 لا ينبض و30.0 ينبض")


async def test_zero_heartbeat_keeps_change_only_behaviour():
    """صفر = السلوك قبل 4.1.0 — باب رجعة بلا تعديل كود."""
    print("\n--- test_zero_heartbeat_keeps_change_only_behaviour ---")
    bus = FakeEventBus()
    atom = await _hb_atom(bus, 0.0)
    await bus.publish("SYS_SECOND", {"official_time": 1000.0})
    await bus.publish(ANALYST_SOURCE, {"symbol": "NQ"})
    base = len(_state_rows(bus))
    for t in (1100.0, 1200.0, 9000.0):
        await bus.publish("SYS_SECOND", {"official_time": t})
    assert len(_state_rows(bus)) == base, "بلا نبض وبلا تغيّر: لا إعادة"
    assert atom.heartbeats_sent == 0
    print("OK — نبض صفر: لا إعادة بتاتًا")


async def main():
    tests = [test_interrupt_and_recover, test_no_false_interrupt_before_baseline,
             test_health_states, test_secondary_feed_does_not_mask_analyst_silence,
             test_secondary_feed_alone_is_never_seen,
             test_analyst_tick_revives_immediately_without_waiting_for_clock,
             test_thresholds_are_tested_at_the_boundary_itself,
             test_state_heartbeat_republishes_without_faking_an_event,
             test_heartbeat_boundary_is_tested_at_the_threshold,
             test_zero_heartbeat_keeps_change_only_behaviour]
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