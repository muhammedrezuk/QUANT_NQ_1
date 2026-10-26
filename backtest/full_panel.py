# -*- coding: utf-8 -*-
"""صفحة الاختبار التاريخيّ الكامل في اللوحة — الجهاز يشغّله، والصفحة تطلقه وتعرض نتيجته.

أمر المالك ٢٠٢٦-١٠-٠٦ («ليش انت عم تعمل باك تست … بينما سستم فيه باك تست … ابنيها كامل بهل صفحة nq»،
ثمّ «شيل منها كل شي اله علاقة بالقسم كريبتو القديم nq»): زرٌّ في صفحة «باك تست» يطلق
`backtest/full_replay.py` عمليّةً خلفيّة على الجهاز، ويحفظ سجلّ التشغيلات، ويقرأ تقريرها — ولا يحتاج
أحدًا يراقبه.

المسارات (يوجّهها `trade_replay.handle_backtest` إلى هنا):
    GET  /gov/backtest/full/catalog     البيانات المتاحة ونوافذها، الرموز، المفاتيح بقيمها المعتمدة الحيّة
    GET  /gov/backtest/full/runs        التشغيلات وحالاتها وتقدّمها
    GET  /gov/backtest/full/run/<اسم>   تقرير تشغيلٍ واحد: الملخّص والصفقات وأوامر الدخول
    POST /gov/backtest/full/start       إطلاق تشغيل
    POST /gov/backtest/full/stop        إيقاف تشغيلٍ جارٍ (وشرائحه)
"""
from __future__ import annotations

import csv
import json
import os
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "forex_runtime"
RUNS_DIR = RUNTIME / "var" / "backtest_runs"
REGISTRY = RUNS_DIR / "panel_runs.json"
TICKS_DB = RUNTIME / "var" / "store" / "market_data.db"
HISTORY_DB = RUNTIME / "var" / "history" / "ctrader_history.db"
SETTINGS_DB = RUNTIME / "var" / "store" / "analysis_settings.db"
PYTHON = ROOT / "vendor" / "python" / "runtime" / "python.exe"

SYMBOLS = ("XAUUSD", "BTCUSD", "USTEC", "US30", "US500", "EURUSD", "GBPUSD")
MAX_WORKERS = 6
# مفاتيح الذرّات القابلة للتجربة من الصفحة: (المفتاح، الذرّات، حقل الإعداد).
ATOM_KNOBS = {
    "prob_depth": ((350, 351, 352, 353, 354, 355, 356, 357, 359), "required_depth"),
    "prob_confidence": ((350, 351, 352, 353, 354, 355, 356, 357, 359), "confidence_threshold"),
    "strat_active": ((413,), "min_active_weight"),
    "strat_depth": ((400, 413), "required_depth"),
    "strat_confidence": ((400, 413), "confidence_threshold"),
}
ANALYZERS = ("trend", "momentum", "volatility", "volume", "spread", "candle", "gap", "session", "time",
             "correlation", "relative_strength", "velocity", "acceleration", "volume_quality", "noise")
CALIB_FIELDS = ("required_depth", "confidence_threshold", "strength_threshold", "stale_after_s",
                "direction_neutral_band", "weight")


def _ro(path: Path) -> sqlite3.Connection:
    return sqlite3.connect("file:%s?mode=ro" % path, uri=True, timeout=5.0)


def _registry() -> list[dict[str, Any]]:
    try:
        rows = json.loads(REGISTRY.read_text(encoding="utf-8"))
        return rows if isinstance(rows, list) else []
    except (OSError, ValueError):
        return []


def _save_registry(rows: list[dict[str, Any]]) -> None:
    REGISTRY.parent.mkdir(parents=True, exist_ok=True)
    REGISTRY.write_text(json.dumps(rows[-200:], ensure_ascii=False, indent=1), encoding="utf-8")


def _alive(pid: int) -> bool:
    if not pid:
        return False
    try:
        out = subprocess.run(["tasklist", "/FI", "PID eq %d" % pid, "/NH"], capture_output=True,
                             text=True, timeout=10, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return str(pid) in out.stdout
    except (OSError, subprocess.SubprocessError):
        return False


def _iso(ts: float | None) -> str | None:
    return None if not ts else datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%dT%H:%M")


# ─────────────────────────────────────────────────────────── الفهرس ──

def catalog() -> dict[str, Any]:
    windows: dict[str, Any] = {"recorded": None, "ctrader": {}}
    try:
        with _ro(TICKS_DB) as db:                           # فهرس الزمن: سريعٌ على قاعدةٍ ضخمة
            lo, hi = db.execute("SELECT MIN(occurred_at), MAX(occurred_at) FROM market_data").fetchone()
            windows["recorded"] = {"from": _iso(lo), "to": _iso(hi)}
    except sqlite3.Error:
        pass
    try:
        with _ro(HISTORY_DB) as db:
            for symbol in SYMBOLS:
                row = db.execute("SELECT MIN(ts_ms), MAX(ts_ms) FROM ticks_history WHERE symbol=? AND side=1",
                                 (symbol,)).fetchone()
                if row and row[0]:
                    windows["ctrader"][symbol] = {"from": _iso(row[0] / 1000), "to": _iso(row[1] / 1000)}
    except sqlite3.Error:
        pass
    params: list[dict[str, Any]] = []
    # ٢٠٢٦-١٠-٠٩ (ختم المالك «NQ» — إلغاء مفاتيح السرعة إلى الأرشيف): لا يُعرض للتجربة صفٌّ لا اسم له في الكود
    # (لا `DECLARED` ولا `DIALS`) — تغييره في النسخة لا يقرؤه شيء (يومها: المفاتيح الأربعة وتفعيل شخصيّة الأفق).
    from shared.decision_dials import DIALS
    from shared.parameter_registry import DECLARED
    known = set(DECLARED) | set(DIALS)
    try:
        with _ro(SETTINGS_DB) as db:
            for name, scope, value in db.execute("SELECT name, scope, value FROM parameters ORDER BY name"):
                if scope == "global" and name in known:
                    params.append({"name": name, "value": value})
    except sqlite3.Error:
        pass
    return {"ok": True, "windows": windows, "symbols": list(SYMBOLS), "parameters": params,
            "atom_knobs": list(ATOM_KNOBS), "analyzers": list(ANALYZERS), "calib_fields": list(CALIB_FIELDS),
            "max_workers": MAX_WORKERS, "year": YEAR_SOURCE}


# ٢٠٢٦-١٠-١٧ (ختم المالك «NQ»): «سنة القياس» مصدرٌ ثالث في الصفحة — «أداة وحدة … من قسم الباك تست، تُستعمل دايمًا من
# اللوحة» و«قياس على نفس السنة دايمًا». يطلق `backtest/year_measure.py`؛ وتقريره بشكل المالك (السنة · الأشهر · الأسابيع ·
# كلّ الصفقات) في `summary.json` و`trades.csv` كغيره.
YEAR_SOURCE = {"label": "سنة القياس 2023 — شموع الدقيقة", "from": "2023-01-01", "to": "2024-01-01", "symbol": "USTEC"}


# ٢٠٢٦-١٠-١٧ (ختم المالك «NQ» — أداة الباك تست الاحترافيّة): «منشئ التوليفة» — يختار المالك من الصفحة الرمز والفترة والبيانات
# والجهة والشروط من حقائق الذرّات الحقيقيّة (مخزن الحقائق)، وإدارة الصفقة والأخبار والوقت، ويشغّل؛ والنتيجة في مجلّدٍ باسم يوم
# الاختبار واسمه («الاختبار.md» و«النتيجة.md»). المحرّك `backtest/combo_engine.py`، والمخزن `backtest/facts_store.py`.
FACTS_STORE = RUNTIME / "var" / "facts_store"
#: ١٩/١٠ (المالك: «لازم تقدر تعملها من صفحة نفسها»): كلّ المخازن تظهر في الصفحة بنوعها — الكامل · السريع (داو والقمم والهيكل)
#: · البنية (قسم 200 مع 151) · التِّكّ الحقيقيّ (سلسلة السيولة على تِكّات سي‑تريدر).
STORE_KINDS = {"facts_store": "كامل", "facts_store_quick": "سريع", "facts_store_structure": "البنية", "facts_store_ticks": "التِّكّ الحقيقيّ"}


def _virtual_vocab(key: str) -> list[str]:
    from backtest import combo_engine as ce
    if key == "sessions.next_open":
        return [ce.EXCHANGE_AR[x] for x in ce.EXCHANGES]
    if key == "gap.opened":
        return [v for v in ce.GAP_AR.values() if v]
    if key.startswith("holiday."):
        return [v for k, v in ce.HOLIDAY_AR.items() if v and (key == "holiday.today" or k != "none")]
    return []


def combo_catalog() -> dict[str, Any]:
    from backtest import combo_engine as ce
    stores = []
    for index in sorted(p for root in STORE_KINDS for p in (RUNTIME / "var" / root).glob("*/*/index.json")):
        try:
            ix = json.loads(index.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        atoms: dict[str, Any] = {}
        for g in ix.get("groups", []):
            a = atoms.setdefault(g["atom"], {"id": g["atom"], "name": (ix.get("names", {}).get(g["atom"]) or g["atom"]).replace("_", " "),
                                             "frames": [], "fields": {}})
            if g["frame"] and g["frame"] not in a["frames"]:
                a["frames"].append(g["frame"])
            for f in g["fields"]:
                if f["key"] in ("as_of", "atom_id", "section_id", "computed_on", "period_start", "m.period_start", "contract_version"):
                    continue
                cur = a["fields"].setdefault(f["key"], {"key": f["key"], "label": ce.field_label(f["key"]), "kind": f["kind"],
                                                        "vocab": set(), "frames": []})
                cur["vocab"].update(f.get("vocab") or [])
                if g["frame"] not in cur["frames"]:
                    cur["frames"].append(g["frame"])
        for a in atoms.values():
            a["fields"] = [dict(v, vocab=sorted(v["vocab"])) for v in sorted(a["fields"].values(), key=lambda x: x["key"])]
        # ١٧/١٠ (المالك: «هدول مو قلتلك عملهم»): حقائق السياق والجلسات والعطل والأخبار والمستويات والأداء — تُحسب عند كلّ لحظة
        # قرارٍ بالكود المشترك نفسه الذي تقرؤه الذرّات الحيّة 123 و124 و109 و469.
        for vid, v in ce.VIRTUAL.items():
            atoms[vid] = {"id": vid, "name": v["name"], "frames": ["كلّ لحظة"], "fields": [
                {"key": k, "label": label, "kind": "word" if k in ce.WORD_FIELDS else "num", "frames": ["كلّ لحظة"],
                 "vocab": _virtual_vocab(k)} for k, label in v["fields"].items()]}
        stores.append({"symbol": ix.get("symbol"), "folder": index.parent.name, "from": index.parent.name.split("_")[0],
                       "path": str(index.parent), "kind": STORE_KINDS.get(index.parents[2].name, ""),
                       "ticks": "حقيقيّة" if ix.get("ticks") == "real" else "أربعة لكلّ دقيقة",
                       "to": index.parent.name.split("_")[-1], "minutes": ix.get("minutes"), "seconds": ix.get("seconds"),
                       "atoms": sorted(atoms.values(), key=lambda x: x["id"])})
    building = [r for r in _registry() if r.get("mode") == "store" and r.get("status") == "running"]
    return {"ok": True, "stores": stores, "defaults": ce.DEFAULTS, "frames": list(ce.FRAME_S), "symbols": list(SYMBOLS),
            "building": [{"name": r["name"], "symbol": r.get("symbols", [""])[0], "progress": _progress(RUNS_DIR / r["name"])}
                         for r in building]}


def _launch(name: str, args: list[str], row: dict[str, Any]) -> dict[str, Any]:
    out = RUNS_DIR / name
    out.mkdir(parents=True, exist_ok=True)
    log = (out / "panel.log").open("w", encoding="utf-8")
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    proc = subprocess.Popen([str(PYTHON), "-u", "-m", *args], cwd=str(ROOT), stdout=log, stderr=subprocess.STDOUT,
                            creationflags=flags, env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    rows = _registry()
    rows.append({"name": name, "pid": proc.pid, "status": "running", "started_at": time.time(), **row})
    _save_registry(rows)
    return {"ok": True, "name": name}


def combo_start(body: dict[str, Any]) -> dict[str, Any]:
    spec = body.get("spec") if isinstance(body.get("spec"), dict) else {}
    if not spec.get("symbol") or not spec.get("from") or not spec.get("to"):
        return {"ok": False, "error": "اختر الرمز والفترة"}
    chosen = Path(spec["store"]) if spec.get("store") else FACTS_STORE / spec["symbol"] / ("%s_%s" % (spec["from"], spec["to"]))
    if spec.get("store") and (RUNTIME / "var") not in chosen.parents:
        return {"ok": False, "error": "مخزنٌ خارج مخازن المنظومة"}
    if not (chosen / "index.json").exists():
        return {"ok": False, "error": "لا مخزن حقائق لهذا الرمز وهذه الفترة — ابنِه أوّلًا من الزرّ نفسه"}
    name = "combo-%s" % datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    out = RUNS_DIR / name
    out.mkdir(parents=True, exist_ok=True)
    (out / "spec.json").write_text(json.dumps(spec, ensure_ascii=False, indent=1), encoding="utf-8")
    return _launch(name, ["backtest.combo_engine", "--spec", str(out / "spec.json"), "--done", str(out / "done.txt")],
                   {"mode": "combo", "source": "store", "from": _epoch(spec["from"]), "to": _epoch(spec["to"]),
                    "symbols": [spec["symbol"]], "workers": 1, "request": {"name": spec.get("name") or ""}})


#: 2026-10-22 (the owner, «NQ»): every frame up or down by his rule, Nasdaq, one falling year and one rising -- two only.
#: Then (same day): «بدّي مؤشّرات مع داو تقول صاعد أو هابط، ما تشتري ولا تبيع، مع شموع» -- the owner's run is 3, and the
#: tools are compared with the candles' own direction.
DIRECTION_SPEC = {"name": "الناسداك — الأدوات مقابل الشموع — 2022 و2023", "symbol": "USTEC",
                  "years": [["2022-01-01", "2023-01-01"], ["2023-01-01", "2024-01-01"]],
                  "frames": ["M1", "M5", "M15", "M30", "H1", "H4", "D1", "W1", "MN1"], "runs": [3], "ahead": [1, 5],
                  "truth_run": 3, "tools": ["ema_order", "above50", "dow", "dow_ema"],
                  # then: «في إفادة من دمج 3 متوسّطات مع داو وشموع لمعرفة اتّجاه؟ … قيسها»
                  "combos": [["candles"], ["candles", "above50"], ["candles", "ema_order"], ["candles", "dow"],
                             ["candles", "above50", "ema_order", "dow"]],
                  # then: «لازم يكون عنّا اتّجاه واضح حقيقي» -- his heavy frames agreeing, read on five minutes and one
                  "align": {"heavy": ["H4", "H1", "M15"], "targets": ["M5", "M1"], "run": 3}}


#: Then: «الضبط على الماضي: نجرّب أعدادًا كثيرة … على 2022 و2023، ونختار الأعلى نتيجة» -- in-sample by his choice.
DIRECTION_FIT_SPEC = {"name": "الناسداك — 2022 و2023", "symbol": "USTEC",
                      "years": [["2022-01-01", "2023-01-01"], ["2023-01-01", "2024-01-01"]],
                      "frames": ["M1", "M5", "M15", "M30", "H1", "H4", "D1"], "ahead": [1, 5]}


def direction_start(body: dict[str, Any]) -> dict[str, Any]:
    runs()                                      # refresh the statuses first, as the page does every five seconds
    if any(r.get("mode") == "direction" and r.get("status") == "running" and _alive(int(r.get("pid") or 0)) for r in _registry()):
        return {"ok": False, "error": "قياس اتّجاه قائم الآن — انتظر انتهاءه"}
    # «الضبط على الماضي» (fit) · «هيك لازم يتعاير بالبداية — NQ» (describe: against the moves the eye sees afterwards)
    # «قيسه على سنة بنفس الإعدادات بدون ما يعرف — باك تست رسمي» (exam: chosen on 2022–2023, applied unchanged to 2024)
    for flag, arg, title in (("fit", "--direction-fit", "ضبط الاتّجاه على الماضي"),
                             ("describe", "--direction-describe", "معايرة الاتّجاه على موجات الماضي"),
                             ("exam", "--direction-exam", "امتحان الاتّجاه على 2024"),
                             # «نظام بدّك تعلّمو … فرجيه شارت كامل مشان يتعلّم» -- taught on 2022–2023, examined on 2024
                             ("learn", "--direction-learn", "تعليم الاتّجاه وامتحانه على 2024")):
        if not body.get(flag):
            continue
        spec = dict(DIRECTION_FIT_SPEC)
        if flag in ("exam", "learn"):
            spec.update({"train": spec["years"], "test": ["2024-01-01", "2025-01-01"], "targets": ["M5", "M15", "H1"],
                         # «غذّيه معلومات وأدوات — عنّا أدوات كتيرة وأقسام كتيرة»
                         "rich": bool(body.get("rich")), "sections": bool(body.get("sections"))})
        name = "direction-%s-%s" % (flag, datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S"))
        out = RUNS_DIR / name
        out.mkdir(parents=True, exist_ok=True)
        (out / "spec.json").write_text(json.dumps(spec, ensure_ascii=False, indent=1), encoding="utf-8")
        return _launch(name, ["backtest.combo_engine", arg, str(out / "spec.json"), "--done", str(out / "done.txt")],
                       {"mode": "direction", "source": "store", "from": _epoch(spec["years"][0][0]),
                        "to": _epoch(spec["years"][-1][1]), "symbols": [spec["symbol"]], "workers": 1,
                        "request": {"name": title}})
    spec = dict(DIRECTION_SPEC)
    name = "direction-%s" % datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    out = RUNS_DIR / name
    out.mkdir(parents=True, exist_ok=True)
    (out / "spec.json").write_text(json.dumps(spec, ensure_ascii=False, indent=1), encoding="utf-8")
    return _launch(name, ["backtest.combo_engine", "--direction", str(out / "spec.json"), "--done", str(out / "done.txt")],
                   {"mode": "direction", "source": "store", "from": _epoch(spec["years"][0][0]), "to": _epoch(spec["years"][-1][1]),
                    "symbols": [spec["symbol"]], "workers": 1, "request": {"name": spec["name"]}})


#: 2026-10-23 (the owner's paper «البحث عن استراتيجيّة رابحة», sealed «NQ»): the answer at every moment for both sides --
#: the structure stop, the thirds, every red line -- taught to the student from the tools' 147 readings, and examined on
#: two years, one falling and one rising, each taught on the years before it only. The Nasdaq first.
STRATEGY_SPEC = {"symbol": "USTEC", "exams": [["2022-01-01", "2023-01-01"], ["2023-01-01", "2024-01-01"]],
                 "train_from": "2018-01-01"}


def strategy_start(body: dict[str, Any]) -> dict[str, Any]:
    runs()                                      # refresh the statuses first, as the page does every five seconds
    if any(r.get("mode") == "strategy" and r.get("status") == "running" and _alive(int(r.get("pid") or 0)) for r in _registry()):
        return {"ok": False, "error": "بحثٌ قائم الآن — انتظر انتهاءه"}
    symbol = str(body.get("symbol") or STRATEGY_SPEC["symbol"]).upper()
    if symbol not in SYMBOLS:
        return {"ok": False, "error": "رمزٌ غير معروف"}
    spec = dict(STRATEGY_SPEC, symbol=symbol)
    name = "strategy-%s-%s" % (symbol, datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S"))
    out = RUNS_DIR / name
    out.mkdir(parents=True, exist_ok=True)
    (out / "spec.json").write_text(json.dumps(spec, ensure_ascii=False, indent=1), encoding="utf-8")
    return _launch(name, ["backtest.combo_engine", "--strategy-search", str(out / "spec.json"), "--done", str(out / "done.txt")],
                   {"mode": "strategy", "source": "store", "from": _epoch(spec["train_from"]),
                    "to": _epoch(spec["exams"][-1][1]), "symbols": [symbol], "workers": 1,
                    "request": {"name": "البحث عن استراتيجيّة رابحة"}})


#: 2026-10-23 (the owner's paper «مستويات المتداول وخطّة السيناريوهين», «حط هدول مع سستم حي nq» then «يقاس»): one spearhead
#: inside the live combination -- break-and-hold and false break at the trader's levels, on five-minute and on minute
#: candles -- beside the combination without it, on one falling and one rising year. The Nasdaq first.
LEVELS_SPEC = {"symbol": "USTEC", "years": [["2022-01-01", "2023-01-01"], ["2023-01-01", "2024-01-01"]]}


def levels_start(body: dict[str, Any]) -> dict[str, Any]:
    runs()
    if any(r.get("mode") == "levels" and r.get("status") == "running" and _alive(int(r.get("pid") or 0)) for r in _registry()):
        return {"ok": False, "error": "قياس المستويات قائم الآن — انتظر انتهاءه"}
    symbol = str(body.get("symbol") or LEVELS_SPEC["symbol"]).upper()
    if symbol not in SYMBOLS:
        return {"ok": False, "error": "رمزٌ غير معروف"}
    spec = dict(LEVELS_SPEC, symbol=symbol)
    if body.get("target") == "map":                # the owner's «قيس» (23/10): the next level from his map alone
        spec["variants"] = "map"
    elif body.get("target") == "notime":           # the owner (24/10): the live combination without law 21, for knowledge
        spec["variants"] = "notime"
    name = "levels-%s-%s" % (symbol, datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S"))
    out = RUNS_DIR / name
    out.mkdir(parents=True, exist_ok=True)
    (out / "spec.json").write_text(json.dumps(spec, ensure_ascii=False, indent=1), encoding="utf-8")
    return _launch(name, ["backtest.combo_engine", "--levels-plan", str(out / "spec.json"), "--done", str(out / "done.txt")],
                   {"mode": "levels", "source": "store", "from": _epoch(spec["years"][0][0]), "to": _epoch(spec["years"][-1][1]),
                    "symbols": [symbol], "workers": 1, "request": {"name": "مستويات المتداول والسيناريوهان"}})


#: 2026-10-25 (the owner, «قيس شغلات سستم»): the live combination as the code holds it after laws 17 and 21 changed, on its
#: seven pairs, one falling and one rising year, and the seven together on one account with the saved limits -- no verdict.
SYSTEM_SPEC = {"symbols": ["USTEC", "US30", "US500", "XAUUSD", "BTCUSD", "EURUSD", "GBPUSD"],
               "years": [["2022-01-01", "2023-01-01"], ["2023-01-01", "2024-01-01"]]}


def system_start(body: dict[str, Any]) -> dict[str, Any]:
    runs()
    if any(r.get("mode") == "system" and r.get("status") == "running" and _alive(int(r.get("pid") or 0)) for r in _registry()):
        return {"ok": False, "error": "قياس المنظومة قائم الآن — انتظر انتهاءه"}
    spec = dict(SYSTEM_SPEC)
    name = "system-%s" % datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    out = RUNS_DIR / name
    out.mkdir(parents=True, exist_ok=True)
    (out / "spec.json").write_text(json.dumps(spec, ensure_ascii=False, indent=1), encoding="utf-8")
    return _launch(name, ["backtest.combo_engine", "--system-plan", str(out / "spec.json"), "--done", str(out / "done.txt")],
                   {"mode": "system", "source": "store", "from": _epoch(spec["years"][0][0]), "to": _epoch(spec["years"][-1][1]),
                    "symbols": spec["symbols"], "workers": 1, "request": {"name": "المنظومة كما هي — الأزواج السبعة"}})


#: 2026-10-24 (the owner's seal «نقيس الثلاثة قيس nq»): which of Dow on four hours, the averages on the quarter hour and the
#: price's answer at the trader's levels knows the session's turn earlier and better -- a direction measurement, no trades.
DETECTORS_SPEC = {"symbol": "USTEC", "years": [["2022-01-01", "2023-01-01"], ["2023-01-01", "2024-01-01"]],
                  "example": "2026-10-23"}


def detectors_start(body: dict[str, Any]) -> dict[str, Any]:
    runs()
    if any(r.get("mode") == "detectors" and r.get("status") == "running" and _alive(int(r.get("pid") or 0)) for r in _registry()):
        return {"ok": False, "error": "قياس الكواشف قائم الآن — انتظر انتهاءه"}
    symbol = str(body.get("symbol") or DETECTORS_SPEC["symbol"]).upper()
    if symbol not in SYMBOLS:
        return {"ok": False, "error": "رمزٌ غير معروف"}
    spec = dict(DETECTORS_SPEC, symbol=symbol)
    name = "detectors-%s-%s" % (symbol, datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S"))
    out = RUNS_DIR / name
    out.mkdir(parents=True, exist_ok=True)
    (out / "spec.json").write_text(json.dumps(spec, ensure_ascii=False, indent=1), encoding="utf-8")
    return _launch(name, ["backtest.combo_engine", "--session-detectors", str(out / "spec.json"), "--done", str(out / "done.txt")],
                   {"mode": "detectors", "source": "store", "from": _epoch(spec["years"][0][0]), "to": _epoch(spec["years"][-1][1]),
                    "symbols": [symbol], "workers": 1, "request": {"name": "الكواشف الثلاثة لتغيّر اتّجاه الجلسة"}})


def store_build(body: dict[str, Any]) -> dict[str, Any]:
    symbol = str(body.get("symbol") or "").upper()
    if symbol not in SYMBOLS or not body.get("from") or not body.get("to"):
        return {"ok": False, "error": "اختر الرمز والفترة"}
    if any(r.get("mode") == "store" and r.get("status") == "running" and _alive(int(r.get("pid") or 0)) for r in _registry()):
        return {"ok": False, "error": "بناء مخزنٍ قائم الآن — انتظر انتهاءه"}
    name = "store-%s-%s" % (symbol, datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S"))
    atoms = [a for a in str(body.get("atoms") or "").replace(" ", "").split(",") if a.isdigit()]
    real = bool(body.get("real_ticks"))
    root = "facts_store_ticks" if real else "facts_store_quick" if atoms else "facts_store"
    out = RUNTIME / "var" / root / symbol / ("%s_%s" % (body["from"], body["to"]))
    return _launch(name, ["backtest.facts_store", "--symbol", symbol, "--from", str(body["from"]), "--to", str(body["to"]),
                          "--warm-days", str(float(body.get("warm_days") or 60)), "--out", str(out)]
                   + (["--atoms", ",".join(atoms)] if atoms else []) + (["--real-ticks"] if real else []),
                   {"mode": "store", "source": "store", "from": _epoch(body["from"]), "to": _epoch(body["to"]),
                    "symbols": [symbol], "workers": 1, "request": {}, "out": str(out)})


def combo_report(out: Path) -> dict[str, Any]:
    try:
        folder = Path((out / "done.txt").read_text(encoding="utf-8").strip())
        summary = json.loads((folder / "summary.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"ok": False, "error": "لا تقرير بعد لهذا التشغيل"}
    trades: list[dict[str, str]] = []
    try:
        with (folder / "الصفقات.csv").open(encoding="utf-8-sig") as fh:
            trades = list(csv.DictReader(fh))
    except OSError:
        pass
    texts = {}
    for name in ("الاختبار.md", "النتيجة.md"):
        try:
            texts[name] = (folder / name).read_text(encoding="utf-8")
        except OSError:
            texts[name] = ""
    return {"ok": True, "name": out.name, "summary": summary, "trades": trades, "entries": [], "lab": {},
            "texts": texts, "folder": str(folder)}


def _start_year() -> dict[str, Any]:
    running = [r for r in _registry() if r.get("status") == "running" and _alive(int(r.get("pid") or 0))]
    if running:
        return {"ok": False, "error": "تشغيلٌ قائم الآن (%s) — أوقفه أو انتظر انتهاءه" % running[-1]["name"]}
    name = "year-%s" % datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    out = RUNS_DIR / name
    out.mkdir(parents=True, exist_ok=True)
    log = (out / "panel.log").open("w", encoding="utf-8")
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    proc = subprocess.Popen([str(PYTHON), "-u", "-m", "backtest.year_measure", "--out", str(out), "--name", name],
                            cwd=str(ROOT), stdout=log, stderr=subprocess.STDOUT, creationflags=flags,
                            env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    rows = _registry()
    rows.append({"name": name, "pid": proc.pid, "status": "running", "started_at": time.time(), "mode": "year",
                 "source": "year", "from": _epoch(YEAR_SOURCE["from"]), "to": _epoch(YEAR_SOURCE["to"]),
                 "symbols": [YEAR_SOURCE["symbol"]], "workers": 1, "request": {}})
    _save_registry(rows)
    return {"ok": True, "name": name}


# ─────────────────────────────────────────────────────────── الإطلاق ──

def _epoch(text: Any) -> float:
    value = str(text or "").strip()
    try:
        return float(value)
    except ValueError:
        return datetime.fromisoformat(value.replace("Z", "")).replace(tzinfo=timezone.utc).timestamp()


def start(body: dict[str, Any]) -> dict[str, Any]:
    if body.get("source") == "year":                    # ١٧/١٠: حلّ محلّها منشئ التوليفة (الأداة في الأرشيف)
        return {"ok": False, "error": "سنة القياس صارت جزءًا من منشئ التوليفة — اختر الفترة والتوليفة منه"}
    try:
        t_from, t_to = _epoch(body.get("from")), _epoch(body.get("to"))
    except ValueError:
        return {"ok": False, "error": "تاريخ البداية أو النهاية غير صالح"}
    if t_to <= t_from:
        return {"ok": False, "error": "النهاية قبل البداية"}
    symbols = [s for s in (body.get("symbols") or []) if s in SYMBOLS]
    if not symbols:
        return {"ok": False, "error": "اختر رمزًا واحدًا على الأقلّ"}
    source = "ctrader" if body.get("source") == "ctrader" else "recorded"
    workers = max(1, min(MAX_WORKERS, int(body.get("workers") or 1)))
    running = [r for r in _registry() if r.get("status") == "running" and _alive(int(r.get("pid") or 0))]
    if running:
        return {"ok": False, "error": "تشغيلٌ قائم الآن (%s) — أوقفه أو انتظر انتهاءه" % running[-1]["name"]}
    name = "panel-%s" % datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    out = RUNS_DIR / name
    args = [str(PYTHON), "-u", "-m", "backtest.full_replay", "--from", repr(t_from), "--to", repr(t_to),
            "--symbols", ",".join(symbols), "--source", source, "--out", str(out), "--name", name,
            "--balance", str(float(body.get("balance") or 10000.0)),
            "--coalesce-ms", str(int(float(body.get("coalesce_s") or 0) * 1000)),
            "--warmup-hours", str(float(body.get("warmup_hours") or 1.5)), "--workers", str(workers)]
    if body.get("trade_from"):
        args += ["--trade-from", repr(_epoch(body.get("trade_from")))]
    mode = "lab" if body.get("mode") == "lab" else "backtest"
    if mode == "lab":
        args += ["--lab"]
    if body.get("lab_overrides"):
        args += ["--lab-overrides"]
    for pname, value in (body.get("parameters") or {}).items():
        if value not in (None, ""):
            args += ["--set", "%s=%s" % (pname, float(value))]
    for knob, value in (body.get("knobs") or {}).items():
        if knob in ATOM_KNOBS and value not in (None, ""):
            ids, field = ATOM_KNOBS[knob]
            for aid in ids:
                args += ["--atom", "%d:%s=%s" % (aid, field, float(value))]
    for row in body.get("calibs") or []:
        try:
            symbol = str(row.get("symbol") or "*").upper()
            analyzer, path, field = str(row["analyzer"]), str(row.get("path") or "*"), str(row["field"])
            value = float(row["value"])
        except (KeyError, TypeError, ValueError):
            return {"ok": False, "error": "صفّ عيارٍ ناقص"}
        if analyzer not in ANALYZERS or field not in CALIB_FIELDS:
            return {"ok": False, "error": "محلّلٌ أو حقلٌ غير معروف"}
        args += ["--calib", "%s:%s:%s:%s=%s" % (symbol, analyzer, path, field, value)]
    out.mkdir(parents=True, exist_ok=True)
    log = (out / "panel.log").open("w", encoding="utf-8")
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    proc = subprocess.Popen(args, cwd=str(ROOT), stdout=log, stderr=subprocess.STDOUT, creationflags=flags,
                            env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    rows = _registry()
    rows.append({"name": name, "pid": proc.pid, "status": "running", "started_at": time.time(), "mode": mode,
                 "from": t_from, "to": t_to, "symbols": symbols, "source": source, "workers": workers,
                 "request": {k: body.get(k) for k in ("parameters", "knobs", "calibs", "coalesce_s",
                                                       "warmup_hours", "balance", "trade_from")}})
    _save_registry(rows)
    return {"ok": True, "name": name}


def stop(body: dict[str, Any]) -> dict[str, Any]:
    name = str(body.get("name") or "")
    rows = _registry()
    for row in rows:
        if row.get("name") == name and row.get("status") == "running":
            subprocess.run(["taskkill", "/PID", str(row.get("pid")), "/T", "/F"], capture_output=True,
                           timeout=20, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            row["status"] = "stopped"
            row["ended_at"] = time.time()
            _save_registry(rows)
            return {"ok": True, "name": name}
    return {"ok": False, "error": "لا تشغيل جارٍ بهذا الاسم"}


# ─────────────────────────────────────────────────────────── الحالة والتقرير ──

def _progress(out: Path) -> str:
    lines: list[str] = []
    for log in sorted(out.glob("*.log")) + sorted(out.glob("chunk*/panel.log")):
        try:
            tail = [l for l in log.read_text(encoding="utf-8", errors="replace").splitlines() if l.strip()]
        except OSError:
            continue
        progress = [l for l in tail if "تِكّة/ث" in l or "انتهت" in l or "شرائح" in l or "قياس سنة" in l or "باقي" in l
                    or "التوليفة:" in l or "البحث:" in l or "المستويات:" in l or "الكواشف:" in l or "المنظومة:" in l or "مخزن الحقائق" in l]
        if progress:
            lines.append(progress[-1].strip(" …"))
    return " | ".join(lines[-3:])


def runs() -> dict[str, Any]:
    rows = _registry()
    changed = False
    for row in rows:
        out = RUNS_DIR / row["name"]
        if row.get("status") == "running" and row.get("mode") in ("combo", "store", "direction", "strategy", "levels", "detectors", "system"):
            finished = (out / "done.txt").exists() if row.get("mode") in ("combo", "direction", "strategy", "levels", "detectors", "system") else (Path(row["out"]) / "index.json").exists() \
                if row.get("out") else bool(list(
                (FACTS_STORE / row.get("symbols", [""])[0]).glob("%s_%s/index.json" % (
                    datetime.fromtimestamp(row.get("from") or 0, timezone.utc).strftime("%Y-%m-%d"),
                    datetime.fromtimestamp(row.get("to") or 0, timezone.utc).strftime("%Y-%m-%d")))))
            # 2026-10-22: Windows reuses process numbers -- a finished run's number was taken by a browser window, so the
            # run stayed "running" and blocked the next one. The engine writes done.txt last, so done.txt alone means done.
            if finished and (row.get("mode") in ("combo", "direction", "strategy", "levels", "detectors", "system") or not _alive(int(row.get("pid") or 0))):
                row["status"], row["ended_at"], changed = "done", time.time(), True
            elif not _alive(int(row.get("pid") or 0)):
                row["status"], row["ended_at"], changed = "failed", time.time(), True
            if row["status"] == "done" and row.get("mode") == "combo" and "brief" not in row:
                rep = combo_report(out)
                if rep.get("ok"):
                    res = rep["summary"].get("النتائج", {})
                    row["brief"] = {"صفقات": (res.get("التوليفة", {}).get("الإحصاء", {}) or {}).get("صفقات"),
                                    "عوائد": {k: (v.get("الإحصاء", {}) or {}).get("صافي_٪") for k, v in res.items()},
                                    "الاسم": rep["summary"].get("الاسم")}
                    changed = True
            if row["status"] == "done" and row.get("mode") == "strategy" and "brief" not in row:
                rep = combo_report(out)
                if rep.get("ok"):
                    years = rep["summary"].get("السنوات", {})
                    student = {y: (v.get("النتائج", {}).get("التلميذ", {}).get("الإحصاء", {}) or {}) for y, v in years.items()}
                    row["brief"] = {"صفقات": sum(int(s.get("صفقات") or 0) for s in student.values()),
                                    "عوائد": {"التلميذ %s" % y: s.get("صافي_٪") for y, s in student.items()},
                                    "الاسم": "الحكم: %s" % rep["summary"].get("الحكم", "—")}
                    changed = True
            if row["status"] == "done" and row.get("mode") in ("detectors", "system") and "brief" not in row:
                rep = combo_report(out)
                if rep.get("ok"):
                    row["brief"] = {"الاسم": "الحكم: %s" % rep["summary"].get("الحكم", "—")}
                    changed = True
            if row["status"] == "done" and row.get("mode") == "levels" and "brief" not in row:
                rep = combo_report(out)
                if rep.get("ok"):
                    row["brief"] = {"صفقات": sum(int(((r.get("التوليفة") or {}).get("الإحصاء") or {}).get("صفقات") or 0)
                                                 for r in rep["summary"].get("التجارب", {}).values()),
                                    "عوائد": {"%s %s" % (r.get("السنة"), r.get("التجربة")): ((r.get("التوليفة") or {}).get("الإحصاء") or {}).get("صافي_٪")
                                              for r in rep["summary"].get("التجارب", {}).values()},
                                    "الاسم": "الحكم: %s" % rep["summary"].get("الحكم", "—")}
                    changed = True
        elif row.get("status") == "running":
            if (out / "summary.json").exists():
                row["status"], row["ended_at"], changed = "done", time.time(), True
            elif not _alive(int(row.get("pid") or 0)):
                row["status"], row["ended_at"], changed = "failed", time.time(), True
        row["progress"] = _progress(out) if row.get("status") == "running" else ""
        if row.get("status") == "done" and "brief" not in row:
            try:
                s = json.loads((out / "summary.json").read_text(encoding="utf-8"))
                if s.get("kind") == "year":
                    row["brief"] = {"صفقات": s.get("صفقات_مغلقة"),
                                    "عوائد": {r["الاسم"]: r["السنة"]["عائد"] for r in s.get("القراءات", [])}}
                    changed = True
                    continue
                row["brief"] = {"صافي": s.get("صافي", (s.get("الرصيد") or {}).get("صافي")),
                                "صفقات": s.get("صفقات_مغلقة"), "نسبة_الربح": s.get("نسبة_الربح")}
                if (out / "lab.json").exists():
                    lab = json.loads((out / "lab.json").read_text(encoding="utf-8"))
                    row["brief"]["أحداث_متعثّرة"] = sum(1 for v in lab.values() if v.get("healthy_pct", 100) < 50)
                changed = True
            except (OSError, ValueError):
                pass
        if row.get("status") == "failed" and "error_tail" not in row:
            try:
                tail = (out / "panel.log").read_text(encoding="utf-8", errors="replace").splitlines()[-6:]
                row["error_tail"] = "\n".join(tail)
                changed = True
            except OSError:
                pass
    if changed:
        _save_registry(rows)
    return {"ok": True, "runs": list(reversed(rows))[:40]}


def report(name: str) -> dict[str, Any]:
    out = RUNS_DIR / name
    if (out / "spec.json").exists():
        return combo_report(out)
    try:
        summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"ok": False, "error": "لا تقرير بعد لهذا التشغيل"}
    trades: list[dict[str, str]] = []
    try:
        with (out / "trades.csv").open(encoding="utf-8-sig") as fh:
            trades = list(csv.DictReader(fh))
    except OSError:
        pass
    entries: list[Any] = []
    for path in [out / "entries.json", *sorted(out.glob("chunk*/entries.json"))]:
        try:
            entries.extend(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            continue
    lab: dict[str, Any] = {}
    try:
        lab = json.loads((out / "lab.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    keep = len(trades) if summary.get("kind") == "year" else 500        # the owner: «كلّ صفقات الشهر كاملة»
    return {"ok": True, "name": name, "summary": summary, "trades": trades[-keep:], "entries": entries[-200:],
            "lab": lab}


def handle_full(method: str, path: str, body: dict[str, Any] | None) -> dict[str, Any]:
    sub = path[len("/gov/backtest/full"):].strip("/")
    try:
        if method == "GET" and sub in ("", "catalog"):
            return catalog()
        if method == "GET" and sub == "combo/catalog":
            return combo_catalog()
        if method == "POST" and sub == "combo/start":
            return combo_start(body or {})
        if method == "POST" and sub == "combo/build":
            return store_build(body or {})
        if method == "POST" and sub == "direction/start":
            return direction_start(body or {})
        if method == "POST" and sub == "strategy/start":
            return strategy_start(body or {})
        if method == "POST" and sub == "levels/start":
            return levels_start(body or {})
        if method == "POST" and sub == "system/start":
            return system_start(body or {})
        if method == "POST" and sub == "detectors/start":
            return detectors_start(body or {})
        if method == "GET" and sub == "runs":
            return runs()
        if method == "GET" and sub.startswith("run/"):
            return report(sub[4:])
        if method == "POST" and sub == "start":
            return start(body or {})
        if method == "POST" and sub == "stop":
            return stop(body or {})
    except Exception as exc:  # noqa: BLE001 — الصفحة ترى السبب ولا يسقط الخادم
        return {"ok": False, "error": "%s: %s" % (type(exc).__name__, exc)}
    return {"ok": False, "error": "مسارٌ غير معروف: %s" % path}
