# -*- coding: utf-8 -*-
"""سجلّ الأخبار الحمراء من اليوم فصاعدًا — بلا تداول (ختم المالك «nq يسجّل» ٢٠٢٦-١٠-١٣).

لماذا: القياس التاريخيّ (النسخة الثانية) لم يجد أثرًا ثابتًا على 12 سنة، لكنّ الأخبار الكبيرة في 2025–2026 مشى الناسداك معها أبعد
عند مسافة 1٪ (حظّ 0.03 بين 32 محاولة — قد يكون صدفة). الاختبار الصادق: أخبارٌ لم يرها أحدٌ قبل القياس.

يعمل كلّ ليلة على الجهاز (مهمّة مجدولة)، ويعيد الحساب كلّه من البداية فلا يضيع شيء ولا يتكرّر:
- الأخبار: أحمر فوركس فاكتوري للدولار من جدول الجالب (`calendar_ff` في قاعدة الجسر) منذ START، بالمتوقّع والسابق.
- الفعليّ والسابق المعدَّل: تقويم ميتاتريدر (يتحدّث كلّ ساعة) بالاسم المقابل وفي الدقيقة نفسها ±5 د.
- الجهة: «مقابل المتوقّع» (الفعليّ − متوقّع فوركس فاكتوري) و«مقابل السابق» — إيجابيّ للدولار = سلبيّ للناسداك؛ البطالة معكوسة.
  الأخبار في الدقيقة نفسها تُجمع؛ «كبير» = |التغيّر مقابل السابق| ≥ انحرافه المعياريّ على 2014–2019 (كالنسخة الثانية).
- المشي من +15 د كالقياس التاريخيّ تمامًا (0.25٪ · 0.5٪ · 1٪ · البنية)، حتّى 10 أيّام؛ ما لم ينتهِ بعد يُكتب «جارٍ».
المخرج: «السجلّ.md» و records.json بجانبه. قياسٌ فقط: لا يمسّ الحيّ.
"""
import calendar
import importlib.util
import json
import os
import re
import sqlite3
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
# المهمّة المجدولة تشغّله بلا نافذة (pythonw): لا مخرج قياسيّ، فيُوجَّه إلى سجلّ التشغيل بجانبه.
if sys.stdout is None or sys.stderr is None:
    sys.stdout = sys.stderr = open(os.path.join(HERE, "run.log"), "a", encoding="utf-8")
sys.stdout.reconfigure(encoding="utf-8")
_spec = importlib.util.spec_from_file_location("nr2", os.path.join(HERE, "..", "news_red_v2_2026-10-13", "news_red2.py"))
nr2 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(nr2)
nr = nr2.nr
BRIDGE = "file:C:/Users/NQ/AppData/Roaming/MetaQuotes/Terminal/Common/Files/nq_brain.db?mode=ro"
START = calendar.timegm(time.strptime(os.environ.get("NEWS_FWD_START") or "2026-10-13", "%Y-%m-%d"))
MATCH_S = 5 * 60
LOAD_BEFORE = 5 * nr.DAY
FF_TO_MT5 = {
    "Non-Farm Employment Change": "قوائم الرواتب غير الزراعية", "Unemployment Rate": "معدل البطالة",
    "Average Hourly Earnings m/m": "متوسط الدخل بالساعة على أساس أساس شهري",
    "CPI m/m": "مؤشر اسعار المستهلك على أساس شهري", "CPI y/y": "مؤشر أسعار المستهلك على أساس سنوي",
    "Core CPI m/m": "مؤشر أسعار المستهلك الأساسي على أساس شهري",
    "PPI m/m": "مؤشر أسعار المنتجين على أساس شهري", "Core PPI m/m": "مؤشر أسعار المنتجين الأساسيين على أساس شهري",
    "Retail Sales m/m": "مبيعات التجزئة على أساس شهري", "Core Retail Sales m/m": "مبيعات التجزئة الأساسية على أساس شهري",
    "Core PCE Price Index m/m": "مؤشر سعر نفقات الاستهلاك الشخصي الأساسي على أساس شهري",
    "Advance GDP q/q": "الناتج الإجمالي المحلي على أساس ربع سنوي", "Prelim GDP q/q": "الناتج الإجمالي المحلي على أساس ربع سنوي",
    "Final GDP q/q": "الناتج الإجمالي المحلي على أساس ربع سنوي",
    "Federal Funds Rate": "قرار سعر فائدة بنك الإحتياطي الفيدرالي"}
INVERSE = {"Unemployment Rate"}


def num(text):
    m = re.search(r"-?\d+(?:\.\d+)?", str(text or ""))
    return float(m.group()) if m else None


def ff_events(now):
    con = sqlite3.connect(BRIDGE, uri=True)
    rows = con.execute("select title, scheduled_at, forecast, previous, written_at from calendar_ff where currency='USD' "
                       "and impact_level='HIGH' and scheduled_at >= ? and scheduled_at <= ? order by written_at",
                       (START, now)).fetchall()
    con.close()
    # الجالب يُبقي صفًّا واحدًا لكلّ خبرٍ ويعيد كتابته (وقت الكتابة غالبًا بعد الصدور)؛ ومتوقّع فوركس فاكتوري لا يتغيّر بعد الصدور.
    return {(title, float(at)): (num(fc), num(prev)) for title, at, fc, prev, _ in rows}


def mt5_lookup():
    con = sqlite3.connect(nr.CAL, uri=True)
    rows = con.execute("select event_name, time_server, actual, prev, revised_prev from calendar_history where currency='USD' "
                       "and time_server >= ?", (START + nr.CAL_OFFSET_S - nr.DAY,)).fetchall()
    con.close()
    out = {}
    for name, ts, act, prev, rprev in rows:
        out.setdefault(name.strip(), []).append((float(ts) - nr.CAL_OFFSET_S, act, rprev if rprev is not None else prev))
    return out


def scales():
    con = sqlite3.connect(nr.CAL, uri=True)
    d = {}
    for name, ts, act, prev, rprev in con.execute("select event_name, time_server, actual, prev, revised_prev from "
                                                  "calendar_history where currency='USD'"):
        ref = rprev if rprev is not None else prev
        if act is not None and ref is not None and ts - nr.CAL_OFFSET_S < nr2.LEARN_END:
            d.setdefault(name.strip(), []).append(act - ref)
    con.close()
    return {n: float(np.std(v)) for n, v in d.items() if len(v) >= 8}


def load_prices(t_from):
    con = sqlite3.connect(nr.HIST, uri=True)
    a = np.array(con.execute("select period_start, high, low, close from candles_history where symbol='USTEC' and "
                             "period='M1' and period_start >= ? order by period_start", (t_from,)).fetchall(), dtype=float)
    con.close()
    return a[:, 0], a[:, 1], a[:, 2], a[:, 3]


def main():
    now = time.time()
    ff = ff_events(now)
    mt5 = mt5_lookup()
    sc = scales()
    groups = {}
    for (title, at), (fc, prev_ff) in ff.items():
        g = groups.setdefault(at, {"items": [], "exp": [], "prev": [], "big": False, "speech": False})
        mt_name = FF_TO_MT5.get(title)
        if mt_name is None:
            g["speech"] = True
            g["items"].append({"الخبر": title})
            continue
        hit = min((x for x in mt5.get(mt_name, []) if abs(x[0] - at) <= MATCH_S), key=lambda x: abs(x[0] - at), default=None)
        act, ref = (hit[1], hit[2]) if hit else (None, prev_ff)
        sign = -1 if title in INVERSE else 1
        item = {"الخبر": title, "الفعليّ": act, "المتوقّع": fc, "السابق": ref}
        if act is not None and fc is not None and act != fc:
            g["exp"].append(-sign * (1 if act > fc else -1))
        if act is not None and ref is not None and act != ref:
            g["prev"].append(-sign * (1 if act > ref else -1))
            if sc.get(mt_name) and abs(act - ref) >= sc[mt_name]:
                g["big"] = True
        g["items"].append(item)
    records = []
    if groups:
        ts, hi, lo, cl = load_prices(min(groups) - LOAD_BEFORE)
        for at, g in sorted(groups.items()):
            rec = {"الوقت": time.strftime("%Y-%m-%d %H:%M غ", time.gmtime(at)), "الأخبار": g["items"], "كبير": g["big"]}
            i = nr.at_index(ts, at + nr.ENTRY_DELAY) if len(ts) else None
            if i is None or ts[i] + nr.MIN < at + nr.ENTRY_DELAY - nr.MIN or i + 2 >= len(ts):
                rec["الحال"] = "لم يحن الدخول أو لا أسعار"
                records.append(rec)
                continue
            done = (len(ts) - 1 - i) >= nr.HOLD_BARS
            for vname, votes in (("مقابل المتوقّع", g["exp"]), ("مقابل السابق", g["prev"])):
                net = sum(votes)
                d = 1 if net > 0 else -1 if net < 0 else (1 if g["speech"] and not votes else 0)
                if d == 0:
                    rec[vname] = "بلا جهة"
                    continue
                w = nr2.walks(hi, lo, cl, i, d)
                if w is None:
                    rec[vname] = "لا أسعار كافية"
                    continue
                rec[vname] = {"الجهة_للناسداك": ("صعود" if d > 0 else "هبوط") if votes else "بلا رقم (حجمٌ فقط)",
                              **{str(r): {"مع": round(w[r][0], 1), "ضدّ": round(w[r][1], 1)} for r in nr2.RS}}
            rec["الحال"] = "انتهى" if done else "جارٍ (أقلّ من 10 أيّام)"
            records.append(rec)
    json.dump(records, open(os.path.join(HERE, "records.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    report(records, now)
    print(time.strftime("%Y-%m-%d %H:%M غ", time.gmtime(now)), "سُجّل:", len(records), "مجموعة خبر منذ",
          time.strftime("%Y-%m-%d", time.gmtime(START)), flush=True)


def report(records, now):
    L = ["# سجلّ الأخبار الحمراء — من %s فصاعدًا (بلا تداول، ختم «nq يسجّل»)" % time.strftime("%Y-%m-%d", time.gmtime(START)), "",
         "آخر تحديث: %s (غرينتش). الأرقام بنقطة الأساس (100 = 1٪): أبعد مشيٍ مع جهة الخبر / ضدّها من +15 د قبل الانعكاس." % (
             time.strftime("%Y-%m-%d %H:%M", time.gmtime(now))), ""]
    for vname in ("مقابل المتوقّع", "مقابل السابق"):
        L += ["## المجموع — %s" % vname, "", "| المسافة | أخبار | متوسّط مع | متوسّط ضدّ | مع أبعد | الكبيرة: أخبار · مع − ضدّ |", "|---|---|---|---|---|---|"]
        for r in nr2.RS:
            rows = [x[vname][str(r)] | {"big": x["كبير"]} for x in records
                    if isinstance(x.get(vname), dict) and x[vname]["الجهة_للناسداك"] in ("صعود", "هبوط")]
            if not rows:
                L.append("| %s | 0 | — | — | — | — |" % r)
                continue
            w = np.array([x["مع"] for x in rows]); o = np.array([x["ضدّ"] for x in rows])
            big = [x["مع"] - x["ضدّ"] for x in rows if x["big"]]
            L.append("| %s | %d | %.1f | %.1f | %d من %d | %d · %s |" % (
                r, len(rows), w.mean(), o.mean(), int((w > o).sum()), len(rows), len(big),
                "%.1f" % np.mean(big) if big else "—"))
        L.append("")
    L += ["## الأخبار واحدًا واحدًا", ""]
    for x in reversed(records):
        names = " · ".join("%s (فعليّ %s · متوقّع %s · سابق %s)" % (i["الخبر"], i.get("الفعليّ"), i.get("المتوقّع"), i.get("السابق"))
                           if "الفعليّ" in i else i["الخبر"] for i in x["الأخبار"])
        L.append("- **%s** · %s · %s%s" % (x["الوقت"], x.get("الحال", ""), names, " · كبير" if x["كبير"] else ""))
        for vname in ("مقابل المتوقّع", "مقابل السابق"):
            v = x.get(vname)
            if isinstance(v, dict):
                L.append("  - %s: %s — %s" % (vname, v["الجهة_للناسداك"], " · ".join(
                    "%s: مع %s / ضدّ %s" % (r, v[str(r)]["مع"], v[str(r)]["ضدّ"]) for r in nr2.RS)))
            elif v:
                L.append("  - %s: %s" % (vname, v))
    open(os.path.join(HERE, "السجلّ.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")


if __name__ == "__main__":
    main()
