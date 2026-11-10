"""٧٠٧ — أسماءُ المراحل وسياستُها: ما يحميه السقف، وما يُؤجَّل إلى الدفعة، وما يُقصّ أوّلًا.

v4.20.1 (٢٠٢٦-١٠-٠١، ختم المالك «Nq»): نُقلت **حرفيًّا** من `atom.py` ليبقى تحت حدّ
الأربع مئة سطر فعليّ (المادة ٩ ملف ٤). لا اسمَ ولا رقمَ ولا نصَّ SQL ولا منطقَ تبدّل —
الموضعُ وحده. والقائمتان (`_PROTECTED_WHERE` و`_is_deferrable`) تتّفقان عن قصد، فهما
هنا معًا. و`trim_buffer` تأخذ الذرّة أوّلًا (`atom`) مكان `self`، و`atom.py` يُبقي
اسمها القديم `_trim_buffer` بوّابةً رفيعة.
"""

from __future__ import annotations

from typing import Any

STAGE_APPROVED = "APPROVED"
# عقد المحورين v1.1 §3-6: هدف 581 يُسجَّل بحقوله (risk_dial, base_target,
# gross_target, target_net, remaining_RB, dial_add_budget, remaining_add_budget)
# — الحمولة كاملة في payload_json.
STAGE_TARGET = "TARGET_STATE"
STAGE_DISPATCH = "DISPATCH"
STAGE_ORDER_REQUESTED = "ORDER_REQUESTED"
STAGE_ORDER_BUILT = "ORDER_BUILT"
STAGE_ORDER_REJECTED = "ORDER_REJECTED"
STAGE_DECISION_FINALIZED = "DECISION_FINALIZED"
STAGE_QUEUED = "QUEUED_TO_BRIDGE"
STAGE_BRIDGE_FAILED = "BRIDGE_WRITE_FAILED"
STAGE_ACKNOWLEDGED = "BROKER_ACKNOWLEDGED"
STAGE_COMMAND_FAILED = "BROKER_COMMAND_FAILED"
STAGE_FILLED_OPEN = "FILLED_OPEN"
STAGE_FILLED_PARTIAL = "FILLED_PARTIAL"
STAGE_FILLED_CLOSED = "FILLED_CLOSED"

# مراحل لا يطردها السقف. الحذف بالأقدميّة وحدها أعمى، ومقيس ٢٠٢٦-٠٩-٠٩ أنّ
# `TARGET_STATE` وحدها ٤٥٢٬٩٦٦ صفًّا من ٥٢٨٬٠٧٥ (٨٣٪) بينما تذاكر التنفيذ
# نادرة: ٩٥ إرسالًا · ٤٩ طلب أمر · ٢٨ أمرًا مبنيًّا · ٤ إشعارات وسيط. فطوفان
# حالات الهدف كان يطرد سجلّ التنفيذ نفسه — وهو الذي لا يُعوَّض. القاعدة تحتفظ
# اليوم بيوم واحد بينما جاراتها تحتفظ بأربعة ونصف؛ فليكن المقصوص هو المتكرّر.
_PROTECTED_STAGES = (
    STAGE_DISPATCH, STAGE_ORDER_REQUESTED, STAGE_ORDER_BUILT, STAGE_ORDER_REJECTED,
    STAGE_DECISION_FINALIZED, STAGE_QUEUED, STAGE_BRIDGE_FAILED,
    STAGE_ACKNOWLEDGED, STAGE_COMMAND_FAILED,
    STAGE_FILLED_OPEN, STAGE_FILLED_PARTIAL, STAGE_FILLED_CLOSED,
)
# والقرار المقبول نفسه محميّ — لا مراحلُ تنفيذه وحدها. كان السقف يُبقي
# `DISPATCH` ويأكل `APPROVED`، فتبقى الصفقة معروفة الهويّة مجهولة السبب:
# لا ثقة ولا سبب ولا عيار مسجّل لقرارٍ كلّف مالًا. مقيس ٢٠٢٦-٠٩-١٦ على
# القاعدة الحيّة: من ٤٤ تذكرة بهويّة قرار، **٤٠ لها `DISPATCH` وواحدة لها
# `APPROVED`** — أي الوصلة نجت بالمرحلة المحميّة وحدها. والثمن زهيد:
# `approved=1` **٣٧٨ صفًّا** من ٨٩٬٤٩١ (المرفوض ٨٩٬١١٣)، فالمحميّ يصير
# ٧٫٤٪ من الجدول بدل ٧٫٣٪. والمرفوض يبقى قابلًا للإخراج — سببه محفوظ في
# `rejection_reason` وفي الحمولة.
# ⚠️ `COALESCE` لا زينة: الإخراج يعمل بـ`WHERE NOT (<الحماية>)`، و`approved`
# قد تكون NULL — و`NOT (NULL)` في SQL ليست TRUE بل NULL، فالصفّ لا يُطابق
# ولا يخرج أبدًا. أي أنّ حمايةً مكتوبة `approved = 1` تحمي الفارغ أيضًا
# وتُجمّد السقف بصمت. كشفه اختبارٌ قائم حين سقط بـ«السقف ما عضّ».
_PROTECTED_WHERE = (
    "(stage IN (%s) OR (stage = '%s' AND COALESCE(approved, 0) = 1))" % (
        ", ".join("'%s'" % stage for stage in _PROTECTED_STAGES), STAGE_APPROVED))

# ‏**الطوفان يُكتب بدفعات، والتذكرة تُكتب فورًا.**
#
# مقيس ٢٠٢٦-٠٩-١٦ من تشريح المعالج نفسه (v4.12.1، ٨٨٤ إدراجًا حيًّا)، وميزانية
# المعالج ٠٫٠٥٠ ث:
#
#     المعالج كلّه  ٤٨٫٣٨٦ م.ث   ← عند حافّة الميزانية تمامًا
#       قفزة الخيط   ٥٫٥٨٦ م.ث   (١٢٪) انتظار خيط حرّ في المنفّذ
#       انتظار القفل ٢٫٦٩٦ م.ث   ( ٦٪) قفل الاتصال (الإنفاذ يحتجزه)
#       sqlite      ١٣٫٤٩٣ م.ث   (٢٨٪) العمل الحقيقيّ وحده
#       رحلة العودة ٢٦٫١٣٠ م.ث   (٥٤٪) إيقاظ حلقة الأحداث بعد انتهاء الخيط
#       نشر          ٠٫٣٧٨ م.ث   (<١٪)
#
# أي أنّ **ثلثَي زمن المعالج جدولةٌ لا عمل**: ذهابٌ وإيابٌ إلى خيطٍ عامل لأجل
# صفٍّ واحد، على حلقة أحداث تستضيف مئات المعالجات. والعلاج ليس تسريع sqlite
# بل **إلغاء الرحلة**: تُجمَّع صفوف الطوفان في ذاكرةٍ وتُكتب دفعةً واحدة خارج
# مسار الحدث، فيصير المعالج عملًا محضًا بلا `await` على خيط.
#
# لكن لا يُشترى ذلك بفقدِ ما لا يُعوَّض: **ما مرّ من البوّابة يُكتب فورًا** —
# تذاكر التنفيذ (٠٫٢٨ صفّ/ث) والقرار المقبول (٠٫٢١ صفّ/ث)، وكلاهما نادرٌ
# فكلفته لا تُذكر وفقدُه عند انقطاعٍ مفاجئ ثمنٌ لا يُدفع. والمؤجَّل هو
# المتكرّر والمرفوض: ٢٩٫١٤ صفًّا/ث من أصل ٢٩٫٦٣ مقيسة — انظر `_is_deferrable`.
_BUFFERED_FLUSH_S = 1.0
_BUFFER_MAX_ROWS = 500
# السقف الصلب: عند بلوغه يُقصّ الأقدم بدل أن ينتظر المعالج. عشرون ضعف عتبة
# الدفع — أي عشرون دفعةً متأخّرة. والمقيس ٢٠٢٦-٠٩-٢٢ أنّ أسوأ دفعةٍ استغرقت
# ١٦٧ ثانية، ومعدّل الورود في الطوفان ≈٢٩ صفًّا/ث ⟹ ‎4,800‎ صفًّا. فالسقف
# يستوعب أسوأ ما قِيس ويقصّ ما بعده مُعلِنًا، ولا يترك الذاكرة بلا حدّ.
_BUFFER_HARD_CAP = 10000

# ‏**قائمة سماحٍ لا قائمة منع**: المؤجَّل يُسمّى صراحةً، وكلّ ما عداه يبقى
# فوريًّا — فمرحلةٌ جديدة تُضاف غدًا تُولد دائمة لا مؤجَّلة.
#
# والمؤجَّل واحدة: `TARGET_STATE` — **٧٦٫٥٪ من الجدول** (٣٨٠٬٠٢٨ من ٤٩٦٬٧٤٠)
# وتُسجَّل ٢٥٫٩٢ صفًّا/ث: حالةٌ متكرّرة أحدثُها يكفي.
_BUFFERED_STAGES = frozenset({STAGE_TARGET})


def _is_deferrable(stage: str, row: dict[str, Any]) -> bool:
    """أيؤجَّل هذا الصفّ؟ — القطع بقيمة القرار لا باسم مرحلته وحده.

    كان القطع بالمرحلة: `APPROVED` كلّها فوريّة. والقياس ٢٠٢٦-٠٩-١٦ على
    القاعدة الحيّة يقول إنّ ذلك يخلط شيئين لا يجمعهما إلّا الاسم:

        المسار الفوريّ كلّه            ٣٫٧١ صفّ/ث
          APPROVED بـapproved=0        ٣٫٢٢   ٨٧٪   ← رفضٌ، طوفان
          APPROVED بـapproved=1        ٠٫٢١    ٦٪   ← مرّ من البوّابة
          تذاكر التنفيذ كلّها          ٠٫٢٨    ٧٪

    والتاريخ يؤكّده: `approved=1` **٥٬١٠٢ صفًّا من ٧١٬١٧٨** (٧٫٢٪). أي أنّ
    **٨٧٪ من رحلات الخيط الباقية كانت لقراراتٍ مرفوضة** — وثمن الرحلة
    الواحدة ٤٢٫٨ م.ث مقيسًا، ثلثاها انتظارُ جدولة.

    فالقطع صار حيث الفرق حقيقيّ: **قرارٌ مرّ من البوّابة يُكتب فورًا** —
    كلّف مالًا ولا يُعوَّض، وهو المحميّ من السقف بالمعيار نفسه
    (`_PROTECTED_WHERE`) فالقائمتان تتّفقان عن قصد. **والرفض يُجمَّع** — سببه
    محفوظ في `rejection_reason` وفي الحمولة، وتأخُّره ثانيةً لا يكلّف شيئًا.

    ⚠️ و`COALESCE` هنا لنفس سبب وجودها هناك: `approved` قد تكون NULL، وقرارٌ
    بلا حقلٍ صريح ليس قرارًا ناجحًا — فيُعامَل معاملة المرفوض ويُجمَّع.
    """
    if stage in _BUFFERED_STAGES:
        return True
    if stage != STAGE_APPROVED:
        return False
    return not row.get("approved")


def trim_buffer(atom) -> None:
    """القصُّ بالقيمة لا بالأقدميّة — وما يُقصّ يُسمّى بمرحلته.

    ⚠️ **وقع فعلًا: ١٬٣٤٩ قرارًا أُسقطت** يوم ٢٠٢٦-٠٩-٢٣ والبفر ممتلئ عند
    ١٠٬٠٠٠. والسبب مقيس: النسخة الاحتياطيّة (٨٠٠) تقرأ القواعد نفسها فقفز
    `sqlite` إلى **٤٬٨٥٧ م.ث** للإدراج الواحد، ووسطُ الدفعة **٣٬٤٧٢ م.ث**
    وأسوأها **١٨٢٬٣٤٩** — فعجزت عن التصريف وامتلأ البفر.

    والقصُّ السابق كان `del self._buffer[:excess]` — **الأقدم عمياءَ**.
    وهو يخلط ما لا يُعوَّض بما يتكرّر كلّ تِكّة: `TARGET_STATE` وحدها ٨٣٪
    من الجدول مقيسًا، بينما `APPROVED` المقبول نادر. فصار القصُّ بالترتيب:
    الطوفان أوّلًا، ثمّ الأقدم إن لم يكفِ — ولا تُمسّ مرحلةٌ محميّة إلّا
    عند العجز التامّ، وتُسمّى حينها.
    """
    excess = len(atom._buffer) - _BUFFER_HARD_CAP
    if excess <= 0:
        return
    # الأقلّ قيمةً أوّلًا: طوفانُ حالات الهدف، ثمّ باقي المؤجَّل
    order = {STAGE_TARGET: 0, STAGE_APPROVED: 1}
    victims = sorted(range(len(atom._buffer)),
                     key=lambda i: (order.get(atom._buffer[i][0], 2), i))[:excess]
    doomed = set(victims)
    dropped: dict[str, int] = {}
    kept = []
    for index, item in enumerate(atom._buffer):
        if index in doomed:
            dropped[item[0]] = dropped.get(item[0], 0) + 1
            continue
        kept.append(item)
    atom._buffer = kept
    atom.buffered_dropped += excess
    atom._last_error = "BUFFER_OVERFLOW: قُصّ %d (%s)" % (
        excess, " · ".join("%s=%d" % kv for kv in sorted(dropped.items())))
