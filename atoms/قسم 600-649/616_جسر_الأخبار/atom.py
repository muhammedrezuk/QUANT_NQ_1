from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import time
from pathlib import Path
from typing import Any

from core.contracts.atom import AtomBase, AtomContext, HealthState, HealthStatus

ATOM_VERSION = "1.10.0"
# v1.4.0 (2026-08-27, item 21/27 of the 27-atom review -- same event
# name, two conflicting shapes between 615 and 616, both publishing
# market.news by deliberate design: 615's own history (v1.0.0) records
# the owner's own decision that 615 is a parallel path alongside 616,
# not a replacement -- 108 stays untouched. This atom's own
# "symbols" convention (omit when empty, NQ seal item 22 batch A -- see
# below) turned out to be the more deliberately-reasoned of the two, so
# 615 was aligned to IT, not the reverse. "written_at" (always sent, even
# as None) was the one field 615 had more deliberately -- aligned this
# atom to that. Also namespaced "id" by atom id -- 615 and 616 read
# separate databases with independent row-id sequences, and the only
# confirmed consumer (108) dedups by this field; an id collision across
# the two sources would silently drop a real, distinct headline as a
# false duplicate.

EVENT_PULSE = "SYS_SECOND"
EVENT_NEWS = "market.news"
EVENT_CALENDAR = "market.calendar"

TABLE_NEWS = "news"
TABLE_CALENDAR = "calendar"
# ٢٠٢٦-٠٩-١٦ (أمر المالك «صلح» بختم `NQ`، ومصدره forexfactory.com): جدولٌ
# ثانٍ يكتبه جالب ForexFactory (`QUANT_NQ_NEWS/app/ff_calendar.py`) بنفس
# الأعمدة. يُفضَّل حين يوجد ويكون طازجًا، وإلّا فجدول المنصّة كما كان.
#
# ولماذا فُضِّل — مقيس على يومٍ واحد، أحداث USD:
#
#     الحدث                       المنصّة    ForexFactory
#     Retail Sales m/m             HIGH        Medium
#     Core Retail Sales m/m        HIGH        Medium
#     Crude Oil Inventories        HIGH        Low
#     FOMC Statement               MEDIUM      High
#     FOMC Economic Projections    MEDIUM      High
#
# خمسة من سبعة مختلفة، **واثنان مقلوبان**: مخزون النفط يُرفع إلى الأحمر
# فيُغلق التداول ساعةً على الذهب وناسداك وبتكوين بلا صلة، وبيان الفيدراليّ
# وتوقّعاته يُخفضان وهما أعنف ما يحرّكها. والعدد مضخَّم: **٣٢ صفًّا مقابل
# ١١** لأنّ المنصّة تفكّك الحدث الواحد إلى شهريّ وسنويّ وباستثناء السيارات.
TABLE_CALENDAR_FF = "calendar_ff"
#: جالبٌ متوقّفٌ لا يُبقي تقويمًا بائتًا حاكمًا: بعد هذا العمر يعود المصدر
#: إلى جدول المنصّة. أسبوعٌ وثلث — فالملفّ أسبوعيّ ويُجلب مرارًا خلاله.
_FF_MAX_AGE_S = 8 * 24 * 3600.0

# Owner item 22 / batch A (ruling Q7): symbols and impact_level ride along
# only when the bridge table really has those columns. The schema is checked
# at read time and the SELECT is built from named columns that exist — a
# missing column degrades to an absent field, never to a crash and never to
# an invented value.
_NEWS_COLUMNS = ("id", "headline", "link", "source", "sentiment_score",
                 "impact_level", "symbols", "published_at", "written_at")
_SQL_NEWS_TAIL = " FROM news WHERE id > ? ORDER BY id LIMIT ?"
#: ذيلُ البداية الدافئة — أحدثُ `N` بالمعرّف مهما تباعدت الأرقام.
#: v1.8.0 كانت تُزيح نقطةَ البدء إلى `last_news_id - N` بالاستعلام نفسه،
#: وذلك يفترض معرّفاتٍ متلاصقة. والمقيس حيًّا أنّها متباعدة (34051 ثمّ
#: 33491 ثمّ 33481)، فطلبتْ خمسةً ونشرت **واحدًا** — والتعليق يقول خمسة.
#: كفى الواحدُ لإيقاظ ١٠٨، ولم يكفِ لِما ادّعاه الكود. فالذيل صريح الآن.
_SQL_NEWS_WARM_TAIL = " FROM news ORDER BY id DESC LIMIT ?"

#: كم خبرًا يُعاد نشرُه مرّةً واحدة عند الإقلاع. المؤشّر محفوظٌ على القرص،
#: فبعد إقلاعٍ يقع والمؤشّرُ عند قمّة الجدول لا يُنشر شيءٌ إطلاقًا حتى يصل
#: خبرٌ جديد — وقد يتأخّر ساعات. ومستهلكُنا ١٠٨ يقول `UNAVAILABLE_NO_NEWS_SOURCE`
#: على شرط `self._received == 0`، أي «لم يصلني شيء منذ الإقلاع» لا «لا مصدر».
#: مقيس ٢٠٢٦-٠٩-١٩: `last_news_id = 34051` وهو أعلى `id` في الجدول بالضبط،
#: و`news=0`، و١٠٨ `DEGRADED` بينما الجدول فيه ٦٣٢ خبرًا وآخرُها من ساعة.
#: خمسةٌ تعطي صورةً لا خبرًا واحدًا، ولا تُغرق مستهلكًا يفضّ التكرار بالمعرّف.
_WARM_START_NEWS = 5
# Owner stamp 2026-08-25: ascending order read the OLDEST rows, and the bridge
# table keeps months of history (measured: 815 rows, 736 past, 79 future). The
# oldest 500 held ZERO future events, so 109 pruned every one of them and the
# economic calendar reached the system empty. Descending takes the newest rows,
# which always contain every future event. No clock is read here -- ordering
# alone fixes it, and rule 13 stays intact.
_SQL_CALENDAR = ("SELECT id, title, country, currency, impact_level, "
                 "scheduled_at, actual, forecast, previous, written_at "
                 "FROM calendar ORDER BY scheduled_at DESC LIMIT ?")
_SQL_CALENDAR_FF = ("SELECT id, title, country, currency, impact_level, "
                    "scheduled_at, actual, forecast, previous, written_at "
                    "FROM calendar_ff ORDER BY scheduled_at DESC LIMIT ?")
# ٢٠٢٦-٠٩-١٩: يُقرأ الطابعان معًا. `written_at` يقول «أحيٌّ الجالب؟»
# و`scheduled_at` يقول «أفي هذا التقويم مستقبل؟» — والثاني هو السؤال.
_SQL_FF_FRESH = "SELECT MAX(written_at), MAX(scheduled_at) FROM calendar_ff"

_BUSY_TIMEOUT_MS = 3000
_CONNECT_TIMEOUT_S = 5.0

IMPACT_UNKNOWN = "UNKNOWN"
SYMBOLS_UNKNOWN = "UNKNOWN"
SYMBOL_SEPARATOR = ","

REASON_NOT_STARTED = "NOT_STARTED"
REASON_UNREADABLE = "BRIDGE_UNREADABLE"
REASON_NO_DATA = "NO_ROWS_YET"

# ── v1.5.0: Persistent consumption cursor ──────────────────────
# 616 reads a bridge database that accumulates historical rows.
# Without persistence, every restart re-reads from id=0, re-broadcasting
# all historical rows to the EventBus. This is wrong: old data should
# NOT be re-published on startup. The cursor tracks the last consumed
# row id to disk so consecutive startups only see genuinely new rows.
# Historical rows remain in the bridge database (never deleted) for
# audit; they are simply not re-emitted.


def _state_path_for(bridge_db: str) -> str:
    """Derive a state file path next to the bridge db."""
    p = Path(bridge_db)
    return str(p.parent / (p.stem + "_616_cursor.json"))


#: مؤشّرٌ لا يُقرأ. ليس صفرًا — الصفر يعني «لم أستهلك شيئًا» وهو ادّعاء.
CURSOR_UNREADABLE = -1


def _load_cursor(state_path: str) -> int:
    """آخرُ خبرٍ استُهلك. صفرٌ إن لم يوجد الملفّ، و-1 إن وُجد ولم يُقرأ.

    ٢٠٢٦-٠٩-٢٣ (تدقيق المالك الخارجيّ): كان **كلُّ** فشلٍ يُرجع صفرًا —
    الغيابُ والتلفُ سواء. والفرق بينهما ثقيل: الغياب يعني أوّل تشغيلٍ
    فالصفر صادق؛ أمّا ملفٌّ موجودٌ تالف فصفرُه **ادّعاءٌ بأنّنا لم ننشر
    شيئًا قطّ**، فيُعاد نشرُ الجدول كلِّه (٦٣٢ خبرًا) على أنّه جديد —
    ١٠٨ ومن خلفه يقرؤون خبرًا عمرُه شهرٌ على أنّه الآن.

    وهذا هو النمط نفسه الذي سمّاه التدقيق: **عدمُ معرفة الحالة يتحوّل
    إلى نتيجةٍ تبدو سليمة**.
    """
    if not Path(state_path).exists():
        return 0
    try:
        data = json.loads(Path(state_path).read_text())
        return int(data["last_news_id"])
    except (OSError, json.JSONDecodeError, ValueError, KeyError, TypeError):
        return CURSOR_UNREADABLE


def _save_cursor(state_path: str, last_news_id: int) -> None:
    """Persist the last consumed news id."""
    try:
        Path(state_path).write_text(json.dumps({
            "last_news_id": last_news_id,
            "updated_at": time.time(),
        }))
    except OSError:
        pass  # Best-effort; cursor resets to 0 on next restart if lost


def _to_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _resolve_db(configured: str) -> str:
    """مرسى الجسر — من البيئة أوّلًا، ثمّ المانيفست، ومتغيّرات البيئة تُوسَّع.

    ٢٠٢٦-٠٩-٢٣ (ختم NQ): كان المانيفست يحمل المسار المطلق إلى جهاز المالك
    باسمه (`C:/Users/NQ/...`) — أي أنّ اسمَه وجهازَه محفوران في عقد ستّ
    ذرّات. نقلُ المشروع إلى مستخدمٍ آخر كان يُسقطها صامتةً. صار الاحتياطيّ
    `%APPDATA%` ثمّ `MetaQuotes/Terminal/Common/Files` — يُوسَّع هنا فيصحّ
    على أيّ جهاز.

    و`NQ_BRIDGE_DB` يبقى مقدَّمًا (يضبطه `governance/app.py` من مكانٍ واحد)،
    فهذا احتياطيٌّ لا طريقٌ أوّل.
    """
    override = os.path.expandvars(os.environ.get("NQ_BRIDGE_DB", "").strip())
    if override:
        return override
    return os.path.expandvars(configured)


def _bridge_connect(db_path: str) -> sqlite3.Connection:
    connection = sqlite3.connect("file:%s?mode=ro" % db_path, uri=True,
                                 timeout=_CONNECT_TIMEOUT_S)
    connection.execute("PRAGMA busy_timeout=%d" % _BUSY_TIMEOUT_MS)
    connection.row_factory = sqlite3.Row
    return connection


def _table_exists(connection: sqlite3.Connection, name: str) -> bool:
    row = connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (name,)).fetchone()
    return row is not None


def _table_columns(connection: sqlite3.Connection, name: str) -> set[str]:
    rows = connection.execute("PRAGMA table_info(%s)" % name).fetchall()
    return {str(row["name"]) for row in rows}


def _news_select(available: set[str]) -> str | None:
    """SELECT built from the columns the table actually has (named, ordered).

    id is the paging cursor: without it no safe incremental read exists, so
    the read is skipped entirely rather than guessed.
    """
    selected = [column for column in _NEWS_COLUMNS if column in available]
    if "id" not in selected:
        return None
    return "SELECT %s%s" % (", ".join(selected), _SQL_NEWS_TAIL)


def _news_select_warm(available: set[str]) -> str | None:
    """الأعمدة نفسها والترتيب نفسه — ويختلف الذيل وحده."""
    selected = [column for column in _NEWS_COLUMNS if column in available]
    if "id" not in selected:
        return None
    return "SELECT %s%s" % (", ".join(selected), _SQL_NEWS_WARM_TAIL)


def _symbols_of(raw: Any) -> list[str]:
    """Unified names separated by commas, or the literal UNKNOWN.

    Unknown or empty yields an empty list and the caller then omits the
    field: absence of knowledge is not a claim of "no symbols".
    """
    text = str(raw or "").strip()
    if not text or text == SYMBOLS_UNKNOWN:
        return []
    return [part.strip() for part in text.split(SYMBOL_SEPARATOR) if part.strip()]


class Atom(AtomBase):
    def __init__(self) -> None:
        self._context: AtomContext | None = None
        self._running = False
        self._db_path = ""
        self._poll_interval_s = 0.0
        self._batch_limit = 0
        self._reading = False
        self._read_task: asyncio.Task | None = None
        self._now = 0.0
        self._last_read_at = 0.0
        self._last_news_id = 0
        self._seen_events: dict[str, float] = {}
        self._last_error = ""
        self._news_published = 0
        self._calendar_published = 0
        self._reads = 0
        # أيّ جدولٍ حكم آخر قراءة — يُعلَن في الشارة. مصدرٌ يتبدّل بصمت
        # أسوأ من مصدرٍ خاطئ: لا يُعرف بأيّ تصنيفٍ حُجبت الصفقة.
        self._calendar_source = ""
        # v1.5.0: persistent cursor
        self._state_path = ""
        self._cursor_restored = False
        # يُرفع عند التشغيل ويُخفض بعد أوّل قراءة — مرّةً واحدة لكلّ إقلاع.
        self._warm_pending = False
        self._warm_published = 0
        # مؤشّرٌ وُجد ولم يُقرأ — يُعلَن ولا يُبتلع.
        self._cursor_unreadable = False
        #: آخر مؤشّرٍ كُتب على القرص — لا يُعاد كتابةُ ما لم يتغيّر.
        self._saved_news_id = 0

    async def initialize(self, context: AtomContext) -> None:
        self._context = context
        cfg = context.config
        self._db_path = _resolve_db(str(cfg["db_path"]))
        self._poll_interval_s = float(cfg["poll_interval_s"])
        self._batch_limit = int(cfg["batch_limit"])
        # v1.5.0: restore persistent cursor — prevents re-broadcast of
        # historical rows on consecutive startups.
        self._state_path = _state_path_for(self._db_path)
        restored = _load_cursor(self._state_path)
        if restored == CURSOR_UNREADABLE:
            # مؤشّرٌ تالف: لا يُبدأ من صفرٍ فيُغرَق المستهلك بتاريخٍ كامل
            # على أنّه الآن. يُرفع العلَم، ويُضبط المؤشّر عند قمّة الجدول
            # في أوّل قراءة — فيُفقد ما بين التلف والإقلاع، ولا يُكذَب
            # على أحد. والبداية الدافئة تعطي المستهلك صورةً على كلّ حال.
            self._cursor_unreadable = True
        elif restored > 0:
            self._last_news_id = restored
            self._saved_news_id = restored
            self._cursor_restored = True
        context.subscribe(EVENT_PULSE, self._on_pulse)

    async def start(self) -> None:
        self._running = True
        # بدايةٌ دافئة لهذا الإقلاع وحده — تُستهلك في أوّل قراءة.
        self._warm_pending = True

    async def stop(self) -> None:
        self._running = False
        task = self._read_task
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._read_task = None
        self._reading = False

    async def shutdown(self) -> None:
        await self.stop()

    async def _on_pulse(self, payload: dict[str, Any]) -> None:
        if not self._running or self._context is None or not isinstance(payload, dict):
            return
        now = _to_float(payload.get("official_time"))
        if now is None:
            return
        self._now = now
        if self._reading or (now - self._last_read_at) < self._poll_interval_s:
            return
        self._last_read_at = now
        self._reading = True
        self._read_task = asyncio.create_task(self._read_all())

    def _read_rows(self, warm: bool = False) -> tuple[list[dict], list[dict]]:
        connection = _bridge_connect(self._db_path)
        try:
            news: list[dict] = []
            if _table_exists(connection, TABLE_NEWS):
                select = _news_select(_table_columns(connection, TABLE_NEWS))
                if warm:
                    # أحدثُ `N` بالمعرّف، ثمّ تُقلب لتخرج بترتيب النشر
                    # المعتاد (الأقدم أوّلًا) — فالمستهلك يرى التسلسل نفسه.
                    warm_select = _news_select_warm(
                        _table_columns(connection, TABLE_NEWS))
                    if warm_select is not None:
                        news = [dict(r) for r in connection.execute(
                            warm_select, (_WARM_START_NEWS,)).fetchall()][::-1]
                elif select is not None:
                    news = [dict(r) for r in connection.execute(
                        select, (self._last_news_id, self._batch_limit)).fetchall()]
            calendar: list[dict] = []
            # ForexFactory أوّلًا حين يوجد وهو طازج، وإلّا جدول المنصّة.
            # والطزاجة شرطٌ لا زينة: جالبٌ متوقّف يعني تقويمًا يشيخ، وتقويمٌ
            # شائخ يحجب أحداثًا مضت ويفتح على أحداث لم يرها — وهو أسوأ من
            # تصنيفٍ مبالِغ. فالسقوط إلى المنصّة عند البيات مقصود ومعلَن.
            if _table_exists(connection, TABLE_CALENDAR_FF):
                row = connection.execute(_SQL_FF_FRESH).fetchone()
                newest = row[0] if row else None
                horizon = row[1] if row and len(row) > 1 else None
                now = time.time()
                written_ok = (isinstance(newest, (int, float))
                              and now - float(newest) <= _FF_MAX_AGE_S)
                # ٢٠٢٦-٠٩-١٩ — **الحارس كان يقيس السؤال الخطأ.**
                # `written_at` وحده يجيب «أحيٌّ الجالب؟»، والجالبُ كان حيًّا
                # فعلًا (آخر كتابة قبل ثماني دقائق) بينما **كلّ أحداث**
                # `calendar_ff` ماضية (آخرها 09-19 13:15 والساعة 15:45).
                # فاختار ٦١٦ جدولًا بلا مستقبل، فأعلن ١٠٩ «أفق التقويم
                # انتهى» ⟵ `allow_new_entries: false` ⟵ حجب ٤٥٤ ألفين
                # وتسعمئة وثلاثة وعشرين قرارًا ⟵ **صفر صفقة في المنصّة**.
                # والجدول الآخر `calendar` فيه اثنا عشر حدثًا أمامنا.
                #
                # فالشرط أفقٌ لا كتابة: يُقدَّم ForexFactory حين يكون حيًّا
                # **ويحمل حدثًا واحدًا على الأقلّ أمامنا**. وحين ينقضي أفقُه
                # يسقط إلى جدول المنصّة — وهو المقصود أصلًا في التعليق
                # أعلاه، لكنّ المقياس لم يكن يقيسه.
                horizon_ok = (isinstance(horizon, (int, float))
                              and float(horizon) > now)
                fresh = written_ok and horizon_ok
                if fresh:
                    calendar = [dict(r) for r in connection.execute(
                        _SQL_CALENDAR_FF, (self._batch_limit,)).fetchall()]
                    self._calendar_source = TABLE_CALENDAR_FF
            if not calendar and _table_exists(connection, TABLE_CALENDAR):
                calendar = [dict(r) for r in connection.execute(
                    _SQL_CALENDAR, (self._batch_limit,)).fetchall()]
                self._calendar_source = TABLE_CALENDAR
            return news, calendar
        finally:
            connection.close()

    async def _read_all(self) -> None:
        try:
            if self._context is None:
                return
            try:
                news, calendar = await asyncio.to_thread(self._read_rows)
            except sqlite3.Error as exc:
                self._last_error = str(exc)
                return
            self._last_error = ""
            self._reads += 1
            for row in news:
                await self._emit_news(row)
            # لا تُعاد إلّا إذا لم يأتِ جديد: وجودُ خبرٍ جديد يعني أنّ
            # المستهلك سيُوقَظ على كلّ حال، فالإعادة عندئذٍ تكرارٌ بلا سبب.
            if self._warm_pending:
                self._warm_pending = False
                if self._cursor_unreadable and self._last_news_id == 0:
                    # قمّةُ الجدول تصير نقطةَ البدء: لا تاريخَ يُعاد نشرُه.
                    try:
                        top, _ = await asyncio.to_thread(self._read_rows, True)
                    except sqlite3.Error:
                        top = []
                    for row in top:
                        rid = row.get("id")
                        if isinstance(rid, int) and rid > self._last_news_id:
                            self._last_news_id = rid
                if not news:
                    try:
                        warm, _ = await asyncio.to_thread(self._read_rows, True)
                    except sqlite3.Error:
                        warm = []
                    for row in warm:
                        await self._emit_news(row)
                        self._warm_published += 1
            for row in calendar:
                await self._emit_calendar(row)
            # v1.5.0: persist cursor after successful batch
            # 🔴 ٢٠٢٦-٠٩-٢٥ (ختم المالك «Nq كل إصلاحات») — كان يُكتب بعد كلّ قراءة ولو لم
            # يتغيّر، وعلى خيط الحلقة: مِرقاب الحلقة وجده 6.39٪ من زمن التجمّد
            # (`write_text` هنا). الآن حين يتغيّر وحده، وفي خيطٍ لا في الحلقة.
            if self._last_news_id > 0 and self._last_news_id != self._saved_news_id:
                await asyncio.to_thread(_save_cursor, self._state_path, self._last_news_id)
                self._saved_news_id = self._last_news_id
        finally:
            self._reading = False

    async def _emit_news(self, row: dict[str, Any]) -> None:
        if self._context is None:
            return
        row_id = row.get("id")
        if isinstance(row_id, int) and row_id > self._last_news_id:
            self._last_news_id = row_id
        # v1.4.0: published "id" is namespaced by atom -- 615 reads a
        # separate database with its own independent row-id sequence, and
        # the only confirmed consumer (108) dedups by this field.
        published_id = "616:%s" % row_id if row_id is not None else None
        published_at = _to_float(row.get("published_at"))
        body: dict[str, Any] = {
            "id": published_id, "headline": row.get("headline"), "link": row.get("link"),
            "source": row.get("source"),
            "sentiment_score": _to_float(row.get("sentiment_score")),
            "impact_level": row.get("impact_level") or IMPACT_UNKNOWN,
            "published_at": published_at}
        # NQ seal, item 22 batch A: absent column = absent field, not a
        # claimed empty list -- absence of knowledge is not a claim of
        # "zero symbols". Kept as the reference convention for this field
        # (item 21/27 of the 27-atom review aligned 615 to it instead).
        symbols = _symbols_of(row.get("symbols"))
        if symbols:
            body["symbols"] = symbols
        # Owner stamp 2026-08-25: written_at is the moment WE pulled the row,
        # not the moment the news happened. Substituting it for the event time
        # made a three-week-old headline arrive stamped "now", and the
        # high-impact guard is exactly a "did this happen within +/- 15
        # minutes" question. Measured on the bridge table: 20 of 214 rows carry
        # no publish time. When it is unknown the event has NO time: written_at
        # rides along under its own name so nothing is lost and nothing lies.
        body["written_at"] = _to_float(row.get("written_at"))
        if published_at is not None:
            body["timestamp"] = published_at
        self._news_published += 1
        await self._context.publish(EVENT_NEWS, body)

    async def _emit_calendar(self, row: dict[str, Any]) -> None:
        if self._context is None:
            return
        key = str(row.get("id"))
        written = _to_float(row.get("written_at")) or 0.0
        if self._seen_events.get(key) == written:
            return
        self._seen_events[key] = written
        body: dict[str, Any] = {
            "id": key, "title": row.get("title"), "country": row.get("country"),
            "currency": row.get("currency"),
            "impact_level": row.get("impact_level") or IMPACT_UNKNOWN,
            "scheduled_at": _to_float(row.get("scheduled_at")),
            "actual": row.get("actual"), "forecast": row.get("forecast"),
            "previous": row.get("previous")}
        if written:
            body["timestamp"] = written
        self._calendar_published += 1
        await self._context.publish(EVENT_CALENDAR, body)

    async def health_check(self) -> HealthStatus:
        if not self._running:
            return HealthStatus(state=HealthState.UNHEALTHY, message=REASON_NOT_STARTED)
        details = {"reads": self._reads, "news": self._news_published,
                   "warm_published": self._warm_published,
                   "calendar": self._calendar_published,
                   "last_news_id": self._last_news_id,
                   "cursor_restored": self._cursor_restored,
                   "tracked_events": len(self._seen_events)}
        if self._last_error:
            return HealthStatus(state=HealthState.DEGRADED, message=REASON_UNREADABLE,
                                details={**details, "error": self._last_error})
        if self._news_published == 0 and self._calendar_published == 0:
            return HealthStatus(state=HealthState.DEGRADED, message=REASON_NO_DATA,
                                details=details)
        return HealthStatus(
            state=HealthState.HEALTHY,
            message="news=%d calendar=%d source=%s%s%s" % (
                self._news_published, self._calendar_published,
                self._calendar_source or "-",
                (" · دافئة=%d" % self._warm_published) if self._warm_published else "",
                " · ⛔ مؤشّرٌ تالف — بُدئ من القمّة" if self._cursor_unreadable else ""),
            details=details)
