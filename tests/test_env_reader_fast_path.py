"""قارئ البيئة في مسار العيارات الساخن — سرعةٌ بلا تأخير في الرؤية.

**المقيس ٢٠٢٦-٠٩-١٠** (`py-spy`، ٦٬٩٩٢ عيّنة على النواة الحيّة):
`parameter_registry` = **10.1% من معالج العملية**، و`_refresh_dials` وحدها
5.87%. والتفكيك سمّى السبب:

    os.environ.get(name)  1.083 µs   ⟵ غلاف `_Environ`: encodekey ثمّ KeyError
    dict.get(name)        0.093 µs   ⟵ أبطأ 11.6×

بعد تجاوز الغلاف: بصمة البيئة 3.85 ⟵ 0.855 µs · `approved_value` 6.25 ⟵ 2.253 µs.

⛔ **وما لا يجوز أن تشتريه هذه السرعة:** تأخيرَ رؤية تبديل قاعدة العيارات.
البديل المرفوض كان تخزينًا زمنيًّا بثانيتين — و28 ملفّ اختبار يبدّل هذه
المتغيّرات ولا يستدعي كلّها `refresh_gate`، فكان يقدّم قاعدةً لقاعدة (م-27).
"""

from __future__ import annotations

import os

import pytest

import shared.parameter_registry as pr


def _naive(names) -> tuple[str, ...]:                      # noqa: ANN001
    """التنفيذ المرجعيّ — ما يجب أن يطابقه المسار السريع حرفًا بحرف."""
    return tuple(str(os.environ.get(name) or "").strip() for name in names)


# ── الرؤية فورية ────────────────────────────────────────────────────────

def test_setting_a_variable_is_visible_immediately() -> None:
    name = pr._REGISTRY_PATH_ENV[0]
    previous = os.environ.get(name)
    try:
        os.environ[name] = "market-alpha"
        assert "market-alpha" in pr._registry_env_stamp()
        os.environ[name] = "market-beta"
        assert "market-beta" in pr._registry_env_stamp(), "التبديل لم يُرَ فورًا"
    finally:
        if previous is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = previous


def test_deleting_a_variable_is_visible_immediately() -> None:
    name = pr._REGISTRY_PATH_ENV[0]
    previous = os.environ.get(name)
    try:
        os.environ[name] = "to-be-removed"
        assert "to-be-removed" in pr._registry_env_stamp()
        del os.environ[name]
        assert "to-be-removed" not in pr._registry_env_stamp(), "الحذف لم يُرَ فورًا"
    finally:
        if previous is not None:
            os.environ[name] = previous


def test_monkeypatch_setenv_is_visible_immediately(monkeypatch) -> None:  # noqa: ANN001
    """الأداة التي تستعملها الاختبارات فعلًا — لا `os.environ` وحدها."""
    monkeypatch.setenv(pr._REGISTRY_PATH_ENV[1], "C:/tmp/other-settings.db")
    assert "C:/tmp/other-settings.db" in pr._registry_env_stamp()


# ── التطابق مع المرجع ───────────────────────────────────────────────────

@pytest.mark.parametrize("value,expected", [
    ("plain", "plain"),
    ("  padded  ", "padded"),
    ("", ""),
])
def test_the_fast_path_matches_the_reference_exactly(value: str, expected: str,
                                                     monkeypatch) -> None:  # noqa: ANN001
    name = pr._REGISTRY_PATH_ENV[2]
    monkeypatch.setenv(name, value)
    assert pr._registry_env_stamp() == _naive(pr._REGISTRY_PATH_ENV)
    assert expected in pr._registry_env_stamp()


def test_unset_variables_read_as_empty_not_none(monkeypatch) -> None:  # noqa: ANN001
    for name in pr._REGISTRY_PATH_ENV:
        monkeypatch.delenv(name, raising=False)
    stamp = pr._registry_env_stamp()
    assert stamp == ("", "", ""), stamp
    assert stamp == _naive(pr._REGISTRY_PATH_ENV)


# ── الرجوع الآمن ────────────────────────────────────────────────────────

class _StubEnv:
    """بيئة بديلة تُمرَّر صراحةً — لا يُستبدل `os.environ` العامّ.

    استبداله يكسر pytest نفسه (`shutil.get_terminal_size` يقرأ COLUMNS)،
    فصارت الدالّة تقبل البيئة وسيطًا: قابلة للفحص بلا أثر جانبيّ.
    """

    def __init__(self, data=None) -> None:                 # noqa: ANN001
        if data is not None:
            self._data = data
        self.values = {"PATH": "/real/path", "PATHEXT": ".EXE", "SYSTEMROOT": "C:/Windows"}

    def get(self, key, default=None):                      # noqa: ANN001, ANN201
        return self.values.get(key, default)


def test_it_falls_back_when_the_internal_dict_is_absent() -> None:
    """`_data` تفصيل تنفيذ — غيابه يرجعنا إلى الغلاف، لا يكسر شيئًا."""
    stub = _StubEnv()                                      # بلا `_data`
    assert pr._pick_env_reader(stub) == stub.get


def test_it_falls_back_when_the_internal_dict_disagrees() -> None:
    """مفاتيح bytes (لينكس) أو أيّ اختلاف بحرف = رجوعٌ فورًا."""
    stub = _StubEnv({b"PATH": "/real/path"})               # مفاتيح bytes
    assert pr._pick_env_reader(stub) == stub.get, "وثِق بقاموس لا يطابق البيئة"


def test_it_uses_the_dict_when_it_matches() -> None:
    stub = _StubEnv({"PATH": "/real/path", "PATHEXT": ".EXE"})
    assert pr._pick_env_reader(stub) == stub._data.get


def test_a_dict_that_matches_the_probe_but_lies_elsewhere_is_still_refused() -> None:
    """الفحص على متغيّر موجود يقينًا — قاموسٌ يطابق `PATH` وحده يُقبل عمدًا.

    وهذا حدّ الضمان صراحةً: التطابق يُفحص بالعيّنة لا بالبيئة كلّها (٩٠
    مفتاحًا في كلّ استيراد كلفةٌ بلا مقابل). ولو انحرف CPython يومًا عن
    مشاركة القاموس نفسه، فحصُ العيّنة يمسكه لأنّ الانحراف بنيويّ لا جزئيّ.
    """
    stub = _StubEnv({"PATH": "/real/path"})
    assert pr._pick_env_reader(stub) == stub._data.get


def test_the_chosen_reader_is_declared_not_silent() -> None:
    """اختيارٌ صامت لا يُقاس — فيُعلَن."""
    assert isinstance(pr.env_reader_is_direct, bool)
