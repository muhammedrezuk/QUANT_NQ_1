# -*- coding: utf-8 -*-
"""تكافؤ NQ ENGINE — الشريط نفسه على الناقل القديم وعلى المحرّك، والقرار واحد.

§٢٧ من ورقة المحرّك: «قبل أيّ تحسين CPU يجب تثبيت: same input → old engine →
reference output · same input → new engine → new output · outputs identical».
ولا يكفي `process started` ولا `queue empty`.

ثلاث خطوات، كلٌّ أمرٌ:

    record   يسجّل كلّ ما يمرّ على `ws/events` من النواة الحيّة إلى JSONL
    replay   يُقلع كتلة ذرّات (افتراضًا 100-499) في هذه العمليّة على ناقلٍ
             (`--mode old`) أو على المحرّك (`--mode new`)، ويُعيد عليها
             الأحداث **الخارجيّة** من الشريط بالترتيب، ويصرّف بعد كلّ حدث
             (فلا دمج ولا تزاحم — التكافؤ يُقاس بلا ضغط)، ويكتب كلّ ما نشرته
             الكتلة
    compare  يقارن مخرجَي replay: بالعدّ لكلّ (حدث، رمز)، وبالحمولة بعد نزع
             الحقول المتغيّرة (هويّات، أزمنة) — ويعلن نسبة تكافؤ القرارات

⛔ الإعادة تعمل على جذر تشغيلٍ مؤقّت: لا مخزن حيّ يُلمس ولا سجلّ.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import tempfile
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

VOLATILE_KEYS = {
    "event_id", "trace_id", "parent_event_id", "parent_event", "timestamp", "source",
    "published_at", "received_at", "exchange_timestamp", "cycle_id", "seq",
}
VOLATILE_RE = re.compile(r"(?:^|_)(at|ts|time|timestamp|latency|elapsed|duration|age|uptime|"
                         r"clock|epoch|ms|seconds|s)$")


def parse_ranges(spec: str) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            low, high = part.split("-", 1)
            ranges.append((int(low), int(high)))
        else:
            ranges.append((int(part), int(part)))
    return ranges


def in_ranges(number: int, ranges: list[tuple[int, int]]) -> bool:
    return any(low <= number <= high for low, high in ranges)


# ── record ────────────────────────────────────────────────────────────────

async def _record(seconds: float, out: Path, url: str) -> int:
    import websockets  # يأتي مع uvicorn[standard]

    count = 0
    t_end = time.time() + seconds
    async with websockets.connect(url, subprotocols=["quant-nq"], max_size=None,
                                  ping_interval=20) as ws:
        with out.open("w", encoding="utf-8") as fh:
            while time.time() < t_end:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=max(1.0, t_end - time.time()))
                except asyncio.TimeoutError:
                    break
                try:
                    doc = json.loads(raw)
                except Exception:  # noqa: BLE001
                    continue
                if doc.get("type") != "event":
                    continue
                fh.write(json.dumps({"t": time.time(), "name": doc.get("name"),
                                     "payload": doc.get("payload")}, ensure_ascii=False) + "\n")
                count += 1
    return count


def cmd_record(args: argparse.Namespace) -> int:
    out = Path(args.out)
    count = asyncio.run(_record(args.seconds, out, args.url))
    print("سُجّل %d حدثًا في %s" % (count, out))
    return 0 if count else 1


# ── replay ────────────────────────────────────────────────────────────────

def _prepare_isolated_runtime() -> Path:
    """جذر تشغيلٍ مؤقّت — كما يفعل `conftest.py`: لا مخزن حيّ يُلمس."""
    runtime = Path(tempfile.mkdtemp(prefix="nq_parity_runtime_"))
    (runtime / "var").mkdir(parents=True, exist_ok=True)
    os.environ["QUANT_RUNTIME_ROOT"] = str(runtime)
    os.environ["QUANT_CORE_STATE_ROOT"] = str(runtime / "var")
    os.environ["QUANT_ANALYSIS_SETTINGS_DB"] = str(runtime / "analysis_settings.db")
    os.environ.setdefault("QUANT_ATOMS_ROOT", str(ROOT / "atoms"))
    os.environ.setdefault("QUANT_CORE_DOMAIN", "forex")
    os.environ.setdefault("QUANT_LOCAL_MODE", "1")
    return runtime


def _auto_ids(atoms_root: Path, ranges: list[tuple[int, int]]) -> tuple[set[int], dict[int, str]]:
    from core.manifest_loader import scan

    discovery = scan(atoms_root)
    chosen: set[int] = set()
    names: dict[int, str] = {}
    for atom in discovery.atoms:
        manifest = atom.manifest
        mode = getattr(manifest.startup_mode, "value", str(manifest.startup_mode))
        names[int(manifest.id)] = manifest.name
        if mode == "auto" and in_ranges(int(manifest.id), ranges):
            chosen.add(int(manifest.id))
    return chosen, names


def _build_bus(mode: str, cold_sections: list[tuple[int, int]]):  # noqa: ANN202
    from transport.owned_event_bus import OwnedEventBus

    critical = ("execution.", "decision.", "risk.", "trading.", "platform.trade",
                "market.outcome", "feed.")
    if mode == "old":
        return OwnedEventBus(worker_count=0, partitioned_ownership=True, mailbox_max_events=1024,
                             cold_sections=cold_sections, scope_groups=4,
                             critical_prefixes=critical)
    from engine import NQEngine
    cold = OwnedEventBus(worker_count=2, partitioned_ownership=False, mailbox_max_events=1024,
                         cold_sections=cold_sections, scope_groups=1, critical_prefixes=critical)
    return NQEngine(cold_bus=cold, cadence_sections=[(150, 499)], cold_sections=cold_sections)


async def _replay(args: argparse.Namespace) -> dict[str, Any]:
    from core.bootloader import Bootloader
    from core.journal import Journal
    from core.lifecycle import call_lifecycle
    from core.metrics import Metrics
    from core.registry import Registry

    runtime = _prepare_isolated_runtime()
    atoms_root = Path(os.environ["QUANT_ATOMS_ROOT"])
    ranges = parse_ranges(args.sections)
    include, names = _auto_ids(atoms_root, ranges)
    cold_sections = parse_ranges(args.cold_sections)
    bus = _build_bus(args.mode, cold_sections)
    registry = Registry()
    bootloader = Bootloader(atoms_root, registry, bus, Journal(path=None), Metrics())

    include_names = {str(i) for i in include}
    outputs: list[dict[str, Any]] = []
    inputs_replayed = 0

    async def collect(name: str, payload: Any) -> None:
        if not isinstance(payload, dict):
            return
        if str(payload.get("source") or "") in include_names:
            outputs.append({"name": name, "payload": dict(payload)})

    t0 = time.perf_counter()
    report = await bootloader.boot(include_ids=set(include))
    boot_s = time.perf_counter() - t0
    bus.subscribe_all(collect, subscriber="cold:parity", isolate_payload=False)
    await bus.drain(timeout_s=10.0)
    boot_outputs = len(outputs)

    t1 = time.perf_counter()
    limit = int(args.limit or 0)
    with Path(args.input).open(encoding="utf-8") as fh:
        for line in fh:
            if limit and inputs_replayed >= limit:
                break
            try:
                row = json.loads(line)
            except Exception:  # noqa: BLE001
                continue
            name, payload = row.get("name"), row.get("payload")
            if not name or not isinstance(payload, dict):
                continue
            source = str(payload.get("source") or "")
            if source in include_names:
                continue                     # تُولَّد داخل الكتلة — لا تُعاد
            if str(name).startswith("core."):
                continue                     # أحداث دورة حياة النواة الحيّة لا تخصّ هذه العمليّة
            await bus.publish(name, dict(payload), publisher=source or "replay")
            inputs_replayed += 1
            if not args.no_drain:
                await bus.drain(timeout_s=float(args.drain_timeout))
    await bus.drain(timeout_s=30.0)
    replay_s = time.perf_counter() - t1

    # إيقافٌ نظيف — ولا يُترك مورد مفتوحًا خلفنا.
    for record in list(registry.all()):
        for phase in ("stop", "shutdown"):
            try:
                await call_lifecycle(getattr(record.instance, phase)(), phase, timeout=10.0)
            except Exception:  # noqa: BLE001
                pass
    try:
        closer = bus.close()
        if asyncio.iscoroutine(closer):
            await closer
    except Exception:  # noqa: BLE001
        pass

    stats = bus.transport_stats() if hasattr(bus, "transport_stats") else {}
    engine_stats = stats.get("engine") or {}
    summary = {k: engine_stats.get(k) for k in (
        "cycles", "cycle_timeouts", "depth_exceeded", "budget_exceeded", "cycle_mean_s",
        "cycle_worst_s", "cycle_worst_root", "coalesced_in_cycle")}
    sched = engine_stats.get("scheduler") or {}
    summary["cadence"] = {k: sched.get(k) for k in (
        "every_admitted", "cadence_admitted", "coalesced", "cycles_every", "cycles_cadence",
        "every_backlog_peak", "cadence_batch_peak")}
    summary["overrun_by_subscriber"] = engine_stats.get("overrun_by_subscriber")
    summary["error_by_subscriber"] = engine_stats.get("error_by_subscriber")
    summary["last_error_by_subscriber"] = engine_stats.get("last_error_by_subscriber")
    runtime_stats = stats.get("runtime") or {}
    summary["old_bus_workers"] = [
        {k: w.get(k) for k in ("worker_id", "processed", "dropped", "coalesced", "queued")}
        for w in (runtime_stats.get("workers") or [])]
    result = {
        "mode": args.mode,
        "engine_summary": summary,
        "sections": args.sections,
        "requested": sorted(include),
        "booted": list(report.booted),
        "failed": list(report.failed),
        "failed_reasons": {int(i): (registry.find(int(i)).last_error if registry.find(int(i)) else None)
                           for i in report.failed},
        "excluded": list(report.excluded),
        "boot_s": round(boot_s, 2),
        "replay_s": round(replay_s, 2),
        "inputs_replayed": inputs_replayed,
        "boot_outputs": boot_outputs,
        "outputs": len(outputs),
        "runtime": str(runtime),
        "stats": stats,
    }
    out = Path(args.out)
    with out.open("w", encoding="utf-8") as fh:
        fh.write(json.dumps({"meta": {k: v for k, v in result.items() if k != "stats"}},
                            ensure_ascii=False) + "\n")
        for row in outputs:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    return result


def cmd_replay(args: argparse.Namespace) -> int:
    result = asyncio.run(_replay(args))
    meta = {k: v for k, v in result.items() if k not in ("stats", "requested", "booted")}
    if args.no_drain:
        meta["engine_summary"] = result.get("engine_summary")
    else:
        meta.pop("engine_summary", None)
    meta["booted_count"] = len(result["booted"])
    print(json.dumps(meta, ensure_ascii=False, indent=1))
    return 0 if not result["failed"] else 2


# ── compare ───────────────────────────────────────────────────────────────

def _normalize(value: Any) -> Any:
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            k = str(key)
            if k in VOLATILE_KEYS or VOLATILE_RE.search(k):
                continue
            out[k] = _normalize(item)
        return out
    if isinstance(value, list):
        return [_normalize(v) for v in value]
    if isinstance(value, float):
        return round(value, 8)
    return value


def _load(path: Path) -> tuple[dict, list[dict]]:
    rows: list[dict] = []
    meta: dict = {}
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            doc = json.loads(line)
            if "meta" in doc:
                meta = doc["meta"]
            else:
                rows.append(doc)
    return meta, rows


def _key(row: dict) -> tuple[str, str, str]:
    payload = row.get("payload") or {}
    return (str(row.get("name")), str(payload.get("symbol") or ""),
            str(payload.get("section_id") or payload.get("analyzer_id")
                or payload.get("strategy_id") or ""))


def cmd_compare(args: argparse.Namespace) -> int:
    meta_a, rows_a = _load(Path(args.a))
    meta_b, rows_b = _load(Path(args.b))
    by_a: dict[tuple, list] = defaultdict(list)
    by_b: dict[tuple, list] = defaultdict(list)
    for row in rows_a:
        by_a[_key(row)].append(_normalize(row.get("payload") or {}))
    for row in rows_b:
        by_b[_key(row)].append(_normalize(row.get("payload") or {}))

    keys = sorted(set(by_a) | set(by_b))
    count_mismatch = []
    payload_mismatch = []
    identical = 0
    decision_total = 0
    decision_ok = 0
    for key in keys:
        seq_a, seq_b = by_a.get(key, []), by_b.get(key, [])
        is_decision = key[0].startswith("decision.")
        if len(seq_a) != len(seq_b):
            count_mismatch.append((key, len(seq_a), len(seq_b)))
            if is_decision:
                decision_total += max(len(seq_a), len(seq_b))
            continue
        pairs = list(zip(seq_a, seq_b))
        diff = [i for i, (x, y) in enumerate(pairs) if x != y]
        if diff:
            payload_mismatch.append((key, len(pairs), len(diff), pairs[diff[0]]))
        else:
            identical += 1
        if is_decision:
            decision_total += len(pairs)
            decision_ok += len(pairs) - len(diff)

    print("الشريط A: %s  (%d مخرجًا · %d مدخلًا)" % (meta_a.get("mode"), len(rows_a), meta_a.get("inputs_replayed", 0)))
    print("الشريط B: %s  (%d مخرجًا · %d مدخلًا)" % (meta_b.get("mode"), len(rows_b), meta_b.get("inputs_replayed", 0)))
    print("مفاتيح (حدث، رمز، قسم): %d · متطابقة تمامًا: %d · اختلاف عدد: %d · اختلاف حمولة: %d"
          % (len(keys), identical, len(count_mismatch), len(payload_mismatch)))
    if decision_total:
        print("تكافؤ القرارات (decision.*): %d / %d = %.4f%%"
              % (decision_ok, decision_total, 100.0 * decision_ok / decision_total))
    else:
        print("تكافؤ القرارات: لا أحداث decision.* في الشريطين — الكتلة لم تبلغ قرارًا")
    for key, na, nb in count_mismatch[: args.show]:
        print("  [عدد] %-45s %-8s %-10s A=%d B=%d" % (key[0], key[1], key[2], na, nb))
    for key, n, d, example in payload_mismatch[: args.show]:
        print("  [حمولة] %-45s %-8s %-10s %d/%d مختلف" % (key[0], key[1], key[2], d, n))
        if args.verbose:
            x, y = example
            for field in sorted(set(x) | set(y)):
                if x.get(field) != y.get(field):
                    print("        %s: A=%r  B=%r" % (field, x.get(field), y.get(field)))
    report = {
        "keys": len(keys), "identical": identical,
        "count_mismatch": len(count_mismatch), "payload_mismatch": len(payload_mismatch),
        "decision_total": decision_total, "decision_ok": decision_ok,
        "decision_equivalence_pct": (100.0 * decision_ok / decision_total) if decision_total else None,
    }
    if args.report:
        Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0 if not count_mismatch and not payload_mismatch else 1


# ── CLI ───────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)

    rec = sub.add_parser("record")
    rec.add_argument("--seconds", type=float, default=300.0)
    rec.add_argument("--out", required=True)
    rec.add_argument("--url", default="ws://127.0.0.1:8010/ws/events")
    rec.set_defaults(func=cmd_record)

    rep = sub.add_parser("replay")
    rep.add_argument("--mode", choices=["old", "new"], required=True)
    rep.add_argument("--input", required=True)
    rep.add_argument("--out", required=True)
    rep.add_argument("--sections", default="100-499")
    rep.add_argument("--cold-sections", default="700-749")
    rep.add_argument("--limit", type=int, default=0, help="أقصى عدد مدخلات تُعاد (0 = الكلّ)")
    rep.add_argument("--no-drain", action="store_true", help="بلا تصريف بعد كلّ حدث — اختبار ضغط لا تكافؤ")
    rep.add_argument("--drain-timeout", type=float, default=5.0)
    rep.set_defaults(func=cmd_replay)

    cmp_ = sub.add_parser("compare")
    cmp_.add_argument("a")
    cmp_.add_argument("b")
    cmp_.add_argument("--show", type=int, default=25)
    cmp_.add_argument("--verbose", action="store_true")
    cmp_.add_argument("--report")
    cmp_.set_defaults(func=cmd_compare)

    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
