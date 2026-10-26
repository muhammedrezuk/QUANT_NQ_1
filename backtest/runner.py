# -*- coding: utf-8 -*-
"""BacktestRunner v2 — يشغّل الذرات الفعلية على بيانات تاريخية حقيقية.

المسار الكامل:
  DataStream → HistoricalClock → SyncEventBus → ذرّات حقيقية → نتيجة

ينشر الأحداث الصحيحة لكل ذرّة:
  - market.tick.validated أولًا (المسار السريع)
  - market_data.candle_closed من ذرّة ١٠٣ فقط (عدد محدود من الفريمات)
  - SYS_SECOND بـ official_time = زمن النقطة (لا ساعة جدارية)
  - platform.account.state قبل أول تيك (ومنه صفّ account_v2 في جسر معزول تقرأه ٦١٩)
"""
from __future__ import annotations

import asyncio
import importlib.util
import logging
import os
import random
import sqlite3
import sys
import time
import uuid
from collections import defaultdict
from pathlib import Path
from typing import Any

from backtest.data_contract import DataPoint, DataStream, DataProvenance
from backtest.historical_clock import HistoricalClock
from backtest.sync_event_bus import SyncEventBus, _run_coro, create_logger
from backtest.experiment_store import Experiment, ExperimentConfig, ExperimentResult, ExperimentStore
from backtest.historical_data import to_tick_payload, to_candle_payload
import clock as _clock_pkg  # نفس مصدر الذرّات الزمنيّ
from clock import mono as clock_mono, now as clock_now  # نفس مصدر الذرّات

log = logging.getLogger("backtest.runner")
ROOT = Path(__file__).resolve().parent.parent


# ── جسر الاختبار الخلفي (نفس عقد الجسر الحيّ، لا قناة جانبية) ──────────────
# ٥١٦ قاطع الأمان لا يُعلن READY إلا على حقيقتين:
#     account_status=HEALTHY  ← platform.account.state (حساب+وسيط+equity>0)
#     system_status =HEALTHY  ← platform.terminal_state (متصل/سماح تداول/سماح X)
# والحقيقتان في الإنتاج ليستا من صانع الاختبار: تكتبهما الجسر في جدول
# `account_v2` وتقرأهما ٦١٩ فتنشرهما. فبدل أن نختلق الحمولة في السطر التالي
# مباشرة، يكتب المُعيد تشغيل صفًّا في ملف جسرٍ **معزول** داخل Var الخاص به،
# وتقرأه ٦١٩ كما تقرأ الجسر الحيّ — نفس المسار، بلا أوامر حقيقية (٦٠١ يكتب
# أوامره في نفس الملف المعزول، ولا MetaTrader5 مستوردٌ هناك أصلًا).
BRIDGE_ACCOUNT_SCHEMA = (
    "CREATE TABLE IF NOT EXISTS account_v2 (account_id TEXT PRIMARY KEY,"
    " broker TEXT, account_server TEXT, margin_mode TEXT, currency TEXT,"
    " leverage REAL, balance REAL, equity REAL, margin REAL, free_margin REAL,"
    " margin_level REAL, open_count INTEGER, floating_pnl REAL,"
    " connected INTEGER, trade_allowed INTEGER, expert_allowed INTEGER,"
    " bridge_beat REAL, updated_at REAL)")


def backtest_var_dir() -> Path:
    """مجلّد Var الخاص بإعادة التشغيل (لا يلمس جسرًا حيًّا ولا قاعدة نواة)."""
    env = os.environ.get("QUANT_CORE_STATE_ROOT", "").strip()
    return Path(env) if env else (ROOT / "var")


def backtest_bridge_db() -> str:
    return str(backtest_var_dir() / "backtest_bridge.db")


class ReplayOfficialClock:
    """مرجع زمنيّ لإعادة التشغيل: «الرسميّ» يسير مع البيانات لا مع ساعة العملية.

    الطابع القانوني للذرّات هو `clock.now()` (مرجع مركزيّ تكتبه ٠٠٣ ويقرؤه
    ٥١٦/٥٥٢/٥١٣/section_contract …). عند إعادة تشغيل بيانات عمرها أشهر — أو
    حتى ملفّ البارحة — تبقى ساعة العملية على «الآن»، فتُحسب أعمار النتائج
    بملايين الثواني وتُعلَن كل القنوات STALE: مقيَس في جولة ١٢٠ تيكًا
    `structure.section.live state=STALE src_ts=1760000009.75` (العمر ٢٨٤٤٠٨٧٩ث)
    ⇒ ٤٥١ تجمع بـ `aggregate_state=STALE` ⇒ ٤٥٥/٤٥٦ ترفضان ⇒ لا gate.passed
    ⇒ صمت التنفيذ كله. العطل في **مرجع الزمن**، لا في البوّابات.
    نُبقي العقد كما هو — نفس الدالة، نفس عدم التناقص، نفس الصيغ — ونُعيد
    توطين «الآن» على الجدول الزمنيّ المُعاد تشغيله، ونُرجع المرجع الأصليّ في
    النهاية. لا يُمسّ `mono()` لأن الذرّات تقارن به أختامًا وضعتْها هي هي.
    """

    def __init__(self, target, real_now) -> None:
        self._target = target
        self._real_now = real_now
        self._on = False

    def install(self) -> None:
        self._target.now = self.now
        self._on = True

    def restore(self) -> None:
        if self._on:
            self._target.now = self._real_now
            self._on = False

    def set_time(self, value: float) -> None:
        cur = getattr(self._target, "_replay_now", None)
        self._target._replay_now = float(value) if cur is None or value >= cur else cur

    def now(self) -> float:
        value = getattr(self._target, "_replay_now", None)
        return float(value) if value is not None else self._real_now()


def pump_bridge_readers(atoms: dict[int, Any]) -> int:
    """يُنادي `read_now` عند ٦١٩: قراءة الجسر من الذرّة نفسها، لا بحمولة مخترعة.

    في إعادة التشغيل المتزامنة لا تُدار حلقة الأحداث بين التيكات، فتبقى مهمة
    الاستطلاع الداخلية عند ٦١٩ خاملة (مقيَس: reads=0 مع أنّ صفّ `account_v2`
    مكتوب). هذا المنادى يستدعي `_read_once` نفسه — نفس العقد والأعمدة وشرط
    الطزاجة — مكانَ مؤقّت الذرّة.
    """
    atom = atoms.get(619)
    fn = getattr(atom, "read_now", None) if atom is not None else None
    if fn is None:
        return 0
    try:
        return int(fn() or 0)
    except Exception as exc:
        log.warning("قراءة جسر الاختبار عند ٦١٩ فشلت: %s: %s", type(exc).__name__, exc)
        return 0


def write_bridge_account(row: dict[str, Any]) -> None:
    """صفّ account_v2 في ملف الجسر المعزول — WAL مثل الجسر، بلا حذف ولا إعادة تسمية."""
    path = Path(backtest_bridge_db())
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=5.0)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=3000")
        conn.execute(BRIDGE_ACCOUNT_SCHEMA)
        conn.execute(
            "INSERT INTO account_v2 (account_id, broker, account_server, margin_mode,"
            " currency, leverage, balance, equity, margin, free_margin, margin_level,"
            " open_count, floating_pnl, connected, trade_allowed, expert_allowed,"
            " bridge_beat, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
            " ON CONFLICT(account_id) DO UPDATE SET"
            " broker=excluded.broker, account_server=excluded.account_server,"
            " margin_mode=excluded.margin_mode, currency=excluded.currency,"
            " leverage=excluded.leverage, balance=excluded.balance, equity=excluded.equity,"
            " margin=excluded.margin, free_margin=excluded.free_margin,"
            " margin_level=excluded.margin_level, open_count=excluded.open_count,"
            " floating_pnl=excluded.floating_pnl, connected=excluded.connected,"
            " trade_allowed=excluded.trade_allowed, expert_allowed=excluded.expert_allowed,"
            " bridge_beat=excluded.bridge_beat, updated_at=excluded.updated_at",
            (row["account_id"], row["broker"], row.get("account_server", "backtest"),
             row.get("margin_mode", "RETAIL_NETTING"), row.get("currency", "USD"),
             row.get("leverage", 100.0), row.get("balance"), row.get("equity"),
             row.get("margin", 0.0), row.get("free_margin"), row.get("margin_level"),
             row.get("open_count", 0), row.get("floating_pnl", 0.0),
             int(row.get("connected", True)), int(row.get("trade_allowed", True)),
             int(row.get("expert_allowed", True)), row.get("bridge_beat"),
             row.get("updated_at")))
        conn.commit()
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════════════════════════
# تحميل الذرّات
# ═══════════════════════════════════════════════════════════════════════════════

def _load_atom_class(atom_dir: Path, module_name: str, class_name: str = "Atom") -> Any:
    """تحميل كلاس الذرة — بنفس عقد Bootloader (لا نسخة مبسّطة تنكسر على الذرّات المتعدّدة الملفات).

    ما كان: المكتبة تُنفَّذ ومجلدُها ليس على مسار البحث، فتفشل كل ذرّة
    متعدّدة الملفات تستورد جارتها باسم مجرّد (`from spread_gate import …` في
    ٥٥٢، `reconcile_support` في ٥٢٠) بصمت مُطلَق — log.debug وحده، ولا
    «ذرّة محمَّلة» في النتيجة. النتيجة المقاسة: حلق كاملة (٥٥٢ مدقّق الأمر =
    مصدر trading.final_decision، و٥٢٠ المطابقة) غابت عن الباك تست فبدا
    التنفيذ ميتًا وهو في الحقيقة لم يُحمَّل.
    ما صار: نسخة عقدية من core/bootloader.py — تسجيل الموديول قبل التنفيذ،
    إضافة مجلد الذرة أثناء التنفيذ فقط ثم سحبه، وعزل الموديولات الجارة
    بنفس البادئة، فيُستورد جارتها لا جارةَ ذرّةٍ أخرى.
    """
    atom_file = atom_dir / "atom.py"
    if not atom_file.exists():
        return None
    spec = importlib.util.spec_from_file_location(module_name, str(atom_file))
    if spec is None or spec.loader is None:
        return None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    dir_str = str(atom_dir.resolve())
    before = set(sys.modules)
    sys.path.insert(0, dir_str)
    try:
        spec.loader.exec_module(mod)
    except Exception as exc:
        sys.modules.pop(module_name, None)
        log.warning(f"فشل تحميل {atom_dir.name}: {type(exc).__name__}: {exc}")
        return None
    finally:
        try:
            sys.path.remove(dir_str)
        except ValueError:
            pass
        try:
            from core.bootloader import Bootloader
            Bootloader._isolate_sibling_modules(_atom_id_of(module_name), dir_str, before)
        except Exception:  # noqa: BLE001 — بلا core/ (اختبار معزول) نكتفي بسحب المسار
            pass
    # الكلاس من entrypoint المانيفست أولًا، ثم البحث المعتاد
    cls = getattr(mod, class_name, None)
    if isinstance(cls, type) and hasattr(cls, "initialize") and hasattr(cls, "start"):
        return cls
    for name in ("Atom", "AtomBase"):
        cls = getattr(mod, name, None)
        if cls and hasattr(cls, "initialize") and hasattr(cls, "start"):
            return cls
    for attr_name in dir(mod):
        obj = getattr(mod, attr_name)
        if isinstance(obj, type) and attr_name not in ("AtomBase", "AtomContext"):
            if hasattr(obj, "initialize") and hasattr(obj, "start"):
                return obj
    log.warning(f"لا كلاس ذرّة في {atom_dir.name} (entrypoint={class_name})")
    return None


def _atom_id_of(module_name: str) -> int:
    """رقم الذرّة من اسم الموديول المُولَّد ("bt_v2_atom_552") — بلا فرض بلاغ."""
    tail = module_name.rsplit("_", 1)[-1]
    try:
        return int(tail)
    except ValueError:
        return 0


def _entrypoint_class(manifest: dict[str, Any]) -> str:
    """class_name من entrypoint المانيفست (النمط: "atom:Atom")."""
    ep = str(manifest.get("entrypoint") or "atom:Atom")
    return ep.split(":", 1)[1] if ":" in ep else "Atom"


def _load_manifest(atom_dir: Path) -> dict[str, Any]:
    import yaml
    manifest_file = atom_dir / "manifest.yaml"
    if not manifest_file.exists():
        return {}
    try:
        return yaml.safe_load(manifest_file.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


def discover_atoms(atoms_dir: Path, atom_range: tuple[int, int] | None = None) -> list[dict]:
    results = []
    for section_dir in sorted(atoms_dir.iterdir()):
        if not section_dir.is_dir():
            continue
        for atom_dir in sorted(section_dir.iterdir()):
            if not atom_dir.is_dir() or not (atom_dir / "atom.py").exists():
                continue
            try:
                atom_id = int(atom_dir.name.split("_", 1)[0])
            except (ValueError, IndexError):
                continue
            if atom_range and not (atom_range[0] <= atom_id <= atom_range[1]):
                continue
            manifest = _load_manifest(atom_dir)
            results.append({
                "dir": atom_dir, "id": atom_id,
                "name": atom_dir.name.split("_", 1)[-1] if "_" in atom_dir.name else "",
                "manifest": manifest,
                "startup_mode": manifest.get("startup_mode", "auto"),
            })
    return results


# ═══════════════════════════════════════════════════════════════════════════════
# BacktestRunner v2
# ═══════════════════════════════════════════════════════════════════════════════

class BacktestRunner:
    """المحرك — يشغّل ذرّات حقيقية مع المسار الكامل."""

    def __init__(self, atoms_dir: Path | None = None):
        self._atoms_dir = atoms_dir or (ROOT / "atoms")
        self._bus = SyncEventBus()
        self._loaded_atoms: dict[int, Any] = {}
        self._atom_meta: dict[int, dict] = {}
        self._clock: HistoricalClock | None = None
        self._stream: DataStream | None = None
        self._stage_outputs: dict[str, list[dict]] = {}
        self._decisions: list[dict] = []
        self._run_id: str = ""
        self._error: str = ""
        self._started_at: float = 0
        self._finished_at: float = 0
        # Candle builder
        self._candle_buffer: dict[str, dict] = {}
        self._current_candle_ts: float = 0
        self._candle_interval: float = 60.0  # M1 default
        self._tick_count: int = 0
        self._candle_count: int = 0
        self._news_queue: list[dict[str, Any]] = []

    @property
    def bus(self) -> SyncEventBus:
        return self._bus

    @property
    def loaded_atom_ids(self) -> list[int]:
        return sorted(self._loaded_atoms.keys())

    # ═══ تحميل الذرّات ═══

    def load_atoms(self, atom_ids: list[int] | None = None,
                   atom_range: tuple[int, int] | None = None,
                   config_overrides: dict[int, dict] | None = None) -> int:
        """تحميل ذرّات محددة. config_overrides طبقة ذاكرة فقط — لا تُكتب للمانيفست."""
        discovered = discover_atoms(self._atoms_dir, atom_range)
        count = 0
        for info in discovered:
            if atom_ids and info["id"] not in atom_ids:
                continue
            cls = _load_atom_class(info["dir"], f"bt_v2_atom_{info['id']}",
                                  _entrypoint_class(info["manifest"]))
            if cls is None:
                continue
            try:
                atom = cls()
                config = dict(info["manifest"].get("config") or {})
                extra = (config_overrides or {}).get(info["id"])
                if extra:
                    config.update(extra)
                ctx = _make_context(info["id"], config, self._bus)
                loop = asyncio.new_event_loop()
                loop.run_until_complete(atom.initialize(ctx))
                loop.run_until_complete(atom.start())
                loop.close()
                self._loaded_atoms[info["id"]] = atom
                self._atom_meta[info["id"]] = info
                count += 1
            except Exception as exc:
                log.warning(f"فشل تهيئة ذرّة {info['id']} ({info['dir'].name}): "
                            f"{type(exc).__name__}: {exc}")
        return count

    def load_full_pipeline(self, config_overrides: dict[int, dict] | None = None) -> int:
        """تحميل المسار الكامل من كل قسم.

        config_overrides طبقة ذاكرة فقط تُمرَّر كما في load_atoms — تُستعمل
        لقياس المسار بعتبات مُرخاة دون لمس أي مانيفست على القرص.

        الحلق الثلاث التي كانت مفقودة (مقيَسة على الناقل، لا ادّعاءً):
        · ٤٥٨ حلّ التعارض  — حلقة الوصل decision.scored → decision.resolved ← ٤٥٤
        · ٥١٦ قاطع الأمان  — مصدر risk.validation.completed ← ٥٥١ (باني الأمر)
        · ٥٥٢ مدقّق الأمر  — مصدر trading.final_decision ← ٥٥٠ و٦٢٦ (التنفيذ)
        · وسلسلة المخاطر/الشرعية المطلوبة منها: ٥١٢/٥١٣ (تحدّد risk.position_size.state
          ← ٥٥١)، ٥٨٤ (execution.order.legal ← ٥٥٢)، ٥١٧/٥١٨ (دفتر الأصل)، ٥٨٥ (حارس
          الهامش)، ٥١٩/٥٢٠ (المحفظة والمطابقة).
        بدونها يُلخَّص المسار «decision=٤٠٠ / execution=٠» ويُنسب الفراغ إلى
        المحرّك، وهو في الحقيقة قطعٌ في السلسلة: ٤٥٣ → ٥٥١ → ٥٥٢ → ٥٥٠/٦٢٦.
        """
        key_atoms = [
            # Analysis (150-166) — المدير + كل التحليلات، لا عيّنة منها:
            # ٤٥١ يحجب إشارته عن كل قسم ناقص (m-46 new_invalid_sections)،
            # فاقتطاع القائمة كان يُنتج «تجميع قرار» بثُمن الصورة ويُقفل الباب
            # على ٤٥٨ عند wait(NO_ELIGIBILITY) بلا سبب مفهوم.
            150, 151, 152, 153, 154, 155, 156, 157, 158, 159, 160, 161, 162, 163, 164, 165, 166,
            # Structure (200-210) — مدير القسم ٢٠٠ ثم rest
            200, 201, 202, 203, 204, 205, 206, 207, 208, 209, 210,
            # Liquidity (250-264) — pool → buyside/sellside → sweep → publish
            250, 251, 252, 253, 254, 255, 256, 257, 258, 259, 260, 261, 262, 263, 264,
            # Statistics (300-318) — ticks → stats → cycle
            300, 301, 302, 303, 304, 305, 306, 307, 308, 309, 310, 311, 312, 313, 314, 315, 316, 318,
            # Probability (350-359) — مدير القسم ٣٥٠ (صاحب probability.section.live،
            # وهو ما كان ٤٥١ يسمّيه top_missing=350=400) ثم النماذج والدمج
            350, 351, 352, 353, 354, 355, 356, 357, 358, 359,
            # Strategy (400-413) — مدير القسم ٤٠٠ ثم الاستراتيجيات
            400, 401, 402, 403, 404, 405, 406, 407, 408, 409, 410, 411, 412, 413,
            # Decision (450-468) — aggregated + signal eval + score + filter + buy/sell + conflict,
            # ثم سُلَّم البوابات الذي كان مفقودًا (مقيَس على القرص: لم تكن هذه المعرّفات
            # في key_atoms أصلًا، لم تُرفض ولم تفشل):
            #   ٤٥٠ مدير القرار (decision.cycle.*) — يشهد حلقات التجميع/الدرجة/الموافقة
            #   ٤٦٠/٤٦١/٤٦٢/٤٦٣/٤٦٤ فلترات الثقة/الشروط/التوقيت/المراكز/الطزاجة
            #   ٤٦٦ موافقة القرار — بوابتها آلية (decision.filtered.state + side صالح
            #         + metadata.passed) وليست موافقة بشرية؛ بلا مصدر لـ
            #         decision.approved.state تظلّ ٤٦٧ صامتة فيصمت ٥٧٦/٥٧٨.
            450, 451, 452, 453, 454, 455, 456, 457, 458,
            460, 461, 462, 463, 464, 466,
            # Risk (500+) — account + exposure + profit + session → unified + safety cutoff,
            # sizing, asset ledger and margin guard (الحلقات التي تطلبها ٥٥١/٥٥٢)
            500, 506, 507, 508, 512, 513, 516, 517, 518, 519, 520, 585,
            # Execution (550-708) — الباني ٥٥١ → شرعية الستوب ٥٨٤ → مدقّق الأمر ٥٥٢
            # → مدير التنفيذ ٥٥٠ + المطابقة ٥٢٠؛ وحلقة الهامش/القرار التي كانت
            # مقطوعة (مقيَسة: risk.validation.completed = ٠ رغم position_size = ٤٠٠):
            #   ٥٧٨ منفذ التحوط (يبتدئ risk.validation.completed → execution.order.requested)
            #   ٥٨٦ بوابة دمج الرمز (execution.order.requested → execution.order.resolved)
            #   ٥٨٥ حارس الهامش (execution.order.resolved → risk.margin.validation.completed)
            #   ٧٠٨ سجلّ الرموز (symbol.resolve.requested → symbol.resolve.result)
            #   ٥٨٣ لقطة التنفيذ (execution.snapshot.state لـ٥٧٨ و٥٥٢)
            #   ٤٦٨ التحكم بالأصول (allowed.symbols.state ← ٥٥٢؛ بلا مصدر له يُرفض كل أمر)
            #   ٤٦٧ إرسال القرار (decision.gate.passed ← ٥٧٦/٥٧٨)
            #   ٥٨٦ بوابة دمج الرمز و٥٦٣ تأكيد التنفيذ و٥٦٠ جودة التنفيذ — كانت
            #       مجلّداتها موجودة على القرص ولم تُذكَر قطّ في هذه القائمة
            #       (مقيَس: `loaded=124` مقابل ١٣١ مجلّدًا في المدى المطلوب،
            #       الناقص: ٥٦٠/٥٦٣/٥٨٦). بلا ٥٨٦ لا `execution.order.resolved`
            #       فتبقى ٥٨5 صامتة؛ وبلا ٥٦٣ لا `execution.command.ack` ولا
            #       `market.outcome.realized` — أي أن حلقة التنفيذ تُبنى ولا تُؤكَّد.
            #   ٦٠١ كاتب جسر الدماغ: مانيفسته تعطي db_path مسارًا ويندوزيًّا
            #       مطلقًا (C:\Users\NQ\…) وهو هنا غير موجود، فتفشل تهيئته صامتة.
            #       يُحمَّل مع تجاوز مسارٍ معزول أدناه (لا يلمس الجسر الحيّ).
            #   ٦١٩ حالة الحساب من الجسر: مصدر platform.terminal_state الوحيد —
            #       بدونه يبقى system_status=UNKNOWN عند ٥١٦ فلا `risk.validation.completed`
            #       أبدًا (وهو نفس العطل الذي كان يُقرأ خطأً «قاطع الأمان معطوب»).
            467, 468, 550, 551, 552, 560, 563, 576, 578, 583, 584, 586, 601, 619, 626, 708,
            # Portfolio truth owners (651-659) — ٥١٣ لا يقرأ platform.account.state
            # مباشرة: FinancialTruth مربوط بأصحاب الحقيقة (OWNER_OF: equity←٦٥٤،
            # balance←٦٥٣، …). بدونهم لا equity في أي إعادة تشغيل، فيبقى
            # NO_EQUITY_YET ويمنع risk.position_size.state فتصمت ٥٥١ للأبد.
            651, 652, 653, 654, 655, 656, 657, 658, 659,
        ]
        # عزل مسار الجسر داخل إعادة التشغيل: التجاوز طبقة ذاكرة فقط تُمرَّر كما هي،
        # ولا تُكتب في المانيفست ولا تُنقل إلى نواة حيّة.
        overrides = dict(config_overrides or {})
        # بوابة الأصول ٤٦٨: افتراضيّ مانيفستها (`allowed_symbols: [BTCUSD]`) صُمّمت
        # لأصل دائم معيّن؛ وإعادة التشغيل هذه تُعيد تيكات الرمز الذي يحمله الملف
        # (EURUSD في الغالب). النتيجة المقيَسة قبل هذا الضبط: كل تيك يُمنع عند ٤٦٨
        # ⇒ ٤٥٤ تُغلِق بـ `fail=asset` ⇒ ٤٦٧ تُسجِّل WAIT ولا تُرسل ⇒ سلسلة التنفيذ
        # كلها صفر. الإصلاح في **تهيئة المُعيد تشغيل** (طبقة ذاكرة، لا تُكتب في
        # المانيفست ولا تُطبَّق على النواة الحيّة)، لا في تخفيف البوابة نفسها.
        replay_symbol = (self._stream.symbol if self._stream else "").strip()
        if replay_symbol:
            gate = dict(overrides.get(468) or {})
            gate.setdefault("allowed_symbols", [replay_symbol])
            self._pipeline_overrides = overrides
            overrides[468] = gate
        bridge_db = backtest_bridge_db()
        for aid, extra in ((601, {"cursor_db": str(backtest_var_dir() / "backtest_cursor.db")}),
                           (619, {"poll_interval_s": 0.05})):
            cfg = dict(overrides.get(aid) or {})
            cfg.setdefault("db_path", bridge_db)
            cfg.update({k: v for k, v in extra.items() if not cfg.get(k)})
            overrides[aid] = cfg
        return self.load_atoms(atom_ids=key_atoms, config_overrides=overrides)

    # ═══ البيانات ═══

    def adjust_pipeline_symbol_gate(self) -> bool:
        """يُطبَّق بوابة الأصول ٤٦٨ على رمز البيانات بعد إرفاقها.

        ترتيب المُقلِعات الشائع هو `load_full_pipeline()` ثم `set_data(...)`؛
        حينها لم يكن الرمز معلومًا وقت حساب التجاوز، فتبقى بوابة ٤٦٨ على
        افتراضيّ مانيفستها (أصل دائم واحد) وتُعطِّل كل تيك ⇒ لا أهلية ولا
        إرسال ولا تنفيذ (مقيَس: `468 _allowed={'BTCUSD'} _blocked=300`).
        تُعاد تهيئة ٤٦٧٨—عفوَ—٤٦٨ من **مانيفستها + التجاوز** عبر عقدها هي،
        وتُزال معالجات النسخة القديمة من الناقل (بلا إزالة تتضاعف الحمولات).
        """
        sym = str(getattr(self._stream, "symbol", "") or "").strip()
        overrides = getattr(self, "_pipeline_overrides", None) or {}
        if not sym or 468 in overrides:
            return False
        gate = dict(overrides.get(468) or {})
        if list(gate.get("allowed_symbols") or []) == [sym]:
            return False
        overrides[468] = {**gate, "allowed_symbols": [sym]}
        self._pipeline_overrides = overrides
        meta = self._atom_meta.get(468)
        atom = self._loaded_atoms.get(468)
        if meta is None or atom is None:
            return False
        for event in (meta.get("manifest") or {}).get("subscribes") or []:
            name = event if isinstance(event, str) else (event.get("event") or event.get("name"))
            handlers = self._bus._handlers.get(name, [])
            self._bus._handlers[name] = [h for h in handlers
                                         if getattr(h, "__self__", None) is not atom]
        fresh = type(atom)()
        _run_coro(fresh.initialize(_make_context(468, overrides[468], self._bus)))
        _run_coro(fresh.start())
        self._loaded_atoms[468] = fresh
        log.info("بوّابة ٤٦٘ طُبِّقَت على رمز إعادة التشغيل: %s", sym)
        return True

    def set_data(self, stream: DataStream) -> None:
        """تعيين بيانات تاريخية."""
        self._stream = stream
        self._clock = HistoricalClock(stream, strict=True)
        self.adjust_pipeline_symbol_gate()
        # النظام تيكات. الشموع يبنيها ١٠٣ من التيك — لا ننشر شمعة الملف كأنها تيك.
        self._is_real_candle_data = False
        tf_map = {"M1": 60, "M5": 300, "M15": 900, "M30": 1800, "H1": 3600, "D1": 86400, "tick": 1}
        self._candle_interval = tf_map.get(stream.timeframe, 1)

    def set_news(self, rows: list[dict[str, Any]]) -> None:
        """صفوف جسر حقيقية تُنشر وقت التيك — بلا عنوان مخترَع."""
        def _when(row: dict[str, Any]) -> float:
            for key in ("published_at", "scheduled_at", "timestamp"):
                try:
                    if row.get(key) is not None:
                        return float(row[key])
                except (TypeError, ValueError):
                    continue
            return 0.0
        self._news_queue = sorted((r for r in rows if isinstance(r, dict)), key=_when)

    @staticmethod
    def _news_when(row: dict[str, Any]) -> float:
        """توقيت صيرورة الصفّ نافذًا — نفس مفاتيح set_news، بلا بدائل مخترَعة."""
        for key in ("published_at", "scheduled_at", "timestamp"):
            try:
                if row.get(key) is not None:
                    return float(row[key])
            except (TypeError, ValueError):
                continue
        return 0.0

    def _flush_news(self, now_ts: float) -> int:
        """تفريغ طابور الأخبار المؤجَّلة عند زمن إعادة التشغيل الحالي.

        حيًّا ينشر ٦١٥/٦١٦ «market.news»؛ وفي إعادة التشغيل كان الصفّ يبقى في
        الطابور إلى الأبد — الحلقة تنادي _flush_news ولا أحد عرَّفها، فيسقط
        التشغيل كله بـAttributeError عند أول تيك. النشر بترتيب زمني تصاعدي من
        مقدّمة الطابور فقط (O(1) مضافًا لكل تيك)، و١٠٨ يخصم التكرار بمفتاح id
        أو headline+published_at — فلا إعادة نشر ولا تكرار.
        """
        published = 0
        queue = self._news_queue
        while queue and self._news_when(queue[0]) <= now_ts:
            row = queue.pop(0)
            self._bus.publish("market.news", row)
            published += 1
        return published

    def set_data_from_points(self, points: list[DataPoint],
                              symbol: str = "EURUSD",
                              timeframe: str = "M1",
                              source: str = "backtest") -> None:
        """تعيين بيانات من نقاط."""
        provenance = DataProvenance(original_source=source, ingest_time=time.time())
        self._stream = DataStream(
            symbol=symbol, timeframe=timeframe, source=source,
            points=points, provenance=provenance,
        )
        self._clock = HistoricalClock(self._stream, strict=True)
        self._is_real_candle_data = False
        tf_map = {"M1": 60, "M5": 300, "M15": 900, "M30": 1800, "H1": 3600, "tick": 1, "D1": 86400}
        self._candle_interval = tf_map.get(timeframe, 1)
        self.adjust_pipeline_symbol_gate()

    # ═══ التشغيل ═══

    def run(self) -> dict[str, Any]:
        """تشغيل الباك تست — يمرر البيانات عبر كل المراحل."""
        self._run_id = f"RUN-{uuid.uuid4().hex[:8].upper()}"
        self._started_at = time.time()
        self._stage_outputs = {
            "analysis": [], "structure": [], "liquidity": [],
            "statistics": [], "probability": [], "strategy": [],
            "decision": [], "risk": [], "execution": [],
        }
        self._decisions = []
        self._error = ""
        self._tick_count = 0
        self._candle_count = 0
        self._candle_buffer = {}

        if self._clock is None:
            self._error = "لا توجد بيانات"
            return self._build_result()
        if not self._loaded_atoms:
            self._error = "لا توجد ذرّات محمّلة"
            return self._build_result()

        # إعداد مراقبة الأحداث
        self._setup_monitors()
        # مرجع زمنيّ موحَّد: «الرسميّ» = زمن الجدول المُعاد تشغيله، ويُستعاد
        # المرجع الأصليّ بعد آخر تيك — لا ساعة عملية تُقادم كل قناة بالقياس.
        _replay_clock = ReplayOfficialClock(_clock_pkg, _clock_pkg.now)
        _replay_clock.install()

        def _identity(ts: float, symbol: str = "") -> None:
            # 100_000 = نفس initial_capital الافتراضي في BacktestConfig؛ الحساب
            # الصغير يجعل كل حجمٍ محسوب دون volume_min فيردّ ٥١٣ بـ
            # VOLUME_BELOW_BROKER_MIN ويصمت الفرع كله بلا عطل فيه.
            self._bus.publish("platform.account.state", {
                "account_id": "backtest_001", "broker": "backtest",
                "balance": 100000.0, "equity": 100000.0,
                "free_margin": 100000.0, "margin_used": 0.0,
                "unrealized_pnl": 0.0, "realized_pnl": 0.0,
                "leverage": 100, "currency": "USD",
                "timestamp": ts,
                # حقول يقرؤها أصحاب الحقيقة (٦٥٣‑٦٥٧) بمفاتيحهم الخاصة؛ بلا هذه
                # الأسماء تصل الحمولة ولا يستوعبها FinancialTruth ⇒ صمت تام.
                "measured_at": ts,
            })
            self._bus.publish("platform.positions.state", {
                "account_id": "backtest_001", "broker": "backtest",
                "positions": [], "count": 0,
                "open_count": 0, "floating_pnl": 0.0,
                "timestamp": ts, "measured_at": ts,
            })
            if symbol:
                # عقد ٦١٨ الحرفي: صفّ داخل "symbols"، لا حقلًا مسطّحًا.
                # كان الحمولة مسطّحة ⇒ _on_specs لا يرى "symbols" فتبقى
                # self._specs فارغة، و٥١3 يردّ SIZING_UNAVAILABLE_FOR_SYMBOL
                # بلا صوت، فلا حجم مركز ولا ٥٥١ ولا أمر ولا تنفيذ.
                self._bus.publish("market.symbol_specs", {
                    "provider": "backtest",
                    # سند المساحات يُختم بزمن الرصد الحيّ لا بزمن التيك المُعاد
                    # تشغيله — تمامًا كما يفعل ٦١٨ (`clock.now()`)؛ وبلا ذلك
                    # يبدو كل شيء STALE فورًا في أي ملف أقدم من specs_max_age_s.
                    "published_at": clock_now(),
                    "published_monotonic": clock_mono(),
                    "symbols": [{
                        "account_id": "backtest_001", "broker": "backtest",
                        "symbol": symbol,
                        "contract_size": 100000.0,
                        "tick_value": 10.0, "tick_size": 0.00001,
                        "point": 0.00001, "digits": 5,
                        "stops_level": 0, "freeze_level": 0,
                        "volume_min": 0.01, "volume_max": 100.0,
                        "volume_step": 0.01, "filling_mode": "both",
                        "spec_published_at": clock_now(),
                        "spec_observed_monotonic": clock_mono(),
                    }],
                })

        first_ts = self._stream.first_ts if self._stream else 0.0
        first_sym = self._stream.symbol if self._stream else ""
        _identity(first_ts, first_sym)
        # أول صفّ جسر قبل أول تيك: ٦١٩ يقرأ الجسر عند أول نبضة، فلا تكون هناك
        # نافذة تُعلن فيها ٥١٦ UNKNOWN بعد أول قرار.
        write_bridge_account({
            "account_id": "backtest_001", "broker": "backtest",
            "balance": 100000.0, "equity": 100000.0,
            "free_margin": 100000.0, "margin": 0.0, "margin_level": None,
            "open_count": 0, "floating_pnl": 0.0,
            "connected": True, "trade_allowed": True, "expert_allowed": True,
            "bridge_beat": clock_now(), "updated_at": clock_now(),
        })
        pump_bridge_readers(self._loaded_atoms)

        # تيكات أولًا. الشموع من ١٠٣ — لا ننشر شمعة الملف كأنها تيك.
        for point in self._clock:
            # «الآن» يساير التيك: عمر أي نتيجة = فارق التيكات لا فارق التقويم.
            _replay_clock.set_time(point.timestamp + 1.0)
            self._tick_count += 1
            self._flush_news(point.timestamp)
            self._bus.publish("market.tick.validated", to_tick_payload(point))
            # بناء الشموع من التيكات كان مكتوبًا (١٠٣-ستايل) ولا أحد يناديه:
            # market_data.candle_closed لا يُنشر أبدًا ⇒ كل ما يُبنى على شمعة
            # (التحليل/الهيكل/السيولة/الاحتمالات/الاستراتيجيات في الباك تست)
            # يشتغل على نافذة تيكات فقط، فتبقى الحالة «غير مكتملة» بلا سبب ظاهر.
            self._build_and_publish_candle(point)

            if self._tick_count % 10 == 0:
                self._bus.publish("SYS_SECOND", {
                    "timestamp": point.timestamp,
                    "official_time": point.timestamp,
                    "now": point.timestamp,
                })

            # الهوية والمساحات تُجدَّد على إيقاع ٥٠ تيكًا — مثل إعادة نشر
            # ٦١٨ في الإنتاج، فلا تشيخ المساحات في جولة طويلة (بلا ترفيع سقف).
            if self._tick_count % 50 == 0:
                _identity(point.timestamp, point.symbol)
                # جسر الاختبار المعزول: بنفس الإيقاع، فيبقى updated_at طازجًا
                # بالنسبة لساعة الجدار (max_age_s=٣٠٠) فلا تُعلَن الحالة قديمة.
                write_bridge_account({
                    "account_id": "backtest_001", "broker": "backtest",
                    "balance": 100000.0, "equity": 100000.0,
                    "free_margin": 100000.0, "margin": 0.0, "margin_level": None,
                    "open_count": 0, "floating_pnl": 0.0,
                    "connected": True, "trade_allowed": True, "expert_allowed": True,
                    "bridge_beat": clock_now(), "updated_at": clock_now(),
                })
                pump_bridge_readers(self._loaded_atoms)

        # إيقاف حلقات الذرّات الخلفية (٦١٩ استطلاع الجسر، ٥٨٦/٦٠١ نبضات،
        # ٥١٧ حارس اليقظة): بلا هذا تبقى المهام معلّقة عند الخروج فتُقتل
        # العملية وهي "pending" ويضيع دليل الحالة في اللوحة.
        for aid, atom in list(self._loaded_atoms.items()):
            fn = getattr(atom, "shutdown", None) or getattr(atom, "stop", None)
            if fn is None:
                continue
            try:
                out = fn()
                if asyncio.iscoroutine(out):
                    # نفس حلقة Bus المشترك (`_run_coro`) — لا حلقة جديدة: مهام
                    # الذرّات الخلفية وُلدت على حلقة Bus، والإلغاء عبر حلقتين
                    # يرفع "attached to a different loop" ويترك المهمة حيّة.
                    _run_coro(out)
            except Exception as exc:  # الإيقاف لا يُسكت قياسًا، يُسجَّل
                log.warning("إيقاف %s فشل: %s: %s", aid, type(exc).__name__, exc)
        _replay_clock.restore()
        self._finished_at = time.time()
        clock_report = self._clock.report() if self._clock else {}
        return self._build_result(clock_report=clock_report)

    def _build_and_publish_candle(self, point: DataPoint) -> None:
        """بناء شمعة من التيكات ونشرها."""
        if self._candle_interval <= 0:
            return

        candle_ts = int(point.timestamp / self._candle_interval) * self._candle_interval
        sym = point.symbol

        if sym not in self._candle_buffer or self._candle_buffer[sym]["ts"] != candle_ts:
            # شمعة جديدة — ننشر القديمة إن وجدت
            if sym in self._candle_buffer:
                self._publish_candle(self._candle_buffer[sym])
            self._candle_buffer[sym] = {
                "ts": candle_ts, "symbol": sym,
                "open": point.close, "high": point.close,
                "low": point.close, "close": point.close,
                "volume": point.volume,
            }
        else:
            buf = self._candle_buffer[sym]
            buf["high"] = max(buf["high"], point.close)
            buf["low"] = min(buf["low"], point.close)
            buf["close"] = point.close
            buf["volume"] += point.volume

    def _publish_candle(self, candle: dict) -> None:
        """نشر شمعة مغلقة."""
        self._candle_count += 1
        payload = {
            "symbol": candle["symbol"],
            "account_id": "backtest_001",
            "broker": "backtest",
            "timestamp": candle["ts"],
            "source_timestamp": candle["ts"],
            "exchange_timestamp": candle["ts"],
            "open": candle["open"],
            "high": candle["high"],
            "low": candle["low"],
            "close": candle["close"],
            "volume": candle["volume"],
            "timeframe": self._stream.timeframe if self._stream else "M1",
            "source": self._stream.source if self._stream else "backtest",
            "sequence": self._candle_count,
            "period_start": candle["ts"],
        }
        self._bus.publish("market_data.candle_closed", payload)

    def _setup_monitors(self) -> None:
        """مراقبة أحداث كل مرحلة."""
        monitors = {
            "analysis": ["analysis.trend.state", "analysis.momentum.state",
                         "analysis.volatility.state", "analysis.volume.state",
                         "analysis.spread.state", "analysis.candle.state",
                         "analysis.gap.state", "analysis.session.state",
                         "analysis.regression.state", "analysis.corr.state",
                         "analysis.divergence.state", "analysis.vol_regime.state",
                         "analysis.profile.state", "analysis.pivot.state",
                         "analysis.micro.structure.state", "analysis.dynamics.state"],
            "structure": ["market.structure.updated", "structure.cycle.collected",
                          "structure.section.live", "structure.swing.state",
                          "structure.break.state", "structure.bos.state",
                          "structure.choch.state", "structure.ob.state",
                          "structure.htf.state", "structure.range.state",
                          "structure.equal.state", "structure.order_block.state"],
            "liquidity": ["market.liquidity.updated", "liquidity.cycle.collected",
                          "liquidity.pool.state", "liquidity.buyside.state",
                          "liquidity.sellside.state", "liquidity.sweep.state",
                          "liquidity.fvg.state", "liquidity.section.live"],
            "statistics": ["stats.cycle.collected", "stats.section.live",
                           "stats.mean.state", "stats.median.state",
                           "stats.mode.state", "stats.stddev.state",
                           "stats.variance.state", "stats.percentile.state",
                           "stats.zscore.state", "stats.skew.state",
                           "stats.kurtosis.state", "stats.autocorr.state",
                           "stats.entropy.state", "stats.hurst.state",
                           "stats.cusum.state", "stats.moving_stats.state"],
            "probability": ["probability.cycle.collected", "probability.confidence.state",
                            "probability.section.live", "probability.trend.state",
                            "probability.reversal.state", "probability.breakout.state",
                            "probability.momentum.state", "probability.merged.state",
                            "probability.hurst.state", "probability.range.state",
                            "probability.pullback.state"],
            "strategy": ["strategy.trend.state", "strategy.reversal.state",
                         "strategy.breakout.state", "strategy.cycle.collected",
                         "strategy.section.live", "strategy.entry_rules.state",
                         "strategy.exit_rules.state"],
            "decision": ["decision.aggregated.state", "decision.room.state",
                         "decision.signal_eval.state", "decision.score.state",
                         "decision.filter.state", "decision.buy.state",
                         "decision.sell.state", "decision.section.live"],
            "risk": ["risk.unified.state", "risk.account.state",
                     "risk.exposure.state", "risk.profit_limits.state",
                     "risk.session_limits.state", "risk.kill_switch.state",
                     "risk.halt.requested"],
            "execution": ["execution.order.submitted", "execution.order.filled",
                          "execution.order.built", "execution.order.rejected",
                          "execution.order.skipped", "execution.unified.state",
                          "execution.quality.state", "execution.desired.state",
                          "platform.trade_event.simulated", "sim.execution.state",
                          "platform.trade_event"],
        }
        for stage, events in monitors.items():
            for event_name in events:
                def monitor(payload, _stage=stage, _event=event_name):
                    self._stage_outputs[_stage].append({
                        "event": _event, "ts": time.time(),
                        "keys": list(payload.keys())[:10] if isinstance(payload, dict) else [],
                    })
                    if _stage == "decision" and _event == "decision.aggregated.state":
                        self._decisions.append(dict(payload) if isinstance(payload, dict) else {})
                self._bus.subscribe(event_name, monitor)

        # Bridge: decision → execution
        # When a decision is resolved, republish as trading.final_decision
        # لا نعيد نشر القرار كأمر حي. ٩٠١/٥٧٦/٦٠١ خارج المختبر والباك تست.
        # التنفيذ الورقي يملأ من decision.resolved عبر دفتر منفصل.

        def count_candle(payload):
            if isinstance(payload, dict):
                self._candle_count += 1
        self._bus.subscribe("market_data.candle_closed", count_candle)

    def _build_result(self, clock_report: dict | None = None) -> dict[str, Any]:
        """بناء نتيجة كاملة."""
        duration = self._finished_at - self._started_at if self._finished_at else 0
        return {
            "run_id": self._run_id,
            "status": "completed" if not self._error else "failed",
            "error": self._error,
            "started_at": self._started_at,
            "finished_at": self._finished_at,
            "duration_s": round(duration, 3),
            "tick_count": self._tick_count,
            "candle_count": self._candle_count,
            "atoms_loaded": len(self._loaded_atoms),
            "atom_ids": self.loaded_atom_ids,
            "bus_report": self._bus.report(),
            "clock_report": clock_report or {},
            "stages": {
                stage: {"count": len(outputs)}
                for stage, outputs in self._stage_outputs.items()
            },
            "decisions": {"count": len(self._decisions), "samples": self._decisions[:5]},
            "provenance": self._stream.provenance.to_dict() if self._stream and self._stream.provenance else {},
            "data_info": self._stream.to_dict() if self._stream else {},
        }


def _make_context(atom_id: int, config: dict, bus: SyncEventBus) -> Any:
    from core.contracts.atom import AtomContext

    async def async_publish(event_name: str, payload: dict) -> None:
        """غلاف async لـ bus.publish — الذرّة تنتظر await."""
        bus.publish(event_name, payload)

    return AtomContext(
        atom_id=atom_id, config=config, logger=create_logger(),
        publish=async_publish, subscribe=bus.subscribe,
        subscribe_all=bus.subscribe_all,
    )
