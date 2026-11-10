# -*- coding: utf-8 -*-
"""عدّادات سلسلة الفتح — أين تنقطع الصفقة بالضبط.

حكم المالك ٢٠٢٦-٠٩-٠٦: «ساعتين بلا صفقة… لازم نثبت وين عم تنقطع
السلسلة… بدي هالأرقام، مو كلام عام».

    406 / 410 → SETUP_CREATED → SETUP_VALID → قرار الغرفة → exposure>0
    → 581 target_net → 551 → 584 → OPEN

القراءة:
    APPROVED > 0 و target_net = 0   ⇒ العطل في تحويل الإعداد إلى تعرّض
    target_net > 0 و 551 = 0        ⇒ العطل بين 581 ومسار البناء
    551 > 0 و 584 يرفض              ⇒ العطل في الشرعية/التنفيذ
    الكل يصل 584 و OPEN = 0         ⇒ التنفيذ نفسه هو المانع

    vendor\\python\\runtime\\python.exe tools\\عدادات_سلسلة_الفتح.py [--سجل PATH]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import time
from pathlib import Path

BRIDGE = Path(os.environ.get("APPDATA", "")) / \
    "MetaQuotes/Terminal/Common/Files/nq_brain.db"

# كل عدّاد ونمطه في السجل — ما لا نمط له يُعلَن «غير مقيس» لا يُخمَّن.
PATTERNS = (
    ("SETUP_CREATED_OK", re.compile(r"(4\d\d) إعداد \w+ \w+: دخول")),
    ("SETUP_REJECTED", re.compile(r"4\d\d إعداد مرفوض \S+: (\w+)")),
    ("581_NO_DIRECTION", re.compile(r"581 لا اتجاه \S+: (\w+)")),
    ("581_SKIP", re.compile(r"581 (?:skip|لا صفقة) \S+(?: \w+)?: (\w+)")),
    ("581_BLOCKED", re.compile(r"581 blocked \S+: status='(\w+)' reason='(\w+)'")),
    ("581_FLAT", re.compile(r"581 flat \S+: .*reason='([^']+)'")),
    ("581_ORDER", re.compile(r"581 order requested side=(\w+)")),
    ("551_BUILT", re.compile(r"551 direct \S+ (\w+): volume")),
    ("551_SKIP", re.compile(r"551 direct \S+ \w+: (sizing unavailable)")),
    ("584_ADJUSTED", re.compile(r"584 EXECUTION_STOP_ADJUSTED")),
    ("KILL", re.compile(r"516 KILL SWITCH")),
)


def scan(path: Path) -> dict[str, dict[str, int]]:
    counts: dict[str, dict[str, int]] = {}
    if not path.is_file():
        return counts
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            row = json.loads(line)
        except (TypeError, ValueError):
            continue
        message = str(row.get("message") or "")
        for name, pattern in PATTERNS:
            found = pattern.search(message)
            if not found:
                continue
            detail = found.group(found.lastindex or 0) if found.groups() else "-"
            bucket = counts.setdefault(name, {})
            bucket[detail] = bucket.get(detail, 0) + 1
    return counts


def bridge_counts(since: float) -> dict[str, int]:
    if not BRIDGE.is_file():
        return {}
    conn = sqlite3.connect(f"file:{BRIDGE.as_posix()}?mode=ro", uri=True, timeout=8)
    out = {}
    for label, sql in (
        ("bridge_OPEN_rows", "SELECT COUNT(*) FROM commands WHERE action='OPEN' AND created_at>?"),
        ("bridge_OPEN_done", "SELECT COUNT(*) FROM commands WHERE action='OPEN' AND created_at>? AND status='DONE'"),
        ("bridge_OPEN_failed", "SELECT COUNT(*) FROM commands WHERE action='OPEN' AND created_at>? AND result IS NOT NULL AND result<>'OK'"),
    ):
        out[label] = list(conn.execute(sql, (since,)))[0][0]
    conn.close()
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--سجل", dest="log", default="", help="مسار سجل التشغيل")
    parser.add_argument("--ساعات", dest="hours", type=float, default=2.0)
    args = parser.parse_args()
    logs = [Path(args.log)] if args.log else sorted(
        Path(os.environ.get("TEMP", ".")).parent.rglob("forex_run*.log"))
    logs = [p for p in logs if p.is_file()]
    if not logs:
        print("لا سجلّ تشغيل — مرّر --سجل PATH")
        return 1
    newest = max(logs, key=lambda p: p.stat().st_mtime)
    counts = scan(newest)
    print(f"السجل: {newest.name}  (آخر كتابة "
          f"{time.strftime('%H:%M:%S', time.localtime(newest.stat().st_mtime))})")
    print("=" * 62)
    for name, _ in PATTERNS:
        bucket = counts.get(name)
        if not bucket:
            print(f"  {name:20} = 0")
            continue
        total = sum(bucket.values())
        detail = " · ".join(f"{k}:{v}" for k, v in
                            sorted(bucket.items(), key=lambda x: -x[1])[:5])
        print(f"  {name:20} = {total:<5} [{detail}]")
    print("=" * 62)
    for key, value in bridge_counts(time.time() - args.hours * 3600.0).items():
        print(f"  {key:20} = {value}")
    # الحكم الآلي على نقطة الانقطاع — بالقاعدة التي وضعها المالك.
    orders = sum(counts.get("581_ORDER", {}).values())
    built = sum(counts.get("551_BUILT", {}).values())
    created = sum(counts.get("SETUP_CREATED_OK", {}).values())
    print("=" * 62)
    if created == 0:
        print("  ⇒ الانقطاع عند المالكين: لا إعداد صالح يُنشَر أصلًا.")
    elif orders == 0:
        print("  ⇒ الانقطاع بين الإعداد والتعرّض: إعدادات تُنشَر ولا أمر يُطلب.")
    elif built == 0:
        print("  ⇒ الانقطاع بين 581 و551: أوامر تُطلب ولا تُبنى.")
    else:
        print("  ⇒ السلسلة تصل البناء؛ افحص الشرعية والتنفيذ.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
