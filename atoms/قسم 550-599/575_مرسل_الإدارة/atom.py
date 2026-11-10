from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import uuid
from typing import Any

from core.contracts.atom import AtomBase, AtomContext, HealthState, HealthStatus

ATOM_VERSION = "2.12.0"
# v2.3.0 (2026-08-25): a management command that races the first clock
# pulse is HELD, not lost. Measured at boot: 577's replayed MAINTAIN_STOP
# arrived before the first SYS_SECOND, failed OFFICIAL_TIME_UNAVAILABLE
# and was gone forever -- a protective stop dropped by boot ordering.
# The hold is bounded and flushed on the first pulse.
_PENDING_MAX = 64

EVENT_PULSE = "SYS_SECOND"
EVENT_COMMAND = "execution.manage.command"
EVENT_WRITTEN = "execution.manage.written"
EVENT_FAILED = "execution.command.failed"
EVENT_GATE_COMMAND = "execution.gate.command"
# Same halt contract 552 already honours, word for word: emergency.halt carries
# either an account_id (that account only) or scope=SYSTEM (everything). A halt
# naming neither is counted, never widened into a system halt by assumption.
EVENT_HALT = "emergency.halt"
EVENT_RESET = "risk.kill_switch.reset_requested"
REASON_HALT = "OWNER_HALT"
GATE_ID = "575"

ACTION_MODIFY = "MODIFY_SL"
ACTION_PARTIAL = "CLOSE_PARTIAL"
ACTION_CLOSE = "CLOSE"

_ACTIONS = (ACTION_MODIFY, ACTION_PARTIAL, ACTION_CLOSE)

_BUSY_TIMEOUT_MS = 3000
_CONNECT_TIMEOUT_S = 5.0
PROJECT_BUILD_ID = "QUANT_NQ_FULL_212"

_SCHEMA = (
    "CREATE TABLE IF NOT EXISTS commands ("
    "id INTEGER PRIMARY KEY AUTOINCREMENT, request_id TEXT NOT NULL,"
    "action TEXT NOT NULL, symbol TEXT NOT NULL, side TEXT, volume REAL,"
    "price REAL, stop_loss REAL, take_profit REAL, ticket INTEGER,"
    "trail_dist REAL, trail_step REAL, params_json TEXT, magic INTEGER NOT NULL DEFAULT 0,"
    "account_id TEXT NOT NULL DEFAULT '', project_build_id TEXT,"
    "status TEXT NOT NULL DEFAULT 'PENDING', result TEXT,"
    "created_at REAL NOT NULL, taken_at REAL, done_at REAL)")
_INDEX = "CREATE INDEX IF NOT EXISTS idx_cmd_status ON commands(status, id)"
_INSERT_SQL = (
    "INSERT INTO commands (request_id, action, symbol, side, volume,"
    " ticket, stop_loss, take_profit, params_json, magic, account_id, project_build_id, status, created_at)"
    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING', ?)")

REASON_NOT_STARTED = "NOT_STARTED"
REASON_DISABLED = "DISABLED"

# ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): حارس مسافة الوقف — توأمُ 601 (`601/atom.py`
# `MAX_SL_FRAC = 0.05` و`STOP_LOSS_TOO_FAR`/`STOP_LOSS_NO_ANCHOR`). حادثة 09-05 التي بُني لها
# حارس 601 (وقف 39,677 على دخول 79,677) جاءت من **أمر إدارة**، وأوامر `MODIFY_SL` من 570/577/579
# تمرّ من هنا لا من 601 — وكان هذا المسار يفحص أنّ الوقف موجبٌ فقط. المقيس في الجسر الحيّ (قراءة
# فقط): 34 أمر `MODIFY_SL` أبعد من 5٪ عن دخول مركزه، كلّها بتكوين 09-05/09-06، و31 منها نُفّذ.
# الحدّ نفسه والسبب نفسه. والمرساة من `positions_v2` في المعاملة نفسها التي تفحص الملكيّة: سعرُ
# الدخول **أو** السعر الحاليّ — وقفٌ قريبٌ من أحدهما وقفٌ حقيقيّ (تعادلٌ قرب الدخول، أو تتبّعٌ قرب
# السعر)، وبعيدٌ عنهما معًا مركزٌ بلا حماية. و`CLOSE`/`CLOSE_PARTIAL` لا يُفحصان أبدًا.
MAX_SL_FRAC = 0.05
REASON_SL_TOO_FAR = "STOP_LOSS_TOO_FAR"
REASON_SL_NO_ANCHOR = "STOP_LOSS_NO_ANCHOR"


def _stop_distance_refusal(stop_loss: float | None, anchors: list) -> str:
    """"" = الوقف ضمن الحدّ من مرساةٍ واحدة على الأقلّ؛ وإلّا السبب المسمّى."""
    usable = [a for a in (_to_float(x) for x in anchors) if a is not None and a > 0]
    if not usable:
        return REASON_SL_NO_ANCHOR
    if stop_loss is None or stop_loss <= 0:
        return ""  # يُردّ قبل هذا باسمه (`INVALID_MANAGEMENT_PARAMETERS`)
    nearest = min(usable, key=lambda a: abs(a - stop_loss) / a)
    distance = abs(nearest - stop_loss) / nearest
    if distance > MAX_SL_FRAC:
        return "%s: sl=%s anchor=%s dist=%.1f%%" % (REASON_SL_TOO_FAR, stop_loss, nearest,
                                                    distance * 100.0)
    return ""


def _to_float(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result == result else None


def _to_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _resolve_db(configured: str) -> str:
    """المرسى أوّلًا، ثمّ المانيفست — **وكلاهما يُوسَّع من البيئة**.

    ٢٠٢٦-٠٩-٢٣: كان المانيفست يحمل مسار جهاز المالك مكتوبًا بيد
    (`C:\\Users\\NQ\\AppData\\Roaming\\…`)، فاسمُ صاحب الجهاز محفورٌ في
    عقد الذرّة — ونقلُ المشروع إلى مستخدمٍ آخر يُسقطها بلا رسالة.

    وصار مرسى `NQ_BRIDGE_DB` يُضبَط في `governance/app.py` لكلّ إقلاعٍ لا
    على الزرّ وحده، فحُرّر المانيفست إلى `%APPDATA%\\…` — وهو المصدرُ عينه
    الذي يبني منه المرسى قيمتَه. و`expandvars` هنا تجعل الاحتياطيّ يعمل
    ولو أُقلعت الذرّة من مشغّلٍ لا يمرّ بالمشرف.

    ⚠️ وما لا يُوسَّع يبقى كما هو (سلوك `expandvars`)، فمسارٌ مطلقٌ قديم
    في مانيفستٍ آخر لا يتأذّى.
    """
    override = os.environ.get("NQ_BRIDGE_DB", "").strip()
    return os.path.expandvars(override or configured)


def _connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, timeout=_CONNECT_TIMEOUT_S)
    conn.execute(f"PRAGMA busy_timeout={_BUSY_TIMEOUT_MS}")
    # 🔴 ٢٠٢٦-٠٩-١٩ — `journal_mode=WAL` **كتابةٌ** تأخذ قفلًا حصريًّا على
    # ترويسة الملفّ، و**لا تحترم `busy_timeout`**: ترتدّ في اللحظة نفسها
    # إن كان غيرك ممسكًا بالقاعدة. فكانت هنا في كلّ اتّصال، أي أنّ كلّ
    # محاولةِ كتابةٍ تسقط **قبل أن تبدأ** ولا تنتظر شيئًا — وإعادةُ
    # المحاولة فوقها تغطّي زمن التراجع وحده (0.8ث) لا 9.8ث كما تقول.
    #
    # قاسه صاحب ٦٠١ بقفلٍ حقيقيّ فسقطت إعادتُه في 0.60ث؛ وقياسي أنا كان
    # بدالّةٍ مزيّفة لا تمرّ بهذه الدالّة أصلًا، فقال «أخضر» وهو لا يلمس
    # المسار. والنمط صفةٌ محفوظة في ترويسة الملفّ لا تُضبط كلّ مرّة:
    # يُقرأ أوّلًا — قراءةٌ بلا قفل — ولا يُكتب إلّا إن اختلف.
    try:
        mode = conn.execute("PRAGMA journal_mode").fetchone()
    except sqlite3.Error:
        mode = None
    if not mode or str(mode[0]).lower() != "wal":
        conn.execute("PRAGMA journal_mode=WAL")
    # `synchronous` إعدادُ اتّصالٍ لا يمسّ الملفّ، فلا قفل له.
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


class Atom(AtomBase):
    def __init__(self) -> None:
        self._dropped = 0
        self._context: AtomContext | None = None
        self._running = False
        self._enabled = False
        self._db_path = "nq_brain.db"
        self._counter = 0
        # ٢٠٢٦-٠٩-١٦ — مقيس من سجلّ الصفقات: أحد عشر أمر `MODIFY_SL` متتالٍ
        # ردّه الوسيط قبل أن ينجح الثاني عشر، وزحفت لاحقة المعرّف من ٨ إلى
        # ١٩. السبب أنّ هذا العدّاد متطايِر (يبدأ من الصفر كل إقلاع) بينما
        # جدول `commands` الذي يفحص التكرار **دائم**: فتُولَّد لواحق سبق
        # استعمالها فترتدّ `DUPLICATE_REQUEST_ID` حتى يتجاوزها العدّاد زحفًا.
        # يُستأنف من `MAX(id)`: كل أمر مولَّد يُدرج صفًّا، فأيّ لاحقة سابقة
        # لا تتجاوز عدد الصفوف، والبدء فوقه يتخطّى الجميع.
        self._counter_resumed = False
        # ٢٠٢٦-٠٩-١٦: الأرضيّة المقروءة من المخزن تُعلَن في الشارة. وسببان:
        # أنّها تشخيصٌ حقيقيّ (كم أمرًا في الجدول الدائم)، وأنّها **الدليل
        # الوحيد على وصول هذا الإصلاح** — إصلاحٌ داخليّ بلا حقل جديد في
        # المخرَج لا يمكن التحقّق من نفاذه حيًّا. ورقم الإصدار وحده لا يكفي:
        # مقيس في جلسة مجاورة أنّ نشرًا ساخنًا التُقط مرّةً وتخلّف أخرى
        # عشرين دقيقة، والقرص يقول شيئًا والحيّ شيئًا آخر.
        self._counter_floor = 0
        self._seen = 0
        self._written = 0
        self._skipped = 0
        self._failed = 0
        self._last_error = ""
        # الإعادة على القفل: تُعدّ كي يُعرف هل هي شبكةُ أمانٍ نادرة أم
        # غطاءٌ على تزاحمٍ مزمن. عدّادٌ بلا إعلانٍ يخفي الثانية.
        self._retried = 0
        self._retry_exhausted = 0
        self._last_retry = ""
        self._official_time = 0.0
        self._pending_clock: list[dict[str, Any]] = []
        self._magic = 20260801
        self._global_halted = False
        self._halted_accounts: dict[str, str] = {}
        self._halt_blocked = 0
        self._halt_exit_allowed = 0
        self._halt_identity_blocked = 0
        # ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): حارس مسافة الوقف — ما ردّه، وما لم يُفحص لغياب الأعمدة.
        self._sl_blocked = 0
        self._sl_check_unavailable = 0

    async def initialize(self, context: AtomContext) -> None:
        self._context = context
        self._enabled = bool(context.config["enabled"])
        self._db_path = _resolve_db(str(context.config["db_path"]))
        self._magic = int(context.config.get("magic",20260801))
        context.subscribe(EVENT_COMMAND, self._on_command)
        context.subscribe(EVENT_PULSE, self._on_pulse)
        context.subscribe(EVENT_GATE_COMMAND, self._on_gate_command)
        context.subscribe(EVENT_HALT, self._on_halt)
        context.subscribe(EVENT_RESET, self._on_reset)

    async def _on_halt(self, payload: dict[str, Any]) -> None:
        if not self._running or not isinstance(payload, dict):
            return
        account = str(payload.get("account_id") or "").strip()
        if account:
            self._halted_accounts[account] = str(payload.get("reason") or "").strip() or "RISK_HALT"
        elif str(payload.get("scope") or "").upper() == "SYSTEM":
            self._global_halted = True
        else:
            self._halt_identity_blocked += 1

    async def _on_reset(self, payload: dict[str, Any]) -> None:
        if not self._running or not isinstance(payload, dict):
            return
        account = str(payload.get("account_id") or "").strip()
        if account:
            self._halted_accounts.pop(account, None)
        elif str(payload.get("scope") or "").upper() == "SYSTEM":
            self._global_halted = False
        else:
            self._halt_identity_blocked += 1

    def _halt_reason(self, account_id: str) -> str | None:
        if self._global_halted:
            return REASON_HALT
        if account_id in self._halted_accounts:
            return REASON_HALT
        return None

    async def _on_gate_command(self, payload: dict[str, Any]) -> None:
        if not self._running or not isinstance(payload, dict):
            self._dropped += 1
            return
        if str(payload.get("gate") or "") not in (GATE_ID, "both"):
            self._dropped += 1
            return
        wanted = payload.get("enabled")
        if isinstance(wanted, bool):
            self._enabled = wanted

    async def _on_pulse(self, payload: dict[str, Any]) -> None:
        if not isinstance(payload, dict):
            return
        official = payload.get("official_time")
        if isinstance(official, (int, float)) and not isinstance(official, bool):
            self._official_time = float(official)
            if self._pending_clock:
                held, self._pending_clock = self._pending_clock, []
                for command in held:
                    await self._on_command(command)

    async def start(self) -> None:
        self._running = True

    async def stop(self) -> None:
        self._running = False

    async def shutdown(self) -> None:
        await self.stop()

    def _highest_command_id(self) -> int:
        """أعلى مفتاح في الجدول الدائم، أو صفر إن تعذّر. التعذّر لا يُفشل
        أمرًا — يعيد السلوك إلى ما كان عليه قبل هذا الإصلاح لا أسوأ."""
        try:
            conn = _connect(self._db_path)
            try:
                row = conn.execute("SELECT MAX(id) FROM commands").fetchone()
            finally:
                conn.close()
        except Exception:
            return 0
        value = row[0] if row else None
        return int(value) if isinstance(value, int) else 0

    async def _resume_counter(self) -> None:
        if self._counter_resumed:
            return
        self._counter_resumed = True
        highest = await asyncio.to_thread(self._highest_command_id)
        if highest > self._counter:
            self._counter = highest
        self._counter_floor = highest

    def _insert(self, row: tuple) -> None:
        conn = _connect(self._db_path)
        try:
            conn.execute(_SCHEMA)
            columns = {str(r[1]) for r in conn.execute("PRAGMA table_info(commands)")}
            if "params_json" not in columns:
                conn.execute("ALTER TABLE commands ADD COLUMN params_json TEXT")
            if "magic" not in columns:
                conn.execute("ALTER TABLE commands ADD COLUMN magic INTEGER NOT NULL DEFAULT 0")
            if "account_id" not in columns:
                conn.execute("ALTER TABLE commands ADD COLUMN account_id TEXT NOT NULL DEFAULT ''")
            if "project_build_id" not in columns:
                conn.execute("ALTER TABLE commands ADD COLUMN project_build_id TEXT")
            conn.execute(_INDEX)
            conn.execute("BEGIN IMMEDIATE")
            if conn.execute("SELECT 1 FROM commands WHERE account_id=? AND request_id=?", (row[10], row[0])).fetchone():
                raise sqlite3.IntegrityError("DUPLICATE_REQUEST_ID")
            # ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): صفُّ الملكيّة نفسه يحمل مرساتَي الوقف.
            # جدولٌ بلا عمودَي السعر (شكلٌ أقدم من جدول الإكسبرت) لا يُفحص فيه — ويُعدّ ويُعلَن.
            positions = {str(r[1]) for r in conn.execute("PRAGMA table_info(positions_v2)")}
            prices = [c for c in ("entry_price", "current_price") if c in positions]
            target = conn.execute("SELECT 1%s FROM positions_v2 WHERE account_id=? AND ticket=? AND symbol=? AND magic=?"
                                  % "".join(", " + c for c in prices), (row[10], row[5], row[2],row[9])).fetchone()
            if target is None:
                raise sqlite3.IntegrityError("POSITION_OWNERSHIP_MISMATCH")
            if row[1] == ACTION_MODIFY:
                if not prices:
                    self._sl_check_unavailable += 1
                else:
                    refusal = _stop_distance_refusal(_to_float(row[6]), list(target[1:]))
                    if refusal:
                        self._sl_blocked += 1
                        raise sqlite3.IntegrityError(refusal)
            conn.execute(_INSERT_SQL, row)
            conn.commit()
        finally:
            conn.close()

    async def _insert_with_retry(self, row: tuple) -> None:
        """يكتب، ويعيد على القفل وحده — بمهلٍ متباعدة.

        `busy_timeout=3000` ينتظر قفلًا مقيمًا ولا ينفع في قفلٍ يُطلق
        ويُعاد في اللحظة نفسها؛ فالمحاولة الواحدة تسقط والأمر يموت.
        وثلاث محاولات بمهلٍ 0.2 ثمّ 0.6 ثانية تغطّي نافذةً تسع مرّات
        أطول من المقيس، وأقصى تأخيرٍ ممكن دون عشر ثوانٍ — وهو مقبولٌ
        على صفقةٍ مفتوحة، والبديل ضياعُ أمرها.
        """
        delays = (0.2, 0.6)
        for attempt in range(len(delays) + 1):
            try:
                await asyncio.to_thread(self._insert, row)
                if attempt:
                    self._retried += 1
                    self._last_retry = "%s نجح بعد %d إعادة" % (row[0], attempt)
                return
            except sqlite3.IntegrityError:
                raise
            except sqlite3.OperationalError as exc:
                if "locked" not in str(exc).lower() and "busy" not in str(exc).lower():
                    raise
                if attempt >= len(delays):
                    self._retry_exhausted += 1
                    raise
                await asyncio.sleep(delays[attempt])

    async def _on_command(self, payload: dict[str, Any]) -> None:
        if not self._running or self._context is None or not isinstance(payload, dict):
            return
        action = str(payload.get("action", ""))
        ticket = _to_int(payload.get("ticket"))
        if action not in _ACTIONS or ticket is None or ticket <= 0:
            return
        self._seen += 1
        if not self._enabled:
            self._skipped += 1
            await self._context.publish(EVENT_FAILED,{**payload,"reason":"MANAGEMENT_GATE_DISABLED"})
            return
        account_id = str(payload.get("account_id") or "").strip()
        if not account_id:
            self._failed += 1
            self._last_error = "MISSING_ACCOUNT_ID"
            return
        # v2.2.0 (2026-08-25): the halt no longer blocks EXITS. Every action
        # this atom sends (CLOSE / CLOSE_PARTIAL / MODIFY_SL) reduces or
        # protects exposure -- blocking them during an emergency halt was a
        # measured safety inversion: the owner halts the system and thereby
        # loses the ability to get OUT of the market. Exits during halt are
        # counted and declared, never refused.
        halted = self._halt_reason(account_id)
        if halted is not None:
            self._halt_exit_allowed += 1
        try:command_magic=int(payload.get("magic"))
        except (TypeError,ValueError):command_magic=0
        if command_magic!=self._magic:
            self._failed+=1;self._last_error="MISSING_OR_FOREIGN_MAGIC"
            await self._context.publish(EVENT_FAILED,{**payload,"reason":self._last_error});return
        symbol = str(payload.get("symbol", ""))
        side = str(payload.get("side", ""))
        volume = _to_float(payload.get("volume"))
        stop_loss = _to_float(payload.get("stop_loss"))
        if (action == ACTION_MODIFY and (stop_loss is None or stop_loss <= 0)) or (action == ACTION_PARTIAL and (volume is None or volume <= 0)):
            self._failed += 1; self._last_error = "INVALID_MANAGEMENT_PARAMETERS"
            await self._context.publish(EVENT_FAILED,{**payload,"reason":self._last_error}); return
        if self._official_time <= 0:
            # v2.3.0: يُحفظ حتى أول نبضة بدل أن يضيع — أمر حماية لا يُرمى
            # لعِلّة ترتيب الإقلاع. تجاوز السقف وحده يُعدّ فشلًا معلَنًا.
            if len(self._pending_clock) < _PENDING_MAX:
                self._pending_clock.append(dict(payload)); return
            self._failed += 1; self._last_error = "OFFICIAL_TIME_UNAVAILABLE"
            await self._context.publish(EVENT_FAILED,{**payload,"reason":self._last_error}); return
        await self._resume_counter()
        self._counter += 1
        # 🔴 ٢٠٢٦-٠٩-٢٢ — المسار الثاني: أمرٌ يصل بلا `request_id` فيُبنى
        # هنا. وكان بلاحقةٍ من عدّادٍ متطايِر تعود إلى الخلف مع كلّ إعادة
        # بناء، والجدول الذي يفحص التكرار **دائم** — فتُولَّد لواحق سبق
        # استعمالها ويردّها الوسيط `DUPLICATE_REQUEST_ID`.
        #
        # وهي العلّة نفسها التي أصلحتُها في ٥٧٠ بـ`uuid4`، **ونسيتُ نظيرها
        # هنا**: رأيتُها في الحيّ باسمها `mgmt-MODIFY_SL-1945478364-763`
        # بينما ٥٧٠ يُخرج `manage-…-<hex12>`. مسارٌ مُصلَحٌ وجارُه معطوب،
        # وهو نمطُ البوّابات التوأم بعينه. [[twin-gates-fix-one-forget-the-other]]
        #
        # و`_resume_counter` (استئنافٌ من `MAX(id)`) لا يكفي: يرفع الأرضيّة
        # مرّةً عند الإقلاع، ثمّ يزحف العدّاد فوق لواحقَ استُعملت في هذه
        # الحياة نفسها. والتفرّد البنيويّ لا يحتاج أرضيّةً ولا قاعدة.
        request_id = str(payload.get("request_id")
                         or "mgmt-%s-%d-%s" % (action, ticket, uuid.uuid4().hex[:12])).strip()
        metadata = {key: payload.get(key) for key in (
            "extraction_id", "target_amount", "origin", "bias", "score"
        ) if payload.get(key) is not None}
        params_json = json.dumps(metadata, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        # ٢٠٢٦-٠٩-١٧ — الهدف كان يُكتب `None` دائمًا، فينكسر عقد ٣:١ عند
        # أوّل تعديل وقف: ٥٧٧ يوسّع الوقف ليبلغ مئة المالك والهدف يبقى على
        # مسافته القديمة. مقيس على شاشة المالك (xauusd 1938572346):
        #     وقف 2.50 = 97.50$  ·  هدف 7.09 = 276.51$  ⇒ النسبة 2.84 لا 3
        # يُمرَّر الآن إن أرسله صاحب الأمر، ويبقى `None` إن لم يرسله — فلا
        # يتغيّر سلوك أيّ مُرسِل قائم.
        take_profit = _to_float(payload.get("take_profit"))
        if take_profit is not None and take_profit <= 0:
            take_profit = None
        row = (request_id, action, symbol, side, volume, ticket, stop_loss,
               take_profit, params_json, command_magic, account_id, PROJECT_BUILD_ID, self._official_time)
        # 🔴 ٢٠٢٦-٠٩-١٩ — قفلٌ عابرٌ كان يقتل أمر إدارةٍ إلى الأبد.
        #
        # مقيسٌ عند صاحب ٦٠١: الأمر `555-9b813eca1a82` عبر كلّ حارسٍ وصار
        # قرارًا نهائيًّا ثمّ سقط بـ`database is locked`، ولا صفّ له في
        # `commands` بحالةٍ ولا بأخرى — لأنّ الكاتب لا يعيد. وذرّتي تكتب
        # في القاعدة نفسها بالنمط نفسه.
        #
        # والفرق أنّ ضياع أمر ٦٠١ فرصةٌ فائتة، وضياع أمري **صفقةٌ مفتوحة
        # بلا حمايتها**: نقلُ الوقف إلى التعادل، وإغلاق الجزء عند الهدف
        # الأوّل — خطّة المالك كلّها تمرّ من هنا. فسقوطُ سطرٍ واحدٍ صامتًا
        # يترك الصفقة على وقفها الأوّل ولا يعلم به أحد.
        #
        # والإعادة على القفل وحده: `DUPLICATE_REQUEST_ID` و
        # `POSITION_OWNERSHIP_MISMATCH` حارسان يجب أن يبقيا قاطعين، وإعادةُ
        # المحاولة عليهما تكرارُ أمرٍ على مالٍ حيّ.
        try:
            await self._insert_with_retry(row)
            self._written += 1
            self._last_error = ""
            await self._context.publish(EVENT_WRITTEN, {
                "request_id": request_id, "account_id": account_id,
                "action": action, "ticket": ticket, "symbol": symbol, **metadata})
        except sqlite3.Error as exc:
            self._failed += 1
            self._last_error = str(exc)
            self._context.logger.error("575 manage write failed: %s", exc)
            await self._context.publish(EVENT_FAILED,{**payload,"request_id":request_id,"reason":str(exc)})

    async def health_check(self) -> HealthStatus:
        if not self._running:
            return HealthStatus(state=HealthState.UNHEALTHY, message=REASON_NOT_STARTED)
        details = {"enabled": self._enabled, "seen": self._seen, "written": self._written,
                   "skipped": self._skipped, "failed": self._failed,
                   "last_error": self._last_error,
                   "global_halted": self._global_halted,
                   "halted_accounts": dict(self._halted_accounts),
                   "halt_blocked": self._halt_blocked,
                   "halt_exit_allowed": self._halt_exit_allowed,
                   "halt_identity_blocked": self._halt_identity_blocked,
                   "sl_too_far_blocked": self._sl_blocked,
                   "sl_check_unavailable": self._sl_check_unavailable,
                   "max_sl_frac": MAX_SL_FRAC}
        if self._global_halted or self._halted_accounts:
            return HealthStatus(state=HealthState.DEGRADED, message=REASON_HALT,
                                details=details)
        if not self._enabled:
            return HealthStatus(state=HealthState.DEGRADED, message=REASON_DISABLED,
                                details=details)
        if self._failed > 0 and self._written == 0:
            return HealthStatus(state=HealthState.DEGRADED, message=self._last_error,
                                details=details)
        return HealthStatus(state=HealthState.HEALTHY,
                            # ٢٠٢٦-٠٩-١٦ (فحص شامل ٤٥٠–٥٩٩): `failed`
                            # و`halt_blocked` في `details` وحدها والنواة
                            # تحذفها — فأمرُ إدارةٍ يفشل أو يُحجب بإيقافٍ
                            # طارئ ولا يظهر إلّا `written=N`.
                            # ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): وحارس مسافة الوقف بعياره.
                            message="written=%d skipped=%d id_floor=%d%s%s%s%s%s%s | عيار: وقف≤%g%% من الدخول أو السعر" % (
                                self._written, self._skipped, self._counter_floor,
                                " ⚠ فشل=%d" % self._failed if self._failed else "",
                                " محجوب_بإيقاف=%d" % self._halt_blocked if self._halt_blocked else "",
                                " أُعيد_على_قفل=%d" % self._retried if self._retried else "",
                                " 🔴 ضاع_رغم_الإعادة=%d" % self._retry_exhausted
                                if self._retry_exhausted else "",
                                " وقف_بعيد_مردود=%d" % self._sl_blocked if self._sl_blocked else "",
                                " ⚠ وقف_بلا_فحص=%d" % self._sl_check_unavailable
                                if self._sl_check_unavailable else "",
                                MAX_SL_FRAC * 100.0),
                            details=details)
