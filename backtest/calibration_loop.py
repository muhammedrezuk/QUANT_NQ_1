# -*- coding: utf-8 -*-
"""عيارٌ مستمرّ على الجهاز — يدور على طابور تجارب الاختبار التاريخيّ ويكتب نتائجها، بلا انتظار أحد.

ختم المالك ٢٠٢٦-١٠-٠٦ «NQ صلاحية كاملة»: «شغل بايثون مستمر بقلب مشروع … تعتمد معايرة … لا تلاقي
كل حواف لازمة وتخلي هل سستم يربح». وقبلها: الاختبارات يشغّلها الجهاز، لا تُراقَب من المحادثة.

· الطابور  `forex_runtime/var/backtest_runs/calibration/queue.jsonl` — سطرٌ لكلّ تجربة:
            {"name": "...", "args": ["--from", "...", ...], "note": "لماذا"} (وسائط `backtest.full_replay`).
· النتائج  `results.jsonl` — سطرٌ لكلّ تجربةٍ منتهية: وسائطها وخلاصتها كاملة.
· الحالة   `state.json` — ما يجري الآن وما انتهى، يُكتب كلّ دورة.
· الإيقاف  ملفّ `stop` في المجلّد نفسه — يُكمل الجاري ولا يبدأ جديدًا ثمّ يخرج.
· كلّ تجربةٍ منتهية تُسجَّل في `panel_runs.json` (النوع «عيار») فتظهر في صفحة «باك تست».
· لا يحذف شيئًا، والتجربة بالاسم نفسه لا تُعاد.

التشغيل (من جذر المشروع، في الخلفيّة):
    vendor\\python\\runtime\\python.exe -m backtest.calibration_loop --slots 4
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RUNS_DIR = ROOT / "forex_runtime" / "var" / "backtest_runs"
HOME = RUNS_DIR / "calibration"
QUEUE = HOME / "queue.jsonl"
RESULTS = HOME / "results.jsonl"
STATE = HOME / "state.json"
STOP = HOME / "stop"
REGISTRY = RUNS_DIR / "panel_runs.json"
PYTHON = ROOT / "vendor" / "python" / "runtime" / "python.exe"


def _lines(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                if isinstance(row, dict):
                    rows.append(row)
    except OSError:
        pass
    return rows


def _append(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def _brief(summary: dict[str, Any]) -> dict[str, Any]:
    """الأرقام التي يُحكم بها — من خلاصة التشغيل الواحد أو المدموج كما هي."""
    balance = summary.get("الرصيد") or {}
    return {"صافي": summary.get("صافي", balance.get("صافي")),
            "صفقات": summary.get("صفقات_مغلقة"),
            "نسبة_الربح": summary.get("نسبة_الربح"),
            "معامل_الربح": summary.get("معامل_الربح"),
            "أقصى_سحب": summary.get("أقصى_سحب_على_الإغلاقات", balance.get("أقصى_سحب")),
            "لكلّ_رمز": summary.get("لكلّ_رمز"),
            "أوامر_دخول": summary.get("أوامر_دخول")}


def _register(name: str, item: dict[str, Any], status: str, started: float, brief: dict[str, Any]) -> None:
    try:
        rows = json.loads(REGISTRY.read_text(encoding="utf-8"))
        rows = rows if isinstance(rows, list) else []
    except (OSError, ValueError):
        rows = []
    args = [str(a) for a in item.get("args") or []]

    def opt(key: str, default: str = "") -> str:
        return args[args.index(key) + 1] if key in args and args.index(key) + 1 < len(args) else default

    def epoch(text: str) -> float | None:
        try:
            return float(text)
        except ValueError:
            try:
                from datetime import datetime, timezone
                return datetime.fromisoformat(text).replace(tzinfo=timezone.utc).timestamp()
            except ValueError:
                return None
    rows.append({"name": name, "pid": 0, "status": status, "mode": "calibration",
                 "started_at": started, "ended_at": time.time(), "note": item.get("note", ""),
                 "from": epoch(opt("--from")), "to": epoch(opt("--to")),
                 "symbols": [s for s in opt("--symbols").split(",") if s],
                 "source": opt("--source", "recorded"), "workers": int(opt("--workers", "1") or 1),
                 "request": {"args": args, "env": item.get("env")}, "brief": brief})
    REGISTRY.write_text(json.dumps(rows[-200:], ensure_ascii=False, indent=1), encoding="utf-8")


def _launch(item: dict[str, Any]) -> tuple[str, subprocess.Popen, float]:
    name = "calib-%s" % item["name"]
    out = RUNS_DIR / name
    out.mkdir(parents=True, exist_ok=True)
    args = [str(PYTHON), "-u", "-m", "backtest.full_replay", *map(str, item.get("args") or []),
            "--out", str(out), "--name", name]
    log = (out / "panel.log").open("w", encoding="utf-8")
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    proc = subprocess.Popen(args, cwd=str(ROOT), stdout=log, stderr=subprocess.STDOUT, creationflags=flags,
                            env={**os.environ, "PYTHONIOENCODING": "utf-8", **(item.get("env") or {})})
    return name, proc, time.time()


def _collect(name: str, item: dict[str, Any], proc: subprocess.Popen, started: float) -> dict[str, Any]:
    out = RUNS_DIR / name
    try:
        summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
        status = "done"
    except (OSError, ValueError):
        summary, status = {}, "failed"
    tail = ""
    if status == "failed":
        try:
            tail = "\n".join((out / "panel.log").read_text(encoding="utf-8", errors="replace").splitlines()[-8:])
        except OSError:
            pass
    brief = _brief(summary)
    row = {"name": item["name"], "run": name, "status": status, "code": proc.returncode,
           "started": started, "ended": time.time(), "wall_s": round(time.time() - started, 1),
           "args": item.get("args"), "env": item.get("env"), "note": item.get("note", ""),
           "brief": brief, "summary": summary, "error_tail": tail}
    _append(RESULTS, row)
    _register(name, item, status, started, brief)
    return row


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="عيارٌ مستمرّ: طابور تجارب الاختبار التاريخيّ")
    ap.add_argument("--slots", type=int, default=4, help="تجارب في وقتٍ واحد")
    ap.add_argument("--poll", type=float, default=10.0)
    args = ap.parse_args(argv)
    HOME.mkdir(parents=True, exist_ok=True)
    running: dict[str, tuple[dict[str, Any], subprocess.Popen, float]] = {}
    print("بدأ العيار المستمرّ: %d مقعد · الطابور %s" % (args.slots, QUEUE), flush=True)
    while True:
        for name, (item, proc, started) in list(running.items()):
            if proc.poll() is not None:
                row = _collect(name, item, proc, started)
                print("انتهت %s (%s) صافي=%s صفقات=%s" % (name, row["status"], row["brief"]["صافي"],
                                                            row["brief"]["صفقات"]), flush=True)
                del running[name]
        stopping = STOP.exists()
        if not stopping:
            done = {row.get("name") for row in _lines(RESULTS)}
            active = {item["name"] for item, _p, _s in running.values()}
            for item in _lines(QUEUE):
                if len(running) >= args.slots:
                    break
                if not item.get("name") or item["name"] in done or item["name"] in active:
                    continue
                name, proc, started = _launch(item)
                running[name] = (item, proc, started)
                active.add(item["name"])
                print("بدأت %s" % name, flush=True)
        STATE.write_text(json.dumps({
            "updated": time.time(), "slots": args.slots, "stopping": stopping,
            "running": [{"name": item["name"], "pid": proc.pid, "started": started}
                        for item, proc, started in running.values()]}, ensure_ascii=False, indent=1),
            encoding="utf-8")
        if stopping and not running:
            print("أُوقف بملفّ الإيقاف", flush=True)
            return 0
        time.sleep(args.poll)


if __name__ == "__main__":
    raise SystemExit(main())
