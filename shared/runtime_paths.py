"""مالك جذور المسارات — المكان الوحيد الذي يُشتقّ منه جذر التشغيل (بند ٨).

العقد (لا يُنقض في أي ملفّ آخر):
    * جذر البيانات الحيّة = ``<PROJECT_ROOT>/forex_runtime/var`` — سوق واحد
      (حكم المالك 2026-09-07، ومُسح قسم الكريبتو 2026-09-09). كل مورد تشغيليّ
      (market_data · decisions · logs · backups · commands · tilt_rules ·
      analysis_settings) يشتقّ من هنا، لا من ``PROJECT_ROOT/var``.
    * طبقة حالة النواة (journal · snapshots) تُرسى على ``core_state_root()``
      أدناه — وهي ``<runtime>/var`` حين يضبط المُقلِع ``QUANT_CORE_STATE_ROOT``،
      و``PROJECT_ROOT`` **تمامًا كما كانت** قبل هذا القياس حين لا تضبط شيئًا.
    * ``Path.cwd()`` عقد إقلاع مسموح حيث ينصّه المُقلِع صراحة
      (``scripts/run_forex.py`` يعمل chdir إلى الـruntime)؛ لا يُتَّخذ أساسًا
      عامًّا (بند ٧).
    * ⛔ لا رجوع صامت إلى ``PROJECT_ROOT/var``: الجذر القانوني إما موجود، أو
      وصلة/نسخة runtime معلَنة، أو ``QUANT_RUNTIME_ROOT`` مضبوط — وإلّا خطأ
      صريح. قِيس ٢٠٢٦-٠٩-٠٣: ``governance/server.py`` كان يحسب
      ``ROOT.parent/<runtime>`` بلا تحقّق، فقرأ مجلّدًا بلا ``var`` وأعلن
      ``available=false`` على قاعدة موجودة بينما المحرّك يكتب في ملفّ آخر.

اصطلاح واحد لكل المستهلِكين — ``code_root`` هو **جذر الشجرة التي يعمل منها
الكود**: ``PROJECT_ROOT`` من ``<root>/shared``، و``<mirror>`` من
``<mirror>/shared``، و``ROOT.parent`` من ``governance/server.py`` (في الأصل
يُطبَّع إلى ``PROJECT_ROOT``، وفي النسخة إلى ``<mirror>``). التطبيع يتمّ هنا
مرّة واحدة، فلا يتفرّع المنطق بين ملفّين.

متغيّرات البيئة الحاكمة:
    QUANT_RUNTIME_ROOT          جذر الـruntime؛ يضعه المُقلِع، ويُقبل مطلقًا فقط
    QUANT_CORE_STATE_ROOT       مرسى journal/snapshots (يضعه المُقلِع)
    QUANT_ANALYSIS_SETTINGS_DB  مسار سجلّ المعايرة (عقد ParameterRegistry — يُحترم هنا)
"""
from __future__ import annotations

import os
import re
from pathlib import Path

# ٢٠٢٦-٠٩-٠٧ (قرار المالك): الكريبتو مشروع مستقلّ على جهاز آخر، فحُذفت
# شجرته من هنا. بقي `crypto` مقبولًا في `runtime_dir_name` وحدها كي لا
# ينهار إعداد قديم يمرّر السوق باسمه — يُرجِع اسم المجلّد ولا يوجد.
RUNTIME_VARS = ("forex_runtime",)
_TREE_DIRS = ("shared", "core", "atoms", "governance")
ENV_RUNTIME_ROOT = "QUANT_RUNTIME_ROOT"
ENV_CORE_STATE_ROOT = "QUANT_CORE_STATE_ROOT"
ENV_SETTINGS_DB = "QUANT_ANALYSIS_SETTINGS_DB"


def runtime_dir_name(market: str) -> str:
    """اسم مجلّد السوق: `forex`→`forex_runtime`، وما عداه ⟵ `""` (سوق واحد).

    يقبل الاسمَين كليهما (اسمُ السوق واسمُ المجلّد) لأنّ المُقلِعات تمرّر
    `QUANT_CORE_DOMAIN`/`QUANT_GOV_MARKET` باسم السوق لا باسم المجلّد — وهذا
    الاشتقاق كان صامتًا يُرجع الفوركس لكلّ سوقٍ لا يطابق حرفيًّا (قِيس).
    """
    name = str(market or "").strip().lower()
    if name.endswith("_runtime"):
        return name if name in RUNTIME_VARS else ""
    return f"{name}_runtime" if f"{name}_runtime" in RUNTIME_VARS else ""


def _is_link(path: Path) -> bool:
    if path.is_symlink():
        return True
    is_junction = getattr(path, "is_junction", None)          # Python 3.12+
    try:
        return bool(is_junction()) if is_junction is not None else False
    except OSError:
        return False


def _valid_runtime_dir(candidate: Path) -> bool:
    """مجلّد runtime قانوني: يحوي `var/` — أو وصلة/نسخة كما في عهد السوقين.

    ٢٠٢٦-٠٩-٠٧ (قرار المالك): «بلاها مرايا وشي زيادة ما له لزوم». شرطُ وجود
    شجرة `shared` داخل الـruntime كان يخدم عهد السوقين: كل سوق يعمل من مجلّده
    عبر `chdir` فيحتاج نسخة كود بجانبه. وبسوق واحد يعمل الكود من جذر المشروع،
    فالـruntime لم يعد إلّا **جذر بيانات**: `var/` وحده.

    الشرطان القديمان يبقيان مقبولَين كي لا ينهار تركيبٌ قائم على جهاز آخر —
    والجديد يُضاف لا يحلّ محلّهما.
    """
    if not candidate.is_dir():
        return False
    return (_is_link(candidate)
            or (candidate / "shared").exists()
            or (candidate / "var").is_dir())


def project_root_of(code_root: Path | str) -> Path:
    """جذر المشروع العامّ — من داخل نسخة الـruntime هو أبوها."""
    base = Path(code_root).resolve()
    if base.name in RUNTIME_VARS:
        return base.parent
    if base.parent.name in RUNTIME_VARS:
        return base.parent.parent
    return _project_root(base)


def _candidate_roots(base: Path) -> tuple[Path, ...]:
    """جذور محتملة لـ«جذر الشجرة التي يعمل منها الكود».

    ``<X>/shared|core|atoms`` → ``<X>``؛ و``governance`` **لا تُنقص طبقة** لأن
    مُستهلِكها (``server.py``) يمرّر ``ROOT.parent`` جاهزًا — الإنقاص كان يولد
    ``governance/forex_runtime``. نُبقي الأب احتياطًا لمن يمرّر ``ROOT`` نفسها.
    """
    if base.name in ("shared", "core", "atoms"):
        return (base.parent,)
    if base.name == "governance":
        return (base, base.parent)
    return (base,)


def _project_root(base: Path) -> Path:
    """جذر المشروع من قاعدة مُستهلِك — لا يُنقص طبقة عند مجلّد وسطيّ غامض."""
    for root in _candidate_roots(base):
        if root.name in RUNTIME_VARS:
            return root.parent
        if (root / "governance").is_dir() or (root / "config").is_dir() or (root / "atoms").is_dir():
            return root
    return base


def runtime_root(*, code_root: Path | str, market: str = "") -> Path:
    """جذر بيانات الـruntime للسوق — بلا fallback إلى ``PROJECT_ROOT/var`` إطلاقًا.

    الترتيب الحاكم:
      ١) ``QUANT_RUNTIME_ROOT`` — قولبة المُقلِع؛ أوّلوية مطلقة (متى كان مطلقًا
         وموجودًا)، ولا يُعاد اشتقاق أيّ شيء بعده.
      ٢) قاعدة داخل نسخة الـruntime (``<mirror>/governance`` من ``server.py``
         المنسوخ، ``<mirror>/shared`` …) → تلك النسخة: لا نسخة تخدم سوقين.
      ٣) قاعدة عامّة + سوقٌ مسمّى → ``<root>/<market>_runtime`` إن كان مجلّده
         قانونيًّا (وصلة عقد أو نسخة كاملة).
      ٤) قاعدة عامّة بلا سوق → ``forex_runtime`` (افتراضيّ المُقلِعات التاريخيّ).
      ⛔ وإلّا RuntimeError — لا ``<root>/var``.
    """
    base = Path(code_root).resolve()
    name = str(market or "").strip().lower()

    override = str(os.environ.get(ENV_RUNTIME_ROOT) or "").strip()
    if override:
        root = Path(override)
        if not root.is_absolute():
            raise RuntimeError(
                f"{ENV_RUNTIME_ROOT} يجب أن يكون مسارًا مطلقًا — أُعطي: {override}")
        if not root.is_dir():
            raise RuntimeError(
                f"{ENV_RUNTIME_ROOT} يشير إلى مجلّد غير موجود: {root}")
        return root.resolve()

    # ٢) نسخة الـruntime (بما فيها ``<mirror>/governance`` حيث أبُوها = النسخة)
    if base.name in RUNTIME_VARS:
        return base
    if base.parent.name in RUNTIME_VARS:
        return base.parent
    root = base                                  # التطبيع يُطبَّق في ٣/٤ أدناه
    if name and name not in RUNTIME_VARS and runtime_dir_name(name) == "":
        raise RuntimeError(
            f"سوق غير معروف للجذر: {name!r} — المسموح forex|crypto (أو أسماء "
            f"المجلّدين {RUNTIME_VARS}).⛔ لا يُقبل سوقٌ مجهول بإسقاطه على الفوركس.")

    # ٣/٤) من جذر عامّ — لكلّ قاعدة محتملةٍ سوقُها، وأوّل مجلّد قانوني يفوز
    want_dir = runtime_dir_name(name)
    for base_root in _candidate_roots(root):
        for cand in ((want_dir,) if want_dir else ()) + ("forex_runtime",):
            candidate = base_root / cand
            if _valid_runtime_dir(candidate):
                return candidate
    for base_root in _candidate_roots(root):
        candidate = base_root / (want_dir or "forex_runtime")
        if candidate.is_dir():
            raise RuntimeError(
                f"جذر بيانات التشغيل غير مطابق للعقد: {candidate} مجلّد حقيقيّ لا هو وصلة "
                f"ولا يحوي شجرة shared خاصة به — وهو ما يفصل لوحة الحوكمة عن المحرّك. "
                f"شغّل «أزرار التشغيل/تشغيل الفوركس الموحد.bat» (يعمل chdir إلى الـruntime)، "
                f"أو أعِد عقد الوصلات بـ«python scripts/prepare_unified.py "
                f"--convert-identical» بعد نسخة احتياطية، أو اضبط {ENV_RUNTIME_ROOT} صراحةً.")
    raise RuntimeError(
        f"لا جذر بيانات تشغيل عند {root / 'forex_runtime'} — وممنوع الرجوع صامتًا إلى "
        f"{root / 'var'}. اضبط {ENV_RUNTIME_ROOT} أو ثبّت الـmirror بـ"
        f"scripts/prepare_unified.py.")


def runtime_var(*parts: str, code_root: Path | str, market: str = "") -> Path:
    """``<runtime>/var/…`` — الأساس الوحيد لمسارات الموارد التشغيليّة."""
    return runtime_root(code_root=code_root, market=market).joinpath("var", *parts)


PATH_PREFIXES = ("var/", "var" + os.sep)
SUFFIXES = ("_path", "_dir", "_file")
# الجمع: مفتاحٌ واحدٌ يحمل **قائمة** مسارات. القاعدة كانت تلصق المفرد النصّيّ
# وحده، والنصوص العارية داخل القوائم تمرّ بلا لمس لأنّها بلا مفتاحٍ في المدى.
# فكانت ٨٠٠ تنسخ `var/store` نسبةً إلى مجلد العمل: شجرةٌ شبحيّة بخمسين صدفةً
# فارغة (١٫٠ م.ب) بدل المخزن الحيّ (٤٩ ملفًّا، ١٥٫١ جيجابايت). مقيس ٢٠٢٦-٠٩-١٩.
SUFFIXES_PLURAL = ("_paths", "_dirs", "_files")
KEYS: tuple[str, ...] = ()


def manifest_config_rebase(config: dict, *, code_root: Path | str, market: str = "",
                           keys: tuple[str, ...] | None = None) -> dict:
    """يعيد config نفسه مع إلصاق مسارات الحالة النسبية بجذر الـruntime — **عائديًّا**.

    قاعدة الإلصاق واحدة بلا استثناء: قيمة نصّية لمفتاح اسمُه ينتهي بـ``_path``
    أو ``_dir`` أو ``_file``، أو كان ``dir`` مجرّدًا (أو في ``keys``)،
    ويبدأ بـ``var/`` أو ``var\\`` — تُقرأ
    نسبةً إلى ``runtime_root()``، أي إلى الجذر الذي يملكه هذا الملفّ نفسه.
    المسار المطلق والقيم الأُخرى تمرّ كما هي. الغاية: لا تُحَلّ حالةٌ حيّة
    نسبةً إلى مجلد تشغيل عمّاه المُقلِع — ذرّات ٧٠١-٧٠٩ و٥٦٣ و٥٨٠ و٨٧٠
    كانت تجمع قيمها النسبية إلى مجلد العمل (أو تمرّرها خامًا إلى sqlite)،
    فتُنشئ ``<root>/var/store/…`` موازيًا لنسخة الـruntime التي تقرأها
    اللوحة والمحركات — ملفّان لا يلتقيان أبدًا.

    العائدية ليست ترفًا: ٧١٦/٧١٧ (ونسخائهما الكريبتو ٢٧١٦/٢٧١٧) تحمل مساراتها
    داخل **قوائم** من القواميس (``stores: [{db_path: …}]``)، فكانت الطبقةُ الواحدة
    تراها ولا تلمسها؛ والقياس على ويندوز أنبت أربع قواعد تحت جذر المستودع.
    """
    if not isinstance(config, dict):
        return config
    root = runtime_root(code_root=code_root, market=market)
    effective = tuple(keys) if keys else KEYS
    changed = False

    def rebase_text(text: str) -> str | None:
        # Both separators are matched explicitly: manifests carry Windows
        # spellings (`var\store\trades.db`) even on POSIX.
        norm = text.strip().replace("\\", os.sep)
        if os.sep != "\\" and norm.startswith("var\\"):
            norm = "var/" + norm[4:].lstrip("\\")
        for prefix in PATH_PREFIXES:
            if norm.startswith(prefix):
                return str(root / norm)
        return None

    def walk(node):
        nonlocal changed
        if isinstance(node, dict):
            out = {}
            for key, value in node.items():
                named = isinstance(key, str) and (
                    key in effective if keys else key == "dir" or key.endswith(SUFFIXES))
                if named and isinstance(value, str):
                    fixed = rebase_text(value)
                    if fixed is not None:
                        out[key] = fixed
                        changed = True
                        continue
                plural = isinstance(key, str) and not keys and (
                    key == "dirs" or key.endswith(SUFFIXES_PLURAL))
                if plural and isinstance(value, list):
                    items = [rebase_text(x) or x if isinstance(x, str) else x
                             for x in value]
                    if items != value:
                        out[key] = items
                        changed = True
                        continue
                new_value = walk(value) if isinstance(value, (dict, list, tuple)) else value
                if new_value is not value:
                    out[key] = new_value
                    changed = True
                else:
                    out[key] = value
            return out
        if isinstance(node, list):
            items = []
            for item in node:
                new_item = walk(item) if isinstance(item, (dict, list, tuple)) else item
                if new_item is not item:
                    changed = True
                items.append(new_item)
            return items
        return node

    out = walk(config)
    return out if changed else config


def settings_db_path(*, code_root: Path | str, market: str = "") -> Path:
    """مسار سجلّ المعايرة المحكوم — عقد ``ParameterRegistry`` نفسه (بند ٤).

    ``QUANT_ANALYSIS_SETTINGS_DB`` أولًا (مطلقًا كما هو، نسبيًا على جذر المشروع —
    وذاك فعل ``shared/parameter_registry.py``)، ثم الافتراضيّ تحت
    ``<runtime>/var/store``. لا فرع ثالث ولا اشتقاق يدويّ في أي ملفّ آخر.
    """
    configured = str(os.environ.get(ENV_SETTINGS_DB) or "").strip()
    if configured:
        path = Path(configured)
        if path.is_absolute():
            return path
        return project_root_of(code_root) / path
    return runtime_var("store", "analysis_settings.db", code_root=code_root,
                       market=market)


def core_state_root(*, code_root: Path | str, market: str = "") -> Path:
    """مرسى journal/snapshots — ``PROJECT_ROOT`` حرفيًا عند غياب البيئة.

    ``governance/scripts/run_core.py`` كان يرسو على ``PROJECT_ROOT`` دائمًا، فحين
    يعمل المُقلِع ``chdir`` إلى الـruntime تنفصل حالة النواة عن كلّ مورد آخر.
    الآن: ``QUANT_CORE_STATE_ROOT`` أوّلاً، ثم ``<runtime>/var`` حين يكون جذر
    الـruntime مُعلَنًا (بواسطة المُقلِع)، وإلا ``PROJECT_ROOT`` كما كان.
    """
    override = str(os.environ.get(ENV_CORE_STATE_ROOT) or "").strip()
    if override:
        root = Path(override)
        if not root.is_absolute():
            raise RuntimeError(f"{ENV_CORE_STATE_ROOT} يجب أن يكون مطلقًا — أُعطي: {override}")
        return root
    base = Path(code_root).resolve()
    if str(os.environ.get(ENV_RUNTIME_ROOT) or "").strip() or \
            base.name in RUNTIME_VARS or base.parent.name in RUNTIME_VARS:
        return runtime_root(code_root=code_root, market=market) / "var"
    # بلا قولبة من المُقْلِع ولا سياق نسخة: لا يُسمَح بإسقاط حالة النواة على جذر
    # المشروع — runtime_root() يقرّر النسخة الشرعية ويرفع صراحةً إن لم تكن.
    return runtime_root(code_root=code_root, market=market) / "var"



def anchored_state_path(raw: "Path | str", *, code_root: "Path | str") -> "Path":
    """يُرجع المسار النسبي ``raw`` على مرسى الـruntime — بغير رجوعٍ صامت إلى جذر المشروع.

    الذرّة تملك سطرًا واحدًا لا نسخةً من منطق المسارات: الاشتقاق كله يمرّ عبر
    ``runtime_var`` (المالك الوحيد لـ``<runtime>/var``)، والمسار المطلق — قرصٌ
    أو UNC — يمرّ حرفيًّا لأنّ إعادة صياغته قرار نشر لا تصحيح مسار. وتعذُّر
    الاشتقاق **يرفع**: لا بقعة رجوع تُنبت شجرة حالة تحت المستودع.
    """
    value = str(raw).strip()
    # Windows spellings pass verbatim BEFORE separator normalisation:
    # a drive-absolute path or a UNC share is an owner decision, not a stray.
    if re.match(r"^(?:[A-Za-z]:[/\\]|\\\\)", value):
        return Path(value)
    value = value.replace("\\", os.sep)
    base = Path(code_root)
    if base.is_file():
        base = base.parent
    for cand in (base, *base.parents):
        if (cand / "shared" / "runtime_paths.py").is_file():
            base = cand
            break
    for prefix in PATH_PREFIXES:
        if value == prefix.rstrip(os.sep if hasattr(os, "sep") else "/"):
            return runtime_var(code_root=base)
        if value.startswith(prefix):
            return runtime_var(*[x for x in value[len(prefix):].split(os.sep) if x], code_root=base)
    return runtime_var(*[x for x in value.split(os.sep) if x], code_root=base)


def settings_db_relpath() -> Path:
    """المسار النسبيّ الافتراضيّ داخل الـruntime — للفحوص والمقارنة."""
    return Path("var") / "store" / "analysis_settings.db"
