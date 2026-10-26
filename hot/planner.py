# -*- coding: utf-8 -*-
"""§5 / D+E — مُجمِّع الاعتماد والخطّة الساخنة المُجمَّعة.

## ما يفعله

يقرأ المانيفستات مرّةً **عند الإقلاع** ويُخرج خطّةً ثابتة: مجموعةَ عقدٍ،
ورسمَ اعتمادٍ، وترتيبًا طوبولوجيًّا، وتصنيفَ كلّ اعتماد. وبعدها لا يُحلَّل
رسمٌ في دورة تِكّة، ولا يُبحَث عن مشترِك.

## سياسة الاعتماد — ثلاثُ حالاتٍ لا رابع (§٢٠)

    LOCAL          يبقى داخل `Account×Symbol`
    CROSS_SYMBOL   يمرّ عبر خدمة الحالة العابرة (قراءةً فقط)
    CENTRAL        يبقى في النواة أو خدمةٍ مركزيّة

⛔ و**لا اعتمادَ يُفترَض محلّيًّا**. اشتراكٌ لا ناشرَ له في المستودع كلّه
يُصنَّف `DANGLING`: يُسمَّى ويُعدّ، ولا تُبنى عليه حافّةُ اعتماد، ويرفضه
`strict_dangling=True`. هذا هو الفرق بين خطّةٍ مُثبَتة وخطّةٍ تُخمّن.

    حدثٌ له ناشرٌ داخل النطاق   ⟶ حافّةُ اعتماد
    حدثٌ مُعلَنٌ خارجيًّا          ⟶ مدخلٌ بلا حافّة
    حدثٌ بلا ناشرٍ إطلاقًا       ⟶ DANGLING — مسمًّى لا مفترَض

ولا حالةَ رابعة: كان هنا مسارٌ اسمه `unknown` فصار ميّتًا بعد هذا
التصنيف، وأُزيل — حارسٌ لا يُبلَغ أبدًا أسوأ من غيابه.

## ودورةُ اعتمادٍ حقيقيّة ترفض الإقلاع (§١٩)

    A → B → C → A

لا تُكسَر صامتةً ولا يُختار لها مدخلٌ عشوائيّ. تُسمَّى ويُرفَض البناء.

## المحافظة أوّلًا (§١١)

الخطّة الأولى **لا تُقلّم**: ترتيبٌ طوبولوجيٌّ كاملٌ صحيح. و`dirty`
يُضاف بعد أن يثبت التكافؤ — كي لا يختلط خطأُ تنفيذٍ بتحسينِ جدولة.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

#: النطاق الساخن (§٧).
HOT_RANGE = (100, 599)

#: عقدٌ **خارج المالك** بالعقد الحاليّ — فصلُ ملكيّةٍ لا إزالةَ وظيفة (§٧).
CENTRAL_ATOMS = frozenset({"111", "150", "300", "450", "601"})
CROSS_SYMBOL_ATOMS = frozenset({"160", "161", "307"})

LOCAL = "LOCAL"
CROSS_SYMBOL = "CROSS_SYMBOL"
CENTRAL = "CENTRAL"

#: حوافٌّ **راجعةٌ عبر الدورات** — ختم المالك `NQ — ACCEPT FEEDBACK 367→452`.
#:
#:      قرارُ الدورة الحاليّة ⟶ تسجيلُ النتيجة ⟶ التعلّم ⟶ استخراجُ الدليل
#:      ⟶ يُخزَّن حالةً ملتزمة ⟶ يؤثّر في القرار **التالي**
#:
#: وليست: «التعلّمُ الحاليّ ⟶ القرارُ الحاليّ». وهذا هو الفرق الحاسم.
#:
#: والإعلان **لا يحذف الاعتماد**: يُستثنى من الترتيب داخل التِكّة وحدها،
#: ويبقى اعتمادَ حالةٍ عبر الدورات. كلّ حافّةٍ مذكورةٌ باسمها وحدثها، فلا
#: حافّةَ تُزال صامتةً (§١٩: «لا يكسر الحلقة صامتًا»).
#
# ## الحدود الستّ (ختم المالك ٢٠٢٦-٠٩-١٨)
#
# القاعدة الواحدة: **الحافّة التي تحمل النتيجة المتحقّقة وتعيدها إلى مسار
# التحجيم أو القرار التالي هي `FEEDBACK`.** وطُبِّقت على الرسم المقيس:
#
#   367 Learning Evidence     ⟶ 452  دليلُ نموذجٍ يعود إلى القرار التالي
#   563 Durable Exec Confirm  ⟶ 517  **نتيجةُ صفقةٍ متحقّقة** ⟶ Trade Outcome
#   551 Order Builder         ⟶ 518  أمرٌ مبنيٌّ يُحدّث دفتر الأصل
#   518 Asset Risk Ledger     ⟶ 524  حالةُ الدفتر ⟶ استخلاصُ الربح التراكميّ
#   516 Per-Account Authority ⟶ 506  إعادةُ ضبطِ مفتاح الإيقاف ⟶ حدود الجلسة
#
# والحافّة **واحدةٌ في الرسم** ولو ظهرت في أكثر من مسارٍ سياقيّ: الحلقات
# الثلاث ٣ و٤ و٥ تمرّ كلّها بـ`551 ⟶ 518`، فلا تُكتب ثلاثًا.
#
# ⚠️ وحقلان في جدول المالك كانا منقولين، فصُحِّحا **بقاعدته لا بحرفه**:
#
#   جدولُه `552 ⟶ 563` بـ`market.outcome.realized` — والمقيس أنّ
#   `552 ⟶ 563` يحمل `trading.final_decision` (مسارٌ **ذاهب**: مدقّقُ الأمر
#   ⟶ تأكيدُ تنفيذه)، وأنّ حاملَ النتيجة المتحقّقة هو `563 ⟶ 517`. وإعلانُ
#   الذاهب راجعًا يفصل التدقيق عن تأكيده داخل الدورة — عكسُ المقصود.
#
#   وجدولُه `551 ⟶ 518` بـ`risk.asset_ledger.state` — والزوج صحيح، لكنّ
#   `risk.asset_ledger.state` هو ما **يُخرجه** 518 لا ما يدخله. والداخل
#   `execution.order.built`.
#
# ## Temporal SCC — الحكم بالحدث لا بالحافّة (ختم المالك ٢٠٢٦-٠٩-١٨)
#
# كتلةُ المخاطر والتنفيذ ليست رسمًا ناقصًا يُطارَد حتّى يختفي، بل **نظامُ
# حالةٍ متكرّر**: أمرٌ ⟶ تنفيذ ⟶ نتيجة/دفتر/إيقاف ⟶ حالةٌ ملتزمة ⟶ الأمر
# التالي. ومحاولةُ جعلها طوبولوجيّةً داخل تِكّةٍ واحدة خطأٌ معماريّ.
#
# فالإعلان يقع على **الحدث**، والمُجمِّع يشتقّ الحوافّ من الرسم. وكتابةُ
# `551⟶518` و`551⟶519` و`551⟶523`… باليد هي سببُ انفجار القائمة.
#
# والقاعدة ليست «كلّ حافّةٍ تحمل هذا الحدث راجعة». هي:
#
#     حدثُ الحافّة في FEEDBACK_EVENTS
#     **و** الحافّة تعود إلى سلفٍ (أي إضافتها تُغلق حلقة)
#     ⟶ FEEDBACK
#
# وحافّةٌ تحمل الحدث نفسه إلى أمامٍ لم تُنتَج فيه النتيجة بعدُ **تبقى
# حافّةً عاديّة**. وهذا ما يمنع الإعلانَ من أن يقطع اعتمادًا مشروعًا.
#
# ## الختم النهائيّ `NQ — ACCEPT TEMPORAL SCC BOUNDARIES` (٢٠٢٦-٠٩-١٨)
#
# نهض المُجمِّع بالعقد الأوّل (السبعة الأولى أدناه) فأذاب ١١ ذرّةً من مكوّن
# الـ٢٧ وبقيت ثلاثةُ مكوّنات، فأُكمل الإعلان بثمانيةٍ **مقيسةٍ من قاعدته
# لا من أصغر عدد**: «الحافّة التي تحمل النتيجة المتحقّقة وتعيدها إلى مَن
# أصدر الأمر». وأرخصُ المجموعات (خمسةُ أحداثٍ بـ١٢ مكافئة) مرفوضةٌ لأنّها
# تُعلن `execution.manage.command` راجعًا وهو **أمرٌ ذاهب**.
FEEDBACK_EVENTS: tuple[str, ...] = (
    # ── العقد الأوّل ─────────────────────────────────────────────────────
    "learning.model.evidence",
    "market.outcome.realized",
    "execution.order.built",
    "risk.asset_ledger.state",
    "risk.kill_switch.reset_requested",
    "execution.order.rejected",
    "emergency.halt",
    # ── تمامُ العقد: نتائجُ التنفيذ المتحقّقة ────────────────────────────
    "execution.command.ack",            # 563 ⟶ 520  تأكيدُ الوسيط ⟶ المصالحة
    "execution.command.failed",         # 575 ⟶ 570  فشلُ إرسالٍ ⟶ المنسّق
    "execution.manage.written",         # 575 ⟶ 570  كُتب الأمر ⟶ المنسّق
    "asset.extraction.confirmed",       # 579 ⟶ 524  تأكيدُ سحبٍ ⟶ الاستخلاص
    "asset.extraction.failed",          # 579 ⟶ 524  فشلُ سحبٍ ⟶ الاستخلاص
    "risk.margin.validation.completed",  # 526 ⟶ 516  حكمُ الهامش ⟶ السلطة
    "learning.model.active.state",      # 367 ⟶ 365  حالةُ السجلّ ⟶ المقارنة
    "dial.profile.state",               # 523 ⟶ 581  ناتجُ العيار ⟶ صاحبه
)

FEEDBACK = "FEEDBACK"

#: حوافٌّ **مختومةٌ بعينها**: تُعدّ راجعةً دائمًا، ويُتحقَّق من وجودها.
#: وهي مشمولةٌ بالأحداث أعلاه، فتبقى هنا سندًا صريحًا لا اشتقاقًا وحده.
#:
#: ⛔ ولا يُضاف إليها ما اشتقّه الرسم: «والأحداث الأخرى… تدخل في نفس
#: سياسة FEEDBACK، ولا تُحوَّل إلى حوافَّ ثابتةٍ باليد» — ختم المالك.
#:
#: ٢٠٢٦-١٠-٠٧ (ختم المالك «NQ»): خرجت الحافّتان `367 ⟶ 452` و`523 ⟶ 581` — طرفاهما 452 و581
#: أُرشفا مع فكّ الأقسام عن القرار، فصارتا إعلانًا بائتًا (`feedback_stale`). والحدثان باقيان
#: في FEEDBACK_EVENTS: الاشتقاق يقطع بهما أيَّ حافّةٍ راجعةٍ تظهر لهما من جديد.
FEEDBACK_EDGES: tuple[tuple[str, str, str], ...] = (
    ("516", "506", "risk.kill_switch.reset_requested"),
    ("518", "524", "risk.asset_ledger.state"),
    ("551", "518", "execution.order.built"),
    ("563", "517", "market.outcome.realized"),
    # ⚠️ كتب المالك `552 ⟶ 516`، والمانيفست يقول إنّ ناشر الحدث **٥٨٥**
    #    (حارس الهامش) لا ٥٥٢ (مدقّق الأمر)، وأنّ ٥١٦ و٥٥٢ كلاهما مشترِك.
    #    فصورتُه الدلاليّة قائمةٌ حرفًا — الذاهب إلى المدقّق يبقى والعائد
    #    إلى السلطة يُقطَع — ورقمُ الناشر وحده صُحِّح: `585 ⟶ 516`.
    #    ونُقل حارسُ الهامش من ٥٨٥ إلى ٥٢٦ بختم `nq` ٢٠٢٦-٠٩-٢٣ (قسم المخاطر).
    ("526", "516", "risk.margin.validation.completed"),
)

#: حوافٌّ ختمها المالك **ذاهبةً** — لا تُقطَع ولو حملت حدثًا راجعًا.
#:
#:      الذهاب:  581 ⟶ 523  decision.settings.state  = NORMAL
#:               526 ⟶ 552                            = NORMAL
#:               552 ⟶ 563  trading.final_decision   = NORMAL
#:
#: وهذه ليست زينة. `526 ⟷ 552` **زوجٌ راجعٌ في الاتّجاهين**: حكمُ الهامش
#: يصل المدقّقَ، ورفضُ الأمر يعود إلى الحارس. والرسمُ وحده لا يفصل بينهما،
#: فكان الفرزُ بالاسم يقطع الأوّل — أي أنّ المدقّق يوافق على حكم هامشٍ من
#: **الدورة السابقة**. وهو عينُ ما نهى عنه المالك: «لا نقطع المسار الذاهب
#: إلى المدقّق». فيُثبَّت ذاهبًا، فيصير `552 ⟶ 526` هو الراجع اشتقاقًا.
#:
#: ⚠️ ورقمُ الناشر في ختمه (`516 ⟶ 552`) صُحِّح إلى `585 ⟶ 552`: المانيفست
#:    يقول إنّ ناشر `risk.margin.validation.completed` هو ٥٨٥ لا ٥٥٢.
#:
#: ٢٠٢٦-١٠-٠٧ (ختم المالك «NQ»): خرجت `581 ⟶ 523` (decision.settings.state) — 581 أُرشفت مع
#: فكّ الأقسام عن القرار، فصارت إعلانًا ذاهبًا بائتًا (`normal_stale`).
NORMAL_EDGES: tuple[tuple[str, str, str], ...] = (
    ("552", "563", "trading.final_decision"),
    ("526", "552", "risk.margin.validation.completed"),  # كان ٥٨٥ — نُقل ٢٠٢٦-٠٩-٢٣
)


class CompileError(RuntimeError):
    """خطّةٌ لا تُجمَّع. تُرفَض ولا تُصلَح — §٢٠: لا اعتمادَ مجهولٌ يُفترَض."""


@dataclass(frozen=True)
class Node:
    """عقدةُ تنفيذٍ: ذرّةٌ تستهلك أحداثًا وتنتج أخرى."""
    atom_id: str
    name: str
    section: int
    subscribes: tuple[str, ...]
    publishes: tuple[str, ...]
    policy: str


@dataclass
class HotPlan:
    """الخطّة المُجمَّعة — تُبنى مرّةً وتُقرأ كثيرًا."""
    nodes: dict[str, Node] = field(default_factory=dict)
    order: tuple[str, ...] = ()
    #: `حدث ⟶ العقد التي تنتجه` و`حدث ⟶ العقد التي تستهلكه`.
    producers: dict[str, tuple[str, ...]] = field(default_factory=dict)
    consumers: dict[str, tuple[str, ...]] = field(default_factory=dict)
    #: `عقدة ⟶ من تعتمد عليه` (بالاسم، مرتّبًا).
    depends_on: dict[str, tuple[str, ...]] = field(default_factory=dict)
    dependents: dict[str, tuple[str, ...]] = field(default_factory=dict)
    policies: dict[str, str] = field(default_factory=dict)
    central: tuple[str, ...] = ()
    cross_symbol: tuple[str, ...] = ()
    external_inputs: tuple[str, ...] = ()
    #: `حدث ⟶ من ينتظره` بلا ناشرٍ في المستودع كلّه. يُعرَض ولا يُبنى عليه
    #: اعتماد — ولا يُسمّى «مجهولًا» ولا يُفترَض له ناشر (ختم المالك).
    dangling: dict[str, tuple[str, ...]] = field(default_factory=dict)
    #: كلُّ الحوافّ الراجعة التي **وُجدت فعلًا** في الرسم، بحدثها.
    feedback: tuple[tuple[str, str, str], ...] = ()
    #: ما كان منها **مختومًا بعينه** — سندُ المالك الصريح.
    feedback_declared: tuple[tuple[str, str, str], ...] = ()
    #: ما **اشتقّه المُجمِّع** من الرسم بالحدث — لم يُكتب بيدٍ قطّ.
    feedback_derived: tuple[tuple[str, str, str], ...] = ()
    #: حوافٌّ حملت حدثًا راجعًا و**لم تكن راجعة**: ذاهبةٌ إلى أمامٍ لم تُنتَج
    #: فيه النتيجة بعد، فبقيت اعتمادًا عاديًّا. تُعرَض كي يظهر أنّ الإعلان
    #: بالحدث لم يقطع اعتمادًا مشروعًا.
    feedback_forward: tuple[tuple[str, str, str], ...] = ()
    #: حوافٌّ ختمها المالك ذاهبةً ووُجدت في الرسم، فلم تدخل الفرز أصلًا.
    normal_sealed: tuple[tuple[str, str, str], ...] = ()
    #: حوافٌّ مُعلَنةٌ ولم تعد في المانيفستات — إعلانٌ بائتٌ يُسمَّى لا يُسكَت.
    feedback_stale: tuple[tuple[str, str, str], ...] = ()
    normal_stale: tuple[tuple[str, str, str], ...] = ()

    def fingerprint(self) -> str:
        """بصمةٌ حتميّةٌ للخطّة — §٢٩: إعادتان تعطيان البصمة نفسها."""
        import hashlib
        digest = hashlib.blake2b(digest_size=16)
        for atom_id in self.order:
            node = self.nodes[atom_id]
            digest.update(("%s|%s|%s|%s|%s\n" % (
                node.atom_id, node.policy,
                ",".join(node.subscribes), ",".join(node.publishes),
                ",".join(self.depends_on.get(atom_id, ()))
            )).encode("utf-8"))
        for producer, consumer, event in self.feedback:
            digest.update(("FEEDBACK|%s|%s|%s\n"
                           % (producer, consumer, event)).encode("utf-8"))
        for producer, consumer, event in self.normal_sealed:
            digest.update(("NORMAL|%s|%s|%s\n"
                           % (producer, consumer, event)).encode("utf-8"))
        return digest.hexdigest()

    def summary(self) -> dict[str, Any]:
        return {
            "nodes": len(self.nodes),
            "order": len(self.order),
            "local": sum(1 for p in self.policies.values() if p == LOCAL),
            "cross_symbol": len(self.cross_symbol),
            "central": len(self.central),
            "events_produced": len(self.producers),
            "events_consumed": len(self.consumers),
            "external_inputs": len(self.external_inputs),
            "dangling": len(self.dangling),
            "feedback": len(self.feedback),
            "feedback_declared": len(self.feedback_declared),
            "feedback_derived": len(self.feedback_derived),
            "feedback_forward": len(self.feedback_forward),
            "normal_sealed": len(self.normal_sealed),
            "feedback_stale": len(self.feedback_stale),
            "normal_stale": len(self.normal_stale),
            "fingerprint": self.fingerprint(),
        }


def _section_of(atom_id: str) -> int | None:
    try:
        return int(str(atom_id).strip())
    except (TypeError, ValueError):
        return None


def policy_for(atom_id: str) -> str:
    """تصنيفُ عقدةٍ — بالاسم من العقد المكتوب، لا بتخمين."""
    text = str(atom_id).strip()
    if text in CENTRAL_ATOMS:
        return CENTRAL
    if text in CROSS_SYMBOL_ATOMS:
        return CROSS_SYMBOL
    return LOCAL


def external_events(root: Path | str = "") -> frozenset[str]:
    """الأحداث الداخلة من خارج النطاق الساخن — **مشتقّةٌ لا مكتوبة بيد**.

    ثلاثة مصادرَ، كلٌّ من موضعه لا من ذاكرتي:

        ١) ما تنشره ذرّاتٌ خارج `100..599` (تغذيةٌ · تنفيذٌ · تخزينٌ · قياس)
        ٢) إشارات الوقت من النواة نفسها: `core.event_bus._TIME_SIGNAL_EVENTS`
        ٣) دورة حياة الذرّة التي تنشرها النواة: `core.atom.*`

    ⛔ وقائمةٌ مكتوبةٌ بالأسماء ممنوعة: لو أضاف المالك ذرّةً تنشر حدثًا
       جديدًا، وجب أن يعرفه المُجمِّع من المانيفست لا من تحديثي.
    """
    import yaml

    base = Path(root) if root else (_ROOT / "atoms")
    outside: set[str] = set()
    for path in sorted(base.rglob("manifest.yaml")):
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except Exception:                                      # noqa: BLE001
            continue
        section = _section_of(data.get("id"))
        if section is not None and HOT_RANGE[0] <= section <= HOT_RANGE[1]:
            continue
        outside.update(str(e) for e in (data.get("publishes") or []) if e)

    try:
        from core.event_bus import _TIME_SIGNAL_EVENTS
        outside.update(str(e) for e in _TIME_SIGNAL_EVENTS)
    except Exception:                                          # noqa: BLE001
        raise CompileError("تعذّر قراءة إشارات الوقت من النواة — "
                           "ولا تُكتب بالأسماء بديلًا عنها")

    # دورةُ حياة الذرّة تنشرها النواة نفسها، ولا مانيفستَ لها. والاستخراج
    # بتعبيرٍ نمطيّ على `publish(… "الاسم"` مهما تعدّدت الأسطر — الصيغة
    # الأولى طابقت نصًّا حرفيًّا فأسقطت `core.atom.started` المكتوب بسطرين.
    import re as _re
    pattern = _re.compile(r'publish\(\s*"((?:core|SYS)[^"]*)"')
    for path in sorted((_ROOT / "core").rglob("*.py")):
        text = path.read_text(encoding="utf-8", errors="ignore")
        outside.update(pattern.findall(text))
    return frozenset(outside)


def read_manifests(root: Path | str = "") -> list[dict[str, Any]]:
    """يقرأ مانيفستات الذرّات في النطاق الساخن — قراءةٌ محضة."""
    import yaml

    base = Path(root) if root else (_ROOT / "atoms")
    out: list[dict[str, Any]] = []
    for path in sorted(base.rglob("manifest.yaml")):
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except Exception as exc:                               # noqa: BLE001
            raise CompileError("مانيفستٌ لا يُقرأ: %s — %s" % (path, exc)) from exc
        section = _section_of(data.get("id"))
        if section is None or not (HOT_RANGE[0] <= section <= HOT_RANGE[1]):
            continue
        out.append({
            "atom_id": str(data.get("id")).strip(),
            "name": str(data.get("name") or ""),
            "section": section,
            "subscribes": tuple(str(e) for e in (data.get("subscribes") or []) if e),
            "publishes": tuple(str(e) for e in (data.get("publishes") or []) if e),
        })
    return out


def compile_plan(manifests: Iterable[dict[str, Any]] | None = None, *,
                 root: Path | str = "",
                 known_external: Iterable[str] = (),
                 strict_dangling: bool = False,
                 feedback_events: Iterable[str] = FEEDBACK_EVENTS,
                 feedback_edges: Iterable[tuple[str, str, str]] = FEEDBACK_EDGES,
                 normal_edges: Iterable[tuple[str, str, str]] = NORMAL_EDGES,
                 ) -> HotPlan:
    """يبني الخطّة أو يرفع `CompileError`. حتميٌّ: نفسُ المدخل ⟶ نفسُ الخطّة.

    `known_external` أحداثٌ تدخل من خارج النطاق الساخن (تغذيةٌ أو نواة).
    وما ليس فيها ولا ينتجه أحدٌ داخل الرسم **اعتمادٌ مجهول** ⟶ فشل.
    """
    rows = list(manifests) if manifests is not None else read_manifests(root)
    if not rows:
        raise CompileError("لا ذرّات في النطاق الساخن — لا خطّة تُبنى")

    plan = HotPlan()
    producers: dict[str, list[str]] = {}
    consumers: dict[str, list[str]] = {}
    for row in sorted(rows, key=lambda r: (r["section"], r["atom_id"])):
        atom_id = row["atom_id"]
        if atom_id in plan.nodes:
            raise CompileError("ذرّةٌ مكرّرة في المانيفستات: %s" % atom_id)
        node = Node(atom_id=atom_id, name=row["name"], section=row["section"],
                    subscribes=tuple(sorted(set(row["subscribes"]))),
                    publishes=tuple(sorted(set(row["publishes"]))),
                    policy=policy_for(atom_id))
        plan.nodes[atom_id] = node
        plan.policies[atom_id] = node.policy
        for event in node.publishes:
            producers.setdefault(event, []).append(atom_id)
        for event in node.subscribes:
            consumers.setdefault(event, []).append(atom_id)

    external = set(str(e) for e in known_external)
    dangling: dict[str, list[str]] = {}
    declared_feedback = {tuple(edge) for edge in feedback_edges}
    declared_normal = {tuple(edge) for edge in normal_edges}
    both = declared_feedback & declared_normal
    if both:
        raise CompileError("حافّةٌ مختومةٌ راجعةً وذاهبةً معًا: %s"
                           % ", ".join("%s ⟶ %s عبر %s" % t for t in sorted(both)))
    feedback_event_set = frozenset(str(e) for e in feedback_events)
    seen_feedback: set[tuple[str, str, str]] = set()
    seen_normal: set[tuple[str, str, str]] = set()
    candidates: list[tuple[str, str, str]] = []
    depends: dict[str, set[str]] = {a: set() for a in plan.nodes}
    #: `(منتِج، مستهلك) ⟶ الأحداث` للحوافّ الإلزاميّة — كي يسمّي الرفضُ
    #: ما يُغلق المكوّن بحدثه، فيُختَم منه مباشرةً لا من تحليلٍ جديد.
    carried: dict[tuple[str, str], set[str]] = {}
    for event, listeners in consumers.items():
        makers = producers.get(event)
        if not makers:
            if event in external:
                continue
            # ⛔ لا ناشرَ له لا داخل النطاق ولا خارجه ⟶ **معلَّقٌ** لا مجهول.
            #    ولا حافّةَ اعتمادٍ تُبنى على ما لا يُنتِجه أحد. يُسمَّى
            #    ويُعدّ، ولا يُفترَض محلّيًّا، ولا يُبتلع صامتًا.
            for listener in listeners:
                dangling.setdefault(event, []).append(listener)
            continue
        for listener in listeners:
            for maker in makers:
                if maker == listener:
                    continue
                triple = (maker, listener, event)
                if triple in declared_feedback:
                    # مختومةٌ بعينها — راجعةٌ دائمًا وبلا فحصِ سلَف.
                    seen_feedback.add(triple)
                elif triple in declared_normal:
                    # ⛔ مختومةٌ **ذاهبةً**: تدخل العمود ولا تُعرَض على الفرز
                    #    أبدًا. وهذه هي التي تمنع الاسمَ المرتَّب من الحكم
                    #    على زوجٍ راجعٍ في الاتّجاهين — مسارُ مالٍ لا يُترَك
                    #    للأبجديّة.
                    seen_normal.add(triple)
                    depends[listener].add(maker)
                    carried.setdefault((maker, listener), set()).add(event)
                elif event in feedback_event_set:
                    # مرشّحةٌ بالحدث: تُؤجَّل حتّى يُبنى الرسم الإلزاميّ،
                    # ثمّ يُفصَل فيها بفحصِ السلَف لا بالاسم وحده.
                    candidates.append(triple)
                else:
                    depends[listener].add(maker)
                    carried.setdefault((maker, listener), set()).add(event)
    # ⛔ كان هنا مسارٌ ثانٍ اسمه `unknown` — وصار **ميّتًا** بعد تصنيف
    #    `DANGLING`: كلّ حدثٍ إمّا له ناشرٌ (حافّة)، أو مُعلَنٌ خارجيًّا (بلا
    #    حافّة)، أو بلا ناشرٍ إطلاقًا (معلَّق). فلا حالةَ ثالثة تبقى.
    #    وحارسٌ يدّعي إنفاذ §٢٠ ولا يُبلَغ أبدًا أسوأ من غيابه، فأُزيل.
    if dangling and strict_dangling:
        lines = ["اشتراكاتٌ معلَّقةٌ بلا ناشر — %d حدثًا:" % len(dangling)]
        for event, listeners in sorted(dangling.items()):
            lines.append("  %s ⟵ %s" % (event, ", ".join(sorted(listeners))))
        raise CompileError("\n".join(lines))

    # ── العمود أوّلًا، ثمّ يُفصَل في المرشّحات ────────────────────────────
    #
    # ختم المالك «Temporal SCC»: الإعلان يقع على **الحدث**، والمُجمِّع يشتقّ
    # الحافّة. فلا تُكتب `551⟶518` و`551⟶519` و`551⟶523`… باليد، ولا تنفجر
    # القائمة كلّما كُشف مسارٌ آخر داخل المجموعة نفسها.
    #
    # والترتيب مقصود: تُبنى أوّلًا الحوافّ التي **لا تحمل** حدثًا راجعًا —
    # وهي وحدها العمود — ثمّ تُعرَض كلّ مرشّحةٍ عليه:
    #
    #     تصل من المنتِج إلى المستهلك إلى أمامٍ  ⟶ حافّةٌ عاديّة تبقى
    #     تعود إلى سلفٍ (إضافتها تُغلق حلقة)      ⟶ FEEDBACK
    #
    # ⛔ ودورةٌ في العمود نفسه **لا يكسرها إعلانٌ**: لا حدثَ راجعٌ فيها
    #    يُعلَّق عليه، فتُسمَّى مكوّنًا ويُرفَض البناء (§١٩).
    _refuse_components(depends, carried, plan.nodes)
    _refuse_two_way(candidates, depends, plan.nodes)
    forward: list[tuple[str, str, str]] = []
    # والترتيب بالثلاثيّة مرتَّبًا — §٢٩: إعادتان، بصمةٌ واحدة. ولا يقع على
    # هذا الترتيب حكمٌ في زوجٍ راجعٍ في الاتّجاهين: ذاك يُرفَض قبله.
    for maker, listener, event in sorted(candidates):
        if _depends_through(depends, maker, listener):
            seen_feedback.add((maker, listener, event))
        else:
            depends[listener].add(maker)
            forward.append((maker, listener, event))

    plan.dangling = {e: tuple(sorted(v)) for e, v in sorted(dangling.items())}
    plan.producers = {e: tuple(sorted(v)) for e, v in sorted(producers.items())}
    plan.consumers = {e: tuple(sorted(v)) for e, v in sorted(consumers.items())}
    plan.depends_on = {a: tuple(sorted(v)) for a, v in sorted(depends.items())}
    dependents: dict[str, set[str]] = {a: set() for a in plan.nodes}
    for listener, makers in depends.items():
        for maker in makers:
            dependents[maker].add(listener)
    plan.dependents = {a: tuple(sorted(v)) for a, v in sorted(dependents.items())}
    plan.central = tuple(sorted(a for a, p in plan.policies.items() if p == CENTRAL))
    plan.cross_symbol = tuple(sorted(a for a, p in plan.policies.items()
                                     if p == CROSS_SYMBOL))
    plan.external_inputs = tuple(sorted(
        e for e in consumers if e not in producers and e in external))
    plan.feedback = tuple(sorted(seen_feedback))
    plan.feedback_declared = tuple(sorted(seen_feedback & declared_feedback))
    plan.feedback_derived = tuple(sorted(seen_feedback - declared_feedback))
    plan.feedback_forward = tuple(sorted(forward))
    plan.normal_sealed = tuple(sorted(seen_normal))
    plan.feedback_stale = tuple(sorted(declared_feedback - seen_feedback))
    plan.normal_stale = tuple(sorted(declared_normal - seen_normal))
    # ⛔ حارسٌ داخل المُجمِّع نفسه: حافّةٌ راجعةٌ **لا تكون اعتمادًا داخل
    #    التِكّة**. لو أعادها أحدٌ حافّةً عاديّة، يفشل التجميع ولا يمرّ صامتًا.
    for producer, consumer, event in plan.feedback:
        if producer in plan.depends_on.get(consumer, ()):
            raise CompileError(
                "حافّةٌ راجعةٌ استُعملت اعتمادًا داخل التِكّة: %s ⟶ %s عبر %s"
                % (producer, consumer, event))
    plan.order = _topological(plan)
    return plan


def _depends_through(depends: dict[str, set[str]], start: str, target: str) -> bool:
    """هل يعتمد `start` — ولو بالوساطة — على `target`؟

    وهو **فحصُ السلَف** الذي يفصل الراجعة عن الذاهبة، ولا يفصلهما الاسمُ
    ولا رقمُ القسم: `367⟶452` و`518⟶524` تصعدان بالرقم وهما راجعتان،
    و`516⟶506` تنزل. فالحكم من الرسم وحده.

    فإن كان `start` يعتمد أصلًا على `target`، فإضافةُ «`target` يعتمد على
    `start`» تُغلق حلقةً ⟶ راجعة. وإلّا فذاهبةٌ تبقى اعتمادًا عاديًّا.
    """
    if start == target:
        return True
    seen = {start}
    stack = [start]
    while stack:
        for nxt in depends.get(stack.pop(), ()):
            if nxt == target:
                return True
            if nxt not in seen:
                seen.add(nxt)
                stack.append(nxt)
    return False


def _refuse_two_way(candidates: list[tuple[str, str, str]],
                    depends: dict[str, set[str]],
                    nodes: dict[str, Node]) -> None:
    """يرفض زوجًا **مرشّحًا في الاتّجاهين** ولا يدع الاسم يحكم فيه.

    ⛔ الحالة: `أ ⟶ ب` و`ب ⟶ أ` كلاهما يحمل حدثًا راجعًا، ولا يصل أحدهما
    إلى الآخر في العمود المجمَّد. فالرسم **لا يفصل**، وأوّلُ من يُفرَز يبقى
    ذاهبًا والثاني يصير راجعًا — أي أنّ الأبجديّة تقرّر أيُّ طرفٍ يقرأ
    الدورة السابقة.

    وهذا وقع فعلًا على `585 ⟷ 552`: قطع الفرزُ حكمَ الهامش إلى المدقّق،
    فكان المدقّق يوافق على هامشِ دورةٍ ماضية. فصار الرفض صريحًا، ويُفَضّ
    بختم `NORMAL_EDGES` لا بترتيبِ حروف.
    """
    seen = {(maker, listener) for maker, listener, _ in candidates}
    pairs = sorted({tuple(sorted((a, b))) for a, b in seen if (b, a) in seen})
    blocked = [(a, b) for a, b in pairs
               if not _depends_through(depends, a, b)
               and not _depends_through(depends, b, a)]
    if not blocked:
        return
    lines = ["زوجٌ راجعٌ في الاتّجاهين والرسمُ لا يفصل فيه — %d زوجًا. "
             "يُفَضّ بختم `NORMAL_EDGES` لا بترتيب الأسماء:" % len(blocked)]
    for a, b in blocked:
        lines.append("")
        for maker, listener in ((a, b), (b, a)):
            node = nodes.get(listener)
            for _, _, event in sorted(c for c in candidates
                                      if c[0] == maker and c[1] == listener):
                lines.append("  %s ⟶ %-5s %-34s (%s)"
                             % (maker, listener, event,
                                node.name if node else ""))
    raise CompileError("\n".join(lines))


def _refuse_components(depends: dict[str, set[str]],
                       carried: dict[tuple[str, str], set[str]],
                       nodes: dict[str, Node]) -> None:
    """يرفض البناء على **مكوّنٍ** متّصلٍ بقوّة، ويسمّي أعضاءه وأحداثه.

    ولا يطارد حلقةً حلقة: مطاردةُ الحلقات تُعطي سرابًا يتكاثر — كلّ حدٍّ
    يُعلَن يكشف مسارًا آخر داخل المجموعة نفسها. وتسميةُ المكوّن تُعطي
    المالك ما يقرّر عليه.

    والرفض يطبع **حوافَّه الداخليّة بأحداثها**، لأنّ الحكم يقع على الحدث:
    فيُختَم من نصّ الرفض مباشرةً، ولا يُطلَب تحليلٌ جديد لكلّ مكوّن.
    """
    blocks = strongly_connected(depends)
    if not blocks:
        return
    lines = ["دورةُ اعتمادٍ ترفض الإقلاع (§١٩) — %d مكوّنًا لا يحمل أيٌّ من "
             "حوافّه الداخليّة حدثًا مُعلَنًا راجعًا:" % len(blocks)]
    for block in blocks:
        members = set(block)
        lines.append("")
        lines.append("  مكوّنٌ من %d ذرّة:" % len(block))
        for atom_id in block:
            node = nodes.get(atom_id)
            lines.append("    %-5s %s" % (atom_id, node.name if node else ""))
        lines.append("  وحوافُّه الداخليّة بأحداثها:")
        for (maker, listener), events in sorted(carried.items()):
            if maker in members and listener in members:
                for event in sorted(events):
                    lines.append("    %s ⟶ %-5s %s" % (maker, listener, event))
    raise CompileError("\n".join(lines))


def _topological(plan: HotPlan) -> tuple[str, ...]:
    """ترتيبٌ طوبولوجيٌّ **حتميّ** — والتعادل يُفَضّ بالاسم لا بالصدفة.

    ودورةٌ حقيقيّةٌ تُسمَّى ولا تُكسَر: §١٩ يرفض الإقلاع عليها.
    """
    remaining = {a: set(v) for a, v in plan.depends_on.items()}
    order: list[str] = []
    while remaining:
        ready = sorted(a for a, deps in remaining.items()
                       if not (deps & remaining.keys()))
        if not ready:
            # ⛔ `remaining[a]` = مَن تعتمد عليه `a` — أي **الأسلاف** لا
            #    الأخلاف. فالمسار الراجع يُقلَب قبل أن يُطبع، وإلّا قرأه
            #    القارئ بالاتّجاه المعكوس وحكم على غير ما وقع.
            cycle = list(reversed(_find_cycle(remaining)))
            raise CompileError("دورةُ اعتمادٍ ترفض الإقلاع (§١٩): %s"
                               % " → ".join(cycle + [cycle[0]]))
        for atom_id in ready:
            order.append(atom_id)
            remaining.pop(atom_id, None)
    return tuple(order)


def strongly_connected(edges: dict[str, set[str]]) -> list[list[str]]:
    """المكوّنات المتّصلة بقوّة — تُسمّي **البنية** بدل مطاردة حلقةٍ حلقة.

    ⛔ وُلدت لأنّ العدّ حلقةً حلقةً كان يتكاثر بلا نهاية: كلّ حدٍّ يُعلَن
    يكشف مسارًا آخر داخل المجموعة نفسها. والحقيقة أنّ ذلك ليس سبع حلقاتٍ
    ولا عشرًا، بل **مجموعةٌ يصل كلُّ عضوٍ فيها إلى كلّ عضو**. وتسميةُ
    المجموعة تُعطي المالك ما يقرّر عليه؛ ومطاردةُ الحلقات تُعطيه سرابًا.

    خوارزمية Tarjan، تكراريّةٌ لا عوديّة — الرسم قد يعمق.
    """
    index: dict[str, int] = {}
    low: dict[str, int] = {}
    on_stack: set[str] = set()
    stack: list[str] = []
    result: list[list[str]] = []
    counter = 0

    for root in sorted(edges):
        if root in index:
            continue
        work: list[tuple[str, int]] = [(root, 0)]
        while work:
            node, child = work[-1]
            if child == 0:
                index[node] = low[node] = counter
                counter += 1
                stack.append(node)
                on_stack.add(node)
            successors = sorted(edges.get(node, ()))
            if child < len(successors):
                work[-1] = (node, child + 1)
                nxt = successors[child]
                if nxt not in index:
                    work.append((nxt, 0))
                elif nxt in on_stack:
                    low[node] = min(low[node], index[nxt])
                continue
            work.pop()
            if work:
                parent = work[-1][0]
                low[parent] = min(low[parent], low[node])
            if low[node] == index[node]:
                component: list[str] = []
                while True:
                    member = stack.pop()
                    on_stack.discard(member)
                    component.append(member)
                    if member == node:
                        break
                result.append(sorted(component))
    return sorted((c for c in result if len(c) > 1), key=lambda c: -len(c))


def _find_cycle(remaining: dict[str, set[str]]) -> list[str]:
    """يسمّي دورةً واحدةً بعينها — الرفض بلا اسمٍ لا يُصلَح."""
    colour: dict[str, int] = {}
    stack: list[str] = []

    def walk(node: str) -> list[str] | None:
        colour[node] = 1
        stack.append(node)
        for nxt in sorted(remaining.get(node, ())):
            if nxt not in remaining:
                continue
            state = colour.get(nxt, 0)
            if state == 1:
                return stack[stack.index(nxt):]
            if state == 0:
                found = walk(nxt)
                if found:
                    return found
        colour[node] = 2
        stack.pop()
        return None

    for node in sorted(remaining):
        if colour.get(node, 0) == 0:
            found = walk(node)
            if found:
                return found
    return sorted(remaining)[:1]
