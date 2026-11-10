# -*- coding: utf-8 -*-
"""يُعيد تشغيل شريط المدخلات في مرجعٍ ثانٍ ويقارنه بالأوّل.

## ما يُثبته وما لا يُثبته

**يُثبت:** أنّ نفس المدخلات بنفس الترتيب تُعطي **نفس المرجع حرفًا** — أي
أنّ المرجع حتميٌّ لا يحمل حالةً عابرة ولا يعتمد على ساعةٍ أو ترتيبٍ عرضيّ.
وهذا **شرطٌ سابق** لأيّ حكمٍ بالتكافؤ: مرجعٌ يختلف عن نفسه لا يحكم على غيره.

**لا يُثبت:** تكافؤ محرّكين. ذاك يحتاج زمن التشغيل الساخن (§٥ فما بعد)،
ويومها يُغذّى الشريطُ نفسه إليه وتُشغَّل المقارنة نفسها.

## الاستعمال

    python tools/parity_replay.py <شريط.jsonl> [مرجع.jsonl]

بلا مرجعٍ ثانٍ يقارن الإعادةَ بالإعادة (حتميّة محضة). ومع مرجعٍ حيّ يقارن
الإعادة به — وفارقُ المهل والمكانس يظهر مصنَّفًا لا مبتلعًا.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from hot import parity  # noqa: E402


def read_tape(path: str) -> list[tuple[str, dict]]:
    """يقرأ الشريط **بترتيب وصوله** — الترتيب جزءٌ من المدخلات."""
    rows: list[tuple[int, str, dict]] = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except ValueError:
                continue
            payload = row.get("payload")
            if isinstance(payload, dict) and row.get("name"):
                rows.append((int(row.get("i", len(rows))),
                             str(row["name"]), payload))
    rows.sort(key=lambda r: r[0])
    return [(name, payload) for _i, name, payload in rows]


def replay(tape: list[tuple[str, dict]], out_path: str,
           *, runtime: str) -> dict[str, dict]:
    """يمرّر الشريط في مسجّلٍ جديد. `grace_s=0` كي يكون الإغلاق حتميًّا.

    ⚠️ المهلة والمكنسة تعتمدان الساعة، والإعادة لا ساعةَ حقيقيّةَ لها.
    فتُعطَّلان هنا عمدًا: الحتميّة تُقاس على المنطق لا على التوقيت.
    """
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_text("", encoding="utf-8")
    rec = parity.ParityRecorder(out_path, runtime=runtime,
                                grace_s=0.0, close_after_s=10 ** 9)
    for name, payload in tape:
        rec.observe(name, payload)
    rec.close()
    return parity.load(out_path)


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    tape_path = sys.argv[1]
    live_path = sys.argv[2] if len(sys.argv) > 2 else ""
    tape = read_tape(tape_path)
    if not tape:
        print("⛔ الشريط فارغ — لا مدخلات تُعاد")
        return 1
    print("الشريط: %d حدثًا من %d اسمًا\n"
          % (len(tape), len({n for n, _ in tape})))

    scratch = ROOT / "forex_runtime" / "var" / "parity"
    a = replay(tape, str(scratch / "replay-a.jsonl"), runtime="replay-a")
    b = replay(tape, str(scratch / "replay-b.jsonl"), runtime="replay-b")

    result = parity.compare(a, b, ignore=("runtime",))
    print("=== حتميّة المرجع: إعادةٌ ضدّ إعادة ===")
    print(parity.format_report(result))
    rep = {}
    parity.load(str(scratch / "replay-a.jsonl"), report=rep)
    import os as _os
    mut = {"caught": 0, "total": 0}
    mut_path = _os.environ.get("MUT_JSON", "")
    if mut_path and _os.path.exists(mut_path):
        mut = json.load(open(mut_path, encoding="utf-8"))
    closed = parity.closure(a, load_report=rep, replay_result=result,
                            mutation_caught=mut["caught"],
                            mutation_total=mut["total"])
    print()
    print(parity.format_closure(closed))
    ok = closed["closed"]

    if live_path:
        rep: dict = {}
        live = parity.load(live_path, report=rep)
        cross = parity.compare(live, a, ignore=("runtime",))
        print("\n=== المرجع الحيّ ضدّ الإعادة ===")
        print(parity.format_report(cross))
        print("\n⚠️ فارقُ العدد هنا متوقَّعٌ ومفسَّر: الحيّ يُغلق بمهلةٍ ومكنسةٍ "
              "على ساعةٍ حقيقيّة، والإعادة بلا ساعة. وما يُحكَم عليه هو "
              "**الحقول** لا العدّ.")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
