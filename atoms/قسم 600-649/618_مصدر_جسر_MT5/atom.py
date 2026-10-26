from __future__ import annotations

import asyncio
import math
import os
import sqlite3
import time
from typing import Any

import clock
from core.contracts.atom import AtomBase, AtomContext, HealthState, HealthStatus

ATOM_VERSION = "4.8.2"

SUBSECOND_CLOCK_REASON = "tick receipt time needs sub-second resolution"

PROVIDER = "MT5"
EVENT_TICK = "feed.mt5.tick"
EVENT_SPECS = "market.symbol_specs"
EVENT_PULSE = "SYS_SECOND"
EVENT_FAST_PULSE = "SYS_10MS"
EVENT_ACCOUNT = "platform.account.state"

REASON_NOT_STARTED = "NOT_STARTED"
REASON_NO_TABLE = "TICKS_TABLE_MISSING"
REASON_NO_FILE = "BRIDGE_FILE_MISSING"
REASON_NO_DATA = "NO_TICKS_YET"

_COLUMNS = ("id", "account_id", "symbol", "bid", "ask", "last", "volume", "tick_ms")

_MS_PER_SECOND = 1000.0

_CLOCK_TOLERANCE_S = 5.0


def broker_clock(broker_stamp: float, received_at: float):
    offset = broker_stamp - received_at
    aligned = abs(offset) <= _CLOCK_TOLERANCE_S
    return offset, (broker_stamp if aligned else None)


def utc_gate(broker_stamp: float, received_at: float) -> dict[str, Any] | None:
    """باب التطبيع: جوّا النظام UTC فقط. الاستلام بديل الطابع الفاسد."""
    if not math.isfinite(received_at) or received_at <= 0:
        return None
    raw = broker_stamp if math.isfinite(broker_stamp) else None
    if raw is None:
        return {
            "broker_timestamp_raw": None,
            "received_at": received_at,
            "exchange_timestamp": None,
            "timestamp": received_at,
            "timestamp_source": "received",
            "clock_domain": "UTC",
            "clock_offset_s": None,
            "clock_valid": False,
        }
    offset, exchange_stamp = broker_clock(raw, received_at)
    valid = exchange_stamp is not None
    stamp = raw if valid else received_at
    return {
        "broker_timestamp_raw": raw,
        "received_at": received_at,
        "exchange_timestamp": exchange_stamp,
        "timestamp": stamp,
        "timestamp_source": "broker" if valid else "received",
        "clock_domain": "UTC",
        "clock_offset_s": offset,
        "clock_valid": valid,
    }
_MID_DIVISOR = 2.0
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


def _connect(db_path: str, read_only: bool = True) -> sqlite3.Connection:
    uri = f"file:{db_path}?mode=ro" if read_only else db_path
    conn = sqlite3.connect(uri, uri=read_only, timeout=_CONNECT_TIMEOUT_S)
    conn.execute(f"PRAGMA busy_timeout={_BUSY_TIMEOUT_MS}")
    if not read_only:
        # ٢٠٢٦-٠٩-١٩ — **وتصحيحُ ادّعاءٍ لي في الختم `f4d26ed`.**
        # ادّعيتُ أنّ هذا السطر كان يُسقط دورات حذفٍ حيًّا. **وهذا خطأ**:
        # الأمر لا-عمل حين تكون القاعدة في WAL أصلًا (مقيس: 0.000ث بلا
        # قفل)، وقاعدة الجسر الحيّة `wal`. والقفل الحصريّ يُطلب في حالة
        # **التحوّل** من `DELETE` وحدها — أي على قاعدةٍ جديدة.
        # يبقى التعديل لأنّه صحيحٌ في ذاته: عملٌ بلا فائدة كلّ اتّصال
        # (ومئةً في الثانية هنا عند `poll_interval_s: 0.01`)، ويفتح خطرَ
        # التحوّل على قاعدةٍ تُبنى من جديد. يُقرأ ولا يُكتب إلّا إن اختلف.
        try:
            mode = conn.execute("PRAGMA journal_mode").fetchone()
            if not mode or str(mode[0]).lower() != "wal":
                conn.execute("PRAGMA journal_mode=WAL")
        except sqlite3.OperationalError:
            pass
        conn.execute("PRAGMA synchronous=NORMAL")
    return conn


class Atom(AtomBase):
    def __init__(self) -> None:
        self._context: AtomContext | None = None
        self._running = False
        self._last_specs_at = 0.0
        self._last_poll_at = 0.0
        self._db_path = ""
        self._table = "ticks_v2"
        self._spec_table = "symbol_specs"
        self._spec_refresh_s = 0.0
        self._poll_interval_s = 0.0
        self._batch_limit = 0
        self._delete_consumed = True
        self._last_id = 0
        self._last_error = ""
        self._symbols: set[tuple[str, str]] = set()
        self._announced: set[tuple[str, str]] = set()
        self._broker_by_account: dict[str, str] = {}
        self.published_count = 0
        self.spec_publishes = 0
        # أسماء الرموز التي أُسقطت من آخر دفعة مواصفات — تُنطق في الرسالة.
        self._specs_dropped: list[str] = []
        self.dropped_count = 0
        self.failure_count = 0
        self._official_time = 0.0
        self._last_data_official = 0.0
        self._max_age_s = 30.0

    async def initialize(self, context: AtomContext) -> None:
        self._context = context
        cfg = context.config
        self._db_path = _resolve_db(str(cfg["db_path"]))
        self._table = str(cfg["table_name"])
        self._spec_table = str(cfg["spec_table"])
        if self._table != "ticks_v2" or self._spec_table != "symbol_specs_v2":
            self._table = "ticks_v2"
            self._spec_table = "symbol_specs_v2"
            self._last_error = "LEGACY_MARKET_TABLE_FORBIDDEN"
        self._spec_refresh_s = float(cfg["spec_refresh_s"])
        self._poll_interval_s = float(cfg["poll_interval_s"])
        self._batch_limit = int(cfg["batch_limit"])
        self._delete_consumed = bool(cfg["delete_consumed"])
        self._max_age_s = float(cfg.get("max_age_s", 30.0))
        context.subscribe(EVENT_PULSE, self._on_pulse)
        context.subscribe(EVENT_FAST_PULSE, self._on_fast_pulse)
        context.subscribe(EVENT_ACCOUNT, self._on_account)

    async def _on_account(self, payload: dict[str, Any]) -> None:
        if not isinstance(payload, dict):
            return
        account = str(payload.get("account_id") or "").strip()
        broker = str(payload.get("broker") or "").strip()
        if not account or not broker:
            return
        if self._broker_by_account.get(account) == broker:
            return
        # 4.5.0 — قِيس ٢٠٢٦-٠٩-٠٧ بختم NQ: `start()` ينشر المواصفات قبل وصول أوّل
        # `platform.account.state`، فتخرج بـ broker="" (السطر 222). و`_announce_if_new`
        # لا يعيد النشر إلا لرمزٍ جديد، والرموز الأربعة معلَنة سلفًا ⇒ الصفوف لا
        # تُعاد أبدًا، فيبقى 513 على SIZING_UNAVAILABLE_FOR_SYMBOL (مفتاحه
        # حساب|وسيط|رمز) ولا يُبنى أمر. عند تعلُّم وسيطٍ جديد نُعيد النشر مرّة
        # واحدة — الشرط أعلاه يمنع التكرار على كل نبضة حساب، و618 لا يشترك في
        # `market.symbol_specs` فلا حلقة.
        self._broker_by_account[account] = broker
        await self._refresh_specs()

    async def _on_pulse(self, payload: dict[str, Any]) -> None:
        stamp = _to_float(payload.get("official_time")) if isinstance(payload, dict) else None
        if stamp is not None:
            self._official_time = stamp

    async def start(self) -> None:
        if self._running or self._context is None:
            return
        self._running = True
        await self._refresh_specs()
        # v4.3.0: the paced pump task (622's bridge pattern) -- see _run.
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._running = False
        task = getattr(self, "_task", None)
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._task = None
        self.failure_count = 0
        self._last_error = ""

    async def shutdown(self) -> None:
        await self.stop()

    def _fetch(self) -> list[dict[str, Any]]:
        columns = ", ".join(_COLUMNS)
        conn = _connect(self._db_path, read_only=True)
        try:
            conn.row_factory = sqlite3.Row
            return [dict(r) for r in conn.execute(
                f"SELECT {columns} FROM {self._table} WHERE id > ? ORDER BY id LIMIT ?",
                (self._last_id, self._batch_limit)).fetchall()]
        finally:
            conn.close()

    def _purge(self, up_to_id: int) -> None:
        conn = _connect(self._db_path, read_only=False)
        try:
            conn.execute(f"DELETE FROM {self._table} WHERE id <= ?", (up_to_id,))
            conn.commit()
        finally:
            conn.close()

    def _read_specs(self) -> list[dict[str, Any]]:
        conn = _connect(self._db_path, read_only=True)
        try:
            conn.row_factory = sqlite3.Row
            return [dict(r) for r in conn.execute(f"SELECT * FROM {self._spec_table}").fetchall()]
        finally:
            conn.close()

    async def _refresh_specs(self) -> None:
        if self._context is None:
            return
        try:
            rows = await asyncio.to_thread(self._read_specs)
        except sqlite3.Error as exc:
            self._context.logger.warning("618 spec read failed: %s | db=%s", exc, self._db_path)
            return
        usable = []
        dropped: list[str] = []
        for row in rows:
            size = _to_float(row.get("contract_size"))
            if size is None or size <= 0:
                # ٢٠٢٦-٠٩-١٩: الإسقاط صحيح — `contract_size=0` لا يُبنى عليه
                # لوت. لكنّه كان **صامتًا**، ومستهلكُ المواصفات يخزّنها لكلّ
                # مفتاحٍ على حدة، فالرمز المسقَط يبقى بقيمته القديمة ويشيخ
                # بلا أن يُعلن. ومقيس اليوم: حين انقطع الوسيط قرأ الإكسبرت
                # أصفارًا للرموز السبعة المشترَك فيها، فخرجت دفعةٌ تحمل
                # `AUDUSD` و`DXY_U6` وحدهما (وهما غير مشترَك فيهما فبقيت
                # قيمهما)، وشاخت السبعة عند 513 فحجب 555 خمسةً وأربعين
                # قرارًا بـ`NO_SIZE_FOR_SCOPE`. الإسقاط يبقى، والصمت يزول.
                name = str(row.get("symbol") or "?")
                if name not in dropped:
                    dropped.append(name)
                continue
            account_id = str(row.get("account_id") or "")
            # الصفّ كما ورد أوّلًا — ثمّ تُطبَّق فوقه الحقول المطبَّعة.
            # ٢٠٢٦-٠٩-١٩: كانت الحمولة تُبنى بقائمة مفاتيح مكتوبة بخطّ اليد،
            # فكلُّ عمودٍ جديد في الجدول يُقرأ من القاعدة ثمّ **يُرمى هنا**.
            # وقد قلتُ لقسم 450-599 إنّ `SELECT *` يُوصل أيّ عمودٍ جديد
            # تلقائيًّا — وكان ذلك **خطأً منّي**: القراءة شاملة والنشر مقصوص.
            # فالحقول الاثنا عشر (`calc_mode` · `swap_*` · `margin_*` ·
            # `tick_value_profit/loss` · `currency_*`) كانت تصل الذرّة ولا
            # تغادرها. الأساس الآن الصفُّ كلُّه، والمطبَّع يعلوه.
            usable.append({**{k: v for k, v in row.items() if k != "account_id"},
                           "account_id": account_id,
                           "broker": self._broker_by_account.get(account_id, ""),
                           "symbol": row.get("symbol"), "contract_size": size,
                           "tick_value": _to_float(row.get("tick_value")),
                           "tick_size": _to_float(row.get("tick_size")),
                           "point": _to_float(row.get("point")),
                           "digits": row.get("digits"),
                           "stops_level": row.get("stops_level"),
                           "freeze_level": row.get("freeze_level"),
                           "volume_min": _to_float(row.get("volume_min")),
                           "volume_max": _to_float(row.get("volume_max")),
                           "volume_step": _to_float(row.get("volume_step")),
                           "filling_mode": row.get("filling_mode"),
                           "spec_published_at": self._official_time or clock.now(),
                           "spec_observed_monotonic": clock.mono()})
        self._specs_dropped = dropped
        if not usable:
            return
        self._announced = {(str(r.get("account_id") or ""), str(r["symbol"])) for r in usable}
        self.spec_publishes += 1
        await self._context.publish(EVENT_SPECS, {
            "provider": PROVIDER, "published_at": self._official_time or clock.now(),
            "published_monotonic": clock.mono(), "symbols": usable})

    async def _announce_if_new(self, symbols: set[tuple[str, str]]) -> None:
        if symbols - self._announced:
            await self._refresh_specs()

    async def _drain_once(self) -> None:
        if self._context is None:
            return
        try:
            rows = await asyncio.to_thread(self._fetch)
        except sqlite3.Error as exc:
            self.failure_count += 1
            message = str(exc).lower()
            self._last_error = (REASON_NO_TABLE if "no such table" in message
                                else REASON_NO_FILE if "unable to open" in message else str(exc))
            self._context.logger.warning("618 read failed: %s | db=%s", exc, self._db_path)
            return
        self._last_error = ""
        if not rows:
            return
        seen = {(str(r.get("account_id") or ""), str(r["symbol"])) for r in rows if r.get("symbol")}
        await self._announce_if_new(seen)
        highest = self._last_id
        for row in rows:
            row_id = int(row["id"])
            highest = max(highest, row_id)
            account_id = str(row.get("account_id") or "")
            symbol = row.get("symbol")
            bid = _to_float(row.get("bid"))
            ask = _to_float(row.get("ask"))
            tick_ms = _to_float(row.get("tick_ms"))
            if not account_id or not symbol or tick_ms is None:
                # المصدر يُسلّم ولا يحكم. يبقى ما يعجز عن التسليم بدونه:
                # بلا حساب ولا رمز لا تُعرف الهويّة، وبلا طابع لا تُبنى شمعة.
                # صلاحية السعر شأن 112، وهو يعلن سببه على
                # `market_data.validation_failed` بدل ابتلاعه — وهنا تحديدًا
                # لا يُبتلع فقط: الصفّ يُمحى من الجسر بعده (`_purge`) فلا
                # يُسترجع أبدًا.
                self.dropped_count += 1
                continue
            self._symbols.add((account_id, str(symbol)))
            received = time.time()
            broker_stamp = tick_ms / _MS_PER_SECOND
            gated = utc_gate(broker_stamp, received)
            if gated is None:
                self.dropped_count += 1
                continue
            await self._context.publish(EVENT_TICK, {
                "provider": PROVIDER,
                "account_id": account_id,
                "broker": self._broker_by_account.get(account_id, ""),
                "symbol": symbol,
                "bid": bid,
                "ask": ask,
                "price": ((bid + ask) / _MID_DIVISOR
                          if bid is not None and ask is not None else None),
                "volume": _to_float(row.get("volume")),
                "last_trade": _to_float(row.get("last")),
                "broker_timestamp": gated["broker_timestamp_raw"],
                "broker_timestamp_raw": gated["broker_timestamp_raw"],
                "broker_clock_offset_s": gated["clock_offset_s"],
                "clock_offset_s": gated["clock_offset_s"],
                "exchange_timestamp": gated["exchange_timestamp"],
                "received_at": gated["received_at"],
                "timestamp": gated["timestamp"],
                "timestamp_source": gated["timestamp_source"],
                "clock_domain": gated["clock_domain"],
                "clock_valid": gated["clock_valid"],
                "source_row_id": row_id,
            })
            self.published_count += 1
            if self._official_time > 0:
                self._last_data_official = self._official_time
        self._last_id = highest
        if self._delete_consumed and highest > 0:
            try:
                await asyncio.to_thread(self._purge, highest)
            except sqlite3.Error as exc:
                self._context.logger.warning("618 purge failed: %s | db=%s", exc, self._db_path)

    async def _on_fast_pulse(self, payload: dict[str, Any]) -> None:
        # v4.3.0 (nq seal 2026-08-25): kept for compatibility -- if a SYS_10MS
        # pulse ever exists it still drives the pump. But the 2026-08-24 patch
        # note "reading ticks_v2 on SYS_10MS; poll loop removed" hung this
        # atom's ONLY pump on a pulse NOBODY publishes (measured: zero
        # SYS_10MS publishers project-wide) -- the MT5 feed has been
        # structurally dead since that patch. The bridge-family paced task
        # loop (622's pattern) is restored below as the actual pump.
        if not self._running or not isinstance(payload, dict):
            return
        stamp = _to_float(payload.get("official_time"))
        if stamp is None:
            return
        # ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): الإيقاع بساعةٍ واحدة رتيبة كـ`_run`.
        # ختمُ النبضة هنا والرتيبة هناك يخلطان أساسين في `_last_poll_at` فيوقف أحدُهما الآخر.
        await self._pump(clock.mono())

    async def _pump(self, stamp: float) -> None:
        if stamp - self._last_poll_at < self._poll_interval_s:
            return
        self._last_poll_at = stamp
        await self._drain_once()
        if stamp - self._last_specs_at >= self._spec_refresh_s:
            self._last_specs_at = stamp
            await self._refresh_specs()

    async def _run(self) -> None:
        # Paced poll loop -- the bridge family's sanctioned pattern (622).
        while self._running:
            try:
                # ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): الإيقاع بالساعة الرتيبة لا بختم
                # النبضة. كان `self._official_time or time.time()`، و`_official_time` لا
                # يتحرّك إلّا مع `SYS_SECOND` مرّةً في الثانية — فالفارق في `_pump` صفرٌ
                # طوال الثانية فيخرج قبل القراءة، وتُصرَّف تِكّات ميتاتريدر دفعةً واحدة
                # في الثانية لا كلّ 10 م.ث (`poll_interval_s: 0.01`). مقيس بالاختبار
                # الجديد: 38 تِكّة في ~0.4ث خرجت في دفعة أو اثنتين. و`_official_time`
                # يبقى للختم وحده (`spec_published_at` · عمر البيانات).
                await self._pump(clock.mono())
            except asyncio.CancelledError:
                return
            except Exception as exc:  # noqa: BLE001 -- bridge isolation
                self._last_error = "%s: %s" % (type(exc).__name__, exc)
            await asyncio.sleep(max(self._poll_interval_s, 0.005))

    async def health_check(self) -> HealthStatus:
        if not self._running:
            return HealthStatus(state=HealthState.UNHEALTHY, message=REASON_NOT_STARTED)
        details = {"published": self.published_count, "dropped": self.dropped_count,
                   "specs_dropped": list(self._specs_dropped),
                   "failures": self.failure_count, "last_id": self._last_id,
                   "symbols": len(self._symbols), "last_error": self._last_error,
                   "age_s": (self._official_time - self._last_data_official) if self._official_time and self._last_data_official else None}
        if self._last_error:
            return HealthStatus(state=HealthState.DEGRADED, message=self._last_error, details=details)
        if self.published_count == 0:
            return HealthStatus(state=HealthState.DEGRADED, message=REASON_NO_DATA, details=details)
        if details["age_s"] is None or details["age_s"] < 0 or details["age_s"] > self._max_age_s:
            return HealthStatus(state=HealthState.DEGRADED, message="MT5_TICK_FEED_STALE", details=details)
        # الرموز المسقَطة من دفعة المواصفات في **الرسالة**: `details` تُقصّ
        # عند حدود النواة، ورمزٌ يسقط صامتًا يشيخ عند مستهلكه فيُحجب أمره.
        # ٢٠٢٦-٠٩-٢٣ (بلاغ قسم 500-550): `market.symbol_specs` لم يصل ٥٨٣
        # و٥٧٢ منذ الإقلاع، وعدّادُ النشر محبوسٌ في `details` التي تُقصّ
        # عند حدود النواة — فلا يُعرف من الخارج **أنُشر ولم يصل، أم لم
        # يُنشر أصلًا**. وهذان عطلان مختلفان وعلاجهما مختلف.
        specs = " · مواصفات: نُشرت %d مرّة" % self.spec_publishes
        if self._specs_dropped:
            specs += " · ⚠️ مسقَطة: %s" % ",".join(self._specs_dropped)
        return HealthStatus(state=HealthState.HEALTHY,
                            message=f"published={self.published_count} symbols={len(self._symbols)}{specs}",
                            details=details)

    async def snapshot(self) -> dict:
        # ٢٠٢٦-٠٩-٢٣: `spec_publishes` يُحفظ كإخوته. كان يُصفَّر عند كلّ
        # تحميلٍ حارّ، فقرأه قسم 500-550 بعد ٥٦ ثانية من تحميلٍ ودورتي
        # ٣٠٠ — فبدا صفرًا وبُني عليه بلاغُ انقطاع. عدّادٌ يُصفَّر بلا أن
        # يُعلَن زمنُ تصفيره يكذب على قارئه وإن صدَق في نفسه.
        return {"last_id": self._last_id, "published": self.published_count,
                "dropped": self.dropped_count, "spec_publishes": self.spec_publishes}

    async def restore(self, state: dict) -> None:
        self._last_id = int(state.get("last_id", 0))
        self.published_count = int(state.get("published", 0))
        self.dropped_count = int(state.get("dropped", 0))
        self.spec_publishes = int(state.get("spec_publishes", 0))
