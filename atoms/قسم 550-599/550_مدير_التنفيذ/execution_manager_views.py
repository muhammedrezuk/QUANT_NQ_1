"""٥٥٠ — ما تعرضه الذرّة: حالتها المنشورة (`state`) وشارتها (`health_check`).

٢٠٢٦-١٠-٠١ (ختم المالك «Nq»): نُقلتا **حرفيًّا** من `atom.py` ليبقى تحت حدّ الأربع
مئة سطرٍ فعليّ (المادة ٩ ملف ٤) — صفر تغيير في السلوك. كلتاهما تقرأ الذرّة ولا
تكتب فيها؛ و`self` صار الذرّةَ معاملًا أوّل (`atom`)، وبقي في `atom.py` تفويضٌ
بالاسمين القديمين (`_state` · `health_check`). ونافذةُ الشارة
(`_IDENTITY_ALERT_WINDOW_S`) هنا بشرحها، و`atom.py` يستوردها باسمها.
"""

from __future__ import annotations

import time
from typing import Any

from core.contracts.atom import HealthState, HealthStatus

# إسقاط هويّة واحد كان يُبقي الشارة صفراء **أبدًا**: الشرط على عدّاد
# تراكميّ، فأوّل إسقاط في العمر يصبغ الذرّة إلى آخر الدهر ولو كان قبل
# أسبوع. والرسالة كانت اسم السبب وحده بلا رقم — فلا يُعرف أواحدٌ هو أم
# ألف. الشارة تقيس الحاضر الآن، والعدد التراكميّ يبقى مرئيًّا في الرسالة.
_IDENTITY_ALERT_WINDOW_S = 300.0


def state(atom) -> dict[str, Any]:
    return {
        "id": "execution_manager", "status": "READ_ONLY",
        "counts": dict(atom._counts),
        "counts_by_account": {a: dict(v) for a, v in atom._counts_by_account.items()},
        "halted_accounts": dict(atom._halted_accounts),
        "orders": {key: dict(value) for key, value in atom._orders.items()},
        # قاموسٌ مسطّح `مفتاح ⟵ رتبة`: عقدةُ تجميدٍ واحدة مهما كثر.
        "retired_stages": dict(atom._retired),
        "last_outcome_by_account": dict(atom._last_outcome_by_account),
        "reject_reasons": dict(atom._reject_reasons),
        "skip_reasons": dict(atom._skip_reasons),
        "vocabulary": "PROVEN_EVENT_BOUNDARIES",
    }


async def health_check(atom) -> HealthStatus:
    if not atom._running:
        return HealthStatus(state=HealthState.UNHEALTHY, message="NOT_STARTED")
    details = {"counts": dict(atom._counts), "accounts": len(atom._counts_by_account),
               "orders": len(atom._orders), "halted_accounts": sorted(atom._halted_accounts),
               "reject_reasons": dict(atom._reject_reasons),
               "skip_reasons": dict(atom._skip_reasons),
               "identity_dropped": atom._identity_dropped,
               "identity_dropped_by": dict(atom._identity_dropped_by),
               # التقليم يُعلَن: تقليمٌ لا يُرى لا يُصدَّق.
               "live_orders": len(atom._orders) - len(atom._retired_at),
               "awaiting_prune": len(atom._retired_at),
               "retired_stages": len(atom._retired),
               "pruned": atom._pruned, "forgotten": atom._forgotten,
               "regression_blocked": atom._regression_blocked,
               "resurrected": atom._resurrected,
               "restore_error": atom._restore_error}
    idle = (None if atom._identity_dropped_mono is None
            else time.monotonic() - atom._identity_dropped_mono)
    details["identity_dropped_idle_s"] = None if idle is None else round(idle, 1)
    if atom._restore_error:
        return HealthStatus(state=HealthState.DEGRADED,
                            message=atom._restore_error, details=details)
    if idle is not None and idle <= _IDENTITY_ALERT_WINDOW_S:
        return HealthStatus(
            state=HealthState.DEGRADED,
            message="MISSING_EXECUTION_IDENTITY | dropped=%d منذ %ds | %s"
                    % (atom._identity_dropped, int(idle),
                       " ".join("%s=%d" % row for row in
                                sorted(atom._identity_dropped_by.items(),
                                       key=lambda item: -item[1])[:4])
                       or "مصدر غير مسمّى"),
            details=details)
    if atom._seen == 0 and not atom._orders:
        return HealthStatus(state=HealthState.HEALTHY,
                            message="READY_AWAITING_FIRST_FINAL_DECISION_OR_ORDER | finalized=0 queued=0",
                            details=details)
    message = "finalized=%d queued=%d ack=%d fills=%d" % (
        atom._counts["decision_finalized"], atom._counts["queued_to_bridge"],
        atom._counts["broker_acknowledged"],
        atom._counts["filled_open"] + atom._counts["filled_partial"]
        + atom._counts["filled_closed"])
    # الوسيطُ المحمول يُعلَن: عددٌ يصعد يعني أنّ حمولات الجسر ما زالت
    # بلا وسيط وأنّ الحملَ يعمل. و`مجهول` يصعد يعني أمرًا لم يُعرَف
    # وسيطُه قطُّ — وذاك عطبُ هويّةٍ حقيقيّ لا يُداوى بالحمل.
    carried = getattr(atom, "_broker_carried", 0)
    unknown = getattr(atom, "_broker_unknown", 0)
    if carried or unknown:
        message += " · وسيط[محمول=%d مجهول=%d]" % (carried, unknown)
    # العدد التراكميّ يبقى مرئيًّا بعد أن تهدأ الشارة — الحاضر يحكم
    # اللون، والتاريخ لا يُمحى من الرسالة.
    if atom._identity_dropped:
        message += " · dropped=%d" % atom._identity_dropped
    # ٢٠٢٦-٠٩-١٧ — كم حدثًا أُنقذ بالتذكرة بعد أن كان يُسقط لغياب الطلب.
    # وهو الحقل الذي يشهد بنفاذ هذا الإصلاح: رقم الإصدار يُبنى من
    # المانيفست لا من `ATOM_VERSION`.
    if getattr(atom, "_keyed_by_ticket", 0):
        message += " · بالتذكرة=%d" % atom._keyed_by_ticket
    # ٢٠٢٦-٠٩-١٨ (ختم NQ) — أمر المالك: «أظهر كل ما هو مهمّ ومخفيّ».
    # هذه الذرّة تجمع مصير كل أمر، وكانت الرسالة تقول «كم نجح» ولا
    # تقول **لماذا فشل**. وأسبابُ الرفض والتخطّي هي أوّل ما يُسأل عنه
    # حين لا تُفتح صفقة: مقيسًا اليوم `UPSTREAM_REJECTED: 1875` وحده
    # في `skip_reasons`، ولم يكن يبلغ اللوحة.
    top_rej = sorted(atom._reject_reasons.items(), key=lambda kv: -kv[1])[:3]
    top_skip = sorted(atom._skip_reasons.items(), key=lambda kv: -kv[1])[:3]
    if top_rej:
        message += " · رفض: " + " ".join("%s=%d" % kv for kv in top_rej)
    if top_skip:
        message += " · تخطٍّ: " + " ".join("%s=%d" % kv for kv in top_skip)
    failed = atom._counts.get("bridge_write_failed", 0) + \
        atom._counts.get("broker_command_failed", 0)
    if failed:
        message += " · فشل_إرسال=%d" % failed
    return HealthStatus(state=HealthState.HEALTHY, message=message, details=details)
