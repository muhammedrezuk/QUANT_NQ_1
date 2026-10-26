# -*- coding: utf-8 -*-
"""طابعُ حداثةِ ملفٍّ مخزَّنًا — `stat` مرّةً كلّ فترة، لا مع كلّ نداء.

## لماذا وُلد هذا الملفّ

المقيس ٢٠٢٦-٠٩-١٨ بمِرسمةٍ إحصائيّة على النواة الحيّة (١٩٬٥٩٥ عيّنة، منها
٣٩٫٣٪ خمولٌ في الحلقة):

    18.91٪ من العيّنات كلّها  =  ٣١٪ من زمن الحلقة المشغول   ⟵ `pathlib.stat`

ومصدرها ثلاثة نداءات `stat` تقع مع **كلّ** قراءة عيار:

    shared/strategy_contract.py  movement_scale   ⟵ ١٣ ذرّة استراتيجيّة × رمز × تِكّة
    shared/strategy_contract.py  edge_factor      ⟵ نفسها
    shared/trade_setup.py        _floor_frac      ⟵ على مسار القرار

الـ JSON نفسه كان مخزَّنًا بالـ`mtime` — **والـ`stat` وحده لم يكن مخزَّنًا**.
أي أنّ الذاكرة التي بُنيت لحماية المسار الساخن كانت تدفع نداء نظامِ ملفّاتٍ
لتسأل «هل تغيّر؟» قبل أن تردّ من ذاكرتها.

والنمط المعالِج موجودٌ في هذا المستودع مرّتين أصلًا:

    shared/parameter_registry.py   `_GATE_RECHECK_S = 2.0`
    shared/horizon_profile.py      `_OVR_RECHECK_S  = 2.0`

فهذا الملفّ يجمعهما في موضعٍ واحد كي لا يتفرّق النمط ثالثةً ورابعة.

## العقد

* **الفشل يُخزَّن كما يُخزَّن النجاح.** لو خُزّن النجاح وحده، لصار ملفٌّ
  يُحذف يُقرأ من ذاكرةٍ بائتة بلا حدّ. فتُعاد **نتيجة المحاولة** كما هي —
  `(ok, stamp)` — ويُعاد تقييمها بعد الفترة نفسها في الاتّجاهين.
* **الفترة سقفُ تأخّرٍ لا سقفُ صحّة.** تغيّرُ الملفّ يصل خلال `recheck_s`
  على الأكثر. وهذه الملفّات يكتبها اشتقاقٌ دوريّ (أوزان الحافّة، مقياس
  الحركة، أرضيّة السبريد) لا تِكّة، فتأخّرُ ثانيتين غيرُ مرئيّ.
* **لا قفل.** إسنادُ الصفّ إلى مفتاح معجمٍ عمليّةٌ ذرّيّة تحت الـGIL، وأسوأ
  ما يقع عند التسابق نداءُ `stat` زائد — وهو ما نحاول تقليله أصلًا، لا منعه.
"""
from __future__ import annotations

import os
import time
from typing import Any

#: الفترة الافتراضيّة — نفس رقم `_GATE_RECHECK_S` و`_OVR_RECHECK_S`.
DEFAULT_RECHECK_S = 2.0

#: المسار ⟶ (لحظة الفحص الرتيبة، نجح؟، الطابع)
_stamps: dict[str, tuple[float, bool, float]] = {}

#: عدّادان للفحص لا للسلوك — يُقرآن في الاختبار وفي القياس.
calls = 0
syscalls = 0


def file_stamp(path: Any, *, recheck_s: float = DEFAULT_RECHECK_S) -> tuple[bool, float]:
    """`(هل وُجد الملفّ، طابع تعديله)` — من الذاكرة ما دامت الفترة لم تنقضِ.

    يعيد `(False, 0.0)` حين يتعذّر الوصول، تمامًا كما يرفع `stat` خطأه —
    فيتصرّف المستدعي كما كان يتصرّف عند `OSError` بلا تغيير.
    """
    global calls, syscalls
    calls += 1
    key = str(path)
    now = time.monotonic()
    cached = _stamps.get(key)
    if cached is not None and now - cached[0] < recheck_s:
        return cached[1], cached[2]
    syscalls += 1
    try:
        stamp = os.stat(key).st_mtime
        ok = True
    except OSError:
        stamp, ok = 0.0, False
    _stamps[key] = (now, ok, stamp)
    return ok, stamp


def forget(path: Any = None) -> None:
    """ينسى المخزَّن — للاختبار، ولمن كتب الملفّ للتوّ وأراد قراءته فورًا."""
    if path is None:
        _stamps.clear()
    else:
        _stamps.pop(str(path), None)


def stats() -> dict[str, int]:
    """كم نداءً وكم نداءَ نظامٍ فعليًّا — يُقرأ ليُصدَّق التوفير."""
    return {"calls": calls, "syscalls": syscalls,
            "saved": calls - syscalls, "tracked": len(_stamps)}
