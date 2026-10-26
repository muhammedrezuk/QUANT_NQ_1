import asyncio
import inspect
import os
import sqlite3
import sys
import tempfile
import threading
import time

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from pathlib import Path as _Path
sys.path.insert(0, str(_Path(__file__).resolve().parents[4]))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.contracts.atom import AtomContext, HealthState  # noqa: E402
import importlib.util as _ilu  # noqa: E402

_spec = _ilu.spec_from_file_location(
    "_atom707", _Path(__file__).resolve().parents[1] / "atom.py")
_mod = _ilu.module_from_spec(_spec)
sys.modules["_atom707"] = _mod
_spec.loader.exec_module(_mod)
Atom = _mod.Atom
EVENT_APPROVED = _mod.EVENT_APPROVED
EVENT_FINAL = _mod.EVENT_FINAL
EVENT_ORDER_BUILT = _mod.EVENT_ORDER_BUILT
EVENT_OUT = _mod.EVENT_OUT


class _NullLogger:
    def debug(self, *a): pass
    def info(self, *a): pass
    def warning(self, *a): pass
    def error(self, *a): pass
    def critical(self, *a): pass


class _RecordingLogger(_NullLogger):
    """يلتقط ما يُنطق — العطل الصامت لا يصل أحدًا."""

    def __init__(self):
        self.warnings = []
        self.errors = []

    def warning(self, *a):
        self.warnings.append(a)

    def error(self, *a):
        self.errors.append(a)


class FakeEventBus:
    """ناقل وهميّ ينادي المعالجات مباشرة — ويدفع ما تأجّل قبل أن يعود.

    منذ `4.13.0` لا تُكتب مراحل الطوفان (`APPROVED`/`TARGET_STATE`) على القرص
    فور الحدث بل تتجمّع وتُكتب دفعةً كل ثانية. فلو عاد `publish` هنا بلا دفعٍ
    لأصبح كلّ اختبارٍ يقرأ القاعدة بعده سباقًا مع مؤقّت. الدفع هنا يقف مقام
    مرور الثانية، لا أكثر: **متى** تصل الصفوف يُختبَر وحده في
    `test_flood_is_buffered_while_execution_tickets_are_written_at_once`،
    وهناك بلا هذه المساعدة.
    """

    def __init__(self):
        self.published = []
        self._handlers = {}
        self.atom = None

    def subscribe(self, name, handler):
        self._handlers.setdefault(name, []).append(handler)
        # الذرّة تُعرِّف نفسها باشتراكها: `_on_trade` تابعٌ مربوط فيه `__self__`.
        owner = getattr(handler, "__self__", None)
        if owner is not None:
            self.atom = owner

    async def publish(self, name, payload):
        self.published.append((name, payload))
        for h in self._handlers.get(name, []):
            r = h(payload)
            if inspect.isawaitable(r):
                await r
        atom = self.atom
        if atom is not None and getattr(atom, "_buffer", None):
            await atom._flush_buffer()

    def make_context(self, cfg, logger=None):
        return AtomContext(atom_id=707, config=cfg, logger=logger or _NullLogger(),
                           publish=self.publish, subscribe=self.subscribe)


def _tmp_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.unlink(path)
    return path


def _query(db_path, sql, params=()):
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute(sql, params).fetchall()
    finally:
        conn.close()


# الذرّات الحيّة في الاختبار الجاري. الاتصال معمَّر منذ v4.4.0، فالقاعدة تبقى
# ممسوكة حتى `stop()` — وهذا نفسه سلوك يُختبَر أدناه.
_LIVE: list = []


async def _make(bus, db_path, keep_payload=True):
    atom = Atom()
    await atom.initialize(bus.make_context(
        {"db_path": db_path, "keep_full_payload": keep_payload}))
    await atom.start()
    _LIVE.append(atom)
    return atom


async def _shutdown():
    """إيقاف كل ذرّة أنشأها الاختبار — يُغلق الاتصال المعمَّر ويحرّر الملف."""
    while _LIVE:
        atom = _LIVE.pop()
        try:
            await atom.stop()
        except Exception:  # noqa: BLE001 — التنظيف لا يُسقط اختبارًا
            pass


async def test_flood_is_buffered_while_execution_tickets_are_written_at_once():
    """التأجيل يشمل الطوفان وحده — والتذكرة تصل القرص فورًا.

    مقيس ٢٠٢٦-٠٩-١٦ أنّ ثلثَي زمن معالج ٧٠٧ جدولةٌ لا عمل: ذهابٌ وإيابٌ إلى
    خيطٍ عامل لأجل صفٍّ واحد (٢٦٫١ م.ث للعودة وحدها من ٤٨٫٤). فصار الطوفان
    يُجمَّع ويُكتب دفعةً. والخطر المقابل واضح: صفٌّ في الذاكرة ليس صفًّا على
    القرص. فهذا الاختبار يثبّت الحدّ من الجهتين معًا — أنّ تذكرة التنفيذ
    **لا** تُؤجَّل، وأنّ المؤجَّل **يصل** بالمؤقّت وحده بلا دفعٍ يدويّ.
    """
    print("\n--- test_flood_is_buffered_while_execution_tickets_are_written_at_once ---")
    db = _tmp_db()
    try:
        bus = FakeEventBus()
        atom = await _make(bus, db)
        bus.atom = None  # لا دفع من الناقل: المؤقّت وحده هو المُختبَر

        await atom._store(_mod.STAGE_TARGET, {"request_id": "flood", "account_id": "A1"})
        assert len(atom._buffer) == 1, atom._buffer
        assert _query(db, "SELECT COUNT(*) FROM decisions")[0][0] == 0, "الطوفان وصل القرص فورًا"

        # التذكرة والقرار الذي مرّ من البوّابة: كلاهما فوريّ لأنّه لا يُعوَّض.
        await atom._store(_mod.STAGE_ORDER_BUILT, {"request_id": "ticket", "account_id": "A1"})
        await atom._store(_mod.STAGE_APPROVED, {"request_id": "approved", "account_id": "A1",
                                                "approved": True})
        on_disk = sorted(r[0] for r in _query(db, "SELECT request_id FROM decisions"))
        assert on_disk == ["approved", "ticket"], on_disk

        deadline = time.monotonic() + _mod._BUFFERED_FLUSH_S * 5
        while time.monotonic() < deadline:
            await asyncio.sleep(0.05)
            if _query(db, "SELECT COUNT(*) FROM decisions")[0][0] >= 3:
                break
        rows = sorted(r[0] for r in _query(db, "SELECT request_id FROM decisions"))
        assert rows == ["approved", "flood", "ticket"], rows
        assert atom._buffer == [], atom._buffer
        print("OK — التذكرة والمقبول على القرص فورًا، و`TARGET_STATE` بعد %.1f ث"
              " بلا دفعٍ يدويّ: %s" % (_mod._BUFFERED_FLUSH_S, rows))
    finally:
        await _shutdown()
        for suffix in ("", "-wal", "-shm"):
            if os.path.exists(db + suffix):
                os.unlink(db + suffix)


async def test_the_gate_verdict_decides_what_waits_not_the_stage_name():
    """القرار المقبول يُكتب فورًا، والمرفوض يُجمَّع — والاسم واحد.

    مقيس ٢٠٢٦-٠٩-١٦ على القاعدة الحيّة: المسار الفوريّ ٣٫٧١ صفّ/ث، **منه
    ٣٫٢٢ قراراتٌ مرفوضة (٨٧٪)** و٠٫٢١ فقط مرّت من البوّابة. فالقطع بالمرحلة
    كان يخلط ما لا يجمعه إلّا الاسم. هنا يُثبَّت المعيار الجديد من ثلاث
    جهات: مقبولٌ فورًا · مرفوضٌ يُجمَّع · وبلا حقلٍ صريح يُعامَل معاملة
    المرفوض (فقرارٌ بلا إقرار ليس ناجحًا).
    """
    print("\n--- test_the_gate_verdict_decides_what_waits_not_the_stage_name ---")
    db = _tmp_db()
    try:
        bus = FakeEventBus()
        atom = await _make(bus, db)
        bus.atom = None

        await atom._store(_mod.STAGE_APPROVED, {"request_id": "passed", "account_id": "A1",
                                                "approved": True})
        assert atom._buffer == [], "المقبول تأجّل"
        assert [r[0] for r in _query(db, "SELECT request_id FROM decisions")] == ["passed"]

        await atom._store(_mod.STAGE_APPROVED, {"request_id": "refused", "account_id": "A1",
                                                "approved": False})
        await atom._store(_mod.STAGE_APPROVED, {"request_id": "silent", "account_id": "A1"})
        assert len(atom._buffer) == 2, atom._buffer
        assert [r[0] for r in _query(db, "SELECT request_id FROM decisions")] == ["passed"]

        await atom._flush_buffer()
        rows = _query(db, "SELECT request_id, COALESCE(approved,0) FROM decisions"
                          " ORDER BY request_id")
        assert rows == [("passed", 1), ("refused", 0), ("silent", 0)], rows
        print("OK — مرّ من البوّابة ⇒ القرص فورًا · رُفض أو سكت ⇒ الدفعة: %s"
              % [r[0] for r in rows])
    finally:
        await _shutdown()
        for suffix in ("", "-wal", "-shm"):
            if os.path.exists(db + suffix):
                os.unlink(db + suffix)


async def test_buffered_rows_are_not_lost_when_the_atom_stops():
    """الإيقاف يكتب ما تأجّل — وإلّا كان التأجيل فقدًا مؤجَّلًا."""
    print("\n--- test_buffered_rows_are_not_lost_when_the_atom_stops ---")
    db = _tmp_db()
    try:
        bus = FakeEventBus()
        atom = await _make(bus, db)
        bus.atom = None
        for i in range(7):
            await atom._store(_mod.STAGE_TARGET, {"request_id": "s%d" % i, "account_id": "A1"})
        assert _query(db, "SELECT COUNT(*) FROM decisions")[0][0] == 0
        await _shutdown()
        count = _query(db, "SELECT COUNT(*) FROM decisions")[0][0]
        assert count == 7, count
        print("OK — سبعة صفوف كانت في الذاكرة ووصلت القرص عند الإيقاف")
    finally:
        await _shutdown()
        for suffix in ("", "-wal", "-shm"):
            if os.path.exists(db + suffix):
                os.unlink(db + suffix)


async def test_stores_decision_with_identity():
    print("\n--- test_stores_decision_with_identity ---")
    db = _tmp_db()
    try:
        bus = FakeEventBus()
        await _make(bus, db)
        await bus.publish(EVENT_APPROVED, {
            "request_id": "r1", "account_id": "A1", "symbol": "NQ100",
            "direction": "BUY", "approved": True, "confidence": 0.8,
            "strategy_id": "breakout", "model_id": "m7", "timestamp": 3.0})
        rows = _query(db, "SELECT stage, account_id, strategy_id, model_id, approved,"
                          " confidence FROM decisions WHERE request_id='r1'")
        assert rows == [("APPROVED", "A1", "breakout", "m7", 1, 0.8)], rows
        print(f"OK — قرار مع مفاتيح الهوية (account/strategy/model — قاعدة ٢٢): {rows[0]}")
    finally:
        await _shutdown()
        os.unlink(db)


async def test_metadata_fallback():
    print("\n--- test_metadata_fallback ---")
    db = _tmp_db()
    try:
        bus = FakeEventBus()
        await _make(bus, db)
        # decision.approved.state (466) يحمل approved/direction بالميتاداتا لا بالأعلى
        await bus.publish(EVENT_APPROVED, {
            "request_id": "r2", "account_id": "A1", "symbol": "BTCUSD",
            "metadata": {"approved": False, "direction": "sell", "confidence": 0.3}})
        rows = _query(db, "SELECT direction, approved, confidence FROM decisions"
                          " WHERE request_id='r2'")
        assert rows == [("sell", 0, 0.3)], rows
        print(f"OK — استخراج من الميتاداتا احتياطًا (approved/direction/confidence): {rows[0]}")
    finally:
        await _shutdown()
        os.unlink(db)


async def test_multi_stage_by_request():
    print("\n--- test_multi_stage_by_request ---")
    db = _tmp_db()
    try:
        bus = FakeEventBus()
        await _make(bus, db)
        await bus.publish(EVENT_APPROVED, {"request_id": "r9", "account_id": "A1"})
        await bus.publish(EVENT_ORDER_BUILT, {"request_id": "r9", "account_id": "A1",
                                              "volume": 1.5})
        await bus.publish(EVENT_FINAL, {"request_id": "r9", "account_id": "A1"})
        stages = [r[0] for r in _query(
            db, "SELECT stage FROM decisions WHERE request_id='r9' ORDER BY id")]
        assert stages == ["APPROVED", "ORDER_BUILT", "DECISION_FINALIZED"], stages
        print(f"OK — تتبّع القرار عبر مراحله بنفس request_id: {stages}")
    finally:
        await _shutdown()
        os.unlink(db)


async def test_stores_decision_link_columns():
    print("\n--- test_stores_decision_link_columns ---")
    db = _tmp_db()
    try:
        bus = FakeEventBus()
        await _make(bus, db)
        await bus.publish(EVENT_APPROVED, {
            "request_id": "r5", "account_id": "A1", "symbol": "NQ100",
            "decision_id": "dec:5", "gate_request_id": "gate:5"})
        rows = _query(db, "SELECT decision_id, gate_request_id FROM decisions"
                          " WHERE request_id='r5'")
        assert rows == [("dec:5", "gate:5")], rows
        print(f"OK — عمودا الربط decision_id/gate_request_id يُخزَّنان: {rows[0]}")
    finally:
        await _shutdown()
        os.unlink(db)


async def test_link_columns_absent_stay_null():
    print("\n--- test_link_columns_absent_stay_null ---")
    db = _tmp_db()
    try:
        bus = FakeEventBus()
        await _make(bus, db)
        await bus.publish(EVENT_APPROVED, {"request_id": "r6", "account_id": "A1"})
        rows = _query(db, "SELECT decision_id, gate_request_id FROM decisions"
                          " WHERE request_id='r6'")
        assert rows == [(None, None)], rows
        print("OK — بلا هوية بالحمولة: العمودان NULL صريحة -- لا اختراع")
    finally:
        await _shutdown()
        os.unlink(db)


async def test_migrates_existing_database_without_link_columns():
    print("\n--- test_migrates_existing_database_without_link_columns ---")
    db = _tmp_db()
    try:
        # قاعدة قديمة بمخطط بلا العمودين الجديدين إطلاقًا -- المهاجرة
        # الحقيقية: عمود يُضاف لجدول قائم فيه صفوف، بلا فقد بيانات.
        conn = sqlite3.connect(db)
        conn.execute("""CREATE TABLE decisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT, stage TEXT NOT NULL,
            request_id TEXT, account_id TEXT, symbol TEXT, direction TEXT,
            approved INTEGER, reason TEXT, confidence REAL, strategy_id TEXT,
            model_id TEXT, volume REAL, stop_loss REAL, take_profit REAL,
            payload_json TEXT, decided_at REAL)""")
        conn.execute("INSERT INTO decisions (stage, request_id, account_id) "
                     "VALUES ('APPROVED', 'old1', 'A1')")
        conn.commit(); conn.close()

        bus = FakeEventBus()
        atom = await _make(bus, db)
        columns = {row[1] for row in _query(db, "PRAGMA table_info(decisions)")}
        assert {"decision_id", "gate_request_id"} <= columns, columns
        old_row = _query(db, "SELECT request_id, decision_id, gate_request_id"
                             " FROM decisions WHERE request_id='old1'")
        assert old_row == [("old1", None, None)], old_row
        print("OK — الصفّ القديم نجا من الهجرة والعمودان الجديدان NULL له")

        await bus.publish(EVENT_APPROVED, {
            "request_id": "new1", "account_id": "A1",
            "decision_id": "dec:9", "gate_request_id": "gate:9"})
        new_row = _query(db, "SELECT decision_id, gate_request_id FROM decisions"
                             " WHERE request_id='new1'")
        assert new_row == [("dec:9", "gate:9")], new_row
        print("OK — بعد الهجرة: صف جديد يخزّن العمودين بلا مشكلة")

        # محاكاة إعادة تشغيل: مثيل ثانٍ على نفس القاعدة المهاجَرة أصلًا --
        # ALTER TABLE على عمود موجود مسبقًا يجب ألا يفشل.
        atom2 = Atom()
        await atom2.initialize(bus.make_context({"db_path": db, "keep_full_payload": True}))
        await atom2.start()
        health = await atom2.health_check()
        assert health.details["store_ready"] is True, health.details
        print("OK — إعادة التشغيل على قاعدة مهاجَرة أصلًا لا تفشل (العمود موجود مسبقًا)")
    finally:
        await _shutdown()
        os.unlink(db)


async def test_health_states():
    print("\n--- test_health_states ---")
    db = _tmp_db()
    try:
        bus = FakeEventBus()
        atom = Atom()
        await atom.initialize(bus.make_context(
            {"db_path": db, "keep_full_payload": True}))
        assert (await atom.health_check()).state == HealthState.UNHEALTHY
        await atom.start()
        _LIVE.append(atom)
        assert (await atom.health_check()).state == HealthState.DEGRADED
        await bus.publish(EVENT_APPROVED, {"request_id": "r1", "account_id": "A1"})
        assert (await atom.health_check()).state == HealthState.HEALTHY
        print("OK — الصحة: UNHEALTHY -> DEGRADED -> HEALTHY")
    finally:
        await _shutdown()
        os.unlink(db)


async def test_rejection_reason_is_stored_beside_layer_reason():
    print("\n--- test_rejection_reason_is_stored_beside_layer_reason ---")
    db = _tmp_db()
    try:
        bus = FakeEventBus()
        await _make(bus, db)
        # حمولة ٤٦٦ الفعليّة: تصنيف الطبقة في metadata.reason، والسبب الحقيقي
        # في rejection.reason (بنية مأخوذة من صفّ حيّ يوم ٢٠٢٦-٠٩-٠٩).
        await bus.publish(EVENT_APPROVED, {
            "request_id": "rj1", "account_id": "A1", "symbol": "BTCUSD",
            "approved": False,
            "metadata": {"approved": False, "reason": "BLOCKED_UPSTREAM"},
            "rejection": {"reason": "DECISION_SIDE_WAIT", "stage": "454",
                          "value": "wait", "threshold": None},
            "barriers": [{"name": "signal_wait", "reason": "DECISION_SIDE_WAIT"}]})
        rows = _query(db, "SELECT reason, rejection_reason FROM decisions"
                          " WHERE request_id='rj1'")
        assert rows == [("BLOCKED_UPSTREAM", "DECISION_SIDE_WAIT")], rows
        # وبلا rejection يبقى العمود NULL — لا اختراع
        await bus.publish(EVENT_APPROVED, {
            "request_id": "rj2", "account_id": "A1", "approved": True})
        rows2 = _query(db, "SELECT rejection_reason FROM decisions WHERE request_id='rj2'")
        assert rows2 == [(None,)], rows2
        print(f"OK — العمودان يتعايشان: {rows[0]} · وبلا rejection يبقى NULL")
    finally:
        await _shutdown()
        os.unlink(db)


async def test_skew_is_read_from_the_new_contract_fields():
    """العقد تغيّر ٢٠٢٦-٠٩-١٦ — والعدّاد يجب ألّا يعمى.

    ٦١١ v4.1.0 صار يضع `timestamp` بساعتنا وينقل طابع الوسيط إلى
    `broker_time` مع `clock_skew_s`. قياسُ الانحراف من `timestamp` وحده
    يتوقّف عن الزيادة — لا لأنّ العلّة زالت بل لأنّ مكانها تبدّل.
    """
    print("\n--- test_skew_is_read_from_the_new_contract_fields ---")
    db = _tmp_db()
    logger = _RecordingLogger()
    try:
        bus = FakeEventBus()
        atom = Atom()
        await atom.initialize(bus.make_context(
            {"db_path": db, "keep_full_payload": True}, logger=logger))
        await atom.start()
        _LIVE.append(atom)
        now = time.time()
        # الحمولة الجديدة: الطابع سليم والانحراف في حقله الخاصّ
        await bus.publish(EVENT_APPROVED, {
            "request_id": "n1", "account_id": "A1", "timestamp": now,
            "broker_time": now + 8784.0, "clock_skew_s": 8784.0})
        assert atom.future_stamp_count == 1, "العدّاد عمي عن الحقل الجديد"
        assert logger.warnings, "الانحراف ما وصل السجلّ"
        # وبلا `clock_skew_s`: يُشتقّ من `broker_time`
        await bus.publish(EVENT_APPROVED, {
            "request_id": "n2", "account_id": "A1", "timestamp": now,
            "broker_time": now + 8784.0})
        assert atom.future_stamp_count == 2, atom.future_stamp_count
        # وحمولة سليمة تمامًا لا تُعدّ
        await bus.publish(EVENT_APPROVED, {"request_id": "n3",
                                           "account_id": "A1",
                                           "timestamp": time.time()})
        assert atom.future_stamp_count == 2, atom.future_stamp_count
        # والطابع نفسه لم يُمسّ
        rows = _query(db, "SELECT decided_at FROM decisions WHERE request_id='n1'")
        assert abs(rows[0][0] - now) < 1, rows
        print(f"OK — قُرئ من الحقل الجاهز ثم اشتُقّ من broker_time"
              f" · السليم لا يُعدّ · العدّاد={atom.future_stamp_count}")
    finally:
        await _shutdown()
        for suffix in ("", "-wal", "-shm"):
            if os.path.exists(db + suffix):
                os.unlink(db + suffix)


async def test_future_stamp_is_recorded_and_spoken_not_corrected():
    print("\n--- test_future_stamp_is_recorded_and_spoken_not_corrected ---")
    db = _tmp_db()
    logger = _RecordingLogger()
    try:
        bus = FakeEventBus()
        atom = Atom()
        await atom.initialize(bus.make_context(
            {"db_path": db, "keep_full_payload": True}, logger=logger))
        await atom.start()
        _LIVE.append(atom)
        # طابع الوسيط: ثلاث ساعات في المستقبل (المقيس على الحيّ ٢٠٢٦-٠٩-٠٩)
        future = time.time() + 10800.0
        await bus.publish(EVENT_APPROVED, {"request_id": "f1", "account_id": "A1",
                                           "timestamp": future})
        rows = _query(db, "SELECT decided_at, recorded_at FROM decisions"
                          " WHERE request_id='f1'")
        decided, recorded = rows[0]
        assert abs(decided - future) < 0.001, "الطابع صُحِّح — والتصحيح تخمين"
        assert recorded is not None and recorded < decided, (recorded, decided)
        assert abs((decided - recorded) - 10800.0) < 60.0, decided - recorded
        assert atom.future_stamp_count == 1, atom.future_stamp_count
        assert logger.warnings, "الانحراف ما وصل السجلّ"
        # وطابع سليم لا يُحسب انحرافًا
        await bus.publish(EVENT_APPROVED, {"request_id": "f2", "account_id": "A1",
                                           "timestamp": time.time()})
        assert atom.future_stamp_count == 1, atom.future_stamp_count
        print(f"OK — الطابع خُزّن كما جاء (فرق {decided - recorded:.0f}س)"
              f" · ساعة الاستلام محفوظة · ونُطق في السجلّ")
    finally:
        await _shutdown()
        os.unlink(db)


async def test_ceiling_never_evicts_execution_tickets():
    print("\n--- test_ceiling_never_evicts_execution_tickets ---")
    db = _tmp_db()
    try:
        bus = FakeEventBus()
        atom = await _make(bus, db)
        # تذكرة تنفيذ واحدة أوّلًا (فهي الأقدم = أوّل ما يُحذف بالأقدميّة)،
        # ثم طوفان حالات الهدف كما على الحيّ (٨٣٪ من الجدول).
        await bus.publish(_mod.EVENT_ACK, {"request_id": "tk1", "account_id": "A1",
                                           "symbol": "EURUSD"})
        # ٢٠٢٦-١٠-٠٧: حدث الهدف بلا ناشر (٥٨١ أُرشف) — فالطوفان يُبنى بالمرحلة
        # مباشرةً، كصفوف TARGET_STATE القديمة الباقية في القاعدة الحيّة.
        for i in range(60):
            await atom._store(_mod.STAGE_TARGET, {"request_id": "t%d" % i,
                                                  "account_id": "A1"})
        await atom._flush_buffer()
        before = _query(db, "SELECT COUNT(*) FROM decisions")[0][0]
        assert before == 61, before
        # سقف صفوف قاسٍ: لا يُبقي إلّا خمسة
        _mod.enforce_limits(db, "decisions", max_rows=5,
                            protect_where=_mod._PROTECTED_WHERE)
        stages = [r[0] for r in _query(
            db, "SELECT stage FROM decisions ORDER BY id")]
        assert "BROKER_ACKNOWLEDGED" in stages, stages
        assert stages.count("TARGET_STATE") <= 5, stages.count("TARGET_STATE")
        print(f"OK — بعد سقفٍ قاسٍ بقيت تذكرة التنفيذ: {stages[:3]}…"
              f" · حالات هدف باقية={stages.count('TARGET_STATE')}")
    finally:
        await _shutdown()
        for suffix in ("", "-wal", "-shm"):
            if os.path.exists(db + suffix):
                os.unlink(db + suffix)


async def test_approved_decision_survives_the_cap():
    """القرار المقبول لا يطرده السقف — وإلّا بقيت الصفقة بلا سبب.

    مقيس ٢٠٢٦-٠٩-١٦: من ٤٤ تذكرة بهويّة قرار، واحدة فقط كان لها `APPROVED`
    و٤٠ لها `DISPATCH` — لأنّ الأولى لم تكن محميّة والثانية محميّة.
    """
    print("\n--- test_approved_decision_survives_the_cap ---")
    db = _tmp_db()
    try:
        bus = FakeEventBus()
        atom = await _make(bus, db)
        # قرار مقبول أوّلًا (فهو الأقدم = أوّل ما يُخرجه السقف بالأقدميّة)
        await bus.publish(EVENT_APPROVED, {"request_id": "keep", "account_id": "A1",
                                           "symbol": "USTEC", "approved": True,
                                           "decision_id": "dec:keep"})
        # ورفضٌ قديم — يجوز إخراجه
        await bus.publish(EVENT_APPROVED, {"request_id": "drop", "account_id": "A1",
                                           "approved": False})
        for i in range(60):
            await atom._store(_mod.STAGE_TARGET, {"request_id": "t%d" % i,
                                                  "account_id": "A1"})
        await atom._flush_buffer()
        _mod.enforce_limits(db, "decisions", max_rows=5,
                            protect_where=_mod._PROTECTED_WHERE)
        rows = _query(db, "SELECT request_id, approved FROM decisions "
                          "WHERE stage='APPROVED' ORDER BY id")
        ids = {r[0] for r in rows}
        assert "keep" in ids, "القرار المقبول طرده السقف: %s" % rows
        assert "drop" not in ids, "المرفوض بقي رغم السقف: %s" % rows
        print(f"OK — المقبول نجا والمرفوض خرج: {rows}")
    finally:
        await _shutdown()
        for suffix in ("", "-wal", "-shm"):
            if os.path.exists(db + suffix):
                os.unlink(db + suffix)


async def test_failed_store_is_spoken_not_counted_in_silence():
    print("\n--- test_failed_store_is_spoken_not_counted_in_silence ---")
    db = _tmp_db()
    logger = _RecordingLogger()
    try:
        bus = FakeEventBus()
        atom = Atom()
        await atom.initialize(bus.make_context(
            {"db_path": db, "keep_full_payload": True}, logger=logger))
        await atom.start()
        _LIVE.append(atom)
        await atom._store("NOT_A_REAL_STAGE", {"request_id": "x1"})
        assert atom.failure_count == 1, atom.failure_count
        assert logger.errors, "الإخفاق ما وصل السجلّ — عُدّ في صمت"
        text = " ".join(str(a) for a in logger.errors[0])
        assert "INVALID_DECISION_STAGE" in text or "%s" in text, text
        print(f"OK — إخفاق التخزين نُطق في السجلّ ({len(logger.errors)})"
              f" · العدّاد={atom.failure_count}")
    finally:
        await _shutdown()
        for suffix in ("", "-wal", "-shm"):
            if os.path.exists(db + suffix):
                os.unlink(db + suffix)


async def test_connection_is_reused_and_released_on_failure():
    print("\n--- test_connection_is_reused_and_released_on_failure ---")
    db = _tmp_db()
    try:
        bus = FakeEventBus()
        atom = await _make(bus, db)
        await bus.publish(EVENT_APPROVED, {"request_id": "c1", "account_id": "A1"})
        first = atom._conn
        assert first is not None, "ما بقي اتصال معمَّر"
        for i in range(10):
            await bus.publish(EVENT_APPROVED, {"request_id": "c%d" % (i + 2),
                                               "account_id": "A1"})
        assert atom._conn is first, "أُعيد فتح الاتصال — التعمير لا يعمل"
        assert atom.stored_count == 11, atom.stored_count

        # فشل كتابة: يجب أن يُطرح الاتصال ويُحرَّر الملف — وإلّا تعذّر إصلاح
        # ما تلف (الدرس المقيس يوم ٢٠٢٦-٠٩-٠٩ على analysis.db).
        atom._conn.close()          # اتصال معطوب في اليد
        await bus.publish(EVENT_APPROVED, {"request_id": "c99", "account_id": "A1"})
        assert atom._conn is None, "الاتصال المعطوب بقي معمَّرًا"
        assert atom._store_ready is False, "بقي المخزن «جاهزًا» بعد فشل كتابة"
        assert atom.failure_count >= 1, atom.failure_count
        os.unlink(db)               # يبرهن أنّ الملف تُرك حرًّا
        print(f"OK — اتصال واحد لـ١١ إدراجًا · وعند الفشل تُرك الملف حرًّا"
              f" (حُذف بنجاح) · فشل={atom.failure_count}")
    finally:
        await _shutdown()
        for suffix in ("", "-wal", "-shm"):
            if os.path.exists(db + suffix):
                os.unlink(db + suffix)


async def test_cap_moves_rows_to_archive_instead_of_destroying_them():
    """أمر المالك ٢٠٢٦-٠٩-١٠: ما يخرجه السقف يُرحَّل ولا يُتلف."""
    print("\n--- test_cap_moves_rows_to_archive_instead_of_destroying_them ---")
    db = _tmp_db()
    arch = db + ".archive.db"
    try:
        bus = FakeEventBus()
        atom = Atom()
        await atom.initialize(bus.make_context(
            {"db_path": db, "keep_full_payload": True, "max_rows": 2,
             "max_db_bytes": 10_000_000, "archive_db_path": arch}))
        await atom.start()
        _LIVE.append(atom)
        for i in range(5):
            await bus.publish(EVENT_APPROVED, {"request_id": "a%d" % i,
                                               "symbol": "EURUSD", "timestamp": i})
        left = _query(db, "SELECT request_id FROM decisions ORDER BY id")
        moved = _query(arch, "SELECT request_id FROM decisions ORDER BY id")
        ids_left = {r[0] for r in left}
        ids_moved = {r[0] for r in moved}
        # الجوهر: **لا صفّ يضيع**. والعدد الباقي ≤ السقف + هامش الفحص، لا
        # السقف بالضبط — الهامش مقصود ومقيس (وثيقة `_ROW_SLACK_DIVISOR`).
        assert ids_moved, "ما رُحّل شيء رغم تجاوز السقف"
        assert ids_left | ids_moved == {"a0", "a1", "a2", "a3", "a4"}, (ids_left, ids_moved)
        assert not (ids_left & ids_moved), "صفّ في المخزن والأرشيف معًا"
        assert len(left) <= 3, left
        # والأقدم هو ما يُرحَّل، لا العشوائيّ
        assert "a0" in ids_moved, ids_moved
        assert atom._limit_state.get("archived") == len(moved), atom._limit_state
        print(f"OK — بقي {sorted(ids_left)} في المخزن، ورُحّل {sorted(ids_moved)}"
              f" إلى الأرشيف · لا صفّ أُتلف")
    finally:
        await _shutdown()
        for base in (db, arch):
            for suffix in ("", "-wal", "-shm"):
                if os.path.exists(base + suffix):
                    os.unlink(base + suffix)


async def test_archive_failure_blocks_destruction():
    """تعذُّر الأرشيف يوقف الإنفاذ — لا يُتلف صفٌّ لأنّ الأرشيف غاب."""
    print("\n--- test_archive_failure_blocks_destruction ---")
    db = _tmp_db()
    blocked = _tmp_db()
    try:
        # ملفٌ ليس قاعدة في موضع الأرشيف ⇒ الربط يفشل
        with open(blocked, "wb") as handle:
            handle.write(b"NOT-A-SQLITE-DATABASE" * 64)
        bus = FakeEventBus()
        logger = _RecordingLogger()
        atom = Atom()
        await atom.initialize(bus.make_context(
            {"db_path": db, "keep_full_payload": True, "max_rows": 2,
             "max_db_bytes": 10_000_000, "archive_db_path": blocked}, logger=logger))
        await atom.start()
        _LIVE.append(atom)
        for i in range(5):
            await bus.publish(EVENT_APPROVED, {"request_id": "b%d" % i, "timestamp": i})
        n = _query(db, "SELECT COUNT(*) FROM decisions")[0][0]
        assert n == 5, "أُتلفت صفوف رغم غياب الأرشيف: بقي %d" % n
        assert atom._limit_state.get("archive_error"), atom._limit_state
        assert logger.errors, "تعذُّر الأرشيف ما وصل السجلّ"
        print(f"OK — الأرشيف متعذّر ⇒ بقيت الصفوف الخمس كلّها، والسبب منطوق:"
              f" {atom._limit_state.get('archive_error')[:48]}")
    finally:
        await _shutdown()
        for base in (db, blocked):
            for suffix in ("", "-wal", "-shm"):
                if os.path.exists(base + suffix):
                    os.unlink(base + suffix)


async def test_backfills_rejection_reason_for_old_rows():
    """الصفوف التي سبقت العمود تُملأ من حمولتها — بلا سكربت خارجيّ."""
    print("\n--- test_backfills_rejection_reason_for_old_rows ---")
    db = _tmp_db()
    try:
        bus = FakeEventBus()
        atom = await _make(bus, db)
        # صفوف «قديمة»: حمولتها تحمل السبب والعمود فارغ (كحال ٧٢٬٦٦٦ رفضة)
        conn = sqlite3.connect(db)
        try:
            conn.executemany(
                "INSERT INTO decisions (stage, request_id, payload_json,"
                " rejection_reason) VALUES ('APPROVED', ?, ?, NULL)",
                [("old%d" % i,
                  '{"rejection": {"reason": "DECISION_SIDE_WAIT"}}')
                 for i in range(5)])
            conn.commit()
        finally:
            conn.close()
        before = _query(db, "SELECT COUNT(*) FROM decisions"
                            " WHERE rejection_reason IS NULL")[0][0]
        assert before == 5, before
        moved = await asyncio.to_thread(atom._backfill_once)
        assert moved == 5, moved
        rows = _query(db, "SELECT DISTINCT rejection_reason FROM decisions"
                          " WHERE request_id LIKE 'old%'")
        assert rows == [("DECISION_SIDE_WAIT",)], rows
        # وجولة ثانية لا تجد شيئًا ⇒ الترحيل يتوقّف من نفسه
        assert await asyncio.to_thread(atom._backfill_once) == 0
        print(f"OK — رُحّل {moved} صفًّا قديمًا من الحمولة، والجولة التالية صفر")
    finally:
        await _shutdown()
        for suffix in ("", "-wal", "-shm"):
            if os.path.exists(db + suffix):
                os.unlink(db + suffix)


async def test_overflow_drops_the_flood_not_the_approved():
    """حين يفيض البفر يُقصّ الطوفان لا القرارُ المقبول — والمقصوص يُسمّى.

    ⚠️ وقع فعلًا ٢٠٢٦-٠٩-٢٣: **١٬٣٤٩ قرارًا أُسقطت** والبفر ممتلئ عند
    ١٠٬٠٠٠، لأنّ النسخة الاحتياطيّة تقرأ القواعد نفسها فقفز `sqlite` إلى
    **٤٬٨٥٧ م.ث** للإدراج الواحد. والقصُّ كان بالأقدميّة عمياءَ — يخلط ما لا
    يُعوَّض بما يتكرّر كلّ تِكّة (`TARGET_STATE` ٨٣٪ من الجدول مقيسًا).
    """
    print("\n--- test_overflow_drops_the_flood_not_the_approved ---")
    db = _tmp_db()
    try:
        bus = FakeEventBus()
        atom = await _make(bus, db)
        bus.atom = None

        cap = _mod._BUFFER_HARD_CAP
        # قرارٌ مقبولٌ واحدٌ أوّلًا (الأقدم — كان يُقصّ أوّلًا بالقاعدة القديمة)
        atom._buffer = [(_mod.STAGE_APPROVED, {"request_id": "KEEP",
                                               "account_id": "A1"})]
        atom._buffer += [(_mod.STAGE_TARGET, {"request_id": "F%d" % i,
                                              "account_id": "A1"})
                         for i in range(cap + 49)]
        assert len(atom._buffer) == cap + 50

        atom._trim_buffer()

        assert len(atom._buffer) == cap, len(atom._buffer)
        assert atom.buffered_dropped == 50, atom.buffered_dropped
        stages = {row[0] for row in atom._buffer}
        assert _mod.STAGE_APPROVED in stages, "قُصّ القرار المقبول"
        assert "TARGET_STATE=50" in atom._last_error, atom._last_error
        print("OK — قُصّ ٥٠ طوفانًا · المقبول باقٍ · والسبب: %s"
              % atom._last_error)
    finally:
        # البفر هنا حشوٌ للاختبار لا بيانات: يُفرَّغ **في كلّ الأحوال** فلا
        # يكتب الإغلاقُ عشرة آلاف صفٍّ ويحتجز الملفّ. وكان في مسار النجاح
        # وحده، فكان التعطيب يفشل بـ`PermissionError` بدل أن يُظهر الحكم.
        atom._buffer = []
        await _shutdown()
        for suffix in ("", "-wal", "-shm"):
            if os.path.exists(db + suffix):
                os.unlink(db + suffix)


async def test_enforcement_skips_a_busy_lock_and_never_blocks_the_handler():
    """الإنفاذ يُنفَّذ فورًا حين يخلو القفل، ويُتخطّى حين يمسكه جار.

    ثالثُ انتظارٍ في هذا المعالج، والنمط نفسه للمرّة الثالثة. مقيس
    ٢٠٢٦-٠٩-٢٣ بعد `4.17.0`: `handler timeout` صار **صفرًا** (كان ١١٠ أمس)
    لكنّ **المعالج أسوأه ٢٦٬٢٥٦٫٥ م.ث** ولا يفسّره عدّاد — فبقي هذا المسار
    غير مقيس: `await self._enforce_limits()` يأخذ قفل الملفّ بلا مهلة.
    """
    print("\n--- test_enforcement_skips_a_busy_lock_and_never_blocks_the_handler ---")
    db = _tmp_db()
    try:
        bus = FakeEventBus()
        atom = await _make(bus, db)

        # ١) القفل حرّ ⟹ الإنفاذ يقع فعلًا (العقد الذي يطلب قصًّا فوريًّا)
        before = atom.enforce_skipped
        await atom._enforce_limits()
        assert atom.enforce_skipped == before, "تُخطّي الإنفاذ والقفل حرّ"

        # ٢) جارٌ يمسك القفل ⟹ يُتخطّى ولا يُنتظَر
        held, release = threading.Event(), threading.Event()

        def neighbour():
            with atom._conn_lock:
                held.set()
                release.wait(timeout=10)

        worker = threading.Thread(target=neighbour, daemon=True)
        worker.start()
        assert held.wait(timeout=5), "الجار ما أمسك القفل"
        try:
            started = time.perf_counter()
            await atom._enforce_limits()
            elapsed = time.perf_counter() - started
        finally:
            release.set()
            worker.join(timeout=5)

        assert elapsed < 0.050, (
            "الإنفاذ انتظر %.3f ث والميزانية ٠٫٠٥٠" % elapsed)
        assert atom.enforce_skipped == before + 1, "ما انعدّ التخطّي"
        print("OK — الإنفاذ وقع بالقفل الحرّ · وتُخطّي بالمشغول في %.4f ث" % elapsed)
    finally:
        await _shutdown()
        for suffix in ("", "-wal", "-shm"):
            if os.path.exists(db + suffix):
                os.unlink(db + suffix)


async def test_handler_never_waits_on_a_full_buffer():
    """امتلاءُ الدفعة يُجدوِل الكتابة ولا يحجب المعالج.

    مقيس حيًّا ٢٠٢٦-٠٩-٢٢ بعد إصلاح مسار الإدراج: انتظارُ القفل نزل إلى
    **٠٫٠٩٥ م.ث**، لكنّ **الدفعة** وسطُها **٤٬٢٥٠٫٩ م.ث** وأسوأها
    **١٦٧٬١٢٠٫٩** — فبلغ المعالج **٢٥٬٥٣٤ م.ث** مقابل ميزانية ٥٠.
    وليست sqlite (٢٩٫٨ م.ث وسطًا) بل انتظارُ قفل الملفّ المشترك.
    """
    print("\n--- test_handler_never_waits_on_a_full_buffer ---")
    db = _tmp_db()
    try:
        bus = FakeEventBus()
        atom = await _make(bus, db)
        bus.atom = None          # الناقل الوهميّ يدفع بعد كلّ نشر — يُعطَّل هنا

        slow = threading.Event()
        real_many = atom._insert_many

        def slow_many(rows):
            slow.wait(timeout=10)          # دفعةٌ بطيئة كالتي قِيست حيًّا
            return real_many(rows)
        atom._insert_many = slow_many

        # يُملأ البفر حتّى عتبة الدفع تمامًا
        handler = bus._handlers[EVENT_APPROVED][0]
        for i in range(_mod._BUFFER_MAX_ROWS - 1):
            await handler({"request_id": "B%d" % i, "account_id": "A1",
                           "symbol": "EURUSD"})
        assert len(atom._buffer) == _mod._BUFFER_MAX_ROWS - 1

        started = time.perf_counter()
        await handler({"request_id": "BLAST", "account_id": "A1",
                       "symbol": "EURUSD"})      # ← الصفّ الذي يبلغ السقف
        elapsed = time.perf_counter() - started
        slow.set()

        assert elapsed < 0.050, (
            "المعالج انتظر الدفعة %.3f ث والميزانية ٠٫٠٥٠" % elapsed)
        assert atom._urgent_flush is not None, "ما جُدولت الدفعة"
        print("OK — المعالج رجع بـ%.4f ث والدفعة جُدولت" % elapsed)
    finally:
        await _shutdown()
        for suffix in ("", "-wal", "-shm"):
            if os.path.exists(db + suffix):
                os.unlink(db + suffix)


async def test_handler_never_waits_on_a_busy_lock():
    """قفلٌ بيد جارٍ لا يحجب المعالج — يُودَع الصفّ ويُكتب بالدفعة.

    مقيس حيًّا ٢٠٢٦-٠٩-١٩ من تشريح ٧٠٧: عملُ sqlite ٠٫٥٤٧ م.ث والانتظارُ على
    القفل ٤٦١٫٨٣٣ وأسوأه **١١٬٤٧١٫٨** — ٢٢٩ ضعف ميزانية المعالج. والسبب أنّ
    قفل الملفّ (٢٠٢٦-٠٩-١٨) صار يعبر الذرّات، فصار ٧٠٧ ينتظر ٧١٤/٧١٦ وهي
    تكنس القاعدة، فصرخت النواة `handler timeout subscriber=707` ثماني مرّات.
    """
    print("\n--- test_handler_never_waits_on_a_busy_lock ---")
    db = _tmp_db()
    try:
        bus = FakeEventBus()
        atom = await _make(bus, db)
        held = threading.Event()
        release = threading.Event()

        def neighbour():
            """جارٌ يمسك قفل الملفّ نفسه — كما تفعل ٧١٦ وهي تكنس."""
            with atom._conn_lock:
                held.set()
                release.wait(timeout=10)

        worker = threading.Thread(target=neighbour, daemon=True)
        worker.start()
        assert held.wait(timeout=5), "الجار ما أمسك القفل"
        try:
            before = atom.deferred_by_lock
            # ⚠️ **يُنادى المعالج مباشرةً لا عبر `bus.publish`.** الناقل الوهميّ
            # يدفع الدفعة بعد كلّ نشر (راحةً للاختبارات)، فقياسُ `publish`
            # يقيسه هو لا المعالج — وأوّل صياغةٍ لهذا الاختبار وقعت فيها
            # فأعطت ١٠٫٠٠٥ ث. والنواة تقيس المعالجَ وحده، فهذا ما يُقاس.
            handler = bus._handlers[EVENT_ORDER_BUILT][0]
            started = time.perf_counter()
            await handler({"request_id": "LB1", "account_id": "A1",
                           "symbol": "EURUSD"})
            elapsed = time.perf_counter() - started
        finally:
            release.set()
            worker.join(timeout=5)

        assert elapsed < 0.050, (
            "المعالج انتظر %.3f ث والميزانية ٠٫٠٥٠" % elapsed)
        assert atom.deferred_by_lock == before + 1, "ما انعدّ التأجيل"
        assert len(atom._buffer) == 1, "الصفّ ما انحطّ بالدفعة"
        # والدفعة تكتبه فعلًا بعد ما يُفكّ القفل — لا فقد
        await atom._flush_buffer()
        rows = _query(db, "SELECT COUNT(*) FROM decisions WHERE request_id='LB1'")
        assert rows[0][0] == 1, "الصفّ المؤجَّل ما انكتب"
        print("OK — المعالج رجع بـ%.4f ث · أُجِّل ١ · وانكتب بالدفعة" % elapsed)
    finally:
        await _shutdown()
        for suffix in ("", "-wal", "-shm"):
            if os.path.exists(db + suffix):
                os.unlink(db + suffix)


async def test_enforcement_and_insert_never_write_together():
    """كاتبٌ واحد من الذرّة في أيّ لحظة — وإلّا اصطدما على قفل sqlite."""
    print("\n--- test_enforcement_and_insert_never_write_together ---")
    db = _tmp_db()
    try:
        bus = FakeEventBus()
        atom = await _make(bus, db)
        held = {"during_enforce": False, "overlap": False}
        real_enforce = _mod.enforce_limits

        def slow_enforce(*a, **kw):
            held["during_enforce"] = True
            # ⚠️ **يُطلَب القفل من خيطٍ آخر — لا من هذا.** صار القفل معاوِدًا
            # (`RLock`) لأنّ `enforce_limits` تأخذ قفل الملفّ وقد أخذته الذرّة
            # قبلها؛ وبلا المعاودة يقفل الخيطُ نفسَه. والمعاودة تعني أنّ سؤال
            # «أأستطيع أخذه؟» من الخيط المالك يُجاب دائمًا بنعم — فلا يقيس
            # شيئًا. والكاتب المنافس خيطٌ آخر أصلًا (`asyncio.to_thread`)،
            # فمن هناك يُسأل السؤال.
            import threading as _th
            probe = {"got": False}

            def _try():
                if atom._conn_lock.acquire(blocking=False):
                    atom._conn_lock.release()
                    probe["got"] = True

            other = _th.Thread(target=_try)
            other.start()
            other.join(timeout=5)
            held["overlap"] = probe["got"]
            held["during_enforce"] = False
            return real_enforce(*a, **kw)

        _mod.enforce_limits = slow_enforce
        try:
            await atom._enforce_limits()
        finally:
            _mod.enforce_limits = real_enforce
        assert not held["overlap"], "الإنفاذ يعمل والقفل حرّ — الإدراج قد يصطدم"
        print("OK — الإنفاذ يحتجز قفل الإدراج طوال عمله")
    finally:
        await _shutdown()
        for suffix in ("", "-wal", "-shm"):
            if os.path.exists(db + suffix):
                os.unlink(db + suffix)


async def test_locked_database_retries_and_keeps_the_store_ready():
    """قفلٌ عابر لا يُسقط قرارًا ولا يهدم المخزن.

    مقيس حيًّا ٢٠٢٦-٠٩-١٠: أربعة إخفاقات `database is locked` في ثلاث عشرة
    ساعة والعدّاد من ٣٦ إلى ٤٢ — قرارات ضاعت لأنّ كاتبًا آخر أمسك القاعدة.
    """
    print("\n--- test_locked_database_retries_and_keeps_the_store_ready ---")
    db = _tmp_db()
    try:
        bus = FakeEventBus()
        atom = await _make(bus, db)
        await bus.publish(EVENT_APPROVED, {"request_id": "L0", "account_id": "A1"})
        kept = atom._conn

        class _LockedOnce:
            """اتصال حقيقيّ يرفع قفلًا عابرًا مرّة واحدة ثم يعمل."""

            def __init__(self, real):
                self._real = real
                self.calls = 0

            def execute(self, sql, *args):
                self.calls += 1
                if self.calls == 1:
                    raise sqlite3.OperationalError("database is locked")
                return self._real.execute(sql, *args)

            # مسار الدفعة (`4.13.0`) يكتب بـ`executemany`، وهو مسار الطوفان —
            # أي أنّ القفل العابر يقع عليه لا على `execute`. القفل نفسه يجب أن
            # يُعاد عليه، فيمرّ الاثنان من العدّاد نفسه.
            def executemany(self, sql, params):
                self.calls += 1
                if self.calls == 1:
                    raise sqlite3.OperationalError("database is locked")
                return self._real.executemany(sql, params)

            def commit(self):
                return self._real.commit()

            def close(self):
                return self._real.close()

        proxy = _LockedOnce(kept)
        atom._conn = proxy
        await bus.publish(EVENT_APPROVED, {"request_id": "L1", "account_id": "A1"})
        ids = [r[0] for r in _query(db, "SELECT request_id FROM decisions ORDER BY id")]
        assert ids == ["L0", "L1"], ids
        assert atom.failure_count == 0, atom.failure_count
        assert atom._store_ready is True, "هُدم المخزن بسبب قفل عابر"
        assert atom._conn is proxy, "طُرح الاتصال بسبب قفل — وهو سليم"
        assert proxy.calls == 2, proxy.calls
        atom._conn = kept
        print(f"OK — قفلٌ واحد ثم نجاح: الصفوف {ids} · صفر إخفاق · المخزن سليم")
    finally:
        await _shutdown()
        for suffix in ("", "-wal", "-shm"):
            if os.path.exists(db + suffix):
                os.unlink(db + suffix)


async def test_lock_beyond_retry_requeues_and_clears_message():
    """٢٠٢٦-١٠-٠٥ (ختم المالك «إصلاحها NQ»): قفلٌ يتجاوز المهلة والإعادة.

    كان الصفّ يُعدّ إخفاقًا ويضيع، و«database is locked» يبقى نصَّ الصحّة حتّى
    إعادة التحميل وإن عادت الكتابة. الآن: الصفّ يعود إلى الطابور (مسار الدفعة
    والمسار الفوريّ معًا)، ويُكتب حين ينفكّ القفل، والنصّ يزول بأوّل كتابةٍ تنجح.
    """
    print("\n--- test_lock_beyond_retry_requeues_and_clears_message ---")
    db = _tmp_db()
    sqlite_mod = _mod.decision_store_sqlite
    real_sleep = sqlite_mod._LOCK_RETRY_SLEEP_S
    sqlite_mod._LOCK_RETRY_SLEEP_S = 0.01
    try:
        bus = FakeEventBus()
        atom = await _make(bus, db)
        await bus.publish(EVENT_APPROVED, {"request_id": "K0", "account_id": "A1"})
        kept = atom._conn

        class _Locked:
            """اتصال حقيقيّ مقفول ما دام `locked` — كلّ محاولةٍ ترفع القفل."""

            def __init__(self, real):
                self._real = real
                self.locked = True

            def execute(self, sql, *args):
                if self.locked:
                    raise sqlite3.OperationalError("database is locked")
                return self._real.execute(sql, *args)

            def executemany(self, sql, params):
                if self.locked:
                    raise sqlite3.OperationalError("database is locked")
                return self._real.executemany(sql, params)

            def commit(self):
                return self._real.commit()

            def close(self):
                return self._real.close()

        proxy = _Locked(kept)
        atom._conn = proxy
        # مسار الدفعة (طوفان) ومسار الإدراج الفوريّ (تذكرة) — كلاهما تحت القفل.
        await bus.publish(EVENT_APPROVED, {"request_id": "K1", "account_id": "A1"})
        await bus.publish(EVENT_FINAL, {"request_id": "K2", "account_id": "A1"})
        await asyncio.sleep(0.05)
        assert atom.failure_count == 0, "صفٌّ عُدّ إخفاقًا بسبب قفل: %d" % atom.failure_count
        assert atom.lock_requeued >= 2, atom.lock_requeued
        pending = {row["request_id"] for _, row in atom._buffer}
        assert {"K1", "K2"} <= pending, pending
        health = await atom.health_check()
        assert "locked" in health.message, health.message
        assert atom._store_ready is True, "هُدم المخزن بسبب قفل"
        # انفكّ القفل: الدفعة التالية تكتب ما انتظر، والنصّ يزول.
        proxy.locked = False
        await bus.publish(EVENT_APPROVED, {"request_id": "K3", "account_id": "A1"})
        await asyncio.sleep(0.05)
        ids = sorted(r[0] for r in _query(db, "SELECT request_id FROM decisions"))
        assert ids == ["K0", "K1", "K2", "K3"], ids
        assert atom._last_error == "", atom._last_error
        health = await atom.health_check()
        assert "locked" not in health.message, health.message
        atom._conn = kept
        print(f"OK — قفلٌ ممتدّ: {atom.lock_requeued} صفًّا عادت للطابور، صفر ضائع، والنصّ زال")
    finally:
        sqlite_mod._LOCK_RETRY_SLEEP_S = real_sleep
        await _shutdown()
        for suffix in ("", "-wal", "-shm"):
            if os.path.exists(db + suffix):
                os.unlink(db + suffix)


async def test_row_cap_still_bites_immediately():
    """العقد الذي كسرتُه ثمّ أعدتُه — الحارس كي لا يُكسر ثالثة.

    `tests/test_store_extended_contract.py` يطلب أن يقصّ سقف الصفوف **فورًا**.
    نقلُ الفحص إلى حلقة دوريّة (v4.3.0) كسره بصمت: اختبارات الذرّة كانت خضراء
    لأنّ عقد المشروع يعيش في ملف آخر خارجها. مكرَّر هنا عمدًا.
    """
    print("\n--- test_row_cap_still_bites_immediately ---")
    db = _tmp_db()
    try:
        bus = FakeEventBus()
        atom = Atom()
        await atom.initialize(bus.make_context(
            {"db_path": db, "keep_full_payload": True,
             "max_rows": 2, "max_db_bytes": 10_000_000}))
        await atom.start()
        _LIVE.append(atom)
        for i in range(4):
            await bus.publish(EVENT_APPROVED, {"request_id": str(i), "timestamp": i})
        n = _query(db, "SELECT COUNT(*) FROM decisions")[0][0]
        assert n == 2, "سقف الصفوف ما عضّ فورًا: %d" % n
        assert atom._limit_state.get("breached"), atom._limit_state
        print(f"OK — أربعة إدراجات بسقف اثنين ⇒ الباقي {n} و breached=True فورًا")
    finally:
        await _shutdown()
        for suffix in ("", "-wal", "-shm"):
            if os.path.exists(db + suffix):
                os.unlink(db + suffix)


async def test_limit_check_is_periodic_not_per_insert():
    print("\n--- test_limit_check_is_periodic_not_per_insert ---")
    db = _tmp_db()
    real_enforce = _mod.enforce_limits
    real_interval = _mod._LIMIT_INTERVAL_S
    calls = {"n": 0}

    def counting(*a, **kw):
        calls["n"] += 1
        return real_enforce(*a, **kw)

    _mod.enforce_limits = counting
    _mod._LIMIT_INTERVAL_S = 30.0  # الحلقة نائمة: ما يُقاس هنا هو مسار الإدراج وحده
    try:
        bus = FakeEventBus()
        atom = await _make(bus, db)
        for i in range(25):
            await bus.publish(EVENT_APPROVED, {
                "request_id": "r%d" % i, "account_id": "A1", "symbol": "EURUSD",
                "approved": True, "timestamp": float(i)})
        assert atom.stored_count == 25, atom.stored_count
        assert calls["n"] == 0, f"فحص السقف جرى {calls['n']} مرّة في مسار الإدراج"
        assert atom._inserts_since_limit == 25, atom._inserts_since_limit
        # الآن الحلقة وحدها: تُعاد بفاصل قصير والعدّاد لم يُمسّ
        await atom.stop()
        _mod._LIMIT_INTERVAL_S = 0.05
        await atom.start()
        await asyncio.sleep(0.2)
        assert calls["n"] >= 1, "الحلقة الدوريّة ما فحصت السقف"
        assert atom._inserts_since_limit == 0, atom._inserts_since_limit
        idle = calls["n"]
        await asyncio.sleep(0.2)
        assert calls["n"] == idle, "فحصت بلا إدراج جديد — عمل بلا سبب"
        await atom.stop()
        print(f"OK — ٢٥ إدراجًا بصفر فحص في المسار الساخن، ثم فحص دوريّ"
              f" ({idle}) ولا فحص بلا إدراج")
    finally:
        await _shutdown()
        _mod.enforce_limits = real_enforce
        _mod._LIMIT_INTERVAL_S = real_interval
        await asyncio.sleep(0.05)  # مهلة لخيط to_thread أن يُنهي ويُغلق
        for suffix in ("-wal", "-shm", ""):
            target = db + suffix
            if os.path.exists(target):
                try:
                    os.unlink(target)
                except OSError:
                    pass


async def main():
    tests = [test_overflow_drops_the_flood_not_the_approved,
             test_enforcement_skips_a_busy_lock_and_never_blocks_the_handler,
             test_handler_never_waits_on_a_full_buffer,
             test_handler_never_waits_on_a_busy_lock,
             test_flood_is_buffered_while_execution_tickets_are_written_at_once,
             test_the_gate_verdict_decides_what_waits_not_the_stage_name,
             test_buffered_rows_are_not_lost_when_the_atom_stops,
             test_stores_decision_with_identity, test_metadata_fallback,
             test_multi_stage_by_request, test_health_states,
             test_stores_decision_link_columns, test_link_columns_absent_stay_null,
             test_migrates_existing_database_without_link_columns,
             test_limit_check_is_periodic_not_per_insert,
             test_connection_is_reused_and_released_on_failure,
             test_rejection_reason_is_stored_beside_layer_reason,
             test_future_stamp_is_recorded_and_spoken_not_corrected,
             test_skew_is_read_from_the_new_contract_fields,
             test_failed_store_is_spoken_not_counted_in_silence,
             test_approved_decision_survives_the_cap,
             test_ceiling_never_evicts_execution_tickets,
             test_row_cap_still_bites_immediately,
             test_locked_database_retries_and_keeps_the_store_ready,
             test_lock_beyond_retry_requeues_and_clears_message,
             test_enforcement_and_insert_never_write_together,
             test_backfills_rejection_reason_for_old_rows,
             test_cap_moves_rows_to_archive_instead_of_destroying_them,
             test_archive_failure_blocks_destruction]
    failed = []
    for t in tests:
        try:
            await t()
        except AssertionError as e:
            failed.append((t.__name__, str(e))); print(f"FAILED: {t.__name__}: {e}")
        except Exception as e:
            failed.append((t.__name__, repr(e))); print(f"ERROR: {t.__name__}: {e!r}")
    print("\n" + "=" * 60)
    if failed:
        print(f"فشل {len(failed)} من أصل {len(tests)}"); sys.exit(1)
    print(f"نجح كل الاختبارات ({len(tests)}/{len(tests)})")


if __name__ == "__main__":
    asyncio.run(main())


async def test_no_subscription_to_archived_target_state():
    """٢٠٢٦-١٠-٠٧ (ختم «NQ»): ناشر perpetual.target.state (٥٨١) أُرشف — فلا اشتراك فيه.

    والمرحلة نفسها (`TARGET_STATE`) تبقى مسموحة: صفوفها القديمة في القاعدة الحيّة
    يحكمها السقف والدفعة كما كانت.
    """
    db = _tmp_db()
    try:
        bus = FakeEventBus()
        atom = await _make(bus, db)
        assert "perpetual.target.state" not in bus._handlers
        for kept in (EVENT_APPROVED, "decision.dispatch.state", "execution.order.requested",
                     "execution.command.ack", "platform.trade_event"):
            assert kept in bus._handlers, kept
        assert _mod.STAGE_TARGET in _mod._ALLOWED_STAGES
    finally:
        await _shutdown()
        for suffix in ("", "-wal", "-shm"):
            if os.path.exists(db + suffix):
                os.unlink(db + suffix)
