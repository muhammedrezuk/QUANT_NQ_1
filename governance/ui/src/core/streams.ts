// أسماء التيارات/الأحداث بالعربي — قاموس مشترك واحد لكل الشاشات (بند 10/13 من دفتر 97):
// «التنبيهات» و«التشخيص» و«المراقبة» و«الرئيسية» كلها تقرأ من هون — لا قواميس متفرّقة.
// القاعدة (المثبتة بالورقة): المعروف يُترجم، والغريب يظهر باسمه الخام — صدق أوضح من إخفائه.

// ترجمة دقيقة للتيارات الحيّة الشائعة (المرصودة فعلًا على الناقل)
const EXACT: Record<string, string> = {
  'market.tick': 'أسعار السوق (تكّات)',
  'market.tick.validated': 'تكّات مدقَّقة',
  'market.trade': 'صفقات السوق',
  'market.volume': 'حجم السوق',
  'market.depth': 'عمق السوق',
  'market.news': 'أخبار السوق',
  'market.calendar': 'التقويم الاقتصادي',
  'market.reference': 'السعر المرجعي',
  'market.symbol_specs': 'مواصفات الرموز',
  'market.ctrader.symbol_specs': 'مواصفات رموز سي-تريدر',
  'market.structure.updated': 'البنية',
  'market.liquidity.updated': 'السيولة',
  'market.outcome.realized': 'نتائج الصفقات المحقَّقة',
  'market.time.drift': 'انحراف ساعة السوق',
  'market.feed.provider_down': 'سقوط مزوّد السوق',
  'market.feed.provider_recovered': 'رجوع مزوّد السوق',
  'market_data.candle_closed': 'الشموع (إغلاق شمعة)',
  'market_data.price_received': 'استقبال الأسعار',
  'market_data.volume_received': 'استقبال الحجم',
  'market_data.news_received': 'استقبال الأخبار',
  'market_data.calendar_event': 'حدث تقويم اقتصادي',
  'market_data.calendar_window': 'نافذة التقويم',
  'market_data.calendar.state': 'حالة التقويم',
  // ٢٠٢٦-٠٩-١٦ — حدثان بلا ناشر منذ أن حذف المالك بيده الذرّتين ١١٣ و١١٤
  // (بلاغ جلسة ١٠٠-١٤٩، والنشر توقّف حيًّا: ١٤٧٦/دقيقة ⟵ صفر في ٤٥ ثانية).
  //
  // ويبقيان هنا عمدًا، وقِيس قبل القرار: **صفر ظهور** لهما في أيّ بطاقة أو
  // شاشة، و**صفر ذرّة** تشترك فيهما — فلا صفحة تنتظرهما ولا مستهلك يتيم.
  // والقاموس ليس ادّعاءً بوجود الحدث: لا يُعرَض اسمٌ منه إلّا إن وصل حدثه.
  // أمّا حذفهما فيفتح بابًا حقيقيًّا: إن أرجع المالك الذرّتين — والملفّان
  // ما زالا في `HEAD` — عادا يظهران **بالإنكليزيّة الخام** على شاشته.
  // فبقاؤهما تأمينٌ بلا كلفة، وحذفهما مقامرةٌ بلا مكسب.
  'market_data.cleaned': 'بيانات سوق منظَّفة',
  'market_data.normalized': 'بيانات سوق موحَّدة',
  'market_data.feed_interrupted': 'انقطاع التغذية',
  'market_data.feed_recovered': 'رجوع التغذية',
  'market_data.feed.state': 'حالة التغذية',
  'market_data.quality_alert': 'إنذار جودة البيانات',
  'market_data.quality.state': 'جودة بيانات السوق',
  'market_data.spread_updated': 'الفرق السعري',
  'market_data.depth_updated': 'تحديث العمق',
  'market_data.trade_tape_updated': 'شريط الصفقات',
  'market_data.reference_index_updated': 'المؤشّر المرجعي',
  'market_data.validation_failed': 'فشل تدقيق بيانات السوق',
  'market_data.validation.state': 'حالة تدقيق البيانات',
  'market_data.state': 'حالة بيانات السوق',
  'analysis.raw.completed': 'التحليل الحي',
  'analysis.fast.state': 'بطاقة المسار السريع (تكّات)',
  'analysis.slow.state': 'بطاقة المسار البطيء (شموع)',
  'analysis.cycle.collected': 'دورة التحليل',
  'analysis.setting.changed': 'تغيّر إعداد محلّل',
  'analysis.settings.command': 'أمر إعدادات التحليل',
  'structure.cycle.collected': 'دورة البنية',
  'structure.cycle.validated': 'تدقيق دورة البنية',
  'structure.validation_failed': 'فشل تدقيق البنية',
  'liquidity.cycle.collected': 'دورة السيولة',
  'liquidity.cycle.validated': 'تدقيق دورة السيولة',
  'liquidity.validation_failed': 'فشل تدقيق السيولة',
  'liquidity.units.state': 'وحدات السيولة',
  'liquidity.section.live': 'قسم السيولة الحيّ',
  'liquidity.depth.state': 'عمق الدفتر (٢٦١)',
  'liquidity.microprice.state': 'الميكرو-سعر (٢٦٢)',
  'liquidity.ofi.state': 'تدفّق الأوامر OFI (٢٦٣)',
  'liquidity.price_impact.state': 'أثر السعر بالدفتر (٢٦٤)',
  'stats.cycle.collected': 'دورة الإحصاء',
  'probability.cycle.collected': 'دورة الاحتمالات',
  'strategy.cycle.collected': 'دورة الاستراتيجيات',
  'decision.cycle.collected': 'دورة القرار',
  'decision.aggregated.state': 'تجميع أدلّة القرار',
  'decision.scored.state': 'درجة القرار',
  'decision.resolved.state': 'حلّ تعارض القرار',
  'decision.filtered.state': 'فلتر القرار',
  'decision.approved.state': 'موافقة القرار',
  // ٢٠٢٦-١٠-٠٨ (فكّ الأقسام عن القرار، ختم المالك «NQ»): أحداث المسار الجديد 414 ⟵ 467 ⟵ 555 — كانت تظهر نصف إنكليزيّة.
  'strategy.card.state': 'بطاقة استمرار الاتّجاه (٤١٤)',
  'strategy.setup.proposed': 'إعداد صفقة مقترَح',
  'strategy.session.state': 'نافذة المالك (الجلسة)',
  'news.trading_window.state': 'نافذة منع الخبر',
  'structure.levels.state': 'سلّم المستويات',
  'decision.gate.passed': 'مرّ القرار من البوّابة',
  'decision.gate.blocked': 'حُجب القرار عند البوّابة',
  'decision.gate.recorded': 'سُجّل القرار انتظارًا',
  'decision.card.state': 'دفتر البطاقات',
  'decision.card.opened': 'فُتحت بطاقة بالدفتر',
  'decision.card.closed': 'أُغلقت بطاقة بالدفتر',
  'decision.card.changed': 'تغيّرت بطاقة بالدفتر',
  'execution.entry.state': 'حالة طالب أمر الدخول',
  'decision.dispatch.state': 'إرسال القرار',
  'decision.evaluated.state': 'تقييم القرار',
  'decision.settings.state': 'عيارات القرار',
  'decision.settings.command': 'أمر عيارات القرار',
  'parameter.approve.command': 'أمر اعتماد مُعامِل معلن',
  'parameter.approved.state': 'اعتماد مُعامِل معلن',
  'dial.profile.state': 'ملفّ العيار (التعرّض)',
  'dial.command': 'أمر العيار',
  'tilt.rule.command': 'أمر قاعدة ترجيح',
  'tilt.rules.state': 'قواعد محرّك الترجيح',
  'tilt.state': 'حالة محرّك الترجيح',
  'risk.unified.state': 'حالة المخاطر الموحّدة',
  'risk.exposure.state': 'التعرّض',
  'risk.position_size.state': 'تحجيم المركز',
  'risk.position_size.rejected': 'رفض تحجيم المركز',
  'risk.structure_stop.state': 'الوقف الهيكلي',
  'risk.hard_stop.price': 'سعر الوقف الصلب',
  'risk.asset_ledger.state': 'دفتر مخاطر الأصل',
  'risk.account_limits.state': 'حدود الحساب',
  'risk.account_limits.command': 'أمر حدود الحساب',
  'risk.asset_budget.state': 'ميزانيّة مخاطر الأصل',
  'risk.halt.requested': 'طلب إيقاف طارئ',
  'risk.kill_switch.reset_requested': 'طلب تصفير قاطع الأمان',
  'risk.loss_reported': 'تبليغ خسارة',
  'execution.gate.state': 'حالة بوّابة التنفيذ',
  'execution.gate.command': 'أمر بوّابة التنفيذ',
  'execution.unified.state': 'حالة التنفيذ الموحّدة',
  'execution.order.requested': 'طلب أمر',
  'execution.order.built': 'بناء أمر',
  'execution.order.legal': 'شرعيّة الأمر',
  'execution.order.skipped': 'أمر ما انبنى',
  'execution.order.rejected': 'أمر مرفوض',
  'execution.order.resolved': 'حلّ رمز الأمر',
  'execution.manage.intent': 'نيّة إدارة صفقة',
  'execution.manage.command': 'أمر إدارة صفقة',
  'execution.manage.written': 'انكتبت الإدارة للجسر',
  'execution.snapshot.state': 'لقطة التنفيذ',
  'execution.reconcile.state': 'مطابقة المراكز',
  'execution.reconcile.requested': 'طلب مطابقة المراكز',
  'execution.desired.state': 'الوضع المطلوب',
  'execution.quality.state': 'جودة التنفيذ',
  'execution.reference_divergence.state': 'انحراف السعر المرجعي',
  'execution.command.ack': 'تأكيد أمر تنفيذ',
  'execution.command.failed': 'فشل أمر تنفيذ',
  'execution.confirmation.rejected': 'رفض تأكيد التنفيذ',
  'trading.final_decision': 'قرار نهائي (انبعت للجسر)',
  'platform.account.state': 'حالة حساب التنفيذ',
  'platform.positions.state': 'مراكز المنصّة',
  'platform.terminal_state': 'حالة طرفيّة ميتاتريدر 5',
  'platform.trade_event': 'حدث صفقة من المنصّة',
  'platform.position.appeared': 'ظهور مركز بالمنصّة',
  'platform.position.vanished': 'اختفاء مركز من المنصّة',
  'platform.brain_signal.written': 'انكتبت إشارة الدماغ',
  'platform.brain_signal.write_failed': 'فشل كتابة إشارة الدماغ',
  'platform.brain_signal.halted': 'إشارة الدماغ موقوفة',
  'perpetual.pair.state': 'زوج المركز الدائم',
  'perpetual.target.state': 'هدف المركز الدائم',
  'perpetual.plan.state': 'خطّة المركز الدائم',
  'perpetual.entry.state': 'دخول المركز الدائم',
  'perpetual.asset.activate': 'تفعيل أصل دائم',
  'perpetual.asset.deactivate': 'إيقاف أصل دائم',
  'perpetual.owner.escalation': 'تصعيد للمالك',
  'asset.portfolio.state': 'محفظة الأصول',
  'asset.extraction.state': 'سحب أرباح الأصل',
  'feed.mt5.tick': 'تغذية ميتاتريدر 5',
  'feed.ctrader.tick': 'تغذية سي-تريدر',
  'system.commands.state': 'بوّابة الأوامر (901)',
  'emergency.halt': 'إيقاف طارئ',
  'kernel.clock.heartbeat': 'نبض النواة',
  'time.utc.synced': 'مزامنة الوقت العالمي',
  'SYS_SECOND': 'نبضة الثانية',
  'SYS_5MIN': 'نبضة 5 دقائق',
  'SYS_15MIN': 'نبضة 15 دقيقة',
  'SYS_HOUR': 'نبضة الساعة',
  'SYS_DAY': 'نبضة اليوم',
  // القياس الحيّ ٢٠٢٦-٠٩-٠٩: هذه تبثّ فعلًا على الناقل وكانت تظهر خامًا
  'kernel.clock.sys_tick': 'نبضة ساعة النواة',
  'feed.ctrader.raw': 'تغذية سي-تريدر الخام',
  'feed.relay.state': 'حالة ناقل التغذية',
  'ai.brain.state': 'حالة العقل الاصطناعي',
  'drift.vector.state': 'حالة متجهة الانحراف',
  'telemetry.carrier.state': 'حالة ناقل القياس البعيد',
  'time.ntp.samples.state': 'حالة عيّنات مزامنة NTP',
  'decision.room.state': 'حالة غرفة القرار',
  'market.book.state': 'حالة دفتر السوق',
  'market.regime.state': 'حالة نظام السوق',
  'core.integrity.alert': 'إنذار سلامة النواة',
  'audit.trail.state': 'سجلّ التدقيق',
  'reference.health.state': 'صحّة المرجع',
  'allowed.symbols.state': 'قائمة الرموز المسموحة',
  'symbol.resolve.requested': 'طلب حلّ رمز',
  'symbol.resolve.result': 'نتيجة حلّ رمز',
  'symbol.resolve.orphaned': 'رمز بلا حلّ',
  'model.persisted': 'حُفظ النموذج',
  'model.persist_requested': 'طلب حفظ النموذج',
  // المُنذِر (831) — تنبيه موحّد من أحداث الإخفاق التي كانت بلا مستمع
  'system.alert': 'تنبيه المُنذِر (إخفاق نشط)',
  'system.alert.state': 'حالة المُنذِر (التنبيهات النشطة)',
  'system.alert.recovered': 'استرداد المُنذِر (انقضاء الصمت)',
  'storage.persistence.save_failed': 'فشل حفظ النماذج',
  'tools.integrity.violation': 'اختراق سلامة الملفات',
  'tools.backup.failed': 'فشل النسخ الاحتياطي',
  'tools.file_archive.failed': 'فشل أرشفة الملفات',
  'tools.file_cleanup.failed': 'فشل تنظيف الملفات',
  'tools.storage.low': 'مساحة التخزين منخفضة',
  'time.utc.stale': 'تقادم مزامنة UTC',
  'time.ntp.drift': 'انحراف NTP (تجاوز العتبة)',
  'financial.truth.shortage': 'نقص الحقيقة المالية (هامش)',
  'storage.symbol.unmapped': 'رمز غير مسجّل',
  'time.clock.divergence': 'انحراف الساعة',
}

// عائلات — لأي اسم غير معروف بالضبط، نعرّف على الأقل عائلته بالعربي
const FAMILY: Array<[string, string]> = [
  ['market_data.', 'بيانات السوق'],
  ['market.', 'السوق'],
  ['analysis.', 'التحليل'],
  ['structure.', 'البنية'],
  ['liquidity.', 'السيولة'],
  ['stats.', 'الإحصاء'],
  ['probability.', 'الاحتمالات'],
  ['strategy.', 'الاستراتيجيات'],
  ['decision.', 'القرار'],
  ['risk.', 'المخاطر'],
  ['execution.', 'التنفيذ'],
  ['platform.', 'المنصّة'],
  ['portfolio.', 'المحفظة'],
  ['perpetual.', 'المركز الدائم'],
  ['asset.', 'الأصل'],
  ['storage.', 'التخزين'],
  ['learning.', 'التعلّم الآلي'],
  ['tools.', 'الأدوات'],
  ['feed.', 'التغذية'],
  ['symbol.', 'الرموز'],
  ['system.', 'النظام'],
  ['kernel.', 'النواة'],
  ['dial.', 'العيار'],
  ['tilt.', 'الترجيح'],
  ['audit.', 'التدقيق'],
  ['reference.', 'المرجع'],
  ['emergency.', 'الطوارئ'],
  ['trading.', 'التداول'],
  ['model.', 'النموذج'],
  ['atom.', 'الذرّات'],
  // ٢٠٢٦-٠٩-٠٩ (ختم NQ): ثماني عائلات تبثّ على الناقل ولم تكن بالجدول، فأسماؤها
  // كانت تظهر إنكليزيّة خامًا بالكامل (adaptation.kill_switch.state…). مقيسة حيًّا.
  ['adaptation.', 'التكيّف'],
  ['ai.', 'الذكاء الاصطناعي'],
  ['drift.', 'الانحراف'],
  ['logs.', 'السجلّات'],
  ['measurement.', 'القياس'],
  ['telemetry.', 'القياس البعيد'],
  ['time.', 'الوقت'],
  ['horizon.', 'الأفق'],
  ['parameter.', 'المُعامِل'],
]

// ── قاموس المقاطع ──
// القياس الحيّ (٢٠٢٦-٠٩-٠٩، ٤٥ ثانية على ناقل النواة): من ١٨٨ حدثًا تبثّ فعلًا،
// ١٣٣ كانت تظهر للمالك بإنكليزيّة — ١١ خامًا بالكامل و١٢٢ نصفيّة مثل
// «التحليل: momentum.state» — على لوحة مواصفتها عربيّة كاملة (ورقة ٩٩ بند ١).
// العلاج ليس سطرًا لكل حدث (يعود الخلل مع أوّل حدث جديد) بل ترجمة مقطعًا مقطعًا.
// والقاعدة الأصليّة محفوظة: إن جُهِل مقطع واحد يظهر الاسم خامًا كما كان —
// صدقٌ أوضح من تلفيق، ولا قناع على معنى.
const WORD: Record<string, string> = {
  // الأنواع (المقطع الأخير — يتقدّم بالجملة العربيّة)
  state: 'حالة', live: 'بثّ', command: 'أمر', requested: 'طلب', record: 'سجلّ',
  recorded: 'تسجيل', collected: 'دورة', validated: 'تدقيق', completed: 'اكتمال',
  synced: 'مزامنة', saved: 'حفظ', applied: 'تطبيق', approved: 'اعتماد',
  approve: 'اعتماد', rejected: 'رفض', failed: 'فشل', skipped: 'تخطّي',
  built: 'بناء', written: 'كتابة', resolved: 'حلّ', evaluated: 'تقييم',
  scored: 'تقييم درجة', filtered: 'فلترة', aggregated: 'تجميع', merged: 'دمج',
  appeared: 'ظهور', vanished: 'اختفاء', realized: 'تحقّق', confirmed: 'تأكيد',
  ack: 'إقرار', updated: 'تحديث', changed: 'تغيّر', cleaned: 'تنظيف',
  normalized: 'توحيد', enriched: 'إغناء', selected: 'اختيار', proposed: 'اقتراح',
  ready: 'جهوز', blocked: 'حجب', halted: 'إيقاف', stale: 'تقادم',
  violation: 'اختراق', alert: 'إنذار', shortage: 'نقص', escalation: 'تصعيد',
  orphaned: 'بلا حلّ', unmapped: 'غير مسجّل', persisted: 'حفظ دائم',
  archived: 'أرشفة', compressed: 'ضغط', tracked: 'تتبّع', release: 'إفراج',
  result: 'نتيجة', summary: 'ملخّص', evidence: 'أدلّة', samples: 'عيّنات',
  sample: 'عيّنة', price: 'سعر', tick: 'تِكّة', raw: 'خام', heartbeat: 'نبض',
  sys_tick: 'نبضة', low: 'انخفاض', active: 'تفعيل', setup: 'تهيئة',
  // المقاييس والأسماء
  momentum: 'الزخم', trend: 'الاتجاه', volatility: 'التقلّب', volume: 'الحجم',
  spread: 'الفرق السعري', session: 'الجلسة', candle: 'الشمعة', gap: 'الفجوة',
  noise: 'الضجيج', acceleration: 'التسارع', velocity: 'السرعة',
  correlation: 'الارتباط', relative_strength: 'القوّة النسبية',
  analysts: 'المحلّلين', volume_quality: 'جودة الحجم', quality: 'الجودة',
  time: 'الوقت', clock: 'الساعة', latency: 'زمن الاستجابة', health: 'الصحّة',
  // البنية
  bos: 'كسر البنية', choch: 'تغيّر الشخصية', mss: 'تحوّل البنية',
  swing: 'التأرجح', phase: 'الطور', internal: 'الداخليّة', external: 'الخارجيّة',
  // السيولة
  pool: 'بِركة السيولة', sweep: 'الكنس', fvg: 'فجوة القيمة العادلة',
  ofi: 'تدفّق الأوامر', microprice: 'السعر الدقيق', depth: 'العمق',
  price_impact: 'أثر السعر', buyside: 'جهة الشراء', sellside: 'جهة البيع',
  book: 'الدفتر', absorption: 'الامتصاص', delta: 'الدلتا', cvd: 'الدلتا التراكميّة',
  // الإحصاء
  mean: 'المتوسّط', median: 'الوسيط', mode: 'المنوال', std: 'الانحراف المعياري',
  variance: 'التباين', cv: 'معامل الاختلاف', skewness: 'الالتواء',
  kurtosis: 'التفلطح', zscore: 'الدرجة المعياريّة', regression: 'الانحدار',
  r_squared: 'معامل التحديد', outlier: 'الشواذّ', distribution: 'التوزيع',
  range: 'المدى', period_compare: 'مقارنة الفترات', hurst: 'معامل هرست',
  // القرار والاستراتيجيّات
  filter: 'فلتر', confidence: 'الثقة', conditions: 'الشروط', timing: 'التوقيت',
  freshness: 'الطزاجة', position: 'المراكز', asset: 'الأصل', room: 'الغرفة',
  wait: 'الانتظار', gate: 'البوّابة', cycle: 'الدورة', aggregate: 'المجموع',
  breakout: 'الاختراق', pullback: 'الارتداد', reversal: 'الانعكاس',
  entry_quality: 'جودة الدخول', invalidation_quality: 'جودة الإبطال',
  news: 'الأخبار', eligibility: 'الأهليّة', dispatch: 'الإرسال',
  // المال والمخاطر
  account: 'الحساب', balance: 'الرصيد', equity: 'القيمة', margin: 'الهامش',
  free_margin: 'الهامش الحرّ', margin_level: 'مستوى الهامش', pnl: 'الربح والخسارة',
  exposure: 'التعرّض', position_size: 'تحجيم المركز', structure_stop: 'الوقف الهيكلي',
  hard_stop: 'الوقف الصلب', asset_stop: 'وقف الأصل', take_profit: 'أخذ الربح',
  asset_ledger: 'دفتر الأصل', asset_budget: 'ميزانيّة الأصل', audit: 'التدقيق',
  session_limits: 'حدود الجلسة', loss_limits: 'حدود الخسارة',
  profit_limits: 'حدود الربح', limits: 'الحدود', kill_switch: 'قاطع الأمان',
  risk_distribution: 'توزيع المخاطر', capital_distribution: 'توزيع رأس المال',
  overview: 'النظرة العامّة', comparison: 'المقارنة', performance: 'الأداء',
  components: 'المكوّنات', extraction: 'سحب الأرباح',
  // التنفيذ والمنصّة
  order: 'الأمر', orders: 'الأوامر', entry: 'الدخول', manage: 'الإدارة',
  reconcile: 'المطابقة', desired: 'المطلوب', snapshot: 'اللقطة',
  positions: 'المراكز', terminal_state: 'حالة الطرفيّة', legal: 'الشرعيّة',
  reference_divergence: 'انحراف المرجع', reference: 'المرجع',
  confirmation: 'التأكيد', final_decision: 'القرار النهائي',
  // النظام
  units: 'الوحدات', section: 'القسم', diagnosis: 'التشخيص', integrity: 'السلامة',
  vector: 'المتجهة', carrier: 'الناقل', brain: 'العقل', relay: 'الناقل',
  map: 'الخريطة', symbols: 'الرموز', symbol: 'الرمز', trades: 'الصفقات',
  decisions: 'القرارات', device_resources: 'موارد الجهاز', profile: 'الملفّ',
  rule: 'القاعدة', rules: 'القواعد', dial: 'العيار', settings: 'العيارات',
  setting: 'العيار', plan: 'الخطّة', target: 'الهدف', pair: 'الزوج',
  model: 'النموذج', feature: 'السمة', backup: 'النسخ الاحتياطي',
  persistence: 'الحفظ الدائم', storage: 'التخزين', fast: 'السريع', slow: 'البطيء',
  utc: 'التوقيت العالمي', ntp: 'مزامنة NTP', portfolio: 'المحفظة',
  calendar: 'التقويم', trading_window: 'نافذة التداول', regime: 'نظام السوق',
  ctrader: 'سي-تريدر', mt5: 'ميتاتريدر 5', liquidity: 'السيولة',
  // ٢٠٢٦-٠٩-١٠ (لقطة المالك): بقيت هذه إنكليزيّة خامًا بصفحة العدّادات —
  // القاموس عُوير على ١٨٨ حدثًا تبثّ، والصفحة تعرض ٢٦٩ من عدّاد الناقل.
  broker_tick: 'تِكّة الوسيط', batch: 'الدفعة', closed: 'إغلاق',
  minute_elapsed: 'انقضاء دقيقة', elapsed: 'انقضاء',
  market_data_saved: 'حفظ بيانات السوق', behaviour: 'السلوك',
  unhealthy: 'غير سليمة', unloaded: 'مسحوبة', started: 'إقلاع',
  stopped: 'إيقاف', restarted: 'إعادة تشغيل', hot_reload: 'تحميل حارّ',
  decisions_saved: 'حفظ القرارات', analysis_saved: 'حفظ التحليل',
  structure_saved: 'حفظ البنية', liquidity_saved: 'حفظ السيولة',
  orders_saved: 'حفظ الأوامر', trades_saved: 'حفظ الصفقات',
  portfolio_saved: 'حفظ المحفظة', feed: 'التغذية', analysis: 'التحليل',
  structure: 'البنية', stats: 'الإحصاء', probability: 'الاحتمالات',
  strategy: 'الاستراتيجيّات', decision: 'القرار', risk: 'المخاطر',
  execution: 'التنفيذ', market: 'السوق',
}

/** يبني اسمًا عربيًّا من مقاطع الحدث: النوع (آخر مقطع) يتقدّم، والبقيّة تتبعه.
 *  يرجع `null` إن جُهِل أيّ مقطع — فيظهر الاسم خامًا بدل تلفيق نصفه. */
function composeAr(rest: string): string | null {
  const parts = rest.split('.').filter(Boolean)
  if (parts.length === 0) return null
  const words = parts.map((p) => WORD[p])
  if (words.some((w) => !w)) return null
  if (words.length === 1) return words[0] as string
  const kind = words[words.length - 1] as string
  return `${kind} ${words.slice(0, -1).join(' ')}`
}

/** اسم التيار بالعربي. الغريب تمامًا يرجع باسمه الخام (لا «غير معروف» أبدًا). */
export function streamAr(ev: string): string {
  const exact = EXACT[ev]
  if (exact) return exact
  for (const [prefix, family] of FAMILY) {
    if (ev.startsWith(prefix)) {
      const rest = ev.slice(prefix.length)
      const built = composeAr(rest)
      return `${family}: ${built ?? rest}`
    }
  }
  return ev
}

/** هل عندنا ترجمة دقيقة (لا عائلة ولا خام)؟ — للشاشات اللي بدها تعرض الخام جنب المعروف */
export const streamKnown = (ev: string): boolean => ev in EXACT

// ——— أحداث المراقبة (الرئيسية/المراقبة): معنى محدَّد + لون — بدل «صفقة / أمر» العامّة ———
const EVENT_COLOR: Array<[RegExp, string]> = [
  [/provider_down|feed_interrupted|halt|\.rejected|failed|violation|alert/i, 'red'],
  [/provider_recovered|feed_recovered|written|built|final_decision|realized/i, 'green'],
  [/skipped|unhealthy|stopped|requested/i, 'amber'],
]

/** (نصّ عربي محدَّد · لون) لحدث مراقبة — من نفس القاموس المشترك */
export function eventAr(name: string): [string, string] {
  const label = streamAr(name)
  for (const [re, c] of EVENT_COLOR) if (re.test(name)) return [label, c]
  return [label, 'grey']
}
