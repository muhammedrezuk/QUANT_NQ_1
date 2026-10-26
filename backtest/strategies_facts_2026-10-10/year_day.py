# -*- coding: utf-8 -*-
"""يومٌ واحد من سنة المشي إلى الأمام (أمر المالك ١٠-١٠ «عيد قياس بطريقة مختلفة وأطول» + «NQ») — قياسٌ فقط.

يسجّل حقائق الذرّات التي تحتاجها الاستراتيجيّات وعواملها، بعياراتها في البيانات اليوم (المعتمدة ١٠-١٠)، ومعها الضوضاء 165
بنافذة 160 (عامل «حركة نظيفة»). يُشغَّل بـ CALIB_DAY في البيئة؛ الناتج في runs_year_<اليوم>.
"""
import asyncio
import gzip
import json
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "s150_calibration_2026-10-09"))
import calib_day as C  # noqa: E402

JOBS = [("151", "live"), ("152", "live"), ("153", "live"), ("156", "live"), ("163", "live"), ("165", "live"),
        ("165", "all×0.1"), ("201", "live"), ("310", "live"), ("315", "live"), ("358", "live")]


def main():
    candles = C.candle_stream()
    ticks = C.tick_stream()
    cat = C.catalog()
    out = C.SCRATCH / f"runs_year_{C.DAY}"        # منفصلٌ عن قياس الشهر (عياراته يومها غير عيارات اليوم)
    out.mkdir(parents=True, exist_ok=True)
    for tune, tag in JOBS:
        path = out / f"{tune}__{tag}.json.gz"
        if path.exists():
            continue
        cfg = dict(next(c for t, c in C.grid(cat, tune) if t == tag))
        record = C.downstream(cat, tune)
        try:
            rec = asyncio.run(C.run_one(cat, tune, cfg, record, candles, ticks))
        except Exception as exc:
            print(json.dumps({"day": C.DAY, "tune": tune, "error": f"{type(exc).__name__}: {exc}"[:300]}), flush=True)
            continue
        with gzip.open(path, "wt", encoding="utf-8") as f:
            json.dump({"tune": tune, "tag": tag, "cfg": cfg, "record": record, "rows": rec}, f, ensure_ascii=False,
                      default=str)
    print(json.dumps({"day": C.DAY, "done": len(list(out.glob("*.json.gz")))}), flush=True)


if __name__ == "__main__":
    main()
