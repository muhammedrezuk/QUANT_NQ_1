# -*- coding: utf-8 -*-
"""عقود الهندسة الثلاثة — يدخل صح · يخسر صح · يربح صح.

حكم المالك ٢٠٢٦-٠٩-٠٦: «خلّي يدخل صح ويخسر صح ويربح صح لأروح أعاير جودة
دخول. بس هيك لسّه مو صحيح — كيف راح أعاير على هندسة غلط؟».

فالمعايرة لا تُبنى على هندسة لم تُثبت. هذه الأداة تحاكم كل صفقة منفَّذة
بثلاثة عقود قابلة للقياس، وتقول أيّها انكسر ومتى — لا رأي فيها ولا ظنّ.

    أ) يدخل صح — النسبة تُقاس على المسافة **المرسلة** (وقف التحليل +
       التكاليف) لا على وقف التحليل وحده. صفقة تمرّ بنسبة 1.7 تحليليًّا
       ويأخذها الحساب 1.19 ليست دخولًا صحيحًا.
    ب) يخسر صح — الخسارة الواقعة لا تتجاوز سقف المالك الصلب مهما انزلق
       التنفيذ.
    ج) يربح صح — الرابحة تُخرِج مثل مخاطرتها فأكثر (1R). رابحةٌ تقبض
       عُشر هدفها ليست ربحًا بل خنقًا للاتجاه.

التشغيل:
    vendor\\python\\runtime\\python.exe tools\\عقود_الهندسة.py [--عدد 40]
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import statistics
import time
from pathlib import Path

CAP = 100.0        # سقف المالك الصلب لكل صفقة (١٪ من قاعدة 10,000)
MIN_RR = 2.0       # الحدّ الأدنى للنسبة على المسافة المرسلة
MIN_WIN_R = 1.0    # الرابحة تُخرج مثل مخاطرتها فأكثر
BRIDGE = Path(os.environ.get("APPDATA", "")) / \
    "MetaQuotes/Terminal/Common/Files/nq_brain.db"


def _load(conn):
    """أوامر الفتح المعروفة، ثم الصفقات المغلقة المطابقة لها."""
    opens = {}
    for ticket, price, stop, target, volume in conn.execute(
            "SELECT ticket,price,stop_loss,take_profit,volume FROM commands "
            "WHERE action='OPEN' AND ticket IS NOT NULL AND stop_loss IS NOT NULL "
            "AND take_profit IS NOT NULL AND price IS NOT NULL"):
        opens[int(ticket)] = (float(price), float(stop), float(target),
                              float(volume or 0.0))
    trades, seen = [], set()
    for ticket, side, volume, entry, exit_price, profit, reason, closed in conn.execute(
            "SELECT ticket,side,volume,entry_price,exit_price,profit,reason,close_time "
            "FROM trade_events_v2 WHERE reason IS NOT NULL AND exit_price IS NOT NULL "
            "AND entry_price IS NOT NULL ORDER BY close_time"):
        ticket = int(ticket)
        if ticket in seen or ticket not in opens:
            continue
        seen.add(ticket)
        trades.append((ticket, str(side).upper(), float(volume), float(entry),
                       float(exit_price), float(profit or 0.0),
                       str(reason).upper(), closed))
    return opens, trades


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--عدد", type=int, default=24, dest="count",
                        help="كم صفقة أخيرة تُحاكَم")
    args = parser.parse_args()
    if not BRIDGE.is_file():
        print(f"لا جسر: {BRIDGE}")
        return 1
    conn = sqlite3.connect(f"file:{BRIDGE.as_posix()}?mode=ro", uri=True, timeout=8)
    opens, trades = _load(conn)
    conn.close()
    if not trades:
        print("لا صفقات مطابقة لأوامر معروفة")
        return 1

    batch = trades[-args.count:]
    broke_a, broke_b, broke_c = [], [], []
    wins, losses, win_r = [], [], []
    print(f"{'التذكرة':>11} {'الوقت':>8} {'ج':2} {'نسبة':>5} {'خطر':>7} "
          f"{'واقع':>8} {'R':>5}  أ ب ج")
    for ticket, side, volume, entry, exit_price, profit, reason, closed in batch:
        price, stop, target, _ = opens[ticket]
        gap, reach = abs(price - stop), abs(target - price)
        ratio = (reach / gap) if gap else 0.0
        planned = volume * gap
        realised_r = (profit / planned) if planned else 0.0
        stamp = time.strftime("%H:%M:%S", time.localtime(closed)) if closed else "?"

        a_ok = ratio >= MIN_RR
        b_ok = abs(profit) <= CAP
        if profit > 0:
            wins.append(profit)
            win_r.append(realised_r)
            c_ok = realised_r >= MIN_WIN_R
            c_mark = "✓" if c_ok else "✗"
            if not c_ok:
                broke_c.append((ticket, realised_r))
        else:
            losses.append(profit)
            c_mark = "·"
        if not a_ok:
            broke_a.append((ticket, ratio))
        if not b_ok:
            broke_b.append((ticket, profit))
        print(f"{ticket:>11} {stamp:>8} {side[:1]:2} {ratio:5.2f} {planned:7.1f} "
              f"{profit:+8.2f} {realised_r:+5.2f}  "
              f"{'✓' if a_ok else '✗'} {'✓' if b_ok else '✗'} {c_mark}")

    print(f"\n=== العقود على {len(batch)} صفقة ===")
    print(f"  أ) يدخل صح — نسبة ≥ {MIN_RR} على المسافة المرسلة")
    print(f"     كُسر {len(broke_a)} مرّة"
          + (f" — أدناها {min(r for _, r in broke_a):.2f}" if broke_a else " ✓"))
    print(f"  ب) يخسر صح — لا يتجاوز {CAP:.0f}$")
    print(f"     كُسر {len(broke_b)} مرّة"
          + (f" — أسوأها {min(p for _, p in broke_b):.2f}$" if broke_b else " ✓"))
    print(f"  ج) يربح صح — الرابحة تُخرج ≥ {MIN_WIN_R:.0f}R")
    print(f"     كُسر {len(broke_c)} من {len(wins)} رابحة"
          + (f" — وسيط نصيب الرابحة {statistics.median(win_r):.2f}R" if win_r else ""))
    if losses:
        print(f"     الخاسرة: ن={len(losses)} · وسيط {statistics.median(losses):.2f}$ "
              f"· أسوأ {min(losses):.2f}$")
    if wins and losses:
        net = sum(wins) + sum(losses)
        print(f"     الصافي على الدفعة: {net:+.2f}$ "
              f"({len(wins)} رابحة من {len(batch)})")
    return 0 if not (broke_a or broke_b or broke_c) else 2


if __name__ == "__main__":
    raise SystemExit(main())
