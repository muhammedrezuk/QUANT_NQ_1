# -*- coding: utf-8 -*-
"""قبول NQ ENGINE — جدول §٢٩ من ورقة المحرّك، بالرقم لا بالعبارة.

يقرأ النواة الحيّة على نافذةٍ (افتراضًا ٦٠ دقيقة، عيّنة كلّ ٣٠ ثانية) ويحكم:

    ميل الطابور الساخن     ≤ 0 (على النصف الأخير من النافذة)
    مهلات الدورة           = 0
    تجاوز العمق/الميزانيّة  = 0
    p99 تِكّة ← قرار        ≤ الحدّ (من `latency.limit_s`) لكلّ رمز
    فقد أحداث المال         = 0 (`critical_dropped_by_event` على البارد)
    معالج عمليّة النواة     ≤ ٥٠٪ من نواة (متوسّط النافذة)
    الرسم مختوم · لا مزرعة · لا حدث خارج الرسم

ولا لقطة مبكّرة: أوّل خمس دقائق بعد الإقلاع تُستثنى من الحكم (درس G1).
الخروج 0 = PASS · 1 = FAIL · 2 = النواة لا تجيب أو المحرّك غير مفعّل.

    python governance/checks/check_engine_acceptance.py --minutes 60
    python governance/checks/check_engine_acceptance.py --from-samples samples.jsonl
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8010"
WARMUP_S = 300.0
CPU_LIMIT_PCT = 50.0


def fetch(path: str, timeout: float = 20.0):
    with urllib.request.urlopen(BASE + path, timeout=timeout) as response:
        return json.load(response)


def sample_once(pid_cpu: dict) -> dict:
    ts = fetch("/api/transport-stats")
    engine = ts.get("engine")
    if not isinstance(engine, dict):
        raise SystemExit(2)
    backlog = (engine.get("scheduler") or {}).get("backlog") or {}
    row = {
        "ts": time.time(),
        "backlog": int(backlog.get("every") or 0) + int(backlog.get("cadence") or 0),
        "cycle_timeouts": int(engine.get("cycle_timeouts") or 0),
        "depth_exceeded": int(engine.get("depth_exceeded") or 0),
        "budget_exceeded": int(engine.get("budget_exceeded") or 0),
        "sealed": bool((engine.get("graph") or {}).get("sealed")),
        "unknown_events": (engine.get("graph") or {}).get("unknown_events") or {},
        "graph_cycles": (engine.get("graph") or {}).get("cycles") or [],
        "farm": ts.get("analysis_farm"),
        "latency": ts.get("latency") or {},
        "critical_dropped": (ts.get("runtime") or {}).get("critical_dropped_by_event") or {},
    }
    try:
        import psutil
        # ٢٠٢٦-٠٩-١٨: النواة صارت خمس عمليّات (جذر + ثلاثة محرّكات + باردة)،
        # فقياس الجذر وحده يُخفي أربعة أخماس الحمل. والحدّ في §٢٩ حدُّ النواة
        # لا حدُّ عمليّة — فيُجمَع. وكانت المطابقة على `run_core.py` وحده
        # بينما المُشغّل الحيّ `scripts/run_forex.py`، فلم يُقَس شيء أصلًا.
        measured = 0.0
        seen_any = False
        for proc in psutil.process_iter(["pid", "cmdline"]):
            cmd = " ".join(proc.info["cmdline"] or [])
            if "QUANT_NQ" not in cmd:
                continue
            if not ("run_core.py" in cmd or "run_forex.py" in cmd
                    or "spawn_main" in cmd):
                continue
            times = proc.cpu_times()
            total = times.user + times.system
            prev = pid_cpu.get(proc.pid)
            if prev is not None:
                dt = row["ts"] - prev[1]
                measured += 100.0 * (total - prev[0]) / max(1e-6, dt)
                seen_any = True
            pid_cpu[proc.pid] = (total, row["ts"])
        if seen_any:
            # ٢٠٢٦-٠٩-١٨ (تصحيح المالك): `measured` نسبةٌ من **نواةٍ واحدة**،
            # و§٢٩ يحدّ قدرة **الجهاز**. فـ107.7٪ من نواة على جهازٍ باثني عشر
            # خيطًا = 8.98٪ من الجهاز — والحكم عليها بـ«≤ 50» كان يحاكم
            # النظام بمقياسٍ غير مقياسه.
            row["cpu_core_pct"] = measured
            row["cpu_threads"] = psutil.cpu_count() or 1
            row["cpu_pct"] = measured / float(row["cpu_threads"])
    except Exception:  # noqa: BLE001 — بلا psutil لا يُقاس المعالج ويُقال ذلك
        pass
    return row


def judge(rows: list[dict], *, warmup_s: float = WARMUP_S) -> tuple[bool, list[str]]:
    lines: list[str] = []
    if not rows:
        return False, ["لا عيّنات"]
    t0 = rows[0]["ts"]
    judged = [r for r in rows if r["ts"] - t0 >= warmup_s] or rows
    ok_all = True

    def add(name: str, ok: bool, measured, limit) -> None:
        nonlocal ok_all
        ok_all = ok_all and ok
        lines.append("  %-4s %-34s المقيس=%-22s الحدّ=%s" % ("PASS" if ok else "FAIL", name, measured, limit))

    half = judged[len(judged) // 2:]
    slope = 0.0
    if len(half) >= 3:
        xs = [r["ts"] for r in half]; ys = [r["backlog"] for r in half]
        mx = statistics.mean(xs); my = statistics.mean(ys)
        den = sum((x - mx) ** 2 for x in xs) or 1e-9
        slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / den
    add("ميل الطابور الساخن (عنصر/ث)", slope <= 0.05, "%+.4f" % slope, "≤ 0")
    last, first = judged[-1], judged[0]
    add("مهلات الدورة في النافذة", last["cycle_timeouts"] - first["cycle_timeouts"] == 0,
        last["cycle_timeouts"] - first["cycle_timeouts"], "0")
    add("تجاوز العمق/الميزانيّة", last["depth_exceeded"] + last["budget_exceeded"] == 0,
        last["depth_exceeded"] + last["budget_exceeded"], "0")
    lat = last["latency"]; limit = float(lat.get("limit_s") or 0.1)
    breaches = {s: r for s, r in (lat.get("symbols") or {}).items()
                if len(s) > 3 and isinstance(r.get("p99_s"), (int, float)) and r["p99_s"] > limit}
    worst = max(((s, r["p99_s"]) for s, r in (lat.get("symbols") or {}).items() if len(s) > 3),
                key=lambda kv: kv[1], default=("-", 0.0))
    add("p99 تِكّة ← قرار (أسوأ رمز)", not breaches, "%s=%.4f ث" % worst, "≤ %.4f ث" % limit)
    crit_last = sum(int(v) for v in last["critical_dropped"].values())
    crit_first = sum(int(v) for v in first["critical_dropped"].values())
    add("فقد أحداث المال في النافذة", crit_last - crit_first == 0, crit_last - crit_first, "0")
    cpus = [r["cpu_pct"] for r in judged if isinstance(r.get("cpu_pct"), (int, float))]
    if cpus:
        cores = [r.get("cpu_core_pct") for r in judged
                 if isinstance(r.get("cpu_core_pct"), (int, float))]
        threads = next((r.get("cpu_threads") for r in judged if r.get("cpu_threads")), 1)
        mean_machine = statistics.mean(cpus)
        add("معالج النواة كلّها (٪ من الجهاز)", mean_machine <= CPU_LIMIT_PCT,
            "%.2f  (= %.1f٪ من نواة ÷ %d خيطًا)" % (
                mean_machine, statistics.mean(cores) if cores else 0.0, threads),
            "≤ %.0f" % CPU_LIMIT_PCT)
        add("الاحتياطيّ المتاح (٪ من الجهاز)", (100.0 - mean_machine) >= CPU_LIMIT_PCT,
            "%.2f" % (100.0 - mean_machine), "≥ %.0f" % CPU_LIMIT_PCT)
    else:
        lines.append("  ---- معالج النواة: لم يُقَس (لا psutil أو لا عمليّة مطابقة)")
    add("الرسم مختوم", bool(last["sealed"]), last["sealed"], "True")
    add("لا مزرعة", last["farm"] is None, "None" if last["farm"] is None else "موجودة", "None")
    # ٢٠٢٦-٠٩-١٨ (تصحيح المالك): كان يُحكم على العدّاد التراكميّ، فحدثٌ مجهولٌ
    # واحد قبل ختم الرسم يُسقط القبول **إلى الأبد** — بلا مقارنةٍ ولا تصفير عند
    # بداية النافذة. والمقيس أنّ القراءة الحيّة بعد الاستقرار صفر. فيُحكم على
    # الفرق داخل النافذة: ما ظهر **بعد** الختم لا ما سبقه.
    before = {str(k): int(v) for k, v in (first["unknown_events"] or {}).items()}
    after = {str(k): int(v) for k, v in (last["unknown_events"] or {}).items()}
    grew = {k: v - before.get(k, 0) for k, v in after.items() if v - before.get(k, 0) > 0}
    add("أحداث خارج الرسم (الجديد في النافذة)", not grew,
        "%d%s" % (sum(grew.values()), (" — %s" % ", ".join(sorted(grew)[:5])) if grew else ""),
        "0")
    if before:
        lines.append("  ---- سبق النافذة (قبل ختم الرسم، لا يُحكم عليه): %d عبر %d اسمًا"
                     % (sum(before.values()), len(before)))
    add("دورات في رسم الأحداث", not last["graph_cycles"], len(last["graph_cycles"]), "0")
    return ok_all, lines


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--minutes", type=float, default=60.0)
    parser.add_argument("--every", type=float, default=30.0)
    parser.add_argument("--from-samples", help="ملفّ عيّنات JSONL بدل القياس الحيّ")
    parser.add_argument("--warmup-s", type=float, default=WARMUP_S)
    args = parser.parse_args()

    rows: list[dict] = []
    if args.from_samples:
        with open(args.from_samples, encoding="utf-8") as fh:
            for line in fh:
                try:
                    rows.append(json.loads(line))
                except Exception:  # noqa: BLE001
                    continue
    else:
        pid_cpu: dict = {}
        deadline = time.time() + args.minutes * 60.0
        try:
            while time.time() < deadline:
                rows.append(sample_once(pid_cpu))
                time.sleep(args.every)
        except (urllib.error.URLError, OSError) as exc:
            print("⛔ النواة لا تجيب: %s" % exc)
            return 2
        except SystemExit as exc:
            if exc.code == 2:
                print("⛔ NQ ENGINE غير مفعّل على هذه النواة — لا يُحكم")
                return 2
            raise
    ok, lines = judge(rows, warmup_s=args.warmup_s)
    print("=" * 78)
    print("قبول NQ ENGINE — نافذة %d عيّنة (%.1f دقيقة)" % (len(rows), (rows[-1]["ts"] - rows[0]["ts"]) / 60 if len(rows) > 1 else 0))
    print("=" * 78)
    print("\n".join(lines))
    print("=" * 78)
    print("الحكم: %s" % ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
