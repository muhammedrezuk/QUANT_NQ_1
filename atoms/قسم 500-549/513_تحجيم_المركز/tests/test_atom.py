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
    "_atom513", _Path(__file__).resolve().parents[1] / "atom.py")
_mod = _ilu.module_from_spec(_spec)
sys.modules["_atom513"] = _mod
_spec.loader.exec_module(_mod)
Atom = _mod.Atom
EVENT_OUT = _mod.EVENT_OUT

CFG = {"risk_per_trade_pct": 1.0, "default_stop_pct": 0.5, "min_lot": 0.01,
       "max_lot": 1.0, "lot_step": 0.01}


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
        return AtomContext(atom_id=513, config=config, logger=_NullLogger(),
                           publish=self.publish, subscribe=self.subscribe)


def _account(equity):
    """ورقة ١٥ §٦ — حقوق الملكية من 654 لا من 619."""
    return {"account_id": "ACC", "broker": "MT5", "equity": equity}


def _specs(tick_value=1.0, tick_size=0.01, symbol="NQ100"):
    return {"account_id": "ACC", "broker": "MT5", "provider": "MT5", "symbols": [
        {"symbol": symbol, "contract_size": 1, "tick_value": tick_value,
         "tick_size": tick_size}]}


def _tick(price=100.0, symbol="NQ100"):
    return {"account_id": "ACC", "broker": "MT5", "symbol": symbol, "timeframe": "tick", "sequence": "0",
            "timestamp": 0.0, "price": price}


def _stop(buy_stop=None, sell_stop=None, symbol="NQ100"):
    return {"account_id": "ACC", "broker": "MT5", "symbol": symbol,
            "metadata": {"buy_stop": buy_stop, "sell_stop": sell_stop}}


async def _new(cfg=None, pair_risk_pct=1.0):
    bus = FakeEventBus()
    atom = Atom()
    await atom.initialize(bus.make_context(cfg or dict(CFG)))
    await atom.start()
    # ٢٠٢٦-١٠-٢٣ (القانون 7): مخاطرة الصفقة نسبة الزوج × الرصيد الابتدائيّ من حالة 509. هذه التجارب كُتبت على 100$ ثابتة،
    # فتُكتب لها النسبة 1٪ من 10,000 (= 100$) كما يكتبها المالك من «التحكّم»؛ والقيمة الأولى 0.50٪ تُختبر وحدها أدناه.
    if pair_risk_pct is not None:
        await atom._on_limits({"settings": {"pair_risk_pct": pair_risk_pct}})
    return atom, bus


async def test_trade_risk_is_the_pairs_share_of_the_initial_balance_2026_10_23():
    """القانون 7: ثابتة لا تراكميّة — 0.50٪ × 10,000 = 50$ بالقيم الأولى، ونسبة زوجٍ كتبها المالك تحكم زوجها وحده."""
    atom, bus = await _new(pair_risk_pct=None)
    await atom._on_truth_equity(_account(25000.0))     # الحقوق لا تغيّر المخاطرة
    await atom._on_specs(_specs())
    await atom._on_tick(_tick(100.0))
    assert _outs(bus)[-1]["metadata"]["max_trade_loss"] == 50.0
    await atom._on_limits({"settings": {"initial_balance": 10000, "pairs": {"NQ100": {"risk_pct": 0.25}}}})
    await atom._on_tick(_tick(100.0))
    assert _outs(bus)[-1]["metadata"]["max_trade_loss"] == 25.0


def _outs(bus):
    return [p for n, p in bus.published if n == EVENT_OUT]


async def test_computed_lot():
    print("\n--- test_computed_lot ---")
    atom, bus = await _new()
    await atom._on_truth_equity(_account(1000.0))
    # ٢٠٢٦-١٠-٠٨ (إصلاح الاختبارات القديمة بأمر المالك): الميزانيّة لم تعد ١٪ من حقوق الملكية (10$) بل 100$ ثابتة لكلّ صفقة (`FIXED_RISK_PER_TRADE` · حكم ٠٩-٠٦)، فكان اللوت 2.0 يُقصّ عند max_lot 1.0؛ وقيمة التِكّة 10 تُبقي المعادلة نفسها مرئيّةً تحت السقف.
    await atom._on_specs(_specs(tick_value=10.0))
    await atom._on_tick(_tick(100.0))
    last = _outs(bus)[-1]
    # ٢٠٢٦-١٠-٠٨ (إصلاح الاختبارات القديمة بأمر المالك): risk=100 ثابتة ; stop=100*0.5%=0.5 ; value_per_unit=10/0.01=1000 ; lot=100/(0.5*1000)=0.2
    assert last["metadata"]["lot"] == 0.2, last["metadata"]["lot"]
    assert last["metadata"]["risk_amount"] == 100.0
    assert last["metadata"]["max_trade_loss"] == 100.0
    # ٢٠٢٦-١٠-٠٨ (إصلاح الاختبارات القديمة بأمر المالك): ورصيدٌ أكبر مئة مرّة لا يغيّر الخسارة عند الوقف ولا اللوت — «١٪ = 100 دايمًا».
    rich, rich_bus = await _new()
    await rich._on_truth_equity(_account(100000.0))
    await rich._on_specs(_specs(tick_value=10.0))
    await rich._on_tick(_tick(100.0))
    assert _outs(rich_bus)[-1]["metadata"]["lot"] == 0.2
    assert _outs(rich_bus)[-1]["metadata"]["risk_amount"] == 100.0
    print(f"OK — لوت محسوب = {last['metadata']['lot']} (risk=100)")


async def test_clamp_to_max():
    print("\n--- test_clamp_to_max ---")
    atom, bus = await _new()
    await atom._on_truth_equity(_account(10000000.0))  # huge equity
    await atom._on_specs(_specs())
    await atom._on_tick(_tick(100.0))
    # ٢٠٢٦-٠٩-٠٦ (تصحيح المالك لنفسه): السقف نسبة من حقوق الملكية —
    # ١٪ — لا رقمٌ بعملة الحساب. برصيد ضخم تكبر الميزانية معه، فيعود
    # القصّ عند max_lot هو الحاكم كما كان أصلًا.
    assert _outs(bus)[-1]["metadata"]["lot"] == 1.0
    print("OK — قصّ عند max_lot=1.0 (السقف نسبة من الرصيد)")


async def test_no_equity_no_size():
    print("\n--- test_no_equity_no_size ---")
    atom, bus = await _new()
    await atom._on_specs(_specs())
    await atom._on_tick(_tick(100.0))
    assert len(_outs(bus)) == 0, "بلا Equity لا يحجّم"
    h = await atom.health_check()
    assert h.state == HealthState.DEGRADED and h.message == "NO_EQUITY_YET"
    print("OK — بلا Equity → لا تحجيم + DEGRADED")


async def test_no_specs_no_size():
    print("\n--- test_no_specs_no_size ---")
    atom, bus = await _new()
    await atom._on_truth_equity(_account(1000.0))
    await atom._on_tick(_tick(100.0))
    assert len(_outs(bus)) == 0, "بلا مواصفات لا يحجّم"
    print("OK — بلا مواصفات → لا تحجيم")


async def test_health_healthy():
    print("\n--- test_health_healthy ---")
    bus = FakeEventBus()
    atom = Atom()
    await atom.initialize(bus.make_context(dict(CFG)))
    assert (await atom.health_check()).state == HealthState.UNHEALTHY
    await atom.start()
    await atom._on_truth_equity(_account(1000.0))
    await atom._on_specs(_specs())
    await atom._on_tick(_tick(100.0))
    assert (await atom.health_check()).state == HealthState.HEALTHY
    print("OK — الصحة HEALTHY عند اكتمال المدخلات")


async def test_structure_lots():
    print("\n--- test_structure_lots ---")
    atom, bus = await _new()
    await atom._on_truth_equity(_account(1000.0))
    # ٢٠٢٦-١٠-٠٨ (إصلاح الاختبارات القديمة بأمر المالك): ميزانيّة 100$ ثابتة لا 10$، فقيمة التِكّة 10 تُعيد الأرقام نفسها تحت سقف اللوت.
    await atom._on_specs(_specs(tick_value=10.0))
    await atom._on_stop(_stop(buy_stop=99.0, sell_stop=101.0))
    await atom._on_tick(_tick(100.0))
    m = _outs(bus)[-1]["metadata"]
    # ٢٠٢٦-١٠-٠٨ (إصلاح الاختبارات القديمة بأمر المالك): buy: dist=100-99=1 ; value_per_unit=10/0.01=1000 ; lot=100/(1*1000)=0.1
    assert m["buy_lot"] == 0.1, m["buy_lot"]
    assert m["buy_stop"] == 99.0
    # sell: dist=101-100=1 ; lot=0.1
    assert m["sell_lot"] == 0.1, m["sell_lot"]
    assert m["sell_stop"] == 101.0
    # default lot still present (back-compat)
    assert m["lot"] == 0.2, m["lot"]
    print("OK — لوت هيكليّ buy/sell=0.1 + الافتراضيّ 0.2 محفوظ")


async def test_symbol_from_other_broker_is_rejected():
    """4.3.0: a unique contract under another broker is still unsafe."""
    print("\n--- test_symbol_from_other_broker_is_rejected ---")
    atom, bus = await _new()
    await atom._on_truth_equity(_account(1000.0))
    await atom._on_account({"account_id": "ACC", "broker": "ServerA"})
    bridge_specs = {"provider": "MT5", "symbols": [
        {"account_id": "ACC", "symbol": "NQ100", "contract_size": 1,
         "tick_value": 1.0, "tick_size": 0.01}]}
    await atom._on_specs(bridge_specs)
    await atom._on_tick({**_tick(100.0), "broker": "CompanyB"})
    assert not _outs(bus), "cross-broker contract must never size"
    rejected = [p for n, p in bus.published if n == _mod.EVENT_REJECTED]
    assert rejected[-1]["reason"] == "SIZING_UNAVAILABLE_FOR_SYMBOL"
    print("OK — مواصفة وسيط آخر تُرفض بلا تخمين")


async def test_symbol_fallback_ambiguous_stays_strict():
    """الوحدة ٢ (4.2.0): وسيطان مختلفان لنفس (الحساب·الرمز) = غموض — يبقى الرفض الصارم."""
    print("\n--- test_symbol_fallback_ambiguous_stays_strict ---")
    atom, bus = await _new()
    await atom._on_truth_equity(_account(1000.0))
    await atom._on_specs({"account_id": "ACC", "broker": "B1", "symbols": [
        {"symbol": "NQ100", "contract_size": 1, "tick_value": 1.0, "tick_size": 0.01}]})
    await atom._on_specs({"account_id": "ACC", "broker": "B2", "symbols": [
        {"symbol": "NQ100", "contract_size": 1, "tick_value": 1.0, "tick_size": 0.01}]})
    await atom._on_tick({**_tick(100.0), "broker": "B3"})
    assert not _outs(bus), "ambiguous broker fallback must not size"
    h = await atom.health_check()
    # ٢٠٢٦-٠٩-٠٩ (ختم المالك `NQ`): الرسالة صارت تحمل الحصيلة والرمز بأسمائه
    # بدل اسم السبب وحده — نطاقٌ واحد ناقص كان يبتلع خبر البقيّة، فيقرأ المالك
    # وقوفًا عامًّا بينما رمز آخر يُحجَّم بنجاح. الفحص هنا أقوى لا أضعف:
    # الحالة والسبب والرمز الناقص، ثلاثتها.
    assert h.state == HealthState.DEGRADED, h.state
    assert "SIZING_UNAVAILABLE_FOR_SYMBOL" in h.message, h.message
    assert "NQ100" in h.message, "الرمز الناقص يُسمّى لا يُخفى: %s" % h.message
    assert "sized=" in h.message, "الحصيلة تبقى مرئيّة: %s" % h.message
    # ٢٠٢٦-١٠-٠٨ (إصلاح الاختبارات القديمة بأمر المالك): عدّاد `symbol_fallback_sized` زال مع المطابقة الاحتياطيّة نفسها في 4.3.0 («منع استعمال مواصفات وسيط آخر» · التاريخ.md)؛ فالمحروس الآن أقوى: لا احتياط أصلًا، وصفرُ تحجيم، والنطاق الغامض مسمًّى بسببه.
    assert "symbol_fallback_sized" not in h.details, "عادت المطابقة الاحتياطيّة عبر الوسطاء: %r" % h.details
    assert h.details["emitted"] == 0, h.details
    assert h.details["unavailable_scopes"] == {"ACC|B3|NQ100": "SIZING_UNAVAILABLE_FOR_SYMBOL"}, h.details
    rejected = [p for n, p in bus.published if n == _mod.EVENT_REJECTED]
    assert rejected and rejected[-1]["reason"] == "SIZING_UNAVAILABLE_FOR_SYMBOL", rejected
    print("OK — وسيطان لنفس الرمز = رفض صارم بلا تخمين")


async def test_tick_teaches_broker_unsticks_pending():
    """الوحدة ٢ (4.2.0): مواصفات تصل قبل أي حالة حساب → تنتظر؛ أول تِكّة
    بهويّة كاملة تعلّم الوسيط وتُخزَّن المواصفة المنتظرة في نفس التِكّة."""
    print("\n--- test_tick_teaches_broker_unsticks_pending ---")
    atom, bus = await _new()
    await atom._on_truth_equity(_account(1000.0))
    bridge_specs = {"provider": "MT5", "symbols": [
        {"account_id": "ACC", "symbol": "NQ100", "contract_size": 1,
         "tick_value": 1.0, "tick_size": 0.01}]}
    await atom._on_specs(bridge_specs)              # no broker known yet -> pending
    h0 = await atom.health_check()
    assert h0.details["pending_specs"] == 1, h0.details
    assert not _outs(bus)
    await atom._on_tick(_tick(100.0))               # broker MT5 learned here
    outs = _outs(bus)
    assert outs and outs[-1]["status"] == "OK", "pending spec never unstuck"
    h1 = await atom.health_check()
    assert h1.details["pending_specs"] == 0, h1.details
    print("OK — التِكّة تُعلّم الوسيط وتُحرّر المواصفة المعلّقة في اللحظة نفسها")


async def main():
    tests = [test_computed_lot, test_clamp_to_max, test_no_equity_no_size,
             test_no_specs_no_size, test_health_healthy, test_structure_lots,
             test_symbol_from_other_broker_is_rejected,
             test_symbol_fallback_ambiguous_stays_strict,
             test_tick_teaches_broker_unsticks_pending]
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




def _dial(frac, symbol="NQ100"):
    """ملفّ العيار كما ينشره محرّك العيار ٥٢٣ — بحقوله هو."""
    return {"profiles": [{"account_id": "ACC", "broker": "MT5", "symbol": symbol,
                          "dial": 50.0, "stop_distance_frac": frac}], "count": 1}


async def test_dial_fraction_overrides_the_blind_default():
    """أمر المالك ٢٠٢٦-٠٩-١٣: أرقامه في محرّك العيار ٥٢٣ يجب أن تصل الوقف.

    كان تحجيم المركز ٥١٣ لا يشترك في ملفّ العيار، فيسدّ الفراغ بـ٠٫٥٪
    عمياء لكل الرموز: ٣٨٥$ على البيتكوين و١٤٧ نقطة على الناسداك، بينما
    أمر المالك ١٠٠$ و٥٠ نقطة.
    """
    atom, bus = await _new()
    await atom._on_truth_equity(_account(1000.0))
    await atom._on_specs(_specs())
    await atom._on_dial(_dial(0.001))          # 0.1% بدل 0.5%
    await atom._on_tick(_tick(100.0))
    meta = _outs(bus)[-1]["metadata"]
    # المسافة = 100 × 0.001 = 0.1 ⇒ لوت = 10 / (0.1 × 100) = 1.0
    assert meta["lot"] == 1.0, meta["lot"]
    assert meta["stop_basis"] == "DIAL_523", meta.get("stop_basis")
    print("OK — عيار المالك نافذ: لوت %s" % meta["lot"])


async def test_without_a_dial_the_default_still_applies():
    atom, bus = await _new()
    await atom._on_truth_equity(_account(1000.0))
    # ٢٠٢٦-١٠-٠٨ (إصلاح الاختبارات القديمة بأمر المالك): ميزانيّة 100$ ثابتة لا 10$، فقيمة التِكّة 10 تُبقي اللوت 0.2 = 100/(0.5×1000) تحت السقف بدل قصّه عند 1.0.
    await atom._on_specs(_specs(tick_value=10.0))
    await atom._on_tick(_tick(100.0))
    meta = _outs(bus)[-1]["metadata"]
    assert meta["lot"] == 0.2 and meta["stop_basis"] == "DEFAULT_PCT"
    print("OK — بلا عيار يبقى الاحتياطيّ")


async def test_malformed_dial_is_ignored():
    atom, bus = await _new()
    await atom._on_truth_equity(_account(1000.0))
    await atom._on_specs(_specs())
    await atom._on_dial({"profiles": [{"account_id": "ACC", "symbol": "NQ100",
                                       "stop_distance_frac": "x"}], "count": 1})
    await atom._on_dial({"profiles": "not-a-list"})
    await atom._on_tick(_tick(100.0))
    meta = _outs(bus)[-1]["metadata"]
    assert meta["stop_basis"] == "DEFAULT_PCT", meta.get("stop_basis")
    print("OK — عيار فاسد يُتجاهَل ولا يُسقط الذرّة")
if __name__ == "__main__":
    asyncio.run(main())
