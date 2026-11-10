"""الرسم الساخن — مَن يستهلك ماذا، ومَن يُنتج ماذا، وأين الدورات.

**الحقيقة من الاشتراك لا من المانيفست:** المانيفست يعلن `subscribes` ولا
تقرؤه النواة؛ الاشتراك يقع حين تنادي الذرّة `context.subscribe(...)`.
فالرسم هنا يُبنى من النداءات نفسها عند الإقلاع — وهو المصدر التنفيذيّ
الوحيد (§٧ من ورقة المحرّك).

**الإنتاج يُرصد لا يُخمَّن:** حين يعالج مشترِكٌ حدثًا وينشر أثناءه حدثًا
آخر، تُسجَّل الحافّة `(المشترِك، الداخل) ⟶ الخارج`. وبعد الختم يُقرأ منها
رسمُ الأحداث ويُفحص للدورات (§١٦ · §١٩): سلسلةُ نداءٍ مباشرة بلا صناديق
تتحوّل إلى حلقةٍ لا نهائيّة عند أوّل دورة — والمزرعة عاشت تضخيم ×١٨ من
تغذيةٍ راجعة واحدة (`transport/atom_host.py`).
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any, Callable


@dataclass(slots=True)
class HotSubscription:
    """اشتراكٌ واحد على المسار الساخن."""

    handler: Callable[..., Any]
    subscriber: str
    is_coro: bool
    #: يعمل بإيقاع «الأحدث يكفي» لكلّ `Account×Symbol` بدل كلّ تِكّة.
    cadence: bool


class HotGraph:
    """مستهلكو كلّ حدث بترتيبٍ ثابت (ترتيب الاشتراك)، وما رُصد من إنتاج."""

    def __init__(self) -> None:
        self._consumers: dict[str, list[HotSubscription]] = defaultdict(list)
        #: `(المشترِك، الحدث الداخل) ⟶ {الأحداث الخارجة}` — مرصودٌ حيًّا.
        self._produced: dict[tuple[str, str], set[str]] = defaultdict(set)
        #: ما نشره ناشرٌ من خارج أيّ دورة (مهامّ التغذية، الساعة، الواجهة).
        self._roots: Counter[str] = Counter()
        self.sealed = False
        #: أحداثٌ ظهرت بعد الختم ولم يعرفها الرسم — تُعدّ بالاسم ولا تُبتلع.
        self.unknown_events: Counter[str] = Counter()

    # ── الاشتراكات ───────────────────────────────────────────────────────

    def add(self, event_name: str, sub: HotSubscription) -> None:
        self._consumers[event_name].append(sub)

    def consumers(self, event_name: str) -> tuple[HotSubscription, ...]:
        subs = self._consumers.get(event_name)
        return tuple(subs) if subs else ()

    def remove_subscriber(self, subscriber: str) -> int:
        removed = 0
        for event_name in list(self._consumers):
            subs = self._consumers[event_name]
            kept = [s for s in subs if s.subscriber != subscriber]
            removed += len(subs) - len(kept)
            if kept:
                self._consumers[event_name] = kept
            else:
                del self._consumers[event_name]
        for key in [k for k in self._produced if k[0] == subscriber]:
            del self._produced[key]
        return removed

    def remove_handler(self, event_name: str, handler: Callable[..., Any]) -> int:
        subs = self._consumers.get(event_name)
        if not subs:
            return 0
        kept = [s for s in subs if s.handler is not handler]
        removed = len(subs) - len(kept)
        if kept:
            self._consumers[event_name] = kept
        else:
            del self._consumers[event_name]
        return removed

    def event_names(self) -> list[str]:
        return list(self._consumers.keys())

    def subscriber_count(self, event_name: str) -> int:
        return len(self._consumers.get(event_name, ()))

    def subscription_count(self) -> int:
        return sum(len(subs) for subs in self._consumers.values())

    def cadence_count(self) -> int:
        return sum(1 for subs in self._consumers.values() for s in subs if s.cadence)

    # ── الرصد ────────────────────────────────────────────────────────────

    def observe_production(self, subscriber: str, inbound: str, outbound: str) -> None:
        self._produced[(subscriber, inbound)].add(outbound)

    def observe_root(self, event_name: str) -> None:
        self._roots[event_name] += 1

    def is_known(self, event_name: str) -> bool:
        return event_name in self._consumers or event_name in self._roots

    def seal(self) -> dict[str, Any]:
        """يختم الرسم ويعيد صورته — والدورات معه إن وُجدت."""
        self.sealed = True
        return self.snapshot()

    # ── الدورات ──────────────────────────────────────────────────────────

    def event_edges(self) -> dict[str, set[str]]:
        """رسم الأحداث: حدثٌ داخل ⟶ ما يُنتَج أثناء معالجته (عبر أيّ مشترِك)."""
        edges: dict[str, set[str]] = defaultdict(set)
        for (_subscriber, inbound), outs in self._produced.items():
            edges[inbound].update(outs)
        return edges

    def cycles(self, *, limit: int = 20) -> list[list[str]]:
        """دوراتُ رسم الأحداث — كلّ دورة مسارًا مغلقًا بأسماء الأحداث.

        بحثٌ بالعمق يلتقط الحوافّ الراجعة. لا يعدّ كلّ الدورات الممكنة
        (قد تكون أسّيّة) — يكفي أن يسمّي ما يوجد ليُفحص بيدٍ بشريّة.
        """
        edges = self.event_edges()
        found: list[list[str]] = []
        seen_cycles: set[tuple[str, ...]] = set()
        WHITE, GREY, BLACK = 0, 1, 2
        color: dict[str, int] = defaultdict(int)
        stack: list[str] = []

        def visit(node: str) -> None:
            if len(found) >= limit:
                return
            color[node] = GREY
            stack.append(node)
            for nxt in sorted(edges.get(node, ())):
                if color[nxt] == GREY:
                    start = stack.index(nxt)
                    cycle = stack[start:] + [nxt]
                    key = tuple(sorted(set(cycle)))
                    if key not in seen_cycles:
                        seen_cycles.add(key)
                        found.append(cycle)
                elif color[nxt] == WHITE:
                    visit(nxt)
            stack.pop()
            color[node] = BLACK

        for node in sorted(edges):
            if color[node] == WHITE:
                visit(node)
        return found

    # ── العرض ────────────────────────────────────────────────────────────

    def dependency_dump(self) -> dict[str, Any]:
        """صورةُ الاعتماد الكاملة — قراءةٌ محضة لا تلمس تنفيذًا.

        `produced`: «المشترِك ⟵ الحدث الداخل ⟶ الأحداث الخارجة» كما رُصد
        حيًّا، فهو الاعتماد **الفعليّ** لا المعلَن في المانيفست.
        `consumers`: «حدث ⟶ المشترِكون» فيُعرف عرضُ كلّ مستوى.
        """
        produced: dict[str, list[str]] = {}
        for (subscriber, inbound), outs in self._produced.items():
            produced["%s|%s" % (subscriber, inbound)] = sorted(outs)
        consumers: dict[str, list[str]] = {}
        for event, subs in self._consumers.items():
            consumers[event] = [str(getattr(s, "subscriber", "؟")) for s in subs]
        return {"produced": produced, "consumers": consumers,
                "roots": dict(self._roots)}

    def snapshot(self) -> dict[str, Any]:
        edges = self.event_edges()
        return {
            "sealed": self.sealed,
            "events": len(self._consumers),
            "subscriptions": self.subscription_count(),
            "cadence_subscriptions": self.cadence_count(),
            "root_events": len(self._roots),
            "produced_edges": sum(len(v) for v in edges.values()),
            "cycles": self.cycles(),
            "unknown_events": dict(self.unknown_events.most_common(20)),
        }
