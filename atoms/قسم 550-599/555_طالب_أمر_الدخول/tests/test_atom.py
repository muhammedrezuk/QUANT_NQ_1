"""اختبارات طالب أمر الدخول 555 — يجمع ولا يحكم، ولا يفتح مركزًا ثانيًا."""
from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
# ٢٠٢٦-١٠-٠١ (v1.24.1): الذرّة تستورد ملفّاتها الشقيقة (`entry_request_*`)،
# والنواةُ تضع مجلّدها في المسار عند التحميل — فيضعه الاختبار كذلك.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

_spec = importlib.util.spec_from_file_location(
    "atom_555", Path(__file__).resolve().parents[1] / "atom.py")
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)

import entry_request_sizing as _sizing  # noqa: E402
import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _floor_for_toy_prices(monkeypatch):
    """٢٠٢٦-١٠-١٧ (ختم المالك «nq»: البِب على كلّ السستم): أسعار هذا الملفّ لعبة — بتكوين على 100 ووقفه 98، أي 2 بِب، وحدّ البتكوين
    الحقيقيّ 82 بِبًا فيُردّ كلّ قرارٍ هنا. وهذه الاختبارات للمسار (قرار ⟵ طلب أمر) لا للحدّ؛ والحدّ مختبرٌ وحده في
    `test_fix_2026_10_02.py` بأرقامٍ حقيقيّة. فيُثبَّت الحدّ هنا على 1 بِب، كما كانت الـ200 نقطة أساس فوق حدّها القديم."""
    monkeypatch.setattr(_sizing, "min_stop_pips", lambda symbol: 1.0)
    # ٢٠٢٦-١٠-٢٣: والكلفة المتوقّعة (انزلاق البتكوين المقيس × السعر) على سعر لعبةٍ 100 وسبريدٍ صفر تقلب اللوت من 0.05 إلى 0.04 عند
    # حدّ الخطوة — فتُثبَّت هنا على السبريد وحده. والكلفة مختبرةٌ وحدها بأرقامٍ حقيقيّة في `test_red_lines_2026_10_23.py`.
    monkeypatch.setattr(_sizing.execution_costs, "crossing_cost", lambda *a, **k: 0.0)

CFG = {"size_stale_after_s": 30.0, "target_stale_after_s": 30.0,
       "max_open_per_symbol": 0, "inflight_ttl_s": 90.0, "min_reward_multiple": 3.0}


class Bus:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    async def publish(self, name: str, payload: dict | None = None) -> None:
        self.events.append((name, payload or {}))

    def subscribe(self, name: str, handler: Any) -> None:
        pass

    def of(self, name: str) -> list[dict]:
        return [p for n, p in self.events if n == name]


def build(positions=(), **overrides):
    from core.contracts.atom import AtomContext
    bus = Bus()
    atom = mod.Atom()
    ctx = AtomContext(atom_id=555, config={**CFG, **overrides}, logger=None,
                      publish=bus.publish, subscribe=bus.subscribe,
                      subscribe_all=lambda h: None)
    asyncio.run(atom.initialize(ctx))
    asyncio.run(atom.start())
    asyncio.run(atom._on_account({"account_id": "ACC", "broker": "BR"}))
    # لقطة مراكز فارغة: الحال الطبيعيّة «لا مركز مفتوح». بدونها ترفض
    # الذرّة كل دخول بـPOSITIONS_UNKNOWN — وهو المقصود، ويختبره
    # `test_entry_is_refused_until_positions_are_known` وحده.
    if positions is not None:
        asyncio.run(atom._on_positions({"positions": list(positions)}))
    return atom, bus


def size(buy_lot=0.10, buy_stop=99.0, sell_lot=0.10, sell_stop=101.0,
         close=100.0) -> dict:
    return {"account_id": "ACC", "broker": "BR", "symbol": "BTCUSD",
            "buy_lot": buy_lot, "buy_stop": buy_stop,
            "sell_lot": sell_lot, "sell_stop": sell_stop,
            "close": close, "max_trade_loss": 100.0, "default_distance": 0.5,
            # ٢٠٢٦-١٠-٠٨ (إصلاح الاختبارات القديمة بأمر المالك): اللوت يُعاد حسابه على وقف التحليل (أمر ٢٠٢٦-٠٩-١٨ · `_lot_for_stop`) فيلزم ما ينشره 513 لذلك: قيمة النقطة وخطوة اللوت والسبريد — 10$ لكلّ 0.01 ⟸ 1000$ للنقطة لكلّ لوت، فلوت 513 (0.10) على وقفه 99 = 100$ ÷ 1000.
            "risk_amount": 100.0, "tick_value": 10.0, "tick_size": 0.01, "spread": 0.0,
            "commission_per_lot": 0.0, "volume_step": 0.01, "volume_min": 0.01,
            "volume_max": 50.0}


# ٢٠٢٦-١٠-٠٨ (إصلاح الاختبارات القديمة بأمر المالك): هدف 526 لم يعد يدخل 555 — أمر المالك ٢٠٢٦-٠٩-١٩ «ولا هدف احتياطي أو هدف صلب، احذفو» ثمّ أُزيل `_on_target` واشتراكه ٢٠٢٦-٠٩-٢١؛ الدالّة باقية للتاريخ ولا يستدعيها اختبار.
def target(price=103.0, source="FLOOR_NO_PROBABILITY") -> dict:
    return {"account_id": "ACC", "broker": "BR", "symbol": "BTCUSD",
            "computable": True, "take_profit": price, "reward_multiple": 3.0,
            "multiple_source": source}


def levels(side="buy") -> dict:
    """مستويات التحليل كما تختمها البطاقة 414 على قرارها ويمرّرها 467 كما هي (`414/atom.py:306` · `467/atom.py:128`).

    ٢٠٢٦-١٠-٠٨ (إصلاح الاختبارات القديمة بأمر المالك): الشراء وقفه 98 وهدفه 108 على سعر 100 (4R صافيًا، 200 ن.أ) والبيع مرآته — فوق حكمَي الإرسال (`send_economics`)، والوقف غير `buy_stop`/`sell_stop` في حمولة 513 كي يُرى أنّه من التحليل وحده.
    """
    if side == "sell":
        return {"invalidation_price": 102.0, "target_price": 92.0, "setup_id": "414:BTCUSD:1",
                "invalidation_source": "414:pullback_high+noise_2.0atr"}
    return {"invalidation_price": 98.0, "target_price": 108.0, "setup_id": "414:BTCUSD:1",
            "invalidation_source": "414:pullback_low+noise_2.0atr"}


def decision(side="buy", with_levels=True, **extra) -> dict:
    """قرارٌ كما ينشره 467 حيًّا — بـ`decision_side` لا `side`.

    ٢٠٢٦-٠٩-٠٩: كانت هذه الدالة تبني بـ`side`، وهو اسمٌ لا يضعه ناشر
    `decision.gate.passed` (467 يضع `decision_side` — `467/atom.py:129`).
    فمرّت كل الاختبارات والذرّة تحجب كل قرار حيّ:
    `555 seen=10 emitted=0 blocked=10 · DECISION_SIDE_UNKNOWN`.
    **اختبارٌ يبني حمولةً لا يبنيها الناشر يختبر وهمًا.**

    ٢٠٢٦-١٠-٠٨ (إصلاح الاختبارات القديمة بأمر المالك): والدرس نفسه تكرّر — القرار الحيّ اليوم يحمل مستوياته (`levels`)، والقرار بلا مستويات يُردّ `NO_STOP_FOR_SIDE`؛ و`with_levels=False` لاختبار ذلك ولمسار الخانة (`_on_setup`).
    """
    body = {"account_id": "ACC", "broker": "BR", "symbol": "BTCUSD",
            "decision_side": side, "decision_id": "D1", "gate_request_id": "G1"}
    if with_levels and side in ("buy", "sell"):
        body.update(levels(side))
    body.update(extra)
    return body


def feed(atom, handler, payload):
    asyncio.run(getattr(atom, handler)(payload))


def test_approved_decision_becomes_an_order_request():
    """الحلقة المفقودة: قرار مُوافَق ⇒ طلب أمر."""
    atom, bus = build()
    feed(atom, "_on_size", size())
    # ٢٠٢٦-١٠-٠٨ (إصلاح الاختبارات القديمة بأمر المالك): لا هدف من 526 (أُزيل ٢٠٢٦-٠٩-٢١) — الوقف والهدف على القرار نفسه.
    feed(atom, "_on_decision", decision("buy"))
    out = bus.of("execution.order.requested")
    assert len(out) == 1, "طلب واحد"
    order = out[0]
    assert order["action"] == "OPEN" and order["side"] == "buy"
    # ٢٠٢٦-١٠-٠٨ (إصلاح الاختبارات القديمة بأمر المالك): الوقف من التحليل وحده (أمر ٢٠٢٦-٠٩-١٩) والحجم يُعاد عليه (أمر ٢٠٢٦-٠٩-١٨)؛ ميزانيّة 100$ من 513 ثابتة.
    assert order["volume"] == 0.05, "100$ ÷ (مسافة 2 × 1000$) — لا 0.10 المحسوب على وقف 513"
    assert order["stop_loss"] == 98.0, "الوقف من التحليل لا buy_stop=99 من 513"
    assert order["take_profit"] == 108.0, "الهدف من التحليل على القرار"
    assert order["invalidation_source"] == "414:pullback_low+noise_2.0atr"
    assert order["setup_id"] == "414:BTCUSD:1"
    assert order["risk_budget"] == 100.0
    assert order["origin"] == "entry-555"
    assert order["request_id"].startswith("555-")
    print("OK — القرار صار طلب أمر")


def test_sell_side_uses_its_own_lot_and_stop():
    atom, bus = build()
    # ٢٠٢٦-١٠-٠٨ (إصلاح الاختبارات القديمة بأمر المالك): لوت الشراء صفر عمدًا — فلو قرأ البيعُ لوتَ الشراء لرُدّ NO_EXECUTABLE_VOLUME؛ ووقف البيع من تحليله (102.5) لا sell_stop=101.5 من 513.
    feed(atom, "_on_size", size(buy_lot=0.0, sell_lot=0.20, sell_stop=101.5))
    feed(atom, "_on_decision", decision("sell", invalidation_price=102.5, target_price=90.0))
    order = bus.of("execution.order.requested")[-1]
    assert order["side"] == "sell" and order["volume"] == 0.04, "100$ ÷ (2.5 × 1000)"
    assert order["stop_loss"] == 102.5 and order["take_profit"] == 90.0
    print("OK — جهة البيع تأخذ لوتها ووقفها")


def test_identity_chain_passes_through_untouched():
    """بلا سلطة يرفض 552 — والذرّة تنقل ولا تخترع."""
    atom, bus = build()
    feed(atom, "_on_size", size())
    feed(atom, "_on_decision", decision("buy", parent_decision_id="P9",
                                        owner_command_id="OC1"))
    order = bus.of("execution.order.requested")[-1]
    assert order["decision_id"] == "D1" and order["gate_request_id"] == "G1"
    assert order["parent_decision_id"] == "P9"
    assert order["owner_command_id"] == "OC1"
    assert order["decision_side"] == "buy"
    print("OK — سلسلة الهويّة تعبر كما وردت")


def test_entry_cooldown_blocks_reentry_after_position_closes():
    """بعد إغلاق المركز، 555 لا يعيد فتح الرمز قبل 45 ثانية."""
    atom, bus = build()
    feed(atom, "_on_size", size())
    feed(atom, "_on_decision", decision("buy"))
    assert len(bus.of("execution.order.requested")) == 1
    # نحاكي وصول لقطة مراكز فارغة: هذا يحرر _inflight، لكنه لا يلغي كبح الدخول.
    # ٢٠٢٦-١٠-٠٨ (إصلاح الاختبارات القديمة بأمر المالك): السطر أعلاه لا يصدق — اللقطة الفارغة لا تحرّر الطائر (ولا يجوز: هي نافذة العنقدة)؛ يحرّره ظهور المركز، فنحاكي فتحه ثمّ إغلاقه.
    feed(atom, "_on_positions", {"positions": [{"symbol": "BTCUSD"}]})
    assert atom._inflight == {}
    feed(atom, "_on_positions", {"positions": []})
    second = dict(decision("buy"), decision_id="D2", gate_request_id="G2")
    feed(atom, "_on_decision", second)
    assert len(bus.of("execution.order.requested")) == 1
    state = bus.of("execution.entry.state")[-1]
    assert state["reason"] == "ENTRY_COOLDOWN"
    print("OK — 555 يمنع إعادة الدخول خلال 45 ثانية")


def test_no_second_position_for_the_same_symbol():
    """الإضافة على مركز قائم شأن 581 — ازدواج المُصدِرين يفتح مركزين."""
    atom, bus = build()
    feed(atom, "_on_size", size())
    feed(atom, "_on_positions", {"positions": [{"symbol": "BTCUSD"}]})
    feed(atom, "_on_decision", decision("buy"))
    assert bus.of("execution.order.requested") == []
    state = bus.of("execution.entry.state")[-1]
    assert state["reason"] == "POSITION_ALREADY_OPEN"
    print("OK — لا مركز ثانٍ للرمز نفسه")


def test_missing_size_declines_with_a_reason():
    atom, bus = build()
    feed(atom, "_on_decision", decision("buy"))
    assert bus.of("execution.order.requested") == []
    assert bus.of("execution.entry.state")[-1]["reason"] == "NO_SIZE_FOR_SCOPE"
    print("OK — بلا حجم لا أمر، والسبب معلن")


def test_stale_size_is_refused():
    # كان ينام ١٠ مللي‌ثانية ويتوقّع عمرًا أكبر من ٠٫٠٠٠١ — ودقّة `monotonic`
    # على ويندوز ≈ ١٥٫٦ مللي‌ثانية، فيقرأ العمر صفرًا فلا يبيت. مقيس
    # ٢٠٢٦-٠٩-١٠: سقطة في كل خمس تشغيلات، والذرّة سليمة. الطابع يُزاح
    # صراحةً بدل انتظار ساعةٍ لا تضمن الدقّة (نفس علاج ٥٢٦).
    atom, bus = build(size_stale_after_s=0.5)
    feed(atom, "_on_size", size())
    for entry in atom._sizes.values():
        entry["at"] -= 5.0
    feed(atom, "_on_decision", decision("buy"))
    assert bus.of("execution.order.requested") == []
    assert bus.of("execution.entry.state")[-1]["reason"] == "SIZE_STALE"
    print("OK — حجم قديم لا يُبنى عليه أمر")


def test_missing_target_is_refused_not_invented():
    """⚖️ ٢٠٢٦-٠٩-١٨ — حكم المالك ينقض حكمه ٢٠٢٦-٠٩-١١.

    كان هذا الاختبار يثبت «الهدف الصلب»: بلا هدفٍ يُبنى ٣ أضعاف الوقف
    ويمضي الأمر. ونصّ المالك الجديد: «صفقة جاي بهدف 1/2، كيف تعدّلها
    وتركّبها 1/3؟ ما رح تشمّ ريحة مال فيها من خسرات متتالية».

    فالثلاثة صارت **أرضيّة قبول لا قالب سحب**: ما بلغها يمرّ بمضاعفه هو،
    وما قصر عنها أو غاب يُرفض بسببه المعلن. ولا يُخترَع هدفٌ لصفقةٍ
    صاحبُها لم يعطها هدفًا.
    """
    atom, bus = build()
    feed(atom, "_on_size", size())
    # ٢٠٢٦-١٠-٠٨ (إصلاح الاختبارات القديمة بأمر المالك): كان ينجح صدفةً على NO_STOP_FOR_SIDE (قرارٌ بلا وقف)؛ الآن الوقف حاضر والهدف وحده غائب، فيُختبر غياب الهدف حقًّا.
    feed(atom, "_on_decision", decision("buy", target_price=None))
    assert not bus.of("execution.order.requested"), "بلا هدفٍ لا يخرج أمر"
    assert bus.of("execution.entry.state")[-1]["reason"] == "NO_TARGET_FOR_SIDE"
    print("OK — بلا هدف يُرفض الأمر ولا يُخترع له واحد")


def test_zero_volume_is_refused():
    atom, bus = build()
    feed(atom, "_on_size", size(buy_lot=0.0))
    feed(atom, "_on_decision", decision("buy"))
    assert bus.of("execution.order.requested") == []
    assert bus.of("execution.entry.state")[-1]["reason"] == "NO_EXECUTABLE_VOLUME"
    print("OK — حجم صفر لا يُرسَل")


def test_unknown_side_is_refused():
    atom, bus = build()
    feed(atom, "_on_size", size())
    feed(atom, "_on_decision", decision("wait"))
    assert bus.of("execution.order.requested") == []
    assert bus.of("execution.entry.state")[-1]["reason"] == "DECISION_SIDE_UNKNOWN"
    print("OK — جهة مجهولة لا تصير أمرًا")


def test_halt_stops_every_request():
    atom, bus = build()
    feed(atom, "_on_size", size())
    feed(atom, "_on_halt", {"reason": "owner"})
    feed(atom, "_on_decision", decision("buy"))
    assert bus.of("execution.order.requested") == []
    assert bus.of("execution.entry.state")[-1]["reason"] == "EMERGENCY_HALT"
    feed(atom, "_on_reset", {})
    feed(atom, "_on_decision", decision("buy"))
    assert len(bus.of("execution.order.requested")) == 1, "الرفع يعيد العمل"
    print("OK — الإيقاف يمنع والرفع يعيد")


def test_default_stop_is_derived_when_structural_is_absent():
    # ٢٠٢٦-١٠-٠٨ (إصلاح الاختبارات القديمة بأمر المالك): الاسم تاريخيّ — كان يحرس وقفًا مشتقًّا من default_distance (99.5)، وألغاه المالك ٢٠٢٦-٠٩-١٩ «ما في وقف احتياطي أو وقف صلب، احذفو»؛ فصار يحرس نقيضه: بلا مستويات تحليل يُردّ الأمر ولا يُشتقّ وقف.
    atom, bus = build()
    feed(atom, "_on_size", size(buy_stop=None))
    feed(atom, "_on_decision", decision("buy", with_levels=False))
    assert bus.of("execution.order.requested") == [], "اشتُقّ وقفٌ من default_distance"
    state = bus.of("execution.entry.state")[-1]
    assert state["reason"] == "NO_STOP_FOR_SIDE" and state["analysis_only"] is True, state
    assert atom._stop_no_setup == 1, "السبب المفرَّق: لا إعداد لهذه الجهة"
    print("OK — بلا مستويات تحليل لا وقف ولا أمر")


def test_health_counts_and_snapshot():
    atom, bus = build()
    feed(atom, "_on_size", size())
    feed(atom, "_on_decision", decision("buy"))
    feed(atom, "_on_decision", decision("wait"))
    health = asyncio.run(atom.health_check())
    assert health.state.name == "HEALTHY"
    assert "seen=2" in health.message and "emitted=1" in health.message
    snap = asyncio.run(atom.snapshot())
    fresh, _ = build()
    asyncio.run(fresh.restore(snap))
    assert fresh._emitted == 1 and fresh._blocked == 1
    print("OK — الصحّة تعدّ واللقطة تعود")


def test_side_read_by_every_name_its_publishers_use():
    """الجهة تُقرأ بأسماء ناشريها الأربعة — لا باسم واحد.

    ٢٠٢٦-٠٩-٠٩: 467 ينشر `decision_side` (`467/atom.py:129`)، و581 يقرأ
    ثلاثة أسماء (`581/atom.py:122`)، و576/578/580 تقرأ `side` — وهي مغلقة
    بأمر المالك. فكانت 555 تقرأ اسم الميت وحده وتحجب كل قرار حيّ.
    """
    for field in ("decision_side", "direction", "signal", "side"):
        atom, bus = build()
        # ٢٠٢٦-١٠-٠٨ (إصلاح الاختبارات القديمة بأمر المالك): القرار يحمل مستوياته كما يمرّرها 467، ولا هدف من 526.
        payload = {"account_id": "ACC", "broker": "BR", "symbol": "BTCUSD",
                   "decision_id": "D1", "gate_request_id": "G1", field: "buy",
                   **levels("buy")}
        feed(atom, "_on_size", size())
        feed(atom, "_on_decision", payload)
        orders = bus.of("execution.order.requested")
        assert orders, "القرار سقط على اسم الحقل: %s" % field
        assert orders[-1]["side"] == "buy", (field, orders[-1])
    print("OK — الجهة تُقرأ بأربعة أسماء: أيّ ناشر يمرّ")


def size_as_513_really_publishes(lot=0.3, price=52774.1, stop_distance=263.8705,
                                 **over) -> dict:
    """حمولة 513 الحيّة حرفًا — أرقامها كلّها تحت `metadata` (`513/atom.py:296`).

    ٢٠٢٦-٠٩-٠٩: أُخذت من الناقل بعد أوّل إقلاع نظيف، حين وصل القرار المُوافَق
    إلى 555 (`467 passed=5`) فسقط على `NO_EXECUTABLE_VOLUME`. الاختبارات
    أعلاه تبني حمولة **مسطَّحة** — وهي شكلٌ لا ينشره 513؛ فهذا الاختبار يبني
    من كود الناشر لا من الوثيقة.
    """
    meta = {"method": "risk_percent_sizing", "lot": lot, "risk_amount": 100.0,
            "risk_pct": 1.0, "stop_distance": stop_distance, "equity": 9625.68,
            "price": price, "buy_lot": None, "buy_stop": None,
            "sell_lot": None, "sell_stop": None, "tick_value": 0.01,
            "tick_size": 0.01, "spread": 0.2, "slippage_reserve": 0.4,
            "commission_per_lot": 0.0, "max_trade_loss": 100.0,
            "volume_step": 0.1, "volume_min": 0.1, "volume_max": 20.0}
    meta.update(over)
    return {"account_id": "ACC", "broker": "BR", "symbol": "BTCUSD",
            "id": "position_sizing", "status": "OK", "approved": True,
            "reason": "", "timeframe": "", "warnings": [], "metadata": meta}


def test_order_is_built_from_the_payload_513_actually_publishes():
    """الحلقة الأخيرة: أرقام 513 تحت `metadata` — والذرّة كانت تقرأ فوقها."""
    atom, bus = build()
    feed(atom, "_on_size", size_as_513_really_publishes())
    # ٢٠٢٦-١٠-٠٨ (إصلاح الاختبارات القديمة بأمر المالك): الوقف من مستويات القرار (150 نقطة، 28 ن.أ) لا price − stop_distance (حُذف ٢٠٢٦-٠٩-١٩)، والهدف صافيه 3.5 بعد سبريد 0.2.
    feed(atom, "_on_decision", decision("buy", invalidation_price=52624.1,
                                        target_price=53300.0))
    orders = bus.of("execution.order.requested")
    assert orders, ("سقط على NO_EXECUTABLE_VOLUME: %s"
                    % bus.of("execution.entry.state")[-1])
    order = orders[-1]
    # ٢٠٢٦-١٠-٠٨ (إصلاح الاختبارات القديمة بأمر المالك): metadata.lot بوّابةٌ فقط، والحجم يُعاد على وقف التحليل بمعاملات metadata نفسها (tick_value · tick_size · spread · volume_step) — فلو لم يُفكّ الغلاف لسقط على NO_EXECUTABLE_VOLUME.
    assert order["volume"] == 0.6, "100$ ÷ (150 + سبريد 0.2) = 0.666 ⟸ خطوة 0.1"
    assert order["reference_price"] == 52774.1, "السعر اسمه price لا close"
    assert order["stop_loss"] == 52624.1, "الوقف من التحليل"
    assert round(order["stop_loss"], 4) != round(52774.1 - 263.8705, 4), \
        "عاد اشتقاق الوقف من stop_distance"
    assert order["risk_budget"] == 100.0, "ميزانية المخاطرة من metadata"
    print("OK — الأمر يُبنى من حمولة 513 الحقيقيّة")


def test_sell_side_reads_the_same_nested_payload():
    atom, bus = build()
    feed(atom, "_on_size", size_as_513_really_publishes())
    # ٢٠٢٦-١٠-٠٨ (إصلاح الاختبارات القديمة بأمر المالك): مرآة الشراء — وقف التحليل فوق السعر بـ150 نقطة لا price + stop_distance.
    feed(atom, "_on_decision", decision("sell", invalidation_price=52924.1,
                                        target_price=52250.0))
    order = bus.of("execution.order.requested")[-1]
    assert order["side"] == "sell" and order["volume"] == 0.6
    assert order["stop_loss"] == 52924.1
    assert round(order["stop_loss"], 4) != round(52774.1 + 263.8705, 4)
    print("OK — جهة البيع تقرأ الغلاف نفسه")


def test_directional_lot_wins_over_the_generic_one():
    """حين يملأ 513 لوتًا اتجاهيًّا فهو الأولى — والعامّ احتياط."""
    # ٢٠٢٦-١٠-٠٨ (إصلاح الاختبارات القديمة بأمر المالك): لوت 513 صار بوّابةً والحجم يُعاد على وقف التحليل (أمر ٢٠٢٦-٠٩-١٨)، وbuy_stop لا يُقرأ (أمر ٢٠٢٦-٠٩-١٩)؛ فالأولويّة تُرى في البوّابة: العامّ صفر والاتجاهيّ 0.7 ⟸ يمرّ الشراء، والبيع بلا اتجاهيّ يقع على العامّ الصفر ⟸ يُردّ.
    atom, bus = build()
    feed(atom, "_on_size",
         size_as_513_really_publishes(lot=0.0, buy_lot=0.7, buy_stop=52500.0))
    feed(atom, "_on_decision", decision("buy", invalidation_price=52624.1,
                                        target_price=53300.0))
    orders = bus.of("execution.order.requested")
    assert orders, bus.of("execution.entry.state")[-1]
    order = orders[-1]
    assert order["volume"] == 0.6, "الحجم على وقف التحليل لا 0.7 المحسوب على وقف 513"
    assert order["stop_loss"] == 52624.1, "buy_stop=52500 من 513 لا يصير وقفًا"
    atom, bus = build()
    feed(atom, "_on_size",
         size_as_513_really_publishes(lot=0.0, buy_lot=0.7, buy_stop=52500.0))
    feed(atom, "_on_decision", decision("sell", invalidation_price=52924.1,
                                        target_price=52250.0))
    assert bus.of("execution.order.requested") == []
    assert bus.of("execution.entry.state")[-1]["reason"] == "NO_EXECUTABLE_VOLUME"
    print("OK — اللوت الاتجاهيّ يعلو العامّ")


def test_flat_payload_still_works():
    """لا ينكسر ناشرٌ يرسل مسطَّحًا — الغلاف إضافة لا استبدال."""
    atom, bus = build()
    feed(atom, "_on_size", size())
    feed(atom, "_on_decision", decision("buy"))
    order = bus.of("execution.order.requested")[-1]
    # ٢٠٢٦-١٠-٠٨ (إصلاح الاختبارات القديمة بأمر المالك): المسطَّح يُقرأ كلّه (الحجم والسعر ومعاملات إعادة الحجم)، والوقف من التحليل لا buy_stop.
    assert order["volume"] == 0.05 and order["stop_loss"] == 98.0
    assert order["reference_price"] == 100.0
    print("OK — الشكل المسطَّح باقٍ")


def test_side_lookup_is_not_a_single_name():
    """حارس بنيويّ: لا يعود `payload.get(\"side\")` وحده حكمًا على الجهة."""
    import ast
    path = Path(__file__).resolve().parents[1] / "atom.py"
    code = ast.unparse(ast.parse(path.read_text(encoding="utf-8")))
    assert "def _side_of" in code, "دالة الجهة اختفت"
    assert "'decision_side'" in code or '"decision_side"' in code, \
        "اسم 467 غاب عن قراءة الجهة"
    print("OK — قراءة الجهة تبقى متعدّدة الأسماء")




def test_entry_is_refused_until_positions_are_known():
    """شكوى المالك ٢٠٢٦-٠٩-١٠: «ليش تفعل هيدج؟ أنا مو مشغّله».

    `_open_counts` حالةٌ في الذاكرة لا تُحفظ في اللقطة ولا تُستعاد،
    والذرّات تُبدَّل ساخنة — فبعد كل إعادة تحميل تبدأ الخريطة فارغة،
    فيقرأ الحارس `open_now = 0` ويمرّر الدخول رغم وجود مركز قائم.
    مقيس: `USTEC SELL 0.5 FILLED_OPEN` مرّتين، وBTCUSD شراءٌ وبيعٌ معًا.
    """
    atom, bus = build(positions=None)          # لم تصل لقطة مراكز بعد
    feed(atom, "_on_size", size())
    # ٢٠٢٦-١٠-٠٨ (إصلاح الاختبارات القديمة بأمر المالك): لا `_on_target` (أُزيل ٢٠٢٦-٠٩-٢١)؛ القرار مكتمل بمستوياته فلا يردّه إلّا جهل المراكز.
    feed(atom, "_on_decision", decision("buy"))
    assert bus.of("execution.order.requested") == [], "دخلَ والمراكز مجهولة"
    assert bus.of("execution.entry.state")[-1]["reason"] == "POSITIONS_UNKNOWN"
    print("OK — الجهل بالمراكز ليس إذنًا بالدخول")


def test_entry_resumes_once_the_first_snapshot_arrives():
    atom, bus = build(positions=None)
    feed(atom, "_on_size", size())
    # ٢٠٢٦-١٠-٠٨ (إصلاح الاختبارات القديمة بأمر المالك): لا `_on_target`؛ الهدف والوقف على القرار.
    feed(atom, "_on_decision", decision("buy"))
    assert bus.of("execution.order.requested") == []
    feed(atom, "_on_positions", {"positions": []})   # لا مركز مفتوح
    feed(atom, "_on_decision", decision("buy"))
    assert len(bus.of("execution.order.requested")) == 1
    print("OK — يستأنف حالما تُعرَف الحال")


def test_open_position_still_blocks_a_second_entry():
    atom, bus = build(positions=[{"symbol": "BTCUSD"}])
    feed(atom, "_on_size", size())
    # ٢٠٢٦-١٠-٠٨ (إصلاح الاختبارات القديمة بأمر المالك): لا `_on_target`؛ قرار البيع مكتمل بمستوياته فلا يردّه إلّا المركز القائم.
    feed(atom, "_on_decision", decision("sell"))
    assert bus.of("execution.order.requested") == []
    assert bus.of("execution.entry.state")[-1]["reason"] == "POSITION_ALREADY_OPEN"
    print("OK — لا مركز ثانٍ على الرمز نفسه")


def test_second_request_is_blocked_while_the_first_is_in_flight():
    """العنقدة: أربعة بيوع BTCUSD في ستّ ثوانٍ ⇒ ‎-324.52‎."""
    atom, bus = build()
    feed(atom, "_on_size", size())
    # ٢٠٢٦-١٠-٠٨ (إصلاح الاختبارات القديمة بأمر المالك): لا `_on_target`؛ القرار بمستوياته.
    feed(atom, "_on_decision", decision("buy"))
    assert len(bus.of("execution.order.requested")) == 1
    feed(atom, "_on_decision", decision("buy"))
    assert len(bus.of("execution.order.requested")) == 1, "طلب ثانٍ والأوّل طائر"
    state = bus.of("execution.entry.state")[-1]
    assert state["reason"] == "REQUEST_IN_FLIGHT", state["reason"]
    assert state["in_flight"] == 1 and state["open_positions"] == 0
    print("OK — الطلب الطائر يُعدّ مركزًا")


def test_in_flight_clears_when_the_position_appears():
    atom, bus = build()
    feed(atom, "_on_size", size())
    # ٢٠٢٦-١٠-٠٨ (إصلاح الاختبارات القديمة بأمر المالك): لا `_on_target`؛ القرار بمستوياته.
    feed(atom, "_on_decision", decision("buy"))
    assert len(bus.of("execution.order.requested")) == 1
    feed(atom, "_on_positions", {"positions": [{"symbol": "BTCUSD"}]})
    assert atom._inflight == {}, "لم يُسقَط بعد ظهور المركز"
    feed(atom, "_on_decision", decision("buy"))
    assert bus.of("execution.entry.state")[-1]["reason"] == "POSITION_ALREADY_OPEN"
    print("OK — يُسقَط حين يظهر أثره، والمركز يمنع بعده")


def test_in_flight_expires_so_a_lost_order_never_locks_the_symbol():
    atom, bus = build()
    feed(atom, "_on_size", size())
    # ٢٠٢٦-١٠-٠٨ (إصلاح الاختبارات القديمة بأمر المالك): لا `_on_target`؛ القرار بمستوياته.
    feed(atom, "_on_decision", decision("buy"))
    assert len(bus.of("execution.order.requested")) == 1
    for key in atom._inflight:
        atom._inflight[key] -= 1000.0
    # ٢٠٢٦-١٠-٠٨ (إصلاح الاختبارات القديمة بأمر المالك): مرور 1000 ثانية يمرّ على مهلة الدخول (45 ث، دُمجت ٢٠٢٦-٠٩-٢٢) كما يمرّ على مهلة الطائر — الساعة واحدة، فتُزاح الاثنتان.
    for key in atom._last_request_at:
        atom._last_request_at[key] -= 1000.0
    feed(atom, "_on_size", size())
    feed(atom, "_on_decision", decision("buy"))
    assert len(bus.of("execution.order.requested")) == 2, "المهلة لم تحرّر الرمز"
    print("OK — أمرٌ ضائع لا يقفل الرمز إلى الأبد")


def test_weak_target_is_refused_not_lifted():
    """⚖️ ٢٠٢٦-٠٩-١٨ — هدفٌ دون ٣ أضعاف الوقف **يُرفض ولا يُرفع**.

    كان يُسحب إلى الأرضيّة فتمشي الصفقة بمستوى لم يطلبه أحد. وسندُ
    النقض مقيس: من ٩٠ صفقة مغلقة تحت القالب **صفرٌ بلغت 3R** وأربعٌ فقط
    خرجت بـTP. القالب لا يصنع مضاعفه، يصنع طابور خسارات.
    """
    atom, bus = build()
    feed(atom, "_on_size", size())
    # ٢٠٢٦-١٠-٠٨ (إصلاح الاختبارات القديمة بأمر المالك): الهدف الضعيف يصل على القرار نفسه (لا من 526)، ويُحكم عند الإرسال بأمر ٢٠٢٦-٠٩-٢٨/١٠-٠٢ «تحت 1/3 مرفوضة».
    feed(atom, "_on_decision", decision("buy", invalidation_price=99.0,
                                        target_price=101.0))   # 1R فقط
    assert not bus.of("execution.order.requested"), "هدف 1R يجب أن يُرفض"
    state = bus.of("execution.entry.state")[-1]
    assert state["reason"] == "RR_BELOW_MIN_AT_SEND", state
    assert state["take_profit"] == 101.0 and state["net_ratio"] == 1.0, \
        "رُفع الهدف أو غُيّر بدل أن يُردّ كما هو"
    print("OK — هدف 1R يُرفض ولا يُركَّب على قالب")


def test_strong_target_is_kept_as_the_analysis_said_it():
    """وهدفٌ أعلى من ٣ يبقى كما نطق به مصدره — الأرضيّة لا سقف.

    وهذا ما لم يتغيّر بحكم ٢٠٢٦-٠٩-١٨: «بجوز تحضر صفقة 1/50 — تعدمها؟
    يعني لا». ما بلغ الأرضيّة أو تجاوزها يمرّ بمضاعفه هو.
    """
    atom, bus = build()
    feed(atom, "_on_size", size())
    # ٢٠٢٦-١٠-٠٨ (إصلاح الاختبارات القديمة بأمر المالك): الهدف القويّ على القرار نفسه لا من 526.
    feed(atom, "_on_decision", decision("buy", invalidation_price=99.0,
                                        target_price=105.0))   # 5R
    order = bus.of("execution.order.requested")[-1]
    assert order["take_profit"] == 105.0, order["take_profit"]
    assert order["target_source"] != "HARD_FLOOR_3R"
    print("OK — هدف 5R لم يُمَسّ")


def test_no_trade_when_stop_equals_price():
    """«صفقة ما معها ستوب وهدف لا تمشي أبدًا» — وقفٌ بلا مسافة لا هدف له."""
    atom, bus = build()
    feed(atom, "_on_size", size(buy_stop=100.0))    # الوقف = السعر
    # ٢٠٢٦-١٠-٠٨ (إصلاح الاختبارات القديمة بأمر المالك): كان ينجح صدفةً على غياب المستويات؛ الوقف يأتي من التحليل فيُوضع هو على السعر نفسه.
    feed(atom, "_on_decision", decision("buy", invalidation_price=100.0))
    assert bus.of("execution.order.requested") == []
    assert bus.of("execution.entry.state")[-1]["reason"] == "NO_STOP_FOR_SIDE"
    assert atom._stop_wrong_side == 1
    print("OK — لا صفقة بلا مسافة وقف")


def _setup(side="buy", invalidation=98.5, target=104.5, symbol="BTCUSD"):
    """إعدادٌ كما تبنيه ٤٠٦/٤١٠ عبر `shared.trade_setup` — لا كما نتخيّله."""
    from shared.trade_setup import build_setup
    return build_setup(
        owner="406", setup_type="BREAKOUT_ACCEPTANCE", side=side, account_id="ACC",
        broker="BR", symbol=symbol, cycle_id="C1", period_start=None,
        entry_reference=100.0,
        invalidation_price=invalidation, invalidation_source="406:STRUCTURE",
        invalidation_reason="below_break", target_price=target,
        target_source="406:MEASURED_MOVE", target_reason="range_projection",
        structure_id="S1", strength=70.0, confidence=80.0, evidence={})


def test_analysis_levels_replace_the_blind_fallback():
    """حكم المالك ٢٠٢٦-٠٩-١١: «الستوب يجي من التحليل حصرًا».

    مقيس على ٣٬٨٢٦ أمرًا: كلّها بوقف ٠٫٥٪ ثابتة و`invalidation_source: None`.
    """
    atom, bus = build()
    feed(atom, "_on_setup", _setup())
    feed(atom, "_on_size", size())
    # ٢٠٢٦-١٠-٠٨ (إصلاح الاختبارات القديمة بأمر المالك): قرارٌ بلا مستويات كي يُختبر مسار الخانة (`_setup_levels`) الباقي لمن لا يختم مستوياته؛ ومع المستويات على القرار لا تُقرأ الخانة أصلًا.
    feed(atom, "_on_decision", decision("buy", with_levels=False))
    order = bus.of("execution.order.requested")[-1]
    assert order["stop_loss"] == 98.5, order["stop_loss"]
    assert order["take_profit"] == 104.5, order["take_profit"]
    assert order["invalidation_source"] == "406:STRUCTURE"
    assert order["setup_id"] is not None and order["setup_id"].startswith("406:")
    assert order["volume"] == 0.06, "100$ ÷ (1.5 × 1000) = 0.066 ⟸ خطوة 0.01"
    print("OK — الوقف والهدف من التحليل، والنسب معهما")


def test_setup_for_the_other_side_is_ignored():
    atom, bus = build()
    # ٢٠٢٦-١٠-٠٨ (إصلاح الاختبارات القديمة بأمر المالك): كان إعداد البيع بهدف 104.5 فوق سعره فيُردّ عند الباب (GEOMETRY_INVERTED) ولا يُخزَّن أصلًا؛ صار إعداد بيعٍ سليمًا (هدف 95.5) كي يُختبر التجاهل حقًّا.
    feed(atom, "_on_setup", _setup(side="sell", invalidation=101.5, target=95.5))
    assert ("BTCUSD", "sell") in atom._setups, atom._refuse_why
    feed(atom, "_on_size", size())
    feed(atom, "_on_decision", decision("buy", with_levels=False))
    # ٢٠٢٦-١٠-٠٨ (إصلاح الاختبارات القديمة بأمر المالك): لا احتياطيّ FALLBACK_513 بعد أمر ٢٠٢٦-٠٩-١٩ — شراءٌ بلا إعدادٍ لجهته يُردّ كلّه، ولا يأخذ وقف البيع.
    assert bus.of("execution.order.requested") == [], "أخذ وقف إعدادٍ لاتجاهٍ آخر"
    assert bus.of("execution.entry.state")[-1]["reason"] == "NO_STOP_FOR_SIDE"
    assert ("BTCUSD", "sell") in atom._setups, "استُهلك إعداد البيع بقرار شراء"
    feed(atom, "_on_decision", decision("sell", with_levels=False,
                                        decision_id="D2", gate_request_id="G2"))
    order = bus.of("execution.order.requested")[-1]
    assert order["side"] == "sell" and order["stop_loss"] == 101.5
    print("OK — إعداد الاتجاه المعاكس لا يُستعمل")


def test_setup_on_the_wrong_side_of_price_is_refused():
    """وقف شراءٍ فوق السعر ليس وقفًا — يسقط إلى الاحتياطيّ ولا يُقبل.

    ٢٠٢٦-١٠-٠٨ (إصلاح الاختبارات القديمة بأمر المالك): لا احتياطيّ بعد أمر ٢٠٢٦-٠٩-١٩ — يُردّ الأمر كلّه NO_STOP_FOR_SIDE، في البابين: إعدادٌ مقلوب على مرجع بنائه يُردّ عند `_on_setup`، وإبطالٌ سليمٌ يوم بنائه صار في الجهة الخطأ من السعر الحيّ يُردّ عند القرار.
    """
    atom, bus = build()
    feed(atom, "_on_setup", _setup(invalidation=101.0))
    assert atom._refuse_why == {"GEOMETRY_INVERTED": 1}, atom._refuse_why
    feed(atom, "_on_size", size())
    feed(atom, "_on_decision", decision("buy", with_levels=False))
    assert bus.of("execution.order.requested") == [], "خرج أمرٌ بلا وقف تحليل"
    assert bus.of("execution.entry.state")[-1]["reason"] == "NO_STOP_FOR_SIDE"
    feed(atom, "_on_decision", decision("buy", invalidation_price=101.0))
    assert bus.of("execution.order.requested") == [], "وقف شراءٍ فوق السعر قُبل"
    assert bus.of("execution.entry.state")[-1]["reason"] == "NO_STOP_FOR_SIDE"
    assert atom._stop_wrong_side == 1
    print("OK — وقفٌ في الجهة الخطأ يُرفض")
if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
    print("\n555: كل الاختبارات خضراء")
