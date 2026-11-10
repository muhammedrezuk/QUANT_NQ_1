from __future__ import annotations

import asyncio
import time
from typing import Any

import transport
from core.contracts.atom import AtomBase, AtomContext, HealthState, HealthStatus
from ctrader_stream_state import ACTIVE, DEAD, NEVER_SEEN, STALE, StreamTracker
from shared import fix_session as fx
from shared.market_hours import CLOSED, market_state

ATOM_VERSION = "1.10.0"
# 🔴 ٢٠٢٦-٠٩-٢٦ (ختم المالك «Nq» · «كل اسبوع نفس قصة عطلة، مافي غير بتكوين شغال») —
# كلّ عطلة أسبوع تعلن هذه الذرّة الرموز الستّة `FIX_SYMBOLS_OUT_OF_SESSION` وتصفرّ، وهي
# مغلقةٌ عند الوسيط لا معطوبة. الآن تسمع `market.symbol_specs` (جلسات الوسيط نفسه من
# الإكسبرت v3.17)، فالرمز الساكن في سوقٍ مغلقة لا يُعدّ ميتًا ولا متأخّرًا، ويُسمّى «السوق
# مغلق». والرمز الساكن في سوقٍ مفتوحة يبقى عطلًا كما كان، وجلساتٌ مجهولة لا تُسكت شيئًا.
# v1.5.0 (٢٠٢٦-٠٩-٠٩، ختم المالك `NQ`): **اللقطة صارت تتكرّر.** كان الاشتراك
# يُرسل مرّة واحدة عند وصول قائمة الأوراق، فتصل لقطة `W` واحدة ثمّ لا تعود
# أبدًا، والدفتر بعدها تزايديّ محض بينما سي‑تريدر لا يحذف ما هجره. المقيس
# حيًّا بعد إقلاع نظيف: العمق من 14 إلى 371 في عشرين دقيقة، والطرفان اختلّا
# (450 عرضًا مقابل 26 طلبًا) فتقاطعا، ورفض 112 من ٢٪ إلى ١٦٪. عولجت مرّتين
# بيد المالك (stop ثمّ start) — وهذا العلاج نفسه بلا يد. التفصيل عند
# `_refresh_subscriptions`.
# v1.4.0 (2026-08-27, item 20/27 of the 27-atom review -- a synchronous
# TLS connect freezes the loop, no connection timeout): _connect() called
# stream.connect() (TCP handshake + TLS handshake, up to
# transport.DEFAULT_TIMEOUT_S=5.0s in the ordinary case -- and DNS
# resolution inside socket.create_connection has NO timeout bound at
# all) directly on the atom's own coroutine, i.e. on the shared core
# event loop. transport/client.py's own docstring states the design
# principle this violated: "an unbounded outbound call is how a
# pulse-driven atom turns into a hung one" -- true here even bounded,
# since ANY multi-second block on the shared loop stalls every other
# atom. _teardown() (called as _connect()'s own first line) had the same
# problem via stream.close()'s thread.join(timeout=...). Both now run
# via asyncio.to_thread.
EVENT_TIME = "SYS_SECOND"
EVENT_MT5_SPECS = "market.symbol_specs"
EVENT_RAW = "feed.ctrader.raw"
EVENT_SPECS = "market.ctrader.symbol_specs"
EVENT_HEARTBEAT = "feed.ctrader.heartbeat"
EVENT_STATE = "feed.ctrader.state"

STATE_DOWN, STATE_CONNECTING, STATE_READY = "DOWN", "CONNECTING", "READY"
MD_REQ_PREFIX = "MD-"


class Atom(AtomBase):
    """cTrader price feed over FIX -- no desktop platform, no bridge file.

    Publishes exactly the events the archived atom 617 published, same payload
    shape, so every consumer downstream (613, 106, 521, 103, 150 ...) keeps
    working untouched while the source underneath changes.

    Two facts this atom refuses to invent: the symbol identity (cTrader
    addresses symbols by NUMBER, taken from the venue's own SecurityList) and
    the time of a price (taken from the message that carried it, never from
    this machine's clock).
    """

    def __init__(self) -> None:
        self._context: AtomContext | None = None
        self._running = False
        self._task: asyncio.Task | None = None
        self._stream: transport.StreamSession | None = None
        self._session: fx.FixSession | None = None
        self._buffer = b""
        self._by_id: dict[str, str] = {}
        self._by_name: dict[str, str] = {}
        self._link = STATE_DOWN
        self._last_error = ""
        self._auth_failed = False
        self._ever_logged_on = False
        self._last_sent = 0.0
        self._sequence = 0
        self._fabric_gap = False
        self._connects = 0
        self._updates = self._heartbeats = self._unknown = 0
        self._tracker = StreamTracker({"tick": 30.0, "depth": 30.0, "spec": 600.0}, 120.0)
        self._official_time = 0.0
        # ساعتُنا لحظة وصول الرسالة من المقبس. سبعة مستهلكين يقرؤون
        # `received_at` (112 · 102 · 464 · 521 · 582 · 613 · 623) ومصدر
        # سي‑تريدر لم يضعه قطّ، فكان العمر الوحيد المتاح هو طابع الوسيط:
        # لا يفرّق بين «الوسيط لم يرسل» و«وصل عندنا وتأخّر». هذا الحقل
        # يفصل المجالين، وبه وحده يُقاس أين تضيع الثواني.
        self._received_at = 0.0
        # فجوة نبض المضخّة. `poll_interval_s` خمسة أجزاء من الألف، فأيّ
        # فجوة أكبر بكثير ليست عيارًا بل حلقةً مشغولة بغيرنا: التغذية
        # تنتظر دورها. هذا الرقم يفصل «الوسيط بطيء» عن «لم يُعطَ لنا وقت».
        self._pump_last_mono = 0.0
        self._pump_gap_ewma = 0.0
        self._pump_gap_max = 0.0
        self._wanted: list[str] = []
        self._account = ""
        self._broker = ""
        self._password_key = ""
        self._market_depth = 0
        self._resubscribe_every_s = 0.0   # 0 = لا تجديد (السلوك قبل العيار)
        self._last_subscribe_at = 0.0
        self._resubscribes = 0
        self._poll_interval_s = 0.005
        self._reconnect_backoff_s = 5.0
        self._heartbeat_s = 30
        self._host = ""
        self._port = 0
        self._use_tls = True
        #: جلسات التداول لكلّ رمز كما يعلنها الوسيط (من مواصفات ٦١٨) — بالاسم.
        self._hours: dict[str, dict[str, Any]] = {}

    async def initialize(self, context: AtomContext) -> None:
        self._context = context
        cfg = context.config
        self._host = str(cfg["host"])
        self._port = int(cfg["port"])
        self._use_tls = bool(cfg["use_tls"])
        # v1.3.0 (2026-08-25): the FEED CREDENTIAL is not a trading identity.
        # Ticks used to stamp account_id = the FIX username (6175701, the live
        # quote account), so the WHOLE decision chain ran on a scope no
        # execution account matches -- 601 would reject any passing decision
        # with ACCOUNT_ID_MISMATCH (measured). identity_account_id declares
        # the trading account the ticks belong to.
        # v1.3.1: the two roles are SEPARATE fields -- _login goes to the FIX
        # session (must equal the SenderCompID's account or the broker refuses
        # the logon: measured live, FIX_LOGON_REFUSED "Username does not match
        # SenderCompID"), _account stamps the published identity only.
        self._login = str(cfg["username"])
        self._account = str(cfg.get("identity_account_id") or cfg["username"])
        self._broker = str(cfg["broker"])
        self._password_key = str(cfg["password_secret_key"])
        self._wanted = [str(name).strip() for name in cfg["symbols"] if str(name).strip()]
        self._market_depth = int(cfg["market_depth"])
        self._resubscribe_every_s = float(cfg.get("resubscribe_every_s", 0.0) or 0.0)
        self._heartbeat_s = int(cfg["heartbeat_s"])
        self._poll_interval_s = float(cfg["poll_interval_s"])
        self._reconnect_backoff_s = float(cfg["reconnect_backoff_s"])
        self._tracker = StreamTracker(
            {"tick": float(cfg["tick_stale_after_s"]), "depth": float(cfg["depth_stale_after_s"]),
             "spec": float(cfg["specs_stale_after_s"])}, float(cfg["dead_after_s"]))
        self._session = fx.FixSession(str(cfg["sender_comp_id"]), str(cfg["target_comp_id"]),
                                      str(cfg["sub_id"]), self._login, self._heartbeat_s)
        context.subscribe(EVENT_TIME, self._on_pulse)
        context.subscribe(EVENT_MT5_SPECS, self._on_mt5_specs)

    async def _on_mt5_specs(self, payload: dict[str, Any]) -> None:
        """جلسات الوسيط لكلّ رمز — ذاكرةٌ تُملأ ولو قبل البدء، ولا تمسّ التغذية."""
        if not isinstance(payload, dict):
            return
        rows = payload.get("symbols")
        for row in rows if isinstance(rows, list) else []:
            if not isinstance(row, dict):
                continue
            account = str(row.get("account_id") or payload.get("account_id") or "")
            symbol = str(row.get("symbol") or "")
            if symbol and (not account or account == self._account):
                self._hours[symbol] = {field: row.get(field) for field in (
                    "trade_sessions", "server_gmt_offset", "trade_mode")}

    def _closed_now(self, names: set[str]) -> set[str]:
        """من هذه الرموز: ما سوقُه مغلقة الآن بجلسات الوسيط."""
        now = self._official_time or time.time()
        return {name for name in names if market_state(self._hours.get(name), now) == CLOSED}

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._auth_failed = False
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._running = False
        if self._task is not None and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None
        await self._teardown()

    async def shutdown(self) -> None:
        await self.stop()

    async def _teardown(self) -> None:
        stream, self._stream = self._stream, None
        if stream is not None:
            await asyncio.to_thread(stream.close)
        self._link = STATE_DOWN
        self._buffer = b""

    def _password(self) -> str:
        """The atom names a key; it never holds or stores the value (rule 8)."""
        from security import get_secret_provider
        return str(get_secret_provider().get_secret(self._password_key) or "")

    async def _run(self) -> None:
        while self._running:
            try:
                if self._auth_failed:
                    # A refused logon is not a flaky link. Retrying it on a loop
                    # is how a live account gets locked out by its own broker,
                    # so the atom stops and says so until a human restarts it.
                    await asyncio.sleep(self._reconnect_backoff_s)
                    continue
                if self._stream is None or not self._stream.connected:
                    await self._connect()
                await self._pump()
                await self._refresh_subscriptions()
                await asyncio.sleep(self._poll_interval_s)
            except asyncio.CancelledError:
                return
            except Exception as exc:  # noqa: BLE001
                self._last_error = "%s: %s" % (type(exc).__name__, exc)
                if self._context is not None:
                    self._context.logger.warning("622 loop error: %s", self._last_error)
                await self._teardown()
                await self._announce(STATE_DOWN, {"error": self._last_error})
                await asyncio.sleep(self._reconnect_backoff_s)

    async def _connect(self) -> None:
        await self._teardown()
        self._link = STATE_CONNECTING
        password = self._password()
        if not password:
            raise transport.TransportError("NO_PASSWORD_IN_VAULT:%s" % self._password_key)
        stream = transport.StreamSession(
            self._host, self._port, use_tls=self._use_tls,
            max_buffer_bytes=0,
        )
        # v1.4.0: TCP connect + TLS handshake (up to several seconds, DNS
        # resolution unbounded) moved off the shared event loop.
        await asyncio.to_thread(stream.connect)
        self._stream = stream
        self._session = fx.FixSession(self._session.sender_comp_id, self._session.target_comp_id,
                                      self._session.sub_id, self._login, self._heartbeat_s)
        now = time.time()
        stream.send(self._session.logon(password, now))
        self._last_sent = now
        self._connects += 1
        if self._context is not None:
            self._context.logger.warning(
                "622 logon sent host=%s:%s tls=%s sender=%s user=%s connects=%s",
                self._host, self._port, self._use_tls, self._session.sender_comp_id,
                self._login, self._connects)
        self._tracker.rebase()
        await self._announce(STATE_CONNECTING, {"connects": self._connects})

    async def _pump(self) -> None:
        stream, session = self._stream, self._session
        if stream is None or session is None:
            return
        # The session beat is serviced BEFORE the backlog, never after. Measured
        # 2026-08-21: publishing a burst took longer than the 30s heartbeat
        # window, the venue stopped hearing from us and cut the session every
        # few minutes. A feed must keep its own line alive before it feeds
        # anyone else.
        now = time.time()
        if session.logged_on and now - self._last_sent >= self._heartbeat_s:
            stream.send(session.heartbeat(now))
            self._last_sent = now
        pulse = time.monotonic()
        if self._pump_last_mono:
            gap = pulse - self._pump_last_mono
            self._pump_gap_ewma = (self._pump_gap_ewma * 0.99 + gap * 0.01
                                   if self._pump_gap_ewma else gap)
            if gap > self._pump_gap_max:
                self._pump_gap_max = gap
        self._pump_last_mono = pulse
        drained = stream.drain()
        # يُختم هنا لا عند بناء الحمولة: كلّ ما تُخرجه `fx.frame` أدناه
        # اكتمل في هذه السحبة (المتبقّي في `_buffer` رسالة ناقصة دومًا)،
        # فهذه لحظة وصولها الحقيقيّة قبل أيّ تأطير أو توزيع.
        self._received_at = time.time()
        self._buffer += drained
        self._trace_pumps = getattr(self, "_trace_pumps", 0) + 1
        if self._trace_pumps <= 40 and self._context is not None:
            st = stream.stats()
            self._context.logger.warning(
                "622 pump#%s drained=%s buf=%s in=%s out=%s connected=%s err=%r",
                self._trace_pumps, len(drained), len(self._buffer),
                st.get("bytes_in"), st.get("bytes_out"), st.get("connected"),
                st.get("error"))
        messages, self._buffer = fx.frame(self._buffer)
        for raw in messages:
            await self._dispatch(fx.parse(raw))
        if not stream.connected:
            raise transport.TransportError(stream.error or "LINK_LOST")

    async def _dispatch(self, pairs: list[tuple[int, str]]) -> None:
        session, stream = self._session, self._stream
        if session is None or stream is None:
            return
        msg_type = session.observe(pairs)
        stamp = fx.parse_sending_time(fx.first(pairs, fx.TAG_SENDING_TIME) or "")
        if msg_type == fx.MSG_LOGON:
            self._ever_logged_on = True
            # 2026-09-04 (NQ seal): `_last_error` was written on failure (line 170,
            # and from `session.last_error`) but never cleared on success, while
            # `health_check` prints it for any DOWN link.  So the panel kept
            # showing the FIRST failure of the process for the rest of its life.
            # Measured 2026-09-04: the feed had reconnected and streamed 26,625
            # ticks, and the card still read `NO_PASSWORD_IN_VAULT` from a boot
            # attempt made before the vault opened -- a stale reason reported as
            # the current one, which is exactly what an owner cannot act on.
            # A completed logon means the previous error is history, not state.
            self._last_error = ""
            now = time.time()
            stream.send(session.security_list_request("SEC-%d" % self._connects, now))
            self._last_sent = now
            await self._announce(STATE_CONNECTING, {"logged_on": True})
            return
        if msg_type == fx.MSG_TEST_REQUEST:
            now = time.time()
            stream.send(session.heartbeat(now, fx.first(pairs, fx.TAG_TEST_REQ_ID)))
            self._last_sent = now
            return
        if msg_type == fx.MSG_HEARTBEAT:
            self._heartbeats += 1
            await self._publish(EVENT_HEARTBEAT, self._common("*", stamp))
            return
        if msg_type == fx.MSG_SECURITY_LIST:
            await self._on_security_list(pairs, stamp)
            return
        if msg_type in (fx.MSG_SNAPSHOT, fx.MSG_INCREMENTAL):
            await self._on_market_data(pairs, stamp, msg_type == fx.MSG_SNAPSHOT)
            return
        if msg_type in (fx.MSG_REJECT, fx.MSG_MD_REQUEST_REJECT, fx.MSG_LOGOUT):
            self._last_error = session.last_error
            if msg_type == fx.MSG_LOGOUT and not self._ever_logged_on:
                self._auth_failed = True
            await self._announce(STATE_DOWN, {"reject": session.last_error,
                                              "auth_failed": self._auth_failed})
            if msg_type == fx.MSG_LOGOUT:
                # The venue ended the session. Leaving the socket open looked
                # alive to the reconnect check while nothing arrived -- measured
                # as five silent minutes in CloseWait.
                raise transport.TransportError("LOGOUT: %s" % session.last_error)
            return
        if not fx.FixSession.is_admin(msg_type):
            self._unknown += 1

    def _next_sequence(self) -> int:
        self._sequence += 1
        return self._sequence

    def _common(self, symbol: str, stamp: float | None, *, sequence: int | None = None,
                sequence_gap: bool = False, out_of_order: bool = False,
                fabric_gap: bool = False) -> dict[str, Any]:
        if sequence is None:
            sequence = self._next_sequence()
        return {"provider": "CTRADER", "account_id": self._account, "broker": self._broker,
                "build": "QUANT_NQ_FIX_%s" % ATOM_VERSION, "symbol": symbol,
                "timestamp": stamp if stamp is not None else self._official_time,
                "received_at": self._received_at or time.time(),
                "sequence": sequence, "sequence_gap": sequence_gap,
                "out_of_order": out_of_order, "fabric_gap": fabric_gap}

    async def _publish(self, event: str, payload: dict[str, Any]) -> None:
        if self._context is not None:
            await self._context.publish(event, payload)

    async def _announce(self, state: str, extra: dict[str, Any]) -> None:
        self._link = state
        await self._publish(EVENT_STATE, {"provider": "CTRADER", "state": state,
                                          "account_id": self._account, **extra})

    async def _on_security_list(self, pairs: list[tuple[int, str]], stamp: float | None) -> None:
        rows = fx.read_security_list(pairs)
        if not rows:
            return
        for row in rows:
            symbol_id = row.get(fx.TAG_SYMBOL, "")
            name = row.get(fx.TAG_SYMBOL_NAME, "")
            if symbol_id and name:
                self._by_id[symbol_id] = name
                self._by_name[name] = symbol_id
        stream, session = self._stream, self._session
        if stream is None or session is None:
            return
        missing = [name for name in self._wanted if name not in self._by_name]
        subscribed = self._send_subscriptions()
        await self._publish(EVENT_SPECS, {"provider": "CTRADER", "account_id": self._account,
                                          "published_at": stamp if stamp is not None else self._official_time,
                                          "sequence": self._next_sequence(),
                                          "symbols": [dict(self._common(self._by_id.get(row.get(fx.TAG_SYMBOL, ""), ""), stamp),
                                                           **{"venue_symbol_id": row.get(fx.TAG_SYMBOL, ""),
                                                              "venue_fields": {str(k): v for k, v in row.items()}})
                                                      for row in rows if row.get(fx.TAG_SYMBOL_NAME) in self._by_name]})
        await self._announce(STATE_READY, {"listed": len(rows), "subscribed": subscribed,
                                           "missing": missing})

    def _send_subscriptions(self, cancel_first: bool = False) -> list[str]:
        """يطلب السلّم لكل رمز مطلوب — ويُعيد أسماء ما أُرسل له طلب.

        بنفس `MDReqID` في كل مرّة عمدًا: `_on_market_data` يستخرج معرّف الرمز
        من هذا المعرّف (`MD-<symbol_id>`)، فتغييره كان يقطع الربط بين الردّ
        ورمزه. و`SubscriptionRequestType=1` يجعل الوسيط يبدأ بلقطة `W` كاملة،
        وهي المقصودة: 624 يمسح دفتره عند `is_snapshot` ويبني من جديد.

        و`cancel_first` للتجديد وحده: إعادة الطلب على اشتراك **قائم** لا
        تُعيد اللقطة — قِيس ٢٠٢٦-٠٩-٠٩ أنّ سبع دورات تجديد أُرسلت بينما لقطات
        الدفتر ارتفعت مع إعادات الاتصال وحدها (تسعة مقابل تسعة). فالإلغاء
        قبله يجعل ما يليه اشتراكًا جديدًا حقًّا، فتأتي `W`.
        """
        stream, session = self._stream, self._session
        if stream is None or session is None:
            return []
        # حارس صريح: التحميل الحارّ يطهّر وحدات الذرّة وحدها ويُبقي `shared`
        # مخبّأً في `sys.modules`. فذرّةٌ جديدة فوق `shared` قديم كانت سترمي
        # على الطريق الحيّ — وقد وقع ذلك فعلًا في 624 يوم ٢٠٢٦-٠٩-٠٩ (9.5
        # خطأ/ثانية وصفر عمق حتى إعادة تشغيل النواة). هنا يسقط الإلغاء وحده
        # ويبقى التجديد يعمل كما كان، بلا حرف واحد يُكسر.
        cancel = getattr(session, "market_data_unsubscribe", None)
        sent = []
        for name in self._wanted:
            symbol_id = self._by_name.get(name)
            if not symbol_id:
                continue
            request_id = MD_REQ_PREFIX + symbol_id
            now = time.time()
            if cancel_first and cancel is not None:
                stream.send(cancel(request_id, symbol_id, self._market_depth, now))
            stream.send(session.market_data_request(request_id, symbol_id,
                                                    self._market_depth, now))
            self._last_sent = now
            sent.append(name)
        if sent:
            self._last_subscribe_at = time.time()
        return sent

    async def _refresh_subscriptions(self) -> None:
        """تجديد دوريّ للاشتراك — اللقطة التي كانت تصل مرّة واحدة فقط.

        ٢٠٢٦-٠٩-٠٩ (ختم المالك `NQ`) — العلّة المقيسة حيًّا: الاشتراك يُرسل
        مرّة واحدة عند وصول قائمة الأوراق، فتصل لقطة `W` واحدة ثمّ لا تتكرّر
        أبدًا. والدفتر بعدها تزايديّ محض، وسي‑تريدر لا يحذف المستوى الذي
        هجره — فالسلّم ينحرف بلا رجعة. المقيس على BTCUSD في العشرين دقيقة
        الأولى بعد إقلاع نظيف: العمق من **14 مستوًى إلى 371**، والطرفان
        اختلّا (**450 عرضًا مقابل 26 طلبًا**) حتى تقاطعا بـ12.61 دولارًا،
        ورفض 112 صعد من **٢٪ إلى ١٦٪** بسبب `crossed_spread` وحده.

        وقد عولج هذا مرّتين بيد المالك (`622/stop` ثمّ `622/start`) ونجح
        مرّتين — لأنّ إعادة التشغيل تُعيد الاشتراك فتصل لقطة جديدة. هذا هو
        العلاج نفسه، لكن بلا يد: يتكرّر وحده فلا تعود العلّة.
        """
        if self._resubscribe_every_s <= 0 or not self._by_name:
            return
        session = self._session
        if session is None or not session.logged_on:
            return
        if time.time() - self._last_subscribe_at < self._resubscribe_every_s:
            return
        sent = self._send_subscriptions(cancel_first=False)
        if not sent:
            return
        self._resubscribes += 1
        if self._context is not None:
            self._context.logger.warning(
                "622 تجديد الاشتراك #%s: %s رمزًا — لقطة سلّم جديدة مطلوبة",
                self._resubscribes, len(sent))

    async def _on_market_data(self, pairs: list[tuple[int, str]], stamp: float | None,
                              is_snapshot: bool) -> None:
        entries = fx.read_md_entries(pairs)
        if not entries:
            return
        # The request id is ours and rides on every W/X. Tag 55 does not: a
        # delete entry carries 279 and 278 only, so a delete-only message has no
        # symbol at all and would be dropped whole, drifting the book silently.
        request = fx.first(pairs, fx.TAG_MD_REQ_ID) or ""
        symbol_id = (request[len(MD_REQ_PREFIX):] if request.startswith(MD_REQ_PREFIX)
                     else "") or fx.first(pairs, fx.TAG_SYMBOL) or ""
        name = self._by_id.get(symbol_id, "")
        if not name:
            self._unknown += 1
            return
        # المصدر يُسلّم ولا يبني. تحديثات المستويات تخرج كما وردت من المصدر،
        # ويبنيها 623 خلفه. بناء الدفتر هنا كان يؤخّر التفريغ فيتراكم المخزن،
        # وهو ليس عمل مصدر: التِكّة تُشتقّ من الدفتر، ومن يبني الدفتر يملكها.
        when = stamp if stamp is not None else self._official_time
        rows = []
        for row in entries:
            entry_type, entry_id, price, size, action = fx.entry_values(row)
            if not entry_id:
                continue
            rows.append({"entry_type": entry_type, "entry_id": entry_id,
                         "price": price, "size": size,
                         "action": fx.ACTION_NEW if is_snapshot else action})
        nseq = self._next_sequence()
        # تتبّع التسلسل يبقى عمل المصدر: الفجوة وخروج الترتيب صفتا **جلسة**
        # لا صفتا دفتر. تُقاس هنا وتُحمل مع الخام، فتصل التِكّة عبر 624 و623
        # كما كانت تصلها قبل فصل الدفتر.
        self._tracker.mark(self._account, name, "tick", when)
        obs = self._tracker.observe(self._account, name, "tick", when, nseq)
        fg = self._fabric_gap
        self._fabric_gap = False
        await self._publish(EVENT_RAW, dict(
            self._common(name, stamp, sequence=nseq,
                         sequence_gap=obs["sequence_gap"],
                         out_of_order=obs["out_of_order"], fabric_gap=fg),
            entries=rows, is_snapshot=is_snapshot, exchange_timestamp=when))
        self._updates += 1

    async def _on_pulse(self, payload: dict[str, Any]) -> None:
        official = payload.get("official_time") if isinstance(payload, dict) else None
        if isinstance(official, (int, float)):
            self._official_time = float(official)
        if self._context is None:
            return
        await self._publish(EVENT_STATE, {"provider": "CTRADER", "state": "STREAMS",
                                          "streams": self._tracker.view(self._freshness_now()),
                                          "sequence_gaps": self._tracker.gaps,
                                          "out_of_order": self._tracker.out_of_order,
                                          "timestamp": self._official_time})

    def _freshness_now(self) -> float:
        return max(self._tracker.newest_stamp(), self._official_time)

    async def snapshot(self) -> dict[str, Any]:
        return {"version": ATOM_VERSION, "tracker": self._tracker.snapshot(),
                "by_name": dict(self._by_name), "by_id": dict(self._by_id),
                "counts": {"updates": self._updates,
                           "heartbeats": self._heartbeats, "unknown": self._unknown,
                           "connects": self._connects, "sequence": self._sequence}}

    async def restore(self, state: dict[str, Any]) -> None:
        if not isinstance(state, dict):
            raise ValueError("INVALID_FIX_FEED_STATE")
        self._tracker.restore(state.get("tracker") or {})
        # v1.3.2 (nq seal 2026-08-25): rows restored under a FOREIGN identity
        # are dropped. After the identity_account_id migration the snapshot
        # still carried ("6175701", symbol) rows whose stamps froze at the
        # switch -- the health view then declared ALL symbols dead/stale
        # (ghost of the old identity) while the live rows under the current
        # account were ACTIVE and ticks flowed (measured live).
        foreign = {pair for pair in self._tracker.symbols
                   if pair[0] != self._account}
        if foreign:
            self._tracker.symbols -= foreign
            for old_account, old_symbol in foreign:
                for kind in ("tick", "depth", "spec"):
                    self._tracker.last.pop(
                        self._tracker.key(old_account, old_symbol, kind), None)
                self._tracker.last_sequence.pop(old_account, None)
                self._tracker.stopped.discard(old_account)
        by_name = state.get("by_name")
        by_id = state.get("by_id")
        self._by_name = {str(k): str(v) for k, v in by_name.items()} if isinstance(by_name, dict) else {}
        self._by_id = {str(k): str(v) for k, v in by_id.items()} if isinstance(by_id, dict) else {}
        counts = state.get("counts") if isinstance(state.get("counts"), dict) else {}
        self._updates = int(counts.get("updates") or 0)
        self._heartbeats = int(counts.get("heartbeats") or 0)
        self._unknown = int(counts.get("unknown") or 0)
        self._connects = int(counts.get("connects") or 0)
        self._sequence = int(counts.get("sequence") or 0)

    async def health_check(self) -> HealthStatus:
        if not self._running:
            return HealthStatus(state=HealthState.UNHEALTHY, message="NOT_STARTED")
        streams = self._tracker.view(self._freshness_now())
        ticks = [row for row in streams if row["stream"] == "tick"]
        session = self._session
        details = {"link": self._link, "host": "%s:%d" % (self._host, self._port),
                   "logged_on": bool(session and session.logged_on),
                   "symbols_listed": len(self._by_name), "subscribed": len(self._by_id),
                   "updates": self._updates, "heartbeats": self._heartbeats,
                   "unknown_messages": self._unknown, "connects": self._connects,
                   "rejects": session.rejects if session else 0,
                   "last_error": self._last_error, "streams": streams,
                   "stream_link": self._stream.stats() if self._stream else None,
                   "sequence_gaps": self._tracker.gaps,
                   "out_of_order": self._tracker.out_of_order}
        details["auth_failed"] = self._auth_failed
        # Counters ride on EVERY message, not only the healthy one: a feed that
        # is stale or dead is exactly when the numbers are needed, and hiding
        # them there is what turned a throughput problem into a guessing game.
        details["resubscribes"] = self._resubscribes
        details["resubscribe_every_s"] = self._resubscribe_every_s
        details["last_subscribe_age_s"] = (round(time.time() - self._last_subscribe_at, 1)
                                           if self._last_subscribe_at else None)
        tail = " up=%d c=%d u=%d q=%d p=%d rs=%d pump=%.0f/%.0fم.ث" % (
            self._updates, self._connects, self._unknown,
            (self._stream.stats().get("pending_bytes") or 0) if self._stream else -1,
            len(self._buffer), self._resubscribes,
            self._pump_gap_ewma * 1000.0, self._pump_gap_max * 1000.0)
        if self._auth_failed:
            return HealthStatus(state=HealthState.UNHEALTHY, details=details,
                                message="FIX_LOGON_REFUSED_NO_RETRY: %s%s" % (self._last_error, tail))
        if self._last_error and self._link == STATE_DOWN:
            return HealthStatus(state=HealthState.UNHEALTHY, message="FIX_DOWN: %s%s" % (self._last_error, tail),
                                details=details)
        if session is None or not session.logged_on:
            return HealthStatus(state=HealthState.DEGRADED, message="FIX_NOT_LOGGED_ON" + tail, details=details)
        if not self._by_name:
            return HealthStatus(state=HealthState.DEGRADED, message="FIX_AWAITING_SECURITY_LIST" + tail,
                                details=details)
        if not ticks or all(row["state"] == NEVER_SEEN for row in ticks):
            return HealthStatus(state=HealthState.UNKNOWN, message="FIX_NEVER_SEEN" + tail, details=details)
        # A symbol outside its trading session is not a broken link.  Only a
        # feed where EVERY symbol is dead is a real outage; a mixed picture is
        # degraded and must name the silent symbols instead of condemning the
        # whole feed.  Measured 2026-08-25: four index/metal symbols went quiet
        # at their daily break while three kept ticking under one second.
        #
        # ٢٠٢٦-٠٩-٢٦ — والآن يُعرف «خارج الجلسة» من الوسيط نفسه: الساكنُ في سوقٍ
        # مغلقة بجلساته يخرج من الموتى والمتأخّرين ويُسمّى وحده. فعطلة الأسبوع
        # خضراء، ورمزٌ ساكنٌ في سوقٍ مفتوحة يبقى عطلًا كما كان.
        quiet = {str(row.get("symbol") or "?") for row in ticks
                 if row["state"] in (DEAD, STALE, NEVER_SEEN)}
        closed = self._closed_now(quiet)
        details["market_closed"] = sorted(closed)
        details["session_symbols"] = len(self._hours)
        if closed:
            tail = " · السوق مغلق: %s%s" % (",".join(sorted(closed)), tail)
        dead_names = sorted({str(row.get("symbol") or "?")
                             for row in ticks if row["state"] == DEAD} - closed)
        live_rows = [row for row in ticks if row["state"] not in (DEAD, NEVER_SEEN)
                     and str(row.get("symbol") or "?") not in closed]
        if dead_names and not live_rows:
            return HealthStatus(state=HealthState.UNHEALTHY, details=details,
                                message="FIX_TICK_DEAD_ALL: %s%s" % (",".join(dead_names), tail))
        if dead_names:
            return HealthStatus(state=HealthState.DEGRADED, details=details,
                                message="FIX_SYMBOLS_OUT_OF_SESSION: %s%s" % (",".join(dead_names), tail))
        stale_names = sorted({str(row.get("symbol") or "?")
                              for row in ticks if row["state"] == STALE} - closed)
        if stale_names:
            return HealthStatus(state=HealthState.DEGRADED, details=details,
                                message="FIX_TICK_STALE: %s%s" % (",".join(stale_names), tail))
        return HealthStatus(state=HealthState.HEALTHY, details=details,
                            message="updates=%d symbols=%d%s"
                                    % (self._updates, len(self._by_id), tail))
