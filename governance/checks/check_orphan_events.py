#!/usr/bin/env python3
"""فحص حوكمة: حدث يُنشر ولا يسمعه أحد.

تكرّر النمط ثلاث مرّات في نافذة ٢٠٢٦-٠٩-٠٧ وحدها:

- `feed.replay.tick` — ذرّتا الإعادة 625 و630 تنشران في الفراغ لأنّ 613
  لم يكن يشترك بالاسم ولا يوجّهه (أُصلح).
- `market_data.normalized` — 114 ينشر ولا مشترك له في المشروع كلّه.
- `decision.room.state` — نُشر 2,835 مرّة بلا مشترك واحد (مقيس حيًّا).

والذرّة في كل حالة **تبدو سليمة**: تعمل، وعدّاداتها ترتفع، وصحّتها خضراء
— بينما ناتجها لا يبلغ قرارًا. هذا الفحص يقرأ المانيفستات وحدها ويقارن
المنشور بالمشترَك، فيظهر الانقطاع قبل أن يُكتشف بالمصادفة.

    python3 governance/checks/check_orphan_events.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
ATOMS = ROOT / "atoms"

# أحداث تُستهلك خارج شجرة الذرّات (النواة · اللوحة · أدوات الحوكمة)، أو
# يقرؤها مشترك شامل (`subscribe_all`). ليست يتيمة، ولا تُعدّ مخالفة.
EXTERNAL: set[str] = {
    "core.atom.started", "core.atom.failed", "core.atom.unhealthy",
    "core.atom.stopped", "core.boot.completed", "core.shutdown.started",
    "tools.integrity.violation",
}
EXTERNAL_PREFIXES = ("logs.", "dashboard.", "panel.", "ui.", "telemetry.")


def _events(manifest: dict, key: str) -> list[str]:
    raw = manifest.get(key) or []
    return [str(item).strip() for item in raw if str(item).strip()]


def external_subscribers() -> set[str]:
    """أحداث يشترك بها مستهلك خارج شجرة الذرّات — لوحة أو أداة حوكمة.

    تُقرأ من الكود فعليًّا لا تُفترض: البحث عن `subscribe(` يحمل اسم الحدث.
    ذكرُ الاسم في فحص يقارن المانيفستات ليس استهلاكًا، فلا يُحتسب.
    """
    found: set[str] = set()
    roots = [ROOT / "governance", ROOT / "core", ROOT / "shared"]
    pattern = re.compile(r'subscribe(?:_all)?\(\s*["\']([a-zA-Z0-9_.]+)["\']')
    for root in roots:
        if not root.is_dir():
            continue
        for path in root.rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            try:
                found.update(pattern.findall(path.read_text(encoding="utf-8")))
            except OSError:
                continue
    return found


def scan() -> tuple[dict[str, list[str]], set[str]]:
    published: dict[str, list[str]] = {}
    subscribed: set[str] = set()
    for path in sorted(ATOMS.rglob("manifest.yaml")):
        try:
            manifest = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            continue
        owner = path.parent.name
        for event in _events(manifest, "publishes"):
            published.setdefault(event, []).append(owner)
        subscribed.update(_events(manifest, "subscribes"))
    return published, subscribed


def inspect() -> tuple[bool, list[str], list[str]]:
    """يفصل اليتيم الخطر عن اليتيم المتوقَّع.

    `*.state` عرض لوحة بطبيعته: يُنشر ليُقرأ من خارج شجرة الذرّات، فغيابُ
    مشترك له ليس انقطاعًا. أمّا حدث **بيانات** بلا مشترك فهو ناتج لا يبلغ
    قرارًا — وهو ما يستحقّ الوقوف.
    """
    published, subscribed = scan()
    subscribed |= external_subscribers()
    data_orphans: list[str] = []
    panel_orphans: list[str] = []
    for event, owners in sorted(published.items()):
        if event in subscribed or event in EXTERNAL:
            continue
        if event.startswith(EXTERNAL_PREFIXES):
            continue
        line = f"{event} ← {' · '.join(owners)}"
        (panel_orphans if event.endswith(".state") else data_orphans).append(line)
    return not data_orphans, data_orphans, panel_orphans


def main() -> int:
    ok, data_orphans, panel_orphans = inspect()
    print("فحص الأحداث اليتيمة — يُنشر ولا يسمعه أحد")
    print("ORPHAN_DATA_EVENTS=" + ("NONE" if ok else str(len(data_orphans))))
    print("ORPHAN_PANEL_STATES=%d (متوقَّع — عرض لوحة)" % len(panel_orphans))
    if ok:
        print("✅ كل حدث بيانات له مشترك.")
        return 0
    print("\nأحداث بيانات بلا مشترك — ناتج لا يبلغ قرارًا:")
    for line in data_orphans:
        print("  ⚠ " + line)
    print("\nاليتيم ليس عطلًا دائمًا: قد يكون مسارًا لم يُوصَل بعد، أو ناتجًا")
    print("صار زائدًا. القرار للمالك — لكن لا يبقى مخفيًّا.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
