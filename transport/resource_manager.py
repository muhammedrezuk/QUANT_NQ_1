# -*- coding: utf-8 -*-
"""مدير الموارد — §٩ من ورقة المصنع.

**وظيفته أربع ولا خامسة لها:** `Discover · Plan · Assign · Monitor`.

⛔ **ولا يملك أيّ حقّ** في: قرار شراء · تعديل مخاطرة · تعديل وقف · فتح
مركز · إغلاق مركز. (§٩ حرفيًّا.)

---

## لماذا وُجد — والعطب الذي يعالجه مقيسًا

`default_worker_count()` كان الجواب المؤقّت، وهو يقول عن نفسه في تعليقه:
«**بذرة مؤقّتة** لا سياسة نهائية». وعطبه اثنان، كلاهما مكتوب هناك:

1. يقسم `os.cpu_count()` على اثنين، وذاك يُرجع **الخيوط المنطقية لا
   الأنوية**: جهاز المالك ٦ أنوية / ١٢ خيطًا، فيُرجع ٦ — أي عاملًا لكلّ
   نواة فيزيائية، وهو **١٠٠٪ من الأنوية لا ٥٠٪** كما تستهدف §١٩.
2. ويشتقّ العدد من الجهاز لا من **الحمل المقاس وقدرة الوحدة**، وذلك ما
   تفرضه §٢٥ و§٢٦ نصًّا.

**وهذه الوحدة تشتقّ العدد من القياس** — والقياس يُمرَّر إليها، لا تخترعه.

---

## القياس الذي تستند إليه (٢٠٢٦-٠٩-١٧ · نافذة ١٣٠ ث)

```
معالج عمليّة النواة        = 136.6 ث / 130 ث = 105% من نواة واحدة
                             = 8.7% من الجهاز (١٢ خيطًا)

§٢٤-٢  عالميّ مقابل خاصّ:
    أحداث بلا رمز  11.0%   ⟹  15.0 ث   ⟵ العمود الفقريّ **خفيف**
    أحداث برمز     89.0%   ⟹ 121.6 ث

§٢٤-١  حصّة كلّ رمز من المعالج:
    BTCUSD 26.7%  ·  XAUUSD 22.8%  ·  USTEC 19.4%   ⟵ ثلاثة = 68.9%
    GBPUSD  6.7%  ·  EURUSD  5.0%  ·  US30   4.5%  ·  US500 3.5%
```

**وهذا يحسم ما علّقته الورقة:** §٢٤-٢ كانت تسأل «هل العمود الفقريّ خفيف
فعلًا؟ إن ثقُل انهار المكسب». **الجواب: خفيف — ١١٪.** فالتقسيم بالرمز
يعطي مكسبًا حقيقيًّا، ولا يُبتلع في حصّة مشتركة.

⚠️ **وحدّ صدقٍ على الطريقة:** حصّة الرمز مشتقّة من **حصّته من الأحداث**
لا من تشريح مكدّس. فهي تقدير عادلٌ حين تتقارب كلفة الحدث الواحد، ويصير
متحيّزًا حين يحمل رمزٌ أحداثًا أغلى. تُستعمل لتحديد **عدد العمّال**، لا
لوعد أداء — وهو نصّ حكم المالك في نِسَب التشريح.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Mapping

#: سياسة استهلاك المعالج — §١٩ و§٣١. **معلَنة لا عرضيّة**، وهي ما كان
#: ناقصًا: حالة العامل كانت تُشتقّ من عمق صندوقه وحده، فلا سقف معالجٍ
#: مُعلَن أصلًا.
POLICY_NORMAL = 0.40      # طبيعيّ
POLICY_TARGET = 0.50      # الهدف — وفوقه يبدأ أكل الاحتياط (§١٩)
POLICY_PRESSURE = 0.70    # ضغط
POLICY_EMERGENCY = 0.80   # طوارئ — وما فوقه فشل (§٣١)

#: هامش الذروة فوق الحمل المقاس (§٢٥). الذروة مقيسة على هذه الشجرة:
#: `feed.mt5.tick` تذبذب بين 36.3 و270.2 حدثًا/ث في ثلاث نوافذ متتالية،
#: أي **٧٫٤×** بين أهدأ نافذة وأشدّها. ويُؤخذ ضعفان لا سبعة: الذروة
#: القصوى لحظيّة والطابور يمتصّها (§١٧)، والسبعة تبني لذروةٍ دائمة.
PEAK_MARGIN = 2.0

#: الاحتياط المطلوب (§١٩): «احتياط ≥ ٥٠٪ في الحالة المستقرّة».
RESERVE_RATIO = 0.50

#: أقلّ عدد عمّال — عاملٌ واحد لا يوازن شيئًا، واثنان أقلّ ما يُقسَّم عليه.
MIN_WORKERS = 2


@dataclass(frozen=True, slots=True)
class Resources:
    """ما اكتُشف من الجهاز — `Discover`. لا رقم مثبَّت في الكود (§٨)."""

    logical_threads: int
    #: الأنوية الفيزيائية **لا تُعرَف** من المكتبة القياسية. تُترك `None`
    #: ولا تُخمَّن: `os.cpu_count()` يُرجع الخيوط، والفارق يعتمد على SMT.
    physical_cores: int | None = None

    @classmethod
    def discover(cls) -> "Resources":
        return cls(logical_threads=max(1, int(os.cpu_count() or 1)))

    @property
    def usable_threads(self) -> int:
        """ما يجوز استهلاكه فعلًا — §١٩: الهدف ≤ ٥٠٪ والاحتياط ≥ ٥٠٪."""
        return max(1, int(self.logical_threads * POLICY_TARGET))


@dataclass(frozen=True, slots=True)
class LoadMeasurement:
    """الحمل **المقيس** — لا يُخترع هنا ولا يُقدَّر (§٢٦).

    `core_cpu_ratio` : معالج عمليّة النواة كنسبة من نواة واحدة (1.05 = 105%)
    `per_symbol`     : حصّة كلّ رمز من ذلك الحمل (مجموعها ≤ 1.0)
    `global_ratio`   : حصّة ما لا يخصّ رمزًا — العمود الفقريّ
    """

    core_cpu_ratio: float
    per_symbol: Mapping[str, float] = field(default_factory=dict)
    global_ratio: float = 0.0

    def __post_init__(self) -> None:
        if self.core_cpu_ratio < 0:
            raise ValueError("حمل سالب")
        if not 0.0 <= self.global_ratio <= 1.0:
            raise ValueError("حصّة العمود الفقريّ خارج [0,1]")

    @property
    def heaviest_symbol_ratio(self) -> float:
        """أثقل رمزٍ كنسبة من نواة — وهو **سقف التوازي الحقيقيّ**.

        §٢٢: «عدد موارد أكبر ≠ توازي أكبر تلقائيًّا». الوحدة لا تنقسم
        (§٥)، فلا يمكن لعاملٍ أن يحمل أقلّ من أثقل رمزٍ عنده.
        """
        if not self.per_symbol:
            return self.core_cpu_ratio
        return self.core_cpu_ratio * max(self.per_symbol.values())


@dataclass(frozen=True, slots=True)
class Plan:
    """ما قرّره المدير — `Plan`. ويحمل **سببه**، لا الرقم وحده."""

    workers: int
    required_capacity: float
    available_capacity: float
    heaviest_unit: float
    reason: str
    warnings: tuple[str, ...] = ()

    @property
    def fits(self) -> bool:
        return self.required_capacity < self.available_capacity


def plan_workers(resources: Resources, load: LoadMeasurement) -> Plan:
    """§٢٥ المعادلة النهائية — مطبَّقة حرفًا.

        السعة المطلوبة = الحمل المقاس + هامش الذروة + هامش الاحتياط
        عدد العمّال    = أقلّ عددٍ يجعل السعة الفعليّة > المطلوبة بفارق

    ⛔ **ولا يُرجع رقمًا لا يستطيع تفسيره** (§١٥: «كلّ رقم قابل للتفسير»).
    """
    warnings: list[str] = []

    # ⚠️ **وحدة القياس واحدة في الطرفين**: كلاهما «نواة من الحمل».
    #    خلطُ «سعةٍ خام» بـ«حملٍ عند الهدف» أعطى 4.2 مقابل 2.5 فبدا أنّه
    #    لا يتّسع وهو يتّسع — أمسكه الاختبار قبل أن يصير قرارًا.
    peak_load = load.core_cpu_ratio * PEAK_MARGIN      # الحمل عند الذروة
    required = peak_load                                # ما يجب أن يُحمَل

    # ولا عامل يحمل أكثر من الهدف — فالعدد الأدنى من قسمة الحمل على الهدف.
    by_load = peak_load / POLICY_TARGET

    # وسقفٌ لا يُتجاوز: الوحدة لا تنقسم، فأثقل رمزٍ يحدّ الفائدة (§٢٢).
    heaviest = load.heaviest_symbol_ratio * PEAK_MARGIN
    if heaviest > POLICY_TARGET:
        warnings.append(
            "أثقل رمزٍ يستهلك %.0f%% من نواة عند الذروة — فوق هدف %.0f%%. "
            "زيادة العمّال **لا تعالجه**: الوحدة لا تنقسم (§٥). "
            "العلاج مفتاح ملكيّة أدقّ (§٢٣: Account×Symbol×AnalysisGroup)."
            % (heaviest * 100, POLICY_TARGET * 100))

    # ولا يُطلب من الجهاز ما ليس فيه.
    ceiling = resources.usable_threads
    workers = max(MIN_WORKERS, min(ceiling, int(by_load) + 1))

    if by_load > ceiling:
        warnings.append(
            "الحمل يطلب %.1f عاملًا والجهاز يسمح بـ%d عند هدف %.0f%% — "
            "الجهاز نفسه هو الحدّ، لا التوزيع."
            % (by_load, ceiling, POLICY_TARGET * 100))

    if load.global_ratio > POLICY_TARGET:
        warnings.append(
            "العمود الفقريّ %.0f%% من الحمل — التقسيم بالرمز لا يخفّفه (§١١)."
            % (load.global_ratio * 100))

    # ما يقدر عليه العدد المختار **عند الهدف** — لا سعته الخام.
    available = workers * POLICY_TARGET
    return Plan(
        workers=workers,
        required_capacity=round(required, 4),
        available_capacity=round(available, 4),
        heaviest_unit=round(heaviest, 4),
        reason=("حمل %.2f نواة × ذروة %.1f ÷ هدف %.0f%% = %.2f ⟶ %d عاملًا "
                "(سقف الجهاز %d)"
                % (load.core_cpu_ratio, PEAK_MARGIN, POLICY_TARGET * 100,
                   by_load, workers, ceiling)),
        warnings=tuple(warnings),
    )


def load_state(cpu_ratio: float) -> str:
    """حالة الحمل بالسياسة المعلَنة — §١٩ و§٣١.

    ⚠️ **وهذه سياسة سعة لا شهادة صحّة.** §١٨ ترتّب معايير الصحّة:
    الطابور أوّلًا، ثمّ زمن التِكّة←القرار، ثمّ الفقد، ثمّ الترتيب
    والملكيّة، والمعالج **خامسًا**. نظامٌ على ٤٠٪ وطابوره ينمو **فاشل**.
    """
    if cpu_ratio < POLICY_NORMAL:
        return "NORMAL"
    if cpu_ratio < POLICY_TARGET:
        return "TARGET"
    if cpu_ratio < POLICY_PRESSURE:
        return "PRESSURE"
    if cpu_ratio < POLICY_EMERGENCY:
        return "EMERGENCY"
    return "FAILED"


def policy() -> dict[str, Any]:
    """السياسة معلَنة للتشخيص — §٣٠: «أيّ أفضلية تُضاف يجب أن تظهر بالاسم»."""
    return {
        "normal": POLICY_NORMAL,
        "target": POLICY_TARGET,
        "pressure": POLICY_PRESSURE,
        "emergency": POLICY_EMERGENCY,
        "peak_margin": PEAK_MARGIN,
        "reserve_ratio": RESERVE_RATIO,
        "min_workers": MIN_WORKERS,
    }

# ══ حدود الزمن — بند بوّابة §٣٦ «تحديد حدود الزمن» ════════════════════════
#
# كانت أربعة أرقام في أربعة ملفّات لا يعرف بعضها بعضًا، وكشف ذلك عطبًا
# حقيقيًّا: `drain_timeout_s = 15` (صامت) كان **يسبق دائمًا**
# `SymbolCoordinator.expiry_s = 30` (مسمّى)، فلا يُبلَغ المسار المسمّى
# أبدًا — ولذلك كان `expired = 0` حيًّا، لا لأنّ شيئًا لم ينتهِ.
#
# فتُجمع هنا **بسلّمٍ متّسق**، وكلّ درجةٍ أوسع ممّا قبلها:
#
#     تصريف العامل  <  كنس المنسّق  <  انتهاء سجلّ الطائر
#           15 ث           30 ث              60 ث
#
# المعنى: العامل يستسلم أوّلًا ويُسمّي السبب · ثمّ يكنس المنسّق ما بقي
# محجوزًا · ثمّ يُنهي سجلّ الطائر ما لم يُحسم أصلًا. ثلاث شبكات، لا
# ثلاثة متنافسين.

#: مهلة تصريف الناقل المحلّيّ داخل العامل — `transport/atom_host.py`.
TIME_WORKER_DRAIN_S = 15.0
#: كنس المنسّق لتِكّةٍ لن تكتمل — `transport/symbol_coordinator.py`.
TIME_COORDINATOR_SWEEP_S = 30.0
#: انتهاء صلاحيّة مدخلةٍ في سجلّ الطائر — `transport/analysis_farm.py`.
TIME_INFLIGHT_CEILING_S = 60.0
#: ميزانية العمل الواحد. **صفر = بلا مهلة** وهو الساري: العقد يلزم
#: اشتقاقها من ٥٬٠٠٠ عيّنة عمرٍ مقيسة (حكم المالك)، ولم تكتمل بعد.
#: وغيابُها لا يترك ثغرة — الثلاثة أعلاه تحرس ضدّ النموّ الأبديّ.
TIME_WORK_BUDGET_S = 0.0


def _assert_time_ladder() -> None:
    """السلّم يُفحص عند الاستيراد — لا يُترك ينقلب بصمت.

    ⛔ انقلابُه هو العطب الذي وقع فعلًا: الصامت أسرع من المسمّى فابتلعه.
    """
    ladder = (("تصريف العامل", TIME_WORKER_DRAIN_S),
              ("كنس المنسّق", TIME_COORDINATOR_SWEEP_S),
              ("سجلّ الطائر", TIME_INFLIGHT_CEILING_S))
    for (lo_name, lo), (hi_name, hi) in zip(ladder, ladder[1:]):
        if not lo < hi:
            raise AssertionError(
                "سلّم الزمن مقلوب: %s (%.1f) ليس أضيق من %s (%.1f) — "
                "الأضيق يسبق فيبتلع الأوسع" % (lo_name, lo, hi_name, hi))
    if TIME_WORK_BUDGET_S < 0:
        raise AssertionError("ميزانية عملٍ سالبة")
    if TIME_WORK_BUDGET_S > 0 and TIME_WORK_BUDGET_S >= TIME_COORDINATOR_SWEEP_S:
        raise AssertionError(
            "ميزانية العمل %.1f ث تبلغ كنس المنسّق %.1f ث — عندها يسبق "
            "الصامتُ المسمّى ثانيةً" % (TIME_WORK_BUDGET_S, TIME_COORDINATOR_SWEEP_S))


_assert_time_ladder()


def time_bounds() -> dict[str, Any]:
    """حدود الزمن معلَنة — §٣٠: ما لا يظهر بالاسم يصير عمًى."""
    return {
        "worker_drain_s": TIME_WORKER_DRAIN_S,
        "coordinator_sweep_s": TIME_COORDINATOR_SWEEP_S,
        "inflight_ceiling_s": TIME_INFLIGHT_CEILING_S,
        "work_budget_s": TIME_WORK_BUDGET_S,
        "budget_active": TIME_WORK_BUDGET_S > 0,
    }

# ══ عدد الأقسام المنطقيّة — بند بوّابة §٣٦ الأخير ══════════════════════════
#
# §٢٦ تمنع اعتماد `64` رقمًا نهائيًّا قبل القياس، و§٢٢ تقول إنّ سقف
# التوازي هو **عدد الأشياء المستقلّة** لا عدد الأنوية، و§٢٣ تؤجّل توسيع
# المفتاح «حتى يثبت القياس الحاجة». **القياس وقع ٢٠٢٦-٠٩-١٧ ويقول: نعم.**

#: الحدّ الأدنى لتغطية النموّ — §٥: «عدد الأقسام > عدد العمّال المتوقّع».
PARTITION_HEADROOM = 2


def plan_partitions(load: "LoadMeasurement", *, symbols: int,
                    logical_partitions: int) -> dict[str, Any]:
    """يشتقّ مفتاح الملكيّة المطلوب وعدد الأقسام — من الحمل لا من الظنّ.

    §٢٢: الوحدة لا تنقسم (§٥)، فعاملٌ يحمل أثقل رمزٍ لا ينزل تحته مهما
    كثر العمّال. فإن تجاوز أثقلُ رمزٍ الهدفَ عند الذروة، **لا علاج
    بالعدد** — العلاج مفتاحٌ أدقّ: `Account × Symbol × AnalysisGroup`.
    """
    heaviest = load.heaviest_symbol_ratio * PEAK_MARGIN
    groups = 1
    while heaviest / groups > POLICY_TARGET and groups < 16:
        groups += 1
    needed = symbols * groups
    return {
        "heaviest_unit_at_peak": round(heaviest, 4),
        "target": POLICY_TARGET,
        "groups_required": groups,
        "unit_after_split": round(heaviest / groups, 4),
        "partitions_needed": needed,
        "logical_partitions": logical_partitions,
        "partitions_sufficient": logical_partitions >= needed * PARTITION_HEADROOM,
        "key": ("Account × Symbol" if groups == 1
                else "Account × Symbol × AnalysisGroup"),
        "reason": (
            "أثقل رمزٍ %.1f%% عند الذروة %s هدف %.0f%% ⟶ %d مجموعة "
            "⟶ %d قسمًا مطلوبًا من %d متاحًا"
            % (heaviest * 100, "فوق" if groups > 1 else "دون",
               POLICY_TARGET * 100, groups, needed, logical_partitions)),
    }
