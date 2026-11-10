# -*- coding: utf-8 -*-
"""§5 / Gate A — يجمّد الشريط ويثبت أمانة الإطار عليه.

    raw tape ⟶ encode ⟶ binary frames ⟶ decode ⟶ reconstructed tape
    reconstructed == original   على العدّ والترتيب والهويّة والحمولة

وأيّ اختلافٍ يوقف §5 (ورقة المالك §١٢). ولا يُسقَط صفٌّ مخالفٌ ثمّ تُحسب
النسبة على الباقي (§٢٢).

    python tools/frame_gate.py <شريط.jsonl> [--freeze] [--batch 512]
"""
from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from hot import frame  # noqa: E402

FROZEN = ROOT / "forex_runtime" / "var" / "parity" / "frozen"


def read_tape(path: str) -> tuple[list[tuple[int, str, dict]], list[list[int]]]:
    """يقرأ الشريط **بترتيب الملفّ** ويكشف حدود التشغيلات.

    ⛔ لا يفرز. الفرزُ كان يخلط تشغيلتين في مجرًى واحدٍ يبدو سليمًا:
    أرشفةُ الشريط والنواةُ تعمل تجعل إغلاقَها النظيف يكتب آخر دفعةٍ في
    ملفٍّ جديدٍ بالاسم نفسه، فيبدأ الملفّ بذيل التشغيلة السابقة. المقيس
    ٢٠٢٦-٠٩-١٨: مقطعان `[58591…58623]` ثمّ `[0…27835]`. والفرز يخفيه
    «فجوةً واحدة»، والرفض يسمّيه.
    """
    rows: list[tuple[int, str, dict]] = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            payload = row.get("payload")
            if isinstance(payload, dict) and row.get("name"):
                rows.append((int(row["i"]), str(row["name"]), payload))
    runs: list[list[int]] = []
    previous = None
    for index, _name, _payload in rows:
        if previous is None or index != previous + 1:
            runs.append([index, index])
        else:
            runs[-1][1] = index
        previous = index
    return rows, runs


def freeze(path: str, rows: list) -> dict:
    """ينسخ الشريط إلى مسارٍ لا يُكتَب عليه، ويسجّل بصمته وعدّه."""
    FROZEN.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    target = FROZEN / ("tape-%s.jsonl" % stamp)
    target.write_bytes(Path(path).read_bytes())
    manifest = {
        "frozen_at": stamp,
        "source": str(path),
        "file": target.name,
        "sha256": digest.hexdigest(),
        "bytes": target.stat().st_size,
        "records": len(rows),
        "first_i": rows[0][0] if rows else None,
        "last_i": rows[-1][0] if rows else None,
        "names": sorted({name for _i, name, _p in rows}),
    }
    (FROZEN / ("tape-%s.json" % stamp)).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = {a for a in sys.argv[1:] if a.startswith("--")}
    if not args:
        print(__doc__)
        return 2
    size = 512
    for flag in list(flags):
        if flag.startswith("--batch"):
            flags.discard(flag)
    for i, a in enumerate(sys.argv):
        if a == "--batch" and i + 1 < len(sys.argv):
            size = int(sys.argv[i + 1])

    tape_path = args[0]
    rows, runs = read_tape(tape_path)
    if not rows:
        print("⛔ شريطٌ فارغ")
        return 1
    print("الشريط: %d واقعة · %d اسمًا · i من %d إلى %d"
          % (len(rows), len({n for _i, n, _p in rows}), rows[0][0], rows[-1][0]))

    # ── اتّصال التسلسل بترتيب **الملفّ** لا بعد فرزٍ يُخفي الحدود ──────────
    print("مقاطع متّصلة = %d  %s"
          % (len(runs), runs[:3] if len(runs) <= 3 else runs[:3] + [["…"]]))
    if len(runs) != 1:
        print()
        print("⛔ الشريط يحمل أكثر من تشغيلة — لا يُجمَّد ولا يُقاس عليه.")
        print("   السبب المعروف: أرشفةُ الشريط والنواةُ تعمل، فيكتب إغلاقُها")
        print("   النظيف آخرَ دفعةٍ في ملفٍّ جديدٍ بالاسم نفسه.")
        print("   العلاج: أوقف النواة **ثمّ** أرشف.")
        return 1
    print()

    # ── الترميز والفكّ ───────────────────────────────────────────────────
    t0 = time.perf_counter()
    blobs = [frame.encode(chunk) for chunk in frame.batches(rows, max_records=size)]
    enc_s = time.perf_counter() - t0
    total_bytes = sum(len(b) for b in blobs)

    t0 = time.perf_counter()
    rebuilt: list = []
    for blob in blobs:
        _header, decoded = frame.decode(blob)
        rebuilt.extend(decoded)
    dec_s = time.perf_counter() - t0

    raw_bytes = Path(tape_path).stat().st_size
    print("دفعات = %d (حدّ %d واقعة)" % (len(blobs), size))
    print("حجم: خام %.1f م.ب ⟵ إطارات %.1f م.ب  (%.1f%%)"
          % (raw_bytes / 1e6, total_bytes / 1e6, 100.0 * total_bytes / raw_bytes))
    print("ترميز %.3f ث (%.2f ميكرو/واقعة) · فكّ %.3f ث (%.2f ميكرو/واقعة)"
          % (enc_s, 1e6 * enc_s / len(rows), dec_s, 1e6 * dec_s / len(rows)))

    report = frame.identical(rows, rebuilt)
    print()
    print("=== Gate A — أمانة الإطار ===")
    for key in ("left", "right", "count_match", "order_mismatch",
                "identity_mismatch", "payload_mismatch"):
        print("  %-20s %s" % (key, report[key]))
    if report["first_mismatch"]:
        print("  أوّل اختلاف: %s" % report["first_mismatch"])
    print("\nالحكم: %s" % ("✅ أمانةٌ تامّة — reconstructed == original"
                           if report["identical"] else
                           "⛔ الإطار غيّر المدخل — §5 يقف"))

    if "--freeze" in flags and report["identical"] and len(runs) == 1:
        manifest = freeze(tape_path, rows)
        print("\nالشريط مجمَّد: %s" % manifest["file"])
        print("  sha256 = %s" % manifest["sha256"])
        print("  وقائع = %d · بايت = %d" % (manifest["records"], manifest["bytes"]))
    return 0 if report["identical"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
