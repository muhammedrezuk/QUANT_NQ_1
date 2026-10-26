// رحلة البطاقة — تُعرض داخل «التنفيذ» لا في تبويب جديد.
// حكم المالك ٢٠٢٦-٠٩-١٨: «صارت مو لوحات، صارت كم حال من تكرار… خفّف» — و٣٢ تبويبًا
// تُقرأ حائطًا لا قائمة. فمكانُها حيث الموضوع نفسه: مسار قرار→أمر→جسر→تعبئة.
//
// المصدر `/gov/card/journey` — قراءةٌ فقط من `decisions.db` (٧٠٧) و`trade_cards.db`
// (دفتر ٤٦٥ وجدول `card_writes`). لا رقم محسوبٌ هنا: الخادم يقيس والواجهة تعرض.
//
// ⚠️ المفتاح `request_id` بصيغة `555-<بصمة>` يختمه ٥٥٥ نفسه. الربطُ بـ`decision_id`
// يعطي **صفر** رحلةٍ كاملة — وهو عيبُ ربطٍ لا غيابُ رحلات.
// ⚠️ وكلّ أزمنة هذه اللوحة بساعة المنصّة (`recorded_at`). `opened_at` في مخزن
// الصفقات بساعة الوسيط وتسبقها ثلاث ساعات — لا يُطرح أحدهما من الآخر.
import { useEffect, useState } from 'react'

const num = (n?: number | null, dp = 0) =>
  n == null ? '—' : n.toLocaleString('ar-EG-u-nu-latn', { maximumFractionDigits: dp, minimumFractionDigits: dp })

const clock = (ts: number) =>
  new Date(ts * 1000).toLocaleTimeString('ar-EG-u-nu-latn', { hour12: false })

interface FunnelRow { stage: string; label: string; what: string; event?: string; n: number; pct: number }
interface HopRow { from: string; to: string; median: number; min: number; max: number; n: number }
interface TripStep { stage: string; at: number; offset: number; reason: string }
interface WriteRow { author: string; field: string; value_json: string; first_at: number; hits: number }
interface Journey {
  available: boolean
  days: number
  requests?: number
  funnel?: FunnelRow[]
  hops?: HopRow[]
  last_trip?: { request_id: string; symbol: string; span: number; steps: TripStep[] }
  cards_available?: boolean
  cards_total?: number
  card_states?: { state: string; n: number }[]
  card_authors?: { author: string; writes: number; cards: number }[]
  card?: Record<string, string | number | null>
  card_filled?: number
  card_columns?: number
  card_writes?: WriteRow[]
}

// محطّتان تعنيان «مات هنا» — تُصبغان بالأحمر فلا يُقرأ الرقم إنجازًا
const DEAD = new Set(['ORDER_REJECTED', 'BRIDGE_WRITE_FAILED'])

// ⚠️ قاعدة المالك: **لا إنكليزي على اللوحة** — والخام في تلميح الفأرة وحده.
// حكمه ٢٠٢٦-٠٩-١٩: «ق انكليزي ندق لا مترجم». وحارس `check_arabic_ui.py` ما
// اشتعل لأنّه يفحص `Settings.tsx` وحده — فالحارس ما كان حارسًا للوحة كلّها.
const FIELD_AR: Record<string, string> = {
  state: 'الحالة', signal: 'الإشارة', quality: 'جودة السوق',
  direction: 'الاتّجاه', strength: 'قوّة الإشارة', score: 'النقاط',
  blocked_by: 'مين حجب', side: 'الجهة', verdict: 'الحكم', margin: 'الهامش',
  reason: 'السبب', approved: 'موافَق', decision_id: 'رقم القرار',
  stop: 'الوقف', target: 'الهدف', rr: 'ربح إلى مخاطرة', scale: 'المقياس',
  setup_rejected: 'الإعداد مرفوض', side_conflict: 'تعارض الجهة',
  side_changed: 'الجهة تبدّلت', reversal_called: 'انعكاس مُعلَن',
  stop_widened: 'الوقف اتوسّع', volume: 'الحجم',
  sent_stop: 'الوقف المبعوت', sent_target: 'الهدف المبعوت',
  rr_at_send: 'ربح/مخاطرة وقت الإرسال', rr_rule: 'قاعدة الحساب',
  risk_amount: 'مبلغ المخاطرة', symbol_budget: 'ميزانيّة الرمز',
  budget_left: 'الباقي من الميزانيّة', verdict_552: 'حكم البوّابة',
  ticket: 'رقم التذكرة', fill_price: 'سعر التعبئة', exit_price: 'سعر الخروج',
  entry_slip: 'انزلاق الدخول', outcome: 'النتيجة', profit: 'الربح',
  entry: 'الدخول', opened_at: 'ساعة الفتح', closed_at: 'ساعة الإغلاق',
}

// قيمٌ يكتبها الناشرون بالإنكليزيّة — تُعرض عربيّةً والخام في التلميح.
// ⚠️ **القاموس مبنيّ على مسحٍ كامل للقاعدة لا على ما وقعت عليه عيني**: ٧٩ قيمةً
// فيها لاتينيّة في `card_writes` (استعلام `SELECT field, value_json`)، وكلّها
// مغطّاة هنا أو بقواعد التركيب تحت. مقيس ٢٠٢٦-٠٩-١٩.
const VALUE_AR: Record<string, string> = {
  // حالات البطاقة
  NOT_READY: 'مش جاهزة', READY: 'جاهزة', OPEN: 'مفتوحة', CLOSED: 'مسكّرة',
  DISPATCHED: 'انبعتت', EXPIRED: 'راحت عليها', REJECTED: 'مرفوضة',
  FILLED: 'تعبّت',
  // النتيجة والجهة
  WIN: 'ربح', LOSS: 'خسارة', buy: 'شراء', sell: 'بيع', wait: 'استنّى',
  BUY: 'شراء', SELL: 'بيع',
  // الأحكام
  pass: 'مرق', block: 'محجوب', allow: 'مسموح', reject: 'مرفوض',
  // ذيول الأحكام المركّبة (pass:clean · block:low_confidence …)
  clean: 'نظيف', sideways: 'سوق عرضيّ', trending: 'سوق مُتّجه',
  high_confidence: 'ثقة عالية', low_confidence: 'ثقة واطية',
  // جودة السوق والإشارة
  normal: 'عاديّة', good: 'منيحة', poor: 'ضعيفة', invalid: 'مش صالحة',
  // منطق
  true: 'نعم', false: 'لا', null: 'ما انكتب', none: 'ولا شي',
  // الحاجبون (`blocked_by` من ٤٥٤)
  signal_wait: 'الإشارة مستنّية', confidence_filter: 'فلتر الثقة',
  position_filter: 'فلتر المركز', timing_filter: 'فلتر التوقيت',
  freshness_filter: 'فلتر الطزاجة', asset_filter: 'فلتر الأصل',
  conditions_filter: 'فلتر الظروف',
  // أسباب مكتوبة
  BLOCKED_UPSTREAM: 'محجوب من فوق', NO_ELIGIBLE_SIDE: 'ما في جهة مؤهّلة',
  ELIGIBLE_SIDE_BUY: 'الجهة المؤهّلة شراء',
  ELIGIBLE_SIDE_SELL: 'الجهة المؤهّلة بيع',
  STOP_BELOW_FLOOR: 'الوقف تحت الأرضيّة', SL: 'ضرب الوقف', TP: 'ضرب الهدف',
}

const word = (w: string): string =>
  VALUE_AR[w] ?? (/[A-Za-z]/.test(w) ? '' : w)

/**
 * يعرض القيمة عربيّةً قدر الإمكان، وما بقي إنكليزيًّا يبقى في التلميح وحده.
 * ويفكّ ثلاث تركيبات حقيقيّة في القاعدة: `حكم:ذيل` · `جهة←جهة` · `رقم:بقيّة`
 * · وقائمة `['a', 'b']`.
 */
const valueAr = (raw: unknown): string => {
  const text = String(raw ?? '').trim().replace(/^"|"$/g, '')
  if (!text || text === 'null') return VALUE_AR.null
  if (VALUE_AR[text]) return VALUE_AR[text]
  if (/^-?[\d.,]+$/.test(text)) {
    return Number(text.replace(/,/g, '')).toLocaleString('ar-EG-u-nu-latn', { maximumFractionDigits: 5 })
  }
  // قائمة الحاجبين: ['signal_wait', 'confidence_filter']
  if (text.startsWith('[')) {
    const parts = text.replace(/[[\]'"]/g, '').split(',').map((s) => s.trim()).filter(Boolean)
    const named = parts.map(word).filter(Boolean)
    return named.length ? named.join(' · ') : 'تفصيل تقنيّ'
  }
  // «٤٠٦:buy←sell» أو «buy←sell @-100.0» — الرقم والسهم يبقيان، والكلمات تُترجم
  if (/[←|:]/.test(text)) {
    const out = text.replace(/[A-Za-z_]+/g, (m) => word(m) || m)
    if (!/[A-Za-z]/.test(out)) return out
    // حكمٌ مركّب `حكم:ذيل` لم يُغطَّ بالكامل
    const head = text.split(':')[0]
    if (VALUE_AR[head]) {
      const tail = word(text.slice(head.length + 1))
      return tail ? `${VALUE_AR[head]} — ${tail}` : VALUE_AR[head]
    }
  }
  return /[A-Za-z]/.test(text) ? 'تفصيل تقنيّ' : text
}

const fieldAr = (key: string): string => FIELD_AR[key] ?? 'حقل تقنيّ'

// وصفُ كلّ محطّة — **بالواجهة لا بالخادم**: الخادم ما بينحمّل حيًّا، فلو كانت
// الكلمات عنده لَاحتاج المالك إقلاعًا تانيًا لأجل صياغة. والبناء وحده بيحييها.
// والاسم الخام للحدث بيضلّ بتلميح الفأرة (`event` من الخادم).
const STAGE_WHAT: Record<string, string> = {
  ORDER_REQUESTED: 'بيطلب يفتح مركز',
  ORDER_BUILT: 'بيركّب الأمر بسعره وحجمه',
  ORDER_REJECTED: 'شرعيّة الوقف أو تدقيق الأمر ردّته',
  DECISION_FINALIZED: 'مرّره — صار قرارًا نهائيًّا',
  QUEUED_TO_BRIDGE: 'انكتب بقاعدة الجسر',
  BRIDGE_WRITE_FAILED: 'ما وصل القاعدة',
  BROKER_ACKNOWLEDGED: 'الوسيط أقرّ الأمر',
  FILLED_OPEN: 'امتلأ وفتح المركز',
  FILLED_PARTIAL: 'امتلأ جزءٌ منه',
  FILLED_CLOSED: 'سكّر المركز',
}

/** الوصف من الواجهة أوّلًا؛ وما جا من الخادم ما بينعرض إذا فيه إنكليزي. */
const whatAr = (stage: string, fromServer?: string): string =>
  STAGE_WHAT[stage] ?? (fromServer && !/[A-Za-z]/.test(fromServer) ? fromServer : '')

export default function CardJourney() {
  const [data, setData] = useState<Journey | null>(null)
  const [open, setOpen] = useState(false)
  const [err, setErr] = useState('')

  useEffect(() => {
    let alive = true
    const load = () => {
      fetch('/gov/card/journey?days=3', { cache: 'no-store' })
        .then((r) => r.json())
        .then((d: Journey) => { if (alive) { setData(d); setErr('') } })
        .catch(() => { if (alive) setErr('ما وصل الردّ — الخادم بحاجة إعادة تشغيل ليعرف المنفذ') })
    }
    load()
    const t = window.setInterval(load, 60000)
    return () => { alive = false; window.clearInterval(t) }
  }, [])

  if (err) return <div className="scard"><div className="st">رحلة البطاقة</div><div className="ss dim">{err}</div></div>
  if (!data) return <div className="scard"><div className="st">رحلة البطاقة</div><div className="ss dim">عم يقرأ…</div></div>
  if (!data.available) {
    return (
      <div className="scard">
        <div className="st">رحلة البطاقة</div>
        <div className="ss dim">ما في مخزن قرارات يُقرأ منه بعد.</div>
      </div>
    )
  }

  const funnel = data.funnel ?? []
  const finalized = funnel.find((f) => f.stage === 'DECISION_FINALIZED')?.n ?? 0
  const bridgeBad = funnel.find((f) => f.stage === 'BRIDGE_WRITE_FAILED')?.n ?? 0
  const opened = funnel.find((f) => f.stage === 'FILLED_OPEN')?.n ?? 0
  const closed = funnel.find((f) => f.stage === 'FILLED_CLOSED')?.n ?? 0
  const label = (stage: string) => funnel.find((f) => f.stage === stage)?.label ?? stage

  return (
    <div className="scard" style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      <div>
        <div className="st">رحلة البطاقة — من بنائها عند ٤٦٥ إلى ٥٥٥ إلى الجسر إلى المخازن</div>
        <div className="ss dim">
          مقيسٌ على {num(data.requests)} طلبًا ختمه ٥٥٥ خلال {num(data.days)} أيّام.
          كلّ رقم مقروءٌ من السجلّ الحيّ — لا شي محسوب بالشاشة.
        </div>
      </div>

      {/* القُمع */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
        {funnel.map((f) => {
          const dead = DEAD.has(f.stage)
          const empty = f.n === 0
          return (
            <div key={f.stage} style={{
              display: 'grid', gridTemplateColumns: 'minmax(90px,150px) minmax(0,1fr) 92px',
              gap: 10, alignItems: 'center', fontSize: 12.5,
              opacity: empty ? 0.55 : 1,
            }}>
              <div style={{ fontWeight: 600 }}>{f.label}</div>
              <div>
                {/* الوصف عربيّ، واسم الحدث الخام في التلميح وحده */}
                <div className="dim" style={{ fontSize: 11, overflowWrap: 'anywhere' }} title={f.event || f.what || undefined}>{whatAr(f.stage, f.what)}</div>
                <div style={{ height: 5, borderRadius: 3, background: 'var(--line, #3334)', overflow: 'hidden', marginTop: 3 }}>
                  <div style={{
                    height: '100%', width: `${Math.min(100, f.pct)}%`,
                    background: dead ? 'var(--red)' : 'var(--green)',
                  }} />
                </div>
              </div>
              <div style={{ textAlign: 'center' }}>
                <span className="num" style={{ fontSize: 16, fontWeight: 700, color: dead ? 'var(--red)' : undefined }}>
                  {num(f.n)}
                </span>
                <span className="num dim" style={{ fontSize: 11, marginInlineStart: 5 }}>{num(f.pct, 1)}٪</span>
              </div>
            </div>
          )
        })}
      </div>

      {/* الأزمنة */}
      {(data.hops?.length ?? 0) > 0 && (
        <div>
          <div className="st" style={{ marginBottom: 4 }}>كم تاخد كلّ قفزة (الوسيط — ما بينزاح بقفزة وحدة بطيئة)</div>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12.5 }}>
              <thead><tr className="dim" style={{ fontSize: 11 }}>
                <th style={{ textAlign: 'right', padding: '3px 6px' }}>القفزة</th>
                <th style={{ textAlign: 'right', padding: '3px 6px' }}>الوسيط</th>
                <th style={{ textAlign: 'right', padding: '3px 6px' }}>أسرع</th>
                <th style={{ textAlign: 'right', padding: '3px 6px' }}>أبطأ</th>
                <th style={{ textAlign: 'right', padding: '3px 6px' }}>عدد</th>
              </tr></thead>
              <tbody>
                {(data.hops ?? []).slice(0, 7).map((h) => (
                  <tr key={h.from + h.to} style={{ borderTop: '1px solid var(--line, #3333)' }}>
                    <td style={{ padding: '3px 6px' }}>{label(h.from)} ← {label(h.to)}</td>
                    <td className="num" style={{ padding: '3px 6px' }}>{num(h.median, 3)} ث</td>
                    <td className="num dim" style={{ padding: '3px 6px' }}>{num(h.min, 3)}</td>
                    <td className="num dim" style={{ padding: '3px 6px' }}>{num(h.max, 3)}</td>
                    <td className="num dim" style={{ padding: '3px 6px' }}>{num(h.n)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* آخر رحلة كاملة */}
      {data.last_trip && (
        <div>
          <div className="st" style={{ marginBottom: 4 }}>
            آخر رحلة وصلت الجسر وتعبّت — {data.last_trip.symbol} · من الطلب للمركز{' '}
            <span className="num" style={{ fontWeight: 700 }}>{num(data.last_trip.span, 3)} ثانية</span>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
            {data.last_trip.steps.map((s) => (
              <div key={s.stage} style={{ display: 'flex', gap: 10, fontSize: 12.5, alignItems: 'baseline' }}>
                <span className="num dim" style={{ minWidth: 62 }}>{clock(s.at)}</span>
                <span className="num" style={{ minWidth: 62 }}>+{num(s.offset, 3)} ث</span>
                <span>{label(s.stage)}</span>
                {s.reason && <span className="dim" style={{ fontSize: 11 }} title={s.reason}>{valueAr(s.reason)}</span>}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* بناء البطاقة */}
      {data.cards_available && data.card && (
        <div>
          <div className="st" style={{ marginBottom: 4 }}>
            كيف تنبنى بطاقة وحدة — رقم <span className="num">{num(Number(data.card.card_no))}</span>{' '}
            · {String(data.card.symbol ?? '')} {valueAr(data.card.side)}
            {data.card.state ? <> · {valueAr(data.card.state)}</> : null}
            {data.card.ticket ? <> · تذكرة <span className="num">{String(data.card.ticket)}</span></> : null}
            {' '}· حقول مكتوبة <span className="num">{num(data.card_filled)}</span> من{' '}
            <span className="num">{num(data.card_columns)}</span>
          </div>
          <button className="btn" onClick={() => setOpen((v) => !v)} style={{ fontSize: 12 }}>
            {open ? 'اطوِ الحقول' : `افتح الحقول (${num(data.card_writes?.length)} كتابة — كلّ وحدة باسم صاحبها)`}
          </button>
          {open && (
            <div style={{ maxHeight: 340, overflowY: 'auto', marginTop: 6 }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
                <thead><tr className="dim" style={{ fontSize: 11 }}>
                  <th style={{ textAlign: 'right', padding: '3px 6px' }}>الساعة</th>
                  <th style={{ textAlign: 'right', padding: '3px 6px' }}>من فتح البطاقة</th>
                  <th style={{ textAlign: 'right', padding: '3px 6px' }}>مين كتب</th>
                  <th style={{ textAlign: 'right', padding: '3px 6px' }}>الحقل</th>
                  <th style={{ textAlign: 'right', padding: '3px 6px' }}>القيمة</th>
                </tr></thead>
                <tbody>
                  {(data.card_writes ?? []).map((w, i) => {
                    const t0 = data.card_writes?.[0]?.first_at ?? w.first_at
                    return (
                      <tr key={`${w.author}-${w.field}-${i}`} style={{ borderTop: '1px solid var(--line, #3333)' }}>
                        <td className="num dim" style={{ padding: '3px 6px' }}>{clock(w.first_at)}</td>
                        <td className="num" style={{ padding: '3px 6px' }}>+{num(w.first_at - t0, 3)} ث</td>
                        <td className="num" style={{ padding: '3px 6px', fontWeight: 600 }}>{w.author}</td>
                        <td style={{ padding: '3px 6px' }} title={w.field}>{fieldAr(w.field)}</td>
                        <td className="dim" style={{ padding: '3px 6px', overflowWrap: 'anywhere' }}
                            title={String(w.value_json ?? '')}>
                          {valueAr(w.value_json)}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* ما طلع بالقياس — وهو خبر لا زينة */}
      {finalized > 0 && bridgeBad > 0 && (
        <div className="ss" style={{ color: 'var(--red)' }}>
          ⚠️ <b>{num(bridgeBad)}</b> من <b>{num(finalized)}</b> أمرًا مرّرها ٥٥٢ ما وصلت الجسر أصلًا
          (<span className="num">{num((100 * bridgeBad) / finalized, 1)}٪</span>) — والسبب المكتوب
          بالسجلّ <b title="database is locked">«القاعدة مقفولة»</b>: قفل على قاعدة الجسر، مش على
          المخازن.
        </div>
      )}
      {opened > 0 && closed === 0 && (
        <div className="ss" style={{ color: 'var(--amber)' }}>
          ⚠️ الأثر بينقطع عند الإغلاق: <b>{num(opened)}</b> طلبًا وصل «امتلأ» وما في ولا واحد بيطلع
          عند «أُغلق» بنفس المفتاح — محطّة الإغلاق ما بتحمل <span title="request_id">مفتاح الطلب</span>.
          الصفقة متسجّلة بمخزن الصفقات، بس سلسلة القرار بتنتهي قبل نهايتها.
        </div>
      )}
      <div className="ss dim">
        كل الأزمنة بساعة المنصّة. <span title="opened_at">ساعة فتح الصفقة</span> بمخزن الصفقات
        بساعة الوسيط وبتسبقها ٣ ساعات — ما بينطرح وحدة من التانية.
      </div>
    </div>
  )
}
