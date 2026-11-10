"""٥٥٥ — نصّ الشارة وحده: العيار، وسطر «منذ الإقلاع» بحصيلته وأسبابه.

v1.24.1 (٢٠٢٦-١٠-٠١، ختم `Nq`): نُقل صوغُ النصّ من `health_check` في `atom.py`
**حرفيًّا** كي ينزل تحت حدّ المادة 9 (٤٠٠ سطر فعليّ). `health_check` نفسها باقيةٌ
في `atom.py` بحالاتها وتفاصيلها وترتيبها: هي التي تقرّر HEALTHY/UNHEALTHY وتضع
`halt` أوّلًا و`dials` آخرًا، وهذا الملفّ يصوغ النصّ وحده. والفرقُ الوحيد أنّ
`self` صار `atom` — لا حقل ولا ترتيب ولا رمز تغيّر.
"""
from __future__ import annotations

import time

from entry_request_sizing import MIN_SETUP_RATIO, MIN_STOP_PIPS


def halt_text(atom) -> str:
    """سطرُ الإيقاف أوّل الرسالة — عامٌّ أو بحساباته.

    ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): الإيقاف صار لكلّ حساب، فيُسمّى من
    أُوقف بدل «موقوف» واحدة لا تقول لمن.
    """
    if atom._halt_all:
        return "🔴 موقوف (كلّ الحسابات) — لا أمر يخرج · "
    if atom._halted_accounts:
        return "🔴 موقوف للحسابات [%s] — لا أمر يخرج منها · " % ",".join(
            sorted(atom._halted_accounts))
    return ""


def dials_text(atom) -> str:
    """عيارُ الذرّة كما يُعلَن في ذيل كلّ رسالة (السبب فوق نداءه في `health_check`).

    ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): مضاعفُ البناء ما زال يُقاس ولا يحكم،
    أمّا عند الإرسال فالصافي بعد السبريد والوقف بالنقاط الأساس **يحكمان** — ويُعلَن
    الفرق كي لا يُقرأ «يُقاس ولا يحكم» على الحارس الجديد.
    """
    return (" | عيار: هدف %gR على البناء يُقاس · عند الإرسال: صافي≥%g بعد السبريد"
            " ووقف≥%g بِب (ولكلّ رمزٍ حدّه) يحكمان (حكم المالك ٢٠٢٦-٠٩-٢٨ · البِب ١٠-١٧)"
            " مراكز/رمز=%d مهل[حجم=%g هدف=%g طيران=%g]") % (
        atom._min_reward, MIN_SETUP_RATIO, MIN_STOP_PIPS, atom._max_open_per_symbol,
        atom._size_stale_after_s, atom._target_stale_after_s,
        atom._inflight_ttl_s)


def boot_message(atom, halt: str, dials: str) -> str:
    """رسالة الصحّة بعد أوّل قرار: `halt` أوّلًا، ثمّ الحصيلة والأسباب، و`dials` آخرًا."""
    return (halt + "منذ الإقلاع: رأى=%d أصدر=%d حجب=[%s]" % (
        getattr(atom, "_seen_boot", 0), getattr(atom, "_emitted_boot", 0),
        " ".join("%s×%d" % (k, v) for k, v in sorted(
            getattr(atom, "_reason_tally", {}).items(),
            key=lambda kv: -kv[1])[:5]) or "—")
            + " | تراكميّ: seen=%d emitted=%d blocked=%d freed=%d تحجيم=%d تعذّر=%d"
              " | إعداد: خانات=%d بلا_جهة=%d ميت=%d | %s last=%s" % (
        atom._seen, atom._emitted, atom._blocked,
        getattr(atom, "_inflight_cleared", 0),
        getattr(atom, "_resized", 0), getattr(atom, "_resize_failed", 0),
        len(atom._setups), getattr(atom, "_setup_missing", 0),
        getattr(atom, "_setup_dead", 0),
        getattr(atom, "_last_resize", "-"), atom._last_reason)
            + " | إعداد وارد: قُبل=%d رُدّ=%d [%s] آخره=%s" % (
                getattr(atom, "_setup_taken", 0),
                getattr(atom, "_setup_refused", 0),
                " ".join("%s×%d" % (k, v) for k, v in sorted(
                    getattr(atom, "_refuse_why", {}).items(),
                    key=lambda kv: -kv[1])) or "—",
                getattr(atom, "_last_refused", "") or "-")
            + (lambda ages: " | أقدم إعدادٍ مخزَّن: %s" % (
                ("%.0f ث (%s %s)" % (max(ages, key=lambda a: a[0])[0],
                                     max(ages, key=lambda a: a[0])[1],
                                     max(ages, key=lambda a: a[0])[2]))
                if ages else "—"))(
                [(time.monotonic() - float(v.get("_received_at") or 0.0), k[0], k[1])
                 for k, v in atom._setups.items() if v.get("_received_at")])
            + " | إعداد استُهلك=%d %s" % (
                getattr(atom, "_setup_consumed", 0),
                getattr(atom, "_last_consumed", "") or "-")
            + " | مستويات: على القرار=%d مخزون=%d" % (
                getattr(atom, "_levels_inline", 0),
                getattr(atom, "_levels_stored", 0))
            + " | وقف التحليل حصرًا: استُعمل=%d · رُدَّ[بلا إعداد=%d بلا إبطال=%d جهة خطأ=%d] %s" % (
                getattr(atom, "_setup_used", 0),
                getattr(atom, "_stop_no_setup", 0),
                getattr(atom, "_stop_no_level", 0),
                getattr(atom, "_stop_wrong_side", 0),
                getattr(atom, "_last_stop_reject", "") or "-")
            + " | هندسة على البناء=%d فات الهدف=%d %s%s" % (
                getattr(atom, "_geometry_at_build", 0),
                getattr(atom, "_target_reached", 0),
                getattr(atom, "_last_drift", "") or "-",
                (" ⟵ " + atom._last_reached) if getattr(atom, "_last_reached", "") else "")
            # ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): ما ردّه حكما الإرسال، وآخره بأرقامه.
            + " | عند الإرسال رُدّ: [%s] %s" % (
                " ".join("%s×%d" % kv for kv in sorted(
                    getattr(atom, "_send_blocked", {}).items())) or "—",
                getattr(atom, "_last_send_block", "") or "-")
            + dials)
