# -*- coding: utf-8 -*-
"""عقد إعداد الصفقة — الكائن الوحيد الذي يملك فكرة الصفقة.

حكم المالك ٢٠٢٦-٠٩-٠٦: «مو تحطّ سقف يخنق غلطه — لازم من أساس ما يغلط»
ثم «حلّها من جذر لا ترقّع».

الجذر المقيس: النظام لم يملك يومًا كائنًا واحدًا يمثّل **فكرة الصفقة**.
كانت الفكرة موزّعة على ثلاثة لا يعرف بعضها بعضًا:

    لماذا ندخل؟  ← 404/408 (تقاطع متوسّطات · زخم حسابيّ)
    أين نخطئ؟    ← 581 يختار أقرب مستوى من خريطة عامّة
    إلى أين؟     ← 581 يختار أبعد مستوى من الخريطة نفسها

فلا أحد يستطيع الإجابة عن السؤال الأول: **لماذا هذه الصفقة موجودة؟**
ومن لا يملك جوابًا لا يملك وقفًا: تقاطعُ متوسّطين لا يُبطله سعرٌ معيّن
لأنه لا يدّعي شيئًا عن السعر. ولهذا كانت كل الحرّاس التي بُنيت — بوّابة
النسبة، سقف الخسارة، مجال تنفّس الزحف — تحسّن أرقامًا حول فراغ.

هذا الملفّ ينقل ملكية هندسة الصفقة إلى **صاحب الفكرة**:

    من يستطيع أن يقول «أنا مخطئ عند هذا السعر» — وحده يفتح صفقة.
    ومن لا يستطيع، يصوّت للسياق ولا يُنفَّذ.

وحين يملك الإعداد إبطاله وهدفه، تسقط الحرّاس من تلقائها: النسبة تخرج
من الفكرة نفسها، والوقف يعرف ما يحرس، والزحف يتبع إبطالًا يتطوّر لا
أقرب قاع عشوائيّ.

الأدوار بعد هذا العقد:
    الاستراتيجية البنيوية → تُنشئ إعدادًا كاملًا (اتجاه + إبطال + هدف)
    المحلّلات الأخرى      → سياق يقوّي الإعداد أو يضعفه، ولا يخلقه
    581                   → إدارة تعرّض وكمّية فقط — لا يخترع وقفًا ولا هدفًا
    551                   → حجم فقط
    584                   → شرعيّة فقط
    577                   → يدير إبطال الإعداد أثناء حياته
"""
from __future__ import annotations

import math
import os
import time
from pathlib import Path
from typing import Any

# حدث الإعداد — الاستراتيجية البنيوية تنشره، والغرفة تعتمده، و581 ينفّذه.
EVENT_SETUP = "strategy.setup.proposed"
SETUP_CONTRACT_VERSION = 1

BUY = "buy"
SELL = "sell"
SIDES = (BUY, SELL)

# أنواع الإعداد المعروفة — لكلٍّ إبطال طبيعيّ من بنيته هو، لا من خريطة عامّة.
SETUP_LIQUIDITY_RAID = "LIQUIDITY_RAID"      # كنس سيولة ثم استرداد
SETUP_BREAKOUT = "BREAKOUT_ACCEPTANCE"       # اختراق مستوى وقبولٌ خارجه
# ختم `NQ` ٢٠٢٦-٠٩-١٩ — نوعٌ ثالث لفكرةٍ **إحصائيّة** لا هيكليّة: السعر
# ابتعد عن متوسّط نافذته فيُنتظر رجوعه. وإبطالها إحصائيٌّ مثلها — ابتعادٌ
# آخر بمقدار انحرافٍ معياريّ — فلا تُقاس بحدٍّ هيكليّ لا وجود له هنا.
SETUP_MEAN_REVERSION = "MEAN_REVERSION"      # بُعدٌ عن المتوسّط وعودةٌ إليه
# ٢٠٢٦-١٠-٠٧ (ختم المالك «NQ» — فكّ الأقسام عن القرار): نوع البطاقة 414 — اتّجاهٌ متّفق على الساعة
# والأربع ساعات، ارتدادٌ على ٥ د ثمّ إغلاقٌ يكسر قمّته. إبطالها هيكليّ: خلف قاع الارتداد وخلف ضجيج ٥ د.
SETUP_TREND_PULLBACK = "TREND_CONTINUATION_PULLBACK"
SETUP_TYPES = (SETUP_LIQUIDITY_RAID, SETUP_BREAKOUT, SETUP_MEAN_REVERSION, SETUP_TREND_PULLBACK)

# عمر الإعداد الافتراضيّ: فكرةٌ لا تُنفَّذ سريعًا تصف سوقًا مضى.
DEFAULT_TTL_S = 120.0

# حالات الإعداد (ورقة التنفيذ §٢٦): تُسجَّل كلّها ولو كان عدد الصفقات صفرًا،
# كي يقول النظام صراحةً **لماذا لم يتداول** بدل أن يبدو واقفًا بلا تفسير.
STATE_CREATED = "SETUP_CREATED"
STATE_APPROVED = "SETUP_APPROVED"
STATE_REJECTED = "SETUP_REJECTED"
STATE_INVALIDATED = "SETUP_INVALIDATED"
STATE_EXPIRED = "SETUP_EXPIRED"
# ٢٠٢٦-٠٩-٠٦ (حكم المالك): فكرةٌ بلغ السعرُ هدفَها قبل الدخول لم تُخطئ
# هندستها — **فاتت فرصتها**. الحالتان مختلفتان ولا يجوز خلطهما: الأولى
# عيبٌ في الإعداد، والثانية مضيُّ وقتٍ. والدخول بعد بلوغ الهدف مطاردة
# لا فكرة.
STATE_TARGET_REACHED = "SETUP_TARGET_REACHED"
LOG_STOP_FROM_SETUP = "STOP_DERIVED_FROM_SETUP"
LOG_TARGET_FROM_SETUP = "TARGET_DERIVED_FROM_SETUP"
LOG_EXEC_STOP_ADJUSTED = "EXECUTION_STOP_ADJUSTED"

# أسباب الرفض — تُعلَن ولا تُبتلع، فالإعداد المرفوض يُقاس لا يُخمَّن.
REJECT_SIDE = "SIDE_NOT_BUY_OR_SELL"
REJECT_TYPE = "UNKNOWN_SETUP_TYPE"
REJECT_OWNER = "OWNER_MISSING"
REJECT_PRICES = "PRICE_NOT_FINITE_OR_POSITIVE"
REJECT_GEOMETRY = "GEOMETRY_INVERTED"
REJECT_WHY = "INVALIDATION_WITHOUT_REASON"
REJECT_TARGET_WHY = "TARGET_WITHOUT_REASON"
REJECT_EXPIRY = "EXPIRY_NOT_AFTER_CREATION"
OK = ""


def _real(value: Any) -> float | None:
    """رقم حقيقيّ موجب أو لا شيء — لا صفر ولا لانهاية ولا نصّ."""
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _text(value: Any) -> str:
    return str(value or "").strip()


def build_setup(
    *,
    owner: Any,
    setup_type: str,
    side: str,
    entry_reference: Any,
    invalidation_price: Any,
    invalidation_source: str,
    invalidation_reason: str,
    target_price: Any,
    target_source: str,
    target_reason: str,
    account_id: str = "",
    broker: str = "",
    symbol: str = "",
    cycle_id: str = "",
    period_start: Any = None,
    structure_id: str = "",
    strength: Any = 0.0,
    confidence: Any = 0.0,
    evidence: dict[str, Any] | None = None,
    created_at: float | None = None,
    ttl_s: float = DEFAULT_TTL_S,
) -> dict[str, Any]:
    """يبني حمولة الإعداد كما تنطق بها الاستراتيجية — بلا تحقّق هنا.

    التحقّق مسؤولية `validate_setup` كي يبقى البناء وصفًا خالصًا،
    والرفض قرارًا معلنًا بسببه.
    """
    now = float(created_at if created_at is not None else time.time())
    symbol = _text(symbol).upper()
    return {
        "contract_version": SETUP_CONTRACT_VERSION,
        "setup_id": "%s:%s:%s:%s" % (_text(owner), setup_type, symbol, round(now, 3)),
        "setup_owner": _text(owner),
        "setup_type": _text(setup_type).upper(),
        "side": _text(side).lower(),
        "account_id": _text(account_id),
        "broker": _text(broker),
        "symbol": symbol,
        "cycle_id": _text(cycle_id),
        "period_start": period_start,
        "setup_state": STATE_CREATED,
        "entry_reference": _real(entry_reference),
        # الإبطال: السعر الذي يُثبت أن الفكرة ماتت — ومصدره وسببه معه،
        # فلا يُقبل رقمٌ بلا نسب.
        "invalidation_price": _real(invalidation_price),
        "invalidation_source": _text(invalidation_source),
        "invalidation_reason": _text(invalidation_reason),
        # الهدف: إلى أين تقصد الحركة، بنسبه أيضًا.
        **_target_fields(side, entry_reference, invalidation_price,
                         target_price, target_source, target_reason),
        "structure_id": _text(structure_id),
        "strength": _real(strength) or 0.0,
        "confidence": _real(confidence) or 0.0,
        "evidence": dict(evidence or {}),
        "created_at": now,
        "expires_at": now + max(1.0, float(ttl_s or DEFAULT_TTL_S)),
    }


def _target_fields(side: str, entry: Any, stop: Any, target: Any,
                   source: str, reason: str) -> dict[str, Any]:
    """حقولُ الهدف — كما نطقت بها الاستراتيجيّة، بلا مدٍّ ولا تعديل.

    ⛔ **حكم المالك ٢٠٢٦-٠٩-١٨: «مابصير يتوسّع ستوب ولا يتوسّع هدف».**
    كنتُ قد بنيتُ هنا مدًّا يرفع الهدف إلى ما تقتضيه نسبة ٣ حين يقصر عنها
    (`ratio_extended`)، بحجّة أنّ «النسبة مُدخَلٌ للبناء لا مرشّحٌ للناتج».
    والحجّة صحيحةٌ في محلٍّ آخر، **وهذا ليس محلّها**: هدفٌ يُمدّ إلى رقمٍ
    لم يقله مستوًى هيكليّ هو سعرٌ مخترَع مهما اشتُقّ من وقفٍ مقيس — والسوق
    لا يعرف نسبتنا فيبلغه.

    فالهدف يبقى حيث وضعته الاستراتيجيّة. وما لا يبلغ النسبة **يُرفض** لا
    يُمطّ — والرفض يُعدّ في ٤٦٥ (`رفض_نسبة`) فيُقرأ ثمنه بالرقم.
    """
    return {
        "target_price": _real(target),
        "target_source": _text(source),
        "target_reason": _text(reason),
        "structural_target": _real(target),
    }


def validate_setup(setup: Any) -> str:
    """يعيد `OK` إن صحّ الإعداد، أو سبب الرفض صريحًا.

    الشروط ليست تجميلًا: كلٌّ منها يمنع صفقةً بلا فكرة.
      · الجانب معروف، والنوع من الأنواع المعلنة، وله مالك.
      · الأسعار الثلاثة حقيقية موجبة.
      · الهندسة غير مقلوبة: الإبطال خلف الدخول، والهدف أمامه.
      · للإبطال مصدر وسبب — رقمٌ بلا نسب ليس إبطالًا بل تخمين.
      · للهدف مصدر وسبب — للسبب نفسه.
      · للإعداد أجلٌ: فكرةٌ لا تُنفَّذ تصف سوقًا مضى.
    """
    if not isinstance(setup, dict):
        return REJECT_TYPE
    side = _text(setup.get("side")).lower()
    if side not in SIDES:
        return REJECT_SIDE
    if _text(setup.get("setup_type")).upper() not in SETUP_TYPES:
        return REJECT_TYPE
    if not _text(setup.get("setup_owner")):
        return REJECT_OWNER
    entry = _real(setup.get("entry_reference"))
    stop = _real(setup.get("invalidation_price"))
    target = _real(setup.get("target_price"))
    if entry is None or stop is None or target is None:
        return REJECT_PRICES
    if entry <= 0 or stop <= 0 or target <= 0:
        return REJECT_PRICES
    if side == BUY and not (stop < entry < target):
        return REJECT_GEOMETRY
    if side == SELL and not (target < entry < stop):
        return REJECT_GEOMETRY
    if not (_text(setup.get("invalidation_source"))
            and _text(setup.get("invalidation_reason"))):
        return REJECT_WHY
    if not (_text(setup.get("target_source")) and _text(setup.get("target_reason"))):
        return REJECT_TARGET_WHY
    created = _real(setup.get("created_at")) or 0.0
    expires = _real(setup.get("expires_at")) or 0.0
    if expires <= created:
        return REJECT_EXPIRY
    return OK


def setup_risk(setup: dict[str, Any]) -> float:
    """مسافة الإبطال — ما يخسره الحساب إن ماتت الفكرة."""
    entry = _real(setup.get("entry_reference")) or 0.0
    stop = _real(setup.get("invalidation_price")) or 0.0
    return abs(entry - stop)


def setup_reward(setup: dict[str, Any]) -> float:
    """مسافة الهدف — ما تقصده الفكرة."""
    entry = _real(setup.get("entry_reference")) or 0.0
    target = _real(setup.get("target_price")) or 0.0
    return abs(target - entry)


def setup_ratio(setup: dict[str, Any]) -> float:
    """نسبة الإعداد — **خاصّية للفكرة** لا بوّابة تُطبَّق عليها لاحقًا.

    هذا الفرق هو كل الفرق: نسبةٌ تخرج من الفكرة تُعاير إحصائيًّا، ونسبةٌ
    تُحسب بين رقمين اختارتهما طبقتان مختلفتان لا تعني شيئًا.
    """
    risk = setup_risk(setup)
    return (setup_reward(setup) / risk) if risk > 0 else 0.0


# ٢٠٢٦-٠٩-١٠ (حكم المالك، نقض حكم ٢٠٢٦-٠٩-٠٦): «نحن سكلبنك» ·
# «من 7 إلى 10 على يورو». الحكم القديم («هدف 300 أو 500، ستوب لا يقلّ
# عن 100») كان مقيسًا على سبريد **38.54**، والسبريد اليوم مقيس أصغر
# بكثير: BTCUSD 5.42 · US30 1.20 · USTEC 1.00 · XAUUSD 0.12 — فالظرف
# الذي بُني عليه ذلك الحكم زال، والمالك نقضه صراحةً.
#
# ⛔ وخطأ في الحكم القديم يُصحَّح هنا للسجلّ: تعليقه اشتقّ النسبتين من
#    «100 ÷ 80,000 و300 ÷ 80,000» = 0.00125 و0.00375، بينما الكود حمل
#    0.00005 و0.00035 — أصغر بـ25 و11 ضعفًا. انزلاق فاصلة عشرية جعل
#    العتبتين أضعف بكثير ممّا ظنّه كل من قرأ تعليقهما.
#
# الرقم الجديد مشتقّ من رقم المالك لا من رأيي:
#   7 نقاط على EURUSD @ 1.1636  =  0.0007 ÷ 1.1636  =  0.0006
# وعلى بقيّة الرموز بالنسبة نفسها: XAUUSD ≈ 2.65$ · BTCUSD ≈ 47$ ·
# USTEC ≈ 17.6 نقطة · US30 ≈ 27.6 نقطة.
#
# والهدف الأدنى رُفع معه إلى القيمة نفسها **لا إلى نسبة مخترعة**:
# المالك حدّد الوقف ولم يحدّد الهدف، وترك الهدف الأدنى (4.1 نقطة) دون
# الوقف الأدنى (7 نقاط) يسمح بفكرةٍ هدفها أقرب من وقفها — شذوذٌ لا
# يقصده أحد. فالمساواة هي أقلّ ما يمنع الشذوذ بلا اختراع نسبة.
#
# ⚠️ وهذا وحده لا يعطي وقفًا 7-10: حين تُرفض كل الإعدادات يبقى العيار
#    `stop_distance_frac` في ٥٢٣ هو المصدر (0.00325 = 37.8 نقطة على
#    اليورو). تعديل ٥٢٣ خارج هذا القسم وأُرسل إلى مختصّه بطلب المالك.
MIN_INVALIDATION_FRAC = 0.0006
MIN_TARGET_FRAC = 0.0006

# ٢٠٢٦-٠٩-١٢ (ختم NQ): العتبة أعلاه كانت **مخلوطة** — نفس الخطأ الذي أمر
# المالك بإزالته من مقياس القوّة، وقعتُ فيه هنا بعده بساعات.
#
#   0.0006 على EURUSD = 7 نقاط        ← رقم المالك، صحيح
#   0.0006 على BTCUSD = $46.80        ← وهو أمر بـ$20 إلى $40 ⇒ تخالفه
#
# ومقيس على سجلّ ٢٠٢٦-٠٩-١١: **ولا إعداد واحد في أيّ رمز بلغ العتبة**،
# فلم يُنشر إعدادٌ واحد ذلك اليوم (109 رفضًا كلّها SCALE_TOO_SMALL).
# وسيط ما تقترحه الاستراتيجيات فعلًا:
#   BTCUSD 0.000133 (4.5× أصغر)  ·  XAUUSD 0.000043 (14×)
#   USTEC  0.000036 (17×)        ·  US30   0.000062 (10×)
#
# ⚠️ وفصلٌ لزم توضيحه: أرقام المالك ($20-$40 لبتكوين · 7-10 نقاط لليورو)
#    تحكم **الوقف الفعلي** وموضعها عيار ٥٢٣ `stop_bounds_by_symbol` وقد
#    نُفّذت هناك. وهذه العتبة شيءٌ آخر: أدنى حجمٍ يستحقّ أن **يُقترَح**.
#    خلطُ الاثنين هو ما جعل عتبةً تخنق قسمًا كاملًا.
#
# فالأرضية صارت **السبريد المقيس لكل رمز**: فكرةٌ إبطالها أضيق من تكلفة
# عبورها لا معنى لها — مبرَّرٌ اقتصاديًّا، لا رقمٌ من عندي. ومن لا سبريد
# مقيس له يبقى على الثابت أعلاه.
# ⛔ والفشل آمن: ملفّ غائب أو تالف ⇒ الثابت، بلا استثناء.
def runtime_var_file(*parts: str) -> Path:
    """`<جذر التشغيل>/var/<parts>` من مالك الجذور (`shared.runtime_paths.runtime_var`).

    ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): المسارات هنا وفي `strategy_contract` و
    `structure_exits` كانت محفورة على `<المشروع>/forex_runtime/var/…` فتتجاهل
    `QUANT_RUNTIME_ROOT` — فالفحوص والإعادة تقرأ ملفّات المنصّة الحيّة. والمنصّة
    الحيّة تُقلع بـ`QUANT_RUNTIME_ROOT=<المشروع>/forex_runtime` فالمسار فيها نفسه حرفًا.
    وتعذّر الاشتقاق لا يرجع إلى الحيّ حين يُعلَن جذرٌ آخر: المتغيّر المضبوط يبقى
    المرسى ولو لم يوجد مجلّده (الملفّ غائب ⟵ السلوك الآمن نفسه). وبلا متغيّرٍ ولا
    جذرٍ صالح: المسار التاريخيّ كما كان.
    """
    code_root = Path(__file__).resolve().parents[1]
    try:
        from shared.runtime_paths import runtime_var
        return runtime_var(*parts, code_root=code_root)
    except (RuntimeError, OSError, ImportError):
        override = str(os.environ.get("QUANT_RUNTIME_ROOT") or "").strip()
        base = Path(override) if override else code_root / "forex_runtime"
        return base.joinpath("var", *parts)


_FLOOR_PATH = runtime_var_file("telemetry", "analysis_scale.json")
_FLOOR_CACHE: dict[str, Any] = {"mtime": None, "table": {}}

from shared.fs_stamp import file_stamp  # noqa: E402


def _floor_frac(symbol: Any) -> tuple[float, float] | None:
    """أرضية (الإبطال، الهدف) لهذا الرمز — من سبريده المقيس.

    ⛔ **أرضيّةُ الحركة جُرِّبت هنا ٢٠٢٦-٠٩-١٨ وسُحبت في اليوم نفسه.** رفعتُها
    من السبريد إلى الحركة الوسيطة (بتكوين ٥٫٠٠ ⟵ ٦٤٫٥٠)، فرُفض **كلّ** إعدادٍ
    تبنيه ٤٠٦ و٤١٠ — مخاطرتها الحقيقيّة ١١٫٨٢. والنتيجة أسوأ لا أفضل: توقّف
    التحليل عن إعطاء وقفٍ أصلًا، فصار ٥٥٥ يبنيه من احتياطيّ ٥١٣ (`FALLBACK_513`)
    بلا رأيٍ خلفه. **وقفٌ رديءٌ من تحليل خيرٌ من وقفٍ بلا تحليل.**

    والحكم صحيحٌ والموضع خطأ: وقفٌ دون حركة الرمز يقع داخل الضجيج فعلًا
    (بتكوين ١١٫٦ يعيش إحدى عشرة تِكّة)، لكنّ مكان هذا الحكم **إعلانٌ في
    البطاقة عند ٤٦٥** (`465.scale` و`دون_أرضيّة_الحركة`) لا حاجزٌ عند المنتج.
    فيُقاس الثمن قبل أن يُدفع. ولا يُشدَّد هذا الحاجز حتى يبني ٤٠٦/٤١٠ وقفًا
    بمقياس الحركة — وذاك يحتاج `VOL_PAD_MULT` معه، وهدفًا يكبر مع الوقف.

    الأصل المحفوظ أدناه كما كان قبل التجربة.

    ختم `NQ` ٢٠٢٦-٠٩-١٨. كانت الأرضيّة `السبريد ÷ السعر`، أي أنّه يكفي
    الوقفَ أن يغطّي تكلفة العبور. ومقيسٌ أنّ ذلك أصغر من حركة الرمز
    الوسيطة **٧×–٢٠×** (بتكوين ٥٫٠٠ مقابل ٦٤٫٧١)، فالوقف يقع داخل الضجيج
    ويُضرب قبل أن تتحرّك الفكرة — ونسبتُه تبدو `1:20` لصغر مقامها لا لقرب
    هدفها. وذاك تفسير ١٢٦ خاسرة من ١٩٨.

    ومقيسٌ أقسى منه: وقفُ بتكوين اليوم (١١٫٦) يعيش **إحدى عشرة تِكّة**،
    وحافّةُ المنصّة الوحيدة المؤكَّدة (٤٠٩ على داو) لا تدفع قبل **ألف**.
    فالخروج يقع في واحدٍ بالمئة من المدّة التي تحتاجها الفكرة كي تُثمر.

    والأرضيّة الآن حركةُ الرمز الوسيطة المقيسة (`movement` في
    `analysis_scale.json`، يولّده `scripts/scale_refresh.py`). ومن لا حركةَ
    مقيسة له يرجع إلى السبريد كما كان — لا يُحجب لغياب قياس.
    """
    key = str(symbol or "").strip().upper()
    if not key:
        return None
    ok, stamp = file_stamp(_FLOOR_PATH)
    if not ok:
        return None
    if _FLOOR_CACHE["mtime"] != stamp:
        try:
            import json
            rows = json.loads(_FLOOR_PATH.read_text(encoding="utf-8")).get("symbols")
            _FLOOR_CACHE["table"] = rows if isinstance(rows, dict) else {}
        except Exception:
            _FLOOR_CACHE["table"] = {}
        _FLOOR_CACHE["mtime"] = stamp
    row = _FLOOR_CACHE["table"].get(key)
    if not isinstance(row, dict):
        return None
    try:
        spread = float(row.get("spread"))
        price = float(row.get("price"))
    except (TypeError, ValueError):
        return None
    if not (price > 0 and spread > 0):
        return None
    frac = spread / price
    return (frac, frac)

# ٢٠٢٦-٠٩-٠٧ (حكم المالك المقيس): «بتكوين تحرّك 750 دولار على فريم
# دقيقة وسبريده 3.5 ولا صفقة — هذا مو شغل على سوق سريع».
#
# القياس أثبته: السوق تحرّك 720.35$ في ساعة (12$/دقيقة) بينما إبطال 410
# هو مسافة الكنس — رقم مجهريّ ≈4.5$ لا علاقة له بتقلّب السوق. عمر
# الفكرة المتوقّع 22 ثانية، ومهلتها 120. فماتت 23 فكرة بـALREADY_BROKEN
# وEXPIRED قبل ربع مهلتها.
#
# إبطالٌ ثابت في سوق متغيّر التقلّب = نظام يعمل ليلًا ويصمت نهارًا.
# فالإبطال يبقى بنيويًّا (طرف الكنس · حدّ المدى) لكن بهامش يعرف السوق
# الذي يقيس فيه: نافذة 120 تِكّة تساوي ~90 ثانية في السوق السريع و~3.5
# دقائق في الهادئ، فيصير الهامش ~33$ نهارًا و~10$ ليلًا — من الرقم
# لا من رأي أحد.
# المعامل مقيس لا مقدَّر: على 30 ألف تِكّة، القبول بلغ ذروته عند 0.15
# (127 إعدادًا) وانهار إلى 45 عند 1.0 لأن الهامش صار أكبر من الهدف.
# ووقفه الوسطيّ 15.4$ يطابق P99 للحركة المعاكسة عند الثانية (16.57).
VOL_WINDOW = 120
# ختم `NQ` ٢٠٢٦-٠٩-١٨ — `0.15` ⟵ `2.5`، بقياسٍ التقى فيه قيدان مستقلّان:
#
#   الرمز    تقلّب ١٢٠   يلزم لأرضيّة المالك   يلزم للصمود ١٠٠٠ تِكّة
#   الذهب      1.090          1.83×                  2.42×
#   ناسداك     6.100          2.46×                  2.47×
#   بتكوين    49.960            —                    2.34×
#
# القيد الأوّل حكمُ المالك («دهب مافي أقلّ من ٢ دولار») وحدُّ تكلفة العبور
# عند المئين ٨٠ معه. والثاني مقيسٌ من السوق: أقصى حركةٍ معاكسة داخل ألف
# تِكّة — وهو الأفق الذي تدفع عنده الحافّة الوحيدة المثبتة (٤٠٧ فوق قوّة ٢٩،
# صمدت في ثلاث نوافذ من أربع). ولا يجتمعان صدفةً: كلاهما يقول إنّ الوقف
# يجب أن يتجاوز ضجيج نافذته مرّتين ونصفًا لا أن يكون سُبعه.
#
# والثمن المقيس قبل التغيير: وقف الذهب `0.153` مقابل أرضيةٍ `2.00` — **فرق
# ثلاثة عشر ضعفًا**، و٩٠ أمرًا من ٩٤ رُفضت بـ`STOP_BELOW_FLOOR`. ووقف بتكوين
# `11.6` يعيش **إحدى عشرة تِكّة** بينما الحافّة تحتاج ألفًا.
#
# ⚠️ وقياسٌ قديم يقول إنّ رفعه يُسقط القبول (١٢٧ ⟵ ٤٥ عند `1.0`): صحيحٌ
# وسببه أنّ الهدف بنيويٌّ لا يكبر مع الوقف. فما يسقط الآن يسقط **بحقّ** —
# نسبةٌ دون الثلاثة على وقفٍ صادق خيرٌ من نسبةٍ جميلة على وقفٍ داخل الضجيج.
# و٤٦٥ يعدّ الساقط (`رفض_نسبة`) فيُقرأ الثمن بالرقم لا بالظنّ.
VOL_PAD_MULT = 2.5

#: النسبة المطلوبة تُبنى ولا تُرشَّح. حكم المالك ٢٠٢٦-٠٩-١٢: «النظام يحكم على
#: ناتجٍ بدل أن يحكم المُدخَل — مواصفة الصفقة يجب أن تكون **مدخلًا للبناء**
#: لا مرشّحًا». فكان الهدف بنيويًّا وحده والنسبة تُفحص بعده فتُرفض الصفقة؛
#: والآن: الهدف البنيويّ يُؤخذ إن كان أبعد، وإلّا يُمدّ إلى ما تقتضيه النسبة.
#: ولا يُخترع سعرٌ من عدم — المدّ مشتقٌّ من **وقفٍ مقيس** ونسبةٍ مختومة،
#: ومصدره يُعلَن `ratio_extended` فلا يُقرأ مستوًى هيكليًّا وهو ليس كذلك.
MIN_REWARD_RATIO = 3.0
TARGET_EXTENDED = "ratio_extended"


def tick_volatility(prices, window: int = VOL_WINDOW) -> float:
    """تقلّب مقيس على التِكّة: مدى آخر `window` سعرًا."""
    recent = list(prices)[-window:]
    if len(recent) < 2:
        return 0.0
    return float(max(recent) - min(recent))


def volatility_pad(prices, window: int = VOL_WINDOW,
                   mult: float = VOL_PAD_MULT) -> float:
    """هامش الإبطال: ما دون هذا ضجيجٌ لا إبطال."""
    return tick_volatility(prices, window) * mult


def meets_scale(setup: dict[str, Any]) -> bool:
    """هل الفكرة بحجمٍ يستحقّ التنفيذ أصلًا؟

    سؤالٌ يسبق الاقتصاد: صفقةٌ هدفها تسع وثلاثون نقطة على رمزٍ سبريده
    ثمانٍ وثلاثون ليست فكرةً ضعيفة الاقتصاد بل فكرةٌ في غير مقياسها.
    """
    entry = _real(setup.get("entry_reference"))
    if entry is None or entry <= 0:
        return False
    # الأرضية من سبريد الرمز المقيس؛ والثابت المخلوط احتياطٌ لمن لا قياس له.
    floor = _floor_frac(setup.get("symbol"))
    stop_frac, target_frac = floor if floor else (MIN_INVALIDATION_FRAC, MIN_TARGET_FRAC)
    return (setup_risk(setup) >= entry * stop_frac
            and setup_reward(setup) >= entry * target_frac)


def round_trip_cost(bid: Any, ask: Any) -> float:
    """تكلفة العبور الاقتصادية للجهتين — لا نصفها ولا ضعفها.

    حكم المالك ٢٠٢٦-٠٩-٠٦: «احسب التكلفة اقتصاديًّا على الجهتين». وعلى
    وسيط ذي سعرين، الدورة الكاملة تدفع السبريد **مرّة واحدة**: الشراء
    يدخل على `ask` ويخرج على `bid`، والبيع بالعكس. فالسبريد هو تكلفة
    الذهاب والإياب مجتمعةً، لا تكلفةَ كلّ جهة على حدة.
    """
    top = _real(ask)
    bottom = _real(bid)
    if top is None or bottom is None:
        return 0.0
    return max(0.0, top - bottom)


def net_ratio(setup: dict[str, Any], cost: float) -> float:
    """نسبة العائد إلى المخاطرة **بعد** التكاليف — اقتصاد الصفقة لا هندستها.

    حكم المالك ٢٠٢٦-٠٩-٠٦ بعد أن قِيس أن ٨١٪ من الأفكار تُرفض لأن
    إبطالها أضيق من سبريد: «المهم ليس أن risk < spread، بل هل الخطر
    الاقتصادي الصافي والربح الاقتصادي الصافي ما زالا يحقّقان الحدّ».

        reward_net = العائد الخام − تكلفة العبور
        risk_net   = الخطر الخام + تكلفة العبور
        net_rr     = reward_net / risk_net

    فكرةٌ إبطالها ٣ وهدفها ٤٠ بتكلفة ٥ ⇒ 35 ÷ 8 = 4.38 — تُقبل.
    وفكرةٌ إبطالها ٢٠ وهدفها ٢٥ بالتكلفة نفسها ⇒ 20 ÷ 25 = 0.80 — تُرفض.
    الضيق ليس عيبًا، والاتّساع ليس فضيلة؛ الاقتصاد وحده يحكم.
    """
    cost = max(0.0, float(cost or 0.0))
    risk_net = setup_risk(setup) + cost
    reward_net = setup_reward(setup) - cost
    if risk_net <= 0.0 or reward_net <= 0.0:
        return 0.0
    return reward_net / risk_net


#: أدنى مسافة وقفٍ بنقاط الأساس — الحكم الواحد في 405 و406 و410 وعند الإرسال في 555.
#: ٢٠٢٦-١٠-٠١ ختم المالك «Nq»: 10 لكلّ الرموز (الوقف الأضيق من 5 ن.أ صنع −7,390$ من −8,888$ في أيلول).
#: ٢٠٢٦-١٠-٠٦ 14:50 ختمه «نقاط أساس خليها 3 مو 10 NQ» ثمّ 15:4x ختمه «NQ» على «حدّ 3 للناسداك وحده،
#: ويعود 10 للداو والباقي» — بعد أن فتح الداو صفقةً بوقف 20 نقطة (3.9 ن.أ) ضُربت في 3 دقائق (−90.9$).
#: ٢٠٢٦-١٠-١٧ ختم المالك «nq»: **بالبِب لا بنقاط الأساس** («ما في شي اسمه نقاط أساس») — حُوّلت بأسعار ذلك اليوم فلا يتغيّر الحكم يومها:
#: الناسداك 3 ن.أ × 29,194 = 8.8 ⟸ 9 بِب (نقطة) · الداو 10 × 51,969 ⟸ 52 · الإس آند بي ⟸ 8 · الذهب 4.17$ ⟸ 42 بِب (0.1) · البتكوين ⟸ 82 ·
#: اليورو 1.1239 ⟸ 11 · الجنيه 1.3326 ⟸ 13 · وبقيّة العملات 10 بِب. والرقم ثابتٌ الآن لا يتبع السعر — يعدّله المالك.
#: ٢٠٢٦-١٠-١٧ ختم المالك «nq» بأرقامه: الذهب «حطّه 15» · «50 للبتكوين و10 للداو جونز، فوركس أجمع 5» (كلّ العملات 5)؛
#: الناسداك 9 والإس آند بي 8 وغير المعروف 10 لم يذكرهنّ فبقين.
# ١٧/١٠ (ختم المالك «عمّم وقف 20 Nq»): الناسداك 9 ⟵ 20 — مع حدّ وقف الاستراتيجيّات (facts_strategies.STOP_PIPS)، فلا يمرّ وقفٌ أصغر.
# ٢٣/١٠ (ورقة «خطوط حمراء» المختومة، القانون 5 «حارسٌ لا طريقة عمل»): الناسداك 20 ⟵ 9 — الحارس يرجع إلى رقمه، ووقف الاستراتيجيّة
# 20–45 باقٍ في `facts_strategies.STOP_PIPS` (البند 27 للنقاش)، فلا يتغيّر وقفٌ واحدٌ يُرسَل اليوم.
MIN_STOP_PIPS_BY_SYMBOL: dict[str, float] = {"USTEC": 9.0, "US30": 10.0, "US500": 8.0, "XAUUSD": 15.0, "BTCUSD": 50.0}
MIN_STOP_PIPS_FOREX = 5.0
MIN_STOP_PIPS_DEFAULT = 10.0


def min_stop_pips(symbol: Any) -> float:
    """أدنى وقفٍ مقبول لهذا الرمز بالبِب (`shared.pips`) — كلّ أزواج العملات 5."""
    from shared.pips import is_forex
    sym = _text(symbol).upper()
    if sym in MIN_STOP_PIPS_BY_SYMBOL:
        return MIN_STOP_PIPS_BY_SYMBOL[sym]
    return MIN_STOP_PIPS_FOREX if is_forex(sym) else MIN_STOP_PIPS_DEFAULT


def is_alive(setup: dict[str, Any], now: float | None = None) -> bool:
    """هل الإعداد ما زال يصف السوق الحاضر؟"""
    stamp = float(now if now is not None else time.time())
    return stamp < (_real(setup.get("expires_at")) or 0.0)


def is_target_reached(setup: dict[str, Any], price: Any) -> bool:
    """هل بلغ السعرُ هدفَ الفكرة قبل الدخول؟

    سؤالٌ عن **فوات الفرصة**، لا عن صحّة الهندسة. الدخول بعد بلوغ الهدف
    مطاردةٌ للحركة لا تنفيذٌ لفكرة، ولا عائد يبقى فيها.
    """
    current = _real(price)
    target = _real(setup.get("target_price"))
    if current is None or target is None:
        return False
    return current >= target if _text(setup.get("side")) == BUY else current <= target


def geometry_matches_entry(setup: dict[str, Any]) -> bool:
    """هل الإبطال والهدف متّسقان مع **مرجع الدخول**؟

    حكم المالك ٢٠٢٦-٠٩-٠٦: الهندسة تُقاس على `entry_reference` لا على
    السعر الحاليّ. السعر الحاليّ يجيب سؤالًا آخر تمامًا — «هل فاتت
    الفكرة؟» — وخلط السؤالين كان يُصنّف مئةً وواحدًا وعشرين إعدادًا
    سليمًا بأنه «هندسة مقلوبة» لمجرّد أن السعر تحرّك بعد ولادته.
    """
    entry = _real(setup.get("entry_reference"))
    stop = _real(setup.get("invalidation_price"))
    target = _real(setup.get("target_price"))
    if entry is None or stop is None or target is None:
        return False
    if _text(setup.get("side")) == BUY:
        return stop < entry < target
    return target < entry < stop


def is_broken(setup: dict[str, Any], price: Any) -> bool:
    """هل تجاوز السعرُ الإبطال فماتت الفكرة؟

    يُستعمل قبل الدخول (فلا يُفتح إعداد مات) وبعده (فيعرف 577 ما يحرس).
    """
    current = _real(price)
    stop = _real(setup.get("invalidation_price"))
    if current is None or stop is None:
        return False
    return current <= stop if _text(setup.get("side")) == BUY else current >= stop
