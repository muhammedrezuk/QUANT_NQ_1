# -*- coding: utf-8 -*-
"""§5 / Gate B — حتميّة المرجع على الشريط المجمَّد (ختم `NQ — GATE B`).

## ما تُثبته

    الشريط المجمَّد (بصمةٌ مُتحقَّقة)
              ↓  encode مرّةً واحدة
        frame bytes  ← **نفسها حرفًا** للجانبين
              ↓                    ↓
          Replay A             Replay B
              ↓                    ↓
           outputs A            outputs B
                    ↘        ↙
                  مقارنةٌ بستّة محاور

نفسُ البايتات، نفسُ الترتيب، نفسُ الحمولة، نفسُ الإعداد، نفسُ الحالة
الابتدائيّة. والحكم `CLOSED` لا يقع إلّا عند `mismatch = 0`.

⚠️ والإطار جزءٌ من المسار عمدًا: Gate A أثبتت أنّه لا يغيّر المدخل، وGate B
تُشغّل المرجع **من خلاله** لا من الشريط مباشرةً — وإلّا بقي الإطار خارج ما
يُحكَم عليه.

## ما هو ممنوعٌ هنا

لا محرّك `Account×Symbol`، ولا خطّة مُجمَّعة، ولا Gate C، ولا تعديلَ ناقل،
ولا ٦٠١، ولا تسويةً صامتة، ولا حذفَ سجلٍّ مخالف.

    python tools/gate_b.py <شريط-مجمَّد.jsonl> [--batch 512]
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

from hot import frame, parity  # noqa: E402

#: إعدادُ المرجع — **واحدٌ للجانبين**. الساعة معطّلة: المهلة والمكنسة
#: تعتمدان الزمن، والإعادة لا ساعةَ لها. الحتميّة تُقاس على المنطق.
REPLAY_CONFIG = {"grace_s": 0.0, "close_after_s": 10 ** 9}


def verify_tape(path: Path) -> dict:
    """يتحقّق من بصمة الشريط مقابل بيانه — ولا يعمل على شريطٍ بلا بيان."""
    manifest_path = path.with_suffix(".json")
    if not manifest_path.exists():
        raise SystemExit("⛔ لا بيانَ مجاورٌ للشريط: %s" % manifest_path.name)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    measured = digest.hexdigest()
    if measured != manifest["sha256"]:
        raise SystemExit("⛔ البصمة لا تطابق البيان:\n   المقيس   %s\n"
                         "   المسجَّل %s" % (measured, manifest["sha256"]))
    manifest["measured_sha256"] = measured
    return manifest


def read_single_run(path: Path) -> list[tuple[int, str, dict]]:
    """يقرأ بترتيب الملفّ ويرفض شريطًا يحمل أكثر من تشغيلة."""
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
    previous = None
    runs = 0
    for index, _name, _payload in rows:
        if previous is None or index != previous + 1:
            runs += 1
        previous = index
    if runs != 1:
        raise SystemExit("⛔ الشريط يحمل %d تشغيلة — لا يُقاس عليه" % runs)
    return rows


def replay(blobs: list[bytes], out_path: Path, *, runtime: str) -> dict[str, dict]:
    """يفكّ الإطارات ويمرّرها في مرجعٍ **جديدٍ تمامًا** ثمّ يقرأ مخرجاته."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("", encoding="utf-8")
    recorder = parity.ParityRecorder(str(out_path), runtime=runtime,
                                     **REPLAY_CONFIG)
    for blob in blobs:
        _header, records = frame.decode(blob)
        for _index, name, payload in records:
            recorder.observe(name, payload)
    recorder.close()
    return parity.load(str(out_path))


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        print(__doc__)
        return 2
    size = 512
    for i, a in enumerate(sys.argv):
        if a == "--batch" and i + 1 < len(sys.argv):
            size = int(sys.argv[i + 1])

    tape_path = Path(args[0])
    manifest = verify_tape(tape_path)
    print("الشريط المجمَّد: %s" % tape_path.name)
    print("  sha256 = %s  ✅ مطابق للبيان" % manifest["sha256"][:32] + "…")
    print("  وقائع البيان = %d · بايت = %d\n"
          % (manifest["records"], manifest["bytes"]))

    rows = read_single_run(tape_path)
    if len(rows) != manifest["records"]:
        raise SystemExit("⛔ عدد الوقائع لا يطابق البيان: %d ≠ %d"
                         % (len(rows), manifest["records"]))

    # ── إطاراتٌ **واحدة** تُمرَّر للجانبين، فلا يختلف المدخل ──────────────
    blobs = [frame.encode(chunk) for chunk in frame.batches(rows, max_records=size)]
    fingerprint = hashlib.sha256(b"".join(blobs)).hexdigest()
    print("إطارات = %d · بصمة البايتات = %s…" % (len(blobs), fingerprint[:32]))
    print("  تُمرَّر **نفسها** إلى الجانبين — لا يُعاد ترميزها لكلٍّ\n")

    scratch = ROOT / "forex_runtime" / "var" / "parity" / "gate_b"
    t0 = time.perf_counter()
    left = replay(blobs, scratch / "replay-a.jsonl", runtime="replay-a")
    a_s = time.perf_counter() - t0
    t0 = time.perf_counter()
    right = replay(blobs, scratch / "replay-b.jsonl", runtime="replay-b")
    b_s = time.perf_counter() - t0
    print("Replay A: %d دورة في %.2f ث · Replay B: %d دورة في %.2f ث\n"
          % (len(left), a_s, len(right), b_s))

    result = parity.compare_axes(left, right)
    print("=== Gate B — حتميّة المرجع ===")
    print(parity.format_axes(result))

    closed = (result["mismatches"] == 0
              and result["output_count_match"]
              and result["only_left_count"] == 0
              and result["only_right_count"] == 0
              and result["shared"] > 0
              and not result["self_comparison"])
    print()
    print("الحكم: %s" % ("✅ Gate B = CLOSED" if closed else
                         "⛔ Gate B = OPEN — الاختلاف مصنَّفٌ أعلاه"))
    return 0 if closed else 1


if __name__ == "__main__":
    raise SystemExit(main())
