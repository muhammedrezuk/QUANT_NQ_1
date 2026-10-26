from __future__ import annotations

import asyncio
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

from core.contracts.atom import AtomBase, AtomContext, HealthState, HealthStatus
from storage_policy import enforce_limits, file_lock

ATOM_VERSION = "2.8.0"

_DB_TIMEOUT_S = 5.0
_BUSY_TIMEOUT_MS = 3000
# فارق يُعدّ طابعًا مستقبليًّا، ودوريّة نطقه.
_FUTURE_STAMP_TOLERANCE_S = 60.0
_STAMP_LOG_EVERY_S = 60.0

EVENT_TRADE = "platform.trade_event"
EVENT_OUTCOME = "market.outcome.realized"
EVENT_OUT = "storage.trades_saved"

KIND_OPENED = "OPENED"
KIND_CLOSED = "CLOSED"
KIND_PARTIAL = "PARTIAL"

REASON_NOT_STARTED = "NOT_STARTED"
REASON_STORE_UNAVAILABLE = "STORE_UNAVAILABLE"
REASON_NO_ACTIVITY = "NO_TRADES_YET"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS trades (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    kind            TEXT NOT NULL,
    trade_id        TEXT,
    ticket          INTEGER,
    account_id      TEXT,
    symbol          TEXT,
    side            TEXT,
    size            REAL,
    entry_price     REAL,
    exit_price      REAL,
    opened_at       REAL,
    closed_at       REAL,
    reason          TEXT,
    strategy_id     TEXT,
    pnl             REAL,
    pnl_pct         REAL,
    result          TEXT,
    partial         INTEGER,
    source_event_id INTEGER,
    stored_at       REAL
)
"""

_INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_trades_account ON trades(account_id, id DESC)",
    "CREATE INDEX IF NOT EXISTS idx_trades_ticket ON trades(ticket)",
    "CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades(symbol, id DESC)",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_trades_dedupe"
    " ON trades(kind, source_event_id) WHERE source_event_id IS NOT NULL",
)

_COLUMNS = ("kind", "trade_id", "ticket", "account_id", "symbol", "side", "size",
            "entry_price", "exit_price", "opened_at", "closed_at", "reason",
            "strategy_id", "pnl", "pnl_pct", "result", "partial",
            "source_event_id", "stored_at")


def _to_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _clock_skew(payload, stamp, now):
    """انحراف ساعة المصدر — أيًّا كان الحقل الذي يحمله.

    عقد `platform.trade_event` تغيّر ٢٠٢٦-٠٩-١٦ (٦١١ v4.1.0): `timestamp`
    صار **بساعتنا**، وطابع الوسيط انتقل إلى `broker_time` ومعه
    `clock_skew_s` جاهزًا. فقياسُ الانحراف من `timestamp` وحده — كما كان —
    **يعمى بعد هذا التغيير**: العدّاد يتوقّف عن الزيادة لا لأنّ العلّة زالت
    بل لأنّ مكانها تبدّل. تُقرأ المصادر الثلاثة بالترتيب، وأوّلُ موجودٍ يفوز:
    الحقل الجاهز · ثمّ `broker_time - timestamp` · ثمّ (توافقًا مع الناشرين
    الذين لم يتحوّلوا بعد) `timestamp - الآن`.
    """
    if not isinstance(payload, dict):
        return None
    ready = _to_float(payload.get("clock_skew_s"))
    if ready is not None:
        return ready
    broker = _to_float(payload.get("broker_time"))
    if broker is not None:
        return broker - (stamp if stamp is not None else now)
    return None if stamp is None else stamp - now


def _to_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _rebased_config(raw_cfg: dict) -> dict:
    """config المانيفست على يد مالك المسارات — نسبةً لجذر الـruntime.

    الذرّة لا تعرف أين شُغِّلت: قراءة القيمة النسبية من المانيفست نسبةً إلى
    مجلد التشغيل كانت تُنشئ شجرة ``var/store`` موازية تحت جذر المشروع لا
    يقرأها أحد. لذلك تُحلَّ القيمة عند مالك المسارات: يُتقدَّم جذرُ تشغيل
    صالح (فيه ``shared/runtime_paths.py`` — نسخة الـruntime أو الجذر العام)،
    ثم تُمرَّر config إليه. المسار المطلق (``C:\\…`` في جسر المنصّة) يمرّ
    حرفيًّا — إعادة صياغته قرار نشر لا تصحيح مسار. وتعذُّر الحلّ يرجع
    config كما هي: لا يُعطَّل إقلاع ذرّة بأزمة مسار.
    """
    here = Path(__file__).resolve()
    code_root = None
    for parent in here.parents:
        if (parent / "shared" / "runtime_paths.py").is_file():
            code_root = parent
            break
    if code_root is None:
        return raw_cfg
    import sys as _sys
    if str(code_root) not in _sys.path:
        _sys.path.insert(0, str(code_root))
    try:
        from shared.runtime_paths import manifest_config_rebase
        return manifest_config_rebase(raw_cfg, code_root=code_root)
    except Exception:  # noqa: BLE001 — لا يُعطَّل الإقلاع بأزمة مسار
        return raw_cfg


class Atom(AtomBase):
    def __init__(self) -> None:
        self._context: AtomContext | None = None
        self._initialized = False
        self._running = False
        self._db_path = ""
        self._store_ready = False
        self._last_error = ""
        self._conn: sqlite3.Connection | None = None
        self._max_rows = 0
        self._limit_state: dict[str, Any] = {}
        self.stored_count = 0
        self.duplicate_count = 0
        self.enriched_count = 0
        self.failure_count = 0
        self.future_stamp_count = 0
        self._last_stamp_log_at = 0.0

    async def initialize(self, context: AtomContext) -> None:
        self._context = context
        cfg = _rebased_config(context.config)
        self._db_path = str(cfg["db_path"])   # cfg مُعلَّب — لا قراءة خام
        # قفلُ الملفّ لا قفلُ الكائن: ذرّاتٌ أخرى تكتب على القاعدة نفسها
        # في هذه العمليّة (٧١٦ ينظّف · ٧١٤ يؤرشف · الإنفاذ يرحّل). القفل
        # داخل الكائن يُسلسل الذرّة مع نفسها ولا يعبر إلى جارتها — وذاك
        # ما كسر المنصّة ٢٠٢٦-٠٩-١٨ حين خرجت الأعمال الطويلة إلى مهامّ
        # خلفيّة فسقط التسلسل الذي كانت حلقة العامل تفرضه قسرًا.
        self._conn_lock = file_lock(self._db_path)
        self._max_rows = int(cfg.get("max_rows", 0))
        context.subscribe(EVENT_TRADE, self._on_trade_event)
        context.subscribe(EVENT_OUTCOME, self._on_outcome)
        self._store_ready = self._ensure_store()
        self._initialized = True

    async def start(self) -> None:
        if not self._initialized or self._running or self._context is None:
            return
        self._running = True
        if not self._store_ready:
            self._store_ready = self._ensure_store()

    async def stop(self) -> None:
        self._running = False
        # الإغلاق يُجري نقطة تفتيش ويطوي الـWAL — لا يُترك اتصال معلّقًا.
        with self._conn_lock:
            self._close_connection()

    async def shutdown(self) -> None:
        await self.stop()

    def _connect(self) -> sqlite3.Connection:
        # `check_same_thread=False`: الكتابة تجري في `asyncio.to_thread` وخيطها
        # ليس ثابتًا. الحماية بالقفل `_conn_lock` لا بانتماء الخيط.
        connection = sqlite3.connect(self._db_path, timeout=_DB_TIMEOUT_S,
                                     check_same_thread=False)
        try:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA busy_timeout=%d" % _BUSY_TIMEOUT_MS)
            connection.execute("PRAGMA synchronous=NORMAL")
        except BaseException:
            # أوّل PRAGMA هي التي تقرأ ترويسة الملف: على قاعدة تالفة ترمي
            # بعد إنشاء الاتصال، فيبقى المقبض مفتوحًا والملف ممسوكًا على
            # ويندوز — فيتعذّر إصلاح ما تلف. مقيس ٢٠٢٦-٠٩-٠٩.
            connection.close()
            raise
        return connection

    def _connection(self) -> sqlite3.Connection:
        """الاتصال المعمَّر — يُفتح مرّة ويبقى، تحت قفل.

        كان `_insert` و`_enrich` يفتح كلٌّ منهما اتصالًا لكلّ صفّ ويغلقه.
        والكلفة ليست الاستعلام بل **دورة نظام الملفات**: إنشاء `-wal` و`-shm`
        ثمّ نقطة تفتيش ومحوهما عند كلّ إغلاق. مقيسة في ٧٠٧ على قاعدة حيّة
        ٢٠٢٦-٠٩-٠٩: **٣٣٫٥٣ م.ث مقابل ٤٫٤٩** بمعمَّر — ×٧٫٥.
        """
        if self._conn is None:
            self._conn = self._connect()
        return self._conn

    def _close_connection(self) -> None:
        connection, self._conn = self._conn, None
        if connection is not None:
            try:
                connection.close()
            except sqlite3.Error:
                pass

    def _ensure_store(self) -> bool:
        try:
            Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
            connection = self._connect()
            try:
                connection.execute(_SCHEMA)
                for statement in _INDEXES:
                    connection.execute(statement)
                connection.commit()
            finally:
                connection.close()
            self._last_error = ""
            return True
        except (sqlite3.Error, OSError) as exc:
            self._last_error = str(exc)
            return False

    def _insert(self, row: dict[str, Any]) -> bool:
        with self._conn_lock:
            connection = self._connection()
            columns = ", ".join(_COLUMNS)
            marks = ", ".join("?" for _ in _COLUMNS)
            cursor = connection.execute(
                "INSERT OR IGNORE INTO trades (%s) VALUES (%s)" % (columns, marks),
                tuple(row.get(name) for name in _COLUMNS))
            connection.commit()
            return cursor.rowcount > 0

    def _enrich(self, ticket: int | None, trade_id: str | None, pnl: float | None,
                pnl_pct: float | None, result: str | None,
                strategy_id: str | None, source_event_id: int | None = None,
                account_id: str | None = None) -> int:
        if source_event_id is None and ticket is None and trade_id is None: return 0
        with self._conn_lock:
            connection = self._connection()
            filters = ["kind IN (?, ?)"]; params: list[Any] = [KIND_CLOSED, KIND_PARTIAL]
            if source_event_id is not None:
                filters.append("source_event_id = ?"); params.append(source_event_id)
            elif trade_id:
                filters.append("trade_id = ?"); params.append(trade_id)
            else:
                filters.append("ticket = ?"); params.append(ticket)
                if account_id: filters.append("account_id = ?"); params.append(account_id)
            where = " AND ".join(filters)
            target = connection.execute("SELECT id FROM trades WHERE " + where + " ORDER BY id DESC LIMIT 1", params).fetchone()
            if target is None: return 0
            cursor = connection.execute(
                "UPDATE trades SET pnl=?, pnl_pct=?, result=?, strategy_id=COALESCE(?,strategy_id) WHERE id=?",
                (pnl, pnl_pct, result, strategy_id, target[0]))
            connection.commit(); return cursor.rowcount or 0

    async def _on_trade_event(self, payload: dict[str, Any]) -> None:
        if not isinstance(payload, dict):
            return
        kind = str(payload.get("event_type", ""))
        if kind not in (KIND_OPENED, KIND_CLOSED, KIND_PARTIAL):
            return
        await self._store(kind, payload)

    def _row(self, kind: str, payload: dict[str, Any]) -> dict[str, Any]:
        # ساعة التخزين تُقرأ من ساعتنا لا من الحمولة. كانت `stored_at` تُملأ
        # بـ`payload["timestamp"]` — فالاسم يَعِد بوقت التخزين والقيمة وقتُ
        # ناشرٍ آخر. ومقيس ٢٠٢٦-٠٩-١٦: حدث `platform.trade_event` يأتي بساعة
        # خادم الوسيط (**+٢٫٨٣ ساعة**)، فستّة صفوف هنا بتاريخٍ مستقبليّ —
        # وعمودُ الأرشفة الاحتياطيّ في ٧١٤ يقرأ هذا العمود بعينه.
        stored_at = time.time()
        skew = _clock_skew(payload, _to_float(payload.get("timestamp")), stored_at)
        if skew is not None and skew > _FUTURE_STAMP_TOLERANCE_S:
            self.future_stamp_count += 1
            self._note_future_stamp(kind, stored_at + skew, stored_at)
        return {
            "kind": kind,
            "trade_id": payload.get("trade_id"),
            "ticket": _to_int(payload.get("ticket")),
            "account_id": str(payload.get("account_id"))
            if payload.get("account_id") else None,
            "symbol": payload.get("symbol"),
            "side": payload.get("side"),
            "size": _to_float(payload.get("volume")),
            "entry_price": _to_float(payload.get("entry_price")),
            "exit_price": _to_float(payload.get("exit_price")),
            "opened_at": _to_float(payload.get("open_time")),
            "closed_at": _to_float(payload.get("close_time")),
            "reason": payload.get("reason"),
            "strategy_id": str(payload.get("strategy_id"))
            if payload.get("strategy_id") else None,
            "pnl": _to_float(payload.get("profit")), "pnl_pct": None, "result": None,
            "partial": 1 if kind == KIND_PARTIAL else 0,
            "source_event_id": _to_int(payload.get("source_row_id")),
            "stored_at": stored_at,
        }

    def _note_future_stamp(self, kind: str, stamp: float, now: float) -> None:
        """انحراف ساعة الناشر يُنطق ولا يُصحَّح — بخنق دقيقة.

        التصحيح بطرح ثابت تخمينٌ: الفارق قِيس ٢٫٨٣ ساعة لا ٣ بالضبط، وساعة
        الوسيط تنجرف. المخزن يحفظ ما جاء ويقول إنّه منحرف.
        """
        if now - self._last_stamp_log_at < _STAMP_LOG_EVERY_S:
            return
        self._last_stamp_log_at = now
        context = self._context
        if context is None or getattr(context, "logger", None) is None:
            return
        try:
            context.logger.warning(
                "702 مخزن الصفقات: طابع من المستقبل — نوع=%s فرق=%+.0f ثانية"
                " (%.2f ساعة). `closed_at`/`opened_at` من الوسيط كما جاءت،"
                " و`stored_at` بساعتنا. مجموع=%d",
                kind, stamp - now, (stamp - now) / 3600.0, self.future_stamp_count)
        except Exception:  # noqa: BLE001 — لا يسقط مخزن بسبب سجلّ
            pass

    async def _store(self, kind: str, payload: dict[str, Any]) -> None:
        if not self._running or self._context is None or not isinstance(payload, dict):
            return
        if kind == KIND_CLOSED and payload.get("partial"):
            kind = KIND_PARTIAL
        if not self._store_ready:
            self._store_ready = self._ensure_store()
        if not self._store_ready:
            self.failure_count += 1
            return
        row = self._row(kind, payload)
        try:
            inserted = await asyncio.to_thread(self._insert, row)
        except sqlite3.Error as exc:
            self.failure_count += 1
            self._last_error = str(exc)
            return
        if not inserted:
            self.duplicate_count += 1
            return
        self.stored_count += 1
        try:
            self._limit_state = await asyncio.to_thread(self._enforce_limits_locked)
        except (OSError, sqlite3.Error, ValueError) as exc:
            self._last_error = str(exc)
        body: dict[str, Any] = {"kind": kind, "ticket": row["ticket"],
                                "account_id": row["account_id"], "symbol": row["symbol"]}
        if row["stored_at"] is not None:
            body["timestamp"] = row["stored_at"]
        await self._context.publish(EVENT_OUT, body)

    async def _on_outcome(self, payload: dict[str, Any]) -> None:
        if not self._running or self._context is None or not isinstance(payload, dict):
            return
        if not self._store_ready:
            self._store_ready = self._ensure_store()
        if not self._store_ready:
            self.failure_count += 1
            return
        try:
            updated = await asyncio.to_thread(
                self._enrich, _to_int(payload.get("ticket")), payload.get("trade_id"),
                _to_float(payload.get("pnl", payload.get("profit"))), _to_float(payload.get("pnl_pct")),
                payload.get("result"),
                str(payload.get("strategy_id")) if payload.get("strategy_id") else None,
                _to_int(payload.get("source_row_id")),
                str(payload.get("account_id")) if payload.get("account_id") else None)
        except sqlite3.Error as exc:
            self.failure_count += 1
            self._last_error = str(exc)
            return
        self.enriched_count += updated

    def _enforce_limits_locked(self) -> dict[str, Any]:
        """الإنفاذ تحت قفل الإدراج — كاتبٌ واحد من هذه الذرّة في أيّ لحظة.

        ‏⛔ وقايةٌ من انحدارٍ سبّبتُه أنا. حين عمَّرتُ الاتّصال (٢٠٢٦-٠٩-١٦)
        بقي `enforce_limits` يفتح **اتّصاله الثاني** ويكتب على القاعدة نفسها،
        **خارج قفل الإدراج** — فصار ممكنًا أن يتداخل مع `_flush`. وقبل
        التعمير كان `_flush` يفتح ويغلق مع كلّ دفعة فلا يلتقيان.

        ⚠️ والآلية مقيسة لا مظنونة (قاعدة ٤١ م.ب بـWAL حقيقيّ): المقبض
        المعمَّر **وحده بريء** — خاملًا أو بعد `commit` ينكمش الملف ٤١ م.ب
        ← ٠٫٣٥. والقاتل **معاملةٌ مفتوحة** لحظة الإنفاذ: معاملة كتابة ⟵
        `database is locked`، ومعاملة قراءة ⟵ لا ينكمش و٦٨٫٨ ثانية صامتة.
        و`sqlite3` يفتح معاملةً ضمنيّة مع كلّ كتابة حتى `commit`.

        وقد قتل هذا المنصّة في ٧١٢ ليلة ٢٠٢٦-٠٩-١٨، وكان أشدّ هناك لأنّها
        وحدها تُنادي بـ`shrink=True`. وهذه لا تُفرغ، فيكفيها **التسلسل**:
        القفل نفسه يمنع التداخل، ولا يُسلَّم الاتّصال فتبقى فائدة التعمير.
        """
        with self._conn_lock:
            return enforce_limits(
                self._db_path, "trades", max_rows=self._max_rows)

    async def snapshot(self) -> dict[str, Any]:
        return {"version": ATOM_VERSION, "stored": self.stored_count,
                "duplicates": self.duplicate_count, "enriched": self.enriched_count,
                "failures": self.failure_count}

    async def restore(self, state: dict[str, Any]) -> None:
        if not isinstance(state, dict): raise ValueError("INVALID_TRADE_STORE_STATE")
        self.stored_count = int(state.get("stored") or 0)
        self.duplicate_count = int(state.get("duplicates") or 0)
        self.enriched_count = int(state.get("enriched") or 0)
        self.failure_count = int(state.get("failures") or 0)

    async def health_check(self) -> HealthStatus:
        if not self._running:
            return HealthStatus(state=HealthState.UNHEALTHY, message=REASON_NOT_STARTED)
        details = {"stored": self.stored_count, "duplicates": self.duplicate_count,
                   "enriched": self.enriched_count, "failures": self.failure_count,
                   "store_ready": self._store_ready, "last_error": self._last_error,
                   "limits": dict(self._limit_state)}
        if not self._store_ready:
            return HealthStatus(
                state=HealthState.DEGRADED,
                message=self._last_error or REASON_STORE_UNAVAILABLE, details=details)
        if self._last_error:
            return HealthStatus(state=HealthState.DEGRADED, message=self._last_error, details=details)
        if self._limit_state.get("breached"):
            return HealthStatus(state=HealthState.DEGRADED, message="STORAGE_LIMIT_ENFORCED", details=details)
        if self.stored_count == 0:
            if self.failure_count:
                return HealthStatus(
                    state=HealthState.DEGRADED,
                    message="SUSPECTED_FAULT: %d store failures and zero rows stored" % self.failure_count,
                    details=details)
            return HealthStatus(
                state=HealthState.HEALTHY,
                message="READY_AWAITING_FIRST_TRADE_STORE | stored=0",
                details=details)
        return HealthStatus(
            state=HealthState.HEALTHY,
            message="stored=%d enriched=%d" % (self.stored_count, self.enriched_count),
            details=details)
