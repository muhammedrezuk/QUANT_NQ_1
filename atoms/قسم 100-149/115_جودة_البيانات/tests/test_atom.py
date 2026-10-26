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
    "_atom115", _Path(__file__).resolve().parents[1] / "atom.py")
_mod = _ilu.module_from_spec(_spec)
sys.modules["_atom115"] = _mod
_spec.loader.exec_module(_mod)
Atom = _mod.Atom
EVENT_OUT = _mod.EVENT_OUT


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
        return AtomContext(atom_id=115, config={"gap_threshold_s": 5.0,
                           "spike_pct": 5.0, "spread_pct": 1.0}, logger=_NullLogger(),
                           publish=self.publish, subscribe=self.subscribe)


async def _make(bus):
    atom = Atom()
    await atom.initialize(bus.make_context())
    await atom.start()
    await bus.publish("platform.account.state", {"account_id": "A", "broker": "BR"})
    return atom


def _alerts(bus, kind=None):
    out = [p for n, p in bus.published if n == EVENT_OUT]
    return [a for a in out if kind is None or a["kind"] == kind]


async def test_clean_tick_no_alert():
    print("\n--- test_clean_tick_no_alert ---")
    bus = FakeEventBus()
    await _make(bus)
    await bus.publish("market.tick", {"account_id": "A", "symbol": "NQ", "bid": 100.0, "ask": 100.2, "timestamp": 1.0})
    assert not _alerts(bus), "clean tick -> no alert"
    print("OK — تكّة سليمة → لا تنبيه")


async def test_detects_spike():
    print("\n--- test_detects_spike ---")
    bus = FakeEventBus()
    await _make(bus)
    await bus.publish("market.tick", {"account_id": "A", "symbol": "NQ", "bid": 100.0, "ask": 100.2, "timestamp": 1.0})
    await bus.publish("market.tick", {"account_id": "A", "symbol": "NQ", "bid": 110.0, "ask": 110.2, "timestamp": 2.0})  # ~10%
    sp = _alerts(bus, "price_spike")
    assert sp and sp[-1]["symbol"] == "NQ" and sp[-1]["timestamp"] == 2.0, sp
    print(f"OK — كشف قفزة سعرية: {sp[-1]['change_pct']}%")


async def test_detects_gap():
    print("\n--- test_detects_gap ---")
    bus = FakeEventBus()
    await _make(bus)
    await bus.publish("market.tick", {"account_id": "A", "symbol": "NQ", "bid": 100.0, "ask": 100.2, "timestamp": 1.0})
    await bus.publish("market.tick", {"account_id": "A", "symbol": "NQ", "bid": 100.0, "ask": 100.2, "timestamp": 20.0})  # 19s gap
    assert _alerts(bus, "time_gap"), "gap > 5s must alert"
    print("OK — كشف فجوة زمنية (>5s)")


async def test_detects_abnormal_spread():
    print("\n--- test_detects_abnormal_spread ---")
    bus = FakeEventBus()
    await _make(bus)
    await bus.publish("market.tick", {"account_id": "A", "symbol": "NQ", "bid": 100.0, "ask": 105.0, "timestamp": 1.0})  # 5% spread
    assert _alerts(bus, "abnormal_spread"), "wide spread must alert"
    print("OK — كشف سبريد شاذ")


async def test_per_symbol_no_false_spike():
    print("\n--- test_per_symbol_no_false_spike ---")
    bus = FakeEventBus()
    await _make(bus)
    await bus.publish("market.tick", {"account_id": "A", "symbol": "BTC", "bid": 64000.0, "ask": 64001.0, "timestamp": 1.0})
    await bus.publish("market.tick", {"account_id": "A", "symbol": "ETH", "bid": 2500.0, "ask": 2500.5, "timestamp": 2.0})
    assert not _alerts(bus, "price_spike"), "different symbols must NOT cross-trigger spike"
    print("OK — حالة مستقلة لكل رمز (BTC↔ETH ما يعملوا قفزة وهمية)")


async def test_health_states():
    print("\n--- test_health_states ---")
    bus = FakeEventBus()
    atom = Atom()
    await atom.initialize(bus.make_context())
    assert (await atom.health_check()).state == HealthState.UNHEALTHY
    await atom.start()
    assert (await atom.health_check()).state == HealthState.DEGRADED
    await bus.publish("platform.account.state", {"account_id": "A", "broker": "BR"})
    await bus.publish("market.tick", {"account_id": "A", "symbol": "NQ", "bid": 1, "ask": 1.001, "timestamp": 1.0})
    assert (await atom.health_check()).state == HealthState.HEALTHY
    print("OK — الصحة: UNHEALTHY -> DEGRADED -> HEALTHY")


async def main():
    tests = [test_clean_tick_no_alert, test_detects_spike, test_detects_gap,
             test_detects_abnormal_spread, test_per_symbol_no_false_spike,
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


# ٢٠٢٦-٠٩-١٦ — أُضيفت بعد اختبار طفرات. أربع طفرات نجت من هذا الملفّ:
# قلب `usable_for_decision`، و`ask <= bid` ← `<`، و`spread > العتبة` ←
# `>=`. كلّها تشعل أخضر والذرّة تكذب.
STATE_EVENT = _mod.EVENT_STATE


def _states(bus):
    return [p for n, p in bus.published if n == STATE_EVENT]


async def test_usable_for_decision_is_not_inverted():
    """`usable_for_decision` يقرؤه 454 ليحجب القرار — قلبُه كارثة صامتة.

    طفرة `status != INVALID` ← `status == INVALID` نجت من كل اختبارات
    هذا الملفّ: الفاسد يصير صالحًا للقرار والسليم يُحجب، وكلّ عدّاد
    وشارة تبقى كما هي. تُقتل بفحص الحقل في الحالتين معًا.
    """
    print("\n--- test_usable_for_decision_is_not_inverted ---")
    bus = FakeEventBus()
    await _make(bus)
    await bus.publish("market.tick", {"account_id": "A", "symbol": "NQ",
                                      "bid": 100.0, "ask": 100.2, "timestamp": 1.0})
    good = _states(bus)[-1]
    assert good["status"] == "HEALTHY", good["status"]
    assert good["usable_for_decision"] is True, "السليم صالح للقرار"

    await bus.publish("market.tick", {"account_id": "A", "symbol": "NQ",
                                      "bid": 100.0, "ask": 99.5, "timestamp": 2.0})
    bad = _states(bus)[-1]
    assert bad["status"] == "INVALID", bad["status"]
    assert bad["usable_for_decision"] is False, "الفاسد لا يُبنى عليه قرار"
    assert "crossed_spread" in bad["reasons"], bad["reasons"]
    print("OK — الصلاحية صادقة في الحالتين: سليم=True وفاسد=False")


async def test_zero_spread_is_invalid_like_crossed():
    """`bid == ask` دفتر معطوب — القاعدة موحّدة مع 112 و103 و106.

    طفرة `ask <= bid` ← `ask < bid` نجت لأنّ الاختبارات كانت تستعمل
    سبريدًا مقلوبًا فعليًّا (99.5 < 100). الحدّ هو التساوي نفسه.
    """
    print("\n--- test_zero_spread_is_invalid_like_crossed ---")
    bus = FakeEventBus()
    atom = await _make(bus)
    await bus.publish("market.tick", {"account_id": "A", "symbol": "NQ",
                                      "bid": 100.0, "ask": 100.0, "timestamp": 1.0})
    state = _states(bus)[-1]
    assert state["status"] == "INVALID", state
    # ٢٠٢٦-١٠-٠١ (ختم المالك «Nq»): منذ 4.3.0 (التزام 59413f6، التاريخ ٢٠٢٦-٠٩-٢٤ «السبريد
    # الصفريّ يُعدّ وحده لا فسادًا»، ختم «Nq كل إصلاحات») المساواة تُسمّى `locked_spread`
    # لا `crossed_spread`، وتبقى INVALID للقرار كما قضت قاعدة ٠٩-٠٧. ويُعدّ في عدّاد السبريد
    # الصفر وحده، لا في الفاسد ولا في إنذار الدفتر.
    assert state["reasons"] == ["locked_spread"], state["reasons"]
    assert state["usable_for_decision"] is False
    assert atom._locked_total == 1 and atom._book_total == 0 and atom._invalid == 0, (
        atom._locked_total, atom._book_total, atom._invalid)
    print("OK — السبريد الصفريّ مرفوضٌ للقرار ويُعدّ وحده لا فسادًا")


async def test_spread_threshold_is_tested_at_the_boundary():
    """العتبة ليست شذوذًا؛ ما يتجاوزها هو الشاذّ.

    `spread_pct = 1.0`. سبريد يساوي 1% بالضبط يجب أن يمرّ بلا تنبيه،
    وما يزيد عليه يُنبَّه. طفرة `>` ← `>=` نجت لأنّ لا اختبار وقف عند
    الواحد بالمئة نفسه.
    """
    print("\n--- test_spread_threshold_is_tested_at_the_boundary ---")
    bus = FakeEventBus()
    await _make(bus)
    # mid = 100.0 · سبريد 1.0 ⇒ 1.0% بالضبط بلا خطأ عائم
    await bus.publish("market.tick", {"account_id": "A", "symbol": "NQ",
                                      "bid": 99.5, "ask": 100.5, "timestamp": 1.0})
    assert not _alerts(bus, "abnormal_spread"), "عند العتبة بالضبط: لا تنبيه"
    await bus.publish("market.tick", {"account_id": "A", "symbol": "NQ",
                                      "bid": 100.0, "ask": 102.0, "timestamp": 2.0})
    assert _alerts(bus, "abnormal_spread"), "تجاوز العتبة يُنبَّه"
    print("OK — 1.0% بالضبط يمرّ، وما فوقه يُنبَّه")


# ٢٠٢٦-٠٩-١٨ — الشارة كانت تُحكَم بعدّادٍ تراكميّ: تكّةٌ فاسدة واحدة
# منذ الإقلاع ⇒ `DEGRADED` بلا رجعة. ومقيس من `timeline.db` أنّ
# `crossed_spread` حاضرٌ في كلّ ساعةٍ من ثلاثين (99.4% من الرفض) — أي
# أنّ الشارة لم تكن تستطيع أن تخضرّ أبدًا، فلو انهارت التغذية فعلًا
# لبدت اللوحة كما هي الآن بالضبط. هذه الاختبارات تحرس البديل.

_BASE_CFG = {"gap_threshold_s": 5.0, "spike_pct": 5.0, "spread_pct": 1.0}


def _ctx(bus, **overrides):
    config = dict(_BASE_CFG)
    config.update(overrides)
    return AtomContext(atom_id=115, config=config, logger=_NullLogger(),
                       publish=bus.publish, subscribe=bus.subscribe)


async def _atom(bus, **overrides):
    atom = Atom()
    await atom.initialize(_ctx(bus, **overrides))
    await atom.start()
    await bus.publish("platform.account.state", {"account_id": "A", "broker": "BR"})
    return atom


async def _clean(bus, ts):
    await bus.publish("market.tick", {"account_id": "A", "symbol": "NQ",
                                      "bid": 100.0, "ask": 100.2, "timestamp": ts})


async def _crossed(bus, ts):
    """سبريد مقلوب — حالة «دفتر»: سوقٌ لا علّة تغذية."""
    await bus.publish("market.tick", {"account_id": "A", "symbol": "NQ",
                                      "bid": 100.0, "ask": 99.5, "timestamp": ts})


async def _shapeless(bus, ts):
    """تكّة بلا رمز — حالة «شكل»: تغذيةٌ مشوّهة، وهي الأخطر والأندر."""
    await bus.publish("market.tick", {"account_id": "A", "symbol": "",
                                      "bid": 100.0, "ask": 100.2, "timestamp": ts})


async def test_one_bad_tick_no_longer_pins_the_badge_amber():
    """الانحدار الأصليّ: `DEGRADED if self._invalid else HEALTHY`.

    تكّةٌ مقلوبة واحدة بين أربعين (2.5%) كانت تُصفّر الشارة إلى الأصفر
    إلى الأبد. والسوق يعطي هذه النسبة كلّ ساعة.
    """
    print("\n--- test_one_bad_tick_no_longer_pins_the_badge_amber ---")
    bus = FakeEventBus()
    atom = await _atom(bus, min_sample=1)
    await _crossed(bus, 1.0)
    for i in range(39):
        await _clean(bus, 2.0 + i)
    health = await atom.health_check()
    assert health.state == HealthState.HEALTHY, health.message
    assert atom._invalid == 1, "العدّاد التراكميّ يبقى للسجلّ"
    print("OK — 1 من 40 (2.5%) لا تُطفئ الشارة: " + health.message)


async def test_book_threshold_is_tested_at_the_boundary():
    """العتبة ليست شذوذًا؛ ما يتجاوزها هو الشاذّ — كقاعدة السبريد.

    `book_max_pct = 5.0`: واحدةٌ من عشرين = 5.0% بالضبط تمرّ، واثنتان
    من عشرين = 10% تُعلَن. طفرة `>` ← `>=` تُقتل هنا وحدها.
    """
    print("\n--- test_book_threshold_is_tested_at_the_boundary ---")
    bus = FakeEventBus()
    atom = await _atom(bus, min_sample=1)
    await _crossed(bus, 1.0)
    for i in range(19):
        await _clean(bus, 2.0 + i)
    assert (await atom.health_check()).state == HealthState.HEALTHY, "5.0% بالضبط يمرّ"

    bus2 = FakeEventBus()
    atom2 = await _atom(bus2, min_sample=1)
    await _crossed(bus2, 1.0)
    await _crossed(bus2, 2.0)
    for i in range(18):
        await _clean(bus2, 3.0 + i)
    health = await atom2.health_check()
    assert health.state == HealthState.DEGRADED, health.message
    assert "دفتر" in health.message, health.message
    print("OK — 5.0% بالضبط يمرّ، و10% تُعلَن")


async def test_shape_fault_alarms_even_when_book_stays_inside_its_dial():
    """الفصل هو المقصد: علّة الشكل كانت تغرق في خلفيّة الدفتر.

    أربعُ تكّاتٍ مقلوبة من مئة (4% — تحت عيار الدفتر) وواحدةٌ بلا رمز
    (1% — فوق عيار الشكل). بعدّادٍ واحد لا يظهر الفرق أبدًا.
    """
    print("\n--- test_shape_fault_alarms_even_when_book_stays_inside_its_dial ---")
    bus = FakeEventBus()
    atom = await _atom(bus, min_sample=1)
    for i in range(4):
        await _crossed(bus, 1.0 + i)
    await _shapeless(bus, 5.0)
    for i in range(95):
        await _clean(bus, 6.0 + i)
    health = await atom.health_check()
    assert health.state == HealthState.DEGRADED, health.message
    assert "شكل" in health.message, health.message
    assert "missing_symbol" in health.message, health.message
    assert "دفتر" not in health.message.split("·")[0], "الدفتر تحت عياره فلا يُتّهم"
    print("OK — الشكل يُعلَن والدفتر بريء: " + health.message)


async def test_window_rolls_so_a_bad_minute_does_not_last_forever():
    """دقيقةٌ سيّئة تمضي — وهذا كلّ الفرق عن العدّاد التراكميّ."""
    print("\n--- test_window_rolls_so_a_bad_minute_does_not_last_forever ---")
    bus = FakeEventBus()
    atom = await _atom(bus, quality_window_s=10.0, min_sample=1)
    for i in range(10):
        await _crossed(bus, 1.0 + i * 0.1)
    assert (await atom.health_check()).state == HealthState.DEGRADED, "نافذة كلّها فاسدة"
    for i in range(40):
        await _clean(bus, 100.0 + i)
    health = await atom.health_check()
    assert health.state == HealthState.HEALTHY, health.message
    print("OK — النافذة دارت والشارة عادت: " + health.message)


async def test_a_thin_fresh_window_borrows_the_previous_one():
    """بلا الضمّ ترتجف الشارة عند كلّ دوران.

    نافذةٌ فُتحت للتوّ فيها تكّةٌ واحدة مقلوبة تعطي 100% — والسابقة
    مئةُ تكّةٍ نظيفة. القراءة الصادقة 1 من 101 لا 1 من 1.
    """
    print("\n--- test_a_thin_fresh_window_borrows_the_previous_one ---")
    bus = FakeEventBus()
    atom = await _atom(bus, quality_window_s=10.0, min_sample=50)
    for i in range(100):
        await _clean(bus, 1.0 + i * 0.05)
    await _crossed(bus, 50.0)
    health = await atom.health_check()
    assert health.state == HealthState.HEALTHY, health.message
    print("OK — النافذة الرقيقة تستعير سابقتها: " + health.message)


async def test_shape_threshold_is_tested_at_the_boundary():
    """حدّ الشكل يُختبر عنده لا في وسطه."""
    print("\n--- test_shape_threshold_is_tested_at_the_boundary ---")
    bus = FakeEventBus()
    atom = await _atom(bus, min_sample=1, shape_max_pct=10.0)
    await _shapeless(bus, 1.0)
    for i in range(9):
        await _clean(bus, 2.0 + i)
    assert (await atom.health_check()).state == HealthState.HEALTHY, "10.0% بالضبط يمرّ"

    bus2 = FakeEventBus()
    atom2 = await _atom(bus2, min_sample=1, shape_max_pct=10.0)
    await _shapeless(bus2, 1.0)
    await _shapeless(bus2, 2.0)
    for i in range(8):
        await _clean(bus2, 3.0 + i)
    assert (await atom2.health_check()).state == HealthState.DEGRADED, "20% تُعلَن"
    print("OK — 10.0% بالضبط يمرّ، و20% تُعلَن")


async def test_dials_fall_back_to_code_defaults_and_say_so():
    """`atom.py` يصل حيًّا و`config` قد لا يصل — فالنسخة في الكود تعمل وتُعلن.

    وإخفاء ذلك أسوأ من غيابه: يُقرأ العيار منفَّذًا من مصدرٍ لم يُقصد.
    """
    print("\n--- test_dials_fall_back_to_code_defaults_and_say_so ---")
    bus = FakeEventBus()
    atom = await _atom(bus)
    await _clean(bus, 1.0)
    health = await atom.health_check()
    assert "افتراضيّ" in health.message, health.message
    assert "/300ث" in health.message, health.message

    bus2 = FakeEventBus()
    atom2 = await _atom(bus2, quality_window_s=60.0, book_max_pct=2.0,
                        shape_max_pct=0.1, min_sample=10)
    await _clean(bus2, 1.0)
    health2 = await atom2.health_check()
    assert "افتراضيّ" not in health2.message, health2.message
    print("OK — الافتراضيّ يعمل ويقول إنّه افتراضيّ، والمذكور يسكت")


async def test_explicit_zero_window_stays_the_owners_decision():
    """صفرٌ صريح = «احكم على العمر كلّه» — لا فراغٌ يُدهس بافتراضيّ.

    لهذا الفحص `in config` لا `.get() or`.
    """
    print("\n--- test_explicit_zero_window_stays_the_owners_decision ---")
    bus = FakeEventBus()
    atom = await _atom(bus, quality_window_s=0, min_sample=1)
    for i in range(40):
        await _clean(bus, 1.0 + i)
    await _crossed(bus, 100.0)
    health = await atom.health_check()
    assert "نافذة=0ث/0ث" in health.message, health.message
    assert health.state == HealthState.HEALTHY, health.message
    print("OK — الصفر الصريح باقٍ: " + health.message)


# ٢٠٢٦-٠٩-١٨ — نجت طفرتان من الاختبارات أعلاه، وكلتاهما حدٌّ لم يُختبر
# **عنده**: دوران النافذة عند مدّتها بالضبط، والضمّ عند العيّنة الدنيا
# بالضبط. الحالة الصحّيّة وحدها لا تفرّقهما (كلتاهما تعطي اللون نفسه)،
# فالفحص على حجم العيّنة المقروءة نفسه.

async def test_window_rolls_exactly_at_its_span():
    """`>=` مقابل `>`: الفرق تكّةٌ واحدة تقع عند المدّة بالضبط.

    نافذةٌ مدّتها عشر ثوانٍ بدأت عند 1.0، وتكّةٌ عند 11.0 — الفارق
    عشرٌ تمامًا. بـ`>=` تفتح نافذةً جديدة فيها هي وحدها؛ بـ`>` تبقى
    مع التسع عشرة قبلها.
    """
    print("\n--- test_window_rolls_exactly_at_its_span ---")
    bus = FakeEventBus()
    atom = await _atom(bus, quality_window_s=10.0, min_sample=1)
    for i in range(19):
        await _clean(bus, 1.0 + i * 0.01)
    await _crossed(bus, 11.0)
    details = (await atom.health_check()).details
    assert details["window_checked"] == 1, details
    print("OK — الدوران عند المدّة نفسها لا بعدها")


async def test_merge_stops_exactly_at_the_minimum_sample():
    """`<` مقابل `<=`: نافذةٌ بلغت العيّنة الدنيا بالضبط تُقرأ وحدها.

    بلغتها = صارت كافية، فلا تُستعار السابقة. و`<=` يستعيرها فيخلط
    مئة تكّةٍ قديمة بعشرٍ حاضرة ويؤخّر الإنذار.
    """
    print("\n--- test_merge_stops_exactly_at_the_minimum_sample ---")
    bus = FakeEventBus()
    atom = await _atom(bus, quality_window_s=10.0, min_sample=10)
    for i in range(100):
        await _clean(bus, 1.0 + i * 0.05)
    for i in range(10):
        await _crossed(bus, 50.0 + i * 0.1)
    health = await atom.health_check()
    assert health.details["window_checked"] == 10, health.details
    assert health.state == HealthState.DEGRADED, health.message
    print("OK — العيّنة الدنيا بالضبط تكفي بنفسها")