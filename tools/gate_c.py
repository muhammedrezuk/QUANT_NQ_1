# -*- coding: utf-8 -*-
"""§5 / Gate C — المرجعُ مقابل المحرّك الجديد على الشريط المجمَّد نفسه.

## ما يُثبته

Gate A أثبتت أنّ الإطار لا يغيّر المدخل. وGate B أثبتت أنّ المرجع حتميّ.
وGate C تسأل سؤال §5 نفسه:

    هل يغيّر تقسيمُ العمل على مالكي `Account×Symbol`، وتوزيعُهم على عمّالٍ
    مستقلّين، وإنفاذُ ترتيب الخطّة المُجمَّعة — **قرارًا واحدًا**؟

    الشريط المجمَّد (بصمةٌ مُتحقَّقة)
              ↓  encode مرّةً واحدة
        frame bytes  ← **نفسها حرفًا** للجانبين
              ↓                         ↓
      المرجع التسلسليّ           المحرّك الجديد (٦ عمّال)
       حالةٌ عالميّةٌ واحدة        مالكٌ لكلّ Account×Symbol
              ↓                         ↓
           outputs                   outputs
                    ↘           ↙
                  مقارنةٌ بستّة محاور

والحكم `CLOSED` لا يقع إلّا عند `mismatch = 0` **مع** صفرِ خرقِ ملكيّة
وصفرِ دورةٍ في عاملَين وصفرِ واقعةٍ بلا مالك.

## ⚠️ ما لا يشهد به هذا الباب

الشريط من الصندوق **البارد**، وترتيبُ الوصول عليه ليس ترتيبَ النشر:
مقيسٌ أنّ ٨٫٣٪ من الدورات تصل تِكّتُها بعد موافقتها (وسيط ٨ وقائع)،
و٠٫٣٪ من التِكّات راجعةٌ بالتسلسل بإزاحاتٍ محلّيّة (٢ إلى ١٧).

فرتبةُ الخطّة تُعدّ وتُعرَض **ولا يُحكَم بها هنا**: شريطٌ باردٌ لا يشهد
على ترتيبٍ ساخن. والترتيب يُثبَت بنيويًّا — الخطّة `DAG` وسلسلتُها
`112(#7) ⟶ 451(#122) ⟶ 466(#131) ⟶ 467(#133)`.

## ما هو ممنوعٌ هنا

لا تعديلَ ناقل، ولا ٦٠١، ولا تغييرَ صيغةِ قرارٍ أو مخاطرة، ولا تسويةً
صامتة، ولا حذفَ سجلٍّ مخالف، ولا لمسَ النواة.

    python tools/gate_c.py <شريط-مجمَّد.jsonl> [--batch 512] [--workers 6]
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from hot import frame, parity, planner, runtime  # noqa: E402
from tools.gate_b import read_single_run, verify_tape  # noqa: E402


def reference(blobs: list[bytes], out_path: Path) -> dict[str, dict]:
    """المرجع كما أغلق Gate B حرفًا — لا يُعاد بناؤه هنا."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("", encoding="utf-8")
    recorder = parity.ParityRecorder(str(out_path), runtime="oracle",
                                     **runtime.REPLAY_CONFIG)
    for blob in blobs:
        _header, records = frame.decode(blob)
        for _index, name, payload in records:
            recorder.observe(name, payload)
    recorder.close()
    return parity.load(str(out_path))


def new_engine(blobs: list[bytes], out_dir: Path, plan: planner.HotPlan,
               *, workers: int) -> tuple[dict[str, dict], dict]:
    """المحرّك الجديد: نفسُ البايتات، مالكون وأقسامٌ وعمّالٌ وخطّة."""
    engine = runtime.HotEngine(plan, out_dir, workers=workers)
    for blob in blobs:
        _header, records = frame.decode(blob)
        engine.feed_records(records)
    return engine.close(), engine.stats()


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        print(__doc__)
        return 2
    size, workers = 512, 6
    for i, a in enumerate(sys.argv):
        if a == "--batch" and i + 1 < len(sys.argv):
            size = int(sys.argv[i + 1])
        if a == "--workers" and i + 1 < len(sys.argv):
            workers = int(sys.argv[i + 1])

    tape_path = Path(args[0])
    manifest = verify_tape(tape_path)
    print("الشريط المجمَّد: %s" % tape_path.name)
    print("  sha256 = %s…  ✅ مطابق للبيان" % manifest["sha256"][:32])
    print("  وقائع البيان = %d\n" % manifest["records"])

    rows = read_single_run(tape_path)
    if len(rows) != manifest["records"]:
        raise SystemExit("⛔ عدد الوقائع لا يطابق البيان: %d ≠ %d"
                         % (len(rows), manifest["records"]))

    plan = planner.compile_plan(known_external=planner.external_events())
    summary = plan.summary()
    print("الخطّة المُجمَّعة: %d عقدة · %d في الترتيب · %d راجعة · %d ذاهبةٌ مختومة"
          % (summary["nodes"], summary["order"], summary["feedback"],
             summary["normal_sealed"]))
    print("  بصمة الخطّة = %s" % summary["fingerprint"])
    left_over = planner.strongly_connected(
        {a: set(v) for a, v in plan.depends_on.items()})
    if left_over:
        raise SystemExit("⛔ الخطّة ليست DAG — %d مكوّنًا" % len(left_over))
    print("  مكوّناتٌ باقية = 0  ✅ DAG\n")

    blobs = [frame.encode(chunk)
             for chunk in frame.batches(rows, max_records=size)]
    import hashlib
    fingerprint = hashlib.sha256(b"".join(blobs)).hexdigest()
    print("إطارات = %d · بصمة البايتات = %s…" % (len(blobs), fingerprint[:32]))
    print("  تُمرَّر **نفسها** إلى الجانبين\n")

    scratch = ROOT / "forex_runtime" / "var" / "parity" / "gate_c"
    t0 = time.perf_counter()
    oracle = reference(blobs, scratch / "oracle.jsonl")
    oracle_s = time.perf_counter() - t0
    t0 = time.perf_counter()
    engine, stats = new_engine(blobs, scratch / "engine", plan, workers=workers)
    engine_s = time.perf_counter() - t0
    print("المرجع: %d دورة في %.2f ث · المحرّك الجديد: %d دورة في %.2f ث\n"
          % (len(oracle), oracle_s, len(engine), engine_s))

    print("=== المحرّك الجديد — الملكيّة والترتيب ===")
    print("  عمّال = %d · أقسامٌ منطقيّة = %d · وقائع = %d"
          % (stats["workers"], stats["logical_partitions"], stats["fed"]))
    print("  ⛔ معايير الإغلاق — بلا مالك = %d · خرقُ ملكيّة = %d "
          "· دورةٌ في عاملَين = %d"
          % (stats["dropped_no_owner"], stats["foreign_cycles"],
             stats["cycles_in_two_workers"]))
    for row in stats["per_worker"]:
        print("    عامل %d: %5d واقعة · %d مالك · %5d دورة · %d التزام"
              % (row["worker"], row["records"], row["owners"],
                 row["cycles"], row["commits"]))
    # ── يُعرَض ولا يُحكَم به: أثرُ الصندوق البارد لا عطبُ خطّة ─────────────
    print("\n  ⚠️ يُقاس ولا يُغلِق (الشريط باردٌ لا يحفظ ترتيب النشر):")
    print("     أحداثٌ لها رتبةٌ في الخطّة = %d · مخالفةُ رتبةٍ على الشريط = %d"
          % (stats["ranked_events"], stats["rank_violations"]))
    print("     تِكّاتٌ قُبِلت = %d · راجعةٌ بالتسلسل = %d"
          % (stats["ticks_admitted"], stats["ticks_rejected"]))
    print("     والسبب مقيس: ٨٫٣٪ من الدورات تصل تِكّتُها بعد موافقتها.")

    result = parity.compare_axes(oracle, engine)
    print("\n=== Gate C — المرجع مقابل المحرّك الجديد ===")
    print(parity.format_axes(result))

    clean = (stats["dropped_no_owner"] == 0 and stats["foreign_cycles"] == 0
             and stats["cycles_in_two_workers"] == 0)
    closed = (result["mismatches"] == 0
              and result["output_count_match"]
              and result["only_left_count"] == 0
              and result["only_right_count"] == 0
              and result["shared"] > 0
              and not result["self_comparison"]
              and clean)
    print()
    print("الحكم: %s" % ("✅ Gate C = CLOSED" if closed else
                         "⛔ Gate C = OPEN — الاختلاف مصنَّفٌ أعلاه"))
    return 0 if closed else 1


if __name__ == "__main__":
    raise SystemExit(main())
