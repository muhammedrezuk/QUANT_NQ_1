"""واجهة سطر الأوامر لتصنيف الذرّات — المنطق في `transport/atom_graph.py`.

المنطق انتقل إلى `transport/` لأنّ **الإقلاع يشتقّ منه حدّ العملية**،
وكود الإنتاج لا يستورد من أدوات التشخيص. هذا الملفّ عرضٌ فقط.

    python tools/atom_classifier.py            # جدول
    python tools/atom_classifier.py --json     # للأدوات
    python tools/atom_classifier.py --root <حدث>
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from transport.atom_graph import (  # noqa: E402
    CLASS_CROSS_SCOPE,
    CLASS_DEPENDENT,
    CLASS_ORDER_SENSITIVE,
    CLASS_PIPELINE,
    CLASS_PURE,
    CLASS_STATEFUL,
    CLASS_UNKNOWN,
    ORDER_MARKS,
    SEVERITY,
    boundary_events,
    classify,
    run,
    scan_atom,
)

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--atoms-root", type=str, default=str(PROJECT_ROOT / "atoms"))
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--show", type=str, default="",
                        help="اعرض تفاصيل صنفٍ واحد فقط")
    parser.add_argument("--root", type=str, default="market_data.candle_closed",
                        help="جذر الفَتَحة الذي يُحسب الاعتماد بالنسبة إليه")
    args = parser.parse_args()

    result = run(Path(args.atoms_root), args.root)
    if args.json:
        print(json.dumps(result, ensure_ascii=False))
        return 0

    counts: dict[str, int] = {}
    for row in result["rows"]:
        counts[row["class"]] = counts.get(row["class"], 0) + 1

    print("== المرحلتان B و C — تصنيف الذرّات (§13 · §38) ==")
    print("ذرّات مفحوصة: %d" % result["atoms"])
    print("")
    print("%-18s %7s   %s" % ("الصنف", "العدد", "ما يعنيه للتقسيم"))
    print("-" * 74)
    meaning = {
        CLASS_PIPELINE: "مرحلة تالية — تُفصل إن كانت حالتها نطاقيّة",
        CLASS_PURE: "تُفصل بحرّية",
        CLASS_STATEFUL: "تُفصل مع بقاء حالتها في قسمها",
        CLASS_ORDER_SENSITIVE: "تبقى خلف المُرتِّب",
        CLASS_DEPENDENT: "لا تُفصل إلّا بعقد مزامنة",
        CLASS_CROSS_SCOPE: "⛔ لا تُنقل قبل تعريف المشاركة صراحةً",
        CLASS_UNKNOWN: "⛔ لا يُحكم — تُفحص تجريبيًّا قبل أيّ تقسيم",
    }
    for level in SEVERITY:
        if counts.get(level):
            print("%-18s %7d   %s" % (level, counts[level], meaning[level]))

    print("")
    print("جذر الفَتَحة: %s  (%d حدثًا يُولَد داخلها)"
          % (result["root"] or "—", len(result["fanout_events"])))
    hard = [row for row in result["rows"]
            if row["class"] in (CLASS_CROSS_SCOPE, CLASS_DEPENDENT, CLASS_UNKNOWN)]
    print("")
    print("== ما لا يُقسَّم اليوم (%d) ==" % len(hard))
    for row in hard[:25]:
        print("  %-26s %-15s %s" % (row["atom"][:26], row["class"],
                                    (row["reasons"] or [""])[0][:60]))
    if len(hard) > 25:
        print("  … و%d غيرها (استعمل --json)" % (len(hard) - 25))

    if args.show:
        print("")
        print("== تفاصيل %s ==" % args.show)
        for row in result["rows"]:
            if row["class"] == args.show:
                print("  %-26s %s" % (row["atom"][:26], row["reasons"]))
    print("")
    print("⛔ هذا الفاحص يعطي **مرشَّحين** لا إذنًا: الحكم النهائيّ لاختبار")
    print("   التكافؤ (§34) — `tools/atom_factory_bench.py --probe`.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
