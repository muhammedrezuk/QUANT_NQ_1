from __future__ import annotations

from core.contracts.atom import AtomBase, AtomContext, HealthState, HealthStatus
from shared.section_contract import section_atom

ATOM_VERSION = "1.3.0"
SNAPSHOT_VERSION = 1

EVENT_VALIDATED = "learning.model.validated"
EVENT_ACTIVE = "learning.model.active.state"
EVENT_OUT = "learning.model.selection"


@section_atom("350", "365")
class Atom(AtomBase):
    def __init__(self) -> None:
        self._context: AtomContext | None = None
        self._running = False
        self._active: dict | None = None
        self._seen = 0
        self._improvement = 0.0
        self._approved = 0
        self._last: tuple | None = None

    async def initialize(self, context: AtomContext) -> None:
        self._context = context
        # v1.2.0: لا تصفير لـ`_active` هنا -- `__init__` ضبطه أصلًا، وتكراره
        # يمحو ما تستعيده اللقطة لو استُدعيت التهيئة بعد الاستعادة يومًا.
        self._improvement = float(context.config.get("min_improvement", 0.0))
        context.subscribe(EVENT_VALIDATED, self._on_validated)
        context.subscribe(EVENT_ACTIVE, self._on_active)

    async def start(self) -> None:
        self._running = True

    async def stop(self) -> None:
        self._running = False

    async def shutdown(self) -> None:
        await self.stop()

    async def _on_active(self, p: dict) -> None:
        if self._running and isinstance(p, dict):
            self._active = dict(p)

    async def _on_validated(self, p: dict) -> None:
        if not self._running or self._context is None or not isinstance(p, dict):
            return
        old = float((self._active or {}).get("accuracy", 0.0))
        new = float(p.get("accuracy", 0.0))
        # v1.2.0: `>=` كان يقبل المساوي تمامًا، و`min_improvement` عيارُه 0.0
        # -- أي أنّ نموذجًا **لا يحسّن شيئًا** يستبدل القائم، ومع ضجيج القياس
        # قد يكون أسوأ منه فعلًا. الشرط صار تحسّنًا حقيقيًّا، بلا اختراع رقم:
        # العيار يبقى كما ختمه المالك، والمقارنة وحدها صُحّحت.
        approved = bool(p.get("passed")) and (
            self._active is None or new > old + self._improvement)
        # 🔎 سببُ الرفض بالرقم — لا «NOT_BETTER» عاريةً. مقيس ٢٠٢٦-٠٩-٢٢:
        #    أربعُ مقارنات و`selected=0` عند ٣٦٦، ولا أحد يعرف أسقطها
        #    التصديق أم المقارنة بالنشِط.
        self._approved += 1 if approved else 0
        self._last = (bool(p.get("passed")), new, old,
                      self._active is not None, bool(approved))
        self._seen += 1
        await self._context.publish(EVENT_OUT, {
            "candidate": dict(p),
            "approved": approved,
            "current_accuracy": old,
            "candidate_accuracy": new,
            "reason": "BETTER_OR_FIRST" if approved else "NOT_BETTER",
        })

    async def snapshot(self) -> dict:
        # v1.1.0: الذرّة كانت بلا لقطة، و`_active` هو **المرجع الذي يُقارَن
        # به كل مرشّح**. وشرط الاعتماد `self._active is None` يقبل المرشّح
        # بلا مقارنة -- فكلّ إقلاع كان ينسى النموذج القائم ويمرّر أوّل
        # مرشّح مهما ضعُف. ٣٦٧ يبثّ الحالة النشطة عند إقلاعه، لكنّ مرشّحًا
        # يسبق ذلك البثّ يعبر بلا حكم. اللقطة أرضيّةٌ حتى يصل البثّ ويصحّح.
        return {"snapshot_version": SNAPSHOT_VERSION,
                "active": self._active, "seen": self._seen}

    async def restore(self, state: dict) -> None:
        if not isinstance(state, dict) or state.get("snapshot_version") != SNAPSHOT_VERSION:
            raise ValueError("INVALID_LEARNING_COMPARISON_SNAPSHOT")
        active = state.get("active")
        self._active = dict(active) if isinstance(active, dict) else None
        self._seen = max(0, int(state.get("seen", 0)))

    async def health_check(self) -> HealthStatus:
        if not self._running:
            return HealthStatus(state=HealthState.UNHEALTHY, message="NOT_STARTED")
        if self._seen:
            return HealthStatus(
                state=HealthState.HEALTHY,
                message=("comparisons=%d وافق=%d نشِط=%s%s") % (
                    self._seen, self._approved, "نعم" if self._active else "لا",
                    ("" if self._last is None else
                     " | آخر: صدّق=%s جديد=%.4f قديم=%.4f ⟹ %s"
                     % ("نعم" if self._last[0] else "لا", self._last[1],
                        self._last[2], "وافق" if self._last[4] else
                        ("لم يُصدَّق" if not self._last[0] else "ليس أفضل")))),
                details={"seen": self._seen, "active": bool(self._active)})
        return HealthStatus(
            state=HealthState.HEALTHY,
            message="READY_AWAITING_FIRST_VALIDATED_MODEL | comparisons=0",
            details={"seen": self._seen, "active": bool(self._active)})
