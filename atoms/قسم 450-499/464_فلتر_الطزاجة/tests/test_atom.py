import asyncio
import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from pathlib import Path as _Path
sys.path.insert(0, str(_Path(__file__).resolve().parents[4]))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.pop("QUANT_REPLAY_CLOCK", None)

from core.contracts.atom import AtomContext, HealthState  # noqa: E402
import importlib.util as _ilu  # noqa: E402

_spec = _ilu.spec_from_file_location(
    "_atom464", _Path(__file__).resolve().parents[1] / "atom.py")
_mod = _ilu.module_from_spec(_spec)
sys.modules["_atom464"] = _mod
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

    def subscribe(self, name, handler):
        pass

    async def publish(self, name, payload):
        self.published.append((name, payload))

    def make_context(self, cfg):
        return AtomContext(atom_id=464, config=cfg, logger=_NullLogger(),
                           publish=self.publish, subscribe=self.subscribe)


# حمولة `market.tick.validated` كما يبنيها ناشرها فعلًا — لا كما نتخيّلها.
# ١١٢ (`مدقق_البيانات`) يمرّر التِكّة الواردة كما هي ويضيف `broker` من
# `platform.account.state`؛ وحقوله المعلَنة في رأس ملفه:
#   symbol · bid · ask · price · volume · provider · timestamp ·
#   exchange_timestamp · received_at · account_id   (+ broker المضاف)
# الدرس الذي دفعنا ثمنه: اختبار يبني حمولة لا ينشرها ناشرها يبقى أخضر
# والذرّة ميتة حيًّا.
def _tick(symbol="BTCUSD", *, exchange_timestamp=None, account_id="52992818",
          broker="Raw Trading Ltd", timestamp=None, received_at=None,
          with_exchange_stamp=True):
    payload = {
        "symbol": symbol,
        "bid": 78484.7,
        "ask": 78489.7,
        "price": 78487.2,
        "volume": 0.0,
        "provider": "CTRADER",
        "timestamp": timestamp,
        "account_id": account_id,
        "broker": broker,
    }
    if received_at is not None:
        payload["received_at"] = received_at
    if with_exchange_stamp:
        payload["exchange_timestamp"] = exchange_timestamp
    return payload


def _cfg(threshold=180.0):
    return {"stale_threshold_s": threshold}


async def _new(threshold=180.0, official_time=1000.0):
    bus = FakeEventBus()
    atom = Atom()
    await atom.initialize(bus.make_context(_cfg(threshold)))
    await atom.start()
    atom._official_time = official_time
    return atom, bus


def _rows(bus, symbol=None):
    return [p for n, p in bus.published
            if n == EVENT_OUT and (symbol is None or p["symbol"] == symbol)]


def _verdict(bus, symbol):
    hits = _rows(bus, symbol)
    return hits[-1]["metadata"]["passed"] if hits else None


async def test_stale_blocked_fresh_pass():
    print("\n--- test_stale_blocked_fresh_pass ---")
    atom, bus = await _new(threshold=180.0, official_time=1000.0)
    await atom._on_tick(_tick("LIVE", exchange_timestamp=990.0))    # عمر 10
    await atom._on_tick(_tick("STOCK", exchange_timestamp=500.0))   # عمر 500
    assert _verdict(bus, "STOCK") is False, "STOCK يجب أن يُحجب"
    assert _verdict(bus, "LIVE") is True, "LIVE يجب أن يمرّ"
    assert _rows(bus, "STOCK")[-1]["metadata"]["age_s"] == 500.0
    print("OK — البايت يُحجب، الحيّ يمرّ")


async def test_all_fresh_all_pass():
    print("\n--- test_all_fresh_all_pass ---")
    atom, bus = await _new(threshold=180.0, official_time=1000.0)
    for s, t in (("A", 1000.0), ("B", 1000.0), ("C", 999.0)):
        await atom._on_tick(_tick(s, exchange_timestamp=t))
    for s in ("A", "B", "C"):
        assert _verdict(bus, s) is True, s
    print("OK — كلها حيّة → كلها تمرّ")


async def test_emits_on_every_tick():
    """حكم المالك ٢٠٢٦-٠٨-١٦: الحكم ينتهي بانتهاء القراءة التي أنتجته.

    كان النشر عند انقلاب الحكم فقط — و٤٥٤ يخزّن حكم الرمز **بلا إطار زمنيّ**،
    فبقي `False` واحد حاكمًا للأبد. المقيس حيًّا وقتها: `reads=281 emitted=8`
    بينما ٤٥٤ مرّر **صفرًا من ٣٨٦**. فصار النشر على كل تِكّة، لا على التغيّر.
    """
    print("\n--- test_emits_on_every_tick ---")
    atom, bus = await _new(threshold=180.0, official_time=1000.0)
    await atom._on_tick(_tick("X", exchange_timestamp=1000.0))
    await atom._on_tick(_tick("Y", exchange_timestamp=400.0))
    assert len(bus.published) == 2
    await atom._on_tick(_tick("X", exchange_timestamp=1000.0))   # نفس الحكم
    await atom._on_tick(_tick("Y", exchange_timestamp=400.0))
    assert len(bus.published) == 4, "كل تِكّة تُجدّد الحكم ولو لم يتغيّر"
    atom._official_time = 1001.0
    await atom._on_tick(_tick("Y", exchange_timestamp=1000.0))    # Y صار حيًّا
    assert _verdict(bus, "Y") is True
    assert len(bus.published) == 5
    print("OK — حكم لكل تِكّة، فلا يبقى حظر قديم حاكمًا")


async def test_verdict_is_published_under_the_tick_account_scope():
    """النطاق الذي يقرأه ٤٥٤ فعلًا هو `(account_id, symbol)`.

    ٤٥٤ يدمج في `_symbol_records` بترتيب `("*", symbol)` ثم `(account, symbol)`،
    والأخير يطغى. فحكمٌ يُنشر بحساب `"*"` لا يصل إلى أي قرار ما دامت التِكّات
    الحيّة تجري. هذا ما قتل المسار القرصي المتقاعد صامتًا، وهذا حارسه.
    """
    print("\n--- test_verdict_is_published_under_the_tick_account_scope ---")
    atom, bus = await _new(threshold=180.0, official_time=1000.0)
    await atom._on_tick(_tick("BTCUSD", exchange_timestamp=999.0,
                              account_id="52992818"))
    row = _rows(bus, "BTCUSD")[-1]
    assert row["account_id"] == "52992818", row["account_id"]
    assert row["broker"] == "Raw Trading Ltd"
    assert ("52992818", "BTCUSD") in atom._verdict
    print("OK — الحكم بنطاق حساب التِكّة، وهو ما يرجّحه ٤٥٤")


async def test_missing_stamp_blocks_and_is_counted_never_invented():
    """A8: قياس حقيقي أو لا شيء — لا يُخترع عمرٌ لتِكّة بلا طابع."""
    print("\n--- test_missing_stamp_blocks_and_is_counted_never_invented ---")
    atom, bus = await _new(threshold=180.0, official_time=1000.0)
    await atom._on_tick(_tick("NOSTAMP", with_exchange_stamp=False))
    row = _rows(bus, "NOSTAMP")[-1]
    assert row["metadata"]["passed"] is False
    assert row["metadata"]["age_s"] is None, "العمر يبقى None لا صفرًا"
    assert atom._no_stamp == 1
    assert (await atom.health_check()).details["no_stamp"] == 1
    print("OK — بلا طابع: يُحجب، ويُعدّ، ولا يُخترع رقم")


async def test_lag_vs_newest_is_information_not_a_barrier():
    """`price_staleness_vs_newest` عاد معلومةً من التِكّة الحيّة لا من قاعدة.

    مقيس ٢٠٢٦-٠٩-٠٩ على الرموز السبعة الحيّة: الفارق بين أحدث رمز وأقدمه
    ٧٨٫٧ ثانية — أي أنّ المقارنة عبر الرموز لا تحجب شيئًا اليوم. تُنشر رقمًا
    تقرأه اللوحة، والحجب يبقى على العمر المطلق وحده.
    """
    print("\n--- test_lag_vs_newest_is_information_not_a_barrier ---")
    atom, bus = await _new(threshold=180.0, official_time=1000.0)
    await atom._on_tick(_tick("FAST", exchange_timestamp=1000.0))
    await atom._on_tick(_tick("SLOW", exchange_timestamp=920.0))
    row = _rows(bus, "SLOW")[-1]
    assert row["metadata"]["passed"] is True, "عمره المطلق ٨٠ث < ١٨٠ فيمرّ"
    assert row["metadata"]["age_s"] == 80.0
    assert row["metadata"]["lag_vs_newest_s"] == 80.0, "ويُعلن تأخّره خلف الأسرع"
    print("OK — التأخّر خلف الأحدث رقمٌ مُعلَن، لا حاجز")


async def test_replay_clock_uses_newest_data_stamp():
    """`QUANT_REPLAY_CLOCK=1`: المرجع أحدث طابع بيانات مرّ لا الساعة الرسمية."""
    print("\n--- test_replay_clock_uses_newest_data_stamp ---")
    os.environ["QUANT_REPLAY_CLOCK"] = "1"
    try:
        atom, bus = await _new(threshold=5.0, official_time=9_999_999.0)
        await atom._on_tick(_tick("HIST", exchange_timestamp=1000.0))
        assert _verdict(bus, "HIST") is True, "شريط تاريخي لا يُحجب في الإعادة"
        assert _rows(bus, "HIST")[-1]["metadata"]["age_s"] == 0.0
    finally:
        os.environ.pop("QUANT_REPLAY_CLOCK", None)
    print("OK — وضع الإعادة يقيس مقابل أحدث بيانات، لا مقابل اليوم")


async def test_no_bridge_database_is_opened():
    """المسار القرصي متقاعد: لا `db_path` ولا `table_name` ولا اتصال sqlite.

    الإعداد كان يفتح ملف الجسر (٦٩٫٩ م.ب) ويمسح جدولًا كاملًا كل خمس ثوانٍ،
    وهو الملف نفسه الذي يكتب فيه الإكسبرت — وينتج `reads=0` أبدًا.
    """
    print("\n--- test_no_bridge_database_is_opened ---")
    src = (_Path(__file__).resolve().parents[1] / "atom.py").read_text(encoding="utf-8")
    assert "import sqlite3" not in src, "لا استيراد sqlite3"
    assert "sqlite3.connect" not in src, "لا اتصال بقاعدة"
    atom, _ = await _new()
    assert not hasattr(atom, "_db_path") and not hasattr(atom, "_table")
    manifest = (_Path(__file__).resolve().parents[1] / "manifest.yaml").read_text(
        encoding="utf-8")
    for key in ("db_path", "table_name", "poll_interval_s"):
        assert key not in manifest, f"{key} ما زال في المانيفست"
    assert "nq_brain.db" not in manifest
    print("OK — لا قاعدة جسر، ولا إعداد ميت في المانيفست")


async def test_health_states():
    print("\n--- test_health_states ---")
    bus = FakeEventBus()
    atom = Atom()
    await atom.initialize(bus.make_context(_cfg()))
    assert (await atom.health_check()).state == HealthState.UNHEALTHY
    await atom.start()
    atom._official_time = 1000.0
    degraded = await atom.health_check()
    assert degraded.state == HealthState.DEGRADED
    assert degraded.message == "NO_TICK_YET"
    await atom._on_tick(_tick("A", exchange_timestamp=1000.0))
    healthy = await atom.health_check()
    assert healthy.state == HealthState.HEALTHY
    assert "live=1" in healthy.message and "no_stamp=0" in healthy.message
    print("OK — الصحة: UNHEALTHY -> DEGRADED -> HEALTHY")


async def test_stale_symbols_are_named_in_the_message_not_only_details():
    """`details` يموت عند حدود النواة — الاسم يجب أن يكون في `message`.

    `core/api/app.py` (`_serialize_atom`) يُخرج من الصحّة `state` و`message`
    فقط، فما يوضع في `details` لا يبلغ اللوحة ولا `/api/atoms`. و`blocked=7`
    وحده لا يقول أيّ سبعة — وهو السؤال الوحيد القابل للتصرّف هنا.
    """
    print("\n--- test_stale_symbols_are_named_in_the_message_not_only_details ---")
    atom, _ = await _new(threshold=180.0, official_time=1000.0)
    await atom._on_tick(_tick("BTCUSD", exchange_timestamp=1000.0))
    assert "stale=" not in (await atom.health_check()).message, "لا لاحقة بلا حجب"
    await atom._on_tick(_tick("EURUSD", exchange_timestamp=100.0))
    await atom._on_tick(_tick("XAUUSD", exchange_timestamp=100.0))
    msg = (await atom.health_check()).message
    assert "blocked=2" in msg, msg
    assert "stale=EURUSD,XAUUSD" in msg, msg
    assert "BTCUSD" not in msg.split("stale=")[1], "الحيّ لا يُسمّى بايتًا"
    print("OK — الرمز البايت مسمًّى في الرسالة نفسها")


async def test_named_stale_list_is_capped_and_overflow_declared():
    """الرسالة تُعرض على اللوحة فلا تكبر بلا حدّ — والفائض يُعلن لا يُكتم."""
    print("\n--- test_named_stale_list_is_capped_and_overflow_declared ---")
    atom, _ = await _new(threshold=180.0, official_time=1000.0)
    for i in range(_mod._MAX_NAMED_STALE + 3):
        await atom._on_tick(_tick("SYM%02d" % i, exchange_timestamp=100.0))
    msg = (await atom.health_check()).message
    listed = msg.split("stale=")[1]
    assert listed.count(",") == _mod._MAX_NAMED_STALE, msg
    assert listed.endswith(",+3"), msg
    print("OK — سقف الأسماء محترم والفائض معلَن بعدده")


async def test_blocked_scopes_are_named_in_health():
    print("\n--- test_blocked_scopes_are_named_in_health ---")
    atom, _ = await _new(threshold=180.0, official_time=1000.0)
    await atom._on_tick(_tick("GOOD", exchange_timestamp=1000.0))
    await atom._on_tick(_tick("BAD", exchange_timestamp=100.0))
    details = (await atom.health_check()).details
    assert details["blocked_now"] == 1
    assert ["52992818", "BAD"] in details["blocked_scopes"]
    assert details["threshold_s"] == 180.0
    print("OK — الصحة تسمّي النطاق المحجوب وعتبته")


async def main():
    tests = [test_stale_blocked_fresh_pass, test_all_fresh_all_pass,
             test_emits_on_every_tick,
             test_verdict_is_published_under_the_tick_account_scope,
             test_missing_stamp_blocks_and_is_counted_never_invented,
             test_lag_vs_newest_is_information_not_a_barrier,
             test_replay_clock_uses_newest_data_stamp,
             test_no_bridge_database_is_opened,
             test_health_states,
             test_stale_symbols_are_named_in_the_message_not_only_details,
             test_named_stale_list_is_capped_and_overflow_declared,
             test_blocked_scopes_are_named_in_health]
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
