from __future__ import annotations

import asyncio
import threading
import time
from collections import OrderedDict, deque
from pathlib import Path
from typing import Any

from core.contracts.atom import AtomBase, AtomContext, HealthState, HealthStatus
from shared import owner_trades

ATOM_VERSION = "1.3.0"
# ٢٠٢٦-١٠-٢٦ (قانون صفقات المالك، ختم «NQ»: «صفقات انا بفتحها مالها علاقة بل منظومة ابدا ولا بصير يقيس عليها ولا
# يسجلها»): ظهور مركز المالك واختفاؤه لا يُكتبان في السجلّ ولا يُعدّان في `events_in` — بالتمييز الواحد في
# `shared/owner_trades.py`. وحدهما يحملان صفقته: أحداث الصفقات للمنظومة من مصدرها، والرفض والإقرار والفشل
# لأوامرها. وما كُتب قبل اليوم يبقى كما هو — لا حذف.
# v1.1.0 (2026-08-27, item 13/27 of the 27-atom review -- exceeding the
# daily line cap, a real TOCTOU): _write checked self._lines_today >=
# self._max_lines_per_day, then awaited the actual file write
# (asyncio.to_thread(self._append, ...) -- a genuine suspension, the
# write runs on a worker thread), and only incremented self._lines_today
# AFTER that write returned. Six different event types feed _write, each
# its own subscription/consumer task (V3.0 mailbox) -- two can race right
# at the cap boundary, both pass the stale check before either
# increments, both write, and the cap is exceeded by however many raced
# through concurrently. Fixed with an asyncio.Lock serializing the whole
# check -> write -> increment section; _append's own threading.Lock
# already serialized the actual file bytes, so this closes the gap
# without changing I/O behavior.

EVENT_TRADE = "platform.trade_event"
EVENT_APPEARED = "platform.position.appeared"
EVENT_VANISHED = "platform.position.vanished"
EVENT_REJECTED = "execution.order.rejected"
EVENT_ACK = "execution.command.ack"
EVENT_CMD_FAILED = "execution.command.failed"
EVENT_STATE = "logs.trades.state"

REASON_NOT_STARTED = "NOT_STARTED"
REASON_WRITE_FAILED = "LOG_WRITE_FAILED"

# فارق يُعدّ طابعًا مستقبليًّا، ودوريّة نطقه.
_FUTURE_STAMP_TOLERANCE_S = 60.0
_STAMP_LOG_EVERY_S = 60.0

#: ⚠️ كانت `{"BUY": "BUY", "SELL": "SELL"}` — خريطةٌ وُضعت للتعريب ولم
#: تُملأ قطّ، فبدت مطبَّقةً وهي لا تفعل شيئًا. مُلئت بختم المالك ٢٠٢٦-٠٩-١٩.
_SIDE_AR = {"BUY": "شراء", "SELL": "بيع"}
_SEEN_ROWS_CAP = 500
_INT_DISPLAY_LIMIT = 10 ** 15


def _to_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result == result else None


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


def _num(value: Any) -> str | None:
    f = _to_float(value)
    if f is None:
        return None
    if f == int(f) and abs(f) < _INT_DISPLAY_LIMIT:
        return str(int(f))
    return ("%.6f" % f).rstrip("0").rstrip(".")


def _signed(value: Any) -> str | None:
    f = _to_float(value)
    if f is None:
        return None
    text = _num(f) or "0"
    return text if f < 0 else "+" + text


def _side(value: Any) -> str | None:
    raw = str(value or "").strip().upper()
    if not raw:
        return None
    return _SIDE_AR.get(raw, raw)


def _text(value: Any) -> str | None:
    raw = str(value or "").strip()
    return raw or None


#: ── تعريبُ السجلّ (ختم المالك `nq` ٢٠٢٦-٠٩-١٩) ─────────────────────────
#:
#: المالك لا يقرأ الإنكليزيّة، وهذا **سجلُّ ماله**: هو الذي يقول لماذا
#: رُفض أمر. والمقيس أنّه كان إنكليزيًّا بالكامل — ١٬٧٥٤ سطرًا، عربيُّه صفر.
#:
#: ⛔ ولا يُعرَّب إلّا ما يُكتب في الملفّ. أسماءُ الأحداث ومفاتيحُ الحمولة
#:    وحقولُ اللقطة ومميّزاتُ النوع (`kind`) تبقى حرفًا — تقرؤها اللوحةُ
#:    والذرّاتُ الأخرى، وتعريبُها يقطع وصلةً لا يترجم كلمة.

#: رؤوسُ الأسطر — مقيسةٌ من سجلّات ثلاثة أيّام، لا مُخمَّنة.
HEAD_AR = {
    "TRADE_OPENED:": "فُتحت صفقة:",
    "TRADE_CLOSED:": "أُغلقت صفقة:",
    "PARTIAL_CLOSE:": "إغلاقٌ جزئيّ:",
    "POSITION_APPEARED_ON_PLATFORM:": "ظهر مركزٌ على المنصّة:",
    "POSITION_VANISHED_FROM_PLATFORM:": "اختفى مركزٌ من المنصّة:",
}

#: أسبابُ الرفض كما تصل من الحمولة — أُخذت من ‏١٠٬٢٢٢ سطرَ رفضٍ حقيقيّ.
#: وما ليس هنا **يمرّ كما هو**: ترجمةٌ ناقصةٌ خيرٌ من سببٍ يضيع.
REASON_AR = {
    "CLOCK_NOT_SYNCED": "الساعة غير متزامنة",
    "REFERENCE_NOT_USABLE": "المرجع غير صالح",
    "STOP_BELOW_FLOOR": "الوقف دون الأرضيّة",
    "NO_SYMBOL_SPECS": "لا مواصفاتٍ للرمز",
    "SYMBOL_RESOLUTION_TIMEOUT": "انتهت مهلة حلّ الرمز",
    "RECONCILIATION_NOT_MATCHED": "المصالحة لم تُطابق",
    "STOP_FLOOR_BREAKS_REWARD": "أرضيّة الوقف تكسر العائد",
    "DUPLICATE_REQUEST_ID": "معرّف طلبٍ مكرّر",
    "RISK_OFF_BUDGET": "خارج ميزانيّة المخاطرة",
    "SPREAD_TOO_WIDE": "السبريد واسعٌ جدًّا",
    "EXPOSURE_STATE_NOT_USABLE": "حالة الانكشاف غير صالحة",
    "SL": "وقفُ خسارة",
    "SYSTEM": "النظام",
}

#: تسمياتُ الحقول داخل السطر.
FIELD_AR = {
    "ticket": "تذكرة", "account": "حساب", "volume": "حجم",
    "entry": "دخول", "exit": "خروج", "profit": "ربح",
    "commission": "عمولة", "swap": "تبييت", "fee": "رسم",
    "request": "طلب", "reason": "السبب",
}


#: الفعلُ والحالةُ كما يصلان من الحمولة — مقيسان من ‏١٬٠٥٠ سطرَ نتيجة.
ACTION_AR = {
    "OPEN": "فتح", "CLOSE": "إغلاق", "CLOSE_PARTIAL": "إغلاقٌ جزئيّ",
    "MODIFY_SL": "تعديلُ وقف", "BUY": "شراء", "SELL": "بيع",
}
STATUS_AR = {"DONE": "تمّ", "ACK": "أُقرّ", "FAILED": "فشل"}


def _reason_ar(value: str | None) -> str | None:
    """يترجم السبب إن عُرف، ويُمرّره حرفًا إن لم يُعرف — ولا يبتلعه."""
    if not value:
        return None
    key = value.strip().upper()
    known = REASON_AR.get(key)
    if known:
        return known
    # رموزُ الوسيط تُقرأ بأرقامها: الرقم هو الدليل ولا يُترجَم.
    if key.startswith("RETCODE_"):
        return "رمزُ الوسيط %s" % key[len("RETCODE_"):]
    return value


def _lookup(table: dict[str, str], value: Any) -> str | None:
    """يترجم من جدولٍ، ويُمرّر المجهول حرفًا — لا يُسقطه."""
    raw = str(value or "").strip()
    if not raw:
        return None
    return table.get(raw.upper(), raw)


def _field(name: str, value: Any) -> str | None:
    """`حقل قيمة` بالعربيّة، أو `None` إن لم تكن ثمّة قيمة."""
    if value in (None, ""):
        return None
    return "%s %s" % (FIELD_AR.get(name, name), value)


def _join(*parts: str | None) -> str:
    return " · ".join(p for p in parts if p)


def _pair(*parts: str | None) -> str | None:
    joined = " ".join(p for p in parts if p)
    return joined or None


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
        self._running = False
        self._dir = Path("var/logs")
        self._prefix = "trades"
        self._state_tail = 12
        self._max_lines_per_day = 20000
        self._file_lock = threading.Lock()
        self._write_lock = asyncio.Lock()
        self._day = ""
        self._lines_today = 0
        self._total_lines = 0
        self._suppressed_today = 0
        self._cap_announced = False
        self._io_failures = 0
        self._last_io_error = ""
        self._last_lines: deque[str] = deque(maxlen=12)
        self._seen_rows: OrderedDict[int, bool] = OrderedDict()
        self.events_in = 0
        self.future_stamp_count = 0
        self._last_stamp_log_at = 0.0

    async def initialize(self, context: AtomContext) -> None:
        self._context = context
        cfg = _rebased_config(context.config)
        self._dir = Path(str(cfg["dir"]))
        self._prefix = str(cfg["file_prefix"])
        self._state_tail = int(cfg["state_tail"])
        self._max_lines_per_day = int(cfg["max_lines_per_day"])
        self._last_lines = deque(self._last_lines, maxlen=self._state_tail)
        self._dir.mkdir(parents=True, exist_ok=True)
        context.subscribe(EVENT_TRADE, self._on_trade)
        context.subscribe(EVENT_APPEARED, self._on_appeared)
        context.subscribe(EVENT_VANISHED, self._on_vanished)
        context.subscribe(EVENT_REJECTED, self._on_rejected)
        context.subscribe(EVENT_ACK, self._on_ack)
        context.subscribe(EVENT_CMD_FAILED, self._on_cmd_failed)

    async def start(self) -> None:
        if self._running or self._context is None:
            return
        self._running = True

    async def stop(self) -> None:
        self._running = False

    async def shutdown(self) -> None:
        await self.stop()

    def _today_path(self, day: str) -> Path:
        return self._dir / f"{self._prefix}-{day}.log"

    def _stamp(self, payload: dict[str, Any]) -> float:
        """ساعة السطر هي ساعتنا — كما تَعِد ترويسة الملف حرفيًّا.

        كانت تُؤخذ من `payload["timestamp"]`، وترويسة الملف تقول
        `all times machine-local` — فتكذب حين يأتي ناشرٌ بساعة أخرى. مقيس
        ٢٠٢٦-٠٩-١٦ وأبلغ به قسم الصفقات: سطران متجاوران لنفس التذكرة،
        `POSITION_VANISHED 14:06:03` ثم `TRADE_CLOSED 17:06:02` — ثلاث ساعات
        فرقًا لأنّ أحدهما بساعة خادم الوسيط. فصار السجلّ بساعة واحدة يُقرأ
        ترتيبه، وانحرافُ الناشر يُعدّ ويُنطق بدل أن يتسلّل إلى الطابع.
        """
        now = time.time()
        stamp = _to_float(payload.get("timestamp")) if isinstance(payload, dict) else None
        skew = _clock_skew(payload, stamp, now)
        if skew is not None and skew > _FUTURE_STAMP_TOLERANCE_S:
            stamp = now + skew
            self.future_stamp_count += 1
            if now - self._last_stamp_log_at >= _STAMP_LOG_EVERY_S:
                self._last_stamp_log_at = now
                context = self._context
                logger = getattr(context, "logger", None) if context else None
                if logger is not None:
                    try:
                        logger.warning(
                            "720 سجل الصفقات: طابع ناشرٍ من المستقبل فرق=%+.0f"
                            " ثانية (%.2f ساعة) — السطر يُكتب بساعتنا. مجموع=%d",
                            stamp - now, (stamp - now) / 3600.0,
                            self.future_stamp_count)
                    except Exception:  # noqa: BLE001 — لا يسقط سجلّ بسبب سجلّ
                        pass
        return now

    def _append(self, day: str, text: str) -> None:
        with self._file_lock:
            path = self._today_path(day)
            fresh = not path.exists()
            with open(path, "a", encoding="utf-8") as fh:
                if fresh:
                    fh.write("- QUANT_NQ · سجلّ الصفقات · يوم %s-%s-%s "
                             "· كلُّ الأوقات بتوقيت الجهاز -\n"
                             % (day[0:4], day[4:6], day[6:8]))
                fh.write(text + "\n")

    async def _write(self, kind: str, when: float, body: str) -> None:
        if self._context is None:
            return
        # v1.1.0: the whole check -> write -> increment section is
        # serialized -- the write below awaits (asyncio.to_thread), a real
        # suspension point six different event types can race through.
        async with self._write_lock:
            day = time.strftime("%Y%m%d")
            if day != self._day:
                self._day = day
                self._lines_today = 0
                self._suppressed_today = 0
                self._cap_announced = False
            if self._lines_today >= self._max_lines_per_day:
                self._suppressed_today += 1
                if not self._cap_announced:
                    self._cap_announced = True
                    try:
                        await asyncio.to_thread(
                            self._append, day,
                            "⛔ بلغ السجلّ سقفَه اليوميّ (%d سطرًا) — ما بقي "
                            "من أحداث اليوم يُعدّ ولا يُكتب (‏عددُه في صحّة "
                            "الذرّة ٧٢٠ تحت `suppressed_today`)"
                            % self._max_lines_per_day)
                    except OSError:
                        pass
                return
            line = "%s | %s" % (
                time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(when)), body)
            try:
                await asyncio.to_thread(self._append, day, line)
            except OSError as exc:
                self._io_failures += 1
                self._last_io_error = str(exc)
                return
            self._last_io_error = ""
            self._lines_today += 1
            self._total_lines += 1
            self._last_lines.append(line)
            await self._context.publish(EVENT_STATE, {
                "file": str(self._today_path(day)),
                "date": day,
                "kind": kind,
                "lines_today": self._lines_today,
                "total_lines": self._total_lines,
                "last_lines": list(self._last_lines),
                "timestamp": when})

    def _remember_row(self, row_id: int) -> bool:
        seen = row_id in self._seen_rows
        self._seen_rows[row_id] = True
        self._seen_rows.move_to_end(row_id)
        while len(self._seen_rows) > _SEEN_ROWS_CAP:
            self._seen_rows.popitem(last=False)
        return seen

    async def _on_trade(self, payload: dict[str, Any]) -> None:
        if not self._running or not isinstance(payload, dict):
            return
        self.events_in += 1
        kind = str(payload.get("event_type") or "").strip().upper()
        row_id = payload.get("source_row_id")
        revision = isinstance(row_id, int) and self._remember_row(row_id)
        ticket = _text(payload.get("ticket"))
        account = _text(payload.get("account_id"))
        symbol = _text(payload.get("symbol"))
        side = _side(payload.get("side"))
        volume = _num(payload.get("volume"))
        if revision:
            body = _join(
                "اكتملت كلفةُ الصفقة:",
                _field("ticket", ticket),
                _field("commission", _num(payload.get("commission"))),
                _field("swap", _num(payload.get("swap"))),
                _field("fee", _num(payload.get("fee"))),
                _field("profit", _signed(payload.get("profit"))))
            await self._write("costs", self._stamp(payload), body)
            return
        # ⛔ المفتاحُ الإنكليزيّ يبقى مفتاحًا (‏يأتي من `event_type` في
        #    الحمولة)، والمعروضُ وحده يُعرَّب.
        head = HEAD_AR.get(
            {"OPENED": "TRADE_OPENED:", "CLOSED": "TRADE_CLOSED:",
             "PARTIAL": "PARTIAL_CLOSE:"}.get(kind, ""),
            "حدثُ صفقة (%s):" % (kind or "؟"))
        entry = _num(payload.get("entry_price"))
        exit_price = _num(payload.get("exit_price"))
        profit = _signed(payload.get("profit"))
        reason = _text(payload.get("reason"))
        if kind == "OPENED":
            detail = _join(_field("volume", volume),
                           f"@ {entry}" if entry else None)
        else:
            detail = _join(_field("volume", volume),
                           _field("entry", entry),
                           _field("exit", exit_price),
                           _field("profit", profit))
        body = _join(
            "%s %s" % (head, _pair(side, symbol) or "؟"),
            detail or None,
            _field("ticket", ticket),
            _field("account", account),
            ("السبب: %s" % _reason_ar(reason))
            if reason and kind != "OPENED" else None)
        await self._write(kind.lower() or "trade", self._stamp(payload), body)

    async def _position_line(self, payload: dict[str, Any], head: str,
                             kind: str, with_profit: bool) -> None:
        if not self._running or not isinstance(payload, dict) or owner_trades.is_owner(payload):
            return
        self.events_in += 1
        body = _join(
            "%s %s" % (HEAD_AR.get(head, head),
                       _pair(_side(payload.get("side")),
                             _text(payload.get("symbol"))) or "؟"),
            _field("volume", _num(payload.get("volume"))),
            ("@ %s" % _num(payload.get("entry_price")))
            if not with_profit and _num(payload.get("entry_price")) else None,
            ("آخرُ ربحٍ عائم %s" % _signed(payload.get("profit")))
            if with_profit and _signed(payload.get("profit")) is not None else None,
            _field("ticket", _text(payload.get("ticket"))),
            _field("account", _text(payload.get("account_id"))))
        await self._write(kind, self._stamp(payload), body)

    async def _on_appeared(self, payload: dict[str, Any]) -> None:
        await self._position_line(payload, "POSITION_APPEARED_ON_PLATFORM:", "appeared", False)

    async def _on_vanished(self, payload: dict[str, Any]) -> None:
        await self._position_line(payload, "POSITION_VANISHED_FROM_PLATFORM:", "vanished", True)

    async def _on_rejected(self, payload: dict[str, Any]) -> None:
        if not self._running or not isinstance(payload, dict):
            return
        self.events_in += 1
        body = _join(
            "رُفض أمر: %s" % (_pair(_side(payload.get("side")),
                                    _text(payload.get("symbol"))) or "؟"),
            _field("volume", _num(payload.get("volume"))),
            "السبب: %s" % (_reason_ar(_text(payload.get("reason"))) or "؟"),
            _field("request", _text(payload.get("request_id"))),
            _field("account", _text(payload.get("account_id"))))
        await self._write("rejected", self._stamp(payload), body)

    async def _result_line(self, payload: dict[str, Any], verdict: str, kind: str) -> None:
        if not self._running or not isinstance(payload, dict):
            return
        self.events_in += 1
        status = _text(payload.get("status"))
        reason = _text(payload.get("reason"))
        body = _join(
            "نتيجةُ أمر: %s%s" % (
                verdict,
                " (%s)" % _lookup(STATUS_AR, status) if status else ""),
            _lookup(ACTION_AR, payload.get("action")),
            _pair(_side(payload.get("side")), _text(payload.get("symbol"))),
            _field("volume", _num(payload.get("volume"))),
            _field("ticket", _text(payload.get("ticket"))),
            ("السبب: %s" % _reason_ar(reason)) if reason else None,
            _field("request", _text(payload.get("request_id"))),
            _field("account", _text(payload.get("account_id"))))
        await self._write(kind, self._stamp(payload), body)

    async def _on_ack(self, payload: dict[str, Any]) -> None:
        await self._result_line(payload, "نُفِّذ على المنصّة", "ack")

    async def _on_cmd_failed(self, payload: dict[str, Any]) -> None:
        await self._result_line(payload, "فشل", "failed")

    async def health_check(self) -> HealthStatus:
        if not self._running:
            return HealthStatus(state=HealthState.UNHEALTHY, message=REASON_NOT_STARTED)
        day = time.strftime("%Y%m%d")
        details: dict[str, Any] = {
            "file": str(self._today_path(day)),
            "events_in": self.events_in,
            "lines_today": self._lines_today if day == self._day else 0,
            "suppressed_today": self._suppressed_today if day == self._day else 0,
            "total_lines": self._total_lines,
            "io_failures": self._io_failures,
            "last_io_error": self._last_io_error,
            "last_lines": list(self._last_lines)}
        if self._last_io_error:
            return HealthStatus(state=HealthState.DEGRADED,
                                message=REASON_WRITE_FAILED, details=details)
        if self._total_lines == 0:
            return HealthStatus(
                state=HealthState.HEALTHY,
                message="جاهزٌ — بانتظار أوّل صفقةٍ أو أمرٍ حقيقيّ · أسطر=٠",
                details=details)
        return HealthStatus(
            state=HealthState.HEALTHY,
            message="اليوم=%d الإجماليّ=%d" % (details["lines_today"],
                                               self._total_lines),
            details=details)

    async def snapshot(self) -> dict[str, Any]:
        # الإصدار في اللقطة: أداة القياس تقرأ الإصدار الحيّ منها، وغيابه
        # كان يُظهر هذه الذرّة وحدها بـ«v؟» في تدقيق القسم.
        return {"version": ATOM_VERSION,
                "day": self._day, "lines_today": self._lines_today,
                "total_lines": self._total_lines,
                "suppressed_today": self._suppressed_today,
                "last_lines": list(self._last_lines),
                "seen_rows": list(self._seen_rows)[-_SEEN_ROWS_CAP:],
                "events_in": self.events_in}

    async def restore(self, state: dict[str, Any]) -> None:
        day = str(state.get("day") or "")
        today = time.strftime("%Y%m%d")
        self._total_lines = int(state.get("total_lines", 0))
        self.events_in = int(state.get("events_in", 0))
        if day == today:
            self._day = day
            self._lines_today = int(state.get("lines_today", 0))
            self._suppressed_today = int(state.get("suppressed_today", 0))
        for line in list(state.get("last_lines") or [])[-self._state_tail:]:
            self._last_lines.append(str(line))
        for row_id in state.get("seen_rows") or []:
            if isinstance(row_id, int):
                self._seen_rows[row_id] = True
