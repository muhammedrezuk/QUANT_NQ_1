# -*- coding: utf-8 -*-
"""صفقات المالك اليدويّة — التمييز الواحد (ختم المالك «NQ» ٢٠٢٦-١٠-٢٦).

قال المالك: «صفقات انا بفتحها مالها علاقة بل منظومة ابدا ولا بصير يقيس عليها ولا يسجلها ولا يحسبها ولا بصير تدخل سستم
ابدا بل نسبة لا خسارة وربح يسجل على انه خسار وربح مالك على لوحة وبل منطومة NQ».

**صفقة المالك:** كلّ مركزٍ يحمل رقم سحرٍ **معروفًا** غير سحر المنظومة (صفقته اليدويّة سحرها 0 عند الوسيط).
وما لا يحمل رقم سحرٍ أصلًا (حقلٌ غائب أو فارغ أو لا يُقرأ رقمًا) لا يُعدّ للمالك، كما كانت ٥٦٥ و٥٠٩ و٥٧٧ تعدّه: الخبير يكتب
السحر لكلّ مركز (`positions_v2.magic`، `mt5/QUANT_NQ.mq5`)، فغيابه صورةٌ ناقصة لا صفقةُ مالك، ولا يُترك مركزٌ للمنظومة بلا
وقفٍ ولا إغلاقٍ بسبب حقلٍ ناقص. وحارس الملكيّة عند ٥٧٥ والخبير يردّ كلّ أمرٍ على مركزٍ ليس للمنظومة في الحالين.

**أين يدخل المالك المنظومة:** من صورة المراكز وحدها (`platform.positions.state` من ٦٠٩). أمّا أحداث الصفقات
(`platform.trade_event` من ٦١١) فالخبير لا يكتب إغلاقًا ولا إغلاقًا جزئيًّا إلّا لسحر المنظومة (`QUANT_NQ.mq5:2207` و`:1997`)،
ولا فتحًا إلّا لأوامرها. فكلّ عدّادٍ يُبنى من أحداث الصفقات نظيفٌ من صفقات المالك من مصدره.

هذه الدالّة هي التمييز الوحيد. كلّ ذرّةٍ تميّز صفقة المالك تستعملها، ولا تمييز ثانٍ في ذرّة.
"""
from __future__ import annotations

from typing import Any, Iterable

#: سحر المنظومة — كما في بيانات ٥٠٩ و٥٥١ و٥٦٥ و٥٧٠ و٥٧٥ و٦٠١ (`magic` في إعداد الذرّة يعلوه إن وُجد).
SYSTEM_MAGIC = 20260801
MAGIC_FIELD = "magic"


def magic_of(row_or_magic: Any) -> int | None:
    """رقم السحر المعروف في صفّ مركزٍ أو في القيمة نفسها، أو `None` إن غاب أو لم يُقرأ رقمًا."""
    value = row_or_magic.get(MAGIC_FIELD) if isinstance(row_or_magic, dict) else row_or_magic
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, str) and not value.strip():
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number or number in (float("inf"), float("-inf")):
        return None
    return int(number)


def is_owner(row_or_magic: Any, system_magic: Any = SYSTEM_MAGIC) -> bool:
    """صفقة المالك: رقم سحرٍ معروف غير سحر المنظومة."""
    magic = magic_of(row_or_magic)
    return magic is not None and magic != int(system_magic)


def is_system(row_or_magic: Any, system_magic: Any = SYSTEM_MAGIC) -> bool:
    """ما ليس صفقة المالك فهو للمنظومة — ومعه الصفّ بلا سحرٍ معروف."""
    return not is_owner(row_or_magic, system_magic)


def system_rows(rows: Iterable[Any], system_magic: Any = SYSTEM_MAGIC) -> list[Any]:
    """صفوف المراكز بلا صفقات المالك، بترتيبها. وما ليس قاموسًا يمرّ كما هو، ليحكم عليه قارئه كما كان."""
    return [row for row in rows if not (isinstance(row, dict) and is_owner(row, system_magic))]
