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
    "_atom574", _Path(__file__).resolve().parents[1] / "atom.py")
_mod = _ilu.module_from_spec(_spec)
sys.modules["_atom574"] = _mod
_spec.loader.exec_module(_mod)
Atom = _mod.Atom
EVENT_OUT = _mod.EVENT_OUT

CFG = {"partial_at_r": 1.0, "partial_fraction": 0.5, "min_partial_lot": 0.01}


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
        return AtomContext(atom_id=574, config=config, logger=_NullLogger(),
                           publish=self.publish, subscribe=self.subscribe)


def _pos(current, volume=0.2, side="BUY", entry=100.0, stop=99.0, ticket=7,
         target=103.0):
    return {"positions": [{"ticket": ticket, "symbol": "NQ100", "side": side,
            "volume": volume, "entry_price": entry, "current_price": current,
            "stop_loss": stop, "take_profit": target, "profit": 0.0}]}


async def _new(cfg=None):
    bus = FakeEventBus()
    atom = Atom()
    await atom.initialize(bus.make_context(cfg or dict(CFG)))
    await atom.start()
    return atom, bus


def _outs(bus):
    return [p for n, p in bus.published if n == EVENT_OUT]


async def test_first_target_closes_30pct_and_moves_stop_to_entry():
    """خطّة المالك ٢٠٢٦-٠٩-١١ — المرحلة الأولى.

    الهدف 103 والدخول 100، فالمسافة ٣ والثلث عند 101.
    """
    # ٢٠٢٦-١٠-٠٨ (إصلاح الاختبارات القديمة بأمر المالك): الاسم باقٍ من خطّة ٠٩-١١ (30٪ والوقف مع الإغلاق) فلا يُحذف، والجسم يحرس نصّ المالك: ثلث العقد ثمّ الوقف إلى الدخول.
    # ٢٠٢٦-١٠-٠٨ (إصلاح الاختبارات القديمة بأمر المالك): ثلث 0.2 = 0.0667 فيُغلق 0.07 بخطوة 0.01، والوقف لا يخرج حتّى يُرى الحجم ناقصًا على المنصّة (أمر ٠٩-١٩ «يُغلق الجزء أوّلًا ثمّ يُؤمَّن»).
    atom, bus = await _new()
    await atom._on_positions(_pos(100.5))          # دون الثلث
    assert len(_outs(bus)) == 0
    await atom._on_positions(_pos(101.0))          # الثلث
    outs = _outs(bus)
    assert len(outs) == 1, outs
    assert outs[0]["action"] == "CLOSE_PARTIAL" and outs[0]["volume"] == 0.07, outs[0]
    assert outs[0]["stage"] == 1, outs[0]
    # ٢٠٢٦-١٠-٠٨ (إصلاح الاختبارات القديمة بأمر المالك): دورة المراكز تُظهر الحجم 0.13 بعد الإغلاق، فيخرج الوقف إلى الدخول الآن.
    await atom._on_positions(_pos(101.0, volume=0.13))
    outs = _outs(bus)
    assert len(outs) == 2, outs
    assert outs[1]["action"] == "MODIFY_SL" and outs[1]["stop_loss"] == 100.0, outs[1]
    assert outs[1]["reason"] == "BREAKEVEN_AT_FIRST_TARGET"
    print("OK — الهدف الأوّل: ثلث العقد، ثمّ الوقف إلى الدخول بعد نقص الحجم")


async def test_second_target_closes_50pct_of_the_original():
    # ٢٠٢٦-١٠-٠٨ (إصلاح الاختبارات القديمة بأمر المالك): الاسم باقٍ من تفسير «50٪ من الأصليّ» الذي نقضه المالك ٠٩-١٧ («نص باقي من عقد»)، والجسم يحرس نصف الباقي ثمّ الوقف إلى الهدف الأوّل.
    atom, bus = await _new()
    await atom._on_positions(_pos(101.0))                 # الأوّل: يُغلق 0.07
    await atom._on_positions(_pos(102.0, volume=0.13))    # الباقي بعد 0.07، والسعر عند الثلثين
    outs = _outs(bus)
    assert outs[-2]["action"] == "MODIFY_SL" and outs[-2]["stop_loss"] == 100.0, outs[-2]
    assert outs[-1]["action"] == "CLOSE_PARTIAL" and outs[-1]["volume"] == 0.07, outs[-1]
    assert outs[-1]["stage"] == 2
    # ٢٠٢٦-١٠-٠٨ (إصلاح الاختبارات القديمة بأمر المالك): بعد أن يُرى الحجم 0.06 يُنقل الوقف إلى الهدف الأوّل (101) لا إلى الثاني.
    await atom._on_positions(_pos(102.0, volume=0.06))
    lock = _outs(bus)[-1]
    assert lock["action"] == "MODIFY_SL" and lock["stop_loss"] == 101.0, lock
    assert lock["reason"] == "STOP_LOCKED_AT_TARGET_1" and lock["stage"] == 2, lock
    print("OK — الهدف الثاني: نصف الباقي، ثمّ الوقف إلى الهدف الأوّل")


async def test_third_target_closes_the_remainder():
    # ٢٠٢٦-١٠-٠٨ (إصلاح الاختبارات القديمة بأمر المالك): الأحجام صارت أحجام الأثلاث (0.2 ⟵ 0.13 ⟵ 0.06) بدل أحجام خطّة الثلاثين بالمئة.
    atom, bus = await _new()
    await atom._on_positions(_pos(101.0))
    await atom._on_positions(_pos(102.0, volume=0.13))
    await atom._on_positions(_pos(103.0, volume=0.06))
    outs = _outs(bus)
    assert outs[-1]["action"] == "CLOSE" and outs[-1]["volume"] == 0.06, outs[-1]
    assert outs[-1]["stage"] == 3
    print("OK — الهدف الثالث: الباقي كلّه")


async def test_a_seven_r_target_splits_by_the_same_formula():
    """«إذا هدفه ١/٧ تقسم أهداف على ٣ بالتساوي على نفس المعادلة»."""
    # ٢٠٢٦-١٠-٠٨ (إصلاح الاختبارات القديمة بأمر المالك): كان يحرس 30٪ ووقفًا مع الإغلاق؛ صار ثلث العقد ثمّ الدخول، ونصف الباقي عند الثلثين ثمّ الوقف إلى الهدف الأوّل (100 + 7/3).
    atom, bus = await _new()
    await atom._on_positions(_pos(102.0, target=107.0))   # دون الثلث (7/3=2.33)
    assert len(_outs(bus)) == 0, "أطلق قبل ثلث الهدف"
    await atom._on_positions(_pos(102.34, target=107.0))  # الثلث
    outs = _outs(bus)
    assert len(outs) == 1, outs
    assert outs[0]["action"] == "CLOSE_PARTIAL" and outs[0]["volume"] == 0.07, outs[0]
    await atom._on_positions(_pos(102.34, volume=0.13, target=107.0))
    outs = _outs(bus)
    assert outs[1]["action"] == "MODIFY_SL" and outs[1]["stop_loss"] == 100.0, outs[1]
    await atom._on_positions(_pos(104.6, volume=0.13, target=107.0))    # دون الثلثين (104.67)
    assert len(_outs(bus)) == 2, _outs(bus)
    await atom._on_positions(_pos(104.67, volume=0.13, target=107.0))   # الثلثان
    assert _outs(bus)[-1]["action"] == "CLOSE_PARTIAL" and _outs(bus)[-1]["volume"] == 0.07
    await atom._on_positions(_pos(104.67, volume=0.06, target=107.0))
    lock = _outs(bus)[-1]
    assert lock["action"] == "MODIFY_SL" and abs(lock["stop_loss"] - (100.0 + 7.0 / 3.0)) < 1e-6, lock
    print("OK — هدف 7R يُقسم بنفس المعادلة")


async def test_fires_once_per_stage():
    atom, bus = await _new()
    await atom._on_positions(_pos(101.0))
    count = len(_outs(bus))
    await atom._on_positions(_pos(101.5))      # ما زال في المرحلة نفسها
    assert len(_outs(bus)) == count, "أعاد إطلاق المرحلة"
    print("OK — كل مرحلة مرّة واحدة")


async def test_too_small_closes_whole_leg():
    # ٢٠٢٦-١٠-٠٨ (إصلاح الاختبارات القديمة بأمر المالك): الاسم باقٍ من سلوكٍ نقضه أمر ٠٩-١٦ «واذا عقد صغير ما يتسكر منه شي اجزاء مثل 0.01 يكمل لا هدف 3».
    # ٢٠٢٦-١٠-٠٨ (إصلاح الاختبارات القديمة بأمر المالك): عقد 0.01 لا يُجزّأ: لا إغلاق عند الأوّل ولا الثاني، والوقف ينتقل (الدخول ثمّ الهدف الأوّل)، والخروج كاملًا عند الثالث.
    atom, bus = await _new()
    await atom._on_positions(_pos(101.0, volume=0.01))
    outs = _outs(bus)
    assert len(outs) == 1 and outs[-1]["action"] == "MODIFY_SL" and outs[-1]["stop_loss"] == 100.0, outs
    assert atom._indivisible == 1
    await atom._on_positions(_pos(102.0, volume=0.01, stop=100.0))
    outs = _outs(bus)
    assert len(outs) == 2 and outs[-1]["action"] == "MODIFY_SL" and outs[-1]["stop_loss"] == 101.0, outs
    assert atom._indivisible == 2
    await atom._on_positions(_pos(103.0, volume=0.01, stop=101.0))
    outs = _outs(bus)
    assert len(outs) == 3 and outs[-1]["action"] == "CLOSE", outs
    assert outs[-1]["volume"] == 0.01 and outs[-1]["last_lot_guard"] is True
    print("OK — عقدٌ لا يُجزّأ: الوقف يتحرّك ويمضي إلى الهدف الثالث فيُغلق كاملًا")


async def test_health():
    print("\n--- test_health ---")
    bus = FakeEventBus()
    atom = Atom()
    await atom.initialize(bus.make_context(dict(CFG)))
    assert (await atom.health_check()).state == HealthState.UNHEALTHY
    await atom.start()
    assert (await atom.health_check()).state == HealthState.DEGRADED
    await atom._on_positions(_pos(100.0))
    assert (await atom.health_check()).state == HealthState.HEALTHY
    print("OK — الصحة تتدرّج")


async def main():
    tests = [test_partial_at_1r, test_fires_once, test_too_small_skips, test_health]
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
