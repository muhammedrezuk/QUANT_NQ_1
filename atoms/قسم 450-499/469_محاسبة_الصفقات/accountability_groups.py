"""469 — حساب كلّ مجموعةٍ وكلّ عامل: العدد · الرابح · المجموع · المتوسّط · أقصى سحب.

٢٠٢٦-١٠-٠٨ (ختم المالك «NQ» — المعرفة أوّلًا): سؤال المالك «مين من المحلّلين أو البنية أو الإحصاء أو
الاستراتيجيّات أو السيولة عم يعطي قرارات خاسرة؟». فكلّ حقيقةٍ خُتمت على الصفقات المغلقة تُقسَم فئات:
الرقميّة أثلاثًا بحدودٍ من قيمها نفسها (منخفض/وسط/مرتفع)، والنصّيّة بقيمتها — ولكلّ فئة عددها ورابحها
ومتوسّط وحدة مخاطرتها. **وما دون الحدّ الأدنى من الصفقات في الفئة يُعلَم «عيّنة صغيرة» ولا يُرتَّب.**
والترتيب خامٌ للعلم: فرقُ متوسّط R بين أعلى فئةٍ وأدناها — رقمٌ لا حكم، ولا يدخل القرار.
"""

from __future__ import annotations

import math
from typing import Any, Callable, Iterable

from accountability_ledger import THIRDS, parse_fact

GROUP_LOW, GROUP_MID, GROUP_HIGH = "low", "mid", "high"
GROUP_OTHER = "_other"
KIND_NUMBER, KIND_TEXT = "number", "text"
#: سقف فئات الحقيقة النصّيّة — ما زاد يُجمع في `_other` (لا يُرمى).
MAX_TEXT_GROUPS = 12
#: سقف الحقائق المعروضة في الحمولة (الأكثر صفقاتٍ أوّلًا) — والباقي يُعدّ في `facts_not_listed`.
MAX_FACTS_LISTED = 400


def _won(trade: dict[str, Any]) -> bool:
    profit = trade.get("profit_usd")
    return profit is not None and profit > 0


def max_drawdown(values: Iterable[float]) -> float:
    """أقصى نزولٍ من قمّة المجموع التراكميّ إلى قاعه (يبدأ من صفر)."""
    total = peak = worst = 0.0
    for value in values:
        total += value
        peak = max(peak, total)
        worst = max(worst, peak - total)
    return worst


def stats(trades: list[dict[str, Any]], min_sample: int) -> dict[str, Any]:
    """العدد · الرابح · نسبته · المجموع والمتوسّط بالدولار وبوحدة المخاطرة · أقصى سحب — بترتيب الإغلاق.

    ٢٠٢٦-١٠-٠٩ (ختم المالك «NQ» — الصفقة صافيةً بأجزائها): «كم R خسرنا مقابل كم ربحنا صافي» — فيُعلَن مجموع R
    الرابحة (`won_r`) ومجموع R الخاسرة (`lost_r`، سالبًا) والصافي (`total_r`)، ومثلها بالدولار، وما لا R له
    (لا مبلغ مخاطرةٍ على بطاقته) يُعدّ بالدولار وحده (`n_without_r` · `usd_without_r`)."""
    ordered = sorted(trades, key=lambda t: (t.get("closed_at") or 0.0, t.get("card_no") or 0))
    profits = [t["profit_usd"] for t in ordered if t.get("profit_usd") is not None]
    units = [t["result_r"] for t in ordered if t.get("result_r") is not None]
    count = len(ordered)
    wins = sum(1 for t in ordered if _won(t))
    total_r = sum(units)
    bare = [t["profit_usd"] for t in ordered
            if t.get("result_r") is None and t.get("profit_usd") is not None]
    return {
        "n": count, "wins": wins,
        "win_rate_pct": round(100.0 * wins / count, 1) if count else None,
        "total_usd": round(sum(profits), 2),
        "won_usd": round(sum(p for p in profits if p > 0), 2),
        "lost_usd": round(sum(p for p in profits if p < 0), 2),
        "avg_usd": round(sum(profits) / len(profits), 2) if profits else None,
        "n_r": len(units), "total_r": round(total_r, 3),
        "won_r": round(sum(u for u in units if u > 0), 3),
        "lost_r": round(sum(u for u in units if u < 0), 3),
        "avg_r": round(total_r / len(units), 3) if units else None,
        "n_without_r": len(bare), "usd_without_r": round(sum(bare), 2),
        "max_drawdown_r": round(max_drawdown(units), 3),
        "max_drawdown_usd": round(max_drawdown(profits), 2),
        "small_sample": count < min_sample,
    }


def group_by(trades: list[dict[str, Any]], key: Callable[[dict[str, Any]], str],
             min_sample: int) -> dict[str, dict[str, Any]]:
    buckets: dict[str, list[dict[str, Any]]] = {}
    for trade in trades:
        buckets.setdefault(key(trade) or "?", []).append(trade)
    return {name: stats(rows, min_sample) for name, rows in sorted(buckets.items())}


OWNER_ZONE = "Europe/Istanbul"


def strategy_periods(trades: list[dict[str, Any]], min_sample: int, now: float) -> dict[str, Any]:
    """٢٠٢٦-١٠-١٧ (الخطوة 20): كلّ استراتيجيّة بأشهرها وأسابيعها، وأسبوعها الجاري ويومها — بتاريخ تركيا لوقت الإغلاق
    كما يسجّله دفتر البطاقات. بلا قاعدة المناطق يُؤخذ تاريخ غرينتش ويُعلَن."""
    from datetime import datetime, timezone
    try:
        from zoneinfo import ZoneInfo
        zone, zone_name = ZoneInfo(OWNER_ZONE), OWNER_ZONE
    except Exception:  # noqa: BLE001 -- no zone database: UTC dates, declared below
        zone, zone_name = timezone.utc, "UTC"
    closed = [t for t in trades if t.get("closed_at")]

    def day(trade: dict[str, Any]):
        return datetime.fromtimestamp(float(trade["closed_at"]), zone).date()

    today = datetime.fromtimestamp(now, zone).date()
    week_now = tuple(today.isocalendar())[:2]
    out: dict[str, Any] = {"date_zone": zone_name, "today": today.isoformat()}
    for strategy in sorted({t.get("strategy") or "?" for t in closed}):
        own = [t for t in closed if (t.get("strategy") or "?") == strategy]
        out[strategy] = {
            "by_month": group_by(own, lambda t: day(t).strftime("%Y-%m"), min_sample),
            "by_week": group_by(own, lambda t: "%d-W%02d" % tuple(day(t).isocalendar())[:2], min_sample),
            "this_week": stats([t for t in own if tuple(day(t).isocalendar())[:2] == week_now], min_sample),
            "today": stats([t for t in own if day(t) == today], min_sample)}
    return out


def tercile_bounds(values: list[float]) -> tuple[float, float]:
    """حدّا الأثلاث من القيم نفسها: الأوّل آخر قيمةٍ في الثلث الأدنى، والثاني آخرها في الثلث الأوسط."""
    ordered = sorted(values)
    count = len(ordered)
    first = ordered[max(0, math.ceil(count / THIRDS) - 1)]
    second = ordered[max(0, math.ceil(2 * count / THIRDS) - 1)]
    return first, second


def _tercile_of(value: float, bounds: tuple[float, float]) -> str:
    if value <= bounds[0]:
        return GROUP_LOW
    return GROUP_MID if value <= bounds[1] else GROUP_HIGH


def _fact_rows(trades: list[dict[str, Any]], facts: dict[int, dict[str, str]]
               ) -> tuple[dict[str, dict[str, Any]], int]:
    """حقيقة ⟵ {الاسم، [(صفقة، قيمة)]} من كلّ صفقةٍ تحمل حقائق ولادتها."""
    table: dict[str, dict[str, Any]] = {}
    withheld = 0
    for trade in trades:
        for author, raw in (facts.get(trade["card_no"]) or {}).items():
            label, pairs, hidden = parse_fact(raw)
            withheld += hidden
            for key, value in pairs:
                row = table.setdefault("%s.%s" % (author, key), {"label_ar": label, "rows": []})
                row["rows"].append((trade, value))
    return table, withheld


def _fact_entry(label: str, rows: list[tuple[dict[str, Any], Any]],
                min_sample: int) -> dict[str, Any]:
    numbers = [value for _, value in rows if isinstance(value, float)]
    entry: dict[str, Any] = {"label_ar": label, "n": len(rows)}
    buckets: dict[str, list[dict[str, Any]]] = {}
    if len(numbers) == len(rows):
        bounds = tercile_bounds(numbers)
        entry.update(kind=KIND_NUMBER, bounds=[bounds[0], bounds[1]])
        for trade, value in rows:
            buckets.setdefault(_tercile_of(value, bounds), []).append(trade)
        order = [name for name in (GROUP_LOW, GROUP_MID, GROUP_HIGH) if name in buckets]
    else:
        entry["kind"] = KIND_TEXT
        for trade, value in rows:
            buckets.setdefault(str(value), []).append(trade)
        order = sorted(buckets, key=lambda name: (-len(buckets[name]), name))
        if len(order) > MAX_TEXT_GROUPS:
            pooled = [t for name in order[MAX_TEXT_GROUPS:] for t in buckets.pop(name)]
            order = order[:MAX_TEXT_GROUPS] + [GROUP_OTHER]
            buckets[GROUP_OTHER] = pooled
    entry["groups"] = {}
    for name in order:
        full = stats(buckets[name], min_sample)
        # ٢٠٢٦-١٠-٠٩ (ختم المالك «NQ» — الصفقة صافيةً بأجزائها): ولكلّ فئة كم R ربحت وكم خسرت والصافي.
        entry["groups"][name] = {k: full[k] for k in (
            "n", "wins", "win_rate_pct", "n_r", "avg_r", "won_r", "lost_r", "total_r",
            "total_usd", "small_sample")}
    return entry


def fact_gap(name: str, entry: dict[str, Any]) -> dict[str, Any] | None:
    """فرقُ متوسّط R بين أعلى فئةٍ وأدناها — من الفئات التي بلغت العيّنة وحدها، وإلّا لا ترتيب."""
    ranked = [(group["avg_r"], key, group["n"]) for key, group in entry["groups"].items()
              if not group["small_sample"] and group["avg_r"] is not None]
    if len(ranked) < 2:
        return None
    ranked.sort()
    low, high = ranked[0], ranked[-1]
    return {"fact": name, "label_ar": entry["label_ar"], "avg_r_gap": round(high[0] - low[0], 3),
            "highest_avg_r_group": high[1], "highest_avg_r": high[0], "highest_n": high[2],
            "lowest_avg_r_group": low[1], "lowest_avg_r": low[0], "lowest_n": low[2],
            "n": entry["n"]}


def fact_table(trades: list[dict[str, Any]], facts: dict[int, dict[str, str]],
               min_sample: int, top: int) -> dict[str, Any]:
    """حساب كلّ عامل: الجدول، والترتيب الخام لأكبر الفروق، وما حُجب، وما لم يُعرض."""
    table, withheld = _fact_rows(trades, facts)
    names = sorted(table, key=lambda name: (-len(table[name]["rows"]), name))
    listed = names[:MAX_FACTS_LISTED]
    by_fact = {name: _fact_entry(table[name]["label_ar"], table[name]["rows"], min_sample)
               for name in listed}
    gaps = [gap for gap in (fact_gap(name, by_fact[name]) for name in listed) if gap]
    gaps.sort(key=lambda gap: (-gap["avg_r_gap"], gap["fact"]))
    return {"by_fact": by_fact, "fact_gaps": gaps[:top], "facts_ranked": len(gaps),
            "facts_withheld": withheld, "facts_listed": len(listed),
            "facts_not_listed": len(names) - len(listed)}
