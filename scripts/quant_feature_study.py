"""بحثٌ عن محلّلٍ كمّيّ له حافّة — قبل أن يُكتب سطرٌ من كوده.

أمر المالك ٢٠٢٦-٠٩-١٨: «جيب محلّلين كمّيّ»، بعد أن قِيس أنّ استراتيجيّات
القسم بلا إشارة (اختراق المدى: نسبةٌ وسيطة ‎1.00‎، و**لا واحدة** من خمس
خصائص سعريّة تفصل الرابح عن الخاسر في ٧٩٥ اختراقًا).

⛔ ولا SMC هنا بحكمٍ صريح: لا كنس ولا فجوات ولا كتل أوامر ولا BOS/CHoCH.
الخصائص كلّها **كمّيّة خالصة** تُشتقّ من سلسلة الأسعار نفسها.

**الطريقة — كلُّ درسٍ دُفع ثمنه اليوم مطبَّقٌ فيها:**
  · **الطرفان لا الوسط:** لكلّ خاصّة تُقاس عوائدُ الرُبع الأعلى ناقص الرُبع
    الأدنى (`long-short`). فالخاصّة تُحاكَم على قدرتها على **الفصل** لا على
    متوسّطٍ يبتلع طرفيها.
  · **ضبطُ الانحراف:** يُطرح انحراف السوق مضروبًا في ميل الإشارة، وإلّا
    سُمّيت الموجةُ حافّة (بتكوين ارتفع ٢٧١٬٢٣٥ نقطة في عيّنةٍ واحدة).
  · **التكرار قبل الحجم:** أربع نوافذ منفصلة. عيّنةُ ٢٥٬٠٩١ إشارة سقطت أمس
    لأنّها نافذةٌ واحدة، وعيّنةُ ٨٥٥ صمدت. لا حكم دون ثلاثٍ من أربع.
  · **والحدّ هو السبريد:** فارقٌ لا يغطّي تكلفة العبور ليس حافّة.
"""
from __future__ import annotations

import argparse
import collections
import math
import sqlite3
import statistics as st
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "forex_runtime" / "var" / "store" / "market_data.db"
PIP = {"XAUUSD": 1e-2, "BTCUSD": 1e-2, "USTEC": 1e-2, "US30": 1e-2,
       "EURUSD": 1e-4, "GBPUSD": 1e-4}
#: ⛔ كانت (200, 1000) ثابتةً — وهذا خطأ الأفق نفسه الذي أسقط عتبة ٤٠٩ ثمّ
#: أُعيدت: الإشارة تحتاج ~٢٥ دقيقة لتُعبّر (نافذة ٤٠٥ المقيسة ٣٠٠٠ تِكّة،
#: وقياس قسم البنية ١٥٠٠ث حافّة ٤/٤ وخمس دقائق صفر). فالأفق **مُعامِل**.
HORIZONS = (200, 1000)


def prices(symbol: str, limit: int, offset: int) -> tuple[list[float], float]:
    connection = sqlite3.connect("file:%s?mode=ro" % DB.as_posix(), uri=True, timeout=10)
    try:
        rows = connection.execute(
            "SELECT bid,ask FROM market_data WHERE symbol=? ORDER BY rowid DESC "
            "LIMIT ? OFFSET ?", (symbol, limit, offset)).fetchall()
    finally:
        connection.close()
    rows.reverse()
    mid = [(b + a) / 2.0 for b, a in rows if b and a]
    spreads = [a - b for b, a in rows if a and b and a > b]
    return mid, (st.median(spreads) if spreads else 0.0)


def _mean(rows: list[float]) -> float:
    return sum(rows) / len(rows) if rows else 0.0


def build(series: list[float], step: int) -> dict[str, list[tuple[int, float]]]:
    """خصائصُ كمّيّة عند كلّ نقطة عيّنة — قيمةٌ موقّعة، موجبها يعني «اشترِ»."""
    out: dict[str, list[tuple[int, float]]] = collections.defaultdict(list)
    n = len(series)
    diffs = [series[k] - series[k - 1] for k in range(1, n)]
    for i in range(1200, n - max(HORIZONS), step):
        short = series[i - 60:i]
        long = series[i - 600:i]
        d_short = diffs[i - 60:i]
        d_long = diffs[i - 600:i]
        sd_long = st.pstdev(long) or 1e-12

        # ١) الانحراف المعياريّ عن المتوسّط — إشارةُ ارتداد (عكسُ البُعد).
        out["ارتداد_درجة_زد"].append((i, -(series[i] - _mean(long)) / sd_long))

        # ٢) الزخم: عائد المئتي تِكّة الأخيرة معيَّرًا بتقلّبه.
        out["زخم_200"].append((i, (series[i] - series[i - 200]) / sd_long))

        # ٣) الارتباط الذاتيّ للخطوات (lag 1) — استمرارٌ أم انعكاس.
        pos = sum(1 for k in range(1, len(d_short)) if d_short[k] * d_short[k - 1] > 0)
        neg = sum(1 for k in range(1, len(d_short)) if d_short[k] * d_short[k - 1] < 0)
        persist = (pos - neg) / max(1, pos + neg)
        out["استمرار_الخطوة"].append((i, persist * (1.0 if series[i] > _mean(short) else -1.0)))

        # ٤) نسبةُ التباين (١٠ مقابل ١): >1 استمرار · <1 ارتداد.
        var1 = st.pvariance(d_long) if len(d_long) > 2 else 0.0
        agg = [series[k] - series[k - 10] for k in range(i - 600 + 10, i, 10)]
        var10 = st.pvariance(agg) / 10.0 if len(agg) > 2 else 0.0
        vr = (var10 / var1) if var1 > 0 else 1.0
        out["نسبة_التباين"].append((i, (vr - 1.0) * (1.0 if series[i] > _mean(short) else -1.0)))

        # ٥) نظام التقلّب: تقلّب قصير إلى طويل.
        sd_short = st.pstdev(short) or 1e-12
        out["نظام_التقلّب"].append((i, math.log(sd_short / sd_long)
                                   * (1.0 if series[i] > _mean(short) else -1.0)))

        # ٦) التواءُ توزيع الخطوات — أيّ الجهتين ذيلُها أثقل.
        m = _mean(d_long)
        sd = st.pstdev(d_long) or 1e-12
        skew = _mean([((x - m) / sd) ** 3 for x in d_long])
        out["التواء_الخطوات"].append((i, skew))
    return out


def evaluate(series: list[float], rows: list[tuple[int, float]], pip: float,
             horizon: int) -> tuple[float, float, float]:
    """عائدُ الرُبع الأعلى ناقص الأدنى، بعد ضبط الانحراف — بالنقاط."""
    values = sorted(v for _, v in rows)
    if len(values) < 200:
        return (0.0, 0.0, 0.0)
    lo_cut, hi_cut = values[len(values) // 4], values[3 * len(values) // 4]
    steps = [(series[i + horizon] - series[i]) / pip
             for i in range(0, len(series) - horizon, 10)]
    drift = _mean(steps)
    drift_se = (st.pstdev(steps) / (len(steps) ** 0.5)) if len(steps) > 2 else 0.0

    def side(group: list[tuple[int, float]], sign: float) -> list[float]:
        return [((series[i + horizon] - series[i]) / pip) * sign
                for i, _ in group if i + horizon < len(series)]

    top = side([r for r in rows if r[1] >= hi_cut], 1.0)
    bottom = side([r for r in rows if r[1] <= lo_cut], -1.0)
    both = top + bottom
    if len(both) < 100:
        return (0.0, 0.0, 0.0)
    mean = _mean(both)
    se = st.pstdev(both) / (len(both) ** 0.5)
    bias = (len(top) - len(bottom)) / len(both)
    adjusted = mean - drift * bias
    joint = (se ** 2 + (drift_se * abs(bias)) ** 2) ** 0.5
    return (adjusted, joint, float(len(both)))


def main() -> None:
    parser = argparse.ArgumentParser(description="بحثٌ عن خاصّة كمّيّة لها حافّة")
    parser.add_argument("--symbols", nargs="*", default=["BTCUSD"])
    parser.add_argument("--limit", type=int, default=60000)
    parser.add_argument("--windows", type=int, default=4)
    parser.add_argument("--step", type=int, default=25)
    parser.add_argument("--horizons", default="",
                        help="آفاق مفصولةً بفاصلة؛ الافتراضي 200,1000")
    args = parser.parse_args()
    if args.horizons:
        global HORIZONS
        HORIZONS = tuple(int(x) for x in args.horizons.split(",") if x.strip())
    for symbol in args.symbols:
        symbol = symbol.upper()
        pip = PIP.get(symbol, 1e-2)
        score: dict[tuple[str, int], list[tuple[float, float]]] = collections.defaultdict(list)
        spread_pips = 0.0
        for k in range(args.windows):
            series, spread = prices(symbol, args.limit, k * args.limit)
            if len(series) < args.limit // 2:
                continue
            spread_pips = spread / pip
            table = build(series, args.step)
            for name, rows in table.items():
                for horizon in HORIZONS:
                    adjusted, se, n = evaluate(series, rows, pip, horizon)
                    if n:
                        score[(name, horizon)].append((adjusted, se))
            print("  %s إزاحة %d ✓" % (symbol, k * args.limit))
        print("\n=== %s · سبريد %.1f نقطة · %d نوافذ ==="
              % (symbol, spread_pips, args.windows))
        print("  %-18s %5s %10s %10s %8s %s"
              % ("الخاصّة", "أفق", "وسيط الفرق", "أدنى نافذة", "تغطّي", "الحكم"))
        need = max(2, (args.windows * 2 + 2) // 3)
        for (name, horizon), rows in sorted(score.items()):
            if len(rows) < args.windows:
                continue
            lowers = [a - 2.0 * s for a, s in rows]
            wins = sum(1 for low in lowers if low > spread_pips)
            ruling = ("حافّة — %d/%d" % (wins, len(rows))) if wins >= need else "لا"
            print("  %-18s %5d %10.2f %10.2f %7d/%d %s"
                  % (name, horizon, st.median(a for a, _ in rows),
                     min(lowers), wins, len(rows), ruling))


if __name__ == "__main__":
    main()
