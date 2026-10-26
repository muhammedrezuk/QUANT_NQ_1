"""٤٦٥ — المخزن: الاستعادة، والكتابة والطيّ، والدفع مع النبض، والكنس.

v1.30.1 (٢٠٢٦-٠٩-٢٣، ختم `nq`): نُقلت **حرفيًّا** من `atom.py` (حدّ الأربع مئة
سطر). كلّ دالّةٍ هنا تأخذ الذرّة أوّلًا (`atom`) مكان `self`، و`atom.py` يُبقي
اسمها القديم بوّابةً رفيعة — فكلّ نداءٍ `atom._x(...)` يمرّ من الذرّة كما كان.
"""

from __future__ import annotations

import asyncio
import sqlite3
import time
from typing import Any

from card_ledger_common import _DRAFT_CAP, _DRAFT_SYMBOLS, _text


def _legs_of(body: Any) -> list[dict[str, Any]]:
    """أجزاء الصفقة المحفوظة في جسم البطاقة (`card_ledger_legs.body`) — وما ليس قائمةَ أجزاءٍ يُترك."""
    legs = body.get("legs") if isinstance(body, dict) else None
    return [dict(leg) for leg in legs if isinstance(leg, dict)] if isinstance(legs, list) else []


async def reload_live(atom) -> None:
    """يستعيد الحيّ من المخزن — فالإقلاع لا يفتح بطاقةً ثانية لزوجٍ مشغول."""
    try:
        cards = await asyncio.to_thread(atom._store.live_cards)
    except (OSError, sqlite3.Error) as exc:
        atom._store_error(exc)
        return
    # ⛔ كانت تسعةَ حقولٍ فقط، بلا `stop` ولا `target` ولا `ticket`.
    #    فالصفُّ يحملها (`_CARD_COLUMNS`) **والاستعادةُ ترميها** — وكلّ
    #    حارسٍ يقرؤها يموت صامتًا بعد أوّل إقلاع. وقع مرّتين في يومٍ
    #    واحد (٢٠٢٦-٠٩-١٩): حارس الهدف الميّت أصلحتُه في مسار الكتابة
    #    فقتلَته الاستعادة، وحارس الفكرة الميّتة لم يشتغل أصلًا فبقيت
    #    البطاقة ٤٤ تحجز خانة بتكوين ووقفُها مخترَقٌ بـ٢٢٣ نقطة.
    #    **كلُّ حقلٍ يقرؤه حارسٌ يُستعاد** — والقائمة تُقرأ مع الحرّاس.
    atom._live = {
        _text(card["symbol"]): {"card_no": int(card["card_no"]),
                                "state": _text(card["state"]),
                                "side": _text(card["side"]), "seen": {},
                                "entry": card["entry"],
                                "stop": card["stop"],
                                "target": card["target"],
                                "ticket": card["ticket"],
                                "opened_at": card["opened_at"],
                                "dispatched_at": card["dispatched_at"],
                                "stop_points": card["stop_points"],
                                "peak": card["peak_points"],
                                "worst": card["worst_points"],
                                "saved_r": card["peak_r"] or 0.0,
                                # ٢٠٢٦-١٠-٠٩ (ختم المالك «NQ» — الصفقة صافيةً بأجزائها): أجزاءُ صفقةٍ
                                # مفتوحة جزئيًّا وسعرُ تنفيذها يُستعادان — وإلّا بدأ الصافي من صفرٍ بعد الإقلاع.
                                "legs": _legs_of(card.get("body")),
                                "fill": card["fill_price"]}
        for card in cards}
    atom._changed = True


def write(atom, symbol: str, author: str, field: str, value: Any) -> None:
    """يكتب في البطاقة الحيّة، أو يحفظ في المسوّدة إن لم تُولد بعد.

    ولا يُكتب إلا المتغيّر: القيمة نفسها من الكاتب نفسه تُطوى عدًّا.
    """
    symbol = _text(symbol).upper()
    if not symbol:
        return
    key = author + "." + field
    card = atom._live.get(symbol)
    if card is None:
        draft = atom._drafts.get(symbol)
        if draft is None:
            if len(atom._drafts) >= _DRAFT_SYMBOLS:
                atom._drafts.pop(next(iter(atom._drafts)))
            draft = atom._drafts[symbol] = {}
        if draft.get(key) == value:
            return
        if key not in draft and len(draft) >= _DRAFT_CAP:
            draft.pop(next(iter(draft)))
        draft[key] = value
        return
    seen = card["seen"]
    if seen.get(key) == value:
        atom._folded += 1
        return
    seen[key] = value
    atom._pending.append((card["card_no"], author, field, value, time.time()))
    atom._writes += 1


async def flush(atom) -> None:
    if atom._store is None:
        return
    # ⛔ التحديثاتُ أوّلًا ثمّ الملاحظات — كما كان الترتيب قبل التأجيل:
    #    `_update` كان فوريًّا و`_pending` مؤجَّلًا، فسبقه دائمًا.
    #    وقلبُ الترتيب هنا يقلب ما يصل القرصَ أوّلًا بلا سبب.
    if atom._pending_updates:
        updates, atom._pending_updates = atom._pending_updates, []
        for index, (card_no, fields, body) in enumerate(updates):
            try:
                await asyncio.to_thread(atom._store.update, card_no,
                                        fields, body)
            except sqlite3.IntegrityError as exc:
                # 🔴 ٢٠٢٦-٠٩-٢١ — هذا **ليس عطل قرص**، بل الفهرس الفريد
                #    يفعل عمله: «بطاقةٌ حيّةٌ واحدة لكلّ رمز». تحديثٌ
                #    يعيد بطاقةً منتهيةً إلى الحياة ورمزُها مشغول يُرفض
                #    بحقّ، فيُسقَط وحده ويُعلَن باسمه.
                #
                #    وكان يُعامَل عطلَ قرص: تُعاد الدفعة كاملةً إلى
                #    الطابور ويُرفع `_store_ready = False`. فالصفُّ
                #    المسموم يعود فيُرفض فيسمّم الطابور أبدًا، **ويتوقّف
                #    الكنس الذي كان سيُنهي البطاقة العالقة** — أي أنّ
                #    السبب لا يُنظَّف أبدًا. مقيس: البطاقة ٦١ (الذهب)
                #    عالقة `DISPATCHED` ‎13.2‎ ساعة و٤٦٥ ساقطٌ معها.
                atom._dup_live += 1
                atom._last_error = "%s: %s" % (card_no, str(exc)[:80])
                continue
            except (OSError, sqlite3.Error) as exc:
                # ما لم يُكتب يعود إلى رأس الطابور — قفلًا عابرًا كان أو عطبًا.
                atom._pending_updates = updates[index:] + atom._pending_updates
                atom._store_error(exc)
                raise
    if not atom._pending:
        atom._last_flush = time.time()
        return
    batch, atom._pending = atom._pending, []
    try:
        await asyncio.to_thread(atom._store.notes, batch)
    except (OSError, sqlite3.Error) as exc:
        # لا تُرمى الدفعة على خطأ قرص — تُعاد إلى الطابور وتُحاول ثانية.
        atom._pending = batch + atom._pending
        atom._last_error = str(exc)
        raise
    atom._last_flush = time.time()


async def update(atom, card_no: int, fields: dict[str, Any] | None = None,
                 body: dict[str, Any] | None = None) -> None:
    """يُقيّد تحديثًا ولا يكتبه — الكتابةُ تقع مع النبض.

    ⛔ لا تُغيَّر بصمةُ النداء ولا مواضعُه: كلُّ `await self._update(...)`
    يبقى كما هو، فلا يتبدّل منطقُ قرارٍ ولا مخاطرةٍ ولا نيّةِ أمر.
    """
    if atom._store is None:
        return
    atom._pending_updates.append((card_no, fields, body))


def read_seq(atom) -> int:
    """أعلى رقم بطاقة صُرف — يُقرأ في خيط، لا على الحلقة."""
    connection = atom._store.connect()
    try:
        row = connection.execute(
            "SELECT seq FROM sqlite_sequence WHERE name='cards'").fetchone()
        return int(row[0]) if row else 0
    finally:
        connection.close()


def read_expired(atom, expired: list[int]) -> list[tuple[Any, ...]]:
    """مستويات البطاقات المنتهية — تُقرأ في خيط، لا على الحلقة."""
    connection = atom._store.connect()
    try:
        return connection.execute(
            "SELECT symbol,side,entry,stop,target,ticket FROM cards "
            "WHERE card_no IN (%s)" % ",".join("?" * len(expired)),
            [int(x) for x in expired]).fetchall()
    finally:
        connection.close()


async def sweep(atom, now: float) -> None:
    if atom._store is None:
        return
    try:
        expired = await asyncio.to_thread(
            atom._store.expire, now - atom._max_open_age,
            now - atom._max_dispatch_age)
    except (OSError, sqlite3.Error) as exc:
        atom._store_error(exc)
        return
    # حكم المالك ٢٠٢٦-٠٩-١٨: «مابصير يتوسّع ستوب ولا يتوسّع هدف».
    # البطاقة تحمل وقف التحليل (`stop`) ووقف الأمر (`sent_stop`) معًا،
    # فالتوسيع بينهما مقروءٌ برقمين لا بتنقيب. ولا أحجبه — ليس من قسمي —
    # لكنّي أعدّه وأسمّيه، فيُرى إن وقع بدل أن يُكتشف بعد الخسارة.
    try:
        live = await asyncio.to_thread(atom._store.live_cards)
    except (OSError, sqlite3.Error):
        live = []
    for card in live:
        built, sent = card.get("stop"), card.get("sent_stop")
        entry = card.get("entry")
        if built is None or sent is None or entry is None:
            continue
        if abs(float(sent) - float(entry)) > abs(float(built) - float(entry)) * 1.01:
            symbol = _text(card.get("symbol"))
            key = "%s|%s" % (card["card_no"], round(float(sent), 6))
            if key not in atom._widened_seen:
                atom._widened_seen.add(key)
                if len(atom._widened_seen) > 512:
                    atom._widened_seen.clear()
                atom._widened += 1
                atom._write(symbol, "465", "stop_widened",
                            "%.6f→%.6f" % (float(built), float(sent)))
    try:
        seq = await asyncio.to_thread(atom._read_seq)
    except (OSError, sqlite3.Error):
        seq = 0
    if seq:
        if seq < atom._high_water:
            atom._numbering_broke = "%d ⟵ %d" % (atom._high_water, seq)
        else:
            atom._high_water = seq

    # تحليلٌ نصفُه وصل ونصفُه لم يأتِ: يُنقض بعمر البطاقة المفتوحة نفسه،
    # ويُعدّ ليُرى. ولا يحمل رقمًا — لم يكتمل فلم يستحقّه.
    # الانتظار لا يُقصّ بعمر البطاقة (المالك: «بنضل عم نبني فيها لحتى
    # تزبط»)، بل بيومٍ كامل — وما جاوزه سوقٌ مضى لا تحليلٌ ينضج.
    stale = [s for s, w in atom._waiting.items()
             if now - float(w.get("at") or 0.0) > max(atom._max_open_age, 86400.0)]
    for s in stale:
        atom._waiting.pop(s, None)
        atom._incomplete += 1

    if not expired:
        return
    gone = set(expired)
    for symbol in [s for s, c in atom._live.items() if c["card_no"] in gone]:
        atom._live.pop(symbol, None)
    atom._expired += len(expired)
    # 🗂️ فكرةٌ انتهت بلا تنفيذ تُحفَظ بمستوياتها، فلا تأخذ رقمًا ثانيًا
    #    حتّى تتغيّر. والمنفَّذة لا تُحفظ: لها نتيجةٌ وقد قيلت.
    if expired:
        try:
            rows = await asyncio.to_thread(atom._read_expired, list(expired))
        except (OSError, sqlite3.Error):
            rows = []
        for symbol, side, entry, stop, target, ticket in rows:
            if ticket or entry is None or stop is None:
                continue
            atom._spent_idea[_text(symbol).upper()] = (
                _text(side).lower(), float(entry), float(stop),
                float(target) if target is not None else None)
        if len(atom._spent_idea) > _DRAFT_SYMBOLS:
            atom._spent_idea.pop(next(iter(atom._spent_idea)))
    atom._changed = True
