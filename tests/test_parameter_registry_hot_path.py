"""قراءة العيار لا تلمس نظام الملفّات في المسار الساخن.

⛔ العطب المقيس بـ`py-spy` على النواة الحيّة ٢٠٢٦-٠٩-١٠ (٣٬٧٦٨ عيّنة):

    parameter_registry.py:119   21.7%
    parameter_registry.py:129   13.7%
    ─────────────────────────────────
                                35.4%  من نواة المعالج الوحيدة

`unapproved_parameters()` كانت تُنفّذ `str(ParameterRegistry().path)` في كلّ
نداء، و`__init__` ينفّذ `Path.resolve()` و`settings_db_path()` و
`mkdir(parents=True, exist_ok=True)` — أي `realpath` ٢٠٫٧٪ و`mkdir` ١٣٫٥٪
و`stat` ٣٫٩٪ من المعالج. والنداء يقع لكلّ محلّل × رمز × تِكّة عبر
`approved_value`. والأسوأ: الكلفة تُدفع **قبل** فحص الذاكرة المؤقّتة،
فالذاكرة لم تكن تحمي المسار الساخن من شيء.
"""

from __future__ import annotations

import shared.parameter_registry as registry_module
from shared.parameter_registry import (
    ParameterRegistry,
    _registry_path,
    approved_value,
    unapproved_parameters,
)


def _reset_path_cache() -> None:
    registry_module._registry_cache = None


def test_repeated_reads_do_not_rebuild_the_registry(monkeypatch) -> None:  # noqa: ANN001
    """النداء المتكرّر لا يبني `ParameterRegistry` مرّةً لكلّ قراءة."""
    _reset_path_cache()
    builds = {"n": 0}
    original = ParameterRegistry.__init__

    def counting_init(self, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003
        builds["n"] += 1
        return original(self, *args, **kwargs)

    monkeypatch.setattr(ParameterRegistry, "__init__", counting_init)

    unapproved_parameters()
    after_first = builds["n"]
    for _ in range(60):
        unapproved_parameters()

    extra = builds["n"] - after_first
    assert extra == 0, (
        "بُني السجلّ %d مرّة إضافية في ستّين قراءة — المسار الساخن يلمس القرص" % extra
    )


def test_approved_value_is_filesystem_free_when_repeated(monkeypatch) -> None:  # noqa: ANN001
    """`approved_value` هي نداء كلّ محلّل × رمز × تِكّة — يجب أن تكون رخيصة."""
    _reset_path_cache()
    unapproved_parameters()  # تسخين الذاكرة ومسارها

    builds = {"n": 0}
    original = ParameterRegistry.__init__

    def counting_init(self, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003
        builds["n"] += 1
        return original(self, *args, **kwargs)

    monkeypatch.setattr(ParameterRegistry, "__init__", counting_init)
    for index in range(120):
        approved_value("speed.window", 1.0, scope="52992818|EURUSD%d" % (index % 8))

    assert builds["n"] == 0, (
        "بُني السجلّ %d مرّة في مئة وعشرين قراءة عيار" % builds["n"]
    )


def test_path_is_recomputed_when_the_market_changes(monkeypatch) -> None:  # noqa: ANN001
    """الذاكرة مفتاحها `QUANT_GOV_MARKET` — لا تُقدّم مسار سوق لسوق آخر.

    م-٢٧ في الملفّ نفسه سجّلت أنّ خلط سجلّي سوقين كان يمرّر اعتمادات
    أحدهما للآخر؛ فالتخزين هنا يجب ألّا يعيد إنتاج ذلك الخلط.
    """
    _reset_path_cache()
    monkeypatch.setenv("QUANT_GOV_MARKET", "forex")
    first = _registry_path()
    assert _registry_path() is first or _registry_path() == first

    monkeypatch.setenv("QUANT_GOV_MARKET", "other")
    second = _registry_path()
    assert registry_module._registry_cache[0][0] == "other"
    assert isinstance(second, str) and second


def test_cached_path_matches_a_freshly_built_registry() -> None:
    """التسريع لا يغيّر الوجهة: نفس مسار السجلّ المبنيّ حديثًا."""
    _reset_path_cache()
    assert _registry_path() == str(ParameterRegistry().path)
