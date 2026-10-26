"""469 — محاسبة الصفقات: لماذا ربحنا، ولماذا خسرنا، ومن معنا ومن علينا — حقائق خام من دفتر البطاقات.

٢٠٢٦-١٠-٠٨ (ختم المالك «NQ» — المعرفة أوّلًا): «إذا خسر، عنده جواب حقيقيّ مفصّل ليش خسرنا؟ وإذا ربح
ليش ربح؟» و«مين من المحلّلين أو البنية أو الإحصاء أو الاستراتيجيّات أو السيولة عم يعطي قرارات خاسرة؟».

المصدر واحد ويُقرأ ولا يُكتب: دفتر البطاقات الذي يكتبه 465 (`var/store/trade_cards.db` تحت جذر التشغيل)،
في خيطٍ لا على الحلقة. وتنشر `knowledge.accountability.state`:
  ‏`last_trade`   شرح آخر صفقة مغلقة (من بناها · المستويات وأسبابها · ما ذهب معنا وضدّنا · الثلث · الخروج ·
                 النتيجة بالدولار وبوحدة المخاطرة · حقائق الأقسام عند الدخول) وجملةٌ عربيّة مركّبةٌ منها.
  ‏`by_fact`      حساب كلّ حقيقةٍ مختومة: أثلاثًا أو بقيمتها، ولكلّ فئة عددها ورابحها ومتوسّط R،
                 والفئة الصغيرة تُعلَم ولا تُرتَّب · و`fact_gaps` ترتيبٌ خام لأكبر الفروق (للعلم لا حكم).
  ‏`by_strategy` · `by_window` · `by_side` · `by_symbol`  العدد · الرابح · المجموع · المتوسّط · أقصى سحب.
متى: بعد الإقلاع بمهلة (اكتمال الإقلاع كلّه) · مع كلّ `SYS_HOUR` · وبعد كلّ `decision.card.closed` من 465
بمهلة استقرار (465 يدفع ذروة الصفقة وجملتها مع نبضه بعد الإغلاق).
ولا تدخل القرار: لا جهة ولا وزن ولا ثقة — عقد الحقائق ١٠-٠٧.

٢٠٢٦-١٠-٠٩ (ختم المالك «NQ» — الصفقة صافيةً بأجزائها): «كم R خسرنا مقابل كم ربحنا صافي… R عنّا 100 دولار». الصافي
صار من سجلّ الوسيط نفسه (`trade_events_v2` في قاعدة الجسر، `bridge_db_path`، قراءةً في خيط): لكلّ تذكرةٍ لها بطاقة
مجموعُ أجزائها (الربح + العمولة + المبادلة + الرسوم) ÷ مبلغ المخاطرة على البطاقة، بأجزائها ومراحلها، و«ربحنا ·
خسرنا · الصافي» لكلّ مجموعةٍ وحقيقة، ومقارنةٌ بما قالته البطاقات القديمة (`card_vs_broker`) — كانت البطاقات تقول
−170.6R لأنّ 465 أغلقها عند أوّل جزء. وغيابُ الجسر يُعيدها إلى البطاقات معلنًا (`net_source`). الوحدة `accountability_broker`.
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any

from core.contracts.atom import AtomBase, AtomContext, HealthState, HealthStatus
import accountability_broker
import accountability_ledger
import accountability_text

ATOM_VERSION = "1.0.0"
EVENT_HOUR = "SYS_HOUR"
#: يعلنه 465 (`card_ledger_trade.on_outcome`) لحظة إغلاق البطاقة بنتيجتها.
EVENT_CARD_CLOSED = "decision.card.closed"
EVENT_OUT = "knowledge.accountability.state"

DEFAULT_STORE = "var/store/trade_cards.db"
#: ٢٠٢٦-١٠-٠٩ (ختم المالك «NQ» — الصفقة صافيةً بأجزائها): قاعدة جسر الإكسبرت — سجلّ الوسيط (`trade_events_v2`)؛
#: ومرسى البيئة `NQ_BRIDGE_DB` يسبقها (عقد قرّاء الجسر).
DEFAULT_BRIDGE_DB = r"%APPDATA%\MetaQuotes\Terminal\Common\Files\nq_brain.db"
#: بعد اكتمال الإقلاع كلّه (نمط 153: الذرّات تبدأ بالتتابع ~7 ث) — فلا يسبق النشرُ مستمعيه.
BOOT_DELAY_S = 30.0
#: بعد إغلاق بطاقة: 465 يُقيّد الذروة والجملة ويدفعهما مع نبضه (كلّ ٥ ث) — فيُقرأ بعد استقرارهما.
CLOSE_SETTLE_S = 15.0
#: مهلة انشغال القاعدة عند القراءة — قراءةٌ لا تنتظر أكثر من هذا ثمّ تُعلن تعذّرها.
READ_TIMEOUT_S = 5.0
#: أقلّ عددٍ من الصفقات في الفئة كي تدخل الترتيب — ما دونه «عيّنة صغيرة» (أمر المالك ١٠-٠٨).
MIN_SAMPLE = 10
TOP_GAPS = 10


def _rebased_config(raw: dict[str, Any]) -> dict[str, Any]:
    """يحلّ `var/…` عند جذر التشغيل لا عند مجلّد العمل — نمط 465 نفسه، وتعذُّره لا يعطّل الإقلاع."""
    code_root = next((parent for parent in Path(__file__).resolve().parents
                      if (parent / "shared" / "runtime_paths.py").is_file()), None)
    if code_root is None:
        return raw
    try:
        from shared.runtime_paths import manifest_config_rebase
        return manifest_config_rebase(raw, code_root=code_root)
    except Exception:  # noqa: BLE001 — لا يُعطَّل الإقلاع بأزمة مسار
        return raw


class Atom(AtomBase):
    def __init__(self) -> None:
        self._context: AtomContext | None = None
        self._running = False
        self._started_at = time.monotonic()
        self._store_path = DEFAULT_STORE
        self._bridge_path = DEFAULT_BRIDGE_DB
        self._boot_delay = BOOT_DELAY_S
        self._settle = CLOSE_SETTLE_S
        self._min_sample = MIN_SAMPLE
        self._top = TOP_GAPS
        #: الحساب المملوك — يُطلق ولا يُنتظر في المعالج، ويُراقَب خطؤه، ويُلغى في `stop`.
        self._tasks: set[asyncio.Task[Any]] = set()
        self._computing = False
        self._rerun = False
        self._settle_pending = False
        self._published = 0
        self._refreshes = 0
        self._closes_seen = 0
        self._dropped = 0
        self._coalesced = 0
        self._unavailable = 0
        self._failed = 0
        self._last_error = ""
        self._last_status = ""
        self._last_summary = ""
        self._last_computed_at: float | None = None
        self._last_card_no = 0
        self._trades_closed = 0
        self._fact_trades = 0
        self._wins = 0
        self._total_r = 0.0
        self._total_usd = 0.0
        self._won_r = 0.0
        self._lost_r = 0.0
        self._net_source = ""

    # ------------------------------------------------------------------ حياة

    async def initialize(self, context: AtomContext) -> None:
        self._context = context
        cfg = _rebased_config(dict(context.config or {}))
        self._store_path = str(cfg.get("store_path", DEFAULT_STORE))
        self._bridge_path = accountability_broker.resolve_bridge_path(
            str(cfg.get("bridge_db_path") or DEFAULT_BRIDGE_DB))
        self._boot_delay = float(cfg.get("boot_delay_s", BOOT_DELAY_S))
        self._settle = float(cfg.get("close_settle_s", CLOSE_SETTLE_S))
        self._min_sample = int(cfg.get("min_sample", MIN_SAMPLE))
        self._top = int(cfg.get("top_gaps", TOP_GAPS))
        context.subscribe(EVENT_HOUR, self._on_hour)
        context.subscribe(EVENT_CARD_CLOSED, self._on_card_closed)

    async def start(self) -> None:
        self._running = True
        self._started_at = time.monotonic()
        self._spawn(self._later(self._boot_delay), "469-boot")

    async def stop(self) -> None:
        # ٢٠٢٦-١٠-٠٨ (ختم المالك «NQ» — المعرفة أوّلًا): لا شيء هنا يُكتب فيضيع بالقطع — القراءة للقراءة
        # فقط، والمهلات نائمة. فيُلغى كلّ عملٍ مملوك فورًا، ولا مهمّة تعيش بعد ذرّتها.
        self._running = False
        for task in list(self._tasks):
            task.cancel()
        self._settle_pending = False

    async def shutdown(self) -> None:
        await self.stop()

    def _spawn(self, coro: Any, label: str) -> None:
        task = asyncio.get_running_loop().create_task(coro, name=label)
        self._tasks.add(task)

        def _done(finished: asyncio.Task[Any]) -> None:
            self._tasks.discard(finished)
            if not finished.cancelled() and finished.exception() is not None:
                self._last_error = "%s: %s" % (label, finished.exception())

        task.add_done_callback(_done)

    # ---------------------------------------------------------------- أحداث

    async def _on_hour(self, payload: dict[str, Any]) -> None:
        if not self._running:
            return
        self._spawn(self._refresh(), "469-hour")

    async def _on_card_closed(self, payload: dict[str, Any]) -> None:
        if not self._running:
            return
        if not isinstance(payload, dict) or payload.get("card_no") is None:
            self._dropped += 1
            return
        self._closes_seen += 1
        if self._settle_pending:
            self._coalesced += 1
            return
        self._settle_pending = True
        self._spawn(self._later(self._settle, closing=True), "469-closed")

    async def _later(self, delay: float, closing: bool = False) -> None:
        await asyncio.sleep(max(0.0, delay))
        if closing:
            self._settle_pending = False
        if self._running:
            await self._refresh()

    # ---------------------------------------------------------------- الحساب

    async def _refresh(self) -> None:
        """يقرأ الدفتر في خيط ويبني الحمولة وينشرها — وطلبٌ يصل أثناء حسابٍ جارٍ يُعاد مرّةً بعده."""
        if self._computing:
            self._rerun = True
            self._coalesced += 1
            return
        self._computing = True
        try:
            while True:
                self._rerun = False
                await self._compute_once()
                if not (self._rerun and self._running):
                    break
        finally:
            self._computing = False

    async def _compute_once(self) -> None:
        now = time.time()
        self._refreshes += 1
        try:
            payload = await asyncio.to_thread(
                accountability_text.build_payload, self._store_path, now,
                self._min_sample, self._top, READ_TIMEOUT_S, self._bridge_path)
        except accountability_ledger.LedgerUnavailable as exc:
            self._unavailable += 1
            self._last_error = str(exc)
            payload = accountability_text.unavailable_payload(str(exc), now)
        except Exception as exc:  # noqa: BLE001 — صفٌّ شاذّ في الدفتر لا يُسقط الذرّة؛ يُعلَن سببه
            # ٢٠٢٦-١٠-٠٨ (ختم المالك «NQ» — المعرفة أوّلًا): الذرّة حيّة متى وُصلت — لا تنهار في أيّ حال.
            self._failed += 1
            self._last_error = "%s: %s" % (type(exc).__name__, exc)
            payload = accountability_text.unavailable_payload(
                "تعذّر الحساب (%s)" % self._last_error, now)
        self._remember(payload)
        if self._context is not None and self._running:
            await self._context.publish(EVENT_OUT, payload)
            self._published += 1

    def _remember(self, payload: dict[str, Any]) -> None:
        facts = payload.get("facts") or {}
        self._last_status = str(payload.get("status") or "")
        self._last_summary = str(payload.get("summary_ar") or "")
        self._last_computed_at = payload.get("computed_at")
        if self._last_status != "ok":
            return
        totals = facts.get("totals") or {}
        self._trades_closed = int(facts.get("trades_closed") or 0)
        self._fact_trades = int(facts.get("trades_with_entry_facts") or 0)
        self._wins = int(totals.get("wins") or 0)
        self._total_r = float(totals.get("total_r") or 0.0)
        self._total_usd = float(totals.get("total_usd") or 0.0)
        self._won_r = float(totals.get("won_r") or 0.0)
        self._lost_r = float(totals.get("lost_r") or 0.0)
        self._net_source = str(facts.get("net_source") or "")
        self._last_card_no = int((facts.get("last_trade") or {}).get("card_no") or 0)
        self._last_error = ""

    # --------------------------------------------------------------- الصحّة

    async def health_check(self) -> HealthStatus:
        if not self._running:
            return HealthStatus(state=HealthState.UNHEALTHY, message="NOT_STARTED")
        counters = ("نُشر=%d · حسابات=%d · إغلاقات_مسموعة=%d · مدموجة=%d · مرميّ=%d · "
                    "تعذّر_الدفتر=%d · تعذّر_الحساب=%d · منذ_الإقلاع=%d ث" % (
                        self._published, self._refreshes, self._closes_seen, self._coalesced,
                        self._dropped, self._unavailable, self._failed,
                        int(time.monotonic() - self._started_at)))
        details = {"published": self._published, "refreshes": self._refreshes,
                   "closes_seen": self._closes_seen, "dropped": self._dropped,
                   "coalesced": self._coalesced, "unavailable": self._unavailable,
                   "failed": self._failed, "trades_closed": self._trades_closed,
                   "last_error": self._last_error}
        if self._last_computed_at is None:
            return HealthStatus(state=HealthState.HEALTHY, details=details, message=(
                "لم يُحسب بعد — أوّل قراءةٍ للدفتر بعد %.0f ث من الإقلاع · %s" % (
                    self._boot_delay, counters)))
        if self._last_status != "ok":
            return HealthStatus(state=HealthState.DEGRADED, details=details, message=(
                "دفتر البطاقات غير متاح: %s · %s" % (self._last_error or "—", counters)))
        age = int(time.time() - float(self._last_computed_at))
        # ٢٠٢٦-١٠-٠٩ (ختم المالك «NQ» — الصفقة صافيةً بأجزائها): ربحنا · خسرنا · الصافي، ومصدر الصافي معلنًا.
        source = "من سجلّ الوسيط" if self._net_source == "broker" else "من البطاقات (الوسيط غير متاح)"
        return HealthStatus(state=HealthState.HEALTHY, details=details, message=(
            "يعرف %d صفقة مغلقة: %d رابحة · ربحنا %+.2fR · خسرنا %+.2fR · الصافي %+.2fR (%+.2f$) %s · "
            "آخرها البطاقة %d · تحمل حقائق الأقسام %d · آخر حساب قبل %d ث · %s" % (
                self._trades_closed, self._wins, self._won_r, self._lost_r, self._total_r,
                self._total_usd, source, self._last_card_no, self._fact_trades, age, counters)))

    # ------------------------------------------------------------- اللقطة

    async def snapshot(self) -> dict[str, Any]:
        # الأرقام نفسها مصدرها الدفتر وتُعاد قراءتها بعد الإقلاع؛ تُحفظ العدّادات وآخر ما عُرف
        # كي تقول الصحّة ما كانت تعرفه قبل أوّل حسابٍ جديد.
        return {"version": ATOM_VERSION, "published": self._published,
                "refreshes": self._refreshes, "closes_seen": self._closes_seen,
                "dropped": self._dropped, "coalesced": self._coalesced,
                "unavailable": self._unavailable, "failed": self._failed,
                "last_status": self._last_status,
                "last_summary": self._last_summary, "last_computed_at": self._last_computed_at,
                "last_card_no": self._last_card_no, "trades_closed": self._trades_closed,
                "fact_trades": self._fact_trades, "wins": self._wins,
                "total_r": self._total_r, "total_usd": self._total_usd,
                "won_r": self._won_r, "lost_r": self._lost_r, "net_source": self._net_source}

    async def restore(self, state: dict[str, Any]) -> None:
        if not isinstance(state, dict):
            raise ValueError("INVALID_ACCOUNTABILITY_STATE")
        try:
            counts = {name: int(state.get(name) or 0) for name in (
                "published", "refreshes", "closes_seen", "dropped", "coalesced", "unavailable",
                "failed", "last_card_no", "trades_closed", "fact_trades", "wins")}
            sums = {name: float(state.get(name) or 0.0)
                    for name in ("total_r", "total_usd", "won_r", "lost_r")}
            computed = state.get("last_computed_at")
            computed = None if computed is None else float(computed)
        except (TypeError, ValueError):
            raise ValueError("INVALID_ACCOUNTABILITY_STATE")
        for name, value in counts.items():
            setattr(self, "_" + name, value)
        self._total_r, self._total_usd = sums["total_r"], sums["total_usd"]
        self._won_r, self._lost_r = sums["won_r"], sums["lost_r"]
        self._net_source = str(state.get("net_source") or "")
        self._last_status = str(state.get("last_status") or "")
        self._last_summary = str(state.get("last_summary") or "")
        self._last_computed_at = computed
