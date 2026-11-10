from __future__ import annotations

import sqlite3
import time

from brain_bridge_db import _CONNECT_TIMEOUT_S, _load_durable_cursor, _save_durable_cursor

# ٢٠٢٦-٠٩-٢٣ (v4.4.2) — قراءاتُ كاتب الجسر من قاعدة الجسر (للقراءة فقط
# `mode=ro`)، نُقلت **حرفيًّا** من `atom.py` ليعود تحت حدّ ٤٠٠ سطرٍ فعليّ
# (م9/ملف4) — بلا تغيير سلوك: عدّ أوامر الفتح مجهولة المصير (حارس الفتح
# المزدوج)، وسعر دخول المركز (مرساة فحص مسافة الوقف)، ودفعة النتائج من
# جدول `commands` مع المؤشّر الدائم. نصوص SQL والأرقام كما كانت حرفًا بحرف.
# ما كان تابعًا للذرّة (`self`) صار دالّةً تأخذ الذرّة أوّلَ معامل (`atom`)،
# ويبقى في `atom.py` تفويضٌ بالاسم القديم نفسه.

_RESULT_BATCH_LIMIT = 200
# نافذة تسوية الأمر الذي رُدَّ بمهلة: يبقى مجهول المصير خلالها فلا
# يُرسَل بديل. خمس عشرة دقيقة مسنودة بالقياس — أطول احتجاز مرصود عند
# الوسيط كان ١٨ دقيقة (02:27:58 أُرسل · 02:45:11 نُفِّذ).
_TIMEOUT_SETTLE_S = 900.0
# سقفُ اعتبار أمرِ فتحٍ «معلّقًا عند الوسيط». مشتقّ من قياسٍ في هذا
# الملفّ نفسه: أطول احتجازٍ مرصود ١٨ دقيقة (02:27:58 ⟵ 02:45:11)، فثلاثون
# دقيقة = ضِعفه تقريبًا — أعلى من كلّ احتجازٍ حقيقيّ، ودون «إلى الأبد».
_OPEN_STUCK_AFTER_S = 1800.0

#: قيمةُ «لا أعرف» من عدّاد الأوامر العالقة. ليست عددًا بل غيابُ عدد،
#: ولذلك سالبة: أيّ عددٍ حقيقيّ صفرٌ فما فوق.
_PENDING_UNKNOWN = -1

# ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): أيُّ ردٍّ يجمّد، وعلى أيّ نطاق.
#
# كان النمط `result LIKE 'RETCODE_100%'` بلا حساب ولا رمز، والشرح أعلاه (ختم `0fb0df5`،
# ٢٠٢٦-٠٩-٠٦) يقصد **المهلة** وحدها: أمرٌ مصيرُه مجهول قد يُنفَّذ بعد قليل. فكان يطابق الرفض
# القاطع أيضًا — `10019` «لا مال» و`10016` «وقف غير صالح» — وكلاهما لم يُنفَّذ يقينًا. المقيس
# بإعادة ردود الجسر الحيّ الـ83 على أوامر الفتح (10019×48 · 10016×31 · 10012×4): القاعدة
# القديمة جمّدت كلّ دخولٍ على كلّ رمز **1146.5 دقيقة (19.1 ساعة)**، والجديدة 25.8 دقيقة على
# الحساب (المهلات الأربع) و400.7 دقيقة موزّعة على رموزها وحدها؛ ومن 800 فتحٍ ردّه هذا الحارس
# في السجلّات كان 700 سيُكتب (539 خلف 10019 · 157 خلف 10016 على رمزٍ آخر · 4 بلا سبب قائم).
# النصوص من وثائق ميتاتريدر لرموز خادم التداول (والأرقام كما في وحدة MetaTrader5 المضمّنة).
#
# الحساب كلّه — لأنّ المصير مجهول (وهو قصدُ الحارس الأصليّ) أو لأنّ الحساب نفسه لا يتداول:
_FREEZE_ACCOUNT_RESULTS = (
    "RETCODE_10012",        # Request canceled by timeout — حادثة 09-06: نُفّذت الأربعة كلّها
    "RETCODE_10011",        # Request processing error — لم يثبت أنّه لم يُنفَّذ (shared/broker_refusals.py)
    "RETCODE_10028",        # Request locked for processing — كذلك
    "RETCODE_10031",        # No connection with the trade server — كذلك
    "UNKNOWN_AFTER_CRASH",  # الإكسبرت يختم ما التقطه قبل انهياره دون سؤال الوسيط (QUANT_NQ.mq5:2013-2016)
    "RETCODE_10017",        # Trade is disabled — نطاقه حسابٌ أو رمز بلا تمييز، فيُؤخذ الأوسع
    "RETCODE_10026",        # Autotrading disabled by server — الحساب كلّه
    "RETCODE_10027",        # Autotrading disabled by client terminal — الطرفيّة كلّها
)
# الرمز وحده — حالُ الرمز نفسه، ورمزٌ آخر لا شأن له بها:
_FREEZE_SYMBOL_RESULTS = (
    "RETCODE_10018",        # Market is closed — جلسة الرمز
    "RETCODE_10016",        # Invalid stops in the request — مستويات الرمز عند ذلك السعر
)
# وما سواها (10019 لا مال · 10014/10015 حجمٌ أو سعر · 10004/10020/10021/10024 عابر …) رفضٌ قاطع
# لم يُنفَّذ: لا تجميد — الأمر التالي يُحكم عليه بنفسه.


def _to_number(value):
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result == result else None


def count_unsettled_opens(atom, account_id=None, symbol=None) -> int:
    """أوامر فتحٍ مصيرها مجهول — لا يجوز إرسال بديل ما دام أحدها قائمًا.

    صنفان:

    ١) ما التقطه الإكسبرت ولم يُحسم (لا DONE ولا FAILED) — أمرٌ عالق
       لا يُنتج مركزًا يراه الكبح، فيرسل النظام غيره ويتراكم الحجز.

    ٢) **ما فشل بمهلة** — وهذا هو العطب الذي كلّف حساب المالك:
       ٢٠٢٦-٠٩-٠٦، أربعة أوامر رُدّت بـRETCODE_10012 فسجّلها الجسر
       FAILED واعتبرها محسومة، فأرسل بدائل. والمهلة ليست رفضًا: الخادم
       **نفّذها كلها** ثم أفرغ الطابور دفعةً واحدة الساعة 02:45:11 —
       خمس صفقات في الثانية نفسها، ثلاث بيع وشراء متقابلة ألغت
       بعضها. التذاكر 1911177645 · 1911177749 · 1911178075 ·
       1911178187 نُفِّذت ولم يعرفها الجسر قط، وكلّفت 14.42$ من
       78.43$ خسارة اليوم.

    فالأمر الذي رُدَّ بمهلة يبقى **مجهول المصير** حتى يظهر له حدث
    تنفيذ في سجلّ الإكسبرت (فيكون قد نُفِّذ)، أو تمضي نافذة التسوية
    بلا ظهور (فيكون لم يُنفَّذ). النافذة 15 دقيقة مسنودة بالقياس:
    أطول احتجاز مرصود كان 18 دقيقة (02:27:58 → 02:45:11).
    """
    try:
        conn = sqlite3.connect(f"file:{atom._db_path}?mode=ro", uri=True,
                               timeout=_CONNECT_TIMEOUT_S)
        try:
            # ٢٠٢٦-٠٩-١٩ (ختم NQ): كان هذا الفرع **بلا مهلة** ويقرأ
            # `NOT IN (DONE,FAILED)` وحدهما — و`EXPIRED`/`CANCELLED`
            # نهائيّتان واقعًا (٨ و١ في الجدول)، فكان أوّلُ أمرِ فتحٍ
            # ينتهي أو يُلغى يحجب كلّ فتحٍ بعده **إلى الأبد**. و٢٧ من
            # ٣١ فشلًا في سجلّ ٥٠٠-٥٩٩ كانت بهذا السبب: ليس حارسًا
            # يعمل بل بابًا أُغلق ولم يُفتح. المهلة هنا أطول من مهلة
            # الفرع الثاني عمدًا — ذاك يقيس أمرًا مرفوضًا، وهذا يقيس
            # أمرًا قد يكون حيًّا عند الوسيط.
            # ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): الحساب نفسه وحده (`account_id`) — كان
            # العدّ بلا حساب، فأمرٌ عالق لحسابٍ يجمّد غيره. وبلا حساب (نداءٌ قديم) يبقى كما كان.
            scope, scope_args = ("", ()) if not account_id else (" AND account_id=?", (str(account_id),))
            stuck_cutoff = time.time() - _OPEN_STUCK_AFTER_S
            row = conn.execute(
                "SELECT COUNT(*) FROM commands WHERE action='OPEN' "
                "AND status NOT IN ('DONE','FAILED','EXPIRED','CANCELLED') "
                "AND created_at > ?" + scope, (stuck_cutoff,) + scope_args).fetchone()
            pending = int(row[0]) if row else 0
            cutoff = time.time() - _TIMEOUT_SETTLE_S
            # ردودُ الحساب كلّه تُعدّ على كلّ رمز، وردودُ الرمز على رمزها وحده (بلا رمزٍ في
            # النداء تُعدّ كلّها — الأوسع عند الغياب).
            account_marks = ",".join("?" for _ in _FREEZE_ACCOUNT_RESULTS)
            symbol_marks = ",".join("?" for _ in _FREEZE_SYMBOL_RESULTS)
            same_symbol, symbol_args = ("", ()) if not symbol else (" AND c.symbol=?", (str(symbol),))
            row = conn.execute(
                "SELECT COUNT(*) FROM commands c WHERE c.action='OPEN' "
                "AND c.status='FAILED' AND (c.result IN (" + account_marks + ") "
                "OR (c.result IN (" + symbol_marks + ")" + same_symbol + ")) "
                "AND c.created_at > ?" + scope.replace("account_id", "c.account_id") +
                " AND NOT EXISTS ("
                "  SELECT 1 FROM trade_events_v2 e "
                "  WHERE e.request_id = c.request_id AND e.ticket IS NOT NULL)",
                _FREEZE_ACCOUNT_RESULTS + _FREEZE_SYMBOL_RESULTS + symbol_args
                + (cutoff,) + scope_args).fetchone()
            return pending + (int(row[0]) if row else 0)
        finally:
            conn.close()
    except sqlite3.Error as exc:
        # **«لا جدول» ليست «لا أعرف»**: جدولُ الأوامر يبنيه الإكسبرت،
        # وغيابُه يعني أنّه لم يُكتب أمرٌ قطّ — فالعالقُ صفرٌ حقيقةً لا
        # جهلًا. كشفَته ثلاثةُ اختباراتٍ سقطت حين سوّيتُ الحالتين،
        # وكانت محقّة: قاعدةٌ نظيفة بلا جدولٍ ليست قاعدةً مجهولة.
        if "no such table" in str(exc).lower():
            return 0
        # ٢٠٢٦-٠٩-٢٣ (تدقيق المالك الخارجيّ · ختم NQ): كان يُرجع صفرًا.
        #
        # وصفرٌ هنا لا يعني «لا أمرَ عالق» بل **«لم أستطع أن أعرف»** —
        # والفرق بينهما أمرٌ مزدوج على مالٍ حقيقيّ:
        #     OPEN A ⟶ الوسيط لم يحسم ⟶ القراءة تفشل ⟶ الحارس يرى 0
        #            ⟶ OPEN B يُكتب على المركز نفسه
        # وهذا هو النمط الذي سمّاه التدقيق: **تحويلُ عدم معرفة الحالة
        # إلى نتيجةٍ تبدو سليمة**.
        #
        # ولا يُحذف `except`: سقوطُ الذرّة يقطع الجسر كلَّه. تُعلَن
        # الحقيقة كما هي — `UNKNOWN` — ويقفل المستدعي البابَ عليها.
        atom.pending_unknown += 1
        return _PENDING_UNKNOWN


def entry_price(atom, ticket):
    """سعر دخول المركز من الجسر — مرساة فحص مسافة الوقف.

    ٢٠٢٦-٠٩-٠٥ (مقيس): التذكرة تصل نصًّا والعمود عدد صحيح، فكان
    الاستعلام لا يجد صفًّا ويعيد None، فيمرّ الوقف بلا فحص — عبر
    وقف 54,666 على دخول 79,652 (31%) رغم وجود الحارس.
    """
    if ticket in (None, "", 0):
        return None
    try:
        ticket_id = int(float(ticket))
    except (TypeError, ValueError):
        return None
    try:
        conn = sqlite3.connect(f"file:{atom._db_path}?mode=ro", uri=True,
                               timeout=_CONNECT_TIMEOUT_S)
        try:
            row = conn.execute(
                "SELECT entry_price FROM positions_v2 WHERE ticket=?",
                (ticket_id,)).fetchone()
        finally:
            conn.close()
    except Exception:  # noqa: BLE001 — أي عطل قراءة = لا مرساة
        return None
    return _to_number(row[0]) if row else None


def read_results(atom) -> list[tuple]:
    # كان `Atom._read_results` — منقولٌ حرفيًّا، و`self` صار `atom`.
    accounts = sorted(atom._detected_account_ids if atom._current_account_mode else {atom._account_id})
    if not accounts: return []
    marks = ",".join("?" for _ in accounts)
    conn = sqlite3.connect(f"file:{atom._db_path}?mode=ro", uri=True, timeout=_CONNECT_TIMEOUT_S)
    try:
        if atom._result_cursor is None:
            # v4.2.0: المؤشر الدائم أولًا — يستأنف من حيث توقفت آخر حياة
            # فتُنشر نتائج فترة الغياب بدل ابتلاعها. أول تشغيل على
            # الإطلاق فقط يتأسس عند الذيل ويُثبت دائمًا.
            durable = _load_durable_cursor(atom._cursor_db)
            if durable is not None:
                atom._result_cursor = durable
            else:
                row = conn.execute("SELECT COALESCE(MAX(done_at),0),COALESCE(MAX(id),0) FROM commands"
                    f" WHERE done_at IS NOT NULL AND account_id IN ({marks})", accounts).fetchone()
                atom._result_cursor = (float(row[0] or 0.0), int(row[1] or 0))
                _save_durable_cursor(atom._cursor_db, atom._result_cursor)
                return []
        elif not atom._cursor_reconciled:
            # لقطة مستعادة: الأبعد بين اللقطة والدائم يمنع إعادة النشر
            # المزدوج وابتلاع الفجوة معًا.
            durable = _load_durable_cursor(atom._cursor_db)
            if durable is not None and durable > atom._result_cursor:
                atom._result_cursor = durable
        atom._cursor_reconciled = True
        done_at,last_id=atom._result_cursor
        return conn.execute("SELECT id,request_id,action,symbol,side,volume,ticket,status,result,account_id,done_at,params_json FROM commands"
            f" WHERE done_at IS NOT NULL AND account_id IN ({marks}) AND (done_at>? OR (done_at=? AND id>?))"
            " ORDER BY done_at,id LIMIT ?", tuple(accounts)+(done_at,done_at,last_id,_RESULT_BATCH_LIMIT)).fetchall()
    finally: conn.close()
