// تعريب رسائل صحّة الذرّات — حكم المالك ٢٠٢٦-٠٨-١٦: «ما بدّي أشوف ولا شي أجنبيّ».
//
// الذرّات تكتب رسائلها بالإنجليزيّة لأنّ دستور الذرّة يمنع العربيّة داخل الكود
// (القاعدة م٣). فالترجمة مكانها هنا — في اللوحة — لا في الذرّة.
//
// قاعدة العرض: ما نعرفه يُترجم، والرمز التقني المجهول يُستبدل بوصف عربي
// واضح بدل تسريب الإنجليزية. الأرقام تبقى أرقامًا؛ نترجم المعنى لا القيمة.

const REASONS: Record<string, string> = {
  // ٢٠٢٦-٠٩-٠٩ (ختم NQ): أربعة عشر رمزًا مقيسًا على رسائل الصحّة الحيّة (٢٢٨
  // ذرّة) لم يكن لها ترجمة، فكانت تظهر إنكليزيّة خامًا على «الرئيسيّة» و«غرفة
  // النظام» — خرق «لا إنكليزي باللوحة» (ورقة ٩٩). المعاني من مصدر كل رمز.
  UNTRUSTED: 'غير موثوق',
  NO_VOLUME_IN_CANDLES: 'لا حجم بالشموع',
  NO_VOLUME_YET: 'لا حجم بعد',
  DEGRADED: 'متعثّرة',
  UNAVAILABLE_NO_NEWS_SOURCE: 'غير متاح — لا مصدر أخبار',
  QUALITY_BLOCKED: 'محجوب لضعف الجودة',
  OK_EMITTING: 'سليمة وتبثّ',
  TRADE_FEED_STALE: 'تغذية الصفقات متقادمة',
  NO_CANDIDATES_YET: 'لا مرشّحين بعد',
  NO_DOWNSTREAM_CONSUMER: 'لا مستهلك بعدها',
  CLOCK_HEARTBEAT_STALE: 'نبض الساعة متقادم',
  SYNCED: 'مُزامَنة',
  SNAPSHOT_INCOMPLETE: 'اللقطة ناقصة',
  PENDING_OR_ORPHANED_RESOLUTION: 'حلّ رمز معلّق أو يتيم',
  NOT_STARTED: 'لم تُشغَّل',
  NO_INPUT_YET: 'لم يصلها مدخل بعد',
  NO_TRADES_YET: 'لا صفقات بعد',
  NO_DATA_YET: 'لا بيانات بعد',
  NO_SCORE_YET: 'لا درجة بعد',
  NO_PLAN_YET: 'لا خطّة بعد',
  NO_CANDLES_YET: 'لا شموع بعد',
  NO_LEDGER_YET: 'لا دفتر بعد',
  NO_TARGET_OR_PAIR_YET: 'لا هدف ولا زوج بعد',
  NO_REFERENCE_CAPITAL: 'لا رأس مال مرجعيّ',
  NO_READ_YET: 'لم تُقرأ بعد',
  DISABLED: 'موقوف',
  KILL_SWITCH_ACTIVE: 'قاطع الأمان مفتوح',
  MISSING_ACCOUNT_ID: 'رقم الحساب مفقود',
  NO_REQUESTED_PRICE: 'لا سعر مطلوب — القياس ممنوع',
  ACCOUNT_STATE_STALE: 'بيانات الحساب متقادمة',
  SPREAD_TOO_WIDE: 'الفرق السعريّ واسع',
  PREVIEW_ONLY: 'مقفول',
  LIVE: 'مفتوحة',
  STOPPED: 'متوقّفة',
  HALTED: 'موقوفة بالطوارئ',
  READY: 'جاهزة',
  ACTIVE: 'نشطة',
  UNAVAILABLE: 'غير متاح من الوسيط',
  BRIDGE_UNREADABLE: 'الجسر غير مقروء',
  RESTORE_FAILED_FAIL_CLOSED: 'فشل الاسترجاع — أُقفلت احتياطًا',
  RETRIES_EXHAUSTED: 'نفدت المحاولات',
  ledger_active: 'الدفتر نشط',
  stop_targets_ready: 'أهداف الوقف جاهزة',
  account_state: 'حالة الحساب',
  bridge_writable: 'الجسر قابل للكتابة',
  // رموز «جاهزة بلا عمل بعد» — حملة تنظيف مادة اللغة 2026-08-20:
  // الذرّات صارت تتكلم رموزًا إنكليزية (دستور الذرة م٣) والترجمة هنا.
  READY_AWAITING_FIRST_CLOSED_TRADE_OUTCOME: 'جاهزة — بانتظار أول نتيجة صفقة مغلقة',
  READY_AWAITING_FIRST_LEARNING_SAMPLE: 'جاهزة — بانتظار أول عيّنة تعلّم',
  READY_AWAITING_FIRST_SAMPLE_FOR_FEATURES: 'جاهزة — بانتظار أول عيّنة للميّزات',
  READY_AWAITING_ENOUGH_TRAINING_SAMPLES: 'جاهزة — بانتظار عيّنات كافية للتدريب',
  READY_AWAITING_FIRST_CANDIDATE_MODEL: 'جاهزة — بانتظار أول نموذج مرشّح',
  READY_AWAITING_FIRST_VALIDATED_MODEL: 'جاهزة — بانتظار أول نموذج متحقَّق',
  READY_AWAITING_FIRST_APPROVED_MODEL: 'جاهزة — بانتظار أول نموذج معتمَد',
  SUSPECTED_FAULT_MODEL_SELECTED_BUT_NOT_ACTIVE: 'شكّ عطل: نموذج مُختار بلا تفعيل',
  READY_AWAITING_FIRST_APPROVED_MODEL_TO_REGISTER: 'جاهزة — بانتظار أول نموذج معتمَد للتسجيل',
  READY_AWAITING_FIRST_OUTCOME_FOR_DRIFT: 'جاهزة — بانتظار أول نتيجة لقياس الانجراف',
  READY_AWAITING_FIRST_ORDER_OR_POSITION: 'جاهزة — بانتظار أول أمر أو مركز',
  READY_AWAITING_FIRST_ASSET_LEDGER: 'جاهزة — بانتظار أول دفتر أصول',
  READY_AWAITING_FIRST_FINANCIAL_CANDLE: 'جاهزة — بانتظار أول شمعة بهويّة مالية',
  READY_AWAITING_FIRST_TRADE_OUTCOME: 'جاهزة — بانتظار أول نتيجة صفقة',
  READY_LEDGER_EMPTY_AWAITING_FIRST_POSITION_OR_TRADE: 'جاهزة — الدفتر فاضٍ، بانتظار أول مركز أو صفقة',
  READY_AWAITING_FIRST_FINAL_DECISION_OR_ORDER: 'جاهزة — بانتظار أول قرار نهائي أو أمر',
  READY_AWAITING_FIRST_RISK_VALIDATION: 'جاهزة — بانتظار أول تحقّق مخاطر',
  READY_AWAITING_FIRST_LEGAL_ORDER: 'جاهزة — بانتظار أول أمر شرعي',
  READY_AWAITING_FIRST_MEASURED_TRADE: 'جاهزة — بانتظار أول صفقة تُقاس جودتها',
  READY_AWAITING_FIRST_PLATFORM_TRADE_EVENT: 'جاهزة — بانتظار أول حدث صفقة من المنصّة',
  READY_AWAITING_FIRST_MANAGE_INTENT: 'جاهزة — بانتظار أول نيّة إدارة',
  READY_AWAITING_FIRST_TARGET_OR_PAIR: 'جاهزة — بانتظار أول هدف أو زوج',
  READY_AWAITING_FIRST_TARGET: 'جاهزة — بانتظار أول هدف',
  READY_AWAITING_FIRST_ORDER_STOP_CHECK: 'جاهزة — بانتظار أول فحص وقف لأمر',
  READY_AWAITING_FIRST_ORDER_MARGIN_CHECK: 'جاهزة — بانتظار أول فحص هامش لأمر',
  READY_AWAITING_FIRST_ORDER_SYMBOL_RESOLVE: 'جاهزة — بانتظار أول ترجمة رمز لأمر',
  READY_AWAITING_FIRST_MT5_TRADE_EVENT: 'جاهزة — بانتظار أول حدث صفقة من الوسيط',
  READY_AWAITING_FIRST_CTRADER_REFERENCE_TICK: 'جاهزة — بانتظار أول تكّة مرجعية من سي-تريدر',
  READY_AWAITING_FIRST_OPEN_POSITION: 'جاهزة — بانتظار أول مركز مفتوح',
  READY_AWAITING_FIRST_TRADE_STORE: 'جاهزة — بانتظار أول تخزين صفقة',
  READY_AWAITING_FIRST_ORDER_STORE: 'جاهزة — بانتظار أول تخزين أمر',
  READY_AWAITING_FIRST_MODEL_SAVE: 'جاهزة — بانتظار أول حفظ نموذج',
  READY_AWAITING_FIRST_ROTATED_ARCHIVE_714: 'جاهزة — بانتظار أول أرشيف مدوَّر من 714',
  READY_AWAITING_FIRST_ARCHIVE_EVENT: 'جاهزة — بانتظار أول حدث أرشفة',
  READY_AWAITING_FIRST_CLEANUP_EVENT: 'جاهزة — بانتظار أول حدث تنظيف',
  READY_ATTACHED_AWAITING_FIRST_ERROR: 'جاهزة ومتّصلة — بانتظار أول خطأ',
  READY_AWAITING_FIRST_REAL_TRADE_OR_ORDER_EVENT: 'جاهزة — بانتظار أول حدث صفقة أو أمر حقيقي',
  READY_AWAITING_FIRST_BACKUP_RUN: 'جاهزة — بانتظار أول جولة نسخ',
  READY_AWAITING_FIRST_DASHBOARD_COMMAND: 'جاهزة — بانتظار أول أمر من اللوحة',
  AWAITING_FIRST_PULSE: 'بانتظار أول نبضة',
  SUSPECTED_FAULT: 'شكّ عطل',
  ERROR_LOG_DAILY_CAP_REACHED: 'بلغ سقف سجل الأخطاء اليومي',
  TRADE_LOG_DAILY_CAP_REACHED: 'بلغ سقف سجل الصفقات اليومي',
  // بند أ١١ — حالات بطاقات المسارين/القسم (166) وتحذيراتها المقيسة من الكود:
  ANALYZING: 'قيد التحليل',
  NOT_READY: 'غير جاهز',
  STALE: 'متقادم',
  missing_path: 'مسار غائب',
  missing_weight: 'وزن غائب',
  no_valid_analysis: 'لا تحليل صالحًا',
  // ٢٠٢٦-٠٩-١٠ (سؤال المالك عن «حاكم التغيير»): رسائل صحّة ذرّات التكيّف
  // (840/850/860/870) لم تكن مترجمة، وأهمّها كانت تخفي حقيقة: المفتاح مرفوع.
  // المعاني من مصدر كل رمز في `atom.py` الخاص به — لا تخمين.
  ADAPTATION_OFF: 'التعديل الذاتي موقوف',
  ARMED: 'مسلَّح — التعديل الذاتي مسموح',
  HOT_PATH_LATENCY_REGRESSION: 'تراجع زمن المسار الحار',
  CRITICAL_DRIFT: 'انحراف حادّ',
  DRIFT_THRESHOLD_EXCEEDED: 'تجاوز عتبة الانحراف',
  OWNER_COMMAND: 'أمر المالك',
  OWNER_COMMAND_ONLY: 'بأمر المالك وحده',
  BASELINE_WARMING: 'خطّ الأساس يتكوّن',
  CONTINUES: 'مستمرّ',
  WATCH: 'مراقبة',
  SHADOW: 'ظلّ',
  APPROVED_FOR_SHADOW: 'موافَق للتشغيل بالظلّ',
  KILL_SWITCH_COMMAND_INVALID: 'أمر مفتاح الإيقاف غير صالح',
  // ٢٠٢٦-٠٩-١٦ — قيمٌ تظهر في رسائل الصحّة الحيّة وكانت تُطبع «قيمة تقنية».
  // معانيها من مصدرها: أسباب عدم الأهليّة (455-458) وأسباب الحجب (454 · 552).
  DIRECTION_ABOVE_THRESHOLD: 'الاتجاه فوق العتبة',
  DIRECTION_BELOW_THRESHOLD: 'الاتجاه تحت العتبة',
  DIRECTION_INSUFFICIENT: 'الاتجاه غير كافٍ',
  // ٢٠٢٦-٠٩-١٦ — أمسكها الحارس بعد أوّل جرد: كلمات ظهرت لاحقًا حين وقعت
  // أحداثها الشرطيّة. تُرجمت ولم تُضَف إلى الدَّين — الدَّين لما يتعذّر لا
  // لما يسهل.
  STRENGTH_BELOW_THRESHOLD: 'القوّة أقلّ من العتبة',
  REFERENCE_NOT_USABLE: 'السعر المرجعيّ غير صالح للاستعمال',
  NO_COMPARISON_YET: 'لا مقارنة بعد',
  // ٢٠٢٦-٠٩-١٨ — أسباب رفع قاطع الأمان (٥١٦). كانت تُعرَض **خامًا** في ثلاث
  // شاشات: «السبب: RISK_DAILY_LIMIT». وهو أهمّ سطر على الشاشة وقتها — جواب
  // «ليش التداول موقوف» — ومكتوبٌ بلغةٍ لا يقرؤها المالك.
  RISK_DAILY_LIMIT: 'بلغت حدّ الخسارة اليوميّة',
  RISK_SESSION_LIMIT: 'بلغت حدّ خسارة الجلسة',
  RISK_CONSECUTIVE_LOSSES: 'خسائر متتالية فوق المسموح',
  RISK_EQUITY_DRAWDOWN: 'هبوط قيمة الحساب فوق المسموح',
  RISK_PROFIT_GIVEBACK: 'تراجُع الربح فوق المسموح',
  RISK_MAX_TRADES: 'بلغت أقصى عدد صفقات',
  OWNER_HALT: 'إيقاف بأمرك',
  NO_TICKS_YET: 'لا تِكّات بعد',
  NO_STOP_PRICE: 'لا سعر وقف',
  // ٢٠٢٦-٠٩-١٨ — أسبابُ رفض مدقّق الأمر ٥٥٢، وهو **آخر بوّابة قبل الوسيط**:
  // ما يرفضه هنا لا يصل المنصّة أبدًا. كانت سبعة عشر سببًا منها بلا تعريب في
  // القاموس المشترك، فيظهر الرمز الخام لمن لا يقرأ الإنكليزيّة. مقروءة من
  // `atoms/قسم 550-599/552_مدقق_الأمر/atom.py` و`order_validation.py`.
  // ٢٠٢٦-٠٩-١٩ — أسبابُ حجب طالب أمر الدخول ٥٥٥، وهي **أوّل حاجزٍ** بعد
  // اعتماد القرار: ما يُحجب هنا لا يصير أمرًا أصلًا. ظهر منها
  // `NO_TARGET_FOR_SIDE` على الحكم الكبير فخرج نصفَ معرَّب («بلا هدف ربح ·
  // تفصيل تقني») لأنّ القاموس كان يحمل `NO_TARGET` وحدها — والمفتاح يُكتب
  // **كما ينشره ناشره** لا مقطوعًا. مقروءة من `555/atom.py:74-90`.
  // ٢٠٢٦-٠٩-٢٢ — أسبابُ إيقاف الحساب التي تصل بوّابة الأوامر في
  // `halted_accounts` (`552/atom.py:164` يأخذها من حمولة الحارس). ثلاثةٌ منها
  // ينشرها حارس حدود الجلسة (`506/atom.py:42-44`) وواحدٌ هو البديل عند غياب
  // السبب. وبلا تعريبها يقرأ المالك رمزًا خامًّا في أهمّ سطرٍ على الشاشة.
  // ٢٠٢٦-٠٩-٢٣ — اختصاراتُ حقولٍ ظاهرةٌ الآن على البطاقات، رفعها حارس
  // `check_health_arabic.py` مرتَّبةً بالورود. قصيرةٌ فتبدو هيّنة، وهي
  // مقروءةٌ على شاشة المالك بالإنكليزيّة.
  age: 'العمر', pub: 'نُشر', via: 'عبر', ack: 'تأكيد', avail: 'المتاح',
  at_r: 'عند المضاعف', elig: 'مستاهل', org: 'المصدر', net: 'الصافي',
  band: 'النطاق', fills: 'تنفيذات', queued: 'بالطابور', breakevens: 'تعادلات',
  tracked: 'متتبَّعة', conflicts: 'تعارضات', scopes: 'نطاقات',
  unmeasurable: 'غير قابل للقياس', max_drift_ever: 'أقصى انحراف مسجَّل',
  // اسمُ الوسيط الرسميّ — **اسمُ علَمٍ لا لغةٌ أجنبيّة**، كرمز الأداة. يُعرض
  // كما هو لأنّه ما يراه المالك على منصّته، وتعريبُه يخلق اسمًا لا وجود له.
  Raw: 'Raw', Trading: 'Trading', Ltd: 'Ltd',
  SESSION_LOSS_LIMIT: 'بلغت حدّ خسارة الجلسة',
  MAX_SESSION_TRADES: 'بلغت أقصى عدد صفقات الجلسة',
  EQUITY_DRAWDOWN_LIMIT: 'بلغت حدّ تراجع قيمة الحساب',
  RISK_HALT: 'إيقاف من حارس المخاطر',
  NO_TARGET_FOR_SIDE: 'ما في هدف ربح للجهة المطلوبة',
  NO_STOP_FOR_SIDE: 'ما في وقف خسارة للجهة المطلوبة',
  TARGET_BELOW_MIN_REWARD: 'الهدف أقرب من الحدّ المطلوب مقابل الوقف',
  DECISION_SIDE_UNKNOWN: 'جهة القرار غير معروفة',
  NO_SIZE_FOR_SCOPE: 'ما وصل تحجيم للّوت',
  SIZE_STALE: 'التحجيم متقادم',
  NO_EXECUTABLE_VOLUME: 'ما في حجم قابل للتنفيذ',
  POSITION_ALREADY_OPEN: 'في مركز مفتوح على الرمز',
  // ٢٠٢٦-١٠-٢٦ (جواب المالك «NQ»: «ما يفتح شي على اي زوج عليه صفقة مني»)
  OWNER_POSITION_OPEN: 'صفقتك اليدويّة مفتوحة على هذا الزوج — المنظومة لا تفتح عليه بأيّ جهة',
  POSITIONS_UNKNOWN: 'صورة المراكز غير معروفة',
  NO_ACCOUNT_OR_BROKER: 'بلا حساب أو وسيط',
  EMERGENCY_HALT: 'إيقاف طارئ',
  REWARD_BELOW_MULTIPLE: 'الهدف أقرب من المطلوب مقابل الوقف',
  RISK_OFF_BUDGET: 'المال المعرَّض خارج ميزانيّة الرمز',
  // ٢٠٢٦-١٠-٠٥ (ختم المالك «NQ وأبنيها»): أسباب ردٍّ أضافها إصلاح ٢٠٢٦-١٠-٠٢ في مدقّق الأمر
  // وطالبه بلا تعريب — فكان أهمّ سطر على «شو صاير» يقول «آخر سبب: ASSET_FROZEN».
  // المعاني من كود ناشرها: `552/order_gates.py:112-137,190-225` · `552/atom.py:435-470`
  // · `555/entry_request_sizing.py:55-75`.
  ASSET_FROZEN: 'الأصل مجمّد — ميزانيّته نفدت أو أوقفته إنت',
  ASSET_BUDGET_EXHAUSTED: 'ميزانيّة الأصل نفدت',
  ASSET_STATE_UNKNOWN: 'حالة الأصل ما وصلت',
  RR_BELOW_MIN_AT_SEND: 'الهدف أقرب من ثلاثة أضعاف الوقف عند الإرسال',
  STOP_BELOW_10BPS_AT_SEND: 'الوقف أقرب من حدّ البِب لهذا الأصل عند الإرسال',
  NO_TRADE_DAY: 'يوم عطلةٍ لا تداول فيه (قانون الأيّام)',
  OUTSIDE_TRADING_WINDOW: 'خارج نافذة بورصة الأصل (أو النافذة العامّة: من افتتاح سيدني إلى 16:00 نيويورك)',
  NEWS_RED_LINE: 'نافذة خبرٍ أحمر لعملةٍ في الأصل (والدولار لكلّ الرموز) — 15 دقيقة قبله وبعده',
  FIRST_15_MIN_OF_SESSION: 'أوّل ربع ساعة من افتتاح جلسة الأصل — لا دخول',
  // ٢٥/١٠ (ختم المالك «nq»، القانون 21): الساعة الأخيرة بدل «الوقت يكفي».
  LAST_HOUR_OF_SESSION: 'الساعة الأخيرة من نافذة الأصل — لا صفقة جديدة، والمفتوح يكمل حتّى الإغلاق',
  NOT_ENOUGH_TIME_BEFORE_RED_LINE: 'الهدف أبعد من الحركة المتوقّعة قبل أقرب خطٍّ أحمر (قانون ما قبل ٢٥/١٠)',
  WAIT_AFTER_TRADE_15M: 'ربع ساعة انتظار بعد انتهاء صفقةٍ على هذا الأصل (قانون ما قبل ٢٣/١٠)',
  WAIT_AFTER_LOSS_OTHER_ACCOUNT_1H: 'ساعة انتظار: صفقةٌ خاسرة على هذا الرمز أُغلقت في حسابٍ آخر (قانون ما قبل ٢٣/١٠)',
  // ٢٣/١٠ (ورقة «خطوط حمراء» المختومة): ساعة وربع بدل ربع ساعة وساعة، ومنع التحوّط، وحدود الحساب.
  WAIT_AFTER_TRADE_75M: 'ساعة وربع انتظار بعد انتهاء صفقةٍ على هذا الأصل',
  WAIT_AFTER_LOSS_OTHER_ACCOUNT_75M: 'ساعة وربع انتظار: صفقةٌ خاسرة على هذا الرمز أُغلقت في حسابٍ آخر',
  HEDGE_WITH_OTHER_ACCOUNT: 'تحوّط ممنوع: الجهة المعاكسة مفتوحة على هذا الرمز في حسابٍ آخر',
  TOTAL_DRAWDOWN_LIMIT: 'التراجع الكلّيّ بلغ حدّه — التداول واقف حتّى تعيده أنت من «التحكّم»',
  DAILY_LOSS_LIMIT: 'الحدّ اليوميّ الشامل بلغ حدّه — لا دخول حتّى 00:00 بساعتك',
  PAIR_DAILY_LIMIT: 'حدّ هذا الزوج اليوميّ بلغ حدّه — لا دخول عليه حتّى 00:00 بساعتك',
  ACCOUNT_LIMITS_UNKNOWN: 'أرقام الحساب أو حدوده غير معروفة الآن — لا دخول بلا معرفة',
  // ٢٦/١٠ (فحص المشروع، ختم المالك «nq اصلح»): أسباب ردٍّ جديدة في طالب الدخول 555 — الجهل يمنع ولا يمرّر.
  // المعاني من ورقة عامل الإصلاح الأوّل («ورقة خطوات الإصلاح — ملحق تقنيّ»، الخطوة الرابعة).
  NEWS_CALENDAR_UNKNOWN: 'التقويم لا يعرف الأخبار الآن (حالته قديمة أو غائبة أو انقضى أفقه) — لا دخول',
  CLOCK_PULSE_STALE: 'نبضة الساعة متوقّفة — لا دخول',
  RED_LINES_GATE_MISSING: 'وحدة قوانين الوقت والأخبار لم تُحمَّل — لا دخول حتّى الإقلاع',
  // وصحّة الخطوط الحمراء 565 وحدود الحساب 509 (نصّاهما الكاملان في `PHRASES` تحت؛ وهذان احتياطٌ لما لا يطابق).
  PULSE_STALE: 'نبضة الساعة صامتة — يُحكم بالساعة الاحتياطيّة',
  TRUTH_UNKNOWN: 'أرقام الحساب غير معروفة الآن — لا دخول',
  TRUTH_STALE: 'أرقام الحساب قديمة — لا دخول',
  TRUTH_MISSING: 'أرقام الحساب لم تصل من ميتاتريدر — لا دخول',
  LOSING_POSITION_OPEN_OTHER_ACCOUNT: 'على هذا الرمز مركزٌ خاسرٌ مفتوح في حسابٍ آخر',
  EXPOSURE_CAP_BELOW_MIN_LOT: 'بعد قصّه لسقف التعرّض صار أصغر من أقلّ لوت',
  EXPOSURE_PROJECTION_UNKNOWN: 'التعرّض بعد الأمر ما انحسب — بيانات ناقصة',
  EXPOSURE_STATE_STALE: 'حالة التعرّض قديمة',
  RECONCILIATION_STALE: 'مطابقة المراكز قديمة',
  REFERENCE_STALE: 'سعر المرجع قديم',
  // ٢٠٢٦-١٠-٠٥ (ختم المالك «ترجم nq»): الكلمات التي رفعها حارس عربيّة رسائل الصحّة —
  // كلٌّ من كود ذرّتها: ٥٢٤ و٥٧٩ (`_pending` فيه طلبٌ `FAILED`) · ٧٠٧ (خطأ قفل SQLite
  // يبقى نصّه في الرسالة حتّى إعادة التحميل وإن عادت الكتابة) · ٥٨٠ · ٤٥٦.
  EXTRACTION_FAILED_PENDING: 'تخريج ربح فشل وما زال معلّقًا',
  // ٧٠٧ `4.21.0`: الصفّ المصطدم بالقفل يعود إلى الطابور، والنصّ يزول بأوّل كتابةٍ تنجح.
  'database is locked': 'قاعدة البيانات مقفولة بيد كاتب آخر — الصفوف بالانتظار وتُكتب حين تنفكّ',
  // ٨٠٢ `2.3.0`: المصدر الغائب يُتخطّى ويُعلَن، والموجود يُؤرشَف.
  SOURCES_MISSING: 'مصادر غير موجودة',
  NO_GATE_DECISION_YET: 'ما وصل حكم البوّابة بعد',
  // ٧ (`atom.py:101-117`): مرجعُ سلامة الملفّات بصيغةٍ أخرى أو لنطاقٍ غير المراقَب الآن،
  // أو فارغ — فالحارس لا يقارن بشيء حتّى يُعاد توليد المرجع.
  BASELINE_SCOPE_MISMATCH: 'مرجع سلامة الملفّات لا يطابق النطاق المراقَب — يحتاج إعادة توليد',
  BASELINE_EMPTY: 'مرجع سلامة الملفّات فارغ',
  STATE_NOT_READY: 'الحالة ما نضجت بعد',
  None: 'بلا قيمة',
  // أكثرُ ثلاثة أسبابٍ للرفض ورودًا على شارة مدير التنفيذ (٥٥٠) الآن —
  // ٧١٥ و٢٣ و٧ — ولم تصل الشاشة قطّ لأنّ الزوجَ كان يُسقَط باسمه وعدده.
  STOP_BELOW_FLOOR: 'الوقف أقرب من الأرضيّة المسموحة',
  SYMBOL_RESOLUTION_TIMEOUT: 'انتهت مهلة حلّ الرمز عند الوسيط',
  UPSTREAM_REJECTED: 'مرفوض من فوق — ما اعتُمد القرار',
  SYMBOL_NOT_ALLOWED: 'الرمز مش مفعَّل',
  CLOCK_NOT_SYNCED: 'ساعة الوسيط مش مضبوطة',
  RECONCILIATION_NOT_MATCHED: 'صورة المراكز ما طابقت الوسيط',
  EXPOSURE_STATE_NOT_USABLE: 'حالة التعرّض غير صالحة للقراءة',
  NO_BUDGET: 'بلا ميزانيّة للرمز',
  PERPETUAL_NO_TP: 'بلا هدف ربح',
  NO_STOP: 'بلا وقف خسارة',
  NO_TARGET: 'بلا هدف ربح',
  BUY_LEVELS: 'مستويات الشراء مقلوبة (الوقف فوق السعر أو الهدف تحته)',
  SELL_LEVELS: 'مستويات البيع مقلوبة (الوقف تحت السعر أو الهدف فوقه)',
  BAD_PRICE: 'سعر غير صالح',
  BAD_ACTION: 'نوع أمر غير معروف',
  NO_SYMBOL: 'بلا رمز',
  BAD_SIDE: 'اتجاه غير صالح',
  BAD_VOLUME: 'حجم غير صالح',
  REQUEST_IN_FLIGHT: 'طلبٌ قيد الإرسال',
  CATCHUP_REQUIRED: 'يحتاج لحاقًا',
  SNAPSHOT_READY: 'اللقطة جاهزة',
  RANGING: 'سوق عرضيّ',
  SYSTEM: 'النظام',
  signal_wait: 'الإشارة انتظار',
  calendar_window: 'داخل نافذة حدث اقتصادي',
  eligibility: 'الأهليّة',
  neutral: 'محايد',
  shadow: 'ظلّ',
  wait: 'انتظار',
  london: 'لندن',
  eligible: 'مؤهَّل',
  not_eligible: 'غير مؤهَّل',
  False: 'لا',
  True: 'نعم',
  // ٢٠٢٦-١٠-٠٨ (فكّ الأقسام عن القرار، ختم المالك «NQ»): حالات بطاقة استمرار الاتّجاه (414) كما ينشرها
  // `strategy.card.state` وكما تُعدّ في رسالة صحّتها (`OUTSIDE_OWNER_WINDOW=15`). المعاني من مصدرها:
  // `shared/card_trend.py:39-50` و`atoms/قسم 400-449/414_بطاقة_استمرار_الاتجاه/atom.py:56-58,243-277`.
  // تُكتب هنا حرفًا حرفًا لا بنشر قاموسٍ آخر: حارس `check_health_arabic.py` يقرأ مفاتيح هذا القاموس نصًّا.
  OPEN: 'بطاقة مفتوحة',
  OUTSIDE_OWNER_WINDOW: 'خارج نافذة المالك',
  NEWS_BLACKOUT: 'نافذة منع الخبر',
  FRAMES_DISAGREE: 'الإطاران مختلفان',
  CORRELATION_DISAGREES: 'الأسواق المرتبطة تخالف',
  FACT_MISSING: 'حقيقة ناقصة',
  NO_PULLBACK_STRUCTURE: 'لا بنية ارتداد',
  NO_TRIGGER: 'لا زناد',
  NO_TARGET_WITHIN_REACH: 'لا هدف في المتناول',
  NON_POSITIVE_RISK: 'مخاطرة غير موجبة',
  CANDLE_LATE: 'الشمعة وصلت متأخّرة',
  CANDLE_OLD: 'شمعة قديمة مكرّرة',
  POSITION_OPEN: 'مركز مفتوح على الرمز',
  ACCOUNT_UNKNOWN: 'الحساب غير معروف',
  // ٢٠٢٦-١٠-٠٨ (فكّ الأقسام عن القرار، ختم المالك «NQ»): كلمتان ظهرتا في رسالتَي 830 و820 بعد الفكّ — من كودهما:
  // `830/atom.py:52` (لم يصل مدخلٌ يُحسب منه النظام السوقيّ) · `820/atom.py:106-113,187` (عدد نطاقات حساب·وسيط·رمز التي وصلت تِكّتها).
  NO_REGIME_INPUT_YET: 'لم يصل مدخل النظام السوقيّ بعد',
  tick_scopes: 'نطاقات التِكّات',
}

const FIELDS: Record<string, string> = {
  sent: 'أُرسل', rejected: 'مرفوض', seen: 'وصلها', built: 'بُني',
  // ٢٠٢٦-٠٩-١٦ — قِيست رسائل صحّة الـ228 ذرّة الحيّة: **١٨٢ اسم حقل بلا
  // ترجمة**، وكلّها كانت تُعرض للمالك «حقل تقني=قيمة تقنية». وحارس العربيّة
  // كان أخضر لأنّه يفحص أسماء العيارات في `Settings.tsx` وحدها — لا رسائل
  // الصحّة التي تملأ «التنفيذ» و«التحليل». حارسٌ يفحص السطح الخطأ.
  // هذه أكثرها ورودًا، مأخوذة من سياق ذرّاتها لا من التخمين:
  ticks: 'تِكّات', candles: 'شموع', last: 'الأخير', inputs: 'مدخلات',
  forwarded: 'مُرِّرت', buffered: 'بالمخزن المؤقّت', late: 'متأخّرة',
  panel: 'اللوحة', units: 'وحدات', invalid: 'غير صالحة', duplicates: 'مكرّرة',
  eligible: 'مؤهَّل', not_eligible: 'غير مؤهَّل', recorded: 'مسجَّل',
  scopes: 'نطاقات', swings: 'تأرجحات', validated: 'مُتحقَّق منها',
  breaks: 'كسور', checked: 'مفحوصة', dup: 'مكرّر', enriched: 'مُثراة',
  events: 'أحداث', evicted: 'أُخرجت', excluded: 'مستبعَدة',
  log_suppressed: 'سطور سجلّ مكتومة', malformed: 'مشوَّهة',
  new_invalid: 'غير صالح جديد', news: 'أخبار', runs: 'جولات',
  samples: 'عيّنات', saved: 'محفوظة', superseded: 'استُبدلت',
  timed_out: 'انتهت مهلتها', today: 'اليوم', total: 'الإجمالي',
  admitted: 'قُبلت', aggregates: 'تجميعات', alerts: 'إنذارات',
  batch: 'دفعة', batches: 'دفعات', book: 'الدفتر', books: 'دفاتر',
  candidates: 'مرشّحون', cap: 'السقف', cause: 'السبب', closed: 'مغلقة',
  coalesced: 'مدموجة', compared: 'قُورنت', comparisons: 'مقارنات',
  compressed: 'مضغوطة', crossed: 'متقاطعة', crossed_book: 'دفتر مقلوب',
  crossed_spread: 'سبريد مقلوب', cut: 'قُصّت', deepest: 'الأعمق',
  directional: 'اتجاهيّة', divergence: 'تباعد', duplicate: 'مكرّر',
  evaluated: 'قُيّمت', evidence: 'أدلّة', extremes: 'أطراف',
  features: 'سمات', fills: 'تنفيذات', floor: 'الأرضيّة', flushed: 'أُفرغت',
  frames: 'أُطُر', gap: 'فجوة', held: 'محجوزة', inactive: 'خاملة',
  live: 'حيّ', loaded: 'محمَّلة', merged: 'مدموجة', missing: 'ناقص',
  net: 'الصافي', orphans: 'يتيمة', outliers: 'شواذّ', pools: 'برك',
  processed: 'معالَجة', pruned: 'مقلَّمة', queued: 'بالطابور',
  quality: 'الجودة', ready: 'جاهز', received: 'وصلت', records: 'سجلّات',
  refused: 'رُفضت', removed: 'أُزيلت', restored: 'استُعيدت', rows: 'صفوف',
  rules: 'قواعد', selected: 'مختارة', session: 'الجلسة', sized: 'مُحجَّمة',
  spread: 'السبريد', stopped: 'متوقّفة', sweeps: 'اكتساحات',
  synced: 'مُزامَنة', trimmed: 'مقصوصة', unmatched: 'بلا مطابق',
  unusable: 'غير قابلة للاستعمال', valid: 'صالحة', verdicts: 'أحكام',
  waits: 'انتظارات', warming: 'قيد الإحماء', regime: 'النظام السوقيّ',
  room: 'الروم', tilt: 'الترجيح', prob: 'الاحتمال', idle_s: 'ثواني الخمول',
  not_found: 'غير موجود', not_watched: 'غير مراقَب', no_time: 'بلا وقت',
  no_stamp: 'بلا طابع', clock_invalid: 'ساعة غير صالحة',
  fail: 'فشل', op: 'العمليّة', ref: 'المرجع', from_order: 'من الأمر',
  added: 'أُضيف', modified: 'عُدِّل', more: 'أخرى', read: 'قُرئ',
  fallback: 'بديل احتياطيّ', backups: 'نسخ احتياطيّة', clock: 'الساعة',
  deleted: 'محذوف', sources: 'مصادر', waiting: 'ينتظر',
  invalid_or_missing_price: 'سعر ناقص أو غير صالح',
  mode: 'الوضع', applied: 'مُطبَّق', sections: 'الأقسام',
  proposals: 'اقتراحات', experiments: 'تجارب', trips: 'مرّات الرفع',
  suppressed: 'مكتوم',
  legal: 'قانونيّ', approved: 'موافَق', released: 'أُفرج', validations: 'فحوص',
  rejections: 'رفوض', resolved: 'مُترجَم', blocked: 'محجوب', allowed: 'مسموح',
  written: 'كُتب', skipped: 'تُخطّي', failed: 'فشل', dropped: 'أُسقط',
  emitted: 'صدر', scored: 'حُسب', cycles: 'دورات', symbols: 'رموز',
  evidence_sources: 'مصادر الأدلّة', complete: 'مكتملة', deadline: 'بالمهلة',
  stale: 'متأخّر', targets: 'أهداف', snapshots: 'لقطات', published: 'نُشر',
  active: 'نشط', pending: 'معلّق', opened: 'فُتح', dials: 'أقراص',
  emits: 'إصدارات', plans: 'خطط', tilts: 'ترجيحات', trails: 'تتبّعات',
  breakevens: 'تعادلات', partials: 'إغلاقات جزئيّة', tracked: 'مُتابَع',
  pairs: 'أزواج', delta_sent: 'فروق أُرسلت', delta_failed: 'فروق فشلت',
  confirmed: 'مؤكَّد', realized: 'محقَّق', outcomes: 'نتائج',
  passed: 'مرّ', finalized: 'قرارات نهائية', bridge: 'الجسر', writable: 'قابل للكتابة',
  reported: 'مُبلَّغ', components: 'مكوّنات', accounts: 'حسابات',
  open: 'مفتوح', floating: 'عائم', slip: 'انزلاق', buy: 'شراء',
  sell: 'بيع', neutral: 'محايد', wait: 'انتظار', conflicts: 'تعارضات',
  updates: 'تحديثات', modify_sent: 'تعديلات أُرسلت', specs: 'مواصفات',
  balance_updates: 'تحديثات الرصيد', equity_updates: 'تحديثات الملكيّة',
  pnl_updates: 'تحديثات الربح', margin_updates: 'تحديثات الهامش',
  overview_parts: 'أجزاء النظرة', stored: 'مخزَّن', unmeasured: 'غير مقيس',
  computable: 'قابل للحساب', stops: 'وقوف', halt: 'إيقاف', reset: 'تصفير',
  activate: 'تفعيل', expired: 'منتهٍ', heartbeat: 'نبضة', minute: 'دقيقة',
  max_drift: 'أقصى انحراف', sys_tick: 'نبضة النظام',
  // بند أ١١ — العقد الثماني لبطاقات المسارين/القسم (166) وأسماء المسارات:
  direction: 'الاتجاه', strength: 'القوّة', confidence: 'الثقة',
  current_depth: 'العمق الحالي', required_depth: 'العمق المطلوب',
  weight: 'الوزن', ratio: 'النسبة', state: 'الحالة',
  fast: 'المسار السريع', slow: 'المسار البطيء', section: 'القسم',
  fused: 'مدموج',
  // حزمة ج (ختم 22) — الهوية الست وحقول سلسلة القرار (451..467) المشتركة عبر
  // أكثر من صفحة: بطاقة القرار · جدول الحواجز · بطاقات الأهلية · رحلة القرار.
  account_id: 'الحساب', broker: 'الوسيط', symbol: 'الرمز',
  timeframe: 'الإطار الزمني', period_start: 'بداية الدورة',
  decision_id: 'معرّف القرار', gate_request_id: 'معرّف طلب البوابة',
  request_id: 'معرّف الطلب', cycle_id: 'معرّف الدورة',
  reason: 'السبب', value: 'القيمة', threshold: 'العتبة',
  measured_at: 'وقت القياس', name: 'الاسم', checks: 'الفحوص',
  origin: 'المصدر', resolution: 'الحسم', stage: 'المرحلة',
  gated_at: 'وقت البوابة', side: 'الجانب', decision_side: 'الجانب',
  direction_buy: 'اتجاه الشراء', direction_sell: 'اتجاه البيع',
  target: 'الهدف', position: 'المركز', budget: 'الميزانية', action: 'الإجراء',
  // ٢٠٢٦-٠٩-٢٣ (ختم nq) — إحدى عشرة كلمة دخلت رسائل الصحّة بلا ترجمة؛ كلٌّ من
  // سياق ذرّتها: ٥٠٦ `breached` (حدّ الجلسة) · ٣٦٠ `bridged` (نتائج رُبطت
  // بالتذكرة) و`rmax` (تذاكر عُرف أقصى R لها) · ٤٥٤ اسما حاجزين · ٥٨٠ `ensure`
  // (زمن تهيئة المخزن عند الإقلاع) · ٥٥٥ `freed` (`_inflight_cleared`) ·
  // ٤٦٥ `n` (عدد عيّنات الهامش) · ٥٧٤ `partial_fraction` · ٥٦٠ `quality_scopes`
  // · ٤٥٦ `stale_ok` (قرارٌ متأخّر قُبل).
  breached: 'مُخترَق', bridged: 'رُبطت بالتذكرة', rmax: 'تذاكر بأقصى R',
  confidence_filter: 'حاجز الثقة', market_quality_invalid: 'جودة السوق غير صالحة',
  ensure: 'تهيئة المخزن', freed: 'حجوزٌ أُفرجت', n: 'العدد',
  partial_fraction: 'نسبة الإغلاق الجزئيّ', quality_scopes: 'نطاقات الجودة',
  stale_ok: 'متأخّر مقبول',
  // ٢٠٢٦-١٠-٠٥ (ختم المالك «ترجم nq»): دَين `KNOWN_UNTRANSLATED` وثماني كلماتٍ جديدة —
  // كلٌّ من كود ذرّتها لا من التخمين. والحرفان `p` و`s` معناهما في ٤٥٣ (المشاركة
  // والاتفاق)؛ و`p` في ٦٢٢ شيءٌ آخر (بايتات رسالةٍ ناقصة) فيُترجَم هناك بنمطه في `PHRASES`.
  // البنية والسيولة (٢٠٤–٢٥٥):
  bos: 'كسر البنية', choch: 'تغيّر الطابع', mss: 'تحوّل البنية', shifts: 'تحوّلات',
  fvgs: 'فجوات القيمة العادلة', buyside: 'سيولة الشراء', sellside: 'سيولة البيع',
  dropped_buy: 'شراء مُسقَط', dropped_sell: 'بيع مُسقَط',
  // القرار (٤١٣–٤٦٨):
  band_held: 'أمسكها نطاق الحياد', lowpart_waits: 'انتظار لقلّة المشاركة',
  s: 'الاتفاق', p: 'المشاركة', top_missing: 'العائلة الأكثر غيابًا',
  swept_restored: 'مستعادة كُنست', confidence_cycles: 'دورات الثقة',
  feed_stale: 'التغذية قديمة', asset_filter: 'حاجز الأصل', freshness_filter: 'حاجز الطزاجة',
  // البيانات والتغذية (١٠١–١٥٠ · ٦٠٨–٦٢٤):
  unified_published: 'موحَّد نُشر', ooo: 'خارج الترتيب', empty_side: 'جهة فارغة',
  invalid_or_missing_ask: 'سعر الطلب ناقص أو غير صالح',
  invalid_or_missing_bid: 'سعر العرض ناقص أو غير صالح',
  live_forwarded: 'دفعات حيّة مُرِّرت', echoes: 'أصداء مكرّرة',
  new_duplicate: 'مكرّر جديد', new_late: 'متأخّر جديد', unreadable_conf: 'ثقة غير مقروءة',
  ctrader: 'سي‑تريدر', up: 'تحديثات', c: 'اتصالات', u: 'رسائل مجهولة',
  q: 'بايتات بالانتظار', rs: 'إعادات اشتراك', pump: 'فاصل الضخّ',
  rcv: 'مُستلَم', forwarding: 'يمرّر', routes: 'مسارات', streaming: 'يبثّ',
  median_offset: 'وسيط فرق الساعة', sync_age: 'عمر المزامنة',
  calendar: 'التقويم', calendar_ff: 'التقويم الخارجيّ', source: 'المصدر',
  // المخاطر والتنفيذ والإدارة (٥٠٦–٥٨٠):
  new_york: 'نيويورك', exposure_known: 'التعرّض معروف', reconciliation_live: 'المطابقة حيّة',
  portfolios: 'المحافظ', dropped_trade: 'صفقات لم تُحتسب', dup_suppressed: 'تكرار مكبوح',
  id_floor: 'أرضيّة المعرّف', commands_emitted: 'أوامر صدرت',
  positions: 'مراكز', trades: 'صفقات', narrow: 'ضيّق',
  // الحساب والأداء (٦٥٦–٦٦٧ · ٣٦٨):
  capital_updates: 'تحديثات رأس المال', comparison_updates: 'تحديثات المقارنة',
  free_margin_updates: 'تحديثات الهامش الحرّ', margin_level_updates: 'تحديثات مستوى الهامش',
  loss_limit_updates: 'تحديثات حدّ الخسارة', profit_limit_updates: 'تحديثات حدّ الربح',
  performance_updates: 'تحديثات الأداء', positions_updates: 'تحديثات المراكز',
  risk_updates: 'تحديثات المخاطر', drift_updates: 'تحديثات الانحراف', rollbacks: 'تراجعات',
  // النظام والأرشفة (١ · ٦ · ٧٠٧ · ٧١٤ · ٧٥٣ · ٨٠٢ · ٨٣٠):
  watching: 'يراقب', disk: 'القرص', usage: 'مستعمل', cpu: 'المعالج', mem: 'الذاكرة',
  archive: 'الأرشفة', archived: 'صفوف أُرشفت', successful: 'ناجحة', hours: 'ساعات',
  ago: 'مضت', at: 'عند', startup: 'الإقلاع', database: 'قاعدة البيانات', locked: 'مقفولة',
  regimes: 'الأنظمة السوقيّة',
}

// ٢٠٢٦-١٠-٠٥ (ختم المالك «ترجم nq»): رسائلُ هي **جُمَلٌ** لا أزواج — ترجمتها كلمةً كلمة
// تُخرج عربيّةً مكسّرة («جاهزة الأخير ناجحة أرشفة 5 ساعات مضت عند الإقلاع»). فتُترجَم
// بنمطها كاملًا قبل التقطيع، والقاموس أعلاه يبقى احتياطًا لما لا يطابق. وما يخرج من هنا
// عربيٌّ وأرقام ورموز أدوات فقط، فيمرّ في التقطيع كما هو. المصادر من كود ناشريها:
// ٧١٤ `atom.py:452` · ٦ · ٦١٣ · ٦٢٠ · ٨٠٢ `atom.py:104-106` · ١ `atom.py:134` ·
// ٨٠٠ `atom.py:477` · ٦٢٢ `atom.py:583-587` · ٨٣٠ `atom.py:218-231`.
const REGIME_AR: Record<string, string> = {
  TRENDING: 'اتجاهيّ', TRENDING_HIGH_VOL: 'اتجاهيّ عالي التذبذب',
  RANGING: 'عرضيّ', TRANSITION: 'انتقاليّ',
}
const PHRASES: [RegExp, string | ((...m: string[]) => string)][] = [
  // ٢٦/١٠ — 565 و509: «PULSE_STALE 806 silent 12s, judged on 003 x5 | …»، و509: «TRUTH_UNKNOWN 52992818 (no entry) | …».
  [/\bPULSE_STALE 806 silent (\d+)s, judged on 003 x(\d+)/,
    'نبضة الساعة (806) صامتة منذ $1ث — يُحكم بالساعة الاحتياطيّة (003)، $2 مرّة'],
  [/\bTRUTH_UNKNOWN (\S+) \(no entry\)/, 'أرقام الحساب $1 غير معروفة الآن — لا دخول'],
  [/^READY - last successful archive (\S+) hours ago at startup$/, 'جاهزة — آخر أرشفة ناجحة قبل $1 ساعة (عند الإقلاع)'],
  [/^BACKUP_STALE: last success (\S+) days ago$/, 'النسخ الاحتياطيّ قديم — آخر نجاح قبل $1 يوم'],
  [/^disk usage: (\S+)$/, 'القرص مستعمل: $1'],
  [/^forwarding (\d+) symbols via (\d+) routes$/, 'يمرّر $1 من الرموز عبر $2 من المسارات'],
  [/^streaming (\d+) symbols\b/, 'يبثّ $1 من الرموز'],
  [/^archive sources missing: (.+)$/, 'الأرشفة متوقّفة — مصادر غير موجودة: $1'],
  [/^SOURCES_MISSING (.+)$/, 'الأرشفة تعمل وتتخطّى مصادر غير موجودة: $1'],
  // ١ — «watching» يعني أنّ ختم النواة قُرئ وطابق المرجع؛ والبصمة المختصرة لا تُقرأ للمالك.
  [/^watching: (\S+) \(\S+\)$/, 'ختم النواة سليم: $1'],
  [/^(\d+) active alert\(s\)$/, '$1 من الإنذارات النشطة'],
  // ١١٦ — ثواني منذ آخر حدثٍ من كلّ مصدر (`-` = لم يصل قطّ).
  [/\(mt5=(\S+) ctrader=(\S+)\)/, '(منذ آخر حدث: الوسيط $1ث · سي‑تريدر $2ث)'],
  // ٦٠٨ — الوسيط بالثواني، والخوادم أسماءُ نطاقاتٍ لاتينيّة تُعَدّ ولا تُسرد.
  [/median_offset=(-?[\d.]+)s via (\S+)/,
    (_m, off, servers) => `فرق الساعة الوسيط=${off}ث من ${servers.split(',').length} خوادم وقت`],
  // ٤٥٨ — `ratio=<نسبة>/band=<نطاق الحياد>`: كان `band` يتسرّب لأنّ الشرطة تجعل القيمة «مسارًا».
  [/\bratio=(-?[\d.]+)\/band=(-?[\d.]+)/, 'النسبة=$1 ونطاق الحياد=$2'],
  // ١٠٣ — ذيل تنبيه الحجم الصفريّ.
  [/بـvolume=0 — استعمل tick_count\)/, 'بحجم صفر — استعمل عدد التِكّات)'],
  // ١١٢ — `أسوأ=EURUSD:31575,GBPUSD:273`: الرموز أعلام والأعداد أرقام.
  [/أسوأ=(\S+)/, (_m, list) => 'أسوأ: ' + list.split(',').map((x) => x.replace(':', ' ')).join(' · ')],
  // ٦٢٢ — ذيلُ عدّادات النقل: `p` هنا بايتاتُ رسالةٍ ناقصة لا «المشاركة».
  [/\bup=(\d+) c=(\d+) u=(\d+) q=(-?\d+) p=(\d+) rs=(\d+) pump=(\S+)/,
    'تحديثات=$1 اتصالات=$2 رسائل مجهولة=$3 بايتات بالانتظار=$4 رسالة ناقصة=$5 بايتًا إعادات اشتراك=$6 فاصل الضخّ=$7'],
  // ٤٥٣ — `last=<جهة> s=<اتفاق> p=<مشاركة>/<حدّها>`.
  [/\blast=(buy|sell|neutral) s=(\d+) p=([\d.]+)\/([\d.]+)/,
    (_m, side, s, p, min) => `الأخير=${side === 'buy' ? 'شراء' : side === 'sell' ? 'بيع' : 'محايد'} الاتفاق=${s} المشاركة=${p} وحدّها=${min}`],
  // ٨٣٠ — `regimes=BTCUSD:TRANSITION …`: الرمز اسم علم، والحالة تُعرَّب. يُفصل بمسافة
  // لأنّ «BTCUSD:انتقاليّ» كلمةٌ فيها لاتينيّ غير رمزٍ خالص فتُسقَط عند التقطيع.
  [/\bregimes=/, 'الأنظمة السوقيّة: '],
  [/\b([A-Z][A-Z0-9_]{2,}):(TRENDING_HIGH_VOL|TRENDING|RANGING|TRANSITION)\b/g,
    (_m, sym, st) => `${sym} ${REGIME_AR[st]} ·`],
]
// فاصلٌ يتيم في آخر السطر — بقيّة قائمةٍ سُرد آخرُها أو أُسقط.
const TRAILING_DOT = /(\s*·)+$/

// ——— محرّك الترجيح (580) — ث٣ (ق١٠ §١٨–٢١): القاموس المركزي للحدثين والحقول ———
// الحقول الستّة القابلة للترجيح بمفردات ق١٠ §٣ نفسها. state وweight ليسا هنا
// عمدًا: الحالة حاجز والوزن عامل مساهمة — لا سلّما نقاط، فلا منحنى لهما.
export const TILT_FIELD_AR: Record<string, string> = {
  direction: 'القيمة الاتجاهية',
  strength: 'القوة',
  confidence: 'الثقة',
  current_depth: 'العمق الحالي',
  required_depth: 'العمق المطلوب',
  ratio: 'النسبة',
}
export const TILT_SIDE_AR: Record<string, string> = {
  up: 'صعودًا',
  down: 'هبوطًا',
  abs: 'بالقيمة المطلقة',
}
// أسماء أحداث الترجيح بالعربي (تقرأها الشاشات من قاموس التيارات في streams.ts أيضًا)
export const TILT_EVENT_AR: Record<string, string> = {
  'tilt.rule.command': 'أمر قاعدة ترجيح',
  'tilt.rules.state': 'قواعد محرّك الترجيح',
  'tilt.state': 'حالة محرّك الترجيح',
}

// ——— بطاقة استمرار الاتّجاه (414) — مصدر القرار الوحيد منذ ٢٠٢٦-١٠-٠٧ ———
// ٢٠٢٦-١٠-٠٨ (فكّ الأقسام عن القرار، ختم المالك «NQ»): الاسم المختصر للحالة من `REASONS` أعلاه
// (مصدرٌ واحد للصحّة وللصفحات)، وهنا اللون والجملة التي تشرح الحالة لتاجرٍ بلا مصطلح ولا رقم ذرّة.
export type CardTone = 'green' | 'amber' | 'red' | 'grey'
export const CARD_STATUS_TONE: Record<string, CardTone> = {
  OPEN: 'green',
  OUTSIDE_OWNER_WINDOW: 'grey', NEWS_BLACKOUT: 'amber', FRAMES_DISAGREE: 'grey',
  CORRELATION_DISAGREES: 'grey', FACT_MISSING: 'amber', NO_PULLBACK_STRUCTURE: 'grey',
  NO_TRIGGER: 'grey', NO_TARGET_WITHIN_REACH: 'grey', NON_POSITIVE_RISK: 'amber',
  CANDLE_LATE: 'amber', CANDLE_OLD: 'grey', POSITION_OPEN: 'amber',
  POSITIONS_UNKNOWN: 'amber', ACCOUNT_UNKNOWN: 'red',
}
export const CARD_STATUS_HINT: Record<string, string> = {
  OPEN: 'كل الشروط تحقّقت — انبعتت صفقة بجهتها ووقفها وهدفها للتنفيذ.',
  OUTSIDE_OWNER_WINDOW: 'الوقت برّا ساعات التداول اللي حدّدتها (ذروة لندن · افتتاح أمريكا).',
  NEWS_BLACKOUT: 'في خبر قويّ قريب — التداول ممنوع حوله.',
  FRAMES_DISAGREE: 'اتّجاه الساعة واتّجاه الأربع ساعات مش بنفس الجهة.',
  CORRELATION_DISAGREES: 'الإس آند بي أو الداو مش ماشيين بنفس جهة الناسداك.',
  FACT_MISSING: 'معلومة لازمة للقرار ما وصلت بعد — ما في دخول على نقص.',
  NO_PULLBACK_STRUCTURE: 'ما في ارتداد واضح (قمّة وقاع مؤكَّدين بالترتيب الصحيح) على شموع ٥ دقائق.',
  NO_TRIGGER: 'الشمعة ما كسرت المستوى اللي بيفتح الدخول.',
  NO_TARGET_WITHIN_REACH: 'ما في هدف بثلاثة أضعاف الوقف ضمن حركة اليوم المعتادة.',
  NON_POSITIVE_RISK: 'الوقف طلع على السعر نفسه أو بالجهة الغلط — ما في دخول.',
  CANDLE_LATE: 'الشمعة وصلت متأخّرة عن وقتها، فسعرها صار ماضي.',
  CANDLE_OLD: 'شمعة سبق وانقرت — ما بتنعاد.',
  POSITION_OPEN: 'في صفقة مفتوحة على الرمز — ما بتنفتح تانية فوقها.',
  POSITIONS_UNKNOWN: 'صورة الصفقات المفتوحة ما وصلت بعد — ما في دخول على عمى.',
  ACCOUNT_UNKNOWN: 'رقم الحساب أو الوسيط ما وصل — الصفقة ما انبعتت.',
}
/** اسم حالة البطاقة بالعربيّة — والمجهول يُقال مجهولًا لا خامًا. */
export const cardStatusAr = (status?: unknown): string => {
  const s = String(status ?? '')
  if (!s) return 'ما وصلت حالة'
  return REASONS[s] ?? arabicVisible(s, 'حالة غير مترجمة')
}
/** نوافذ المالك كما ينشرها 412 (`shared/owner_windows.py:24-25`). */
export const OWNER_WINDOW_AR: Record<string, string> = {
  london_peak: 'ذروة لندن',
  ny_open: 'افتتاح أمريكا',
}
export const ownerWindowAr = (w?: unknown): string => {
  const s = String(w ?? '')
  if (!s || s === 'null' || s === 'None') return 'خارج النافذة'
  return OWNER_WINDOW_AR[s] ?? arabicVisible(s, 'نافذة غير مترجمة')
}

export function arabicVisible(value?: unknown, fallback = 'تفصيل تقني غير مترجم'): string {
  const text = String(value ?? '').trim()
  if (!text) return '—'
  return /[A-Za-z]/.test(text) ? fallback : text
}

/** اسم حقل من قاموس الحقول المركزي (العقد الثماني · المسارات) — لا يسرّب إنكليزيًّا. */
/**
 * اسم المنصّة في نصّ الواجهة — حكم المالك ٢٠٢٦-٠٨: «ما بدّي أشوف ولا شي أجنبيّ».
 * حارس tests/test_analysis_dashboard_arabic.py يمنع العلامة التجارية داخل النص
 * العربيّ، والقاموس نفسه يسمّيها «الوسيط» (UNAVAILABLE و
 * READY_AWAITING_FIRST_MT5_TRADE_EVENT). فكل ظهور سابق لاسم المنصّة في نصّ مُعرَض
 * يعود إلى هذه المفردة — لا حذف المعلومة، ولا إسكات الحارس.
 */
export const BROKER_PLATFORM_AR = 'منصّة الوسيط'
export const BROKER_ENGINE_AR = 'الإكسبرت'

export const fieldAr = (key: string): string => FIELDS[key] ?? arabicVisible(key, 'حقل تقني')

/** يترجم رسالة صحّة ذرّة إلى العربيّة، ولا يسرّب رمزًا إنجليزيًا مجهولًا للواجهة. */
export function arabicHealth(message?: string | null): string {
  if (!message) return '—'
  // ٢٠٢٦-٠٩-٢٣ — مقيسٌ على الشاشة الحيّة: رسالة ٥٦٠ تحمل فاصلَ وحداتٍ
  // (`\u001f`) بين الحساب والوسيط والرمز، فيظهر على الشاشة مربّعًا أسودَ
  // داخل النصّ: `Raw Trading Ltd␟BTCUSD=…`. وحرفُ تحكّمٍ ليس معلومةً أبدًا
  // ولا يُقرأ — يُبدَل بفاصلٍ مقروء. والأصل باقٍ في تلميح الفأرة كما هو.
  const clean = message.replace(/[\u0000-\u0008\u000b-\u001f\u007f]+/g, ' · ')
  const direct = REASONS[clean.trim()]
  if (direct) return direct
  const phrased = PHRASES.reduce(
    (text, [re, to]) => (typeof to === 'string' ? text.replace(re, to) : text.replace(re, to)), clean)
  return phrased
    .split(/\s+/)
    .map((raw) => {
      // فاصلة/فاصلة منقوطة/نقطتان لاصقة بآخر الكلمة تمنع مطابقة القاموس — تُقصّ وتُعاد
      const tail = /[،,؛;:]+$/.exec(raw)?.[0] ?? ''
      const token = tail ? raw.slice(0, raw.length - tail.length) : raw
      const put = (t: string) => t + tail
      if (REASONS[token]) return put(REASONS[token])
      const pair = token.match(/^([A-Za-z_]+)=(.*)$/)
      if (pair) {
        // ٢٠٢٦-٠٩-١٦ — حكم المالك «فكّر إنّك بشري بيعرف تداول بس»: كان الحقل
        // المجهول يُطبع «حقل تقني=قيمة تقنية»، فيقرأ المالك على صفحة «التنفيذ»
        // سطرًا يقول حرفيًّا `حقل تقني=قيمة تقنية حقل تقني=قيمة تقنية` —
        // **عبارةٌ تشبه المعلومة ولا تحمل شيئًا**، وهي أسوأ من الرمز الخام:
        // الخام يمكن نسخه والسؤال عنه، أمّا هذه فتُقرأ بيانًا فارغًا.
        // الآن: ما لا تُعرف ترجمته يُحذف من النصّ المعروض ويُعلَن عدده، ويبقى
        // الأصل كاملًا في الخام وتلميح الفأرة.
        const rawValue = pair[2]
        // مفتاحٌ اسمه رمز أداة (`BTCUSD=1e-05`) — اسم عَلَم يبقى كما هو، وإلّا
        // أسقطنا رقم السبريد لكل رمز بحجّة أنّه «غير مترجَم».
        // 🔴 ٢٠٢٦-٠٩-٢٣ — البحثُ عن **اسم** الحقل كان في `FIELDS` وحده،
        // والأسبابُ تسكن `REASONS`. فرسالةُ مدير التنفيذ (٥٥٠) تعدّ الرفضَ
        // بصيغة `سبب=عدد`:
        //
        //   رفض: STOP_BELOW_FLOOR=715 RISK_OFF_BUDGET=27
        //        SYMBOL_RESOLUTION_TIMEOUT=23 · تخطٍّ: UPSTREAM_REJECTED=7
        //
        // فلا يُوجد الاسمُ فيُسقَط **الزوجُ كلُّه** — والعددُ معه. فيقرأ
        // المالك «رفض:» ثمّ لا شيء، وهذه أهمُّ ثلاثة أرقامٍ في الرسالة:
        // ٧١٥ أمرًا رُفضت لوقفٍ دون الأرضيّة، ولم تصل الشاشة قطّ.
        //
        // وكنتُ صحّحتُ الجهةَ المقابلة (القيمة) في ٠٩-١٦ بالحجّة نفسها
        // حرفيًّا — «معنى الكلمة واحد أينما وقعت» — ونسيتُ جهةَ الاسم.
        const label = SYMBOLISH.test(pair[1])
          ? pair[1]
          : FIELDS[pair[1]] ?? REASONS[pair[1]]
        // ٢٠٢٦-٠٩-١٦: الكلمة الواحدة قد تقع مفتاحًا أو قيمةً (`sell` تظهر
        // حقلًا في ذرّة وقيمةً في أخرى)، وكان البحث للقيم في `REASONS` وحده
        // فتُسقَط قيمةٌ لها ترجمة في `FIELDS`. معنى الكلمة واحد أينما وقعت.
        const known = REASONS[rawValue] ?? FIELDS[rawValue]
        const numeric = rawValue !== '' && !/[A-Za-z]/.test(rawValue)
        if (!label) return ''                       // حقل مجهول كليًّا — يُسقط
        // 🔴 ٢٠٢٦-٠٩-٢٣ — قاعدةُ «ما لا يُترجَم يُسقَط» صارت تأكل **الخبر
        // نفسه**. مقيسٌ على الحيّ: حارس سلامة الملفّات (٧) ينشر
        //
        //   modified: file:core/CORE.lock; modified: file:pyproject.toml;
        //   modified: dir:atoms/::قسم 000-049/001_NQ/الشرح.md; +563 more
        //
        // فكانت الشاشة تكتب **«عُدِّل: عُدِّل: عُدِّل: … +563 أخرى»** — الكلمة
        // ستّ مرّات بلا اسمِ ملفٍّ واحد. ومسارُ الملفّ هو كلُّ الخبر في
        // حارسٍ وظيفتُه أن يقول **ما تغيّر**؛ بدونه البلاغ ضجيجٌ لا إنذار.
        //
        // والمسارُ ليس «مصطلحًا أجنبيًّا لم يُترجَم» — هو **بيانات**، كرقمٍ
        // أو رمزِ أداة. فيُبقى كما هو.
        const value = known
          ?? (numeric || SYMBOLISH.test(rawValue) || PATHISH.test(rawValue) ? rawValue : null)
        if (value == null) return ''                // قيمة لا تُقرأ — يُسقط الزوج
        return put(`${label}=${value}`)
      }
      // كلمة مفردة معروفة، أو سلسلة تحمل سببًا داخلها.
      for (const key of Object.keys(REASONS)) {
        if (token.startsWith(key + '_')) {
          const rest = token.slice(key.length + 1)
          return put(`${REASONS[key]} · ${REASONS[rest] ?? arabicVisible(rest, 'تفصيل تقني')}`)
        }
      }
      // كلمة مفردة: تُعرض إن كانت معروفة أو رقمًا أو رمز أداة (BTCUSD…)،
      // وتُسقط إن كانت إنكليزيّة مجهولة. رموز الأدوات ليست لغةً بل أسماء أعلام.
      if (FIELDS[token]) return put(FIELDS[token])
      // 🔴 ٢٠٢٦-٠٩-٢٣ — هنا كانت تُؤكل أسماء الملفّات. حارس السلامة (٧)
      // ينشر `modified: file:core/CORE.lock; modified: dir:atoms/…` فيمرّ
      // `modified` على القاموس («عُدِّل») ويسقط `file:core/CORE.lock` لأنّه
      // «إنكليزيّة مجهولة». فقرأ المالك على الشاشة:
      //
      //   عُدِّل: عُدِّل: عُدِّل: عُدِّل: عُدِّل: عُدِّل: +563 أخرى
      //
      // كلمةٌ ستّ مرّات بلا اسمِ ملفٍّ واحد — من حارسٍ وظيفتُه أن يقول **ما
      // تغيّر**. والمسار هو كلُّ الخبر؛ بدونه البلاغ ضجيجٌ لا إنذار.
      //
      // فالمسارُ **بيانات لا لغة** (كالرقم ورمز الأداة) ويُبقى كما هو،
      // وبادئتاه `file:`/`dir:` تُعرَّبان لأنّهما كلمتان لا مسار.
      const filed = /^(file|dir):(.+)$/.exec(token)
      if (filed) return put(`${filed[1] === 'dir' ? 'مجلَّد' : 'ملف'} ${filed[2]}`)
      if (!/[A-Za-z]/.test(token) || SYMBOLISH.test(token) || PATHISH.test(token)) return put(token)
      return ''
    })
    .filter((t) => t !== '')
    .join(' ')
    .replace(TRAILING_DOT, '')
    .trim() || '—'
}

/**
 * رموز الأدوات والمؤشّرات تُكتب لاتينيّةً في كل منصّات العالم، وهي **أسماء
 * أعلام لا لغة أجنبيّة**: `EURUSD` · `XAUUSD` · `^GSPC` · `DXY_U6`. تُعرض كما
 * هي — تعريبها يخلق اسمًا لا يعرفه أحد ولا يطابق ما على منصّة الوسيط.
 */
const SYMBOLISH = /^[\^]?[A-Z][A-Z0-9]{2,}(?:[_.][A-Z0-9]+)?$/

/**
 * مسارُ ملفٍّ أو مجلَّد — **بيانات لا لغة**، كالرقم ورمز الأداة. يُعرض كما هو.
 *
 * أُضيف ٢٠٢٦-٠٩-٢٣ لأنّ قاعدة «ما لا يُترجَم يُسقَط» كانت تحذف أسماء
 * الملفّات من بلاغ حارس السلامة (٧)، فيقرأ المالك «عُدِّل» ستّ مرّات ولا
 * يعرف **ماذا** عُدِّل — وذلك كلُّ الخبر.
 *
 * يُقبل: `core/CORE.lock` · `shared/live_analysis.py` · `pyproject.toml`
 *        `dir:atoms/::قسم 000-049/001_NQ/الشرح.md` · `C:\x\y.json`
 */
const PATHISH = /[/\\]|\.(py|ts|tsx|json|ya?ml|md|lock|toml|db|log|txt|bat|ps1|csv|ini|cfg)$/i

/** حالة الذرّة نفسها (تعمل / متوقّفة). */
export function arabicState(state?: string | null): string {
  if (state === 'running') return 'تعمل'
  if (state === 'stopped') return 'متوقّفة'
  if (state === 'failed') return 'فاشلة'
  return arabicVisible(state, 'حالة غير معروفة')
}
