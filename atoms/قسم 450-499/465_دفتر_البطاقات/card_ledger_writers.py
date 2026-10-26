"""٤٦٥ — الكتّاب الآخرون: البوّابات والشهود والمحلّلون، وجملةُ «لماذا».

v1.30.1 (٢٠٢٦-٠٩-٢٣، ختم `nq`): نُقلت **حرفيًّا** من `atom.py` (حدّ الأربع مئة
سطر). كلّ دالّةٍ تأخذ الذرّة أوّلًا (`atom`) مكان `self`، والمعالِجات يشترك بها
`atom.py` بأسمائها القديمة كما كانت.
"""

from __future__ import annotations

from typing import Any, Callable

from card_ledger_common import _DRAFT_SYMBOLS, SIDE_BUY
from card_ledger_common import _meta, _text


#: أسماءُ الشهود بالعربيّة — تُكتب في الجملة لا أرقامًا يفكّها قارئ.
_WHO = {"414": "بطاقة استمرار الاتّجاه", "415": "التوليفة الشاملة", "406": "الاختراق", "410": "السيولة", "404": "الاتّجاه",
        "405": "الانعكاس", "407": "الارتداد", "408": "الزخم",
        "409": "المدى", "413": "المحصّلة", "453": "الدرجة",
        "458": "حلّ التعارض", "207": "البنية", "208": "الطور",
        "260": "السيولة المقيسة", "313": "الشذوذ", "316": "جودة البيانات",
        "411": "الأخبار", "460": "الثقة", "461": "الظروف",
        "462": "التوقيت", "463": "المركز", "464": "الطزاجة",
        "468": "الأصل", "465": "النسبة", "467": "الإرسال"}


def compose_reason(atom, symbol: str, card: dict[str, Any]) -> str:
    """جملةُ «لماذا» — مركّبةٌ ممّا قاله الشهود فعلًا، لا قالبًا.

    حكم المالك ٢٠٢٦-٠٩-١٨: «لما بدنا نخسر بدي أسلك ليش، بدي جواب. ولما
    نربح كمان». والبطاقة كانت تحمل **من قال ماذا** ولا تحمل الجملة، فيُقرأ
    صفٌّ من الأرقام لا سبب. وهذه تُركّب من الحقول المقيسة وحدها: من لم
    يتكلّم لا يُذكر، ولا تُضاف كلمةٌ لا يسندها رقم.
    """
    seen = card.get("seen") or {}
    parts: list[str] = []
    side = "شراء" if card.get("side") == SIDE_BUY else "بيع"
    parts.append("%s على %s" % (side, symbol))

    # ٢٠٢٦-١٠-٠٧ (ختم المالك «NQ»): البطاقة 414 بانيةٌ أيضًا — وحدها حيّةً بعد أرشفة 406/410.
    builder = next((a for a in ("415", "414", "406", "410") if a + ".stop" in seen), "")
    if builder:
        body = card.get("why") or {}
        why_stop = _text(body.get("invalidation_reason"))
        why_target = _text(body.get("target_reason"))
        line = "بناها %s" % atom._WHO.get(builder, builder)
        if why_stop:
            line += " — الإبطال: %s" % why_stop
        if why_target:
            line += "، والهدف: %s" % why_target
        parts.append(line)

    direction = seen.get("413.direction")
    strength = seen.get("413.strength")
    if direction is not None:
        parts.append("المحصّلة %s بقوّة %s" % (direction, strength))
    margin = seen.get("458.margin")
    if margin is not None:
        parts.append("حُسم بهامش %s" % margin)

    context = [(atom._WHO.get(a, a), seen.get(a + "." + f))
               for a, f in (("207", "state"), ("208", "phase"), ("208", "state"),
                            ("313", "outlier"), ("313", "signal"),
                            ("316", "quality"), ("411", "window"))
               if seen.get(a + "." + f) not in (None, "")]
    if context:
        parts.append("السوق: " + " · ".join("%s=%s" % kv for kv in context))

    blocked = [atom._WHO.get(a, a) for a in
               ("460", "461", "462", "463", "464", "468", "454")
               if str(seen.get(a + ".verdict") or "").startswith("block")]
    if blocked:
        parts.append("حجبها: " + " · ".join(blocked))
    rr = seen.get("465.rr")
    if rr is not None:
        parts.append("النسبة %s" % rr)
    scale = seen.get("465.scale")
    if scale:
        parts.append("الأرضيّة %s" % scale)
    return " | ".join(parts)


def gate_handler(atom, author: str) -> Callable[[dict[str, Any]], Any]:
    async def handler(payload: dict[str, Any]) -> None:
        if not atom._running or not isinstance(payload, dict):
            return
        symbol = _text(payload.get("symbol")).upper()
        if not symbol:
            return
        verdict = _text(payload.get("signal")).lower() or "-"
        source = _text(_meta(payload).get("source"))
        atom._write(symbol, author, "verdict",
                    verdict if not source else "%s:%s" % (verdict, source))
    return handler


def witness_handler(atom, author: str,
                    keys: tuple[str, ...]) -> Callable[[dict[str, Any]], Any]:
    """شاهدٌ من قسمٍ آخر — أوّلُ حقلٍ مملوء يُكتب، ولا يُخترع بديل.

    ولا يُكتب إلا في بطاقةٍ حيّة: قبل ولادتها يذهب إلى المسوّدة، وبعد
    إغلاقها لا يُكتب شيء. والقيمة نفسها من الشاهد نفسه تُطوى عدًّا.
    """
    async def handler(payload: dict[str, Any]) -> None:
        if not atom._running or not isinstance(payload, dict):
            return
        symbol = _text(payload.get("symbol")).upper()
        if not symbol:
            return
        for key in keys:
            value = payload.get(key)
            if value not in (None, "", [], {}):
                if isinstance(value, float):
                    value = round(value, 4)
                atom._write(symbol, author, key, value)
                return
    return handler


# ٢٠٢٦-١٠-٠٧ (ختم «NQ»): خرجت on_scored (453) وon_resolved (458) وon_filtered (454) وon_aggregate (413) —
# ناشروها أُرشفوا مع فكّ الأقسام عن القرار، ولا اختبار يستدعيها.


def opinion_handler(atom, atom_id: str, label: str):
    """مغلَّفٌ يلتقط رأي محلّلٍ واحد — أرخص ما يمكن: إسنادٌ ولا شيء غيره."""
    async def _handle(payload: dict[str, Any]) -> None:
        if not atom._running or not isinstance(payload, dict):
            return
        symbol = _text(payload.get("symbol")).upper()
        if not symbol:
            return
        value = payload.get("declared_direction")
        if value in (None, ""):
            value = payload.get("direction")
        book = atom._opinions.get(symbol)
        if book is None:
            if len(atom._opinions) >= _DRAFT_SYMBOLS:
                atom._opinions.pop(next(iter(atom._opinions)))
            book = atom._opinions[symbol] = {}
        book[atom_id] = (label, value, payload.get("signal"),
                         payload.get("strength"), payload.get("confidence"),
                         payload.get("state") or payload.get("status"),
                         fact_summary(payload))
    return _handle


#: مفاتيح الوصف لا الحقيقة — لا تُختم.
_NOT_FACT = frozenset({"method", "timeframe", "symbol", "id", "cycle_id", "warnings", "source"})


def fact_summary(payload: dict[str, Any], limit: int = 10) -> str:
    """٢٠٢٦-١٠-٠٨ (أمر المالك «أوصل كلّ الأقسام بالاستراتيجيّات… والنماذج»): بعد عقد الحقائق لا رأي لقسم —
    فيُختم على الصفقة **حقيقته**: أرقامه الخام من `metadata` لحظة ولادتها، باسمه. فتُحسب الصفقة على كلّ
    عاملٍ شارك (أمره ١٠-٠٧)، ويُقاس بعدها أيّ قسمٍ يضيف فيدخل القرار بقياسه."""
    meta = payload.get("metadata")
    if not isinstance(meta, dict):
        # ٢٠٢٦-١٠-٠٨ (ختم المالك «NQ» — المعرفة أوّلًا): ذرّات المعرفة (117–120) تنشر حقائقها في `facts`.
        meta = payload.get("facts")
    if not isinstance(meta, dict):
        return ""
    parts: list[str] = []
    for key, value in meta.items():
        if key in _NOT_FACT or value is None or isinstance(value, (dict, list, tuple)):
            continue
        if isinstance(value, float):
            value = round(value, 4)
        elif isinstance(value, str) and len(value) > 24:
            continue
        parts.append("%s=%s" % (key, value))
        if len(parts) >= limit:
            break
    return " · ".join(parts)


def stamp_opinions(atom, symbol: str) -> int:
    """يجمّد آراء المحلّلين كلّها على البطاقة لحظة ميلادها.

    تُكتب بأسماء أصحابها لا مجمَّعةً: من أراد بعد أيّامٍ أن يعرف
    **من أصاب ومن أخطأ** يقرأ الصفوف بأسمائها، ويعاير كلًّا بحسبه.
    """
    book = atom._opinions.get(symbol) or {}
    for atom_id, row in book.items():
        label, direction, signal, strength, confidence, state = row[:6]
        fact = row[6] if len(row) > 6 else ""
        if fact:
            atom._write(symbol, atom_id, "حقيقة", "%s · %s" % (label, fact))
        if direction in (None, "") and strength is None and confidence is None and not state:
            continue          # لا رأي بعد عقد الحقائق — الحقيقة وحدها خُتمت أعلاه
        parts = [label]
        if direction not in (None, ""):
            try:
                number = float(direction)
                parts.append("شراء" if number > 0 else
                             "بيع" if number < 0 else "حياد")
                parts.append("%+.0f" % number)
            except (TypeError, ValueError):
                parts.append(str(direction))
        if signal: parts.append(str(signal))
        for name, val in (("قوّة", strength), ("ثقة", confidence)):
            try:
                if val is not None: parts.append("%s=%.0f" % (name, float(val)))
            except (TypeError, ValueError):
                pass
        if state: parts.append(str(state))
        atom._write(symbol, atom_id, "رأي", " · ".join(parts))
    return len(book)
