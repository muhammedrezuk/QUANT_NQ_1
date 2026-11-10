#!/usr/bin/env python3
"""Read-only execution safety inspection through Build Registry.

The checker may use atom IDs as identity, but never assumes a filesystem path.
It is a policy checker outside Core; it does not start or mutate execution.
"""

from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in __import__("sys").path:
    __import__("sys").path.insert(0, str(ROOT))
from build_registry import BuildRegistry
MQL5 = ROOT / "mt5" / "QUANT_NQ.mq5"
ACTIVE_EX5 = ROOT / "mt5" / "QUANT_NQ.ex5"


def _version(value: Any) -> tuple[int, int, int]:
    m = re.match(r"^\s*(\d+)\.(\d+)\.(\d+)", str(value or ""))
    return tuple(int(x) for x in m.groups()) if m else (0, 0, 0)


def _record(snapshot, atom_id: int):  # noqa: ANN001
    matches = snapshot.find_atom(atom_id, scope="forex")
    return matches[0] if len(matches) == 1 else None


def _manifest(record) -> dict[str, Any]:  # noqa: ANN001
    if record is None or not record.manifest_path:
        return {}
    try:
        return yaml.safe_load(Path(record.manifest_path).read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


def _source(record, *names: str) -> str:  # noqa: ANN001
    if record is None:
        return ""
    base = Path(record.path)
    parts: list[str] = []
    for name in names:
        path = base / name
        if path.is_file():
            parts.append(path.read_text(encoding="utf-8", errors="replace"))
    return "\n".join(parts)


# ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): بوّابة الإقلاع بلا أسنان (تدقيق ٢٠٢٦-١٠-٠٢ ع-06).
# شروط ٥٧٨ (حارس الفيضان ومقارنة صورة الوسيط) تنحّت بأرشفتها ٢٠٢٦-٠٩-١٨ ولم يحلّ
# محلّها شيء، وعتبات ٥١٦ لا تعترض إلّا على 999٪. الآن تُفحص السلسلة الحاليّة كما
# تعلنها مانيفستاتها (مقيس من BuildRegistry):
#   ٥٥٥ و٥٨١ ⟵ execution.order.requested ⟵ ٥٢٧ ⟵ execution.order.resolved ⟵ ٥٢٦
#   ⟵ risk.margin.validation.completed (ومعها ٥١٦) · ٥٢٥ execution.order.legal
#   ⟵ ٥٥٢ ⟵ trading.final_decision ⟵ ٦٠١ (الجسر).
# غياب حلقة منها يمنع التنفيذ. واختلاف رقم الكود عن رقم البطاقة **يُعلَن ولا يمنع**:
# إصلاحات اليوم ترفع `ATOM_VERSION` وحده وتترك رفع البطاقة لإعادة تشغيلٍ يأمر بها
# المالك، فلو منع لأغلق التنفيذ عند أوّل إقلاع بعدها.
# ٢٠٢٦-١٠-٠٧ (ختم المالك «NQ» — فكّ الأقسام عن القرار): أُرشفت ٥٨١ مع سلسلة الحكم القديمة،
# وصار ٥٥٥ وحده ينشر `execution.order.requested` (قرار البطاقة 414 ⟵ 467 ⟵ 555). بقاؤها هنا
# كان يغلق البوّابة على ذرّةٍ أُخرجت عمدًا — الدرس نفسه الذي كُتب لـ٥٧٦ و٥٧٨ أدناه.
CHAIN: dict[int, str] = {
    555: "طالب أمر الدخول",
    527: "بوّابة الرموز",
    525: "شرعيّة الستوب",
    526: "حارس الهامش",
    516: "قاطع الأمان",
    552: "مدقّق الأمر",
    601: "كاتب جسر الدماغ",
}
_CODE_VERSION = re.compile(r'^ATOM_VERSION\s*=\s*["\'](\d+\.\d+\.\d+)["\']', re.M)

# حدود ٥١٦. «بلا أسنان» = قيمةٌ لا يمكن أن يقطع عندها القاطع قبل ذهاب الحساب، أو
# قيم التعطيل القديمة (999/100000/100) — هذه تمنع. وما فوق قرار المالك التشغيليّ
# يُعلَن ولا يمنع: 30٪ أمر المالك ٢٠٢٦-٠٩-١٨ («max_daily_loss_pct هاد من 5 لا 30
# رفعو»)، ثمّ 90٪ أمره ٢٠٢٦-٠٩-٢٤ للحساب التجريبيّ 52992818 («حط بدك ياه ديمو عم
# نختبر … فك قاطع») — قرارُه فلا يُغلق عليه الإقلاع، ويُعلَن كلّ إقلاعٍ حتى يُخفَّض.
LOSS_PCT_NO_TEETH = 100.0
LOSS_PCT_OWNER_OPERATING = 30.0
DISABLE_SENTINELS = {"max_consecutive_losses": 999, "max_daily_trades": 100000,
                     "max_open_trades": 100}


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _code_version(record) -> str | None:  # noqa: ANN001
    match = _CODE_VERSION.search(_source(record, "atom.py"))
    return match.group(1) if match else None


def inspect(project_root: Path | None = None) -> tuple[bool, list[str]]:
    """واجهة المُقلِع (`run_core.py`): (جاهز؟، الموانع). التنبيهات تُطبع ولا تمنع."""
    ok, problems, warnings = inspect_report(project_root)
    for warning in warnings:
        print("⚠️ سلامة التنفيذ (تنبيه لا يمنع): " + warning)
    return ok, problems


def inspect_report(project_root: Path | None = None) -> tuple[bool, list[str], list[str]]:
    root = (project_root or ROOT).resolve()
    snapshot = BuildRegistry(root).refresh()
    problems: list[str] = []
    warnings: list[str] = []
    # ٢٠٢٦-٠٩-٢٣ (ختم `nq 525+526+527`) — نُقلت ٥٨٤ شرعيّة الستوب إلى الهويّة
    # ٥٢٥ في `قسم 500-549` (ومعها ٥٨٥→٥٢٦ و٥٨٦→٥٢٧). كان هذا الحارس يطلب ٥٨٤
    # بالاسم فأغلق البوّابة على ذرّةٍ موجودة باسمٍ جديد — يحرس رقمًا لا معنًى.
    records = {atom_id: _record(snapshot, atom_id)
               for atom_id in sorted({516, 552, 578, 525, 708, *CHAIN})}

    # ٢٠٢٦-٠٩-١٨ (ختم NQ) — أمر المالك: «ذرّات معطّلة انقلها على أرشيف،
    # ما لها شغل الآن». نُقلت ٥٧٦ و٥٧٨ إلى
    # `Desktop/ارشيف — أصداف الترقيم القديم — QUANT_NQ — 2026-09-08/
    #  ذرّتان معطّلتان بأمر المالك — 576 و578 — 2026-09-18`.
    #
    # وكان هذا الحارس يشترط وجودهما، فصار يمنع التشغيل لغياب ذرّةٍ
    # أُخرجت عمدًا — أي يحرس ماضيًا لا حاضرًا. وشروطُ ٥٧٨ أدناه مكتوبةٌ
    # أصلًا بـ`if record_578 is not None`، فهي تتنحّى من نفسها؛ الباقي
    # سطرُ الغياب هذا وشرطُ الإصدار في بوّابة ٥٥٢.
    OPTIONAL = {576, 578}
    for atom_id, record in records.items():
        if record is None and atom_id not in OPTIONAL:
            link = f" ({CHAIN[atom_id]} — حلقة في سلسلة التنفيذ)" if atom_id in CHAIN else ""
            problems.append(f"Registry لا يجد ذرة الفوركس ذات الهوية {atom_id}{link}")

    # ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): رقم الكود مقابل رقم البطاقة لكلّ حلقة — يُعلَن ولا يمنع.
    for atom_id in CHAIN:
        record = records[atom_id]
        if record is None:
            continue
        code = _code_version(record)
        if code is None:
            warnings.append(f"{atom_id} ({CHAIN[atom_id]}) بلا ATOM_VERSION مقروء في atom.py")
        elif code != str(record.version or ""):
            warnings.append(f"{atom_id} ({CHAIN[atom_id]}) الكود {code} ≠ البطاقة {record.version}"
                            " — رفع البطاقة بيد المالك")

    # ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): خلفُ حارس الفيضان في ٥٧٨ (resend_hold_s ومقارنة
    # صورة الوسيط قبل الإعادة) هو «الطلب الطائر» في ٥٥٥: يُعدّ الطلب مركزًا حتى يظهر أثره
    # في `platform.positions.state` (صورة الوسيط) أو تنقضي `inflight_ttl_s`
    # (`555/entry_request_inputs.py:39-67`). بلا مهلة موجبة أو بلا صورة الوسيط يُعاد
    # الطلب نفسه مع كلّ قرار — وهو بعينه الفيضان الذي وُجد ٥٧٨ لمنعه.
    record_555 = records[555]
    if record_555 is not None:
        manifest_555 = _manifest(record_555)
        cfg_555 = manifest_555.get("config") if isinstance(manifest_555.get("config"), dict) else {}
        props_555 = ((manifest_555.get("config_schema") or {}).get("properties") or {})
        ttl = _number(cfg_555.get("inflight_ttl_s"))
        if "inflight_ttl_s" not in props_555 or ttl is None or ttl <= 0.0:
            problems.append("555 بلا مهلة طلبٍ طائر موجبة (inflight_ttl_s) — لا حارس فيضان يخلف 578")
        if "platform.positions.state" not in (record_555.subscribes or ()):
            problems.append("555 لا تشترك في platform.positions.state — لا مقارنة بصورة الوسيط قبل إعادة الطلب")
        whole_555 = _source(record_555, *sorted(p.name for p in Path(record_555.path).glob("*.py")))
        if "_inflight" not in whole_555:
            problems.append("555 بلا كود الطلب الطائر (_inflight) — لا حارس فيضان يخلف 578")

    record_578 = records[578]
    manifest_578 = _manifest(record_578)
    source_578 = _source(record_578, "atom.py", "flood_guard.py")
    actual_version = _version(manifest_578.get("version"))
    if record_578 is not None and actual_version < (2, 1, 0):
        problems.append(f"578 إصدارها {manifest_578.get('version')}; المطلوب ≥ 2.1.0 مع حارس الفيضان")
    config_578 = manifest_578.get("config") if isinstance(manifest_578.get("config"), dict) else {}
    schema_578 = manifest_578.get("config_schema") if isinstance(manifest_578.get("config_schema"), dict) else {}
    props_578 = schema_578.get("properties") if isinstance(schema_578.get("properties"), dict) else {}
    if record_578 is not None and ("resend_hold_s" not in props_578 or "resend_hold_s" not in config_578):
        problems.append("578 لا تعلن resend_hold_s في العقد والإعداد")
    if record_578 is not None and "resend_hold_s" not in source_578:
        problems.append("578 لا تحتوي حارس resend_hold_s في الكود")
    if record_578 is not None and not all(word in source_578.lower() for word in ("broker", "snapshot")):
        problems.append("578 لا تثبت مقارنة صورة الوسيط الفعلية قبل إعادة الإرسال")

    record_552 = records[552]
    manifest_552 = _manifest(record_552)
    if record_552 is not None and bool((manifest_552.get("config") or {}).get("enabled", False)):
        source_552 = _source(record_552, "atom.py", "order_validation.py")
        missing: list[str] = []
        if "_perpetual_budget_contract" not in source_552:
            missing.append("552 بلا عقد الرجل الدائمة")
        # شروط ٥٧٨ تُفحص إن كانت موجودة؛ وقد أُخرجت بأمر المالك ٢٠٢٦-٠٩-١٨.
        if record_578 is not None:
            if "PROTECTION_PERPETUAL" not in source_578:
                missing.append("578 ما زالت تلصق ستوب وسيط على الرجل الدائمة")
            if "_protection_blocks" not in source_578:
                missing.append("578 بلا أمر تحوط ذري — يُنفَّذ نصفه فيصفّي المركز")
            if actual_version < (2, 5, 0):
                missing.append(f"578 إصدارها {manifest_578.get('version')}; فتح البوابة يتطلب ≥ 2.5.0")
        if missing:
            problems.append("552 enabled=true بلا إصلاحاتها: " + " · ".join(missing))

    manifest_525 = _manifest(records[525])
    if records[525] is not None and float((manifest_525.get("config") or {}).get("stop_buffer", 0.0)) <= 0.0:
        problems.append("525 stop_buffer=0 — لا وسادة أمان فوق حد الوسيط")

    manifest_708 = _manifest(records[708])
    if records[708] is not None and not ((manifest_708.get("config") or {}).get("broker_map") or {}):
        problems.append("708 broker_map فارغ — لا يجوز تفعيل أصل قبل مطابقة رمز الوسيط صراحة")

    if MQL5.is_file():
        bridge = MQL5.read_text(encoding="utf-8", errors="replace")
        if "EnsureSymbol" not in bridge or "SYMBOL_UNAVAILABLE_AT_BROKER" not in bridge:
            problems.append("إكسبرت MT5 بلا مسار ضمّ رمز صريح مع إبلاغ رفض الوسيط (EnsureSymbol)")
        if "InpMaxCmdAgeSec  = 2" not in bridge:
            problems.append("إكسبرت MT5 لا يفرض عمر أمر أقصاه ثانيتان")
        command_block = bridge.split("CREATE TABLE IF NOT EXISTS commands", 1)[-1].split(");", 1)[0]
        if "account_id TEXT" not in command_block:
            problems.append("جسر MT5 لا يضع account_id داخل جدول commands — خطر تنفيذ مزدوج بين الطرفيات")
        if "CHECK (id=1)" in bridge and "CREATE TABLE IF NOT EXISTS account" in bridge:
            problems.append("جسر MT5 يفرض صف حساب واحد — تعدد الحسابات غير آمن")
    if ACTIVE_EX5.is_file():
        problems.append("QUANT_NQ.ex5 موجود في مسار التشغيل دون إثبات بصمته مع المصدر — انقله للأرشيف أو أعد Compile")

    manifest_516 = _manifest(records[516])
    cfg_516 = manifest_516.get("config") if isinstance(manifest_516.get("config"), dict) else {}
    if records[516] is not None:
        # ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): كانت 999٪ وحدها تعترض — فخسارة يوميّة 500٪
        # تمرّ «جاهزة». الآن: حدٌّ غير مقروء أو ≥ 100٪ (لا يقطع قبل ذهاب الرصيد كلّه) أو
        # قيمة تعطيل ⟸ يمنع؛ وما فوق قرار المالك التشغيليّ ⟸ يُعلَن ولا يمنع.
        limits = {key: _number(cfg_516.get(key)) for key in
                  ("max_daily_loss_pct", *DISABLE_SENTINELS)}
        unreadable = sorted(key for key, value in limits.items() if value is None)
        if unreadable:
            problems.append("516 حدود قاطع الأمان غير مقروءة: " + ", ".join(unreadable))
        loss = limits["max_daily_loss_pct"]
        if loss is not None and loss >= LOSS_PCT_NO_TEETH:
            problems.append(f"516 حدّ الخسارة اليوميّة {loss:g}٪ ≥ {LOSS_PCT_NO_TEETH:g}٪"
                            " — لا يقطع قبل ذهاب الرصيد كلّه، القاطع بلا أسنان")
        disabled = sorted(key for key, cap in DISABLE_SENTINELS.items()
                          if limits[key] is not None and limits[key] >= cap)
        if disabled:
            problems.append("516 حدود قاطع الأمان موضوعة كقيم تعطيل (999/100000/100): "
                            + ", ".join(disabled) + " — القاطع لا يملك أسنانًا")
        if loss is not None and LOSS_PCT_OWNER_OPERATING < loss < LOSS_PCT_NO_TEETH:
            warnings.append(f"516 حدّ الخسارة اليوميّة {loss:g}٪ فوق {LOSS_PCT_OWNER_OPERATING:g}٪"
                            " (أمر المالك ٢٠٢٦-٠٩-١٨) — قيمة الحساب التجريبيّ بأمره ٢٠٢٦-٠٩-٢٤؛"
                            " لا تمنع الإقلاع، وتُخفَّض قبل أيّ حساب حقيقيّ")

    # ٢٠٢٦-٠٩-٠٧ — أُزيل فحص cBot سي‑تريدر: الطريق القديم (روبوت + ملفّ جسر)
    # مؤرشف نهائيًّا بأمر المالك، وبديله 622 (FIX مباشر) لا قائمة رموز فيه
    # بيد الروبوت. الأرشيف: ورق/أرشيف/الطريق_القديم_روبوت_سي_تريدر/
    return not problems, problems, warnings


def main() -> int:
    ok, problems, warnings = inspect_report()
    print("فحص سلامة التنفيذ عبر Build Registry")
    print("EXECUTION_SAFETY=" + ("READY" if ok else "BLOCKED"))
    print("سلسلة التنفيذ المفحوصة: " + " · ".join(f"{i} {n}" for i, n in CHAIN.items()))
    for warning in warnings:
        print("⚠️ " + warning)
    if ok:
        print("✅ أهداف التنفيذ اكتُشفت بالهوية لا بالمسار؛ يمكن متابعة فحوص البيئة فقط.")
        return 0
    for problem in problems:
        print("❌ " + problem)
    print("لا يجوز تشغيل التنفيذ أو اعتبار الحزمة جاهزة قبل إدخال النسخة الصحيحة.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
