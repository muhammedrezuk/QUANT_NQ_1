from __future__ import annotations

import asyncio
import os
import sqlite3
import time
from typing import Any

from core.contracts.atom import AtomBase, AtomContext, HealthState, HealthStatus

ATOM_VERSION = "4.3.0"
# 🔴 ٢٠٢٦-٠٩-٢٥ (ختم المالك «Nq كل إصلاحات» وأمره «اقفل كل مشاكل») — القارئ يُحكم
# عليه بقراءته لا بالسوق. كان `TRADE_FEED_STALE` يُحسب من عمر **آخر صفقة**، فصار
# أصفر كلّما هدأ التداول: بعد إقلاع 10:32 والقاطع مغلق لا صفقة تُكتب، والقارئ يقرأ
# كلّ نبضةٍ بلا خطأ — فبدا «راكدًا» وهو حيّ. الآن الحكم على **آخر قراءةٍ ناجحة**
# (`_last_read_official`)، وعمرُ آخر صفقة يبقى معلومةً في الرسالة لا حكمًا.
# v4.0.3 (2026-08-27, item 19/27 of the 27-atom review -- restore() with
# no shape guard at all): every other atom's restore() at least checks
# `isinstance(state, dict)` before touching it; this one called
# state.get(...) directly with no check whatsoever -- state=None (the
# ordinary "no prior snapshot" case) crashes with AttributeError
# immediately, and a malformed pending_cost_rows item can raise mid-loop
# AFTER self._restored=True and the counters were already set, tearing
# self. Fixed the same shape as 518/520/524: non-dict state raises
# cleanly, every field parses into a local first, and self._restored is
# only flipped to True as the LAST step of a successful commit -- if
# restore() fails or is never called cleanly, start()'s existing fallback
# (_seed_pointer from the live bridge DB) still fires, which is the safe
# recovery for a bridge-reader atom.

EVENT_OUT = "platform.trade_event"
#: ما يتجاوزه فرقُ ساعة الوسيط عن ساعتنا يُعدّ ويُعلَن. خمس دقائق أوسع من
#: أيّ تأخّر قراءة معقول، وأضيق بكثير من الإزاحة المقيسة (2.2–2.9 ساعة).
_SKEW_ALERT_S = 300.0
EVENT_PULSE = "SYS_SECOND"

REASON_NOT_STARTED = "NOT_STARTED"
REASON_NO_READ = "BRIDGE_UNREADABLE"
REASON_NO_DATA = "NO_READ_YET"

_COLUMNS = ("id", "event_type", "ticket", "symbol", "side", "volume",
            "entry_price", "exit_price", "open_time", "close_time", "reason")

_BUSY_TIMEOUT_MS = 3000
_CONNECT_TIMEOUT_S = 5.0


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


def _connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=_CONNECT_TIMEOUT_S)
    conn.execute(f"PRAGMA busy_timeout={_BUSY_TIMEOUT_MS}")
    return conn


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
    return row is not None


class Atom(AtomBase):
    def __init__(self) -> None:
        self._context: AtomContext | None = None
        self._running = False
        self._task: asyncio.Task | None = None
        self._db_path = ""
        self._table = ""
        self._poll_interval_s = 0.0
        self._batch_limit = 0
        self._last_id = 0
        self._restored = False
        self._seeded_from: int | None = None
        self._last_error = ""
        self.read_count = 0
        self.published_count = 0
        self.failure_count = 0
        self.identity_rejected = 0
        self._official_time = 0.0
        self.skewed_count = 0
        self.worst_skew_s = 0.0
        self._last_data_official = 0.0
        #: آخر قراءةٍ ناجحة للجسر بساعتنا — بها يُعرف أنّ القارئ حيّ ولو لم تقع صفقة.
        self._last_read_official = 0.0
        self._max_age_s = 60.0
        self._pending_cost_rows: dict[int, str] = {}
        self._pending_cost_deadlines: dict[int, float] = {}
        self._cost_refresh_timeout_s = 60.0

    async def initialize(self, context: AtomContext) -> None:
        self._context = context
        cfg = context.config
        self._db_path = _resolve_db(str(cfg["db_path"]))
        self._table = str(cfg["table_name"])
        if self._table != "trade_events_v2":
            self._table = "trade_events_v2";self._last_error="LEGACY_TRADE_EVENTS_TABLE_FORBIDDEN"
        self._poll_interval_s = float(cfg["poll_interval_s"])
        self._batch_limit = int(cfg["batch_limit"])
        self._max_age_s = float(cfg.get("max_age_s", 60.0))
        self._cost_refresh_timeout_s = max(1.0,float(cfg.get("cost_refresh_timeout_s",60.0)))
        context.subscribe(EVENT_PULSE, self._on_pulse)

    async def _on_pulse(self, payload: dict[str, Any]) -> None:
        stamp = _to_float(payload.get("official_time")) if isinstance(payload, dict) else None
        if stamp is not None: self._official_time = stamp

    def _seed_pointer(self) -> int:
        conn = _connect(self._db_path)
        try:
            if not _table_exists(conn, self._table):
                return 0
            row = conn.execute(f"SELECT MAX(id) FROM {self._table}").fetchone()
            return int(row[0]) if row and row[0] is not None else 0
        finally:
            conn.close()

    async def start(self) -> None:
        if self._running or self._context is None:
            return
        if not self._restored:
            try:
                self._last_id = await asyncio.to_thread(self._seed_pointer)
                self._seeded_from = self._last_id
            except sqlite3.Error as exc:
                self._last_error = str(exc)
                self._context.logger.warning("611 seed failed: %s | db=%s", exc, self._db_path)
        self._running = True
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        self._running = False
        if self._task is not None and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None

    async def shutdown(self) -> None:
        await self.stop()

    def _fetch(self) -> list[dict[str, Any]]:
        columns = ", ".join(_COLUMNS)
        conn = _connect(self._db_path)
        try:
            conn.row_factory = sqlite3.Row
            if not _table_exists(conn, self._table):
                return []
            rows = [dict(r) for r in conn.execute(
                f"SELECT {columns} FROM {self._table} WHERE id > ? ORDER BY id LIMIT ?",
                (self._last_id, self._batch_limit)).fetchall()]
            for row in rows:
                row["account_id"] = None
                row["profit"] = None
                row["request_id"] = None
                row["commission"] = None
                row["swap"] = None
                row["fee"] = None
                row["trade_id"] = None
            try:
                ident = conn.execute(
                    f"SELECT id, account_id FROM {self._table} WHERE id > ? ORDER BY id LIMIT ?",
                    (self._last_id, self._batch_limit)).fetchall()
                by_id = {r[0]: r[1] for r in ident}
                for row in rows:
                    row["account_id"] = by_id.get(row.get("id"))
            except sqlite3.Error:
                pass
            try:
                prof = conn.execute(
                    f"SELECT id, profit FROM {self._table} WHERE id > ? ORDER BY id LIMIT ?",
                    (self._last_id, self._batch_limit)).fetchall()
                by_id_p = {r[0]: r[1] for r in prof}
                for row in rows:
                    row["profit"] = by_id_p.get(row.get("id"))
            except sqlite3.Error:
                pass
            try:
                reqs = conn.execute(
                    f"SELECT id, request_id FROM {self._table} WHERE id > ? ORDER BY id LIMIT ?",
                    (self._last_id, self._batch_limit)).fetchall()
                by_id_r = {r[0]: r[1] for r in reqs}
                for row in rows:
                    row["request_id"] = by_id_r.get(row.get("id"))
            except sqlite3.Error:
                pass
            for optional in ("commission", "swap", "fee", "trade_id"):
                try:
                    values = conn.execute(
                        f"SELECT id, {optional} FROM {self._table} WHERE id > ? ORDER BY id LIMIT ?",
                        (self._last_id, self._batch_limit)).fetchall()
                    by_id_optional = {r[0]: r[1] for r in values}
                    for row in rows:
                        row[optional] = by_id_optional.get(row.get("id"))
                except sqlite3.Error:
                    pass
            return rows
        finally:
            conn.close()

    def _fetch_pending_costs(self) -> list[dict[str, Any]]:
        now=time.monotonic()
        for row_id,deadline in list(self._pending_cost_deadlines.items()):
            if now>=deadline:
                self._pending_cost_deadlines.pop(row_id,None);self._pending_cost_rows.pop(row_id,None)
        if not self._pending_cost_rows:
            return []
        connection = _connect(self._db_path)
        try:
            connection.row_factory = sqlite3.Row
            marks = ",".join("?" for _ in self._pending_cost_rows)
            rows = [dict(row) for row in connection.execute(
                f"SELECT * FROM {self._table} WHERE id IN ({marks}) ORDER BY id",
                tuple(self._pending_cost_rows)).fetchall()]
            for row in rows:
                for name in ("commission", "swap", "fee", "trade_id", "request_id",
                             "account_id", "profit"):
                    row.setdefault(name, None)
            return rows
        finally:
            connection.close()

    @staticmethod
    def _cost_revision(row: dict[str, Any]) -> str:
        return "|".join(str(row.get(name)) for name in
                        ("profit", "commission", "swap", "fee", "trade_id", "request_id"))

    async def _publish_row(self, row: dict[str, Any]) -> None:
        if self._context is None:
            return
        account_id=str(row.get("account_id") or "").strip()
        if not account_id:
            self.identity_rejected+=1;self._last_error="TRADE_EVENT_ACCOUNT_ID_MISSING";return
        row_id = row.get("id")
        body = {key: row.get(key) for key in _COLUMNS if key != "id"}
        body.update({"account_id": row.get("account_id"), "profit": row.get("profit"),
                     "request_id": row.get("request_id"), "source_row_id": row_id})
        for optional in ("commission", "swap", "fee", "trade_id"):
            body[optional] = row.get(optional)
        # ٢٠٢٦-٠٩-١٦ — **طابع الوسيط لم يعد يُنشر باسم `timestamp`.**
        # المقيس على `nq_brain.db` حيًّا: ستّة جداول يكتبها الإكسبرت ساعتُها
        # صحيحة (`display` · `depth` · `ticks_v2` · `account_v2` كلّها ‎-0.00‎
        # ساعة · `commands.done_at` · `news.published_at`)، وجدولٌ واحد بحقلين
        # في **المستقبل**: `trade_events_v2.open_time` ‎+2.20‎ ساعة و`close_time`
        # ‎+2.41‎. والسبب طبيعةُ الحقل لا عطبٌ: ميتاتريدر يخزّن أوقات الصفقات
        # بوقت **خادم الوسيط**، وهذه الذرّة كانت تنقله حرفًا باسمٍ يَعِد بساعتنا.
        # فقرأه تسعة مشتركين زمنَ حدث — منهم 506 (حدود الجلسة) و522 (التدقيق)
        # و704 (الخطّ الزمنيّ) و720 (سجلّ الصفقات).
        #
        # ولا تصحيح بطرح ثابت: الإزاحة قِيست **2.83 ساعة** يوم ٠٩-١٥ و**2.41**
        # اليوم — تنجرف عبر الأيام وإن ثبتت داخل اللحظة (فارق 72.8 دقيقة بين
        # صفّين قابله فارق 72.6 دقيقة في انحرافهما). فأيّ ثابتٍ يزرع خطأً
        # جديدًا مكان القديم.
        #
        # فالطابع يُحفظ باسمه الصريح بلا مساس، وساعتنا تحمل `timestamp`،
        # والانحراف يُنطق رقمًا — وهو نمط جيراننا في 702/704 (`recorded_at`).
        now = self._official_time if self._official_time > 0 else time.time()
        stamp = _to_float(row.get("close_time")) or _to_float(row.get("open_time"))
        if stamp is not None:
            body["broker_time"] = stamp
            skew = stamp - now
            body["clock_skew_s"] = round(skew, 3)
            if abs(skew) > _SKEW_ALERT_S:
                self.skewed_count += 1
                if abs(skew) > abs(self.worst_skew_s):
                    self.worst_skew_s = round(skew, 3)
        body["timestamp"] = now
        self.published_count += 1
        if self._official_time > 0:
            self._last_data_official = self._official_time
        await self._context.publish(EVENT_OUT, body)

    async def _drain_once(self) -> None:
        if self._context is None:
            return
        try:
            rows = await asyncio.to_thread(self._fetch)
            revisions = await asyncio.to_thread(self._fetch_pending_costs)
        except sqlite3.Error as exc:
            self.failure_count += 1
            self._last_error = str(exc)
            self._context.logger.warning("611 read failed: %s | db=%s", exc, self._db_path)
            return
        self._last_error = ""
        self._last_read_official = self._official_time if self._official_time > 0 else time.time()
        if not rows and not revisions:
            return
        self.read_count += len(rows)
        for row in rows:
            row_id = row.get("id")
            if isinstance(row_id, int) and row_id > self._last_id:
                self._last_id = row_id
            await self._publish_row(row)
            if (isinstance(row_id, int) and str(row.get("event_type") or "").upper() in
                    {"CLOSED", "PARTIAL"} and any(row.get(name) is None for name in
                                                   ("commission", "swap", "fee"))):
                self._pending_cost_rows[row_id] = self._cost_revision(row)
                self._pending_cost_deadlines[row_id]=time.monotonic()+self._cost_refresh_timeout_s
        for row in revisions:
            row_id = row.get("id")
            if not isinstance(row_id, int) or row_id not in self._pending_cost_rows:
                continue
            revision = self._cost_revision(row)
            if revision == self._pending_cost_rows[row_id]:
                continue
            self._pending_cost_rows[row_id] = revision
            await self._publish_row(row)
            if all(row.get(name) is not None for name in ("commission", "swap", "fee")):
                self._pending_cost_rows.pop(row_id, None);self._pending_cost_deadlines.pop(row_id,None)

    async def _loop(self) -> None:
        try:
            while self._running:
                await self._drain_once()
                await asyncio.sleep(self._poll_interval_s)
        except asyncio.CancelledError:
            return

    async def health_check(self) -> HealthStatus:
        if not self._running:
            return HealthStatus(state=HealthState.UNHEALTHY, message=REASON_NOT_STARTED)
        details = {"read": self.read_count, "published": self.published_count,
                   "failures": self.failure_count, "identity_rejected":self.identity_rejected,
                   "last_id": self._last_id,
                   "skewed": self.skewed_count, "worst_skew_s": self.worst_skew_s,
                   "age_s": (self._official_time-self._last_data_official) if self._official_time and self._last_data_official else None}
        if self._last_error:
            return HealthStatus(state=HealthState.DEGRADED, message=REASON_NO_READ, details=details)
        if self.read_count == 0:
            return HealthStatus(state=HealthState.HEALTHY,
                                message="READY_AWAITING_FIRST_MT5_TRADE_EVENT | read=0 published=0",
                                details=details)
        now = self._official_time if self._official_time > 0 else time.time()
        read_age = (now - self._last_read_official) if self._last_read_official else None
        details["read_age_s"] = read_age
        last_trade = ("%.0fث" % details["age_s"]) if details["age_s"] is not None else "—"
        if read_age is not None and 0 <= read_age <= self._max_age_s:
            # القارئ حيّ: يقرأ ولا خطأ. هدوءُ التداول يُقال معلومةً لا عطبًا.
            skew = ("" if not self.skewed_count else
                    " · ساعة الوسيط: %d حدثًا منحرفًا · أقصى %+.0f ث"
                    % (self.skewed_count, self.worst_skew_s))
            return HealthStatus(
                state=HealthState.HEALTHY, details=details,
                message="published=%d · آخر قراءة منذ %.0fث · آخر صفقة منذ %s%s" % (
                    self.published_count, read_age, last_trade, skew))
        if read_age is not None:
            # القارئ نفسه توقّف عن القراءة — هذا هو الركود الحقيقيّ.
            return HealthStatus(
                state=HealthState.DEGRADED, details=details,
                message="TRADE_READER_STALE | آخر قراءة منذ %.0fث عتبة=%.0fث · آخر صفقة منذ %s"
                        % (read_age, self._max_age_s, last_trade))
        if details["age_s"] is None or details["age_s"] < 0 or details["age_s"] > self._max_age_s:
            # الاسم وحده لا يكفي — والبيات هو اللحظة التي يُسأل فيها
            # «أتوقّفت الصفقات أم توقّف القارئ؟». كان يخرج `TRADE_FEED_STALE`
            # عاريًا والعدّادات في `details` التي تُقصّ عند النواة، فسألت عنه
            # جلسةٌ أخرى (٢٠٢٦-٠٩-١٧) ولم تجد جوابًا فرجّحت صفقاتٍ وهميّة.
            # الصواب أن تحمل الرسالة ما يفرّق: كم قرأ، وكم نشر، وعمر آخر
            # صفقة، مقابل العتبة. صمتُ المصدر يُرى عندئذٍ صمتًا لا عطبًا.
            return HealthStatus(
                state=HealthState.DEGRADED,
                message="TRADE_FEED_STALE | read=%d published=%d عمر=%s عتبة=%.0fث%s" % (
                    self.read_count, self.published_count,
                    ("%.0fث" % details["age_s"]) if details["age_s"] is not None else "—",
                    self._max_age_s,
                    "" if not self.skewed_count else
                    " · ساعة الوسيط: %d منحرفًا · أقصى %+.0fث"
                    % (self.skewed_count, self.worst_skew_s)),
                details=details)
        # الانحراف يُنطق في **الرسالة** لا في `details` وحدها: `details`
        # تُقصّ عند النواة فلا تبلغ لوحةً ولا API — وما لا يُقرأ لا يُعدّ معلنًا.
        skew = ("" if not self.skewed_count else
                " · ساعة الوسيط: %d حدثًا منحرفًا · أقصى %+.0f ث"
                % (self.skewed_count, self.worst_skew_s))
        return HealthStatus(state=HealthState.HEALTHY,
                            message=f"published={self.published_count}{skew}", details=details)

    async def snapshot(self) -> dict:
        return {"last_id": self._last_id, "read": self.read_count,
                "published": self.published_count, "failures": self.failure_count,
                "identity_rejected":self.identity_rejected,
                # عدّادا الانحراف يُحفظان: الحدث المنحرف نادر، وإن ضاعا
                # عند كلّ إقلاع ضاع الدليل مع أنّ العلّة باقية.
                "skewed": self.skewed_count, "worst_skew_s": self.worst_skew_s,
                "pending_cost_rows": [{"row_id":row_id,"revision":revision,
                    "remaining_s":max(0.0,self._pending_cost_deadlines.get(row_id,time.monotonic())-time.monotonic())}
                    for row_id,revision in self._pending_cost_rows.items()]}

    async def restore(self, state: dict) -> None:
        if not isinstance(state, dict):
            raise ValueError("INVALID_TRADE_READER_STATE")
        new_last_id = int(state.get("last_id", 0))
        new_read_count = int(state.get("read", 0))
        new_published_count = int(state.get("published", 0))
        new_failure_count = int(state.get("failures", 0))
        new_identity_rejected = int(state.get("identity_rejected", 0))
        new_skewed_count = int(state.get("skewed", 0))
        new_worst_skew_s = float(state.get("worst_skew_s", 0.0))
        new_pending_cost_rows: dict[int, str] = {}
        new_pending_cost_deadlines: dict[int, float] = {}
        raw = state.get("pending_cost_rows") or []
        if isinstance(raw, dict):
            raw = [{"row_id": key, "revision": value, "remaining_s": self._cost_refresh_timeout_s}
                   for key, value in raw.items()]
        if not isinstance(raw, list): raw = []
        for item in raw:
            if not isinstance(item, dict): continue
            row_id = int(item.get("row_id"))
            new_pending_cost_rows[row_id] = str(item.get("revision") or "")
            new_pending_cost_deadlines[row_id] = time.monotonic() + max(0.0, float(item.get("remaining_s") or 0.0))
        self._last_id = new_last_id
        self.read_count = new_read_count
        self.published_count = new_published_count
        self.failure_count = new_failure_count
        self.identity_rejected = new_identity_rejected
        self.skewed_count = new_skewed_count
        self.worst_skew_s = new_worst_skew_s
        self._pending_cost_rows = new_pending_cost_rows
        self._pending_cost_deadlines = new_pending_cost_deadlines
        self._restored = True
