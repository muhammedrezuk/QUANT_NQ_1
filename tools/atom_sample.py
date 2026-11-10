# -*- coding: utf-8 -*-
"""أين تذهب المِلّي ثانية — بالعيّنة، وبأداةٍ تُثبت نفسَها أوّلًا.

## الترتيب مُلزِم

    ١) تشغيلٌ **بلا** الأداة  ⟶ عدّاداتٌ مستقلّة
    ٢) تشغيلٌ **مع** الأداة   ⟶ نفسُ العدّادات
    ٣) إن تحرّك عدّادٌ واحد   ⟶ **يُرفَض التقرير ولا يُطبَع رقم**
    ٤) وإلّا يُقرأ التشريح

والعدّاداتُ لا تملكها الأداة: اتّصالاتُ قاعدةٍ من الحاجز · نشراتٌ من
المضيف · أخطاءُ معالجات · دورات. فإن غيّرت الأداةُ السلوك ظهر ذلك فيها.

⛔ وهذا ما لم أفعله مع `hot/profiler.py`، فسلّمتُ جدولًا كاملًا من أداةٍ
   تقلب تِكّاتٍ سليمةً إلى باطلة (‏1.03 ⟵ 31.28 اتّصال/دورة).

    python tools/atom_sample.py --cycles 300 --warmup 120
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
from hot.sampler import StackSampler  # noqa: E402
from tools.gate_b import read_single_run  # noqa: E402
from tools.gate_d import provenance  # noqa: E402

TAPE = (ROOT / "forex_runtime" / "var" / "parity" / "frozen"
        / "tape-20260918-154724.jsonl")
OUT = ROOT / "forex_runtime" / "var" / "parity" / "gate_d" / "atom_sample.json"
#: ما يُسمَح به من فارقٍ نسبيٍّ في عدّادٍ مستقلّ قبل رفض التقرير.
TOLERANCE = 0.02


async def one_run(cycles: int, warmup: int, *, sample: bool,
                  interval_ms: float) -> dict[str, Any]:
    plan = planner.compile_plan(known_external=planner.external_events())
    guard = SideEffectGuard()
    guard.install()
    host = AtomHost(plan, guard=guard)
    sampler = None
    try:
        await host.boot(freeze=True)
        rows = read_single_run(TAPE)
        ticks = [p for _i, n, p in rows if n == parity.TICK_EVENT]
        for index in range(warmup):          # تسخينٌ يتجاوز البداية الباردة
            await host.cycle(parity.TICK_EVENT, ticks[index % len(ticks)])
            del host.published[:]
        base_connects = guard.attempts.get("قاعدة", 0)
        published = 0
        errors_before = sum(host.errors.values())
        if sample:
            sampler = StackSampler(interval_s=interval_ms / 1000.0,
                                   owner_of=lambda: guard.current)
            sampler.start()
        started = time.perf_counter()
        for index in range(cycles):
            result = await host.cycle(parity.TICK_EVENT,
                                      ticks[(warmup + index) % len(ticks)])
            published += result["published"]
            del host.published[:]
        wall = time.perf_counter() - started
        if sampler is not None:
            sampler.stop()
        out: dict[str, Any] = {
            # ── عدّاداتٌ مستقلّةٌ لا تملكها الأداة ────────────────────────
            "connects": guard.attempts.get("قاعدة", 0) - base_connects,
            "published": published,
            "errors": sum(host.errors.values()) - errors_before,
            "cycles": cycles, "wall_s": wall,
        }
        if sampler is not None:
            out["profile"] = sampler.report(cycles, wall)
        return out
    finally:
        guard.remove()


def diff(left: dict, right: dict) -> list[str]:
    """أيُّ عدّادٍ مستقلٍّ تحرّك؟ — الزمنُ مستثنًى، فهو المتوقَّع أن يتحرّك."""
    complaints = []
    for key in ("connects", "published", "errors"):
        a, b = left[key], right[key]
        if a == b:
            continue
        span = max(abs(a), abs(b), 1)
        if abs(a - b) / span > TOLERANCE:
            complaints.append("%s: بلا=%d · مع=%d (فارق %.1f٪)"
                              % (key, a, b, 100.0 * abs(a - b) / span))
    return complaints


def main() -> int:
    opts: dict[str, str] = {}
    for i, a in enumerate(sys.argv):
        if a.startswith("--") and i + 1 < len(sys.argv):
            opts[a[2:]] = sys.argv[i + 1]
    cycles = int(opts.get("cycles", 300))
    warmup = int(opts.get("warmup", 120))
    interval = float(opts.get("interval-ms", 1.0))
    if not TAPE.exists():
        raise SystemExit("⛔ لا شريطَ مجمَّد")

    info = provenance()
    print("النسخة: %s @ %s · دورات %d · تسخين %d · عيّنة كلّ %.1f م.ث\n"
          % (info["head"], info["branch"], cycles, warmup, interval))

    print("=== ١) الأداةُ تُثبت نفسَها قبل أن تنطق ===")
    clean = asyncio.run(one_run(cycles, warmup, sample=False,
                                interval_ms=interval))
    watched = asyncio.run(one_run(cycles, warmup, sample=True,
                                  interval_ms=interval))
    print("  عدّادٌ مستقلّ     بلا الأداة      مع الأداة")
    for key, label in (("connects", "اتّصالات"), ("published", "نشرات"),
                       ("errors", "أخطاء")):
        print("  %-14s %12d %14d" % (label, clean[key], watched[key]))
    print("  %-14s %11.3f ث %12.3f ث  (يُتوقَّع أن يتحرّك)"
          % ("زمنُ الجدار", clean["wall_s"], watched["wall_s"]))

    complaints = diff(clean, watched)
    if complaints:
        print("\n⛔ **مرفوض — الأداةُ تُغيّر ما تقيسه.** لا يُطبَع رقم:")
        for line in complaints:
            print("   %s" % line)
        return 1
    overhead = (100.0 * (watched["wall_s"] - clean["wall_s"])
                / max(clean["wall_s"], 1e-9))
    print("\n  ✅ لم يتحرّك عدّادٌ مستقلّ · كلفةُ الأداة على الزمن %+.1f٪\n"
          % overhead)

    profile = watched["profile"]
    print("=== ٢) أين كان المفسّر (عيّنات: %d · %.4f م.ث للعيّنة) ==="
          % (profile["samples"], profile["ms_per_sample"]))

    print("\n--- بالذرّة (‏مَن كان معالجُها يجري) ---")
    print("  ذرّة  طور        عيّنات      ٪     م.ث/دورة")
    for row in profile["by_owner"][:14]:
        owner = row["owner"]
        print("  %-5s %-9s %8d %6.1f٪ %10.3f"
              % (owner, phase_of(owner) if owner.isdigit() else "—",
                 row["samples"], row["pct"], row["ms_per_cycle"]))

    print("\n--- بالدالّة الأعمق (‏ما كان يُنفَّذ فعلًا) ---")
    print("  ذرّة  موضع                                   ٪     م.ث/دورة")
    for row in profile["leaf"][:18]:
        print("  %-5s %-38s %6.1f٪ %10.3f"
              % (row["owner"], row["spot"][:38], row["pct"],
                 row["ms_per_cycle"]))

    result = {"provenance": info, "clean": clean, "watched": watched,
              "overhead_pct": overhead}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    print("\nكُتب: %s" % OUT.name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
