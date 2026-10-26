# -*- coding: utf-8 -*-
"""حارس ق13 — الفرق بين حلقةٍ بلا رقيب ومهمّةٍ مملوكة.

القاعدة وُجدت لعاصفة ٢٠٢٦-٠٨-١١: «محرّكات لا يراقبها أحد **بين** النبضات»
أنتجت 164 ألف أمر. وهي قاعدةٌ صحيحة ولا تُضعَّف.

وفي ٢٠٢٦-٠٩-١٨ وجد القياس نمطًا معاكسًا: معالجٌ ينتظر عملًا حاجزًا **داخل**
النبضة فيحجز الدورة على كلّ مشترِك — 49.99 + 20.38 + 9.00 مِلّي ثانية في
615 و601 و580. فصار الإعفاء للمهمّة المملوكة وحدها، بشروطٍ ثلاثة مجتمعة.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = ROOT / "governance" / "scripts" / "validate_atoms.py"


def _owned(source: str) -> bool:
    """يُعيد حكم ق13 كما هو مكتوبٌ في المدقّق — لا نسخةً موازية."""
    text = VALIDATOR.read_text(encoding="utf-8")
    start = text.index("        held = re.search(")
    end = text.index("        if not owned:")
    import textwrap
    snippet = textwrap.dedent(text[start:end])
    namespace: dict = {"re": re, "source": source}
    exec(compile(snippet, "<rule13>", "exec"), namespace)
    return bool(namespace["owned"])


UNWATCHED = '''
class Atom:
    async def start(self):
        asyncio.create_task(self._loop())
'''

HALF_OWNED = '''
class Atom:
    def spawn(self, coro):
        task = asyncio.get_running_loop().create_task(coro)
        self._pulse_tasks.add(task)
'''

FULLY_OWNED = '''
class Atom:
    def spawn(self, coro):
        task = asyncio.get_running_loop().create_task(coro)
        self._pulse_tasks.add(task)
        task.add_done_callback(self._done)

    async def stop(self):
        for _task in list(self._pulse_tasks):
            _task.cancel()
        self._pulse_tasks.clear()
'''


def test_an_unwatched_task_is_still_refused() -> None:
    """السابقة التي وُجدت القاعدة لأجلها — لا تمرّ."""
    assert _owned(UNWATCHED) is False


def test_ownership_without_watching_or_cancelling_is_refused() -> None:
    """الحاوية وحدها لا تكفي: خطؤها يُبتلع وتعيش بعد الذرّة."""
    assert _owned(HALF_OWNED) is False


def test_the_full_triad_is_accepted() -> None:
    assert _owned(FULLY_OWNED) is True


@pytest.mark.parametrize("prefix", ["615", "601", "580"])
def test_the_three_fixed_atoms_satisfy_the_triad(prefix: str) -> None:
    """الذرّات الثلاث التي أُصلحت اليوم — بالمصدر لا بالادّعاء."""
    directory = next((p for p in (ROOT / "atoms").glob("*/%s_*" % prefix) if p.is_dir()), None)
    # ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): 615 جسر مصدر الأخبار أُرشفت بختم المالك (`d77a5c0`،
    # ٢٠٢٦-٠٩-١٩ «أرشفة ٦١٥») — غيابها مشروع (سابقة 25b0cbb)، والذرّتان الباقيتان تُفحصان كما هما.
    if directory is None and prefix == "615":
        pytest.skip("615 أُرشفت في d77a5c0 (٢٠٢٦-٠٩-١٩)")
    assert _owned((directory / "atom.py").read_text(encoding="utf-8")) is True


def test_the_three_fixed_atoms_no_longer_warn_on_the_live_tree() -> None:
    """على الشجرة الحقيقيّة: 615 و601 و580 خرجت من ق13، وبقي فيها من يستحقّ.

    ⚠️ لا يُفحص هنا رمز خروج المدقّق: الشجرة تحمل ثلاثة عشر خطأً سابقًا
    لعملي (نسخٌ مزدوجة وأحجام وأرقام سحريّة، موجودة عند 86e26e1) — وخلطُها
    بهذا الحارس يجعله يكذب في الاتّجاهين.
    """
    import subprocess, sys, json
    result = subprocess.run([sys.executable, "governance/scripts/validate_atoms.py", "--json"],
                            cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8")
    findings = json.loads(result.stdout)["findings"]
    background = {f["atom_id"] for f in findings if "حلقة خلفية" in f.get("check", "")}
    for atom_id in (615, 601, 580):
        assert atom_id not in background, atom_id
    # ولم تُفتح البوّابة للجميع: من له حلقةٌ بلا الثلاثيّة يبقى محذَّرًا
    assert background, "ق13 صمتت عن الجميع — إعفاءٌ لا تمييز"
