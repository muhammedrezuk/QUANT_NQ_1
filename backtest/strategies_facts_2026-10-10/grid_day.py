# -*- coding: utf-8 -*-
"""يومٌ واحد من شبكة النوافذ على السنة (أمر المالك ١٠-١١ «قيس على كلّ النوافذ والاستراتيجيّات … قياس معمّق احترافي»).

لكلّ ذرّةٍ تقرأ منها استراتيجيّةٌ زنادها (151 · 152 · 165 · 201 · 310 · 315): نوافذها كلّها معًا أضيق وأوسع («all×…» من
شبكة calib_day — الشموع ×0.1…×10، والتِّكّ 20…6000 تِكّة). يُشغَّل بـ CALIB_DAY؛ الناتج يُضاف إلى runs_year_<اليوم>.
"""
import asyncio
import gzip
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "s150_calibration_2026-10-09"))
import calib_day as C  # noqa: E402

TRIGGER_ATOMS = ("151", "152", "165", "201", "310", "315")


def main():
    candles = C.candle_stream()
    ticks = C.tick_stream()
    cat = C.catalog()
    out = C.SCRATCH / f"runs_year_{C.DAY}"
    out.mkdir(parents=True, exist_ok=True)
    # الأثقل أخيرًا: النوافذ الواسعة على التِّكّ.
    jobs = [(t, tag, cfg) for t in TRIGGER_ATOMS for tag, cfg in C.grid(cat, t) if tag.startswith("all×")]
    for tune, tag, cfg in jobs:
        path = out / f"{tune}__{tag}.json.gz"
        if path.exists():
            continue
        try:
            rec = asyncio.run(C.run_one(cat, tune, dict(cfg), C.downstream(cat, tune), candles, ticks))
        except Exception as exc:
            print(json.dumps({"day": C.DAY, "tune": tune, "tag": tag, "error": f"{type(exc).__name__}: {exc}"[:300]},
                             ensure_ascii=False), flush=True)
            continue
        with gzip.open(path, "wt", encoding="utf-8") as f:
            json.dump({"tune": tune, "tag": tag, "cfg": cfg, "rows": rec}, f, ensure_ascii=False, default=str)
    print(json.dumps({"day": C.DAY, "grid_done": len(list(out.glob("*.json.gz")))}), flush=True)


if __name__ == "__main__":
    main()
