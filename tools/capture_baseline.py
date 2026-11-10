# -*- coding: utf-8 -*-
"""المرحلة ٠ — خطّ الأساس قبل أيّ تغيير في عقد التنفيذ ٢٠٢٦-٠٩-١٦.

⛔ **إلزاميّ قبل أيّ سطر.** عقد `UNRESOLVED-3` المعتمَد ينصّ على أنّ
أعدادًا كانت أصفارًا سترتفع أوّل ما يُوصَل العقد — لأنّ المسار الصامت
(١٥ ث) كان يسبق المسمّى (٣٠ ث). فبلا خطّ أساسٍ يُقرأ الكشفُ انحدارًا.

ثلاث نوافذ متباعدة، لا واحدة: لقطةٌ واحدة تُخطئ لأنّ السوق يتذبذب.
"""
from __future__ import annotations

import io
import json
import sys
import time
import urllib.request
from pathlib import Path

URL = "http://127.0.0.1:8010/api/transport-stats"
OUT = Path("var/telemetry/baseline")
WINDOW_S = 60.0
GAP_S = 30.0
ROUNDS = 3


def grab() -> tuple[dict, float]:
    with urllib.request.urlopen(URL, timeout=20) as fh:
        return json.loads(fh.read().decode("utf-8")), time.time()


def _sum_worker(doc: dict, field: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for worker in doc["runtime"]["workers"]:
        for key, value in (worker.get(field) or {}).items():
            out[key] = out.get(key, 0) + int(value)
    return out


def snapshot(doc: dict) -> dict:
    runtime = doc["runtime"]
    farm = doc.get("analysis_farm") or {}
    coordinators = farm.get("coordinators") or {}
    return {
        "dropped_by_event": _sum_worker(doc, "dropped_by_event"),
        "coalesced_by_event": _sum_worker(doc, "coalesced_by_event"),
        "dropped_by_subscriber": _sum_worker(doc, "dropped_by_subscriber"),
        "critical_dropped_by_event": dict(runtime.get("critical_dropped_by_event") or {}),
        "critical_prefixes": list(runtime.get("critical_prefixes") or []),
        "market_dropped": runtime.get("market_dropped"),
        "market_coalesced": runtime.get("market_coalesced"),
        "farm": {key: farm.get(key) for key in (
            "routed", "republished", "rejected_backpressure", "echoed_input_blocked",
            "unknown_results", "ordering_violations", "revivals", "revived_workers",
            "in_flight_messages", "uptime_s", "silent_for_s")},
        "coordinators": dict(coordinators),
        "workers": [{key: worker.get(key) for key in (
            "worker_id", "lane", "overload_state", "queued", "processed",
            "dropped", "coalesced", "busy_s_total")}
            for worker in runtime["workers"]],
    }


def delta(before: dict, after: dict, span: float) -> dict:
    def _map(name: str) -> dict[str, float]:
        a, b = before[name], after[name]
        rows = {k: b.get(k, 0) - a.get(k, 0) for k in set(a) | set(b)}
        return {k: round(v / span, 3) for k, v in sorted(rows.items(),
                                                        key=lambda kv: -kv[1]) if v > 0}

    def _flat(name: str) -> dict[str, float]:
        a, b = before[name], after[name]
        out = {}
        for key in sorted(set(a) | set(b)):
            x, y = a.get(key), b.get(key)
            if isinstance(x, (int, float)) and isinstance(y, (int, float)):
                out[key] = round(y - x, 3)
        return out

    return {
        "span_s": round(span, 2),
        "dropped_by_event_per_s": _map("dropped_by_event"),
        "coalesced_by_event_per_s": _map("coalesced_by_event"),
        "dropped_by_subscriber_per_s": _map("dropped_by_subscriber"),
        "critical_dropped_by_event": _map("critical_dropped_by_event"),
        "farm_delta": _flat("farm"),
        "coordinators_delta": _flat("coordinators"),
        "coordinators_absolute": after["coordinators"],
        "critical_prefixes_live": after["critical_prefixes"],
    }


def main() -> int:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    OUT.mkdir(parents=True, exist_ok=True)
    rounds = []
    for index in range(ROUNDS):
        before, t0 = grab()
        time.sleep(WINDOW_S)
        after, t1 = grab()
        row = delta(snapshot(before), snapshot(after), t1 - t0)
        row["at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        rounds.append(row)
        print("نافذة %d/%d · %.1f ث · %s" % (index + 1, ROUNDS, row["span_s"], row["at"]))
        for name, value in list(row["dropped_by_event_per_s"].items())[:4]:
            print("    أُسقط %-32s %8.1f/ث" % (name[:32], value))
        print("    المنسّقون: %s" % row["coordinators_delta"])
        if index < ROUNDS - 1:
            time.sleep(GAP_S)

    final, _ = grab()
    doc = {
        "purpose": "baseline قبل تنفيذ عقد UNRESOLVED 1-4",
        "contract": "سياق/عقد التنفيذ — تحويل UNRESOLVED 1-4 إلى تغييرات — 2026-09-16.md",
        "captured_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "window_s": WINDOW_S, "rounds": ROUNDS,
        "state_at_end": snapshot(final),
        "windows": rounds,
    }
    stamp = time.strftime("%Y%m%d-%H%M%S")
    path = OUT / ("baseline-%s.json" % stamp)
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n✅ حُفظ: %s" % path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
