# -*- coding: utf-8 -*-
"""§5 / Gate D — تشريحُ ذيل p99 (ختم `NQ — MEASURE REAL P99 TAIL`).

## السؤال

    p50 = 8.704   p95 = 13.412   p99 = 24.639

القفزةُ بين p95 وp99 هي الإشارة. **ما الذي يصنعها؟** وباسم الذرّة
والطور، لا بتخمين. وقبل معرفته لا يُقسَّم مالكٌ ولا تُعدَّل ذرّة: تقسيمُ
المالك قد **يُخفي** العلّة بدل أن يحلّها، ويُبدّل ملكيّةَ الحالة معها.

## الفصل المطلوب

    atom p99        مجموعُ زمن المعالجات داخل الدورة
    cycle p99       الدورة كاملةً من أوّل معالجٍ إلى آخره
    wait p99        الفرق بينهما — جدولةٌ وانتظارٌ لا عملَ ذرّة
    owner p99       لكلّ `Account×Symbol` على حدة
    cold I/O        مستثنًى (‏الحاجز يعزل القاعدة أصلًا)

## طريقةُ تسمية المتّهم

لا يكفي «أيُّ ذرّةٍ أغلى في الذيل»: أغلاها في الذيل قد تكون أغلاها في
كلّ دورة. فيُقاس **الفائض**:

    فائضُ ذرّةٍ = وسطيُّ كلفتها في دورات الذيل − وسيطُها في الدورات العاديّة

فمن يصنع الذيل هو من يقفز فيه، لا من هو ثقيلٌ دائمًا.

    python tools/tail_probe.py --rate 120 --cycles 400
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
from tools.gate_d import _fine_timer, provenance  # noqa: E402
from transport.ownership import ownership_key  # noqa: E402

TAPE = (ROOT / "forex_runtime" / "var" / "parity" / "frozen"
        / "tape-20260918-154724.jsonl")
OUT = ROOT / "forex_runtime" / "var" / "parity" / "gate_d"
#: يُضبَط من سطر الأوامر — الوجهان يُقاسان ويُعلَنان.
NO_GC = False
FREEZE = False
LEAN = False


def pct(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1,
                max(0, int(round(fraction * (len(ordered) - 1)))))
    return ordered[index]


async def probe(rate: float, cycles: int, warmup: int) -> dict[str, Any]:
    plan = planner.compile_plan(known_external=planner.external_events())
    guard = SideEffectGuard()
    guard.install()
    host = AtomHost(plan, guard=guard)
    cells = CellMap()
    samples: list[dict[str, Any]] = []
    try:
        await host.boot(freeze=FREEZE)
        rows = read_single_run(TAPE)
        ticks = [p for _i, n, p in rows if n == parity.TICK_EVENT]
        # ⛔ فرضيّةٌ تُختبَر لا تُروى: كانسُ المهملات.
        #
        #    الأدلّة التي قادت إليها: الذيل **لا يتحرّك** بين 120 و150 و240
        #    (‏فليس حِملًا)، و«الانتظار» p99 = 1.3 م.ث وحدها (‏فليست جدولة)،
        #    والذرّاتُ القافزة **تتبدّل بين تشغيلٍ وآخر** (‏فليست ذرّةً
        #    بعينها)، والذيل يأتي **دفعاتٍ متلاصقة** (‏1، 1، 2، 2…).
        #    وكنسٌ جيليٌّ يقع داخل أيّ معالجٍ صادف، فيُحسَب كلفتَه.
        if NO_GC:
            import gc
            gc.collect()
            gc.freeze()            # ما أنشأه الإقلاع يخرج من الفحص
            gc.disable()
        _fine_timer(True)
        t0 = time.perf_counter() + 0.05
        for index in range(warmup + cycles):
            payload = ticks[index % len(ticks)]
            # ── الضخُّ بالمعدّل: الذيل تحت حِملٍ لا في حلقةٍ محمومة ────────
            due = t0 + index / rate
            now = time.perf_counter()
            if now < due:
                gap = due - now
                if gap > 0.002:
                    time.sleep(gap - 0.002)
                while time.perf_counter() < due:
                    pass
            key = ownership_key(payload)
            if key is not None:
                cells.cell_for(key)
            before = dict(host.cost_ns)
            started = time.perf_counter_ns()
            result = await host.cycle(parity.TICK_EVENT, payload)
            wall = time.perf_counter_ns() - started
            if index < warmup:
                continue
            deltas = {a: v - before.get(a, 0)
                      for a, v in host.cost_ns.items() if v - before.get(a, 0)}
            atom_ns = sum(deltas.values())
            if LEAN:
                # ⛔ المسبارُ نفسه متّهم: `published` ينمو بلا حدّ (‏~100
                #    لكلّ دورة) و`deltas` يُحتفَظ بها لكلّ دورة. فيصير
                #    الهرمُ الذي يكنسه الكانس **من صنعي أنا** لا من
                #    المحرّك. وفي التشغيل الحقيقيّ لا يحتفظ أحدٌ بهذا.
                #    فيُقصّ ويُعاد القياس: إن سقط الذيل فالمتّهم مسباري.
                del host.published[:]
            samples.append({
                "index": index - warmup,
                "owner": key.text if key else "?",
                "wall_ms": wall / 1e6,
                "atom_ms": atom_ns / 1e6,
                # ⛔ الفرق ليس صفرًا بالضرورة: فرزُ المعالجات وبناءُ
                #    الطابور والاستئنافُ بعد `await` كلُّها خارج الذرّات.
                "wait_ms": (wall - atom_ns) / 1e6,
                "handled": result["handled"],
                "depth": result["depth"],
                # في الوضع النحيف تُحفظ أثقلُ ثمانٍ فقط: الفائضُ يُحسَب
                # عليها، ولا يُبنى معجمٌ من ١٦٣ مدخلًا لكلّ دورة.
                "deltas": ({a: v / 1e6 for a, v in
                            sorted(deltas.items(), key=lambda kv: -kv[1])[:8]}
                           if LEAN else
                           {a: v / 1e6 for a, v in deltas.items()}),
            })
        _fine_timer(False)
    finally:
        guard.remove()
        if NO_GC:
            import gc
            gc.enable()
            gc.unfreeze()
    return {"plan": plan.summary()["fingerprint"], "rate": rate,
            "samples": samples, "atoms": len(plan.order), "no_gc": NO_GC,
            "freeze": FREEZE, "gc_record": host.gc_record}


def analyse(run: dict[str, Any]) -> dict[str, Any]:
    samples = run["samples"]
    wall = [s["wall_ms"] for s in samples]
    atom = [s["atom_ms"] for s in samples]
    wait = [s["wait_ms"] for s in samples]
    p95 = pct(wall, 0.95)
    tail = [s for s in samples if s["wall_ms"] >= p95]
    body = [s for s in samples if s["wall_ms"] < p95]

    def median_of(rows: list[dict], atom_id: str) -> float:
        values = [r["deltas"].get(atom_id, 0.0) for r in rows]
        return pct(values, 0.5)

    def mean_of(rows: list[dict], atom_id: str) -> float:
        if not rows:
            return 0.0
        return sum(r["deltas"].get(atom_id, 0.0) for r in rows) / len(rows)

    involved = {a for s in samples for a in s["deltas"]}
    excess = []
    for atom_id in involved:
        gap = mean_of(tail, atom_id) - median_of(body, atom_id)
        if gap > 0.0:
            excess.append((atom_id, gap, mean_of(tail, atom_id),
                           median_of(body, atom_id), phase_of(atom_id)))
    excess.sort(key=lambda row: -row[1])

    owners: dict[str, list[float]] = {}
    for sample in samples:
        owners.setdefault(sample["owner"], []).append(sample["wall_ms"])

    phase_tail: dict[str, float] = {}
    phase_body: dict[str, float] = {}
    for name in ("analysis", "decision", "risk", "intent"):
        phase_tail[name] = (sum(sum(v for a, v in s["deltas"].items()
                                    if phase_of(a) == name) for s in tail)
                            / max(len(tail), 1))
        phase_body[name] = (sum(sum(v for a, v in s["deltas"].items()
                                    if phase_of(a) == name) for s in body)
                            / max(len(body), 1))

    return {
        "cycles": len(samples), "tail_cycles": len(tail),
        "cycle": {k: pct(wall, v) for k, v in
                  (("p50", .5), ("p95", .95), ("p99", .99), ("max", 1.0))},
        "atom": {k: pct(atom, v) for k, v in
                 (("p50", .5), ("p95", .95), ("p99", .99), ("max", 1.0))},
        "wait": {k: pct(wait, v) for k, v in
                 (("p50", .5), ("p95", .95), ("p99", .99), ("max", 1.0))},
        "owners": {o: {"n": len(v), "p50": pct(v, .5), "p95": pct(v, .95),
                       "p99": pct(v, .99), "max": max(v)}
                   for o, v in sorted(owners.items())},
        "phase_tail_ms": phase_tail, "phase_body_ms": phase_body,
        "excess": excess[:14],
        # ⛔ الفصلُ الأخير: أدوريٌّ هو أم لمسةٌ أولى؟ والفرق يقرّر المعمار.
        #    الأدوريُّ عملٌ لازمٌ يتكرّر، ولا يُزيله تقسيمُ مالك.
        #    ولمسةُ أوّلٍ تختفي في الحالة المستقرّة، فلا تُبنى عليها بنية.
        "tail_indices": [s["index"] for s in tail],
        "tail_owners": sorted({s["owner"] for s in tail}),
        "tail_first_per_owner": {
            owner: min((s["index"] for s in samples if s["owner"] == owner),
                       default=-1)
            for owner in sorted({s["owner"] for s in tail})},
        "tail_handled_mean": (sum(s["handled"] for s in tail)
                              / max(len(tail), 1)),
        "body_handled_mean": (sum(s["handled"] for s in body)
                              / max(len(body), 1)),
    }


def main() -> int:
    opts: dict[str, str] = {}
    for i, a in enumerate(sys.argv):
        if a.startswith("--") and i + 1 < len(sys.argv):
            opts[a[2:]] = sys.argv[i + 1]
    rate = float(opts.get("rate", 120))
    cycles = int(opts.get("cycles", 400))
    warmup = int(opts.get("warmup", 60))
    global NO_GC, FREEZE, LEAN
    NO_GC = "--no-gc" in sys.argv
    FREEZE = "--freeze" in sys.argv
    LEAN = "--lean" in sys.argv
    if NO_GC and FREEZE:
        raise SystemExit("⛔ لا يُجمَّع تعطيلٌ وتجميدٌ — قياسان مختلفان")
    if not TAPE.exists():
        raise SystemExit("⛔ لا شريطَ مجمَّد")

    info = provenance()
    print("النسخة: %s @ %s · بايثون %s"
          % (info["head"], info["branch"], info["python"]))
    run = asyncio.run(probe(rate, cycles, warmup))
    result = analyse(run)
    print("الخطّة %s · ذرّات %d · معدّل %.0f تِك/ث · دورات %d%s"
          % (run["plan"][:16], run["atoms"], rate, result["cycles"],
             "  ⚠️ الكانس معطَّل" if run.get("no_gc") else ""))
    if run.get("gc_record"):
        from hot.gc_gate import summary as gc_summary
        print("  %s" % gc_summary(run["gc_record"]))
    print()

    print("=== الفصل (م.ث) ===")
    print("           p50      p95      p99      أقصى")
    for name, key in (("دورة", "cycle"), ("ذرّات", "atom"),
                      ("انتظار", "wait")):
        row = result[key]
        print("  %-8s %7.3f  %7.3f  %7.3f  %8.3f"
              % (name, row["p50"], row["p95"], row["p99"], row["max"]))

    print("\n=== لكلّ مالك (م.ث) ===")
    for owner, row in sorted(result["owners"].items(),
                             key=lambda kv: -kv[1]["p99"]):
        print("  %-22s n=%4d · p50 %6.3f · p95 %7.3f · p99 %7.3f · أقصى %8.3f"
              % (owner, row["n"], row["p50"], row["p95"], row["p99"],
                 row["max"]))

    print("\n=== الذيل مقابل الجسم (%d دورةَ ذيلٍ من %d) ==="
          % (result["tail_cycles"], result["cycles"]))
    print("  معالجاتٌ لكلّ دورة: ذيل %.1f · جسم %.1f"
          % (result["tail_handled_mean"], result["body_handled_mean"]))
    print("  الطور        ذيل      جسم     الفائض")
    for name in ("analysis", "decision", "risk", "intent"):
        t, b = result["phase_tail_ms"][name], result["phase_body_ms"][name]
        print("  %-10s %7.3f  %7.3f  %+7.3f" % (name, t, b, t - b))

    idx = result["tail_indices"]
    gaps = [b - a for a, b in zip(idx, idx[1:])]
    print("\n=== أدوريٌّ أم لمسةٌ أولى؟ ===")
    print("  مواضعُ دورات الذيل: %s" % idx[:24])
    if gaps:
        print("  الفواصل بينها: %s" % gaps[:23])
        print("  أصغرُ فاصل %d · أكبرُ %d · وسيط %d"
              % (min(gaps), max(gaps), sorted(gaps)[len(gaps) // 2]))
    print("  أوّلُ ظهورٍ لكلّ مالكٍ ذي ذيل: %s"
          % result["tail_first_per_owner"])

    print("\n=== مَن يقفز في الذيل (فائضٌ م.ث · ذيل · جسم · طور) ===")
    for atom_id, gap, tail_mean, body_median, phase in result["excess"][:10]:
        print("  %-5s %+8.3f   %7.3f  %7.3f   %s"
              % (atom_id, gap, tail_mean, body_median, phase))

    path = OUT / ("tail-r%d.json" % rate)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"provenance": info, "analysis": result},
                               ensure_ascii=False, indent=2), encoding="utf-8")
    print("\nكُتب: %s" % path.name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
