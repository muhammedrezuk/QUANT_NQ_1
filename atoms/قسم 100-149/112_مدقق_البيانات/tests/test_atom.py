"""اختبارات 112 — بوّابة التِكّة المصدَّقة.

٢٠٢٦-٠٩-١٠: أُعيدت كتابتها. ما كان قبلها:

  * ملفّ من اثني عشر سطرًا بتحقّق واحد، و`async def main()` بلا دالّة
    `test_*` — فـ`pytest` **لا يجمعه إطلاقًا**. كان يُشغَّل باليد أو لا
    يُشغَّل، والذرّة تفحص 272,221 تِكّة في تشغيلة واحدة.
  * وناقله الوهميّ `def subscribe(self,*a): pass` **يبتلع الاشتراك**،
    والاختبار يستدعي `_on_tick` مباشرة. فلو تغيّر اسم الحدث الذي تشترك
    فيه الذرّة — أو انقطع مرجع المشترِك — لبقي أخضر والذرّة معزولة.
  * وحمولته `provider='MT5'`، وهو مزوّد **لا يبلغ `market.tick` أبدًا**
    (613 يحوّله إلى `market.broker_tick` بحكم المالك ٢٠٢٦-٠٨-٣١). أي
    أنّ الاختبار يصدّق على شكل لا ينشره ناشر.

القاعدتان المتّبعتان هنا: الناقل الوهميّ **يوصّل فعلًا**، والحمولة
**مبنيّة من كود الناشر** (613 `_forward`) لا من الخيال.
"""

import importlib.util as _ilu
import inspect
import sys
from pathlib import Path as _Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(_Path(__file__).resolve().parents[4]))

from core.contracts.atom import AtomContext, HealthState  # noqa: E402

_spec = _ilu.spec_from_file_location(
    "_atom112", _Path(__file__).resolve().parents[1] / "atom.py")
_mod = _ilu.module_from_spec(_spec)
sys.modules["_atom112"] = _mod
_spec.loader.exec_module(_mod)
Atom = _mod.Atom
EVENT_TICK = _mod.EVENT_TICK
EVENT_ACCOUNT = _mod.EVENT_ACCOUNT
EVENT_VALID = _mod.EVENT_VALID
EVENT_INVALID = _mod.EVENT_INVALID
EVENT_STATE = _mod.EVENT_STATE
CONTRACT_FIELDS = _mod.CONTRACT_FIELDS


class _NullLogger:
    def __getattr__(self, name):
        return lambda *a, **k: None


class FakeEventBus:
    """ناقل يوصّل فعلًا — لا يبتلع الاشتراك.

    لولا هذا لما كشف أيّ اختبار أن الذرّة اشتركت في اسم حدث خاطئ.
    """

    def __init__(self):
        self.published = []
        self._handlers = {}

    def subscribe(self, name, handler):
        self._handlers.setdefault(name, []).append(handler)

    async def publish(self, name, payload):
        self.published.append((name, payload))
        for handler in self._handlers.get(name, []):
            result = handler(payload)
            if inspect.isawaitable(result):
                await result

    def rows(self, name):
        return [p for n, p in self.published if n == name]

    def make_context(self):
        return AtomContext(atom_id=112, config={}, logger=_NullLogger(),
                           publish=self.publish, subscribe=self.subscribe)


def tick_from_publisher(**overrides):
    """حمولة `market.tick` كما يبنيها 613 `_forward` حرفيًّا.

    الحقول الثابتة من بناء الناشر، ثمّ `_IDENTITY_KEYS` التي يمرّرها من
    المصدر. و`provider='CTRADER'` لأنّ ميتاتريدر لا يصل هذا الحدث.
    """
    payload = {
        "symbol": "XAUUSD",
        "bid": 4398.10,
        "ask": 4398.35,
        "price": 4398.225,
        "volume": None,          # الفوركس بلا حجم — مقيس: 0 من 25 حزمة خام
        "provider": "CTRADER",
        "timestamp": 1789030846.089,
        "exchange_timestamp": 1789030846.089,
        "received_at": 1789030846.310,
        "account_id": "52992818",
        "broker": "Raw Trading Ltd",
        "sequence": 2788938,
        "top_changed": True,
        "book_empty": False,
        "sequence_gap": 0,
        "out_of_order": False,
        "fabric_gap": False,
    }
    payload.update(overrides)
    return payload


async def _started(bus=None):
    bus = bus or FakeEventBus()
    atom = Atom()
    await atom.initialize(bus.make_context())
    await atom.start()
    return atom, bus


async def test_subscription_is_wired_not_called_directly():
    """النشر على الناقل يبلغ الذرّة — لا استدعاء مباشر للمعالج."""
    atom, bus = await _started()
    await bus.publish(EVENT_TICK, tick_from_publisher())
    assert atom.checked_count == 1, "الذرّة غير موصولة بـmarket.tick"
    assert bus.rows(EVENT_VALID), "لم تُنشر التِكّة المصدَّقة"
    print("OK — الاشتراك موصول فعلًا (لا يبتلعه الوهميّ)")


async def test_contract_fields_cross_unchanged():
    """عقد الحقول يعبر كما جاء — يقرؤه أيضًا tests/test_market_decision_path."""
    atom, bus = await _started()
    raw = tick_from_publisher()
    await bus.publish(EVENT_TICK, raw)
    valid = bus.rows(EVENT_VALID)[-1]
    for field in CONTRACT_FIELDS:
        assert valid.get(field) == raw.get(field), field
    print("OK — عقد الحقول العشرة يعبر بلا تحريف")


async def test_crossed_spread_is_rejected_with_reason():
    """السبريد المقلوب — 99.6% من الرفض الحقيقيّ (12,663 من 12,714 مقيسة)."""
    atom, bus = await _started()
    await bus.publish(EVENT_TICK, tick_from_publisher(bid=4399.94, ask=4399.87))
    rejected = bus.rows(EVENT_INVALID)
    assert rejected, "التِكّة المقلوبة يجب أن تُرفض"
    assert "crossed_spread" in rejected[-1]["problems"], rejected[-1]["problems"]
    assert not bus.rows(EVENT_VALID), "لا تِكّة مصدَّقة من دفتر مقلوب"
    print("OK — ask < bid يُرفض بسبب معلن")


async def test_zero_spread_is_rejected_too():
    """`bid == ask` دفتر معطوب لا سوق — القاعدة موحّدة مع 103 و106 و115.

    قبل ٢٠٢٦-٠٩-٠٧ كان الشرط `ask < bid` فيمرّ السبريد الصفريّ هنا
    ويُرفض في مسار العمق. ومقيس على القرص: 1,989 تِكّة مقلوبة عبرت
    التصديق يوم 09-07 وحده، وصفر بعد توحيد القاعدة.
    """
    _, bus = await _started()
    await bus.publish(EVENT_TICK, tick_from_publisher(bid=4398.10, ask=4398.10))
    assert "crossed_spread" in bus.rows(EVENT_INVALID)[-1]["problems"]
    print("OK — السبريد الصفريّ مرفوض كالمقلوب")


async def test_missing_identity_is_named():
    """الرمز والحساب والمزوّد — كلّ ناقص يُسمّى بذاته لا برقم مجمل."""
    _, bus = await _started()
    await bus.publish(EVENT_TICK, tick_from_publisher(symbol="", account_id="",
                                                      provider=""))
    problems = bus.rows(EVENT_INVALID)[-1]["problems"]
    for expected in ("missing_symbol", "missing_account_id", "missing_provider"):
        assert expected in problems, (expected, problems)
    print("OK — النواقص تُسمّى واحدًا واحدًا")


async def test_nonfinite_price_is_rejected():
    _, bus = await _started()
    await bus.publish(EVENT_TICK, tick_from_publisher(bid=float("nan")))
    assert "invalid_or_missing_bid" in bus.rows(EVENT_INVALID)[-1]["problems"]
    print("OK — قيمة غير منتهية مرفوضة")


async def test_zero_is_on_the_reject_side_of_every_boundary():
    """الحدّ يُختبر **عنده** لا في وسطه — حكم المالك ٢٠٢٦-٠٩-١٦.

    أربع طفرات نجت من اختباراتي قبل هذا: `bid <= 0` ← `bid < 0`،
    و`price <= 0` ← `< 0`، و`stamp <= 0` ← `< 0`. كلّها تمرّ ما دام
    الاختبار يستعمل قيمة سالبة: السالب مرفوض في الحالتين. **الصفر
    وحده يفرّق** — وهو الحدّ نفسه.

    وسعرٌ صفريّ ليس فرضًا نظريًّا: `invalid_or_missing_*` وقعت 114 مرّة
    مقيسة على القرص بحمولات `bid=null · ask=null · price=null`.
    """
    _, bus = await _started()
    cases = (
        ({"bid": 0.0}, "nonpositive_bid"),
        ({"ask": 0.0}, "nonpositive_ask"),
        ({"price": 0.0}, "nonpositive_price"),
        ({"timestamp": 0.0}, "invalid_timestamp"),
    )
    for overrides, expected in cases:
        bus.published.clear()
        await bus.publish(EVENT_TICK, tick_from_publisher(**overrides))
        rejected = bus.rows(EVENT_INVALID)
        assert rejected, ("الصفر عند الحدّ يجب أن يُرفض", overrides)
        assert expected in rejected[-1]["problems"], (expected,
                                                      rejected[-1]["problems"])
        assert not bus.rows(EVENT_VALID), overrides
    print("OK — الصفر مرفوض عند كل حدّ: bid · ask · price · timestamp")


async def test_zero_volume_is_accepted_not_rejected():
    """الجانب الآخر من الحدّ: `volume == 0` **يمرّ**.

    طفرة `volume < 0` ← `volume <= 0` نجت لأنّ اختباري استعمل `-1`
    فقط. صفر حجمٍ رقمٌ مشروع (وهو ما تعطيه تغذية الفوركس فعليًّا حين
    تحمل الحقل)، ورفضه كان سيُسقط تِكّات سليمة بلا أن يشكو أحد.
    """
    _, bus = await _started()
    await bus.publish(EVENT_TICK, tick_from_publisher(volume=0.0))
    assert bus.rows(EVENT_VALID), "حجم صفر تِكّة سليمة لا مرفوضة"
    assert not bus.rows(EVENT_INVALID)
    print("OK — volume=0 يمرّ، والسالب وحده يُرفض")


async def test_null_volume_passes_because_forex_has_none():
    """`volume=None` ليس عطلًا: تغذية الفوركس بلا حجم — مقيس 0 من 25 حزمة."""
    atom, bus = await _started()
    await bus.publish(EVENT_TICK, tick_from_publisher(volume=None))
    assert bus.rows(EVENT_VALID), "الحجم الغائب لا يُسقط تِكّة"
    await bus.publish(EVENT_TICK, tick_from_publisher(volume=-1.0,
                                                      timestamp=1789030847.0))
    assert "negative_volume" in bus.rows(EVENT_INVALID)[-1]["problems"]
    print("OK — الحجم الغائب يمرّ والسالب يُرفض")


async def test_broker_is_enriched_from_account_state():
    """اسم الوسيط يُكمَّل من حالة الحساب ولا يُرفض بغيابه.

    الفرق عن 115 مقصود: 115 ترفض بـ`missing_broker`، و112 تُثري فقط.
    """
    atom, bus = await _started()
    await bus.publish(EVENT_ACCOUNT, {"account_id": "52992818",
                                      "broker": "Raw Trading Ltd"})
    raw = tick_from_publisher()
    raw.pop("broker")
    await bus.publish(EVENT_TICK, raw)
    valid = bus.rows(EVENT_VALID)[-1]
    assert valid["broker"] == "Raw Trading Ltd", valid.get("broker")
    print("OK — الوسيط يُكمَّل من platform.account.state")


async def test_health_message_names_reasons_and_worst_symbol():
    """توزيع الأسباب في `message` — النواة تحذف `details` قبل اللوحة.

    قبل ٢٠٢٦-٠٩-١٠ كان العدد وحده معلنًا (`invalid=5,723`) بلا سبب،
    فاستغرقت معرفة سبب واحد جلسةً كاملة وفتح `timeline.db`.
    """
    _, bus = await _started()
    await bus.publish(EVENT_TICK, tick_from_publisher())
    await bus.publish(EVENT_TICK, tick_from_publisher(
        symbol="EURUSD", bid=1.0805, ask=1.0804, price=1.08045))
    atom = None
    for handlers in bus._handlers.values():
        for handler in handlers:
            atom = getattr(handler, "__self__", atom)
    health = await atom.health_check()
    assert "crossed_spread=1" in health.message, health.message
    assert "EURUSD" in health.message, health.message
    assert health.details["problems"]["crossed_spread"] == 1
    print("OK — السبب والرمز الأسوأ يظهران في الرسالة المرئيّة")


async def test_rejection_carries_symbol_account_and_reason_at_root():
    """مستهلكا الرفض يقرآن من الجذر — لا من `payload`.

    مقيس على القرص قبل هذا الإصلاح: 294,784 صفّ رفضٍ في `timeline.db`،
    عمودا `symbol` و`account_id` فارغان **100%**، بينما 115 في القسم
    نفسه ممتلئان 100%. و831 يصنّف الحدث `CRITICAL` ويبحث عن تفصيله في
    `reason` فلا يجده، فيطلق إنذارًا حرجًا بلا سبب.

    هذا الاختبار يحرس الحقول الثلاثة في موضعها، ويحرس أنّ ما كان
    موجودًا لم يُحذف.
    """
    _, bus = await _started()
    await bus.publish(EVENT_TICK, tick_from_publisher(bid=4399.94, ask=4399.87))
    row = bus.rows(EVENT_INVALID)[-1]
    assert row["symbol"] == "XAUUSD", row.get("symbol")
    assert row["account_id"] == "52992818", row.get("account_id")
    assert "crossed_spread" in row["reason"], row.get("reason")
    # ولا شيء فُقد: القائمة والحمولة الكاملة باقيتان
    assert row["problems"] == ["crossed_spread"], row["problems"]
    assert row["payload"]["bid"] == 4399.94
    assert row["source_event"] == EVENT_TICK and row["status"] == "INVALID"
    print("OK — الرمز والحساب والسبب في الجذر، والقائمة والحمولة باقيتان")


async def test_reason_names_every_problem_not_just_the_first():
    """`reason` نصّ كامل — إنذار يذكر عيبًا واحدًا من ثلاثة يضلّل."""
    _, bus = await _started()
    await bus.publish(EVENT_TICK, tick_from_publisher(symbol="", account_id="",
                                                      provider=""))
    row = bus.rows(EVENT_INVALID)[-1]
    for expected in ("missing_symbol", "missing_account_id", "missing_provider"):
        assert expected in row["reason"], (expected, row["reason"])
    assert row["symbol"] == "" and row["account_id"] == ""
    print("OK — السبب يذكر كل العيوب لا أوّلها")


async def test_stop_is_announced():
    atom, bus = await _started()
    await atom.stop()
    assert bus.rows(EVENT_STATE)[-1]["status"] == "STOPPED"
    assert (await atom.health_check()).state == HealthState.UNHEALTHY
    print("OK — التوقّف يُعلن ولا يُكتم")
