from __future__ import annotations

from typing import Any
from clock import PulseGuard

from core.contracts.atom import AtomBase, AtomContext, HealthState, HealthStatus
from shared.financial_truth import EVENT_SHORTAGE, FinancialTruth, bind_truth

ATOM_VERSION = "1.7.0"
FAIL_CLOSED = "RESTORE_FAILED_FAIL_CLOSED"

EVENT_SESSION = "analysis.session.state"
EVENT_ACCOUNT = "platform.account.state"
EVENT_LOSS = "risk.loss_reported"
EVENT_TRADE = "platform.trade_event"
EVENT_DAY = "SYS_MARKET_DAY"   # 2026-10-17 (owner seal): the funder's day starts 00:00 Turkey (806), not UTC midnight
# ٢٠٢٦-٠٩-٠٦ (مقيس): إعادة الوزن كانت معلّقة على `platform.account.state`
# وهو **لا يصل 506 في التشغيل الحيّ** — لا نبضة دورية عنده أصلًا، فبقي
# الإفراج لا يُنشر أبدًا. نبضة الثانية مثبتة الجريان (`official_time`
# عند 516 رقم حيّ)، فتحمل التأجيلة الوحيدة بعد اكتمال الإقلاع.
EVENT_CLOCK = "SYS_SECOND"
# ٢٠٢٦-٠٩-٠٦ (مقيس مرّتين): السحب نُشر الساعة 12:32:16 بينما اكتمل
# الإقلاع 12:32:4x — أي **قبل أن يشترك 516 بثلاثين ثانية**، فضاع في
# الفراغ. عدد النبضات تخمين لا يعرف متى يجهز السامع؛ الإشارة الدقيقة
# هي بدء 516 نفسه — حامل المفتاح — والنواة تنشره بعد `start` أي بعد
# اشتراكاته. النبضة تبقى شبكة أمان متأخّرة إن غاب الحدث.
EVENT_ATOM_STARTED = "core.atom.started"
HALT_AUTHORITY_ID = 516
REVALIDATE_AFTER_PULSES = 120
EVENT_RESET = "risk.kill_switch.reset_requested"

EVENT_OUT = "risk.session_limits.state"
EVENT_HALT_REQUEST = "risk.halt.requested"
# ٢٠٢٦-٠٩-٠٦ (حكم المالك: «لازم يصير أوتوماتيك»): كان 506 يمسح خرقه
# عند تبدّل الجلسة **بصمت**، فيبقى المفتاح مكسورًا عند 516 والتجميد
# قائمًا عند 519 بلا أجل — مقيسًا: ثلاث ساعات بلا أمر بعد خرق عدّ
# أُصلح ذاتيًّا. من رفع الخرق هو من يعلن زواله.
EVENT_RELEASE_REQUEST = "risk.release.requested"
ORIGIN = "506"

ID_SESSION = "session_limits"
BREACH_LOSS = "SESSION_LOSS_LIMIT"
BREACH_TRADES = "MAX_SESSION_TRADES"
BREACH_DRAWDOWN = "EQUITY_DRAWDOWN_LIMIT"
STATUS_OK = "ok"

OPENED = "OPENED"
SESSION_UNKNOWN = "UNKNOWN"
_TIME_SESSIONS = frozenset({"asia", "london", "new_york", "overlap", "closed"})

REASON_NOT_STARTED = "NOT_STARTED"
REASON_NO_ACCOUNT = "NO_ACCOUNT_DATA"

_PERCENT = 100.0
_DP = 4


def _to_float(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result == result else None


class Atom(AtomBase):
    def __init__(self) -> None:
        self._dropped = 0
        self._context: AtomContext | None = None
        self._running = False
        self._max_loss_pct = 0.0
        self._max_trades = 0
        self._max_drawdown_pct = 0.0
        self._session = SESSION_UNKNOWN
        self._books: dict[str, dict[str, Any]] = {}
        self._pending_revalidation = False
        self._pulses = 0
        self._restore_error = ""
        self._halts = 0
        self._emitted = 0
        self._day_guard = PulseGuard(EVENT_DAY)
        self._truth = FinancialTruth(ORIGIN)

    async def initialize(self, context: AtomContext) -> None:
        self._context = context
        cfg = context.config
        self._max_loss_pct = float(cfg["max_session_loss_pct"])
        self._max_trades = int(cfg["max_session_trades"])
        self._max_drawdown_pct = float(cfg["max_equity_drawdown_pct"])
        context.subscribe(EVENT_SESSION, self._on_session)
        context.subscribe(EVENT_ACCOUNT, self._on_account)
        bind_truth(self, context, self._truth, ("equity",), after=self._on_equity)
        context.subscribe(EVENT_LOSS, self._on_loss)
        context.subscribe(EVENT_TRADE, self._on_trade)
        context.subscribe(EVENT_DAY, self._on_day)
        context.subscribe(EVENT_CLOCK, self._on_clock)
        context.subscribe(EVENT_ATOM_STARTED, self._on_atom_started)
        context.subscribe(EVENT_RESET, self._on_reset)

    async def start(self) -> None:
        self._running = True
        # لا يُفرَج هنا: الإقلاع لكل ذرّة على حدة (initialize → restore →
        # start)، و506 يسبق 516 بالرقم — فإفراجٌ يُنشر الآن يضيع قبل أن
        # يشترك من يسمعه. يُؤجَّل إلى أوّل حدث حساب، وقد اكتمل الإقلاع.
        self._pending_revalidation = True

    async def _on_atom_started(self, payload: dict[str, Any]) -> None:
        """سلطة الإيقاف صارت تسمع — الآن يُسحب ما لم يعد يُدَّعى."""
        if not self._running or not isinstance(payload, dict):
            return
        try:
            started = int(payload.get("atom_id"))
        except (TypeError, ValueError):
            return
        if started == HALT_AUTHORITY_ID:
            await self._maybe_revalidate()

    async def _on_clock(self, payload: dict[str, Any]) -> None:
        """نبضة الثانية — لا تحمل إلا التأجيلة الواحدة بعد الإقلاع."""
        if not self._running or not self._pending_revalidation:
            return
        self._pulses += 1
        if self._pulses >= REVALIDATE_AFTER_PULSES:
            await self._maybe_revalidate()

    async def _maybe_revalidate(self) -> None:
        if not self._running or not self._pending_revalidation:
            return
        self._pending_revalidation = False
        await self._revalidate_breaches()

    async def _revalidate_breaches(self) -> None:
        """يُعيد وزن كل خرق مستعاد بالحدّ **الحالي**، ويُفرج عمّا بطل.

        ٢٠٢٦-٠٩-٠٦ (حكم المالك: «لازم يصير أوتوماتيك»): الخرق قولٌ بأن
        القيمة بلغت الحدّ. فإن تغيّر الحدّ بعد إقلاع — كما رُفع سقف
        صفقات الجلسة من ١٠ إلى ٦٠ — صار القول كاذبًا، ومع ذلك كان
        يُستعاد كما هو من اللقطة ويُبقي مفتاح 516 مكسورًا إلى ما لا
        نهاية. المقيس: عشر صفقات في جلسة آسيا جمّدت الرموز الثمانية،
        ونجا التجميد إقلاعين كاملين رغم أن الحدّ الجديد لم يُبلَغ.
        """
        checks = ((BREACH_TRADES, "session_trades", self._max_trades),
                  (BREACH_LOSS, "session_loss_pct", self._max_loss_pct),
                  (BREACH_DRAWDOWN, "drawdown_pct", self._max_drawdown_pct))
        stale: list[tuple[str, str]] = []
        for account_id, book in self._books.items():
            for reason, field, limit in checks:
                # ٢٠٢٦-٠٩-٠٦ (مقيس — الحالة التي كشفت العطب): زال الخرق
                # عند تبدّل الجلسة قبل أن تُنشر شيفرة الإفراج، فبقي 516
                # ممسكًا بمفتاح لسببٍ **لم يعد أحد يدّعيه** — ولا سبيل
                # آليّ لفكّه أبدًا. فلا يكفي أن يُفرَج عمّا زال للتوّ:
                # 506 يعلن عند كل إقلاع ما لا يدّعيه من أسبابه الثلاثة،
                # فمن كفّ عن الادّعاء يسحب طلبه. والإعلان لا ضرر فيه:
                # 516 لا يفكّ إلا إن طابق السببُ ما يمسكه.
                if limit > 0 and float(book.get(field) or 0.0) >= limit:
                    continue
                book["breaches"].discard(reason)
                stale.append((account_id, reason))
        for account_id, reason in stale:
            await self._release(account_id, reason)
        for account_id in {a for a, _ in stale}:
            await self._emit(account_id, None)

    async def stop(self) -> None:
        self._running = False

    async def shutdown(self) -> None:
        await self.stop()

    def _book(self, account_id: str) -> dict[str, Any]:
        return self._books.setdefault(account_id, {
            "peak_equity": None, "equity": None, "drawdown_pct": 0.0,
            "session_loss_pct": 0.0, "session_trades": 0, "breaches": set()})

    async def _on_session(self, payload: dict[str, Any]) -> None:
        if not self._running or not isinstance(payload, dict):
            return
        # ٢٠٢٦-٠٩-٢٣ (ختم nq): ١٥٨ مغلَّفٌ بـ`live_analyzer`، وتوأمه الشمعيّ يكتب
        # **رقمه الاتّجاهيّ** مكان `signal` (`'up'`) ويحفظ مفردة الذرّة في
        # `metadata.pattern` (`'london'`) — مُعاد إنتاجه على ١٥٨ الحقيقيّة. فكان
        # هذا السطر يقرأ `up` فلا تتبدّل الجلسة أبدًا، ولا تُصفَّر خسارتها،
        # ويبقى `SESSION_LOSS_LIMIT` ممسوكًا عند ٥١٦ بلا مخرج آليّ.
        metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
        raw = metadata.get("pattern") if "pattern" in metadata else payload.get("signal", "")
        session = str(raw or "").strip().lower()
        if session not in _TIME_SESSIONS or session == self._session:
            return
        self._session = session
        cleared: list[tuple[str, str]] = []
        for account_id, book in self._books.items():
            before = set(book["breaches"])
            book["session_loss_pct"] = 0.0
            book["session_trades"] = 0
            book["breaches"].discard(BREACH_LOSS)
            book["breaches"].discard(BREACH_TRADES)
            cleared.extend((account_id, name) for name in before - book["breaches"])
        await self._emit_all(_to_float(payload.get("timestamp")))
        for account_id, reason in cleared:
            await self._release(account_id, reason)

    async def _on_account(self, payload: dict[str, Any]) -> None:
        if not self._running or not isinstance(payload, dict):
            return
        account_id = str(payload.get("account_id") or "")
        if not account_id:
            return
        book = self._book(account_id)
        book["broker"] = str(payload.get("broker") or "") or book.get("broker", "")
        # لا سحب من هنا: `platform.account.state` يصل **أثناء** الإقلاع
        # (مقيس: السحب نُشر 12:39:49 و516 لم يبدأ قبل 12:40:2x)، فيضيع
        # قبل أن يشترك حامل المفتاح. المشغّل الوحيد هو بدء 516 نفسه.
        if not self._truth.has(account_id, "equity") and self._context is not None:
            await self._context.publish(EVENT_SHORTAGE, self._truth.shortage_body(
                account_id, "equity", broker=book.get("broker", ""),
                detail="506 drawdown guard"))

    async def _on_equity(self, account_id: str) -> None:
        if not self._running:
            return
        equity = self._truth.get(account_id, "equity")
        if equity is None or equity <= 0.0:
            return
        book = self._book(account_id)
        book["equity"] = equity
        peak = book["peak_equity"]
        if peak is None or equity > peak:
            book["peak_equity"] = equity
            book["drawdown_pct"] = 0.0
        else:
            book["drawdown_pct"] = round((peak - equity) / peak * _PERCENT, _DP)
        stamp = None
        if self._max_drawdown_pct > 0.0 and book["drawdown_pct"] >= self._max_drawdown_pct:
            await self._raise(account_id, BREACH_DRAWDOWN, book["drawdown_pct"],
                              self._max_drawdown_pct, stamp)
        await self._emit(account_id, stamp)

    async def _on_loss(self, payload: dict[str, Any]) -> None:
        if not self._running or not isinstance(payload, dict):
            self._dropped += 1
            return
        if str(payload.get("completeness") or "").upper() != "COMPLETE":
            return
        account_id = payload.get("account_id")
        loss_pct = _to_float(payload.get("loss_pct"))
        if not account_id or loss_pct is None:
            self._dropped += 1
            return
        account_id = str(account_id)
        book = self._book(account_id)
        # 🔴 ٢٠٢٦-٠٩-٢٤ (ختم المالك «Nq صلح») — خسارة الجلسة صافيةٌ: الرابحة تُنقصها.
        #
        # كانت الخاسرة وحدها تُجمع (`if loss_pct > 0.0`) والرابحة تُسقط، فخسارة
        # الجلسة هنا إجماليُّ الخسائر لا صافيها — بلا حكمٍ مسجَّل بذلك. فأوقف 506
        # التداول 17:53:27 على «50٪» والحساب عند الوسيط رابحٌ اليوم 1,358.22$
        # (219 مركزًا) ومنذ 16:00 رابحٌ 971.42$. وهو بنصّ المالك: «ماعم يحسب ربحان
        # عم يعوض». الآن كلُّ نتيجةٍ بإشارتها كما في عدّاد 516 اليوميّ، فلا يُرفع
        # الخرق إلا إذا خسرت الجلسة صافيًا حدَّها. ويبقى حارس السحب من القمّة
        # (`max_equity_drawdown_pct`) قائمًا بجانبه يحمي من إرجاع الربح.
        book["session_loss_pct"] = round(book["session_loss_pct"] + loss_pct, _DP)
        stamp = _to_float(payload.get("timestamp"))
        if self._max_loss_pct > 0.0 and book["session_loss_pct"] >= self._max_loss_pct:
            await self._raise(account_id, BREACH_LOSS, book["session_loss_pct"],
                              self._max_loss_pct, stamp)
        await self._emit(account_id, stamp)

    async def _on_trade(self, payload: dict[str, Any]) -> None:
        if not self._running or not isinstance(payload, dict):
            self._dropped += 1
            return
        if str(payload.get("event_type", "")) != OPENED:
            return
        account_id = payload.get("account_id")
        if not account_id:
            self._dropped += 1
            return
        account_id = str(account_id)
        book = self._book(account_id)
        book["session_trades"] += 1
        stamp = _to_float(payload.get("timestamp"))
        if self._max_trades > 0 and book["session_trades"] >= self._max_trades:
            await self._raise(account_id, BREACH_TRADES, book["session_trades"],
                              self._max_trades, stamp)
        await self._emit(account_id, stamp)

    async def _raise(self, account_id: str, reason: str, value: float, limit: float,
                     stamp: float | None) -> None:
        if self._context is None:
            return
        book = self._book(account_id)
        if reason in book["breaches"]:
            return
        book["breaches"].add(reason)
        self._halts += 1
        body = {"reason": reason, "origin": ORIGIN, "account_id": account_id,
                "value": value, "limit": limit, "session": self._session}
        if stamp is not None:
            body["timestamp"] = stamp
        await self._context.publish(EVENT_HALT_REQUEST, body)

    async def _release(self, account_id: str, reason: str) -> None:
        """يعلن زوال خرقٍ رفعه 506 نفسه — لا أكثر.

        الإفراج **موسوم بمصدره وسببه**: 516 لا يفكّ مفتاحه إلا إن كان
        السبب الممسوك هو هذا السبب بعينه. فخرق عدّ الجلسة يزول من تلقاء
        نفسه عند تبدّل الجلسة، بينما يبقى مفتاح رُفع لخسارة يومية أو
        متتاليات مكسورًا حتى يد المالك. زر المالك العامّ لا يتغيّر.
        """
        if self._context is None:
            return
        book = self._book(account_id)
        self._context.logger.warning(
            "506 سحب طلبه حساب=%s سبب=%s جلسة=%s — لم يعد يدّعيه",
            account_id, reason, self._session)
        await self._context.publish(EVENT_RELEASE_REQUEST, {
            "account_id": account_id, "broker": book.get("broker", ""),
            "reason": reason, "origin": ORIGIN, "session": self._session,
            # ٢٠٢٦-٠٩-٠٦ (عطب مقيس): كان 516 يميّز الإفراج الآليّ بكون
            # المصدر رقمًا — وأمر المالك يمرّ من البوّابة 901 وهي رقم
            # أيضًا، فرُفض زرّه: «516 إفراج آليّ مرفوض وارد=OWNER_COMMAND
            # ممسوك=RISK_DAILY_LIMIT». العلامة صريحة الآن، ومن لا يحملها
            # فهو يد المالك ولا يُشترط عليه شيء.
            "auto_rearm": True})

    async def _on_day(self, payload: dict[str, Any]) -> None:
        if not self._running or not self._day_guard.accept(payload):
            return
        cleared: list[tuple[str, str]] = []
        for account_id, book in self._books.items():
            cleared.extend((account_id, name) for name in book["breaches"])
            book["session_loss_pct"] = 0.0
            book["session_trades"] = 0
            book["drawdown_pct"] = 0.0
            book["peak_equity"] = book["equity"]
            book["breaches"] = set()
        await self._emit_all(_to_float(payload.get("timestamp")))
        for account_id, reason in cleared:
            await self._release(account_id, reason)

    async def _on_reset(self, payload: dict[str, Any]) -> None:
        if not self._running or not isinstance(payload, dict):
            return
        account_id = str(payload.get("account_id") or "")
        if not account_id or account_id not in self._books:
            return
        self._books[account_id]["breaches"] = set()
        await self._emit(account_id, None)

    async def _emit_all(self, stamp: float | None) -> None:
        for account_id in list(self._books):
            await self._emit(account_id, stamp)

    def _state(self, account_id: str) -> dict[str, Any]:
        book = self._book(account_id)
        return {"account_id": account_id, "id": ID_SESSION, "status": STATUS_OK,
                "session": self._session, "session_loss_pct": book["session_loss_pct"],
                "session_trades": book["session_trades"],
                "max_session_loss_pct": self._max_loss_pct,
                "max_session_trades": self._max_trades,
                "equity": book["equity"], "peak_equity": book["peak_equity"],
                "equity_drawdown_pct": book["drawdown_pct"],
                "max_equity_drawdown_pct": self._max_drawdown_pct,
                "breached": sorted(book["breaches"])}

    async def _emit(self, account_id: str, stamp: float | None) -> None:
        if self._context is None:
            return
        body = self._state(account_id)
        if stamp is not None:
            body["timestamp"] = stamp
        await self._context.publish(EVENT_OUT, body)
        self._emitted += 1

    async def snapshot(self) -> dict:
        return {"version": ATOM_VERSION, "session": str(self._session or ""),
                "day_guard": self._day_guard.snapshot(),
                "books": {str(a): {"session_loss_pct": float(b["session_loss_pct"]),
                                   "session_trades": int(b["session_trades"]),
                                   "drawdown_pct": float(b["drawdown_pct"]),
                                   "breaches": sorted(b["breaches"])}
                          for a, b in self._books.items()}}

    async def restore(self, state: dict) -> None:
        books = state.get("books") if isinstance(state, dict) else None
        ok = isinstance(books, dict) and all(
            isinstance(a, str) and isinstance(b, dict)
            and isinstance(b.get("session_loss_pct"), (int, float))
            and isinstance(b.get("session_trades"), int)
            and isinstance(b.get("drawdown_pct"), (int, float))
            and isinstance(b.get("breaches"), list) for a, b in books.items())
        if not ok:
            self._restore_error = FAIL_CLOSED
            raise ValueError(FAIL_CLOSED)
        self._session = str(state.get("session") or "")
        # 2026-10-17: a guard snapshotted for the old SYS_DAY would raise on restore (name mismatch) -- it is skipped and
        # the new guard starts fresh; 806 sends no market-day pulse at boot, so nothing resets on the restart itself.
        guard = state.get("day_guard")
        if isinstance(guard, dict) and guard.get("event_name") == EVENT_DAY: self._day_guard.restore(guard)
        for account_id, b in books.items():
            book = self._book(account_id)
            book.update({"session_loss_pct": float(b["session_loss_pct"]),
                         "session_trades": int(b["session_trades"]),
                         "drawdown_pct": float(b["drawdown_pct"]),
                         "breaches": set(b["breaches"])})
        self._restore_error = ""

    async def health_check(self) -> HealthStatus:
        if not self._running:
            return HealthStatus(state=HealthState.UNHEALTHY, message=REASON_NOT_STARTED)
        if self._restore_error:
            return HealthStatus(state=HealthState.DEGRADED, message=self._restore_error,
                                details={"restore_error": self._restore_error})
        breached = {a: sorted(b["breaches"]) for a, b in self._books.items()
                    if b["breaches"]}
        details = {"session": self._session, "accounts": len(self._books),
                   "halts": self._halts, "emitted": self._emitted,
                   "books": {a: self._state(a) for a in self._books}}
        if not any(b["equity"] is not None for b in self._books.values()):
            return HealthStatus(state=HealthState.DEGRADED, message=REASON_NO_ACCOUNT,
                                details=details)
        # ٢٠٢٦-٠٩-١٨ (ختم NQ) — العيارات الثلاثة كانت غير معلَنة، والمالك
        # رفع سقف الجلسة اليوم من ٣٪ إلى ١٠٪ ولا شاشة تُظهر السارية. وهذه
        # الذرّة هي التي أوقفت التداول اثنتي عشرة ساعة ونصفًا بـ
        # `SESSION_LOSS_LIMIT` — فرقمُها هو ما يفتح السوق أو يغلقه.
        dials = " | عيار: خسارة=%g%% صفقات=%d سحب=%g%%" % (
            self._max_loss_pct, self._max_trades, self._max_drawdown_pct)
        if breached:
            return HealthStatus(state=HealthState.DEGRADED,
                                message="session-limit breached: %s%s"
                                        % (",".join(breached), dials),
                                details=details)
        return HealthStatus(state=HealthState.HEALTHY,
                            message="session=%s accounts=%d%s"
                                    % (self._session, len(self._books), dials),
                            details=details)
