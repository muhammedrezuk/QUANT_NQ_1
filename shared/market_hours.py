"""ساعات السوق من الوسيط نفسه — مفتوحٌ · مغلقٌ · مجهول.

🔴 ٢٠٢٦-٠٩-٢٦ (ختم المالك «Nq») — «سستم عندك ما يعرف أيّ يوم عايش فيه… ما بيعرف
سوق مغلق».

كلّ عطلة أسبوع يُغلق اليورو والجنيه والذهب وداو وإس‌آند‌بي وناسداك، ولا يتداول
إلّا البتكوين. والمنصّة لا تعرف ذلك: تغذية سي‑تريدر تعلن الرموز الستّة «خارج
الجلسة» عطلًا، ولقطة التنفيذ تعلن سعرها «بائتًا»، والاستخراج يطرق مركزًا في
سوقٍ مغلق فيردّه الوسيط. والجواب عند الوسيط منذ البداية ولم يُطلب.

الإكسبرت (v3.17) يكتب الآن مع مواصفات كلّ رمز ثلاثة حقول كما يعطيها ميتاتريدر،
بلا حسابٍ ولا تفسير:

    trade_sessions     جلسات التداول لكلّ يوم (`SymbolInfoSessionTrade`) بتوقيت
                       الخادم، ثوانٍ من منتصف الليل:
                       {"SUNDAY": [[s, e], ...], "MONDAY": [...], ...}
    server_gmt_offset  فرق ساعة الخادم عن غرينتش بالثواني (مقيسٌ 10800 صيفًا).
    trade_mode         وضع التداول نصًّا (`SYMBOL_TRADE_MODE_*`).

ولا يُخترع هنا شيء: رمزٌ بلا هذه الحقول — إكسبرتٌ لم يُجمَّع بعد، أو صفٌّ ناقص —
«مجهول»، والمجهول يُعامَل مفتوحًا كما كان كلّ شيءٍ قبلها. فلا يُحجب رمزٌ بظنّ،
ولا يُعلن سوقٌ مغلقًا إلّا بكلام الوسيط.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any

OPEN = "OPEN"
CLOSED = "CLOSED"
UNKNOWN = "UNKNOWN"

#: أسماء الأيّام كما يكتبها الإكسبرت (`EnumToString(ENUM_DAY_OF_WEEK)`)، بترتيب
#: `datetime.weekday()` في بايثون (الاثنين صفر) — فلا يتوقّف شيءٌ على أرقام
#: التعداد في ميتاتريدر.
_DAYS = ("MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY")
_DAY_SECONDS = 86400
_DISABLED = "SYMBOL_TRADE_MODE_DISABLED"


def _int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


@lru_cache(maxsize=64)
def _parse(raw: str) -> tuple[tuple[tuple[int, int], ...], ...] | None:
    """نصّ الجلسات ⟵ سبعة أيّام بترتيب `_DAYS`، أو `None` إن نقص يومٌ أو فسد رقم."""
    try:
        body = json.loads(raw)
    except (TypeError, ValueError):
        return None
    if not isinstance(body, dict):
        return None
    days = []
    for name in _DAYS:
        spans = body.get(name)
        if not isinstance(spans, list):
            return None
        pairs = []
        for span in spans:
            if not isinstance(span, (list, tuple)) or len(span) != 2:
                return None
            start, end = _int(span[0]), _int(span[1])
            if (start is None or end is None or not 0 <= start <= _DAY_SECONDS
                    or not 0 <= end <= _DAY_SECONDS):
                return None
            pairs.append((start, end))
        days.append(tuple(pairs))
    return tuple(days)


def market_state(spec: Any, now_utc: float) -> str:
    """حالة سوق الرمز الآن بجلسات الوسيط: `OPEN` أو `CLOSED` أو `UNKNOWN`."""
    if not isinstance(spec, dict):
        return UNKNOWN
    if str(spec.get("trade_mode") or "").strip().upper() == _DISABLED:
        return CLOSED
    raw = spec.get("trade_sessions")
    if isinstance(raw, dict):
        raw = json.dumps(raw, sort_keys=True)
    offset = _int(spec.get("server_gmt_offset"))
    if not isinstance(raw, str) or not raw or offset is None:
        return UNKNOWN
    days = _parse(raw)
    if days is None:
        return UNKNOWN
    try:
        server = datetime.fromtimestamp(float(now_utc) + offset, timezone.utc)
    except (TypeError, ValueError, OverflowError, OSError):
        return UNKNOWN
    second = server.hour * 3600 + server.minute * 60 + server.second
    for start, end in days[server.weekday()]:
        if start <= end:
            if start <= second < end:
                return OPEN
        elif second >= start or second < end:
            # نهايةٌ قبل البداية تُقرأ جلسةً تعبر منتصف الليل — لا إغلاقًا.
            return OPEN
    return CLOSED
