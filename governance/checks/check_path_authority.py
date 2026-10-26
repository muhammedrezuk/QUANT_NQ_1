#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""فحص سلطة المسارات — «المُصلِح يكتب حيث يقرأ القارئ» (فصل ٢٣ · بنود ٨–١١).

نشأ هذا الفحص من قياس ٢٠٢٦-٠٩-٠٣: `governance/server.py` كان يحسب جذر بياناته
بـ`ROOT.parent/"forex_runtime"` بلا تحقّق، و`scripts/run_forex.py` كان يدوس
`QUANT_ANALYSIS_SETTINGS_DB` على `PROJECT_ROOT/var/forex/...`، وذرّة ٥٨0 كانت
ترسو على `parents[2]` = `atoms/var/store/tilt_rules.db` (مجلّد لا وجود له).
النتيجة المقياسة: `/gov/parameters` يرجع `available=false, عدد=0` بينما السجلّ
موجود وفيه ٣٦ صفًّا، واللوحة approve ستّةً والمحرّك يحصي ٣٦ عند الإقلاع.

الفحص لا يكتفي بالقراءة النصيّة — يقارن **الغاية والمسار المحسوب**:

    أ) المالك الوحيد: `shared/runtime_paths.py` هو مصدر الاشتقاق، ولا ملفّ آخر
       يشتقّ `<var/>` أو `QUANT_ANALYSIS_SETTINGS_DB` أو جذر الـruntime بنفسه.
    ب) تطابق النسخة: كل ملفّ مُتحكَّم به داخل `forex_runtime/`/`crypto_runtime/`
       يساوي أخاه في الجذر بايت-ببايت (انفصال الأشجار = انفصال المسارات).
    ج) اللقيا: لوحة الحوكمة والسجلّ المحكوم وبوّابة ٩٠١ وحالة النواة تُقلع كلّها
       على الجذر القانوني نفسه، والكريبتو لا يشارك الفوركس مجلّدًا واحدًا.
    د) الحفظ ≠ الاعتماد: الحقل الحاكم موجود، ولا اعتماد في مسار الحفظ.
    ⛔ أي خرق = rc=1. لا يُقبل «أصفر»: إمّا عقد مُرضًى أو فشل صريح.

يُشغَّل من جذر الشجرة التي يُفحص فيها (الجذر أو أي نسخة runtime) — فيحسب
جذر مشروعه هو، فلا يكذب على النسخ.
"""
from __future__ import annotations

import hashlib
import os
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve()
# <root>/governance/checks/هذا → ``<root>/governance`` → أبُوها = **جذر الشجرة
# العاملة** (PROJECT_ROOT في الأصل، و<runtime> في النسخة). لا تطبيع إضافي بعد ذلك.
ROOT = HERE.parents[1].parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

RUNTIMES = ("forex_runtime",)   # سوق واحد — أُزيل `crypto_runtime` 2026-09-09

# ── أ) أنماط ممنوعة: اشتقاق موازٍ لجذر خارج المالك ─────────────────────────
# كل عنصر: (النمط، الوصف، استثناءات نسبية مسموحة صراحةً)
BANNED = (
    (re.compile(r'(?:ROOT|PROJECT_ROOT|BASE_DIR|_PROJECT)\s*/\s*["\']var["\']'),
     "اشتقاق `var` من جذر المشروع خارج المالك",
     {"conftest.py", "governance/runtime_paths.py", "governance/app.py",
      "governance/checks/check_path_authority.py",
      "governance/checks/check_crypto_isolation.py",
      "governance/checks/check_telegram.py",
      "governance/scripts/verdict_cycle.py",
      "governance/scripts/live_probe.py",
      "governance/scripts/start_asset.py"}),
    (re.compile(r'ROOT\.parent\s*/\s*["\'](?:forex|crypto)_runtime["\']'),
     "حساب يدويّ لجذر الـruntime في server (تجاوزه إلى أبٍ أعمى)", set()),
    (re.compile(r'parents\[\d+\]\s*/\s*["\']var["\']'),
     "مرسى `parents[n]/var` — يخرج عن الجذر القانوني عند نقل الملفّ", set()),
    (re.compile(r'Path\(__file__\)\.resolve\(\)\.parent\.parent\s*/\s*["\']var["\']'),
     "مرسى `ملفّ/../../var` داخل shared — يُنكر جذر الـruntime", set()),
    (re.compile(r'_root\s*/\s*["\']var["\']\s*/\s*["\']store["\']'),
     "مرسى محلّي لقاعدة المعايرة داخل الملفّ نفسه (ملفّ ظلّ لا يقرأه أحد)", set()),
    (re.compile(r'ROOT\s*/\s*["\']var["\']\s*/\s*["\']forex["\']'),
     "قراءة `var/forex` المتقاعِدة بدل عقد الـruntime", set()),
    (re.compile(r'setdefault\(\s*["\']QUANT_ANALYSIS_SETTINGS_DB["\'][^)]*["\']var["\']'
                r'\s*/\s*["\']forex["\']'),
     "دوس سجلّ المعايرة على `var/forex` من المُقلِع (يخالف عقد السجلّ)", set()),
    (re.compile(r'\.resolve\(\)\.parents\[\d+\]\s*/\s*raw\b'),
     "مرسى ذرّة على parents[n] المطلق — ينفصل عن جذر الـruntime", set()),
)

# النطاق المحكوم: الملفات التي تُقِلع أو تُقرأ زمن التشغيل (لا الأدوات ولا الاختبارات —
# تلك تبني بيئتها الخاصّة وتُرسى على tmp_path، وممنوع عليها هي الأخرى الجذر العام لكنّها
# لا تكسر عقدها حين تعمل).
SCAN_FILES = (
    "governance/server.py", "governance/app.py", "governance/telegram.py",
    "governance/vault_ops.py", "governance/runtime_paths.py",
    "governance/scripts/run_core.py", "governance/scripts/start_asset.py",
    "governance/scripts/verdict_cycle.py", "governance/scripts/live_probe.py",
    "shared/runtime_paths.py", "shared/parameter_registry.py",
    "shared/decision_dials.py", "shared/section_contract.py",
    "shared/live_analysis.py", "shared/section_live.py",
    "tools/approve_scalp_params.py", "tools/set_scalp_weights.py",
    "scripts/run_forex.py", "scripts/run_crypto.py", "scripts/run_governance.py",
    "scripts/prepare_unified.py",
)
# المُقلِعات يملك حقّ **ضبط** المتغيّرات الحاكمة (وهذا عقد الإقلاع) — لكن يجب أن
# يمرّ بالمالك لاشتقاق أيّ مسار، ويُمنع أن يدوس سجلّ المعايرة على `var/forex`.
LAUNCHERS = {"scripts/run_forex.py", "scripts/run_crypto.py", "scripts/run_governance.py"}
# مواضع مسموح فيها `PROJECT_ROOT/var` لأنّها تراثٌ صريح بلا مُقلِع (fallback معلَن):
LEGACY_FALLBACK = {"governance/app.py", "governance/telegram.py", "governance/vault_ops.py",
                   "governance/checks/check_telegram.py", "governance/runtime_paths.py",
                   "governance/scripts/start_asset.py", "governance/scripts/verdict_cycle.py",
                   "governance/scripts/live_probe.py"}
CODE_DIRS = ("governance", "shared", "scripts", "core", "transport",
             "config", "security", "clock", "catchup", "tools")


def _scan_targets() -> list[tuple[str, Path]]:
    out: list[tuple[str, Path]] = []
    for rel in SCAN_FILES:
        p = ROOT / rel
        if p.is_file():
            out.append((rel, p))
    return out


def check_owner() -> list[str]:
    """أ: المالك مصدر الاشتقاق الوحيد، ولا ملفّ محكوم يحسب جذرًا في بيته."""
    problems: list[str] = []
    for rel, path in _scan_targets():
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            problems.append(f"⛔ {rel}: لا يُقرأ ({exc})")
            continue
        for pattern, why, allow in BANNED:
            for m in pattern.finditer(text):
                if rel in allow:
                    continue
                if why.startswith("دوس") and rel in LAUNCHERS and "var/forex" not in m.group(0):
                    continue        # المُقلِع يضبط المتغيّر — الممنوع دوسه على جذر المشروع
                if "اشتقاق `var`" in why and rel in LEGACY_FALLBACK:
                    continue        # مرسى تراثيّ معلَن داخل except
                line = text[:m.start()].count("\n") + 1
                problems.append(f"⛔ {rel}:{line} — {why}: `{m.group(0)[:70]}`")
        if rel in LAUNCHERS and "runtime_paths" not in text:
            problems.append(f"⛔ {rel}: يضبط متغيّرات الجذر بلا المالك "
                            "(`shared.runtime_paths`) — الحارس يرفض الحُكمَين المتوازيين")
    owner = ROOT / "shared" / "runtime_paths.py"
    if not owner.is_file():
        problems.append("⛔ shared/runtime_paths.py مفقود — لا مالك للجذور")
        return problems
    t = owner.read_text(encoding="utf-8")
    if re.search(r"return\s+\w*[Rr]oot\s*/\s*[\'\"']var[\'\"']", t):
        problems.append("⛔ المالك يرجع صامتًا إلى PROJECT_ROOT/var")
    if "RuntimeError" not in t:
        problems.append("⛔ المالك بلا خطأ صريح عند جذر غير قانوني (regression: silent fallback)")
    for name in ("governance/server.py", "shared/parameter_registry.py",
                 "shared/live_analysis.py", "tools/approve_scalp_params.py",
                 "tools/set_scalp_weights.py", "governance/scripts/run_core.py"):
        p2 = ROOT / name
        if p2.is_file() and "runtime_paths" not in p2.read_text(encoding="utf-8"):
            problems.append(f"⛔ {name} يشتقّ مساراته بلا المالك (runtime_paths غير مذكور)")
    # `QUANT_ATOMS_ROOT`: لا يجوز أن يكون مفتاحًا بلا سلك ولا سلكًا بلا مفتاح
    rc = (ROOT / "governance" / "scripts" / "run_core.py")
    sets_it = any((ROOT / n).is_file() and "QUANT_ATOMS_ROOT" in (ROOT / n).read_text(encoding="utf-8")
                  for n in LAUNCHERS)
    reads_it = rc.is_file() and "QUANT_ATOMS_ROOT" in rc.read_text(encoding="utf-8")
    if sets_it != reads_it:
        problems.append(f"⛔ QUANT_ATOMS_ROOT: يُضبط={sets_it} يُقرأ={reads_it} "
                        "— مفتاح بلا سلك (لا يُطبَّق) أو سلك بلا مفتاح")
    # ⛔ لا مسار مطلق لخزنة/سجلّ في جذر المشروع من داخل المُقلِع
    for rel, path in _scan_targets():
        if rel not in LAUNCHERS:
            continue
        for m in re.finditer(r'(ROOT|_PROJECT)\s*/\s*"var"\s*/\s*"(?:forex|store)"', path.read_text(encoding="utf-8")):
            problems.append(f"⛔ {rel}: يرسو على جذر المشروع (`…/var/…`) بدل الـruntime — `{m.group(0)[:60]}`")
    return problems


def check_mirror_identity() -> list[str]:
    """ب: نسخة الـruntime ≡ الأصل في شجرة الكود. الفوركس صارم، والكريبتو مُعلَن."""
    problems: list[str] = []
    notes: list[str] = []

    def digest(p: Path) -> str:
        h = hashlib.sha256()
        with p.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest()

    for runtime in RUNTIMES:
        mirror = ROOT / runtime
        if not mirror.is_dir():
            continue
        for rel, outer in _scan_targets():
            inner = mirror / rel
            if not inner.is_file():
                problems.append(f"⛔ {runtime}/{rel}: مفقود والنسخة تنفّذه فعليًّا عند chdir")
                continue
            if inner.is_symlink():
                continue                       # وصلة = العقد مُرضًى بحكم التعريف
            if digest(inner) != digest(outer):
                msg = f"⛔ انحراف نسخة: {runtime}/{rel} ≠ {rel} — شجرتان بمنطقين"
                (problems if runtime == "forex_runtime" else notes).append(msg)
    if notes:
        print("   ℹ الكريبتو شجرة متشعّبة السجلّات (decision_dials/parameter_registry "
              "خاصّة بها) — انحرافها مُعلَن لا محجوب:")
        for n in notes:
            print("     " + n[2:])
    return problems


def check_meeting_points() -> list[str]:
    """ج: القارئ والواضع على المسار نفسه، والسوقان منفصلان — مقاسًا لا مذكورًا.

    ⛔ بلا `QUANT_RUNTIME_ROOT`: الفحص يريد أن يرى **اكتشاف** المالك لمجلّد
    الـruntime القانوني لا غشاء البيئة فوقه؛ الضبطُ كان يوَحّد الجذرين داخل
    نسخة الـruntime فيتَّهم الفحصُ عزلَ السوقين بالكسر وهو يعمل كما يُفترض.
    """
    problems: list[str] = []
    env_save = {k: os.environ.get(k) for k in
                ("QUANT_RUNTIME_ROOT", "QUANT_CORE_STATE_ROOT",
                 "QUANT_ANALYSIS_SETTINGS_DB", "QUANT_GOV_MARKET")}
    try:
        for k in ("QUANT_RUNTIME_ROOT", "QUANT_ANALYSIS_SETTINGS_DB",
                  "QUANT_CORE_STATE_ROOT"):
            os.environ.pop(k, None)
        os.environ["QUANT_GOV_MARKET"] = "forex"
        for mod in [m for m in list(sys.modules)
                    if m.startswith(("shared", "core", "governance"))]:
            sys.modules.pop(mod, None)
        try:
            from shared.runtime_paths import runtime_var, settings_db_path
        except Exception as exc:  # noqa: BLE001
            return [f"⛔ المالك لا يُستورد: {exc}"]
        # القاعدة = أبُو مجلّد governance: جذر المشروع في الأصل، وجذر الـruntime
        # في النسخة (يكتشفه المالك من اسم أبيه بلا طبقة زائدة).
        # نسخة الـruntime: لا شجرة فوقها تُشتقّ منها سوقان — الجذر هو مجلّدها
        # ويُقاس بقايا العقد لا بمقارنة سوقٍ بآخر. من جذر المشروع تُقاس الشجرتان.
        # بنية الملفّ: <root>/governance/checks/هذا (أصل أو نسخة runtime).
        # ``ROOT`` أبُو مجلّد governance = **جذر الشجرة التي يعمل منها**.
        in_mirror = ROOT.name in RUNTIMES
        code_root = ROOT
        if in_mirror:
            os.environ["QUANT_RUNTIME_ROOT"] = str(code_root)
        board_db = settings_db_path(code_root=code_root)
        try:
            from shared.parameter_registry import ParameterRegistry
            registry_path = ParameterRegistry().path
        except Exception as exc:  # noqa: BLE001
            registry_path = None
            problems.append(f"⛔ السجلّ المحكوم لا يُقرأ: {exc}")
        if registry_path is not None and Path(registry_path) != Path(board_db):
            problems.append(f"⛔ اللوحة تقرأ {board_db} والسجلّ يكتب {registry_path}")
        try:
            from shared.decision_dials import _default_registry_path
            dials_db = _default_registry_path()
            if Path(dials_db) != Path(board_db):
                problems.append(f"⛔ عيارات القرار تُقلع على {dials_db} لا على {board_db}")
        except Exception:  # noqa: BLE001 — نسخة كريبتو بلا decision_dials كاملة
            pass
        # server.py: كل مورد على المالك، لا حساب يدويّ من DATA_ROOT
        src = (ROOT / "governance" / "server.py").read_text(encoding="utf-8")
        hand = [f"  سطر {src[:m.start()].count(chr(10))+1}: {m.group(0)[:64]}"
                for m in re.finditer(r"=\s*DATA_ROOT\s*/", src)]
        if hand:
            problems.append("⛔ server.py يشتقّ موارد من DATA_ROOT يدويًا بدل المالك:\n"
                            + "\n".join(hand))
        # ذرّة ٥٨٠: مرساها cwd (عقد المُقلِع) لا parents[2]
        for atoms_dir in ("atoms", "atoms/قسم 550-599"):
            pass
        a580 = next(iter(sorted((ROOT / "atoms").glob("*580*/atom.py"))),
                    next(iter(sorted((ROOT / "atoms").glob("**/580*/atom.py"))), None))
        if a580 is not None:
            body = a580.read_text(encoding="utf-8")
            if re.search(r"parents\[\d\]\s*/\s*raw", body):
                problems.append(f"⛔ {a580.name}: tilt_rules ما يزال يرسو على parents[n]")
        # journal/snapshots: تُدار عبر state root مُعلَن لا PROJECT_ROOT مباشرة
        rc_text = (ROOT / "governance" / "scripts" / "run_core.py").read_text(encoding="utf-8")
        for m in re.finditer(r"PROJECT_ROOT\s*/\s*(journal_path|snapshot_path)", rc_text):
            problems.append(f"⛔ run_core يرسو {m.group(1)} على PROJECT_ROOT مباشرة "
                            "(يجب أن يمرّ بـstate_root)")
        # ٢٠٢٦-٠٩-٠٩ (أمر المالك «امسح»): كان هنا فحص عزل السوقين. لم يبقَ
        # سوق ثانٍ ولا `crypto_runtime`، فالمقيس الآن أنّ جذر الفوركس هو
        # `forex_runtime/var` بعينه — لا مقارنة بين اثنين.
        fx = runtime_var(code_root=code_root, market="forex").resolve()
        if in_mirror:
            own = ROOT / "var"
            if Path(fx) != own.resolve():
                problems.append(f"⛔ نسخة الـruntime تُقِلع على {fx} لا على {own}")
            print("   · ℹ من داخل نسخة الـruntime: الجذر هو جذر تلك النسخة "
                  "(يُقاس من جذر المشروع) — لا يُحتسب خرقًا")
        else:
            want = (ROOT / "forex_runtime/var").resolve()
            if fx != want:
                problems.append(f"⛔ جذر الفوركس ليس `{want}` بل {fx}")
        print(f"   · لقاء مُقاس (بلا غشاء بيئة): فوركس {fx}")
        print(f"   · سجلّ المعايرة (لوحة=سجلّ): {board_db}")
    finally:
        for k, v in env_save.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    return problems


def check_save_is_not_approve() -> list[str]:
    """د: «حفظ» يكتب مسودة، و«اعتماد» قرارٌ منفصل (لا اعتماد في مسار الحفظ)."""
    problems: list[str] = []
    dd = ROOT / "shared" / "decision_dials.py"
    if not dd.is_file():
        return [f"⛔ {dd} مفقود"]
    t = dd.read_text(encoding="utf-8")
    if "confirm" not in t:
        problems.append("⛔ decision_dials لا يفرّق الحفظ عن الاعتماد (لا حقل confirm)")
    if "write_value" not in t:
        problems.append("⛔ مسار الحفظ لا يستدعي write_value (مسودة بلا اعتماد)")
    body = t[t.index("def apply_command"):]
    approve_at = body.find("registry.approve(")
    guard_at = body.find("confirm is not True")
    if approve_at > 0 and (guard_at < 0 or guard_at > approve_at):
        problems.append("⛔ apply_command يعتمد قبل أن يحرس الحقل — الحفظ يعتمد ضمّنًا")
    pr = ROOT / "shared" / "parameter_registry.py"
    if pr.is_file() and "def write_value" not in pr.read_text(encoding="utf-8"):
        problems.append("⛔ ParameterRegistry.write_value مفقود — لا قناة حفظ بلا اعتماد")
    return problems


def check_junction_contract() -> list[str]:
    """هـ: عقد الوصلات لا يُمرَّر «كُتب kept» لمجلّد حقيقيّ محلّ وصلة."""
    problems: list[str] = []
    pu = ROOT / "scripts" / "prepare_unified.py"
    if not pu.is_file():
        return ["⛔ scripts/prepare_unified.py مفقود"]
    t = pu.read_text(encoding="utf-8")
    if "--convert-identical" not in t:
        problems.append("⛔ prepare_unified لا يملك مسار تحويل لا-تخريبيًّا للعقد")
    if "real directory where a link is contracted" not in t:
        problems.append("⛔ prepare_unified يمرّر مجلّدًا حقيقيًّا محلّ وصلة بلا رفض")
    return problems


def main() -> int:
    print(f"🧭 فحص سلطة المسارات — {ROOT}")
    sections = (("أ/المالك الوحيد", check_owner),
                ("ب/تطابق النسخ", check_mirror_identity),
                ("ج/نقاط اللقاء", check_meeting_points),
                ("د/الحفظ ≠ الاعتماد", check_save_is_not_approve),
                ("هـ/عقد الوصلات", check_junction_contract))
    all_problems: list[str] = []
    for title, fn in sections:
        try:
            problems = fn()
        except Exception as exc:  # noqa: BLE001 — الفحص الساقط فشلٌ لا نجاح
            problems = [f"⛔ {title}: استثناء {type(exc).__name__}: {exc}"]
        mark = "🟢" if not problems else "🛑"
        print(f"  {mark} {title}: {'سليم' if not problems else str(len(problems)) + ' خرقًا'}")
        for p in problems:
            print("     " + p)
        all_problems.extend(problems)
    if all_problems:
        print(f"\n🛑 فحص سلطة المسارات: {len(all_problems)} خرقًا — الإصلاح لازم قبل الإقلاع")
        return 1
    print("\n🟢 فحص سلطة المسارات: القارئ والواضع على جذر واحد، والنسخ مطابقة، "
          "والحفظ لا يعتمد")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
