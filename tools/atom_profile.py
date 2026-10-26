# -*- coding: utf-8 -*-
"""من أين تذهب المِلّي ثانية؟ (ختم `NQ — OPEN ATOM INTERNAL PROFILE`).

نفسُ الـ١٦٣ ذرّة · نفسُ الشريط · نفسُ الخطّة · نفسُ الصندوق الرمليّ.
لا تعديلَ ذرّةٍ ولا تغييرَ ملكيّة.

    inclusive   زمنُ المعالج كاملًا
    − نشر − قاعدة − ملفّ − خيط − نوم   (‏كلٌّ مقيسٌ بمؤقّتٍ على منفذه)
    = exclusive  حسابٌ خالصٌ داخل بايثون

ويُرتَّب العشرون الأوائل **بالزمن الفعليّ لا بعدد النداءات**.

    python tools/atom_profile.py --cycles 300 --warmup 50
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from hot import parity, planner  # noqa: E402
from hot.atom_host import AtomHost, SideEffectGuard, phase_of  # noqa: E402
from hot.profiler import GATES, Profiler  # noqa: E402
from tools.gate_b import read_single_run  # noqa: E402
from tools.gate_d import provenance  # noqa: E402

TAPE = (ROOT / "forex_runtime" / "var" / "parity" / "frozen"
        / "tape-20260918-154724.jsonl")
OUT = ROOT / "forex_runtime" / "var" / "parity" / "gate_d" / "atom_profile.json"
LABEL = {"publish": "نشر", "connect": "فتحُ اتّصال", "pragma": "براغما",
         "query": "استعلام", "fs": "ملفّ", "thread": "خيط", "sleep": "نوم"}


async def run(cycles: int, warmup: int) -> dict[str, Any]:
    plan = planner.compile_plan(known_external=planner.external_events())
    profiler = Profiler()
    guard = SideEffectGuard(profiler=profiler)
    guard.install()
    host = AtomHost(plan, guard=guard)
    try:
        await host.boot(freeze=True)
        rows = read_single_run(TAPE)
        ticks = [p for _i, n, p in rows if n == parity.TICK_EVENT]
        for index in range(warmup + cycles):
            if index == warmup:       # التسخين خارج التشريح
                profiler.enabled = True
                profiler.ns.clear(); profiler.hits.clear()
                profiler.inclusive.clear(); profiler.samples.clear()
            await host.cycle(parity.TICK_EVENT, ticks[index % len(ticks)])
            del host.published[:]
        profiler.enabled = False
        # ⛔ أتُصيب بصمةُ الحداثة أصلًا؟ — إن لم تتبدّل القاعدةُ خلال التشغيل
        #    فالذاكرةُ تُصيب ١٠٠٪ ويسقط كلُّ الاتّصالِ والاستعلام معًا.
        #    وإن تبدّلت كثيرًا فالبصمةُ لا تنفع والعلاجُ التعمير.
        stamps = {}
        for name, copy in guard.db_copies.items():
            try:
                origin = Path(name)
                stamps[origin.name] = {
                    "source_mtime": origin.stat().st_mtime if origin.exists() else None,
                    "sandbox_mtime": Path(copy).stat().st_mtime if Path(copy).exists() else None,
                    "sandbox_size": Path(copy).stat().st_size if Path(copy).exists() else 0,
                }
            except Exception:                                  # noqa: BLE001
                pass
    finally:
        guard.remove()
    report = profiler.report(cycles)
    report["databases"] = stamps
    report["provenance"] = provenance()
    report["plan"] = plan.summary()["fingerprint"]
    report["cycles"] = cycles
    report["booted"] = len(host.loaded)
    return report


def main() -> int:
    opts: dict[str, str] = {}
    for i, a in enumerate(sys.argv):
        if a.startswith("--") and i + 1 < len(sys.argv):
            opts[a[2:]] = sys.argv[i + 1]
    if not TAPE.exists():
        raise SystemExit("⛔ لا شريطَ مجمَّد")
    result = asyncio.run(run(int(opts.get("cycles", 300)),
                             int(opts.get("warmup", 50))))
    info = result["provenance"]
    rows = result["per_atom"]
    cycles = result["cycles"]
    print("النسخة: %s @ %s · الخطّة %s · ذرّات %d · دورات %d\n"
          % (info["head"], info["branch"], result["plan"][:16],
             result["booted"], cycles))

    total_inc = sum(r["inclusive_ms"] for r in rows)
    gates_total = {g: sum(r["gates_ms"][g] for r in rows) for g in GATES}
    exclusive = total_inc - sum(gates_total.values())
    print("=== أين تذهب المِلّي ثانية (كلُّ الذرّات) ===")
    print("  الإجماليّ           %8.3f م.ث/دورة" % (total_inc / cycles))
    for gate in GATES:
        value = gates_total[gate]
        if value > 0.0:
            print("  %-18s %8.3f م.ث/دورة  (%.1f٪)"
                  % (LABEL[gate], value / cycles, 100.0 * value / total_inc))
    print("  %-18s %8.3f م.ث/دورة  (%.1f٪)  ⟵ حسابٌ خالص"
          % ("exclusive", exclusive / cycles, 100.0 * exclusive / total_inc))

    print("\n=== العشرون الأوائل بالزمن الفعليّ ===")
    print("  ذرّة  طور        نداء/دورة  inclusive  exclusive   p50    p95"
          "    p99     max   أبرزُ منفذ")
    for row in rows[:20]:
        gates = row["gates_ms"]
        top = max(GATES, key=lambda g: gates[g])
        share = (100.0 * gates[top] / row["inclusive_ms"]
                 if row["inclusive_ms"] else 0.0)
        port = ("%s %.0f٪" % (LABEL[top], share)) if share >= 1.0 else "—"
        print("  %-5s %-9s %8.2f %10.4f %10.4f %6.3f %6.3f %6.3f %7.3f  %s"
              % (row["atom"], phase_of(row["atom"]), row["calls_per_cycle"],
                 row["inclusive_per_cycle"], row["exclusive_ms"] / cycles,
                 row["p50"], row["p95"], row["p99"], row["max"], port))

    top20 = sum(r["inclusive_ms"] for r in rows[:20])
    print("\n  العشرون الأوائل = %.1f٪ من الكلفة · والباقي %d ذرّةً = %.1f٪"
          % (100.0 * top20 / total_inc, len(rows) - 20,
             100.0 * (total_inc - top20) / total_inc))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    print("\nكُتب: %s" % OUT.name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
