# -*- coding: utf-8 -*-
"""الحركة المتوقّعة وقانون الوقت الكافي — خطّة المالك ١٠-١٧ (الخطوتان 24 و25؛ ختم «NQ»).

قانون المالك: «باقي على خبر 40 دقيقة — هل هو على قياس حركةٍ متوقّعة … ممكن تضرب أهداف 3؟ يفتح. إذا لا … ما في داعي يفتح
صفقة إذا بدها تنقصّ بالخطّ الأحمر وتُغلق» — «والشيء نفسه على خطّ العاشرة: نعم يُطبَّق».

الجدول مقيسٌ على سنين البناء (2014-07 ⟵ 2020) ومفحوصٌ على سنين الاختبار (2021 ⟵ 2025-09) — `expected_move_table.json` بجانب
هذا الملفّ، يكتبه قياس المرحلة 4 (المحاولة 2): لكلّ نصف ساعة من جلسة نيويورك ولكلّ أفق (دقائق): وسيط أقصى حركةٍ صاعدة وأقصى
حركةٍ هابطة **نسبةً إلى وسيط مدى الجلسات الخمس السابقة** — لأنّ البِب المطلق لا يثبت بين حقبتين بسعرين مختلفين (المحاولة 1). وتُحوَّل
إلى بِب بمدى الأيّام الخمسة الحاليّ (من ذرّة المستويات 124). «تكفي» = مسافة الهدف بالبِب ≤ الحركة المتوقّعة في جهة الصفقة خلال
الوقت الباقي حتّى أقرب خطٍّ أحمر.
أصلٌ بلا جدول (لم يُقَس بعد) ⟸ لا حكم (`None`) ويُعدّ — القانون لا يُطبَّق على ما لم يُقَس.

**٢٥/١٠ (ختم المالك «nq»، القانون 21): لا يقرؤها الحيّ ولا أداة القياس بعد اليوم.** سقط «الوقت يكفي» كلّه، وصار القانون «لا صفقة جديدة في
الساعة الأخيرة من نافذة الأصل» (shared/red_lines.in_last_hour). بقيت الوحدة وجدولها للتاريخ.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    from zoneinfo import ZoneInfo
except ImportError:  # noqa: BLE001
    ZoneInfo = None

TABLE_PATH = Path(__file__).with_name("expected_move_table.json")
NEW_YORK = "America/New_York"
SLOT_MIN = 30
_CACHE: dict[str, Any] = {}


def table() -> dict[str, Any]:
    if "table" not in _CACHE:
        try:
            _CACHE["table"] = json.loads(TABLE_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            _CACHE["table"] = {}
    return _CACHE["table"]


def reachable(symbol: Any, epoch_s: float, side: str, target_pips: float, seconds_left: float | None,
              ref_pips: float | None = None) -> tuple[bool | None, dict[str, Any]]:
    """(هل يتّسع الوقت؟ · التفصيل). None = لا حكم (لا جدول للأصل، أو لا وقت معروف، أو لا قاعدة مناطق)."""
    sym = str(symbol or "").upper()
    entry = table().get("symbols", {}).get(sym)
    if not entry or seconds_left is None or ZoneInfo is None or not ref_pips:
        return None, {"reason": "NO_TABLE" if not entry else "NO_TIME" if seconds_left is None else "NO_REF"}
    minutes_left = seconds_left / 60.0
    horizons = sorted(int(h) for h in entry.get("horizons", []))
    usable = [h for h in horizons if h <= minutes_left]
    detail: dict[str, Any] = {"minutes_left": round(minutes_left, 1), "target_pips": round(target_pips, 1)}
    if not usable:
        return False, {**detail, "reason": "LESS_THAN_SHORTEST_HORIZON", "shortest_min": horizons[0] if horizons else None}
    local = datetime.fromtimestamp(epoch_s, ZoneInfo(NEW_YORK))
    minute = local.hour * 60 + local.minute
    slot_min = minute - minute % SLOT_MIN
    slot = "%02d:%02d" % (slot_min // 60, slot_min % 60)
    cell = entry.get("slots", {}).get(slot, {}).get(str(usable[-1]))
    if not cell:
        return None, {**detail, "reason": "NO_CELL", "slot": slot, "horizon_min": usable[-1]}
    ratio = cell.get("up" if str(side).lower() == "buy" else "down")
    if ratio is None:
        return None, {**detail, "reason": "NO_CELL", "slot": slot}
    move = ratio * ref_pips
    return target_pips <= move, {**detail, "slot": slot, "horizon_min": usable[-1], "expected_pips": round(move, 1),
                                 "ratio": ratio, "ref_pips": round(ref_pips, 1), "percentile": table().get("percentile")}
