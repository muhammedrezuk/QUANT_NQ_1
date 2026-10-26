# -*- coding: utf-8 -*-
"""المرحلة ١ — حارس الساعة: هل `monotonic` على مستوى النظام؟

عقد المهلة المعتمَد (`UNRESOLVED-2`، ٢٠٢٦-٠٩-١٦) يقوم على بندٍ واحد:

    deadline = authoritative monotonic age

أي أنّ **النواة تختم** `created_mono` و**العامل يقرؤه** فيحسب العمر:

    age = time.monotonic() - created_mono

⛔ **وهذا صحيحٌ فقط إذا كان `monotonic` على مستوى النظام لا العمليّة.**
ولغةُ بايثون **لا تضمن ذلك**: `time.monotonic()` معرَّفٌ بأنّه لا يرتدّ،
ولا يُشترَط أن تكون نقطة أصله مشتركة بين العمليّات.

والمقيس على هذه المنصّة (٢٠٢٦-٠٩-١٦):

    win32 ⟶ GetTickCount64()   عدّاد تشغيلٍ على مستوى النظام
    adjustable = False          لا تمسّه تسوياتُ ساعة الحائط
    resolution = 0.015625 ث     ⟵ ١٥٫٦ م.ث

فالفرضيّة صحيحةٌ **هنا**. وهذا الحارس يمنع أن تصير خطأً **صامتًا** على
منصّةٍ أخرى: عمرٌ محسوبٌ من أصلين مختلفين يعطي رقمًا بلا معنى، فتُرفض
أعمالٌ سليمة أو تُقبل أعمالٌ شاخت — **وكلاهما قرارُ مال**.

⚠️ والدقّة تُفحص أيضًا: مهلةٌ بالثواني تحتمل ١٥٫٦ م.ث، وقياسُ ما دون
المئة ملّي ثانية **لا يُبنى على هذه الساعة**.

يُشغَّل: ``python governance/checks/check_monotonic_scope.py``
يخرج 0 إن صحّت الفرضيّة، و2 إن سقطت.
"""
from __future__ import annotations

import io
import multiprocessing as mp
import sys
import time

#: عدد العيّنات — واحدةٌ قد تصدق بالصدفة.
SAMPLES = 3
#: أقصى انتظارٍ لطفلٍ واحد. الإقلاع البارد لـ`spawn` على ويندوز ثقيل.
CHILD_TIMEOUT_S = 60.0
#: أخشن دقّةٍ مقبولة. أعلى منها يعني أنّ المهلة بالثواني نفسها تهتزّ.
MAX_RESOLUTION_S = 0.1
#: السياق نفسه الذي يستعمله `transport/process_factory.py`.
CONTEXT = "spawn"


def _child(queue) -> None:  # noqa: ANN001 — يعبر حدّ العمليّة
    queue.put((time.monotonic(), time.perf_counter()))


def _probe(ctx) -> tuple[bool, bool, float]:  # noqa: ANN001
    """عيّنةٌ واحدة: أيقع زمن الابن بين طرفَي نافذة الأب؟"""
    queue = ctx.Queue()
    process = ctx.Process(target=_child, args=(queue,))
    mono_before, perf_before = time.monotonic(), time.perf_counter()
    process.start()
    try:
        child_mono, child_perf = queue.get(timeout=CHILD_TIMEOUT_S)
    finally:
        process.join(timeout=CHILD_TIMEOUT_S)
    mono_after, perf_after = time.monotonic(), time.perf_counter()
    return (
        mono_before <= child_mono <= mono_after,
        perf_before <= child_perf <= perf_after,
        child_mono - mono_before,
    )


def main() -> int:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    info = time.get_clock_info("monotonic")
    print("حارس الساعة — عقد المهلة `UNRESOLVED-2`")
    print("=" * 70)
    print("المنصّة   : %s" % sys.platform)
    print("التنفيذ   : %s" % info.implementation)
    print("adjustable: %s" % info.adjustable)
    print("الدقّة     : %.6f ث" % info.resolution)
    print()

    problems: list[str] = []

    if info.resolution > MAX_RESOLUTION_S:
        problems.append(
            "دقّة `monotonic` %.4f ث أخشن من الحدّ %.4f ث — المهلة نفسها تهتزّ"
            % (info.resolution, MAX_RESOLUTION_S))

    ctx = mp.get_context(CONTEXT)
    mono_ok = perf_ok = True
    for index in range(SAMPLES):
        in_mono, in_perf, offset = _probe(ctx)
        mono_ok &= in_mono
        perf_ok &= in_perf
        print("   عيّنة %d   monotonic %-8s (%+.3f ث)   perf_counter %s"
              % (index + 1,
                 "داخل ✅" if in_mono else "خارج ⛔", offset,
                 "داخل ✅" if in_perf else "خارج ⛔"))

    print()
    if not mono_ok:
        problems.append(
            "`monotonic` **ليس على مستوى النظام** على هذه المنصّة — "
            "فلا يجوز ختم `created_mono` في النواة وقراءته في العامل. "
            "العقد يلزمه مرجعٌ آخر (مثل مدّةٍ متبقّية تُرسَل بدل طابع)")

    if problems:
        print("⛔ سقطت الفرضيّة:")
        for line in problems:
            print("   • %s" % line)
        print()
        print("⟹ المرحلة ٣ (ختم المهلة من النواة) **لا تُنفَّذ كما هي**.")
        return 2

    print("✅ `monotonic` على مستوى النظام ودقّته كافية —")
    print("   ختمُ النواة `created_mono` يقرؤه العامل صحيحًا،")
    print("   و`age = monotonic() - created_mono` معنًى لا رقمًا عشوائيًّا.")
    if not perf_ok:
        print()
        print("ℹ️  `perf_counter` ليس على مستوى النظام هنا — ولا يضرّ:")
        print("   العقد يستعمل `monotonic` وحده عبر الحدّ.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
