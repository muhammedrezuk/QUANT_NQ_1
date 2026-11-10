"""بطاقة الصفقة — الكائن الواحد الذي يكتب عليه الجميع.

حكم المالك ٢٠٢٦-٠٩-١٨:
    «بدي كل قسم تحليل يشتغل على بطاقة وحدة ويكون عم يتبع بطاقة وتحليل زوج
     بدي يضل مرافق بطاقة لا اغلاقها. اذا في بطاقة شغالة على زوج مافي بطاقة
     جديدة على نفس اصل. كلها بدي ياها تكون بي مخزن محفوظ، مابدي بطاقة تضيع،
     بدي كل يكتب على بطاقة وحدة.»

أربعة عقودٍ تنبع من الحكم، وكلّها مفروضة هنا لا بالاتّفاق:

١) **رقمٌ لكلّ بطاقة** يبدأ من واحد ولا يُعاد — ``AUTOINCREMENT`` يمنع إعادة
   استعمال رقم بطاقةٍ محذوفة، فرقم البطاقة يبقى مرجعًا أبديًّا.

٢) **بطاقةٌ حيّةٌ واحدة لكلّ رمز** — فهرسٌ فريد جزئيّ في المحرّك نفسه، لا فحصٌ
   في الكود. فحصُ الكود يسقط عند سباق اثنين، والفهرس لا يسقط: الثانية تُرفض
   بـ``IntegrityError`` ويُعاد رقم البطاقة القائمة.

٣) **لا تضيع كتابة** — ``card_writes`` تسجّل (البطاقة · الكاتب · الحقل) مرّةً
   واحدة وتعدّ التكرار. فمليون حدثٍ يصير عشرات الصفوف، ويبقى معلومًا **من**
   كتب **ماذا** و**متى أوّلًا وآخرًا**. الطيّ في العدّ لا في الحذف.

٤) **لا اتّصال معمَّر** — كلّ نداءٍ يفتح ويغلق. عمَّرتُ اتّصالًا مرّةً فمنع
   ``VACUUM`` وأوقف المنصّة (حكم ٢٠٢٦-٠٩-١٨)؛ لا يتكرّر.

والمال ليس هنا: البطاقة تحمل مسافةً ونسبة — نقاطًا ومئويّة — بحكم المالك
«شغلك بل نسبة أو بعدد نقاط وليس مال، محلّل ماله علاقة بي امور مال». الحجم
والمبلغ والميزانيّة يملؤها قسم المال في حقوله الخاصّة، ولا يلمس حقول التحليل.
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from typing import Any, Iterable

CONTRACT_VERSION = "1.1.0"

STATE_OPEN = "OPEN"
STATE_DISPATCHED = "DISPATCHED"
STATE_FILLED = "FILLED"
STATE_CLOSED = "CLOSED"
STATE_REJECTED = "REJECTED"
STATE_EXPIRED = "EXPIRED"

#: الحالات التي تعني «بطاقةٌ شغّالة على هذا الزوج» — وهي وحدها التي يمنع
#: الفهرس الفريد أن تجتمع اثنتان منها على رمز واحد.
LIVE_STATES = (STATE_OPEN, STATE_DISPATCHED, STATE_FILLED)
#: الحالات النهائيّة — بطاقةٌ بلغتها لا تُعدَّل بعدها إلا بحقول النتيجة.
FINAL_STATES = (STATE_CLOSED, STATE_REJECTED, STATE_EXPIRED)

_LIVE_SQL = ",".join("'%s'" % state for state in LIVE_STATES)

_SCHEMA = (
    "CREATE TABLE IF NOT EXISTS cards ("
    "card_no INTEGER PRIMARY KEY AUTOINCREMENT, "
    "symbol TEXT NOT NULL, account_id TEXT NOT NULL DEFAULT '', "
    "broker TEXT NOT NULL DEFAULT '', state TEXT NOT NULL, side TEXT, "
    "opened_at REAL NOT NULL, updated_at REAL NOT NULL, closed_at REAL, "
    "decision_id TEXT, gate_request_id TEXT, "
    "entry REAL, stop REAL, target REAL, "
    "stop_points REAL, target_points REAL, stop_pct REAL, target_pct REAL, "
    "spread_points REAL, rr REAL, reason TEXT, "
    "peak_points REAL, worst_points REAL, peak_r REAL, worst_r REAL, "
    "outcome TEXT, profit REAL, body_json TEXT NOT NULL)",
    "CREATE UNIQUE INDEX IF NOT EXISTS cards_one_live_per_symbol "
    "ON cards(symbol) WHERE state IN (%s)" % _LIVE_SQL,
    "CREATE INDEX IF NOT EXISTS cards_by_state ON cards(state, updated_at)",
    "CREATE TABLE IF NOT EXISTS card_writes ("
    "card_no INTEGER NOT NULL, author TEXT NOT NULL, field TEXT NOT NULL, "
    "value_json TEXT, first_at REAL NOT NULL, last_at REAL NOT NULL, "
    "hits INTEGER NOT NULL DEFAULT 1, "
    "PRIMARY KEY (card_no, author, field))",
)

_CARD_COLUMNS = (
    "card_no", "symbol", "account_id", "broker", "state", "side",
    "opened_at", "updated_at", "closed_at", "decision_id", "gate_request_id",
    "entry", "stop", "target", "stop_points", "target_points",
    "stop_pct", "target_pct", "spread_points", "rr", "rr_rule", "reason",
    "peak_points", "worst_points", "peak_r", "worst_r",
    # حقول قسم المال — بختم المالك ٢٠٢٦-٠٩-١٨: «صار يسلمك بطاقة وانت تكتب
    # عليه: نفّذت بطاقة بحكم لوت ستوب هدف، ربحت خسرت انزلقت، كلّها بهل
    # بطاقة. بالأخير أنا لما بدي أراجع صفقة بسحب بطاقتها».
    # يكتبها ٥٥٢ عند الأمر و٥٦٣ عند النتيجة، ولا يكتبها التحليل أبدًا.
    "verdict_552", "volume", "sent_stop", "sent_target", "rr_at_send",
    "risk_amount", "symbol_budget", "budget_left",
    "ticket", "fill_price", "exit_price", "entry_slip", "stop_overshoot",
    "dispatched_at", "outcome", "profit",
)
#: ما يكتبه التحليل — وما عداه لقسم المال. حدٌّ مقروء لا مفروض: البطاقة
#: كائنٌ واحد يكتب عليه قسمان، والقسمة بالاسم لا بالقفل.
ANALYSIS_FIELDS = frozenset((
    "side", "decision_id", "gate_request_id", "entry", "stop", "target",
    "stop_points", "target_points", "stop_pct", "target_pct", "spread_points",
    "rr", "rr_rule", "reason", "peak_points", "worst_points", "peak_r", "worst_r"))
MONEY_FIELDS = frozenset((
    "verdict_552", "volume", "sent_stop", "sent_target", "rr_at_send",
    "risk_amount", "symbol_budget", "budget_left", "ticket", "fill_price",
    "exit_price", "entry_slip", "stop_overshoot", "outcome", "profit"))
#: أعمدةٌ تُضاف إلى جدولٍ قائم — الترقية لا تُعيد بناء المخزن ولا تُسقط بطاقة.
#: وقسم المال يضيف أعمدته هنا (حجم · مبلغ · ميزانيّة) ولا يمسّ حقول التحليل.
_MIGRATIONS: tuple[tuple[str, str], ...] = (
    ("peak_points", "REAL"), ("worst_points", "REAL"),
    ("peak_r", "REAL"), ("worst_r", "REAL"), ("rr_rule", "TEXT"),
    ("verdict_552", "TEXT"), ("volume", "REAL"),
    ("sent_stop", "REAL"), ("sent_target", "REAL"), ("rr_at_send", "REAL"),
    ("risk_amount", "REAL"), ("symbol_budget", "REAL"), ("budget_left", "REAL"),
    ("ticket", "TEXT"), ("fill_price", "REAL"), ("exit_price", "REAL"),
    ("entry_slip", "REAL"), ("stop_overshoot", "REAL"),
    # ختم `NQ` ٢٠٢٦-٠٩-١٩ — لحظةُ الإرسال، ثابتةً لا تتجدّد. تفصيلُها في
    # `expire`: `updated_at` يتحرّك مع كلّ تِكّة فلا تشيخ بطاقةٌ أبدًا.
    ("dispatched_at", "REAL"),
)
#: قاعدةُ حساب النسبة تُعلَن مع الرقم. رقمان لنفس الصفقة بقاعدتين مختلفتين
#: يُقرآن كذبًا من أحدهما — ومن يراجع بطاقةً يجب أن يرى كيف حُسبت.
RR_RULE = "(|هدف| − سبريد/2) ÷ (|وقف| + سبريد/2)"
#: الحقول التي يجوز لنداءٍ واحد أن يعدّلها — ما عداها بنيةٌ لا تُمسّ.
WRITABLE = frozenset(_CARD_COLUMNS) - {"card_no", "symbol", "opened_at"}

_SELECT = "SELECT %s,body_json FROM cards " % ",".join(_CARD_COLUMNS)


def _dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _row(row: tuple[Any, ...] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    card = dict(zip(_CARD_COLUMNS, row[:-1]))
    try:
        body = json.loads(row[-1])
    except (TypeError, ValueError):
        body = {}
    card["body"] = body if isinstance(body, dict) else {}
    return card


class CardStore:
    """مخزن البطاقات — يفتح ويغلق مع كل نداء، فلا يحبس المحرّك."""

    def __init__(self, path: str) -> None:
        self.path = path

    def connect(self) -> sqlite3.Connection:
        directory = os.path.dirname(os.path.abspath(self.path))
        if directory:
            os.makedirs(directory, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=10.0)
        # `journal_mode=WAL` كتابةٌ لا تحترم `busy_timeout`، وكانت المهلة
        # تُضبط بعدها فتُنفَّذ بصفر. تفصيلُهما في
        # [[pragma-wal-ignores-busy-timeout]] وفي `durable_execution_journal`.
        # والبطاقة أثرُ الصفقة الوحيد — سقوطُ كتابةٍ فيها يفقد رحلتها.
        connection.execute("PRAGMA busy_timeout=10000")
        try:
            mode = connection.execute("PRAGMA journal_mode").fetchone()
        except sqlite3.Error:
            mode = None
        if not mode or str(mode[0]).lower() != "wal":
            connection.execute("PRAGMA journal_mode=WAL")
        return connection

    def ensure(self) -> None:
        connection = self.connect()
        try:
            for statement in _SCHEMA:
                connection.execute(statement)
            existing = {row[1] for row in connection.execute("PRAGMA table_info(cards)")}
            for name, kind in _MIGRATIONS:
                if name not in existing:
                    connection.execute("ALTER TABLE cards ADD COLUMN %s %s" % (name, kind))
            connection.commit()
        finally:
            connection.close()

    def verify(self) -> list[str]:
        """أعمدةُ العقد الغائبة عن الجدول — قائمةٌ فارغة تعني أنّه مطابق.

        فحصُ السلامة ٧١٧ يرى التلف والطابع الزمنيّ **ولا يرى الشكل** (مقيس
        ٢٠٢٦-٠٩-١٨ بقسم ٧٠٠-٧٤٩: صفر ذكرٍ لـ`schema` أو `table_info` في كوده).
        فعمودٌ يختفي أو اسمٌ يُضاف إلى ``_CARD_COLUMNS`` ويُنسى في
        ``_MIGRATIONS`` يكسر كلّ قراءةٍ صامتًا على قاعدةٍ قائمة. وحارسُ
        العقد على صاحب العقد — لا على من يحرس القرص.

        وهذا نفس الداء الذي دفعتُ ثمنه اليوم: مانيفستٌ صار صفر بايت فحُذفت
        الذرّة، ولا شيء قال ذلك حتى سُئل.
        """
        connection = self.connect()
        try:
            present = {row[1] for row in connection.execute("PRAGMA table_info(cards)")}
        finally:
            connection.close()
        return [name for name in _CARD_COLUMNS if name not in present]

    # ------------------------------------------------------------------ فتح

    def open_card(self, symbol: str, account_id: str, broker: str, side: str,
                  at: float | None = None,
                  body: dict[str, Any] | None = None) -> tuple[int, bool]:
        """يفتح بطاقةً للرمز، أو يعيد رقم البطاقة الحيّة القائمة.

        يعيد ``(رقم البطاقة، أَجديدةٌ هي)``. الفهرس الفريد هو الحكم: محاولةُ
        فتح ثانيةٍ على رمزٍ له بطاقةٌ حيّة تُرفض في المحرّك، فيُقرأ القائم
        ويُعاد. ولا يُرمى استثناء — «بطاقةٌ قائمة» جوابٌ صحيح لا عطل.
        """
        moment = time.time() if at is None else float(at)
        connection = self.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute(
                "INSERT OR IGNORE INTO cards "
                "(symbol,account_id,broker,state,side,opened_at,updated_at,body_json) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (symbol, account_id or "", broker or "", STATE_OPEN, side or None,
                 moment, moment, _dumps(body or {})))
            if cursor.rowcount:
                card_no = int(cursor.lastrowid)
                connection.commit()
                return card_no, True
            connection.rollback()
            row = connection.execute(
                "SELECT card_no FROM cards WHERE symbol=? AND state IN (%s)" % _LIVE_SQL,
                (symbol,)).fetchone()
            if row is None:
                # سباقٌ نادر: البطاقة الحيّة أُغلقت بين المحاولتين.
                return self.open_card(symbol, account_id, broker, side, moment, body)
            return int(row[0]), False
        finally:
            connection.close()

    # ---------------------------------------------------------------- قراءة

    def live_card(self, symbol: str) -> dict[str, Any] | None:
        connection = self.connect()
        try:
            return _row(connection.execute(
                _SELECT + "WHERE symbol=? AND state IN (%s)" % _LIVE_SQL,
                (symbol,)).fetchone())
        finally:
            connection.close()

    def live_cards(self) -> list[dict[str, Any]]:
        connection = self.connect()
        try:
            rows = connection.execute(
                _SELECT + "WHERE state IN (%s) ORDER BY card_no" % _LIVE_SQL).fetchall()
        finally:
            connection.close()
        return [card for card in (_row(row) for row in rows) if card]

    def card(self, card_no: int) -> dict[str, Any] | None:
        connection = self.connect()
        try:
            return _row(connection.execute(
                _SELECT + "WHERE card_no=?", (int(card_no),)).fetchone())
        finally:
            connection.close()

    def writes(self, card_no: int) -> list[dict[str, Any]]:
        connection = self.connect()
        try:
            rows = connection.execute(
                "SELECT author,field,value_json,first_at,last_at,hits FROM card_writes "
                "WHERE card_no=? ORDER BY first_at", (int(card_no),)).fetchall()
        finally:
            connection.close()
        out = []
        for author, field, raw, first_at, last_at, hits in rows:
            try:
                value = json.loads(raw) if raw is not None else None
            except (TypeError, ValueError):
                value = raw
            out.append({"author": author, "field": field, "value": value,
                        "first_at": first_at, "last_at": last_at, "hits": hits})
        return out

    # ---------------------------------------------------------------- كتابة

    def update(self, card_no: int, fields: dict[str, Any] | None = None,
               body: dict[str, Any] | None = None, at: float | None = None) -> bool:
        """يعدّل حقول البطاقة ويدمج جسمها. الحقل غير المعروف يُهمَل معلنًا."""
        moment = time.time() if at is None else float(at)
        clean = {k: v for k, v in (fields or {}).items() if k in WRITABLE}
        connection = self.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            if body:
                row = connection.execute(
                    "SELECT body_json FROM cards WHERE card_no=?", (int(card_no),)).fetchone()
                if row is None:
                    connection.rollback()
                    return False
                try:
                    merged = json.loads(row[0])
                except (TypeError, ValueError):
                    merged = {}
                if not isinstance(merged, dict):
                    merged = {}
                merged.update(body)
                clean["body_json"] = _dumps(merged)
            clean["updated_at"] = moment
            assignments = ",".join("%s=?" % name for name in clean)
            # 🔴 ٢٠٢٦-٠٩-١٩، بعد الإقلاع — كان ختمُ الإرسال في `set_state`
            # وحدها، **و٤٦٥ لا يمرّ بها**: ينادي `_update` بـ`{"state":
            # "DISPATCHED"}` مباشرةً. فالبطاقة ٢٩ خرجت `DISPATCHED` وختمُها
            # فارغ، ولولا `COALESCE` في `expire` لعادت الجثّة من جديد.
            #
            # فالختم ينتقل إلى **المختنق الذي تمرّ منه كلّ كتابة**، لا إلى
            # بابٍ من أبوابه. و`COALESCE` في الإسناد تجعله **يُكتب مرّة**:
            # نداءٌ ثانٍ بالحالة نفسها لا يحرّك الساعة، وإلّا عاد العيب
            # الذي أُصلح — عمرٌ يتجدّد فلا يشيخ.
            if clean.get("state") == STATE_DISPATCHED:
                assignments += ",dispatched_at=COALESCE(dispatched_at,?)"
                cursor = connection.execute(
                    "UPDATE cards SET %s WHERE card_no=?" % assignments,
                    (*clean.values(), moment, int(card_no)))
                connection.commit()
                return cursor.rowcount > 0
            cursor = connection.execute(
                "UPDATE cards SET %s WHERE card_no=?" % assignments,
                (*clean.values(), int(card_no)))
            connection.commit()
            return cursor.rowcount > 0
        finally:
            connection.close()

    def note(self, card_no: int, author: str, field: str, value: Any,
             at: float | None = None) -> None:
        """يسجّل كتابةً: أوّل مرّة صفٌّ جديد، وما بعدها عدّادٌ وقيمةٌ أحدث."""
        moment = time.time() if at is None else float(at)
        payload = _dumps(value)
        connection = self.connect()
        try:
            connection.execute(
                "INSERT INTO card_writes (card_no,author,field,value_json,first_at,last_at,hits) "
                "VALUES (?,?,?,?,?,?,1) "
                "ON CONFLICT(card_no,author,field) DO UPDATE SET "
                "value_json=excluded.value_json, last_at=excluded.last_at, hits=hits+1",
                (int(card_no), str(author), str(field), payload, moment, moment))
            connection.commit()
        finally:
            connection.close()

    def notes(self, rows: Iterable[tuple[int, str, str, Any, float]]) -> int:
        """دفعةٌ من الكتابات في معاملةٍ واحدة — أرخص من نداءٍ لكلّ حقل."""
        batch = [(int(c), str(a), str(f), _dumps(v), float(t), float(t))
                 for c, a, f, v, t in rows]
        if not batch:
            return 0
        connection = self.connect()
        try:
            connection.executemany(
                "INSERT INTO card_writes (card_no,author,field,value_json,first_at,last_at,hits) "
                "VALUES (?,?,?,?,?,?,1) "
                "ON CONFLICT(card_no,author,field) DO UPDATE SET "
                "value_json=excluded.value_json, last_at=excluded.last_at, hits=hits+1",
                batch)
            connection.commit()
            return len(batch)
        finally:
            connection.close()

    def set_state(self, card_no: int, state: str, at: float | None = None,
                  **fields: Any) -> bool:
        moment = time.time() if at is None else float(at)
        if state in FINAL_STATES:
            fields.setdefault("closed_at", moment)
        fields["state"] = state
        return self.update(card_no, fields, at=moment)

    def expire(self, before_open: float, before_dispatch: float) -> list[int]:
        """يُنهي البطاقات البائتة ويحرّر رموزها — ``FILLED`` لا تنتهي بعمر.

        بطاقةٌ مفتوحةٌ لم تُرسَل تحبس رمزها إلى الأبد لو تُركت، وصفقةٌ منفَّذة
        لا يُنهيها الوقت بل نتيجتها. فالعمر يُطبَّق على ``OPEN`` و``DISPATCHED``
        وحدهما، وبعتبتين مختلفتين لأنّ انتظار التنفيذ غير انتظار القرار.
        """
        moment = time.time()
        connection = self.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            # 🔴 ٢٠٢٦-٠٩-١٩ — كان الشرطان كلاهما على `updated_at`، **فبطاقةٌ
            # مرسَلةٌ بلا تذكرة لا تشيخ أبدًا**: متتبّع أقصى حركةٍ ومعاكسها
            # يكتب فيها مع كلّ تِكّة فيُجدّد `updated_at`، والعيار (ربع ساعة)
            # لا يُبلَغ. ومقيس: البطاقة ٢٨ بقيت `DISPATCHED` **ثلاث عشرة
            # ساعة** بلا تذكرة، وآخرُ كتابةٍ فيها قبل دقيقتين.
            #
            # وثمنُه أنّها تحبس رمزها: الفهرس الفريد يمنع بطاقةً ثانية حيّة
            # على الرمز، فكلّ قرارٍ جديد على بتكوين **يُعاد إلى تلك الجثّة**
            # (`reused=53,264`) بدل أن يفتح بطاقته.
            #
            # فالعمر يُقاس من `dispatched_at` — ختمٌ يُكتب مرّةً عند الإرسال.
            # و`COALESCE` إلى `opened_at` للصفوف القديمة التي سبقت العمود:
            # بطاقةٌ بلا ختمٍ هي بطاقةٌ من قبل الإصلاح، وعمرها من فتحها
            # أصدقُ من «الآن».
            rows = connection.execute(
                "SELECT card_no FROM cards WHERE (state=? AND updated_at<?) "
                "OR (state=? AND COALESCE(dispatched_at,opened_at)<?)",
                (STATE_OPEN, before_open, STATE_DISPATCHED, before_dispatch)).fetchall()
            expired = [int(row[0]) for row in rows]
            if expired:
                connection.executemany(
                    "UPDATE cards SET state=?,closed_at=?,updated_at=? WHERE card_no=?",
                    [(STATE_EXPIRED, moment, moment, card_no) for card_no in expired])
            connection.commit()
            return expired
        finally:
            connection.close()

    def counts(self) -> dict[str, int]:
        connection = self.connect()
        try:
            totals = {state: int(count) for state, count in connection.execute(
                "SELECT state,count(*) FROM cards GROUP BY state")}
            totals["total"] = int(connection.execute(
                "SELECT count(*) FROM cards").fetchone()[0])
            totals["writes"] = int(connection.execute(
                "SELECT count(*) FROM card_writes").fetchone()[0])
            totals["last_no"] = int(connection.execute(
                "SELECT coalesce(max(card_no),0) FROM cards").fetchone()[0])
            return totals
        finally:
            connection.close()


_SCALE_PATH = (os.path.dirname(os.path.abspath(__file__)) + os.sep + ".." + os.sep
               + "forex_runtime" + os.sep + "var" + os.sep + "telemetry"
               + os.sep + "analysis_scale.json")
_SCALE_CACHE: dict[str, Any] = {"mtime": None, "table": {}, "checked": None, "path": None}
#: ٢٠٢٦-٠٩-٢٥ (ختم المالك «Nq صلح كل امور»): بصمةُ ملفّ العيار تُفحص مرّةً كلّ
#: هذه المدّة لا مع كلّ نداء. كان `os.path.getmtime` يجري مع كلّ إعدادٍ على حلقة
#: المنصّة، ومِرقاب الحلقة وجده في 7.5٪ من عيّنات تجمّدٍ والقرص مشبَع
#: (`shared/trade_card.py:449`). والعيار ملفُّ قياسٍ يتبدّل نادرًا، فثوانٍ من
#: التأخّر في رؤية جديده لا تغيّر حكمًا.
_SCALE_RECHECK_S = 5.0


def movement_floor(symbol: Any) -> float | None:
    """الحركة الوسيطة المقيسة لهذا الرمز — أرضيّةُ الوقف الطبيعيّة.

    وقفٌ دون حركة الرمز الوسيطة يقع **داخل الضجيج**: يُضرب قبل أن تتحرّك
    الفكرة، ونسبتُه تبدو ممتازة لأنّ مقامها صغير لا لأنّ هدفه قريب. مقيس
    ٢٠٢٦-٠٩-١٨: الأرضيّة السارية هي السبريد وحده — ٥ دولارات على بتكوين
    بينما حركته ٦٩٫٣، أي **أصغر بثلاثة عشر ضعفًا**.

    والقراءة إعلانٌ لا حجب: تُكتب في البطاقة ليُعرف الثمن قبل أن يُبدَّل
    العيار — فقد خنقتُ هذا القسم مرّةً بعتبةٍ رفعتُها بلا قياسِ أثرها.
    """
    key = str(symbol or "").strip().upper()
    if not key:
        return None
    now = time.monotonic()
    checked = _SCALE_CACHE["checked"]
    if (checked is None or now - checked >= _SCALE_RECHECK_S
            or _SCALE_CACHE["path"] != _SCALE_PATH):
        _SCALE_CACHE["checked"] = now
        _SCALE_CACHE["path"] = _SCALE_PATH
        try:
            stamp = os.path.getmtime(_SCALE_PATH)
        except OSError:
            stamp = None
        if stamp is None:
            # الملفّ غائب: لا أرضيّة — كما كان يُعاد `None` عند تعذّر البصمة.
            _SCALE_CACHE["table"] = {}
            _SCALE_CACHE["mtime"] = None
        elif _SCALE_CACHE["mtime"] != stamp:
            try:
                with open(_SCALE_PATH, encoding="utf-8") as handle:
                    rows = json.load(handle).get("symbols")
                _SCALE_CACHE["table"] = rows if isinstance(rows, dict) else {}
            except (OSError, ValueError):
                _SCALE_CACHE["table"] = {}
            _SCALE_CACHE["mtime"] = stamp
    row = _SCALE_CACHE["table"].get(key)
    if not isinstance(row, dict):
        return None
    try:
        movement = float(row.get("movement"))
    except (TypeError, ValueError):
        return None
    return movement if movement > 0 else None


def excursion(entry: float | None, stop_points: float | None, side: str,
              price: float | None, peak: float | None,
              worst: float | None) -> dict[str, float] | None:
    """أقصى ما بلغته الصفقة وأسوأ ما بلغته — بالنقاط وبمضاعف المخاطرة.

    تحذير قسم ٣٥٠-٣٩٩ (٢٠٢٦-٠٩-١٨): الحكم المشتقّ من الربح المحقَّق ملوَّث —
    **٤ من ٤٣ صفقة معكوسة التسمية، و١٢ من ٢٨ خاسرة حُرِّك وقفها** بعد أن
    بلغت ربحًا. فبطاقةٌ تحمل الخاتمة وحدها تورّث التلوّث، ومن تعلّم منها تعلّم
    كذبًا. لذلك تحمل البطاقة **الذروة والحضيض** لا النهاية فقط.

    ولا تُخترع قيمة: بلا سعرٍ أو بلا مخاطرةٍ موجبة يعود ``None``.
    """
    if entry is None or price is None or not stop_points or stop_points <= 0:
        return None
    move = (float(price) - float(entry)) * (1.0 if side == "buy" else -1.0)
    best = move if peak is None else max(float(peak), move)
    bad = move if worst is None else min(float(worst), move)
    return {"peak_points": round(best, 6), "worst_points": round(bad, 6),
            "peak_r": round(best / float(stop_points), 4),
            "worst_r": round(bad / float(stop_points), 4)}


def geometry_of(entry: float | None, stop: float | None,
                target: float | None) -> str:
    """الجهة التي تنطق بها المستويات نفسها — لا التي كُتبت عليها.

    شراءٌ وقفُه تحت دخوله وهدفُه فوقه، وبيعٌ بالعكس. وما عدا ذلك مشوَّه.
    """
    if entry is None or stop is None:
        return ""
    if target is None:
        return "buy" if stop < entry else "sell" if stop > entry else "flat"
    if stop < entry < target:
        return "buy"
    if target < entry < stop:
        return "sell"
    return "broken"


def levels(entry: float | None, stop: float | None, target: float | None,
           spread: float | None = None, side: str = "") -> dict[str, Any]:
    """يشتقّ المسافة والنسبة من ثلاثة أسعار — بالنقاط والمئويّة، بلا مال.

    **نصفُ السبريد يُضاف إلى المخاطرة ويُطرح من العائد** — لأنّ المرجع الذي
    تبني عليه الاستراتيجيّة هو `mid` لا `ask`. قِسته مع قسم ٥٠٠-٥٤٩ على ١٤٦
    أمرًا منفَّذًا على بتكوين: فرقُ التنفيذ عن المرجع **شراءً ‎+2.99‎ وبيعًا
    ‎−2.50‎** — متماثلٌ حول الصفر بمقدار نصف سبريد، وهي بصمة `mid` قاطعة.

    فالشراء يُملأ عند ``mid + s/2`` ويخرج على العرض: الخسارة ``d + s/2``
    والربح ``t − s/2``. وكنتُ أقول إنّ السبريد داخل المسافة أصلًا — وذاك
    صحيحٌ لو كان المرجع `ask`، وهو ليس كذلك هنا. ومَن يضيفه كاملًا يضخّم
    المخاطرة بنصفه، ومَن يُسقطه يُنقصها بنصفه.

    والقسمة على صفرٍ لا تُخترع لها قيمة — تعود ``None`` معلنة.
    """
    if entry is None or stop is None:
        return {}
    price = float(entry)
    half = abs(float(spread)) / 2.0 if spread else 0.0
    risk = abs(price - float(stop)) + half
    out: dict[str, Any] = {
        "stop_points": round(risk, 6),
        "spread_points": round(abs(float(spread)), 6) if spread else None,
        "stop_pct": round(100.0 * risk / price, 6) if price else None,
    }
    shape = geometry_of(entry, stop, target)
    out["geometry"] = shape
    if target is not None:
        reward = abs(float(target) - price) - half
        out["target_points"] = round(reward, 6)
        out["target_pct"] = round(100.0 * reward / price, 6) if price else None
        # ⛔ لا نسبةَ من هندسةٍ مقلوبة. `abs` تُخرج رقمًا موجبًا من وقفٍ فوق
        # الدخول وهدفٍ تحته، فتبدو النسبة ٩٫٤ وهي بلا معنى — مقيس على
        # بطاقتَي الذهب وناسداك ٢٠٢٦-٠٩-١٨ (رآه المالك على القرص قبلي).
        # والرقم الكاذب أسوأ من الفراغ: الفراغ يُسأل عنه.
        mismatch = bool(side) and shape in ("buy", "sell") and shape != str(side).lower()
        if shape == "broken" or mismatch:
            out["rr"] = None
            out["rr_rule"] = "لا نسبة — هندسة %s" % ("مشوَّهة" if shape == "broken"
                                                     else "تخالف الجهة %s" % side)
        else:
            out["rr"] = round(reward / risk, 4) if risk > 0 else None
            out["rr_rule"] = RR_RULE
    return out
