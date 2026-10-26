"""صافي الصفقة بأجزائها — حسابٌ خالص يشترك فيه دفتر البطاقات (465) ومحاسبة الصفقات (469).

٢٠٢٦-١٠-٠٩ (ختم المالك «NQ» — الصفقة صافيةً بأجزائها): «نحن نشتغل نجمع R — كم R خسرنا مقابل كم ربحنا
صافي، ثلث، نصّ وهيك… R عنّا 100 دولار» و«لازم ينحسب: إذا ضرب الهدف الأوّل ورجع ضرب الدخول، أو هدف ثاني
ثمّ ضرب التأمين على الهدف الأوّل — يعني إغلاق صفقة على صافي كم R ربح».

الصفقة تذكرةٌ واحدة عند الوسيط، وأجزاؤها كلُّ إغلاقٍ جزئيّ (`PARTIAL`) والإغلاقُ الأخير (`CLOSED`).
صافيها مجموعُ (الربح + العمولة + المبادلة + الرسوم) على أجزائها كلّها، و R = الصافي ÷ مبلغ المخاطرة الذي
كتبه 552 على البطاقة. وكان دفتر البطاقات يُغلق البطاقة عند أوّل جزء فيسجّل ثلث العقد وحده: البطاقة 86470
قالت +0.33R والوسيط قال +2.20R.

لا قرص هنا ولا ناقل — كلّ ذرّةٍ تقرأ مصدرها (465 أحداث 563، و469 سجلّ الوسيط) وتنادي هذه الدوال، فلا
يفترق تعريفان لصافي صفقةٍ واحدة ولا لاسم مرحلتها.
"""
from __future__ import annotations

import math
from typing import Any, Iterable

EVENT_PARTIAL = "PARTIAL"
EVENT_CLOSED = "CLOSED"
COSTS = ("commission", "swap", "fee")
#: سببٌ استعاده الإكسبرت بعد انقطاع (`SL_RECOVERED` · `TP_RECOVERED`) هو السبب نفسه.
RECOVERED_SUFFIX = "_RECOVERED"
REASON_TP, REASON_SL, REASON_MANUAL, REASON_SYSTEM = "TP", "SL", "MANUAL", "SYSTEM"
#: ربع مسافة الوقف الأصليّ حول سعر الدخول = «تعادل». مقيسٌ ٢٠٢٦-١٠-٠٩ على سجلّ الوسيط: خروجُ الوقف بعد
#: الهدف الأوّل (83 صفقة) وقع بين −0.23 و+0.21 من مسافة الوقف إلّا سبعًا (إزاحةُ العمولة والانزلاق)، وخروجُ
#: الوقف بلا جزءٍ قبله (342) تكتّل حول −1. وصفٌ لموضع الخروج لا حكم، والرقم نفسه يُعلَن معه.
BREAKEVEN_BAND_R = 0.25
#: إغلاقُ النظام عند ما لا يقلّ عن هذا من مسافة الهدف المرسَل = «على الهدف» (الهدف الثالث في خطّة 574).
TARGET_REACHED_FRAC = 0.95
#: تقريب مفتاح الجزء — نسقُ 517 (`_leg_key`) نفسه، فصفٌّ مكرَّر بقيمه كلّها مفتاحٌ واحد.
KEY_DP = 8
#: سنتٌ واحد: ما دونه من الصافي تعادلٌ ماليّ لا ربحٌ ولا خسارة.
CENT = 0.005

STAGE_FIRST, STAGE_SECOND, STAGE_PARTIAL = "first_target", "second_target", "partial"
EXIT_TARGET, EXIT_PROTECTIVE, EXIT_BREAKEVEN = "target", "protective_stop", "breakeven"
EXIT_ORIGINAL, EXIT_STOP, EXIT_MANUAL = "original_stop", "stop", "manual"
EXIT_SYSTEM, EXIT_OTHER = "system", "other"
STAGE_AR = {
    STAGE_FIRST: "الهدف الأوّل", STAGE_SECOND: "الهدف الثاني", STAGE_PARTIAL: "إغلاقٌ جزئيّ",
    EXIT_TARGET: "خروج على الهدف", EXIT_PROTECTIVE: "على وقف التأمين", EXIT_BREAKEVEN: "على التعادل",
    EXIT_ORIGINAL: "على الوقف الأصليّ", EXIT_STOP: "على الوقف (موضعه غير معروف)",
    EXIT_MANUAL: "إغلاقٌ يدويّ", EXIT_SYSTEM: "إغلاق النظام", EXIT_OTHER: "خروجٌ آخر"}
RESULT_WIN, RESULT_LOSS, RESULT_EVEN = "WIN", "LOSS", "BREAKEVEN"


def number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def make_leg(event_type: Any, volume: Any, price: Any, profit: Any, commission: Any = None,
             swap: Any = None, fee: Any = None, reason: Any = None, at: Any = None,
             entry: Any = None, seq: int = 0) -> dict[str, Any]:
    """جزءٌ واحد بأرقامه — `event` فارغٌ يُعدّ إغلاقًا أخيرًا (عقدُ 465 القديم: نتيجةٌ بلا نوعٍ تُغلق)."""
    leg = {"event": text(event_type).upper() or EVENT_CLOSED, "volume": number(volume),
           "price": number(price), "profit": number(profit), "commission": number(commission),
           "swap": number(swap), "fee": number(fee), "reason": text(reason).upper(),
           "at": number(at), "entry": number(entry), "seq": int(seq)}
    leg["net"] = leg_net(leg)
    return leg


def leg_net(leg: dict[str, Any]) -> float:
    """ربحُ الجزء ومعه تكاليفه — والمجهول منها صفرٌ معلَن (`costs_known` في المجموع)."""
    return round(sum(number(leg.get(name)) or 0.0 for name in ("profit", *COSTS)), KEY_DP)


def leg_key(leg: dict[str, Any]) -> str:
    """هويّة الجزء بمحتواه: النوع · الحجم · سعر الخروج · الربح (لا التكاليف — مراجعتُها تقع على المفتاح نفسه)."""
    parts = [text(leg.get("event")).upper() or EVENT_CLOSED]
    for name in ("volume", "price", "profit"):
        value = number(leg.get(name))
        parts.append("?" if value is None else repr(round(value, KEY_DP)))
    return "|".join(parts)


def merge_leg(legs: list[dict[str, Any]], leg: dict[str, Any]) -> bool:
    """يضيف الجزء، أو يراجع تكاليفَ جزءٍ وصل قبلُ بقيمه نفسها — صفٌّ مكرَّر لا يُعدّ مرّتين.

    مقيس: الإكسبرت كتب أربعة أجزاءٍ جزئيّة مرّتين بقيمها كلّها (517 قاسه ٠٩-٢٤؛ وفي السجلّ الحيّ ٠٩-١٠ أربعة)،
    ويحدّث عمولة الصفّ بعد كتابته، و563 يعيد نشر الجزء إذا رُوجعت تكاليفه. فالتكلفة المعروفة الأحدث تغلب (المفتاح
    بلا تكاليف، وعلى 606 أجزاء لم يتطابق جزءان مختلفان في المفتاح قطّ — 517). يُرجع `True` إن تغيّر المال.
    """
    key = leg_key(leg)
    for old in legs:
        if leg_key(old) != key:
            continue
        revised = False
        for name in COSTS:
            if leg.get(name) is not None and leg.get(name) != old.get(name):
                old[name] = leg[name]
                revised = True
        if revised:
            old["net"] = leg_net(old)
        return revised
    legs.append(leg)
    return True


def ordered(legs: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(legs, key=lambda leg: (number(leg.get("at")) or 0.0, int(leg.get("seq") or 0)))


def exit_stage(reason: Any, move_r: float | None, target_frac: float | None) -> str:
    """اسم الخروج من سبب الوسيط وموضعه: الوقف يُسمّى بموضعه من الدخول (بوحدة مسافة الوقف الأصليّ)."""
    base = text(reason).upper()
    if base.endswith(RECOVERED_SUFFIX):
        base = base[:-len(RECOVERED_SUFFIX)]
    if base == REASON_TP:
        return EXIT_TARGET
    if base == REASON_SL:
        if move_r is None:
            return EXIT_STOP
        if move_r >= BREAKEVEN_BAND_R:
            return EXIT_PROTECTIVE
        return EXIT_ORIGINAL if move_r <= -BREAKEVEN_BAND_R else EXIT_BREAKEVEN
    if base == REASON_MANUAL:
        return EXIT_MANUAL
    if base == REASON_SYSTEM:
        reached = target_frac is not None and target_frac >= TARGET_REACHED_FRAC
        return EXIT_TARGET if reached else EXIT_SYSTEM
    return EXIT_OTHER


def label_legs(legs: list[dict[str, Any]], side: Any, entry: Any, stop: Any, target: Any,
               risk: Any = None) -> list[dict[str, Any]]:
    """يسمّي كلّ جزءٍ بمرحلته ويقيس موضعه — ويُرجع الأجزاء مرتّبةً بوقتها.

    الجزئيّ بترتيبه: الأوّل «الهدف الأوّل» والثاني «الهدف الثاني» (أثلاث المالك في 574)، وما بعدهما «إغلاقٌ
    جزئيّ». والإغلاق بسببه (`exit_stage`). والموضع `move_r` = حركة الخروج من الدخول ÷ مسافة الوقف الأصليّ؛
    وبلا وقفٍ معروف يُقاس بالمال: (ربح الجزء ÷ المخاطرة) × (حجم العقد ÷ حجم الجزء).
    """
    sign = {"BUY": 1.0, "SELL": -1.0}.get(text(side).upper())
    entry, stop, target, risk = number(entry), number(stop), number(target), number(risk)
    rows = ordered(legs)
    total_volume = sum(number(leg.get("volume")) or 0.0 for leg in rows)
    partials = 0
    for leg in rows:
        start = number(leg.get("entry")) or entry
        price = number(leg.get("price"))
        move = None if sign is None or start is None or price is None else sign * (price - start)
        unit = abs(start - stop) if start is not None and stop is not None and start != stop else None
        span = abs(target - start) if start is not None and target is not None and start != target else None
        leg["move_r"] = None if move is None or unit is None else round(move / unit, 4)
        volume, profit = number(leg.get("volume")), number(leg.get("profit"))
        if leg["move_r"] is None and risk and volume and profit is not None and total_volume:
            leg["move_r"] = round((profit / risk) * (total_volume / volume), 4)
        leg["target_frac"] = None if move is None or span is None else round(move / span, 4)
        if leg.get("event") == EVENT_PARTIAL:
            partials += 1
            leg["stage"] = {1: STAGE_FIRST, 2: STAGE_SECOND}.get(partials, STAGE_PARTIAL)
        else:
            leg["stage"] = exit_stage(leg.get("reason"), leg["move_r"], leg["target_frac"])
        leg["stage_ar"] = STAGE_AR[leg["stage"]]
        leg["r"] = None if not risk or risk <= 0 else round(leg_net(leg) / risk, 4)
    return rows


def result_of(net: float | None) -> str | None:
    if net is None:
        return None
    return RESULT_WIN if net > CENT else RESULT_LOSS if net < -CENT else RESULT_EVEN


def summarize(legs: list[dict[str, Any]], risk: Any = None) -> dict[str, Any]:
    """مجموع الصفقة: الربح · التكاليف · الصافي بالدولار وبـR · عدد الأجزاء · اسم الخروج الأخير."""
    rows = ordered(legs)
    gross = round(sum(number(leg.get("profit")) or 0.0 for leg in rows), 2)
    costs = round(sum(number(leg.get(name)) or 0.0 for leg in rows for name in COSTS), 2)
    net = round(sum(leg_net(leg) for leg in rows), 2)
    risk = number(risk)
    last = rows[-1] if rows else {}
    return {"gross_usd": gross, "costs_usd": costs, "net_usd": net,
            "risk_usd": risk if risk and risk > 0 else None,
            "net_r": round(net / risk, 4) if risk and risk > 0 else None,
            "legs": len(rows), "partials": sum(1 for leg in rows if leg.get("event") == EVENT_PARTIAL),
            "volume": round(sum(number(leg.get("volume")) or 0.0 for leg in rows), KEY_DP),
            "costs_known": all(leg.get(name) is not None for leg in rows for name in COSTS),
            "exit": last.get("stage"), "exit_ar": last.get("stage_ar"), "result": result_of(net)}


def leg_text(leg: dict[str, Any]) -> str:
    """«الهدف الأوّل: 0.4 @31013.2 ⟸ +30.72$ (+0.33R)» — سطر الجزء كما يُكتب على البطاقة ويُقرأ."""
    price = number(leg.get("price"))
    shown = "—" if price is None else ("%.5f" % price).rstrip("0").rstrip(".")
    r = number(leg.get("r"))
    return "%s: %s @%s ⟸ %+.2f$%s" % (
        leg.get("stage_ar") or leg.get("event") or "—", number(leg.get("volume")) or 0.0, shown,
        leg_net(leg), "" if r is None else " (%+.2fR)" % r)
