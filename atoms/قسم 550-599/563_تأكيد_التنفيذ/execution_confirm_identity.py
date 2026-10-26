"""٥٦٣ — هويّة القرار على حدث النتيجة: من حمولة الوسيط أوّلًا ثمّ من سجلّ الطلب الدائم.

v3.4.2 (٢٠٢٦-١٠-٠١، ختم `Nq`): نُقلت من `atom.py` **حرفيًّا** كي ينزل تحت حدّ
المادة 9 (٤٠٠ سطر فعليّ). `_decision_identity` كان تابعًا في صنف الذرّة، والفرقُ
الوحيد أنّ `self` صار `atom` — والتابعُ باسمه باقٍ في `atom.py` يُحيل إلى هنا.
والثوابتُ الثلاثة نُقلت معه بتعليقاتها كما هي، و`atom.py` يستوردها بأسمائها.
لا سلوك جديد، ولا اسمُ حقلٍ ولا إنذارٌ تغيّر.
"""
from __future__ import annotations

from typing import Any

# NQ seal, item 22, package T (T1): broker events cannot carry the decision
# identity (the external bridge never sees those fields as columns), so it is
# rejoined HERE from the durable request ledger this atom already keeps -- the
# remembered trading.final_decision payload, safe across any reboot. Absent
# values pass as None and are declared, never invented.
IDENTITY_FIELDS = ("decision_id", "gate_request_id")
WARNING_IDENTITY = "identity_incomplete"
# ٢٠٢٦-٠٩-١٨ — قياسٌ من هذا الصندوق نفسه (٤٥٢ حدث وسيط · ٢٥٣ سجلّ طلب):
# `market.outcome.realized` خرج ٢٤٢ مرّةً و**صفرٌ** منها يحمل هويّة قرار،
# فوقفت سلسلة التعلّم ٣٦٢–٣٦٨ عند صفر أسابيع. والسببان مقيسان ومنفصلان:
#
#   (أ) الوسيط يعلن `request_id` في حدث الفتح وحده — ٢١٠/٢١٠ — ولا يعلنه
#       في الإغلاق ولا الجزئيّ (٠ من ١٩٨ و٠ من ٤٤)، بينما `ticket` يعبر في
#       ٤٥٢/٤٥٢. فالبحث في الدفتر بـ`request_id` وحده يُخفق في كل نتيجة.
#       والجسر إعلانٌ لا اشتقاق: الوسيط نفسه قرن التذكرة بالطلب عند الفتح.
#   (ب) اسمٌ ثانٍ للحقل نفسه: مسار ٥٥٥ يكتب `decision_id` (١٦٩/١٦٩ سليمة)
#       ومحرّك ٥٨١ الاتّجاهيّ يكتبها `parent_decision_id` (٨٢/٨٢ ناقصة).
#       وهو نمط ٢٠٢٦-٠٩-٠٩ عينه: `decision_side` مقابل `side`.
#
# والأثر مقيس على تاريخ هذا الصندوق: الجسر وحده ١٦١/٢٤٢ (٦٦٫٥٪)، ومعه
# قبولُ الاسم الثاني ٢٣٦/٢٤٢ (٩٧٫٥٪). ولا قيمة تُخترع: الغياب يبقى معلنًا.
IDENTITY_ALIASES = {"decision_id": ("decision_id", "parent_decision_id")}


def decision_identity(atom, requested: dict[str, Any] | None,
                       payload: dict[str, Any]) -> dict[str, Any]:
    """T1: the identity pair for a result event -- the broker payload first
    (future-proof), then the durably remembered request. Missing values
    pass as None and are declared."""
    source = (requested or {}).get("payload")
    source = source if isinstance(source, dict) else {}
    body: dict[str, Any] = {}
    missing = []
    for field in IDENTITY_FIELDS:
        value = None
        for name in IDENTITY_ALIASES.get(field, (field,)):
            value = payload.get(name) or source.get(name)
            if value:
                if name != field:
                    atom._identity_by_alias += 1
                break
        body[field] = value
        if not value:
            missing.append(field)
    if missing:
        atom._identity_incomplete += 1
        body["identity_missing"] = missing
        body["identity_warnings"] = [WARNING_IDENTITY]
    return body
