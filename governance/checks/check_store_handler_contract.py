# -*- coding: utf-8 -*-
"""حارس عقد مخازن ٧٠٠-٧٥٠: لا عملَ طويلًا في معالج، ولا اتّصالًا لكلّ كتابة.

وُلد من تدقيق ٢٠٢٦-٠٩-١٦، حين ظهر العطبان في **ثماني ذرّات** من سبع عشرة —
لا في واحدة. وكلاهما لا يُرى من قراءة ملفٍّ واحد، ولا يُسقط اختبارًا، ولا
يُظهر شيئًا في الصحّة. يُريان بالقياس وحده:

  ١. **عملٌ طويل في معالج حدث.** تسليم الناقل يمضي بالتتابع على مسار العامل،
     وميزانية المعالج **٠٫٠٥ ث**. فمشترِكٌ ينتظر `to_thread` يحجب كلّ ما خلفه.
     المقيس من عدّاد الناقل يومها: ٧١٤ **٣٠٫٠١ ث** · ٧١٦ **٣٠٫٠١** ·
     ٧١٧ **٣٠٫٠٣** · ٧١٥ **٣٠٫٠٢** · ٧١٢ **٧٫٠٤** · ٧٠٧ **٢٢٫٨٧**.
     والعلاج واحد: مهمّة خلفيّة بحارس «واحدة في آنٍ».

  ٢. **اتّصال sqlite جديد لكلّ كتابة.** الكلفة ليست الاستعلام بل دورة نظام
     الملفات: إنشاء `-wal` و`-shm` ثمّ نقطة تفتيش ومحوهما عند كلّ إغلاق.
     مقيس في ٧٠٧: **٣٣٫٥٣ م.ث مقابل ٤٫٤٩** بمعمَّر؛ وقاسه قسم التغذية في
     ٦٠١: **٧٫٥٥ مقابل ٠٫٠٤**.

يُشغَّل بلا وسائط. يخرج بـ1 إن عاد أحدهما.
"""
from __future__ import annotations

import io
import os
import re
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "atoms", "قسم 700-749")

# العمل الطويل: كتابةٌ أو تشذيبٌ أو ضغطٌ أو أرشفةٌ أو إنفاذُ سقف. أمّا
# `_ensure_store` فمسار تعافٍ نادر (مرّة كلّ ثلاثين ثانية بأسوأ حال) فلا يُعدّ.
_LONG_IN_HANDLER = re.compile(
    r"await\s+(?:asyncio\.to_thread\(\s*self\._(?:flush|run|prune|compress|archive|"
    r"insert_many|write_pending|clean)\b"
    r"|self\._(?:flush_and_report|archive|enforce_limits|run_daily|compress_and_report|"
    r"check_and_report|clean_and_report|write_and_report)\b)")

_HANDLER = re.compile(
    r"    async def (_on_[a-z_]+)\(self[^)]*\)[^\n]*\n((?:.*\n)*?)(?=\n    (?:async )?def |\Z)")


def audit() -> list[tuple[str, str, str]]:
    problems: list[tuple[str, str, str]] = []
    for name in sorted(os.listdir(ROOT)):
        path = os.path.join(ROOT, name, "atom.py")
        if not os.path.isfile(path):
            continue
        text = io.open(path, encoding="utf-8").read()

        for match in _HANDLER.finditer(text):
            if _LONG_IN_HANDLER.search(match.group(2)):
                problems.append((name, "عملٌ طويل في معالج", match.group(1)))

        # التوقيع الحقيقيّ للعطب ليس غياب دالّةٍ بالاسم — بل **فتحُ اتّصالٍ
        # في مسار عمل**. تُقاس بما يُنفَّذ لا بما يُسمّى: أيّ `self._connect()`
        # خارج `_connection` نفسها هو اتّصالٌ يُفتح ويُغلق لكلّ نداء.
        # ⚠️ وُلد هذا السطر من طفرةٍ نجت: الصيغة الأولى فحصت وجود الاسم،
        # فمرّت `_connection_DISABLED` سالمة. ما لم يُعطَّب عمدًا لا يُوثَق به.
        opens = [m for m in re.finditer(r"=\s*self\._connect\(\)", text)]
        for match in opens:
            head = text.rfind("\n    def ", 0, match.start())
            owner = text[head:head + 60].strip().split("(")[0].replace("def ", "")
            # `_connection` هي المستثناة بحكم دورها، و`_ensure_store` مسار
            # إقلاعٍ وتعافٍ يجري مرّة لا مع كلّ صفّ — فتحُه هناك لا يتكرّر.
            if owner == "_connection" or owner.startswith("_ensure_store"):
                continue
            problems.append((name, "اتّصال جديد لكلّ كتابة",
                             "`self._connect()` داخل `%s`" % owner))
    return problems


def main() -> int:
    problems = audit()
    print("=" * 74)
    print("حارس عقد المعالج والاتّصال — مخازن ٧٠٠-٧٥٠")
    print("=" * 74)
    if not problems:
        total = sum(1 for n in os.listdir(ROOT)
                    if os.path.isfile(os.path.join(ROOT, n, "atom.py")))
        print("سليم: %d ذرّة — لا معالجَ ينتظر عملًا طويلًا،" % total)
        print("      ولا مخزنَ يفتح اتّصالًا لكلّ كتابة.")
        print("\nالخروق = 0")
        return 0
    for atom, kind, detail in problems:
        print("  ⛔ %-26s %-24s %s" % (atom[:26], kind, detail))
    print("\nالخروق = %d" % len(problems))
    print("العلاج: مهمّة خلفيّة بحارس «واحدة في آنٍ» · واتّصالٌ معمَّر تحت قفل.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
