"""سجلّ كلّ عمليّةٍ ابنة في مجلّدٍ خاصّ بها — فلا تدوّر عمليّةٌ ملفًّا مفتوحًا في أخرى.

٢٠٢٦-٠٩-٢٤ (ختم المالك «صلح nq تأكد أنه مافي تخبيص»): `core.logger.configure()`
يضيف `TimedRotatingFileHandler(<مجلّد السجلّ>/core.log, when="midnight")` في كلّ
عمليّةٍ تستدعيه — المحرّك والعمليّة الباردة وعمليّات الرموز — فتكتب كلّها في
الملفّ نفسه. والتدوير منتصف الليل إعادةُ تسمية، وويندوز يرفض إعادة تسمية ملفٍّ
مفتوحٍ في عمليّةٍ أخرى. مقيس ليلة ٢٣→٢٤ أيلول: آخر سطر في `core.log.2026-09-23`
عند ٢٣:٥٩:٣٧، وأوّل سطر في `core.log` الجديد عند ٠٠:٢٤:٤٣ — وهو أوّل ما كتبته
العمليّة الباردة (٧٠٢ و٧٢٠ مع أوّل صفقة)، فدوّرت هي. وضاع ما بينهما من المحرّك
كلّه: ٢٥ دقيقة.

العلاج خارج النواة: قبل أن تُعِدّ العمليّة الابنة سجلّها، يوجَّه
`QUANT_CORE_LOG_DIR` في بيئتها هي وحدها إلى مجلّدٍ فرعيّ باسمها، ويُحلّ المجلّد
الأب بالتعبير نفسه الذي يحلّ به `core.logger.configure` مجلّده. فيبقى `core.log`
للمحرّك، و`cold/core.log` للعمليّة الباردة، و`symbol-<المجموعة>/core.log` لكلّ
عمليّة رموز — كلٌّ يدوّر ملفّه وحده. ولا يقرأ `core.log` أيّ كودٍ في المشروع.
"""
from __future__ import annotations

import asyncio
import atexit
import copy
import logging
import logging.handlers
import os
import queue
import re
import threading
from pathlib import Path
from typing import Any

_isolated: Path | None = None
_listener: logging.handlers.QueueListener | None = None


def isolate_log_dir(name: str) -> Path:
    """يوجّه سجلّ هذه العمليّة إلى `<مجلّد السجلّ>/<name>` ويعيد المسار.

    يُنادى في العمليّة الابنة وحدها، قبل `core.logger.configure()`. والنداء
    الثاني في العمليّة نفسها لا يعشّش مجلّدًا داخل مجلّد.
    """
    global _isolated
    if _isolated is not None:
        return _isolated
    from core import logger as core_logger  # قراءةُ دالّةٍ من النواة، لا تعديل
    current = os.environ.get("QUANT_CORE_LOG_DIR")
    parent = Path(current).expanduser() if current else core_logger._default_log_dir()
    safe = re.sub(r"[^\w.-]+", "_", str(name)).strip("._") or "child"
    target = parent / safe
    os.environ["QUANT_CORE_LOG_DIR"] = str(target)
    _isolated = target
    return target


# ── السجلّ لا يحجز الحلقة ──────────────────────────────────────────────────
#
# 🔴 ٢٠٢٦-٠٩-٢٥ (ختم المالك «Nq كل إصلاحات» وأمره «اقفل كل مشاكل») — مِرقاب الحلقة
# (`NQ_LOOP_WATCH=1.0`) سمّى سطر التجمّد: 99.25٪ من عيّنات تجمّدٍ طوله 17.6ث ثمّ
# 23.2ث في سطرٍ واحد — تحذير 618 «purge failed» — والإطار الأعلى `logging … flush`.
# أي أنّ حلقة المنصّة كلّها كانت تنتظر **كتابةَ سطر سجلّ**: `core.logger.configure`
# يكتب في نافذة النواة (`StreamHandler(sys.stdout)`، ونافذتها `CREATE_NEW_CONSOLE`)
# وفي `core.log`، وكلاهما على خيط الحلقة نفسه. ونافذة ويندوز توقف كلَّ من يكتب
# إليها ما دامت في وضع التحديد (`QuickEdit=1` في `HKCU\Console`) أو ما دامت عالقة.
# ومقيسٌ قبله: 13 مهلة دورة بعد إقلاع 10:32، و«المصدران صامتان 36ث»، ومضخّة 622
# دورتها 46ث — والسجلّ نفسه 15–50 سطرًا في الدقيقة، فليس حجمًا.
#
# العلاج خارج النواة: معالجاتُ السجلّ تنتقل إلى خيطٍ واحد خلف طابور
# (`QueueListener`)، والحلقة تضع السطر في الطابور وتمضي. فإن علقت النافذة علق
# الخيطُ وحده وتراكم الطابور، ولا تتوقّف المنصّة. ولا يضيع شيء ممّا يكتبه
# `_JsonFormatter`: رقمُ الأثر يُقرأ من سياق الحلقة لحظةَ الوضع ويُعاد في الخيط قبل
# التنسيق، والخطأ وتتبّعه يبقيان كما هما، والترتيب واحد (طابورٌ واحد وخيطٌ واحد).


class _LoopSafeQueueHandler(logging.handlers.QueueHandler):
    """يضع السطر في الطابور ومعه رقم الأثر من سياق الحلقة — بلا أيّ كتابة."""

    def prepare(self, record: logging.LogRecord) -> logging.LogRecord:
        from core.logger import current_trace_id  # قراءةٌ من النواة، لا تعديل
        record = copy.copy(record)
        # الرسالة تُدمج هنا كي لا تتغيّر معاملاتُها قبل أن يصلها الخيط.
        record.msg = record.getMessage()
        record.args = None
        record.nq_trace_id = current_trace_id.get()
        return record


class _TraceQueueListener(logging.handlers.QueueListener):
    """يعيد رقم الأثر إلى سياق خيط الكتابة، فيقرؤه `_JsonFormatter` كما كان."""

    def handle(self, record: logging.LogRecord) -> None:
        from core.logger import current_trace_id
        token = current_trace_id.set(getattr(record, "nq_trace_id", None))
        try:
            super().handle(record)
        finally:
            current_trace_id.reset(token)


def make_logging_nonblocking(name: str = "quant_nq.core") -> bool:
    """ينقل كتابة سجلّ هذه العمليّة إلى خيطٍ خلف طابور. يُنادى مرّةً قبل الحلقة.

    يُعِدّ سجلّ النواة أوّلًا (`configure` لا يعيد الإعداد إن سبق)، ثمّ يأخذ
    معالجاته كما هي — النافذة والملفّ — ويضعها خلف `QueueListener`. والنداء الثاني
    لا يفعل شيئًا.
    """
    global _listener
    if _listener is not None:
        return False
    from core import logger as core_logger  # نداءُ دالّةٍ من النواة، لا تعديل
    core_logger.configure()
    root = logging.getLogger(name)
    handlers = [h for h in root.handlers
                if not isinstance(h, logging.handlers.QueueHandler)]
    if not handlers:
        return False
    channel: queue.SimpleQueue = queue.SimpleQueue()
    listener = _TraceQueueListener(channel, *handlers, respect_handler_level=True)
    for handler in handlers:
        root.removeHandler(handler)
    root.addHandler(_LoopSafeQueueHandler(channel))
    listener.start()
    atexit.register(_stop_listener)
    _listener = listener
    return True


def _stop_listener() -> None:
    """يفرغ الطابور ويغلق الخيط عند الخروج — مرّةً واحدة ولو نودي مرّتين."""
    global _listener
    listener, _listener = _listener, None
    if listener is not None and getattr(listener, "_thread", None) is not None:
        listener.stop()

# ── مرحّل سجلّ المحرّك إلى 719 ─────────────────────────────────────────────────
#
# ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): 719 (سجلّ الأخطاء) نُقلت إلى العمليّة الباردة يوم
# ٠٩-١٨ ومعالجُها مسجّلُ عمليّتها وحدها، فعميت عن المحرّك: مقيسٌ اليوم 21,721 WARNING و262
# ERROR في `core.log` الحارّ وصفرٌ منها في `errors-*.log`. المرحّل يجمع WARNING فما فوق بمفتاح
# القالب وينشرها دفعةً كلّ 5 ث على `system.log.record` الذي تسمعه 719 v1.2.0.

EVENT_LOG_RECORD = "system.log.record"


class LogRecordRelay(logging.Handler):
    """يجمع WARNING فما فوق من مسجّل النواة بمفتاح القالب، ويُسلّمها دفعةً كلّ `every_s`.

    `emit` يجري على خيط من يكتب السطر (حلقة المحرّك غالبًا): قاموسٌ تحت قفل، بلا إدخال
    ولا إخراج — لا يحجب الحلقة. المفتاح (المسجّل، المستوى، قالب الرسالة قبل المعاملات):
    ‏«453 evidence USTEC: buy=…» بأرقامه المتغيّرة مفتاحٌ واحد يُكتب مرّةً بعدّاده.
    والسقف `max_keys` لكلّ نافذة: ما زاد يُعدّ في `dropped` ولا يُحمل.
    """

    def __init__(self, every_s: float = 5.0, max_keys: int = 200) -> None:
        super().__init__(level=logging.WARNING)
        self.every_s = float(every_s)
        self.max_keys = int(max_keys)
        self._lock = threading.Lock()
        self._pending: dict[tuple, dict[str, Any]] = {}
        self.dropped = 0
        self.forwarded = 0

    def emit(self, record: logging.LogRecord) -> None:  # noqa: D102
        try:
            key = (record.name, record.levelno, str(record.msg)[:160])
            with self._lock:
                item = self._pending.get(key)
                if item is not None:
                    item["repeats"] += 1
                    item["created"] = record.created
                    item["message"] = record.getMessage()[:4000]
                    return
                if len(self._pending) >= self.max_keys:
                    self.dropped += 1
                    return
                atom_id = getattr(record, "atom_id", None)
                self._pending[key] = {
                    "level": record.levelname, "logger": record.name,
                    "atom_id": atom_id if isinstance(atom_id, int) else None,
                    "message": record.getMessage()[:4000], "created": record.created,
                    "repeats": 1, "process": "hot"}
        except Exception:  # noqa: BLE001 — سطر سجلٍّ لا يُسقط من كتبه
            pass

    def take(self) -> list[dict[str, Any]]:
        with self._lock:
            items = list(self._pending.values())
            self._pending.clear()
        return items


def install_log_relay(event_bus: Any, name: str = "quant_nq.core",
                      every_s: float = 5.0) -> LogRecordRelay:
    """يعلّق المرحّل على مسجّل النواة ويطلق مهمّة تسليمٍ دوريّة على حلقة المحرّك."""
    relay = LogRecordRelay(every_s=every_s)
    logging.getLogger(name).addHandler(relay)

    async def _pump() -> None:
        while True:
            await asyncio.sleep(relay.every_s)
            for payload in relay.take():
                try:
                    await event_bus.publish(EVENT_LOG_RECORD, payload, publisher="core.log_relay")
                    relay.forwarded += 1
                except Exception:  # noqa: BLE001 — لا يُسجَّل هنا: لا حلقة سجلٍّ على نفسه
                    relay.dropped += 1

    relay.task = asyncio.get_running_loop().create_task(_pump(), name="nq-log-relay")
    return relay
