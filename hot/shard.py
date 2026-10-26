# -*- coding: utf-8 -*-
"""§5 / Gate D — عامِلٌ في **عمليّةٍ مستقلّة**: الوحدة التي تُقاس.

## لماذا عمليّةٌ لا خيط

مقيسٌ على هذا الجهاز: `python 3.12.10` و`sys._is_gil_enabled() == True`.
فالخيوط لا تُعطي توازيًا لمعالِجٍ بايثونيٍّ خالص — وكلُّ معالجات الذرّات
كذلك. فالعامل عمليّةٌ أو لا يكون، وكلُّ ما دون ذلك قياسُ سرابٍ متوازٍ.

## ما يُقاس هنا بالضبط

    إطارٌ يصل ⟶ فكُّ ترميز ⟶ توجيهٌ بالملكيّة ⟶ عملُ التِكّة ⟶ صفّ

وعملُ التِكّة **مُعايَرٌ لا مُفترَض**: دورانُ معالجٍ خالصٌ يُقاس زمنُ
دورته عند الإقلاع، ثمّ يُطلَب منه كلفةٌ بالنانو ثانية فيوفّيها.

    ⛔ ولا يُستعمَل `sleep`: النوم يُخلي المعالج فيبدو العامل رخيصًا
       وتظهر سعةٌ لا وجود لها. العمل عملٌ أو لا يُقاس.

## التأخّر — يُقاس على الجدول لا على الوصول

لكلّ واقعةٍ موعدٌ مشتقٌّ من رقمها العالميّ ومعدّل الضخّ:

    due(k) = t0 + k / tick_rate          و`k` ترتيبُ التِكّة لا الواقعة
    latency = اكتمالُ المعالجة − due(k)

فيلتقط التأخّرُ **الانتظارَ في الطابور** كما يلتقط زمنَ المعالجة. ولو
قِيس من لحظة الاستلام لأخفى الطابورَ كلَّه — وهو عينُ ما نبحث عنه.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

#: حمولةُ المعايرة — عددُ الدورات الذي يُقاس زمنُه مرّةً عند الإقلاع.
_CALIBRATION_SPINS = 200_000


def burn(spins: int) -> int:
    """دورانُ معالجٍ خالصٌ وحتميّ — لا تخصيصَ ولا نداءَ نظام.

    ⛔ ولا `time.sleep`: النائم يُخلي النواة فيبدو العامل رخيصًا.
    """
    value = 12345
    for _ in range(spins):
        value = (value * 1103515245 + 12345) & 0x7FFFFFFF
    return value


def calibrate() -> float:
    """نانو ثانيةٌ لكلّ دورة — تُقاس على العامل نفسه لا على المُشغِّل.

    والقياس ثلاثُ مرّاتٍ ويُؤخَذ **أصغرها**: الأصغر أقربُ إلى الكلفة
    الحقيقيّة، والأكبر يحمل مقاطعةَ نظامٍ لا كلفةَ شيفرة.
    """
    best = None
    for _ in range(3):
        start = time.perf_counter_ns()
        burn(_CALIBRATION_SPINS)
        elapsed = time.perf_counter_ns() - start
        if best is None or elapsed < best:
            best = elapsed
    return best / _CALIBRATION_SPINS


def run_shard(conn: Any, result_q: Any, *, index: int, workers: int,
              out_path: str, tick_rate: float,
              tick_cost_ns: int, deadline_s: float,
              real_atoms: bool = False) -> None:
    """نقطةُ دخول العمليّة. تُبلِغ جاهزيّتها، تتسلّم الصفر، ثمّ تقيس.

    ⛔ والمصافحةُ ليست ترفًا: بلا انتظارٍ لجاهزيّة العمّال كان الضخّ يبدأ
    والعمليّاتُ ما زالت تُقلِع (spawn على ويندوز + استيراد + تجميعُ خطّةٍ
    يقرأ كلّ المانيفستات). فيتراكم أوّلُ الشريط في الأنبوب ويُقاس **زمنُ
    إقلاعٍ** على أنّه تأخّرُ معالجة: قِيس `p99 = 1,060 م.ث` والمعالج ٠٫٢٪.
    """
    import struct

    from hot import frame, gc_gate, parity, planner, runtime

    ns_per_spin = calibrate()
    spins = int(tick_cost_ns / ns_per_spin) if tick_cost_ns > 0 else 0

    plan = planner.compile_plan(known_external=planner.external_events())
    # عاملٌ واحدٌ داخل العمليّة: التقسيم وقع في المُغذّي، وهذا ينفّذ نصيبه.
    engine = runtime.HotEngine(plan, out_path, workers=1,
                               runtime="gate-d-w%d" % index)

    # ── الذرّات الحقيقيّة داخل العامل ────────────────────────────────────
    #
    # ⛔ بلا هذا يقيس الحاملُ سقالةً وحِملًا مُعايَرًا. وختم المالك
    #    `NQ — RERUN GATE D UNDER FREEZE` يطلب السعةَ الحقيقيّة، فيُشغَّل
    #    `AtomHost` نفسُه الذي قاس كلفةَ الدورة — لا نسخةٌ ثانية.
    #
    #    ولكلّ عمليّةٍ صندوقُها الرمليّ: قواعدُ منسوخةٌ باسمٍ يحمل رقمَ
    #    العامل، وإلّا تنازع سبعةُ عمّالٍ على ملفٍّ واحد.
    host = None
    guard = None
    if real_atoms:
        import asyncio
        from pathlib import Path as _Path

        from hot.atom_host import AtomHost, SideEffectGuard
        guard = SideEffectGuard(sandbox=_Path(out_path) / ("sandbox-%d" % index))
        guard.install()
        host = AtomHost(plan, guard=guard)
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(host.boot())

    # ── حدُّ الإقلاع: بعد الاستيراد والخطّة والمحرّك، قبل أوّل واقعة ──────
    #
    # ختم المالك `NQ — APPLY GC FREEZE AFTER BOOT`. وموضعُه هنا بعينه:
    # كلُّ ما يبنيه العامل مرّةً واحدةً قد اكتمل، ولم تصل واقعةٌ بعد.
    gc_record = gc_gate.freeze_after_boot()

    result_q.put({"ready": index})
    t0 = struct.unpack("<d", conn.recv_bytes())[0]

    latencies: list[float] = []
    #: ⚠️ مقياسٌ ثانٍ لازم: من **لحظة وصول الإطار** إلى اكتمال المعالجة.
    #: الأوّل يُقاس على الجدول فيحمل انحرافَ المُغذّي معه، وهذا لا يحمله.
    #: والفرق بينهما هو كلفةُ الحامل بعينها — فتُعرَض ولا تُنسَب للمحرّك.
    service: list[float] = []
    ticks = 0
    records = 0
    deadline_misses = 0          # على المحرّك وحده
    schedule_misses = 0          # على الجدول — يحمل انحرافَ المُغذّي معه
    max_depth = 0
    oldest_pending = 0.0
    cpu0 = time.process_time()
    wall0 = time.perf_counter()
    first_at = None
    last_at = None

    #: زمنُ دورة الذرّات وحدها — يُفصَل عن زمن الواقعة كما طلب المالك.
    cycles_ns: list[int] = []
    backlog_max = 0
    frames = 0
    frames_with_backlog = 0
    while True:
        # ⛔ التراكم يُقاس هنا: هل كان إطارٌ ينتظر **قبل** أن نطلبه؟ عاملٌ
        #    يلحق يجد أنبوبَه فارغًا دائمًا. وعاملٌ يتراكم عليه العمل يجد
        #    الوارد جاهزًا كلّ مرّة، ويطول صفُّه.
        waiting = 0
        while conn.poll():
            waiting += 1
            break                      # `poll` لا يعدّ، فيكفي «هل ثمّة وارد»
        blob = conn.recv_bytes()
        if not blob:
            break
        frames += 1
        if waiting:
            frames_with_backlog += 1
            if waiting > backlog_max:
                backlog_max = waiting
        arrived = time.time()
        _header, rows = frame.decode(blob)
        pending = len(rows)
        if pending > max_depth:
            max_depth = pending
        for global_index, name, payload in rows:
            engine.feed(name, payload)
            records += 1
            pending -= 1
            if name == parity.TICK_EVENT:
                if host is not None:
                    # الدورة الحقيقيّة: ١٦٣ ذرّةً بترتيب الخطّة
                    outcome = loop.run_until_complete(
                        host.cycle(parity.TICK_EVENT, payload))
                    cycles_ns.append(outcome["wall_ns"])
                    del host.published[:]      # لا يُبنى هرمٌ يكنسه الكانس
                elif spins:
                    burn(spins)
                ticks += 1
                now = time.time()
                # الفهرس على السلك = ترتيبُ التِكّة في الجدول (انظر المُغذّي).
                due = t0 + global_index / tick_rate
                lag = now - due
                latencies.append(lag)
                service.append(now - arrived)
                if lag > oldest_pending:
                    oldest_pending = lag
                if lag > deadline_s:
                    schedule_misses += 1
                # ⛔ والتمييز لازم: تجاوزٌ سببُه انحرافُ المُغذّي ليس تجاوزَ
                #    محرّك. فيُعدّ على **ما يملكه العامل**: من وصول الإطار
                #    إلى اكتمال المعالجة. وإلّا سقطت البوّابة على حاملها —
                #    وهي عينُ الغلطة التي وقعت في Gate C ثمّ صُحِّحت.
                if now - arrived > deadline_s:
                    deadline_misses += 1
                if first_at is None:
                    first_at = now
                last_at = now

    cpu = time.process_time() - cpu0
    atoms_booted = len(host.loaded) if host is not None else 0
    if guard is not None:
        guard.remove()
    atom_ms = sorted(v / 1e6 for v in cycles_ns)
    wall = time.perf_counter() - wall0
    # ── الانحراف: هل يكبر التأخّر مع مضيّ التشغيل؟ ───────────────────────
    #
    # ⛔ هذا هو معيار «لا تراكم» بعينه، ولا يُستبدَل بـ`p99`: تأخّرٌ ثابتٌ
    #    عالٍ يعني كلفةً، وتأخّرٌ **ينمو** يعني أنّ الوارد أسرع من الخدمة.
    #    والأوّل يُحتمَل والثاني ينكسر بعد دقيقةٍ أو ساعة.
    ordered = latencies                        # بترتيب الوصول لا مرتَّبةً
    slice_n = max(1, len(ordered) // 5)
    head = sum(ordered[:slice_n]) / slice_n if ordered else 0.0
    tail = sum(ordered[-slice_n:]) / slice_n if ordered else 0.0
    merged = engine.close()
    stats = engine.stats()
    latencies.sort()
    service.sort()

    def _pick(values: list[float], fraction: float) -> float:
        if not values:
            return 0.0
        position = min(len(values) - 1,
                       max(0, int(round(fraction * (len(values) - 1)))))
        return values[position]

    def pct(fraction: float) -> float:
        return _pick(latencies, fraction)

    def svc(fraction: float) -> float:
        return _pick(service, fraction)

    result_q.put({
        "worker": index,
        "pid": os.getpid(),
        "records": records,
        "ticks": ticks,
        "cycles": len(merged),
        "cpu_s": cpu,
        "wall_s": wall,
        "ns_per_spin": ns_per_spin,
        "spins_per_tick": spins,
        "gc_enabled_after": gc_record["still_enabled"],
        "gc_frozen": gc_record["after"]["frozen"],
        "gc_newly_frozen": gc_record["newly_frozen"],
        "gc_tracked_after": gc_record["after"]["tracked"],
        "atoms_booted": atoms_booted,
        "atom_p50": _pick(atom_ms, 0.50),
        "atom_p95": _pick(atom_ms, 0.95),
        "atom_p99": _pick(atom_ms, 0.99),
        "atom_max": atom_ms[-1] if atom_ms else 0.0,
        "p50": pct(0.50),
        "p95": pct(0.95),
        "p99": pct(0.99),
        "svc_p50": svc(0.50),
        "svc_p95": svc(0.95),
        "svc_p99": svc(0.99),
        "svc_max": service[-1] if service else 0.0,
        "max_lag": latencies[-1] if latencies else 0.0,
        "oldest_pending": oldest_pending,
        "deadline_misses": deadline_misses,
        "schedule_misses": schedule_misses,
        "max_batch_depth": max_depth,
        "frames": frames,
        "frames_with_backlog": frames_with_backlog,
        "backlog_max": backlog_max,
        "lag_head_ms": head * 1000.0,
        "lag_tail_ms": tail * 1000.0,
        "lag_drift_ms": (tail - head) * 1000.0,
        "busy_fraction": cpu / wall if wall > 0 else 0.0,
        "first_at": first_at,
        "last_at": last_at,
        "owner_violations": stats["foreign_cycles"],
        "dropped_no_owner": stats["dropped_no_owner"],
        "ticks_admitted": stats["ticks_admitted"],
        "ticks_rejected": stats["ticks_rejected"],
        "out_path": out_path,
    })
