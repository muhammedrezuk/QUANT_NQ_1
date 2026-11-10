"""الإسقاط يُسمّي ما أسقط ومَن — §٢٤ («who / what / when / why»).

**⛔ العطب، مقيسًا على النواة الحيّة ٢٠٢٦-٠٩-١٠:**

    الإسقاط 1,118/ث  ·  والعدّاد يقول «كم» ولا يقول **ماذا**

عدّادٌ إجماليّ يجعل التشخيص تخمينًا: بحثتُ عن العلّة في بيانات السوق،
وتبيّن بالقياس أنّ أكثر ما يُنشر ليس السوق أصلًا (`measurement.*` = 43.3%
من كلّ النشر). بلا نسبة الإسقاط إلى حدثه لا سبيل لمعرفة ما يُفقد.

⚠️ **ودقّة تُكلِّف إن أُخطئت:** الإخلاء يرمي **أقدم** ما في الصندوق لا
الحدث الوارد. نسبُ الإسقاط إلى الوارد يسمّي الجاني ضحيّةً — ويرسل التشخيص
إلى الطريق المعاكس تمامًا.
"""

from __future__ import annotations

import asyncio

import pytest

from transport.ownership import OwnershipWorker, item_name


def _item(event: str, payload: dict | None = None) -> tuple:
    return ("sub", event, payload or {}, ("handler", "subscriber", False))


def _worker(max_events: int = 2) -> OwnershipWorker:
    async def dispatch(_handler_id: int, _item: tuple) -> None:
        return None

    return OwnershipWorker(0, dispatch=dispatch, is_active=lambda _hid: True,
                           max_events=max_events)


def test_item_name_reads_the_event_from_the_queue_element() -> None:
    assert item_name(_item("market_data.cleaned")) == "market_data.cleaned"
    assert item_name(("مشوَّه",)) == "؟"
    assert item_name(None) == "؟"


def test_a_drop_is_attributed_to_the_evicted_event_not_the_incoming_one() -> None:
    """⚠️ الفرق الذي يقلب التشخيص رأسًا على عقب."""
    worker = _worker(max_events=2)
    worker.enqueue(1, _item("قديم.أ"), "قديم.أ", subscriber="s")
    worker.enqueue(1, _item("قديم.ب"), "قديم.ب", subscriber="s")
    worker.enqueue(1, _item("وارد.جديد"), "وارد.جديد", subscriber="s")

    assert worker.dropped == 1
    assert dict(worker.dropped_by_event) == {"قديم.أ": 1}, (
        "نُسب الإسقاط للوارد بدل المُخلَى: %s" % dict(worker.dropped_by_event))
    assert "وارد.جديد" not in worker.dropped_by_event


def test_the_owner_of_the_overflowing_mailbox_is_named() -> None:
    """§٢٤ «who» — أيّ مشترِك امتلأ صندوقه."""
    worker = _worker(max_events=1)
    for index in range(3):
        worker.enqueue(7, _item("حدث.%d" % index), "حدث.%d" % index,
                       subscriber="مخزن_القرارات")
    assert dict(worker.dropped_by_subscriber) == {"مخزن_القرارات": 2}


def test_a_mailbox_without_a_subscriber_is_marked_not_blank() -> None:
    worker = _worker(max_events=1)
    worker.enqueue(1, _item("a"), "a")
    worker.enqueue(1, _item("b"), "b")
    assert dict(worker.dropped_by_subscriber) == {"؟": 1}, (
        "صندوق بلا صاحب يُعلَن، لا يُترك فارغًا")


def test_coalescing_is_counted_separately_from_dropping() -> None:
    """§١٧ — الدمج ليس فقدًا. خلطهما في عدّادٍ واحد يخفي أيّهما وقع."""
    worker = _worker(max_events=8)
    payload = {"account_id": "A", "symbol": "USTEC"}
    for _ in range(4):
        worker.enqueue(2, _item("analysis.trend.state", payload),
                       "analysis.trend.state", subscriber="s")
    assert worker.dropped == 0, "عُدّ دمجٌ إسقاطًا"
    assert worker.coalesced >= 1
    assert worker.coalesced_by_event.get("analysis.trend.state") == worker.coalesced
    assert not worker.dropped_by_event


def test_stats_exposes_the_top_offenders_not_the_whole_tail() -> None:
    """القائمة الكاملة تُثقل اللوحة، والذيل لا يُشخّص."""
    worker = _worker(max_events=1)
    for index in range(12):
        worker.enqueue(1, _item("حدث.%02d" % index), "حدث.%02d" % index,
                       subscriber="s%d" % (index % 3))
    stats = worker.stats()
    assert len(stats["dropped_by_event"]) <= 5
    assert sum(stats["dropped_by_event"].values()) <= stats["dropped"]
    assert set(stats) >= {"dropped_by_event", "dropped_by_subscriber",
                          "coalesced_by_event"}


def test_a_command_is_never_dropped_to_make_room() -> None:
    """الأمر ليس حالة: إسقاطه فقدُ نيّة لا فقدُ تحديث."""
    worker = _worker(max_events=1)
    worker.enqueue(3, _item("x.command"), "x.command", subscriber="s")
    worker.enqueue(3, _item("x.command"), "x.command", subscriber="s")
    assert worker.dropped == 0, "أُسقط أمر لإفساح مكان"


# ── §٢٨ — مَن يسكن كلّ مسار وبأيّ حمل ───────────────────────────────────

def test_each_worker_names_its_residents_with_their_load() -> None:
    """⛔ بلا هذا يُعرَف أنّ العامل محمَّل ولا يُعرف **بماذا**.

    والفرق الذي لا يُرى إلّا هنا: «مشترِكٌ ثقيلٌ واحد يحجب المسار» مقابل
    «عدّة أعمال بتوزيعٍ مختلّ» — وحلّ كلٍّ منهما نقيض الآخر. إعادةُ موازنةٍ
    على الظنّ تنقل الحمل ولا تصلح الحجب.
    """
    worker = _worker(max_events=8)
    worker.enqueue(1, _item("a.state"), "a.state", subscriber="ثقيل")
    worker.enqueue(2, _item("b.state"), "b.state", subscriber="خفيف")

    stats = worker.stats()
    residents = {row["subscriber"]: row for row in stats["subscribers"]}
    assert set(residents) == {"ثقيل", "خفيف"}, residents
    for row in residents.values():
        for field in ("queued", "delivered", "dropped", "busy_s", "avg_ms"):
            assert field in row, field
    assert stats["mailboxes"] == 2
    assert "busy_s_total" in stats


def test_a_mailbox_counts_its_own_drops_not_the_workers() -> None:
    """الإسقاط يُنسب لصندوقه — عدّاد العامل وحده لا يقول مَن امتلأ."""
    worker = _worker(max_events=1)
    for index in range(4):
        worker.enqueue(1, _item("x.%d" % index), "x.%d" % index, subscriber="ممتلئ")
    worker.enqueue(2, _item("y"), "y", subscriber="فارغ")

    rows = {r["subscriber"]: r for r in worker.stats()["subscribers"]}
    assert rows["ممتلئ"]["dropped"] == 3
    assert rows["فارغ"]["dropped"] == 0
    assert worker.dropped == 3


def test_residents_are_ranked_by_work_time_not_by_queue() -> None:
    """الترتيب بزمن الشغل: صندوقٌ قصير الطابور قد يكون أثقل عملًا."""
    worker = _worker(max_events=8)
    worker.enqueue(1, _item("a"), "a", subscriber="بطيء")
    worker.enqueue(2, _item("b"), "b", subscriber="سريع")
    boxes = {b.subscriber: b for b in worker._mailboxes.values()}
    boxes["بطيء"].busy_s, boxes["بطيء"].delivered = 5.0, 10
    boxes["سريع"].busy_s, boxes["سريع"].delivered = 0.1, 1000

    rows = worker.stats()["subscribers"]
    assert rows[0]["subscriber"] == "بطيء"
    assert rows[0]["avg_ms"] == pytest.approx(500.0, abs=1e-3)
    assert rows[1]["avg_ms"] == pytest.approx(0.1, abs=1e-3)


def test_a_mailbox_with_no_delivery_reports_zero_not_a_division_error() -> None:
    worker = _worker()
    worker.enqueue(1, _item("a"), "a", subscriber="جديد")
    assert worker.stats()["subscribers"][0]["avg_ms"] == 0.0


# ══ فجواتٌ كشفها التعطيب المتعمَّد ٢٠٢٦-٠٩-١٦ ═══════════════════════════════

async def test_drain_reports_false_when_it_times_out() -> None:
    """⛔ طفرةٌ نجت: `return False` عند انقضاء المهلة (سطر 661).

    `drain` تُنادى قبل كلّ لقطةٍ وكلّ إغلاق. ولو أعادت `True` عند انقضاء
    المهلة لقالت «فرغ الطابور» وفيه عمل — فتُؤخذ لقطةٌ ناقصة أو يُغلق
    مسارٌ على عملٍ حيّ، **والنتيجة صامتة**. والاختبارات كلّها كانت تُصرّف
    طابورًا فارغًا فتُصيب `True` دائمًا.
    """
    worker = _worker(max_events=8)
    started = asyncio.Event()

    async def blocked(*_args) -> None:  # noqa: ANN002
        started.set()
        await asyncio.sleep(5.0)

    worker._dispatch = blocked
    worker.enqueue(1, _item("a.state"), "a.state", subscriber="بطيء")
    await asyncio.wait_for(started.wait(), timeout=2.0)
    assert await worker.drain(timeout_s=0.05) is False, (
        "قالت `فرغ` ومعالجٌ ما زال يعمل")
    await worker.close()


async def test_drain_reports_true_when_the_lane_is_actually_empty() -> None:
    """والوجه الآخر — وإلّا صارت `drain` تكذب دائمًا بالنفي."""
    worker = _worker(max_events=8)
    assert await worker.drain(timeout_s=0.5) is True
    await worker.close()


def test_the_overload_state_names_an_empty_lane_normal() -> None:
    """⛔ طفرةٌ نجت: `if queued == 0 and busy == 0` (سطر 681).

    الحالة تُقرأ على اللوحة. وطابورٌ فارغ يُسمّى `DEGRADED` يرسل جلسةً
    كاملة تطارد اختناقًا لا وجود له — وقد وقع ذلك في هذا المشروع.
    """
    worker = _worker(max_events=4)
    assert worker.stats()["overload_state"] == "NORMAL", "مسارٌ فارغ ليس سليمًا"
    for index in range(2):
        worker.enqueue(index, _item("x.state"), "x.state", subscriber="س%d" % index)
    assert worker.stats()["overload_state"] != "NORMAL", (
        "طابورٌ فيه عمل ما زال يُسمّى سليمًا")


# ══ ⛔ «مَن ينتظر» سؤالٌ غير «مَن يحجب» — مقيس ٢٠٢٦-٠٩-١٦ ═════════════════
#
# قائمة `subscribers` مرتَّبة بـ`busy_s` وحده، فهي تعرض **مَن اشتغل**.
# وصندوقٌ فيه آلافُ الأحداث ينتظر ولا يعمل لا يظهر فيها أبدًا — وزمن
# انشغاله قريبٌ من الصفر **لأنّه محجوب**، فكلّما زاد جوعُه زاد اختفاؤه.
#
# المقيس على النواة الحيّة: طابور العامل 4 = **11,133** وأثقل ثمانية فيه
# طوابيرهم **≤ 82**. أي أنّ أحد عشر ألف حدثٍ تنتظر في صناديقَ لا يعرضها
# التشخيص. وجاءت جلسة التغذية تسأل «أين تضيع الثماني عشرة ثانية؟» فلم يكن
# في الأداة ما يجيب.

async def test_the_starved_mailbox_is_visible_even_with_zero_busy_time() -> None:
    """⛔ الحارس الذي كان غائبًا: الجائع أخفى نفسه بجوعه."""
    worker = _worker(max_events=64)
    # ⚠️ حدثُ حالةٍ (`.state`) **يُدمَج** فتصير الأربعون واحدة — فيُستعمل
    # حدثُ حدوثٍ كي ينشأ طابورٌ فعلًا. (سقط أوّل اختبارٍ كتبتُه هنا على
    # هذا بالضبط، فعلّمني سلوكًا لم أكن أحسبه.)
    for index in range(40):
        worker.enqueue(1, _item("جوع.tick", {"n": index}), "جوع.tick",
                       subscriber="جائع")
    worker.enqueue(2, _item("عمل.tick", {"n": 0}), "عمل.tick", subscriber="عامل")
    box = worker._mailboxes[2]
    box.busy_s = 9.0          # اشتغل كثيرًا وطابوره واحد
    box.delivered = 3

    stats = worker.stats()
    busy_names = [row["subscriber"] for row in stats["subscribers"]]
    waiting_names = [row["subscriber"] for row in stats["waiting"]]

    assert busy_names[0] == "عامل", "ترتيب الشغل تغيّر"
    assert waiting_names[0] == "جائع", (
        "الصندوق الجائع غائبٌ عن قائمة الانتظار: %s" % waiting_names)
    assert stats["waiting"][0]["queued"] == 40
    assert stats["waiting"][0]["busy_s"] == 0.0, (
        "المفروض أن يظهر رغم أنّ زمن شغله صفر — وذلك بيت القصيد")


async def test_an_empty_mailbox_is_not_listed_as_waiting() -> None:
    """ولا يُحشى بالفارغ: قائمة انتظارٍ فيها من لا ينتظر تُقرأ ازدحامًا."""
    worker = _worker(max_events=8)
    worker.enqueue(1, _item("a.tick", {"n": 0}), "a.tick", subscriber="أ")
    worker._mailboxes[1].queue.clear()
    assert worker.stats()["waiting"] == []


async def test_queue_concentration_separates_one_hog_from_a_spread() -> None:
    """§٢٨ — «مشترِكٌ واحد يحجب أم توزيعٌ مختلّ» تُجاب برقمٍ لا بمسح."""
    hog = _worker(max_events=64)
    for index in range(30):
        hog.enqueue(1, _item("x.tick", {"n": index}), "x.tick", subscriber="وحده")
    hog.enqueue(2, _item("y.tick", {"n": 0}), "y.tick", subscriber="آخر")
    assert hog.stats()["queue_concentration"] > 0.9, hog.stats()["queue_concentration"]

    spread = _worker(max_events=64)
    for index in range(10):
        for step in range(3):
            spread.enqueue(index, _item("z.tick", {"n": step}), "z.tick",
                           subscriber="س%d" % index)
    assert spread.stats()["queue_concentration"] < 0.2, (
        spread.stats()["queue_concentration"])


async def test_concentration_is_zero_on_an_idle_lane() -> None:
    assert _worker(max_events=8).stats()["queue_concentration"] == 0.0


# ══ ⛔ قائمةٌ مقصوصة تُخفي مَن يفقد قليلًا باستمرار — ٢٠٢٦-٠٩-١٦ ═══════════
#
# بلاغ جلسة المخازن: «`dropped_by_subscriber` يعرض اثني عشر فقط... وهذا يخفي
# خبرًا عمّن يفقد قليلًا باستمرار». وهو حقّ: `most_common` يعرض الصاخب
# ويُخفي الذيل. ومشترِكٌ يفقد عشرين حدثًا في الثانية **إلى الأبد** غير موجود
# ما دام ثلاثةٌ عامّون فوقه يفقدون الملايين (4.25 مليون لكلٍّ، مقيسًا).
#
# والقصّ يبقى — القائمة الكاملة تُثقل اللوحة — لكنّ **بقيّته تُعلَن**.
# وهو مبدأ اليوم نفسه: معادلةٌ لا عدّاد.


def test_the_cut_list_declares_what_it_hid() -> None:
    """⛔ الحارس الذي كان غائبًا: المجموع يُغلق فيُرى حجم الذيل."""
    worker = _worker(max_events=2)
    #: صاخبون فوق، وذيلٌ طويل من الصغار تحتهم
    for name, hits in (("ضجيج1", 500), ("ضجيج2", 400), ("ضجيج3", 300),
                       ("ضجيج4", 200), ("ضجيج5", 100)):
        worker.dropped_by_subscriber[name] = hits
    for index in range(30):
        worker.dropped_by_subscriber["صغير%02d" % index] = 20

    stats = worker.stats()
    shown = stats["dropped_by_subscriber"]
    tail = stats["dropped_by_subscriber_tail"]

    assert len(shown) == 5, shown
    assert "صغير00" not in shown, "الذيل ظهر بالاسم — تغيّر القصّ"
    assert tail["subjects"] == 30, tail
    assert tail["total"] == 600, tail
    assert sum(shown.values()) + tail["total"] == 2100, "المجموع لا يُغلق"


def test_a_short_list_declares_an_empty_tail() -> None:
    """ولا يُخترع ذيلٌ حيث لا ذيل — وإلّا قُرئ الصفر خبرًا."""
    worker = _worker(max_events=2)
    worker.dropped_by_subscriber["وحده"] = 7
    tail = worker.stats()["dropped_by_subscriber_tail"]
    assert tail == {"subjects": 0, "total": 0}, tail


def test_the_event_lists_declare_their_tails_too() -> None:
    """الحدث والدمج مثل المشترِك — القصّ نفسه فالبقيّة نفسها."""
    worker = _worker(max_events=2)
    for index in range(9):
        worker.dropped_by_event["حدث%d" % index] = 10 - index
        worker.coalesced_by_event["دمج%d" % index] = 10 - index
    stats = worker.stats()
    for key in ("dropped_by_event_tail", "coalesced_by_event_tail"):
        assert stats[key]["subjects"] == 4, (key, stats[key])
        assert stats[key]["total"] == 5 + 4 + 3 + 2, (key, stats[key])


async def test_the_runtime_wide_list_declares_its_tail() -> None:
    """والمجمَّع عبر المسارات كذلك — وهو ما تقرؤه اللوحة."""
    from transport.ownership import OwnershipRuntime

    async def _dispatch(_handler_id, _item) -> None:
        return None

    runtime = OwnershipRuntime(worker_count=3, mailbox_max_events=8,
                               dispatch=_dispatch, is_active=lambda _h: True)
    for index in range(20):
        runtime._workers[index % 3].dropped_by_subscriber["س%02d" % index] = 100 - index
    stats = runtime.stats()
    assert len(stats["dropped_by_subscriber"]) == 12
    assert stats["dropped_by_subscriber_tail"]["subjects"] == 8
    total = (sum(stats["dropped_by_subscriber"].values())
             + stats["dropped_by_subscriber_tail"]["total"])
    assert total == sum(100 - index for index in range(20)), "المجموع لا يُغلق"
    await runtime.close()


# ══ ⛔ حدثُ المال لا يختفي في ذيل — حكم المالك ٢٠٢٦-٠٩-١٦ ═══════════════════
#
#     «كل اللي بنيتوه بكبّه بالزبالة إذا قسم يمسّ مال عنده عمًى وخلل مو
#      معروف وين.»
#
# والعمى كان مقيسًا بالرقم على النواة الحيّة: قوائم الإسقاط مقصوصة عند خمسة
# لكلّ عامل، فظهر **266 ألف** إسقاطٍ باسمه واختفى **910,604** في ذيلٍ من
# **224 حدثًا** — ثلاثة أضعاف المعروض ونصف. ومنها أحداثٌ على مسار المال،
# وبين المُسقِطين `552` مدقّق الأمر نفسه.
#
# فالقائمة الحرجة **لا تُقصّ أبدًا**. وحجمها الطبيعيّ صغير (أحداث القرار
# والتنفيذ والمخاطر)، وثمنُ عرضها كاملةً أرخص بكثير من سؤال «أين ضاع
# الأمر؟» بلا جواب.


def test_a_money_event_is_named_even_when_it_drops_once() -> None:
    """⛔ الحارس الذي كان غائبًا: مرّةٌ واحدة تكفي لتُسمّى."""
    worker = _worker(max_events=1)
    worker.critical_prefixes = ("decision.",)
    for index in range(3):
        worker.enqueue(1, _item("decision.cycle.record", {"n": index}),
                       "decision.cycle.record", subscriber="707")
    stats = worker.stats()
    assert stats["critical_dropped_by_event"] == {"decision.cycle.record": 2}, stats
    assert stats["critical_dropped_by_subscriber"] == {"707": 2}


def test_the_money_list_is_never_cut() -> None:
    """الذيل هو العطب — فلا ذيل لهذه القائمة مهما طالت."""
    worker = _worker(max_events=1)
    worker.critical_prefixes = ("decision.",)
    for index in range(30):
        name = "decision.n%02d" % index
        for step in range(2):
            worker.enqueue(index, _item(name, {"s": step}), name,
                           subscriber="س%02d" % index)
    named = worker.stats()["critical_dropped_by_event"]
    assert len(named) == 30, "قُصّت قائمة المال: %d" % len(named)
    assert all(count == 1 for count in named.values()), named


def test_a_non_money_event_stays_out_of_the_money_list() -> None:
    """ولا يُحشى بغير المال — وإلّا غرق الحرج في الضجيج من جديد."""
    worker = _worker(max_events=1)
    worker.critical_prefixes = ("decision.",)
    for index in range(3):
        worker.enqueue(1, _item("feed.mt5.tick", {"n": index}), "feed.mt5.tick",
                       subscriber="613")
    stats = worker.stats()
    assert stats["critical_dropped_by_event"] == {}
    assert stats["dropped_by_event"] == {"feed.mt5.tick": 2}, stats["dropped_by_event"]


def test_without_a_declared_prefix_nothing_is_critical() -> None:
    """بلا إعلانٍ في الإعداد لا يُصنَّف حدثٌ حرجًا (§٤٣) — ولا كلفة تُضاف."""
    worker = _worker(max_events=1)
    for index in range(3):
        worker.enqueue(1, _item("decision.cycle.record", {"n": index}),
                       "decision.cycle.record", subscriber="707")
    assert worker.stats()["critical_dropped_by_event"] == {}
    assert worker.stats()["critical_prefixes"] == []


def test_a_merged_money_event_is_named_too() -> None:
    """والدمج ليس إسقاطًا — لكنّه على مسار المال **يُسمّى** أيضًا.

    فحالةٌ تُدمَج تعني أنّ نسخةً لم تصل المشترِك، وقد يكون ذلك مقصودًا —
    لكن لا يُقرَّر ما لم يُرَ.
    """
    worker = _worker(max_events=64)
    worker.critical_prefixes = ("decision.",)
    for _ in range(5):
        worker.enqueue(1, _item("decision.room.state",
                                {"account_id": "A", "symbol": "X"}),
                       "decision.room.state", subscriber="810")
    merged = worker.stats()["critical_coalesced_by_event"]
    assert merged.get("decision.room.state", 0) >= 1, merged


# ══ ⛔ `UNRESOLVED-5` — القائمة المقصوصة كانت تُقرأ كلًّا ═══════════════════
#
# **حكم المالك ٢٠٢٦-٠٩-١٦:** «الاختصار يجوز أن يبقى في واجهة العرض، لكن لا
# يجوز أن تختفي البقية دون aggregate واضح:
#     visible + hidden_count + hidden_load = total»
#
# والعمى كان مقيسًا: المرئيّ في قوائم `subscribers`/`waiting` **٢٢٠٪ من
# ٦٠٠٪** طاقة — أي أنّ **ثلثَي الاستهلاك** خارج ما يُعرض. ولهذا اختلف رقمي
# (22.7%) عن رقم جلسة التغذية (28.4%) للمشترِكين أنفسهم: كلٌّ منّا يرى
# صناديقَ غير التي يراها الآخر، **وكلانا يظنّ أنّه يرى الكلّ**.
#
# ولا يُبنى قرار توزيعٍ ولا نقلُ ملكيّة على قائمةٍ تُخفي ثلثَي الحِمل.


def _fill(worker, name: str, count: int, busy: float) -> None:
    for index in range(count):
        worker.enqueue(hash(name) & 0xFFFF, _item("%s.tick" % name, {"n": index}),
                       "%s.tick" % name, subscriber=name)
    box = worker._mailboxes[hash(name) & 0xFFFF]
    box.busy_s = busy
    box.delivered = count


def test_the_visible_plus_hidden_equals_the_total() -> None:
    """⛔ المعادلة التي فرضها الحكم — تُغلق أو الفحص أحمر."""
    worker = _worker(max_events=64)
    for index in range(20):                       # عشرون صندوقًا، والمعروض ثمانية
        _fill(worker, "س%02d" % index, index + 1, float(20 - index))

    stats = worker.stats()
    shown = stats["subscribers"]
    hidden = stats["subscribers_hidden"]
    total = stats["mailbox_totals"]

    assert len(shown) == 8, len(shown)
    assert hidden["mailboxes"] == 12, hidden
    assert total["mailboxes"] == 20

    for field in ("busy_s", "delivered", "dropped", "queued"):
        seen = sum(row[field] for row in shown)
        assert abs(seen + hidden[field] - total[field]) < 0.01, (
            "%s لا يُغلق: معروض %s + مخفيّ %s ≠ كلّ %s"
            % (field, seen, hidden[field], total[field]))


def test_the_hidden_tail_is_empty_when_everything_is_shown() -> None:
    """ولا يُخترع مخفيٌّ حيث لا مخفيّ — الصفر خبرٌ أيضًا."""
    worker = _worker(max_events=16)
    for index in range(3):
        _fill(worker, "ق%d" % index, 2, 1.0)
    stats = worker.stats()
    assert stats["subscribers_hidden"]["mailboxes"] == 0
    assert stats["subscribers_hidden"]["busy_s"] == 0.0
    assert stats["mailbox_totals"]["mailboxes"] == 3


def test_the_waiting_list_declares_its_hidden_queues_too() -> None:
    """والانتظار مثل الشغل — قائمةٌ مقصوصة بلا بقيّتها تُقرأ كلًّا."""
    worker = _worker(max_events=64)
    for index in range(15):
        _fill(worker, "و%02d" % index, index + 1, 0.0)
    stats = worker.stats()
    shown_q = sum(row["queued"] for row in stats["waiting"])
    assert stats["waiting_hidden"]["mailboxes"] == 7, stats["waiting_hidden"]
    assert shown_q + stats["waiting_hidden"]["queued"] == stats["queued"], (
        "طابور الانتظار لا يُغلق")


async def test_the_runtime_reports_load_without_summing_cut_lists() -> None:
    """الحِمل الكلّيّ يُقرأ من مصدره لا يُجمَع من قوائمَ مقصوصة."""
    from transport.ownership import OwnershipRuntime

    async def _dispatch(_handler_id, _item) -> None:
        return None

    runtime = OwnershipRuntime(worker_count=3, mailbox_max_events=64,
                               dispatch=_dispatch, is_active=lambda _h: True)
    for worker_index, worker in enumerate(runtime._workers):
        for index in range(12):
            _fill(worker, "ع%d_%02d" % (worker_index, index), index + 1, 1.0)

    load = runtime.stats()["load_totals"]
    assert load["mailboxes"] == 36, load
    assert load["capacity_workers"] == 3
    assert load["busy_s"] == pytest.approx(36.0, abs=0.01)
    # والمجموع من الصناديق نفسها لا من القوائم المعروضة
    shown = sum(row["busy_s"] for w in runtime.stats()["workers"]
                for row in w["subscribers"])
    assert shown < load["busy_s"], "القائمة المعروضة تساوي الكلّ — القصّ اختفى"
    await runtime.close()
