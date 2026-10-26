"""Domain control adapters kept outside Core.

Core accepts a generic control-event publisher. This module owns the market
vocabulary and allowlists so the frozen Core does not know the market
business events.
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable


# ٢٠٢٦-٠٩-٠٧ (قرار المالك): حُذفت شجرة السوق الثاني. الفوركس مغلق أصلًا —
# لا حدث تحكّم يُسمح بنشره من اللوحة إلى النواة، والبنية تبقى لأنّ الإغلاق
# نفسه عقدٌ يُفحص (`test_boundary_contracts`).
_CONTROL_EVENTS: dict[str, frozenset[str]] = {
    "forex": frozenset(),
}


ControlPublisher = Callable[[str, dict[str, Any]], Awaitable[None]]


def build_control_event_publisher(domain: str, event_bus: Any) -> ControlPublisher:
    """Return a fail-closed publisher for one externally selected domain."""
    allowed = _CONTROL_EVENTS.get(str(domain).strip().lower(), frozenset())

    async def publish(name: str, payload: dict[str, Any]) -> None:
        if name not in allowed:
            raise PermissionError("event not allowed for selected domain")
        await event_bus.publish(name, payload, publisher="governance.dashboard")

    return publish
