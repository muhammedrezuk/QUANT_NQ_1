// إقفال القسم 150 · مرحلة ٥ (٢٠٢٦-٠٨-٢٣): الإنذار المبكّر — الأحداث الثلاثة العمياء.
// «مشاكل لوحة.md»: ثلاثة أحداث تصل الوصلة ولا تجد سطرًا يعرضها — وهي التي تخبر
// المالك أنّ الجهاز أو الساعة أو الناقل بدأ يتعثّر. الآن لها شريط فوق كل شي.
// ⛔ لا حساب: يُعرض ما وصل فقط؛ من لم يصل قطّ = «لم يصل بعد».
import { useStore } from '../core/store'
import { arabicHealth } from '../core/arabic'

// ٢٠٢٦-٠٩-١٦ (المالك: «٧٥٣ زرّة إلك هيّي») — البطاقة كانت تقول «لم يصل بعد»
// والذرّة سليمةٌ تنشر. والسبب أنّ هذه الأحداث **دوريّة بطيئة**: ٧٥٣ يشترك في
// `SYS_5MIN`، فمن يفتح اللوحة ينتظر خمس دقائق قبل أن يرى شيئًا — وفي تلك
// المدّة يقرأ «لم يصل» فيظنّها معطّلة.
//
// وهي **نفس علّة «حاكم التغيير»**: حدثٌ لا يُعاد بثّه، ومصدرٌ ثانٍ باقٍ
// موجود. فتُقرأ رسالة صحّة الذرّة ريثما يصل الحدث — ويُسمّى المصدر في تلميح
// الفأرة، فلا يُظنّ البديل أصلًا.
//
// وأوّل قراءة أعطت `cpu=61.1 mem=94.0` — **الذاكرة ٩٤٪**، رقمٌ كان مخفيًّا
// خلف «لم يصل بعد».
interface ChipSpec { event: string; ar: string; atom?: number }
const CHIPS: ChipSpec[] = [
  { event: 'tools.device_resources.state', ar: 'موارد الجهاز', atom: 753 },
  { event: 'telemetry.carrier.state', ar: 'ناقل التلمترية', atom: 810 },
  { event: 'time.clock.quality.state', ar: 'جودة الساعة', atom: 806 },
]

type MaybeRec = Record<string, unknown>

// ٢٠٢٦-٠٩-١٦ (المالك: «٧٥٣ زرّة إلك هيّي») — كانت الشارة تقول «وصل» أو تسرّب
// `HEALTHY` خامًا. و«وصل» لا تقول شيئًا: المالك يريد أن يعرف **كم**. والحمولة
// تحمل الأرقام فعلًا (`cpu_pct: 71` · `memory_pct: 94`) وكانت مهدورة.
//
// فصار لكل شارة نصّها من حقولها هي، بالعربيّة وبالأرقام. وأوّل قراءة:
// **الذاكرة ٩٤٪** — رقمٌ يستحقّ لونًا لا كلمة «وصل».
const pct1 = (v: unknown) =>
  typeof v === 'number' ? `${v.toLocaleString('ar-EG-u-nu-latn', { maximumFractionDigits: 0 })}٪` : null

function pickStatus(event: string, p: MaybeRec | undefined): string {
  if (!p) return ''
  if (event === 'tools.device_resources.state') {
    const cpu = pct1(p.cpu_pct)
    const mem = pct1(p.memory_pct)
    if (cpu || mem) return [cpu ? `المعالج ${cpu}` : '', mem ? `الذاكرة ${mem}` : ''].filter(Boolean).join(' · ')
  }
  if (event === 'telemetry.carrier.state' && typeof p.rows_seen === 'number') {
    const dropped = typeof p.dropped === 'number' ? p.dropped : 0
    return dropped > 0 ? `أُسقط ${dropped}` : 'يمرّر بلا فقد'
  }
  if (event === 'time.clock.quality.state') {
    const q = typeof p.quality === 'string' ? p.quality : ''
    const off = typeof p.offset_s === 'number' ? Math.abs(p.offset_s) : null
    const qAr = q === 'GOOD' ? 'سليمة' : q === 'DEGRADED' ? 'متعثّرة' : q === 'BAD' ? 'سيّئة' : q ? arabicHealth(q) : ''
    return [qAr, off != null ? `فرق ${off.toFixed(2)} ث` : ''].filter(Boolean).join(' · ') || 'وصلت'
  }
  for (const key of ['status', 'state', 'quality', 'health']) {
    const v = p[key]
    if (typeof v === 'string' && v) return arabicHealth(v)
  }
  return 'وصلت'
}

/** لون شارة الموارد من الرقم نفسه — لا من كلمة «سليم» التي تقولها الذرّة. */
function resourceColor(p: MaybeRec | undefined): string | null {
  const mem = typeof p?.memory_pct === 'number' ? p.memory_pct : null
  const cpu = typeof p?.cpu_pct === 'number' ? p.cpu_pct : null
  const worst = Math.max(mem ?? 0, cpu ?? 0)
  if (mem == null && cpu == null) return null
  return worst >= 90 ? 'var(--red)' : worst >= 75 ? 'var(--amber)' : 'var(--green)'
}

function statusColor(s: string): string {
  const u = s.toUpperCase()
  if (u.includes('OK') || u.includes('READY') || u.includes('GOOD') || u.includes('HEALTHY') || s === 'وصل') return 'var(--green)'
  if (u.includes('STALE') || u.includes('DEGRADED') || u.includes('WARN')) return 'var(--amber)'
  if (u.includes('FAIL') || u.includes('ERROR') || u.includes('BAD')) return 'var(--red)'
  return 'var(--dim)'
}

export function EarlyWarningStrip() {
  const streams = useStore((s) => s.streams)
  const flows = useStore((s) => s.flows)
  const atoms = useStore((s) => s.atoms)
  return (
    <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 6 }}>
      {CHIPS.map(({ event, ar, atom }) => {
        const payload = streams[event] as MaybeRec | undefined
        const arrived = flows[event] != null
        const rec = atom != null ? atoms[atom] : undefined
        const fallback = !arrived && rec?.health?.message ? arabicHealth(rec.health.message) : ''
        const status = arrived ? pickStatus(event, payload) : (fallback || 'لم يصل بعد')
        const color = arrived
          ? (resourceColor(payload) ?? statusColor(status))
          : fallback
            ? (rec?.health?.state === 'healthy' ? 'var(--green)'
              : rec?.health?.state === 'degraded' ? 'var(--amber)' : 'var(--red)')
            : 'var(--dim)'
        return (
          <span key={event}
            title={arrived ? event
              : fallback ? `${event} — لم يصل الحدث بعد (دوريّ)؛ هذا من رسالة صحّة الذرّة ${atom}`
                : event}
            style={{ display: 'inline-flex', gap: 6, alignItems: 'center', fontSize: 11.5,
                     padding: '2px 9px', border: `1px ${arrived ? 'solid' : 'dashed'} var(--line)`,
                     borderRadius: 99, color: 'var(--ink)' }}>
            <span style={{ width: 7, height: 7, borderRadius: 99, background: color, flex: 'none' }} />
            <span>{ar}</span>
            <span className="num" style={{ color, fontSize: 11 }}>{status}</span>
          </span>
        )
      })}
    </div>
  )
}
