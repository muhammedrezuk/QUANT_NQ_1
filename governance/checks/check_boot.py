#!/usr/bin/env python3
"""Read-only Atom Boot check with dynamic expectations from Build Registry."""

from __future__ import annotations

import os
from pathlib import Path
import queue
import re
import subprocess
import sys
import tempfile
import threading
import time

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from build_registry import BuildRegistry  # noqa: E402

BOOT_PATTERN = re.compile(r"بدأت=\[(.*?)\] فشلت=\[(.*?)\] استُبعدت=\[(.*?)\]")


def boot_cfg_path(root: Path) -> Path:
    """ملفّ الإعداد الذي يقرؤه المُقلِع الإنتاجيّ نفسه — لا نسخة ثانية."""
    env = os.environ.get("QUANT_CORE_CONFIG")
    if env and Path(env).is_file():
        return Path(env)
    for candidate in (root / "forex_runtime" / "config" / "core_forex.yaml",
                      root / "config" / "core_forex.yaml",
                      root / "config" / "core.yaml"):
        if candidate.is_file():
            return candidate
    return root / "config" / "core_forex.yaml"


def _cold_scope(cfg: Path) -> tuple[list[tuple[int, int]], set[int], set[int], bool]:
    """نطاقات العمليّة الباردة (§٢١) — من الإعداد نفسه، بلا `yaml` كنظيرها.

    ٢٠٢٦-٠٩-٢٣ (ختم nq): منذ تفعيلها تُقلع 700-749 و800-949 في مفسّرٍ مستقلّ،
    فلا يذكرها تقرير إقلاع النواة — والحارس كان يعدّها غائبة: «بدأت 192 <
    الأرضيّة 217» والعمليّة الباردة أعلنت 32 ذرّة في السجلّ نفسه (192+32=224).
    المرض نفسه الذي أُصلح للمزرعة ٢٠٢٦-٠٩-١٦: عدٌّ صادق في حدوده يُقرأ انكماشًا.
    """
    try:
        text = cfg.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return [], set(), set(), False
    block = re.search(r"^([ \t]*)cold_process:[^\n]*\n((?:(?:\1[ \t]+[^\n]*)?\n)*)", text, re.M)
    body = block.group(2) if block else ""
    enabled = re.search(r"^\s+enabled:\s*true\s*$", body, re.M) is not None
    ranges: list[tuple[int, int]] = []
    sections = re.search(r"^\s+sections:\s*(\[.*?\])\s*$", body, re.M)
    if sections:
        for lo, hi in re.findall(r"\[\s*(\d+)\s*,\s*(\d+)\s*\]", sections.group(1)):
            ranges.append((int(lo), int(hi)))

    def ids(key: str) -> set[int]:
        found = re.search(r"^\s+%s:\s*\[([^\]]*)\]" % key, body, re.M)
        return {int(x) for x in re.findall(r"\d+", found.group(1))} if found else set()

    return ranges, ids("exclude"), ids("include"), enabled


def _farm_scope(cfg: Path) -> tuple[list[tuple[int, int]], bool]:
    """نطاقات مزرعة التحليل وحالة تفعيلها — من الإعداد لا من ذاكرة كاتبٍ.

    تُقرأ بلا `yaml` كي لا يعتمد حارس الإقلاع على استيراد قد يسقط: البحث عن
    كتلة `analysis_farm` ثمّ `enabled` و`sections` داخلها وحدها.
    """
    try:
        text = cfg.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return [], False
    # ٢٠٢٦-٠٩-١٦: الصيغة الأولى كانت `^analysis_farm:\s*$(.*?)(?=^\S)` ولم
    # تطابق شيئًا — `\s*` يبتلع السطر الجديد وما بعده فينهار الالتقاط بصمت،
    # والنتيجة `enabled=False` فتُلغى القسمة كلّها **ويبقى الحارس يصرخ كما
    # كان**. أي أنّ الإصلاح كان سيبدو منفَّذًا وهو معطَّل. الصيغة الآن صريحة:
    # سطر المفتاح، ثمّ كل سطر مُزاح أو فارغ بعده.
    block = re.search(r"^analysis_farm:[^\n]*\n((?:(?:[ \t][^\n]*)?\n)*)", text, re.M)
    body = block.group(1) if block else ""
    enabled = re.search(r"^\s+enabled:\s*true\s*$", body, re.M) is not None
    ranges: list[tuple[int, int]] = []
    sections = re.search(r"^\s+sections:\s*(\[.*?\])\s*$", body, re.M)
    if sections:
        for lo, hi in re.findall(r"\[\s*(\d+)\s*,\s*(\d+)\s*\]", sections.group(1)):
            ranges.append((int(lo), int(hi)))
    return ranges, enabled


def _reader(stream, output: queue.Queue[str]) -> None:
    try:
        for line in iter(stream.readline, ""):
            output.put(line)
    finally:
        stream.close()


def _stop(process: subprocess.Popen) -> None:
    # ⛔ ٢٠٢٦-٠٩-٢٣ (ختم nq): `terminate()` يقتل `run_core.py` وحده، والعمليّة
    # الباردة ابنُه (multiprocessing) تبقى يتيمةً تعمل — وُجدت ستّ منها من
    # تشغيلات هذا الحارس بين ١٩:٤٤ و٢١:٥٤، أربعٌ منها على بيانات المنصّة الحيّة
    # قبل العزل. على ويندوز تُقتل الشجرة كلّها (`taskkill /T`).
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                       capture_output=True, check=False)
    if process.poll() is not None:
        return
    try:
        process.terminate()
        process.wait(timeout=10)
    except Exception:  # noqa: BLE001
        try:
            process.kill()
            process.wait(timeout=5)
        except Exception:
            pass


def _numbers(text: str) -> list[int]:
    return [int(x.strip()) for x in text.split(",") if x.strip()]


def main() -> int:
    registry = BuildRegistry(ROOT).refresh()
    # إصلاح م-28 (ورقة ٤١، بأمر المالك 2026-08-28): عاد التوقع **المستقل الثابت**
    # إلى جانب توقّع Registry — فلو عُبث بالمانيفستات صمتًا (حذف ذرّة أو قلب
    # startup_mode) اكتشفه الفحص حتى لو ظل السجلّ متسقًا مع نفسه.
    # ٢٠٢٦-٠٩-٠٧ — ٢٣٣ ⇐ ٢٣٧ بقرار المالك: 526 · 555 · 623 · 624.
    # ٢٠٢٦-٠٩-١٦ — ٢٣٧ ⇐ ٢٣٥ **بختم `NQ` صريح**: المالك حذف بيده الذرّتين
    # ١١٣ (منظّف البيانات) و١١٤ (موحّد البيانات) وقال «شلتهم». وهذا الحارس هو
    # الذي كشف الحذف خلال ساعة («❌ توقع مستقل مخالف: forex=235»).
    #
    # ولم يُحدَّث الرقم يوم كُشف الحذف رغم أنّه كان يُسكِت الإنذار فورًا:
    # **تحديثه بلا ختمٍ التفافٌ على الحارس لا إصلاح له.** بقي يصرخ حتى جاء
    # الختم، فصار ٢٣٥ رقمًا مقروءًا بقرار لا رقمًا يُسكِت إنذارًا. والفرق
    # بينهما هو كل الفرق بين حارسٍ يُوثَق به وحارسٍ يُعلَّم تجاهله.
    #
    # وأثر الحذف مقيس ونظيف: صفر عقد حدثٍ مكسور (`check_events` — المنشورة
    # ٣٧٠⟵٣٦٨ والمسموعة ٢٩٧⟵٢٩٦، خرج الحدثان ومعهما مستهلكوهما)، وصفر ظهور
    # على أيّ شاشة، وصفر ذرّة تشترك فيهما. والملفّان محفوظان في `HEAD`.
    # ٢٠٢٦-١٠-٠٧ — ٢٣١ ⇐ ٢٢٦ **بختم المالك «nq»**: (١) 571 أُرشف في ١٠-٠٢ بختمه
    # (`0b5d545`) ولم يُحدَّث الرقم يومها، فبقي الفحص يصرخ «forex=230» منذئذ؛ (٢) أربع ذرّات
    # بلا مصدرٍ عند الوسيط نقلها المالك إلى أرشيف سطح المكتب: 107 شريط الصفقات · 256 الدلتا ·
    # 257 التراكميّ · 258 الامتصاص («ذرّات ميّتة ما ممكن تشتغل… مالها عمل»). مستهلكاها
    # (101 و465) نُزع منهما الاشتراك في الوقت نفسه، فلا مستمع بلا ناشر.
    # ٢٠٢٦-١٠-٠٧ ٢٢:٥٠ — ٢٢٦ ⇐ ١٩١ **بختم المالك «NQ»** (فكّ الأقسام عن القرار): خرجت ٣٦ ذرّة حكم إلى
    # سطح المكتب/أرشيف QUANT_NQ/فكّ الأقسام عن القرار — 36 ذرّة — 2026-10-07 (مدراء الأقسام والدمج ·
    # الاستراتيجيّات القديمة 400 و404–410 و413 · سلسلة القرار 450–466 · 581)، ودخلت البطاقة 414.
    # ٢٠٢٦-١٠-٠٨ — ١٩١ ⇐ ١٩٦ **بختم المالك «NQ»** («قبل كلّ شي لازم يعرف النظام»): خمس ذرّات معرفة —
    # 117 الوقت والعطل · 118 السياسة النقديّة · 119 ذاكرة الناسداك الموسميّة · 120 تصنيف الأخبار وأثرها ·
    # 469 محاسبة الصفقات. حقائق خام تُختم على كلّ صفقة (465)، ولا تدخل قرار الدخول إلّا بقياسها.
    # ١٩٦ ⇐ ١٩٨ بختمه أيضًا: 121 تسعير قرار الفائدة («تسعير الفائدة حيًّا يحتاج ياهو NQ») · 122 الشركات والأسواق
    # («بميتاتريدر في كلّ الأسهم» + الخوف والدولار) — وجلب الإنترنت كلّه في بوت الأخبار («تحت سقفٍ واحد»).
    EXPECTED_FOREX_ROOT = 198
    # 2026-08-29: مطابقة شجرة أحمد المُسلَّمة رفعت العدد 77 ← 84 (ورقة
    # ASMAR_كريبتو 16-20). الثابت مقصود: أي تغيّر صامت بالمانيفستات يُفشِل.
    # 2026-09-01: 84 ← 80. المالك حذف أربع ذرّات بيده («4 زرات انا مسحتهم
    # مالهم شغل»)، فصار الفحص يصرخ على قرارٍ مقصود كل مرّة — وحارسٌ يصرخ
    # على الصواب يُعلَّم تجاهله، فيصمت يوم يقع خطأ حقيقيّ. الثابت يُحدَّث مع
    # قرار المالك لا يُلتَفّ عليه. (`tests/test_unified_layout.py` حُدّث معه.)
    #
    # ٢٠٢٦-٠٩-١٦ — **الأرضيّة الثابتة ٢٢٠ سقطت.** كانت تعطي:
    #     «❌ أرضية مستقلة: بدأت 144 < 220 — انكماش صامت في الإقلاع»
    # وليس هناك انكماش: منذ تشغيل **مزرعة التحليل** (`analysis_farm.enabled`)
    # تُقلع ذرّات النطاق [150, 499] **داخل عمليّات المزرعة** لا في عمليّة
    # النواة، فلا يذكرها تقرير إقلاع النواة. فالتقرير صادقٌ في حدوده، و«بدأت»
    # تعني «أقلعتها عمليّة النواة» لا «أقلعت». (قِيس بجلسة النقل: من الـ84
    # الغائبة، **82 تُظهر أرقامًا حيّة متحرّكة** — أي أنّها تعمل فعلًا.)
    #
    # وهذا هو **نفس مرض «212/212»** الذي أُصلح في زرّ اللوحة اليوم: رقمٌ ثابت
    # مكتوب بيدٍ يشيخ بصمت، فيصرخ الحارس على الصواب حتى يُعلَّم تجاهله.
    # فالأرضيّة تُشتقّ الآن من نفس المصدر الذي يقرؤه المُقلِع: ذرّات `auto`
    # **خارج** نطاق المزرعة حين تكون مفعَّلة. ولا يُلتَفّ على الحارس: إن
    # عُطّلت المزرعة عادت الأرضيّة إلى كل ذرّات `auto` تلقائيًّا.
    farm_ranges, farm_on = _farm_scope(boot_cfg_path(ROOT))
    # م-44 (ورقة ٤١، 2026-08-28): تثبيت أوضاع الذرّات الحرجة — انقلاب startup_mode
    # صمتًا (مثل تحويل 901 أو 2901) كان يمرّ ما دام العدد الكلي مطابقًا.
    # ٢٠٢٦-٠٩-٠٥ (ختم المالك `NQ`: «ثبّته NQ — مؤجّلين إلى وقت لاحق»):
    # 576 (المحرّك الدائم) و578 (منفّذ التحوّط) صارا `manual` بقرار المالك
    # يوم فُتح التداول الاتجاهي — حكمه المقيس يومها: «ما عم يتداول، عم
    # يفتح هيدج جديد». هما ناشرا `execution.order.requested` الوحيدان
    # للزوج المتعادل، فبقاؤهما `auto` كان يفتح تحوّطًا يمحو الاتجاه.
    # التأجيل مؤقّت بنصّ المالك، والثابت يُعاد إلى "auto" يوم يرفعه —
    # لا يُلتَفّ على الحارس، بل يُحدَّث معه.
    CRITICAL_PINNED = {
        901: "auto", 516: "auto", 550: "auto", 552: "auto",
        576: "manual", 578: "manual",
        601: "auto", 613: "auto", 701: "auto", 703: "auto",
        2901: "manual", 625: "manual", 626: "manual",
    }
    expected_auto = {
        record.atom_id
        for record in registry.forex_all
        if record.atom_id is not None and record.startup_mode == "auto"
    }
    # ما تستضيفه المزرعة يُقلع في عمليّاتها لا في عمليّة النواة — فيُطرح من
    # المتوقَّع، والمقارنة تبقى بين متشابهين. (الشرح الكامل عند تعريف الأرضيّة.)
    hosted = {aid for aid in expected_auto
              if farm_on and any(lo <= aid <= hi for lo, hi in farm_ranges)}
    # والعمليّة الباردة كالمزرعة: تُقلع خارج النواة، فتُطرح بالقاعدة نفسها التي
    # يطبّقها المُقلِع (`run_core.py`: النطاقات − `exclude` + `include`).
    cold_ranges, cold_exclude, cold_include, cold_on = _cold_scope(boot_cfg_path(ROOT))
    cold = ({aid for aid in expected_auto if any(lo <= aid <= hi for lo, hi in cold_ranges)}
            - cold_exclude | (cold_include & expected_auto)) if cold_on else set()
    hosted |= cold
    core_expected = expected_auto - hosted
    # هامش الأمان نفسه الذي كان ضمنيًّا في ٢٢٠ مقابل ٢٣٧: يُسمح بغياب ٣٪ لا أكثر.
    MIN_STARTED_FLOOR = max(1, int(len(core_expected) * 0.97))
    if registry.integrity.missing_roots or registry.integrity.discovery_failures:
        print("❌ Registry discovery غير صالح قبل فحص الإقلاع")
        return 1
    by_id = {r.atom_id: r for r in registry.forex_all if r.atom_id is not None}
    flipped = {aid: (by_id[aid].startup_mode, want) for aid, want in CRITICAL_PINNED.items()
               if aid in by_id and by_id[aid].startup_mode != want}
    if flipped:
        print(f"❌ انقلاب وضع ذرّة حرجة صمتًا: {flipped} — قرار مالك مطلوب")
        return 1
    if len(registry.forex_all) != EXPECTED_FOREX_ROOT:
        print(f"❌ توقع مستقل مخالف: forex={len(registry.forex_all)} "
              f"(المتوقع {EXPECTED_FOREX_ROOT}) — تغيير صامت بالمانيفستات؟")
        return 1

    # ٢٠٢٦-٠٩-٠٣ (جولة ٢٠ · قرار مالك): قياس الإقلاع يجب أن يحترم **عقد الإقلاع**
    # نفسه: المُقلِع الإنتاجي `scripts/run_forex.py` يعمل os.chdir إلى نسخة الـruntime
    # قبل تحميل الذرّات. بقيت هذه الفحوص تُقلِع من جذر المستودع، فكل ثابت احتياطي على
    # هيئة "var\store\…" أنبت شجرة `var/` موازية تحت الجذر (٢٦ ملفًّا على HEAD نقيّ،
    # منها اسم بظهرٍ مائل حرفيٍّ) — أي أن الفحص كان يُخفي انحراف المسار بدل قياسه.
    # الأولوية لـQUANT_RUNTIME_ROOT إن مضبوطًا، وإلا نسخة forex_runtime إن وُجدت.
    boot_cwd = Path(os.environ.get("QUANT_RUNTIME_ROOT") or "") if os.environ.get("QUANT_RUNTIME_ROOT") else None
    if boot_cwd is None or not (boot_cwd / "shared" / "runtime_paths.py").is_file():
        boot_cwd = ROOT / "forex_runtime"
        if not (boot_cwd / "shared" / "runtime_paths.py").is_file():
            boot_cwd = ROOT          # لا شجرة runtime: نعود للجذر كما كان صراحةً

    temp = tempfile.TemporaryDirectory(prefix="quant_nq_boot_")
    # عقد المُقْلِع الإنتاجي حرفيًّا (انظر scripts/run_forex.py): مرسى حالة النواة
    # وملفّ إعداد السوق — بغيابه كانت journal/snapshots تُرسى على PROJECT_ROOT/var
    # (جذر المستودع) فتُنبت شجرة حالة موازية لا يقرأها أحد (قِيس ٢٦ ملفًّا على HEAD).
    _boot_cfg = boot_cwd / "config" / "core_forex.yaml"
    # ⛔ ٢٠٢٦-٠٩-٢٣ (ختم nq): كان الجذران هنا `forex_runtime` نفسه — أي أنّ هذا
    # الحارس يُقلع **منصّةً ثانية على بيانات المنصّة الحيّة**: لقطاتها ودفاتر
    # ٥١٦/٥١٧/٥١٨ ودفتر بطاقات ٤٦٥ ومخازن ٧xx، بينما الحيّة تعمل. (والجسر
    # وحده كان معزولًا.) الكود والإعداد يبقيان من `forex_runtime` (cwd وملفّ
    # الإعداد المطلق)، والحالة كلّها — `var/…` لكلّ ذرّة ومرسى النواة — في
    # مجلّدٍ مؤقّت يُرمى بعد الفحص. العدّ نفسه يُقاس، ولا يُمَسّ حرفٌ حيّ.
    _iso = Path(temp.name) / "runtime"
    (_iso / "var" / "store").mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, PYTHONUTF8="1", PYTHONUNBUFFERED="1", PYTHONDONTWRITEBYTECODE="1",
               QUANT_CORE_STATE_ROOT=str(_iso / "var"),
               QUANT_RUNTIME_ROOT=str(_iso))
    if _boot_cfg.is_file():
        env.setdefault("QUANT_CORE_CONFIG", str(_boot_cfg))
    env["NQ_BRIDGE_DB"] = str(Path(temp.name) / "bridge.db")
    env["NQ_CTRADER_FEED"] = str(Path(temp.name) / "ctrader.jsonl")
    command = [sys.executable, str(ROOT / "governance" / "scripts" / "run_core.py"), "--no-api"]

    process = subprocess.Popen(
        command,
        cwd=str(boot_cwd),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )
    assert process.stdout is not None
    lines: queue.Queue[str] = queue.Queue()
    thread = threading.Thread(target=_reader, args=(process.stdout, lines), daemon=True)
    thread.start()
    deadline = time.monotonic() + 60
    boot_line = ""
    recent: list[str] = []
    try:
        while time.monotonic() < deadline:
            try:
                line = lines.get(timeout=0.25)
            except queue.Empty:
                if process.poll() is not None:
                    break
                continue
            recent.append(line.rstrip())
            recent = recent[-20:]
            if "انتهى الإقلاع:" in line:
                boot_line = line
                break
    finally:
        _stop(process)
        try:
            temp.cleanup()
        except OSError:
            # مقبضٌ يُفلت متأخّرًا على ويندوز: المجلّد مؤقّت ويُكنس لاحقًا —
            # لا يُسقط فحصَ إقلاعٍ نجح. (العمليّات نفسها قُتلت بشجرتها أعلاه.)
            pass

    print("فحص الإقلاع الفعلي عبر Build Registry")
    print(f"المتوقع تلقائيًا من Registry: {len(expected_auto)}")
    if not boot_line:
        print("❌ لم يصل تقرير الإقلاع خلال 60 ثانية")
        for line in recent[-8:]:
            print(line)
        return 1

    match = BOOT_PATTERN.search(boot_line)
    if not match:
        print("❌ تقرير الإقلاع وصل لكن صيغته غير قابلة للقراءة")
        print(boot_line.rstrip())
        return 1

    started = _numbers(match.group(1))
    failed = _numbers(match.group(2))
    excluded = _numbers(match.group(3))
    # المقارنة تكون بين متشابهين: ما تقلعه عمليّة النواة مقابل ما يُتوقَّع منها،
    # لا مقابل كل ذرّات `auto` ومنها ما تستضيفه المزرعة في عمليّاتها.
    missing = sorted(core_expected - set(started))
    unexpected = sorted(set(started) - expected_auto)
    print(f"بدأت فعليًا في عمليّة النواة: {len(started)}")
    if farm_on:
        print(f"تستضيفها مزرعة التحليل (خارج عمليّة النواة): {len(hosted - cold)} "
              f"— النطاق {', '.join(f'{lo}-{hi}' for lo, hi in farm_ranges)}")
    if cold_on:
        print(f"تُقلعها العمليّة الباردة (خارج عمليّة النواة): {len(cold)} "
              f"— النطاق {', '.join(f'{lo}-{hi}' for lo, hi in cold_ranges)}")
    print(f"المتوقَّع من عمليّة النواة: {len(core_expected)} · الأرضيّة المشتقّة: {MIN_STARTED_FLOOR}")
    print(f"فشلت: {failed or 'لا شيء'}")
    print(f"استُبعدت: {excluded or 'لا شيء'}")
    if len(started) < MIN_STARTED_FLOOR:
        print(f"❌ انكماش صامت: بدأت {len(started)} < الأرضيّة {MIN_STARTED_FLOOR} "
              f"(المتوقَّع من النواة {len(core_expected)}"
              + (f" بعد استبعاد {len(hosted)} تستضيفها المزرعة" if farm_on else "") + ")")
        return 1
    if missing or unexpected or failed:
        print(f"❌ اختلاف الإقلاع: missing={missing or 'لا شيء'} unexpected={unexpected or 'لا شيء'}")
        return 1
    # 2026-09-01: الرسالة كانت تطبع «233/77» نصًّا ثابتًا بينما الثابت الفعليّ
    # صار 84 ثم 80 — أي حارس يعلن رقمًا غير الذي فحص به. تُشتقّ من الثابتين.
    print(f"✅ Atom Boot يطابق auto المكتشفة + التوقع المستقل "
          f"{EXPECTED_FOREX_ROOT} + أوضاع الذرّات الحرجة مثبّتة (م-44).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())