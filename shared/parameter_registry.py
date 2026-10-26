"""سجلّ المُعامِلات — الأولوية ٠: لا رقم يحكم القرار بلا مصدر واعتماد.

المشكلة التي يحلّها:
    ستّة أرقام تحكم بوّابة `READY` اليوم وهي **اجتهاد المنفِّذ**، مكتوبة
    ثوابتَ في الكود. وسمُها «غير معتمدة» في ورقة لا يمنع أحدًا من البناء
    عليها بعد شهر — والورقة لا تُنفَّذ، الكود يُنفَّذ.

⇒ المُعامِل يصير صفًّا له `source` و`status`، والحاجز يقرأ الحالة آليًّا:

    status != APPROVED  ⇒  provisional  ⇒  لا يبلغ READY

⛔ هذا الملفّ **لا يعتمد رقمًا ولا يقترح قيمة**. يسجّل القيمة السارية
   في الكود اليوم مع `source=UNSET` و`status=UNAPPROVED` — أي يُعلن
   الجهل، لا يملؤه. الاعتماد قرار مالك يمرّ عبر `approve()` بتدقيق.
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
from pathlib import Path
from typing import Any

SOURCE_UNSET = "UNSET"
SOURCE_OWNER = "OWNER"
SOURCE_BACKTEST = "BACKTEST"
SOURCE_VENDOR = "VENDOR"
ALL_SOURCES = frozenset({SOURCE_UNSET, SOURCE_OWNER, SOURCE_BACKTEST, SOURCE_VENDOR})

STATUS_APPROVED = "APPROVED"
STATUS_UNAPPROVED = "UNAPPROVED"
ALL_STATUSES = frozenset({STATUS_APPROVED, STATUS_UNAPPROVED})

SCOPE_GLOBAL = "global"
REASON_UNAPPROVED = "UNAPPROVED_PARAMETER"

#: المُعامِلات الستّة التي تحكم بوّابة `READY` اليوم — بقيمها السارية في
#: الكود، ومصدرها `UNSET` وحالتها `UNAPPROVED` حتّى يعتمدها المالك.
DECLARED: dict[str, dict[str, Any]] = {
    "MOVEMENT_FLOOR": {
        "value": 1e-6, "scope": SCOPE_GLOBAL,
        "where": "live_analysis._MOVEMENT_FLOOR",
        "governs": "strength.abnormality"},
    "ABNORMALITY_GAIN": {
        "value": 50.0, "scope": SCOPE_GLOBAL,
        "where": "live_analysis._analyze",
        "governs": "strength.abnormality"},
    "INTEGRITY_BLEND": {
        "value": 3.0, "scope": SCOPE_GLOBAL,
        "where": "live_analysis._analyze (coherence+concentration+persistence)/3",
        "governs": "strength.integrity"},
    "CONFIDENCE_BLEND": {
        "value": 0.40, "scope": SCOPE_GLOBAL,
        "where": "live_analysis + section_live (0.40/0.30/0.30)",
        "governs": "confidence"},
    "DEPTH_BLEND": {
        "value": 0.35, "scope": SCOPE_GLOBAL,
        "where": "live_analysis + section_live (0.35/0.30/0.20/0.15)",
        "governs": "current_depth"},
    "STALE_AFTER_S": {
        "value": 5.0, "scope": SCOPE_GLOBAL,
        "where": "section_contract.STALE_AFTER_S · live_analysis · section_live",
        "governs": "state.freshness"},
}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS parameters (
    name           TEXT NOT NULL,
    scope          TEXT NOT NULL,
    value          REAL NOT NULL,
    source         TEXT NOT NULL,
    status         TEXT NOT NULL,
    version        INTEGER NOT NULL,
    effective_from REAL NOT NULL,
    approved_by    TEXT NOT NULL,
    approved_at    REAL NOT NULL,
    governs        TEXT NOT NULL,
    declared_at    TEXT NOT NULL,
    PRIMARY KEY(name, scope)
);
CREATE TABLE IF NOT EXISTS parameters_audit (
    audit_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL,
    scope      TEXT NOT NULL,
    old_json   TEXT NOT NULL,
    new_json   TEXT NOT NULL,
    version    INTEGER NOT NULL,
    changed_at REAL NOT NULL,
    changed_by TEXT NOT NULL,
    command_id TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_parameters_command
ON parameters_audit(command_id, name, scope);
"""


class ParameterRegistry:
    """مخزن المُعامِلات — نفس قاعدة المعايرة، جدول مستقلّ (§٥٢)."""

    _lock = threading.Lock()
    #: المسارات التي ضُمن مخطّطها في هذه العملية — الضمان يجري مرّة واحدة.
    #: (كان `_ensure_schema` يكتب `executescript` + 6 صفوف مع **كلّ** بناء
    #: نسخة، وذرّات القرار تبني نسخًا على المسار الساخن — كتابة قاعدة لكل
    #: دورة قرار. مقيس ٢٠٢٦-٠٨-٢٥.)
    _schema_ready: set[str] = set()

    def __init__(self, path: str | Path | None = None) -> None:
        # المسار الافتراضيّ لمالك جذور المسارات (shared/runtime_paths.py) — كان
        # يُشتقّ هنا من `Path(__file__).parent.parent` فيقع على `PROJECT_ROOT/var`
        # بينما اللوحة تحسب `<runtime>/var` (قِيس ٢٠٢٦-٠٩-٠٣). المتغيّر
        # البيئيّ والقيمة الصريحة كما هما — عقد `QUANT_ANALYSIS_SETTINGS_DB` لم يتغيّر.
        try:                                    # نسخة الـruntime تُقدَّم على العامة
            from shared.runtime_paths import settings_db_path
        except ModuleNotFoundError:
            import sys as _s
            _s.path.insert(0, str(Path(__file__).resolve().parent.parent))
            from shared.runtime_paths import settings_db_path
        code_root = Path(__file__).resolve().parent.parent
        if path is not None:
            candidate = Path(path)
            self.path = (candidate if candidate.is_absolute()
                         else settings_db_path(code_root=code_root).parent.parent.parent
                         / candidate)
        else:
            self.path = settings_db_path(
                code_root=code_root,
                market=str(os.environ.get("QUANT_GOV_MARKET", "")).strip().lower())
        self.path.parent.mkdir(parents=True, exist_ok=True)
        key = str(self.path)
        if key not in ParameterRegistry._schema_ready:
            self._ensure_schema()
            ParameterRegistry._schema_ready.add(key)

    #: اتّصال واحد لكلّ خيط. كائن sqlite3 يرفض الاستعمال من خيطٍ غير خيط
    #: إنشائه (`check_same_thread`)، والناقل يشغّل معالجات على بِركة خيوط.
    _conn_local = threading.local()

    def _connect(self) -> sqlite3.Connection:
        """اتّصال **مُعاد استعماله** لكلّ خيط — لا اتّصال جديد لكلّ استعلام.

        ⛔ **المقيس ٢٠٢٦-٠٩-١٠** على قاعدة العيارات الحيّة (٣٧ صفًّا):

            اتّصال جديد + استعلام : 578.3 µs
            اتّصال مُعاد استعماله  :   9.1 µs      ⟵ **63×**

        وكان `_connect` **ثاني أثقل إطار** في ملمح النواة الحيّة: 6.8% من
        معالج العملية (`py-spy`، 5,093 عيّنة/45ث).

        ⚠️ والـPRAGMA بريئة: القياس بلا PRAGMA أعطى 594.8 µs — لا فرق.
        الكلفة كلّها في `sqlite3.connect` نفسه (فتح ملفّ وقراءة ترويسة
        وبناء مفسّر). فلا تُحذف الـPRAGMA ظنًّا أنّها العلّة.

        وتبديل المسار **يغلق القديم فورًا**: مقبضٌ مفتوح على ملفّ مؤقّت
        يمنع تنظيفه على ويندوز، و28 ملفّ اختبار يبدّل هذه القاعدة.
        """
        local = ParameterRegistry._conn_local
        key = str(self.path)
        conn = getattr(local, "conn", None)
        if conn is not None:
            if getattr(local, "key", None) == key:
                return conn
            try:
                conn.close()
            except Exception:  # noqa: BLE001 — اتّصال ميت لا يمنع فتح غيره
                pass
            local.conn = None
        conn = sqlite3.connect(key, timeout=10.0)
        conn.row_factory = sqlite3.Row
        # `journal_mode=WAL` كتابةٌ لا تحترم `busy_timeout`، وكانت المهلة
        # تُضبط بعدها فتُنفَّذ بصفر — [[pragma-wal-ignores-busy-timeout]].
        conn.execute("PRAGMA busy_timeout=10000")
        try:
            mode = conn.execute("PRAGMA journal_mode").fetchone()
        except sqlite3.Error:
            mode = None
        if not mode or str(mode[0]).lower() != "wal":
            conn.execute("PRAGMA journal_mode=WAL")
        local.conn = conn
        local.key = key
        return conn

    @classmethod
    def close_connections(cls) -> None:
        """يغلق اتّصال هذا الخيط — للإطفاء النظيف وللاختبارات."""
        local = cls._conn_local
        conn = getattr(local, "conn", None)
        if conn is not None:
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass
        local.conn = None
        local.key = None

    def _ensure_schema(self) -> None:
        with self._lock, self._connect() as conn:
            conn.executescript(_SCHEMA)
            for name, spec in DECLARED.items():
                # ⛔ لا يُكتب إلّا الإعلان الأوّل: إعادة التشغيل لا تُرجع
                #    مُعامِلًا اعتمده المالك إلى `UNAPPROVED`.
                conn.execute(
                    """INSERT OR IGNORE INTO parameters(name,scope,value,source,
                       status,version,effective_from,approved_by,approved_at,
                       governs,declared_at)
                       VALUES(?,?,?,?,?,0,0.0,'','',?,?)""",
                    (name, spec["scope"], float(spec["value"]), SOURCE_UNSET,
                     STATUS_UNAPPROVED, spec["governs"], spec["where"]))
            conn.commit()

    def get(self, name: str, scope: str = SCOPE_GLOBAL) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM parameters WHERE name=? AND scope=?",
                (name, scope)).fetchone()
        return dict(row) if row is not None else None

    def all(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            return [dict(row) for row in conn.execute(
                "SELECT * FROM parameters ORDER BY name, scope")]

    def unapproved(self) -> list[str]:
        with self._connect() as conn:
            return [str(row["name"]) for row in conn.execute(
                "SELECT name FROM parameters WHERE status!=? ORDER BY name",
                (STATUS_APPROVED,))]

    def write_value(self, name: str, *, value: float, scope: str = SCOPE_GLOBAL,
                    changed_by: str = "", command_id: str = "",
                    at: float = 0.0) -> dict[str, Any]:
        """**حفظ قيمة مسودة دون اعتماد** (فصل «حفظ» عن «اعتماد» — بند ٥، ٢٠٢٦-٠٩-٠٣).

        تكتب القيمة والصفّ يبقى ``status=UNAPPROVED`` بـ``source=UNSET``، فلا
        يقرؤها أي محرّك: ``effective_value()`` و``approved_value()`` يشترطان
        ``STATUS_APPROVED``، والقيمة الجارية تبقى قيمة المانيفست. الاعتماد يظلّ
        قرارًا منفصلًا عبر ``approve()`` / ``/gov/command action=parameter_approve``
        (أو ``decision_setting`` بحقل ``confirm: true``).
        ⛔ لا ``source`` هنا: مصدر «المالك» حقّ الاعتماد لا الحقّ في الكتابة،
        وإلا تحوّل حفظ عابر إلى قرار حاكم.
        تُبذر الصفّ إن لم يكن مُعلَنًا (نفس عقد ``approve``).
        """
        try:
            number = float(value)
        except (TypeError, ValueError):
            raise ValueError("PARAMETER_VALUE_INVALID") from None
        if number != number:
            raise ValueError("PARAMETER_VALUE_INVALID")
        stamp = float(at or 0.0)
        with self._lock, self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT * FROM parameters WHERE name=? AND scope=?",
                (name, scope)).fetchone()
            if row is None:
                conn.rollback()
                raise ValueError("PARAMETER_NOT_DECLARED")
            old = dict(row)
            new = dict(old)
            new.update({"value": number, "status": STATUS_UNAPPROVED,
                        "version": int(old["version"]) + 1})
            conn.execute(
                """UPDATE parameters SET value=?,status=?,version=?
                   WHERE name=? AND scope=?""",
                (new["value"], new["status"], new["version"], name, scope))
            conn.execute(
                """INSERT INTO parameters_audit(name,scope,old_json,new_json,
                   version,changed_at,changed_by,command_id)
                   VALUES(?,?,?,?,?,?,?,?)""",
                (name, scope,
                 json.dumps(old, ensure_ascii=False, sort_keys=True),
                 json.dumps(new, ensure_ascii=False, sort_keys=True),
                 new["version"], stamp, str(changed_by or ""),
                 str(command_id or "")))
            conn.commit()
        refresh_gate()
        return new

    def approve(self, name: str, *, value: float, source: str, approved_by: str,
                command_id: str, approved_at: float,
                scope: str = SCOPE_GLOBAL) -> dict[str, Any]:
        """اعتماد مُعامِل — قرار مالك، لا اجتهاد كود.

        ⛔ `source=UNSET` مرفوض: رقمٌ بلا مصدر لا يُعتمد مهما كان صحيحًا.
        """
        if source not in ALL_SOURCES or source == SOURCE_UNSET:
            raise ValueError("PARAMETER_SOURCE_REQUIRED")
        if not approved_by or not command_id:
            raise ValueError("PARAMETER_APPROVAL_IDENTITY_REQUIRED")
        try:
            number = float(value)
        except (TypeError, ValueError):
            raise ValueError("PARAMETER_VALUE_INVALID") from None
        with self._lock, self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            duplicate = conn.execute(
                """SELECT new_json FROM parameters_audit
                   WHERE command_id=? AND name=? AND scope=?""",
                (command_id, name, scope)).fetchone()
            if duplicate is not None:
                conn.rollback()
                return json.loads(str(duplicate["new_json"]))
            row = conn.execute(
                "SELECT * FROM parameters WHERE name=? AND scope=?",
                (name, scope)).fetchone()
            if row is None:
                conn.rollback()
                raise ValueError("PARAMETER_NOT_DECLARED")
            old = dict(row)
            new = dict(old)
            new.update({"value": number, "source": source,
                        "status": STATUS_APPROVED,
                        "version": int(old["version"]) + 1,
                        "effective_from": approved_at,
                        "approved_by": approved_by, "approved_at": approved_at})
            conn.execute(
                """UPDATE parameters SET value=?,source=?,status=?,version=?,
                   effective_from=?,approved_by=?,approved_at=?
                   WHERE name=? AND scope=?""",
                (new["value"], new["source"], new["status"], new["version"],
                 new["effective_from"], new["approved_by"], new["approved_at"],
                 name, scope))
            conn.execute(
                """INSERT INTO parameters_audit(name,scope,old_json,new_json,
                   version,changed_at,changed_by,command_id)
                   VALUES(?,?,?,?,?,?,?,?)""",
                (name, scope,
                 json.dumps(old, ensure_ascii=False, sort_keys=True),
                 json.dumps(new, ensure_ascii=False, sort_keys=True),
                 new["version"], approved_at, approved_by, command_id))
            conn.commit()
        refresh_gate()
        return new


# ── الحاجز الميكانيكيّ ───────────────────────────────────────────────────
_gate_lock = threading.Lock()
_gate_cache: list[str] | None = None
#: بصمة الحداثة التي بُنيت عليها الذاكرة: (mtime القاعدة، لحظة آخر فحص).
#: ⛔ الذاكرة التي تُبذر مرّةً وتعيش عمر العملية كانت جذر «ما بتتحمل إلا
#:    على البارد» (مقيس ٢٠٢٦-٠٨-٢٥): اعتماد يُكتب من عمليّة الحوكمة لا
#:    يصل عمليّة النواة أبدًا. الآن تُفحص بصمة الملفّ كل `_GATE_RECHECK_S`
#:    على الأكثر — فتصل الاعتمادات عبر العمليّات خلال ثوانٍ بلا إقلاع بارد.
_gate_mtime: float = -1.0
_gate_path: str | None = None
_gate_checked_monotonic: float = -1.0
_GATE_RECHECK_S = 2.0


#: متغيّرات البيئة التي تحدّد مسار السجلّ وحدها (`settings_db_path`).
#: أيّ تبدّل في واحدة منها يعيد البناء — قراءتها رخيصة، وحساب المسار غالٍ.
_REGISTRY_PATH_ENV = (
    "QUANT_GOV_MARKET",
    "QUANT_ANALYSIS_SETTINGS_DB",
    "QUANT_RUNTIME_ROOT",
)

#: سجلّ العيارات مبنيًّا مرّة واحدة: (بصمة البيئة، الكائن).
_registry_cache: tuple[tuple[str, ...], "ParameterRegistry"] | None = None


def _pick_env_reader(environ=None):  # noqa: ANN001
    """قارئ متغيّرات البيئة — يتجاوز غلاف `os._Environ` **إن ثبت تطابقه**.

    ⛔ العطب، مقيسًا بـ`py-spy` على النواة الحيّة ٢٠٢٦-٠٩-١٠:
    `parameter_registry` = **10.1% من معالج العملية كلّه**، و`_refresh_dials`
    وحدها 5.87%. والسبب المسمّى بالتفكيك:

        os.environ.get(name)   1.083 µs
        dict.get(name)         0.093 µs      ⟵ أبطأ 11.6×

    لأنّ كلّ نداء يمرّ بـ`encodekey` ثمّ يرفع `KeyError` ويلتقطه. وبصمة
    البيئة تُقرأ في **كلّ** قراءة عيار، فصار الغلاف وحده ~3.85 µs = 62% من
    زمن `approved_value` كلّه.

    ولماذا هكذا لا بتخزينٍ زمنيّ: تأجيل الفحص ثانيتين كان يخفي تبديل قاعدة
    البيانات (م-27)، و28 ملفّ اختبار يبدّل هذه المتغيّرات ولا يستدعي كلّها
    `refresh_gate`. فالقراءة تبقى **لحظية بلا تأخير**، ويُحذف الغلاف وحده.

    و`os.environ._data` تفصيل تنفيذ في CPython، فلا يُوثق به بالظنّ: يُفحص
    عند الاستيراد بمتغيّر موجود يقينًا (`PATH`) — وعلى لينكس مفاتيحه bytes
    فيفشل الفحص ونرجع إلى `os.environ.get` كما كان.
    """
    env = os.environ if environ is None else environ
    data = getattr(env, "_data", None)
    if not isinstance(data, dict):
        return env.get
    for probe in ("PATH", "PATHEXT", "SYSTEMROOT"):
        actual = env.get(probe)
        if actual is None:
            continue
        return data.get if data.get(probe) == actual else env.get
    return env.get


#: يُحسم مرّة عند الاستيراد — لا فحص في المسار الساخن.
_env_get = _pick_env_reader()

#: هل نُقرأ من القاموس مباشرة؟ يُعرض في التشخيص، فلا يبقى الاختيار صامتًا.
env_reader_is_direct = _env_get is not os.environ.get


def _registry_env_stamp() -> tuple[str, ...]:
    get = _env_get
    return tuple(str(get(name) or "").strip() for name in _REGISTRY_PATH_ENV)


def _registry() -> "ParameterRegistry":
    """سجلّ العيارات مبنيًّا مرّة لا مع كلّ قراءة.

    الكائن لا يحمل حالة متغيّرة: يحمل المسار، ويفتح اتّصاله عند كلّ استعلام
    (`_connect`)، وتهيئة المخطّط محسوبة على مستوى الصنف (`_schema_ready`).
    فإعادة بنائه في كلّ نداء كانت كلفة صرفًا بلا مقابل.

    ⚠️ والمفتاح **بصمة البيئة كاملة** لا السوق وحده: `settings_db_path`
    يقرأ `QUANT_ANALYSIS_SETTINGS_DB` أوّلًا ثم يشتقّ من جذر الـruntime.
    أوّل صيغة من هذا التخزين فاتها ذلك، فأمسك اختبارُ عقد الحدود سجلًّا
    قديمًا عند تبديل القاعدة وأرجع `BLOCKED` بدل `READY` — تخزينٌ بمفتاح
    ناقص أخطر من غياب التخزين، لأنّه يُقدّم قاعدةً لقاعدة.
    """
    global _registry_cache
    stamp = _registry_env_stamp()
    cached = _registry_cache
    if cached is not None and cached[0] == stamp:
        return cached[1]
    instance = ParameterRegistry()
    _registry_cache = (stamp, instance)
    return instance


def _registry_path() -> str:
    """مسار قاعدة العيارات — يُحسب مرّة لا مع كلّ قراءة عيار.

    ⛔ العطب الذي تعالجه هذه الدالّة، مقيسًا بـ`py-spy` على النواة الحيّة
    ٢٠٢٦-٠٩-١٠ (٣٬٧٦٨ عيّنة): بناء ``ParameterRegistry()`` لمجرّد قراءة
    ``.path`` كان يستهلك **٣٥٫٤٪ من نواة المعالج الوحيدة**. السبب أنّ
    ``__init__`` ينفّذ ``Path(__file__).resolve()`` و``settings_db_path()``
    و``mkdir(parents=True, exist_ok=True)`` في كلّ نداء — أي عمليات نظام
    ملفّات كاملة (``realpath`` ٢٠٫٧٪ · ``mkdir`` ١٣٫٥٪ · ``stat`` ٣٫٩٪).

    والنداء ليس نادرًا: ``_scoped`` في ``analysis_speed`` تستدعي
    ``approved_value`` ⟵ ``unapproved_parameters`` لكلّ محلّل × رمز × تِكّة.

    والأسوأ أنّ الكلفة كانت تُدفع **قبل** فحص الذاكرة المؤقّتة، فالذاكرة
    التي بُنيت لحماية المسار الساخن لم تكن تحميه من شيء.

    المسار يعتمد على ``QUANT_GOV_MARKET`` وحده، وهو ثابت طوال التشغيل؛
    فالمفتاح قيمته، ولو تبدّلت أُعيد الحساب.
    """
    return str(_registry().path)


def _registry_mtime() -> float:
    """بصمة حداثة السجلّ — أحدثُ طابعٍ بين الملفّ ورفيقَي WAL.

    ٢٠٢٦-٠٩-١٦ (مقيس على المنصّة الحيّة، والعلّة نفسها وُجدت في
    `shared/horizon_profile.py` وأُصلحت بـ`1368e22`): المالك أوقف شخصيّة
    الأفق الساعة ١٤:٥٤:٢٣ **ولم يصل الإيقافُ الذرّاتِ**.

        analysis_settings.db       368,640   14:35:44
        analysis_settings.db-wal    16,512   14:54:24   ← الكتابة هنا

    القاعدة تعمل بـ`journal_mode=WAL` (سطر ١٧٠)، فالكتابة تذهب إلى
    `<path>-wal` **ولا تمسّ الملفّ الرئيسيّ**. وهذه البصمة هي التي يقارن بها
    `unapproved_parameters` (٤٨٥-٤٨٦) ليُبطل `_approved_cache` — فما دامت
    لا تتغيّر، لا يُبطَل الكاش أبدًا، و**كلّ عيارٍ يعتمده المالك يبقى خارج
    العملية الحيّة**: الاعتماد يقع في عملية اللوحة فيُبطل كاشَها هي،
    والنواة تبقى على قيمتها القديمة بلا أيّ علامة.

    و`refresh_gate()` لا تنجّي: بحثٌ في `core/` و`atoms/` و`governance/`
    أعطى **صفر مستدعٍ** لها خارج هذا الملفّ — فوجود الدالّة ليس استدعاءها.

    `-shm` مشمول لأنّ نقطة تفتيشٍ قد تُفرِغ `-wal` وتترك أثرها فيه.
    """
    base = _registry_path()
    newest = -1.0
    for suffix in ("", "-wal", "-shm"):
        try:
            stamp = os.path.getmtime(base + suffix)
        except OSError:
            continue
        if stamp > newest:
            newest = stamp
    return newest


def refresh_gate() -> None:
    """يُبطل الذاكرة المؤقّتة — يُستدعى بعد كلّ اعتماد."""
    global _gate_cache, _gate_path
    with _gate_lock:
        _gate_cache = None
        _gate_path = None
        _approved_cache.clear()


def unapproved_parameters() -> list[str]:
    """أسماء المُعامِلات غير المعتمدة — محفوظة وتُعاد قراءتها عند تغيّر القاعدة.

    ⛔ لا تُقرأ القاعدة في كلّ نشرة: `stamp_section` مسار ساخن — الفحص
       الدوريّ بصمةُ ملفّ (stat) لا استعلام، ومرّة كل ثانيتين كحدّ أقصى.
    """
    global _gate_cache, _gate_mtime, _gate_path, _gate_checked_monotonic
    import time as _time
    now = _time.monotonic()
    # م-27 (ورقة ٤١، أمر المالك 2026-08-28): مفتاح الحداثة صار (المسار، mtime)
    # لا mtime وحده — سجلّان مختلفان (فوركس/كريبتو) بختم ثانيةٍ واحد كانا
    # يقدّمان اعتمادات أحدهما للآخر عبر عملية واحدة تخدم السوقين.
    try:
        reg_path = _registry_path()   # محسوب مرّة — لا بناء سجلّ لكلّ تِكّة
    except Exception:  # noqa: BLE001
        reg_path = ""
    with _gate_lock:
        if _gate_cache is not None and _gate_path == reg_path:
            if now - _gate_checked_monotonic < _GATE_RECHECK_S:
                return list(_gate_cache)
    mtime = _registry_mtime()
    with _gate_lock:
        _gate_checked_monotonic = now
        if (_gate_cache is not None and _gate_path == reg_path
                and mtime == _gate_mtime):
            return list(_gate_cache)
    try:
        names = _registry().unapproved()
    except sqlite3.Error:
        # تعذّرت القراءة ⇒ نفترض عدم الاعتماد. المجهول لا يفتح البوّابة.
        names = sorted(DECLARED)
    with _gate_lock:
        _gate_cache = list(names)
        _gate_mtime = mtime
        _gate_path = reg_path
    return list(names)


def approved_value(name: str, fallback: float,
                   scope: str = SCOPE_GLOBAL) -> float:
    """القيمة المعتمدة من المالك لمُعامِل مُعلَن — أو القيمة السارية بالكود.

    وُلدت لسدّ نمط «مفتاح بلا سلك» (سجلّ الختم، البند 47): مُعامِل يعتمده
    المالك بالسجلّ وصفر قارئ له بالكود. تُقرأ عبر نفس بصمة حداثة البوّابة
    (لا استعلام على المسار الساخن إلا عند تغيّر القاعدة فعلًا)."""
    global _approved_cache
    unapproved_parameters()  # يُحدّث بصمة الحداثة ويُبطل ما يلزم
    stamp = (_gate_path, _gate_mtime)  # م-27: الختم بالمسار أيضًا
    # م-38 (ورقة ٤١، أمر المالك «صلّح الباقي» 2026-08-28): الذاكرة كانت تُسقط
    # قيمة المانيفست من مفتاحها — أول مستدعيٍّ (ذرّة/اختبار بمانيفست 1) يسمّم
    # كل من بعده بقميته مهما اختلف مانيفسته (مقيس: 463 بcap=2 يعمل بـ1 بعد
    # أي اختبار سابق). القيمة المخزّنة صارت تحمل الـfallback وتقارن به.
    fallback_key = float(fallback)
    with _gate_lock:
        cached = _approved_cache.get((name, scope))
        if (cached is not None and cached[0] == stamp
                and cached[2] == fallback_key):
            return cached[1]
    try:
        row = _registry().get(name, scope)
    except Exception:  # noqa: BLE001 — قاعدة مقفولة/غائبة لحظيًّا
        return float(fallback)
    value = (float(row["value"])
             if row is not None and str(row.get("status")) == STATUS_APPROVED
             else float(fallback))
    with _gate_lock:
        _approved_cache[(name, scope)] = (stamp, value, fallback_key)
    return value


_approved_cache: dict[tuple[str, str], tuple[float, float]] = {}


def readiness_blocked() -> bool:
    """هل يوجد مُعامِل غير معتمد يحكم بوّابة `READY`؟"""
    return bool(unapproved_parameters())
