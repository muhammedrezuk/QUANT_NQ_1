from __future__ import annotations

import math
import time
from typing import Any

from core.contracts.atom import AtomBase, AtomContext, HealthState, HealthStatus
from shared.financial_scope import financial_key, row_key, text
from shared.market_hours import CLOSED, market_state

ATOM_VERSION = "3.3.0"
# 🔴 ٢٠٢٦-٠٩-٢٦ (ختم المالك «Nq» · «سستم عندك ما يعرف أيّ يوم عايش فيه… ما بيعرف سوق
# مغلق») — كلّ عطلة أسبوع يصير سعر الرموز الستّة المغلقة «بائتًا» فتُعلن اللقطة
# `SNAPSHOT_STALE` عطلًا. والوسيط يعرف أنّ السوق مغلق: الإكسبرت v3.17 ينقل جلساته مع
# المواصفات. فسعرٌ لم يتجدّد في سوقٍ مغلقة بجلسات الوسيط حالتُه الآن `MARKET_CLOSED`:
# لا تعرّضَ جديدًا ولا حمايةَ (الوسيط يردّ كلّ أمرٍ فيها)، ولا إنذار. والسعر الحيّ يعلو
# الجلسات: رمزٌ تتجدّد تِكّاته يُحكم كما كان ولو قالت الجلسات غير ذلك.
# ٢٠٢٦-١٠-٠٧ (ختم «NQ»): خرج ثابت perpetual.target.state مع اشتراكه — ناشره (٥٨١) أُرشف.
EVENT_LEDGER = "risk.asset_ledger.state"
EVENT_PORTFOLIO = "asset.portfolio.state"
EVENT_TICK = "feed.mt5.tick"
EVENT_SPECS = "market.symbol_specs"
EVENT_DIAL = "dial.profile.state"
EVENT_OUT = "execution.snapshot.state"
EVENT_PULSE = "SYS_SECOND"
EVENT_ACCOUNT = "platform.account.state"

READY = "READY"
PROTECTION_ONLY = "PROTECTION_ONLY"
INCOMPLETE = "INCOMPLETE"
STALE = "STALE"
MARKET_CLOSED = "MARKET_CLOSED"
_COMPONENTS = ("ledger", "portfolio", "price", "specs", "dial")


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


class Atom(AtomBase):
    def __init__(self) -> None:
        self._context = None
        self._running = False
        self._brokers: dict[str, str] = {}
        self._pending_specs: list[dict[str, Any]] = []
        self._components: dict[str, dict[tuple[str, str, str], dict[str, Any]]] = {
            name: {} for name in _COMPONENTS}
        self._version = 0
        self._seen = 0
        self._epoch = 0.0
        self._official_time = 0.0
        self._missing_scope = 0
        self._last_status = INCOMPLETE
        self._last_symbol = ""
        self._status_counts = {READY: 0, PROTECTION_ONLY: 0, INCOMPLETE: 0, STALE: 0,
                               MARKET_CLOSED: 0}
        #: 🔴 ٢٠٢٦-٠٩-٢٣ — أسماءُ ما نقص وما بات في آخر لقطة.
        #: كانت الشارة تقول `SNAPSHOT_INCOMPLETE` عاريةً: تُعلن أنّ اللقطة
        #: ناقصة ولا تقول **أيُّ** مكوّنٍ نقص — والقائمتان محسوبتان في
        #: `_on_target` وتُنشَران في الحمولة، لكنّ القارئ يقرأ الشارة.
        #: و`details` تحذفها النواة، فالمرئيُّ هو `message` وحده.
        #: وهذا نمطٌ معروفٌ في المشروع: حارسٌ صائبٌ صامتٌ يُقرأ عطلًا عند
        #: غيرك — وقد كلّف ٦١٨ و`TRADE_FEED_STALE` ثمنًا من قبل.
        #: وكم مرّةً نقص كلُّ مكوّنٍ يُعدّ أيضًا: مرّةٌ عابرة غيرُ مزمنة.
        self._last_missing: list[str] = []
        self._last_stale: list[str] = []
        self._missing_counts: dict[str, int] = {}
        self._specs_no_key = 0
        self._specs_no_number = 0
        self._specs_last_drop = ""
        self._specs_events = 0
        self._specs_before_start = 0
        #: 🔴 ٢٠٢٦-٠٩-٢٣ — عمرُ الذرّة ولحظةُ آخر وصول، إلى جانب العدد.
        #:
        #: العدّادُ وحده أوقعني اليوم: قرأتُ `وصلني=0` بعد ‎56‎ ثانية من
        #: تحميلٍ حارّ، ودورةُ الناشر ‎300‎ ثانية — فأعلنتُ «لا يصل» وأبلغتُ
        #: قسمًا آخر، والصوابُ «لم تكتمل الدورة». وبعد دورةٍ واحدة صار
        #: `SNAPSHOT_READY` بلا أيّ تغييرٍ في الناشر.
        #:
        #: والعلاجُ ليس حذرَ القارئ بل **أن يحمل الرقمُ حدَّه معه**: صفرٌ
        #: بجانبه `عمري=56ث` يقول بنفسه إنّه لا يدلّ، وصفرٌ بجانبه
        #: `عمري=3400ث` يقول إنّه يدلّ. وعمرٌ منذ آخر وصول يفصل «لم يصل
        #: قطُّ» عن «وصل وانقطع» — وهما عطلان مختلفان.
        #:
        #: ولم أُعمّره في لقطة: هذه الذرّة بلا `snapshot`، وتعميرُ عدّادٍ
        #: يجعله يقول «وصل» عن عمليّةٍ ماتت. العمرُ أصدقُ من التعمير.
        self._birth = time.monotonic()
        self._specs_last_at = 0.0
        self._max_age = {"ledger": 30.0, "portfolio": 30.0, "price": 5.0,
                         "specs": 600.0, "dial": 3600.0}

    async def initialize(self, context: AtomContext) -> None:
        self._context = context
        cfg = context.config
        self._max_age = {
            "ledger": float(cfg.get("ledger_max_age_s", 30.0)),
            "portfolio": float(cfg.get("portfolio_max_age_s", 30.0)),
            "price": float(cfg.get("price_max_age_s", 5.0)),
            "specs": float(cfg.get("specs_max_age_s", 600.0)),
            "dial": float(cfg.get("dial_max_age_s", 3600.0)),
        }
        # ٢٠٢٦-١٠-٠٧ (ختم «NQ»): لا اشتراك في perpetual.target.state — ناشره (٥٨١) أُرشف؛ `_on_target` باقٍ لأنّ الاختبار يستدعيه.
        for event, handler in (
            (EVENT_LEDGER, self._on_ledger),
            (EVENT_PORTFOLIO, self._on_portfolio), (EVENT_TICK, self._on_tick),
            (EVENT_SPECS, self._on_specs), (EVENT_DIAL, self._on_dial),
            (EVENT_PULSE, self._on_pulse), (EVENT_ACCOUNT, self._on_account)):
            context.subscribe(event, handler)

    async def start(self) -> None:
        self._running = True

    async def stop(self) -> None:
        self._running = False

    async def shutdown(self) -> None:
        await self.stop()

    async def _on_account(self, payload: dict[str, Any]) -> None:
        if not self._running or not isinstance(payload, dict):
            return
        account = text(payload.get("account_id")); broker = text(payload.get("broker"))
        if account and broker:
            self._brokers[account] = broker
            pending, self._pending_specs = self._pending_specs, []
            for item in pending:
                await self._on_specs(item)

    async def _on_pulse(self, payload: dict[str, Any]) -> None:
        if not isinstance(payload, dict):
            return
        now = _number(payload.get("official_time"))
        if now is None:
            return
        self._official_time = now
        if not self._epoch:
            self._epoch = now

    def _key(self, payload: dict[str, Any]) -> tuple[str, str, str] | None:
        return financial_key(payload, payload.get("symbol"), self._brokers)

    def _store(self, component: str, key: tuple[str, str, str], data: dict[str, Any]) -> None:
        self._components[component][key] = {
            "data": dict(data), "seen_at": self._official_time if self._official_time > 0 else None,
            "source_timestamp": data.get("timestamp", data.get("produced_at")),
            "cycle_id": data.get("cycle_id"),
        }

    async def _on_ledger(self, payload: dict[str, Any]) -> None:
        if not self._running or not isinstance(payload, dict):
            return
        for row in payload.get("ledgers", []) if isinstance(payload.get("ledgers"), list) else []:
            if isinstance(row, dict):
                key = self._key(row)
                if key is not None:
                    self._store("ledger", key, row)

    async def _on_portfolio(self, payload: dict[str, Any]) -> None:
        if not self._running or not isinstance(payload, dict):
            return
        for row in payload.get("portfolios", []) if isinstance(payload.get("portfolios"), list) else []:
            if isinstance(row, dict):
                key = self._key(row)
                if key is not None:
                    self._store("portfolio", key, row)

    async def _on_tick(self, payload: dict[str, Any]) -> None:
        if not self._running or not isinstance(payload, dict):
            return
        key = self._key(payload)
        price = _number(payload.get("price"))
        bid = _number(payload.get("bid")); ask = _number(payload.get("ask"))
        if key is not None and ((price is not None and price > 0)
                                or (bid is not None and ask is not None and bid > 0 and ask >= bid)):
            self._store("price", key, payload)

    async def _on_specs(self, payload: dict[str, Any]) -> None:
        # ٢٠٢٦-٠٩-٢٣ — يُعدُّ **قبل** أيّ حارس. أعلنتُ في ٣.١.١ أنّ صفر
        # صفٍّ رُفض وصفر صفٍّ خُزّن، وهذا لا يفرّق بين حالتين مختلفتين
        # تمامًا: أنّ الحدث لم يصلني قطُّ، أو أنّه وصل ورددتُه أنا صامتًا
        # عند `not self._running` (والاشتراكُ يقع في `initialize` بينما
        # الرايةُ تُرفع في `start`، فبينهما نافذةٌ تبتلع بلا أثر).
        # العدّادُ فوق الحارس هو ما يفصلهما.
        self._specs_events += 1
        self._specs_last_at = time.monotonic()
        if not self._running:
            self._specs_before_start += 1
            return
        if not isinstance(payload, dict):
            return
        for row in payload.get("symbols", []) if isinstance(payload.get("symbols"), list) else []:
            if not isinstance(row, dict):
                continue
            key = row_key(payload, row, self._brokers)
            point = _number(row.get("point")); tick_size = _number(row.get("tick_size"))
            if key is not None and ((point is not None and point > 0)
                                    or (tick_size is not None and tick_size > 0)):
                self._store("specs", key, row)
            else:
                # 🔴 ٢٠٢٦-٠٩-٢٣ — هنا كان الإسقاطُ صامتًا تمامًا.
                #
                # ٦١٨ ناشرٌ وحيد وصحّتُه `published=24,917,675 symbols=7`، أي
                # أنّ المواصفات تصل فعلًا — ومع ذلك `specs` **لم يصل قطُّ**
                # إلى هذه الذرّة في ‎1,469‎ لقطة. فالخسارةُ هنا لا هناك.
                #
                # وسببان لا ثالث لهما، ولا يُشخَّصان بالدواء نفسه:
                #   • `key is None` — الوسيطُ غيرُ معروفٍ لهذا الحساب بعد،
                #     أي لم يصل `platform.account.state` يحمل `broker`.
                #     وحمولةُ ٦١٨ لا تحمل وسيطًا أصلًا: `provider` و
                #     `published_at` و`symbols` فقط.
                #   • رقمٌ غائب — لا `point` ولا `tick_size` موجبًا.
                # يُعدّان منفصلين، وآخرُ رمزٍ سقط يُسمّى، لأنّ عدّادًا بلا
                # اسمٍ يقول «هناك عطل» ولا يقول أين.
                if key is None:
                    self._specs_no_key += 1
                else:
                    self._specs_no_number += 1
                self._specs_last_drop = text(row.get("symbol")) or "?"
                if text(row.get("account_id") or payload.get("account_id")) \
                        and payload not in self._pending_specs:
                    self._pending_specs.append(dict(payload))

    async def _on_dial(self, payload: dict[str, Any]) -> None:
        if not self._running or not isinstance(payload, dict):
            return
        for row in payload.get("profiles", []) if isinstance(payload.get("profiles"), list) else []:
            if isinstance(row, dict):
                key = self._key(row)
                if key is not None:
                    self._store("dial", key, row)

    def _component_view(self, key: tuple[str, str, str]) -> tuple[dict[str, Any], list[str], list[str], dict[str, Any]]:
        snapshot: dict[str, Any] = {}
        missing: list[str] = []
        stale: list[str] = []
        stamps: dict[str, Any] = {}
        for name in _COMPONENTS:
            record = self._components[name].get(key)
            if record is None:
                snapshot[name] = None; missing.append(name); stamps[name] = None
                continue
            snapshot[name] = record["data"]
            seen = record.get("seen_at"); stamps[name] = {
                "seen_at": seen, "source_timestamp": record.get("source_timestamp"),
                "cycle_id": record.get("cycle_id")}
            if (self._official_time <= 0 or seen is None or seen <= 0
                    or self._official_time - float(seen) < 0
                    or self._official_time - float(seen) > self._max_age[name]):
                stale.append(name)
        return snapshot, missing, stale, stamps

    @staticmethod
    def _pure_reduction(payload: dict[str, Any]) -> bool:
        action = text(payload.get("action")).upper()
        if action not in {"REDUCE", "CLOSE", "CLOSE_PARTIAL"}:
            return False
        positives = [(_number(payload.get(name)) or 0.0) > 0
                     for name in ("delta_buy", "delta_sell")]
        return not any(positives) and isinstance(payload.get("current_legs"), list)

    async def _on_target(self, payload: dict[str, Any]) -> None:
        if not self._running or self._context is None or not isinstance(payload, dict):
            return
        key = self._key(payload)
        if key is None:
            self._missing_scope += 1
            return
        self._version += 1; self._seen += 1
        snapshot, missing, stale, stamps = self._component_view(key)
        official_ready = self._official_time > 0 and self._epoch > 0
        if not official_ready:
            missing.append("official_time")
        full = not missing and not stale
        protection_base = (snapshot.get("ledger") is not None
                           and snapshot.get("portfolio") is not None
                           and self._pure_reduction(payload) and official_ready)
        # سعرٌ لم يتجدّد (بائتٌ أو لم يصل) في سوقٍ أغلقها الوسيط بجلساته.
        closed = (("price" in stale or "price" in missing) and official_ready
                  and market_state(snapshot.get("specs"), self._official_time) == CLOSED)
        if full:
            status = READY
        elif closed:
            status = MARKET_CLOSED
        elif protection_base:
            status = PROTECTION_ONLY
        elif stale:
            status = STALE
        else:
            status = INCOMPLETE
        account, broker, symbol = key
        snapshot.update({"version": self._version, "component_stamps": stamps})
        out = dict(payload)
        out.update({
            "account_id": account, "broker": broker, "symbol": symbol,
            "snapshot_id": "snapshot-%s-%s-%s-%d-%d" % (
                account, broker, symbol, self._epoch, self._version),
            "producer_epoch": self._epoch, "produced_at": self._official_time,
            "sequence": self._version, "snapshot_status": status,
            "missing_components": sorted(set(missing)),
            "stale_components": sorted(set(stale)),
            "usable_for_new_exposure": status == READY,
            "usable_for_protection": status in {READY, PROTECTION_ONLY},
            "component_stamps": stamps, "snapshot": snapshot,
        })
        self._last_status = status; self._status_counts[status] += 1
        self._last_symbol = symbol
        self._last_missing = sorted(set(missing))
        self._last_stale = sorted(set(stale))
        # سكونُ سوقٍ مغلقة لا يُعدّ في «الأكثر» — عطلةُ نهاية أسبوعٍ واحدة كانت
        # ستملأ العدّاد بعشرات الآلاف وتدفن العطل الحقيقيّ تحتها.
        if status != MARKET_CLOSED:
            for name in self._last_missing:
                self._missing_counts[name] = self._missing_counts.get(name, 0) + 1
            for name in self._last_stale:
                key_name = name + "(بائت)"
                self._missing_counts[key_name] = self._missing_counts.get(key_name, 0) + 1
        await self._context.publish(EVENT_OUT, out)

    async def health_check(self) -> HealthStatus:
        if not self._running:
            return HealthStatus(state=HealthState.UNHEALTHY, message="NOT_STARTED")
        details = {"targets": self._seen, "snapshots": self._version,
                   "status": self._last_status, "status_counts": dict(self._status_counts),
                   "missing_scope": self._missing_scope,
                   "components": {name: len(rows) for name, rows in self._components.items()}}
        if self._seen == 0:
            return HealthStatus(state=HealthState.HEALTHY,
                                message="READY_AWAITING_FIRST_TARGET | targets=0 snapshots=%d" % self._version,
                                details=details)
        details["last_missing"] = list(self._last_missing)
        details["last_stale"] = list(self._last_stale)
        details["missing_counts"] = dict(self._missing_counts)
        if self._last_status == MARKET_CLOSED:
            # سوقٌ أغلقها الوسيط ليست عطلًا: تُسمّى ولا يُنبَّه عليها.
            return HealthStatus(
                state=HealthState.HEALTHY,
                message="SNAPSHOT_MARKET_CLOSED | السوق مغلق بجلسات الوسيط: %s · مغلقة حتى الآن=%d"
                        % (self._last_symbol or "?", self._status_counts[MARKET_CLOSED]),
                details=details)
        if self._last_status != READY:
            # ما يُرمى يُسمّى. والعدّاد إلى جانب الاسم كي يُعرف المزمنُ من
            # العابر: `ledger×4812` علّةٌ قائمة، و`price×2` ارتعاشةُ تِكّة.
            chronic = ", ".join(
                "%s×%d" % (name, self._missing_counts[name])
                for name in sorted(self._missing_counts,
                                   key=lambda k: -self._missing_counts[k])[:4])
            parts = []
            if self._last_missing:
                parts.append("ناقص=" + "+".join(self._last_missing))
            if self._last_stale:
                parts.append("بائت=" + "+".join(self._last_stale))
            if chronic:
                parts.append("الأكثر: " + chronic)
            # مكوّناتٌ لم تصل قطُّ تُفصَل عمّا وصل ثمّ بات — الأولى عطلُ
            # ناشرٍ والثانية عطلُ إيقاع، ولا يُشخَّصان بالدواء نفسه.
            never = [n for n in _COMPONENTS if not self._components[n]]
            if never:
                parts.append("لم يصل قطُّ: " + "+".join(never))
            if "specs" in self._last_missing or self._specs_events:
                age = time.monotonic() - self._birth
                since = ("%.0fث" % (time.monotonic() - self._specs_last_at)
                         if self._specs_last_at else "لم يصل بعدُ")
                parts.append(
                    "مواصفات: وصلني=%d منذ=%s · عمري=%.0fث · قبل البدء=%d"
                    " بلا وسيط=%d بلا رقم=%d آخر ساقط=%s معلّق=%d وسطاء=%d"
                    % (self._specs_events, since, age, self._specs_before_start,
                       self._specs_no_key, self._specs_no_number,
                       self._specs_last_drop or "-",
                       len(self._pending_specs), len(self._brokers)))
            return HealthStatus(
                state=HealthState.DEGRADED,
                message="SNAPSHOT_%s | %s" % (self._last_status,
                                              " · ".join(parts) or "بلا تفصيل"),
                details=details)
        return HealthStatus(state=HealthState.HEALTHY, message="SNAPSHOT_READY", details=details)
