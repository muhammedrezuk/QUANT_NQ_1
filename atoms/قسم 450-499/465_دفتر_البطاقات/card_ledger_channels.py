"""٤٦٥ — قنواتُ من يكتب على البطاقة: البوّابات، وشهود السياق، وآراء المحلّلين.

v1.30.1 (٢٠٢٦-٠٩-٢٣، ختم `nq`): الجداول الثلاثة نُقلت **حرفيًّا** من `atom.py`
(حدّ الأربع مئة سطر). الاشتراك نفسه بقي في `initialize` هناك — هنا الجداول وحدها.
"""

from __future__ import annotations

#: البوّابات التي تكتب حكمها في البطاقة — الحدث ومن أصدره، بالترتيب نفسه
#: الذي تظهر به على البطاقة.
GATES: tuple[tuple[str, str], ...] = (
    # ٢٠٢٦-١٠-٠٧ (ختم «NQ»): خرجت بوّابات الثقة/الشروط/التوقيت/المراكز (460–463) — أُرشفت مع فكّ الأقسام عن القرار.
    ("decision.filter.freshness.state", "464"),
    ("decision.filter.asset.state", "468"),
)

#: شهودُ السياق — أقسامٌ ليست لي تكتب على البطاقة نفسها، بحكم المالك
#: ٢٠٢٦-٠٩-١٨: «اقسامهم موجودة تعاونو على صفقة». لكلٍّ (الحدث · الكاتب ·
#: الحقول التي تُقرأ منه). وهي تجيب سؤاله «ليش يرشق صفقات بنص ضوضاء ونيوز»
#: على كلّ بطاقةٍ بعينها بدل أن يُبحث عنه بتنقيب.
WITNESSES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("structure.trend.state", "207", ("state", "direction", "signal")),
    ("structure.phase.state", "208", ("phase", "state", "signal")),
    ("stats.outlier.state", "313", ("outlier", "z_score", "signal")),
    ("stats.quality.state", "316", ("quality", "status", "signal")),
    # ٢٠٢٦-١٠-٠٧ (ختم «NQ»): خرج market.liquidity.updated — ناشره (260) أُرشف مع فكّ الأقسام عن القرار.
    ("news.trading_window.state", "411", ("window", "state", "impact", "signal")),
)

#: ختم `NQ` ٢٠٢٦-٠٩-١٩ — أمر المالك: «كلّه بده يكون موجود بالبطاقة.
#: هذا المحلّل قال شراء وهذا قال بيع… البطاقة بدها تكون علوّه ٧٠٠ سطر
#: ما عندي مشكلة. المهمّ تكون كاملة فيها كلّ شيء.»
#:
#: وكان الدفتر يسمع **حصائل الأقسام** لا آراء أفرادها: ٨٦ قناة رأيٍ
#: فرديّة في المنصّة، يسمع منها ستًّا ويجهل ثمانين. فبطاقةٌ تقول «القسم
#: قال شراء» لا تُجيب بعد ثلاثة أيّام: **أيُّ محلّلٍ أصاب فيُرفع وزنه،
#: وأيُّهم أخطأ فتُعدَّل عتبته؟** وهذا هو الغرض كلّه.
#:
#: والقراءة رخيصة عمدًا: إسنادُ قاموسٍ واحد لكلّ حدث، بلا قرصٍ ولا
#: تحليل. والكتابة تقع **مرّةً عند الميلاد** فتُجمَّد لقطةُ الآراء
#: في لحظتها — «ساعة اللحظة اللي أخذت فيها لقطة».
_OPINION_CHANNELS: dict[str, tuple[str, str]] = {
    "analysis.trend.state": ("151", "الاتجاه"),
    "analysis.momentum.state": ("152", "الزخم"),
    "analysis.volatility.state": ("153", "التذبذب"),
    "analysis.volume.state": ("154", "الحجم"),
    "analysis.spread.state": ("155", "السبريد"),
    "analysis.candle.state": ("156", "الشموع"),
    "analysis.gap.state": ("157", "الفجوات"),
    "analysis.session.state": ("158", "الجلسات"),
    "analysis.time.state": ("159", "أثر الوقت"),
    "analysis.correlation.state": ("160", "الارتباط"),
    "analysis.relative_strength.state": ("161", "القوة النسبية"),
    "analysis.velocity.state": ("162", "السرعة"),
    "analysis.acceleration.state": ("163", "التسارع"),
    "analysis.volume_quality.state": ("164", "جودة الحجم"),
    "analysis.noise.state": ("165", "الضوضاء"),
    "structure.swing.state": ("201", "القمم والقيعان"),
    # ٢٠٢٦-١٠-٠٨ (أمر المالك «أوصل كلّ الأقسام»): الأربعة كانت شهودًا بحقول حكمٍ نُزعت — تُختم حقيقتها الآن.
    "structure.trend.state": ("207", "حالة الاتّجاه"),
    "structure.phase.state": ("208", "طور السوق"),
    "stats.outlier.state": ("313", "كاشف الشذوذ"),
    "stats.quality.state": ("316", "جودة البيانات"),
    "structure.external.state": ("202", "الهيكل الخارجي"),
    "structure.internal.state": ("203", "الهيكل الداخلي"),
    "structure.bos.state": ("204", "كاشف كسر الهيكل"),
    "structure.choch.state": ("205", "كاشف تغيّر الطابع"),
    "structure.mss.state": ("206", "تحوّل الهيكل"),
    "liquidity.pool.state": ("251", "مجمعات السيولة"),
    "liquidity.buyside.state": ("252", "سيولة الشراء"),
    "liquidity.sellside.state": ("253", "سيولة البيع"),
    "liquidity.sweep.state": ("254", "كنس السيولة"),
    "liquidity.fvg.state": ("255", "فجوة القيمة العادلة"),
    # ٢٠٢٦-١٠-٠٧ (ختم المالك «nq»): 256–258 أُرشفت — بلا شريط صفقات عند الوسيط لم تنشر يومًا.
    "liquidity.depth.state": ("261", "محلل العمق"),
    "liquidity.microprice.state": ("262", "محلل الميكرو سعر"),
    "liquidity.ofi.state": ("263", "تدفّق الأوامر"),
    "liquidity.price_impact.state": ("264", "أثر السعر بالدفتر"),
    "stats.mean.state": ("301", "المتوسط"),
    "stats.median.state": ("302", "الوسيط"),
    "stats.mode.state": ("303", "المنوال"),
    "stats.std.state": ("304", "الانحراف المعياري"),
    "stats.variance.state": ("305", "التباين"),
    "stats.cv.state": ("306", "معامل الاختلاف"),
    "stats.correlation.state": ("307", "الارتباط الإحصائي"),
    "stats.regression.state": ("308", "الانحدار الخطي"),
    "stats.r_squared.state": ("309", "معامل التحديد"),
    "stats.zscore.state": ("310", "الدرجة المعياريّة"),
    "stats.skewness.state": ("311", "الالتواء"),
    "stats.kurtosis.state": ("312", "التفلطح"),
    "stats.distribution.state": ("314", "التوزيع"),
    "stats.range.state": ("315", "المدى"),
    "stats.period_compare.state": ("318", "مقارنة الفترات"),
    "probability.trend.state": ("351", "نموذج الاتجاه"),
    "probability.reversal.state": ("352", "نموذج الانعكاس"),
    "probability.breakout.state": ("353", "نموذج الاختراق"),
    "probability.pullback.state": ("354", "نموذج الارتداد"),
    "probability.momentum.state": ("355", "نموذج الزخم"),
    "probability.range.state": ("356", "نموذج المدى"),
    # ٢٠٢٦-١٠-٠٧ (ختم «NQ»): خرج دمج النماذج (357) ومجمّع الثقة (359) — أُرشفا مع فكّ الأقسام عن القرار.
    "probability.hurst.state": ("358", "معامل هيرست"),
    "learning.model.active.state": ("367", "سجلّ نماذج التعلّم"),
    "learning.model.drift.state": ("368", "انجراف التعلّم والتراجع"),
    "strategy.entry_quality.state": ("401", "قواعد الدخول"),
    "strategy.invalidation_quality.state": ("402", "قواعد الخروج"),
    # ٢٠٢٦-١٠-٠٧ (ختم «NQ»): خرجت الاستراتيجيّات السبع (404–410) — أُرشفت مع فكّ الأقسام عن القرار.
    "strategy.news.state": ("411", "استراتيجية الأخبار"),
    "strategy.session.state": ("412", "استراتيجية الجلسة"),
    # ٢٠٢٦-١٠-٠٧ (ختم «NQ»): بطاقة استمرار الاتّجاه (414) — حكمها (direction · status) يُختم رأيًا عند الميلاد.
    "strategy.card.state": ("414", "بطاقة استمرار الاتّجاه"),
    # ٢٠٢٦-١٠-٠٨ (ختم المالك «NQ» — «قبل كلّ شي لازم يعرف النظام»): ذرّات المعرفة — حقائقها تُختم على كلّ صفقة
    # فتُحسب عليها كأيّ عامل، ولا تدخل قرار الدخول إلّا بقياسها.
    "knowledge.time.state": ("117", "معرفة الوقت والعطل"),
    "knowledge.monetary.state": ("118", "السياسة النقديّة"),
    "knowledge.seasonal.state": ("119", "ذاكرة الناسداك الموسميّة"),
    "knowledge.news.state": ("120", "تصنيف الأخبار وأثرها"),
    # ٢٠٢٦-١٠-٠٨ (ختم المالك «NQ»): تسعير السوق لقرار الفائدة (عقود الفائدة الآجلة) · الشركات والخوف والدولار.
    "knowledge.fed_pricing.state": ("121", "تسعير قرار الفائدة"),
    "knowledge.companies.state": ("122", "الشركات والأسواق"),
}
