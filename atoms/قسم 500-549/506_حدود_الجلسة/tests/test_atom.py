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
    "_atom506", _Path(__file__).resolve().parents[1] / "atom.py")
_mod = _ilu.module_from_spec(_spec)
sys.modules["_atom506"] = _mod
_spec.loader.exec_module(_mod)
Atom = _mod.Atom
EVENT_OUT = _mod.EVENT_OUT
EVENT_HALT_REQUEST = _mod.EVENT_HALT_REQUEST


class _NullLogger:
    def debug(self, *a): pass
    def info(self, *a): pass
    def warning(self, *a): pass
    def error(self, *a): pass
    def critical(self, *a): pass


class FakeEventBus:
    def __init__(self):
        self.published = []

    def subscribe(self, name, handler):
        pass

    async def publish(self, name, payload):
        self.published.append((name, payload))

    def make_context(self, cfg):
        return AtomContext(atom_id=506, config=cfg, logger=_NullLogger(),
                           publish=self.publish, subscribe=self.subscribe)


async def _new(loss=3.0, trades=2, dd=10.0):
    bus = FakeEventBus()
    atom = Atom()
    await atom.initialize(bus.make_context(
        {"max_session_loss_pct": loss, "max_session_trades": trades,
         "max_equity_drawdown_pct": dd}))
    await atom.start()
    return atom, bus


def _last(bus, name):
    hits = [p for n, p in bus.published if n == name]
    return hits[-1] if hits else None


async def test_session_trades_halt():
    print("\n--- test_session_trades_halt ---")
    atom, bus = await _new(trades=2)
    await atom._on_session({"signal": "london"})
    await atom._on_trade({"event_type": "OPENED", "account_id": "A1"})
    await atom._on_trade({"event_type": "OPENED", "account_id": "A1"})
    halt = _last(bus, EVENT_HALT_REQUEST)
    assert halt is not None and halt["reason"] == "MAX_SESSION_TRADES", halt
    print(f"OK — تجاوز صفقات الجلسة → halt: {halt['value']} ≥ {halt['limit']}")


async def test_session_loss_halt():
    print("\n--- test_session_loss_halt ---")
    atom, bus = await _new(loss=3.0)
    await atom._on_session({"signal": "london"})
    await atom._on_loss({"account_id": "A1", "loss_pct": 3.5, "completeness": "COMPLETE"})
    halt = _last(bus, EVENT_HALT_REQUEST)
    assert halt is not None and halt["reason"] == "SESSION_LOSS_LIMIT", halt
    print(f"OK — تجاوز خسارة الجلسة → halt: {halt['value']}% ≥ {halt['limit']}%")


async def test_drawdown_halt():
    print("\n--- test_drawdown_halt ---")
    atom, bus = await _new(dd=10.0)
    await atom._on_truth_equity({"account_id": "A1", "broker": "BR", "equity": 1000.0})  # peak — من 654
    await atom._on_truth_equity({"account_id": "A1", "broker": "BR", "equity": 850.0})   # -15%
    halt = _last(bus, EVENT_HALT_REQUEST)
    assert halt is not None and halt["reason"] == "EQUITY_DRAWDOWN_LIMIT", halt
    print(f"OK — سحب الحقوق → halt: {halt['value']}% ≥ {halt['limit']}%")


async def test_session_change_resets():
    print("\n--- test_session_change_resets ---")
    atom, bus = await _new(trades=5)
    await atom._on_session({"signal": "london"})
    await atom._on_trade({"event_type": "OPENED", "account_id": "A1"})
    await atom._on_session({"signal": "new_york"})  # session change → reset
    st = _last(bus, EVENT_OUT)
    assert st["session"] == "new_york" and st["session_trades"] == 0, st
    print("OK — تغيّر الجلسة يصفّر عدّاد صفقات الجلسة")


async def test_session_read_from_twin_merged_payload():
    # ٢٠٢٦-٠٩-٢٣: الحمولة كما تخرج حيًّا من ١٥٨ بعد توأمه — `signal` رقمٌ
    # اتّجاهيّ والجلسة في `metadata.pattern`. كانت تُقرأ `up` فلا تتبدّل الجلسة.
    print("\n--- test_session_read_from_twin_merged_payload ---")
    atom, bus = await _new(trades=5)
    await atom._on_session({"signal": "up", "metadata": {"pattern": "london", "twin": "candle"}})
    await atom._on_trade({"event_type": "OPENED", "account_id": "A1"})
    await atom._on_session({"signal": "up", "metadata": {"pattern": "new_york", "twin": "candle"}})
    st = _last(bus, EVENT_OUT)
    assert st["session"] == "new_york" and st["session_trades"] == 0, st
    print("OK — الجلسة من مفردة ١٥٨ لا من رقم التوأم، والتبدّل يصفّر")


async def test_ignores_non_time_session():
    print("\n--- test_ignores_non_time_session ---")
    atom, bus = await _new(trades=5)
    await atom._on_session({"signal": "london"})
    await atom._on_trade({"event_type": "OPENED", "account_id": "A1"})
    await atom._on_session({"signal": "crypto_24h"})  # ليست جلسة زمنيّة → تُتجاهَل
    st = _last(bus, EVENT_OUT)
    assert st["session"] == "london" and st["session_trades"] == 1, st
    print("OK — crypto_24h/open (خاصّة برمز) لا تغيّر الجلسة الزمنيّة")


async def test_duplicate_day_pulse_is_ignored_after_restore():
    atom, _ = await _new(trades=10)
    await atom._on_session({"signal": "london"})
    await atom._on_trade({"event_type": "OPENED", "account_id": "A1"})
    pulse = {"pulse_id": "SYS_MARKET_DAY|86400", "bucket_start": 86400.0,
             "official_time": 86400.0}
    await atom._on_day(pulse)
    await atom._on_trade({"event_type": "OPENED", "account_id": "A1"})
    assert atom._books["A1"]["session_trades"] == 1
    await atom._on_day(dict(pulse))
    assert atom._books["A1"]["session_trades"] == 1
    snap = await atom.snapshot()
    atom2, _ = await _new(trades=10)
    await atom2.restore(snap)
    await atom2._on_day(dict(pulse))
    assert atom2._books["A1"]["session_trades"] == 1


async def test_health_states():
    print("\n--- test_health_states ---")
    bus = FakeEventBus()
    atom = Atom()
    await atom.initialize(bus.make_context(
        {"max_session_loss_pct": 3.0, "max_session_trades": 2,
         "max_equity_drawdown_pct": 10.0}))
    assert (await atom.health_check()).state == HealthState.UNHEALTHY
    await atom.start()
    assert (await atom.health_check()).state == HealthState.DEGRADED  # no account
    await atom._on_truth_equity({"account_id": "A1", "broker": "BR", "equity": 1000.0})
    assert (await atom.health_check()).state == HealthState.HEALTHY
    print("OK — الصحة: UNHEALTHY → DEGRADED → HEALTHY")


async def test_session_change_releases_what_it_raised():
    """٢٠٢٦-٠٩-٠٦ (حكم المالك: «لازم يصير أوتوماتيك»).

    كان الخرق يزول عند تبدّل الجلسة **بصمت**، فيبقى مفتاح 516 مكسورًا
    وتجميد 519 قائمًا بلا أجل — مقيسًا: ثلاث ساعات بلا أمر. من رفع
    الخرق هو من يعلن زواله، موسومًا بمصدره وسببه.
    """
    print("\n--- test_session_change_releases_what_it_raised ---")
    atom, bus = await _new(trades=2)
    await atom._on_session({"signal": "london"})
    await atom._on_trade({"event_type": "OPENED", "account_id": "A1"})
    await atom._on_trade({"event_type": "OPENED", "account_id": "A1"})
    assert _last(bus, EVENT_HALT_REQUEST)["reason"] == "MAX_SESSION_TRADES"
    assert _last(bus, _mod.EVENT_RELEASE_REQUEST) is None, "أُفرج قبل زوال الخرق"

    await atom._on_session({"signal": "new_york"})
    rel = _last(bus, _mod.EVENT_RELEASE_REQUEST)
    assert rel is not None, "تبدّلت الجلسة ولم يُعلن الإفراج"
    assert rel["reason"] == "MAX_SESSION_TRADES", rel
    assert rel["origin"] == _mod.ORIGIN and rel["account_id"] == "A1", rel
    print(f"OK — تبدّل الجلسة → إفراج موسوم: {rel['reason']} من {rel['origin']}")


async def test_day_roll_releases_every_breach():
    print("\n--- test_day_roll_releases_every_breach ---")
    atom, bus = await _new(loss=3.0)
    await atom._on_session({"signal": "london"})
    await atom._on_loss({"account_id": "A1", "loss_pct": 3.5, "completeness": "COMPLETE"})
    assert _last(bus, EVENT_HALT_REQUEST)["reason"] == "SESSION_LOSS_LIMIT"
    await atom._on_day({"pulse_id": "SYS_MARKET_DAY|1", "bucket_start": 1.0})
    rel = _last(bus, _mod.EVENT_RELEASE_REQUEST)
    assert rel is not None and rel["reason"] == "SESSION_LOSS_LIMIT", rel
    print(f"OK — دوران اليوم → إفراج: {rel['reason']}")


async def test_restored_breach_is_reweighed_against_current_limit():
    """خرق مستعاد بحدّ قديم يُفرَج عنه عند الإقلاع بالحدّ الجديد.

    المقيس: عشر صفقات في جلسة آسيا رفعت MAX_SESSION_TRADES بسقف ١٠،
    ثم رُفع السقف إلى ٦٠ — ومع ذلك نجا الخرق إقلاعين ﻷنه يُستعاد كما هو.
    الخرق قولٌ بأن القيمة بلغت الحدّ، فيُعاد وزنه بالحدّ الحالي.
    """
    print("\n--- test_restored_breach_is_reweighed_against_current_limit ---")
    bus = FakeEventBus()
    atom = Atom()
    await atom.initialize(bus.make_context(
        {"max_session_loss_pct": 3.0, "max_session_trades": 60,
         "max_equity_drawdown_pct": 10.0}))
    await atom.restore({"version": _mod.ATOM_VERSION, "session": "asia",
                        "day_guard": {"event_name": "SYS_DAY"},
                        "books": {"A1": {"session_loss_pct": 0.25,
                                         "session_trades": 10,
                                         "drawdown_pct": 0.0,
                                         "breaches": ["MAX_SESSION_TRADES"]}}})
    assert "MAX_SESSION_TRADES" in atom._books["A1"]["breaches"]
    await atom.start()
    assert "MAX_SESSION_TRADES" in atom._books["A1"]["breaches"], \
        "أُفرج داخل start — يضيع قبل أن يشترك 516"
    assert _last(bus, _mod.EVENT_RELEASE_REQUEST) is None
    # بدء 516 — حامل المفتاح — هو موضع إعادة الوزن.
    await atom._on_atom_started({"atom_id": _mod.HALT_AUTHORITY_ID})
    assert "MAX_SESSION_TRADES" not in atom._books["A1"]["breaches"], \
        "الخرق بقي رغم أن الحدّ الجديد لم يُبلَغ"
    reasons = {p["reason"] for n, p in bus.published
               if n == _mod.EVENT_RELEASE_REQUEST}
    assert "MAX_SESSION_TRADES" in reasons, reasons
    # 506 يعلن كل سبب لا يدّعيه — وإلا بقي مفتاحٌ لسببٍ زال قبل نشر الإفراج.
    assert {"SESSION_LOSS_LIMIT", "EQUITY_DRAWDOWN_LIMIT"} <= reasons, reasons

    # المسار الحيّ: `platform.account.state` لا يصل 506 مقيسًا، فنبضة
    # الثانية هي التي تحمل التأجيلة — وبعد العدد المقرّر لا قبله.
    bus3 = FakeEventBus()
    atom3 = Atom()
    await atom3.initialize(bus3.make_context(
        {"max_session_loss_pct": 3.0, "max_session_trades": 60,
         "max_equity_drawdown_pct": 10.0}))
    await atom3.restore({"version": _mod.ATOM_VERSION, "session": "asia",
                         "day_guard": {"event_name": "SYS_DAY"},
                         "books": {"A1": {"session_loss_pct": 0.25,
                                          "session_trades": 10,
                                          "drawdown_pct": 0.0,
                                          "breaches": ["MAX_SESSION_TRADES"]}}})
    await atom3.start()
    # ذرّة أخرى بدأت — لا تعني شيئًا؛ السامع المقصود هو 516 وحده.
    await atom3._on_atom_started({"atom_id": 519})
    assert _last(bus3, _mod.EVENT_RELEASE_REQUEST) is None, \
        "سُحب الطلب قبل أن تسمع سلطة الإيقاف"
    await atom3._on_atom_started({"atom_id": _mod.HALT_AUTHORITY_ID})
    assert _last(bus3, _mod.EVENT_RELEASE_REQUEST) is not None, \
        "بدأت سلطة الإيقاف ولم يُسحب الطلب"
    assert "MAX_SESSION_TRADES" not in atom3._books["A1"]["breaches"]
    # ولا يتكرّر السحب: تأجيلة واحدة لا أكثر.
    count = len([1 for n, _ in bus3.published if n == _mod.EVENT_RELEASE_REQUEST])
    await atom3._on_atom_started({"atom_id": _mod.HALT_AUTHORITY_ID})
    for _ in range(_mod.REVALIDATE_AFTER_PULSES + 1):
        await atom3._on_clock({})
    assert len([1 for n, _ in bus3.published
                if n == _mod.EVENT_RELEASE_REQUEST]) == count, "تكرّر السحب"

    # وخرق ما زال صادقًا بالحدّ الحالي لا يُفرَج عنه.
    bus2 = FakeEventBus()
    atom2 = Atom()
    await atom2.initialize(bus2.make_context(
        {"max_session_loss_pct": 3.0, "max_session_trades": 10,
         "max_equity_drawdown_pct": 10.0}))
    await atom2.restore({"version": _mod.ATOM_VERSION, "session": "asia",
                         "day_guard": {"event_name": "SYS_DAY"},
                         "books": {"A1": {"session_loss_pct": 0.25,
                                          "session_trades": 12,
                                          "drawdown_pct": 0.0,
                                          "breaches": ["MAX_SESSION_TRADES"]}}})
    await atom2.start()
    await atom2._on_atom_started({"atom_id": _mod.HALT_AUTHORITY_ID})
    assert "MAX_SESSION_TRADES" in atom2._books["A1"]["breaches"], \
        "أُفرج عن خرق ما زال صادقًا"
    kept = {p["reason"] for n, p in bus2.published
            if n == _mod.EVENT_RELEASE_REQUEST}
    assert "MAX_SESSION_TRADES" not in kept, kept
    print("OK — 10<60 يُفرَج عنه؛ 12≥10 يبقى")


async def main():
    tests = [test_session_trades_halt, test_session_loss_halt, test_drawdown_halt,
             test_session_change_resets, test_session_read_from_twin_merged_payload,
             test_ignores_non_time_session,
             test_duplicate_day_pulse_is_ignored_after_restore, test_health_states,
             test_session_change_releases_what_it_raised,
             test_day_roll_releases_every_breach,
             test_restored_breach_is_reweighed_against_current_limit]
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
