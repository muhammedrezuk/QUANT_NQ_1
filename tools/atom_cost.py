# -*- coding: utf-8 -*-
"""§5 / Gate D — كلفةُ دورةِ التِكّة الحقيقيّة (ختم `NQ — OPEN REAL ATOM COST`).

## العقد كما ختمه المالك

    مدخلٌ حقيقيّ ⟶ مالكُ Account×Symbol الحقيقيّ ⟶ الخطّة المُجمَّعة
        ⟶ تنفيذُ ذرّةٍ حقيقيّ ⟶ قرار ⟶ مخاطر ⟶ نيّةُ أمر

ولا Gate A ولا B ولا C تُعاد: المرجعُ مغلق، والإطارُ مغلق، والمُجمِّع
مغلق، و`Account×Symbol` و٦٤ قسمًا قائمة. هذا القياس الأخير وحده، وبنفس
العقد لا بنسخةٍ تجريبيّةٍ ثانية.

## بوّابةُ القرار

    120 تِك/ث ⟶ cycle_budget ≤ 6.000 م.ث
    150       ⟶               ≤ 4.000
    240 replay⟶               ≤ 2.000

وهذه حدودٌ **داخلَ دورة المالك**: إن تجاوزتها الذرّات فلا عددَ عمّالٍ
يُصلحها، لأنّ الدورة تسلسليّةٌ في مالكها.

    python tools/atom_cost.py --cycles 400 --warmup 60
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from hot import parity, planner  # noqa: E402
from hot.atom_host import AtomHost, SideEffectGuard, phase_of  # noqa: E402
from hot.cell import CellMap  # noqa: E402
from tools.gate_b import read_single_run  # noqa: E402
from tools.gate_d import provenance  # noqa: E402
from transport.ownership import ownership_key  # noqa: E402

TAPE = (ROOT / "forex_runtime" / "var" / "parity" / "frozen"
        / "tape-20260918-154724.jsonl")
OUT = ROOT / "forex_runtime" / "var" / "parity" / "gate_d" / "atom_cost.json"
BUDGETS = ((120.0, 6.0), (150.0, 4.0), (240.0, 2.0))
#: يُضبَط من سطر الأوامر — الوجهان يُقاسان ويُعلَنان، ولا يُختار أحدهما صامتًا.
COALESCE = False
#: ذرّاتٌ تُعزَل للتشخيص وحده — تُعرَض دائمًا في المخرَج.
EXCLUDE: frozenset[str] = frozenset()


def percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1,
                max(0, int(round(fraction * (len(ordered) - 1)))))
    return ordered[index]


async def measure(cycles: int, warmup: int) -> dict[str, Any]:
    plan = planner.compile_plan(known_external=planner.external_events())
    guard = SideEffectGuard()
    guard.install()
    host = AtomHost(plan, guard=guard)
    cells = CellMap()
    try:
        await host.boot()
        if EXCLUDE:
            # ⛔ لا تُحذف ذرّةٌ من الحكم صامتةً. هذا مِبضعُ تشخيصٍ فقط:
            #    يفصل «الميزانيّة مكسورةٌ بالمنصّة كلِّها» عن «مكسورةٌ بذرّةٍ
            #    واحدة» — والفرق بينهما يقرّر أين يقع الإصلاح.
            for name, subs in list(host.handlers.items()):
                host.handlers[name] = [(a, h) for a, h in subs
                                       if a not in EXCLUDE]
        rows = read_single_run(TAPE)
        ticks = [(i, p) for i, n, p in rows if n == parity.TICK_EVENT]

        wall: list[float] = []
        phases: list[dict[str, float]] = []
        handled: list[int] = []
        depth_max = 0
        published_total = 0
        cpu0 = time.process_time()
        started = time.perf_counter()

        for index, (sequence, payload) in enumerate(ticks):
            if index >= warmup + cycles:
                break
            # ── المالك الحقيقيّ: نفسُ `Cell` الذي أغلق Gate C ────────────
            key = ownership_key(payload)
            if key is not None:
                cell = cells.cell_for(key)
                try:
                    cell.admit(int(payload.get("sequence") or sequence), payload)
                except Exception:                              # noqa: BLE001
                    pass                    # إعادةُ ترتيبٍ باردة — قِيست سابقًا
            before = dict(host.cost_ns)
            result = await host.cycle(parity.TICK_EVENT, payload,
                                      coalesce=COALESCE)
            if key is not None:
                cell.commit()               # حدُّ الدورة: الحيّة ⟶ الملتزمة
            if index < warmup:
                continue                    # تسخينٌ يُرمى: استيرادٌ وذاكرةٌ باردة
            wall.append(result["wall_ns"] / 1e6)
            handled.append(result["handled"])
            published_total += result["published"]
            depth_max = max(depth_max, result["depth"])
            spent: dict[str, float] = {}
            for atom_id, value in host.cost_ns.items():
                delta = value - before.get(atom_id, 0)
                if delta:
                    spent[phase_of(atom_id)] = spent.get(
                        phase_of(atom_id), 0.0) + delta / 1e6
            phases.append(spent)

        cpu = time.process_time() - cpu0
        elapsed = time.perf_counter() - started
    finally:
        guard.remove()

    def phase_series(name: str) -> list[float]:
        return [row.get(name, 0.0) for row in phases]

    report = host.report()
    return {
        "provenance": provenance(),
        "plan_fingerprint": plan.summary()["fingerprint"],
        "atoms_in_plan": len(plan.order),
        "atoms_booted": report["loaded"],
        "atoms_failed": report["failed"],
        "events": len(host.handlers),
        "handlers": sum(len(v) for v in host.handlers.values()),
        "cycles": len(wall),
        "warmup": warmup,
        "coalesce": COALESCE,
        "excluded": sorted(EXCLUDE),
        "cascade_depth_max": depth_max,
        "handlers_per_cycle_p50": percentile([float(h) for h in handled], 0.5),
        "published_per_cycle": published_total / max(len(wall), 1),
        "owners": len(cells.keys()),
        "cpu_s": cpu,
        "elapsed_s": elapsed,
        "cycle_wall_ms": {
            "p50": percentile(wall, 0.50), "p95": percentile(wall, 0.95),
            "p99": percentile(wall, 0.99), "max": max(wall) if wall else 0.0,
            "mean": sum(wall) / len(wall) if wall else 0.0,
        },
        "phase_ms": {
            name: {"p50": percentile(phase_series(name), 0.50),
                   "p95": percentile(phase_series(name), 0.95),
                   "p99": percentile(phase_series(name), 0.99),
                   "mean": (sum(phase_series(name)) / len(phases)
                            if phases else 0.0)}
            for name in ("analysis", "decision", "risk", "intent")
        },
        "heaviest_atoms": report["heaviest"],
        "heaviest_handlers": [
            ("%s.%s" % (a, h), round(ns / 1e6, 3), host.handler_calls[(a, h)],
             round(ns / 1e6 / max(host.handler_calls[(a, h)], 1), 4))
            for (a, h), ns in sorted(host.handler_ns.items(),
                                     key=lambda kv: -kv[1])[:14]],
        "errors": report["errors"],
        "guard": report["guard"],
    }


def main() -> int:
    opts = {}
    for i, a in enumerate(sys.argv):
        if a.startswith("--") and i + 1 < len(sys.argv):
            opts[a[2:]] = sys.argv[i + 1]
    cycles = int(opts.get("cycles", 400))
    warmup = int(opts.get("warmup", 60))
    global COALESCE, EXCLUDE, OUT
    COALESCE = "--coalesce" in sys.argv
    EXCLUDE = frozenset(x for x in opts.get("exclude", "").split(",") if x)
    suffix = ("%s%s" % ("-coalesced" if COALESCE else "",
                        "-no" + "-".join(sorted(EXCLUDE)) if EXCLUDE else ""))
    if suffix:
        OUT = OUT.with_name("atom_cost%s.json" % suffix)
    if not TAPE.exists():
        raise SystemExit("⛔ لا شريطَ مجمَّد")

    result = asyncio.run(measure(cycles, warmup))
    info = result["provenance"]
    print("النسخة: %s @ %s · بايثون %s · GIL %s"
          % (info["head"], info["branch"], info["python"], info["gil_enabled"]))
    print("بصمة الإعداد: %s%s\n"
          % (info["config_sha256_16"],
             "  ⚠️ معدَّلٌ غير ملتزَم" if info["config_uncommitted"] else ""))

    print("الخطّة %s · ذرّات %d · أقلعت %d · سقطت %d"
          % (result["plan_fingerprint"][:16], result["atoms_in_plan"],
             result["atoms_booted"], len(result["atoms_failed"])))
    print("أحداثٌ %d · معالجاتٌ %d · مالكون %d"
          % (result["events"], result["handlers"], result["owners"]))
    print("دوراتٌ مقيسة %d (بعد تسخين %d) · عمقُ التتالي %d · "
          "معالجاتٌ لكلّ دورة %.0f · نشرٌ لكلّ دورة %.1f\n"
          % (result["cycles"], result["warmup"], result["cascade_depth_max"],
             result["handlers_per_cycle_p50"], result["published_per_cycle"]))

    cycle = result["cycle_wall_ms"]
    print("=== كلفةُ دورة التِكّة الحقيقيّة (م.ث) ===")
    print("  p50 %7.3f · p95 %7.3f · p99 %7.3f · أقصى %7.3f · وسطيّ %7.3f"
          % (cycle["p50"], cycle["p95"], cycle["p99"], cycle["max"],
             cycle["mean"]))
    print("\n  الطور        p50      p95      p99     وسطيّ")
    for name in ("analysis", "decision", "risk", "intent"):
        row = result["phase_ms"][name]
        print("  %-10s %7.3f  %7.3f  %7.3f  %7.3f"
              % (name, row["p50"], row["p95"], row["p99"], row["mean"]))

    print("\n=== أثقلُ الذرّات (م.ث إجمالًا · نداءات · ٪) ===")
    for atom_id, ms, calls, pct in result["heaviest_atoms"][:8]:
        print("  %-5s %9.3f  %7d  %5.1f٪" % (atom_id, ms, calls, pct))

    print("\n=== أثقلُ المعالجات (م.ث إجمالًا · نداءات · م.ث/نداء) ===")
    for label, ms, calls, each in result["heaviest_handlers"][:10]:
        print("  %-34s %9.3f %7d %8.4f" % (label[:34], ms, calls, each))

    print("\n=== بوّابةُ القرار ===")
    for rate, budget in BUDGETS:
        p99 = cycle["p99"]
        ok = p99 <= budget
        print("  %s %5.0f تِك/ث · الميزانيّة %.3f م.ث · p99 المقيس %.3f م.ث"
              % ("✅" if ok else "⛔", rate, budget, p99))

    guard = result["guard"]
    print("\nالحاجز: %s" % json.dumps(guard["attempts"], ensure_ascii=False))
    if guard["background_tasks_suppressed"]:
        print("مهامُّ خلفيّةٌ مُنعت: %d ذرّة"
              % len(guard["background_tasks_suppressed"]))
    if result["errors"]:
        top = sorted(result["errors"].items(), key=lambda kv: -kv[1])[:6]
        print("⚠️ ذرّاتٌ رفعت استثناءً داخل المعالج: %d — أعلاها %s"
              % (len(result["errors"]), top))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    print("\nكُتب: %s" % OUT.name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
