# -*- coding: utf-8 -*-
"""تدقيق ملكية الصفقة — سطر كامل لكل أمر فتح، وأربع قواعد تُفحص.

حكم المالك ٢٠٢٦-٠٩-٠٦: «ما نعتبر أول صفقة سليمة فقط لأنها خرجت؛ أول
صفقة لازم نعمل عليها تدقيق ملكية كامل».

القواعد الأربع:
    ١. `setup_owner` من المالكين المعتمدين (406 أو 410).
    ٢. الإبطال صادر من المالك نفسه — لا من طبقة لاحقة.
    ٣. الهدف صادر من المالك نفسه.
    ٤. 581 و551 و584 و577 لم يغيّروا أصل الفكرة.

المصدر: صفّ الأمر في جسر الدماغ — هوية الفكرة تعبر داخل `params_json`
(601 · IDENTITY_FIELDS)، فيمكن إعادة بناء أيّ صفقة من صفّها وحده.

    vendor\\python\\runtime\\python.exe tools\\تدقيق_ملكية_الصفقة.py [--عدد 5]
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import time
from pathlib import Path

OWNERS = ("406", "410")
BRIDGE = Path(os.environ.get("APPDATA", "")) / \
    "MetaQuotes/Terminal/Common/Files/nq_brain.db"

# الحقول التي يطلبها المالك في السطر، بترتيبها.
LINE_FIELDS = (
    "setup_id", "setup_owner", "setup_type", "symbol", "side", "entry_reference",
    "analysis_invalidation", "invalidation_reason",
    "analysis_target", "target_reason",
    "decision_id", "gate_request_id",
    "execution_stop", "execution_target",
    "strength", "confidence", "cycle_id",
)


def _params(raw) -> dict:
    try:
        value = json.loads(raw or "{}")
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _num(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def audit(row: dict) -> list[str]:
    """يعيد قائمة المخالفات — فارغة تعني ملكية سليمة من المالك للتنفيذ."""
    broken = []
    owner = str(row.get("setup_owner") or "")
    if owner not in OWNERS:
        broken.append(f"القاعدة ١: المالك {owner!r} ليس من {OWNERS}")
    if not str(row.get("setup_id") or "").strip():
        broken.append("القاعدة ١: بلا هوية فكرة — أمر عارٍ")

    # ٢ و٣: مصدر الإبطال والهدف يحمل رقم المالك نفسه.
    for what, source_key in (("الإبطال", "invalidation_source"),
                             ("الهدف", "target_source")):
        source = str(row.get(source_key) or "")
        if not source:
            broken.append(f"القاعدة {'٢' if 'إبطال' in what else '٣'}: "
                          f"{what} بلا مصدر")
        elif owner and not source.startswith(owner + ":"):
            broken.append(f"القاعدة {'٢' if 'إبطال' in what else '٣'}: "
                          f"{what} مصدره {source!r} لا المالك {owner}")

    # ٤: الوقف المرسل مشتقّ من إبطال المالك، والهدف المرسل هو هدفه.
    invalidation = _num(row.get("analysis_invalidation"))
    target = _num(row.get("analysis_target"))
    sent_stop = _num(row.get("stop_loss"))
    sent_target = _num(row.get("take_profit"))
    if invalidation is None or target is None:
        broken.append("القاعدة ٤: الفكرة بلا إبطال أو هدف في الصفّ")
    else:
        side = str(row.get("side") or "").upper()
        if sent_stop is not None:
            # الوقف المرسل يجوز أن يُزاح **للخارج** (تكاليف وحدّ الوسيط)
            # ولا يجوز أن يقترب من السعر أكثر من الإبطال — فذلك تبديل فكرة.
            outward = (sent_stop <= invalidation) if side == "BUY" \
                else (sent_stop >= invalidation)
            if not outward:
                broken.append(
                    f"القاعدة ٤: الوقف المرسل {sent_stop} أضيق من إبطال "
                    f"المالك {invalidation} — طبقة لاحقة بدّلت الفكرة")
        if sent_target is not None and abs(sent_target - target) > 1e-6:
            broken.append(
                f"القاعدة ٤: الهدف المرسل {sent_target} ≠ هدف المالك {target}")
    return broken


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--عدد", type=int, default=5, dest="count")
    args = parser.parse_args()
    if not BRIDGE.is_file():
        print(f"لا جسر: {BRIDGE}")
        return 1
    conn = sqlite3.connect(f"file:{BRIDGE.as_posix()}?mode=ro", uri=True, timeout=8)
    rows = list(conn.execute(
        "SELECT id,request_id,symbol,side,volume,price,stop_loss,take_profit,"
        "ticket,params_json,status,result,created_at FROM commands "
        "WHERE action='OPEN' ORDER BY id DESC LIMIT ?", (args.count,)))
    conn.close()
    if not rows:
        print("لا أوامر فتح بعد.")
        return 0
    keys = ("id", "request_id", "symbol", "side", "volume", "price", "stop_loss",
            "take_profit", "ticket", "params_json", "status", "result", "created_at")
    clean = broken_total = 0
    for raw in rows:
        row = dict(zip(keys, raw))
        row.update(_params(row.pop("params_json")))
        row.setdefault("entry_reference", row.get("price"))
        row.setdefault("execution_stop", row.get("stop_loss"))
        row.setdefault("execution_target", row.get("take_profit"))
        stamp = time.strftime("%Y-%m-%d %H:%M:%S",
                              time.localtime(row.get("created_at") or 0))
        print("=" * 68)
        print(f"أمر id={row['id']}  تذكرة={row.get('ticket')}  {stamp}  "
              f"{row.get('status')}/{row.get('result')}")
        for field in LINE_FIELDS:
            print(f"  {field:24} = {row.get(field)}")
        problems = audit(row)
        if problems:
            broken_total += 1
            print("  ── مخالفات الملكية ──")
            for item in problems:
                print(f"     ✗ {item}")
        else:
            clean += 1
            print("  ✅ ملكية سليمة: المالك أنشأ الفكرة، وإبطالها وهدفها منه، "
                  "ولم تبدّلهما طبقة لاحقة.")
    print("=" * 68)
    print(f"سليمة={clean}  مخالِفة={broken_total}  من {len(rows)}")
    return 0 if broken_total == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
