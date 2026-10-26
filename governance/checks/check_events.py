#!/usr/bin/env python3
"""فحص عقود الأحداث الأساسية من المانيفستات، بلا تخمين وبلا نشر بيانات."""
from __future__ import annotations

import sys

from collections import defaultdict
from pathlib import Path
import ast

import yaml

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from build_registry.paths import RegistryAtomRoot
from governance.control_adapter import _CONTROL_EVENTS
ATOMS = RegistryAtomRoot(ROOT)

# ٢٠٢٦-٠٩-١٠: هذا الحارس **فشل في إعلان ما وجده**. طرفيّة ويندوز هنا بترميز
# cp1256، فطبعُ العلامة «❌» (U+274C) رفع `UnicodeEncodeError` قبل أن يظهر أيّ
# سبب — فالخرق موجود والرسالة ضائعة، والمنفّذ يرى انفجارًا لا تقريرًا. حارسٌ لا
# يُسمع كحارسٍ لا يوجد. يُفرض UTF-8 على المخرج قبل أوّل طبع، ويُتغاضى عن
# مخرجٍ لا يقبل الإعداد بدل أن يسقط الفحص من أجل حرف.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass

# هذه مصادر خارجية اختيارية. غياب ناشرها ليس انقطاعًا في مسار BTCUSD الحالي.
INTENTIONALLY_UNUSED_EVENTS = {
    "SYS_15MIN": "UNUSED_EVENT",
}

OPTIONAL_EXTERNAL_INPUTS = {
    # ٢٠٢٦-٠٩-٠٩ (ختم NQ): تنشره **النواة** نفسها عند إقلاع كل ذرّة، لا ذرّة
    # — مقيس على `/api/bus-stats`: `core.atom.started = 230`. فمسحُ مانيفستات
    # الذرّات لن يجد له ناشرًا أبدًا، وكان يُعلَن «مستمع بلا ناشر» كذبًا.
    "core.atom.started",
    # ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): ينشرها مدير الصحّة في النواة لا ذرّة، وصار 831
    # يسمعها (v1.1.0)؛ و`system.log.record` ينشره مرحّل سجلّ المحرّك (engine/process_logs.py)
    # وتسمعه 719 (v1.2.0).
    "core.atom.failed", "core.atom.unhealthy", "core.critical_atom.unhealthy",
    "core.atom.restarts_exhausted", "core.atom.restart_failed", "core.atom.restarted",
    "system.log.record",
    "market.trade",
    # Explicit owner/operator command; no autonomous publisher is allowed.
    "asset.extraction.retry_requested",
    # ٢٠٢٦-٠٩-٢٣ (ختم nq): `risk.asset_ledger.reset_requested` خرج من هنا —
    # صار له ناشر: ٩٠١ v2.8.0 (أمر الأصل `RESET_LEDGER` وزرّه في «التحكّم»).
    "feed.yahoo.tick",
    "feed.rithmic.tick",
    # External clock/replay inputs are optional surfaces in this release.
    # Their absence is reported, but it is not a broken internal edge.
    "SYS_10MS",
    "replay.session.start",
    "replay.session.stop",
}

# الرابط هنا مقصود ومثبت: (الحدث، الناشرون المطلوبون، المستمعون المطلوبون).
REQUIRED_LINKS = {
    # ٢٠٢٦-٠٩-٠٩ (ختم NQ): كان الجدول يتوقّع الناشر 622 — والكود يقول غير ذلك.
    # 622 ينشر `feed.ctrader.raw` و`heartbeat` و`state` (مانيفسته)، و**623
    # ناقل التغذية** هو ناشر التِكّة (`atom.py:24 EVENT_OUT`). السلسلة المقيسة:
    # 622 ──raw──► 624 ──depth──► 623 ──tick──► 613. الجدول بائت، والكود الحقيقة.
    # لم يُكتشف هذا سابقًا لأنّ الفحص كلّه كان يموت على `Mexc.tsx` قبل أن يصل هنا.
    "feed.ctrader.tick": ({623}, {521, 582, 613}),
    # 580 intentionally consumes only decision.gate.passed after owner approval;
    # requiring the pre-gate score here contradicted its sealed safety contract.
    # ٢٠٢٦-١٠-٠٧ (ختم المالك «NQ» — فكّ الأقسام عن القرار): سلسلة الحكم القديمة (451–466 · 581 · 413…)
    # أُرشفت؛ القرار من البطاقة 414 وحدها ⟵ 467 ⟵ 555. فخرج رابط `decision.scored.state` ودخل الرابطان:
    "decision.approved.state": ({414}, {467}),
    "decision.gate.passed": ({467}, {555}),
    "market.tick": ({613}, {112, 115}),
    "market.tick.validated": ({112}, {102, 103, 105}),
    # البند ٤ (حكم المالك): 467 توقّف عن نشر طلب التنفيذ وصار طبقة تشخيص تنشر
    # `decision.dispatch.state`؛ المنتِج هو مسار 581 وحده (576 البداية · 578 الفروق).
    # ٢٠٢٦-٠٩-٢٣ (ختم `nq 525+526+527`): 584→525 شرعيّة الستوب · 585→526 حارس
    # الهامش · 586→527 بوّابة الرموز — نُقلت إلى قسم 500-549 والأحداث نفسها.
    # ٢٠٢٦-٠٩-٢٣ (ختم `nq` «ارشف»): 576 و578 أُرشفتا ٢٠٢٦-٠٩-١٨، فخرجتا من
    # الجدول. الناشرون والمستمعون الباقون مقيسون من المانيفستات يومها لا مفترضون:
    # الطلب ينشره 555 (الدخول) و581 · والإقرار يسمعه 520/550/570 · واللقطة يسمعها 552.
    "execution.order.requested": ({555}, {527, 707}),
    "decision.dispatch.state": ({467}, {707}),
    "symbol.resolve.requested": ({527}, {708}),
    "symbol.resolve.result": ({708}, {527}),
    "execution.order.resolved": ({527}, {526}),
    "risk.margin.validation.completed": ({526}, {516}),
    "execution.order.built": ({551}, {550, 525, 703, 707}),
    "execution.order.legal": ({525}, {552}),
    "execution.command.ack": ({563, 601}, {520, 550, 570}),
    "platform.brain_signal.written": ({601}, {522, 550, 704}),
    "symbol.resolve.orphaned": ({527}, {704}),
    # ⚠️ مستمعه الوحيد كان 578 — فلا مستمع له اليوم (مقيس ٢٠٢٦-٠٩-٢٣). يبقى
    # شرط الناشر، ولا يُخترع مستمع؛ و582 ينشر إلى لا أحد حتى يقرّر المالك.
    "execution.reference_divergence.state": ({582}, set()),
    "execution.snapshot.state": ({583}, {552}),
    "asset.extraction.failed": ({579}, {524}),
    "risk.exposure.state": ({508}, {500, 552}),
    "learning.model.selected": ({366}, {367}),
    "model.persist_requested": ({367}, {706}),
    "model.persisted": ({706}, {367}),
    "portfolio.components.state": ({650}, {662, 668}),
}


def main() -> int:
    publishers: dict[str, set[int]] = defaultdict(set)
    subscribers: dict[str, set[int]] = defaultdict(set)
    problems: list[str] = []
    syntax_errors: list[str] = []

    for manifest in sorted(ATOMS.rglob("manifest.yaml")):
        try:
            data = yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}
            atom_id = int(data["id"])
            for event in data.get("publishes", []) or []:
                publishers[str(event)].add(atom_id)
            for event in data.get("subscribes", []) or []:
                subscribers[str(event)].add(atom_id)
            ast.parse((manifest.parent / "atom.py").read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            syntax_errors.append(f"{manifest.relative_to(ROOT)} — {exc}")

    for event, (wanted_publishers, wanted_subscribers) in REQUIRED_LINKS.items():
        actual_p = publishers.get(event, set())
        actual_s = subscribers.get(event, set())
        missing_p = wanted_publishers - actual_p
        missing_s = wanted_subscribers - actual_s
        if missing_p:
            problems.append(f"{event}: ناشرون ناقصون {sorted(missing_p)}")
        if missing_s:
            problems.append(f"{event}: مستمعون ناقصون {sorted(missing_s)}")

    for event, classification in INTENTIONALLY_UNUSED_EVENTS.items():
        if not publishers.get(event):
            problems.append(f"{event}: {classification} بلا ناشر")
        if subscribers.get(event):
            problems.append(f"{event}: مُصنّف {classification} لكن له مستمعون {sorted(subscribers[event])}")

    # م-55 (ورقة ٤١، 2026-08-28): قائمة مغلقة — ناشر platform.trade_event
    # الحقيقي الوحيد هو 611 (قارئ صفقات الوسيط). أي ناشر إضافي (جسر محاكاة،
    # أداة، ذرّة جديدة) على هذا الحدث تحديدًا = حقن محتمل بمسار المخاطر
    # والمحاسبة — يُرفض صراحة هنا مهما كانت نيّته.
    TRADE_EVENT_PUBLISHERS_CLOSED = {611}
    trade_publishers = publishers.get("platform.trade_event", set())
    rogue = sorted(trade_publishers - TRADE_EVENT_PUBLISHERS_CLOSED)
    if rogue:
        problems.append("ناشر غير مصرّح لـplatform.trade_event (خطر حقن بمسار المخاطر): " + ", ".join(map(str, rogue)))
    missing_real = TRADE_EVENT_PUBLISHERS_CLOSED - trade_publishers
    if missing_real:
        problems.append("القارئ الحقيقي 611 لم يعد ينشر platform.trade_event: " + ", ".join(map(str, sorted(missing_real))))

    # ٢٠٢٦-٠٩-٠٩ (أمر المالك «ما ضلّ شي اسمه قسم كريبتو»): كان هنا فحص عقد
    # نتيجة الصفقة اليدويّة على لوحة MEXC. **وكان الفحص كلّه ميتًا**: يقرأ
    # `governance/ui/src/sections/Mexc.tsx` وقد حُذف مع فصل الكريبتو، فيرمي
    # `FileNotFoundError` **قبل أن يفحص شيئًا** — أي حارسٌ لا يحرس. ومعه
    # `atoms_crypto/` غير موجود والذرّة 2275 غير موجودة، فحتى بإصلاح المسار
    # كان يفشل حتمًا. رُفع ما يخصّ السوق الثاني، **وبقي حارس التسرّب** أدناه:
    # مسار النتيجة اليدويّة يجب ألّا يُسمح به في نطاق الفوركس بحال.
    forex_allowed = _CONTROL_EVENTS.get("forex", frozenset())
    if "platform.trade_event" in forex_allowed:
        problems.append("تسرّب مسار نتيجة الصفقة اليدويّة إلى نطاق الفوركس")

    no_publisher = sorted(event for event in subscribers if not publishers[event])
    unexpected_no_publisher = [
        event for event in no_publisher if event not in OPTIONAL_EXTERNAL_INPUTS
    ]
    if unexpected_no_publisher:
        problems.append("أحداث لها مستمع بلا ناشر: " + ", ".join(unexpected_no_publisher))

    print("فحص أحداث المشروع")
    print(f"الأحداث المنشورة: {len(publishers)}")
    print(f"الأحداث المسموعة: {len(subscribers)}")
    print("الروابط الأساسية المفحوصة: %d" % len(REQUIRED_LINKS))
    print("الأحداث غير المستخدمة بقرار صريح: %s" % ", ".join(
        f"{event}={classification}" for event, classification in INTENTIONALLY_UNUSED_EVENTS.items()))
    print("مصادر خارجية اختيارية بلا ناشر: %s" % (", ".join(no_publisher) if no_publisher else "لا شيء"))
    print("مخرجات بلا مستمع: %d — هذه مخرجات عرض/سجل وليست انقطاعًا" % sum(
        1 for event in publishers if not subscribers[event]
    ))
    if syntax_errors:
        problems.extend("كود ذرة غير قابل للتحليل: " + item for item in syntax_errors)

    if problems:
        for problem in problems:
            print("❌ " + problem)
        return 1
    print("✅ الأحداث الأساسية موصولة؛ المصادر الخارجية غير المتاحة معلّمة اختيارية فقط.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
