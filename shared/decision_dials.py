"""عيارات القرار — امتداد سجلّ المُعامِلات المحكوم إلى ذرّات القرار.

أمر المالك المباشر (٢٠٢٦-٠٨-١٩): «هدول العتبات بالآخر رح يكون عيارهم بإيدي
من اللوحات — تأكّد إنها كل أرقام قابلة للتغيير، وعيارات بدقّة 100.00».

⇒ كلّ عيار قرارٍ صفٌّ في نفس جدول `parameters` المحكوم
   ([[shared/parameter_registry.py]]): قيمة عشرية دقيقة (REAL) + مصدر
   واعتماد ونسخة وسجلّ تدقيق، ويعيش بعد إعادة التشغيل. القيمة المعتمدة
   (`APPROVED`) تعلو قيمة المانيفست؛ وغير المعتمدة تُعلن الجهل ولا تغيّر
   السلوك — قيمة المانيفست الحالية تبقى السارية.

مسار التعديل الوحيد: اللوحة ← `/gov/command` (تأكيد بخطوتين، action=
`decision_setting`) ← جسر الأوامر ← الذرّة ٩٠١ تنشر `decision.settings.command`
← الذرّة صاحبة العيار تعتمد بالسجلّ (idempotent عبر `command_id`) وتطبّق
حيًّا وتنشر حالتها `decision.settings.state` للوحة.

⛔ هذا الملفّ لا يقترح قيمة ولا يغيّر سلوكًا: القيم المصرَّح بها أدناه هي
   السارية في مانيفستات الذرّات اليوم، تُسجَّل `UNSET/UNAPPROVED` إعلانًا
   للجهل حتى يعتمدها المالك بيده من اللوحة.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from shared.parameter_registry import (
    SCOPE_GLOBAL, SOURCE_OWNER, STATUS_APPROVED, ParameterRegistry)

EVENT_COMMAND = "decision.settings.command"
EVENT_STATE = "decision.settings.state"

#: عيارات القرار — القيمة هنا = الساري بالمانيفست اليوم (لا اقتراح).
#: `display` للّوحة: كيف يُعرض الرقم بدقّة عشريتين (نسبة مئوية أو رقم خام).
DIALS: dict[str, dict[str, Any]] = {
    "DECISION_NEUTRAL_BAND": {
        "value": 0.05, "atom": "458", "key": "neutral_band",
        "governs": "resolver.neutral_threshold", "display": "percent",
        "bounds": (0.0, 1.0),
        "where": "458_حل_التعارض neutral_band — |net|/available دونه = حياد"},
    "DECISION_CONFLICT_RATIO": {
        "value": 0.5, "atom": "458", "key": "conflict_ratio",
        "governs": "resolver.conflict_flag", "display": "percent",
        "bounds": (0.0, 1.0),
        "where": "458_حل_التعارض conflict_ratio — الخاسر/الرابح فوقه = تعارض"},
    "DECISION_MIN_PARTICIPATION": {
        "value": 0.20, "atom": "453", "key": "min_participation",
        "governs": "score.participation_floor", "display": "percent",
        "bounds": (0.0, 1.0),
        "where": "453_حساب_الدرجة min_participation — مشاركة المتكلّمين الدنيا"},
    "DECISION_DIRECTIONAL_WEIGHT": {
        "value": 1.0, "atom": "453", "key": "directional_weight",
        "governs": "score.weights", "display": "raw",
        "bounds": (0.0, 100.0),
        "where": "453_حساب_الدرجة directional_weight — وزن الاستراتيجية الاتجاهية"},
    "DECISION_CONTEXT_WEIGHT": {
        "value": 0.0556, "atom": "453", "key": "context_weight",
        "governs": "score.weights", "display": "raw",
        "bounds": (0.0, 100.0),
        "where": "453_حساب_الدرجة context_weight — وزن الدليل السياقي"},
    "DECISION_MIN_CONFIDENCE": {
        "value": 0.0, "atom": "452", "key": "min_confidence",
        "governs": "eligibility.confidence_floor", "display": "percent",
        "bounds": (0.0, 1.0),
        "where": "452_تقييم_الإشارات min_confidence — ثقة الدليل الدنيا"},
    "DECISION_LOW_QUALITY_FACTOR": {
        "value": 0.5, "atom": "452", "key": "low_quality_factor",
        "governs": "eligibility.quality_discount", "display": "percent",
        "bounds": (0.0, 1.0),
        "where": "452_تقييم_الإشارات low_quality_factor — خصم الجودة المنخفضة"},
    "DECISION_MIN_SCORE": {
        "value": 0.0, "atom": "454", "key": "min_score",
        "governs": "filter.score_gate", "display": "raw",
        "bounds": (0.0, 100.0),
        "where": "454_فلتر_القرار min_score — بوّابة الدرجة 0-100"},
    "DECISION_FILTER_TTL_S": {
        "value": 30.0, "atom": "454", "key": "filter_ttl_s",
        "governs": "filter.freshness_ttl", "display": "raw",
        "bounds": (0.1, 3600.0),
        "where": "454_فلتر_القرار filter_ttl_s — مهلة نضارة أحكام الفلاتر (ثوانٍ)"},
    "DECISION_MAX_PER_SYMBOL": {
        "value": 1.0, "atom": "463", "key": "max_per_symbol",
        "governs": "position.per_symbol_cap", "display": "integer",
        "bounds": (1.0, 100.0),
        "where": "463_حارس_المراكز max_per_symbol — أقصى مراكز للرمز الواحد"},
    "DECISION_LIVE_STALE_AFTER_S": {
        "value": 5.0, "atom": "166", "key": "live_stale_after_s",
        "governs": "fusion.freshness_horizon", "display": "raw",
        "bounds": (0.1, 600.0),
        "where": "166_دمج_التحليل live_stale_after_s — أفق طزاجة مساهمة المحلّل (ثوانٍ)"},
    "ANALYSIS_FAST_WEIGHT": {
        "value": 55.0, "atom": "166", "key": "fast_weight",
        "governs": "analysis.path_mix", "display": "raw",
        "bounds": (0.0, 100.0),
        "where": "166_دمج_التحليل fast_weight — وزن المسار السريع (التكّات) داخل قسم التحليل؛ البطيء = 100 − السريع (ق٢: إعادة توزيع بالتساوي في نطاق ثنائي)"},
    "ANALYSIS_SLOW_WEIGHT": {
        "value": 45.0, "atom": "166", "key": "slow_weight",
        "governs": "analysis.path_mix", "display": "raw",
        "bounds": (0.0, 100.0),
        "where": "166_دمج_التحليل slow_weight — وزن المسار البطيء (الشموع) داخل قسم التحليل؛ السريع = 100 − البطيء"},
    "ANALYSIS_FAST_REQUIRED_DEPTH": {
        "value": 60.0, "atom": "166", "key": "fast_required_depth",
        "governs": "analysis.fast.readiness", "display": "raw",
        "bounds": (0.0, 100.0),
        "where": "166_دمج_التحليل fast_required_depth — العمق المطلوب لجاهزية المسار السريع (ق٣: إعداد لوحة مستقل)"},
    "ANALYSIS_SLOW_REQUIRED_DEPTH": {
        "value": 60.0, "atom": "166", "key": "slow_required_depth",
        "governs": "analysis.slow.readiness", "display": "raw",
        "bounds": (0.0, 100.0),
        "where": "166_دمج_التحليل slow_required_depth — العمق المطلوب لجاهزية المسار البطيء (ق٣: إعداد لوحة مستقل)"},
    "NEWS_HIGH_WINDOW_BEFORE_MIN": {
        "value": 15.0, "atom": "411", "key": "high_window_before_min",
        "governs": "news.trading_window.high", "display": "raw",
        "bounds": (0.0, 240.0),
        "where": "411_استراتيجية_الأخبار high_window_before_min — دقائق حظر التداول قبل الخبر عالي الأثر (حكم المالك ق٧ بند 22: 15)"},
    "NEWS_HIGH_WINDOW_AFTER_MIN": {
        "value": 15.0, "atom": "411", "key": "high_window_after_min",
        "governs": "news.trading_window.high", "display": "raw",
        "bounds": (0.0, 240.0),
        "where": "411_استراتيجية_الأخبار high_window_after_min — دقائق حظر التداول بعد الخبر عالي الأثر (حكم المالك ق٧ بند 22: 15)"},
    "NEWS_MEDIUM_WINDOW_MIN": {
        "value": 0.0, "atom": "411", "key": "medium_window_min",
        "governs": "news.trading_window.medium", "display": "raw",
        "bounds": (0.0, 240.0),
        "where": "411_استراتيجية_الأخبار medium_window_min — دقائق نافذة الخبر المتوسط قبل/بعد؛ صفر = بلا حظر حتى يضبطها المالك (ق٧: لا اختراع مدد)"},
    "NEWS_LIGHT_WINDOW_MIN": {
        "value": 0.0, "atom": "411", "key": "light_window_min",
        "governs": "news.trading_window.light", "display": "raw",
        "bounds": (0.0, 240.0),
        "where": "411_استراتيجية_الأخبار light_window_min — دقائق نافذة الخبر الخفيف قبل/بعد؛ صفر = بلا حظر حتى يضبطها المالك (ق٧: لا اختراع مدد)"},
    "DECISION_BUY_MIN_DIRECTION": {
        # ٢٠٢٦-٠٩-٠٧ (مقيس على 240 عيّنة من السجل الحيّ): توزيع الاتجاه
        # الفعليّ P50=20 · P75=34 · P90=100. وعتبة 50 تمرّر أقلّ من رُبع
        # اللحظات ذات الإشارة الصحيحة، فكانت 466 ترفض 621 من 621 —
        # والاتجاه هو الفشل الوحيد في سجلّ 455/456 (بقيّة الفحوص تنجح).
        # العتبة تنزل إلى الوسيط المقيس، متماثلةً على الجهتين.
        "value": 20.0, "atom": "455", "key": "buy_min_direction",
        "governs": "eligibility.buy.direction_floor", "display": "raw",
        "bounds": (0.0, 100.0),
        "where": "455_قرار_الشراء buy_min_direction — حكم ق٦: القيمة الاتجاهية ≥ +50.0000 لأهلية الشراء"},
    "DECISION_SELL_MIN_DIRECTION": {
        "value": 20.0, "atom": "456", "key": "sell_min_direction",
        "governs": "eligibility.sell.direction_floor", "display": "raw",
        "bounds": (0.0, 100.0),
        "where": "456_قرار_البيع sell_min_direction — حكم ق٦: القيمة الاتجاهية ≤ -50.0000 لأهلية البيع؛ العيار موجب ويُطبَّق على الجانب السالب"},
    "DECISION_MIN_STRENGTH": {
        "value": 45.0, "atom": "457", "key": "min_strength",
        "governs": "eligibility.strength_floor", "display": "raw",
        "bounds": (0.0, 100.0),
        "where": "457_قرار_الانتظار min_strength — حكم ق٦: القوة ≥ 45.0000؛ يقرؤه الفاحصون الثلاثة 455/456/457 والمالك 457"},
    "DECISION_ELIGIBILITY_MIN_CONFIDENCE": {
        "value": 63.0, "atom": "457", "key": "min_confidence",
        "governs": "eligibility.decision_confidence_floor", "display": "raw",
        "bounds": (0.0, 100.0),
        "where": "457_قرار_الانتظار min_confidence — حكم ق٦: الثقة ≥ 63.0000 بمقياس 0-100 (مستقل عن DECISION_MIN_CONFIDENCE عيار 452 بمقياس 0-1 لثقة الدليل)"},
    "DECISION_MIN_CURRENT_DEPTH": {
        "value": 45.0, "atom": "457", "key": "min_current_depth",
        "governs": "eligibility.depth_floor", "display": "raw",
        "bounds": (0.0, 100.0),
        "where": "457_قرار_الانتظار min_current_depth — حكم ق٦: العمق الحالي ≥ 45.0000؛ يقرؤه الفاحصون الثلاثة 455/456/457 والمالك 457"},
    # ٢٠٢٦-١٠-٠٩ (ختم المالك «NQ» — إلغاء مفاتيح السرعة إلى الأرشيف): خرجت من هنا المفاتيح الأربعة
    # (ANALYSIS_SPEED · TRADING_HORIZON · QUALITY_BAR · MASTER_KEY) وتفعيل شخصيّة الأفق
    # (HORIZON_PROFILE_ACTIVE) — لا قارئ لأيّها في الكود بعد اليوم. صفوفها المعتمدة باقية في جدول
    # `parameters` بياناتٍ بلا قارئ (لا تُحذف)، ولا تُعرض في اللوحة ولا تُضبط منها.
    "RISK_DIAL": {
        "value": 100.0, "atom": "581", "key": "risk_dial",
        "governs": "position.new_exposure_growth", "display": "raw",
        "bounds": (0.0, 100.0),
        "where": "581_محرك_فرق_المركز risk_dial — عقد المحورين v1.1 §3 (مختوم NQ): "
                 "بوابة نمو التعرض الجديد وحدها — لا بوابة بقاء ولا عامل في E(S)/gross_cap/R_B؛ "
                 "100 = سلوك اليوم كاملًا، 0 = لا إضافة ولا تصفية؛ قيمة البدء 100 حتى يضبطها المالك من اللوحة"},
}


#: ٢٠٢٦-١٠-٠٧ (ختم المالك «NQ» — فكّ الأقسام عن القرار): مالكو هذه العيارات أُرشفوا (سلسلة الحكم
#: القديمة 452–463 ودمج التحليل 166). تبقى مفاتيحها في الجدول كي لا يسقط قارئٌ قديم بمفتاحٍ غائب،
#: لكنّها **متقاعدة**: لا تظهر في اللوحة، ولا يطبّقها أحد. أمّا 581 (عيار المخاطرة) و411 (نوافذ الأخبار)
#: فتبقى ظاهرةً.
#: ٢٠٢٦-١٠-٠٩ (ختم المالك «NQ» — إلغاء مفاتيح السرعة إلى الأرشيف): عيارات 150 (المفاتيح الأربعة وتفعيل
#: شخصيّة الأفق) لم تعد هنا أصلًا — انظر رأس `DIALS`.
RETIRED_DIAL_OWNERS = frozenset({"166", "452", "453", "454", "455", "456", "457", "458", "463"})
for _spec in DIALS.values():
    _spec["retired"] = str(_spec.get("atom")) in RETIRED_DIAL_OWNERS


def declare(registry: ParameterRegistry | None = None) -> ParameterRegistry:
    """يسجّل العيارات غير المسجَّلة بعد (INSERT OR IGNORE — لا يمسّ معتمدًا)."""
    registry = registry or ParameterRegistry()
    with registry._lock, registry._connect() as conn:  # noqa: SLF001 — نفس القاعدة عمدًا
        for name, spec in DIALS.items():
            conn.execute(
                """INSERT OR IGNORE INTO parameters(name,scope,value,source,
                   status,version,effective_from,approved_by,approved_at,
                   governs,declared_at)
                   VALUES(?,?,?,?,?,0,0.0,'','',?,?)""",
                (name, SCOPE_GLOBAL, float(spec["value"]), "UNSET",
                 "UNAPPROVED", str(spec["governs"]), str(spec["where"])))
        conn.commit()
    return registry


#: مسار السجلّ الافتراضيّ محفوظ بمفتاح متغيّر البيئة — فحص «هل هذا السجلّ
#: هو الافتراضيّ؟» يجري بلا بناء ParameterRegistry في كلّ نداء.
_default_path_cache: dict[str | None, Path] = {}


def _default_registry_path() -> Path:
    key = os.environ.get("QUANT_ANALYSIS_SETTINGS_DB")
    path = _default_path_cache.get(key)
    if path is None:
        path = _default_path_cache[key] = ParameterRegistry().path
    return path


def effective_value(name: str, manifest_value: float,
                    registry: ParameterRegistry | None = None) -> float:
    """القيمة السارية للعيار: المعتمدة من المالك إن وُجدت، وإلّا قيمة المانيفست.

    تعذُّر قراءة السجلّ لا يُسقط الذرّة: قيمة المانيفست هي السارية أصلًا
    قبل أي اعتماد، فالسقوط إليها صادق لا مُخفٍ.

    (٢٠٢٦-٠٨-٢٥) القراءة عبر `approved_value` الموقّتة ببصمة القاعدة —
    فذرّة تُحمَّل ساخنة ترى اعتمادات كُتبت من عمليّة أخرى بلا إقلاع بارد،
    وبلا استعلام قاعدة على المسار الساخن إلا عند تغيّرها فعلًا.

    (مساء ٢٠٢٦-٠٢٥، قياس py-spy) تمريرُ registry صريحٍ كان يتجاوز ذاكرة
    `approved_value` كليًّا — اتصال sqlite لكل عيار لكل قرار على المسار
    الساخن (ذرّات 454-458 عبر `_refresh_dials` في كل `_on_scored`). سجلٌّ
    على القاعدة الافتراضيّة نفسها يسلك المسار الموقّت؛ ويبقى المسار
    المباشر لقاعدةٍ مغايرة (فحوص بمسار مخصّص) فقط."""
    if registry is not None and registry.path != _default_registry_path():
        try:
            row = registry.get(name)
        except Exception:  # noqa: BLE001 — قاعدة مقفولة/غائبة لحظيًّا
            return float(manifest_value)
        if row is not None and str(row.get("status")) == STATUS_APPROVED:
            return float(row["value"])
        return float(manifest_value)
    # ٢٠٢٦-١٠-٠٩ (ختم المالك «NQ» — إلغاء مفاتيح السرعة إلى الأرشيف): خرج تجاوز «شخصيّة الأفق»
    # (`shared/horizon_profile.dial_override`) — أُرشف مع مفتاح الأفق الذي كان يولّدها، وكان مطفأً
    # (`HORIZON_PROFILE_ACTIVE = 0` معتمدًا منذ ٢٠٢٦-٠٩-١٦) وأسماؤه كلّها لعيارات ذرّاتٍ مؤرشفة.
    from shared.parameter_registry import approved_value
    return approved_value(name, float(manifest_value))


def clamp_to_bounds(name: str, value: float) -> float:
    """قصّ القيمة إلى حدود العيار المعلنة — حماية من قيمة خارجة عن معناها."""
    low, high = DIALS[name]["bounds"]
    return low if value < low else high if value > high else float(value)


def apply_command(payload: dict[str, Any], *, atom_id: str,
                  registry: ParameterRegistry | None = None,
                  confirm: bool | None = None) -> dict[str, Any] | None:
    """يعالج `decision.settings.command` لعيارٍ تملكه هذه الذرّة.

    يعيد {name, value, version, status, approved} عند الاعتماد (أو عند تكرار
    نفس command_id — idempotent عبر سجلّ التدقيق)، وNone إن لم يكن الأمر
    لعيارٍ من عياراتها أو كان ناقص الهوية (فيُكشف الرفض للمُنادي ليحصيه،
    لا يُبتلع بصمت).

    ⚖️ بند ٥ (٢٠٢٦-٠٩-٠٣): «حفظ» ≠ «اعتماد». حقل ``confirm`` في الـpayload هو
    الخطّ الفاصل: ``true`` وحده يعتمد (``source=OWNER``)، وأي شيء آخر —بما فيه
    الغياب والتراثيـة النصّية ``"true"``— حفظُ مسودة ``UNAPPROVED`` لا يقرأه
    محرّك (`effective_value` يشترط STATUS_APPROVED). كان الاعتماد سابقًا يحدث
    ضمن مسار الحفظ نفسه، فاختلط «سجّلتُ رقمًا» بـ«قرّرتُ».
    """
    if not isinstance(payload, dict):
        return None
    name = str(payload.get("name") or "")
    spec = DIALS.get(name)
    if spec is None or str(spec["atom"]) != str(atom_id):
        return None
    try:
        value = float(payload.get("value"))
    except (TypeError, ValueError):
        return None
    command_id = str(payload.get("command_id") or "")
    operator = str(payload.get("operator") or "")
    if confirm is None:          # حقل الـpayload هو الأصل؛ الصريحة تتقدّم
        confirm = payload.get("confirm")
    approved_at = payload.get("approved_at", payload.get("command_requested_at"))
    try:
        approved_at = float(approved_at)
    except (TypeError, ValueError):
        return None
    if not command_id or not operator:
        return None
    value = clamp_to_bounds(name, value)
    registry = registry or ParameterRegistry()
    declare(registry)
    # ٢٠٢٦-١٠-٠٩ (ختم المالك «NQ» — إلغاء مفاتيح السرعة إلى الأرشيف): فرع النطاق (حساب␟رمز) خرج —
    # كان للعيارات المعلنة `scoped` وحدها، وهي المفاتيح الأربعة المؤرشفة؛ فكلّ عيارٍ باقٍ عامّ، وحقلا
    # الحساب والرمز في الحمولة يُتجاهلان كما كانا يُتجاهلان لكلّ عيارٍ غير `scoped`.
    scope = SCOPE_GLOBAL
    if confirm is not True:
        # حفظ مسودة فقط. لا اعتماد ولا source=OWNER (بند ٥).
        row = registry.write_value(name, value=value, scope=scope,
                                   changed_by=operator, command_id=command_id,
                                   at=approved_at)
        return {"name": name, "value": float(row["value"]),
                "version": int(row["version"]), "scope": scope,
                "status": row.get("status", "UNAPPROVED"), "approved": False}
    row = registry.approve(name, value=value, source=SOURCE_OWNER,
                           approved_by=operator, command_id=command_id,
                           approved_at=approved_at, scope=scope)
    return {"name": name, "value": float(row["value"]),
            "version": int(row["version"]), "scope": scope,
            "status": row.get("status", "APPROVED"), "approved": True}
