# -*- coding: utf-8 -*-
"""مفتاح الاستراتيجيّات الحيّة — أيّها يرسل قرارًا (ختم المالك «NQ» ١٧/١٠).

قوله: «حطّ توليفة كاملة تشتغل لايف مباشر على حساب تجريبي … وقّف كلّ شي بخصّ باقي الاستراتيجيّات … باقي الاستراتيجيّات وقّف
بطاقاتها وخلّي بس هي شغّالة». الملفّ `strategy_switch.json` بجانب هذا يسمّي الفعّال؛ والاستراتيجيّات 404–410 والبطاقة 414
والتوليفة 415 تسأل هنا قبل أن ترسل. يُقرأ الملفّ عند تغيّره وحده. وبلا ملفّ: كلّها تعمل كما كانت.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

#: جلسة الفحوص تأخذ مفتاحًا مؤقّتًا غائبًا (`conftest.py` في الجذر) — فلا يُوقف المفتاحُ الحيّ فحصَ استراتيجيّةٍ أُوقفت حيًّا.
PATH = Path(os.environ.get("NQ_STRATEGY_SWITCH") or Path(__file__).with_name("strategy_switch.json"))
_CACHE: dict[str, Any] = {"mtime": None, "active": None}


def active(strategy_id: Any) -> bool:
    try:
        mtime = PATH.stat().st_mtime
    except OSError:
        return True
    if _CACHE["mtime"] != mtime:
        try:
            data = json.loads(PATH.read_text(encoding="utf-8"))
            _CACHE["active"] = {str(x) for x in data.get("active", [])}
        except (OSError, ValueError):
            _CACHE["active"] = None
        _CACHE["mtime"] = mtime
    return _CACHE["active"] is None or str(strategy_id) in _CACHE["active"]