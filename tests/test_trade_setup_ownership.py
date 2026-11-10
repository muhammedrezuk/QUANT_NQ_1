# -*- coding: utf-8 -*-
"""ملكية الصفقة — اختبارات القبول لورقة التنفيذ ٢٠٢٦-٠٩-٠٦.

حكم المالك: «إذا كان بإمكان النظام بعد التعديل فتح صفقة من 404/408
وحدهما، فالإصلاح فاشل، مهما كانت نتائج الاختبارات الأخرى».

هذه الاختبارات تحرس الأربعة التي جعلها المالك معيار النجاح (§٢٥):
    ١. لا يمكن فتح OPEN بلا إعداد.
    ٢. لا يمكن تغيير إبطال الإعداد من طبقة لاحقة.
    ٣. لا يضيع `setup_id` أثناء العبور بين الطبقات.
    ٤. لا يوجد مسار فتح ثانٍ يلتفّ حول العقد.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from shared.trade_setup import (  # noqa: E402
    OK, REJECT_GEOMETRY, REJECT_PRICES, REJECT_WHY, SETUP_LIQUIDITY_RAID,
    build_setup, geometry_matches_entry, is_alive, is_broken, is_target_reached,
    net_ratio as pdr_net, round_trip_cost, setup_ratio, validate_setup)


def _setup(side="sell", entry=79986.0, stop=80012.0, target=79850.0, **kw):
    return build_setup(
        owner="410", setup_type=SETUP_LIQUIDITY_RAID, side=side,
        entry_reference=entry, invalidation_price=stop,
        invalidation_source="410:sweep_edge",
        invalidation_reason="عودة السعر فوق طرف الكنس تُبطل الاسترداد",
        target_price=target, target_source="410:opposite_liquidity",
        target_reason="السيولة المقابلة", symbol="BTCUSD", **kw)


# ─────────── العقد نفسه: الهندسة والنسب والحياة ───────────

def test_setup_geometry_must_be_sane() -> None:
    """اختبارا ١١ و١٠: إبطال مقلوب أو ناقص = رفض، لا اختراع بديل."""
    assert validate_setup(_setup()) == OK
    # بيع بإبطال تحت الدخول = هندسة مقلوبة.
    assert validate_setup(_setup(stop=79900.0)) == REJECT_GEOMETRY
    # بلا إبطال أصلًا.
    assert validate_setup(_setup(stop=None)) == REJECT_PRICES
    # بلا هدف.
    assert validate_setup(_setup(target=None)) == REJECT_PRICES
    # إبطال بلا سبب = رقم بلا نسب، ليس إبطالًا.
    bare = _setup()
    bare["invalidation_reason"] = ""
    assert validate_setup(bare) == REJECT_WHY


def test_ratio_is_a_property_of_the_idea() -> None:
    """النسبة تخرج من الفكرة لا من بوّابة تُطبَّق عليها لاحقًا."""
    setup = _setup(entry=79986.0, stop=80012.0, target=79850.0)
    assert abs(setup_ratio(setup) - (136.0 / 26.0)) < 1e-9


def test_setup_dies_by_price_and_by_time() -> None:
    """§١٧: فكرةٌ ماتت لا تُفتح — لا بتجاوز الإبطال ولا بانقضاء الأجل."""
    setup = _setup(ttl_s=10.0)
    assert is_alive(setup, setup["created_at"] + 5.0)
    assert not is_alive(setup, setup["created_at"] + 11.0)
    assert not is_broken(setup, 79990.0)
    assert is_broken(setup, 80013.0)          # بيع: تجاوز الإبطال فوقه


# ─────────── البوّابة: لا صفقة بلا إعداد مملوك ───────────


# ─────────── قطع المسار القديم: لا باب ثانٍ ───────────


def test_551_carries_ownership_and_never_edits_it() -> None:
    """اختبار ٤ (المرحلة هـ): 551 يحسب الحجم ولا يبدّل إبطال الإعداد."""
    root = Path(__file__).resolve().parents[1]
    source = (root / "atoms/قسم 550-599/551_باني_الأمر/atom.py").read_text(
        encoding="utf-8")
    for field in ("setup_id", "setup_owner", "analysis_invalidation",
                  "analysis_target", "invalidation_source", "target_source"):
        assert f'"{field}"' in source, f"551 لا يحمل حقل الملكية: {field}"
    # ولا يُسند إليها قيمة جديدة في أيّ موضع.
    for field in ("analysis_invalidation", "analysis_target", "setup_id"):
        assert f'["{field}"] =' not in source, f"551 يعدّل حقلًا مملوكًا: {field}"


def test_584_separates_execution_stop_from_the_idea() -> None:
    """اختبار ٥ (المرحلة و): إزاحة وقف التنفيذ تُسجَّل، والهدف لا يُخترع."""
    root = Path(__file__).resolve().parents[1]
    # ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): 584 نُقلت إلى الهويّة 525 في `قسم 500-549`
    # (`ef230e1` · `21b4332`، ٢٠٢٦-٠٩-٢٣)، فكان الاختبار يسقط بـFileNotFoundError على مسارٍ زال.
    # يُقرأ الآن بالهويّة. ⚠️ ولم يُمسّ العقد نفسه: 584 v2.2.0 (`eb222c2`، أمر المالك «وقف لا يوسّع»)
    # ألغى التوسيع كلّه فصار يرفض بـSTOP_BELOW_FLOOR — فإن سقط ما يلي فذلك عقدٌ تغيّر يُعاد
    # كتابته بقرار، لا مرجعٌ مكسور.
    # ٢٠٢٦-١٠-٠٨ (إصلاح الاختبارات القديمة بأمر المالك): العقد تغيّر بأمر المالك ٢٠٢٦-٠٩-١٨ «وقف لا يوسّع … هي مصاري مو لعب» و«المرفوضة تُرفض ولا تُعدَّل» (525 السطور 249-265).
    # ٢٠٢٦-١٠-٠٨ (إصلاح الاختبارات القديمة بأمر المالك): فلم يعد هناك وقف تنفيذٍ مُزاح يُسجَّل (execution_stop · EXECUTION_STOP_ADJUSTED) — الوقف الأقرب من حدّ الوسيط يُرفض بـSTOP_BELOW_FLOOR كما هو.
    # ٢٠٢٦-١٠-٠٨ (إصلاح الاختبارات القديمة بأمر المالك): والمحروس الأصليّ باقٍ ويُفحص بالسلوك لا بالنصّ: الفكرة (الإبطال والهدف) والوقف والهدف المنفّذان يعبرون كما نطق بها الإعداد، لا يُخترع هدف ولا يُكتب فوق الإبطال.
    import asyncio
    import importlib.util

    from build_registry.paths import RegistryAtomRoot
    from core.contracts.atom import AtomContext
    stop_legality = next(RegistryAtomRoot(root).glob("525_*"))
    source = (stop_legality / "atom.py").read_text(encoding="utf-8")
    assert '"analysis_invalidation"' not in source.split("out.update")[-1], \
        "584 يكتب فوق الإبطال التحليليّ"

    spec_525 = importlib.util.spec_from_file_location("ownership_525", stop_legality / "atom.py")
    module = importlib.util.module_from_spec(spec_525)
    spec_525.loader.exec_module(module)

    class _Log:
        def __getattr__(self, _name):
            return lambda *args, **kwargs: None

    events: list[tuple[str, dict]] = []

    async def publish(name, payload):
        events.append((name, payload))

    # ٢٠٢٦-١٠-٠٨ (إصلاح الاختبارات القديمة بأمر المالك): حدّ الوسيط 1000 نقطة × 0.01 = مسافة دنيا 10.0؛ الأمر الأوّل وقفه على 5 والثاني على 15.
    symbol_spec = {"symbol": "NQ", "point": 0.01, "stops_level": 1000, "freeze_level": 0,
                   "volume_min": 0.01, "volume_step": 0.01, "volume_max": 100}

    def order(request_id, stop, target):
        return {"account_id": "A", "symbol": "NQ", "side": "BUY", "action": "OPEN",
                "request_id": request_id, "reference_price": 100.0, "volume": 1.0,
                "stop_loss": stop, "take_profit": target, "symbol_spec": dict(symbol_spec),
                "setup_id": "setup-" + request_id, "analysis_invalidation": stop,
                "analysis_target": target}

    async def scenario():
        atom = module.Atom()
        await atom.initialize(AtomContext(525, {}, _Log(), publish, lambda *args: None))
        await atom.start()
        await atom._on_built(order("near", 95.0, 120.0))
        await atom._on_built(order("far", 85.0, 130.0))
        await atom.stop()

    asyncio.run(scenario())
    rejected = [p for name, p in events if name == module.EVENT_REJECTED]
    legal = [p for name, p in events if name == module.EVENT_LEGAL]
    assert [p["request_id"] for p in rejected] == ["near"], rejected
    assert rejected[0]["reason"] == "STOP_BELOW_FLOOR", "الوقف القريب لم يُرفض بسببه المسمّى"
    assert rejected[0]["stop_loss"] == 95.0, "الوقف المرفوض عُدّل بدل أن يُرفض كما هو"
    assert [p["request_id"] for p in legal] == ["far"], "الوقف القانونيّ لم يعبر"
    for field, value in (("stop_loss", 85.0), ("take_profit", 130.0),
                         ("analysis_invalidation", 85.0), ("analysis_target", 130.0),
                         ("setup_id", "setup-far")):
        assert legal[0][field] == value, f"525 بدّل {field}: {legal[0][field]!r} ≠ {value!r}"


def test_577_respects_the_owned_invalidation() -> None:
    """اختبار ٦ (المرحلة ز): الزحف لا يستبدل إبطال الإعداد بمنطق آخر."""
    root = Path(__file__).resolve().parents[1]
    source = (root / "atoms/قسم 550-599/577_صيانة_الستوب/atom.py").read_text(
        encoding="utf-8")
    assert "EVENT_SETUP" in source and "_setup_stop" in source, \
        "577 لا يسمع الإعداد"
    assert "_on_setup" in source, "577 بلا مستقبِل للإعداد"


def test_economics_judge_the_idea_not_the_spread() -> None:
    """اختبارا المالك الإلزاميّان ٢٠٢٦-٠٩-٠٦.

    قِيس أن ٢٢ من ٢٧ فكرة تُرفض لأن إبطالها أضيق من سبريد — «حكم على
    جودة الفكرة من معيار واحد، بدل أن يكون جزءًا من حساب الاقتصاد
    الكامل». الحكم صار اقتصاديًّا بتكلفة الجهتين.
    """
    cost = 5.0
    # مخاطرة ٣ · هدف ٤٠ · تكلفة ٥ ⇒ (40−5)/(3+5) = 4.38 — تُقبل رغم 3 < 5.
    tight = _setup(side="sell", entry=79624.75, stop=79627.75, target=79584.75)
    assert abs(pdr_net(tight, cost) - (35.0 / 8.0)) < 1e-9, pdr_net(tight, cost)
    assert pdr_net(tight, cost) >= 1.5, "رُفضت فكرة ضيّقة اقتصادها ممتاز"
    # مخاطرة ٢٠ · هدف ٢٥ ⇒ (25−5)/(20+5) = 0.80 — تُرفض اقتصاديًّا.
    wide = _setup(side="sell", entry=79600.0, stop=79620.0, target=79575.0)
    assert abs(pdr_net(wide, cost) - 0.8) < 1e-9, pdr_net(wide, cost)
    assert pdr_net(wide, cost) < 1.5, "قُبلت فكرة واسعة اقتصادها خاسر"
    # وتكلفة العبور تُحسب مرّة واحدة للدورة كاملة، لا مرّتين.
    assert round_trip_cost(79995.0, 80000.0) == 5.0


# ٢٠٢٦-١٠-٠٧ (ختم المالك «NQ»): خرج اختبار test_spread_is_no_longer_a_verdict_on_the_idea — يختبر مصدرَي الاستراتيجيّتين 406/410 المؤرشفتين مع فكّ الأقسام عن القرار.
# ٢٠٢٦-١٠-٠٧ (ختم المالك «NQ»): خرج اختبار test_owners_refuse_ideas_they_cannot_afford — يختبر حدّ MIN_SETUP_RATIO في 406/410 المؤرشفتين مع فكّ الأقسام عن القرار.
# ٢٠٢٦-١٠-٠٧ (ختم المالك «NQ»): خرج اختبار test_406_is_the_second_owner — يختبر الاستراتيجيّة 406 المؤرشفة مع فكّ الأقسام عن القرار.
# ٢٠٢٦-١٠-٠٧ (ختم المالك «NQ»): خرج اختبار test_410_owns_a_real_setup_contract — يختبر الاستراتيجيّة 410 المؤرشفة مع فكّ الأقسام عن القرار.
