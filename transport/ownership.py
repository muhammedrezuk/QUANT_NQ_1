"""Event Ownership runtime primitives.

The runtime separates ingress/routing from handler execution while preserving
FIFO ordering for each handler.  It is intentionally independent of the
trading atoms: the existing EventBus adapter can adopt it without changing
atom logic or event names.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import time
from collections import Counter, deque
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from core.event_bus import _coalesce_key, _is_command, _is_replayable


@dataclass(frozen=True, slots=True)
class OwnershipKey:
    account_id: str
    symbol: str

    #: فاصل المفتاح — ASCII عمدًا.
    #:
    #: ⛔ كان `×` (U+00D7)، فوصل إلى لوحة المالك مشوّهًا: `52992818ÃUSTEC`
    #: (بايتا UTF-8 قُرئا Latin-1 في مكانٍ ما على الطريق). وحقلٌ يعرض
    #: «مَن يملك ماذا» ثمّ يكذب في الاسم أسوأ من غيابه — §٣٠ تجعله أهمّ ما
    #: تعرضه اللوحة. الفاصل الآن `|` كما في `cycle_id` القائم، فلا يبقى
    #: للترميز مدخل أصلًا بدل ملاحقته على كلّ طبقة.
    SEPARATOR = "|"

    @property
    def text(self) -> str:
        return f"{self.account_id}{self.SEPARATOR}{self.symbol}"


def ownership_key(payload: Any) -> OwnershipKey | None:
    if not isinstance(payload, dict):
        return None
    account = payload.get("account_id") or payload.get("account")
    symbol = payload.get("symbol") or payload.get("asset")
    if account is None or symbol is None:
        return None
    account_text = str(account).strip()
    symbol_text = str(symbol).strip().upper()
    if not account_text or not symbol_text:
        return None
    return OwnershipKey(account_text, symbol_text)


# عدد الأقسام المنطقية — ثابت في الكود ومستقلّ تمامًا عن الجهاز
# (ورقة المالك «مصنع معالجة قابل للتوسع» §٥).
#
# لماذا طبقة وسيطة أصلًا؟ لأنّ التوزيع المباشر `digest % worker_count` يربط
# مكان المفتاح بعدد العمّال، فتنتقل كلّ الملكيات حين يتغيّر الجهاز — وهذا ما
# تمنعه §٢١ نصًّا: «نفس الملكية · نفس الأقسام» على ٦ أنوية أو ١٢ أو ٢٤.
# بالأقسام، القسم ثابت أبدًا (`digest % 64`) والمتغيّر الوحيد هو خريطة
# القسم ← العامل.
#
# ٦٤ **مثال تصميميّ لا رقم نهائيّ** (§٢٦): الشرط الوحيد أن يفوق عدد العمّال
# المتوقّع بكثير، فتبقى الخريطة قابلة لإعادة التوزيع بحبيبات ناعمة. يُثبَّت
# الرقم النهائيّ بعد قياسات §٢٤.
LOGICAL_PARTITIONS = 64

#: حالات القسم في بروتوكول الانتقال (ورقة المصنع §٧).
#:
#:      ACTIVE ──begin_migration──▶ DRAINING ──snapshot_taken──▶ HANDOVER
#:         ▲                           │                            │
#:         └────────abort──────────────┴──────complete_migration────┘
#:
#: و`PINNED` خارج المسار كلّه: قسمٌ مرتبط بمركز مفتوح **يُثبَّت مكانه**
#: ولا يُنقل بحال (§٧ نصًّا). التثبيت يسبق البدء ويُبطله.
PARTITION_ACTIVE = "ACTIVE"
PARTITION_PINNED = "PINNED"
PARTITION_DRAINING = "DRAINING"
PARTITION_HANDOVER = "HANDOVER"


class MigrationRefused(RuntimeError):
    """نقلٌ يمنعه بروتوكول §٧ — مركز مفتوح، أو حالة لا تسمح بالخطوة."""


def default_worker_count() -> int:
    """عدد العمّال مشتقًّا من موارد الجهاز — لا رقم أنوية مثبّت في الكود.

    §٨: «لا يوجد رقم ثابت للمعالج داخل الكود» · §٣٣ تمنع «تثبيت عدد العمليات
    على الجهاز الحالي». هذه **بذرة مؤقّتة** لا سياسة نهائية: §٢٥ و§٢٦ تفرضان
    أن يُشتقّ العدد من الحمل المقاس وقدرة الوحدة، لا من قسمة على الأنوية.

    ⚠️ ملحوظتان مقيستان 2026-09-10 يجب أن تحسمهما قياسات §٢٤:

    ١) ``os.cpu_count()`` يُرجع **الخيوط المنطقية لا الأنوية**: جهاز المالك
       ٦ أنوية / ١٢ خيطًا، فيُرجع ١٢ والناتج هنا ٦ — أي عاملٌ لكلّ نواة
       فيزيائية، وهو **١٠٠٪ من الأنوية لا ٥٠٪** كما تستهدف §١٩. لا سبيل في
       المكتبة القياسية لعدّ الأنوية الفيزيائية، والفارق يعتمد على SMT.

    ٢) العمّال اليوم مهامّ asyncio على حلقة واحدة، فعددهم **لا يضيف معالجًا
       إطلاقًا** — يوزّع الصناديق فقط. يصير هذا العدد ذا معنًى حقيقيّ حين
       يصير العامل عمليةً حقيقية (المرحلتان F/G).
    """
    logical = os.cpu_count() or 4
    return max(1, logical // 2)


class OwnershipRegistry:
    """خريطة الملكية: ``Account×Symbol`` ← قسم منطقيّ ← عامل فيزيائيّ.

    طبقتان لا واحدة (ورقة المالك §٤): الوحدة المنطقية تحمل الملكية والحالة،
    والعامل الفيزيائيّ يحمل التنفيذ. المفتاح يُنسب إلى قسمه ببصمة ثابتة (لا
    ``hash`` العشوائيّ) فيبقى القسم نفسه عبر الإقلاعات وعبر الأجهزة، ولا
    تتبدّل إلّا خريطة القسم ← العامل.

    و``reassign`` صريحة عمدًا: §٧ تفرض انتقالًا منظَّمًا (إيقاف ⟵ إنهاء ⟵
    لقطة ⟵ تسليم ⟵ تسجيل) وتمنع النقل الحيّ العشوائيّ — فلا يُحرَّك مالك
    بصمت. البروتوكول نفسه لم يُبنَ بعد؛ هذه نقطة ارتكازه.
    """

    def __init__(self, worker_count: int, *, reserved_workers: Any = ()) -> None:
        requested = int(worker_count)
        self.worker_count = requested if requested > 0 else default_worker_count()
        # ⛔ **العطب المقيس على النواة الحيّة ٢٠٢٦-٠٩-١٦.**
        #
        # المسار البارد بُني ليُبعد المخازن عن طريق السوق. لكنّ العامل البارد
        # بقي عاملًا عاديًّا في نظر خريطة الملكية، فأُسندت إليه نطاقات سوق:
        #
        #     العامل البارد 5 يملك 52992818|XAUUSD و US500 و USTEC#1
        #     وعليه ذرّات تحليل بطوابير: 407=453 · 412=455 · 166=206
        #     خلف 707 (53 م.ث/حدث) · 714 (89) · 712 (طابور 1024)
        #
        # فصار المسار الذي يحمي السوق من التخزين **يحمل السوق خلف التخزين**.
        # والموازنة ضاعفت الأذى بعد إصلاحها: تقيس الحِمل بعدد الورود لا بزمن
        # الانشغال، فيبدو العامل البارد «خفيفًا» (أحداثه قليلة وبطيئة) فتُرسل
        # إليه المزيد — عقوبةٌ على البطء بمزيدٍ من العمل.
        #
        # العلاج: يُحجز العامل البارد فلا يُسنَد إليه نطاقٌ ولا يُنقل إليه.
        # وهو **ليس** تعطيلًا لمساره: المشترِكون الباردون يُثبَّتون عليه
        # مباشرةً في `OwnershipRuntime`, لا عبر خريطة النطاقات.
        #: مصدر عمق الصناديق — يصله `OwnershipRuntime` عبر
        #: `set_backlog_source`. بلا مصدرٍ يرتدّ الوزن إلى عدّاد الورود
        #: **معلَنًا** لا صامتًا (`worker_load` أدناه).
        self._backlog_source: Any = None
        self._reserved = {int(w) for w in (reserved_workers or ())
                          if 0 <= int(w) < self.worker_count}
        #: العمّال الذين يجوز أن يُسنَد إليهم نطاق — لا يصحّ أن تفرغ.
        self._open_workers = [w for w in range(self.worker_count)
                              if w not in self._reserved] or list(
                                  range(self.worker_count))
        self.logical_partitions = LOGICAL_PARTITIONS
        # خريطة القسم ← العامل: هي وحدها ما يتغيّر بتغيّر الجهاز (§٢١).
        # القيمة الأوّلية قسمةٌ باقية، لكنّها **مبدئية**: أوّل استعمال فعليّ
        # لقسمٍ يُعيد إسناده لأقلّ العمّال حِملًا عبر `_assign`، لأنّ القسمة
        # الباقية تتكتّل عند العدد الصغير من المفاتيح الحيّة.
        self._partition_map: dict[int, int] = {
            partition: self._open_workers[partition % len(self._open_workers)]
            for partition in range(self.logical_partitions)
        }
        #: الأقسام التي أُسنِدت فعلًا (لها مفتاح حيّ) — أساس موازنة الحِمل.
        self._assigned_partitions: set[int] = set()
        #: عدّاد الورود لكلّ قسم — أساس الموازنة بالحِمل لا بالعدد.
        self._traffic: dict[int, int] = {}
        #: المالك لكلّ وحدة. المفتاح وحده بلا تقسيم، و``(مفتاح، مجموعة)``
        #: مع §١٤ — فالشكل القديم يبقى كما هو حين لا تقسيم.
        self._owners: dict[Any, int] = {}
        #: حالة القسم في بروتوكول §٧ — الغائب `ACTIVE`.
        self._partition_state: dict[int, str] = {}
        self._migration_target: dict[int, int] = {}

    @staticmethod
    def partition_for(key: OwnershipKey, group: int = 0) -> int:
        """القسم المنطقيّ للمفتاح — ثابت مدى حياة المفتاح، ولا يعرف الجهاز.

        هذا هو موضع الاستقرار: ينتقل المشروع بين ٦ أنوية و٢٤ فيبقى كلّ مفتاح
        في قسمه، ولا يتبدّل إلّا العامل الذي ينفّذ ذلك القسم.

        و``group`` هو §١٤: الرمز المهيمن يُقسَم إلى مجموعات فتصير الوحدة
        ``Account × Symbol × مجموعة``. المجموعة تدخل البصمة نفسها، فتبقى
        القسمة ثابتةً عبر الإقلاعات كما كانت ولا يُضاف بُعدٌ جانبيّ.

        و``group=0`` يعطي البصمة القديمة **حرفيًّا** — فبلا تقسيمٍ معلَن لا
        تتبدّل خريطةُ مفتاحٍ واحد.
        """
        text = key.text if not group else "%s#%d" % (key.text, int(group))
        digest = hashlib.blake2b(text.encode("utf-8"), digest_size=8).digest()
        return int.from_bytes(digest, "big") % LOGICAL_PARTITIONS

    def owner_for(self, key: OwnershipKey | None, group: int = 0) -> int:
        if key is None:
            return 0
        partition = self.partition_for(key, group)
        self._traffic[partition] = self._traffic.get(partition, 0) + 1
        owner_key: Any = key if not group else (key, int(group))
        current = self._owners.get(owner_key)
        if current is not None:
            return current
        current = self._assign(partition)
        self._owners[owner_key] = current
        return current

    # ── الموازنة بالحِمل لا بالعدد ──────────────────────────────────────
    #
    # ⛔ العطب المقيس ٢٠٢٦-٠٩-١٠ بعد موازنة العدد: المفاتيح توزّعت بالتساوي
    # عدديًّا، **والطوابير تباعدت** — ثلاثة عمّال عند ١٥–٢٠ ألفًا وثلاثة عند
    # ١–٣٣٣. السبب أنّ رمزًا نشطًا يساوي عدّة رموز هادئة: التوازن العدديّ
    # ليس توازن حِمل. والعلاقة بين الطابور وعمر التِكّة رتيبة بلا استثناء
    # (٢ ⟵ 0.2ث · 333 ⟵ 0.6ث · 20,213 ⟵ 239ث)، فاختلال الحِمل يترجَم
    # تأخّرًا مباشرًا في القرار.

    def decay_traffic(self, *, factor: float = 0.5) -> None:
        """يُنصّف الوزن التاريخيّ فيصير المقياس **حِملًا حاليًّا لا سِجلًّا**.

        ⛔ العطب: عدّاد تراكميّ من الإقلاع يجعل الموازنة تحكم على ماضٍ ميت.
        دفقةٌ عند الإقلاع تُثبّت الحكم إلى الأبد، فتبقى الطوابير تتباعد
        والموازنة «راضية» — مقيس ٢٠٢٦-٠٩-١٠: طابور العامل ٢ نما
        ٢١٬٢٩٩ ⟵ ٢١٬٦٩١ بينما انكمش الخامس ١٬٢٨٠ ⟵ ٥٠، ولم يتحرّك شيء.

        التنصيف الدوريّ يجعل الوزن نافذةً متحرّكة: ما يحدث الآن يغلب ما حدث
        قبل ساعة، فتتبع الموازنة السوق لا تاريخه.
        """
        if not 0.0 < factor < 1.0:
            raise ValueError("factor يجب أن يكون بين صفر وواحد")
        for partition in list(self._traffic):
            decayed = int(self._traffic[partition] * factor)
            if decayed <= 0:
                self._traffic.pop(partition, None)
            else:
                self._traffic[partition] = decayed

    def set_backlog_source(self, source: Any) -> None:
        """يصل السجلَّ بعمق صناديق العمّال — يضعه `OwnershipRuntime`.

        السجلّ يملك الخريطة (قسم ← عامل) ولا يملك الصناديق، والعمّال
        يملكون الصناديق ولا يملكون الخريطة. فالوصل صريحٌ هنا، لا استيرادٌ
        متبادل ولا تخمين.
        """
        self._backlog_source = source

    def worker_traffic(self) -> dict[int, int]:
        """ما **ورد** إلى كلّ عامل منذ الإقلاع — عدّادٌ تراكميّ لا حالة.

        يبقى لأنّه المؤشّر الوحيد المتاح **لكلّ قسمٍ على حدة**: عمق الطابور
        يُقاس لكلّ صندوقِ معالِج لا لكلّ قسم. فالتراكم يقول «أيّ عاملٍ
        متأخّر»، وهذا يقول «أيّ قسمٍ منه يستحقّ النقل».

        ⚠️ والمحجوز (المسار البارد) **لا يظهر هنا**: حِمله ليس نطاقات سوق
        فلا يُقارَن بها، وظهوره صفرًا يجعله يبدو أخفّ الجميع فتُرسَل إليه
        النطاقات — وهو ما وقع فعلًا على النواة الحيّة.
        """
        load = dict.fromkeys(self._open_workers, 0)
        for partition in self._assigned_partitions:
            worker = self._partition_map[partition]
            if worker in load:
                load[worker] += self._traffic.get(partition, 0)
        return load

    def worker_load(self) -> dict[int, int]:
        """حِمل كلّ عامل بـ**ما تراكم عنده**، لا بما ورد إليه.

        ⛔ **العطب الذي يعالجه، مقيسًا على النواة الحيّة ٢٠٢٦-٠٩-١٦:**

            عامل 1  طابور      0  ·  NORMAL
            عامل 2  طابور 24,593  ·  OVERLOAD  ·  أُسقط 81,032
            عامل 3  طابور 15,128  ·  OVERLOAD  ·  أُسقط 86,748
            rebalanced = 1   ⟵ منذ الإقلاع كلّه

        كان الوزن بعدّاد **الورود**. والورود متقارب بين الرموز بطبعه (كلّ
        رمزٍ يُنشَر له بمعدّلٍ مشابه)، فيرى الموازِنُ توازنًا ويخرج من
        `min_gain` — **بينما عاملٌ يغرق بأربعةٍ وعشرين ألفًا وجارُه صفر**.
        الفارق في **كلفة الخدمة** لا في عدد الوارد: مشترِكٌ بمعالِجٍ ثقيل
        يراكم بنفس الورود.

        وأثرُه مقيسٌ على المال: فجوة استلام التِكّة بلغت **٣٤٠ ثانية**
        للذهب و٠٫٦ ث لليورو — نفس الناشر ونفس التسلسل، والفارق موضعُ
        الرمز في التوزيع. فرُفض ٢٨٥ أمرًا بحقّ على سعرٍ بائت.

        ⚠️ **وهذا مقياسٌ لحظيّ لا تراكميّ**، وهو المقصود: الموازِن يعالج
        حالةً قائمة لا تاريخًا. ويحرسه `min_gain` من التذبذب.
        """
        if self._backlog_source is None:
            # ⚠️ **ارتدادٌ معلَن لا صامت**: سجلٌّ بلا مصدر تراكم (اختبارُ
            #    وحدة، أو استعمالٌ خارج وقت التشغيل) يبقى على السلوك
            #    السابق حرفًا بدل أن يرى أصفارًا فيوزّع على الوهم.
            return self.worker_traffic()
        depths = self._backlog_source()
        return {worker: int(depths.get(worker, 0)) for worker in self._open_workers}

    def partition_weight(self, partition: int, load: dict[int, int] | None = None) -> float:
        """نصيبُ قسمٍ من تراكم عامله — بحصّته من وروده.

        عمق الطابور يُقاس لكلّ **صندوق معالِج**، والقسم ليس صندوقًا. فيُوزَّع
        تراكمُ العامل على أقسامه بنسبة ما ورد لكلٍّ منها. وبهذا تتّحد وحدة
        القياس: `worker_load` تراكمٌ، وهذه تراكمٌ كذلك — فمقارنتهما في
        `rebalance` صحيحة، بينما خلطُ التراكم بالورود كان يقارن شيئين.
        """
        owner = self._partition_map.get(partition)
        if owner is None:
            return 0.0
        siblings = [p for p in self._assigned_partitions
                    if self._partition_map.get(p) == owner]
        total_traffic = sum(self._traffic.get(p, 0) for p in siblings)
        if total_traffic <= 0:
            return 0.0
        backlog = (load if load is not None else self.worker_load()).get(owner, 0)
        return backlog * (self._traffic.get(partition, 0) / total_traffic)

    def rebalance(self, *, max_moves: int = 1, min_gain: float = 0.15) -> list[tuple[int, int, int]]:
        """ينقل أثقل قسمٍ من أثقل عاملٍ إلى أخفّه — عبر بروتوكول §٧ لا بالدهس.

        ``min_gain`` هامشٌ يمنع التذبذب: لا يُنقل شيء ما لم يكن الفارق بين
        الأثقل والأخفّ أكبر من هذه النسبة من الحِمل الكليّ. ونقلٌ واحد في
        الاستدعاء افتراضًا — الموازنة تدريجيّة لا قفزة.

        والأقسام المثبَّتة (مركز مفتوح) لا تتحرّك بحال (§٧).

        يعيد قائمة `(القسم، من، إلى)` بما نُفِّذ فعلًا.
        """
        moves: list[tuple[int, int, int]] = []
        for _ in range(max(1, int(max_moves))):
            load = self.worker_load()
            total = sum(load.values())
            if total <= 0 or self.worker_count < 2:
                break
            heaviest = max(load, key=lambda w: load[w])
            lightest = min(load, key=lambda w: load[w])
            if heaviest == lightest:
                break
            if (load[heaviest] - load[lightest]) <= min_gain * total:
                break

            movable = [
                partition for partition in self._assigned_partitions
                if self._partition_map[partition] == heaviest
                and self.state_of(partition) == PARTITION_ACTIVE
            ]
            if not movable:
                break
            # أثقل قسمٍ يترك أكبر أثر، لكن لا يُنقل إن قلب الميزان.
            # ⚠️ **بالتراكم لا بالورود** (٢٠٢٦-٠٩-١٦): `load` صارت عمق
            #    الطابور، فوزنُ القسم يجب أن يكون بالوحدة نفسها وإلّا
            #    قارنّا شيئين. و`partition_weight` توزّع تراكم العامل على
            #    أقسامه بحصّة وروده.
            weights = {p: self.partition_weight(p, load) for p in movable}
            movable.sort(key=lambda p: weights[p], reverse=True)
            chosen = next(
                (p for p in movable
                 if load[lightest] + weights[p] < load[heaviest]),
                None,
            )
            if chosen is None:
                break

            # §١٤: الوحدة قد تكون `(مفتاح، مجموعة)` — فالقسم يُقرأ بدالّةٍ
            # تفهم الشكلين، لا بـ`partition_for` مباشرةً.
            owner_key = next(
                (k for k in self._owners if self.partition_of_owner(k) == chosen),
                None)
            if owner_key is None:
                break
            self.begin_migration(owner_key, lightest)
            self.mark_snapshot_taken(chosen)
            self.complete_migration(chosen)
            moves.append((chosen, heaviest, lightest))
        return moves

    def _assign(self, partition: int) -> int:
        """يُسنِد قسمًا لأقلّ العمّال حِملًا — لا `partition % workers`.

        ⛔ العطب الذي يعالجه، مقيسًا على النواة الحيّة ٢٠٢٦-٠٩-١٠:

            keys_per_worker = {0: 0, 1: 1, 2: 5, 3: 1, 4: 2, 5: 1}
            العامل 0: صفر مفاتيح · النوبة NORMAL · إسقاط صفر
            العامل 2: خمسة مفاتيح · OVERLOAD · إسقاط 868,404

        السبب أنّ القسمة الباقية تتكتّل عند العدد الصغير: عشرة مفاتيح حيّة
        موزّعة على ٦٤ قسمًا، فأيّها يقع على أيّ عامل رهن الصدفة لا التوازن.
        وهذا نصّ معيار الفشل §٣١: «عامل مختنق بينما الآخرون خاملون».

        الإسناد هنا حتميّ رغم أنّه بالحِمل: نفس مجموعة المفاتيح بنفس ترتيب
        الورود تعطي نفس الخريطة، والتعادل يُفَضّ بالقسمة الباقية — فيبقى
        سلوك النظام قابلًا لإعادة الإنتاج في التشخيص.

        والقسم يبقى ثابتًا كما هو (§٢١): المتغيّر خريطة القسم ← العامل وحدها.
        """
        assigned = self._partition_map.get(partition)
        if assigned is not None and partition in self._assigned_partitions:
            return assigned
        # المحجوز خارج المنافسة: لا يُحسب حِمله ولا يُختار (المسار البارد).
        load = dict.fromkeys(self._open_workers, 0)
        for owned in self._assigned_partitions:
            owner = self._partition_map[owned]
            if owner in load:
                load[owner] += 1
        lightest = min(load, key=lambda worker: (load[worker], (worker - partition) % self.worker_count))
        self._partition_map[partition] = lightest
        self._assigned_partitions.add(partition)
        return lightest

    def layout(self) -> dict[str, Any]:
        """«مَن يملك ماذا؟» — §٣٠ تجعله أهمّ ما تعرضه اللوحة.

        يُخرج التوزيع كاملًا معلَنًا: عدد العمّال، عدد الأقسام، حمل كلّ عامل
        بالمفاتيح الحيّة، والمفاتيح المسنَدة. لا قاعدة توجيه صامتة: أيّ أفضلية
        تُضاف لاحقًا يجب أن تظهر هنا بالاسم، وإلّا صارت عمًى جديدًا.
        """
        per_worker: dict[int, list[str]] = {w: [] for w in range(self.worker_count)}
        for key, worker in self._owners.items():
            per_worker.setdefault(worker, []).append(self.owner_label(key))
        return {
            "worker_count": self.worker_count,
            "logical_partitions": self.logical_partitions,
            "worker_count_source": "discovered" if self.worker_count == default_worker_count() else "explicit",
            "keys_per_worker": {str(w): len(keys) for w, keys in sorted(per_worker.items())},
            # التوازن الحقيقيّ بالحِمل لا بالعدد: عاملان بمفتاحٍ واحد لكلٍّ
            # قد يفترقان عشرين ضعفًا. اللوحة تحتاج الرقمين معًا (§٣٠).
            "load_per_worker": {str(w): n for w, n in sorted(self.worker_load().items())},
            "keys": {str(w): sorted(keys) for w, keys in sorted(per_worker.items())},
            # §٧ + §٣٠: الأقسام غير العاملة تُعلَن بحالتها — مثبَّتة لمركز
            # مفتوح، أو في تصريف، أو في تسليم. الغائب من القائمة `ACTIVE`.
            "partition_states": {
                str(partition): state
                for partition, state in sorted(self._partition_state.items())
            },
            "migrating_to": {
                str(partition): worker
                for partition, worker in sorted(self._migration_target.items())
            },
        }

    # ── بروتوكول الانتقال (§٧) ──────────────────────────────────────────
    #
    # «ممنوع نقل حيّ وعشوائيّ» و«ممنوع نقل قسم عند وجود مركز مفتوح».
    # الخطوات الستّ في الورقة تُنفَّذ هنا كآلة حالة صريحة، فلا يتحرّك مالك
    # إلّا عبرها. `reassign` لم تعد بابًا خلفيًّا: ترفض القسم المثبَّت.

    def state_of(self, partition: int) -> str:
        return self._partition_state.get(int(partition), PARTITION_ACTIVE)

    def pin(self, key: OwnershipKey) -> None:
        """تثبيت قسم لأنّ له مركزًا مفتوحًا — لا يُنقل حتى يُفكّ."""
        partition = self.partition_for(key)
        if self.state_of(partition) in (PARTITION_DRAINING, PARTITION_HANDOVER):
            raise MigrationRefused(
                "القسم %d في انتقال جارٍ — أنهِ الانتقال قبل التثبيت" % partition)
        self._partition_state[partition] = PARTITION_PINNED

    def unpin(self, key: OwnershipKey) -> None:
        partition = self.partition_for(key)
        if self.state_of(partition) == PARTITION_PINNED:
            self._partition_state.pop(partition, None)

    def accepts_new_work(self, partition: int) -> bool:
        """أثناء `HANDOVER` تُجمَّد اللقطة، فلا يجوز أن يبتلع المالك القديم
        عملًا جديدًا يضيع من حالة المالك الجديد."""
        return self.state_of(partition) != PARTITION_HANDOVER

    def begin_migration(self, key: Any, target_worker: int) -> int:
        """الخطوة ١–٢: وقف قبول العمل الجديد، وإمهال الجاري ليكتمل.

        و``key`` مفتاحٌ أو ``(مفتاح، مجموعة)`` — §١٤.
        """
        target = int(target_worker)
        if not 0 <= target < self.worker_count:
            raise ValueError("target_worker خارج المدى 0..%d" % (self.worker_count - 1))
        partition = self.partition_of_owner(key)
        state = self.state_of(partition)
        if state == PARTITION_PINNED:
            raise MigrationRefused(
                "القسم %d مثبَّت لمركز مفتوح — §٧ تمنع نقله" % partition)
        if state != PARTITION_ACTIVE:
            raise MigrationRefused("القسم %d في انتقال جارٍ (%s)" % (partition, state))
        self._partition_state[partition] = PARTITION_DRAINING
        self._migration_target[partition] = target
        return partition

    def mark_snapshot_taken(self, partition: int) -> None:
        """الخطوة ٣: تثبيت لقطة الحالة — بعدها لا يُقبل عمل جديد إطلاقًا."""
        partition = int(partition)
        if self.state_of(partition) != PARTITION_DRAINING:
            raise MigrationRefused(
                "لا لقطة تُثبَّت لقسم ليس في تصريف (%s)" % self.state_of(partition))
        self._partition_state[partition] = PARTITION_HANDOVER

    def complete_migration(self, partition: int) -> int:
        """الخطوتان ٥–٦: تسجيل الملكية الجديدة وإعادة تشغيل القسم."""
        partition = int(partition)
        if self.state_of(partition) != PARTITION_HANDOVER:
            raise MigrationRefused(
                "لا يكتمل انتقالٌ لم تُثبَّت لقطته (%s)" % self.state_of(partition))
        target = self._migration_target.pop(partition)
        self._partition_map[partition] = target
        for key, worker in list(self._owners.items()):
            if self.partition_of_owner(key) == partition:
                self._owners[key] = target
        self._partition_state.pop(partition, None)
        return target

    def abort_migration(self, partition: int) -> None:
        """تراجع آمن: المالك لا يتغيّر، والقسم يعود إلى العمل."""
        partition = int(partition)
        if self.state_of(partition) not in (PARTITION_DRAINING, PARTITION_HANDOVER):
            return
        self._migration_target.pop(partition, None)
        self._partition_state.pop(partition, None)

    def reassign(self, key: Any, worker_id: int) -> None:
        """نقل مباشر — يبقى للأدوات والاختبارات، ويحترم التثبيت.

        ⚠️ ليس بديلًا عن البروتوكول: لا يُصرّف طابورًا ولا يثبّت لقطة. يُستعمل
        حيث لا حالة ساخنة تُفقد. والحالة الوحيدة التي يرفضها قطعًا هي القسم
        المثبَّت لمركز مفتوح — تلك حراسة مال لا حراسة بنية.

        ⛔ **العطب المقيس ٢٠٢٦-٠٩-١٦:** كان يكتب `_owners` وحده ويترك
        `_partition_map` كما هو — فينشقّ العقل: **التوجيه** يقرأ `_owners`
        فينتقل، و**الموازنة** تقرأ `_partition_map` فلا ترى شيئًا. فيُبلّغ
        `worker_load()` حِملًا على عاملٍ لم يعد يملكه، وتُبنى النقلة التالية
        على صورةٍ كاذبة.

        وكشفَه اختبارٌ كتبتُه بصدق: جمعتُ ثلاثة أقسام على عاملٍ واحد
        بـ`reassign` فلم يرها `worker_load` مجتمعة. و`complete_migration`
        كان يحدّث الاثنين معًا من البداية — فالانشقاق هنا وحده.
        """
        worker_id = int(worker_id)
        if not 0 <= worker_id < self.worker_count:
            raise ValueError(f"worker_id must be between 0 and {self.worker_count - 1}")
        partition = self.partition_of_owner(key)
        if self.state_of(partition) == PARTITION_PINNED:
            raise MigrationRefused(
                "القسم %d مثبَّت لمركز مفتوح — §٧ تمنع نقله" % partition)
        self._partition_map[partition] = worker_id
        self._assigned_partitions.add(partition)
        # كلّ وحدات هذا القسم تتبعه — والوحدة قد تكون `(مفتاح، مجموعة)`.
        for owner_key in list(self._owners):
            if self.partition_of_owner(owner_key) == partition:
                self._owners[owner_key] = worker_id

    @classmethod
    def partition_of_owner(cls, owner_key: Any) -> int:
        """قسم وحدة الملكية — أيًّا كان شكلها.

        ⛔ **العطب المقيس ٢٠٢٦-٠٩-١٦:** بعد §١٤ صار `_owners` يحمل
        `(مفتاح، مجموعة)` لا المفتاح وحده، وبقيت ثلاثة مواضع تنادي
        `partition_for(k)` على ما تقرؤه منه مباشرةً — فترمي
        `AttributeError: 'tuple' object has no attribute 'text'`.

        وثمنه أنّ **الموازنة ماتت صامتةً**: `_maybe_rebalance` يبتلع كلّ
        استثناء («الموازنة تحسين، لا تُسقط التوجيه») فلم يظهر خطأ قطّ،
        وظلّ `rebalanced = 0` بينما عاملٌ واحد يحمل **10,381** والأخفّ
        **2,781** على النواة الحيّة. حارسٌ يموت بلا صوتٍ أسوأ من غيابه.

        وأُثبت العطب بإعادة إنتاجه: بمجموعةٍ واحدة تنقل الموازنة
        `[(38, 3, 4)]`، وبأربعٍ ترمي الاستثناء عند النقلة نفسها.
        """
        if isinstance(owner_key, tuple):
            key, group = owner_key
            return cls.partition_for(key, int(group))
        return cls.partition_for(owner_key)

    @staticmethod
    def owner_label(owner_key: Any) -> str:
        """اسم الوحدة كما تُعرض — §٣٠ «مَن يملك ماذا».

        ⛔ ومع §١٤ صار للنطاق الواحد أكثر من مالك، فاسمٌ بلا مجموعة **يكذب**:
        يعرض `52992818|XAUUSD` مرّتين بعاملين مختلفين فيُقرأ خللًا في
        التوزيع وهو التقسيم نفسه. المجموعة جزءٌ من الاسم لا زينة.
        """
        if isinstance(owner_key, tuple):
            key, group = owner_key
            return "%s#%d" % (key.text, int(group))
        return owner_key.text

    def snapshot(self) -> dict[str, int]:
        return {self.owner_label(key): worker for key, worker in self._owners.items()}


def _totals(boxes: Any) -> dict[str, Any]:
    """مجموعُ مجموعةٍ من الصناديق — كم صندوقًا وكم يحملون.

    يُستعمل مرّتين: للكلّ (`mailbox_totals`) وللمخفيّ خارج القائمة
    المقصوصة (`*_hidden`). فيُغلق المجموع:

        المعروض  +  المخفيّ  =  الكلّ

    وبدونه تُقرأ القائمة المقصوصة كأنّها الكلّ — وهو ما وقع فعلًا: قُرئ
    ٢٢٠٪ على أنّه كلّ الحِمل وهو ثلثه.
    """
    rows = list(boxes)
    return {
        "mailboxes": len(rows),
        "queued": sum(len(box.queue) for box in rows),
        "delivered": sum(box.delivered for box in rows),
        "dropped": sum(box.dropped for box in rows),
        "busy_s": round(sum(box.busy_s for box in rows), 3),
    }


def _all_drops(workers: Any) -> "Counter[str]":
    """إسقاط كلّ المسارات مجموعًا بالمشترِك."""
    total: Counter[str] = Counter()
    for worker in workers:
        total.update(worker.dropped_by_subscriber)
    return total


def _tail(counter: "Counter[str]", shown: int) -> dict[str, int]:
    """بقيّة العدّاد بعد المعروضين — كم واحدًا، وكم يحملون مجتمعين.

    ⛔ قائمةٌ مقصوصة بلا بقيّتها تُخفي مَن يفقد قليلًا **باستمرار**: عشرون
    حدثًا في الثانية إلى الأبد لا يظهر ما دام ثلاثةٌ فوقه يفقدون الملايين.
    وبالبقيّة يُغلق المجموع، فيُرى حجمُ الذيل ولو لم يُرَ اسمه.
    """
    ordered = counter.most_common()
    rest = ordered[shown:]
    return {"subjects": len(rest), "total": sum(count for _name, count in rest)}


def item_name(item: Any) -> str:
    """اسم الحدث داخل عنصر الطابور — `(kind, event_name, payload, extra)`."""
    try:
        return str(item[1])
    except Exception:  # noqa: BLE001 — عنصرٌ بشكلٍ آخر لا يُسقط العدّاد
        return "؟"


@dataclass(slots=True)
class _HandlerMailbox:
    """صندوق معالِج واحد.

    ⛔ عناصر الطابور **حوامل** (`[item, coalesce_key]`) لا عناصر مباشرة،
    لأنّ الدمج يستبدل المحتوى في مكانه: بالحامل يصير الاستبدال `holder[0] = …`
    بلا معرفة الموضع، فيكفي فهرسٌ من المفتاح إلى الحامل.

    والسبب مقيس: كان الدمج يمسح الطابور خطّيًّا ويبني `_coalesce_key` **لكلّ
    عنصر معلّق** عند كلّ إدراج حدثِ حالة. بسعة صندوق ١٠٢٤ يعني ذلك ألف نداء
    للإدراج الواحد — سلوك تربيعيّ في المسار الأسخن. وقياس py-spy على النواة
    الحيّة ٢٠٢٦-٠٩-١٠ وضع `enqueue` عند **٢٦٪** من المعالج بعد أن أُزيح عنه
    عطب `mkdir`. الفهرس يجعلها `O(1)`.
    """

    queue: deque[list[Any]]
    ready: bool = False
    busy: bool = False
    #: صاحب الصندوق — §٢٤ تسأل «مَن»، والصندوق يملك مشترِكًا واحدًا.
    subscriber: str = ""
    #: عدّادات الصندوق الواحد — §٢٨: «كل عامل يجب أن يظهر… queue · latency».
    #: بدونها يُعرَف أنّ العامل 2 محمَّل ولا يُعرف **بماذا**، فتُعاد الموازنة
    #: على الظنّ. والفرق بين «مشترِك ثقيل واحد» و«توزيع مختلّ» لا يُرى إلّا هنا.
    delivered: int = 0
    dropped: int = 0
    busy_s: float = 0.0
    #: مفتاح الدمج ← الحامل المعلَّق الذي يحمله (لأحداث الحالة وحدها).
    coalesce_index: dict[tuple[Any, ...], list[Any]] = field(default_factory=dict)


class OwnershipWorker:
    """One owned execution lane with fair per-handler mailboxes."""

    def __init__(
        self,
        worker_id: int,
        *,
        is_cold: bool = False,
        max_events: int,
        dispatch: Callable[[int, tuple[Any, ...]], Awaitable[None]],
        is_active: Callable[[int], bool],
        critical_prefixes: Any = (),
    ) -> None:
        self.worker_id = worker_id
        self.max_events = max(1, int(max_events))
        # ⛔ **حكم المالك ٢٠٢٦-٠٩-١٦:** «كل اللي بنيتوه بكبّه بالزبالة إذا
        # قسم يمسّ مال عنده عمًى وخلل مو معروف وين».
        #
        # والعمى كان مقيسًا بالرقم: قوائم الإسقاط مقصوصة عند خمسة لكلّ عامل،
        # فظهر **266 ألف** إسقاطٍ باسمه واختفى **910,604** في ذيلٍ من
        # **224 حدثًا** — ثلاثة أضعاف المعروض ونصف. ومنها أحداثٌ على مسار
        # المال، وبين المُسقِطين `552` مدقّق الأمر نفسه.
        #
        # فحدثُ المال **لا يجوز أن يختفي في ذيل**. هذه القوائم **لا تُقصّ
        # أبدًا**: بحجمها الطبيعيّ (أحداث القرار والتنفيذ والمخاطر) تبقى
        # صغيرة، وثمنُ عرضها كاملةً أرخص من سؤال «أين ضاع الأمر؟».
        #
        # والبادئات من الإعداد لا من الكود (§٤٣): الناقل لا يعرف أنّ
        # `execution.` مالٌ — يعرف أنّ الإعداد أعلن ذلك.
        self.critical_prefixes = tuple(str(p) for p in (critical_prefixes or ()))
        #: إسقاطٌ على مسار المال — بالاسم، وبلا قصّ، مهما صغر.
        self.critical_dropped_by_event: Counter[str] = Counter()
        self.critical_dropped_by_subscriber: Counter[str] = Counter()
        self.critical_coalesced_by_event: Counter[str] = Counter()
        self._dispatch = dispatch
        self._is_active = is_active
        self._mailboxes: dict[int, _HandlerMailbox] = {}
        self._ready: deque[int] = deque()
        self._wakeup = asyncio.Event()
        self._task: asyncio.Task | None = None
        self._stopping = False
        self._busy = 0
        self.processed = 0
        self.dropped = 0
        self.coalesced = 0
        # §٢٤ — «إذا حدث رفض بسبب الضغط، يجب معرفة who/what/when/why».
        # عدّادٌ إجماليّ يقول «سقط ١٬١١٨ في الثانية» ولا يقول **ماذا** سقط،
        # فيُبحث عن العلّة في المكان الخطأ. مقيس ٢٠٢٦-٠٩-١٠: النواة تُسقط
        # 1,118/ث ولا سبيل لمعرفة أيّ حدثٍ يُفقد.
        #: هل هذا مسارٌ بارد؟ يحدّد **تصنيف** فقده لا سلوكه.
        self.is_cold = bool(is_cold)
        self.dropped_by_event: Counter[str] = Counter()
        self.dropped_by_subscriber: Counter[str] = Counter()
        self.coalesced_by_event: Counter[str] = Counter()
        self.failed = 0
        self.last_error = ""
        self.last_activity = 0.0

    def _ensure_task(self) -> None:
        if self._stopping:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        if self._task is None or self._task.done():
            self._task = loop.create_task(self._run(), name=f"quant-owner-{self.worker_id}")

    def enqueue(self, handler_id: int, item: tuple[Any, ...], event_name: str,
                subscriber: str = "") -> None:
        mailbox = self._mailboxes.get(handler_id)
        if mailbox is None:
            mailbox = self._mailboxes[handler_id] = _HandlerMailbox(
                deque(), subscriber=subscriber)

        # سياسة «آخر حالة تكفي» كما هي — لكن بفهرس لا بمسح خطّيّ.
        key = None
        if _is_replayable(event_name):
            key = _coalesce_key(event_name, item[2])
            pending = mailbox.coalesce_index.get(key)
            if pending is not None:
                pending[0] = item          # استبدال في المكان، بلا معرفة الموضع
                self.coalesced += 1
                self.coalesced_by_event[event_name] += 1
                if self._is_critical(event_name):
                    self.critical_coalesced_by_event[event_name] += 1
                self._ready_handler(handler_id, mailbox)
                return

        if not _is_command(event_name):
            while len(mailbox.queue) >= self.max_events:
                evicted = mailbox.queue.popleft()
                if evicted[1] is not None:
                    mailbox.coalesce_index.pop(evicted[1], None)
                self.dropped += 1
                mailbox.dropped += 1
                # ⚠️ **اسم الحدث المُسقط لا الوارد.** الإخلاء يرمي **أقدم**
                # ما في الصندوق، فنسبُ الإسقاط إلى الحدث الداخل يسمّي
                # الجاني ضحيّةً ويرسل التشخيص إلى الطريق المعاكس.
                evicted_name = str(item_name(evicted[0]))
                self.dropped_by_event[evicted_name] += 1
                self.dropped_by_subscriber[mailbox.subscriber or "؟"] += 1
                # مسار المال يُسمّى دائمًا — لا يدخل ذيلًا ولا يُقصّ.
                if self._is_critical(evicted_name):
                    self.critical_dropped_by_event[evicted_name] += 1
                    self.critical_dropped_by_subscriber[
                        mailbox.subscriber or "؟"] += 1
        holder = [item, key]
        mailbox.queue.append(holder)
        if key is not None:
            mailbox.coalesce_index[key] = holder
        self._ready_handler(handler_id, mailbox)
        self._ensure_task()

    def _is_critical(self, event_name: str) -> bool:
        """أحدثُ مسارِ المال — بالإعلان لا بالتخمين.

        القائمة فارغةٌ افتراضًا: بلا إعلانٍ في الإعداد لا يُصنَّف حدثٌ
        حرجًا، فلا تُضاف كلفةٌ ولا يُدَّعى حرصٌ لم يُطلب.
        """
        if not self.critical_prefixes:
            return False
        return event_name.startswith(self.critical_prefixes)

    def _ready_handler(self, handler_id: int, mailbox: _HandlerMailbox) -> None:
        if not mailbox.ready:
            mailbox.ready = True
            self._ready.append(handler_id)
        self._wakeup.set()

    async def _run(self) -> None:
        try:
            while not self._stopping:
                if not self._ready:
                    self._wakeup.clear()
                    await self._wakeup.wait()
                    continue

                handler_id = self._ready.popleft()
                mailbox = self._mailboxes.get(handler_id)
                if mailbox is None:
                    continue
                mailbox.ready = False
                if not mailbox.queue:
                    continue

                holder = mailbox.queue.popleft()
                item = holder[0]
                if holder[1] is not None:
                    # الحامل غادر الطابور، فلا يُدمَج فيه شيء بعد الآن.
                    if mailbox.coalesce_index.get(holder[1]) is holder:
                        mailbox.coalesce_index.pop(holder[1], None)
                if mailbox.queue:
                    self._ready_handler(handler_id, mailbox)
                mailbox.busy = True
                self._busy += 1
                try:
                    # Unsubscribed handlers are retired without executing stale
                    # work. This is the same safety boundary as the old bus.
                    if self._is_active(handler_id):
                        started = time.perf_counter()
                        await self._dispatch(handler_id, item)
                        mailbox.busy_s += time.perf_counter() - started
                        mailbox.delivered += 1
                        self.processed += 1
                except asyncio.CancelledError:
                    raise
                except BaseException as exc:  # noqa: BLE001
                    # A broken dispatch must not kill a whole owner lane.
                    self.failed += 1
                    self.last_error = f"{type(exc).__name__}: {exc}"
                finally:
                    mailbox.busy = False
                    self._busy -= 1
                    self.last_activity = time.perf_counter()
        except asyncio.CancelledError:
            return

    def queue_depth(self) -> int:
        """ما تراكم في صناديق هذا العامل الآن — حالةٌ لا تاريخ.

        هو ما يزن به الموازِنُ منذ ٢٠٢٦-٠٩-١٦: عدّاد الورود كان يقول
        «متوازن» وعاملٌ يحمل ٢٤٬٥٩٣ وجارُه صفر.
        """
        return sum(len(mailbox.queue) for mailbox in self._mailboxes.values())

    async def drain(self, timeout_s: float | None = None) -> bool:
        deadline = time.monotonic() + timeout_s if timeout_s is not None else None
        while True:
            pending = self._busy > 0 or any(
                mailbox.queue for mailbox in self._mailboxes.values()
            )
            if not pending:
                return True
            if deadline is not None and time.monotonic() > deadline:
                return False
            await asyncio.sleep(0.001)

    async def close(self) -> None:
        self._stopping = True
        self._wakeup.set()
        task = self._task
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._task = None
        self._mailboxes.clear()
        self._ready.clear()

    def stats(self) -> dict[str, Any]:
        queued = sum(len(mailbox.queue) for mailbox in self._mailboxes.values())
        busy = sum(1 for mailbox in self._mailboxes.values() if mailbox.busy)
        if queued == 0 and busy == 0:
            state = "NORMAL"
        elif queued < self.max_events:
            state = "DEGRADED"
        else:
            state = "OVERLOAD"
        return {
            "worker_id": self.worker_id,
            "queued": queued,
            "busy_handlers": busy,
            "processed": self.processed,
            "dropped": self.dropped,
            "lane": "cold" if self.is_cold else "hot",
            # §٢٨ — مَن يسكن هذا المسار وبأيّ حمل. أثقل ثمانية بزمن الشغل،
            # فالسؤال «مشترِكٌ واحد يحجب أم توزيعٌ مختلّ» يُجاب بالرقم.
            #
            # ⛔ **`UNRESOLVED-5`، وحكم المالك ٢٠٢٦-٠٩-١٦ حسمه:**
            #
            #     «الاختصار يجوز أن يبقى في واجهة العرض، لكن لا يجوز أن
            #      تختفي البقية دون aggregate واضح:
            #          visible + hidden_count + hidden_load = total»
            #
            # والعمى كان مقيسًا: المرئيّ في هذه القوائم **٢٢٠٪ من ٦٠٠٪**
            # طاقة — أي أنّ **ثلثَي الاستهلاك** خارج ما يُعرض. ولهذا اختلف
            # رقمي عن رقم جلسة التغذية للمشترِكين أنفسهم: كلٌّ منّا يرى
            # صناديقَ غير التي يراها الآخر، وكلانا يظنّ أنّه يرى الكلّ.
            #
            # **ولا يُبنى قرار توزيعٍ ولا نقلُ ملكيّة على قائمةٍ تُخفي
            # ثلثَي الحِمل.** فالقصّ يبقى، والبقيّة تُعلن، والمجموع يُغلق —
            # وهو مبدأ معادلة الإقلاع نفسه.
            "mailbox_totals": _totals(self._mailboxes.values()),
            "subscribers_hidden": _totals(
                sorted(self._mailboxes.values(),
                       key=lambda b: b.busy_s, reverse=True)[8:]),
            "waiting_hidden": _totals(
                [b for b in sorted(self._mailboxes.values(),
                                   key=lambda b: len(b.queue), reverse=True)[8:]
                 if b.queue]),
            "subscribers": [
                {
                    "subscriber": box.subscriber or "؟",
                    "queued": len(box.queue),
                    "delivered": box.delivered,
                    "dropped": box.dropped,
                    "busy_s": round(box.busy_s, 3),
                    "avg_ms": round(box.busy_s * 1000.0 / box.delivered, 3)
                              if box.delivered else 0.0,
                }
                for box in sorted(self._mailboxes.values(),
                                  key=lambda b: b.busy_s, reverse=True)[:8]
            ],
            # ⛔ **عمًى مقيس ٢٠٢٦-٠٩-١٦:** القائمة أعلاه مرتَّبة بـ`busy_s`
            # وحده — فهي تعرض **مَن اشتغل**. وصندوقٌ فيه آلافُ الأحداث ينتظر
            # ولا يعمل (لأنّه مجوَّع على مسارٍ مزدحم) **لا يظهر فيها أبدًا**،
            # وزمنُ انشغاله قريبٌ من الصفر بالضبط لأنّه محجوب.
            #
            # والمقيس على النواة الحيّة:
            #     طابور العامل 4 = 11,133   وأثقل ثمانية فيه طوابيرهم ≤ 82
            # أي أنّ 11,000 حدث تنتظر في صناديقَ **لا يعرضها تشخيصي**. وجاءت
            # جلسة التغذية تسأل «أين تضيع الثماني عشرة ثانية؟» فلم يكن في
            # أداتي ما يجيب.
            #
            # والسؤال «مَن يحجب» غير السؤال «مَن ينتظر»، وهذا يجيب الثاني.
            "waiting": [
                {
                    "subscriber": box.subscriber or "؟",
                    "queued": len(box.queue),
                    "delivered": box.delivered,
                    "dropped": box.dropped,
                    "busy_s": round(box.busy_s, 3),
                }
                for box in sorted(self._mailboxes.values(),
                                  key=lambda b: len(b.queue), reverse=True)[:8]
                if box.queue
            ],
            # هل الطابور في صندوقٍ واحد أم موزَّع؟ نسبةٌ واحدة تُجيب بلا مسح.
            "queue_concentration": round(
                max((len(b.queue) for b in self._mailboxes.values()), default=0)
                / max(queued, 1), 3),
            "busy_s_total": round(sum(b.busy_s for b in self._mailboxes.values()), 3),
            "mailboxes": len(self._mailboxes),
            "coalesced": self.coalesced,
            # أعلى خمسة فقط: القائمة الكاملة تُثقل اللوحة، والذيل لا يُشخّص.
            # ⛔ **قائمةٌ مقصوصة تُخفي مَن يفقد قليلًا باستمرار** — بلاغ جلسة
            # المخازن ٢٠٢٦-٠٩-١٦، وهو حقّ: `most_common(5)` يعرض الصاخب
            # ويُخفي الذيل، فمشترِكٌ يفقد عشرين حدثًا في الثانية إلى الأبد
            # **غير موجود** ما دام ثلاثةٌ عامّون يفقدون الملايين فوقه.
            #
            # والقصّ يبقى (القائمة الكاملة تُثقل اللوحة)، لكنّه **يُعلن
            # بقيّته**: كم مشترِكًا خارج القائمة وكم يفقدون مجتمعين. فالمجموع
            # يُغلق، وأيّ رقمٍ في الذيل يُرى حجمُه ولو لم يُرَ اسمه.
            #
            # وهو مبدأ اليوم نفسه: **معادلةٌ لا عدّاد.** رقمٌ بلا بقيّته لا
            # يُكذَّب ولا يُصدَّق.
            # ⛔ **بلا قصّ، مهما صغر الرقم.** حدثُ المال لا يختفي في ذيل.
            # قوائمُه صغيرةٌ بطبيعتها، وثمنُ عرضها كاملةً أرخص بكثير من
            # سؤال «أين ضاع الأمر؟» بلا جواب.
            "critical_dropped_by_event": dict(self.critical_dropped_by_event),
            "critical_dropped_by_subscriber": dict(self.critical_dropped_by_subscriber),
            "critical_coalesced_by_event": dict(self.critical_coalesced_by_event),
            "critical_prefixes": list(self.critical_prefixes),
            "dropped_by_event": dict(self.dropped_by_event.most_common(5)),
            "dropped_by_event_tail": _tail(self.dropped_by_event, 5),
            "dropped_by_subscriber": dict(self.dropped_by_subscriber.most_common(5)),
            "dropped_by_subscriber_tail": _tail(self.dropped_by_subscriber, 5),
            "coalesced_by_event": dict(self.coalesced_by_event.most_common(5)),
            "coalesced_by_event_tail": _tail(self.coalesced_by_event, 5),
            "failed": self.failed,
            "overload_state": state,
            "last_error": self.last_error,
        }


class OwnershipRuntime:
    """Supervisor for independent owner lanes and the ownership registry."""

    def __init__(
        self,
        *,
        worker_count: int,
        mailbox_max_events: int,
        dispatch: Callable[[int, tuple[Any, ...]], Awaitable[None]],
        is_active: Callable[[int], bool],
        partitioned: bool = True,
        scope_groups: int = 1,
        critical_prefixes: Any = (),
    ) -> None:
        self.worker_count = max(1, int(worker_count))
        self.partitioned = bool(partitioned)
        #: §١٤ — كم مجموعةً يُقسَم إليها كلّ نطاق. الواحد يعني «بلا تقسيم»
        #: وهو الافتراض: لا تتبدّل خريطةٌ واحدة ما لم يُعلَن العدد.
        self.scope_groups = max(1, int(scope_groups))
        self._group_of_subscriber: dict[str, int] = {}
        #: المسار البارد يُحدَّد قبل السجلّ كي يُحجز منه — ترتيبٌ مقصود:
        #: كان السجلّ يُنشأ أوّلًا فيوزّع النطاقات على العمّال كلّهم بما فيهم
        #: البارد، وهو العطب المقيس ٢٠٢٦-٠٩-١٦.
        #: بادئات أحداث المال — من الإعداد، وتُمرَّر إلى كلّ عامل.
        self.critical_prefixes = tuple(str(p) for p in (critical_prefixes or ()))
        self._cold_worker = max(0, self.worker_count - 1)
        self.registry = OwnershipRegistry(
            self.worker_count,
            # عاملٌ واحد لا يُحجَز منه شيء — وإلّا بقي النقل بلا مسار.
            reserved_workers=() if self.worker_count < 2 else (self._cold_worker,))
        # الوصل: السجلّ يملك الخريطة، والعمّال يملكون الصناديق. وبلا هذا
        # السطر يزن الموازِنُ بعدّاد الورود كما كان — وهو العطب المقيس.
        # و`getattr` لا `self._workers` مباشرةً: العمّال يُبنون بعد هذا
        # السطر، والاستدعاء مؤجَّل — لكنّ استدعاءً مبكّرًا كان ليرفع
        # `AttributeError` داخل `rebalance`، فيبتلعه `except` العريض
        # ويُعدّ `rebalance_failures` بلا أن يُعرف السبب. لا عطبَ صامت.
        self.registry.set_backlog_source(
            lambda: {w.worker_id: w.queue_depth()
                     for w in getattr(self, "_workers", ())})
        #: إيقاع الموازنة بالعدّ لا بالزمن — لا ساعة في المسار الساخن.
        self.rebalance_every = 20_000
        self._routed_since_balance = 0
        self.rebalanced = 0
        self.last_rebalance: list[tuple[int, int, int]] = []
        #: سقوط الموازنة يُعدّ ويُسمّى — لا يُبتلَع صامتًا (§٢٨).
        self.rebalance_failures = 0
        self.last_rebalance_error = ""
        self._dispatch = dispatch
        self._is_active = is_active
        self._handler_workers: dict[int, int] = {}
        self._cold_handlers: set[int] = set()

        self._workers = [
            OwnershipWorker(
                worker_id,
                max_events=mailbox_max_events,
                dispatch=dispatch,
                is_active=is_active,
                # §٦ — الفقد يُصنَّف **بالمسار** لا بقائمة أسماء: ما سقط على
                # مسارٍ ساخن فقدُ سوق، وما سقط على المسار البارد فقدُ لوحةٍ
                # أو قياسٍ أو تخزين. عدّادٌ شامل يخفي أيّهما وقع.
                is_cold=(worker_id == self._cold_worker),
                critical_prefixes=self.critical_prefixes,
            )
            for worker_id in range(self.worker_count)
        ]
        self._closed = False

    def register_handler(self, handler_id: int, subscriber: str, *, cold: bool = False) -> int:
        if cold:
            self._cold_handlers.add(handler_id)
            self._handler_workers[handler_id] = self._cold_worker
        elif handler_id not in self._handler_workers:
            raw = str(subscriber or handler_id).encode("utf-8")
            digest = hashlib.blake2b(raw, digest_size=8).digest()
            self._handler_workers[handler_id] = int.from_bytes(digest, "big") % self.worker_count
        return self._handler_workers[handler_id]

    def group_of(self, subscriber: str, handler_id: int) -> int:
        """مجموعة المشترِك داخل النطاق — §١٤.

        ⛔ **الثبات هو الشرط، لا التوزيع.** ترتيب المشترِك الواحد محفوظٌ لأنّ
        صندوقه FIFO؛ ويبقى محفوظًا بعد التقسيم **بشرط** أن يقع المشترِك نفسه
        على المجموعة نفسها في كلّ توجيه. فلو تنقّل بين مجموعتين لسارت أحداثه
        على مسارين ووصلت مقلوبةً. ولهذا بصمةٌ ثابتة من اسم المشترِك، لا دورة
        ولا أقلّ‑حِملًا ولا عشوائيّة.

        والاسم لا الرقم: ``handler_id`` هو ``id()`` كائنٍ في الذاكرة، يتبدّل
        كلّ إقلاع، فيتبدّل معه التوزيع ولا يُقارَن قياسٌ بقياس. والاسم يحتفظ
        بالقسمة نفسها عبر الإقلاعات.
        """
        if self.scope_groups <= 1:
            return 0
        name = str(subscriber or "")
        if not name:
            # مشترِكٌ بلا اسم لا بصمة له تدوم؛ يبقى في المجموعة صفر بدل أن
            # يتنقّل مع كلّ إقلاع. (وقياس ٢٠٢٦-٠٩-١٠: كلّ مشترِكي المسار
            # الساخن مسمَّون، فهذا سياجٌ لا حالة شائعة.)
            return 0
        cached = self._group_of_subscriber.get(name)
        if cached is None:
            digest = hashlib.blake2b(name.encode("utf-8"), digest_size=8).digest()
            cached = int.from_bytes(digest, "big") % self.scope_groups
            self._group_of_subscriber[name] = cached
        return cached

    def route(self, handler_id: int, subscriber: str, payload: Any, *, cold: bool = False) -> int:
        # A cold consumer has an explicit output owner. For a keyed hot event,
        # the Account×Symbol owner wins; this is the target architecture and
        # guarantees all events for one state partition stay on one lane. Events
        # without a scope keep a stable handler owner for legacy/global atoms.
        #
        # §١٤ — ومع التقسيم تصير الوحدة `Account×Symbol×مجموعة`: مشترِكو
        # النطاق الواحد يتوزّعون على مسارات، وكلٌّ منهم يبقى على مساره.
        if cold:
            self.register_handler(handler_id, subscriber, cold=True)
            return self._cold_worker
        key = ownership_key(payload)
        if self.partitioned and key is not None:
            owner = self.registry.owner_for(key, self.group_of(subscriber, handler_id))
            self._maybe_rebalance()
            return owner
        return self.register_handler(handler_id, subscriber, cold=False)

    def _maybe_rebalance(self) -> None:
        """يوازن الحِمل دوريًّا — وإلّا بقيت الموازنة دالّةً لا يناديها أحد.

        ⛔ المقيس ٢٠٢٦-٠٩-١٠: التوزيع المتساوي **عدديًّا** ترك الطوابير
        تتباعد — ثلاثة عمّال عند ١٥–٢٠ ألفًا وثلاثة عند ١–٣٣٣ — لأنّ رمزًا
        نشطًا يساوي عدّة رموز هادئة. والطابور يترجَم عمرًا للتِكّة بعلاقة
        رتيبة بلا استثناء (٢ ⟵ 0.2ث · 20,213 ⟵ 238.9ث)، أي تأخّرًا في
        القرار على مال المالك.

        الإيقاع بالعدّ لا بالزمن: لا ساعة في المسار الساخن. ونقلٌ واحد في
        المرّة بهامشٍ يمنع التذبذب، فالتصحيح تدريجيّ ولا يقفز.
        """
        self._routed_since_balance += 1
        if self._routed_since_balance < self.rebalance_every:
            return
        self._routed_since_balance = 0
        try:
            # النافذة أوّلًا: يُنصَّف الوزن التاريخيّ فيحكم الحِملُ الحاليّ
            # لا سِجلُّ الإقلاع، ثمّ يُوازَن على الصورة الحديثة.
            self.registry.decay_traffic()
            moved = self.registry.rebalance(max_moves=1)
        except Exception as exc:  # noqa: BLE001 — لا تُسقط التوجيه أبدًا
            # ⛔ الابتلاع يبقى — سقوط الموازنة لا يجوز أن يقطع السوق — لكنّه
            # **يُعدّ ويُسمّى**. المقيس ٢٠٢٦-٠٩-١٦: عطبٌ في سطرٍ واحد أمات
            # الموازنة منذ لحظة §١٤، و`except` صامت أخفاه تمامًا: صفر خطأ
            # في السجلّ، و`rebalanced = 0` يُقرأ «لا حاجة للنقل» وهو في
            # الحقيقة «لا أستطيع». حارسٌ يموت بلا صوتٍ أسوأ من غيابه.
            self.rebalance_failures += 1
            self.last_rebalance_error = "%s: %s" % (type(exc).__name__, exc)
            return
        if moved:
            self.rebalanced += len(moved)
            self.last_rebalance = list(moved)

    def enqueue(
        self,
        handler_id: int,
        subscriber: str,
        payload: Any,
        item: tuple[Any, ...],
        event_name: str,
        *,
        cold: bool = False,
    ) -> None:
        if self._closed:
            return
        worker_id = self.route(handler_id, subscriber, payload, cold=cold)
        self._workers[worker_id].enqueue(handler_id, item, event_name, subscriber)

    async def drain(self, timeout_s: float | None = None) -> bool:
        results = await asyncio.gather(*(
            worker.drain(timeout_s=timeout_s) for worker in self._workers
        ))
        return all(results)

    async def close(self) -> None:
        self._closed = True
        await asyncio.gather(*(worker.close() for worker in self._workers))

    def stats(self) -> dict[str, Any]:
        return {
            "worker_count": self.worker_count,
            "partitioned": self.partitioned,
            "cold_worker": self._cold_worker,
            # §١٤ — تقسيمٌ لا يُرى لا يُصدَّق. والخريطة تُعلَن كي يُعرف على
            # أيّ مجموعةٍ وقع كلّ مشترِك، فلا يُقاس أثرُ التقسيم بالظنّ.
            "scope_groups": self.scope_groups,
            "subscriber_groups": dict(sorted(self._group_of_subscriber.items())),
            # `rebalanced = 0` وحده لا يميّز «لا حاجة» من «لا أستطيع».
            "rebalance_failures": self.rebalance_failures,
            "last_rebalance_error": self.last_rebalance_error,
            # §٦ — «لا يوجد عداد شامل يخفي نوع الفقد».
            "market_dropped": sum(w.dropped for w in self._workers if not w.is_cold),
            "cold_dropped": sum(w.dropped for w in self._workers if w.is_cold),
            "market_coalesced": sum(w.coalesced for w in self._workers if not w.is_cold),
            "cold_coalesced": sum(w.coalesced for w in self._workers if w.is_cold),
            # مجموعُ مسار المال عبر المسارات كلّها — بلا قصّ.
            "critical_dropped_by_event": dict(sum(
                (w.critical_dropped_by_event for w in self._workers), Counter())),
            "critical_dropped_by_subscriber": dict(sum(
                (w.critical_dropped_by_subscriber for w in self._workers), Counter())),
            "critical_coalesced_by_event": dict(sum(
                (w.critical_coalesced_by_event for w in self._workers), Counter())),
            "critical_prefixes": list(self.critical_prefixes),
            # الحِمل الكلّيّ عبر المسارات — لا يُجمع من قوائم مقصوصة.
            # (`UNRESOLVED-5`: المرئيّ كان 220% من 600% طاقة.)
            "load_totals": {
                "mailboxes": sum(len(w._mailboxes) for w in self._workers),
                "busy_s": round(sum(b.busy_s for w in self._workers
                                    for b in w._mailboxes.values()), 3),
                "queued": sum(len(b.queue) for w in self._workers
                              for b in w._mailboxes.values()),
                "delivered": sum(b.delivered for w in self._workers
                                 for b in w._mailboxes.values()),
                "dropped": sum(b.dropped for w in self._workers
                               for b in w._mailboxes.values()),
                "capacity_workers": len(self._workers),
            },
            "dropped_by_subscriber": dict(_all_drops(self._workers).most_common(12)),
            # والبقيّة تُعلن — القائمة مقصوصة عند اثني عشر، والذيل يُرى حجمه.
            "dropped_by_subscriber_tail": _tail(_all_drops(self._workers), 12),
            "ownership": self.registry.snapshot(),
            # «مَن يملك ماذا» — §٣٠. يخرج مع بقيّة العدّادات فتراه اللوحة.
            "layout": self.registry.layout(),
            "rebalanced": self.rebalanced,
            "last_rebalance": [
                {"partition": p, "from": src, "to": dst} for p, src, dst in self.last_rebalance
            ],
            "workers": [worker.stats() for worker in self._workers],
        }
