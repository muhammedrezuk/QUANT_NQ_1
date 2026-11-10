"""٥٥٥ — الصحّة واللقطة والاستعادة.

v1.27.0 (٢٠٢٦-١٠-٢٣، بأمر المالك المختوم على ورقة «خطوط حمراء»): نُقلت هذه الثلاث من `atom.py` **حرفيًّا** كي ينزل تحت حدّ
المادة 9 (٤٠٠ سطر فعليّ) بعد أن زاد عليه سطور القانون 13 (التحوّط) — وكان فوقه قبلها (445). كلّ دالّةٍ كانت تابعًا في صنف
الذرّة، والفرق الوحيد أنّ `self` صار `atom`، وثابتا `atom.py` (`ATOM_VERSION` و`ENTRY_COOLDOWN_S`) يصلان وسيطين.
والتوابع بأسمائها باقيةٌ في `atom.py` تُحيل إلى هنا. لا سلوك جديد.
"""
from __future__ import annotations

import time
from typing import Any

from core.contracts.atom import HealthState, HealthStatus

import entry_request_badge
import entry_request_lines

REASON_NOT_STARTED = "NOT_STARTED"


def health(atom) -> HealthStatus:
    details = {"seen": atom._seen, "emitted": atom._emitted,
               "blocked": atom._blocked, "halted": atom._halted,
               "halt_all": atom._halt_all, "halt_legacy": atom._halt_legacy,
               "halted_accounts": sorted(atom._halted_accounts),
               "scopes_with_size": len(atom._sizes),
               "last_reason": atom._last_reason}
    if not atom._running:
        return HealthStatus(state=HealthState.UNHEALTHY,
                            message=REASON_NOT_STARTED, details=details)
    # 🔴 ٢٠٢٦-٠٩-١٨ — كشفته جلسة اللوحة بالقياس: `halted` كان في
    # `details` وحدها، والنواة تحذفها (`core/api/app.py:93`) — فحالةُ
    # التوقّف **لا تصل اللوحة إطلاقًا**. وهي التي أوقفت التداول اثنتي
    # عشرة ساعة ونصفًا يوم ٢٠٢٦-٠٩-١٨ (`halted: true` بقفلٍ يتيم من
    # `SESSION_LOSS_LIMIT`) ولم تظهر في أيّ شاشة. وكنتُ قد كتبتُ في
    # بلاغي أنّ الشارة «تحمل halted» — لم تكن تحمله. يسبق كلَّ رسالةٍ
    # الآن كي يُقرأ أوّلًا، فالذرّةُ الموقوفة لا تُصدر أمرًا مهما جاءها.
    halt = entry_request_badge.halt_text(atom)
    # ٢٠٢٦-١٠-٢٦ (ختم المالك «nq» بعد فحص المشروع): الحارس الذي لا يعرف يُعلن. بوّابة الوقت والأخبار التي لم تُحمَّل
    # ⟵ غير سليمة، وكلّ دخولٍ يُردّ (إعادة الذرّة لا تُصلحها، والإقلاع يُصلحها). ونبضة الساعة المتوقّفة ⟵ متدهورة: العطب
    # في ذرّة الساعة لا هنا، فلا معنى لإعادة هذه.
    gate = entry_request_lines.gate_block(atom)
    details["gate_block"] = gate
    if gate == entry_request_lines.REASON_GATE_MISSING:
        return HealthStatus(state=HealthState.UNHEALTHY, details=details,
                            message="🔴 %s — كلّ دخولٍ يُردّ حتّى الإقلاع | %s" % (gate, halt))
    if gate:
        halt = "⚠ %s · " % gate + halt
    # ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): الموقوفةُ كانت `HEALTHY` — حيًّا «رأى
    # 54,579 وأصدر 2» وحجب منها 4,752 بالإيقاف وحالتها خضراء (تدقيق ع1). الإيقاف
    # الآن `DEGRADED` في الفرعين؛ الحكم نفسه لم يُمسّ — الصحّة وحدها.
    state = HealthState.DEGRADED if atom._halted or gate else HealthState.HEALTHY
    # ٢٠٢٦-٠٩-١٨ (ختم NQ) — عيارُ هذه الذرّة هو ما يقبل الطلب أو يردّه،
    # وكان غير معلَنٍ في شارةٍ ولا لقطة. وعيارٌ لا يُعلَن لا يُحسَم
    # تعارضُه: المانيفست قد يقول رقمًا والمعتمَد رقمًا آخر، ولا يُعرف
    # أيُّهما يحكم إلّا من فم الذرّة نفسها.
    dials = entry_request_badge.dials_text(atom)
    if atom._seen == 0:
        return HealthStatus(
            state=state, details=details,
            message=halt + "READY_AWAITING_FIRST_APPROVED_DECISION | emitted=0" + dials)
    return HealthStatus(
        state=state, details=details,
        # ٢٠٢٦-٠٩-١٨: سقوطُ الوقف إلى الاحتياطيّ صار له سببان مفرّقان —
        # «لا إعداد لهذه الجهة» و«وصل ومات». وكانا واحدًا قبل مفتاح
        # (رمز × جهة)، ومعهما ثالثٌ مخفيّ: «وصل ودهسه إعداد الجهة
        # الأخرى» — وهو الذي زال، لا الذي يُعدّ.
        message=entry_request_badge.boot_message(atom, halt, dials))


def snapshot(atom, version: str) -> dict[str, Any]:
    return {"version": version, "seen": atom._seen,
            "emitted": atom._emitted, "blocked": atom._blocked,
            "halted": atom._halted,
            # ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): الإيقاف لكلّ حساب يُحفظ كما هو.
            "halt_all": atom._halt_all, "halt_legacy": atom._halt_legacy,
            "halted_accounts": sorted(atom._halted_accounts),
            "send_blocked": dict(atom._send_blocked),
            "resized": getattr(atom, "_resized", 0),
            "resize_failed": getattr(atom, "_resize_failed", 0),
            "last_resize": getattr(atom, "_last_resize", ""),
            "last_request_at": dict(atom._last_request_at),
            "waits": entry_request_lines.snapshot(atom)}


def restore(atom, state: dict[str, Any], cooldown_s: float) -> None:
    if not isinstance(state, dict):
        return
    atom._seen = int(state.get("seen") or 0)
    atom._emitted = int(state.get("emitted") or 0)
    atom._blocked = int(state.get("blocked") or 0)
    # ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): لقطةٌ أقدم من 1.25.0 تحمل `halted`
    # عامًّا وحده ⟸ تُقرأ إيقافًا لكلّ الحسابات (الاتّجاه الآمن)، وكذلك قائمةٌ مشوّهة.
    raw_accounts = state.get("halted_accounts")
    atom._halted_accounts = ({str(a) for a in raw_accounts if str(a)}
                             if isinstance(raw_accounts, list) else set())
    # ٢٠٢٦-١٠-٠٢ v1.25.1 (ختم المالك «صلح كامل nq» — مقيس بعد إقلاع 15:10): 1.25.0 كانت تقرأ
    # halted القديم إيقافًا عامًّا صارمًا لا يفكّه إلّا تحريرٌ بلا حساب، و516 يحرّر بحسابه
    # (AUTO_REARM) فبقيت 555 موقوفة بعد زوال سبب القفل. لقطةُ 1.25.0 نفسها تحمل ذلك الخطأ
    # (halt_all: true وhalted_accounts: [] حيًّا). فالقديم و1.25.0 يُقرآن «إيقافًا موروثًا»:
    # يوقف كلّ حسابٍ حتّى أوّل تحريرٍ — أيّ تحرير — كما كان قبل 1.25.0. والإيقاف العامّ الصارم
    # لا يأتي إلّا من حدث SYSTEM حيّ في 1.25.1 فما بعد.
    legacy_snapshot = "halt_all" not in state or str(state.get("version") or "") == "1.25.0"
    atom._halt_all = bool(state.get("halt_all")) and not legacy_snapshot
    atom._halt_legacy = bool(state.get("halt_legacy")) or (legacy_snapshot and (
        bool(state.get("halt_all")) or (bool(state.get("halted")) and not atom._halted_accounts)))
    raw_last = state.get("last_request_at", {})
    atom._last_request_at = {}
    entry_request_lines.restore(atom, state.get("waits"), time.time())
    if isinstance(raw_last, dict):
        now_restore = time.time()
        for scope, value in raw_last.items():
            try:
                stamp = float(value)
            except (TypeError, ValueError):
                continue
            if now_restore - stamp < cooldown_s:
                atom._last_request_at[str(scope)] = stamp
