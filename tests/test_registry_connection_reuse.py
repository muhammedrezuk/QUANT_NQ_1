"""اتّصال قاعدة العيارات يُعاد استعماله — لا اتّصال جديد لكلّ استعلام.

**⛔ العطب، مقيسًا بـ`py-spy` على النواة الحيّة ٢٠٢٦-٠٩-١٠** (5,093 عيّنة/45ث):
`_connect` كان **ثاني أثقل إطار** — 6.8% من معالج العملية. لأنّ كلّ قراءة
عيارٍ واحدة كانت تفتح اتّصال SQLite جديدًا.

    اتّصال جديد + استعلام : 578.3 µs
    اتّصال مُعاد استعماله  :   9.1 µs      ⟵ **63×**

⚠️ **والـPRAGMA بريئة:** القياس بلا PRAGMA أعطى 594.8 µs — لا فرق. الكلفة
كلّها في `sqlite3.connect` نفسه. فرضيّتي الأولى («الـPRAGMA هي العلّة»)
سقطت بالقياس قبل أن تُكتب سطرًا.

**وما تحرسه هذه الاختبارات هو ثمن السرعة:** مقبضٌ يبقى مفتوحًا. فتبديل
المسار يغلق القديم فورًا (28 ملفّ اختبار يبدّل هذه القاعدة، ومقبضٌ مفتوح
يمنع تنظيف مجلّد مؤقّت على ويندوز)، وكلّ خيط يملك اتّصاله وحده.
"""

from __future__ import annotations

import sqlite3
import threading

import pytest

from shared.parameter_registry import SCOPE_GLOBAL, ParameterRegistry


@pytest.fixture()
def registry(tmp_path):  # noqa: ANN001, ANN201
    made = ParameterRegistry(tmp_path / "settings.db")
    yield made
    ParameterRegistry.close_connections()


# ── إعادة الاستعمال ─────────────────────────────────────────────────────

def test_the_same_thread_reuses_one_connection(registry: ParameterRegistry) -> None:
    first = registry._connect()
    second = registry._connect()
    assert first is second, "فُتح اتّصال جديد لنفس المسار على نفس الخيط"


def test_a_reused_connection_still_reads_correctly(registry: ParameterRegistry) -> None:
    for _ in range(5):
        rows = registry.all()
        assert rows, "القراءة عبر اتّصال مُعاد استعماله رجعت فارغة"
    assert {str(row["name"]) for row in registry.all()} == {
        str(row["name"]) for row in registry.all()}


def test_switching_the_path_closes_the_previous_handle(tmp_path) -> None:  # noqa: ANN001
    """مقبضٌ مفتوح على ملفّ مؤقّت يمنع تنظيفه على ويندوز."""
    first_registry = ParameterRegistry(tmp_path / "one.db")
    first = first_registry._connect()
    second_registry = ParameterRegistry(tmp_path / "two.db")
    second = second_registry._connect()

    assert first is not second, "اتّصالٌ واحد لقاعدتين — يقرأ من الخطأ"
    with pytest.raises(sqlite3.ProgrammingError):
        first.execute("SELECT 1")          # أُغلق فعلًا لا تُرك مفتوحًا
    ParameterRegistry.close_connections()


def test_each_thread_gets_its_own_connection(registry: ParameterRegistry) -> None:
    """كائن sqlite3 يرفض الاستعمال من خيطٍ غير خيط إنشائه.

    والناقل يشغّل معالجات على بِركة خيوط، فاتّصالٌ واحد مشترك كان يرفع
    `ProgrammingError` في المسار الساخن.
    """
    seen: dict[str, object] = {}
    errors: list = []

    def worker(name: str) -> None:
        try:
            seen[name] = registry._connect()
            registry.all()                  # استعمال فعليّ لا مجرّد فتح
        except Exception as exc:  # noqa: BLE001
            errors.append((name, exc))
        finally:
            ParameterRegistry.close_connections()

    threads = [threading.Thread(target=worker, args=("t%d" % index,))
               for index in range(3)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert not errors, errors
    assert len(seen) == 3
    assert len({id(conn) for conn in seen.values()}) == 3, "خيطان تقاسما اتّصالًا"


def test_closing_lets_the_next_call_reopen(registry: ParameterRegistry) -> None:
    first = registry._connect()
    ParameterRegistry.close_connections()
    second = registry._connect()
    assert second is not first
    assert registry.all(), "لم يُعَد الفتح بعد الإغلاق"


def test_closing_twice_is_harmless(registry: ParameterRegistry) -> None:
    registry._connect()
    ParameterRegistry.close_connections()
    ParameterRegistry.close_connections()
    assert registry.all()


# ── الكتابة عبر اتّصال مُعاد استعماله ───────────────────────────────────

def test_a_write_is_visible_on_the_same_reused_connection(registry: ParameterRegistry) -> None:
    """`BEGIN IMMEDIATE` داخل `with` على اتّصالٍ حيّ — لا معاملة معلّقة."""
    name = str(registry.all()[0]["name"])
    registry.write_value(name, value=3.75, scope=SCOPE_GLOBAL,
                         changed_by="اختبار", command_id="cid-1", at=1.0)
    row = registry.get(name, SCOPE_GLOBAL)
    assert row is not None
    assert float(row["value"]) == pytest.approx(3.75)


def test_repeated_writes_do_not_leave_a_transaction_open(registry: ParameterRegistry) -> None:
    """معاملةٌ معلّقة على اتّصالٍ دائم تحجب الكتّاب إلى الأبد."""
    name = str(registry.all()[0]["name"])
    for index in range(4):
        registry.write_value(name, value=float(index), scope=SCOPE_GLOBAL,
                             changed_by="اختبار", command_id="cid-%d" % index,
                             at=float(index))
    assert registry._connect().in_transaction is False, "بقيت معاملة مفتوحة"
    assert float(registry.get(name, SCOPE_GLOBAL)["value"]) == pytest.approx(3.0)


def test_another_thread_sees_a_committed_write(registry: ParameterRegistry) -> None:
    """اتّصالان مختلفان على قاعدة واحدة — الكتابة المعتمَدة تُرى عبرهما."""
    name = str(registry.all()[0]["name"])
    registry.write_value(name, value=9.5, scope=SCOPE_GLOBAL,
                         changed_by="اختبار", command_id="cid-x", at=2.0)
    seen: list = []

    def reader() -> None:
        try:
            row = ParameterRegistry(registry.path).get(name, SCOPE_GLOBAL)
            seen.append(None if row is None else float(row["value"]))
        finally:
            ParameterRegistry.close_connections()

    thread = threading.Thread(target=reader)
    thread.start()
    thread.join(timeout=30)
    assert seen == [pytest.approx(9.5)], seen
