// شريط الاستلام من فوق — عين المالك الوحيدة على القطع ووقت الوسيط.
// لا حساب: عمر آخر حدث وصل، و`timestamp_source` كما نشرته ٦١٨.
import { useEffect, useState } from 'react'
import { useStore, atomStale, atomPartial } from '../core/store'
import { BROKER_PLATFORM_AR } from '../core/arabic'

type Tone = 'green' | 'amber' | 'red' | 'dim'

function ageOf(flows: Record<string, number>, name: string, now: number): number {
  const t = flows[name]
  return t == null ? Infinity : (now - t) / 1000
}

function liveTone(conn: string, age: number): { tone: Tone; text: string } {
  if (conn !== 'live') return { tone: 'dim', text: 'لا نعرف' }
  if (age === Infinity) return { tone: 'red', text: 'صامت' }
  if (age < 5) return { tone: 'green', text: 'حيّ' }
  if (age < 30) return { tone: 'amber', text: `${Math.round(age)}ث` }
  return { tone: 'red', text: 'مقطوع' }
}

export default function FeedLeds() {
  const conn = useStore((s) => s.conn)
  const flows = useStore((s) => s.flows)
  const mt = useStore((s) => s.streams['feed.mt5.tick']) as
    | { timestamp_source?: string; clock_valid?: boolean; clock_domain?: string }
    | undefined
  const div = useStore((s) => s.streams['execution.reference_divergence.state']) as
    | { classification?: string; status?: string }
    | undefined
  const [now, setNow] = useState(() => performance.now())

  useEffect(() => {
    const id = window.setInterval(() => setNow(performance.now()), 1000)
    return () => window.clearInterval(id)
  }, [])

  // «بائت» = التدفّق واصل والبيانات قديمة — أخطر من «مقطوع»، لأنّ القطع يُرى
  // والبيات يتنكّر حياةً. المصدر يعرف عمر بياناته ويعلنه، والشارة تتبع حكمه.
  // 622 مصدر سي‑تريدر · 619 حالة حساب ميتاتريدر — لا 618: طوابع 618 بوقت
  // خادم الوسيط فلا تصلح مقياس عمر، بينما `updated_at` عند 619 يكتبه
  // الإكسبرت بـ`TimeGMT()`. التفصيل في `atomStale` بـ`core/store.ts`.
  const src622 = useStore((s) => s.atoms[622])
  const acct619 = useStore((s) => s.atoms[619])
  const market = useStore((s) => s.market)
  const STALE = { tone: 'red' as Tone, text: 'بائت' }
  const PARTIAL = { tone: 'amber' as Tone, text: 'جزئيّ' }
  // ثلاث حالات لا اثنتان: `degraded` عند 622 = رمز نائم خارج جلسته وقد سمّاه
  // (تنبيه جزئيّ)، و`unhealthy` = موت. التفصيل في `atomStale` بـ`core/store`.
  // وميتاتريدر جسر ملفّ: تدفّقه يكذب (طابور متراكم)، فحكمه عند 619 وحدها،
  // وحسابه واحد لا رموز — فبياتُه كامل لا جزئيّ.
  // ٢٠٢٦-٠٩-١٩ (صورة المالك، السبت ٠٠:٤٣ — ٠٣:٤٣ بتوقيت الخادم): الشريط
  // كلُّه أحمر «صامت · صامت · وقت مقطوع»، **والمنصّة سليمة تمامًا**: ستّة من
  // سبعة رموز خارج جلستها لأنّ السوق مسكّر، وبتكوين وحده ينبض.
  //
  // و٦٢٢ يقولها بنفسه، وفي كودها تعليقٌ صريح (`atom.py:572`):
  //   «A symbol outside its trading session is not a broken link.»
  // وتفرّق بين الحالتين بيدها: `FIX_TICK_DEAD_ALL` (unhealthy) انقطاعٌ
  // حقيقيّ، و`FIX_SYMBOLS_OUT_OF_SESSION` (degraded) نومٌ بموعده وتسمّي
  // النائمين. فالشارة كانت **تعلو على حكم ذرّتها**: تقرأ عمر التدفّق وحده
  // فتكتب «صامت» بالأحمر على نومٍ أعلنه صاحبُه.
  //
  // فتُقرأ الأسماء من رسالة الناشر لا من تقويمٍ نحسبه هنا: اللوحة لا تعرف
  // مواعيد الجلسات، والذرّة تعرفها. «السوق مسكّر» استنتاجٌ، و«ستّة رموز
  // خارج جلستها» خبرٌ — ونحن ننقل الخبر.
  const msg622 = src622?.health?.message ?? ''
  const outOfSession = /FIX_SYMBOLS_OUT_OF_SESSION:\s*([^\s]+)/.exec(msg622)?.[1]
    ?.split(',').map((s) => s.trim()).filter(Boolean) ?? []
  const deadAll = /FIX_TICK_DEAD_ALL:\s*([^\s]+)/.exec(msg622)?.[1]
    ?.split(',').map((s) => s.trim()).filter(Boolean) ?? []

  // ٢٠٢٦-٠٩-١٩، تصحيح المالك على الصورة نفسها: **«بتكوين شغال»**. وهو الفرق
  // كلُّه — «٦ خارج الجلسة» خبرُ نقصٍ يقرؤه التاجر توقّفًا، و«بتكوين شغّال»
  // خبرُ فرصةٍ قائمة. فالشارة تقول **مين صاحي** أوّلًا ثمّ كم نائمًا.
  //
  // والصاحي يُشتقّ من مصدرين حيَّين لا من تقويم: أسماءُ النائمين من ٦٢٢،
  // والرموز المعروفة من أسعار السوق الواصلة. والفرق بينهما هو الصاحي.
  const awake = Object.keys(market).filter((s) => !outOfSession.includes(s)).sort()

  const ctFlow = liveTone(conn, ageOf(flows, 'feed.ctrader.tick', now))
  const ct = atomStale(src622)
    ? STALE
    : outOfSession.length > 0
      // نومٌ مسمًّى: أصفر لا أحمر، ويتقدّم الصاحي — وحكمُ الذرّة يعلو حكمَ العمر.
      ? {
        tone: 'amber' as Tone,
        text: awake.length === 0
          ? `${outOfSession.length} خارج الجلسة`
          : awake.length <= 2
            ? `${awake.join(' · ')} شغّال`
            : `${awake.length} شغّال · ${outOfSession.length} نايم`,
      }
      : (atomPartial(src622) && ctFlow.tone === 'green' ? PARTIAL : ctFlow)
  const ctTitle = outOfSession.length > 0
    ? (awake.length ? `شغّال الآن: ${awake.join(' · ')}. ` : '')
      + `نايمين خارج جلستهم (مش معطّلين): ${outOfSession.join(' · ')}. `
      + 'الذرّة (٦٢٢) هي اللي بتعلنها، وهي اللي بتعرف مواعيد الجلسات — مو اللوحة.'
    : deadAll.length > 0
      ? `كل الرموز واقفة: ${deadAll.join(' · ')} — هاد انقطاع حقيقيّ بحكم الذرّة نفسها (٦٢٢).`
      : 'آخر تكة تحليل — صامت/مقطوع يعني ما في SendingTime داخل'
  const mt5 = (atomStale(acct619) || atomPartial(acct619))
    ? STALE
    : liveTone(conn, ageOf(flows, 'feed.mt5.tick', now))

  let timeTone: Tone = 'dim'
  let timeText = '—'
  let timeTitle = 'ما وصلت تكة تنفيذ بعد'
  if (conn !== 'live') {
    timeText = 'لا نعرف'
    timeTitle = 'النواة مقطوعة — لا قراءة لزمن التكة'
  } else if (mt5.tone === 'red') {
    timeTone = 'red'
    timeText = 'مقطوع'
    timeTitle = `ما في استلام من ${BROKER_PLATFORM_AR} — الزمن التشغيلي واقف`
  } else if (mt?.timestamp_source === 'received' || mt?.clock_valid === false) {
    timeTone = 'amber'
    timeText = 'استلام'
    timeTitle = 'طابع الوسيط مرفوض عند الباب — الزمن الداخلي من وصول الجهاز (UTC)'
  } else if (mt?.timestamp_source === 'broker' || mt?.clock_valid === true) {
    timeTone = 'green'
    timeText = 'UTC'
    timeTitle = 'طابع الوسيط صالح — الزمن الداخلي UTC من التكة'
  } else if (mt) {
    timeTone = 'green'
    timeText = 'وصل'
    timeTitle = 'تكة وصلت بلا حقل مصدر زمن'
  }

  let divTone: Tone = 'dim'
  let divText = '—'
  let divTitle = '٥٨٢ ما نشر بعد'
  const cls = div?.classification
  if (cls === 'STALE' || cls === 'CLOCK_INVALID' || cls === 'INSUFFICIENT_DATA') {
    divTone = cls === 'INSUFFICIENT_DATA' ? 'amber' : 'red'
    divText = cls === 'STALE' ? 'تقادم' : cls === 'CLOCK_INVALID' ? 'ساعة' : 'ناقص'
    divTitle = `٥٨٢ ${cls}`
  } else if (cls === 'SUSPICIOUS_DIVERGENCE') {
    divTone = 'amber'
    divText = 'ريبة'
    divTitle = '٥٨٢ مراقبة — نقلة كبيرة (لا إيقاف)'
  } else if (cls === 'EXPECTED_DIVERGENCE' || cls === 'LEVEL_OFFSET_ONLY' || cls === 'NORMAL') {
    divTone = 'green'
    divText = cls === 'NORMAL' ? 'مطابق' : cls === 'LEVEL_OFFSET_ONLY' ? 'إزاحة' : 'متوقع'
    divTitle = `٥٨٢ ${cls}`
  }

  const chip = (label: string, tone: Tone, text: string, title: string) => (
    <span className={`feedled ${tone}`} title={title}>
      <i className="feeddot" />
      <b>{label}</b>
      <em>{text}</em>
    </span>
  )

  return (
    <div className="feedleds" aria-label="استلام التغذية والزمن">
      {chip('سي‑تريدر', ct.tone, ct.text, ctTitle)}
      {chip(BROKER_PLATFORM_AR, mt5.tone, mt5.text,
        // صمتُ الوسيط وقت نوم الرموز ليس خبرًا جديدًا — يُقال سببُه المعلَن
        // بدل أن يُقرأ عطلًا ثانيًا مستقلًّا.
        mt5.tone === 'red' && outOfSession.length > 0
          ? `آخر تكة تنفيذ من الجسر — وما في تكّات لأنّ ${outOfSession.length} رموز خارج جلستها الآن (بحكم ٦٢٢).`
          : 'آخر تكة تنفيذ من الجسر')}
      {chip('وقت', timeTone, timeText,
        timeTone === 'red' && outOfSession.length > 0
          ? `${timeTitle} — والسبب المعلَن: ${outOfSession.length} رموز خارج جلستها، فما في تكّة تحمل الزمن.`
          : timeTitle)}
      {chip('انحراف', divTone, divText, divTitle)}
    </div>
  )
}
