// عدّادات النواة (٨٦٤) — عدّادات ناقل الأحداث الحقيقيّة لكل حدث.
//
// ٢٠٢٦-٠٩-٠٩ (ختم NQ): كانت الصفحة تقرأ `/gov/metrics` وحده، وهو لا يُخرج إلّا
// `lifecycle.start.success=1` لكل ذرّة — ٢٢٨ عدّادًا جامدًا منذ الإقلاع، تُعرض
// بطاقةً واحدة. ووصفها كان يعد بـ«كم حدث نُشر وسُلّم» ولا سبيل له إليها.
// والعدّادات الحقيقيّة موجودة بالنواة منذ ٢٠٢٦-٠٨-٣١ على `/api/bus-stats`،
// وهذه الصفحة توصلها الآن عبر `/gov/bus-stats` (تمرير قراءة محض).
// كل رقم هنا من الناقل نفسه — لا حساب بالواجهة ولا اشتقاق.
import { useEffect, useRef, useState } from 'react'
import { streamAr } from '../core/streams'
import { useStore } from '../core/store'

interface Lifecycle { counters: Record<string, number> }
type BusStats = Record<string, Record<string, number>>
// ٢٠٢٦-٠٩-١٠ (ختم NQ): حالة النقل من النواة — من يحمل ماذا. كانت موجودة
// بالنواة ولا طريق للوحة إليها، فيقرأ المالك «الناقل» بلا أن يعرف توزيعه.
interface TransportStats {
  payload_mode?: string
  published?: number
  shared_publishes?: number
  shared_deliveries?: number
  private_deliveries?: number
  runtime?: {
    worker_count?: number
    partitioned?: boolean
    cold_worker?: number
    ownership?: Record<string, number>
    // ٢٠٢٦-٠٩-١٠ (ختم NQ): `layout` و`workers` **داخل `runtime`** لا في الجذر
    // — بنيتُ أوّلًا على توقّعٍ ثمّ قِستُ الردّ فصحّحته.
    layout?: {
      worker_count?: number
      logical_partitions?: number
      worker_count_source?: string      // discovered | explicit — فرقٌ يُعرض
      keys_per_worker?: Record<string, number>
      keys?: Record<string, string[]>
      partition_states?: Record<string, string>
      migrating_to?: Record<string, unknown>
    }
    // عدّادات كل عامل — **هنا يقع الفقد الحقيقيّ**: `bus-stats` يقول
    // `dropped=0` لأنّه يقيس الناقل، والعامل يُسقط ويُدمج بعده.
    workers?: Array<{
      worker_id?: number
      queued?: number
      busy_handlers?: number
      processed?: number
      dropped?: number
      coalesced?: number
      failed?: number
      overload_state?: string
      last_error?: string
    }>
  }
}

const n = (v: number) => v.toLocaleString('ar-EG-u-nu-latn')

// المقاييس التي يُخرجها الناقل، بترتيب القراءة ومعناها بالعربي. ما يظهر منها
// غير معروف هنا يُعرض باسمه الخام — لا نُخفي مقياسًا لأنّنا لم نترجمه بعد.
const METRIC_AR: Record<string, string> = {
  published: 'نُشر',
  delivered: 'سُلّم',
  no_subscribers: 'بلا مشترك',
  dropped: 'أُسقط',
  timeout: 'مهلة',
  error: 'خطأ',
  coalesced: 'مُدمَج',
  replayed: 'أُعيد',
  overrun: 'تجاوز',
  pressure: 'ضغط',
  overrun_worst_s: 'أسوأ تجاوز (ث · تراكمي)',
}
// ٢٠٢٦-٠٩-٠٩ (ختم NQ) — تحذير مسؤول النواة، وهو في صلب «لا تكذب اللوحة»:
// `overrun_worst_s` **قيمة عظمى تراكميّة لا تنزل أبدًا**. بعد إصلاح ناجح للحجب
// تبقى كما هي، فمن يقرأها مقياسَ نجاح يظنّ أنّ الإصلاح فشل. الحكم على **فرق
// عدّاد `overrun`** بين عيّنتين متباعدتين، لا على القيمة العظمى. ويُكتب هذا على
// الصفحة صريحًا — لا يُترك لفطنة القارئ.
const CUMULATIVE_MAX = new Set(['overrun_worst_s'])
const ORDER = ['published', 'delivered', 'no_subscribers', 'dropped', 'timeout',
  'error', 'coalesced', 'replayed', 'overrun', 'pressure', 'overrun_worst_s']

// حالة انتقال الأقسام بين العمّال — تُعرض **فقط** إن كان هناك انتقال جارٍ.
// خلوّها هو الحالة الطبيعيّة، فلا تُعرض بطاقة فارغة تُقرأ عطبًا.
const PART_STATE_AR: Record<string, string> = {
  PINNED: 'مثبَّت', DRAINING: 'يُفرَّغ', HANDOVER: 'قيد التسليم',
}
function w_migrating(lay?: { partition_states?: Record<string, string>; migrating_to?: Record<string, unknown> }) {
  const states = Object.entries(lay?.partition_states ?? {})
  const moving = Object.entries(lay?.migrating_to ?? {})
  if (!states.length && !moving.length) return null
  return (
    <div className="ss dim" style={{ marginTop: 6 }}>
      {states.length ? (
        <div>حالة الأقسام: {states.map(([k, v]) => `${k.split('×').pop()} ${PART_STATE_AR[v] ?? v}`).join(' · ')}</div>
      ) : null}
      {moving.length ? (
        <div style={{ color: 'var(--amber)' }}>
          انتقال جارٍ: {moving.map(([k, v]) => `${k.split('×').pop()} → عامل ${String(v)}`).join(' · ')}
        </div>
      ) : null}
    </div>
  )
}

export default function Stats() {
  // صحّة البثّ الواصل لهذه اللوحة نفسها — مقروءة من ترويسة كل رسالة، لا من
  // منفذ. تكشف ما لا يكشفه `bus-stats`: ما فُقد **بين النواة وهذه الشاشة**.
  const streamSeq = useStore((s) => s.streamSeq)
  const streamMissed = useStore((s) => s.streamMissed)
  const streamDropped = useStore((s) => s.streamDropped)
  const streamGaps = useStore((s) => s.streamGaps)
  const clientDropped = useStore((s) => s.clientDropped)
  const [bus, setBus] = useState<BusStats | null>(null)
  const [life, setLife] = useState<Lifecycle | null>(null)
  const [tr, setTr] = useState<TransportStats | null>(null)
  // ٢٠٢٦-٠٩-١٠ (ختم NQ): عدّادات العمّال **تراكميّة من الإقلاع** — تكبر أبدًا،
  // فقراءتها وحدها تقول «الإسقاط يتفاقم» وهو ثابت المعدّل. الحكم على **الفرق
  // بين قراءتين** (درس `overrun_worst_s` نفسه). نحتفظ بالسابقة ونعرض معدّلًا.
  const prevRef = useRef<{ t: number; dropped: number; processed: number; coalesced: number; queued: number } | null>(null)
  const [rate, setRate] = useState<{
    dropped: number; processed: number; coalesced: number; pct: number
    // الحمل = (المعالَج + المُسقَط) ÷ المعالَج — أي الطلبُ على القدرة الفعليّة،
    // والدمج مستثنًى لأنّه سياسة لا فقد (تعريف مسؤول النواة، ورقة ١٨).
    // ⚠️ يُحسب هنا من عدّادَي النواة لا يُنسَخ رقمًا: رقمٌ منسوخ يبيت.
    loadPct: number
    queueGrowth: number              // نموّ الطابور بالثانية — المعيار الأوّل §١٨
  } | null>(null)
  const [err, setErr] = useState('')
  const [q, setQ] = useState('')

  useEffect(() => {
    const load = () => {
      // ٢٠٢٦-٠٩-٠٩ (ختم NQ): خادم الحوكمة يردّ على أيّ مسار مجهول بصفحة اللوحة
      // نفسها — `200` ونوعه `text/html`. فالفحص بـ`r.ok` وحده يمرّ على منفذ
      // غير موجود ثمّ ينكسر بخطأ تحليل غامض. نفحص النوع ونسمّي السبب بدقّة.
      fetch('/gov/bus-stats')
        .then((r) => {
          if (!r.ok) throw new Error(`الخادم ردّ ${r.status}`)
          const ct = r.headers.get('content-type') ?? ''
          if (!ct.includes('json')) {
            throw new Error('المنفذ /gov/bus-stats غير موجود على خادم الحوكمة — أُضيف بالمصدر ويحتاج إعادة تشغيل الحوكمة ليسري')
          }
          return r.json()
        })
        .then((d: BusStats) => { setBus(d); setErr('') })
        .catch((e: Error) => setErr(e.message))
      fetch('/gov/metrics').then((r) => r.json()).then(setLife).catch(() => { /* دورة الحياة ثانويّة */ })
      // حالة النقل — نفحص النوع لا الرمز (الخادم يردّ بصفحة اللوحة على مسار مجهول)
      fetch('/gov/transport-stats')
        .then((r) => (r.ok && (r.headers.get('content-type') ?? '').includes('json') ? r.json() : null))
        .then((d: TransportStats | null) => {
          setTr(d)
          const ws = d?.runtime?.workers
          if (!ws?.length) return
          const now = performance.now()
          const cur = {
            t: now,
            dropped: ws.reduce((s, w) => s + (w.dropped ?? 0), 0),
            processed: ws.reduce((s, w) => s + (w.processed ?? 0), 0),
            coalesced: ws.reduce((s, w) => s + (w.coalesced ?? 0), 0),
            queued: ws.reduce((s, w) => s + (w.queued ?? 0), 0),
          }
          const p = prevRef.current
          prevRef.current = cur
          // إقلاع جديد يصفّر العدّادات فتصير الفروق سالبة — لا نخترع معدّلًا منها
          if (!p || cur.t <= p.t || cur.dropped < p.dropped) return
          const secs = (cur.t - p.t) / 1000
          if (secs < 1) return
          const dd = (cur.dropped - p.dropped) / secs
          const dp = (cur.processed - p.processed) / secs
          const dc = (cur.coalesced - p.coalesced) / secs
          const tot = dd + dp + dc
          setRate({
            dropped: dd, processed: dp, coalesced: dc,
            pct: tot > 0 ? (100 * dd) / tot : 0,
            loadPct: dp > 0 ? (100 * (dp + dd)) / dp : 0,
            queueGrowth: (cur.queued - p.queued) / secs,
          })
        })
        .catch(() => setTr(null))
    }
    load()
    const t = setInterval(load, 4000)
    return () => clearInterval(t)
  }, [])

  // المقاييس الموجودة فعلًا بالردّ، بترتيبنا ثم أي مقياس جديد لم نكن نعرفه
  const metrics = bus
    ? [...ORDER.filter((m) => m in bus), ...Object.keys(bus).filter((m) => !ORDER.includes(m))]
    : []

  // اتّحاد أسماء الأحداث عبر كل المقاييس — حدث يظهر بمقياس واحد لا يضيع
  const events = new Set<string>()
  if (bus) for (const m of metrics) for (const ev of Object.keys(bus[m] ?? {})) events.add(ev)
  const rows = [...events]
    .map((ev) => ({ ev, ar: streamAr(ev), vals: metrics.map((m) => bus?.[m]?.[ev] ?? 0) }))
    .filter((r) => (q ? (r.ev.includes(q) || r.ar.includes(q)) : true))
    .sort((a, b) => (b.vals[0] ?? 0) - (a.vals[0] ?? 0))

  const totals = metrics.map((m) => Object.values(bus?.[m] ?? {}).reduce((s, v) => s + (Number(v) || 0), 0))
  // حدث يُنشر ولا مشترك له بالمرّة — يتيم على الناقل، وهذا أصدق ما تكشفه الصفحة
  const orphans = rows.filter((r) => {
    const pub = r.vals[metrics.indexOf('published')] ?? 0
    const none = r.vals[metrics.indexOf('no_subscribers')] ?? 0
    return pub > 0 && none >= pub
  })
  const bootOk = life ? Object.keys(life.counters ?? {}).length : null

  const th: React.CSSProperties = { padding: '4px 8px', textAlign: 'start', whiteSpace: 'nowrap', borderBottom: '1px solid var(--glassb)' }
  const td: React.CSSProperties = { padding: '3px 8px', whiteSpace: 'nowrap', borderBottom: '1px solid var(--glassb)' }

  return (
    <div className="section">
      <div className="ss dim" style={{ marginBottom: 10 }}>
        عدّادات ناقل النواة لكل حدث — كم نُشر وكم سُلّم وكم لم يجد مشتركًا وكم أُسقط.
        الأرقام تراكميّة من لحظة الإقلاع، وكلّها من الناقل نفسه بلا حساب هنا. هذه صحّة
        تشغيل، لا إحصاء سوق.
        <br />
        <b>«أسوأ تجاوز» قيمة عظمى مسجَّلة — لا تنزل أبدًا حتى بعد إصلاح ناجح.</b> للحكم
        على تحسّنٍ: راقب <b>«تجاوز»</b> هل يزيد بين قراءتين متباعدتين. وتجمّد الحلقة
        يُعرَف بأن أحداثًا لا علاقة بينها تحمل أرقام تجاوز متقاربة — وأصدقها إن كانت
        <b> نبضة الثانية</b> بينها: ساعة النظام لا تتأخّر إلّا إذا أُقفلت الحلقة كلّها.
      </div>

      {/* صحّة البثّ الواصل لهذه الشاشة — تُعرض دائمًا، حتى لو تعذّرت العدّادات،
          لأنّها لا تعتمد على أي منفذ بل على ترويسة الرسائل الواصلة فعلًا. */}
      <div className="cards" style={{ marginBottom: 12 }}>
        <div className="scard">
          <div className="st">رسائل البثّ لهذه الشاشة</div>
          <div className="sv num">{streamSeq === 0 ? '—' : n(streamSeq)}</div>
          <div className="ss dim" style={{ fontSize: 10 }}>{streamSeq === 0 ? 'ما وصلت رسالة بعد' : 'رقم آخر رسالة من النواة'}</div>
        </div>
        <div className="scard">
          <div className="st">فُقد قبل الوصول</div>
          <div className="sv num" style={{ color: streamMissed > 0 ? 'var(--red)' : undefined }}>{n(streamMissed)}</div>
          <div className="ss dim" style={{ fontSize: 10 }}>محسوب من قفزات الترقيم — يكشف الفقد ولو ضاع إعلانه</div>
        </div>
        <div className="scard">
          <div className="st">أعلنت النواة إسقاطه</div>
          <div className="sv num" style={{ color: streamDropped > 0 ? 'var(--amber)' : undefined }}>{n(streamDropped)}</div>
          <div className="ss dim" style={{ fontSize: 10 }}>امتلأ طابور البثّ ({n(streamGaps)} مرّة) فأُسقطت أقدم رسالة</div>
        </div>
        {/* ٢٠٢٦-٠٩-١٦ — العدّاد الرابع، وكان ناقصًا: ما تُسقطه **هذه الشاشة**.
            طابور اللوحة سقفه ٨٠٠ رسالة، وكان الفائض يُقصّ صامتًا. ويُفصل عن
            «أعلنت النواة إسقاطه» عمدًا: ذاك عطبٌ في النظام، وهذا عطبٌ في
            الشاشة — وخلطهما يرسل البحث إلى المكان الخطأ. */}
        <div className="scard">
          <div className="st">أسقطته هذه الشاشة</div>
          <div className="sv num" style={{ color: clientDropped > 0 ? 'var(--amber)' : undefined }}>{n(clientDropped)}</div>
          <div className="ss dim" style={{ fontSize: 10 }}>
            {clientDropped > 0
              ? 'امتلأ طابور اللوحة (٨٠٠) فقُصّ الأقدم — عطب عرضٍ لا عطب نواة'
              : 'طابور اللوحة لم يمتلئ — لا شيء قُصّ هنا'}
          </div>
        </div>
      </div>
      {streamMissed > 0 || streamDropped > 0 || clientDropped > 0 ? (
        <div className="scard" style={{ marginBottom: 12, borderColor: 'var(--red)' }}>
          <div className="st" style={{ fontWeight: 700, color: 'var(--red)' }}>البثّ ناقص — ما تراه ليس كل ما جرى</div>
          <div className="ss dim">
            النواة تُرقّم كل رسالة وتعلن حين يمتلئ طابورها فتُسقط أقدمها. الأرقام أعلاه
            من تلك الترويسة نفسها. هذا لا يعني عطلًا بالنواة — يعني أنّ لقطات هذه الشاشة
            تخطّت أحداثًا، فلا تُقرأ سلاسل الأحداث هنا على أنّها كاملة.
          </div>
        </div>
      ) : null}

      {/* ٢٠٢٦-٠٩-١٠ (ختم NQ) — النقل: من يحمل ماذا. رقمٌ كان بالنواة ولا يراه
          المالك. الأسماء تُعرض كما تصل من النواة (`حساب|رمز`) بلا تجميل. */}
      {tr?.runtime ? (
        <div className="scard" style={{ marginBottom: 12 }}>
          <div className="st" style={{ fontWeight: 700 }}>النقل — من يحمل ماذا</div>
          <div className="ss dim">
            العمّال <b className="num">{n(tr.runtime.worker_count ?? 0)}</b>
            {' · '}التقسيم <b>{tr.runtime.partitioned ? 'مُفعَّل' : 'مُعطَّل'}</b>
            {tr.runtime.cold_worker != null ? <>{' · '}العامل البارد <b className="num">{n(tr.runtime.cold_worker)}</b></> : null}
            {tr.payload_mode ? <>{' · '}نمط الحمولة <b>{tr.payload_mode === 'shared_readonly' ? 'مشتركة للقراءة' : tr.payload_mode}</b></> : null}
          </div>
          <div className="ss dim">
            نُشر <b className="num">{n(tr.published ?? 0)}</b>
            {' · '}تسليم مشترَك <b className="num">{n(tr.shared_deliveries ?? 0)}</b>
            {' · '}تسليم خاصّ <b className="num">{n(tr.private_deliveries ?? 0)}</b>
            {(tr.private_deliveries ?? 0) === 0 ? ' — لا نسخة لكل مشترك، وهذا المقصود' : ''}
          </div>
          {/* ٢٠٢٦-٠٩-١٠ (ختم NQ) — عدّادات العمّال: هنا يقع الفقد الحقيقيّ.
              `bus-stats` يقول `dropped=0` لأنّه يقيس الناقل، والعامل يُسقط
              ويُدمج **بعده** — فكان المالك يقرأ «صفر إسقاط» وعشرات الآلاف
              تسقط عند العمّال. الحمل يُعرض بحاله لا بلونٍ وحده. */}
          {tr.runtime.workers && tr.runtime.workers.length ? (() => {
            const ws = tr.runtime!.workers!
            const sum = (f: 'dropped' | 'coalesced' | 'processed' | 'queued') =>
              ws.reduce((s, w) => s + (w[f] ?? 0), 0)
            const over = ws.filter((w) => (w.overload_state ?? '').toUpperCase().includes('OVERLOAD')).length
            const lay = tr.runtime!.layout
            return (
              <div style={{ marginTop: 8, borderTop: '1px solid var(--line)', paddingTop: 8 }}>
                {/* ٢٠٢٦-٠٩-١٠ (ختم NQ) — `OVERLOAD` **حالة قائمة معلَّلة**، لا
                    إنذارًا ولا طمأنينة: الطلب يفوق القدرة فعلًا، فالحالة صادقة
                    وليست عطبًا مفاجئًا. والمعيار الأوّل ليس الحالة بل **الطابور:
                    هل ينمو؟** — `OVERLOAD` بطابور مستقرّ شيء، وبطابور ينمو شيء
                    آخر تمامًا. والحمل يُحسب هنا من عدّادَي النواة لا يُنسَخ رقمًا. */}
                <div className="ss" style={{ marginBottom: 6 }}>
                  <b>عمّال النقل</b>
                  {over > 0
                    ? <span style={{ color: 'var(--amber)' }}> — {n(over)} من {n(ws.length)} فوق الحمل</span>
                    : <span style={{ color: 'var(--green)' }}> — كلّهم تحت الحمل</span>}
                  {rate && rate.loadPct > 0 ? (
                    <span> · الحمل <b className="num" style={{ color: rate.loadPct >= 150 ? 'var(--red)' : rate.loadPct > 105 ? 'var(--amber)' : 'var(--green)' }}>
                      {Math.round(rate.loadPct)}%
                    </b> من القدرة</span>
                  ) : null}
                  {rate ? (
                    <span> · الطابور <b className="num" style={{ color: rate.queueGrowth > 5 ? 'var(--red)' : rate.queueGrowth < -5 ? 'var(--green)' : 'var(--amber)' }}>
                      {rate.queueGrowth > 0.5 ? `ينمو ${n(Math.round(rate.queueGrowth))}/ث`
                        : rate.queueGrowth < -0.5 ? `ينكمش ${n(Math.abs(Math.round(rate.queueGrowth)))}/ث`
                        : 'مستقرّ'}
                    </b></span>
                  ) : null}
                  {lay?.worker_count_source
                    ? <span className="dim"> · عدد العمّال {lay.worker_count_source === 'discovered' ? 'اشتقّه النظام' : 'فُرض يدويًّا'}</span>
                    : null}
                  {lay?.logical_partitions != null ? <span className="dim"> · أقسام منطقيّة {n(lay.logical_partitions)}</span> : null}
                </div>
                {over > 0 ? (
                  <div className="ss dim" style={{ marginBottom: 6, borderInlineStart: '2px solid var(--amber)', paddingInlineStart: 8 }}>
                    <b>«فوق الحمل» حالة قائمة لا عطب مفاجئ:</b> الطلب يفوق ما يُعالَج فعلًا، فالحالة صادقة.
                    والحلّ المعلَن هو المصنع المتوازي (ورقة ١٨-B) لا معايرة عتبة.
                    <b> والمعيار الأوّل هو الطابور لا الحالة</b> — إن كان مستقرًّا فالنظام يلحق، وإن كان ينمو فالتأخّر يتراكم.
                  </div>
                ) : null}
                {/* المعدّل أوّلًا — هو الحالة. والتراكميّ بعده مسمًّى بأنّه تراكميّ،
                    وإلّا قُرئ «الإسقاط يتفاقم» وهو ثابت المعدّل منذ الإقلاع. */}
                {rate ? (
                  <div className="ss" style={{ marginBottom: 6 }}>
                    <b>الآن، لكل ثانية:</b>{' '}
                    يُسقَط <b className="num" style={{ color: rate.dropped > 0 ? 'var(--red)' : 'var(--green)' }}>{n(Math.round(rate.dropped))}</b>
                    {' · '}يُدمَج <b className="num">{n(Math.round(rate.coalesced))}</b>
                    {' · '}يُعالَج <b className="num">{n(Math.round(rate.processed))}</b>
                    {' — '}<b style={{ color: rate.pct >= 10 ? 'var(--red)' : rate.pct > 0 ? 'var(--amber)' : 'var(--green)' }}>
                      {rate.pct.toFixed(1)}% ممّا يرد العمّال يُسقَط
                    </b>
                  </div>
                ) : (
                  <div className="ss dim" style={{ marginBottom: 6 }}>المعدّل يُحسب من قراءتين — ينتظر القراءة التالية…</div>
                )}
                <div className="ss dim" style={{ marginBottom: 6 }}>
                  <span className="dim">تراكميّ من الإقلاع:</span>{' '}
                  مُسقَط <b className="num" style={{ color: sum('dropped') > 0 ? 'var(--red)' : undefined }}>{n(sum('dropped'))}</b>
                  {' · '}مُدمَج <b className="num">{n(sum('coalesced'))}</b>
                  {' · '}معالَج <b className="num">{n(sum('processed'))}</b>
                  {' · '}بالطابور الآن <b className="num">{n(sum('queued'))}</b>
                  {sum('dropped') > 0 ? <div style={{ color: 'var(--red)' }}>المُسقَط فقدٌ فعليّ — لا يصل اللوحة ولا مشتركًا. والمُدمَج سياسة: آخر قيمة تكفي، فلا يُقرأ الرقمان سواءً.</div> : null}
                  {/* ٢٠٢٦-٠٩-١٠ (ختم NQ) — مُتحقَّق بالقياس لا بالافتراض: «معالَج»
                      عند العمّال يطابق «سُلّم» على الناقل بفرق ١٪٪ (235,713 مقابل
                      236,029 في ٤٥ ثانية)، فالثلاثة متنافية فعلًا والنسبة أعلاه
                      صحيحة. وأوّل فحصٍ صمّمتُه لهذا قارَن «سُلّم» بمجموع الثلاثة
                      فأوهمني أنّ نسبتي خاطئة — الخطأ كان في الفحص لا المقياس. */}
                  <div className="dim" style={{ fontSize: 10 }}>
                    «معالَج» هو ما يصل المشتركين فعلًا — مقيسٌ بمطابقته لعدّاد التسليم على الناقل.
                  </div>
                </div>
                <div style={{ overflowX: 'auto' }}>
                  <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 11.5 }}>
                    <thead><tr className="dim" style={{ fontSize: 10.5 }}>
                      <th style={th}>العامل</th><th style={{ ...th, textAlign: 'end' }}>الطابور</th>
                      <th style={{ ...th, textAlign: 'end' }}>معالَج</th><th style={{ ...th, textAlign: 'end' }}>أُسقط</th>
                      <th style={{ ...th, textAlign: 'end' }}>مُدمَج</th><th style={{ ...th, textAlign: 'end' }}>فشل</th>
                      <th style={th}>الحمل</th><th style={th}>يحمل</th>
                    </tr></thead>
                    <tbody>
                      {ws.map((w) => {
                        const id = String(w.worker_id ?? '')
                        const keys = lay?.keys?.[id] ?? []
                        const hot = (w.overload_state ?? '').toUpperCase().includes('OVERLOAD')
                        return (
                          <tr key={id}>
                            <td style={td} className="num">{id}</td>
                            <td style={{ ...td, textAlign: 'end' }} className="num">{n(w.queued ?? 0)}</td>
                            <td style={{ ...td, textAlign: 'end' }} className="num">{n(w.processed ?? 0)}</td>
                            <td style={{ ...td, textAlign: 'end', color: (w.dropped ?? 0) > 0 ? 'var(--red)' : 'var(--dim)' }} className="num">{n(w.dropped ?? 0)}</td>
                            <td style={{ ...td, textAlign: 'end' }} className="num">{n(w.coalesced ?? 0)}</td>
                            <td style={{ ...td, textAlign: 'end', color: (w.failed ?? 0) > 0 ? 'var(--red)' : 'var(--dim)' }} className="num">{n(w.failed ?? 0)}</td>
                            <td style={{ ...td, color: hot ? 'var(--red)' : 'var(--green)' }}>{hot ? 'فوق الحمل' : (w.overload_state || 'طبيعي')}</td>
                            {/* الفاصل: `|` بعد إصلاح المصدر (٢٠٢٦-٠٩-١٠) و`×`
                                قبله. نشقّ على كليهما ولا **ننظّف** المفتاح —
                                تنظيفٌ فوق مصدر مصحَّح يخفي عودة العطب. والمفتاح
                                الكامل بتلميح الفأرة كما يصل، بلا تجميل. */}
                            <td style={td} className="dim" title={keys.join(' · ')}>
                              {keys.length ? keys.map((k) => k.split(/[|×]/).pop()).join(' · ') : '—'}
                            </td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </div>
                {w_migrating(lay)}
              </div>
            )
          })() : null}

          {tr.runtime.ownership && Object.keys(tr.runtime.ownership).length ? (
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginTop: 6 }}>
              {Object.entries(tr.runtime.ownership)
                .sort((a, b) => (a[1] ?? 0) - (b[1] ?? 0))
                .map(([scope, worker]) => (
                  <span key={scope} title={scope} style={{ fontSize: 10.5, padding: '1px 6px', borderRadius: 6, border: '1px solid var(--glassb)' }}>
                    {scope.split(/[|×]/).join(' · ')}
                    <b className="num" style={{ marginInlineStart: 4 }}>عامل {n(worker)}</b>
                  </span>
                ))}
            </div>
          ) : null}
        </div>
      ) : null}

      {/* ٢٠٢٦-٠٩-١٠ (ختم NQ) — بطاقة بمكانها فارغة، وسببها مكتوب.
          زمن التِكّة ← القرار **أهمّ رقم في النظام**: المقيس بأداة النواة
          `p50 = 1,150` مللي و`p95 = 16,173` مقابل عتبة المالك ثانيتين — أي
          الشريحة الأبطأ تتجاوز العتبة ثمانية أضعاف. ولا منفذ يُخرجه: القياس
          يحتاج تجميع الأثر **داخل** النواة وهي مختومة (يلزم ختم `NQ`).
          وكان بإمكاني حسابه من الأحداث الواصلة لهذه الشاشة — **ورفضتُ**:
          القناة تُسقط ٢٠٪ وتدمج ٥٠٪، فمئينٌ من عيّنة كهذه رقمٌ كاذب بثوب
          مقيس. لوحةٌ تقول «لا أعرف» أصدق من لوحة تخمّن. */}
      <div className="scard" style={{ marginBottom: 12, borderStyle: 'dashed' }}>
        <div className="st" style={{ fontWeight: 700 }}>زمن التِكّة ← القرار — لا تقيسه هذه اللوحة</div>
        <div className="sv dim">—</div>
        <div className="ss dim">
          آخر ما قِيس بأداة النواة: <b className="num">p50 = 1,150</b> مللي · <b className="num">p95 = 16,173</b> مللي
          — <b>والعتبة ثانيتان</b>، أي الشريحة الأبطأ تتجاوزها نحو ثمانية أضعاف. رقمٌ من قياس
          سابق، لا قراءة حيّة — ولذلك يُكتب هكذا ولا يوضع في خانة رقم.
          <div style={{ marginTop: 4 }}>
            <b>ولماذا لا تقيسه هذه اللوحة — مقيسًا لا مفترضًا:</b> حمولات القرار
            <b> لا تحمل طابع المصدر</b> أصلًا (٤٬٧٤٩ حمولة فُحصت: صفر منها فيه
            <span dir="ltr"> source_timestamp</span>)، و<span dir="ltr">decisions.db</span> لا يحفظه،
            ووصولُ أحداث القرار إلى هذه الشاشة <b>١١٪</b> فقط. فأيّ مئين يُحسب هنا
            يكون رقمًا مخترعًا بثوب مقيس.
          </div>
          <div style={{ marginTop: 4 }}>
            يُقاس بربط سلسلة الأثر كاملةً عند مصدرها — لا من هذه النظّارة. وهذه البطاقة
            موضوعة فارغةً بقصد: <b>أن تعرف أنّك لا تعرف أصدق من أن تُطمأن برقم مخترع.</b>
          </div>
        </div>
      </div>

      {err ? <div className="scard"><div className="st">تعذّرت القراءة</div><div className="ss red">{err} — عدّادات الناقل ما وصلت. لا رقم يُعرض مكانها.</div></div> : null}
      {!bus && !err ? <div className="scard"><div className="st">جارِ التحميل…</div><div className="sv">—</div></div> : null}

      {bus ? (
        <>
          <div className="cards" style={{ marginBottom: 12 }}>
            {metrics.map((m, i) => (
              <div className="scard" key={m}>
                <div className="st">{METRIC_AR[m] ?? m}</div>
                {/* القيمة العظمى لا تُجمع — جمعها يخترع رقمًا بلا معنى */}
                <div className="sv num">{CUMULATIVE_MAX.has(m) ? n(Math.max(0, ...Object.values(bus[m] ?? {}).map(Number))) : n(totals[i])}</div>
                {CUMULATIVE_MAX.has(m) ? <div className="ss dim" style={{ fontSize: 10 }}>أعلى قيمة سُجّلت — لا تنزل بعد الإصلاح</div> : null}
              </div>
            ))}
            <div className="scard">
              <div className="st">أحداث على الناقل</div>
              <div className="sv num">{n(events.size)}</div>
            </div>
            <div className="scard">
              <div className="st">ذرّات أقلعت</div>
              <div className="sv num">{bootOk == null ? '—' : n(bootOk)}</div>
            </div>
          </div>

          {orphans.length ? (
            <div className="scard" style={{ marginBottom: 12 }}>
              <div className="st" style={{ fontWeight: 700 }}>أحداث تُنشر ولا مشترك لها — {n(orphans.length)}</div>
              <div className="ss dim">
                يُنشر ولا يستمع له أحد داخل النواة. ليس عطلًا بذاته (اللوحة تقرأ من البثّ لا من الاشتراك)،
                لكنّه المكان الذي تُفقد فيه الوصلات فعلًا — فيُعلَن بالاسم لا يُخفى.
              </div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginTop: 6 }}>
                {orphans.slice(0, 40).map((r) => (
                  <span key={r.ev} title={r.ev} style={{ fontSize: 10.5, padding: '1px 6px', borderRadius: 6, border: '1px solid var(--amber)', color: 'var(--amber)' }}>
                    {r.ar} <b className="num">{n(r.vals[metrics.indexOf('published')] ?? 0)}</b>
                  </span>
                ))}
              </div>
            </div>
          ) : null}

          <input
            value={q} onChange={(e) => setQ(e.target.value)} placeholder="فلترة بالاسم العربي أو الخام…"
            style={{ marginBottom: 8, padding: '5px 10px', width: '100%', maxWidth: 360, background: 'var(--glass)', border: '1px solid var(--glassb)', borderRadius: 8, color: 'var(--ink)' }}
          />
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
              <thead>
                <tr className="dim" style={{ fontSize: 10.5 }}>
                  <th style={th}>الحدث</th>
                  {metrics.map((m) => <th key={m} style={{ ...th, textAlign: 'end' }}>{METRIC_AR[m] ?? m}</th>)}
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.ev}>
                    <td style={td} title={r.ev}>{r.ar}</td>
                    {r.vals.map((v, i) => (
                      <td key={metrics[i]} className="num" style={{ ...td, textAlign: 'end', color: v === 0 ? 'var(--dim)' : undefined }}>{n(v)}</td>
                    ))}
                  </tr>
                ))}
                {rows.length === 0 ? <tr><td style={td} colSpan={metrics.length + 1} className="dim">ما في حدث يطابق الفلترة.</td></tr> : null}
              </tbody>
            </table>
          </div>
        </>
      ) : null}
    </div>
  )
}
