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
    "_atom468", _Path(__file__).resolve().parents[1] / "atom.py")
_mod = _ilu.module_from_spec(_spec)
sys.modules["_atom468"] = _mod
_spec.loader.exec_module(_mod)
Atom = _mod.Atom

CFG = {"allowed_symbols": ["XAUUSD", "USTEC"]}


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
        return AtomContext(atom_id=468, config=config, logger=_NullLogger(),
                           publish=self.publish, subscribe=self.subscribe)


def _tick(symbol):
    return {"symbol": symbol, "account_id": "A", "broker": "BR", "sequence": "1"}


def _filters(bus):
    return [p for n, p in bus.published if n == "decision.filter.asset.state"]


def _whitelists(bus):
    return [p for n, p in bus.published if n == "allowed.symbols.state"]


async def _new(cfg=None):
    bus = FakeEventBus()
    atom = Atom()
    await atom.initialize(bus.make_context(dict(cfg if cfg is not None else CFG)))
    await atom.start()
    return atom, bus


async def test_allowed_symbol_passes():
    print("\n--- test_allowed_symbol_passes ---")
    atom, bus = await _new()
    await atom._on_tick(_tick("XAUUSD"))
    f = _filters(bus)[-1]
    assert f["symbol"] == "XAUUSD" and f["metadata"]["passed"] is True
    print("OK — رمز مسموح (XAUUSD) → passed=True")


async def test_blocked_symbol_fails():
    print("\n--- test_blocked_symbol_fails ---")
    atom, bus = await _new()
    await atom._on_tick(_tick("BTCUSD"))
    f = _filters(bus)[-1]
    assert f["symbol"] == "BTCUSD" and f["metadata"]["passed"] is False
    print("OK — رمز ممنوع (BTCUSD) → passed=False")


async def test_whitelist_published_on_start():
    print("\n--- test_whitelist_published_on_start ---")
    _atom, bus = await _new()
    w = _whitelists(bus)
    assert w and w[-1]["allowed"] == ["USTEC", "XAUUSD"]
    print("OK — القائمة البيضاء تُنشَر عند البدء (مرتّبة)")


async def test_empty_whitelist_blocks_all():
    print("\n--- test_empty_whitelist_blocks_all ---")
    atom, bus = await _new({"allowed_symbols": []})
    assert (await atom.health_check()).state == HealthState.DEGRADED
    await atom._on_tick(_tick("XAUUSD"))
    assert _filters(bus)[-1]["metadata"]["passed"] is False
    print("OK — قائمة فاضية → DEGRADED + يمنع الكلّ (fail-closed)")


async def test_unknown_command_does_not_partition_allowlist():
    print("\n--- test_unknown_command_does_not_partition_allowlist ---")
    atom, bus = await _new()
    await atom._on_asset_command({"symbol": "XAUUSD", "account_id": "A",
                                   "command": "BOGUS_TYPO"})
    assert "A" not in atom._allowed_by_account, (
        "أمر غير معروف أنشأ تقسيماً بالحساب رغم أنه لا يفعل شيئاً: %r"
        % atom._allowed_by_account)
    print("OK — أمر غير معروف لا يُنشئ تقسيماً بالحساب")


async def test_noop_recognized_command_does_not_partition_allowlist():
    print("\n--- test_noop_recognized_command_does_not_partition_allowlist ---")
    atom, bus = await _new()
    # PAUSE على رمز غائب أصلاً (BTCUSD ليس بالقائمة CFG) -- لا شيء يتغيّر.
    await atom._on_asset_command({"symbol": "BTCUSD", "account_id": "A",
                                   "command": "PAUSE"})
    assert "A" not in atom._allowed_by_account, (
        "أمر معروف بلا أثر فعلي أنشأ تقسيماً بالحساب: %r"
        % atom._allowed_by_account)
    print("OK — أمر معروف بلا أثر فعلي لا يُنشئ تقسيماً بالحساب")


async def test_unknown_command_does_not_desync_account_from_later_global_activation():
    print("\n--- test_unknown_command_does_not_desync_account_from_later_global_activation ---")
    atom, bus = await _new()
    # أمر غير معروف يصل بحدث مشترك -- قبل الإصلاح كان هذا وحده كافياً
    # لتجميد لقطة القائمة لهذا الحساب.
    await atom._on_asset_command({"symbol": "XAUUSD", "account_id": "A",
                                   "command": "BOGUS_TYPO"})
    # تفعيل عام (بلا account_id) يضيف رمزاً جديداً للقائمة العامة.
    await atom._on_activate({"symbol": "NEWSYM"})
    # الحساب A يجب أن يرى الرمز الجديد فوراً -- لا انشقاق صامت.
    await atom._on_tick(_tick("NEWSYM"))
    f = _filters(bus)[-1]
    assert f["symbol"] == "NEWSYM" and f["metadata"]["passed"] is True, (
        "الحساب A انشقّ صامتاً عن القائمة العامة بعد أمر غير معروف: %s" % f)
    print("OK — لا انشقاق صامت: الحساب يتبع القائمة العامة الحيّة بعد أمر غير معروف")


async def test_health_healthy():
    print("\n--- test_health_healthy ---")
    bus = FakeEventBus()
    atom = Atom()
    await atom.initialize(bus.make_context(dict(CFG)))
    assert (await atom.health_check()).state == HealthState.UNHEALTHY
    await atom.start()
    await atom._on_tick(_tick("XAUUSD"))
    assert (await atom.health_check()).state == HealthState.HEALTHY
    print("OK — الصحة: UNHEALTHY→HEALTHY")


async def test_allowed_symbols_are_named_in_the_message_not_only_details():
    """`details` يموت عند حدود النواة — واسم الأصل هو سطح قرار المالك.

    `core/api/app.py` (`_serialize_atom`) يُخرج من الصحّة `state` و`message`
    فقط. و`allowed=1` كان يخفي **أيّ** أصل هو المسموح، بينما قرار المالك
    نفسه هو ذاك الاسم (رمز واحد الآن، ثم يفعّل غيره بيده).
    """
    print("\n--- test_allowed_symbols_are_named_in_the_message_not_only_details ---")
    atom, _ = await _new()
    await atom._on_tick(_tick("XAUUSD"))
    msg = (await atom.health_check()).message
    for symbol in sorted(atom._allowed):
        assert symbol in msg, (symbol, msg)
    assert "allowed=%d" % len(atom._allowed) in msg, msg
    assert "accounts=" not in msg, "لا تُذكر تجزئة الحسابات ما لم توجد"
    print("OK — الأصل المسموح مسمًّى في الرسالة:", msg)


async def test_message_declares_account_partitions_when_they_exist():
    """تجزئة القائمة بحساب معيّن تغيّر من يمرّ فعلًا — فلا تبقى صامتة."""
    print("\n--- test_message_declares_account_partitions_when_they_exist ---")
    atom, _ = await _new()
    await atom._on_asset_command({"account_id": "52992818", "symbol": "XAUUSD",
                                  "command": "PAUSE"})
    await atom._on_tick(_tick("XAUUSD"))
    msg = (await atom.health_check()).message
    assert "52992818=" in msg, msg
    print("OK — التجزئة معلَنة في الرسالة:", msg)


async def test_owner_activation_appears_in_the_message_not_only_as_a_count():
    """تفعيل المالك من اللوحة يذهب إلى قائمة الحساب لا العامّة — فيجب أن يُرى.

    مقيس ٢٠٢٦-٠٩-١٠: `activate_asset` من اللوحة يحمل `account_id`، فـ
    `_on_activate` يضعه في `_allowed_by_account[<الحساب>]`. فعّل المالك
    XAUUSD · EURUSD · US30 · USTEC (أوامر الحوكمة 481-484) ودخل EURUSD
    صفقة حقيقية (تذكرة 1921540091)، بينما الرسالة كانت تقول
    `allowed=1 [BTCUSD] accounts=1` — أي عددٌ بلا أسماء يخفي قرار المالك
    نفسه. والقائمة الفعّالة لحسابه هي التي تحكم من يمرّ (`_on_tick`
    يرجّحها على العامّة)، فهي التي تُكتب.
    """
    print("\n--- test_owner_activation_appears_in_the_message_not_only_as_a_count ---")
    atom, _ = await _new()
    for symbol in ("XAUUSD", "EURUSD", "US30", "USTEC"):
        await atom._on_activate({"account_id": "52992818", "symbol": symbol})
    await atom._on_tick(_tick("EURUSD"))
    msg = (await atom.health_check()).message
    for symbol in ("XAUUSD", "EURUSD", "US30", "USTEC"):
        assert symbol in msg, (symbol, msg)
    # العدد يُقرأ من الحالة نفسها لا يُكتب رقمًا ثابتًا: إعداد الاختبار قد
    # يبدأ بقائمة عامّة غير فارغة، والتفعيل يبني فوقها.
    effective = atom._allowed_by_account["52992818"]
    assert "52992818=%d" % len(effective) in msg, msg
    assert "allowed=%d" % len(atom._allowed) in msg, "والقائمة العامّة تبقى معلَنة"
    assert msg.index("allowed=") < msg.index("52992818="), "العامّة أولًا ثم الحسابات"
    print("OK — أصول المالك المفعَّلة مسمّاة:", msg)


async def test_account_and_symbol_overflow_are_declared():
    """السقوف تُحترم في الحسابات والرموز معًا، والفائض يُعلن لا يُكتم."""
    print("\n--- test_account_and_symbol_overflow_are_declared ---")
    atom, _ = await _new()
    for i in range(_mod._MAX_NAMED_ACCOUNTS + 2):
        await atom._on_activate({"account_id": "ACC%02d" % i, "symbol": "S%02d" % i})
    for i in range(_mod._MAX_NAMED_SYMBOLS + 2):
        await atom._on_activate({"account_id": "ACC00", "symbol": "X%02d" % i})
    await atom._on_tick(_tick("XAUUSD"))
    msg = (await atom.health_check()).message
    assert "+2 حسابًا" in msg, msg
    assert ",+" in msg.split("ACC00=")[1], "وفائض الرموز معلَن أيضًا"
    print("OK — فائض الحسابات والرموز معلَن:", msg)


async def test_owner_activation_survives_a_hot_reload():
    """قائمة المالك حالةٌ وضعها بيده — فلا تُنسى عند إعادة تحميل أو إقلاع.

    مقيس ٢٠٢٦-٠٩-١٠ (بثمنه): فعّل المالك أربعة أصول من اللوحة ودخل EURUSD
    صفقة حقيقية (تذكرة 1921540091)، ثم مسحَتها إعادةُ تحميل ساخنة لأنّ
    الذرّة كانت بلا حفظ — فعاد `allowed=1 [BTCUSD]` وحُجب ٩٧–١٠٠٪ من
    الرموز الأربعة خلال دقيقة واحدة. وأيّ إقلاع للمنصّة كان سيفعلها.
    """
    print("\n--- test_owner_activation_survives_a_hot_reload ---")
    # الحساب هو حساب التِكّة نفسه (`_tick` يرسل "A") — فالمسار مُثبَت من
    # طرفٍ لطرف: تفعيلٌ بحساب، ثم إقلاع، ثم تِكّة من ذلك الحساب تمرّ.
    account = _tick("X")["account_id"]
    atom, _ = await _new()
    for symbol in ("EURUSD", "US30"):
        await atom._on_activate({"account_id": account, "symbol": symbol})
    await atom._on_activate({"symbol": "GLOBALSYM"})
    saved = await atom.snapshot()

    fresh, _bus = await _new()                       # ذرّة جديدة كأنّها أُقلعت
    assert "EURUSD" not in fresh._allowed_by_account.get(account, set())
    await fresh._on_tick(_tick("EURUSD"))
    assert _filters(_bus)[-1]["metadata"]["passed"] is False, "قبل الاستعادة: محجوب"

    await fresh.restore(saved)
    assert "GLOBALSYM" in fresh._allowed, "التفعيل العامّ يعود"
    for symbol in ("EURUSD", "US30"):
        assert symbol in fresh._allowed_by_account[account], symbol
    await fresh._on_tick(_tick("EURUSD"))
    assert _filters(_bus)[-1]["metadata"]["passed"] is True, "وبعدها يمرّ فعلًا"
    print("OK — تفعيل المالك نجا إعادة التحميل")


async def test_restore_keeps_a_live_pause_and_picks_up_new_manifest_symbols():
    """فقدُ إيقافٍ أخطر من فقد تفعيل — فالـ`PAUSE` يبقى بعد الاستعادة.

    وفي المقابل: ما يضيفه المالك إلى المانيفست **بعد** أخذ اللقطة يدخل،
    فلا تطغى لقطة قديمة على تعديله (نفس عائلة علّة 1.5.0: لقطة مجمَّدة
    تحجب إضافة لاحقة إلى الأبد).
    """
    print("\n--- test_restore_keeps_a_live_pause_and_picks_up_new_manifest_symbols ---")
    atom, _ = await _new()
    paused = sorted(atom._allowed)[0]
    await atom._on_asset_command({"symbol": paused, "command": "PAUSE"})
    assert paused not in atom._allowed
    saved = await atom.snapshot()

    cfg = dict(CFG)
    cfg["allowed_symbols"] = sorted(set(cfg["allowed_symbols"]) | {"NEWSYM"})
    fresh, _bus = await _new(cfg)
    await fresh.restore(saved)
    assert paused not in fresh._allowed, "الإيقاف الحيّ يبقى"
    assert "NEWSYM" in fresh._allowed, "وإضافة المانيفست الجديدة تدخل"
    print("OK — الإيقاف محفوظ، وإضافة المانيفست ملتقَطة")


async def test_invalid_snapshot_is_declared_in_the_message():
    """لقطة فاسدة تعني عودة القائمة إلى المانيفست — أي ضياع تفعيل المالك.

    لا تُبتلع صامتة: تُعلَن في `message` لأنّ `details` يموت عند حدود النواة.
    """
    print("\n--- test_invalid_snapshot_is_declared_in_the_message ---")
    atom, _ = await _new()
    await atom.restore({"allowed": "ليست قائمة"})
    await atom._on_tick(_tick("XAUUSD"))
    msg = (await atom.health_check()).message
    assert _mod.RESTORE_INVALID in msg, msg
    print("OK — فشل الاستعادة منطوق:", msg)


async def main():
    tests = [test_allowed_symbol_passes, test_blocked_symbol_fails,
             test_owner_activation_survives_a_hot_reload,
             test_restore_keeps_a_live_pause_and_picks_up_new_manifest_symbols,
             test_invalid_snapshot_is_declared_in_the_message,
             test_allowed_symbols_are_named_in_the_message_not_only_details,
             test_message_declares_account_partitions_when_they_exist,
             test_owner_activation_appears_in_the_message_not_only_as_a_count,
             test_account_and_symbol_overflow_are_declared,
             test_whitelist_published_on_start, test_empty_whitelist_blocks_all,
             test_unknown_command_does_not_partition_allowlist,
             test_noop_recognized_command_does_not_partition_allowlist,
             test_unknown_command_does_not_desync_account_from_later_global_activation,
             test_health_healthy]
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
