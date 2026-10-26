"""إثبات بنيوي مستقل لأوراق استقلال المحللات والعمق والعيار والوزن."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from build_registry.paths import RegistryAtomRoot
ATOM_ROOT = RegistryAtomRoot(ROOT)


def _core_matches_its_seal() -> bool:
    """هل النواة ما زالت مطابقةً للبصمة المكتوبة في قفلها؟

    تُحسب البصمة الآن **بالدالّة نفسها** التي كتبت `core/CORE.lock`
    (`freeze_core.compute_manifest`) لا بإعادة كتابتها هنا — فإعادةُ
    كتابةِ خوارزميّةِ بصمةٍ تُنتج جوابًا ثانيًا يبدو صحيحًا.

    وتعذُّرُ القياس ليس نجاحًا: بلا قفلٍ أو بقفلٍ لا يُقرأ يعود `False`،
    فالغياب يُعلَن فشلًا لا يُبتلع صمتًا.
    """
    try:
        sys.path.insert(0, str(ROOT / "governance" / "scripts"))
        import freeze_core                                   # noqa: PLC0415
        locked = json.loads((ROOT / "core" / "CORE.lock").read_text("utf-8"))
        return bool(locked.get("root_digest")) and \
            freeze_core.compute_manifest()["root_digest"] == locked["root_digest"]
    except Exception:
        return False

ANALYZERS = {
    151: "trend", 152: "momentum", 153: "volatility", 154: "volume",
    155: "spread", 156: "candle", 157: "gap", 158: "session", 159: "time",
    160: "correlation", 161: "relative_strength", 162: "velocity",
    163: "acceleration", 164: "volume_quality", 165: "noise",
}


def text(path: str) -> str:
    file = ROOT / path
    return file.read_text("utf-8") if file.is_file() else ""


def atom_file(atom_id: int, name: str) -> Path:
    folder = next((ATOM_ROOT).glob(f"{atom_id}_*"), Path("missing"))
    return folder / name


def main() -> int:
    live = text("shared/live_analysis.py")
    manager = atom_file(150, "atom.py").read_text("utf-8")
    fusion = atom_file(166, "atom.py").read_text("utf-8")
    decision = atom_file(451, "atom.py").read_text("utf-8")
    gateway = atom_file(901, "atom.py").read_text("utf-8")
    panel = text("governance/ui/src/sections/Analysis.tsx")
    server = text("governance/server.py")
    engine = text("governance/ui/src/core/engine.ts")

    manifests_ok = sources_ok = docs_ok = True
    for atom_id, analyzer_id in ANALYZERS.items():
        folder = atom_file(atom_id, "atom.py").parent
        try:
            manifest = yaml.safe_load((folder / "manifest.yaml").read_text("utf-8"))
        except Exception:
            manifest = {}
        manifests_ok &= ({"market.tick.validated", "analysis.settings.command", "SYS_SECOND"}
                         <= set(manifest.get("subscribes") or []))
        manifests_ok &= "analysis.setting.changed" in set(manifest.get("publishes") or [])
        sources_ok &= f'@live_analyzer("{analyzer_id}", EVENT_OUT)' in text(str((folder / "atom.py").relative_to(ROOT)))
        docs_ok &= all((folder / name).is_file() for name in ("الشرح.md", "التاريخ.md"))
        docs_ok &= "٢٠٢٦-٠٨-١٧" in text(str((folder / "التاريخ.md").relative_to(ROOT)))

    ui_sources = "\n".join(path.read_text("utf-8") for path in (ROOT / "governance/ui/src").rglob("*.tsx"))
    forbidden = ["QUANT_NQ", ">MT5", "Kill-Switch", "(React)", "WebGL غير مدعوم"]
    checks = [
        ("وحدة العقد الحي موجودة", bool(live)),
        ("المحللات الخمسة عشر مربوطة بالعقد", sources_ok),
        ("بطاقات المحللات تستقبل التكات والأوامر والنبض", manifests_ok),
        ("العزل بالحساب والأصل والمحلل", "tuple[str, str]" in live and "analyzer_id" in live),
        ("الاتجاه والثقة والعمق محدودة بالمئة", all(token in live for token in ("current_depth", "required_depth", "confidence_threshold", "-100.0"))),
        ("العمق مركب من أدلة لا نوم أو مؤقت", "sample_evidence" in live and "movement_evidence" in live and "continuity_evidence" in live and "sleep(" not in live),
        ("لكل محلل ملف دليل مستقل", "_profile_movement" in live and "analyzer == \"correlation\"" in live),
        ("شرطا العمق والعيار معًا", "current_depth < required" in live and "confidence < threshold" in live),
        ("الإعدادات دائمة ولها سجل تدقيق", "analysis_settings_audit" in live and "BEGIN IMMEDIATE" in live),
        ("المدير يجمع الأحدث بلا انتظار الجميع", "_on_live_state" in manager and "live_latest" in manager),
        ("الدمج يستبعد غير الجاهز ويعلن الوزن الغائب", all(token in fusion for token in ("STATE_READY", "weight_applied", "active_weight", "missing_weight"))),
        ("الغياب لا يتحول إلى حياد", '"signal": None' in fusion and '"score": None' in fusion),
        # ٢٠٢٦-٠٩-٢٣ — كان يبحث عن `_latest_live_analysis` و`DECISION_READY`،
        # وكلاهما **لم يبقَ في ٤٥١**. فقرأتُ الذرّة: الضمانةُ قائمةٌ بأسماءٍ
        # أخرى — `STATE_READY_FLAT = "READY"` ثمّ
        # `is_section_ready = state_name == STATE_READY_FLAT` (سطر ٣٨٦) وتُستعمل
        # بوّابةً (سطر ٤٠٩)، وفي تعليقها: «Only READY … a NOT_READY section is
        # present-but-not-contributing».
        #
        # فالفشل كان **فشلَ فحصي لا فشلَ الضمانة**: يبحث عن اسمٍ هُجر بعد
        # إعادة تسمية. وهذا مرضُ البصمة المثبَّتة نفسه في ثوبٍ آخر — حرفٌ
        # ميّتٌ يُحاكَم به حاضرٌ حيّ. صُوِّب إلى الاسمَين الجاريَين.
        #
        # ⚠️ وحدُّه معلَن: أيُّ إعادةِ تسميةٍ ثانية تُسقطه، **فسقوطُه يعني
        # «اقرأ الذرّة بيدك» لا «الضمانة انكسرت»** — ومن قرأها فليُصوّب هذا
        # السطر لا أن يعلن خرقًا.
        ("نقطة القرار تقبل الجاهز فقط",
         "STATE_READY_FLAT" in decision and "is_section_ready" in decision),
        ("بوابة الأوامر تنقل ضبط التحليل", "ACTION_ANALYSIS_SETTINGS" in gateway and "analysis.settings.command" in gateway),
        ("خادم اللوحة يقرأ الإعدادات ويؤكد تعديلها", "/gov/analysis/settings" in server and '"analysis_setting"' in server),
        ("قسم التحليل يعرض ويضبط كل الحقول", all(token in panel for token in ("العمق الحالي", "العمق المطلوب", "عيار الثقة", "الوزن الغائب", "حفظ الإعداد"))),
        ("مخزن اللوحة معزول بالحساب والأصل", "account_id ?? 'بلا حساب'" in engine),
        ("لا توجد العلامات الإنجليزية المعروفة في النص المرئي", not any(token in ui_sources for token in forbidden)),
        ("الشرح والتاريخ محدثان لكل محلل", docs_ok),
        ("اختبارات الكسر والإثبات موجودة", (ROOT / "tests/test_analysis_live_independence.py").is_file() and (ROOT / "tests/test_analysis_dashboard_arabic.py").is_file()),
        # 🔴 ٢٠٢٦-٠٩-٢٣ (طبقة الحوكمة صارت نطاقي بأمر المالك) — كان هنا
        # **بصمةٌ مثبَّتةٌ بالنصّ**: `root_digest == "08eefd30…"`. وهي بصمةُ
        # ختمٍ قديم، والنواة أُعيد ختمها ثلاث مرّات ليلةَ ٢٠٢٦-٠٩-٢٢ بختم
        # المالك (`fe9c3a6f` ⟵ `f0896fdf` ⟵ `6934610a`). فصار هذا الشرط
        # **كاذبًا إلى الأبد**، ويُسقط إثباتَ استقلال التحليل كلَّه لسببٍ لا
        # علاقة له بالتحليل — وكلُّ ختمٍ مشروعٍ يزيده كذبًا.
        #
        # ونصُّ الشرط كان يعني «النواة لم تُمَسّ بهذه الميزة». وذلك لا
        # يُثبَت بمقارنةِ حاضرٍ بحرفٍ ميّت — يُثبَت بأنّ **النواة ما زالت
        # مطابقةً لختمها**: تُحسب بصمتُها الآن بالدالّة نفسها التي كتبت
        # القفل، وتُقارن بما في القفل. فيبقى الشرط صادقًا بعد كلّ ختمٍ
        # مشروع، ويكذب وحده حين تُمَسّ النواة بلا ختم — وهو المراد.
        ("النواة ما زالت مطابقةً لختمها", _core_matches_its_seal()),
    ]
    passed = sum(ok for _, ok in checks)
    for label, ok in checks:
        print(("نجح" if ok else "فشل") + " — " + label)
    print(f"إثبات استقلال التحليل: {passed} ناجح / {len(checks)-passed} فاشل")
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    sys.exit(main())
