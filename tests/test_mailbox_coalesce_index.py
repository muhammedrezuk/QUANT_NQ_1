"""دمج الحالة داخل الصندوق يجب أن يكون `O(1)` لا مسحًا خطّيًّا.

⛔ العطب المقيس ٢٠٢٦-٠٩-١٠: كان `enqueue` يمسح الطابور كلّه ويبني
`_coalesce_key` **لكلّ عنصر معلّق** عند كلّ إدراج حدثِ حالة. بسعة صندوق
١٠٢٤ يعني ذلك ألف نداء للإدراج الواحد — سلوك تربيعيّ في المسار الأسخن.

وقياس `py-spy` على النواة الحيّة وضع `enqueue` عند **٢٦٪** من المعالج بعد
أن أُزيح عنه عطب `mkdir` — أي صار الجدار التالي بعينه.

و§١٦ محفوظة: الدمج سياسة لا فقد، وهذا الاختبار يحرس **الكلفة** لا السياسة.
"""

from __future__ import annotations

from collections import deque

import transport.ownership as ownership
from transport.ownership import OwnershipWorker


def _worker(max_events: int = 1024) -> OwnershipWorker:
    return OwnershipWorker(worker_id=0, max_events=max_events,
                           dispatch=None, is_active=lambda _: True)


def _state_item(symbol: str, value: int) -> tuple:
    return ("sub", "analysis.trend.state",
            {"account_id": "A", "symbol": symbol, "value": value}, None)


def test_coalescing_does_not_scan_the_mailbox(monkeypatch) -> None:  # noqa: ANN001
    """صندوقٌ ممتلئ بنطاقات كثيرة: الإدراج لا يمسحه.

    ⚠️ الشرط الحاسم أن يكون **الطابور طويلًا فعلًا**. لو اندمجت كلّ
    الأحداث في نطاق واحد لبقي الطابور عنصرًا واحدًا، فيصير المسح الخطّيّ
    رخيصًا ويمرّ الاختبار على الكود المعطوب — أي اختبار يوثّق أمنية لا واقعًا.
    فهنا ٢٠٠ نطاق معلّق، ثمّ ٢٠٠ إدراج فوقها:

        المسح الخطّيّ  ⟵  حتى 200 نداء لكلّ إدراج  = عشرات الآلاف
        الفهرس        ⟵  نداء واحد لكلّ إدراج     = 200
    """
    scopes = 200
    worker = _worker()
    for index in range(scopes):
        worker.enqueue(7, _state_item("SYM%03d" % index, 0), "analysis.trend.state")
    assert len(worker._mailboxes[7].queue) == scopes, "لم يمتلئ الصندوق فلا معنى للقياس"

    calls = {"n": 0}
    original = ownership._coalesce_key

    def counting(event_name, payload):  # noqa: ANN001, ANN202
        calls["n"] += 1
        return original(event_name, payload)

    monkeypatch.setattr(ownership, "_coalesce_key", counting)
    for index in range(scopes):
        worker.enqueue(7, _state_item("SYM%03d" % index, 1), "analysis.trend.state")

    assert calls["n"] == scopes, (
        "بناء المفتاح %d مرّة في %d إدراج — المسح الخطّيّ عاد" % (calls["n"], scopes)
    )
    mailbox = worker._mailboxes[7]
    assert len(mailbox.queue) == scopes, "الدمج غيّر طول الطابور"
    assert all(holder[0][2]["value"] == 1 for holder in mailbox.queue), "المحفوظ ليس الأحدث"


def test_different_scopes_never_coalesce_into_each_other() -> None:
    """المفتاح مُنطَّق بالحساب والرمز — لا يبتلع رمزٌ حالةَ رمزٍ آخر."""
    worker = _worker()
    for symbol in ("EURUSD", "GBPUSD", "XAUUSD"):
        for value in range(5):
            worker.enqueue(7, _state_item(symbol, value), "analysis.trend.state")

    mailbox = worker._mailboxes[7]
    assert len(mailbox.queue) == 3, "دُمجت نطاقات مختلفة معًا"
    kept = {holder[0][2]["symbol"]: holder[0][2]["value"] for holder in mailbox.queue}
    assert kept == {"EURUSD": 4, "GBPUSD": 4, "XAUUSD": 4}


def test_index_is_cleaned_when_an_item_is_evicted() -> None:
    """الحامل المطرود لا يبقى في الفهرس فيُدمَج فيه بعد خروجه."""
    worker = _worker(max_events=2)
    for symbol in ("A1", "A2", "A3", "A4"):
        worker.enqueue(7, _state_item(symbol, 1), "analysis.trend.state")

    mailbox = worker._mailboxes[7]
    assert len(mailbox.queue) == 2
    assert len(mailbox.coalesce_index) == 2, (
        "الفهرس يحمل %d مدخلًا وطابوره اثنان — تسريب" % len(mailbox.coalesce_index)
    )
    live = {holder[1] for holder in mailbox.queue}
    assert set(mailbox.coalesce_index) == live, "الفهرس يشير إلى حامل غادر"


def test_facts_and_commands_are_never_indexed() -> None:
    """الدمج لأحداث الحالة وحدها — الحقائق والأوامر تُصطفّ كما هي (§١٦)."""
    worker = _worker()
    fact = ("sub", "market.trade", {"account_id": "A", "symbol": "EURUSD"}, None)
    for _ in range(6):
        worker.enqueue(9, fact, "market.trade")

    mailbox = worker._mailboxes[9]
    assert len(mailbox.queue) == 6, "دُمجت حقائق — وهذا فقدٌ لا سياسة"
    assert mailbox.coalesce_index == {}
    assert worker.coalesced == 0


def test_queue_order_survives_the_index() -> None:
    """§١٤ — الترتيب داخل الملكية لا يتغيّر بالفهرسة."""
    worker = _worker()
    for symbol in ("S1", "S2", "S3"):
        worker.enqueue(7, _state_item(symbol, 0), "analysis.trend.state")
    worker.enqueue(7, _state_item("S1", 9), "analysis.trend.state")

    mailbox = worker._mailboxes[7]
    assert [holder[0][2]["symbol"] for holder in mailbox.queue] == ["S1", "S2", "S3"], (
        "الدمج نقل العنصر إلى ذيل الطابور بدل استبداله في مكانه"
    )
    assert mailbox.queue[0][0][2]["value"] == 9
