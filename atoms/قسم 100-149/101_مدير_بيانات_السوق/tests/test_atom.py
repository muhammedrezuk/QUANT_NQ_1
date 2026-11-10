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

from core.contracts.atom import AtomContext  # noqa: E402
import importlib.util as _ilu  # noqa: E402
import sys as _sys  # noqa: E402
from pathlib import Path as _AtomPath  # noqa: E402
_MOD_NAME = "_atom101"
_spec = _ilu.spec_from_file_location(
    _MOD_NAME, _AtomPath(__file__).resolve().parents[1] / "atom.py")
_mod = _ilu.module_from_spec(_spec)
_sys.modules[_MOD_NAME] = _mod
_spec.loader.exec_module(_mod)
Atom = _mod.Atom

_UNIFIED = "market_data.state"


class _NullLogger:
    def debug(self, *a): pass
    def info(self, *a): pass
    def warning(self, *a): pass
    def error(self, *a): pass
    def critical(self, *a): pass


class FakeEventBus:
    def __init__(self):
        self.published = []
        self._handlers: dict[str, list] = {}

    def subscribe(self, name, handler):
        self._handlers.setdefault(name, []).append(handler)

    async def publish(self, name, payload):
        self.published.append((name, payload))
        for handler in self._handlers.get(name, []):
            result = handler(payload)
            if inspect.isawaitable(result):
                await result

    def make_context(self, publish_interval_s=0.0):
        # 2.2.0: العيار مطلوب صراحةً. الافتراضيّ صفر هنا = النشر مع كل
        # حدث، فتبقى الاختبارات القائمة تقيس ما كانت تقيسه بالضبط،
        # والاختبارات الجديدة تمرّر إيقاعًا حقيقيًّا.
        return AtomContext(atom_id=101, config={"publish_interval_s": publish_interval_s},
                           logger=_NullLogger(), publish=self.publish, subscribe=self.subscribe)


async def test_unified_state_accumulates_across_event_types():
    print("\n--- test_unified_state_accumulates_across_event_types ---")
    bus = FakeEventBus()
    atom = Atom()
    await atom.initialize(bus.make_context())
    await atom.start()

    await bus.publish("market_data.price_received", {"symbol": "NQ", "bid": 100.0, "ask": 100.5})
    await bus.publish("market_data.volume_received", {"symbol": "NQ", "volume": 1000})
    await bus.publish("market_data.spread_updated", {"symbol": "NQ", "spread": 0.5})

    unified_events = [p for n, p in bus.published if n == _UNIFIED]
    assert len(unified_events) == 3, "لقطة تُنشَر عند كل تحديث"
    last_state = unified_events[-1]["state"]
    assert set(last_state.keys()) == {"price", "volume", "spread"}, "اللقطة الأخيرة تحوي كل الحقول المتراكمة، لا آخر واحد بس"
    print(f"OK — اللقطة الأخيرة تراكمت من 3 أنواع مختلفة: {list(last_state.keys())}")


async def test_publishes_state_suffix_event():
    """قاعدة 16 — اسم الحدث المنشور لازم يكون بلاحقة حالة (قابل للإعادة)."""
    print("\n--- test_publishes_state_suffix_event ---")
    bus = FakeEventBus()
    atom = Atom()
    await atom.initialize(bus.make_context())
    await atom.start()
    await bus.publish("market_data.price_received", {"symbol": "NQ", "bid": 1})
    names = {n for n, _ in bus.published}
    assert _UNIFIED in names, f"لازم ينشر {_UNIFIED}"
    assert _UNIFIED.endswith(".state"), "الحدث لازم يكون بلاحقة حالة (قاعدة 16)"
    print(f"OK — نشر حدث حالة قابل للإعادة: {_UNIFIED}")


async def test_nine_event_types_no_late_binding_bug():
    """أهم اختبار — يثبت عدم وجود عيب الإغلاق المتأخر عبر التسعة أنواع."""
    print("\n--- test_nine_event_types_no_late_binding_bug ---")
    bus = FakeEventBus()
    atom = Atom()
    await atom.initialize(bus.make_context())
    await atom.start()

    event_names = [
        "market_data.price_received", "market_data.candle_closed", "market_data.volume_received",
        "market_data.spread_updated", "market_data.depth_updated",
        "market_data.news_received", "market_data.calendar_event", "market_data.reference_index_updated",
    ]
    for name in event_names:
        await bus.publish(name, {"symbol": "NQ"})

    final_state = atom._state["NQ"]
    # ٢٠٢٦-١٠-٠٧ (ختم المالك «nq»): «trade_tape» خرج مع أرشفة 107 — ثمانية أنواع لا تسعة.
    expected_keys = {
        "price", "candle", "volume", "spread", "depth", "news", "calendar", "reference_index",
    }
    assert set(final_state.keys()) == expected_keys, (
        f"كل نوع حدث لازم يخزَّن بمفتاحه الصحيح بالضبط، لا كلهم بآخر مفتاح (عيب إغلاق متأخر)، لقيت: {set(final_state.keys())}"
    )
    print(f"OK — الثمانية أنواع خُزِّنت كل واحد بمفتاحه الصحيح: {sorted(final_state.keys())}")


async def test_symbols_tracked_independently():
    print("\n--- test_symbols_tracked_independently ---")
    bus = FakeEventBus()
    atom = Atom()
    await atom.initialize(bus.make_context())
    await atom.start()
    await bus.publish("market_data.price_received", {"symbol": "NQ", "bid": 1})
    await bus.publish("market_data.price_received", {"symbol": "ES", "bid": 2})
    assert set(atom._state.keys()) == {"NQ", "ES"}
    assert atom._state["NQ"]["price"]["bid"] == 1
    assert atom._state["ES"]["price"]["bid"] == 2
    print(f"OK — NQ وES بحالتين مستقلتين تمامًا: {atom._state}")


async def test_missing_symbol_goes_global_without_crash():
    """حالة فشل/حافة (قاعدة 9) — payload بلا symbol ما ينهار، يروح لـ_global."""
    print("\n--- test_missing_symbol_goes_global_without_crash ---")
    bus = FakeEventBus()
    atom = Atom()
    await atom.initialize(bus.make_context())
    await atom.start()
    await bus.publish("market_data.price_received", {"bid": 1})  # بلا symbol
    assert "_global" in atom._state, "payload بلا symbol لازم يروح لـ_global"
    assert atom._state["_global"]["price"]["bid"] == 1
    print("OK — payload بلا symbol راح لـ_global بلا انهيار")


async def main():
    tests = [
        test_unified_state_accumulates_across_event_types,
        test_publishes_state_suffix_event,
        test_nine_event_types_no_late_binding_bug,
        test_symbols_tracked_independently,
        test_missing_symbol_goes_global_without_crash,
    ]
    failed = []
    for t in tests:
        try:
            await t()
        except AssertionError as e:
            failed.append((t.__name__, str(e)))
            print(f"FAILED: {t.__name__}: {e}")
        except Exception as e:
            failed.append((t.__name__, repr(e)))
            print(f"ERROR: {t.__name__}: {e!r}")
    print("\n" + "=" * 60)
    if failed:
        print(f"فشل {len(failed)} من أصل {len(tests)}")
        sys.exit(1)
    print(f"نجح كل الاختبارات ({len(tests)}/{len(tests)})")


if __name__ == "__main__":
    asyncio.run(main())


# ٢٠٢٦-٠٩-١٦ (بتفويض المالك) — إيقاع البثّ في 2.2.0.
# الذرّة كانت تنشر الصورة الكاملة مع كل حدث: 2,987 نشرة/دقيقة مقيسة،
# و`no_subscribers` يساوي عدد النشرات كلّها. العيار ينظّم البثّ ولا يمسّ
# الجمع — وهذه الاختبارات تحرس الفرق بينهما.


async def _with(bus, interval):
    atom = Atom()
    await atom.initialize(bus.make_context(publish_interval_s=interval))
    await atom.start()
    return atom


def _states(bus):
    return [p for n, p in bus.published if n == "market_data.state"]


async def test_interval_suppresses_bursts_without_losing_state():
    """الكتم يمسّ البثّ وحده — الصورة تبقى كاملة.

    هذا هو العقد كلّه: لو كتم الإيقاعُ **الجمعَ** لضاعت معلومة، ولو لم
    يكتم البثَّ لبقي النزيف. يُفحص الاثنان معًا في اختبار واحد.
    """
    print("\n--- test_interval_suppresses_bursts_without_losing_state ---")
    bus = FakeEventBus()
    atom = await _with(bus, 1.0)
    await bus.publish("market.tick.validated", {"symbol": "XAUUSD", "timestamp": 100.0, "bid": 1})
    await bus.publish("market_data.spread_updated", {"symbol": "XAUUSD", "timestamp": 100.2, "spread": 2})
    await bus.publish("market_data.depth_updated", {"symbol": "XAUUSD", "timestamp": 100.5, "levels": 3})
    rows = _states(bus)
    assert len(rows) == 1, ("أوّل صورة فقط تُبثّ داخل الإيقاع", len(rows))
    assert atom.suppressed_count == 2, atom.suppressed_count
    # ولا معلومة ضاعت: الحقول الثلاثة كلّها في الحالة المحفوظة
    state = atom._state["XAUUSD"]
    assert set(state) == {"tick", "spread", "depth"}, set(state)
    assert state["depth"]["levels"] == 3
    print("OK — بُثّت واحدة وجُمعت ثلاث: الكتم لا يُفقد شيئًا")


async def test_first_picture_of_each_symbol_is_never_suppressed():
    """من يشترك لاحقًا يجد صورةً لا فراغًا — مهما طال الإيقاع."""
    print("\n--- test_first_picture_of_each_symbol_is_never_suppressed ---")
    bus = FakeEventBus()
    atom = await _with(bus, 3600.0)
    for symbol in ("XAUUSD", "EURUSD", "BTCUSD"):
        await bus.publish("market.tick.validated", {"symbol": symbol, "timestamp": 100.0})
    assert len(_states(bus)) == 3, "لكل رمز صورته الأولى"
    assert atom.suppressed_count == 0
    print("OK — الصورة الأولى لكل رمز تُبثّ دائمًا")


async def test_interval_boundary_is_tested_at_the_threshold():
    """`stamp - last == interval` يُبثّ — الحدّ نفسه لا وسط النطاق."""
    print("\n--- test_interval_boundary_is_tested_at_the_threshold ---")
    bus = FakeEventBus()
    atom = await _with(bus, 1.0)
    await bus.publish("market.tick.validated", {"symbol": "XAUUSD", "timestamp": 100.0})
    await bus.publish("market.tick.validated", {"symbol": "XAUUSD", "timestamp": 100.999})
    assert len(_states(bus)) == 1, "دون الحدّ بجزء من الألف: يُكتم"
    await bus.publish("market.tick.validated", {"symbol": "XAUUSD", "timestamp": 101.0})
    assert len(_states(bus)) == 2, "عند الحدّ بالضبط: يُبثّ"
    print("OK — 0.999 يُكتم و1.0 يُبثّ")


async def test_each_symbol_has_its_own_rhythm():
    """إيقاع رمزٍ لا يكتم رمزًا آخر."""
    print("\n--- test_each_symbol_has_its_own_rhythm ---")
    bus = FakeEventBus()
    atom = await _with(bus, 10.0)
    await bus.publish("market.tick.validated", {"symbol": "XAUUSD", "timestamp": 100.0})
    await bus.publish("market.tick.validated", {"symbol": "EURUSD", "timestamp": 100.1})
    await bus.publish("market.tick.validated", {"symbol": "XAUUSD", "timestamp": 100.2})
    rows = _states(bus)
    assert [r["symbol"] for r in rows] == ["XAUUSD", "EURUSD"], [r["symbol"] for r in rows]
    assert atom.suppressed_count == 1
    print("OK — لكل رمز إيقاعه المستقلّ")


async def test_backwards_time_and_missing_stamp_are_published():
    """تراجُع الزمن وحمولةٌ بلا طابع — كلاهما يُبثّ ولا يُبتلع.

    مصدرٌ أُعيد ضبطه (لقطة جديدة) أو حدثٌ بلا `timestamp` لا يجوز أن
    يختفي لأنّ حسابًا زمنيًّا لم يفهمه.
    """
    print("\n--- test_backwards_time_and_missing_stamp_are_published ---")
    bus = FakeEventBus()
    atom = await _with(bus, 60.0)
    await bus.publish("market.tick.validated", {"symbol": "XAUUSD", "timestamp": 500.0})
    await bus.publish("market.tick.validated", {"symbol": "XAUUSD", "timestamp": 100.0})
    assert len(_states(bus)) == 2, "تراجُع الزمن يُبثّ"
    await bus.publish("market_data.news_received", {"symbol": "XAUUSD", "headline": "x"})
    assert len(_states(bus)) == 3, "حمولة بلا طابع تُبثّ"
    print("OK — التراجع والطابع الغائب لا يُكتمان")


async def test_zero_interval_keeps_the_old_behaviour():
    """صفر = السلوك قبل 2.2.0 بالحرف — باب رجعة بلا تعديل كود."""
    print("\n--- test_zero_interval_keeps_the_old_behaviour ---")
    bus = FakeEventBus()
    atom = await _with(bus, 0.0)
    for i in range(5):
        await bus.publish("market.tick.validated", {"symbol": "XAUUSD", "timestamp": 100.0 + i * 0.01})
    assert len(_states(bus)) == 5, len(_states(bus))
    assert atom.suppressed_count == 0
    print("OK — إيقاع صفر يبثّ كل حدث")


async def test_health_declares_what_it_suppressed():
    """ما يُكتم يُقال — رقم نشرٍ بلا رقم كتمٍ يخفي نصف العمل."""
    print("\n--- test_health_declares_what_it_suppressed ---")
    bus = FakeEventBus()
    atom = await _with(bus, 1.0)
    for i in range(4):
        await bus.publish("market.tick.validated", {"symbol": "XAUUSD", "timestamp": 100.0 + i * 0.1})
    health = await atom.health_check()
    assert "مكتوم=3" in health.message, health.message
    assert "إيقاع=1ث" in health.message, health.message
    assert health.details["collected"] == 4
    assert health.details["published"] == 1
    print("OK — المكتوم والإيقاع معلنان في الرسالة المرئيّة")