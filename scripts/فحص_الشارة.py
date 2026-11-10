# -*- coding: utf-8 -*-
"""يشغّل `health_check()` لذرّةٍ فعلًا — لأنّ عدّ الوسائط لا يكفي.

**أربع مرّاتٍ في يومين** أسقطتُ ذرّةً بصيغةٍ نصّيّة معطوبة:
  · ٤٦٥ — `آراء=%d/%d` بوسيطٍ بلا خانة        ⟹ `TypeError`
  · ١٦٦ — نقصُ وسيطٍ في الشارة
  · ٢٠٠ — حقلٌ يُقرأ قبل تعريفه
  · ٤٦٥ — `منذ_الإقلاع=%d` في آخر الصيغة ووسيطُه في **وسط** القائمة
          ⟹ `must be real number, not str` والدفتر ساقط.

وفحصي الساكن (تحليل `ast` وعدُّ `%` مقابل طول الـtuple) أمسك الثلاثة
الأولى **وسقط في الرابعة**: العدد صحيح والترتيب خطأ. فلا يُمسك هذا الصنف
إلّا بتشغيل الصيغة على قيمٍ حقيقيّة.

    python scripts/فحص_الشارة.py 465
    python scripts/فحص_الشارة.py 405 406 410 465 154 360

⛔ لا يمسّ المنصّة: يُنشئ الكائن في هذه العمليّة ولا يتّصل بنواةٍ ولا مخزن.
"""
from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _folder(atom_id: str) -> Path:
    for path in sorted(ROOT.glob("atoms/*/%s_*" % atom_id)):
        if path.is_dir():
            return path
    raise FileNotFoundError(atom_id)


def _load(folder: Path):
    # ⛔ الذرّة قد تستورد شقيقةً من مجلّدها، والنواةُ تضع المجلّد في
    #    `sys.path` **أثناء التنفيذ** (`bootloader.py:252-259`). فبلا
    #    محاكاة ذلك يسقط الفاحص على ذرّةٍ سليمة — وقعت فيها مع ٣٥٠.
    if str(folder) not in sys.path:
        sys.path.insert(0, str(folder))
    spec = importlib.util.spec_from_file_location("badge_%s" % folder.name[:3],
                                                  folder / "atom.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def check(atom_id: str) -> bool:
    folder = _folder(atom_id)
    try:
        atom = _load(folder).Atom()
    except Exception as exc:  # noqa: BLE001
        print("  %-4s ⛔ لا يُستورد: %s" % (atom_id, exc))
        return False
    ok = True
    # ⛔ **الفرعُ الذي لم يُشغَّل لم يُفحَص.** أوّل نسخةٍ من هذا الفاحص
    #    أعطت ٤٦٥ «أخضر» وهي تخرج من `CARD_STORE_UNAVAILABLE` قبل أن تبلغ
    #    الشارة الطويلة — أي أنّها فحصت فرعًا لا عطبَ فيه أصلًا. فالبوّابات
    #    المعروفة تُفتح عمدًا حتّى تُبلَغ الصيغةُ الكاملة.
    GATES = {"_store_ready": True, "_schema_missing": [], "_records": 1,
             "_candles_seen": 1, "_seen": 1, "_emitted": 1, "_setups": 1,
             "_decisions_seen": 1, "_store": None}
    for name, value in GATES.items():
        if hasattr(atom, name) and not isinstance(getattr(atom, name), (dict,)):
            try: setattr(atom, name, value)
            except Exception: pass
    for running, label in ((False, "قبل الإقلاع"), (True, "بعد الإقلاع")):
        setattr(atom, "_running", running)
        try:
            status = await atom.health_check()
            message = getattr(status, "message", "")
            # الشارة تُقرأ من `message`؛ `details` تُحذف عند حدّ النواة.
            if not isinstance(message, str):
                raise TypeError("الرسالة ليست نصًّا: %r" % type(message))
            print("  %-4s %-12s ✅ %s" % (atom_id, label, message[:96]))
        except Exception as exc:  # noqa: BLE001
            ok = False
            print("  %-4s %-12s ⛔ %s: %s" % (atom_id, label,
                                             type(exc).__name__, exc))
    return ok


async def run(ids: list[str]) -> int:
    print("=== تشغيلُ الشارات فعلًا — لا عدّ وسائط ===")
    bad = 0
    for atom_id in ids:
        if not await check(atom_id):
            bad += 1
    print("\nمعطوبة: %d من %d" % (bad, len(ids)))
    return 1 if bad else 0


if __name__ == "__main__":
    ids = sys.argv[1:] or ["405", "406", "410", "465", "154", "360"]
    raise SystemExit(asyncio.run(run(ids)))
