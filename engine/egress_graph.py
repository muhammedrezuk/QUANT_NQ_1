# -*- coding: utf-8 -*-
"""تصنيف الخروج بالإغلاق المتعدّي — لا بقائمة أسماء.

قاعدة المالك حرفًا: «هل يوجد downstream consumer يؤثّر على تنفيذ/أمر المال؟
إذا نعم ⟵ MONEY. إذا لا ⟵ INTERNAL / STORAGE / OBS.» وهي قاعدةٌ **متعدّية**:
حدثٌ لا يقرؤه أحدٌ في الجذر قد يغذّي — عبر ذرّةٍ أو عشر — أمرًا يُرسَل إلى
الوسيط. فالاشتقاق المباشر لا يكفي.

المقيس ٢٠٢٦-٠٩-١٨: الاشتقاق المباشر صنّف 80 حدثًا مالًا و74 تخزينًا والباقي
عرضًا، فوقعت `structure.*` و`liquidity.*` خارج المال بينما سلسلة التنفيذ في
الجذر تنتظرها — فدفعت مهلة البارد. والأثر مقيس في الشلّال: 0.6654 ث لحدثٍ
ينتهي المحرّك منه في 0.0280.

## من أين تأتي البذرة — بلا قائمة يدويّة

من **تصنيف النواة المختومة نفسها**: `_is_command(name)` يعرّف الفعل الماليّ
بعلاماته (`order` · `.buy` · `.sell` · `.execute` · `.cancel` · `.submit` ·
`.send` · `final_decision` · `command`). هذه هي المصبّات، وهي التعريف الذي
تستعمله النواة أصلًا لتمنع الإسقاط والدمج — لا اختراع هنا.

## ومن أين يأتي الرسم

من المانيفستات: كلّ ذرّة تعلن `subscribes` و`publishes`. فاستهلاك `s`
وإنتاج `p` في الذرّة نفسها حافّةٌ `s ⟶ p`. والإغلاق العكسيّ من المصبّات
يعطي كلّ حدثٍ يصل إلى المال.

⚠️ الحدّ المعلَن: الحافّة **مُعلَنة لا مُثبَتة** — ذرّةٌ تشترك بحدثين وتنشر
حدثًا تُرسَم لها حافّتان وإن كان أحدهما لا يؤثّر فعلًا. فالخطأ في اتّجاه
**الأمان**: يُصنَّف مالًا ما ليس مالًا، فيُنقَل أسرع؛ ولا يُصنَّف عرضًا ما
هو مال. وهذا هو الاتّجاه الوحيد المقبول في مسار أوامر.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

from core.event_bus import _is_command


def money_sinks(events: Iterable[str]) -> set[str]:
    """المصبّات: ما تعدّه النواة المختومة فعلًا ماليًّا بعلامته."""
    return {str(e) for e in events if _is_command(str(e))}


def read_declared_graph(atoms_root: str | Path) -> tuple[dict[str, set[str]], set[str]]:
    """يقرأ المانيفستات ويعيد (حافّة: مُستهلَك ⟶ مُنتَج، وكلّ الأسماء)."""
    import yaml

    edges: dict[str, set[str]] = defaultdict(set)
    names: set[str] = set()
    for manifest in Path(atoms_root).rglob("manifest.yaml"):
        try:
            data = yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}
        except Exception:  # noqa: BLE001 — مانيفست معطوب لا يُسقط الاشتقاق
            continue
        if data.get("id") is None:
            continue
        subscribes = [str(e) for e in (data.get("subscribes") or ())]
        publishes = [str(e) for e in (data.get("publishes") or ())]
        names.update(subscribes)
        names.update(publishes)
        for consumed in subscribes:
            edges[consumed].update(publishes)
    return dict(edges), names


def money_closure(edges: dict[str, set[str]], names: set[str],
                  extra_sinks: Iterable[str] = ()) -> set[str]:
    """كلّ حدثٍ يصل — بحافّةٍ أو بسلسلة — إلى فعلٍ ماليّ."""
    sinks = money_sinks(names) | {str(e) for e in extra_sinks}
    # عكسُ الرسم مرّةً واحدة: مُنتَج ⟶ من يُنتِجه عن استهلاك.
    reverse: dict[str, set[str]] = defaultdict(set)
    for consumed, produced in edges.items():
        for item in produced:
            reverse[item].add(consumed)
    money = set(sinks)
    frontier = list(sinks)
    while frontier:
        current = frontier.pop()
        for upstream in reverse.get(current, ()):
            if upstream not in money:
                money.add(upstream)
                frontier.append(upstream)
    return money


def published_by(atoms_root: str | Path, atom_ids: Iterable[int]) -> set[str]:
    """ما تنشره هذه الذرّات وحدها — لمعرفة ما يُولَد داخل المحرّك."""
    import yaml

    wanted = {int(a) for a in atom_ids}
    produced: set[str] = set()
    for manifest in Path(atoms_root).rglob("manifest.yaml"):
        try:
            data = yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}
        except Exception:  # noqa: BLE001
            continue
        if int(data.get("id") or -1) in wanted:
            produced.update(str(e) for e in (data.get("publishes") or ()))
    return produced


def classify(atoms_root: str | Path, *, hot_events: Iterable[str] = (),
             cold_events: Iterable[str] = (),
             extra_sinks: Iterable[str] = (),
             produced_here: Iterable[str] = (),
             keep_visible: Iterable[str] = (),
             urgent_markers: Iterable[str] = ()) -> dict[str, Any]:
    """الخريطة الكاملة: مال · تخزين · (الباقي عرض).

    `hot_events` ما يقرؤه الجذر فعلًا — يبقى مالًا كما كان (اشتقاقٌ مباشر
    لا يُلغى، يُضاف إليه). و`cold_events` ما تشترك به العمليّة الباردة وحدها.
    """
    edges, names = read_declared_graph(atoms_root)
    names.update(str(e) for e in hot_events)
    reachable = money_closure(edges, names, extra_sinks)

    # ── من يقرأ خارج هذه العمليّة ─────────────────────────────────────────
    # قرّاءٌ **بالاسم** لا بالجملة: `subscribe_all` (الذرّة 001 والناقل 810،
    # وكلاهما في العمليّة الباردة) مراقبٌ لا مستهلك.
    named_readers = {str(e) for e in hot_events} | {str(e) for e in cold_events}

    # ⚠️ ٢٠٢٦-٠٩-١٨ (مقيس ومصحَّح في اليوم نفسه): أوّل اشتقاقٍ متعدٍّ جعل
    # المال = الإغلاق كلّه، فصار 241 اسمًا من 368 — واحدٌ وستّون بالمئة.
    # ومالٌ يعني ستّين بالمئة لا يعني شيئًا: ارتفعت حصّة النقل 0.23 ⟵ 0.43
    # وسقط العرض إلى صفر. فالإغلاق يقرّر **العجلة** لا **العبور**:
    #
    #     يعبر ⟵ من له قارئٌ بالاسم خارج العمليّة
    #     مال  ⟵ منه: ما يصل إلى فعلٍ ماليّ
    #
    # ما أعلنه المسبار علامةً (تِكّة أو قرار) — من عقده لا من يدٍ تكتب أسماء.
    visible = tuple(str(p) for p in keep_visible if str(p))

    money = reachable & named_readers

    # ⛔ ٢٠٢٦-٠٩-١٨ — جذر ذيل §٢٩، مقيسًا من مسار الأثر نفسه:
    # السلسلة كلّها تنتهي عند 0.16 ث، ثمّ **صمتٌ 0.69–0.81 ث**، ثمّ يصل الحدث
    # المُغلِق. وسببه أنّ `decision.room.state` و`decision.dispatch.state` —
    # وهما اللذان يُغلقان قياس §٢٩ — كانا يُصنَّفان «عرضًا»: يُدمجان ويُصرَّفان
    # بمضخّةٍ مهلتها نصف ثانية.
    #
    # وحدثٌ يعرّف عقد القبول لا يجوز أن يركب مسارًا كسولًا: قياسٌ يصل متأخّرًا
    # نصف ثانية يقيس المضخّة لا النظام. فما أعلنه المسبار علامةً — تِكّةً كان
    # أو قرارًا — يُرفَع إلى المال: فوريّ بلا فقدٍ ولا دمج. والقائمة من عقد
    # المسبار المُعلَن لا من يدٍ تكتب أسماء.
    # ⚠️ تصحيحٌ في اليوم نفسه: أوّل تطبيقٍ رفع **كلّ** ما يطابق `keep_visible`،
    # وفيها بادئة التِكّة `market_data.` — فصعد اثنا عشر حدثًا إلى المال
    # وسقط العرض إلى صفر، فأُغرق مسار المال وانتقل الذيل إلى بدايته
    # (3.09 ث قبل أوّل تحليل). والمُغلِقات وحدها هي التي تحتاج العجلة:
    # الفاتح يُنشَر في الجذر أصلًا ولا يعبر حدًّا.
    urgent = tuple(str(p) for p in urgent_markers if str(p))
    if urgent:
        for name in names:
            if str(name).startswith(urgent):
                money.add(str(name))
    storage = {str(e) for e in cold_events} - money

    internal = set()
    for name in (str(e) for e in produced_here):
        if name in named_readers or name in money or name in storage:
            continue
        if visible and name.startswith(visible):
            continue
        internal.add(name)

    return {
        "money": money,
        "storage": storage,
        "internal": internal,
        "reachable": len(reachable),
        "readers": len(named_readers),
        "edges": len(edges),
        "names": len(names),
        "sinks": len(money_sinks(names) | {str(e) for e in extra_sinks}),
    }
