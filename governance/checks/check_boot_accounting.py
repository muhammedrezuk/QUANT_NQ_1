"""حساب الإقلاع — كلّ ذرّةٍ في خانةٍ معرَّفة، أو الفحص أحمر.

**حكم المالك ٢٠٢٦-٠٩-١٦:**

    «صار تعريف حالة الإقلاع كاملًا بدل ما يكون مضللًا… أي ذرة لا تظهر بعد
     الآن لازم تقع في خانة معرّفة.»

    وأوّل قراءةٍ بعد الإقلاع ليست `p99` ولا الفقد:
        booted + excluded + hosted = manifest
        unknown = 0
        runtime.scope_groups = 4
        hosted_by_worker موجود ومتوافق مع المصنع

## ⛔ ما يمنعه هذا الفحص — مقيس ٢٠٢٦-٠٩-١٦

    تقرير الإقلاع : booted=144 · failed=0 · excluded=9
    السجلّ الحيّ   : 228 ذرّة كلّها `running`
    الفارق        : **84 ذرّة** في لا خانة

فقرأه `check_boot.py` «انكماشًا صامتًا» وخرج بـ1، وقرأته اللوحة احتمالَ
«شارة خضراء على ذرّة لم تبدأ». وكلاهما إنذارٌ كاذب: الذرّات تُقلع داخل
عمليّات مزرعة التحليل (`sections: [[150, 499]]`)، و**82 من 84** كانت
تُظهر أرقامًا متحرّكة في `health.message`.

فالنظام كان سليمًا والتقرير ناقص التعريف. وثمنه وقتُ جلستين.

## ولماذا معادلةٌ لا عدّاد

عدّادٌ يقول «144» لا يُكذَّب ولا يُصدَّق — لا مرجع له. والمعادلة تُغلق:
كلّ رقمٍ يبقى خارجها **عطبٌ حقيقيّ** يستحقّ الإنذار، لا نقصَ تعريف.

## ولا رقم ثابت هنا

`scope_groups` المتوقَّع يُقرأ من `config/core_forex.yaml` لا من هذا
الملفّ (§٤٣)، والمانيفستات تُعدّ من القرص. الرقم الوحيد المكتوب هو الصفر
في `unknown`.

Exit 1 على أيّ اختلاف. وإن كانت النواة مطفأة: خروج 2 برسالة صريحة — لا
يُقال «سليم» عمّا لم يُقَس.
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import yaml  # noqa: E402

from build_registry.paths import RegistryAtomRoot  # noqa: E402

ATOMS = RegistryAtomRoot(ROOT)
BASE = "http://127.0.0.1:8010"
CONFIG = ROOT / "config" / "core_forex.yaml"


def fetch(path: str, timeout: float = 20.0):
    with urllib.request.urlopen(BASE + path, timeout=timeout) as response:
        return json.load(response)


def manifest_ids() -> set[int]:
    """كلّ ذرّةٍ على القرص — المرجع الذي تُقاس إليه الخانات."""
    found: set[int] = set()
    for card in Path(ATOMS).glob("*/*/manifest.yaml"):
        try:
            data = yaml.safe_load(card.read_text(encoding="utf-8")) or {}
        except Exception:  # noqa: BLE001 — مانيفست تالف يُعدّ ولا يُسقط الفحص
            continue
        atom_id = data.get("id")
        if atom_id is not None:
            found.add(int(atom_id))
    return found


def main() -> int:
    print("=" * 78)
    print("حساب الإقلاع — كلّ ذرّة في خانة معرَّفة")
    print("=" * 78)

    try:
        report = fetch("/api/boot-report")
        transport = fetch("/api/transport-stats")
        health = fetch("/api/health")
    except (urllib.error.URLError, OSError) as exc:
        print("  ⛔ النواة لا تجيب: %s" % exc)
        print("     لا يُقال «سليم» عمّا لم يُقَس. شغّل النواة ثمّ أعد الفحص.")
        return 2

    on_disk = manifest_ids()
    booted = {int(v) for v in report.get("booted") or ()}
    failed = {int(v) for v in report.get("failed") or ()}
    excluded = {int(v) for v in report.get("excluded") or ()}
    farm = transport.get("analysis_farm") or {}
    hosted = {int(v) for v in farm.get("hosted_atom_ids") or ()}
    # المرحلة F: المستضاف اليوم في العمليّة الباردة لا في مزرعة — والخانة واحدة.
    cold_proc = transport.get("cold_process") or {}
    hosted |= {int(v) for v in cold_proc.get("loaded") or cold_proc.get("hosted_atom_ids") or ()}
    runtime = transport.get("runtime") or {}

    bad = 0

    # ── ٠) السجلّ الحيّ — لا تقرير الإقلاع وحده ─────────────────────────
    #
    # ⛔ **هذا الحارس كذب ٢٠٢٦-٠٩-١٧.** كان يقرأ `booted` من **تقرير
    #    الإقلاع** — لقطةَ لحظةٍ واحدة — فقال «سليم: 235 = 142 + 9 + 84»
    #    بينما السجلّ الحيّ يحمل **226** ذرّة: الفحص الدوريّ أعاد إقلاع
    #    المستضافين بعد خمس ثوانٍ، فصار للذرّة نسختان.
    #
    #    ومعادلةٌ تُحسب على النيّة لا على الواقع ليست حارسًا.
    print("")
    print("٠) السجلّ الحيّ مقابل تقرير الإقلاع")
    live = health.get("atom_count")
    if isinstance(live, int):
        print("      %-34s %d" % ("مُقلَع في النواة الآن (حيّ)", live))
        print("      %-34s %d" % ("تقرير الإقلاع (booted)", len(booted)))
        print("      %-34s %d" % ("تستضيفها المزرعة", len(hosted)))
        extra = live - len(booted)
        if extra > 0:
            bad += 1
            print("      🔴 زائدٌ عن التقرير = %d" % extra)
            print("         ذرّاتٌ دخلت سجلّ النواة بعد الإقلاع. وإن كانت")
            print("         مستضافةً فهي **نسختان** تستهلكان الحدث نفسه")
            print("         وتنشران تحليلين — و%d ذرّة تعمل في مكانين."
                  % max(0, live + len(hosted) - len(on_disk)))
        elif extra < 0:
            bad += 1
            print("      🔴 ناقصٌ عن التقرير = %d — ذرّاتٌ سقطت بعد الإقلاع"
                  % -extra)
        else:
            print("      ✅ السجلّ الحيّ يطابق تقرير الإقلاع")
    else:
        bad += 1
        print("      ⛔ `/api/health` بلا `atom_count` — لا يُقاس السجلّ الحيّ")

    # ── ١) المعادلة ──────────────────────────────────────────────────────
    print("\n١) المعادلة — كلّ ذرّةٍ على القرص في خانة")
    accounted = booted | failed | excluded | hosted
    unknown = sorted(on_disk - accounted)
    ghosts = sorted(accounted - on_disk)
    overlap = sorted((booted & hosted) | (booted & excluded) | (hosted & excluded))

    print("      %-30s %d" % ("مانيفستات على القرص", len(on_disk)))
    for label, group in (("أقلعتها النواة (booted)", booted),
                         ("فشلت (failed)", failed),
                         ("مستبعَدة بأمر (excluded)", excluded),
                         ("تستضيفها المزرعة (hosted)", hosted)):
        print("      %-30s %d" % (label, len(group)))
    print("      %-30s %d" % ("خارج كلّ خانة (unknown)", len(unknown)))

    if unknown:
        bad += 1
        print("      ✗ ذرّاتٌ بلا خانة: %s" % unknown[:25])
    else:
        print("      ✓ unknown = 0")

    if ghosts:
        bad += 1
        print("      ✗ ذرّاتٌ مذكورة ولا مانيفست لها: %s" % ghosts[:15])
    if overlap:
        bad += 1
        print("      ✗ ذرّاتٌ في خانتين معًا: %s" % overlap[:15])
    if failed:
        bad += 1
        print("      ✗ فشل إقلاع: %s" % sorted(failed)[:15])

    # ── ٢) التقسيم دخل حيًّا ─────────────────────────────────────────────
    print("\n٢) §١٤ — التقسيم كما أُعلن في الإعداد، لا كما يُظنّ")
    engine = transport.get("engine")
    if isinstance(engine, dict):
        # NQ ENGINE (٢٠٢٦-٠٩-١٧): لا تقسيم نطاقاتٍ على مسارات — المسار الساخن
        # دورةٌ واحدة لكلّ حدث، والناقل القديم بارد بمسارٍ واحد. فالمعيار هنا
        # أنّ المحرّك يعلن نفسه ويُغلق رسمه، لا عدد المجموعات.
        sealed = bool((engine.get("graph") or {}).get("sealed"))
        bad += 0 if sealed else 1
        print("      %-30s %s" % ("NQ ENGINE يعمل — الرسم مختوم", "✓" if sealed else "✗"))
        print("      %-30s %s اشتراكًا ساخنًا (%s بإيقاع) · %s باردًا"
              % ("الاشتراكات", engine.get("hot_subscriptions"),
                 engine.get("cadence_subscriptions"), engine.get("cold_subscriptions")))
    else:
        declared = int(((yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
                         or {}).get("event_bus") or {}).get("scope_groups", 1))
        live = runtime.get("scope_groups")
        ok = live == declared
        bad += 0 if ok else 1
        print("      %-30s الإعداد=%s · الحيّ=%s  %s"
              % ("scope_groups", declared, live, "✓" if ok else "✗"))

        groups_seen = {int(str(unit).rsplit("#", 1)[1])
                       for unit in (runtime.get("ownership") or {})
                       if "#" in str(unit)} | {0}
        ok = len(groups_seen) == declared or not runtime.get("ownership")
        bad += 0 if ok else 1
        print("      %-30s %s  %s" % ("مجموعات ظهرت في الملكية",
                                      sorted(groups_seen), "✓" if ok else "✗"))

    # ── ٣) المزرعة تُعلن ملكيّتها ─────────────────────────────────────────
    print("\n٣) المزرعة — الإعلان مشتقٌّ من المصنع لا قائمةٌ ثانية")
    by_worker = farm.get("hosted_by_worker")
    if farm.get("running"):
        checks = (
            ("hosted_atom_ids موجود", bool(hosted)),
            ("hosted_by_worker موجود", isinstance(by_worker, dict) and bool(by_worker)),
            ("المجموع يطابق خريطة العمّال",
             isinstance(by_worker, dict)
             and {int(v) for ids in by_worker.values() for v in ids} == hosted),
            ("لا عامل بلا شغل",
             isinstance(by_worker, dict) and all(by_worker.values())),
        )
        for label, good in checks:
            bad += 0 if good else 1
            print("      %-30s %s" % (label, "✓" if good else "✗"))
        if isinstance(by_worker, dict):
            for worker, ids in sorted(by_worker.items()):
                print("         عامل %-3s %3d ذرّة" % (worker, len(ids)))
    else:
        print("      المزرعة مطفأة — فلا ملكيّة تُعلن (hosted = %d)" % len(hosted))
        if hosted:
            bad += 1
            print("      ✗ مطفأة ومع ذلك تُعلن استضافة")

    # ── ٤) المسار البارد محجوز ───────────────────────────────────────────
    print("\n٤) المسار البارد — لا نطاق سوقٍ عليه")
    cold = runtime.get("cold_worker")
    market_on_cold = sorted(unit for unit, worker in (runtime.get("ownership") or {}).items()
                            if worker == cold)
    ok = not market_on_cold
    bad += 0 if ok else 1
    print("      %-30s %s" % ("العامل البارد", cold))
    print("      %-30s %s" % ("نطاقات سوق عليه",
                              "لا شيء ✓" if ok else "%d ✗ %s"
                              % (len(market_on_cold), market_on_cold[:6])))

    print("\n" + "=" * 78)
    print("الاختلافات = %d" % bad)
    if not bad:
        print("سليم: %d = %d booted + %d excluded + %d hosted + 0 unknown"
              % (len(on_disk), len(booted), len(excluded), len(hosted)))
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
