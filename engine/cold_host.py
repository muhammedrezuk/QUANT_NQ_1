"""العمليّة الباردة — المخازن والقياس والمراقبة خارج مفسّر المحرّك.

§٢١ من ورقة المحرّك: «الـUI والتخزين والمراقبة لا يُسمح لهم بلمس الطريق
الساخن… والـCold لا يشارك lock أو mailbox مع Hot». والمقيس قبل هذا الملفّ:
المسار البارد داخل عمليّة المحرّك يأخذ ≈ ٣٠٪ من الحلقة (ثلاثة مشترِكين عامّين
× ١٬٨٠٠ حدث/ث، ومخازن بـsqlite وVACUOM في معالجاتها)، وخيوطه تحمل قفل
المفسّر (GIL) فتزاحم دورة التِكّة. عمليّةٌ مستقلّة تنهي المزاحمة بنيويًّا.

**العقد — لا IPC في المسار الساخن:**

    المحرّك  ──(صندوق وارد، إيداعٌ بلا انتظار)──▶  العمليّة الباردة
    المحرّك  ◀──(صندوق صادر، قارئٌ في خيط)────────  ما تنشره ذرّاتها

الإيداع `put_nowait`: إن امتلأ الصندوق سقط الحدث **للبارد وحده** وعُدّ باسمه
— دورة التِكّة لا تنتظر أحدًا. وما تنشره الذرّات الباردة (حالات القياس، أوامر
مفتاح الإيقاف 860، أوامر المالك 901، `storage.*_saved`) يعود إلى المحرّك جذرًا
عاديًّا بهويّته، ولا يُعاد إرساله إليها (كشف الصدى بهويّة الحدث).

**ما في العمليّة:** مُقلعٌ ومدير صحّة ومحرّك لقطات وسجلٌّ خاصّ بها، على ناقلٍ
`OwnedEventBus` بمساراته — أي ما كانت تعمل عليه هذه الذرّات أصلًا، في مفسّرٍ
له نواةٌ لنفسه. الذرّات لا تُلمس.
"""
from __future__ import annotations

import asyncio
import logging
import multiprocessing as mp
import os
import queue as queue_module
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any, Callable, Iterable

PROJECT_ROOT = Path(__file__).resolve().parents[1]

#: رسائل التحكّم على الصندوقين — قيمٌ لا تلتبس بأحداث.
STOP = "__cold_stop__"
STATS = "__cold_stats__"
BOOTED = "__cold_booted__"

_log = logging.getLogger("quant_nq.core.cold_host")


# ═══════════════════════════ جسم العمليّة الباردة ═══════════════════════════

def _drain(inbox: Any, first_timeout_s: float, batch: int) -> list:
    """يسحب دفعةً من الصندوق في خيط: أوّل عنصرٍ بانتظار، والبقيّة بلا انتظار."""
    items: list = []
    # ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): `ValueError` هو ما يرفعه صندوقٌ أُغلق —
    # وإعادة إقلاع الابنة تُغلق صندوقيها القديمين. لا يُسقط مضخّة الصادر.
    try:
        items.append(inbox.get(timeout=first_timeout_s))
    except (queue_module.Empty, EOFError, OSError, ValueError):
        return items
    for _ in range(batch - 1):
        try:
            items.append(inbox.get_nowait())
        except (queue_module.Empty, EOFError, OSError, ValueError):
            break
    return items


def _watch_parent(on_death: Callable[[], None]) -> threading.Thread | None:
    """خيطٌ نائمٌ على مقبض العمليّة الأمّ، يستيقظ مرّةً واحدة حين تموت فينادي `on_death`.

    ٢٠٢٦-١٠-٢٦ (ختم المالك «nq»): الأنبوب لا يشهد بموت الأمّ. الصندوق يُخلَّل إلى
    الابنة بطرفيه كليهما (`Queue.__getstate__` يحمل `_reader` و`_writer`)، فلا ينقطع
    ما دامت الابنة حيّة. المقيس (تجربة الأنبوب في مسودّة الإيقاف): بعد قتل الأمّ رأى
    القارئ «فارغ» 144 مرّة في ثماني ثوانٍ ولا خطأ أنبوبٍ واحدًا. أمّا مقبض الأمّ
    (`parent_process().join()` انتظارٌ في النظام على مقبض عمليّتها) فاستيقظ بعد
    0.002 ث. لا دوران ولا قفل مشترك: الخيط نائمٌ حتّى تموت الأمّ.
    """
    parent = mp.parent_process()
    if parent is None:            # لم تُطلَق بـmultiprocessing — لا أمّ تُراقَب
        return None

    def _run() -> None:
        try:
            while parent.is_alive():
                parent.join()
        except Exception:  # noqa: BLE001 — المراقب لا يُسقط العمليّة
            return
        try:
            on_death()
        except Exception:  # noqa: BLE001
            pass

    thread = threading.Thread(target=_run, name="cold-parent-watch", daemon=True)
    thread.start()
    return thread


def _atom_view(record: Any) -> dict[str, Any]:
    """صورة ذرّةٍ باردة كما تعرضها `/api/atoms` للجذر — بالحقول نفسها."""
    health = record.last_health
    manifest = record.manifest
    return {
        "name": getattr(manifest, "name", None),
        "version": str(getattr(manifest, "version", "") or ""),
        "critical": bool(getattr(record, "critical", False)),
        "state": getattr(record.state, "value", str(record.state)),
        "health": ({"state": getattr(health.state, "value", str(health.state)),
                    "message": health.message} if health is not None else None),
        "restart_count": int(getattr(record, "restart_count", 0) or 0),
        "last_error": record.last_error,
        "metadata": dict(getattr(manifest, "metadata", None) or {}),
    }


async def _cold_async(inbox: Any, outbox: Any, cfg: dict) -> None:
    from core import logger as core_logger
    from core.bootloader import Bootloader
    from core.health_manager import HealthManager
    from core.journal import Journal
    from core.lifecycle import call_lifecycle
    from core.metrics import Metrics
    from core.registry import Registry
    from core.snapshot_engine import SnapshotEngine
    from transport.owned_event_bus import OwnedEventBus

    core_logger.configure(level=getattr(logging, str(cfg.get("log_level", "INFO")).upper(), logging.INFO),
                          json_output=bool(cfg.get("log_json", True)))
    log = logging.getLogger("quant_nq.core.cold_host")
    atom_ids = {int(v) for v in cfg["atom_ids"]}
    id_names = {str(v) for v in atom_ids}
    atoms_root = Path(cfg["atoms_root"])

    registry = Registry()
    bus = OwnedEventBus(
        payload_mode="shared_readonly",
        worker_count=max(2, int(cfg.get("lanes", 4))),
        partitioned_ownership=False,
        mailbox_max_events=int(cfg.get("mailbox_max_events", 4096)),
        cold_sections=(),
        scope_groups=1,
        critical_prefixes=tuple(cfg.get("critical_prefixes") or ()),
    )
    journal = Journal(path=Path(cfg["journal_path"]) if cfg.get("journal_path") else None)
    metrics = Metrics()
    health = HealthManager(registry, bus, journal, metrics)
    snapshot = SnapshotEngine(registry, Path(cfg["snapshot_dir"])) if cfg.get("snapshot_dir") else None

    async def _restore(atom_id: int) -> None:
        if snapshot is not None:
            await snapshot.restore_one(atom_id)

    bootloader = Bootloader(atoms_root, registry, bus, journal, metrics,
                            health_manager=health, restore_hook=_restore)
    t0 = time.perf_counter()
    report = await bootloader.boot(include_ids=set(atom_ids))
    loaded = sorted(r.id for r in registry.all())
    counters = {"inbound": 0, "inbound_batches": 0, "outbound": 0, "outbound_dropped": 0,
                "echo_suppressed": 0, "snapshots": 0, "snapshot_failed": 0}
    # الأحداث التي لها مشترِكٌ **محدّد** هنا (لا `subscribe_all`): ما عداها يكفيه
    # الرأس — المشترِكان العامّان (001 المراقب · 810 ناقل القياس) يقرآن الرأس وحده.
    try:
        specific = sorted(str(n) for n in bus.event_names())
    except Exception:  # noqa: BLE001
        specific = []
    outbox.put((BOOTED, {
        "pid": os.getpid(), "loaded": loaded, "failed": list(report.failed),
        "subscribed_events": specific,
        "excluded": list(report.excluded), "boot_s": round(time.perf_counter() - t0, 2),
        "failed_reasons": {int(i): (registry.find(int(i)).last_error if registry.find(int(i)) else None)
                           for i in report.failed},
    }))
    log.info("العمليّة الباردة أقلعت: %d ذرّة من %d خلال %.1f ث (فشل %s)",
             len(loaded), len(atom_ids), time.perf_counter() - t0, list(report.failed))

    #: هويّات ما دخل من المركز — لا يعود إليه ولو أعاد نشره مشترِكٌ هنا.
    inbound_ids: "OrderedDict[str, None]" = OrderedDict()

    async def collector(name: str, payload: Any) -> None:
        if not isinstance(payload, dict):
            return
        if str(payload.get("source") or "") not in id_names:
            return                                  # ليس من ذرّاتنا — لا يعبر
        event_id = str(payload.get("event_id") or "")
        if event_id and event_id in inbound_ids:
            counters["echo_suppressed"] += 1
            return
        try:
            outbox.put_nowait((name, dict(payload)))
            counters["outbound"] += 1
        except queue_module.Full:
            counters["outbound_dropped"] += 1

    bus.subscribe_all(collector, subscriber="cold:egress", isolate_payload=False)

    loop = asyncio.get_running_loop()
    stopping = asyncio.Event()

    # ── القارئ: خيطٌ دائم على الصندوق يسلّم دفعاتٍ إلى الحلقة ──────────────
    # المقيس 15:41: جولات `run_in_executor` الصغيرة سحبت ≈ ١٬٣٠٠ حدث/ث فامتلأ
    # الصندوق (٢٠٬٠٠٠) وسقط ربع أحداث التخزين، والعمليّة عند ٣٧٪ معالج فقط.
    # الخيط يحجب على `get()` ويجمّع دفعةً (حتّى ٢٠٠ عنصر أو ٢٠ م.ث)، وفتحات
    # الدفعات محدودة: إن تأخّرت الحلقة توقّف الخيط عن السحب فيمتلئ الصندوق
    # عند المُرسل ويُعدّ الإسقاط هناك — لا يُبتلع.
    batch_max = int(cfg.get("batch", 200))
    batches: asyncio.Queue = asyncio.Queue()
    slots = threading.Semaphore(int(cfg.get("batch_slots", 32)))
    reader_stop = threading.Event()

    def _hand_over(items: list) -> None:
        try:
            batches.put_nowait(items)
        except Exception:  # noqa: BLE001 — الحلقة تُغلق
            slots.release()

    def reader() -> None:
        pending: list = []
        last = time.perf_counter()
        while not reader_stop.is_set():
            try:
                item = inbox.get(timeout=0.05)
            except (queue_module.Empty, EOFError, OSError):
                item = None
            if item is not None:
                if isinstance(item, list):
                    pending.extend(item)          # دفعةٌ من الأمّ
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

    reader_thread = threading.Thread(target=reader, name="cold-inbox-reader", daemon=True)
    reader_thread.start()

    # ── موت الأمّ (٢٠٢٦-١٠-٢٦، ختم المالك «nq») ────────────────────────────
    # كانت هذه العمليّة لا تنتبه لموت النواة: تبقى يتيمةً تكتب في المخازن، وتولد
    # بجانبها باردةٌ ثانية في الإقلاع التالي. الآن حين تموت الأمّ يُوضع STOP في
    # الطريق نفسه الذي يضعه فيه القارئ حين تُرسله الأمّ، فيخرج الجسم بإيقافه
    # النظيف كما هو أدناه (توقّف الذرّات ⟵ لقطة ساكنة ⟵ إغلاق). وقبله يُلغى انتظار
    # خيطَي تغذية الصندوقين عند الخروج: لا أحد يقرأ الصادر بعد موت الأمّ، فيمتلئ
    # الأنبوب ويعلق خيط التغذية، والمفسّر عند خروجه كان سينتظره إلى الأبد (العطب
    # نفسه المقيس في الأمّ 16:01، انظر `ColdProcess.stop`). وإن ماتت الأمّ والإيقاف
    # النظيف جارٍ أصلًا، فـSTOP الثاني لا يقرؤه أحد، ويبقى إلغاء الانتظار وحده.
    def _on_parent_death() -> None:
        for q in (inbox, outbox):
            try:
                q.cancel_join_thread()
            except Exception:  # noqa: BLE001
                pass
        log.warning("العمليّة الأمّ (النواة) ماتت — العمليّة الباردة تتوقّف نظيفًا بطريقها المعتاد")
        try:
            # بلا أخذ فتحة: المضخّة تُطلق فتحةً زائدة واحدة ونحن نُغلق — لا أثر.
            loop.call_soon_threadsafe(batches.put_nowait, [STOP])
        except RuntimeError:
            pass                                    # الحلقة أُغلقت: الإيقاف جارٍ أصلًا

    _watch_parent(_on_parent_death)

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
                counters["inbound"] += 1
                if isinstance(payload, dict):
                    event_id = str(payload.get("event_id") or "")
                    if event_id:
                        inbound_ids[event_id] = None
                        if len(inbound_ids) > 200_000:
                            inbound_ids.popitem(last=False)
                    publisher = str(payload.get("source") or "cold_host.ingress")
                else:
                    publisher = "cold_host.ingress"
                try:
                    await bus.publish(name, payload, publisher=publisher)
                except Exception as exc:  # noqa: BLE001 — حدثٌ معطوب لا يُسقط العمليّة
                    log.error("تعذّر نشر %s في العمليّة الباردة: %s", name, exc)

    async def stats_loop() -> None:
        every = float(cfg.get("stats_every_s", 5.0))
        while not stopping.is_set():
            try:
                await asyncio.wait_for(stopping.wait(), timeout=every)
            except asyncio.TimeoutError:
                pass
            try:
                ts = bus.transport_stats()
                rt = ts.get("runtime") or {}
                rss = None
                try:
                    import psutil
                    rss = round(psutil.Process().memory_info().rss / 1e6, 1)
                except Exception:  # noqa: BLE001
                    pass
                outbox.put_nowait((STATS, {
                    "pid": os.getpid(), "at": time.time(), "cpu_s": round(time.process_time(), 2),
                    "rss_mb": rss, "counters": dict(counters),
                    "lanes": [{k: w.get(k) for k in ("worker_id", "queued", "dropped", "coalesced", "processed", "busy_s_total")}
                              for w in (rt.get("workers") or [])],
                    "critical_dropped_by_event": rt.get("critical_dropped_by_event"),
                    "overrun_by_subscriber": ts.get("overrun_by_subscriber"),
                    "atoms": {str(r.id): getattr(r.state, "value", str(r.state)) for r in registry.all()},
                    # ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): كان يُصدَّر `state` وحده
                    # («running» دائمًا)، فصحّة 32 ذرّة باردة — منها 901 بوّابة أوامر
                    # المالك و707 — لا تصل أحدًا. الآن الصحّة ورسالتها كما يراها
                    # مدير صحّة العمليّة، والجذر يعرضها في `/api/atoms`.
                    "atom_health": {str(r.id): _atom_view(r) for r in registry.all()},
                }))
            except queue_module.Full:
                pass
            except Exception as exc:  # noqa: BLE001
                log.warning("تعذّر إرسال إحصاءات العمليّة الباردة: %s", exc)

    async def snapshot_loop() -> None:
        every = float(cfg.get("snapshot_every_s", 60.0))
        while snapshot is not None and not stopping.is_set():
            try:
                await asyncio.wait_for(stopping.wait(), timeout=every)
                break
            except asyncio.TimeoutError:
                pass
            try:
                rep = await snapshot.snapshot_all()
                counters["snapshots"] += len(rep.captured)
                counters["snapshot_failed"] += len(rep.failed)
            except Exception as exc:  # noqa: BLE001
                log.warning("فشل اللقطة الدوريّة الباردة: %s", exc)

    tasks = [asyncio.create_task(pump(), name="cold-pump"),
             asyncio.create_task(stats_loop(), name="cold-stats"),
             asyncio.create_task(snapshot_loop(), name="cold-snapshot")]
    await stopping.wait()
    reader_stop.set()
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)

    # إيقافٌ نظيف بترتيبٍ عكسيّ: توقّف ⟵ لقطة ساكنة ⟵ إغلاق.
    await health.stop()
    for record in reversed(list(registry.all())):
        try:
            await call_lifecycle(record.instance.stop(), "stop", timeout=10.0)
        except Exception as exc:  # noqa: BLE001
            log.error("فشل إيقاف الذرّة الباردة %s: %s", record.id, exc)
    if snapshot is not None:
        try:
            await snapshot.snapshot_all()
        except Exception as exc:  # noqa: BLE001
            log.warning("فشل لقطة الإغلاق الباردة: %s", exc)
    for record in reversed(list(registry.all())):
        try:
            await call_lifecycle(record.instance.shutdown(), "shutdown", timeout=10.0)
        except Exception as exc:  # noqa: BLE001
            log.error("فشل shutdown للذرّة الباردة %s: %s", record.id, exc)
    try:
        await bus.drain(timeout_s=5.0)
    finally:
        await bus.close()
    log.info("العمليّة الباردة أُوقفت نظيفًا: %s", counters)


def _cold_main(inbox: Any, outbox: Any, cfg: dict) -> None:
    """نقطة دخول العمليّة الابنة — على مستوى الوحدة كي تُخلَّل بـ`spawn`."""
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
    os.environ.setdefault("PYTHONUTF8", "1")
    # ٢٠٢٦-٠٩-٢٤ (ختم المالك «صلح nq»): سجلّ هذه العمليّة في `cold/core.log` —
    # كانت تشارك المحرّكَ ملفّه فيفشل تدويره منتصف الليل (انظر process_logs).
    from .process_logs import isolate_log_dir, make_logging_nonblocking
    isolate_log_dir("cold")
    # ٢٠٢٦-٠٩-٢٥ — وكتابتُه خارج خيط حلقته، كالمحرّك (انظر process_logs).
    make_logging_nonblocking()
    try:
        asyncio.run(_cold_async(inbox, outbox, cfg))
    except KeyboardInterrupt:
        pass


# ═══════════════════════════ الطرف الأمّ (المحرّك) ═══════════════════════════

class ColdProcess:
    """مقبض العمليّة الباردة من جهة المحرّك: إقلاع · إيداع · قراءة الصادر · إحصاء · إيقاف."""

    def __init__(
        self,
        *,
        atom_ids: Iterable[int],
        atoms_root: str,
        snapshot_dir: str | None = None,
        journal_path: str | None = None,
        critical_prefixes: Iterable[str] = (),
        inbox_max: int = 20_000,
        outbox_max: int = 20_000,
        lanes: int = 4,
        log_level: str = "INFO",
        log_json: bool = True,
        batch_max: int = 200,
        flush_every_s: float = 0.02,
        restart_max: int = 3,
        restart_window_s: float = 600.0,
    ) -> None:
        self.hosted_atom_ids = sorted({int(v) for v in atom_ids})
        self._cfg = {
            "atom_ids": list(self.hosted_atom_ids), "atoms_root": str(atoms_root),
            "snapshot_dir": snapshot_dir, "journal_path": journal_path,
            "critical_prefixes": list(critical_prefixes), "lanes": int(lanes),
            "log_level": log_level, "log_json": log_json,
        }
        self._ctx = mp.get_context("spawn")
        self._inbox_max = int(inbox_max)
        self._outbox_max = int(outbox_max)
        self._inbox = self._ctx.Queue(maxsize=self._inbox_max)
        self._outbox = self._ctx.Queue(maxsize=self._outbox_max)
        # ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): الإشراف. كانت الابنة إن ماتت تبقى
        # ميتة — و`restarts` أدناه لا يُزاد في أيّ مكان فيُقرأ «لم تحتج إعادة» —
        # و`/api/health` يبقى `ok` وفيها بوّابة أوامر المالك 901. الآن: إعادة إقلاعٍ
        # محدودة (`restart_max` خلال `restart_window_s`)، ثمّ تُترك ساقطةً بصوت.
        self.restart_max = max(0, int(restart_max))
        self.restart_window_s = float(restart_window_s)
        self._restart_times: list[float] = []
        self.exhausted = False
        self.last_exit_code: int | None = None
        self.down_since: float | None = None
        self.lost_on_death = 0
        # بركة البارد وحده: تركن خيطًا نصف ثانية بلا أن تزاحم مالًا ولا ذرّة
        # (٢٠٢٦-٠٩-١٨ — فصل سياق التنفيذ).
        self._cold_pool = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="nq-cold-process")
        self._process: Any = None
        self.started_at = 0.0
        self.boot_report: dict[str, Any] = {}
        self.last_stats: dict[str, Any] = {}
        self.sent = 0
        self.send_dropped = 0
        self.returned = 0
        self.restarts = 0
        self.dead_detected = 0
        #: الدفعة المعلّقة — رسالةٌ واحدة عبر الصندوق لكلّ دفعة. المقيس ٢٠٢٦-٠٩-١٧
        #: 15:47: صندوق ويندوز يعالج رسالةً رسالة بكلفةٍ ثابتة فيسقُف عند
        #: ~١٬٢٠٠ حدث/ث مهما كبرت سعته (امتلأ 50,000 وسقط 9,912) — والدفعات
        #: تجعل الرسائل ~١٠٠/ث بدل ١٬٨٠٠/ث.
        self._pending: list = []
        self.batch_max = int(batch_max)
        self.flush_every_s = float(flush_every_s)
        self.batches_sent = 0
        self.batches_dropped = 0
        self._flusher: Any = None
        #: الأحداث التي لها مشترِكٌ محدّد في العمليّة الباردة — تُملأ من تقرير
        #: إقلاعها. `None` = لا نعرف بعد فيُرسَل كلّ شيء كاملًا.
        self.specific_events: frozenset[str] | None = None
        self.header_only_sent = 0

    # ── دورة الحياة ─────────────────────────────────────────────────────

    def spawn(self) -> None:
        self._process = self._ctx.Process(target=_cold_main, args=(self._inbox, self._outbox, self._cfg),
                                          name="nq-cold-host", daemon=False)
        self._process.start()
        self.started_at = time.time()

    async def wait_booted(self, timeout_s: float = 180.0) -> dict[str, Any]:
        """ينتظر تقرير إقلاع العمليّة — ولا يخمّن: بلا تقرير لا يُعلَن إقلاع."""
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            # قارئ الصادر قد يكون سحب تقرير الإقلاع قبلنا — يُقرأ منه لا
            # يُنتظر مرّتين. (العطب المقيس: المحرّك الثاني علّق 150 ث.)
            if self.boot_report:
                return self.boot_report
            items = await asyncio.get_running_loop().run_in_executor(
                self._cold_pool, _drain, self._outbox, 0.5, 50)
            for item in items:
                if isinstance(item, tuple) and item and item[0] == BOOTED:
                    self.boot_report = dict(item[1])
                    self.specific_events = frozenset(self.boot_report.get("subscribed_events") or ())
                    return self.boot_report
                if isinstance(item, tuple) and item and item[0] == STATS:
                    self.last_stats = dict(item[1])
            if self._process is not None and not self._process.is_alive():
                raise RuntimeError("العمليّة الباردة خرجت قبل أن تُقلع (رمز %s)" % self._process.exitcode)
        raise TimeoutError("العمليّة الباردة لم تُبلّغ إقلاعها خلال %.0f ث" % timeout_s)

    def is_alive(self) -> bool:
        return self._process is not None and self._process.is_alive()

    # ── الإشراف (٢٠٢٦-١٠-٠٢، ختم المالك «صلح كامل nq») ─────────────────────

    def exit_code(self) -> int | None:
        return self._process.exitcode if self._process is not None else None

    def restarts_in_window(self) -> int:
        now = time.monotonic()
        return sum(1 for t in self._restart_times if now - t < self.restart_window_s)

    def restart_after_death(self) -> str:
        """يُنادى حين تُرى الابنة ميتة. يعيد:

        `restarted` — أُقلعت ابنةٌ جديدة · `exhausted` — نفدت الإعادات الآن (مرّةً واحدة)
        · `down` — نفدت من قبل وما زالت ساقطة · `alive` — لا موت أصلًا.
        """
        if self._process is None or self._process.is_alive():
            return "alive"
        if self.exhausted:
            return "down"
        self.last_exit_code = self._process.exitcode
        if self.down_since is None:
            self.down_since = time.time()
        if self.restarts_in_window() >= self.restart_max:
            self.exhausted = True
            return "exhausted"
        self._restart_times = [t for t in self._restart_times
                               if time.monotonic() - t < self.restart_window_s]
        self._restart_times.append(time.monotonic())
        self._respawn()
        self.restarts += 1
        return "restarted"

    def _respawn(self) -> None:
        """ابنةٌ جديدة على صندوقين جديدين.

        الصندوقان القديمان لا يُعاد استعمالهما: قفل القراءة في `mp.Queue` سيمافور
        بين العمليّتين، وابنةٌ قُتلت وهي تقرأ تتركه مأخوذًا فتعلق الجديدة عليه
        للأبد. وما بقي في الصادر القديم من الميتة يُترك، وما في الوارد القديم
        لم يقرأه أحد فيُعدّ مفقودًا باسمه (`lost_on_death`). والدفعة المعلّقة التي
        لم تُودَع بعد تذهب إلى الابنة الجديدة.
        """
        old = (self._inbox, self._outbox)
        lost = self._safe_qsize(old[0])
        if lost:
            self.lost_on_death += lost
        self._inbox = self._ctx.Queue(maxsize=self._inbox_max)
        self._outbox = self._ctx.Queue(maxsize=self._outbox_max)
        for q in old:
            try:
                q.cancel_join_thread()
                q.close()
            except Exception:  # noqa: BLE001
                pass
        self.boot_report = {}
        self.specific_events = None
        self.last_stats = {}
        self.spawn()

    def supervision(self) -> dict[str, Any]:
        return {
            "restarts": self.restarts,
            "restart_max": self.restart_max,
            "restart_window_s": self.restart_window_s,
            "restarts_in_window": self.restarts_in_window(),
            "exhausted": self.exhausted,
            "last_exit_code": self.last_exit_code,
            "down_since": self.down_since,
            "lost_on_death": self.lost_on_death,
        }

    #: إحصاءات الابنة كلّ 5 ث — أقدم من هذا وهي حيّة = صورةٌ لا تُصدَّق.
    STATS_STALE_S = 30.0

    def health_view(self) -> dict[str, Any]:
        """حالة العمليّة الباردة لـ`/api/health`: `ok` · `degraded` · `unhealthy`."""
        alive = self.is_alive()
        if not alive and self.exhausted:
            status, reason = "unhealthy", "COLD_PROCESS_DOWN"
        elif not alive:
            status, reason = "degraded", "COLD_PROCESS_DEAD_RESTART_PENDING"
        elif not self.boot_report:
            status, reason = ("degraded", "COLD_PROCESS_REBOOTING") if self.restarts else ("ok", "COLD_PROCESS_BOOTING")
        else:
            at = (self.last_stats or {}).get("at")
            stale = at is not None and time.time() - float(at) > self.STATS_STALE_S
            status, reason = ("degraded", "COLD_STATS_STALE") if stale else ("ok", "")
        return {"status": status, "reason": reason, "alive": alive,
                "pid": self._process.pid if self._process is not None else None,
                "booted": bool(self.boot_report), **self.supervision()}

    def atom_rows(self) -> list[dict[str, Any]]:
        """ذرّات العمليّة الباردة بصيغة `/api/atoms` نفسها، وعليها `process: cold`."""
        view = (self.last_stats or {}).get("atom_health") or {}
        at = (self.last_stats or {}).get("at")
        failed = {int(i) for i in (self.boot_report.get("failed") or [])}
        reasons = self.boot_report.get("failed_reasons") or {}
        health = self.health_view()
        rows: list[dict[str, Any]] = []
        for atom_id in self.hosted_atom_ids:
            seen = view.get(str(atom_id))
            row: dict[str, Any] = {
                "id": atom_id, "name": None, "version": None, "critical": False,
                "state": "starting", "health": None, "restart_count": 0,
                "last_error": None, "metadata": {},
            }
            if isinstance(seen, dict):
                row.update({k: seen.get(k, row.get(k)) for k in row if k != "id"})
            elif atom_id in failed:
                row.update(state="failed",
                           last_error=reasons.get(atom_id) or reasons.get(str(atom_id)))
            if health["status"] != "ok":
                # العمليّة نفسها ساقطة أو تُعاد أو صورتها بائتة — لا تُعرض صحّةٌ قديمة خضراء.
                row["state"] = "failed" if health["reason"] == "COLD_PROCESS_DOWN" else \
                    ("starting" if not health["alive"] or not health["booted"] else row["state"])
                row["health"] = {"state": "unhealthy" if health["status"] == "unhealthy" else "degraded",
                                 "message": "%s (exit=%s · restarts=%d/%d)" % (
                                     health["reason"], health["last_exit_code"],
                                     health["restarts_in_window"], health["restart_max"])}
            row["process"] = "cold"
            row["health_at"] = at
            rows.append(row)
        return rows

    HEADER_KEYS = ("timestamp", "source", "trace_id", "event_id", "parent_event_id",
                   "parent_event", "symbol", "account_id", "cycle_id", "section_id", "status")

    def send(self, event_name: str, body: Any) -> bool:
        """يضمّ الحدث إلى الدفعة المعلّقة — الحدث الساخن لا ينتظر البارد أبدًا.

        المقيس بـpy-spy 16:00: أنبوب العمليّة (تخليلٌ وكتابة) ≈ ٩٪ من معالج النواة.
        فالحدث الذي لا مشترِكَ محدّدًا له في العمليّة الباردة يُرسَل **رأسًا فقط**:
        المشترِكون العامّون هناك يقرؤون الرأس وحده (مقيس على 001 و810).
        """
        if isinstance(body, dict):
            if self.specific_events is not None and event_name not in self.specific_events:
                payload = {k: body[k] for k in self.HEADER_KEYS if k in body}
                payload["_header_only"] = True
                self.header_only_sent += 1
            else:
                payload = dict(body)
        else:
            payload = body
        self._pending.append((event_name, payload))
        self.sent += 1
        if len(self._pending) >= self.batch_max:
            self.flush()
        return True

    def flush(self) -> None:
        """يودع الدفعة المعلّقة رسالةً واحدة بلا انتظار؛ الامتلاء إسقاطٌ معدود."""
        if not self._pending:
            return
        batch, self._pending = self._pending, []
        try:
            self._inbox.put_nowait(batch)
            self.batches_sent += 1
        except queue_module.Full:
            self.send_dropped += len(batch)
            self.batches_dropped += 1
        except (ValueError, OSError):
            self.send_dropped += len(batch)
            self.batches_dropped += 1

    def start_flusher(self) -> None:
        """مهمّة تصريفٍ دوريّة على حلقة المحرّك — كلّ `flush_every_s`."""
        async def _run() -> None:
            while True:
                await asyncio.sleep(self.flush_every_s)
                self.flush()
        self._flusher = asyncio.get_running_loop().create_task(_run(), name="nq-cold-flusher")

    def stop_flusher(self) -> None:
        if self._flusher is not None:
            self._flusher.cancel()
            self._flusher = None
        self.flush()

    async def pump_outbound(self, publish: Callable[..., Any], *, mark_inbound: Callable[[str], None] | None = None,
                            on_dead: Callable[[], Any] | None = None) -> None:
        """يقرأ الصادر في خيط ويعيد نشره في المحرّك جذرًا بهويّته."""
        while True:
            items = await asyncio.to_thread(_drain, self._outbox, 0.25, 500)
            if not items:
                if self._process is not None and not self._process.is_alive():
                    self.dead_detected += 1
                    if on_dead is not None:
                        await on_dead()
                    await asyncio.sleep(1.0)
                continue
            for item in items:
                if not (isinstance(item, tuple) and len(item) == 2):
                    continue
                name, payload = item
                if name == STATS:
                    self.last_stats = dict(payload)
                    continue
                if name == BOOTED:
                    self.boot_report = dict(payload)
                    # ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): بعد إعادة الإقلاع لا ينتظر
                    # أحدٌ `wait_booted` — المضخّة هي من يقرأ التقرير، فتملأ ما كان يملؤه.
                    self.specific_events = frozenset(self.boot_report.get("subscribed_events") or ())
                    if self.restarts:
                        self.down_since = None
                        _log.warning("العمليّة الباردة أعادت الإقلاع (إعادة %d): %d ذرّة خلال %s ث · فشل %s",
                                     self.restarts, len(self.boot_report.get("loaded") or []),
                                     self.boot_report.get("boot_s"), self.boot_report.get("failed"))
                    continue
                if isinstance(payload, dict) and mark_inbound is not None:
                    event_id = str(payload.get("event_id") or "")
                    if event_id:
                        mark_inbound(event_id)
                self.returned += 1
                try:
                    await publish(name, payload, publisher=str(payload.get("source") or "cold_process")
                                  if isinstance(payload, dict) else "cold_process")
                except Exception as exc:  # noqa: BLE001
                    _log.error("تعذّر إعادة نشر %s من العمليّة الباردة: %s", name, exc)

    async def stop(self, timeout_s: float = 45.0) -> None:
        try:
            self._cold_pool.shutdown(wait=False, cancel_futures=True)
        except Exception:  # noqa: BLE001
            pass
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
            _log.error("العمليّة الباردة لم تتوقّف خلال %.0f ث — تُنهى قسرًا", timeout_s)
            self._process.terminate()
            await asyncio.sleep(1.0)
            if self._process.is_alive():
                self._process.kill()
        # المقيس 16:01: النواة أنهت إيقافها في ٤ ثوانٍ ثمّ **لم تخرج العمليّة**:
        # المفسّر عند الخروج ينتظر خيط تغذية الصندوق ليصرّف ما بقي في الأنبوب
        # إلى ابنةٍ ماتت. لا انتظار: الصندوقان يُغلقان ولا يُنضمّ إلى خيطيهما.
        for q in (self._inbox, self._outbox):
            try:
                q.cancel_join_thread()
                q.close()
            except Exception:  # noqa: BLE001
                pass

    # ── العرض ────────────────────────────────────────────────────────────

    def stats(self) -> dict[str, Any]:
        return {
            "pid": self._process.pid if self._process is not None else None,
            "alive": self.is_alive(),
            "hosted_atom_ids": list(self.hosted_atom_ids),
            "loaded": list(self.boot_report.get("loaded") or []),
            "failed": list(self.boot_report.get("failed") or []),
            "failed_reasons": self.boot_report.get("failed_reasons") or {},
            "boot_s": self.boot_report.get("boot_s"),
            "uptime_s": round(time.time() - self.started_at, 1) if self.started_at else None,
            "sent": self.sent,
            "send_dropped": self.send_dropped,
            "batches_sent": self.batches_sent,
            "batches_dropped": self.batches_dropped,
            "header_only_sent": self.header_only_sent,
            "specific_events": (len(self.specific_events) if self.specific_events is not None else None),
            "pending": len(self._pending),
            "returned": self.returned,
            "restarts": self.restarts,
            "dead_detected": self.dead_detected,
            "supervision": self.supervision(),
            "inbox_queued": self._safe_qsize(self._inbox),
            "outbox_queued": self._safe_qsize(self._outbox),
            "child": self.last_stats,
        }

    @staticmethod
    def _safe_qsize(q: Any) -> int | None:
        try:
            return int(q.qsize())
        except (NotImplementedError, OSError, ValueError):
            return None
