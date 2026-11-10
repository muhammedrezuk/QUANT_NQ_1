"""٤٦٥ — دفتر البطاقات: الكائن الواحد الذي يتبع الزوج حتى إغلاقه.

حكم المالك ٢٠٢٦-٠٩-١٨: «بدي كل قسم تحليل يشتغل على بطاقة وحدة… إذا في بطاقة
شغّالة على زوج مافي بطاقة جديدة على نفس أصل… كلها بمخزن محفوظ، مابدي بطاقة
تضيع، بدي كل يكتب على بطاقة وحدة.»

وكان المقعد ٤٦٥ فارغًا، وهو موضعه الصحيح: بعد البوّابات الثماني وقبل الموافقة
والإرسال (٤٦٦ · ٤٦٧)، فيرى كلّ حكمٍ صدر ويختم البطاقة قبل خروجها.

**لماذا لا تُفتح البطاقة مع أوّل تحليل:** ٤٦٦ يرى ١٣٢٬١٠٩ قرارًا وأربعةٌ من
كلّ خمسةٍ منها انتظار. فتحُ بطاقةٍ لكلٍّ منها يعني مئة ألف بطاقةٍ ميّتة ومئة
ألف كتابةٍ على القرص — وهو ما يقتل المنصّة لا ما يخدمها. فالبطاقة تُولد عند
**أوّل قرارٍ قابلٍ للتنفيذ** على الرمز، وما سبقه من أحكامٍ لا يضيع: يُحفظ في
مسوّدةٍ صغيرة في الذاكرة (ثلاثة رموزٍ × عشرة كتّاب) وتُختم في البطاقة لحظة
ولادتها. فالبطاقة تحمل الأحكام التي صنعتها، لا الأحكام التي تلتها فقط.

**ولا يُكتب إلا المتغيّر:** حارسٌ يقول «مرّت» مليون مرّة صفٌّ واحدٌ بعدّاد، لا
مليون صف. والطيّ في العدّ لا في الحذف — يبقى معلومًا من كتب وماذا ومتى.

**والقرص لا يُمسّ في كلّ حدث:** الكتابات تُجمَّع وتُدفع دفعةً كلّ خمس ثوانٍ،
وعند كلّ انتقال حالةٍ فورًا. وانتقالُ الحالة هو ما يستحقّ القرص.
"""

from __future__ import annotations

import asyncio
import os
import sqlite3
import time
from pathlib import Path
from typing import Any, Callable

from core.contracts.atom import AtomBase, AtomContext, HealthState, HealthStatus
from shared.trade_card import CardStore, STATE_DISPATCHED
# v1.30.1: المنطق نُقل حرفيًّا إلى وحداتٍ شقيقة في هذا المجلّد (حدّ الأربع مئة سطر، المادة ٩
# ملف ٤). أحداثُ النشر تُستورد بأسمائها كي تبقى سطحَ هذه الوحدة كما كانت.
from card_ledger_channels import GATES, WITNESSES, _OPINION_CHANNELS
from card_ledger_common import EVENT_CHANGED, EVENT_CLOSED, EVENT_OPENED, EVENT_REVERSED, _real, _text
import card_ledger_birth
import card_ledger_store
import card_ledger_trade
import card_ledger_writers

ATOM_VERSION = "1.32.1"
# ٢٠٢٦-١٠-٠٩ (ختم المالك «NQ» — الصفقة صافيةً بأجزائها): البطاقة لا تُغلق إلّا بالإغلاق الأخير لتذكرتها.
# كان `on_outcome` يُغلقها عند أوّل جزء (الهدف الأوّل) فتسجّل ثلث العقد وحده (86470: +0.33R والوسيط +2.20R).
# الآن كلّ جزءٍ يُضاف إلى البطاقة وتبقى «منفَّذة» نتيجتها `PARTIAL`، والأخيرُ يُغلقها بصافي الأجزاء ÷ مبلغ
# المخاطرة — الشقيق `card_ledger_legs` والحساب في `shared/trade_net.py`. لا رقم نسخةٍ جديد بأمر الوكيل
# الرئيس (التحميل الحارّ ينشر برفع البيان)؛ يسري بالإقلاع التالي.
# ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): v1.32.1 — نداءُ الانعكاس يُعدّ ولا يُنشر.
# `decision.card.reversed` بلا مستمع في المشروع كلّه، والمستمع مؤجَّلٌ بأمر المالك
# ٢٠٢٦-٠٩-١٨ («تحت دراسة»). فلا يُنشر في الفراغ: العدّاد في الصحّة واللقطة، والسطر على
# البطاقة (`465.reversal_called`) — انظر `card_ledger_birth.call_reversal`.
# v1.32.0 (٢٠٢٦-٠٩-٢٥، ختم المالك «NQ» على «صلح»): جهةُ البطاقة من التنفيذ لا من البوّابة.
# كانت تنقلب مع كلّ عبورٍ معاكس للبوّابة (11,202 انقلابًا في ٢٤ ساعة) وتبقى مستوياتُ
# الجهة الأولى، ولم تصر بطاقةٌ `FILLED` قطّ (٥٦٣ يُعلن الفتح على `execution.command.ack`
# لا على النتيجة) — فـ41 صفقةً حقيقيّة من 195 جهةُ بطاقتها عكسُ جهة أمرها. الآن: البطاقة
# تسمع تأكيد ٥٦٣ فتصير `FILLED` وتأخذ جهتها الحقيقيّة (وتسقط مستوياتُ الجهة الأخرى)،
# والعبورُ المعاكس يُسمّى تعارضًا ولا يقلبها، والمنفَّذة لا تعود «مرسَلة». وإخلاءُ الفكرة
# الميّتة صار مهمّةً مملوكة لا تحجز دورة التِّكّة. الشقيق `card_ledger_trade` يحمل
# المنطق، والاشتراك الجديد في المانيفست — فيسري بإقلاع.
# v1.31.0 (٢٠٢٦-٠٩-٢٥، ختم المالك «Nq كل إصلاحات واختم كل شي» وأمره «اقفل كل مشاكل»):
# حارس الفكرة الميّتة كان يُخلي بطاقاتٍ حيّة. مهلةُ الطيران (٩٠ ث) تُقاس من
# `dispatched_at`، وشرطُه «بلا تذكرة» — والبطاقة المولودة بعد الإقلاع لا تحمل في
# الذاكرة أيًّا منهما: `open_card` لا يكتب الختم، والتذكرة يكتبها ٥٦٣ في المخزن لا
# هنا. فكانت المهلة صفرًا والتذكرة غائبةً أبدًا. مقيس في ٢٤ ساعة (المخزن نفسه):
# ‏46,071 بطاقة، 45,218 منها أُنهيت قبل ٩٠ ث من ولادتها (79751 بعد 0.35 ث)، و‏24
# صفقةً حقيقيّة من 195 أُنهيت بطاقاتها «فكرةً ميّتة بلا تذكرة» **بعد** أن كتب ٥٦٣
# تذكرتها، فبقيت `EXPIRED` وعليها ربحها وخسارتها. والإصلاح هنا لا في الشقيق كي يسري
# بلا إقلاع: انظر `_retire_if_dead` أدناه.
# v1.30.1 (٢٠٢٦-٠٩-٢٣، ختم `nq`): صفر تغيير في السلوك. الملف كان ١١٢٦ سطرًا فعليًّا
# وحدّ المادة ٩ أربع مئة، فنُقل المنطق **حرفيًّا** إلى ستّ وحداتٍ شقيقة
# (`card_ledger_common` · `_channels` · `_store` · `_writers` · `_birth` · `_trade`)
# تأخذ الذرّة أوّلًا مكان `self`، وبقي هنا ما يخصّ الحياة: الإقلاع والاشتراك والإيقاف،
# والنبضة ومهامّها المملوكة (`_pulse_tasks` · `_spawn_watched` · الإلغاء في `stop`)،
# و`_store_error` و`_recover`، والصحّة واللقطة. وكلّ اسمٍ قديم (`_on_setup` · `_write`
# …) بقي بوّابةً رفيعة، فالنداء من الوحدات يمرّ من الذرّة كما كان. وأوّلُ ملفّ اختبار.
# v1.30.0 (٢٠٢٦-٠٩-٢٣، ختم `nq`): `_on_setup` كان يعيد نداء نفسه بعد `_open`
# بلا شرط — وفتحٌ فاشل (قفل) جعله عَودًا بلا قاع: ٩٥٠ `RecursionError` مقيسة.
# v1.29.0 (٢٠٢٦-٠٩-٢٣، ختم `nq`): قفلٌ عابر لا يُميت الدفتر. كلّ خطأ SQLite
# كان يرفع `_store_ready = False` ولا شيء يعيدها — فقفلٌ واحد `database is
# locked` (مقيس: ٢٤ مرّة اليوم منذ ١٧:٣٦) يُسكت النبضة والكتابة والفتح حتّى
# إعادة الإقلاع، والشارة `CARD_STORE_UNAVAILABLE` ثابتة. القفل العابر يُعدّ
# (`lock_waits`) والعمل يُعاد في النبضة التالية؛ والعطب الحقيقيّ يُسقط كما كان
# ثمّ يُفحص كلّ ثلاثين نبضة، فإن عاد المخزن عادت الذرّة بلا إقلاع.
# v1.28.0 (٢٠٢٦-٠٩-٢٣، ختم `nq`): النبضة تُطلق الكتابة والكنس ولا تنتظرهما.
# المقيس حيًّا من `/api/transport-stats` قبل الإصلاح: `SYS_SECOND ⟶ 465`
# ‏795 ث في 1903 نبضة (418 م.ث للنبضة، أسوأها 48.04 ث) = 91٪ من زمن دورات
# النبضة كلّها، و51 من 65 «مهلة دورة» جذرها النبضة. والكنس كان يفتح SQLite
# **على الحلقة نفسها** (قاعدةٌ 95 م.ب ومهلة انشغالٍ عشر ثوانٍ) فيحجز كلّ مشترِك.
# العمل صار مهمّةً مملوكة (`_pulse_tasks` + مراقبة + إلغاء في `stop`) كنمط ٦٠١،
# وقراءتا الكنس في خيط. البيانات والترتيب كما هما.
EVENT_PULSE = "SYS_SECOND"
EVENT_APPROVED = "decision.approved.state"
EVENT_PASSED = "decision.gate.passed"
EVENT_BLOCKED = "decision.gate.blocked"
# ٢٠٢٦-١٠-٠٧ (ختم «NQ»): خرجت decision.scored/filtered/resolved.state وstrategy.aggregate.state — ناشروها (453/454/458/413) أُرشفوا مع فكّ الأقسام عن القرار.
EVENT_SETUP = "strategy.setup.proposed"
EVENT_OUTCOME = "market.outcome.realized"
#: v1.32.0: تأكيدُ التنفيذ من ٥٦٣ — لحظةُ الصفقة الحقيقيّة (انظر `card_ledger_trade.on_ack`).
EVENT_ACK = "execution.command.ack"
EVENT_TICK = "market.tick.validated"

EVENT_CARD = "decision.card.state"

_HEARTBEAT_PULSES = 15
#: كم ينتظر `stop` عمل النبضة الجاري قبل إلغائه — كتابةٌ واحدة تكفيها عادةً
#: أجزاءٌ من الثانية، والمهلة للقاعدة المشغولة (مهلة انشغالها ١٠ ث).
_STOP_WAIT_S = 12.0

REASON_NOT_STARTED = "NOT_STARTED"
REASON_NO_STORE = "CARD_STORE_UNAVAILABLE"
REASON_SCHEMA = "CARD_SCHEMA_INCOMPLETE"


def _rebased_config(raw_cfg: dict[str, Any]) -> dict[str, Any]:
    """يحلّ المسار النسبيّ عند مالك المسارات — لا تحت مجلّد التشغيل.

    نسخةٌ من نمط ٥٦٣: قراءة `var/store/…` نسبةً إلى مجلّد العمل تُنشئ شجرةً
    موازيةً لا يقرأها أحد. وتعذُّر الحلّ يمرّ بلا تعطيل إقلاع.
    """
    here = Path(__file__).resolve()
    code_root = None
    for parent in here.parents:
        if (parent / "shared" / "runtime_paths.py").is_file():
            code_root = parent
            break
    if code_root is None:
        return raw_cfg
    # ✅ أُزيل حقنُ `sys.path` ٢٠٢٦-٠٩-٢٣ — كان **وزنًا ميّتًا**:
    #    `run_core.py:20-22` يضع جذر المشروع في رأس المسار دائمًا، فحارس
    #    `if not in sys.path` يجعل السطرَ لا يفعل شيئًا أبدًا. ونصُّ النواة
    #    صريح (`bootloader.py:252`): «لا حاجة لأن تحقن الذرة `sys.path`
    #    بنفسها». و`code_root` يبقى لأنّ `manifest_config_rebase` يحتاجه.
    try:
        from shared.runtime_paths import manifest_config_rebase
        return manifest_config_rebase(raw_cfg, code_root=code_root)
    except Exception:  # noqa: BLE001 — لا يُعطَّل الإقلاع بأزمة مسار
        return raw_cfg


class Atom(AtomBase):
    def __init__(self) -> None:
        self._context: AtomContext | None = None
        # 🕐 عمرُ هذه النسخة الحيّة — بطلب جلسة اللوحات ٢٠٢٦-٠٩-٢٢.
        #    العدّاد الصفريّ ذو معنيين: «لم يصلها شيء» أو «أُعيد
        #    بناؤها للتوّ بتحميلٍ حارّ». والشارةُ بلا عمرٍ تجعل
        #    القارئ يخمّن — وقد كتبت اللوحةُ إنذارًا كاذبًا بسببه.
        #    فالصفرُ مع عمرٍ ساعتين انقطاعٌ، ومع ثلاثين ثانية بناءٌ جديد.
        self._started_at = time.monotonic()
        self._running = False
        self._store: CardStore | None = None
        self._store_ready = False
        self._last_error = ""
        self._schema_missing: list[str] = []
        self._max_open_age = 1800.0
        self._max_dispatch_age = 900.0
        self._min_rr = 3.0
        self._flush_every = 5.0
        # الحيّ في الذاكرة: رمز ⟶ {card_no, state, side, seen{كاتب.حقل: قيمة}}
        self._live: dict[str, dict[str, Any]] = {}
        self._drafts: dict[str, dict[str, Any]] = {}
        self._pending: list[tuple[int, str, str, Any, float]] = []
        #: تحديثاتُ البطاقة المؤجَّلة — ختم المالك `NQ — MOVE ATOM 465 TO COLD`.
        #:
        #: كان `_update` يُنتظَر **داخل المعالج**، فيدخل `asyncio.to_thread`
        #: وكتابةُ SQLite في زمن التِكّة. والمقيس ٢٠٢٦-٠٩-١٨ على ٣٠٠ دورةٍ
        #: حقيقيّةٍ خارج الناقل أنّ `_on_tick` وحده كلّف **٦٫٦٨ م.ث للنداء**
        #: (‏٩٩٪ من كلفة هذه الذرّة، و٥٢٪ من كلفة الدورة كلِّها)، وأنّ عزلها
        #: يُنزل `p99` من ٢٦٧٫٨ إلى ٢٥٫١ م.ث.
        #:
        #: فالبيانات هي هي والترتيب هو هو — يتبدّل **موضع الكتابة** وحده:
        #: تُجمَّع هنا وتُصرَّف مع النبض كما تُصرَّف الملاحظات منذ البداية.
        self._pending_updates: list[tuple[int, dict[str, Any] | None,
                                          dict[str, Any] | None]] = []
        self._pulses = 0
        self._last_flush = 0.0
        #: عمل النبضة المملوك — يُطلق ولا يُنتظَر، وحارسا التداخل يمنعان نسختين.
        self._pulse_tasks: set[asyncio.Task[Any]] = set()
        self._flushing = False
        self._sweeping = False
        self._recovering = False
        self._lock_waits = 0
        self._recovered = 0
        self._changed = True
        self._opened = 0
        self._reused = 0
        self._dispatched = 0
        self._closed = 0
        self._expired = 0
        # ⚰️ بطاقةٌ أُرسلت ولم تصر أمرًا وماتت فكرتها — تُخلي الخانة.
        self._dead_idea = 0
        # v1.31.0: بطاقةٌ كاد الحارس يُخليها فوجد المخزنُ عليها تذكرة — صفقةٌ حقيقيّة نجت.
        self._ticket_saved = 0
        # v1.32.0: بطاقاتٌ عرفت تنفيذها من التأكيد، ومنها ما أخذ جهته الحقيقيّة منه.
        self._filled = 0
        self._side_from_fill = 0
        # ٢٠٢٦-١٠-٠٩ (ختم المالك «NQ» — الصفقة صافيةً بأجزائها، `card_ledger_legs`): أجزاءٌ جزئيّة سُجّلت على
        # بطاقةٍ بقيت حيّة · أجزاءٌ وصلت بعد إغلاق بطاقة تذكرتها · أجزاءُ تذكرةٍ ليست تذكرة البطاقة · مكرَّرة؛
        # ثمّ ذاكرتان بسقف: تذكرة ⟶ بطاقتها بعد إغلاقها (لجزءٍ متأخّر)، وتذاكرُ مراكز أخرى على الرمز.
        self._partials = 0
        self._late_legs = 0
        self._foreign_legs = 0
        self._dup_legs = 0
        self._final_tickets: dict[str, dict[str, Any]] = {}
        self._foreign_tickets: dict[str, int] = {}
        # تحديثٌ رفضه الفهرس الفريد — يُسقَط وحده ولا يُسقط المخزن.
        self._dup_live = 0
        # 🗂️ آخرُ فكرةٍ انتهت بلا تنفيذ لكلّ رمز — (جهة، دخول، وقف، هدف).
        #    الفكرةُ نفسها لا تأخذ رقمًا ثانيًا (حكم المالك).
        self._spent_idea: dict[str, tuple] = {}
        self._idea_repeat = 0
        self._dead_idea_grace = 90.0
        # ختم `NQ` ٢٠٢٦-٠٩-١٩ — حكم المالك: «بطاقات تبدأ برقم ١ إلى
        # اللانهاية». والعدّ صحيحٌ اليوم (١..٢٩ بلا فجوة، و`AUTOINCREMENT`
        # فلا رقم يُعاد، و٥٣٬٢٦٤ محاولةَ فتحٍ رُفضت ولم تحرق رقمًا).
        # لكنّ الحكم شرطُ **بقاء** لا وصفُ حال: لو ضاع ملفّ القاعدة أو
        # أُعيد بناؤه لعاد العدّ إلى واحدٍ **صامتًا**، ولا شيء في المنصّة
        # يرى ذلك — ٧١٧ يفحص التلف والطابع الزمنيّ لا التسلسل.
        #
        # فالعلامة المائيّة تُحفظ في **اللقطة**، وهي ملفٌّ آخر: لو تراجع
        # عدّاد القاعدة دونها فذاك ترقيمٌ انكسر، ويُصرَّح به في الصحّة.
        self._high_water = 0
        # ⚖️ حكم المالك ٢٠٢٦-٠٩-١٩: **«الرقم للتحليل»**. وتحليلٌ لم يقل أين
        # يدخل وأين يموت وإلى أين يقصد لم يكتمل — فلا يُصرف عليه رقم.
        #
        # مقيس على أوّل تسعٍ وعشرين بطاقة: **خمس عشرة** منها حملت رقمًا بلا
        # دخولٍ ولا وقفٍ ولا هدف (أرقامٌ على فراغ)، وسبعٌ نُفّذت. والسبب أنّ
        # الولادة كانت عند موافقة ٤٦٦ وحدها، و`_on_setup` **يُسقط الإعداد
        # إن لم تكن البطاقة موجودة** — فالسابقُ يضيع واللاحقُ قد لا يأتي.
        #
        # فالميلاد الآن عند **اكتمال الاثنين**: قرارٌ موافَقٌ عليه ومستوياتٌ
        # مطابقةُ الجهة. وأيّهما سبق ينتظر الآخر في `_waiting`، ولا شيء
        # يُفقد — والمالك يستلم بطاقةً يقبلها أو يردّها، لا رقمًا فارغًا.
        #: رمز ⟶ ذرّة ⟶ (اتّجاه، إشارة، قوّة، ثقة) — الأحدث فقط، بلا تاريخ.
        self._opinions: dict[str, dict[str, tuple]] = {}
        self._waiting: dict[str, dict[str, Any]] = {}
        self._incomplete = 0          # تحليلٌ انتظر ولم يكتمل فانقضى
        self._opinion_rows = 0        # كم رأيًا خُتم على آخر بطاقة
        # ⚰️ حكم المالك ٢٠٢٦-٠٩-١٩ — رآه بعينه قبل أن أقيسه:
        # «٣ صفقات متتالية على نفس هدف، كلّ ما يخسر يشتري».
        #
        # المقيس: ثلاث تذاكر على بتكوين بهدفٍ واحد إلى الرقم السادس
        # (82,011.65 · .646 · .648)، والدخول والوقف يتحرّكان. فالوقف حين
        # ضُرب لم يُبطل الفكرة — أُعيد الدخول عليها بالمستوى نفسه.
        #
        # ⛔ وهذا ينقض أساس ما بُني في ٤٠٥ و٤٠٦: الإبطال «حيث تموت
        # الفكرة». فإن ماتت ثمّ أُحييت بهدفها فالإبطال استراحةٌ لا إبطال.
        #
        # وقاعدة «بطاقةٌ واحدة لكلّ رمز» تحمي من **التزامن** لا من
        # **التكرار بعد الموت**. فهذا حارسُها الثاني: هدفُ صفقةٍ ماتت
        # يُحفظ، وما طابقه يُردّ حتّى يمضي العمر أو يتبدّل المستوى.
        self._dead_target: dict[str, tuple[float, float]] = {}
        self._dead_blocked = 0
        self._numbering_broke = ""
        self._rejected_rr = 0
        self._below_floor = 0
        self._mismatched = 0
        self._widened = 0
        self._flipped = 0
        self._margins: list[float] = []
        self._reversal_at: dict[int, float] = {}
        self._reversals = 0
        self._widened_seen: set[str] = set()
        self._conflicts = 0
        self._writes = 0
        self._folded = 0

    # ------------------------------------------------------------------ حياة

    async def initialize(self, context: AtomContext) -> None:
        self._context = context
        cfg = _rebased_config({k: (str(v).replace(os.sep, "/") if isinstance(v, str) else v)
                               for k, v in context.config.items()})
        self._max_open_age = float(cfg.get("max_open_age_s", 1800.0))
        #: كم يبقى الهدف الميّت محظورًا — بعمر الفكرة المقيس (٧٩ دقيقة
        #: وسيطًا من ولادة الإعداد حتّى الهدف أو الإبطال). فما دون ذلك
        #: إعادةُ دخولٍ على فكرةٍ واحدة، وما بعده مستوًى جديد بحقّ.
        self._dead_target_ttl = float(cfg.get("dead_target_ttl_s", 4740.0))
        self._max_dispatch_age = float(cfg.get("max_dispatch_age_s", 900.0))
        self._min_rr = float(cfg.get("min_rr", 3.0))
        self._reversal_cooldown = float(cfg.get("reversal_cooldown_s", 30.0))
        self._flush_every = float(cfg.get("flush_every_s", 5.0))
        self._store = CardStore(str(cfg.get("store_path", "var/store/trade_cards.db")))
        try:
            await asyncio.to_thread(self._store.ensure)
            # العقد يُفحَص بعد الترقية لا قبلها: ما بقي ناقصًا بعدها اسمٌ
            # أُضيف إلى العقد ونُسي في الهجرة — وذاك يكسر كلّ قراءة صامتًا.
            self._schema_missing = await asyncio.to_thread(self._store.verify)
            self._store_ready = True
        except (OSError, sqlite3.Error) as exc:
            self._last_error = str(exc)
            self._store_ready = False

        context.subscribe(EVENT_PULSE, self._on_pulse)
        context.subscribe(EVENT_APPROVED, self._on_approved)
        context.subscribe(EVENT_PASSED, self._on_passed)
        context.subscribe(EVENT_BLOCKED, self._on_blocked)
        # ٢٠٢٦-١٠-٠٧: لا اشتراك في الدرجة/الفلتر/الحلّ/المحصّلة — ناشروها أُرشفوا، ومعالجاتها خرجت (لا اختبار يستدعيها).
        context.subscribe(EVENT_SETUP, self._on_setup)
        # آراء المحلّلين الأفراد — سبعون قناة، كلٌّ بمغلَّفٍ يحمل اسم صاحبها.
        for _event, (_atom, _label) in _OPINION_CHANNELS.items():
            context.subscribe(_event, self._opinion_handler(_atom, _label))
        context.subscribe(EVENT_OUTCOME, self._on_outcome)
        context.subscribe(EVENT_ACK, self._on_ack)
        context.subscribe(EVENT_TICK, self._on_tick)
        for event, author in GATES:
            context.subscribe(event, self._gate_handler(author))
        for event, author, keys in WITNESSES:
            context.subscribe(event, self._witness_handler(author, keys))

    async def start(self) -> None:
        self._running = True
        self._started_at = time.monotonic()
        if self._store_ready:
            await self._reload_live()

    async def stop(self) -> None:
        # عمل النبضة الجاري يُترك ليكمل (دفعةٌ نُزعت من الطابور تضيع إن قُطعت)،
        # بسقفٍ معلَن، ثمّ يُلغى ما بقي — لا مهمّة تعيش بعد ذرّتها.
        if self._pulse_tasks:
            await asyncio.wait(list(self._pulse_tasks), timeout=_STOP_WAIT_S)
            for task in list(self._pulse_tasks):
                task.cancel()
        # ما في الطابور يُدفع قبل التوقّف — بطاقةٌ لا تضيع ولو بإطفاء.
        # ⛔ والتحديثاتُ منه: تأجيلُها بلا تصريفٍ عند الإطفاء يفقدها.
        if self._store_ready and (self._pending or self._pending_updates):
            try:
                await self._flush()
            except (OSError, sqlite3.Error) as exc:
                self._last_error = str(exc)
        self._running = False

    async def shutdown(self) -> None:
        await self.stop()

    def _store_error(self, exc: BaseException) -> None:
        """قفلٌ عابر يُعدّ ولا يُميت؛ وما عداه يُسقط المخزن حتّى يُفحص ثانيةً."""
        self._last_error = str(exc)
        message = str(exc).lower()
        if isinstance(exc, sqlite3.OperationalError) and (
                "locked" in message or "busy" in message):
            self._lock_waits += 1
            return
        self._store_ready = False

    async def _recover(self) -> None:
        """المخزن سقط: يُفحص في خيط، فإن عاد عادت الذرّة كما في الإقلاع."""
        try:
            await asyncio.to_thread(self._store.ensure)
            self._schema_missing = await asyncio.to_thread(self._store.verify)
        except (OSError, sqlite3.Error) as exc:
            self._last_error = str(exc)
            return
        finally:
            self._recovering = False
        self._store_ready = True
        self._recovered += 1
        await self._reload_live()

    async def _reload_live(self) -> None:
        await card_ledger_store.reload_live(self)

    # ---------------------------------------------------------------- كتابة

    def _write(self, symbol: str, author: str, field: str, value: Any) -> None:
        card_ledger_store.write(self, symbol, author, field, value)

    async def _flush(self) -> None:
        await card_ledger_store.flush(self)

    #: أسماءُ الشهود بالعربيّة — الجدول في `card_ledger_writers` مع الجملة التي تقرؤه.
    _WHO = card_ledger_writers._WHO

    def _compose_reason(self, symbol: str, card: dict[str, Any]) -> str:
        return card_ledger_writers.compose_reason(self, symbol, card)

    async def _announce(self, symbol: str, card: dict, decision_id: str = "") -> None:
        await card_ledger_birth.announce(self, symbol, card, decision_id)

    async def _update(self, card_no: int, fields: Any = None, body: Any = None) -> None:
        await card_ledger_store.update(self, card_no, fields, body)

    # ---------------------------------------------------------------- ولادة

    async def _on_approved(self, payload: dict[str, Any]) -> None:
        await card_ledger_birth.on_approved(self, payload)

    async def _call_reversal(self, symbol: str, card: dict, side: str, payload: dict) -> None:
        await card_ledger_birth.call_reversal(self, symbol, card, side, payload)

    def _same_spent_idea(self, symbol: str, side: str, setup: Any) -> bool:
        return card_ledger_birth.same_spent_idea(self, symbol, side, setup)

    async def _open(self, symbol: str, payload: dict[str, Any], side: str) -> None:
        await card_ledger_birth.open_card(self, symbol, payload, side)

    # ------------------------------------------------------------- كتّابٌ آخرون

    def _gate_handler(self, author: str) -> Callable[[dict[str, Any]], Any]:
        return card_ledger_writers.gate_handler(self, author)

    def _witness_handler(self, author: str, keys: tuple[str, ...]) -> Callable[..., Any]:
        return card_ledger_writers.witness_handler(self, author, keys)

    # ٢٠٢٦-١٠-٠٧ (ختم «NQ»): `_on_scored`/`_on_resolved`/`_on_filtered`/`_on_aggregate` خرجت — أحداثها (453/458/454/413) بلا ناشر بعد الأرشفة.

    def _opinion_handler(self, atom_id: str, label: str):
        return card_ledger_writers.opinion_handler(self, atom_id, label)

    def _stamp_opinions(self, symbol: str) -> int:
        return card_ledger_writers.stamp_opinions(self, symbol)

    def _target_died(self, symbol: str, target: Any, spread: Any, owner: str) -> bool:
        return card_ledger_birth.target_died(self, symbol, target, spread, owner)

    async def _on_setup(self, payload: dict[str, Any]) -> None:
        await card_ledger_birth.on_setup(self, payload)

    async def _retire_if_dead(self, symbol: str, card: dict, price: float | None) -> bool:
        # v1.31.0 — قبل أن يُخلي الشقيقُ بطاقةً: ختمُ الطيران في الذاكرة، والتذكرةُ من
        # المخزن (انظر رأس الملفّ). الختمُ يُكتب أوّلَ ما يُستشار الحارس والبطاقةُ مرسَلة،
        # فلا تُخلى قبل مهلة الطيران منه؛ والمستعادةُ تحمل ختمَ المخزن فلا يُمسّ.
        # والتذكرةُ تُقرأ من المخزن **لحظةَ الإخلاء وحدها**، لا مع كلّ تِكّة: شروطُ
        # الشقيق الرخيصة تُفحص هنا أوّلًا، فلا يُقرأ القرص إلّا لبطاقةٍ سيُخليها. فإن
        # وُجدت تذكرةٌ حُفظت في الذاكرة، وبقيت البطاقة حتّى تُغلقها نتيجتُها.
        # v1.32.0 — وعملُ القرص كلُّه (قراءةُ التذكرة ثمّ الإخلاء) مهمّةٌ مملوكة تُطلق
        # ولا تُنتظر: كان يُنتظر داخل دورة التِّكّة، فمهلة 12:18:11 (5 ث) كانت 465 على
        # `market.tick.validated` وحده. والعلَم `retiring` يمنع مهمّتين لبطاقةٍ واحدة.
        if card.get("state") == STATE_DISPATCHED:
            card.setdefault("dispatched_at", time.time())
        stop = _real(card.get("stop"))
        sent = _real(card.get("dispatched_at")) or _real(card.get("opened_at")) or 0.0
        buy = _text(card.get("side")).lower() == "buy"
        if not (card.get("state") == STATE_DISPATCHED and not card.get("ticket")
                and price is not None and stop is not None and self._store is not None
                and time.time() - sent >= self._dead_idea_grace
                and ((price <= stop) if buy else (price >= stop))):
            return False
        if not card.get("retiring"):
            card["retiring"] = True
            self._spawn_watched(self._retire_owned(symbol, card, price), "465-retire")
        return True

    async def _retire_owned(self, symbol: str, card: dict, price: float) -> None:
        try:
            row = await asyncio.to_thread(self._store.card, card["card_no"])
            if row and row.get("ticket"):
                card["ticket"] = row["ticket"]
                self._ticket_saved += 1
                return
            await card_ledger_trade.retire_if_dead(self, symbol, card, price)
        except (OSError, sqlite3.Error) as exc:
            self._last_error = str(exc)
        finally:
            card["retiring"] = False

    async def _on_tick(self, payload: dict[str, Any]) -> None:
        await card_ledger_trade.on_tick(self, payload)

    async def _on_passed(self, payload: dict[str, Any]) -> None:
        await self._dispatch(payload, STATE_DISPATCHED)

    async def _on_blocked(self, payload: dict[str, Any]) -> None:
        await card_ledger_trade.on_blocked(self, payload)

    async def _dispatch(self, payload: dict[str, Any], state: str) -> None:
        await card_ledger_trade.dispatch(self, payload, state)

    async def _on_outcome(self, payload: dict[str, Any]) -> None:
        await card_ledger_trade.on_outcome(self, payload)

    async def _on_ack(self, payload: dict[str, Any]) -> None:
        await card_ledger_trade.on_ack(self, payload)

    async def _flush_safely(self) -> None:
        try:
            await self._flush()
        except (OSError, sqlite3.Error):
            pass

    async def _flush_owned(self) -> None:
        try:
            await self._flush_safely()
        finally:
            self._flushing = False

    async def _sweep_owned(self, now: float) -> None:
        try:
            await self._sweep(now)
        finally:
            self._sweeping = False

    def _spawn_watched(self, coro: Any, label: str) -> None:
        """يُطلق عملًا لا تنتظره النبضة — مملوكًا ومراقَبًا لا منفلتًا (نمط ٦٠١).

        مرجعه يُحفظ كي لا يُجمَع، وخطؤه يُرفع في `_last_error` لا يُبتلع،
        ويُلغى في `stop`.
        """
        task = asyncio.get_running_loop().create_task(coro, name=label)
        self._pulse_tasks.add(task)

        def _done(finished: asyncio.Task[Any]) -> None:
            self._pulse_tasks.discard(finished)
            if finished.cancelled():
                return
            error = finished.exception()
            if error is not None:
                self._last_error = "%s: %s" % (label, error)

        task.add_done_callback(_done)

    def _read_seq(self) -> int:
        return card_ledger_store.read_seq(self)

    def _read_expired(self, expired: list[int]) -> list[tuple[Any, ...]]:
        return card_ledger_store.read_expired(self, expired)

    # ---------------------------------------------------------------- النبض

    async def _on_pulse(self, payload: dict[str, Any]) -> None:
        if not self._running:
            return
        if not self._store_ready:
            # v1.29.0: المخزن السّاقط يُفحص كلّ ثلاثين نبضة، ولا يُنتظَر.
            self._pulses += 1
            if (self._store is not None and self._pulses % 30 == 0
                    and not self._recovering):
                self._recovering = True
                self._spawn_watched(self._recover(), "465-recover")
            return
        self._pulses += 1
        now = time.time()
        # النبضة نبضةُ الجميع: الكتابة والكنس يُطلقان ولا يُنتظران (v1.28.0).
        if ((self._pending or self._pending_updates) and not self._flushing
                and now - self._last_flush >= self._flush_every):
            self._flushing = True
            self._spawn_watched(self._flush_owned(), "465-flush")
        if self._pulses % 30 == 0 and not self._sweeping:
            self._sweeping = True
            self._spawn_watched(self._sweep_owned(now), "465-sweep")
        if self._context is not None and (
                self._changed or self._pulses % _HEARTBEAT_PULSES == 0):
            self._changed = False
            await self._context.publish(EVENT_CARD, {
                "id": "trade_card_ledger", "atom_id": "465", "status": "ok",
                "open_cards": [{"card_no": card["card_no"], "symbol": symbol,
                                "side": card["side"], "state": card["state"]}
                               for symbol, card in sorted(self._live.items())],
                "opened": self._opened, "dispatched": self._dispatched,
                "closed": self._closed, "expired": self._expired,
                "min_rr": self._min_rr, "rejected_rr": self._rejected_rr})

    async def _sweep(self, now: float) -> None:
        await card_ledger_store.sweep(self, now)

    # --------------------------------------------------------------- الصحّة

    async def health_check(self) -> HealthStatus:
        if not self._running:
            return HealthStatus(state=HealthState.UNHEALTHY, message=REASON_NOT_STARTED)
        details = {"opened": self._opened, "reused": self._reused,
                   "dispatched": self._dispatched, "closed": self._closed,
                   "expired": self._expired, "writes": self._writes,
                   "folded": self._folded, "flipped": self._flipped,
                   "below_floor": self._below_floor, "mismatched": self._mismatched,
                   "stop_widened": self._widened, "reversals": self._reversals,
                   # ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): النداء يُعدّ ولا يُنشر — لا مستمع.
                   "reversal_published": False,
                   "pending": len(self._pending),
                   # طابورٌ جديدٌ يُعرَض ولا يُخفى: طابورٌ ينمو بلا تصريفٍ
                   # يعني بطاقاتٍ لا تصل القرص، وهذا خبرٌ يُقرأ لا يُسكَت.
                   "pending_updates": len(self._pending_updates),
                   "lock_waits": self._lock_waits, "recovered": self._recovered,
                   "partials": self._partials, "late_legs": self._late_legs,
                   "foreign_legs": self._foreign_legs, "dup_legs": self._dup_legs,
                   "last_error": self._last_error}
        if not self._store_ready:
            return HealthStatus(state=HealthState.UNHEALTHY,
                                message="%s %s" % (REASON_NO_STORE, self._last_error),
                                details=details)
        if self._schema_missing:
            return HealthStatus(
                state=HealthState.UNHEALTHY,
                message="%s أعمدة ناقصة: %s" % (
                    REASON_SCHEMA, " · ".join(self._schema_missing)),
                details={**details, "schema_missing": self._schema_missing})
        live = " · ".join("%d:%s %s" % (card["card_no"], symbol, card["state"])
                          for symbol, card in sorted(self._live.items())) or "—"
        margin = "—"
        if self._margins:
            ordered = sorted(self._margins)
            count = len(ordered)
            margin = "p50=%.3f p75=%.3f p90=%.3f n=%d تعارض=%d" % (
                ordered[count // 2], ordered[3 * count // 4],
                ordered[min(count - 1, 9 * count // 10)], count, self._conflicts)
        # العدّادات في `message` لا في `details` — النواة تحذف `details`.
        return HealthStatus(
            state=HealthState.HEALTHY,
            message="بطاقات مفتوحة: %s | فُتحت=%d أُرسلت=%d أُغلقت=%d انتهت=%d "
                    "كتابات=%d مطويّة=%d معلّق=%d رفض_نسبة=%d تعارض_اتّجاه=%d "
                    "دون_أرضيّة_الحركة=%d إعداد_مخالف=%d وقف_وُسِّع=%d "
                    "نداء_انعكاس(يُعدّ_بلا_نشر_لا_مستمع)=%d هدف_ميّت=%d فكرة_ميّتة=%d أُنقذت_بتذكرة=%d رفض_الفهرس=%d فكرة_مكرّرة=%d "
                    "نُفّذت=%d جهة_من_التنفيذ=%d | أجزاء=%d متأخّرة=%d غريبة=%d مكرّرة=%d "
                    "| ينتظر اكتماله=%d لم_يكتمل=%d آراء=%d/%d "
                    "| ترقيم: 1..%d%s | هامش الحسم: %s "
                    "| عيار: ر:م>=%.1f | منذ_الإقلاع=%d" % (
                        live, self._opened, self._dispatched, self._closed,
                        self._expired, self._writes, self._folded,
                        len(self._pending), self._rejected_rr, self._flipped,
                        self._below_floor, self._mismatched, self._widened,
                        self._reversals, self._dead_blocked, self._dead_idea, self._ticket_saved,
                        self._dup_live, self._idea_repeat, self._filled, self._side_from_fill,
                        self._partials, self._late_legs, self._foreign_legs, self._dup_legs,
                        len(self._waiting), self._incomplete,
                        self._opinion_rows, len(_OPINION_CHANNELS),
                        self._high_water,
                        ("" if not self._numbering_broke
                         else " ⛔ تراجع الترقيم %s" % self._numbering_broke),
                        margin, self._min_rr,
                        int(time.monotonic() - self._started_at)),
            details=details)

    # ------------------------------------------------------------- اللقطة

    async def snapshot(self) -> dict[str, Any]:
        # الحيّ لا يُحفظ هنا: مصدره المخزن، وحفظه في لقطةٍ يخلق مصدرين
        # يتناقضان بعد إقلاع. العدّادات وحدها حالةٌ ذاتيّة.
        return {"version": ATOM_VERSION, "opened": self._opened,
                "reused": self._reused, "dispatched": self._dispatched,
                "closed": self._closed, "expired": self._expired,
                "writes": self._writes, "folded": self._folded,
                "rejected_rr": self._rejected_rr, "flipped": self._flipped,
                "below_floor": self._below_floor, "mismatched": self._mismatched,
                "widened": self._widened, "reversals": self._reversals,
                "high_water": self._high_water, "incomplete": self._incomplete}

    async def restore(self, state: dict[str, Any]) -> None:
        if not isinstance(state, dict):
            raise ValueError("INVALID_CARD_LEDGER_STATE")
        try:
            counters = {name: int(state.get(name) or 0) for name in
                        ("opened", "reused", "dispatched", "closed", "expired",
                         "writes", "folded", "rejected_rr", "flipped",
                         "below_floor", "mismatched", "widened", "reversals",
                         "high_water", "incomplete")}
        except (TypeError, ValueError):
            raise ValueError("INVALID_CARD_LEDGER_STATE")
        self._opened = counters["opened"]
        self._reused = counters["reused"]
        self._dispatched = counters["dispatched"]
        self._closed = counters["closed"]
        self._expired = counters["expired"]
        self._writes = counters["writes"]
        self._folded = counters["folded"]
        self._rejected_rr = counters["rejected_rr"]
        self._flipped = counters["flipped"]
        self._high_water = counters["high_water"]
        self._incomplete = counters["incomplete"]
        self._below_floor = counters["below_floor"]
        self._mismatched = counters["mismatched"]
        self._widened = counters["widened"]
        self._reversals = counters["reversals"]
