"""ورقة ١٥ §١٢-0 · §١٢-1 · §١٢-2 — تطبيق العقد الموحّد على أقسام التحليل.

لماذا غلاف بدل تعديل ٥٩ ذرّة يدويًّا؟
    كل ذرّة في الأقسام 150 · 200 · 250 · 300 · 350 · 400 تنشر عبر
    `self._context.publish` وتشترك عبر `context.subscribe`. الغلاف يعترض
    الطرفين: يلتقط الهوية (account_id · broker) من الحمولة الداخلة ويطبع
    العقد الموحّد على الحمولة الخارجة. الذرّة لا تفقد سطرًا من منطقها.

⛔ قيد مقيس — لماذا العقد في كتلة `unified` لا في أعلى الحمولة:
    `confidence` اليوم 0..1 في 88 ذرّة، ويقرأها 451 و452 و460 كعتبة.
    وضع 0..100 مكانها يقلب كل فلتر ثقة في المنظومة.
    `strength` في 151 نصّ ("weak"/"strong") لا رقم.
    `direction` في 350 يُقرأ من metadata، وحقن رقم مكانه يقطع الاحتياط.
  ⇒ العقد كامل داخل `unified`، ويُضاف أعلى الحمولة فقط ما لا يتصادم:
    account_id · broker · symbol · section_id · atom_id · state.

الحقول غير المحسوبة (weight · ratio) تُنشر بصفر وتُعلَن `unknown` صراحةً
في `unified["unknown_fields"]` — «ما يُحسب افتراضيًّا هو كذب» (§١١).
"""
from __future__ import annotations

import contextvars
import math
import os
from typing import Any, Callable

import clock
from core.contracts.atom import AtomContext

from shared.parameter_registry import REASON_UNAPPROVED, unapproved_parameters

from shared.unified_contract import (
    ALL_STATES, STATE_ANALYZING, STATE_ERROR, STATE_INVALID,
    STATE_NOT_READY, STATE_READY, STATE_STALE,
)

REASON_IDENTITY = "IDENTITY_INCOMPLETE"
#: العقد الموحّد — `READY` لا تُمنح لمخرَج لا اتجاه معلومًا فيه.
REASON_DIRECTION_UNKNOWN = "DIRECTION_UNKNOWN"
#: NQ seal item 22 (A8): a missing required_depth is UNKNOWN, never a silent
#: 100. READY is withheld with this explicit reason -- not by comparing the
#: measured depth against an invented bar.
REASON_REQUIRED_DEPTH_UNKNOWN = "REQUIRED_DEPTH_UNKNOWN"
#: §١٤ — بعده تُعدّ النتيجة قديمة. نفس حدّ `live_analysis.stale_after_s`
#: و`section_live.DEFAULT_TTL_S` — حدّ واحد لا ثلاثة تتباعد (§٥٢).
#: ⛔ (٢٠٢٦-٠٨-٢٥ · نمط «مفتاح بلا سلك»، سجلّ الختم بند 47): المالك اعتمد
#:    `STALE_AFTER_S=10.01` بالسجلّ المحكوم وهذا الثابت بقي `5.0` محفورًا
#:    بصفر قارئ للاعتماد. الثابت الآن **افتراضٌ يسقط إليه فقط**، والقيمة
#:    السارية تُقرأ من السجلّ عبر `stale_after_s()`.
STALE_AFTER_S = 5.0


def stale_after_s() -> float:
    """أفق الطزاجة الساري — قيمة المالك المعتمدة، أو الافتراض المعلَن."""
    from shared.parameter_registry import approved_value
    return approved_value("STALE_AFTER_S", STALE_AFTER_S)

_DIRECTION_WORDS = {
    "buy": 1.0, "long": 1.0, "up": 1.0, "bullish": 1.0, "bull": 1.0,
    "swing_low": 1.0, "buyside": 1.0, "breakout_up": 1.0,
    "sell": -1.0, "short": -1.0, "down": -1.0, "bearish": -1.0, "bear": -1.0,
    "swing_high": -1.0, "sellside": -1.0, "breakout_down": -1.0,
    "sideways": 0.0, "range": 0.0, "ranging": 0.0, "neutral": 0.0,
    "flat": 0.0, "none": 0.0,
    # ٢٠٢٦-١٠-٠٥ (ختم المالك «ما بدي ولا قسم ما يشارك ل صفقة nq»): كلماتُ قسم البنية التي
    # كانت تقع خارج القاموس فيُختم اتّجاهها مجهولًا ⟸ `NOT_READY` لوحدتين إلزاميّتين.
    # مقيس من البثّ الحيّ: 207 ينشر «downtrend» بقوّة 40 واتّجاهه في العقد `null`.
    # قمّةٌ أعلى/قاعٌ أعلى = صعود (202/203)، وقاعٌ أدنى/قمّةٌ أدنى = هبوط؛ و«transition»
    # (تغيّر الطابع بلا تأكيد) حيادٌ مقيس لا مجهول.
    "hh": 1.0, "hl": 1.0, "uptrend": 1.0,
    "ll": -1.0, "lh": -1.0, "downtrend": -1.0,
    "transition": 0.0,
    # ومجمّع السيولة (251) على دلالة «buyside/sellside» القائمة أعلاه: سيولةُ شراءٍ فوق
    # القمم = جذبٌ صاعد، وسيولةُ بيعٍ تحت القيعان = جذبٌ هابط.
    "pool_high": 1.0, "pool_low": -1.0,
}

_STATUS_NOT_READY = ("insufficient_data", "warming_up", "not_ready")
_STATUS_INVALID = ("invalid", "rejected")
_STATUS_ERROR = ("error", "failed")
_STATUS_STALE = ("stale",)


def _num(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _text(value: Any) -> str:
    return str(value or "").strip()


def _pct(value: Any) -> float:
    number = _num(value)
    if number is None:
        return 0.0
    return max(0.0, min(100.0, number))


def _confidence_pct(value: Any) -> float:
    """الثقة تصل 0..1 من كل ذرّات التحليل — تُرفع إلى 0..100 داخل العقد فقط."""
    number = _num(value)
    if number is None:
        return 0.0
    if 0.0 <= number <= 1.0:
        number *= 100.0
    return max(0.0, min(100.0, number))


def _direction(payload: dict[str, Any], magnitude: float,
               magnitude_known: bool) -> tuple[float | None, bool, float | None]:
    """(الاتجاه · هل هو معلوم · إشارة الاتجاه) — والمجهول لا يصير حيادًا.

    ⛔ عطل مقيس: ذرّة تقول `buy` بلا مقدار مقيس كانت تُنتج
       `direction = ١ × ٠ = 0.0` **موسومًا معلومًا** — أي أنّ «أعرف
       الجهة ولا أعرف المقدار» كان يصل القرار بوصفه **حيادًا محسوبًا**.
       وهذا نصّ ما يمنعه العقد: `UNKNOWN ≠ NEUTRAL`.

    ✅ الآن: مقدارٌ غير مقيس ⇒ `direction` **مجهول** ويُعلَن في
       `unknown_fields`، وتبقى الجهة محفوظةً في `direction_sign`
       (`-1` · `0` · `+1`) — فلا تضيع المعلومة ولا تُزوَّر.
    """
    raw = payload.get("direction")
    number = _num(raw)
    if number is not None and not isinstance(raw, bool):
        value = max(-100.0, min(100.0, number))
        sign = 0.0 if value == 0.0 else (1.0 if value > 0 else -1.0)
        return value, True, sign
    metadata = payload.get("metadata")
    words = [raw, payload.get("signal"), payload.get("bias")]
    if isinstance(metadata, dict):
        words.append(metadata.get("direction"))
    for word in words:
        key = _text(word).lower()
        if key in _DIRECTION_WORDS:
            sign = _DIRECTION_WORDS[key]
            value = sign * magnitude if magnitude_known else None
            return value, magnitude_known, sign
    return None, False, None


_REPLAY_NOW = {"t": 0.0}


def _reference_now(source: float) -> float:
    """الآن المرجعيّ لقياس العمر.

    ⚠️ وضع الإعادة التاريخية (`QUANT_REPLAY_CLOCK=1`): العمر يُقاس مقابل
    **أحدث طابع بيانات مرّ**، لا مقابل ساعة الحائط. السبب مقيس ٢٠٢٦-٠٩-٠٧:
    البطاقات التاريخية تحمل طوابع أقدم من الساعة الحيّة بأيام، فيعطي
    `clock.now() - source > 5.0` قِدَمًا فوريًّا لكل بطاقة ⇒ الأقسام
    200/250/300 = `STALE` ⇒ `aggregate_state = STALE` ⇒ 456 يرفض بـ
    `STATE_NOT_READY` ⇒ `601 written=0`. القياس نفسه (الفارق مقابل العتبة)
    لا يتغيّر — يتغيّر المرجع وحده، فيبقى الحكم على القِدَم **نسبيًّا**
    داخل الشريط الزمنيّ المُعاد تشغيله.
    الافتراضي بلا المتغيّر: `clock.now()` حرفًا بحرف.
    """
    if os.environ.get("QUANT_REPLAY_CLOCK", "").strip() != "1":
        return clock.now()
    if source > _REPLAY_NOW["t"]:
        _REPLAY_NOW["t"] = source
    return _REPLAY_NOW["t"]


def _is_stale(payload: dict[str, Any]) -> bool:
    """§٧ · §١٤ — نتيجة يمكن قياس عمرها وتجاوز الحدّ ⇒ `STALE`.

    ⛔ عمرٌ **غير قابل للقياس** لا يُترجم قِدَمًا ولا حداثة: الورقة تقول
       «النتيجة القديمة STALE»، لا «المجهولة قديمة». فالذرّات التي لا
       ترسل طابعًا زمنيًّا تبقى على حكم العمق والهوية وحدهما، ويُكشف
       نقصها في `unknown_fields` لا هنا.
    """
    source = _num(payload.get("source_timestamp"))
    if source is None or source <= 0:
        return False
    return (_reference_now(source) - source) > stale_after_s()


def _state_of(payload: dict[str, Any],
              identity_ok: bool) -> tuple[str, float, float, bool, bool, bool]:
    """(الحالة · العمق الحالي · العمق المطلوب · هل العمق مقيس) — لا حساب افتراضي.

    ⛔ العمق الذي لم تُرسله الذرّة **مجهول**، ولا يُفترض بلوغه.
       كان السطر السابق يرفع أيّ حمولة `status="ok"` بلا `current_depth`
       إلى `100/100 ⇒ READY`؛ فيكفي أن يقول قسمٌ «ok» ليَعبُر بلا أن
       يُثبت عمقًا. المجهول الآن يبقى `0` ويُعلَن في `unknown_fields`
       ولا يبلغ `READY` أبدًا — «ما يُحسب افتراضيًّا هو كذب» (§١١)،
       و«العمق الناقص يمنع READY» (§١٢-2).

    NQ seal item 22 (A8) -- returns a 6-tuple:
    (state, current_depth, required_depth, depth_known, required_known,
    required_blocks_ready). A missing required_depth no longer becomes a
    silent 100: the depth gate compares only against a KNOWN requirement,
    and an unknown requirement withholds READY explicitly (last element
    True) instead of failing a fabricated `current < 100` comparison.
    """
    given = _text(payload.get("state")).upper()
    current = _num(payload.get("current_depth"))
    required = _num(payload.get("required_depth"))
    # Missing required_depth stays UNKNOWN (0.0 + declared) -- never 100.
    required_known = required is not None
    required = 0.0 if required is None else max(0.0, min(100.0, required))
    status = _text(payload.get("status")).lower()
    depth_known = current is not None
    current = 0.0 if current is None else max(0.0, min(100.0, current))
    # §٧ — الحالة المُعلَنة من الذرّة تُحترم ما دامت **لا تمنح امتيازًا**:
    #   `DORMANT` · `INVALID` · `ERROR` · `STALE` · `NOT_READY` · `ANALYZING`
    #   كلّها تقييد، فتمرّ كما هي.
    #   ⛔ أمّا `READY` فلا تمرّ بالإعلان: كانت الذرّة تستطيع كتابة
    #      `state="READY"` فتتخطّى فحص الهوية والعمق كلّه — وهذا يفتح
    #      بوّابة القرار بادّعاء. الآن `READY` تُبنى من البوّابة وحدها.
    if given in ALL_STATES and given != STATE_READY:
        return given, current, required, depth_known, required_known, False
    if not identity_ok:
        return STATE_INVALID, current, required, depth_known, required_known, False
    if status in _STATUS_ERROR:
        return STATE_ERROR, current, required, depth_known, required_known, False
    if status in _STATUS_INVALID:
        return STATE_INVALID, current, required, depth_known, required_known, False
    if status in _STATUS_STALE or _is_stale(payload):
        return STATE_STALE, current, required, depth_known, required_known, False
    # Depth gate: only a KNOWN requirement may be compared against.
    if (status in _STATUS_NOT_READY or not depth_known
            or (required_known and current < required)):
        return STATE_NOT_READY, current, required, depth_known, required_known, False
    complete = payload.get("complete")
    if isinstance(complete, bool):
        # حمولة مُجمِّع (200 · 250 · 300 · 350 · 400): دورة مكتملة **وعمق مقيس**.
        candidate = STATE_READY if complete else STATE_NOT_READY
    elif not status:
        candidate = STATE_ANALYZING
    else:
        candidate = STATE_READY
    if candidate == STATE_READY and not required_known:
        # READY needs a known, met depth requirement -- withheld explicitly.
        return STATE_NOT_READY, current, required, depth_known, required_known, True
    return candidate, current, required, depth_known, required_known, False


# هوية الحدث الجاري معالجته الآن — لا سجلّ ولا ذاكرة عابرة للأحداث.
# `ContextVar` تحفظ العزل عبر `await`: كل سلسلة معالجة ترى هويتها وحدها.
_INBOUND: contextvars.ContextVar[tuple[str, str]] = contextvars.ContextVar(
    "quant_nq_inbound_identity", default=("", ""))


class _Identity:
    """ورقة الحلول §٢ — الهوية من الحمولة، أو تُورَّث من الحدث المسبِّب.

    ⛔ أُزيل سجلّ `_by_symbol` بالكامل — لم يُعطَّل فقط. كان عطلين في واحد:
       ١) الرمز ليس هوية: `(A/وسيط‑أ/NASDAQ)` و`(B/وسيط‑ب/NASDAQ)`
          يتقاسمان المفتاح، فآخر هوية تُتعلَّم تغطّي ما قبلها.
       ٢) حمولة ناقصة الهوية كانت تُكمَّل من السجلّ بهوية حسابٍ **آخر**
          بدل أن تُرفض — أي قرار يُنسَب لحساب لم يُرسله.

    ✅ ما حلّ محلّه ليس سجلًّا: مخرَج معالجة الحدث `E` يخصّ — بالضرورة
       السببيّة — حساب `E` ووسيطه. فالهوية تُورَّث من الحدث الجاري وحده،
       وتسقط فور انتهاء معالجته. هذا ليس «ذاكرة سابقة» ولا «fallback
       بالرمز» — وكلاهما ما يمنعه §٢. وبلا هذا التوريث تُطلب ٥٩ ذرّة
       داخلية بتمرير الهوية يدويًّا، وهو ما بُني `@section_atom` أصلًا
       لتجنّبه (انظر رأس الملف).

       وإن لم يحمل الحدث المسبِّب هوية كاملة أيضًا: الناقص يبقى ناقصًا ⇒
       `identity_complete=False` ⇒ `INVALID` + `IDENTITY_INCOMPLETE` (§١٥).
    """

    __slots__ = ()

    def learn(self, payload: Any) -> None:
        """لا شيء يُخزَّن — التوريث سببيّ عبر `_INBOUND` لا سجلّ."""

    def of(self, payload: dict[str, Any]) -> tuple[str, str]:
        account = _text(payload.get("account_id"))
        broker = _text(payload.get("broker"))
        if account and broker:
            return account, broker
        inbound_account, inbound_broker = _INBOUND.get()
        return account or inbound_account, broker or inbound_broker


#: ═══ عقد الحقائق (٢٠٢٦-١٠-٠٧، ختم المالك «NQ» — فكّ الأقسام عن القرار) ═══════════════════════
#: المالك: «لازم نسحب الوزن والثقة والعمق والقوّة من كلّ الأقسام… ما بيصير أيّ قسم يقول شراء أو بيع…
#: كلّهم لازم يزوّدوا الاستراتيجيّات بالتحليل الخام». فالقسم ينشر **حقيقته** وحدها: ما حسبه (`metadata`)،
#: ومتى (`as_of`)، وعلى كم حُسب (`computed_on`)، وأحداثه الواقعيّة (قاعٌ مؤكَّد · كسر · كنس) — ويُنزع كلّ حكم.
#: والقرار للاستراتيجيّة وحدها (البطاقة 414) تقرأ الحقيقة وتحاسب نفسها عليها.
FACTS_CONTRACT = "facts.v1"
#: حقول الحكم — لا تخرج من أيّ قسم بعد اليوم.
JUDGMENT_FIELDS = frozenset({
    "direction", "score", "strength", "confidence", "current_depth", "required_depth",
    "weight", "weight_applied", "weight_effect", "ratio", "probability",
    "directional_confidence", "directional_strength", "directional_units",
    "active_weight", "available_weight", "missing_weight", "readiness_pct",
    "confidence_threshold", "strength_threshold", "fusion_sign", "context_factor",
    "quality", "state", "ready", "analysis_state", "unified", "evidence", "evidence_map",
    "abnormality", "phase", "bias",
})
#: ٢٠٢٦-١٠-٠٧ (تدقيق الإغلاق): الحكم نفسه بأسماءٍ أخرى — يضيفها عقدا الاستراتيجيّة والاحتمالات فوق الحقيقة
#: (`shared/strategy_contract.py`: الجهة والوزن المعلنان وعامل الأفضليّة وحكمه وعتبة الثقة). مقيس: قارئها
#: الوحيد دفتر البطاقات يكتبها «رأيًا» — ولا رأي لقسمٍ بعد أمر المالك.
JUDGMENT_ALIASES = frozenset({"threshold", "declared_weight", "declared_direction", "edge_factor",
                              "edge_verdict"})
#: وداخل الحقيقة (`metadata`) لا يبقى حكمٌ صريح: احتمال الجهة · عامل السياق · الثقة · الوزن.
JUDGMENT_IN_FACTS = frozenset({"probability", "context_factor", "confidence", "weight",
                               "declared_direction", "declared_weight", "edge_factor", "edge_verdict"})
#: كلمات الجهة — حكمٌ لا حقيقة؛ تُنزع من `signal`. وأسماء الأحداث (قاعٌ مؤكَّد · كسر · كنس…) تبقى.
_JUDGMENT_WORDS = frozenset({"buy", "sell", "long", "short", "up", "down", "bullish", "bearish",
                             "bull", "bear", "sideways", "neutral", "uptrend", "downtrend",
                             # ٢٠٢٦-١٠-٠٧ (تدقيق الإغلاق): كلمات القوّة حكمٌ أيضًا — «نسحب … القوّة» (المالك).
                             "strong", "moderate", "medium", "weak", "strong_fit", "weak_fit",
                             # وحالة الاتّجاه وطور السوق (207 · 208 · 356): كانتا تُبنيان من «إشارة» جاراتهما،
                             # فبعد نزعها صارت 207 تقول «عرضيّ» والسوق صاعد (مقيس بسلسلةٍ حيّة) — حكمٌ زائف.
                             "range", "ranging", "transition", "early", "established", "extended"})
#: الحقول النصّيّة التي تُفحص قيمتها بكلمات الحكم (والحقل كلّه يُنزع إن كانت قيمته حكمًا).
_WORDED_FIELDS = ("signal", "level")
#: ١٨/١٠ (ختم المالك «NQ»: «صاعد، هابط، عرضيّ، انتقال / مبكّر، مستقرّ، ممتدّ — رجّعهم»): كلمة حالة الاتّجاه (207) وطور
#: السوق (208) تعود حقيقةً منشورة — لهاتين الذرّتين وحدهما وبكلماتهما وحدها، فالقائمة العامّة أعلاه لم تُمسّ. وسبب نزعها
#: يومها («عرضيّ» والسوق صاعد) عولج في 207: كلمتها قبل أوّل تحوّلٍ تُحسب من أرقام 151 بقاعدته نفسها.
SIGNAL_WORDS_KEPT = {"207": frozenset({"uptrend", "downtrend", "range", "transition"}),
                     "208": frozenset({"neutral", "early", "established", "extended"})}


def _computed_on(out: dict[str, Any]) -> Any:
    """على كم حُسبت الحقيقة **فعلًا** — العدد قبل حجم النافذة (٢٠٢٦-١٠-٠٧: كانت النافذة أوّلًا، فقالت
    316 بعد تِكّتين «حُسبت على 20»، و307 لم تعرف `points`)."""
    meta = out.get("metadata") if isinstance(out.get("metadata"), dict) else {}
    for key in ("count", "sampled", "samples", "points", "candles", "bars", "ticks", "window"):
        if meta.get(key) is not None:
            return meta.get(key)
    return out.get("sample_count") or out.get("window")


#: سلسلة التعلّم (360–368) لا تنشر رأيًا في السوق: «الجهة» في سجلّاتها **جهة صفقةٍ أُغلقت** ونتيجتها —
#: حقيقةٌ عن الصفقة لا حكم. فتبقى على ختمها السابق كما هو كي لا ينقطع 360 ⟵ 361 ⟵ … ⟵ 368.
FACTS_EXEMPT_ATOMS = frozenset({"360", "361", "362", "363", "364", "365", "366", "367", "368"})


def stamp_section(payload: dict[str, Any], *, section_id: str, atom_id: Any,
                  identity: _Identity | None = None) -> dict[str, Any]:
    """يطبع حمولة القسم على **عقد الحقائق**: الحقيقة ومصدرها، بلا حكم."""
    if not isinstance(payload, dict):
        return payload
    if str(atom_id) in FACTS_EXEMPT_ATOMS:
        return _legacy_stamp_judgment(payload, section_id=section_id, atom_id=atom_id, identity=identity)
    out = {k: v for k, v in payload.items() if k not in JUDGMENT_FIELDS and k not in JUDGMENT_ALIASES}
    account, broker = (identity.of(payload) if identity is not None
                       else (_text(payload.get("account_id")), _text(payload.get("broker"))))
    if account:
        out["account_id"] = account
    if broker:
        out["broker"] = broker
    kept = SIGNAL_WORDS_KEPT.get(str(atom_id), frozenset())
    for field in _WORDED_FIELDS:
        word = _text(out.get(field)).lower()
        if word in _JUDGMENT_WORDS and not (field == "signal" and word in kept):
            out.pop(field, None)
    meta = out.get("metadata")
    if isinstance(meta, dict):
        drop_direction = _text(meta.get("direction")).lower() in _JUDGMENT_WORDS
        out["metadata"] = {k: v for k, v in meta.items()
                           if k not in JUDGMENT_IN_FACTS and not (drop_direction and k == "direction")}
    stamp = _num(payload.get("timestamp")) or _num(payload.get("source_timestamp"))
    out["as_of"] = stamp if stamp is not None else clock.now()
    out["computed_on"] = _computed_on(out)
    out["section_id"] = section_id
    out["atom_id"] = str(atom_id)
    out["contract"] = FACTS_CONTRACT
    return out


def _legacy_stamp_judgment(payload: dict[str, Any], *, section_id: str, atom_id: Any,
                           identity: _Identity | None = None) -> dict[str, Any]:
    """العقد الموحّد القديم (حكم: جهة · قوّة · ثقة · عمق · جاهزيّة) — **لا يُنادى** منذ ٢٠٢٦-١٠-٠٧.
    يبقى نصًّا مرجعيًّا لما كان يُختم، ولقراءة السجلّات القديمة."""
    if not isinstance(payload, dict):
        return payload
    out = dict(payload)
    account, broker = (identity.of(out) if identity is not None
                       else (_text(out.get("account_id")), _text(out.get("broker"))))
    symbol = _text(out.get("symbol") or out.get("asset"))
    identity_ok = bool(account and broker and symbol)
    # §٨ — الاتجاه والقوّة حقلان مستقلّان، ولا يُدمجان في رقم واحد.
    #   ⛔ كان: `strength = _pct(score)` ثمّ `direction = sign × strength`
    #      فيخرج `|direction| == strength` **دائمًا**. ومثال المالك
    #      (`Direction +20` مع `Strength 90`) كان مستحيلًا رياضيًّا.
    #   ✅ الآن: مقدار الاتجاه من `score` — وهو مقياس اتجاهيّ بطبعه —
    #      أمّا القوّة فيرسلها المحلّل من مقياس مجاله وحده. غيابها
    #      يُعلَن `UNKNOWN` ولا يُملأ بـ|الاتجاه| (§١١).
    raw_score = _num(out.get("score"))
    directional_magnitude = _pct(raw_score)
    direction, direction_known, direction_sign = _direction(
        out, directional_magnitude, raw_score is not None)
    raw_strength = _num(out.get("strength"))
    strength_known = raw_strength is not None
    strength = _pct(raw_strength) if strength_known else 0.0
    # §٩ — الوزن يأتي من معايرة الذرّة، لا من رقم عالميّ. §١٠ — والحصّة
    # كذلك؛ وما لا يُحسب يبقى `UNKNOWN` ولا يُملأ صفرًا مضلِّلًا.
    raw_weight = _num(out.get("weight"))
    weight_known = raw_weight is not None
    weight = _pct(raw_weight) if weight_known else 0.0
    raw_ratio = _num(out.get("ratio"))
    ratio_known = raw_ratio is not None
    ratio = _pct(raw_ratio) if ratio_known else 0.0
    # NQ seal item 22 (A8): a missing confidence is declared unknown -- the
    # published 0.0 stays (compatibility) but is no longer a silent claim.
    confidence_known = _num(out.get("confidence")) is not None
    (state, current_depth, required_depth, depth_known,
     required_known, required_blocks_ready) = _state_of(out, identity_ok)
    # ═══ الأولوية ٠ — الحاجز الميكانيكيّ ═════════════════════════════════
    # مُعامِل غير معتمد يحكم العمق أو الثقة أو الحداثة ⇒ الناتج مؤقّت،
    # والمؤقّت لا يبلغ `READY` مهما بلغت أرقامه. ليس تعطيلًا للتحليل:
    # الحالة تُنشر كاملةً ويُعلَن سببها — لكنّ بوّابة القرار تبقى مغلقة
    # حتّى يعتمد المالك المصدر. «رقم بلا مصدر ليس حقيقة».
    blocking = unapproved_parameters()
    provisional = bool(blocking)
    if provisional and state == STATE_READY:
        state = STATE_NOT_READY
    # ═══ العقد الموحّد — شرط بنيويّ: `READY` تعني «مخرَجي صالح للاستهلاك»
    # ⛔ ممنوع: `direction = UNKNOWN` مع `state = READY`.
    #    كانت بطاقة كاملة العمق والهوية والحداثة تبلغ `READY` بينما
    #    اتجاهها **مجهول** — أي تُفتح بوّابة القرار على مخرَج لا رأي فيه.
    #    `State` بوّابة صلاحية لا مقياس تحليل: لا تُفتح لمجهول.
    #    ⛔ ولا يُملأ الاتجاه صفرًا ليَعبُر: `UNKNOWN ≠ 0.0000`.
    direction_blocks_ready = state == STATE_READY and not direction_known
    if direction_blocks_ready:
        state = STATE_NOT_READY
    unknown: list[str] = []
    if not weight_known:
        unknown.append("weight")
    if not ratio_known:
        unknown.append("ratio")
    if not direction_known:
        unknown.append("direction")
    if not strength_known:
        unknown.append("strength")
    if not confidence_known:
        # Missing confidence is declared, not read as a measured 0.0 (A8).
        unknown.append("confidence")
    if not depth_known:
        # عمق لم تُرسله الذرّة: يُعلَن مجهولًا ولا يُقرأ صفره كقياس.
        unknown.append("current_depth")
    if not required_known:
        # Missing required_depth is declared -- never a silent 100 bar (A8).
        unknown.append("required_depth")
    unified = {
        "account_id": account, "broker": broker, "symbol": symbol,
        "section_id": section_id, "atom_id": str(atom_id),
        "direction": direction,
        # الجهة محفوظة ولو كان المقدار مجهولًا — `UNKNOWN ≠ NEUTRAL`.
        "direction_sign": direction_sign,
        "strength": strength,
        "confidence": _confidence_pct(out.get("confidence")),
        "weight": weight, "ratio": ratio,
        # §٩ — الوزن لا يؤثّر إلّا بعد `READY`. أيّ حالة أخرى ⇒ أثر صفر،
        #      ولا يُحوَّل الوزن إلى حياد ولا يُخفى نقصه.
        "weight_effect": weight if state == STATE_READY else 0.0,
        # §٨ — `score` حقل توافق **مشتقّ** من الاتجاه، لا مقياس ثانٍ.
        "score_source": "direction",
        "current_depth": current_depth, "required_depth": required_depth,
        "state": state,
        # الأولوية ٠ — الحالة المؤقّتة معلَنة بسببها وبأسماء ما يعطّلها.
        "provisional": provisional,
        "provisional_reason": REASON_UNAPPROVED if provisional else "",
        "unapproved_parameters": blocking,
        # سبب حجب الجاهزية معلَن — لا يُستنتج من غياب.
        "not_ready_reason": (REASON_DIRECTION_UNKNOWN if direction_blocks_ready
                             else REASON_REQUIRED_DEPTH_UNKNOWN if required_blocks_ready
                             else REASON_UNAPPROVED if provisional else ""),
        "timestamp": out.get("timestamp"),
        "sequence": out.get("sequence"),
        "source_timestamp": out.get("source_timestamp", out.get("period_start")),
        "identity_complete": identity_ok,
        "unknown_fields": unknown,
    }
    if not identity_ok:
        unified["reason"] = REASON_IDENTITY
        warnings = out.get("warnings")
        out["warnings"] = ([*warnings, REASON_IDENTITY]
                           if isinstance(warnings, list) and REASON_IDENTITY not in warnings
                           else warnings if isinstance(warnings, list) else [REASON_IDENTITY])
    if account:
        out["account_id"] = account
    if broker:
        out["broker"] = broker
    out["section_id"] = section_id
    out["atom_id"] = str(atom_id)
    out.setdefault("state", state)
    out["unified"] = unified
    return out


def is_ready(payload: Any) -> bool:
    """جاهزية بمعنى §٤ — `READY` وحدها تدخل التجميع."""
    if not isinstance(payload, dict):
        return False
    unified = payload.get("unified")
    state = (unified.get("state") if isinstance(unified, dict)
             else payload.get("state"))
    return _text(state).upper() == STATE_READY


def wrap(context: AtomContext, *, section_id: str, atom_id: Any,
         atom: Any = None) -> AtomContext:
    """يُعيد سياقًا يطبع كل ما تنشره الذرّة على العقد الموحّد ويلتقط الهوية."""
    identity = _Identity()
    inner_publish = context.publish
    inner_subscribe = context.subscribe

    async def publish(name: str, payload: Any) -> None:
        await inner_publish(name, stamp_section(
            payload, section_id=section_id, atom_id=atom_id, identity=identity)
            if isinstance(payload, dict) else payload)

    def subscribe(name: str, handler: Callable[..., Any]) -> None:
        async def wrapped(payload: Any, *args: Any, **kwargs: Any) -> Any:
            # هوية الحدث الداخل تحكم ما يُنشَر أثناء معالجته — ثم تسقط.
            # لا تُورَّث هوية من حدث إلى حدث: حمولة بلا هوية ⇒ ("","").
            token = _INBOUND.set((
                _text(payload.get("account_id")), _text(payload.get("broker")))
                if isinstance(payload, dict) else ("", ""))
            try:
                return await handler(payload, *args, **kwargs)
            finally:
                _INBOUND.reset(token)
        # ⛔ إعادة الربط على الذرّة نفسها ضرورية لا تجميلية: كل فحص في هذا
        # المشروع يستدعي `atom._on_candle(...)` مباشرة بلا ناقل. لو بقي
        # الالتقاط في الناقل وحده، لصار العقد يعمل في التشغيل ويُقاس فارغًا
        # في الفحص — وهذا فرقٌ بين ما يُثبَت وما يعمل، وهو ممنوع.
        own = getattr(handler, "__self__", None)
        name_of = getattr(handler, "__func__", None)
        if atom is not None and own is atom and name_of is not None:
            setattr(atom, name_of.__name__, wrapped)
        inner_subscribe(name, wrapped)

    return _ContextProxy(context, publish, subscribe)


class _ContextProxy:
    """يمرّر كل خدمات السياق كما هي، ويستبدل publish/subscribe فقط.

    ⛔ لا يُبنى `AtomContext` جديد: بعض سياقات الاختبار كائنات duck-typed
    بلا `atom_id`، وبناء العقد الصارم فوقها يسقطها بخطأ ليس فيها.
    """

    __slots__ = ("_inner", "publish", "subscribe")

    def __init__(self, inner: Any, publish: Any, subscribe: Any) -> None:
        object.__setattr__(self, "_inner", inner)
        object.__setattr__(self, "publish", publish)
        object.__setattr__(self, "subscribe", subscribe)

    def __getattr__(self, name: str) -> Any:
        return getattr(object.__getattribute__(self, "_inner"), name)


def section_atom(section_id: str, atom_id: Any) -> Callable[[type], type]:
    """مزيّن قليل التدخل — سطر واحد فوق كل ذرّة، ولا يمسّ منطقها.

    نفس أسلوب `live_analyzer` المعتمد أصلًا في 151–165.
    """
    def decorate(cls: type) -> type:
        old_initialize = cls.initialize

        async def new_initialize(self: Any, context: Any) -> None:
            await old_initialize(self, wrap(
                context, section_id=section_id, atom_id=atom_id, atom=self))

        cls.initialize = new_initialize
        cls.SECTION_ID = section_id
        cls.UNIFIED_CONTRACT = True
        return cls
    return decorate
