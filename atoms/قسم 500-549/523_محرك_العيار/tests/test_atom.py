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
    "_atom523", _Path(__file__).resolve().parents[1] / "atom.py")
_mod = _ilu.module_from_spec(_spec)
sys.modules["_atom523"] = _mod
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

    def make_context(self, config):
        return AtomContext(atom_id=523, config=config, logger=_NullLogger(),
                           publish=self.publish, subscribe=self.subscribe)


async def _new(config=None):
    bus = FakeEventBus()
    atom = Atom()
    await atom.initialize(bus.make_context(config if config is not None else {}))
    await atom.start()
    return atom, bus


def _profile(bus, symbol):
    payload = [p for n, p in bus.published if n == EVENT_OUT][-1]
    return [x for x in payload["profiles"] if x["symbol"] == symbol][0]


async def _cmd(atom, symbol, dial, account="A1"):
    await atom._on_account({"account_id": account, "broker": "BR"})
    await atom._on_command({"account_id": account, "broker": "BR", "symbol": symbol, "dial": dial})


async def test_dial_low_scalp():
    print("\n--- test_dial_low_scalp ---")
    atom, bus = await _new()
    await _cmd(atom, "XAUUSD", 20)
    p = _profile(bus, "XAUUSD")
    assert p["dial"] == 20 and p["horizon_seconds"] == 3024.0
    assert p["stop_distance_frac"] == 0.0028 and p["lot_bias"] == "large"
    print("OK — عيار 20 → مدى قصير · ستوب ضيّق · لوت كبير (سكالب)")


async def test_dial_high_long():
    print("\n--- test_dial_high_long ---")
    atom, bus = await _new()
    await _cmd(atom, "XAUUSD", 80)
    p = _profile(bus, "XAUUSD")
    assert p["dial"] == 80 and p["horizon_seconds"] == 11556.0
    assert p["stop_distance_frac"] == 0.0082 and p["lot_bias"] == "small"
    print("OK — عيار 80 → مدى طويل · ستوب أوسع · لوت أصغر")


async def test_dial_37_continuous():
    print("\n--- test_dial_37_continuous ---")
    atom, bus = await _new()
    await _cmd(atom, "XAUUSD", 37)
    p = _profile(bus, "XAUUSD")
    assert p["dial"] == 37
    assert 0.0028 < p["stop_distance_frac"] < 0.0082
    print("OK — عيار 37 → قيمة وسطيّة دقيقة (متّصل، لا ٣ نماذج)")


async def test_inverse_lot_relationship():
    print("\n--- test_inverse_lot_relationship ---")
    atom, bus = await _new()
    await _cmd(atom, "XAUUSD", 20)
    low = _profile(bus, "XAUUSD")
    await _cmd(atom, "XAUUSD", 80)
    high = _profile(bus, "XAUUSD")
    assert low["stop_distance_frac"] < high["stop_distance_frac"], "عيار أقل → ستوب أضيق"
    assert low["lot_bias"] == "large" and high["lot_bias"] == "small"
    print("OK — عيار أقل → ستوب أضيق → لوت أكبر (العلاقة العكسيّة تلقائيّة)")


async def test_ledger_activates_default_dial():
    print("\n--- test_ledger_activates_default_dial ---")
    atom, bus = await _new({"default_dial": 60.0})
    await atom._on_ledger({"ledgers": [{"account_id": "A1", "broker": "BR", "symbol": "USTEC", "u": 0.3}]})
    p = _profile(bus, "USTEC")
    assert p["dial"] == 60.0
    print("OK — أصل نشِط بلا عيار صريح → default_dial (60)")


async def test_command_live_change():
    print("\n--- test_command_live_change ---")
    atom, bus = await _new()
    await _cmd(atom, "XAUUSD", 20)
    assert _profile(bus, "XAUUSD")["dial"] == 20
    await _cmd(atom, "XAUUSD", 90)
    assert _profile(bus, "XAUUSD")["dial"] == 90
    print("OK — dial.command يغيّر العيار حيًّا")


async def test_config_seed_on_start():
    print("\n--- test_config_seed_on_start ---")
    atom, bus = await _new({"dials": {"A1|BR|XAUUSD": 30.0}})
    p = _profile(bus, "XAUUSD")
    assert p["dial"] == 30.0 and p["account_id"] == "A1"
    print("OK — العيارات المُعدّة تُصدَر عند البدء")


async def test_clamp():
    print("\n--- test_clamp ---")
    atom, bus = await _new()
    await _cmd(atom, "XAUUSD", 250)
    assert _profile(bus, "XAUUSD")["dial"] == 100.0
    await _cmd(atom, "XAUUSD", -10)
    assert _profile(bus, "XAUUSD")["dial"] == 0.0
    print("OK — العيار محصور [0,100]")


async def test_health():
    print("\n--- test_health ---")
    bus = FakeEventBus()
    atom = Atom()
    await atom.initialize(bus.make_context({}))
    assert (await atom.health_check()).state == HealthState.UNHEALTHY
    await atom.start()
    assert (await atom.health_check()).state == HealthState.HEALTHY
    print("OK — الصحة: UNHEALTHY→HEALTHY (مترجم جاهز دائمًا)")


async def main():
    tests = [test_dial_low_scalp, test_dial_high_long, test_dial_37_continuous,
             test_inverse_lot_relationship, test_ledger_activates_default_dial,
             test_command_live_change, test_config_seed_on_start, test_clamp, test_health]
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

async def test_per_symbol_bounds_replace_the_single_ruler():
    """حكم المالك ٢٠٢٦-٠٩-١٠: «كل رمز لازم يشتغل بنطاق يناسبه».

    الحدّان كانا عامّين، فنسبةٌ واحدة تُنتج ٧ نقاط على اليورو و٤٧ دولارًا
    على البيتكوين — ولا يتناسب أيٌّ منهما مع سبريده.
    """
    cfg = {"stop_bounds_by_symbol": {"EURUSD": {"min": 0.0006, "max": 0.00086}}}
    atom, bus = await _new(cfg)
    await _cmd(atom, "EURUSD", 0.0)
    await _cmd(atom, "BTCUSD", 0.0)
    assert _profile(bus, "EURUSD")["stop_distance_frac"] == 0.0006
    assert _profile(bus, "BTCUSD")["stop_distance_frac"] == 0.001, "غير المخصَّص يبقى على العامّ"
    await _cmd(atom, "EURUSD", 100.0)
    assert _profile(bus, "EURUSD")["stop_distance_frac"] == 0.00086
    print("OK — لكل رمز مداه، والباقي على العامّ")


async def test_eurusd_bounds_land_on_seven_to_ten_points():
    """الرقم الذي أمر به المالك: من ٧ إلى ١٠ نقاط على اليورو."""
    cfg = {"stop_bounds_by_symbol": {"EURUSD": {"min": 0.0006, "max": 0.00086}}}
    atom, bus = await _new(cfg)
    price, pip = 1.1636, 0.0001
    await _cmd(atom, "EURUSD", 0.0)
    low = _profile(bus, "EURUSD")["stop_distance_frac"] * price / pip
    await _cmd(atom, "EURUSD", 100.0)
    high = _profile(bus, "EURUSD")["stop_distance_frac"] * price / pip
    assert 6.9 <= low <= 7.1, low
    assert 9.9 <= high <= 10.1, high
    print("OK — اليورو %.1f إلى %.1f نقطة" % (low, high))


async def test_malformed_bounds_are_ignored_not_fatal():
    cfg = {"stop_bounds_by_symbol": {
        "A": {"min": "x", "max": 1}, "B": {"min": 0.002},
        "C": {"min": 0.005, "max": 0.001}, "D": {"min": 0.0, "max": 0.01},
        "E": "not-a-dict"}}
    atom, bus = await _new(cfg)
    assert atom._stop_bounds == {}, atom._stop_bounds
    await _cmd(atom, "A", 0.0)
    assert _profile(bus, "A")["stop_distance_frac"] == 0.001
    print("OK — الإدخال الفاسد يُتجاهل ولا يُسقط الذرّة")

async def test_gold_max_stop_is_ten_dollars_not_forty_four():
    """حكم المالك ٢٠٢٦-٠٩-١٠: «٤٤ أقصى؟ ١٠ — سكالبينج.

    ٤٤ دولار من سعره بدّه يومين لا يتحرّكها». المدى العامّ (0.01) كان
    يعطي الذهب وقفًا أقصى قدره ٤٤٫١١$ عند 4411 — حركةُ يومين لا حركةَ
    صفقة سكالب.
    """
    cfg = {"stop_bounds_by_symbol": {"XAUUSD": {"min": 0.001, "max": 0.00227}}}
    atom, bus = await _new(cfg)
    price = 4411.0
    await _cmd(atom, "XAUUSD", 100.0)
    top = _profile(bus, "XAUUSD")["stop_distance_frac"] * price
    await _cmd(atom, "XAUUSD", 0.0)
    floor = _profile(bus, "XAUUSD")["stop_distance_frac"] * price
    assert 9.9 <= top <= 10.1, "الأقصى %.2f$ وليس ١٠" % top
    assert 4.3 <= floor <= 4.5, floor
    print("OK — الذهب %.2f$ إلى %.2f$" % (floor, top))


async def test_no_subscription_to_archived_settings_state():
    """٢٠٢٦-١٠-٠٧ (ختم «NQ»): ناشر decision.settings.state أُرشف — فلا اشتراك فيه.

    ٢٠٢٦-١٠-٠٩ (ختم المالك «NQ» — إلغاء مفاتيح السرعة إلى الأرشيف): ولا SYS_SECOND — عمله الوحيد كان
    التقاط تغيّر مفتاح الأفق المؤرشف."""
    atom, bus = await _new()
    assert "decision.settings.state" not in bus._handlers
    assert "SYS_SECOND" not in bus._handlers
    for kept in ("risk.asset_ledger.state", "dial.command", "platform.account.state"):
        assert kept in bus._handlers, kept


async def test_default_dial_is_the_manifest_number_and_no_horizon_shadow():
    """٢٠٢٦-١٠-٠٩ (ختم المالك «NQ» — إلغاء مفاتيح السرعة إلى الأرشيف): العيار الافتراضيّ `default_dial`
    حرفيًّا — صفوف المفاتيح المعتمدة في سجلّ المعايير (الأفق والرئيسيّ) بياناتٌ بلا قارئ لا تزيحه —
    ولا يُنشر ظلّ «شخصيّة الأفق» بعد اليوم."""
    from shared.parameter_registry import ParameterRegistry, refresh_gate
    registry = ParameterRegistry()        # سجلّ الجلسة المعزول (conftest) — لا الحيّ
    with registry._lock, registry._connect() as conn:  # noqa: SLF001 — صفوفٌ كصفوف الحيّ المؤرشفة
        for name, value in (("TRADING_HORIZON", 10.0), ("MASTER_KEY", 90.0)):
            conn.execute(
                """INSERT OR REPLACE INTO parameters(name,scope,value,source,status,version,
                   effective_from,approved_by,approved_at,governs,declared_at)
                   VALUES(?,'global',?,'OWNER','APPROVED',1,1.0,'nq-test',1.0,'archived','archived')""",
                (name, value))
        conn.commit()
    refresh_gate()
    atom, bus = await _new({"default_dial": 50.0})
    await atom._on_ledger({"ledgers": [{"account_id": "A1", "broker": "BR", "symbol": "USTEC"}]})
    p = _profile(bus, "USTEC")
    assert p["dial"] == 50.0 and p["horizon_seconds"] == 7290.0, p
    assert not [n for n, _ in bus.published if n == "horizon.profile.state"]
