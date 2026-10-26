import asyncio
import importlib.util
import sys
import threading
from pathlib import Path

root = Path(__file__).resolve().parents[4]
folder = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
sys.path.insert(0, str(folder))
spec = importlib.util.spec_from_file_location("a622", folder / "atom.py")
module = importlib.util.module_from_spec(spec)
sys.modules["a622"] = module
assert spec.loader is not None
spec.loader.exec_module(module)

from shared import fix_session as fx  # noqa: E402

PASSWORD = "TOP-SECRET-VALUE"


class Logger:
    def __getattr__(self, name):
        return lambda *args, **kwargs: None


class Bus:
    def __init__(self):
        self.events = []

    def subscribe(self, *args):
        pass

    async def publish(self, name, payload):
        self.events.append((name, payload))

    def of(self, name):
        return [payload for event, payload in self.events if event == name]


class FakeStream:
    """Stands in for transport.StreamSession: same surface, no socket."""

    def __init__(self, *args, **kwargs):
        self.sent = []
        self.inbox = b""
        self.connected = True
        self.error = ""

    def connect(self):
        self.connected = True

    def send(self, data):
        self.sent.append(data)

    def drain(self):
        data, self.inbox = self.inbox, b""
        return data

    def close(self):
        self.connected = False

    def stats(self):
        return {"connected": self.connected}

    def feed(self, raw):
        self.inbox += raw


def config(**over):
    base = {"host": "h", "port": 5211, "use_tls": True,
            "sender_comp_id": "live4.icmarkets.6175701", "target_comp_id": "cServer",
            "sub_id": "QUOTE", "username": "6175701", "broker": "Raw Trading Ltd",
            "password_secret_key": "ctrader_fix_password",
            "symbols": ["BTCUSD", "XAUUSD"], "market_depth": 0, "heartbeat_s": 30,
            "poll_interval_s": 0.001, "reconnect_backoff_s": 1, "live_max_backlog_bytes": 131072,
            "tick_stale_after_s": 30, "depth_stale_after_s": 30,
            "specs_stale_after_s": 600, "dead_after_s": 120}
    base.update(over)
    return base


def run(coro):
    """A private loop per call.

    The fleet runs thousands of tests in one process and some of them close the
    global loop behind them; a shared `get_event_loop()` here passed in
    isolation and failed 14/14 the moment the file ran with the fleet.
    """
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def build(monkey_stream=True, **over):
    bus = Bus()
    atom = module.Atom()
    ctx = module.AtomContext(atom_id=622, config=config(**over), logger=Logger(),
                             publish=bus.publish, subscribe=bus.subscribe)
    run(atom.initialize(ctx))
    atom._password = lambda: PASSWORD
    stream = FakeStream()
    if monkey_stream:
        atom._stream = stream
        atom._session = fx.FixSession("live4.icmarkets.6175701", "cServer", "QUOTE", "6175701")
    return atom, bus, stream


def venue(msg_type, fields):
    return fx.encode([(fx.TAG_MSG_TYPE, msg_type), (fx.TAG_SENDER, "cServer"),
                      (fx.TAG_SEQ, 1), (fx.TAG_SENDING_TIME, "20260821-15:30:00.500")] + fields)


def logon_and_list(atom, stream):
    stream.feed(venue("A", []))
    run(atom._pump())
    stream.feed(venue("y", [(fx.TAG_SEC_REQ_ID, "R"), (fx.TAG_NO_RELATED_SYM, 2),
                            (fx.TAG_SYMBOL, "1"), (fx.TAG_SYMBOL_NAME, "BTCUSD"),
                            (fx.TAG_SYMBOL, "2"), (fx.TAG_SYMBOL_NAME, "XAUUSD")]))
    run(atom._pump())


SNAPSHOT = [(fx.TAG_SYMBOL, "1"), (fx.TAG_NO_MD_ENTRIES, 4),
            (fx.TAG_MD_ENTRY_TYPE, "0"), (fx.TAG_MD_ENTRY_ID, "b1"),
            (fx.TAG_MD_ENTRY_PX, "77600.5"), (fx.TAG_MD_ENTRY_SIZE, "3"),
            (fx.TAG_MD_ENTRY_TYPE, "0"), (fx.TAG_MD_ENTRY_ID, "b2"),
            (fx.TAG_MD_ENTRY_PX, "77599.0"), (fx.TAG_MD_ENTRY_SIZE, "8"),
            (fx.TAG_MD_ENTRY_TYPE, "1"), (fx.TAG_MD_ENTRY_ID, "a1"),
            (fx.TAG_MD_ENTRY_PX, "77606.0"), (fx.TAG_MD_ENTRY_SIZE, "2"),
            (fx.TAG_MD_ENTRY_TYPE, "1"), (fx.TAG_MD_ENTRY_ID, "a2"),
            (fx.TAG_MD_ENTRY_PX, "77610.0"), (fx.TAG_MD_ENTRY_SIZE, "5")]


def test_logon_is_sent_and_password_never_published():
    atom, bus, stream = build()
    stream.feed(venue("A", []))
    run(atom._pump())
    assert atom._session.logged_on is True
    assert any(b"35=x" in raw for raw in stream.sent), "security list requested after logon"
    for _, payload in bus.events:
        assert PASSWORD not in repr(payload)


def test_security_list_builds_map_and_subscribes():
    atom, bus, stream = build()
    logon_and_list(atom, stream)
    assert atom._by_name == {"BTCUSD": "1", "XAUUSD": "2"}
    requests = [raw for raw in stream.sent if b"35=V" in raw]
    assert len(requests) == 2
    ready = [p for p in bus.of("feed.ctrader.state") if p.get("state") == "READY"]
    assert ready and ready[-1]["subscribed"] == ["BTCUSD", "XAUUSD"]
    assert ready[-1]["missing"] == []


def test_missing_symbol_is_declared_not_invented():
    atom, bus, stream = build(symbols=["BTCUSD", "DOESNOTEXIST"])
    logon_and_list(atom, stream)
    ready = [p for p in bus.of("feed.ctrader.state") if p.get("state") == "READY"][-1]
    assert ready["missing"] == ["DOESNOTEXIST"]
    assert ready["subscribed"] == ["BTCUSD"]


def test_snapshot_yields_raw_entries_with_venue_time():
    """المصدر يُخرج تحديثات المستويات خامًا. الدفتر يبنيه 624 خلفه."""
    atom, bus, stream = build()
    logon_and_list(atom, stream)
    stream.feed(venue("W", SNAPSHOT))
    run(atom._pump())
    raw = bus.of("feed.ctrader.raw")[-1]
    assert raw["symbol"] == "BTCUSD" and raw["provider"] == "CTRADER"
    assert raw["account_id"] == "6175701" and raw["broker"] == "Raw Trading Ltd"
    assert raw["is_snapshot"] is True
    # الوقت من رسالة المصدر لا من ساعة الجهاز
    assert abs(raw["timestamp"] - fx.parse_sending_time("20260821-15:30:00.500")) < 1e-6
    prices = [row["price"] for row in raw["entries"]]
    assert 77600.5 in prices and 77606.0 in prices
    assert "bid" not in raw and "bids" not in raw, "لا قمّة ولا سلّم: هذا عمل 624"


def test_incremental_entries_pass_through_unbuilt():
    atom, bus, stream = build()
    logon_and_list(atom, stream)
    stream.feed(venue("X", [(fx.TAG_NO_MD_ENTRIES, 2),
                            (fx.TAG_MD_ENTRY_TYPE, "0"), (fx.TAG_MD_UPDATE_ACTION, "1"),
                            (fx.TAG_MD_ENTRY_ID, "b1"), (fx.TAG_SYMBOL, "1"),
                            (fx.TAG_MD_ENTRY_PX, "77604.0"), (fx.TAG_MD_ENTRY_SIZE, "4"),
                            (fx.TAG_MD_ENTRY_TYPE, "1"), (fx.TAG_MD_UPDATE_ACTION, "2"),
                            (fx.TAG_MD_ENTRY_ID, "a1"), (fx.TAG_SYMBOL, "1")]))
    run(atom._pump())
    raw = bus.of("feed.ctrader.raw")[-1]
    assert raw["is_snapshot"] is False
    ids = {row["entry_id"] for row in raw["entries"]}
    assert ids == {"b1", "a1"}, "التحديث والحذف يعبران كما وردا"
    actions = {row["entry_id"]: row["action"] for row in raw["entries"]}
    assert actions["a1"] == fx.ACTION_DELETE, "الحذف لا يُطبَّق هنا، يُمرَّر"


def test_every_update_publishes_its_own_message():
    atom, bus, stream = build()
    logon_and_list(atom, stream)
    before = len(bus.of("feed.ctrader.raw"))
    for price in ("77601.0", "77602.0", "77603.0"):
        stream.feed(venue("X", [(fx.TAG_MD_REQ_ID, "MD-1"), (fx.TAG_NO_MD_ENTRIES, 1),
                                (fx.TAG_MD_UPDATE_ACTION, "1"), (fx.TAG_MD_ENTRY_TYPE, "0"),
                                (fx.TAG_MD_ENTRY_ID, "b1"), (fx.TAG_SYMBOL, "1"),
                                (fx.TAG_MD_ENTRY_PX, price), (fx.TAG_MD_ENTRY_SIZE, "1")]))
        run(atom._pump())
    out = bus.of("feed.ctrader.raw")
    assert len(out) - before == 3, "tick by tick: no batching, no conflation"
    assert [m["entries"][0]["price"] for m in out[-3:]] == [77601.0, 77602.0, 77603.0]


def test_group_delimiter_is_read_from_the_wire_not_assumed():
    """عيّنة cServer الحقيقيّة: الفاصل يُقرأ لا يُفترض."""
    atom, bus, stream = build()
    logon_and_list(atom, stream)
    stream.feed(venue("W", SNAPSHOT))
    run(atom._pump())
    raw = bus.of("feed.ctrader.raw")[-1]
    assert len(raw["entries"]) == 4, "المجموعة قُرئت كاملة بلا افتراض فاصل"


def test_delete_entry_is_forwarded_not_applied():
    """حذف بلا 269: يُمرَّر كما ورد، ويطبّقه 624 حيث يعرف الجانب من المعرّف."""
    atom, bus, stream = build()
    logon_and_list(atom, stream)
    stream.feed(venue("X", [(fx.TAG_MD_REQ_ID, "MD-1"), (fx.TAG_NO_MD_ENTRIES, 1),
                            (fx.TAG_MD_UPDATE_ACTION, "2"), (fx.TAG_MD_ENTRY_ID, "a1")]))
    run(atom._pump())
    raw = bus.of("feed.ctrader.raw")[-1]
    assert raw["entries"][0]["entry_id"] == "a1"
    assert raw["entries"][0]["action"] == fx.ACTION_DELETE
    assert raw["symbol"] == "BTCUSD", "الرمز من MDReqID لا من 55 الغائب"


def test_sequence_tracking_rides_on_the_raw_message():
    """التسلسل وفجواته صفتا جلسة — تبقيان عمل المصدر وتصلان التِكّة عبر 624."""
    atom, bus, stream = build()
    logon_and_list(atom, stream)
    stream.feed(venue("W", SNAPSHOT))
    run(atom._pump())
    raw = bus.of("feed.ctrader.raw")[-1]
    for key in ("sequence", "sequence_gap", "out_of_order", "fabric_gap"):
        assert key in raw, f"حقل تتبّع ضاع: {key}"


def test_nothing_is_discarded_under_backlog():
    """المصدر لا يرمي: كل رسالة تصل تُنشر، مهما تراكم."""
    atom, bus, stream = build()
    logon_and_list(atom, stream)
    before = len(bus.of("feed.ctrader.raw"))
    burst = venue("X", [(fx.TAG_MD_REQ_ID, "MD-1"), (fx.TAG_NO_MD_ENTRIES, 1),
                        (fx.TAG_MD_UPDATE_ACTION, "0"), (fx.TAG_MD_ENTRY_TYPE, "0"),
                        (fx.TAG_MD_ENTRY_ID, "z"), (fx.TAG_SYMBOL, "1"),
                        (fx.TAG_MD_ENTRY_PX, "1"), (fx.TAG_MD_ENTRY_SIZE, "1")])
    stream.feed(burst * 40)
    run(atom._pump())
    assert len(bus.of("feed.ctrader.raw")) - before == 40, "أربعون رسالة ⇒ أربعون نشرة"
    assert not [p for p in bus.of("feed.ctrader.state") if p.get("gap")]


def test_no_byte_ceiling_on_the_transport():
    """الرمي كان يبدأ قبل الذرّة، في خيط النقل. لم يعد له سقف."""
    src = (Path(__file__).resolve().parents[1] / "atom.py").read_text(encoding="utf-8")
    assert "max_buffer_bytes=0" in src, "لا سقف بايتات على خيط النقل"
    assert "_max_backlog" not in src, "قانون القفزة أُزيل بالكامل"
    assert "LIVE_LINE_JUMPED" not in src and "TRANSPORT_LIVE_TAIL" not in src


def test_unknown_symbol_id_is_counted_not_guessed():
    atom, bus, stream = build()
    logon_and_list(atom, stream)
    stream.feed(venue("W", [(fx.TAG_SYMBOL, "999"), (fx.TAG_NO_MD_ENTRIES, 1),
                            (fx.TAG_MD_ENTRY_TYPE, "0"), (fx.TAG_MD_ENTRY_ID, "x"),
                            (fx.TAG_MD_ENTRY_PX, "1.0"), (fx.TAG_MD_ENTRY_SIZE, "1")]))
    run(atom._pump())
    assert bus.of("feed.ctrader.raw") == []
    assert atom._unknown == 1


def test_one_sided_entries_are_published_as_is():
    """المصدر يُسلّم: مستوى واحد يخرج ولا يُكتم. القمّة شأن 624."""
    atom, bus, stream = build()
    logon_and_list(atom, stream)
    stream.feed(venue("W", [(fx.TAG_SYMBOL, "1"), (fx.TAG_NO_MD_ENTRIES, 1),
                            (fx.TAG_MD_ENTRY_TYPE, "0"), (fx.TAG_MD_ENTRY_ID, "b1"),
                            (fx.TAG_MD_ENTRY_PX, "100.0"), (fx.TAG_MD_ENTRY_SIZE, "1")]))
    run(atom._pump())
    out = bus.of("feed.ctrader.raw")
    assert out, "الجانب الواحد يخرج"
    assert out[-1]["entries"][0]["price"] == 100.0
    assert len(out[-1]["entries"]) == 1


def test_test_request_is_answered():
    atom, bus, stream = build()
    stream.feed(venue("A", []))
    run(atom._pump())
    stream.feed(venue("1", [(fx.TAG_TEST_REQ_ID, "PING-7")]))
    run(atom._pump())
    assert any(b"112=PING-7" in raw for raw in stream.sent)


def test_reject_is_named_and_link_declared_down():
    atom, bus, stream = build()
    stream.feed(venue("A", []))
    run(atom._pump())
    stream.feed(venue("3", [(fx.TAG_TEXT, "Invalid MDReqID")]))
    run(atom._pump())
    assert atom._session.rejects == 1
    assert "Invalid MDReqID" in atom._last_error
    assert atom._link == module.STATE_DOWN


def test_refused_logon_stops_retrying_instead_of_hammering_the_account():
    atom, bus, stream = build()
    stream.feed(venue("5", [(fx.TAG_TEXT, "RET_NOT_AUTHORIZED")]))
    try:
        run(atom._pump())
    except Exception:  # noqa: BLE001 — الخروج يهدم الوصلة عمدًا
        pass
    assert atom._auth_failed is True, "a refused logon must not look like a flaky link"
    atom._running = True
    health = run(atom.health_check())
    assert "FIX_LOGON_REFUSED" in health.message
    assert "RET_NOT_AUTHORIZED" in health.message
    state = [p for p in bus.of("feed.ctrader.state") if p.get("state") == module.STATE_DOWN][-1]
    assert state["auth_failed"] is True


def test_logout_after_a_good_session_is_a_link_drop_not_an_auth_failure():
    atom, bus, stream = build()
    stream.feed(venue("A", []))
    run(atom._pump())
    stream.feed(venue("5", [(fx.TAG_TEXT, "session end")]))
    raised = ""
    try:
        run(atom._pump())
    except Exception as exc:  # noqa: BLE001
        raised = str(exc)
    assert atom._auth_failed is False, "a normal logout must still allow reconnect"
    assert "LOGOUT" in raised, "الخروج يهدم الوصلة فورًا بدل تركها مفتوحة بلا جلسة"


def test_health_walks_from_not_started_to_healthy():
    atom, bus, stream = build()
    assert run(atom.health_check()).state.name == "UNHEALTHY"
    atom._running = True
    assert run(atom.health_check()).message.startswith("FIX_NOT_LOGGED_ON")
    stream.feed(venue("A", []))
    run(atom._pump())
    assert run(atom.health_check()).message.startswith("FIX_AWAITING_SECURITY_LIST")
    stream.feed(venue("y", [(fx.TAG_NO_RELATED_SYM, 1), (fx.TAG_SYMBOL, "1"),
                            (fx.TAG_SYMBOL_NAME, "BTCUSD")]))
    run(atom._pump())
    assert run(atom.health_check()).state.name == "UNKNOWN"
    stream.feed(venue("W", SNAPSHOT))
    run(atom._pump())
    atom._official_time = fx.parse_sending_time("20260821-15:30:00.500")
    health = run(atom.health_check())
    assert health.state.name == "HEALTHY" and "updates=" in health.message


def test_snapshot_restore_keeps_symbol_map_and_counters():
    atom, bus, stream = build()
    logon_and_list(atom, stream)
    stream.feed(venue("W", SNAPSHOT))
    run(atom._pump())
    state = run(atom.snapshot())
    fresh = module.Atom()
    run(fresh.restore(state))
    assert fresh._by_name == {"BTCUSD": "1", "XAUUSD": "2"}
    assert fresh._updates == atom._updates


def test_restore_rejects_a_broken_state():
    atom, _, _ = build()
    try:
        run(atom.restore("not-a-dict"))
    except ValueError as exc:
        assert "INVALID_FIX_FEED_STATE" in str(exc)
    else:
        raise AssertionError("a corrupt snapshot must not be accepted silently")


def test_link_loss_raises_so_the_caller_reconnects():
    atom, _, stream = build()
    stream.feed(venue("A", []))
    run(atom._pump())
    stream.connected = False
    stream.error = "PEER_CLOSED"
    try:
        run(atom._pump())
    except Exception as exc:  # noqa: BLE001
        assert "PEER_CLOSED" in str(exc)
    else:
        raise AssertionError("a dead link must not look alive")


def test_connect_runs_off_the_event_loop_thread():
    """Item 20/27 of the 27-atom review ("a synchronous TLS connect
    freezes the loop, no connection timeout"): _connect() used to call
    stream.connect() (TCP + TLS handshake, up to several seconds) DIRECTLY
    on the atom's own coroutine -- the shared core event loop. Any
    slowness there stalls every other atom on the same loop. Must now run
    via asyncio.to_thread, i.e. never on the thread that's running the
    event loop."""
    main_thread = threading.current_thread()
    seen = {}

    class RecordingStream:
        def __init__(self, *a, **k): pass
        def connect(self): seen["thread"] = threading.current_thread()
        def send(self, data): pass
        def close(self): pass

    atom, _bus, _stream = build(monkey_stream=False)
    original = module.transport.StreamSession
    module.transport.StreamSession = RecordingStream
    try:
        run(atom._connect())
    finally:
        module.transport.StreamSession = original
    assert seen.get("thread") is not None, "connect() لم يُستدعَ إطلاقاً"
    assert seen["thread"] is not main_thread, (
        "connect() نُفِّذ على خيط الحلقة الرئيسي -- سيجمّد كل الذرّات الأخرى")


def test_teardown_close_runs_off_the_event_loop_thread():
    """Item 20/27: _teardown() (called as _connect()'s own first line, so
    it runs before every reconnect) called stream.close() directly too --
    close() can block for up to the connect timeout waiting for the
    background read-thread to join. Must also run via asyncio.to_thread."""
    main_thread = threading.current_thread()
    seen = {}

    class RecordingStream:
        def close(self): seen["thread"] = threading.current_thread()

    atom, _bus, _stream = build(monkey_stream=True)
    atom._stream = RecordingStream()
    run(atom._teardown())
    assert seen.get("thread") is not None, "close() لم يُستدعَ إطلاقاً"
    assert seen["thread"] is not main_thread, (
        "close() نُفِّذ على خيط الحلقة الرئيسي -- سيجمّد كل الذرّات الأخرى")


# ─────────────────────────────────────────────────────────────────────────────
# v1.5.0 (٢٠٢٦-٠٩-٠٩، ختم المالك `NQ`) — اللقطة التي كانت تصل مرّة واحدة.
#
# المقيس حيًّا بعد إقلاع نظيف: الاشتراك يُرسل عند وصول قائمة الأوراق فقط،
# فتصل `W` واحدة ثمّ لا تتكرّر. والدفتر بعدها تزايديّ محض بينما سي‑تريدر لا
# يحذف المستوى الذي هجره — فالعمق من 14 إلى 371 في عشرين دقيقة، والطرفان
# يختلّان (450 عرضًا مقابل 26 طلبًا) حتى يتقاطعا بـ12.61 دولارًا، ورفض 112
# يصعد من ٢٪ إلى ١٦٪ بـ`crossed_spread` وحده. هذه الحرّاس تمنع عودة ذلك.
# ─────────────────────────────────────────────────────────────────────────────


def _md_requests(stream):
    return [raw for raw in stream.sent if b"35=V" in raw]


def test_subscription_is_renewed_after_the_interval():
    """بعد انقضاء المدّة يُطلب السلّم من جديد — فتصل لقطة `W` نظيفة."""
    atom, _bus, stream = build(resubscribe_every_s=300)
    logon_and_list(atom, stream)
    first = len(_md_requests(stream))
    assert first == 2, "الاشتراك الأوّل لرمزين"

    run(atom._refresh_subscriptions())
    assert len(_md_requests(stream)) == first, "جدّد قبل موعده"

    atom._last_subscribe_at -= 301                 # مرّت المدّة
    run(atom._refresh_subscriptions())
    # رسالتان: اشتراك لكل رمز، بلا إلغاء قبله — انظر
    # `test_renewal_does_not_cancel_the_running_subscription`.
    assert len(_md_requests(stream)) == first + 2, "لم يجدّد بعد انقضاء المدّة"
    assert atom._resubscribes == 1


def test_renewal_keeps_the_same_request_id():
    """معرّف الطلب لا يتبدّل: `_on_market_data` يستخرج الرمز منه.

    تغييره كان يقطع الربط بين ردّ الوسيط ورمزه، فتصل تحديثات بلا رمز.
    """
    atom, _bus, stream = build(resubscribe_every_s=300)
    logon_and_list(atom, stream)
    before = _md_requests(stream)[:]
    atom._last_subscribe_at -= 301
    run(atom._refresh_subscriptions())
    after = _md_requests(stream)[len(before):]
    for raw in after:
        assert b"262=MD-1" in raw or b"262=MD-2" in raw, raw


def test_zero_disables_renewal_entirely():
    """صفر = السلوك قبل العيار حرفيًّا — لا طلب إضافيّ أبدًا."""
    atom, _bus, stream = build(resubscribe_every_s=0)
    logon_and_list(atom, stream)
    count = len(_md_requests(stream))
    atom._last_subscribe_at -= 100000
    run(atom._refresh_subscriptions())
    assert len(_md_requests(stream)) == count
    assert atom._resubscribes == 0


def test_absent_dial_behaves_like_zero():
    """مانيفست لم يُحدَّث لا ينكسر ولا يجدّد."""
    atom, _bus, stream = build()
    logon_and_list(atom, stream)
    count = len(_md_requests(stream))
    atom._last_subscribe_at -= 100000
    run(atom._refresh_subscriptions())
    assert len(_md_requests(stream)) == count


def test_no_renewal_before_logon():
    """قبل تسجيل الدخول لا يُرسل شيء — الطلب على وصلة غير مُصادَقة يُرفض."""
    atom, _bus, stream = build(resubscribe_every_s=1)
    atom._by_name = {"BTCUSD": "1"}
    atom._last_subscribe_at = 0.0
    run(atom._refresh_subscriptions())
    assert _md_requests(stream) == []
    assert atom._resubscribes == 0


def test_no_renewal_without_a_symbol_map():
    """بلا خريطة أرقام الرموز لا يُخترع معرّف — لا طلب."""
    atom, _bus, stream = build(resubscribe_every_s=1)
    stream.feed(venue("A", []))
    run(atom._pump())
    atom._by_name = {}
    atom._last_subscribe_at = 0.0
    run(atom._refresh_subscriptions())
    assert _md_requests(stream) == []


def test_health_declares_the_renewal_counter():
    """اللوحة تقرأ التجديد بالرقم — لا تستنتجه من هدوء الرفض."""
    atom, _bus, stream = build(resubscribe_every_s=300)
    atom._running = True          # بلا start(): لا مهمّة خلفية في اختبار
    logon_and_list(atom, stream)
    atom._last_subscribe_at -= 301
    run(atom._refresh_subscriptions())
    health = run(atom.health_check())
    assert "rs=1" in health.message, health.message
    assert health.details["resubscribes"] == 1
    assert health.details["resubscribe_every_s"] == 300


def _sub_types(stream):
    """أنواع طلبات بيانات السوق بالترتيب: '1' اشتراك · '2' إلغاء."""
    out = []
    for raw in stream.sent:
        if b"35=V" not in raw:
            continue
        for part in raw.split(fx.SOH):
            if part.startswith(b"263="):
                out.append(part.split(b"=", 1)[1].decode())
    return out


def test_renewal_does_not_cancel_the_running_subscription():
    """⛔ التجديد لا يُلغي — والإلغاء مُطفأ عمدًا بقياس حيّ، لا بنسيان.

    ٢٠٢٦-٠٩-٠٩: بُني الإلغاء‑ثمّ‑اشتراك على فرضية أنّ إعادة الطلب على اشتراك
    قائم لا تُعيد اللقطة. وحين شُغّل على نواة نظيفة **ضاعف التدفّق بدل أن
    يستبدله**: الوسيط فتح مجرًى ثانيًا للرمز نفسه. المقيس في دقائق —
    عمق الدفتر 143 ⟵ 1,724 · يتامى +38/ث · تقاطع +37/ث · ورفض 112 من ٥.٨٪
    إلى ٢٦٪ — وأُطفئ التجديد كلّه (`resubscribe_every_s: 0`) واحتاج الأمر
    `622/stop` ثمّ `start` لقطع الاشتراكات المزدوجة عند الوسيط.

    هذا الاختبار حارس: من يُعيد `cancel_first=True` يُسقطه، فيقرأ الثمن قبل
    أن يدفعه ثانيةً. والقدرة نفسها باقية في `_send_subscriptions` — تُشغَّل
    فقط بعد أن يُقاس سببُ التواتر (كان `rs` يتقدّم كل عشر ثوانٍ والعتبة 300)
    ويُثبَت أنّ اللقطة تأتي حقًّا.
    """
    atom, _bus, stream = build(resubscribe_every_s=300)
    logon_and_list(atom, stream)
    assert _sub_types(stream) == ["1", "1"], "الاشتراك الأوّل لا يُلغي شيئًا"

    atom._last_subscribe_at -= 301
    run(atom._refresh_subscriptions())
    assert _sub_types(stream) == ["1", "1", "1", "1"], (
        "التجديد يجب أن يكون اشتراكًا بلا إلغاء: %s" % _sub_types(stream))
    assert "2" not in _sub_types(stream), "عاد الإلغاء — اقرأ سبب إطفائه أعلاه"


def test_cancel_capability_is_kept_and_correct():
    """القدرة على الإلغاء تبقى صحيحة وإن كانت مطفأة — لا كودًا ميّتًا مكسورًا.

    تُستدعى صراحةً هنا لأنّ الطريق الحيّ لم يعد يمرّ بها؛ فلو انكسرت بصمت
    لاكتُشف ذلك يوم يُعاد تشغيلها، على السوق لا على الاختبار.
    """
    atom, _bus, stream = build(resubscribe_every_s=300)
    logon_and_list(atom, stream)
    before = len(_md_requests(stream))
    atom._send_subscriptions(cancel_first=True)
    types = _sub_types(stream)[before:]
    assert types == ["2", "1", "2", "1"], types


def test_cancel_and_subscribe_share_the_request_id():
    """الإلغاء يخاطب الاشتراك نفسه — بمعرّفه، وإلّا ألغى لا شيء."""
    atom, _bus, stream = build(resubscribe_every_s=300)
    logon_and_list(atom, stream)
    before = len(stream.sent)
    atom._last_subscribe_at -= 301
    run(atom._refresh_subscriptions())
    for raw in stream.sent[before:]:
        assert b"262=MD-1" in raw or b"262=MD-2" in raw, raw


def test_renewal_survives_a_shared_without_the_cancel():
    """`shared` قديم في الذاكرة لا يكسر الطريق الحيّ — يسقط الإلغاء وحده.

    التحميل الحارّ يطهّر وحدات الذرّة ويُبقي `shared` مخبّأً. ذرّةٌ جديدة
    تنادي توقيعًا لم يصل هناك بعدُ كانت سترمي على كل رسالة — وقع ذلك فعلًا
    في 624 يوم ٢٠٢٦-٠٩-٠٩. هذا الحارس بنيويّ لا تجميليّ.
    """
    atom, _bus, stream = build(resubscribe_every_s=300)
    logon_and_list(atom, stream)

    class OldSession:                       # نسخة بلا الإلغاء
        def __init__(self, real): self._real = real
        def __getattr__(self, name):
            if name == "market_data_unsubscribe":
                raise AttributeError(name)
            return getattr(self._real, name)

    atom._session = OldSession(atom._session)
    before = len(stream.sent)
    atom._last_subscribe_at -= 301
    run(atom._refresh_subscriptions())      # لا يرمي
    assert _sub_types(stream)[-2:] == ["1", "1"], "سقط الإلغاء فقط، والاشتراك مضى"
    assert len(stream.sent) - before == 2
    assert atom._resubscribes == 1


def test_first_subscription_never_cancels():
    """الاشتراك الأوّل لا يسبقه إلغاء — لا شيء ليُلغى، والرسالة الزائدة كلفة."""
    atom, _bus, stream = build(resubscribe_every_s=300)
    logon_and_list(atom, stream)
    assert "2" not in _sub_types(stream)
