#!/usr/bin/env python3
"""
governance/scripts/run_core.py
=====================
نقطة التشغيل الفعلية لـ Core V1.0: تحميل الإعداد → تهيئة الخدمات
المشتركة → Bootloader.boot() → (اختياري) REST/WebSocket/Dashboard →
انتظار إشارة إيقاف → إيقاف نظيف للذرات بترتيب عكسي عن الإقلاع.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import threading
import time
from pathlib import Path

#: لحظة ولادة العمليّة — طلبُ إيقافٍ أقدم منها بقيّةُ نواةٍ سابقة لا يُطاع.
_PROCESS_STARTED_AT = time.time()

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) in sys.path:
    sys.path.remove(str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT))

from core import logger as core_logger  # noqa: E402
from core.bootloader import BootReport, Bootloader  # noqa: E402
from core.config import load_core_config  # noqa: E402
from core.contracts.atom import AtomState  # noqa: E402
from transport.owned_event_bus import OwnedEventBus  # noqa: E402
from core.health_manager import HealthManager  # noqa: E402
from core.hot_reload_service import HotReloadService  # noqa: E402
from core.journal import Journal  # noqa: E402
from core.lifecycle import call_lifecycle  # noqa: E402
from core.metrics import Metrics  # noqa: E402
from core.registry import Registry  # noqa: E402
from core.snapshot_engine import SnapshotEngine  # noqa: E402
from core.dependency_resolver import resolve  # noqa: E402


async def run(enable_api: bool | None, demo_seconds: float | None = None) -> int:
    configured_path = os.environ.get("QUANT_CORE_CONFIG")
    config_path = Path(configured_path) if configured_path else PROJECT_ROOT / "config" / "core.yaml"
    if not config_path.is_absolute():
        config_path = PROJECT_ROOT / config_path
    core_config = load_core_config(config_path)
    core_logger.configure(
        level=getattr(logging, str(core_config.get("log_level", "INFO")).upper(), logging.INFO),
        json_output=bool(core_config.get("log_json", True)),
    )
    log = logging.getLogger("quant_nq.core.bootstrap")

    # بند ٨ (٢٠٢٦-٠٩-٠٣): `QUANT_ATOMS_ROOT` كان «مفتاحًا بلا سلك» — يضبطه
    # scripts/run_forex.py:19 ولا يقرؤه أحد. صار المرجعَ الأوّل، والمانيفست
    # remains the default — so an un-launched checkout behaves byte-identically.
    _atoms_env = str(os.environ.get("QUANT_ATOMS_ROOT") or "").strip()
    if _atoms_env:
        _atoms = Path(_atoms_env)
        atoms_root = _atoms if _atoms.is_absolute() else PROJECT_ROOT / _atoms
    else:
        atoms_root = PROJECT_ROOT / core_config.get("atoms_root", "atoms")
    # مرسى حالة النواة (journal/snapshots) — مالك واحد shared/runtime_paths،
    # وقيمه الافتراضية = ``PROJECT_ROOT`` تمامًا كما كان قبل هذا القياس.
    try:
        if str(PROJECT_ROOT) not in sys.path:
            sys.path.insert(0, str(PROJECT_ROOT))
        from shared.runtime_paths import core_state_root
        state_root = core_state_root(code_root=PROJECT_ROOT,
                                     market=str(os.environ.get("QUANT_CORE_DOMAIN", "")).strip().lower())
    except Exception:  # noqa: BLE001 — نسخة بلا shared/ ⇒ السلوك التراثيّ حرفيًا
        state_root = PROJECT_ROOT

    # ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): الإغلاق النظيف لم يحدث ولا مرّة — 19
    # إقلاعًا منذ ٢٠٢٦-٠٩-٢٤ وصفر سطر «إشارة إيقاف مستلمة». النواة في نافذةٍ خاصّة
    # (`CREATE_NEW_CONSOLE`) وإشارة الكونسول لا تعبر إليها، فكان زرّ الإيقاف قتلًا
    # صلبًا دائمًا ولقطة الإيقاف لا تُكتب. الطريق الثاني: ملفّ طلبٍ تحت مرسى الحالة
    # (`<state_root>/control/core_stop.request.json`) يقرؤه خيطٌ كلّ ثانية من الآن —
    # لا يمرّ بالحلقة، ويُقرّ فورًا ولو كانت الحلقة عالقة أو الذرّات ما زالت تُقلع —
    # ثمّ يُوصَل بـ`_request_stop` نفسه بعد كتلة الإشارات (انظر `stop_watch.attach`)،
    # فيمرّ الإيقاف بالمسار الوحيد الذي يكتب اللقطات. كتلة الإشارات لم تُمسّ حرفًا
    # (مرساة `governance/checks/check_shutdown_contract.py`).
    stop_watch = _StopRequestWatch(Path(state_root) / "control", log=log)
    stop_watch.start()
    # A unified checkout runs Forex and Crypto with separate config files while
    # sharing the same frozen runtime code. The config is selected by the
    # wrapper through QUANT_CORE_CONFIG; default remains config/core.yaml.
    # ٢٠٢٦-٠٩-٠٣ (جولة ٢٠ · شقّ المسار، طبقة النواة): ``state_root`` هو **مرسى var**
    # نفسه (يُعيده ``core_state_root``)، فكانت قيمتا ``journal.path`` و
    # ``snapshot_root`` في ملفات الإعداد — وكلاهما يبدأ بـ``var/`` — تُلْصقان عليه
    # مرة ثانية: ``<runtime>/var/var/forex/…`` (قِيس: 3460 سطرًا في journal مكرَّر
    # وعشرات snapshot تحت ``forex_runtime/var/var``). والتقليم هنا لا يُنشئ فرعًا
    # ثانيا للحلّ: قيمة مطلقة تمرّ كما هي، ونسبيّة تُقرأ على مرسى حالة النواة.
    def _state_join(root: Path, raw: str) -> Path:
        p = Path(str(raw))
        if p.is_absolute():
            return p
        parts = p.parts
        if parts and parts[0] == "var":
            p = Path(*parts[1:]) if len(parts) > 1 else Path(".")
        return root / p

    registry = Registry()
    event_bus_cfg = core_config.get("event_bus") or {}
    # The production runner uses the first executable slice of Event Ownership:
    # one immutable payload is shared across read-only consumers instead of being
    # serialized once per subscriber.  Set payload_mode: isolated for a
    # compatibility rollback/debug run.
    payload_mode = str(event_bus_cfg.get("payload_mode", "shared_readonly"))
    # 0 (والافتراض) = اشتقاق من موارد الجهاز — §٨ تمنع رقمًا ثابتًا للمعالج،
    # و§٣٣ تمنع تثبيت عدد العمليات على الجهاز الحالي.
    worker_count = int(event_bus_cfg.get("worker_count", 0))
    mailbox_max_events = int(event_bus_cfg.get("mailbox_max_events", 1024))
    partitioned_ownership = bool(event_bus_cfg.get("partitioned_ownership", True))
    # ⛔ المسار البارد للمخازن (قرار المالك ٢٠٢٦-٠٩-١٠). المقيس: `707` حجب
    # مساره 2,230 مرّة بأسوأ 5.64 ث، و`712` نادى `VACUUM` داخل المعالج —
    # دورة 252 ثانية. العزل يمنع الحجب ولا يجعل المخزن أسرع.
    cold_sections = event_bus_cfg.get("cold_sections") or ()
    # §١٤ — تقسيم النطاق إلى مجموعات. ١ = بلا تقسيم وهو الافتراض، فغياب
    # المفتاح من الإعداد يعطي السلوك القديم حرفيًّا.
    scope_groups = int(event_bus_cfg.get("scope_groups", 1))
    # أحداث المال تُسمّى دائمًا حين تُسقَط — قائمةٌ لا تُقصّ (§٢٤).
    critical_prefixes = tuple(event_bus_cfg.get("critical_prefixes") or ())
    # ── NQ ENGINE (ورقة التنفيذ النهائية ٢٠٢٦-٠٩-١٧) ──────────────────────
    # محرّكٌ واحد بواجهة الناقل: المسار الساخن نداءٌ مباشر داخل دورة التِكّة،
    # والبارد (المخازن · اللوحة · القياس · المشترِكون العامّون) على الناقل
    # القديم بصناديقه. `core/` لا تُمَسّ: المحرّك يدخل من هنا وحده.
    engine_cfg = core_config.get("engine") or {}
    engine_enabled = bool(engine_cfg.get("enabled", False))
    if engine_enabled:
        from engine import NQEngine
        # نطاقات البارد في وضع المحرّك أوسع (القياس والمراقبة 800-949) — تُقرأ من
        # مفتاحها الخاصّ كي لا يتبدّل سلوك الناقل القديم إن أُطفئ المحرّك.
        cold_sections = event_bus_cfg.get("cold_sections_engine") or cold_sections
        cold_bus = OwnedEventBus(
            payload_mode=payload_mode,
            # مساران: صفر لا يُستعمل، وواحد بارد (`OwnershipRuntime` يحجز الأخير).
            worker_count=2,
            partitioned_ownership=False,
            mailbox_max_events=mailbox_max_events,
            cold_sections=cold_sections,
            scope_groups=1,
            critical_prefixes=critical_prefixes,
        )
        event_bus = NQEngine(
            cold_bus=cold_bus,
            cadence_sections=engine_cfg.get("cadence_sections") or ((150, 499),),
            cold_sections=cold_sections or ((700, 749),),
            never_coalesce_events=(engine_cfg.get("never_coalesce_events")
                                   or ("market_data.candle_closed",)),
            cold_bus_throttle_s=float(engine_cfg.get("cold_bus_throttle_s", 0.0)),
            cycle_deadline_s=float(engine_cfg.get("cycle_deadline_s", 5.0)),
            max_depth=int(engine_cfg.get("max_depth", 64)),
            max_events_per_cycle=int(engine_cfg.get("max_events_per_cycle", 50000)),
            every_backlog_alarm=int(engine_cfg.get("every_backlog_alarm", 2000)),
            cadence_min_interval_s=float(engine_cfg.get("cadence_min_interval_s", 0.0)),
            latency_stage_cap=int(engine_cfg.get("latency_stage_cap", 0)),
            latency_tick_events=tuple(engine_cfg.get("latency_tick_events") or ()),
            cutoff_mode=str(engine_cfg.get("cutoff_mode", "shadow")),
            cutoff_max_keys=int(engine_cfg.get("cutoff_max_keys", 200_000)),
            cutoff_max_hold_s=float(engine_cfg.get("cutoff_max_hold_s", 0.0)),
            hot_direct=bool(engine_cfg.get("hot_direct", True)),
            cutoff_probe_digits=tuple(engine_cfg.get("cutoff_probe_digits") or ()),
            cutoff_probe_sample=int(engine_cfg.get("cutoff_probe_sample", 1)),
        )
        log.info("أرضيّة الإيقاع: %.3f ث — التحليل لا يعيد الحساب مع كلّ تِكّة (صفر = السلوك السابق)",
                 float(engine_cfg.get("cadence_min_interval_s", 0.0)))
        log.info("القطع المبكّر: %s — ما لم تتغيّر قيمته لا يوقظ أحدًا (`shadow` يحكم ولا يمنع)",
                 str(engine_cfg.get("cutoff_mode", "shadow")))
        log.info("NQ ENGINE يعمل — إيقاع %s · بارد %s · مهلة الدورة %.1f ث",
                 engine_cfg.get("cadence_sections") or [[150, 499]],
                 list(cold_sections), float(engine_cfg.get("cycle_deadline_s", 5.0)))
    else:
        event_bus = OwnedEventBus(
            payload_mode=payload_mode,
            worker_count=worker_count,
            partitioned_ownership=partitioned_ownership,
            mailbox_max_events=mailbox_max_events,
            cold_sections=cold_sections,
            scope_groups=scope_groups,
            critical_prefixes=critical_prefixes,
        )
    # ورقة ٠٧ (فتحة V2.0): توريث الأثر صار **جوّا الناقل** نفسه
    # (event_bus.publish — ورقة ٠٤: trace_id + event_id + parent_event_id).
    # لا لزقة خارجية بعد اليوم؛ الوسيط trace_middleware.py أُبطِل (جذع مهجور لا يُستدعى). المُشغّل صار
    # «تشغيل + توصيل» فقط، بلا حقن منطق نواة.
    metrics = Metrics()
    journal_path = (core_config.get("journal") or {}).get("path")
    journal = Journal(path=_state_join(state_root, journal_path) if journal_path else None)
    health_manager = HealthManager(registry, event_bus, journal, metrics)
    snapshot_path = core_config.get("snapshot_root", "var/snapshots")
    snapshot_engine = SnapshotEngine(registry, _state_join(state_root, snapshot_path))

    # الأسرار تُهيّأ **قبل** الإقلاع: أول ما تفعله الذرة في
    # initialize() قد يكون طلب سرّها، فلا يجوز أن تجده فارغاً.
    _init_secret_provider(core_config, log)

    restored_at_boot: list[int] = []
    async def _restore_before_start(atom_id: int) -> None:
        if await snapshot_engine.restore_one(atom_id):
            restored_at_boot.append(atom_id)
    bootloader = Bootloader(
        atoms_root, registry, event_bus, journal, metrics, health_manager=health_manager,
        restore_hook=_restore_before_start,
    )

    # Core/Atom boundary: load the non-execution auto set first. The external
    # policy gate runs only after Bootloader has been reached; execution atoms
    # are admitted in a second generic Bootloader phase without changing their
    # manifests or startup_mode.
    from build_registry import BuildRegistry
    build_snapshot = BuildRegistry(PROJECT_ROOT).refresh()
    # ٢٠٢٦-٠٩-٠٧ (قرار المالك): سوق واحد. `QUANT_CORE_DOMAIN` يبقى مقروءًا
    # كي لا ينهار إعداد قائم يمرّره، لكنّ الشجرة واحدة — ولو ضُبط على
    # `crypto` لانهار السطر السابق على حقل لم يعد موجودًا.
    domain = "forex"
    domain_records = build_snapshot.forex_all
    auto_ids = {
        record.atom_id for record in domain_records
        if record.atom_id is not None and record.startup_mode == "auto"
    }
    scope = "forex"
    domain_records = tuple(record for record in domain_records if record.atom_id is not None)
    record_by_id = {record.atom_id: record for record in domain_records}
    execution_ids = {
        record.atom_id for record in build_snapshot.execution_targets
        if record.atom_id is not None and record.scope == scope and record.startup_mode == "auto"
    }
    # Defer the reverse dependency closure as well. A non-execution atom that
    # depends on a deferred execution participant must not start half-built.
    changed = True
    while changed:
        changed = False
        for record in domain_records:
            if record.atom_id in execution_ids or record.startup_mode != "auto":
                continue
            if any(dep_id in execution_ids for dep_id in record.dependencies):
                execution_ids.add(record.atom_id)
                changed = True
    non_execution_ids = auto_ids - execution_ids

    # ── المزرعة تقاعدت (NQ ENGINE · §٣٨ من ورقة المحرّك ٢٠٢٦-٠٩-١٧) ────────
    # كودها في `archive/experimental/farm/`. الحساب كلّه داخل المحرّك الواحد،
    # ولا ملكيّة ثانية للذرّة. إعدادٌ باقٍ باسمها يُتجاهَل بصوتٍ لا بصمت.
    if core_config.get("analysis_farm"):
        log.warning("إعداد `analysis_farm` موجود ويُتجاهَل: المزرعة تقاعدت — الحساب كلّه داخل NQ ENGINE")

    # ── المرحلة F — العمليّة الباردة (§٢١ من ورقة المحرّك) ────────────────────
    # المخازن والقياس والمراقبة تُقلع في مفسّرٍ مستقلّ له نواةٌ لنفسه، فلا تزاحم
    # دورة التِكّة على قفل المفسّر. تُستثنى من إقلاع النواة هنا ومن الفحص
    # الدوريّ (`hosted_elsewhere`)، فلا نسختين للذرّة الواحدة — والإقلاع يفشل
    # بصوتٍ إن تقاطعت المجموعتان.
    cold_cfg = (engine_cfg.get("cold_process") or {}) if engine_enabled else {}
    cold_process = None
    cold_ids: set[int] = set()
    if bool(cold_cfg.get("enabled", False)):
        from engine import ColdProcess

        def _in_ranges(number: int, ranges) -> bool:  # noqa: ANN001
            return any(int(low) <= number <= int(high) for low, high in ranges)

        cold_ranges = cold_cfg.get("sections") or event_bus_cfg.get("cold_sections_engine") or cold_sections
        cold_ids = {aid for aid in auto_ids if _in_ranges(int(aid), cold_ranges)}
        # استثناءٌ وإدراجٌ بالاسم من الإعداد: نبضة الوقت 806 تبقى في النواة
        # («الزمن لا يُنقل»)، والمراقب 001 (يرى كلّ حدث ولا يقرّر) يُرحَّل.
        cold_ids -= {int(v) for v in (cold_cfg.get("exclude") or ())}
        cold_ids |= {int(v) for v in (cold_cfg.get("include") or ()) if int(v) in auto_ids}
        overlap = cold_ids & execution_ids
        if overlap:
            # ذرّاتٌ يعدّها سجلّ البناء «مدى تنفيذ» (مخازن الأوامر والصفقات
            # 703/704/707/720 وبوّابة أوامر المالك 901) — تخزينٌ وقراءةُ أوامر لا
            # قرارُ تنفيذ. المقيس بـpy-spy 16:00: 707 وحدها ≈ ١٣٪ من معالج النواة
            # في sqlite. ما يُسمّيه الإعداد `allow_execution_scope` يُرحَّل إلى
            # العمليّة الباردة (§٢١: التخزين بارد) ويُسحب من مرحلة إقلاع التنفيذ؛
            # وما عداه يبقى في النواة بتحذير. المقيس 15:40: الإسقاط بدل الاستثناء
            # ترك المنصّة بلا نواة دقيقتين — لا يُعاد.
            allowed = {int(v) for v in (cold_cfg.get("allow_execution_scope") or ())}
            moved = overlap & allowed
            kept = overlap - allowed
            if kept:
                log.warning("ذرّاتٌ في مدى التنفيذ تبقى في النواة ولا تُرحَّل: %s", sorted(kept))
                cold_ids -= kept
            if moved:
                log.info("ذرّاتٌ في مدى التنفيذ تُرحَّل إلى العمليّة الباردة بإذن الإعداد: %s", sorted(moved))
                execution_ids -= moved
        non_execution_ids = non_execution_ids - cold_ids
    if bool(cold_cfg.get("enabled", False)) and not cold_ids:
        log.info("العمليّة الباردة: لا ذرّة auto في نطاقاتها على هذه الشجرة — لا تُقلع")
    if cold_ids:
        journal_cold = (Path(str(journal._path)).with_suffix(".cold.jsonl")
                        if getattr(journal, "_path", None) else None)
        cold_process = ColdProcess(
            atom_ids=cold_ids, atoms_root=str(atoms_root),
            snapshot_dir=str(_state_join(state_root, snapshot_path)),
            journal_path=str(journal_cold) if journal_cold else None,
            critical_prefixes=critical_prefixes,
            inbox_max=int(cold_cfg.get("inbox_max", 20000)),
            outbox_max=int(cold_cfg.get("outbox_max", 20000)),
            lanes=int(cold_cfg.get("lanes", 4)),
            log_level=str(core_config.get("log_level", "INFO")),
            log_json=bool(core_config.get("log_json", True)),
            # ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): ثلاث إعادات خلال عشر دقائق ثمّ
            # تُترك ساقطةً بصوت (`/api/health = unhealthy`) — لا دوّامة إقلاع.
            restart_max=int(cold_cfg.get("restart_max", 3)),
            restart_window_s=float(cold_cfg.get("restart_window_s", 600.0)),
        )
        cold_process.spawn()
        cold_process.start_flusher()
        event_bus.cold_process = cold_process
        event_bus.cold_sink = cold_process.send
        log.info("العمليّة الباردة تُقلع: %d ذرّة (%s) — pid %s",
                 len(cold_ids), cold_ranges, cold_process.stats().get("pid"))

    # ── النواة الموزّعة: محرّكٌ لكلّ مجموعة رموز ─────────────────────────────
    # المقيس ٢٠٢٦-٠٩-١٧: الجهاز 12 خيطًا ونصفه فارغ، ونواة التداول مشبعة عند
    # 104٪ من **خيطٍ واحد**؛ والتِكّات 120/ث بينما النظام يولّد 2,551 حدثًا/ث.
    # فالمسار الساخن يُقسَم بالرمز — لا بالحدث (درس المزرعة) ولا بالطبقة.
    sym_cfg = (engine_cfg.get("symbol_engines") or {}) if engine_enabled else {}
    symbol_engines: list = []
    symbol_router = None
    symbol_ids: set[int] = set()
    if bool(sym_cfg.get("enabled", False)):
        from engine import SymbolEngine, SymbolRouter

        def _in_ranges2(number: int, ranges) -> bool:  # noqa: ANN001
            return any(int(low) <= number <= int(high) for low, high in ranges)

        sym_ranges = sym_cfg.get("sections") or ((100, 599),)
        excluded_ids = {int(v) for v in (sym_cfg.get("exclude") or ())}
        symbol_ids = {aid for aid in auto_ids
                      if _in_ranges2(int(aid), sym_ranges) and int(aid) not in excluded_ids}
        symbol_ids -= cold_ids
        if not symbol_ids:
            log.error("النواة الموزّعة: لا ذرّة في نطاقاتها — لا تُقلع محرّكات")
        else:
            groups = int(sym_cfg.get("groups", 0)) or max(2, (os.cpu_count() or 2) // 2 - 1)
            declared = [list(g) for g in (sym_cfg.get("symbol_groups") or [])]
            non_execution_ids = non_execution_ids - symbol_ids
            execution_ids = execution_ids - symbol_ids
            # ضبط الساعة يُقرأ من مانيفست 003 نفسها — لا رقمٌ مكرّر في مكانين.
            clock_config: dict = {}
            try:
                import yaml as _yaml
                for _m in Path(atoms_root).rglob("manifest.yaml"):
                    _d = _yaml.safe_load(_m.read_text(encoding="utf-8")) or {}
                    if int(_d.get("id") or 0) == 3:
                        clock_config = dict(_d.get("config") or {})
                        break
            except Exception as exc:  # noqa: BLE001
                log.error("تعذّرت قراءة ضبط الساعة من مانيفست 003: %s", exc)
            if not clock_config:
                log.critical("⛔ لم يُقرأ ضبط الساعة — محرّكات الرموز سترفض الأوامر بـCLOCK_NOT_SYNCED")

            child_env = {k: os.environ[k] for k in
                         ("QUANT_ATOMS_ROOT", "QUANT_RUNTIME_ROOT", "QUANT_CORE_STATE_ROOT",
                          "QUANT_CORE_DOMAIN", "QUANT_ANALYSIS_SETTINGS_DB", "QUANT_CORE_CONFIG",
                          "QUANT_LOCAL_MODE", "NQ_NEWS_DB", "NQ_BRIDGE_DB")
                         if k in os.environ}
            snap_root = _state_join(state_root, snapshot_path)
            for index in range(groups):
                name = "sym%d" % index
                symbol_engines.append(SymbolEngine(
                    group=name,
                    symbols=declared[index] if index < len(declared) else (),
                    atom_ids=symbol_ids, atoms_root=str(atoms_root),
                    snapshot_dir=str(Path(snap_root) / name),
                    journal_path=None, env=child_env,
                    cadence_sections=engine_cfg.get("cadence_sections") or ((150, 499),),
                    cutoff_mode=str(engine_cfg.get("cutoff_mode", "shadow")),
                    cutoff_max_hold_s=float(engine_cfg.get("cutoff_max_hold_s", 0.0)),
                    hot_direct=bool(engine_cfg.get("hot_direct", True)),
                    cadence_min_interval_s=float(engine_cfg.get("cadence_min_interval_s", 0.0)),
                    latency_stage_cap=int(engine_cfg.get("latency_stage_cap", 0)),
                    latency_tick_events=tuple(engine_cfg.get("latency_tick_events") or ()),
                    clock_config=clock_config,
                    cutoff_probe_digits=tuple(engine_cfg.get("cutoff_probe_digits") or ()),
                    cutoff_probe_sample=int(engine_cfg.get("cutoff_probe_sample", 1)),
                    cycle_deadline_s=float(engine_cfg.get("cycle_deadline_s", 5.0)),
                    max_depth=int(engine_cfg.get("max_depth", 64)),
                    inbox_max=int(sym_cfg.get("inbox_max", 2000)),
                    outbox_max=int(sym_cfg.get("outbox_max", 20000)),
                    log_level=str(core_config.get("log_level", "INFO")),
                    log_json=bool(core_config.get("log_json", True))))
            symbol_router = SymbolRouter(
                symbol_engines,
                broadcast_prefixes=tuple(sym_cfg.get("broadcast_prefixes") or ()))
            event_bus.symbol_router = symbol_router
            for eng in symbol_engines:
                eng.spawn()
            log.info("النواة الموزّعة: %d محرّك × %d ذرّة — %s",
                     len(symbol_engines), len(symbol_ids),
                     [e.stats().get("pid") for e in symbol_engines])

    log.info("بدء مرحلة Core/Atom غير التنفيذية من %s", atoms_root)
    base_report = await bootloader.boot(include_ids=non_execution_ids)
    _log_report(log, base_report, prefix="انتهت مرحلة Core/Atom")

    execution_report = None
    refused_execution_ids: set[int] = set()
    safety = _verify_execution_safety_at_startup()
    if execution_ids and safety == 0:
        log.info("بوابة execution نجحت بعد Core Boot؛ بدء أهداف التنفيذ المكتشفة")
        execution_report = await bootloader.boot(include_ids=execution_ids)
        _log_report(log, execution_report, prefix="انتهت مرحلة execution")
    elif execution_ids:
        log.error("execution محجوب بعد إقلاع Core؛ لن تبدأ أهداف التنفيذ")
        # ٢٠٢٦-٠٩-٢٣: الحجب هنا كان يُترك بلا أثر عند خدمة التحميل الحارّ،
        # فتراها «مكتشَفةً غير مسجّلة» وتُقلعها بعد سبعين ثانية — فتداولت
        # المنصّة عبر مسارٍ رُفض. القرار قرارُ المُقلِع، فيُمرَّر معه.
        refused_execution_ids = set(execution_ids)

    report = _merge_boot_reports(base_report, execution_report)
    _log_report(log, report)
    symbol_pumps: list = []
    if symbol_engines:
        for eng in symbol_engines:
            eng.start_flusher()
            # ثلاث مضخّات لثلاثة صناديق فيزيائيّة (عقد الخروج ٢٠٢٦-٠٩-١٧):
            # المال أوّلًا بمهلةٍ قصيرة، والتخزين والعرض بمهلةٍ أطول — فلا ينتظر
            # حدثُ مالٍ خلف تسعة عشر ألف حدث عرض (المقيس: 32.1 ث وسيطًا).
            for label, coro in (("money", eng.pump_outbound), ("storage", eng.pump_storage),
                                ("obs", eng.pump_observation)):
                symbol_pumps.append(asyncio.create_task(
                    coro(event_bus.publish, mark_inbound=event_bus.mark_router_inbound),
                    name="nq-symbol-%s-%s" % (label, eng.group)))
        for eng in symbol_engines:
            try:
                rep_sym = await eng.wait_booted(timeout_s=float(sym_cfg.get("boot_timeout_s", 300.0)))
                # ── آخر عيّنة ساعةٍ فورًا ──────────────────────────────
                # ── ترطيب الحالة ──────────────────────────────────────
                # عمليّةٌ تُقلع متأخّرةً لا تعرف شيئًا عمّا مضى، فتحكم على
                # عالمٍ فارغ. المقيس ٢٠٢٦-٠٩-١٨: عيّنة NTP لم تصلها فرُفض
                # كلّ أمر بـCLOCK_NOT_SYNCED، و`platform.terminal_state`
                # لم تصلها (لا نقطة قبل `state` فليست قابلة للإعادة) فبقيت
                # `_alive` فارغةً في الذرّة 519 ⟵ system_alive=False ⟵
                # 171 حجبًا بـSYSTEM_NOT_ALIVE.
                #
                # فتُسلَّم صورةُ العالم كاملةً عند الإقلاع: آخر حمولةٍ لكلّ
                # حدثٍ عبر الحدّ، بلا أوامر (الحدّ من `_is_command`).
                try:
                    world = event_bus.world_snapshot()
                except Exception as exc:  # noqa: BLE001
                    world = []
                    log.error("تعذّرت صورة العالم لمحرّك %s: %s", eng.group, exc)
                for _name, _body in world:
                    eng.send(_name, _body)
                eng.flush()
                _clock_in = any(n == "time.ntp.samples.state" for n, _ in world)
                log.info("محرّك %s أخذ صورة العالم عند الإقلاع: %d حدثًا · عيّنة الساعة %s",
                         eng.group, len(world), "نعم" if _clock_in else "لا")
                if not _clock_in:
                    log.warning("محرّك %s بلا عيّنة ساعة — سيرفض الأوامر حتّى تصل التالية",
                                eng.group)

                log.info("محرّك %s أقلع: %d ذرّة خلال %s ث · فشل %s · رموز %s",
                         eng.group, len(rep_sym.get("loaded") or []), rep_sym.get("boot_s"),
                         rep_sym.get("failed"), rep_sym.get("symbols") or "بالورود")
                if rep_sym.get("failed"):
                    log.error("ذرّات فشلت في محرّك %s: %s", eng.group, rep_sym.get("failed_reasons"))
            except Exception as exc:  # noqa: BLE001
                # محرّكٌ لا يُقلع = رموزه بلا تحليل. يُعلَن ولا يُسقط النواة،
                # ولا يبقى في الموجّه فيبتلع تِكّاتٍ لا تُعالَج.
                log.critical("تعذّر إقلاع محرّك %s (%s) — يُسحب من التوجيه", eng.group, exc, exc_info=True)
                if symbol_router is not None and eng in symbol_router.engines:
                    symbol_router.engines.remove(eng)
        if symbol_router is not None and not symbol_router.engines:
            log.critical("لا محرّك رموزٍ واحد أقلع — التوجيه يُلغى والنواة تكمل بمحرّكها وحده")
            event_bus.symbol_router = None

    cold_pump_task = None
    cold_boot_task = None
    if cold_process is not None:
        # لا نجعل إقلاع المسار البارد بوابةً لإقلاع Core.
        # كان wait_booted ينتظر حتى 180 ثانية قبل أن يصل التشغيل إلى API،
        # بينما التداول نفسه كان قد اكتمل. المسار البارد يجب أن يتأخر وحده.
        async def _finish_cold_boot() -> None:
            nonlocal cold_process, cold_pump_task
            try:
                cold_report = await cold_process.wait_booted(
                    timeout_s=float(cold_cfg.get("boot_timeout_s", 180.0))
                )
                loaded = set(cold_report.get("loaded") or [])
                dup = loaded & {int(r.id) for r in registry.all()}
                if dup:
                    raise RuntimeError(
                        "ذرّات مُقلَعة في النواة وفي العمليّة الباردة معًا: %s"
                        % sorted(dup)
                    )
                log.info(
                    "العمليّة الباردة أقلعت في الخلفية: %d ذرّة خلال %s ث · فشل %s",
                    len(loaded), cold_report.get("boot_s"), cold_report.get("failed")
                )
                if cold_report.get("failed"):
                    log.error(
                        "ذرّات باردة فشل إقلاعها: %s",
                        cold_report.get("failed_reasons")
                    )
                # ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): كان موتها سطر CRITICAL يتكرّر
                # كلّ ثانية بلا نهاية، بلا إعادة إقلاع، و`/api/health` يبقى `ok` —
                # وفيها 901 بوّابة أوامر المالك (الإيقاف الطارئ). الآن: يُسمّى الموت
                # برمز خروجه، وتُعاد الابنة حتى `restart_max` خلال `restart_window_s`،
                # ثمّ تُترك ساقطةً والصحّة `unhealthy` مع تذكيرٍ كلّ دقيقة.
                cold_down_said = {"at": 0.0}

                async def _cold_died() -> None:
                    proc = cold_process
                    if proc is None:
                        return
                    exit_code = proc.exit_code()
                    outcome = proc.restart_after_death()
                    if outcome == "restarted":
                        log.error(
                            "⛔ العمليّة الباردة ماتت (رمز الخروج %s) — المخازن والقياس "
                            "وبوّابة أوامر المالك متوقّفة؛ إعادة إقلاع %d من %d خلال %.0f د",
                            exit_code, proc.restarts_in_window(), proc.restart_max,
                            proc.restart_window_s / 60.0)
                        event_bus.cold_sink = proc.send
                        log.warning("العمليّة الباردة أُعيد إقلاعها — pid %s (تنتظر تقرير إقلاعها)",
                                    proc.stats().get("pid"))
                    elif outcome == "exhausted":
                        event_bus.cold_sink = None
                        cold_down_said["at"] = time.monotonic()
                        log.critical(
                            "⛔ العمليّة الباردة ماتت (رمز الخروج %s) ونفدت إعادات الإقلاع "
                            "(%d خلال %.0f د) — تُترك ساقطة: المخازن والقياس وبوّابة أوامر "
                            "المالك متوقّفة حتى إعادة إقلاع المنصّة · /api/health = unhealthy",
                            exit_code, proc.restart_max, proc.restart_window_s / 60.0)
                    elif outcome == "down":
                        event_bus.cold_sink = None
                        if time.monotonic() - cold_down_said["at"] >= 60.0:
                            cold_down_said["at"] = time.monotonic()
                            log.critical("⛔ العمليّة الباردة ما زالت ساقطة (رمز الخروج %s) — "
                                         "المخازن وبوّابة أوامر المالك متوقّفة", exit_code)
                cold_pump_task = asyncio.create_task(
                    cold_process.pump_outbound(
                        event_bus.publish,
                        mark_inbound=event_bus.mark_cold_inbound,
                        on_dead=_cold_died,
                    ),
                    name="nq-cold-pump",
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.critical(
                    "تعذّر إقلاع العمليّة الباردة في الخلفية (%s) — "
                    "النواة تكمل بلا مخازن ولا قياس",
                    exc,
                    exc_info=True,
                )
                event_bus.cold_sink = None
                try:
                    await cold_process.stop(timeout_s=10.0)
                except Exception:
                    pass
                cold_process = None
                event_bus.cold_process = None

        cold_boot_task = asyncio.create_task(
            _finish_cold_boot(), name="nq-cold-boot"
        )
        log.info(
            "Core جاهز للمسار الساخن؛ إقلاع العمليّة الباردة مستمرّ بالخلفية "
            "(timeout=%.0f ث)",
            float(cold_cfg.get("boot_timeout_s", 180.0)),
        )
    # ── خريطة الخروج — تُشتقّ من رسم المستهلكين لا من قائمة أسماء ──────────
    # عقد المالك: «العبور يُشتق من الـconsumer graph، وليس من اسم الحدث».
    #   مالٌ    = لحدثه مستهلكٌ **فاعل** في الجذر (الجسر 601 · المحفظة ·
    #             العابرات · التنفيذ) — يمرّ فورًا بلا فقد ولا دمج.
    #   تخزينٌ  = تستهلكه مخازن العمليّة الباردة وحدها — كاملٌ بأولويّة دنيا.
    #   عرضٌ    = ما لا مستهلك فاعل له — يُدمج بالأحدث لكلّ (اسم، رمز).
    if symbol_engines and symbol_router is not None:
        try:
            # ٢٠٢٦-٠٩-١٨ — الاشتقاق صار **متعدّيًا** بقاعدة المالك: «هل يوجد
            # downstream consumer يؤثّر على تنفيذ/أمر المال؟». الاشتقاق المباشر
            # (ما يقرؤه الجذر) صنّف 80 حدثًا مالًا فقط، فوقعت `structure.*`
            # و`liquidity.*` خارج المال بينما سلسلة التنفيذ تنتظرها — ودفعت
            # مهلة البارد: 0.6654 ث لحدثٍ ينهيه المحرّك في 0.0280 (مقيس بالشلّال).
            # والمصبّات من تصنيف النواة المختومة (`_is_command`) لا من قائمة.
            from engine.egress_graph import classify as _classify_egress

            hot_names = set(event_bus.graph.event_names())
            hot_names |= {str(n) for n in event_bus._cold.event_names()}
            cold_names = ({str(n) for n in cold_process.specific_events}
                          if cold_process is not None
                          and getattr(cold_process, "specific_events", None) else set())
            from engine.egress_graph import published_by as _published_by

            produced_here = _published_by(atoms_root, symbol_ids)
            egress = _classify_egress(atoms_root, hot_events=hot_names,
                                      cold_events=cold_names,
                                      produced_here=produced_here,
                                      # البادئات من المسبار الحيّ نفسه — عقدُه
                                      # المُعلَن، لا قائمةٌ تُكتب هنا.
                                      keep_visible=(tuple(event_bus.latency.tick_prefixes)
                                                    + tuple(event_bus.latency.decision_prefixes)),
                                      # المُغلِقات وحدها تحتاج العجلة — الفاتح
                                      # يُنشَر في الجذر ولا يعبر حدًّا.
                                      urgent_markers=tuple(
                                          event_bus.latency.decision_prefixes))
            money_names = egress["money"]
            storage_names = egress["storage"]
            internal_names = egress["internal"]
            log.info("اشتقاق الخروج: %d اسمًا · %d حافّة · %d مصبًّا ⟵ مال %d · تخزين %d · "
                     "داخليّ %d من %d يُنتَج هنا (مباشر %d)",
                     egress["names"], egress["edges"], egress["sinks"],
                     len(money_names), len(storage_names), len(internal_names),
                     len(produced_here), len(hot_names))
            if internal_names:
                log.info("لا يعبر الحدّ (داخليّ): %s",
                         ", ".join(sorted(internal_names)[:20]))
            for eng in symbol_engines:
                eng.send_classification(money_names, storage_names, internal_names)
            log.info("خريطة الخروج أُرسلت إلى %d محرّك: مال %d · تخزين %d · داخليّ %d · الباقي عرض",
                     len(symbol_engines), len(money_names), len(storage_names),
                     len(internal_names))

            # ── ترطيبٌ ثانٍ ─────────────────────────────────────────────
            # الترطيب الأوّل يقع عند `wait_booted` — قبل إقلاع ذرّات الجذر،
            # فحالتها لم تكن قد وُلدت بعد. المقيس ٢٠٢٦-٠٩-١٨: الصورة الأولى
            # حملت 21–36 حدثًا وبقي `SYSTEM_NOT_ALIVE` عند 162 لأنّ
            # `platform.terminal_state` تُنشَر بعدها. فتُعاد الصورة هنا —
            # بعد أن أقلع كلّ شيء — والأحدث يحلّ محلّ الأقدم عند المستهلك.
            try:
                world2 = event_bus.world_snapshot()
            except Exception as exc:  # noqa: BLE001
                world2 = []
                log.error("تعذّر الترطيب الثاني: %s", exc)
            if world2:
                for eng in symbol_engines:
                    for _name, _body in world2:
                        eng.send(_name, _body)
                    eng.flush()
                log.info("ترطيبٌ ثانٍ بعد إقلاع الجذر: %d حدثًا إلى %d محرّك · "
                         "حالة الطرفيّة %s", len(world2), len(symbol_engines),
                         "نعم" if any(n == "platform.terminal_state" for n, _ in world2)
                         else "لا (ستصل حيّةً)")
        except Exception as exc:  # noqa: BLE001
            # بلا خريطة يبقى كلّ شيء **مالًا** — أبطأ، ولا يفقد حدثًا.
            log.error("تعذّر اشتقاق خريطة الخروج (%s) — المحرّكات تعيد كلّ شيء كمالٍ", exc, exc_info=True)

    if engine_enabled:
        event_bus.start_display_flusher()
        # ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): سجلّ المحرّك يصل 719 في العمليّة الباردة.
        from engine.process_logs import install_log_relay
        install_log_relay(event_bus)
        # الرسم يُختم بعد الإقلاع: ما يُنشر بعده من خارج الرسم يُعدّ بالاسم.
        seal_report = event_bus.seal()
        log.info("NQ ENGINE — الرسم مختوم: %d حدثًا · %d اشتراكًا ساخنًا (%d بإيقاع) · دورات %d",
                 seal_report.get("events", 0), seal_report.get("subscriptions", 0),
                 seal_report.get("cadence_subscriptions", 0), len(seal_report.get("cycles") or []))
    if not report.success:
        log.critical(
            "فشلت ذرة/ذرات حرجة أثناء إقلاع Atom: %s — Core يستمر بالعمل.",
            report.abort_reason,
        )

    if restored_at_boot:
        log.info("استُعيدت الحالة قبل start: %s", restored_at_boot)


    discovery_cfg = core_config.get("discovery") or {}
    rescan_interval_s = float(discovery_cfg.get("rescan_interval_s", 5.0))
    # ⛔ **المستضافون لا يُقلَعون هنا** — وبلا تمريرهم يعيد الفحص الدوريّ
    #    إقلاعهم بعد خمس ثوانٍ فتصير للذرّة نسختان. المقيس ٢٠٢٦-٠٩-١٧:
    #    مُقلَع 226 + مستضاف 84 = 310 من 235 مانيفستًا ⟶ ٧٥ في مكانين.
    #    ولا يُستبعَد شيء إن لم تعمل المزرعة فعلًا.
    # 🔴 **مُعطَّل ٢٠٢٦-٠٩-١٧ بعد قياسٍ حيّ — والسبب يُكتب لا يُخفى.**
    #
    # منعُ الفحص الدوريّ من إعادة إقلاع المستضافين **صحيحٌ نظريًّا**
    # (٧٥ ذرّة كانت تعمل في مكانين)، وأزال الازدواج فعلًا:
    #
    #     مُقلَع 226 ⟶ 142   ·   الطوابير ⟶ صفر   ·   فقد السوق ⟶ صفر
    #
    # ⛔ **لكنّه قتل سلسلة القرار.** المقيس بعد الإقلاع مباشرةً:
    #
    #     decision.scored / filtered / approved / dispatch  =  صفر
    #     analysis.cycle.collected                          =  صفر
    #     والمنصّة حيّة: 466 حدثًا/ث وسبعة رموز نشطة
    #
    # والسبب: **المزرعة بابُها `candle_closed` وحده**، فالمستضافون لا
    # يرون التِكّة. والقرار بإيقاع التِكّة لا الشمعة (مقيس ١٤٦٬٣٧٨ مقابل
    # ٥٢). فالنسخة المركزيّة لم تكن هدرًا خالصًا — كانت **تحمل مسار
    # التِكّة كلّه**، والنسخة المستضافة تحمل مسار الشمعة.
    #
    # ⟹ فالازدواج عَرَضٌ لا مرض: المرض أنّ الاستضافة **جزئيّة بالحدث**.
    #   ولا يُزال قبل أن ترى المزرعة التِكّة — وذلك هو المرحلة G نفسها.
    #
    # والقدرة باقية في `HotReloadService` (Core 1.34.0) وخاملةٌ هنا:
    # قائمةٌ فارغة تعطي السلوك السابق حرفًا.
    hosted_elsewhere: set[int] = set(cold_ids) | set(symbol_ids)
    hot_reload = HotReloadService(atoms_root, registry, event_bus, health_manager,
                                  journal=journal, snapshot_engine=snapshot_engine,
                                  hosted_elsewhere=hosted_elsewhere,
                                  refused_ids=refused_execution_ids)
    hot_reload.register()
    await hot_reload.start_periodic(interval_s=rescan_interval_s)
    if hosted_elsewhere:
        log.info("الاكتشاف الدوريّ يستثني %d ذرّة مستضافة في عمليّات — "
                 "لا نسختين للذرّة الواحدة", len(hosted_elsewhere))
    log.info(
        "Runtime Discovery Engine مُفعَّلة — فحص تلقائي كل %.1f ثانية، "
        "+ POST /api/rescan لتفعيل فوري يدوي عند الحاجة",
        rescan_interval_s,
    )

    latest_report_box: dict[str, BootReport] = {"report": report}

    api_cfg = core_config.get("api") or {}
    use_api = enable_api if enable_api is not None else bool(api_cfg.get("enable_api", True))
    server = None
    server_task = None
    if use_api:
        server, server_task = _start_api(
            registry, event_bus, metrics, journal, latest_report_box, api_cfg, log,
            health_manager=health_manager,
            control_event_publisher=_build_control_event_publisher(event_bus, log),
        )
        await asyncio.sleep(0.2)
        if server_task.done():
            server, server_task = None, None

    stop_event = asyncio.Event()

    def _request_stop(*_args: object) -> None:
        log.info("إشارة إيقاف مستلمة")
        stop_event.set()

    loop = asyncio.get_running_loop()
    installed_signals: list[int] = []
    restore_handlers: dict = {}
    import signal
    _SIGNALS = tuple(s for s in (getattr(signal, name, None)
                                 for name in ("SIGINT", "SIGTERM", "SIGBREAK")) if s is not None)
    try:
        for sig in _SIGNALS:
            loop.add_signal_handler(sig, _request_stop)
            installed_signals.append(sig)
    except (NotImplementedError, ImportError, RuntimeError):
        # ويندوز: ProactorEventLoop يرفض add_signal_handler لكل الإشارات، فكانت
        # stop_event لا تُضبط أبدًا، و`await stop_event.wait()` لا يرجع، فلا
        # يُنفَّذ snapshot_all ولا مرّة (var\snapshots = صفر ملفّ). المسار
        # البديل يبلغ **نفس** stop_event عبر signal.signal — فيبقى snapshot_all
        # هو الطريق الوحيد للحفظ، ولا يُضاف طريق ثانٍ.
        for sig in installed_signals:
            try:
                loop.remove_signal_handler(sig)
            except (NotImplementedError, RuntimeError):
                pass
        installed_signals.clear()

        def _request_stop_threadsafe(_signum: int, _frame: object) -> None:
            loop.call_soon_threadsafe(_request_stop)

        for sig in _SIGNALS:
            try:
                restore_handlers[sig] = signal.signal(sig, _request_stop_threadsafe)
            except (ValueError, OSError, RuntimeError):
                continue
        log.info("مقابض الإيقاف عبر signal.signal (مسار ويندوز): %s",
                 [getattr(s, "name", s) for s in restore_handlers])

    # مقبض signal.signal لا يُنفَّذ إلا حين تصحو الحلقة، وProactor قد ينام
    # طويلًا على انتظار خالص. نبضة قصيرة تضمن أن الإشارة تُنفَّذ فورًا.
    async def _signal_pump() -> None:
        while not stop_event.is_set():
            await asyncio.sleep(0.2)

    pump = asyncio.create_task(_signal_pump()) if restore_handlers else None

    # finding 06: لقطة دوريّة كخطّ ثانٍ — لو انقطع التيار أو قُتلت العمليّة
    # فجأةً، تبقى آخر لقطة دوريّة (لا تعتمد على الإيقاف النظيف وحده).
    # قابلة للضبط من الإعداد (`snapshot.interval_s`) — الافتراض 60 كما كان.
    _PERIODIC_SNAPSHOT_INTERVAL_S = float((core_config.get("snapshot") or {}).get("interval_s", 60.0))
    async def _periodic_snapshot() -> None:
        if snapshot_engine is None:
            return
        while not stop_event.is_set():
            await asyncio.sleep(_PERIODIC_SNAPSHOT_INTERVAL_S)
            if stop_event.is_set():
                break
            try:
                report = await snapshot_engine.snapshot_all()
                if report.captured:
                    log.debug("لقطة دوريّة: %s ذرّة", len(report.captured))
            except Exception as exc:  # noqa: BLE001
                log.warning("فشل اللقطة الدوريّة: %s", exc)

    periodic_snap = asyncio.create_task(_periodic_snapshot())

    # ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): طلب الإيقاف من ملفّ التحكّم يدخل من
    # الباب نفسه الذي تدخل منه الإشارة — `_request_stop` ⟵ `stop_event` — ولو وصل
    # أثناء الإقلاع فقد أُقرّ هناك ويُنفَّذ هنا فورًا.
    def _stop_from_file(source: str) -> None:
        log.info("طلب إيقاف من ملفّ التحكّم (%s) — الإغلاق النظيف يبدأ", source)
        _request_stop()

    stop_watch.attach(lambda source: loop.call_soon_threadsafe(_stop_from_file, source))

    # ── GATE 1: مرجع تكافؤ القرار (ختم `nq` ٢٠٢٦-٠٩-١٨) ─────────────────
    # يُركَّب بـ`NQ_PARITY=<مسار>` وحده، ومطفأٌ بلا كلفةٍ بدونه. يركب على
    # `subscribe_all` فيُحوَّل إلى **البارد** حتمًا (§١٦)، فكلفته على مسار
    # التِكّة صفر بالبناء لا بالاتّفاق. والتصريف من مهمّةٍ مملوكة (ق١٣):
    # حاوية + `add_done_callback` + إلغاءٌ عند الإيقاف.
    parity = None
    parity_task = None
    try:
        from hot.parity import install as _install_parity
        parity = _install_parity(
            event_bus,
            runtime=os.environ.get("NQ_PARITY_RUNTIME", "legacy"))
    except Exception as exc:  # noqa: BLE001
        log.warning("تعذّر تركيب مرجع التكافؤ: %s", exc)
    if parity is not None:
        _parity_tasks: set = set()

        async def _parity_flush() -> None:
            while not stop_event.is_set():
                await asyncio.sleep(1.0)
                try:
                    await asyncio.to_thread(parity.flush)
                except Exception as exc:  # noqa: BLE001
                    log.warning("تصريف مرجع التكافؤ: %s", exc)

        parity_task = asyncio.create_task(_parity_flush())
        _parity_tasks.add(parity_task)
        parity_task.add_done_callback(_parity_tasks.discard)
        log.warning("GATE 1 — مرجع التكافؤ يسجّل إلى %s (زمنُ تشغيل: %s)",
                    parity.path, parity.runtime)

    # ── مِرقاب تجمّد الحلقة ───────────────────────────────────────────────
    # يُفتح بمتغيّر بيئة وحده (`NQ_LOOP_WATCH=0.06`)، فهو مطفأٌ بلا كلفة في
    # التشغيل العاديّ. المقيس ٢٠٢٦-٠٩-١٨: ٩٢٪ من زمن أسوأ أثرٍ في خطوتين من
    # سبعٍ وستّين، وبعد كلّ واحدةٍ تنفجر عشرات الأحداث في ١٥ م.ث — شكلُ
    # تجمّدٍ ثمّ لحاق. وهذا يسمّي السطر الحاجب بمكدّسه.
    loop_watch = None
    _watch_s = os.environ.get("NQ_LOOP_WATCH", "")
    if _watch_s:
        from engine.loop_watchdog import LoopWatchdog
        loop_watch = LoopWatchdog(
            stall_s=float(_watch_s),
            mode=os.environ.get("NQ_LOOP_WATCH_MODE", "stall"),
            path=os.environ.get("NQ_LOOP_WATCH_OUT",
                                str(Path.cwd() / "forex_runtime" / "var" / "loop_stalls.txt")))
        loop_watch.start()
        setattr(event_bus, "loop_watchdog", loop_watch)

        async def _heartbeat() -> None:
            while not stop_event.is_set():
                loop_watch.heartbeat()
                await asyncio.sleep(0.002)

        watch_task = asyncio.create_task(_heartbeat())
        log.warning("مِرقاب التجمّد يعمل — عتبة %.3f ث", loop_watch.stall_s)

    # Item 64: a bounded foreground run. The flag existed, the canonical script
    # had lost it, and the only two tests that run the core as a real process
    # were killed by `unrecognized arguments: --demo-seconds` -- which read from
    # the outside as "the core did not boot". It stops through the SAME
    # stop_event, so the clean-shutdown snapshot path is not bypassed.
    if demo_seconds is not None and demo_seconds > 0:
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=demo_seconds)
        except asyncio.TimeoutError:
            log.info("انتهت المدّة المحدودة (%.0fs) — إيقاف نظيف", demo_seconds)
            stop_event.set()
    else:
        await stop_event.wait()
    if pump is not None:
        pump.cancel()
    periodic_snap.cancel()

    log.info("إيقاف نظيف لكل الذرات (بترتيب عكسي عن الإقلاع والاعتماديات حياً)...")
    # يجب أن يتوقف الاكتشاف الحي أولًا: لقطة تُلتقط بينما يُحمَّل محرك
    # الاكتشاف ذرة جديدة تعني لقطة لحالة متغيّرة تحت أقدامنا.
    await hot_reload.stop_periodic()
    for pump in symbol_pumps:
        pump.cancel()
    for pump in symbol_pumps:
        try:
            await pump
        except (asyncio.CancelledError, Exception):  # noqa: BLE001
            pass
    if symbol_engines:
        event_bus.symbol_router = None
        for eng in symbol_engines:
            log.info("إيقاف محرّك %s: %s", eng.group,
                     {k: v for k, v in eng.stats().items()
                      if k in ("symbols", "sent", "send_dropped", "returned")})
            try:
                await eng.stop(timeout_s=float(sym_cfg.get("stop_timeout_s", 60.0)))
            except Exception as exc:  # noqa: BLE001
                log.error("فشل إيقاف محرّك %s: %s", eng.group, exc)

    if cold_boot_task is not None:
        cold_boot_task.cancel()
        try:
            await cold_boot_task
        except (asyncio.CancelledError, Exception):  # noqa: BLE001
            pass
    if cold_pump_task is not None:
        cold_pump_task.cancel()
        try:
            await cold_pump_task
        except (asyncio.CancelledError, Exception):  # noqa: BLE001
            pass
    if cold_process is not None:
        event_bus.cold_sink = None
        log.info("إيقاف العمليّة الباردة: %s", {k: v for k, v in cold_process.stats().items()
                                                   if k in ("sent", "send_dropped", "returned", "loaded")})
        try:
            await cold_process.stop(timeout_s=float(cold_cfg.get("stop_timeout_s", 45.0)))
        except Exception as exc:  # noqa: BLE001
            log.error("فشل إيقاف العمليّة الباردة: %s", exc)
    # Stop first, then snapshot quiescent state, then release resources.
    if loop_watch is not None:
        try:
            watch_task.cancel()
            loop_watch.dump()
            log.warning("مِرقاب التجمّد: %d تجمّدًا · أسوأ تأخّر %.4f ث",
                        loop_watch.stalls, loop_watch.worst)
        except Exception as exc:  # noqa: BLE001
            log.warning("تعذّر كتب تقرير المرقاب: %s", exc)
    if parity is not None:
        try:
            if parity_task is not None:
                parity_task.cancel()
            written = parity.close()
            log.warning("GATE 1 — أُغلق المرجع: %s · آخر دفعة %d سطرًا",
                        parity.stats(), written)
        except Exception as exc:  # noqa: BLE001
            log.warning("إغلاق مرجع التكافؤ: %s", exc)
    snap_report = await _shutdown(registry, health_manager, log, snapshot_engine)
    # Finish and close the ownership lanes after atom shutdown. This prevents
    # pending worker tasks from being abandoned at asyncio.run() teardown.
    if hasattr(event_bus, "aclose"):
        await event_bus.aclose()

    for sig in installed_signals:
        try:
            loop.remove_signal_handler(sig)
        except (NotImplementedError, RuntimeError):
            pass
    for sig, previous in restore_handlers.items():
        try:
            signal.signal(sig, previous)
        except (ValueError, OSError, RuntimeError):
            pass

    if server is not None:
        server.should_exit = True
        await server_task

    # ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): زرّ الإيقاف لا يعلن «نظيف» إلّا بما
    # تكتبه النواة هنا بعد أن كتبت لقطاتها — لا بمجرّد موت العمليّة.
    stop_watch.close()
    stop_watch.finish(captured=list(getattr(snap_report, "captured", None) or []),
                      failed=list(getattr(snap_report, "failed", None) or []))
    log.info("تم إيقاف Core بنجاح")
    return 0


def _log_report(log: logging.Logger, report: BootReport, *, prefix: str = "انتهى الإقلاع") -> None:
    log.info(
        "%s: نجاح=%s مدة=%.2fث بدأت=%s فشلت=%s استُبعدت=%s",
        prefix, report.success, report.duration_s, report.booted, report.failed, report.excluded,
    )
    for f in report.scan_failures:
        log.warning("manifest مرفوض: %s — %s", f.path, f.error)


def _merge_boot_reports(first: BootReport, second: BootReport | None) -> BootReport:
    """Combine phased atom reports without turning deferred atoms into failures."""
    reports = [first] if second is None else [first, second]

    def unique(selector):
        return list(dict.fromkeys(item for report in reports for item in selector(report)))

    abort_reasons = [report.abort_reason for report in reports if report.abort_reason]
    return BootReport(
        started_at=min(report.started_at for report in reports),
        finished_at=max(report.finished_at for report in reports),
        success=all(report.success for report in reports),
        booted=unique(lambda report: report.booted),
        failed=unique(lambda report: report.failed),
        excluded=unique(lambda report: report.excluded),
        scan_failures=[failure for report in reports for failure in report.scan_failures],
        abort_reason="؛ ".join(abort_reasons) or None,
    )


# ── ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): طلب الإيقاف من ملفّ التحكّم ─────────
#
# العقد مع `scripts/stop_all.py` (ملفّان تحت `<state_root>/control/`، ولا يُحذف شيء):
#   core_stop.request.json  يكتبه الزرّ: {request_id, pids, requested_at, by}
#   core_stop.status.json   تكتبه النواة: stage=received عند الإقرار، ثمّ
#                           stage=stopped بعد أن كتبت لقطاتها (captured/failed).
# يُطاع الطلب إن حمل رقم هذه العمليّة وكان أحدث من ولادتها — فطلبٌ قديم بقي على
# القرص من نواةٍ سابقةٍ برقمٍ معاد لا يوقف نواةً جديدة.
STOP_REQUEST_FILE = "core_stop.request.json"
STOP_STATUS_FILE = "core_stop.status.json"


def _write_json_atomic(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(".%s.%d.tmp" % (path.name, os.getpid()))
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


class _StopRequestWatch:
    """خيطٌ يقرأ ملفّ طلب الإيقاف مرّةً كلّ ثانية، ويُقرّ ثمّ يسلّم الطلب مرّةً واحدة."""

    def __init__(self, directory: Path, *, log: logging.Logger, poll_s: float = 1.0) -> None:
        self.directory = Path(directory)
        self._log = log
        self._poll_s = float(poll_s)
        self._pid = os.getpid()
        self._closed = threading.Event()
        self._lock = threading.Lock()
        self._callback = None
        self.request: dict | None = None
        self.received_at: float | None = None
        self._thread = threading.Thread(target=self._run, name="nq-stop-request-watch", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def close(self) -> None:
        self._closed.set()

    def attach(self, callback) -> None:  # noqa: ANN001
        """يوصل الطلب بمسار الإيقاف؛ وطلبٌ وصل قبل الوصل يُسلَّم الآن."""
        with self._lock:
            self._callback = callback
            pending = self.request
        if pending is not None:
            callback(str(pending.get("by") or "?"))

    def _valid(self, data: object) -> bool:
        if not isinstance(data, dict):
            return False
        try:
            pids = {int(p) for p in data.get("pids") or ()}
            requested_at = float(data.get("requested_at"))
        except (TypeError, ValueError):
            return False
        return self._pid in pids and requested_at >= _PROCESS_STARTED_AT

    def _status(self, stage: str, **extra: object) -> None:
        request = self.request or {}
        try:
            _write_json_atomic(self.directory / STOP_STATUS_FILE, {
                "pid": self._pid, "stage": stage, "request_id": request.get("request_id"),
                "requested_at": request.get("requested_at"), "received_at": self.received_at,
                "at": time.time(), **extra})
        except OSError as exc:
            self._log.warning("تعذّرت كتابة حالة الإيقاف في %s: %s", self.directory, exc)

    def _run(self) -> None:
        path = self.directory / STOP_REQUEST_FILE
        while not self._closed.wait(self._poll_s):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if not self._valid(data):
                continue
            with self._lock:
                self.request = dict(data)
                self.received_at = time.time()
                callback = self._callback
            self._status("received")
            if callback is not None:
                callback(str(data.get("by") or "?"))
            return

    def finish(self, *, captured: list, failed: list) -> None:
        """بعد اللقطة الساكنة: يقول للزرّ «نظيف» بما كُتب فعلًا — لا بموت العمليّة."""
        if self.request is not None:
            self._status("stopped", captured=sorted(captured), failed=sorted(failed))


# ── ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): العمليّة الباردة في `/api/atoms` و`/api/health` ──
#
# النواة المختومة تعرض سجلّها وحده، و32 ذرّة باردة — منها 901 بوّابة أوامر المالك —
# لم تكن تظهر، و`/api/health` يقول `ok` ولو ماتت العمليّة. هذا الغلاف خارج الختم:
# يمرّر كلّ طلبٍ كما هو (المصادقة وحارس الأصل داخل التطبيق)، ويُلحق بجوابَي GET
# الناجحَين ذرّاتِ العمليّة الباردة (`process: cold`) وحالتَها.
_COLD_AWARE_PATHS = ("/api/atoms", "/api/health")
_HEALTH_RANK = {"ok": 0, "degraded": 1, "unhealthy": 2}


class _ColdAwareApi:
    def __init__(self, app, cold_of) -> None:  # noqa: ANN001
        self.app = app
        self._cold_of = cold_of

    def _augment(self, path: str, body: bytes, cold) -> bytes:  # noqa: ANN001
        data = json.loads(body.decode("utf-8"))
        if path == "/api/atoms" and isinstance(data, list):
            present = {row.get("id") for row in data if isinstance(row, dict)}
            data.extend(row for row in cold.atom_rows() if row["id"] not in present)
        elif path == "/api/health" and isinstance(data, dict):
            view = cold.health_view()
            data["cold_process"] = view
            if _HEALTH_RANK.get(view["status"], 0) > _HEALTH_RANK.get(str(data.get("status")), 0):
                data["status"] = view["status"]
        else:
            return body
        return json.dumps(data, ensure_ascii=False, default=str).encode("utf-8")

    async def __call__(self, scope, receive, send) -> None:  # noqa: ANN001
        cold = self._cold_of() if scope.get("type") == "http" else None
        if (cold is None or str(scope.get("method", "")).upper() != "GET"
                or scope.get("path") not in _COLD_AWARE_PATHS):
            await self.app(scope, receive, send)
            return
        start: dict = {}
        chunks: list[bytes] = []

        async def capture(message) -> None:  # noqa: ANN001
            if message["type"] == "http.response.start":
                start.update(message)
                return
            if message["type"] != "http.response.body":
                await send(message)
                return
            chunks.append(message.get("body", b""))
            if message.get("more_body"):
                return
            body = b"".join(chunks)
            if start.get("status") == 200:
                try:
                    body = self._augment(scope["path"], body, cold)
                except Exception as exc:  # noqa: BLE001 — العرض لا يُسقط الجواب الأصليّ
                    logging.getLogger("quant_nq.core.bootstrap").warning(
                        "تعذّر إلحاق العمليّة الباردة بـ%s: %s", scope.get("path"), exc)
            headers = [(k, v) for k, v in start.get("headers", []) if k.lower() != b"content-length"]
            headers.append((b"content-length", str(len(body)).encode("ascii")))
            await send({**start, "headers": headers})
            await send({"type": "http.response.body", "body": body})

        await self.app(scope, receive, capture)


async def _serve_with_error_handling(server, host: str, port: int, log: logging.Logger) -> None:
    try:
        await server.serve()
    except SystemExit as exc:
        log.error(
            "فشل بدء خادم API/WebSocket للنواة على %s:%s (كود %s) — على الأرجح "
            "تضارب منفذ أو نقص صلاحيات. Core يستمر بدون واجهة API.",
            host, port, exc.code,
        )
    except Exception as exc:  # noqa: BLE001
        log.error("خطأ غير متوقَّع في خادم API/Dashboard: %s — Core يستمر بدونها.", exc)


_ACCEPT_DEAD_MESSAGE = "Accept failed on a socket"


class _ApiSupervisor:
    """يُبقي مستمع النواة حيًّا عبر فشل `accept` واحد.

    CPython يغلق مقبس الاستماع **نفسه** عند أوّل فشل accept ولا يستأنفه:
    في `asyncio/proactor_events.py` ⟵ `except OSError: ... sock.close()`
    ثم `call_exception_handler` وحده. لا استثناء يخرج إلى `serve()`،
    فلا مُعالج ولا حارس يرى شيئًا.

    المقيس 2026-09-09 الساعة 16:10:48: `WinError 64` واحد أسقط الاستماع
    على 8010 نهائيًّا، بينما الذرّات 453 و581 و406 و622 تواصل النشر
    والتداول بعده بدقائق. أي **النظام يتداول والمالك أعمى تمامًا** — لا
    لوحة ولا `/api/*` ولا بثّ، ولا شيء يشتكي. وهذا أخطر ما في المنظومة
    لأنّه صامت: العَرَض نفسه يمنع الإبلاغ عنه.

    نقل كتابة اللقطات عن الحلقة يزيل أشيع مُطلِق لهذا (طابور accept لا
    يفيض حين لا تُحجب الحلقة 21-34 ثانية) — لكنّه لا يزيل الثغرة: أيّ
    انقطاع شبكيّ عابر يكفي.
    """

    MAX_REVIVALS = 20
    _BACKOFF_S = (1.0, 2.0, 5.0)

    def __init__(self, config, host: str, port: int, log: logging.Logger) -> None:
        self._config = config
        self._host, self._port, self._log = host, port, log
        self._server = None
        self._accept_died = asyncio.Event()
        self._should_exit = False
        self.revivals = 0

    # يُبقي عقد المُنادي كما هو: `server.should_exit = True` ثم `await task`.
    @property
    def should_exit(self) -> bool:
        return self._should_exit

    @should_exit.setter
    def should_exit(self, value: object) -> None:
        self._should_exit = bool(value)
        if self._server is not None:
            self._server.should_exit = self._should_exit
        self._accept_died.set()  # يوقظ المشرف فورًا بدل انتظار المهلة

    def install_guard(self) -> None:
        """يعترض بلاغ asyncio عن موت حلقة القبول دون ابتلاع غيره."""
        loop = asyncio.get_running_loop()
        previous = loop.get_exception_handler()

        def handler(loop_, context) -> None:  # noqa: ANN001
            if context.get("message") == _ACCEPT_DEAD_MESSAGE:
                self._log.critical(
                    "⛔ مات مقبس الاستماع على %s:%s — فشل accept أغلق المستمع "
                    "وCPython لا يستأنفه. النواة حيّة والمنفذ ميت: لا لوحة "
                    "ولا API ولا بثّ. يُستأنف الآن (محاولة %d من %d).",
                    self._host, self._port, self.revivals + 1, self.MAX_REVIVALS,
                )
                self._accept_died.set()
            if previous is None:
                loop_.default_exception_handler(context)
            else:
                previous(loop_, context)

        loop.set_exception_handler(handler)

    async def run(self) -> None:
        import uvicorn

        while not self._should_exit:
            self._accept_died.clear()
            self._server = uvicorn.Server(self._config)
            serving = asyncio.create_task(
                _serve_with_error_handling(self._server, self._host, self._port, self._log)
            )
            died = asyncio.create_task(self._accept_died.wait())
            done, _ = await asyncio.wait({serving, died}, return_when=asyncio.FIRST_COMPLETED)

            if serving in done:
                # توقّف الخادم بنفسه (منفذ محجوز، أو إيقاف مُرتَّب) — لا استئناف.
                died.cancel()
                return

            # مات المستمع تحتنا. أنزل الخادم القديم قبل إعادة الربط، وإلّا
            # بقي كائن uvicorn معلّقًا فوق مقبس مغلق.
            self._server.should_exit = True
            await serving
            if self._should_exit:
                return

            self.revivals += 1
            if self.revivals > self.MAX_REVIVALS:
                self._log.critical(
                    "⛔ تجاوز استئناف المستمع على %s:%s سقفَه (%d) — تُترك "
                    "الواجهة ساقطة. النواة تواصل التداول بلا لوحة.",
                    self._host, self._port, self.MAX_REVIVALS,
                )
                return
            delay = self._BACKOFF_S[min(self.revivals - 1, len(self._BACKOFF_S) - 1)]
            await asyncio.sleep(delay)
            self._log.warning(
                "إعادة ربط مستمع النواة على %s:%s (استئناف %d).",
                self._host, self._port, self.revivals,
            )


def _init_secret_provider(core_config: dict, log) -> None:  # noqa: ANN001
    """يهيّئ مزوّد الأسرار قبل إقلاع الذرات.

    خارج النواة تماماً: `core/` لا يعرف أن هذه الحزمة موجودة. حذف مجلد
    `security/` يجعل هذه الدالة تتجاوز نفسها بصمت وتعمل النواة كما هي
    (المادة 1/41).
    """
    cfg = core_config.get("secrets") or {}
    if not cfg.get("enabled", True):
        return
    try:
        from security import (
            ChainSecretProvider, EnvSecretProvider, FileSecretProvider,
            set_secret_provider,
        )
    except ImportError:
        log.info("حزمة security غير موجودة — يعمل النظام بلا مخزن أسرار")
        return

    # ٢٠٢٦-٠٩-٠٤ (ختم NQ): المسار النسبيّ كان يُحلّ على مجلّد العمل، ومجلّد
    # العمل يختلف بين طريقَي الإقلاع: `scripts/run_forex.py` يعمل chdir إلى
    # الـruntime، بينما `governance/app.py` (غرفة القيادة) يُطلق بـcwd=ROOT.
    # فقيمة `../runtime/secrets.enc` بـ`config/core_forex.yaml` كانت تقفز خارج
    # المشروع كلّه إلى `C:/Users/<user>/runtime` — مقيس 2026-09-04: غير موجود،
    # فيبقى المزوّد UNAVAILABLE وتعلن الذرّة 622 حرفيًّا
    # `NO_PASSWORD_IN_VAULT:ctrader_fix_password` والخزنة سليمة بمكانها.
    # العلاج: يُجذَّر على جذر الـruntime المعلَن من المُقلِع (`QUANT_RUNTIME_ROOT`)
    # لا على مجلّد العمل — نفس ما يفعله `governance/telegram.py:161`، ولذلك كان
    # تلغرام يقرأ توكنه بينما النواة عمياء. وبغياب المتغيّر يبقى السلوك كما كان.
    _anchor = Path(os.environ.get("QUANT_RUNTIME_ROOT") or Path.cwd())

    def _rooted(value):  # noqa: ANN001, ANN202
        if not value:
            return value
        path = Path(value)
        return path if path.is_absolute() else Path(os.path.normpath(_anchor / path))

    vault_path = _rooted(cfg.get("vault_path", "runtime/secrets.enc"))
    provider = ChainSecretProvider(
        FileSecretProvider(
            vault_path,
            dpapi_blob=_rooted(cfg.get("dpapi_blob")),
            allow_prompt=bool(cfg.get("allow_prompt", True)),
        ),
        EnvSecretProvider(prefix=cfg.get("env_prefix", "QUANT_SECRET_")),
    )
    set_secret_provider(provider)
    log.info("مزوّد الأسرار: %s", provider.health())


def _build_control_event_publisher(event_bus, log):  # noqa: ANN001, ANN201
    """Create a domain adapter outside Core; absent adapter means closed ingress."""
    domain = str(os.environ.get("QUANT_CORE_DOMAIN", "")).strip().lower()
    if not domain:
        return None
    try:
        from governance.control_adapter import build_control_event_publisher
        return build_control_event_publisher(domain, event_bus)
    except Exception as exc:  # noqa: BLE001
        log.error("تعذّر تحميل محوّل التحكم للنطاق %s: %s", domain, exc)
        return None


def _start_api(registry, event_bus, metrics, journal, latest_report_box, api_cfg, log,
               health_manager=None, control_event_publisher=None):  # noqa: ANN001, ANN201
    import uvicorn
    from core.api.app import create_app

    local_mode = os.environ.get("QUANT_LOCAL_MODE", "").strip() == "1"
    host, port = ("127.0.0.1" if local_mode else api_cfg.get("host", "127.0.0.1")), int(api_cfg.get("port", 8000))
    api_key = (os.environ.get("QUANT_CORE_API_KEY")
               or os.environ.get("QUANT_GOV_API_KEY") or api_cfg.get("api_key"))
    if local_mode:
        api_key = None
    if api_key is None and host != "127.0.0.1":
        log.warning(
            "⚠️ api_key غير مُعدَّة و host=%s (ليس 127.0.0.1) — المادة 28 (Secure by Default) "
            "توصي بشدة بتعيين api_key بـcore.yaml لأي ربط متاح خارج الجهاز المحلي.", host,
        )
    app = create_app(
        registry, event_bus, metrics, journal,
        get_boot_report=lambda: latest_report_box["report"],
        api_key=api_key,
        health_manager=health_manager,
        control_event_publisher=control_event_publisher,
    )
    # ضغط إطارات WebSocket (permessage-deflate) مطفأ عمدًا: القناة محلية
    # (اللوحة على نفس الجهاز) والضغط كان يُنفَّذ على الحلقة الرئيسية لكل حدث
    # فيسرق ~5% من وقتها تحت تدفّق سبعة رموز (مقيس py-spy‏ 2026-08-19).
    # ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): الغلاف يقرأ العمليّة الباردة لحظة الطلب
    # (قد تُسحب بعد فشل إقلاعها)، ويمرّر كلّ شيء كما هو حين لا عمليّة باردة.
    app = _ColdAwareApi(app, lambda: getattr(event_bus, "cold_process", None))
    config = uvicorn.Config(app, host=host, port=port, log_level="warning",
                            ws_per_message_deflate=False)
    log.info("محاولة بدء API/WebSocket للنواة على http://%s:%s", host, port)
    supervisor = _ApiSupervisor(config, host, port, log)
    supervisor.install_guard()
    task = asyncio.create_task(supervisor.run())
    return supervisor, task


async def _shutdown(registry: Registry, health_manager: HealthManager, log: logging.Logger,
                    snapshot_engine: SnapshotEngine | None = None):  # noqa: ANN201 — تقرير اللقطة أو None
    """⚠️ تطبيق المادة 11 و 16: الإيقاف المبني على السجل الديناميكي (يشمل الذرات المحملة حياً) بالترتيب الهرمي"""
    await health_manager.stop()

    # سحب جميع الذرات المعترف بها حالياً وحل اعتمادياتها لتحديد ترتيب التوقف الدقيق
    active_manifests = [r.manifest for r in registry.all()]
    try:
        graph = resolve(active_manifests)
        shutdown_order = list(reversed(graph.boot_order))
    except Exception as exc:
        log.warning("تعذّر حل الاعتماديات لتحديد ترتيب الإيقاف الدقيق (%s)، سيتم الإيقاف كإجراء طوارئ.", exc)
        shutdown_order = [r.id for r in registry.all()]

    for atom_id in shutdown_order:
        record = registry.find(atom_id)
        if record is None or record.state != AtomState.RUNNING:
            continue
        try:
            await call_lifecycle(record.instance.stop(), "stop")
            registry.set_state(atom_id, AtomState.STOPPED)
        except Exception as exc:  # noqa: BLE001
            log.error("فشل إيقاف الذرة %s بأمان: %s", atom_id, exc)

    snap_report = None
    if snapshot_engine is not None:
        snap_report = await snapshot_engine.snapshot_all()
        if snap_report.captured: log.info("التُقطت حالة ساكنة للذرات: %s", snap_report.captured)
        if snap_report.failed: log.warning("فشل التقاط حالة الذرات: %s", snap_report.failed)

    # مرحلة التنظيف النهائي (تتبع نفس مسار الترتيب العكسي للاعتماديات)
    for atom_id in shutdown_order:
        record = registry.find(atom_id)
        if record is None:
            continue
        try:
            await call_lifecycle(record.instance.shutdown(), "shutdown")
        except Exception as exc:  # noqa: BLE001
            log.error("فشل shutdown نهائي للذرة %s: %s", record.id, exc)
    return snap_report


def _verify_execution_safety_at_startup() -> int:
    """Run external execution policy only for discovered auto targets.

    BuildRegistry owns recursive discovery. The runner never guesses a path or
    a build count, and a scope with no auto execution targets is reported
    explicitly as outside this policy surface.
    """
    from build_registry import BuildRegistry

    domain = str(os.environ.get("QUANT_CORE_DOMAIN", "forex")).strip().lower()
    scope = "forex"
    snapshot = BuildRegistry(PROJECT_ROOT).refresh()
    execution_targets = tuple(
        record for record in snapshot.execution_targets
        if record.scope == scope and record.startup_mode == "auto"
    )
    if not execution_targets:
        print(f"🛡️ فحص سلامة التنفيذ: تُخُطّي — لا أهداف تنفيذ auto في نطاق {scope}.")
        return 0
    # سياسة تنفيذ الكريبتو — اعتمدها المالك 2026-08-28 (جلسة «أعلى جهوزية»):
    # نفس بوّابة سلامة التنفيذ الحاكمة للفوركس (check_execution_safety) تحكم
    # نطاق الكريبتو — لا معاملة خاصة ولا تخفيف؛ التنفيذ الحي بلا مفاتيح أصلًا
    # (الجسر الصوري 2626 هو مسار التجفيف الجاف).
    try:
        from governance.checks.check_execution_safety import inspect
        ok, problems = inspect(PROJECT_ROOT)
    except Exception as exc:  # noqa: BLE001
        print(f"⛔ رفض التشغيل: تعذّر فحص سلامة التنفيذ ({type(exc).__name__})")
        return 4
    if ok:
        print(f"🛡️ فحص سلامة التنفيذ: {len(execution_targets)} هدفًا مكتشفًا عبر Registry.")
        return 0
    print("⛔ رفض التشغيل: بوابة سلامة التنفيذ مغلقة.")
    for problem in problems:
        print("   " + problem)
    return 4

def _verify_seal_at_startup() -> int:
    """سلامة الختم شرط تشغيلي لا فحص يدوي (سدّ فجوة معروفة — 2026-08-07):
    - مختومة وسليمة → تقلع.
    - مختومة ومُنتهَكة → **ترفض الإقلاع** (نفس منطق freeze_core، والرسالة تشرح المخرج:
      إصلاح الملفات أو reseal متعمَّد بعد رفع الإصدار).
    - غير مختومة (المالك فكّ الختم عمدًا) → تحذير صريح وتقلع — فكّ الختم قراره لا قرارنا.
    المشغّل خارج الختم (ورقة ٠٧/١٥) — النواة لا تحرس نفسها."""
    try:
        from governance.scripts.freeze_core import LOCK_FILE, verify
    except ImportError:
        from governance.scripts.freeze_core import LOCK_FILE, verify
    if not LOCK_FILE.exists():
        print("⚠️ تحذير: النواة غير مختومة (لا CORE.lock) — الإقلاع مستمر، والختم قرار المالك.")
        return 0
    result = verify(quiet=True)
    if result == 0:
        print("🔒 فحص الختم عند الإقلاع: النواة سليمة ومطابقة.")
        return 0
    print("⛔ رفض الإقلاع: خرق ختم النواة — التفاصيل الكاملة:")
    verify(quiet=False)
    return 3


def main() -> int:
    parser = argparse.ArgumentParser(description="تشغيل QUANT_NQ Core V1.0")
    parser.add_argument("--no-api", action="store_true", help="تعطيل REST/WebSocket/Dashboard")
    parser.add_argument("--skip-seal-check", action="store_true",
                        help="تجاوز فحص الختم عند الإقلاع (طوارئ فقط — بقرار المالك)")
    parser.add_argument("--demo-seconds", type=float, default=None,
                        help="تشغيل أماميّ محدود بالمدّة ثمّ إيقاف نظيف (اختبار)")
    args = parser.parse_args()
    if not args.skip_seal_check:
        seal = _verify_seal_at_startup()
        if seal != 0:
            return seal
    # 🔴 ٢٠٢٦-٠٩-٢٥ (ختم المالك «Nq كل إصلاحات») — كتابة السجلّ خارج خيط الحلقة.
    # مِرقاب الحلقة سمّى التجمّد (17.6ث ثمّ 23.2ث): الحلقة كلّها تنتظر `flush` سطرِ
    # سجلٍّ إلى نافذة النواة. التفصيل في `engine/process_logs.make_logging_nonblocking`.
    from engine.process_logs import make_logging_nonblocking
    make_logging_nonblocking()
    try:
        return asyncio.run(run(enable_api=(False if args.no_api else None),
                               demo_seconds=args.demo_seconds))
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
