# -*- coding: utf-8 -*-
"""تضخيمُ الغرفة والسجلّ (ختم `NQ — MEASURE ROOM AMPLIFICATION`).

## السؤال

    decision.room.state      5.26 نشرةً لكلّ دورة
    decision.cycle.record    4.00

ولا يُحكَم عليهما بالاسم. المطلوب لكلّ دورة: كم ناشرًا، وكم حمولةً
متمايزة، وكم **تبدّلَ حالةٍ حقيقيًّا**، وكم تسليمًا يُولّده ذلك.

    نشراتٌ = تبدّلات        ⟶ منتِجٌ ولا يُقصّ
    نشراتٌ ≫ تبدّلات       ⟶ تضخيمٌ يستحقّ الإصلاح
    نشرٌ بلا مستهلكٍ دلاليّ ⟶ باردٌ بعد إثبات الأثر

## كيف يُعرَف «تبدّلُ حالة»

بمقارنة الحمولة بسابقتها **لنفس الهويّة** (‏ناشرٌ + حسابٌ + رمز). ويُقاس
الوجهان معًا ولا يُختار أحدهما:

    بالحمولة كاملةً          ⟶ أيُّ حرفٍ تبدّل
    بالحمولة دون حقول الزمن ⟶ أالمضمونُ تبدّل أم الطابعُ وحده

فحمولتان لا تختلفان إلّا في `at` ليستا تبدّلَ حالة. وعدُّهما تبدّلين
يُخفي التضخيم، وعدُّ الأولى وحدها قد يُظهر تضخيمًا لا وجود له.

    python tools/room_probe.py --cycles 300 --warmup 50
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from hot import parity, planner  # noqa: E402
from hot.atom_host import AtomHost, SideEffectGuard  # noqa: E402
from tools.gate_b import read_single_run  # noqa: E402
from tools.gate_d import provenance  # noqa: E402

TAPE = (ROOT / "forex_runtime" / "var" / "parity" / "frozen"
        / "tape-20260918-154724.jsonl")
OUT = ROOT / "forex_runtime" / "var" / "parity" / "gate_d" / "room_probe.json"

WATCHED = ("decision.room.state", "decision.cycle.record")
#: حقولٌ تتبدّل بلا أن يتبدّل المضمون — طوابعُ ومعرّفاتُ أثر.
TIME_FIELDS = frozenset({
    "at", "ts", "time", "timestamp", "emitted_at", "seen_at", "_seen_at",
    "published_at", "created_at", "updated_at", "age_s", "latency_ms",
    "trace_id", "sequence", "elapsed", "elapsed_ms", "now",
})


def _digest(value: Any) -> str:
    return hashlib.blake2b(
        json.dumps(value, sort_keys=True, default=str).encode("utf-8"),
        digest_size=8).hexdigest()


def _strip_time(payload: Any) -> Any:
    if not isinstance(payload, dict):
        return payload
    return {k: (_strip_time(v) if isinstance(v, dict) else v)
            for k, v in payload.items() if k not in TIME_FIELDS}


def _identity(producer: str, payload: Any) -> tuple:
    if not isinstance(payload, dict):
        return (producer,)
    return (producer, payload.get("account_id"), payload.get("symbol"),
            payload.get("id"))


async def probe(cycles: int, warmup: int) -> dict[str, Any]:
    plan = planner.compile_plan(known_external=planner.external_events())
    guard = SideEffectGuard()
    guard.install()
    host = AtomHost(plan, guard=guard)
    stats: dict[str, dict[str, Any]] = {
        name: {
            "publishes": 0, "producers": Counter(), "cycles_seen": 0,
            "distinct_full": 0, "distinct_content": 0,
            "mutations_full": 0, "mutations_content": 0,
            "deliveries": 0, "subscribers": 0,
            "per_cycle_publishes": Counter(),
        } for name in WATCHED
    }
    last: dict[tuple, str] = {}
    try:
        await host.boot(freeze=True)
        for name in WATCHED:
            stats[name]["subscribers"] = len(host.handlers.get(name, ()))
        rows = read_single_run(TAPE)
        ticks = [p for _i, n, p in rows if n == parity.TICK_EVENT]
        for index in range(warmup + cycles):
            payload = ticks[index % len(ticks)]
            await host.cycle(parity.TICK_EVENT, payload)
            if index >= warmup:
                seen_full: dict[str, set] = {n: set() for n in WATCHED}
                seen_content: dict[str, set] = {n: set() for n in WATCHED}
                count: Counter[str] = Counter()
                for producer, name, body in host.published:
                    if name not in WATCHED:
                        continue
                    row = stats[name]
                    row["publishes"] += 1
                    row["producers"][producer] += 1
                    row["deliveries"] += row["subscribers"]
                    count[name] += 1
                    full = _digest(body)
                    content = _digest(_strip_time(body))
                    seen_full[name].add(full)
                    seen_content[name].add(content)
                    key = _identity(producer, body)
                    if last.get(("f",) + key) != full:
                        row["mutations_full"] += 1
                    if last.get(("c",) + key) != content:
                        row["mutations_content"] += 1
                    last[("f",) + key] = full
                    last[("c",) + key] = content
                for name in WATCHED:
                    stats[name]["distinct_full"] += len(seen_full[name])
                    stats[name]["distinct_content"] += len(seen_content[name])
                    if count[name]:
                        stats[name]["cycles_seen"] += 1
                    stats[name]["per_cycle_publishes"][count[name]] += 1
            del host.published[:]
    finally:
        guard.remove()

    out = {"provenance": provenance(), "plan": plan.summary()["fingerprint"],
           "cycles": cycles, "events": {}}
    for name in WATCHED:
        row = stats[name]
        out["events"][name] = {
            "publishes_per_cycle": row["publishes"] / cycles,
            "distinct_payloads_per_cycle": row["distinct_full"] / cycles,
            "distinct_content_per_cycle": row["distinct_content"] / cycles,
            "mutations_full_per_cycle": row["mutations_full"] / cycles,
            "mutations_content_per_cycle": row["mutations_content"] / cycles,
            "deliveries_per_cycle": row["deliveries"] / cycles,
            "subscribers": row["subscribers"],
            "producers": dict(row["producers"]),
            "cycles_with_any": row["cycles_seen"],
            "publish_histogram": dict(sorted(row["per_cycle_publishes"].items())),
        }
    return out


def main() -> int:
    opts: dict[str, str] = {}
    for i, a in enumerate(sys.argv):
        if a.startswith("--") and i + 1 < len(sys.argv):
            opts[a[2:]] = sys.argv[i + 1]
    if not TAPE.exists():
        raise SystemExit("⛔ لا شريطَ مجمَّد")
    result = asyncio.run(probe(int(opts.get("cycles", 300)),
                               int(opts.get("warmup", 50))))
    info = result["provenance"]
    print("النسخة: %s @ %s · الخطّة %s · دورات %d\n"
          % (info["head"], info["branch"], result["plan"][:16],
             result["cycles"]))

    for name, row in result["events"].items():
        print("=== %s ===" % name)
        print("  نشراتٌ لكلّ دورة        %7.2f" % row["publishes_per_cycle"])
        print("  حمولاتٌ متمايزة        %7.2f  (بالحمولة كاملةً)"
              % row["distinct_payloads_per_cycle"])
        print("  مضمونٌ متمايز          %7.2f  (دون حقول الزمن)"
              % row["distinct_content_per_cycle"])
        print("  تبدّلُ حالةٍ حقيقيّ     %7.2f  (دون حقول الزمن)"
              % row["mutations_content_per_cycle"])
        print("  مشترِكون %d ⟶ تسليماتٌ لكلّ دورة %7.2f"
              % (row["subscribers"], row["deliveries_per_cycle"]))
        print("  ناشرون: %s" % row["producers"])
        print("  توزيعُ النشرات في الدورة: %s" % row["publish_histogram"])
        pub = row["publishes_per_cycle"]
        mut = row["mutations_content_per_cycle"]
        if pub > 0:
            ratio = pub / max(mut, 1e-9)
            verdict = ("منتِجٌ — لا يُقصّ" if ratio < 1.25 else
                       "⚠️ تضخيمٌ ×%.1f — يستحقّ الفحص" % ratio)
            print("  ⟹ نشرة/تبدّل = %.2f   %s" % (ratio, verdict))
        print()

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    print("كُتب: %s" % OUT.name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
