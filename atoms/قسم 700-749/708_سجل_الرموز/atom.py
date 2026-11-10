from __future__ import annotations

import re
import time
from typing import Any

from core.contracts.atom import AtomBase, AtomContext, HealthState, HealthStatus

ATOM_VERSION = "2.7.0"

#: ٢٠٢٦-٠٩-٠٤ (ختم NQ): مهلة تقادم الرمز غير المخرَّط. كان `_unmapped` قاموسًا
#: بلا نسيان — يُحفظ في اللقطة ويُستعاد، فرمزٌ ظهر مرّة واحدة يبقى معلَنًا عطلًا
#: إلى الأبد. مقيس ٢٠٢٦-٠٩-٠٤: بعد إلغاء `DXY_U6` من الإكسبرت توقّف وصوله تمامًا
#: (صفر تِكّة في ١٨٠ ثانية) وبقيت الذرّة تقول `unmapped: DXY_U6` — حالة بائتة
#: تُعرض على لوحة المالك كحاضر. وقانون المالك: «ممنوع لوحة تكذب أبدًا».
#: العدّاد يبقى للسجلّ؛ الإعلان وحده هو ما يتقادم — النسيان لا يُخفي شيئًا حصل،
#: بل يمنع إعلان ما لم يعد يحصل.
UNMAPPED_STALE_AFTER_S = 300.0

EVENT_RESOLVE_REQUESTED = "storage.symbol.resolve_requested"
EVENT_RESOLVE_REQUESTED_NEW = "symbol.resolve.requested"
EVENT_RESOLVED = "storage.symbol.resolved"
EVENT_RESOLVED_NEW = "symbol.resolve.result"
EVENT_UNMAPPED = "storage.symbol.unmapped"
EVENT_MAP = "storage.symbol.map.state"
EVENT_SPECS = "market.symbol_specs"
EVENT_CTRADER_SPECS = "market.ctrader.symbol_specs"
EVENT_ACCOUNT = "platform.account.state"

REASON_NOT_STARTED = "NOT_STARTED"
REASON_NO_MAP = "NO_MAPPING_CONFIGURED"


class Atom(AtomBase):
    def __init__(self) -> None:
        self._context: AtomContext | None = None
        self._initialized = False
        self._running = False
        self._exact: dict[str, str] = {}
        self._patterns: list[tuple[re.Pattern, str]] = []
        self._min_stem_length = 0
        self._strip_suffixes: list[str] = []
        self._passthrough_unknown = True
        self._unmapped: dict[str, int] = {}
        self._unmapped_seen: dict[str, float] = {}   # الرمز -> آخر ظهور فعليّ
        self._cache: dict[str, str] = {}
        self._specs: dict[tuple[str, str], dict[str, Any]] = {}
        self._reference_specs: dict[tuple[str, str], dict[str, Any]] = {}
        self._current_account = ""
        self.resolved_count = 0
        self.unmapped_count = 0
        self._bad_patterns: dict[str, str] = {}

    async def initialize(self, context: AtomContext) -> None:
        self._context = context
        cfg = context.config
        self._strip_suffixes = [str(s) for s in cfg["strip_suffixes"]]
        self._min_stem_length = int(cfg["min_stem_length"])
        self._passthrough_unknown = bool(cfg["passthrough_unknown"])
        self._broker_map = {str(k).upper(): str(v) for k,v in dict(cfg.get("broker_map",{})).items()}
        for canonical, aliases in dict(cfg["canonical_map"]).items():
            for alias in aliases:
                self._exact[str(alias).strip().upper()] = str(canonical)
            self._exact[str(canonical).strip().upper()] = str(canonical)
        # نمطٌ خاطئ في العقد كان يُسقَط بـ`pass`: فيبقى الرمز بلا مطابقة إلى
        # الأبد، وتقرأ اللوحة `SYMBOL_UNRESOLVED` بلا سببٍ يُرى — والعلّة
        # مطبعةٌ في المانيفست لا في السوق. يُسقَط كما كان (لا يُعطَّل إقلاع
        # الذرّة بنمطٍ واحد)، لكنّه **يُعدّ ويُنطق**.
        for canonical, pattern in dict(cfg["canonical_patterns"]).items():
            try:
                self._patterns.append(
                    (re.compile(pattern, re.IGNORECASE), str(canonical)))
            except re.error as exc:
                self._bad_patterns[str(canonical)] = "%s — %s" % (pattern, exc)
                logger = getattr(context, "logger", None)
                if logger is not None:
                    try:
                        logger.error("708 سجل الرموز: نمط رمزٍ مرفوض في العقد —"
                                     " %s = %r (%s)", canonical, pattern, exc)
                    except Exception:  # noqa: BLE001 — لا تسقط ذرّة بسبب سجلّ
                        pass
        context.subscribe(EVENT_RESOLVE_REQUESTED, self._on_resolve_requested)
        context.subscribe(EVENT_RESOLVE_REQUESTED_NEW, self._on_resolve_new)
        context.subscribe(EVENT_SPECS, self._on_specs)
        context.subscribe(EVENT_CTRADER_SPECS, self._on_ctrader_specs)
        context.subscribe(EVENT_ACCOUNT, self._on_account)
        self._initialized = True

    async def start(self) -> None:
        if not self._initialized or self._running or self._context is None:
            return
        self._running = True
        await self._context.publish(EVENT_MAP, {
            "aliases": dict(self._exact),
            "strip_suffixes": list(self._strip_suffixes),
            "passthrough_unknown": self._passthrough_unknown,
        })

    async def stop(self) -> None:
        self._running = False

    async def shutdown(self) -> None:
        await self.stop()

    def _strip(self, symbol: str) -> str:
        cleaned = symbol.strip().upper()
        for suffix in self._strip_suffixes:
            marker = suffix.upper()
            if not marker or not cleaned.endswith(marker):
                continue
            stem = cleaned[: -len(marker)]
            if len(stem) < self._min_stem_length:
                continue
            if len(marker) == 1 and marker.isalnum():
                if symbol.strip()[-1:].isupper():
                    continue
            cleaned = stem
            break
        return cleaned

    def resolve(self, symbol: Any) -> str | None:
        if not isinstance(symbol, str) or not symbol.strip():
            return None
        cached = self._cache.get(symbol)
        if cached is not None:
            return cached
        cleaned = self._strip(symbol)
        canonical = self._exact.get(cleaned)
        if canonical is None:
            for pattern, target in self._patterns:
                if pattern.fullmatch(cleaned):
                    canonical = target
                    break
        if canonical is None:
            self._unmapped[symbol] = self._unmapped.get(symbol, 0) + 1
            self._unmapped_seen[symbol] = time.time()
            self.unmapped_count += 1
            if not self._passthrough_unknown:
                return None
            canonical = cleaned
        self._cache[symbol] = canonical
        self.resolved_count += 1
        return canonical

    def is_mapped(self, symbol: Any) -> bool:
        if not isinstance(symbol, str) or not symbol.strip():
            return False
        cleaned = self._strip(symbol)
        if cleaned in self._exact:
            return True
        return any(pattern.fullmatch(cleaned) for pattern, _ in self._patterns)

    async def _on_account(self,payload):
        if self._running and isinstance(payload,dict) and payload.get("account_id"): self._current_account=str(payload["account_id"])

    async def _on_specs(self,payload):
        if not self._running or not isinstance(payload,dict): return
        for row in payload.get("symbols",[]) if isinstance(payload.get("symbols"),list) else []:
            if isinstance(row,dict) and row.get("symbol"):
                self._specs[(str(row.get("account_id") or payload.get("account_id") or ""),str(row["symbol"]).upper())]=dict(row)

    async def _on_ctrader_specs(self, payload):
        if not self._running or not isinstance(payload, dict): return
        for row in payload.get("symbols", []) if isinstance(payload.get("symbols"), list) else []:
            if isinstance(row, dict) and row.get("symbol"):
                key = (str(row.get("account_id") or payload.get("account_id") or ""), str(row["symbol"]).upper())
                self._reference_specs[key] = dict(row)

    async def _on_resolve_new(self, payload):
        if not self._running or self._context is None or not isinstance(payload, dict):
            return
        logical = str(payload.get("logical_symbol") or payload.get("symbol") or "").strip().upper()
        account = str(payload.get("account_id") or "").strip()
        requested_broker_symbol = str(
            payload.get("broker_symbol")
            or self._broker_map.get((account + "|" + logical).upper(), "")
        ).strip().upper()
        canonical = self.resolve(logical)
        if not logical or not account or canonical is None:
            await self._context.publish(EVENT_RESOLVED_NEW, {
                "request_id": payload.get("request_id"), "account_id": account,
                "logical_symbol": logical, "status": "SYMBOL_UNRESOLVED",
                "approved": False, "reason": "MISSING_ACCOUNT_OR_SYMBOL",
            })
            return

        def matches(symbol: str) -> bool:
            if requested_broker_symbol:
                return symbol == requested_broker_symbol
            return symbol in {logical, str(canonical).upper()} or self.resolve(symbol) == canonical

        exact = [(owner, symbol, row) for (owner, symbol), row in self._specs.items()
                 if owner == account and matches(symbol)]
        fallback = [(owner, symbol, row) for (owner, symbol), row in self._specs.items()
                    if not owner and matches(symbol)]
        candidates = exact or fallback
        if len(candidates) != 1:
            reason = "SYMBOL_AMBIGUOUS" if len(candidates) > 1 else "SYMBOL_UNRESOLVED"
            await self._context.publish(EVENT_RESOLVED_NEW, {
                "request_id": payload.get("request_id"), "account_id": account,
                "logical_symbol": logical, "status": "SYMBOL_UNRESOLVED",
                "approved": False, "reason": reason,
            })
            return
        _, resolved, row = candidates[0]
        await self._context.publish(EVENT_RESOLVED_NEW, {
            "request_id": payload.get("request_id"), "account_id": account,
            "broker": payload.get("broker"), "logical_symbol": logical,
            "broker_symbol": resolved, "asset_canonical": canonical,
            "status": "RESOLVED", "approved": True, "spec": dict(row),
        })

    async def _on_resolve_requested(self, payload: dict[str, Any]) -> None:
        if not self._running or self._context is None:
            return
        if not isinstance(payload, dict):
            return
        symbol = payload.get("symbol")
        canonical = self.resolve(symbol)
        mapped = self.is_mapped(symbol)
        body: dict[str, Any] = {
            "request_id": payload.get("request_id"),
            "account_id": payload.get("account_id"),
            "symbol": symbol,
            "canonical": canonical,
            "mapped": mapped,
        }
        stamp = payload.get("timestamp")
        if isinstance(stamp, (int, float)):
            body["timestamp"] = stamp
        await self._context.publish(EVENT_RESOLVED, body)
        if not mapped:
            await self._context.publish(EVENT_UNMAPPED, dict(body))

    async def snapshot(self) -> dict[str, Any]:
        def rows(source):
            return [{"account_id": account, "symbol": symbol, "spec": dict(spec)}
                    for (account, symbol), spec in source.items()]
        return {"version": ATOM_VERSION, "cache": dict(self._cache),
                "unmapped": dict(self._unmapped),
            "unmapped_seen": dict(self._unmapped_seen),
            "specs": rows(self._specs),
                "reference_specs": rows(self._reference_specs),
                "current_account": self._current_account,
                "resolved_count": self.resolved_count,
                "unmapped_count": self.unmapped_count}

    async def restore(self, state: dict[str, Any]) -> None:
        if not isinstance(state, dict):
            raise ValueError("INVALID_SYMBOL_REGISTRY_STATE")
        def load(value):
            if not isinstance(value, list):
                raise ValueError("INVALID_SYMBOL_REGISTRY_STATE")
            result = {}
            for item in value:
                if (not isinstance(item, dict) or not item.get("symbol")
                        or not isinstance(item.get("spec"), dict)):
                    raise ValueError("INVALID_SYMBOL_REGISTRY_STATE")
                key = (str(item.get("account_id") or ""), str(item["symbol"]).upper())
                result[key] = dict(item["spec"])
            return result
        self._cache = {str(k): str(v) for k,v in (state.get("cache") or {}).items()}
        self._unmapped = {str(k): int(v) for k,v in (state.get("unmapped") or {}).items()}
        # لقطة قديمة (قبل 2.6.0) لا تحمل الأزمنة: تُقرأ صفرًا فتُعدّ بائتة فورًا —
        # وهو الصواب، لأنّ رمزًا من حياة سابقة لم يُرَ في هذه الحياة بعد.
        self._unmapped_seen = {str(k): float(v)
                               for k, v in (state.get("unmapped_seen") or {}).items()}
        self._specs = load(state.get("specs", []))
        self._reference_specs = load(state.get("reference_specs", []))
        self._current_account = str(state.get("current_account") or "")
        self.resolved_count = int(state.get("resolved_count") or 0)
        self.unmapped_count = int(state.get("unmapped_count") or 0)

    async def health_check(self) -> HealthStatus:
        if not self._running:
            return HealthStatus(state=HealthState.UNHEALTHY, message=REASON_NOT_STARTED)
        # الحيّ وحده يُعلَن عطلًا؛ والبائت يبقى مرئيًّا بالتفاصيل مؤرَّخًا لا مخفيًّا.
        now = time.time()
        live = sorted(sym for sym in self._unmapped
                      if now - self._unmapped_seen.get(sym, 0.0) <= UNMAPPED_STALE_AFTER_S)
        stale = sorted(set(self._unmapped) - set(live))
        details = {
            "aliases": len(self._exact), "patterns": len(self._patterns),
            "resolved": self.resolved_count, "unmapped": self.unmapped_count,
            "unmapped_symbols": dict(self._unmapped),
            "unmapped_live": live,
            "unmapped_stale": {sym: round(now - self._unmapped_seen.get(sym, 0.0), 1)
                               for sym in stale},
            "unmapped_stale_after_s": UNMAPPED_STALE_AFTER_S,
            # نمطٌ رفضته `re` عند الإقلاع: رمزٌ لن يُطابَق أبدًا، وعلّته مطبعةٌ
            # في العقد لا في السوق. كان يُسقَط بصمتٍ فيُقرأ `UNMAPPED` بلا سبب.
            "bad_patterns": dict(self._bad_patterns),
        }
        if self._bad_patterns:
            return HealthStatus(
                state=HealthState.DEGRADED,
                message="BAD_SYMBOL_PATTERN: %s" % ", ".join(sorted(self._bad_patterns)),
                details=details)
        if not self._exact and not self._patterns:
            return HealthStatus(
                state=HealthState.DEGRADED, message=REASON_NO_MAP, details=details)
        if live:
            return HealthStatus(
                state=HealthState.DEGRADED,
                message="unmapped: %s" % ",".join(live), details=details)
        # لا رمز حيّ بلا خريطة. إن بقي بائت، يُقال بصراحة أنّه بائت — لا يُطمس
        # ولا يُعرض عطلًا: «سليم، وسبق أن مرّ كذا رمزًا لم يعد يصل».
        if stale:
            return HealthStatus(
                state=HealthState.HEALTHY, details=details,
                message="resolved=%d · بائت بلا خريطة (لم يعد يصل): %s"
                        % (self.resolved_count, ",".join(stale)))
        return HealthStatus(
            state=HealthState.HEALTHY,
            message="resolved=%d" % self.resolved_count, details=details)
