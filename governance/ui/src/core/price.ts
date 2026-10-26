// تنسيق الأسعار — ٢٠٢٦-٠٩-١٠ (ختم NQ).
//
// العطب المقيس بلقطة المالك: كل الأسعار كانت تُعرض **بخانتين ثابتتين**، فيرى
// `EURUSD 1.16` و`GBPUSD 1.35`، **وشراء وبيع ومرجع وتنفيذ كلّها تبدو متطابقة**
// بينما السبريد المعروض بجانبها `0.00001` — أي البيانات دقيقة والعرض يقصّها.
// وعلى الشارت ظهرت ثلاثة مستويات مختلفة كلّها `1.16`، فبدت خطوطًا على سعر واحد.
// حكم المالك: «وين أرقام عشرية؟ لا يورو».
//
// القاعدة هنا: **لا نقصّ ولا نخترع — نعرض ما وصل.**
// الدقّة تُشتقّ من القيمة نفسها (عدد خاناتها كما بثّتها النواة)، لا من جدول
// رموز مكتوب بيدنا ولا من تخمين بحدود الأسعار. فإن بثّت النواة `1.16240`
// عُرضت بخمس، وإن بثّت `77942.6` عُرضت بواحدة. وأيّ تغيّر في دقّة الوسيط
// يظهر وحده بلا لمس سطر.
//
// وحين يُعرض عمود من أسعار لرمز واحد (شراء · بيع · مرجع) نوحّد الدقّة على
// **أكبر** ما وُجد فيها، وإلّا اختلفت الخانات بين سطرين متجاورين لنفس الرمز.

/** عدد الخانات العشريّة في القيمة كما وصلت — بلا قصّ وبلا حشو. */
export function decimalsOf(v: unknown): number {
  if (typeof v !== 'number' || !Number.isFinite(v)) return 0
  // `toString` يعطي أقصر تمثيل دقيق للقيمة (1.1624 لا 1.16240000000000002)
  const s = Math.abs(v).toString()
  if (s.includes('e') || s.includes('E')) return 0      // تمثيل علميّ: لا خانات تُقرأ
  const dot = s.indexOf('.')
  return dot < 0 ? 0 : s.length - dot - 1
}

/** أكبر دقّة بين قيم لرمز واحد — لتوحيد عمود الأسعار. */
export function decimalsOfAll(...vs: unknown[]): number {
  let d = 0
  for (const v of vs) {
    const n = decimalsOf(v)
    if (n > d) d = n
  }
  return d
}

/**
 * سعر بالعربيّة بأرقام لاتينيّة (`ar-EG-u-nu-latn` — مواصفة اللوحات).
 * `digits`: الدقّة المطلوبة؛ إن غابت اشتُقّت من القيمة نفسها.
 * الغياب يُعلَن شرطةً — لا صفرًا ولا سعرًا مخترعًا.
 */
export function priceText(v: unknown, digits?: number): string {
  if (typeof v !== 'number' || !Number.isFinite(v)) return '—'
  const d = Math.min(8, digits ?? decimalsOf(v))
  return v.toLocaleString('ar-EG-u-nu-latn', {
    minimumFractionDigits: d,
    maximumFractionDigits: d,
  })
}

/** فرق سعريّ (سبريد/انحراف) — نفس القاعدة، وتُبقى دقّته كما وصلت. */
export function spreadText(v: unknown, digits?: number): string {
  return priceText(v, digits)
}
