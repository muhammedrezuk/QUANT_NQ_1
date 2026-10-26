"""محرّك الرموز — النواة الموزّعة على أنوية الجهاز.

**العلّة التي يعالجها، مقيسة على جهاز المالك ٢٠٢٦-٠٩-١٧ 17:10:**

    الجهاز            12 خيطًا (6 أنوية)   ⟵ نصفه فارغ
    نواة التداول     104٪ من خيطٍ واحد    = 8.7٪ من الجهاز  ⟵ مشبعة
    التِكّات الداخلة   ≈ 120/ث
    الأحداث المولَّدة  ≈ 2,551/ث            ⟵ واحدٌ وعشرون حدثًا لكلّ تِكّة

فالاختناق ليس السوق ولا النقل — بل أنّ **٢١ ضِعف التِكّة يمرّ في خيطٍ واحد**.
وكلّ تحسينٍ داخل ذلك الخيط يعصره ولا يفكّ حبسه: ثمانية رموز تُشبعه اليوم،
وعشرون رمزًا (CFD + عقود شيكاغو) ضعفان ونصف فوق سعته ⟵ سقوط.

**الوحدة هي الرمز لا الطبقة.** تِكّة الذهب كلّها — تحقّق · تحليل · بنية ·
سيولة · إحصاء · احتمالات · استراتيجيات · قرار · مخاطر · نيّة تنفيذ — في
عمليّةٍ واحدة تملك الذهب وحده، بمحرّك NQEngine كامل وحالةٍ محلّيّة. ولا
IPC داخل مسار الرمز إطلاقًا.

**ولماذا لا يخالف هذا ورقة المالك:** §١ منعت التقسيم **بالحدث** — وهو الذي
فشلت فيه المزرعة لأنّها قطعت مسار التِكّة نصفين (candle_closed هنا وtick
هناك). التقسيم بالرمز لا يقطع مسارًا: مالكٌ واحد، وترتيبٌ محفوظ، وحالةٌ لا
تُشارَك. وهو نصّ §٣ من ورقة المصنع: Account × Symbol وحدة الملكيّة، و§١٣:
«مالك واحد فعليّ في لحظة واحدة».

**ما لا ينتقل — بالقياس لا بالظنّ:**

    العابرات للرموز   160 الارتباط · 161 القوّة النسبيّة · 307 (مقيس:
                      التقسيم أعطى 20 مخرجًا خاطئًا من 60)
    المحفظة           650-699 — عابرة بالتعريف
    التغذية والجسور   600-649 — مقابس شبكة ومنافذ وسيط
    الساعة            806 — الزمن لا يُوزَّع
    التنفيذ النهائيّ   601 والجسر — سلطةٌ مركزيّة بحكم §٣

وما يعبر الحدّ: التِكّة داخلةً، والعمود الفقريّ (الحساب · المحفظة · الساعة —
مقيسٌ عند **١١٪** من الأحداث)، ونيّة التنفيذ عائدةً. أي أنّ ٨٩٪ من الحركة
تبقى داخل عمليّة رمزها.
"""
from __future__ import annotations

import asyncio
import logging
import multiprocessing as mp
import os
import queue as queue_module
import sys
import threading
import time
from collections import OrderedDict, deque

import clock
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable, Iterable

from .cold_host import BOOTED, STATS, STOP, _drain

PROJECT_ROOT = Path(__file__).resolve().parents[1]

#: رسالة تحكّم تحمل خريطة التصنيف المشتقّة من رسم المستهلكين في الجذر.
CLASSIFY = "__classify__"
#: رزمة أحداث المال — عنصرٌ واحد في الأنبوب يحمل عدّة أحداث بترتيبها.
MONEY_BATCH = "__money_batch__"
#: سقف الرزمة: عددًا وزمنًا. الزمن ضيّقٌ كي لا ينتظر أوّل حدثٍ فيها.
MONEY_BATCH_MAX = 64
MONEY_BATCH_S = 0.004

_log = logging.getLogger("quant_nq.core.symbol_host")


def _pct(values: Any) -> dict:
    """مئينات زمن عبور المال — تُقاس عند بابه في الجذر لا عند اللوحة."""
    rows = sorted(values)
    if not rows:
        return {}
    n = len(rows)
    return {"n": n, "p50": round(rows[n // 2], 4),
            "p95": round(rows[min(n - 1, int(n * 0.95))], 4),
            "p99": round(rows[min(n - 1, int(n * 0.99))], 4),
            "max": round(rows[-1], 4)}


def _qsize(q: Any) -> int | None:
    try:
        return int(q.qsize())
    except (NotImplementedError, OSError, ValueError):
        return None


# ===================== جسم عمليّة محرّك الرموز =====================

async def _worker_async(inbox: Any, outbox: Any, cfg: dict,
                        out_storage: Any = None, out_obs: Any = None) -> None:
    from core import logger as core_logger
    from core.bootloader import Bootloader
    from core.health_manager import HealthManager
    from core.journal import Journal
    from core.lifecycle import call_lifecycle
    from core.metrics import Metrics
    from core.registry import Registry
    from core.snapshot_engine import SnapshotEngine
    from transport.owned_event_bus import OwnedEventBus

    from .engine import NQEngine

    core_logger.configure(
        level=getattr(logging, str(cfg.get("log_level", "INFO")).upper(), logging.INFO),
        json_output=bool(cfg.get("log_json", True)))
    group = str(cfg.get("group") or "?")
    log = logging.getLogger("quant_nq.core.symbol_host.%s" % group)
    atom_ids = {int(v) for v in cfg["atom_ids"]}
    id_names = {str(v) for v in atom_ids}
    symbols = frozenset(str(s) for s in (cfg.get("symbols") or ()))
    atoms_root = Path(cfg["atoms_root"])

    registry = Registry()
    cold = OwnedEventBus(payload_mode="shared_readonly", worker_count=2,
                         partitioned_ownership=False, mailbox_max_events=2048,
                         cold_sections=(), scope_groups=1)
    engine = NQEngine(
        cold_bus=cold,
        cadence_sections=cfg.get("cadence_sections") or ((150, 499),),
        cold_sections=(),
        cycle_deadline_s=float(cfg.get("cycle_deadline_s", 5.0)),
        max_depth=int(cfg.get("max_depth", 64)),
        every_backlog_alarm=int(cfg.get("every_backlog_alarm", 2000)),
        cold_bus_throttle_s=float(cfg.get("cold_bus_throttle_s", 0.0)),
        cutoff_mode=str(cfg.get("cutoff_mode", "shadow")),
        cutoff_max_hold_s=float(cfg.get("cutoff_max_hold_s", 0.0)),
        hot_direct=bool(cfg.get("hot_direct", True)),
        cadence_min_interval_s=float(cfg.get("cadence_min_interval_s", 0.0)),
        latency_stage_cap=int(cfg.get("latency_stage_cap", 0)),
        latency_tick_events=tuple(cfg.get("latency_tick_events") or ()),
        cutoff_probe_digits=tuple(cfg.get("cutoff_probe_digits") or ()),
        cutoff_probe_sample=int(cfg.get("cutoff_probe_sample", 1)),
    )
    # ── مرآة الساعة ──────────────────────────────────────────────────────
    # الذرّة 003 (الساعة) رقمها ثلاثة — خارج مدى المحرّكات — فلا تُقلع هنا،
    # وساعة هذا المفسّر تبقى `LOCAL_FALLBACK` فترفض 552 كلّ أمرٍ بـ
    # `CLOCK_NOT_SYNCED`. والعيّنة تصل أصلًا (`broadcast_prefixes` تشمل
    # `time.`) ولا مستهلك لها هنا. فيُتبنّى قرار المالك — لا مالكٌ ثانٍ.
    #
    # ٢٠٢٦-٠٩-١٨ (بلاغ قسم 450): 153 أمرًا من 153 مرفوضة، وصفر صفقة منذ
    # 17:25 من 09-17 — وهو يوم شُغّلت المحرّكات.
    _clock_keys = ("max_accepted_offset_s", "max_sample_age_s",
                   "stale_after_s", "max_slew_per_second")
    _clock_cfg = {k: float(v) for k, v in (cfg.get("clock_config") or {}).items()
                  if k in _clock_keys}
    if _clock_cfg:
        try:
            clock.configure(**_clock_cfg)
        except Exception as exc:  # noqa: BLE001
            log.error("تعذّرت تهيئة ساعة المحرّك %s: %s", group, exc)

    journal = Journal(path=Path(cfg["journal_path"]) if cfg.get("journal_path") else None)
    metrics = Metrics()
    health = HealthManager(registry, engine, journal, metrics)
    snapshot = SnapshotEngine(registry, Path(cfg["snapshot_dir"])) if cfg.get("snapshot_dir") else None

    async def _restore(atom_id: int) -> None:
        if snapshot is not None:
            await snapshot.restore_one(atom_id)

    bootloader = Bootloader(atoms_root, registry, engine, journal, metrics,
                            health_manager=health, restore_hook=_restore)
    t0 = time.perf_counter()
    report = await bootloader.boot(include_ids=set(atom_ids))
    loaded = sorted(r.id for r in registry.all())
    counters = {"inbound": 0, "inbound_batches": 0, "outbound": 0, "outbound_dropped": 0,
                "echo_suppressed": 0, "foreign_symbol": 0, "snapshots": 0, "clock_adopted": 0, "clock_rejected": 0,
                "money": 0, "storage": 0, "observation": 0, "internal": 0,
                "obs_coalesced": 0, "money_dropped": 0, "storage_dropped": 0}

    async def _adopt_clock(payload: Any) -> None:
        if not isinstance(payload, dict):
            return
        accepted, reason = clock.adopt_owner_sample(dict(payload))
        if accepted:
            counters["clock_adopted"] += 1
        elif reason != "DUPLICATE_SAMPLE":
            counters["clock_rejected"] += 1
            log.warning("محرّك %s رفض عيّنة الساعة: %s", group, reason)

    engine.subscribe("time.ntp.samples.state", _adopt_clock, subscriber="003")
    # خريطة التصنيف — تصل من الجذر بعد إقلاعه (مشتقّة من رسم المستهلكين).
    # قبل وصولها: كلّ شيء **مال** — أسلم افتراضٍ ممكن، فلا يُبطَّأ حدثُ مالٍ
    # لأنّ الخريطة تأخّرت، ولا يُفقد شيء.
    classify = {"money": None, "storage": frozenset(), "internal": frozenset()}
    money_batch: list = []
    #: العرض المعلَّق: (اسم، رمز) ⟶ حمولة — الأحدث يحلّ محلّ سابقه.
    obs_pending: dict = {}
    engine.start_display_flusher()
    outbox.put((BOOTED, {
        "pid": os.getpid(), "group": group, "symbols": sorted(symbols),
        "loaded": loaded, "failed": list(report.failed),
        "boot_s": round(time.perf_counter() - t0, 2),
        "failed_reasons": {int(i): (registry.find(int(i)).last_error if registry.find(int(i)) else None)
                           for i in report.failed},
    }))
    log.info("محرّك الرموز %s أقلع: %d ذرّة · رموز %s · %.1f ث (فشل %s)",
             group, len(loaded), sorted(symbols), time.perf_counter() - t0, list(report.failed))

    inbound_ids: "OrderedDict[str, None]" = OrderedDict()

    async def collector(name: str, payload: Any) -> None:
        """ما تنتجه ذرّاتنا يعود إلى الجذر — لا ما دخل علينا."""
        if not isinstance(payload, dict):
            return
        if str(payload.get("source") or "") not in id_names:
            return
        event_id = str(payload.get("event_id") or "")
        if event_id and event_id in inbound_ids:
            counters["echo_suppressed"] += 1
            return
        counters["outbound"] += 1
        body = dict(payload)
        money_names = classify["money"]
        # ما لا يقرؤه أحدٌ خارج هذه العمليّة لا يعبر الحدّ أصلًا.
        if name in classify.get("internal", ()):
            counters["internal"] += 1
            return
        # التصنيف: ما له مستهلكٌ فاعل في الجذر = مال (بلا فقد ولا دمج ولا انتظار)؛
        # ما تخزّنه المخازن = تخزين (كامل ومرتّب، أولويّته دنيا)؛ والباقي عرضٌ
        # يُدمج بالأحدث. ولا قائمة أسماءٍ مكتوبة بيد — الخريطة من الرسم.
        if money_names is None or name in money_names:
            counters["money"] += 1
            # ٢٠٢٦-٠٩-١٨ (الدرس نفسه الذي دفعناه في العمليّة الباردة أمس):
            # كلفة أنبوب ويندوز **لكلّ رسالة** لا لكلّ بايت. فإرسال عنصرٍ
            # واحد لكلّ حدثٍ يجعل العبور متقطّعًا: p50 = 0.024 ث وp95 = 1.85.
            # فتُجمَع الأحداث في رزمةٍ واحدة تُرسَل معًا — بالترتيب نفسه،
            # وبلا فقد، وبسقفٍ زمنيٍّ ضيّق كي لا ينتظر أوّلُها.
            money_batch.append((name, body))
            if len(money_batch) >= MONEY_BATCH_MAX:
                _flush_money()
        elif name in classify["storage"]:
            counters["storage"] += 1
            if out_storage is not None:
                try:
                    out_storage.put_nowait((name, body))
                except queue_module.Full:
                    counters["storage_dropped"] += 1
        elif out_obs is not None:
            counters["observation"] += 1
            key = (name, str(body.get("symbol") or ""))
            if key in obs_pending:
                counters["obs_coalesced"] += 1
            obs_pending[key] = (name, body)
        else:
            counters["internal"] += 1

    def _flush_money() -> None:
        if not money_batch:
            return
        batch, money_batch[:] = list(money_batch), []
        try:
            outbox.put_nowait((MONEY_BATCH, batch))
        except queue_module.Full:
            counters["money_dropped"] += len(batch)   # ⛔ يُعدّ ولا يُبتلع أبدًا

    async def _money_flusher() -> None:
        while not stopping.is_set():
            try:
                await asyncio.wait_for(stopping.wait(), timeout=MONEY_BATCH_S)
            except asyncio.TimeoutError:
                pass
            _flush_money()

    engine.subscribe_all(collector, subscriber="cold:egress", isolate_payload=False)
    engine.seal()

    loop = asyncio.get_running_loop()
    stopping = asyncio.Event()
    batches: asyncio.Queue = asyncio.Queue()
    slots = threading.Semaphore(int(cfg.get("batch_slots", 32)))
    reader_stop = threading.Event()

    def _hand_over(items: list) -> None:
        try:
            batches.put_nowait(items)
        except Exception:  # noqa: BLE001
            slots.release()

    def reader() -> None:
        pending: list = []
        last = time.perf_counter()
        batch_max = int(cfg.get("batch", 200))
        while not reader_stop.is_set():
            try:
                item = inbox.get(timeout=0.05)
            except (queue_module.Empty, EOFError, OSError):
                item = None
            if item is not None:
                if isinstance(item, list):
                    pending.extend(item)
                else:
                    pending.append(item)
                if item == STOP or (isinstance(item, list) and item and item[-1] == STOP):
                    slots.acquire()
                    loop.call_soon_threadsafe(_hand_over, pending)
                    return
            now = time.perf_counter()
            if pending and (len(pending) >= batch_max or now - last >= 0.02 or item is None):
                slots.acquire()
                loop.call_soon_threadsafe(_hand_over, pending)
                pending = []
                last = now

    reader_thread = threading.Thread(target=reader, name="symbol-inbox-reader", daemon=True)
    reader_thread.start()

    async def pump() -> None:
        while not stopping.is_set():
            items = await batches.get()
            slots.release()
            counters["inbound_batches"] += 1
            for item in items:
                if item == STOP:
                    stopping.set()
                    break
                name, payload = item
                if name == CLASSIFY:
                    classify["money"] = frozenset(payload.get("money") or ())
                    classify["storage"] = frozenset(payload.get("storage") or ())
                    classify["internal"] = frozenset(payload.get("internal") or ())
                    log.info("محرّك %s: خريطة الخروج — مال %d · تخزين %d · داخليّ %d · الباقي عرض",
                             group, len(classify["money"]), len(classify["storage"]),
                             len(classify["internal"]))
                    continue
                # رمزٌ ليس لنا لا يدخل: الجذر يوجّه، وهذا سياجٌ ثانٍ يمنع أن
                # تعمل عمليّتان على الرمز نفسه لو أخطأ التوجيه.
                if symbols and isinstance(payload, dict):
                    sym = str(payload.get("symbol") or "")
                    if sym and sym not in symbols:
                        counters["foreign_symbol"] += 1
                        continue
                counters["inbound"] += 1
                if isinstance(payload, dict):
                    event_id = str(payload.get("event_id") or "")
                    if event_id:
                        inbound_ids[event_id] = None
                        if len(inbound_ids) > 200_000:
                            inbound_ids.popitem(last=False)
                    publisher = str(payload.get("source") or "symbol_host.ingress")
                else:
                    publisher = "symbol_host.ingress"
                try:
                    await engine.publish(name, payload, publisher=publisher)
                except Exception as exc:  # noqa: BLE001
                    log.error("تعذّر نشر %s في محرّك %s: %s", name, group, exc)

    async def obs_flush_loop() -> None:
        """يُفرغ العرض المدموج بإيقاعٍ — لا يزاحم المال ولا يحبس أحدًا."""
        every = float(cfg.get("obs_flush_s", 1.0))
        while out_obs is not None and not stopping.is_set():
            try:
                await asyncio.wait_for(stopping.wait(), timeout=every)
                break
            except asyncio.TimeoutError:
                pass
            if not obs_pending:
                continue
            batch = list(obs_pending.values())
            obs_pending.clear()
            try:
                out_obs.put_nowait(batch)
            except queue_module.Full:
                pass                                # عرضٌ متأخّر يسقط بلا ضرر

    async def stats_loop() -> None:
        every = float(cfg.get("stats_every_s", 5.0))
        while not stopping.is_set():
            try:
                await asyncio.wait_for(stopping.wait(), timeout=every)
            except asyncio.TimeoutError:
                pass
            try:
                ts = engine.transport_stats()
                e = ts.get("engine") or {}
                rss = None
                try:
                    import psutil
                    rss = round(psutil.Process().memory_info().rss / 1e6, 1)
                except Exception:  # noqa: BLE001
                    pass
                outbox.put_nowait((STATS, {
                    "pid": os.getpid(), "group": group, "at": time.time(),
                    "cpu_s": round(time.process_time(), 2), "rss_mb": rss,
                    "counters": dict(counters),
                    "engine": {k: e.get(k) for k in (
                        "cycles", "cycle_timeouts", "depth_exceeded", "budget_exceeded",
                        "cycle_mean_s", "cycle_worst_s", "cycle_worst_root",
                        "handler_total_s", "cycle_total_s")},
                    # القطع المبكّر: النسبة تُقرأ من كلّ محرّك على حدة — فالذرّات
                    # التحليليّة كلّها هنا لا في الجذر، وهي المقصودة بالقياس.
                    "cutoff": e.get("cutoff"),
                    "cutoff_probes": e.get("cutoff_probes"),
                    "scheduler": e.get("scheduler"),
                    "time_by_pair": e.get("time_by_pair"),
                    "backlog": (e.get("scheduler") or {}).get("backlog"),
                    "overrun_by_subscriber": e.get("overrun_by_subscriber"),
                    "error_by_subscriber": e.get("error_by_subscriber"),
                    "latency": (ts.get("latency") or {}).get("symbols"),
                    "stage_waterfall": (ts.get("latency") or {}).get("stage_waterfall"),
                    "atoms": {str(r.id): getattr(r.state, "value", str(r.state)) for r in registry.all()},
                    # §١٦ — حاجز الاكتمال: كلّ ذرّةٍ تعلن 
                    # يصل قياسها الجذر. الذرّات التي تعيش هنا لا يراها
                    # ، فبلا هذا يبقى الدليل حبيس المفسّر.
                    "barriers": {
                        str(r.id): r.instance.barrier_stats()
                        for r in registry.all()
                        if callable(getattr(getattr(r, "instance", None),
                                            "barrier_stats", None))},
                }))
            except queue_module.Full:
                pass
            except Exception as exc:  # noqa: BLE001
                log.warning("تعذّر إرسال إحصاءات محرّك %s: %s", group, exc)

    async def snapshot_loop() -> None:
        every = float(cfg.get("snapshot_every_s", 180.0))
        while snapshot is not None and not stopping.is_set():
            try:
                await asyncio.wait_for(stopping.wait(), timeout=every)
                break
            except asyncio.TimeoutError:
                pass
            try:
                rep = await snapshot.snapshot_all()
                counters["snapshots"] += len(rep.captured)
            except Exception as exc:  # noqa: BLE001
                log.warning("فشل لقطة محرّك %s: %s", group, exc)

    tasks = [asyncio.create_task(_money_flusher(), name="symbol-money-flush"),
             asyncio.create_task(pump(), name="symbol-pump"),
             asyncio.create_task(stats_loop(), name="symbol-stats"),
             asyncio.create_task(obs_flush_loop(), name="symbol-obs-flush"),
             asyncio.create_task(snapshot_loop(), name="symbol-snapshot")]
    await stopping.wait()
    reader_stop.set()
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)

    await health.stop()
    for record in reversed(list(registry.all())):
        try:
            await call_lifecycle(record.instance.stop(), "stop", timeout=10.0)
        except Exception as exc:  # noqa: BLE001
            log.error("فشل إيقاف الذرّة %s في محرّك %s: %s", record.id, group, exc)
    if snapshot is not None:
        try:
            await snapshot.snapshot_all()
        except Exception as exc:  # noqa: BLE001
            log.warning("فشل لقطة الإغلاق لمحرّك %s: %s", group, exc)
    for record in reversed(list(registry.all())):
        try:
            await call_lifecycle(record.instance.shutdown(), "shutdown", timeout=10.0)
        except Exception as exc:  # noqa: BLE001
            log.error("فشل shutdown للذرّة %s: %s", record.id, exc)
    try:
        await engine.drain(timeout_s=5.0)
    finally:
        await engine.close()
    log.info("محرّك الرموز %s أُوقف نظيفًا: %s", group, counters)


def _worker_main(inbox: Any, outbox: Any, cfg: dict,
                 out_storage: Any = None, out_obs: Any = None) -> None:
    """نقطة دخول العمليّة الابنة — على مستوى الوحدة كي تُخلَّل بـspawn."""
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
    os.environ.setdefault("PYTHONUTF8", "1")
    for key, value in (cfg.get("env") or {}).items():
        os.environ[str(key)] = str(value)
    # ٢٠٢٦-٠٩-٢٤ (ختم المالك «صلح nq»): لكلّ عمليّة رموز سجلّها — العلّة نفسها
    # التي أضاعت ٢٥ دقيقة من سجلّ المحرّك ليلة ٢٣→٢٤ (انظر process_logs).
    from .process_logs import isolate_log_dir, make_logging_nonblocking
    isolate_log_dir("symbol-%s" % (cfg.get("group") or "worker"))
    # ٢٠٢٦-٠٩-٢٥ — وكتابتُه خارج خيط حلقته، كالمحرّك (انظر process_logs).
    make_logging_nonblocking()
    try:
        asyncio.run(_worker_async(inbox, outbox, cfg, out_storage, out_obs))
    except KeyboardInterrupt:
        pass


# ========================= الطرف الجذر =========================

class SymbolEngine:
    """مقبض محرّك رموزٍ واحد من جهة الجذر."""

    def __init__(
        self,
        *,
        group: str,
        symbols: Iterable[str],
        atom_ids: Iterable[int],
        atoms_root: str,
        snapshot_dir: str | None = None,
        journal_path: str | None = None,
        env: dict | None = None,
        cadence_sections: Any = ((150, 499),),
        cutoff_mode: str = "shadow",
        cutoff_max_hold_s: float = 0.0,
        hot_direct: bool = True,
        cadence_min_interval_s: float = 0.0,
        latency_stage_cap: int = 0,
        latency_tick_events: Any = (),
        clock_config: Any = None,
        cutoff_probe_digits: Any = (),
        cutoff_probe_sample: int = 1,
        cycle_deadline_s: float = 5.0,
        max_depth: int = 64,
        inbox_max: int = 2000,
        outbox_max: int = 20000,
        storage_max: int = 40000,
        obs_max: int = 2000,
        batch_max: int = 200,
        # ٢٠٢٦-٠٩-١٧ 17:30 — قِيس 0.005: ثلاثة مصرّفات × 200 استيقاظ/ث تركت
        # **٥٥٪** من الجذر في إدارة مؤقّتات asyncio، والدفعات صغيرة فغلا الأنبوب
        # (16٪). و20 م.ث لا تُرى أمام p99 = 0.5 ث، وتُكبّر الدفعة أربعة أضعاف.
        flush_every_s: float = 0.02,
        log_level: str = "INFO",
        log_json: bool = True,
    ) -> None:
        self.group = str(group)
        self.symbols = frozenset(str(s) for s in symbols)
        self.hosted_atom_ids = sorted({int(v) for v in atom_ids})
        self._cfg = {
            "group": self.group, "symbols": sorted(self.symbols),
            "atom_ids": list(self.hosted_atom_ids), "atoms_root": str(atoms_root),
            "snapshot_dir": snapshot_dir, "journal_path": journal_path,
            "env": dict(env or {}), "cadence_sections": [list(p) for p in cadence_sections],
            "cutoff_mode": str(cutoff_mode),
            "cutoff_max_hold_s": float(cutoff_max_hold_s),
            "hot_direct": bool(hot_direct),
            "cadence_min_interval_s": float(cadence_min_interval_s),
            "latency_stage_cap": int(latency_stage_cap),
            "latency_tick_events": [str(e) for e in (latency_tick_events or ())],
            "clock_config": dict(clock_config or {}),
            "cutoff_probe_digits": [int(n) for n in (cutoff_probe_digits or ())],
            "cutoff_probe_sample": int(cutoff_probe_sample),
            "cycle_deadline_s": float(cycle_deadline_s), "max_depth": int(max_depth),
            "log_level": log_level, "log_json": log_json,
        }
        self._ctx = mp.get_context("spawn")
        self._inbox = self._ctx.Queue(maxsize=int(inbox_max))
        # ⛔ ثلاثة صناديق **فيزيائيّة** لا أولويّة داخل صندوق: حدث المال لا
        #    ينتظر خلف تسعة عشر ألف حدث عرض (المقيس: 32.1 ث وسيطًا).
        self._outbox = self._ctx.Queue(maxsize=int(outbox_max))          # مال
        self._out_storage = self._ctx.Queue(maxsize=int(storage_max))    # تخزين
        self._out_obs = self._ctx.Queue(maxsize=int(obs_max))            # عرض
        self._process: Any = None
        self._pending: list = []
        self.batch_max = int(batch_max)
        self.flush_every_s = float(flush_every_s)
        self._flusher: Any = None
        self.started_at = 0.0
        self.boot_report: dict[str, Any] = {}
        self.last_stats: dict[str, Any] = {}
        self.sent = 0
        self.send_dropped = 0
        self.batches_sent = 0
        self.returned = 0
        self.returned_storage = 0
        self.returned_obs = 0
        #: زمن عبور حدث المال: من ختمه في المحرّك إلى نشره في الجذر — يُقاس
        #: عند بابه لا عند اللوحة (فسقف العرض يضخّم أيّ قياسٍ يمرّ بها).
        self.money_lag: deque = deque(maxlen=4096)
        self.classification_sent = None
        # ── فصل سياق التنفيذ (٢٠٢٦-٠٩-١٨) ────────────────────────────────
        # بركةٌ للمال وحده، وبركةٌ للبارد. ولا واحدة منهما بركة الحلقة
        # الافتراضيّة التي تستعملها الذرّات — فلا يزاحم أحدٌ أحدًا.
        self._money_pool = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="nq-money-%s" % group)
        self._cold_pool = ThreadPoolExecutor(
            max_workers=2, thread_name_prefix="nq-cold-%s" % group)

    # -- دورة الحياة --------------------------------------------------

    def spawn(self) -> None:
        self._process = self._ctx.Process(
            target=_worker_main,
            args=(self._inbox, self._outbox, self._cfg, self._out_storage, self._out_obs),
            name="nq-engine-%s" % self.group, daemon=False)
        self._process.start()
        self.started_at = time.time()

    def start_flusher(self) -> None:
        async def _run() -> None:
            while True:
                await asyncio.sleep(self.flush_every_s)
                self.flush()
        self._flusher = asyncio.get_running_loop().create_task(
            _run(), name="nq-symbol-flusher-%s" % self.group)

    def stop_flusher(self) -> None:
        if self._flusher is not None:
            self._flusher.cancel()
            self._flusher = None
        self.flush()

    async def wait_booted(self, timeout_s: float = 240.0) -> dict[str, Any]:
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            # قارئ الصادر قد يكون سحب تقرير الإقلاع قبلنا — يُقرأ منه لا
            # يُنتظر مرّتين. (العطب المقيس: المحرّك الثاني علّق 150 ث.)
            if self.boot_report:
                return self.boot_report
            items = await asyncio.to_thread(_drain, self._outbox, 0.5, 50)
            for item in items:
                if isinstance(item, tuple) and item and item[0] == BOOTED:
                    self.boot_report = dict(item[1])
                    return self.boot_report
                if isinstance(item, tuple) and item and item[0] == STATS:
                    self.last_stats = dict(item[1])
            if self._process is not None and not self._process.is_alive():
                raise RuntimeError("محرّك %s خرج قبل أن يُقلع (رمز %s)"
                                   % (self.group, self._process.exitcode))
        raise TimeoutError("محرّك %s لم يُبلّغ إقلاعه خلال %.0f ث" % (self.group, timeout_s))

    def is_alive(self) -> bool:
        return self._process is not None and self._process.is_alive()

    def send_classification(self, money: Any, storage: Any,
                            internal: Any = ()) -> None:
        """يرسل خريطة الخروج المشتقّة من رسم المستهلكين — قبلها كلّ شيء مال."""
        self.flush()
        self._inbox.put((CLASSIFY, {"money": sorted(money), "storage": sorted(storage),
                                    "internal": sorted(internal)}))
        self.classification_sent = (len(money), len(storage), len(internal))

    # -- التوجيه ------------------------------------------------------

    def owns(self, symbol: str) -> bool:
        return symbol in self.symbols

    def send(self, event_name: str, body: Any) -> None:
        self._pending.append((event_name, dict(body) if isinstance(body, dict) else body))
        self.sent += 1
        if len(self._pending) >= self.batch_max:
            self.flush()

    def flush(self) -> None:
        if not self._pending:
            return
        batch, self._pending = self._pending, []
        try:
            self._inbox.put_nowait(batch)
            self.batches_sent += 1
        except (queue_module.Full, ValueError, OSError):
            # امتلاءٌ هنا يعني أنّ المحرّك لا يلحق — يُعدّ ولا يُبتلع، ولا يحبس
            # الجذر أبدًا (التغذية والتنفيذ فيه).
            self.send_dropped += len(batch)

    async def pump_storage(self, publish: Callable[..., Any],
                           mark_inbound: Callable[[str], None] | None = None) -> None:
        """التاريخ لا يستعجل — ودفعاتٌ كبيرة بمهلةٍ أطول لا تزاحم المال."""
        while True:
            items = await asyncio.get_running_loop().run_in_executor(
                self._cold_pool, _drain, self._out_storage, 0.5, 2000)
            if not items:
                continue
            self.returned_storage += len(items)
            await self._republish(items, publish, mark_inbound)

    async def pump_observation(self, publish: Callable[..., Any],
                               mark_inbound: Callable[[str], None] | None = None) -> None:
        """دفعات العرض المدموجة — واحدةٌ لكلّ نافذة."""
        while True:
            batches = await asyncio.get_running_loop().run_in_executor(
                self._cold_pool, _drain, self._out_obs, 0.5, 20)
            if not batches:
                continue
            items = [row for batch in batches if isinstance(batch, list) for row in batch]
            self.returned_obs += len(items)
            await self._republish(items, publish, mark_inbound)

    async def _republish(self, items: list, publish: Callable[..., Any],
                         mark_inbound: Callable[[str], None] | None,
                         money_lag: Any = None) -> None:
        for item in items:
            if not (isinstance(item, tuple) and len(item) == 2):
                continue
            name, payload = item
            if money_lag is not None and isinstance(payload, dict):
                ts = payload.get('timestamp')
                if isinstance(ts, (int, float)):
                    d = time.time() - float(ts)
                    if 0.0 <= d < 300.0:
                        money_lag.append(d)
            if isinstance(payload, dict) and mark_inbound is not None:
                event_id = str(payload.get("event_id") or "")
                if event_id:
                    mark_inbound(event_id)
            try:
                await publish(name, payload,
                              publisher=str(payload.get("source") or self.group)
                              if isinstance(payload, dict) else self.group)
            except Exception as exc:  # noqa: BLE001
                _log.error("تعذّر إعادة نشر %s من محرّك %s: %s", name, self.group, exc)

    async def pump_outbound(self, publish: Callable[..., Any],
                            mark_inbound: Callable[[str], None] | None = None) -> None:
        """مسار المال — مهلةٌ قصيرة ودفعاتٌ صغيرة: يُفرَّغ فور وصوله."""
        while True:
            # مسار المال: مهلةٌ ضيّقة ودفعةٌ صغيرة — الهدف ≤ 0.1 ث بأمر المالك.
            # ٢٠٢٦-٠٩-١٨ (المقيس): تأخّر المال p50=0.025 وp95=1.85 — أي أنّ
            # العبور ليس بطيئًا بل **متقطّع**: دفعةٌ من مئة ثمّ رحلةُ ذهابٍ
            # وإيابٍ إلى بركة الخيوط، وفي أثنائها يتراكم ما وراءها. والدفعة
            # الأكبر تقلّل الرحلات بلا أن تؤخّر أوّل عنصرٍ (المهلة 0.01 كما هي).
            items = await asyncio.get_running_loop().run_in_executor(
                self._money_pool, _drain, self._outbox, 0.01, 1000)
            if not items:
                if self._process is not None and not self._process.is_alive():
                    _log.critical("محرّك %s مات — رموزه %s بلا تحليل ولا قرار",
                                  self.group, sorted(self.symbols))
                    await asyncio.sleep(2.0)
                continue
            unpacked: list = []
            for item in items:
                if (isinstance(item, tuple) and len(item) == 2
                        and item[0] == MONEY_BATCH and isinstance(item[1], list)):
                    unpacked.extend(item[1])          # رزمةٌ تُفكّ بترتيبها
                else:
                    unpacked.append(item)
            for item in unpacked:
                if not (isinstance(item, tuple) and len(item) == 2):
                    continue
                name, payload = item
                if name == STATS:
                    self.last_stats = dict(payload)
                    continue
                if name == BOOTED:
                    self.boot_report = dict(payload)
                    continue
                if isinstance(payload, dict):
                    ts = payload.get("timestamp")
                    if isinstance(ts, (int, float)):
                        d = time.time() - float(ts)
                        if 0.0 <= d < 300.0:
                            self.money_lag.append(d)
                if isinstance(payload, dict) and mark_inbound is not None:
                    event_id = str(payload.get("event_id") or "")
                    if event_id:
                        mark_inbound(event_id)
                self.returned += 1
                try:
                    await publish(name, payload,
                                  publisher=str(payload.get("source") or self.group)
                                  if isinstance(payload, dict) else self.group)
                except Exception as exc:  # noqa: BLE001
                    _log.error("تعذّر إعادة نشر %s من محرّك %s: %s", name, self.group, exc)

    async def stop(self, timeout_s: float = 60.0) -> None:
        if self._process is None:
            return
        self.stop_flusher()
        try:
            self._inbox.put(STOP, timeout=2.0)
        except Exception:  # noqa: BLE001
            pass
        deadline = time.monotonic() + timeout_s
        while self._process.is_alive() and time.monotonic() < deadline:
            await asyncio.sleep(0.2)
        if self._process.is_alive():
            _log.error("محرّك %s لم يتوقّف خلال %.0f ث — يُنهى قسرًا", self.group, timeout_s)
            self._process.terminate()
            await asyncio.sleep(1.0)
            if self._process.is_alive():
                self._process.kill()
        for pool in (self._money_pool, self._cold_pool):
            try:
                pool.shutdown(wait=False, cancel_futures=True)
            except Exception:  # noqa: BLE001
                pass
        for q in (self._inbox, self._outbox, self._out_storage, self._out_obs):
            try:
                q.cancel_join_thread()
                q.close()
            except Exception:  # noqa: BLE001
                pass

    def stats(self) -> dict[str, Any]:
        return {
            "group": self.group,
            "pid": self._process.pid if self._process is not None else None,
            "alive": self.is_alive(),
            "symbols": sorted(self.symbols),
            "atoms": len(self.hosted_atom_ids),
            "loaded": len(self.boot_report.get("loaded") or []),
            "failed": list(self.boot_report.get("failed") or []),
            "boot_s": self.boot_report.get("boot_s"),
            "uptime_s": round(time.time() - self.started_at, 1) if self.started_at else None,
            "sent": self.sent, "send_dropped": self.send_dropped,
            "batches_sent": self.batches_sent, "returned": self.returned,
            "returned_storage": self.returned_storage, "returned_obs": self.returned_obs,
            "classification": self.classification_sent,
            "money_lag": _pct(self.money_lag),
            "q_money": _qsize(self._outbox), "q_storage": _qsize(self._out_storage),
            "q_obs": _qsize(self._out_obs),
            "pending": len(self._pending),
            "child": self.last_stats,
        }


class SymbolRouter:
    """يوزّع الأحداث على محرّكات الرموز، ويبثّ العموديّ للجميع.

    **القاعدة:** حدثٌ يحمل رمزًا يذهب إلى مالك ذلك الرمز وحده. وحدثٌ بلا رمز
    (الساعة · الحساب · المحفظة · حدود المخاطر) يُبثّ إلى **كلّ** المحرّكات —
    وهو ١١٪ من الحركة مقيسًا، فالبثّ العامّ رخيص.

    والرمز غير المملوك يُسنَد بالورود إلى أقلّ المحرّكات حملًا وتبقى الخريطة
    ثابتة إلى نهاية التشغيلة (§١٣: القسم لا يتنقّل بعد بدء التشغيل).
    """

    def __init__(self, engines: list, broadcast_prefixes: Iterable[str] = ()) -> None:
        self.engines = list(engines)
        self.broadcast_prefixes = tuple(str(p) for p in broadcast_prefixes)
        self._owner: dict[str, Any] = {}
        for eng in self.engines:
            for sym in eng.symbols:
                self._owner[sym] = eng
        self.routed = 0
        self.broadcast = 0
        self.unowned_assigned = 0

    def owner_of(self, symbol: str):  # noqa: ANN201
        eng = self._owner.get(symbol)
        if eng is not None:
            return eng
        if not self.engines:
            return None
        # رمزٌ جديد: أقلّ المحرّكات رموزًا، وتثبت الخريطة بعدها.
        eng = min(self.engines, key=lambda e: len(self._owner_symbols(e)))
        self._owner[symbol] = eng
        self.unowned_assigned += 1
        _log.info("الرمز %s أُسنِد إلى محرّك %s (إسنادٌ بالورود، يثبت للتشغيلة)",
                  symbol, eng.group)
        return eng

    def _owner_symbols(self, eng) -> list:  # noqa: ANN001
        return [s for s, e in self._owner.items() if e is eng]

    def dispatch(self, event_name: str, body: Any) -> bool:
        """يوجّه حدثًا. يعيد True إن أُرسل إلى محرّك أو أكثر."""
        if not self.engines:
            return False
        symbol = str(body.get("symbol") or "") if isinstance(body, dict) else ""
        if symbol:
            eng = self.owner_of(symbol)
            if eng is not None:
                eng.send(event_name, body)
                self.routed += 1
                return True
            return False
        if self.broadcast_prefixes and not event_name.startswith(self.broadcast_prefixes):
            return False
        for eng in self.engines:
            eng.send(event_name, body)
        self.broadcast += 1
        return True

    def stats(self) -> dict[str, Any]:
        return {
            "engines": len(self.engines),
            "routed": self.routed,
            "broadcast": self.broadcast,
            "unowned_assigned": self.unowned_assigned,
            "owners": {sym: eng.group for sym, eng in sorted(self._owner.items())},
            "workers": [eng.stats() for eng in self.engines],
        }
