"""
Core.errors
============
شجرة الاستثناءات الموحّدة لكامل Core.

القاعدة: أي خطأ يحدث داخل ذرة أو أثناء التعامل معها يُلتقط ويُحوَّل إلى
أحد هذه الأنواع قبل أن يصل إلى Bootloader أو Health Manager، حتى لا
يُسمح لخطأ في ذرة واحدة بإسقاط العملية بأكملها (سياسة الأخطاء في
Project Spec + Article 30).

⚠️ ٢٠٢٦-٠٩-٢٢ — الرموز ٢٠٠٢ · ٣٠٠٢ · ٣٠٠٣ · ٣٠٠٤ · ٣٠٠٥ · ٣١٠٠ · ٣٤٠٠
**شاغرةٌ عمدًا.** سبعة أصنافٍ حملتها نُقلت إلى الأرشيف بأمر المالك، بعد
قياسٍ فحص كلّ اسمٍ في ``core/`` مقابل ٩٩٧ ملفَّ بايثون متتبَّع فأعطى لها
**صفر رفعٍ وصفر التقاط**:

    Desktop\\أرشيف QUANT_NQ\\كود ميّت — النواة — 2026-09-22\\
        core-errors.py.الأصل    الملفّ كاملًا، مطابقٌ بالبصمة sha256
        اقرأني.md               الجدول والاعتراض المسجَّل وطريق الاستعادة

**ولا يُعاد استعمال رقمٍ شاغر لصنفٍ جديد.** الرمز جزءٌ من العقد الذي
تفرضه المادة 89 (خصائص رقمية ومعيارية للرصد والتوثيق الآلي)، وإعادةُ
استعماله تجعل سطرًا قديمًا في سجلٍّ أو لوحة يُقرأ باسمٍ ليس اسمه.
"""

from __future__ import annotations


class CoreError(Exception):
    """الأصل لكل استثناءات Core. لا يُطلق مباشرة."""
    # ⚠️ تطبيق المادة 89: خصائص رقمية ومعيارية للرصد والتوثيق الآلي
    code: int = 1000
    severity: str = "error"


# ---------------------------------------------------------------- Manifest --

class ManifestError(CoreError):
    code = 2000

class ManifestParseError(ManifestError):
    code = 2001

# 2002 شاغر — نُقل إلى الأرشيف ٢٠٢٦-٠٩-٢٢


# ------------------------------------------------------------ Dependencies --

class DependencyError(CoreError):
    code = 2100

class MissingDependencyError(DependencyError):
    code = 2101

class CircularDependencyError(DependencyError):
    code = 2102

class VersionIncompatibleError(DependencyError):
    code = 2103


# ------------------------------------------------------------------- Atom --

class AtomLifecycleError(CoreError):
    code = 3000

class AtomInitializationError(AtomLifecycleError):
    code = 3001

# 3002 · 3003 · 3004 · 3005 شاغرة — نُقلت إلى الأرشيف ٢٠٢٦-٠٩-٢٢


# ---------------------------------------------------------------- Runtime --

# 3100 شاغر — نُقل إلى الأرشيف ٢٠٢٦-٠٩-٢٢

class RegistryError(CoreError):
    code = 3200

class UnknownAtomError(RegistryError):
    code = 3201

class ConfigError(CoreError):
    code = 3300

# 3400 شاغر — نُقل إلى الأرشيف ٢٠٢٦-٠٩-٢٢
