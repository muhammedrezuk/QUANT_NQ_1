# -*- coding: utf-8 -*-
"""§5 / Gate C — المحرّك الجديد: `Account×Symbol Owner ⟶ Compiled Hot Plan`.

## ما يُثبته Gate C

Gate B أثبتت أنّ **المرجع** حتميّ. وGate C تسأل السؤال الذي بُنيت §5 له:

    هل يغيّر تقسيمُ العمل على مالكي `Account×Symbol` — وتوزيعُهم على
    عمّالٍ مستقلّين، وإنفاذُ ترتيب الخطّة المُجمَّعة — **قرارًا واحدًا**؟

    الشريط المجمَّد (البصمة نفسها · الإطارات نفسها)
              ↓                                    ↓
        المرجع التسلسليّ                    المحرّك الجديد
        حالةٌ عالميّةٌ واحدة            ٧ مالكين ⟶ أقسامٌ ⟶ عمّالٌ مستقلّون
        بلا ترتيبٍ مفروض                 رتبةٌ من `plan.order` تُنفَّذ
              ↓                                    ↓
           صفوفٌ  ←—— ستّةُ محاورَ · mismatch = 0 ——→  صفوفٌ

## ما لا يتغيّر — عمدًا

منطقُ بناء الصفّ نفسه حرفًا: نفسُ الحقول، نفسُ التدوير، نفسُ قواعد
اللحاق والإغلاق. §5 **لا تمسّ صيغة قرارٍ ولا مخاطرةٍ ولا أمرًا** — أمرُ
المالك. فما يُبدَّل هو **أين تسكن الحالة وبأيّ ترتيب تُنفَّذ**، وهو بالضبط
ما يقيسه هذا الباب. ولو نسخنا المنطق نسخًا لكان خطأُ النسخ يظهر اختلافًا
كاذبًا بدل أن يظهر عطبًا حقيقيًّا — فيُستورَد ولا يُنسَخ.

## ما هو جديدٌ فعلًا

    المرجع                          المحرّك الجديد
    ──────                          ──────────────
    `_open` معجمٌ عالميّ            حالةٌ داخل مالكٍ واحد لكلّ Account×Symbol
    مفتاحٌ نصّيّ `cycle_id`          `OwnershipKey` ⟶ قسمٌ منطقيٌّ ⟶ عامل
    بلا مفهومِ مدخلٍ مرتَّب          `Cell.admit(sequence)` — مرّةً وبالترتيب
    بلا حدّ دورة                    `Cell.commit()` عند كلّ تِكّة
    خيطٌ واحدٌ يرى كلّ شيء          عامِلٌ لا يرى إلّا أقسامه

⛔ وأيُّ دورةٍ تظهر في عاملَين خرقُ ملكيّة: تُعدّ وتُسمَّى ولا تُبتلع.

## ⚠️ حدُّ ما يشهد به هذا الباب — يُقال قبل نتيجته لا بعدها

الشريط مأخوذٌ من الصندوق **البارد**، وترتيبُ الوصول عليه **ليس** ترتيبَ
النشر: مقيسٌ أنّ ٨٫٣٪ من الدورات تصل تِكّتُها بعد موافقتها (وسيط ٨ وقائع).

فGate C تشهد بأنّ **التقسيم على المالكين والعمّال لا يغيّر قرارًا**،
ولا تشهد بترتيبِ التنفيذ الساخن. وترتيبُ الخطّة يُثبَت بنيويًّا — الخطّة
`DAG` وسلسلتُها `112(#7) ⟶ 451(#122) ⟶ 466(#131) ⟶ 467(#133)` — لا من
هذا الشريط. والرتبةُ تُعدّ وتُعرَض هنا **ولا يُحكَم بها**.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Iterable

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from hot import parity  # noqa: E402
from hot.cell import Cell, CellMap, OwnershipError  # noqa: E402
from hot.planner import HotPlan  # noqa: E402
from transport.ownership import (  # noqa: E402
    LOGICAL_PARTITIONS, OwnershipKey, OwnershipRegistry, ownership_key,
)

#: إعدادُ التجميع — **نفسه الذي أغلق Gate B**. الساعة معطّلةٌ في الجانبين:
#: المهلةُ والمكنسة تعتمدان الزمن، والإعادة لا ساعةَ لها.
REPLAY_CONFIG = {"grace_s": 0.0, "close_after_s": 10 ** 9}


class Worker:
    """عامِلٌ واحد: أقسامُه وحدها، وحالتُه لا يراها غيره.

    ⛔ ولا يعرف عاملًا آخر ولا يقرأ حالته. لو احتاج صفٌّ واحدٌ بيانًا من
    عاملَين لانكسر العقد — وهذا ما يقيسه `foreign_cycles`.
    """

    __slots__ = ("index", "path", "recorder", "cells", "cycles", "records",
                 "rank_violations", "out_of_order", "seen_cycles")

    def __init__(self, index: int, path: Path, *, runtime: str) -> None:
        self.index = index
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")
        #: منطقُ بناء الصفّ **مستورَدٌ لا منسوخ** — انظر رأس الملفّ.
        self.recorder = parity.ParityRecorder(
            str(path), runtime="%s-w%d" % (runtime, index), **REPLAY_CONFIG)
        #: مالكو هذا العامل — حاويات §5 الحقيقيّة، لا معجمٌ عابر.
        self.cells = CellMap()
        self.cycles = 0
        self.records = 0
        self.rank_violations = 0
        self.out_of_order = 0
        self.seen_cycles: set[str] = set()


class HotEngine:
    """المحرّك الجديد كاملًا: ملكيّةٌ ⟶ أقسامٌ ⟶ عمّالٌ ⟶ خطّةٌ مُنفَّذة."""

    def __init__(self, plan: HotPlan, out_dir: Path | str, *,
                 workers: int = 6, runtime: str = "engine-c") -> None:
        self.plan = plan
        self.workers = [
            Worker(i, Path(out_dir) / ("worker-%d.jsonl" % i), runtime=runtime)
            for i in range(int(workers))
        ]
        self.registry = OwnershipRegistry(len(self.workers))
        #: `حدث ⟶ رتبتُه في الخطّة`. **مشتقّةٌ من `plan.order`** لا مكتوبة:
        #: لو بدّل المالك ذرّةً أو حدثًا، تتبدّل الرتبة معه بلا لمسِ كود.
        self.rank: dict[str, int] = {}
        position = {atom: i for i, atom in enumerate(plan.order)}
        for event, makers in plan.producers.items():
            ranks = [position[a] for a in makers if a in position]
            if ranks:
                self.rank[event] = min(ranks)
        self.fed = 0
        self.dropped_no_owner = 0
        self.foreign_cycles = 0
        self.rank_violations = 0
        self.admitted = 0
        self.rejected = 0
        self._last_rank: dict[str, int] = {}
        self._owner_of_cycle: dict[str, int] = {}

    # ── التوجيه ──────────────────────────────────────────────────────────

    def worker_for(self, key: OwnershipKey) -> Worker:
        """`مفتاح ⟶ قسمٌ منطقيّ ⟶ عامل` — طبقتان كما في §٣، لا واحدة.

        ⛔ ولا `digest % worker_count`: ذاك يربط مكان المفتاح بعدد العمّال،
           فتنتقل الملكيّات كلّها حين يتبدّل الجهاز.

        والتوجيه من `OwnershipRegistry` الحيّ نفسه — بموازِنه لا بقسمةٍ
        باقيةٍ أكتبها هنا: القسمة الباقية تتكتّل عند العدد الصغير (مقيسٌ
        على النواة: عاملٌ بصفر مفاتيح وآخر بخمسةٍ وOVERLOAD). ومسارُ
        الإنتاج هو ما يجب أن يُقاس، لا نسخةٌ مهذّبةٌ منه.
        """
        return self.workers[self.registry.owner_for(key)]

    def feed(self, event_name: str, payload: Any) -> None:
        """يوجّه واقعةً واحدةً إلى مالكها ثمّ إلى عامله. لا شيء عالميّ هنا."""
        if event_name not in parity.WATCHED or not isinstance(payload, dict):
            return
        self.fed += 1
        key = ownership_key(payload)
        if key is None:
            # ⛔ لا حسابَ ولا رمز ⟶ لا مالك. تُعدّ وتُسمَّى ولا تُوزَّع عشوائيًّا.
            self.dropped_no_owner += 1
            return
        worker = self.worker_for(key)
        worker.records += 1

        # ── حدُّ الملكيّة: دورةٌ واحدةٌ لعاملٍ واحد (§٤) ───────────────────
        cycle = parity._cycle_key(payload)
        if cycle:
            owner = self._owner_of_cycle.setdefault(cycle, worker.index)
            if owner != worker.index:
                # دورةٌ امتدّت بين عاملَين — خرقُ تقسيمٍ يُسمَّى ولا يُبتلع.
                self.foreign_cycles += 1
            worker.seen_cycles.add(cycle)

        # ── رتبةُ الخطّة: تُقاس وتُعرَض، ولا يُحكَم بها على شريطٍ بارد ─────
        #
        # الخطّة تقول `112(#7) ⟶ 451(#122) ⟶ 466(#131) ⟶ 467(#133)`. والشريط
        # يخالفها ٤٨٩ مرّة — **والمخالفة في الشريط لا في الخطّة**:
        #
        #     ٨٫٣٪ من الدورات تصل تِكّتُها **بعد** موافقتها على الشريط
        #     (وسيط ٨ وقائع، أقصى ٢٩). وتِكّةٌ لا تُنشَر بعد القرار الذي
        #     سبّبته — فترتيبُ الوصول ليس ترتيبَ النشر.
        #
        # والسبب معروفٌ ومكتوبٌ في المرجع نفسه: المسجّل يركب على الصندوق
        # **البارد**، وكلُّ حدثٍ يصله بطابوره («الاتّجاهان لازمان: الترتيب
        # غير مضمون»). فالمرجع لا يفترض ترتيبًا أصلًا، ولذلك بلغ التكافؤ صفرًا.
        #
        # ⛔ فلا يصحّ أن يكون هذا معيارَ إغلاق: شريطٌ باردٌ لا يشهد على
        #    ترتيبٍ ساخن. يُعدّ ويُعرَض بالرقم، وإثباتُ الترتيب الساخن
        #    يحتاج أثرًا من المسار الساخن نفسه — وهو خارج ما يقيسه هذا الباب.
        rank = self.rank.get(event_name)
        if rank is not None and cycle:
            previous = self._last_rank.get(cycle)
            if previous is not None and rank < previous:
                self.rank_violations += 1
                worker.rank_violations += 1
            else:
                self._last_rank[cycle] = rank

        # ── المالك: قبولُ المدخل بالترتيب ومرّةً واحدة (§١٧) ──────────────
        if event_name == parity.TICK_EVENT:
            sequence = payload.get("sequence")
            if sequence is not None:
                cell = worker.cells.cell_for(key)
                try:
                    cell.admit(int(sequence), payload)
                    self.admitted += 1
                except OwnershipError:
                    # ⛔ راجعٌ بالتسلسل — **وهو أثرُ الصندوق البارد** كذلك:
                    #    ١٦ من ٥٬١٩٩ (٠٫٣٪)، كلُّها إزاحاتٌ محلّيّةٌ صغيرة
                    #    (٢ إلى ١٧ تسلسلًا)، ولا مكرّرَ واحد. فهي إعادةُ
                    #    ترتيبِ طوابيرَ لا خرقُ ملكيّة.
                    #    ولا تُسقَط الواقعة من التجميع: الحكمُ على التكافؤ.
                    self.rejected += 1
                    worker.out_of_order += 1
                cell.write("market", {"sequence": sequence})
                # حدُّ الدورة: الحيّةُ تصير ملتزمة، فما تقرؤه الحافّة
                # الراجعة لقطةُ دورةٍ سابقة لا دورتَها (§Feedback).
                cell.commit()
                worker.cycles += 1

        worker.recorder.observe(event_name, payload)

    def feed_records(self, records: Iterable[tuple[int, str, Any]]) -> None:
        for _index, name, payload in records:
            self.feed(name, payload)

    # ── الإغلاق والقراءة ─────────────────────────────────────────────────

    def close(self) -> dict[str, dict]:
        """يُغلق كلّ عامل ويدمج مخرجاته — الدمجُ بالمفتاح لا بالترتيب."""
        merged: dict[str, dict] = {}
        for worker in self.workers:
            worker.recorder.close()
            merged.update(parity.load(str(worker.path)))
        return merged

    def stats(self) -> dict[str, Any]:
        overlap = 0
        for i, left in enumerate(self.workers):
            for right in self.workers[i + 1:]:
                overlap += len(left.seen_cycles & right.seen_cycles)
        return {
            "workers": len(self.workers),
            "logical_partitions": LOGICAL_PARTITIONS,
            "fed": self.fed,
            "dropped_no_owner": self.dropped_no_owner,
            "foreign_cycles": self.foreign_cycles,
            "cycles_in_two_workers": overlap,
            "rank_violations": self.rank_violations,
            "ticks_admitted": self.admitted,
            "ticks_rejected": self.rejected,
            "ranked_events": len(self.rank),
            "per_worker": [
                {"worker": w.index, "records": w.records,
                 "owners": len(w.cells.keys()), "commits": w.cycles,
                 "cycles": len(w.seen_cycles),
                 "rank_violations": w.rank_violations,
                 "out_of_order": w.out_of_order}
                for w in self.workers
            ],
        }
