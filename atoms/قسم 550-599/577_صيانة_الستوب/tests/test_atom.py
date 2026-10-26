import asyncio
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
    "_atom577", _Path(__file__).resolve().parents[1] / "atom.py")
_mod = _ilu.module_from_spec(_spec)
sys.modules["_atom577"] = _mod
_spec.loader.exec_module(_mod)
Atom = _mod.Atom
EVENT_MANAGE = _mod.EVENT_MANAGE


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

    def make_context(self, config):
        return AtomContext(atom_id=577, config=config, logger=_NullLogger(),
                           publish=self.publish, subscribe=self.subscribe)


async def _new():
    bus = FakeEventBus()
    atom = Atom()
    await atom.initialize(bus.make_context({}))
    await atom.start()
    return atom, bus


async def _positions(atom, legs, account="A1", symbol="XAUUSD"):
    rows = [{"account_id": account, "symbol": symbol, "ticket": t, "side": s} for t, s in legs]
    await atom._on_positions({"positions": rows})


def _modifies(bus):
    return [p for n, p in bus.published if n == EVENT_MANAGE]


async def test_trail_lets_the_winner_run():
    """حكم المالك ٢٠٢٦-٠٩-٠٦: «آخر صفقة لازم تربح ٢٠٠ لا ٣٠٠، ربحانة ٣٥».

    المقيس الذي أثبت شكواه: الثماني الأخيرة أهدافها 78→142 نقطة (223$
    إلى 303$) ولا واحدة بلغت هدفها. والسبب رقمان في الزحف: بلا شرط ربح
    أدنى شُدّ الوقف إلى 1.47 نقطة من الدخول والسعر بعيد 9 فقط
    (1911362798 ⇒ −0.53$ بدل +303.08$)، ومجال التنفّس كان 7.71 أي
    بمقدار الضجيج المقيس نفسه (مئين ٨٠ = 7.54).
    """
    # ٢٠٢٦-١٠-٠٨ (إصلاح الاختبارات القديمة بأمر المالك): الزحف موقوفٌ بأمر ٠٩-١٦ «ترييلنج وقفه» وبأمر ١٠-٠٧ «الأثلاث وحدها… ما في غيرها»، فبالإعداد الحيّ لا يُرسل شيء ولو بلغ الربح 2R.
    print("\n--- الزحف يترك الرابح يكمل ---")
    entry, stop = 80000.0, 79970.0           # شراء بمخاطرة ثلاثين نقطة
    original = entry - stop                  # 30.0
    manifest = (_Path(__file__).resolve().parents[1] / "manifest.yaml").read_text(encoding="utf-8")
    assert "trailing_enabled: false" in manifest, "الزحف مفتوحٌ في الإعداد الحيّ"
    live, live_bus = await _new()
    live._structure["XAUUSD"] = {"low": entry + 20.0, "high": 80200.0}
    await live._trail_structure({"account_id": "A1", "symbol": "XAUUSD", "ticket": 7, "side": "BUY",
                                 "entry_price": entry, "current_price": entry + 60.0, "stop_loss": stop})
    assert not _modifies(live_bus), "زُحف الوقف والزحف موقوفٌ بأمر المالك"
    assert live._trail_suppressed == 1
    await _positions(live, [(7, "BUY")])
    assert "ترييلنج=موقوف" in (await live.health_check()).message
    # ٢٠٢٦-١٠-٠٨ (إصلاح الاختبارات القديمة بأمر المالك): الكود باقٍ للرجوع بكلمة، فحرّاسه تُفحص بفتحه صراحةً: لا زحف قبل 1R، ولا داخل مجال التنفّس، ولا إلى وقفٍ أرخى من القائم.
    bus = FakeEventBus()
    atom = Atom()
    await atom.initialize(bus.make_context({"trailing_enabled": True}))
    await atom.start()
    atom._structure["XAUUSD"] = {"low": 79995.0, "high": 80100.0}
    pos = {"account_id": "A1", "symbol": "XAUUSD", "ticket": 7, "side": "BUY",
           "entry_price": entry, "current_price": entry + 9.0, "stop_loss": stop}

    # ربح ٩ نقاط على مخاطرة ٣٠ = 0.3R — دون العتبة، فلا يُمسّ الوقف.
    await atom._trail_structure(pos)
    assert not _modifies(bus), "زُحف الوقف قبل بلوغ الربح مخاطرته"

    # عند 1R بالضبط تُفتح البوّابة، لكن المرساة تحتاج مجال تنفّس كاملًا.
    pos["current_price"] = entry + original * _mod.TRAIL_MIN_PROFIT_R
    atom._structure["XAUUSD"] = {"low": entry + 5.0, "high": 80100.0}
    await atom._trail_structure(pos)
    assert not _modifies(bus), "زحف إلى مرساة داخل مجال التنفّس"

    # مرساة أبعد من مجال التنفّس (0.9 × 30 = 27) ⇒ تُقبل.
    pos["current_price"] = entry + 60.0
    atom._structure["XAUUSD"] = {"low": entry + 20.0, "high": 80200.0}
    await atom._trail_structure(pos)
    sent = _modifies(bus)
    assert len(sent) == 1, sent
    assert sent[0]["stop_loss"] == entry + 20.0, sent[0]
    # ٢٠٢٦-١٠-٠٨ (إصلاح الاختبارات القديمة بأمر المالك): مرساةٌ تحت الوقف القائم (80020) لا تُرسل — الوقف لا يُرخى أبدًا.
    pos["stop_loss"] = entry + 20.0
    atom._structure["XAUUSD"] = {"low": entry + 10.0, "high": 80200.0}
    await atom._trail_structure(pos)
    assert len(_modifies(bus)) == 1, _modifies(bus)
    print(f"  الإعداد الحيّ: لا زحف ✓ · مفتوحًا صراحةً: 0.3R لا زحف ✓ · 1R بمرساة لاصقة: لا زحف ✓ · "
          f"2R بمرساة على بعد 40: زحف إلى {sent[0]['stop_loss']} ✓ · مرساة أرخى: لا ✓")


# ٢٠٢٦-٠٩-٢٣ (ختم nq، v1.11.0): رُفعت ستّة اختبارات للمسار الثالث (خطّة ٥٧١ ⟵
# `_maintain`) مع رفعه — ناشره أُرشف. ما كانت تحرسه من المشترَك بقي محروسًا هنا:
# تنظيف `_last_sl` للتذاكر الغائبة، والصحّة. واختبارٌ يثبت أنّ الاشتراك رُفع فعلًا.


async def test_plan_path_removed():
    print("\n--- test_plan_path_removed ---")
    atom, bus = await _new()
    assert "perpetual.plan.state" not in bus._handlers, sorted(bus._handlers)
    assert not hasattr(atom, "_on_plan") and not hasattr(atom, "_maintain")
    print("OK — لا اشتراك بخطّة ٥٧١ ولا معالج لها")


async def test_ticket_cleanup():
    print("\n--- test_ticket_cleanup ---")
    atom, bus = await _new()
    await _positions(atom, [(1, "BUY"), (2, "SELL")])
    atom._last_sl[1] = 4300.0
    atom._last_sl[2] = 4400.0
    await _positions(atom, [(2, "SELL")])
    assert atom._last_sl == {2: 4400.0}, atom._last_sl
    print("OK — تذكرةٌ غابت يُنظَّف آخر وقفها، والقائمة تبقى")


async def test_health():
    print("\n--- test_health ---")
    bus = FakeEventBus()
    atom = Atom()
    await atom.initialize(bus.make_context({}))
    assert (await atom.health_check()).state == HealthState.UNHEALTHY
    await atom.start()
    status = await atom.health_check()
    assert status.state == HealthState.DEGRADED and status.message == "NO_POSITIONS_YET", status.message
    await _positions(atom, [(1, "BUY")])
    assert (await atom.health_check()).state == HealthState.HEALTHY
    print("OK — الصحة: UNHEALTHY→DEGRADED(NO_POSITIONS_YET)→HEALTHY بصورة المراكز")


async def main():
    tests = [test_trail_lets_the_winner_run, test_plan_path_removed, test_ticket_cleanup, test_health]
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
