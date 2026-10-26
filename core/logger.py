"""
Core.logger
============
Article 14 (+ 20 في الدستور الأول): أي Logger يحمل Atom ID تلقائيًا،
ولا يُكتب يدويًا لكل ذرة.
"""

from __future__ import annotations

import json
import logging
import logging.handlers
import os
from pathlib import Path
import sys
import contextvars
from typing import Any

_CORE_LOGGER_NAME = "quant_nq.core"
_configured = False

# ⚠️ حاوية سياقية آمنة للتزامن (Async-Safe) تمرر رقم التتبع من ناقل الأحداث إلى السجل صمتاً
current_trace_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("trace_id", default=None)
# ⚠️ وراثة الأثر (فتحة النواة V2.0 — ورقة ٠٤): معرّف الحدث الجاري معالجته واسمه،
# ليرث الحدثُ الناتج أباه تلقائيًا (شجرة سببية) دون أن تكتب الذرة ذلك يدويًا.
current_event_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("event_id", default=None)
current_event: contextvars.ContextVar[str | None] = contextvars.ContextVar("event", default=None)


class _AtomLoggerAdapter(logging.LoggerAdapter):
    def process(self, msg: str, kwargs: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        extra = kwargs.setdefault("extra", {})
        extra.setdefault("atom_id", self.extra["atom_id"])
        return msg, kwargs


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "atom_id": getattr(record, "atom_id", None),
        }
        
        # ⚠️ تطبيق المادة 30: قراءة وحقن المعرف تلقائياً (إن وُجد بالسياق)
        trace_id = current_trace_id.get()
        if trace_id:
            payload["trace_id"] = trace_id
            
        payload["message"] = record.getMessage()

        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def _default_log_dir() -> "Path":
    """مجلّد السجلّ: جذرُ حالة النواة المعلَن، وإلّا `var/logs` من مجلّد العمل.

    يُجذَّر على `QUANT_CORE_STATE_ROOT` لأنّه المرسى الذي يضبطه المشرف
    لكلّ عمليّة (`governance/app.py`) — فلا ينقسم السجلّ بين شجرتين كما
    انقسمت اللقطات من قبل.
    """
    root = os.environ.get("QUANT_CORE_STATE_ROOT")
    return (Path(root) / "logs") if root else (Path.cwd() / "var" / "logs")


def configure(level: int = logging.INFO, json_output: bool = True) -> None:
    global _configured
    root = logging.getLogger(_CORE_LOGGER_NAME)
    root.setLevel(level)
    if _configured:
        return

    def _make_formatter() -> logging.Formatter:
        if json_output:
            return _JsonFormatter()
        return logging.Formatter(
            "%(asctime)s | %(levelname)-8s | atom=%(atom_id)s | %(name)s | %(message)s")

    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(_make_formatter())
    root.addHandler(handler)

    # ⚠️ ٢٠٢٦-٠٩-٢٣ — **قناة المعرفة كانت الشاشة وحدها.**
    #
    # كان هذا المُعالِج الوحيد: `StreamHandler(sys.stdout)`. والنواة تُطلق
    # بنافذةٍ خاصّة (`CREATE_NEW_CONSOLE`)، فكلُّ ما تكتبه يموت بإغلاقها.
    # و`var/logs/errors-*.log` الذي يقرؤه الجميع لا يستقبل إلّا خرْجَ
    # العمليّة الباردة — مقيس يوم كتابة هذا: مصادرُ الملفّ كلُّها
    # `ATOM 702/704/707/720` وهي باردة، و`CORE` أربعةَ عشرَ سطرًا.
    #
    # وثمنُه أنّ **«لا سطرَ في السجلّ» لم يكن قياسًا قطّ**: بُنيت عليه
    # ثلاثةُ أحكامٍ في يومٍ واحد (ترقيةٌ تتراجع بلا أثر · خمسَ عشرةَ
    # ذرّةً بلا لقطةٍ ١١٤ ساعة · وعدّادُ مهلٍ قُرئ ناقصًا). العطبُ كان
    # حقيقيًّا في كلٍّ منها، **والدليلُ الذي سُقته كان من قناةٍ عمياء**.
    #
    # والملفُّ لا يُبدّل الشاشة — يُضاف إليها. الصيغة واحدة والمستوى واحد،
    # فلا يتغيّر ما يُكتب، بل يبقى.
    try:
        log_dir = Path(os.environ.get("QUANT_CORE_LOG_DIR") or "").expanduser() \
            if os.environ.get("QUANT_CORE_LOG_DIR") else _default_log_dir()
        log_dir.mkdir(parents=True, exist_ok=True)
        file_handler = logging.handlers.TimedRotatingFileHandler(
            log_dir / "core.log", when="midnight", backupCount=14,
            encoding="utf-8", delay=True)
        file_handler.setFormatter(_make_formatter())
        root.addHandler(file_handler)
    except OSError as exc:                                     # noqa: BLE001
        # قرصٌ ممتلئ أو مسارٌ محجوب لا يُسقط النواة — الشاشة تبقى، ويُقال.
        root.warning("تعذّر فتح سجلّ النواة الملفّيّ: %s", exc)

    root.propagate = False
    _configured = True


def get_logger(atom_id: int, *, component: str | None = None) -> logging.LoggerAdapter:
    if not _configured:
        configure()
    name = (
        f"{_CORE_LOGGER_NAME}.atom.{atom_id}"
        if component is None
        else f"{_CORE_LOGGER_NAME}.atom.{atom_id}.{component}"
    )
    base = logging.getLogger(name)
    return _AtomLoggerAdapter(base, {"atom_id": atom_id})