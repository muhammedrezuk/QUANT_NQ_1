# -*- coding: utf-8 -*-
"""خطُّ أساس Cycle Reduction (ختم `NQ — OPEN CYCLE REDUCTION`).

## السؤال الذي يسبق التصميم

مقيسٌ أنّ الدورة تُشغّل **٢٠٧ استدعاءً** وسيطًا و**٣٤٩** في الذيل.
والمجهول: **كم منها حرّك شيئًا؟**

    استدعاءٌ لا ينشر شيئًا          ⟶ لا يُحرّك التتالي
    استدعاءٌ يرى نفسَ الحمولة       ⟶ مدخلُه لم يتبدّل أصلًا
    واجتماعُهما                     ⟶ مرشّحٌ صريحٌ لقصّ المجموعة المتّسخة

فإن كانت الأكثريّةُ عقيمةً فالمجموعة المتّسخة تقصّ العملَ من جذره، والرقم
يقول **أين** تقصّ. وإن كانت الأكثريّةُ تنشر فالرسمُ كثيفٌ لا زائد،
وذلك تصميمٌ آخرُ تمامًا.

    ⛔ ولا يُكتب سطرُ تصميمٍ قبل هذا الرقم.

## ما لا يتغيّر

نفسُ `AtomHost` ونفسُ المانيفستات ونفسُ الخطّة ونفسُ الـ١٦٣ ذرّة.
هذا قياسٌ لا تعديل: التدقيق يُشغَّل بعلَمٍ ويُطفأ افتراضًا لأنّ كلفته
تُفسد أيّ قياسِ زمن.

    python tools/cycle_audit.py --cycles 300 --warmup 50
"""
from __future__ import annotations

import asyncio
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from hot import parity, planner  # noqa: E402
from hot.atom_host import AtomHost, SideEffectGuard, phase_of  # noqa: E402
from tools.gate_b import read_single_run  # noqa: E402
from tools.gate_d import provenance  # noqa: E402

TAPE = (ROOT / "forex_runtime" / "var" / "parity" / "frozen"
        / "tape-20260918-154724.jsonl")
OUT = ROOT / "forex_runtime" / "var" / "parity" / "gate_d" / "cycle_audit.json"


async def audit(cycles: int, warmup: int) -> dict[str, Any]:
    plan = planner.compile_plan(known_external=planner.external_events())
    guard = SideEffectGuard()
    guard.install()
    host = AtomHost(plan, guard=guard)
    try:
        await host.boot(freeze=True)
        host.audit = True
        rows = read_single_run(TAPE)
        ticks = [p for _i, n, p in rows if n == parity.TICK_EVENT]
        handled: list[int] = []
        for index in range(warmup + cycles):
            payload = ticks[index % len(ticks)]
            if index == warmup:          # التسخين لا يُحسب في التدقيق
                host.silent_calls.clear(); host.speaking_calls.clear()
                host.repeat_payload.clear(); host.fresh_payload.clear()
                host.silent_ns.clear(); host.speaking_ns.clear()
            result = await host.cycle(parity.TICK_EVENT, payload)
            if index >= warmup:
                handled.append(result["handled"])
            del host.published[:]
    finally:
        guard.remove()

    silent = sum(host.silent_calls.values())
    speaking = sum(host.speaking_calls.values())
    repeat = sum(host.repeat_payload.values())
    fresh = sum(host.fresh_payload.values())
    total = silent + speaking

    per_atom = []
    for atom_id in sorted(set(host.silent_calls) | set(host.speaking_calls)):
        s = host.silent_calls.get(atom_id, 0)
        k = host.speaking_calls.get(atom_id, 0)
        r = host.repeat_payload.get(atom_id, 0)
        per_atom.append({
            "atom": atom_id, "phase": phase_of(atom_id),
            "calls": s + k, "silent": s, "speaking": k, "repeat_payload": r,
            "silent_pct": 100.0 * s / max(s + k, 1),
            "repeat_pct": 100.0 * r / max(s + k, 1),
            "ms_total": host.cost_ns.get(atom_id, 0) / 1e6,
            "ms_silent": host.silent_ns.get(atom_id, 0) / 1e6,
            "ms_speaking": host.speaking_ns.get(atom_id, 0) / 1e6,
        })
    per_atom.sort(key=lambda row: -row["calls"])

    return {
        "provenance": provenance(),
        "plan": plan.summary()["fingerprint"],
        "atoms": len(plan.order), "booted": len(host.loaded),
        "cycles": len(handled),
        "calls_per_cycle": total / max(len(handled), 1),
        "total_calls": total,
        "silent": silent, "speaking": speaking,
        "silent_pct": 100.0 * silent / max(total, 1),
        "repeat_payload": repeat, "fresh_payload": fresh,
        "repeat_pct": 100.0 * repeat / max(total, 1),
        "ms_silent": sum(host.silent_ns.values()) / 1e6,
        "ms_speaking": sum(host.speaking_ns.values()) / 1e6,
        "per_atom": per_atom,
    }


def main() -> int:
    opts: dict[str, str] = {}
    for i, a in enumerate(sys.argv):
        if a.startswith("--") and i + 1 < len(sys.argv):
            opts[a[2:]] = sys.argv[i + 1]
    if not TAPE.exists():
        raise SystemExit("⛔ لا شريطَ مجمَّد")
    result = asyncio.run(audit(int(opts.get("cycles", 300)),
                               int(opts.get("warmup", 50))))
    info = result["provenance"]
    print("النسخة: %s @ %s · الخطّة %s"
          % (info["head"], info["branch"], result["plan"][:16]))
    print("ذرّات %d · أقلعت %d · دورات %d\n"
          % (result["atoms"], result["booted"], result["cycles"]))

    print("=== كم استدعاءً حرّك شيئًا؟ ===")
    print("  استدعاءات لكلّ دورة: %.1f" % result["calls_per_cycle"])
    print("  نشرت شيئًا:   %7d  (%.1f٪)"
          % (result["speaking"], 100.0 - result["silent_pct"]))
    print("  صامتة:        %7d  (%.1f٪)"
          % (result["silent"], result["silent_pct"]))
    print("  حمولةٌ مكرّرة: %7d  (%.1f٪)"
          % (result["repeat_payload"], result["repeat_pct"]))
    quiet, loud = result["ms_silent"], result["ms_speaking"]
    print("\n  ⚖️ الكلفة بالمصير — وهي الحكم لا العدد:")
    print("     في الصامتة:  %9.1f م.ث  (%.1f٪) ⟶ %.3f م.ث/دورة"
          % (quiet, 100.0 * quiet / max(quiet + loud, 1e-9),
             quiet / max(result["cycles"], 1)))
    print("     في الناشرة:  %9.1f م.ث  (%.1f٪) ⟶ %.3f م.ث/دورة"
          % (loud, 100.0 * loud / max(quiet + loud, 1e-9),
             loud / max(result["cycles"], 1)))
    print("     ⟹ سقفُ ما يمكن أن يقصّه قصٌّ مثاليّ: %.3f م.ث/دورة"
          % (quiet / max(result["cycles"], 1)))

    print("\n=== بالطور ===")
    by_phase: dict[str, Counter] = {}
    for row in result["per_atom"]:
        bucket = by_phase.setdefault(row["phase"], Counter())
        bucket["calls"] += row["calls"]
        bucket["silent"] += row["silent"]
        bucket["repeat"] += row["repeat_payload"]
        bucket["ms"] += int(row["ms_total"])
    print("  الطور        استدعاءات    صامتة    ٪صامت   مكرّرة   م.ث")
    for name in ("analysis", "decision", "risk", "intent"):
        b = by_phase.get(name)
        if not b:
            continue
        print("  %-10s %10d %9d %7.1f٪ %8d %6d"
              % (name, b["calls"], b["silent"],
                 100.0 * b["silent"] / max(b["calls"], 1), b["repeat"],
                 b["ms"]))

    print("\n=== أكثرُ الذرّات استدعاءً (‏صامت٪ · مكرّر٪ · م.ث) ===")
    for row in result["per_atom"][:14]:
        print("  %-5s %-9s %6d نداءً · صامت %5.1f٪ · مكرّر %5.1f٪ · %8.1f م.ث"
              % (row["atom"], row["phase"], row["calls"], row["silent_pct"],
                 row["repeat_pct"], row["ms_total"]))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    print("\nكُتب: %s" % OUT.name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
