# -*- coding: utf-8 -*-
"""عزل أسطول الفحوص عن سجل العيارات الحي — يسري على كل جلسة pytest من الجذر.

الدرس (166 المقيس + صيد ٢٦-٠٨): اعتماد المالك الحي (مثل ANALYSIS_SPEED=10)
كان سيُقرأ داخل الفحوص عبر approved_value فتنكسر على قيمة يومه لا على عقدها.
كل جلسة فحص تأخذ سجلًا مؤقتًا فارغًا: الساري داخل الفحوص هو قيم المانيفست
ونقاط التطابق دائمًا، واعتماد المالك يبقى ملكًا للنظام الحي وحده.
"""
import os
import tempfile

# ٢٠٢٦-٠٩-٠٣ (فصل ٢٣ · البند ١٢): بعد أن صار `shared/runtime_paths.py` مالك
# الجذور، «العزل» لا يعني السجلّ وحده — بل جذر التشغيل كلّه. قرصٌ مؤقت واحد
# للجلسة: لا الفحوص تكتب في `forex_runtime/var` الحيّ، ولا قيمُ يوم المالك
# تُقرأ داخل فحصٍ فينكسر عقده.
#
# ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): العزل كان بـ`setdefault` — فجلسةٌ تُطلَق من
# بيئة اللوحة (التي ورثت مراسي الحيّ من `governance/app.py`) تبقى على الحيّ، وهو ما
# كتب حدثين تجريبيّين في دفتري 516/518 الحيّين (٢٠٢٦-٠٩-٢٣). ولم يكن يعزل الجسر ولا
# الأخبار أصلًا. الآن يُفرض العزل فرضًا ما لم يُعلَن الخروج منه صراحةً بـ
# `NQ_TESTS_USE_LIVE=1`:
#   · جذر التشغيل ومرسى الحالة وسجلّ المعايرة وقاعدة الأخبار ⟵ مجلّد الجلسة المؤقّت.
#   · الجسر: كلّ قارئٍ له يقدّم `NQ_BRIDGE_DB` على `db_path` المعطى، فمتغيّرٌ مضبوطٌ
#     يُسقط كلّ فحصٍ يبني قاعدته المؤقّتة بيده (14 فحصًا في `tests/` مقيسًا). فيُرفع
#     المتغيّر، ويُوجَّه مرساه نفسه — `APPDATA` الذي تُشتقّ منه قيمة المانيفستات
#     (`%APPDATA%\MetaQuotes\Terminal\Common\Files\nq_brain.db`) ومشغّلُ اللوحة — إلى
#     مجلّد الجلسة. فلا يبلغ جسرَ الإكسبرت الحيّ فحصٌ يعطي مسارًا ولا فحصٌ لا يعطي،
#     ولا فحصٌ يرفع المتغيّر بنفسه (ذرّات 601/609/611/616/618 تفعل ذلك عند الاستيراد).
if os.environ.get("NQ_TESTS_USE_LIVE", "").strip() == "1":
    _TEST_RUNTIME = tempfile.mkdtemp(prefix="nq_runtime_test_")
    os.environ.setdefault("QUANT_RUNTIME_ROOT", _TEST_RUNTIME)
    os.environ.setdefault("QUANT_CORE_STATE_ROOT", _TEST_RUNTIME)
    os.environ.setdefault(
        "QUANT_ANALYSIS_SETTINGS_DB",
        os.path.join(tempfile.mkdtemp(prefix="nq_params_test_"),
                     "analysis_settings.db"))
else:
    _SESSION = tempfile.mkdtemp(prefix="nq_test_session_")
    _TEST_RUNTIME = os.path.join(_SESSION, "runtime")
    os.makedirs(os.path.join(_TEST_RUNTIME, "var", "store"), exist_ok=True)
    os.makedirs(os.path.join(_SESSION, "appdata"), exist_ok=True)
    os.environ["QUANT_RUNTIME_ROOT"] = _TEST_RUNTIME
    os.environ["QUANT_CORE_STATE_ROOT"] = os.path.join(_TEST_RUNTIME, "var")
    os.environ["QUANT_ANALYSIS_SETTINGS_DB"] = os.path.join(
        _TEST_RUNTIME, "var", "store", "analysis_settings.db")
    os.environ["NQ_NEWS_DB"] = os.path.join(_SESSION, "nq_news_test.db")
    os.environ["APPDATA"] = os.path.join(_SESSION, "appdata")
    os.environ.pop("NQ_BRIDGE_DB", None)
    # ١٧/١٠ (ختم المالك «NQ»: «باقي الاستراتيجيّات وقّف بطاقاتها»): مفتاح الاستراتيجيّات الحيّ لا يُقرأ داخل الفحوص —
    # ملفٌّ غائب = كلّها فعّالة، وفحص الإيقاف نفسه يكتب مفتاحه.
    os.environ["NQ_STRATEGY_SWITCH"] = os.path.join(_SESSION, "strategy_switch.json")
