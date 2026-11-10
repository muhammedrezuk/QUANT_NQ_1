// السيولة (٨٥٣ج) — سيولة السوق لكل رمز من ذرة النشر (٢٦٠: market.liquidity.updated):
// كنس · فجوة FVG · تجمّع علوي/سفلي · مستوى شرائي/بيعي. قيم مؤكَّدة من ذرات ٢٥٢..٢٥٥.
import { useStore, type LiquidityUnitRow } from '../core/store'
import { arabicVisible } from '../core/arabic'
import { SectionAtomsHealth, SectionConfigTable } from '../components/SectionAtoms'

const HEAD: Record<string, { t: string; c: string }> = {
  sweep: { t: 'كنس سيولة', c: 'amber' },
  fvg_bullish: { t: 'فجوة صاعدة', c: 'green' },
  fvg_bearish: { t: 'فجوة هابطة', c: 'red' },
  none: { t: 'هادئ', c: 'grey' },
}
const POOL: Record<string, string> = { pool_high: 'تجمّع علوي', pool_low: 'تجمّع سفلي', none: '—' }
const SWEEP_DIR: Record<string, string> = { buy_side: 'جهة الشراء', sell_side: 'جهة البيع' }
const FVG: Record<string, string> = { fvg_bullish: 'صاعدة', fvg_bearish: 'هابطة', none: '—' }
const num = (n?: number | null) => (n == null ? '—' : n.toLocaleString('ar-EG-u-nu-latn', { maximumFractionDigits: 3 }))

// ٢٠٢٦-٠٩-٠٩ — لوحة وحدات ٢٥٠: أسماء الوحدات بالعربي، والدفتر مفصول عن الدورة.
const UNIT_NAME: Record<string, string> = {
  pool: 'التجمّع', buyside: 'سيولة شرائية', sellside: 'سيولة بيعية',
  sweep: 'الكنس', fvg: 'الفجوة', depth: 'عمق الدفتر',
  // ٢٠٢٦-٠٩-١٨: `CVD` كانت الوحيدة الإنكليزيّة بين اثنتي عشرة، وتظهر
  // للمالك بالحرف — وهو لا يقرأ الإنكليزيّة. الرمز الخام يبقى في `title`.
  delta: 'الدلتا', cvd: 'الدلتا التراكميّة', absorption: 'الامتصاص',
  microprice: 'الميكرو-سعر', ofi: 'تدفّق الأوامر', price_impact: 'أثر السعر',
}
const REASON_AR: Record<string, string> = {
  NO_SOURCE_AT_BROKER: 'ما في مصدر عند الوسيط',
  NO_BOOK_STATE_YET: 'ما وصلت حالة بعد',
  OBSERVED_ONLY_NO_CYCLE_ID_AT_SOURCE: 'مرصود فقط — مصدره بلا رقم دورة',
  JOINED_BY_RECENCY_STREAM_HAS_NO_CYCLE_ID: 'مضموم بالحداثة — مصدره تدفّق بلا رقم دورة',
}
// ٢٠٢٦-٠٩-١٦ (ختم NQ): الوحدة تقول بأيّ إيقاع وصلت. «بلّغت داخل دورتها»
// ليست «ضُمّت إليها»، والفرق يظهر بالحرف بدل ما ينطمس.
const PACE_AR: Record<string, string> = { candle: 'بالشمعة', book: 'بالدفتر' }
const unitName = (id: string) => UNIT_NAME[id] ?? arabicVisible(id, 'وحدة غير مترجَمة')

// العقد ينشر الحقل غير المحسوب بصفر ويسمّيه في `unknown_fields`
// (`section_contract` §١١). عرض صفره كأنّه قياس كذبٌ صامت.
// والكلمة «مجهول» بالضبط — هي المصطلح الجاري في اللوحة (٥٤ موضعًا، منها
// `Analysis.tsx: eightVal`)؛ لفظٌ ثانٍ لنفس المعنى قناعٌ لا قاموس.
const fieldVal = (unknown: string[] | undefined, field: string, n?: number | null) =>
  ((unknown ?? []).includes(field) || n == null)
    ? <span className="dim">مجهول</span>
    : <b className="num">{num(n)}</b>

// وحدات الدورة الناقصة: اللوحة كانت تقول «بيانات غير كافية» بلا ما تقول مين
// الناقص ولا ليش. هون بينقال بالاسم — الصمت هو اللي كان يكذب.
function LiquidityUnitsPanel() {
  const panels = useStore((s) => s.liquidityUnits)
  const syms = Object.keys(panels).sort()
  if (syms.length === 0) return null
  return (
    <div style={{ marginTop: 16 }}>
      <div style={{ fontWeight: 700, fontSize: 13, marginBottom: 4 }}>
        وحدات القسم — مين حاضر ومين ناقص (من ٢٥٠)
      </div>
      <div className="dim" style={{ fontSize: 12, marginBottom: 8, lineHeight: 1.7 }}>
        عائلة الدفتر (٢٦١·٢٦٢·٢٦٣·٢٦٤) بتقرا دفتر العمق بإيقاعه هو، وبتنشر بلا رقم دورة
        وبلا هوية حساب — فما بتدخل عدّ الاكتمال ولا القرار. أرقامها تحت كما تنشرها هي،
        مرصودة لا محسوبة.
      </div>
      <div className="cards" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))' }}>
        {syms.map((sym) => {
          const p = panels[sym]
          const cycle = p.units ?? []
          const missing = p.missing ?? []
          const excluded = cycle.filter((row) => row.excluded)
          // تفصيل الدفتر (الاتجاه والمستويات) يُضمّ إلى صفّ وحدته بدل كتلةٍ
          // ثانية تكرّر ما فوقها — مفهرسًا بالمعرّف لا بالترتيب.
          const bookDetail: Record<string, LiquidityUnitRow | undefined> = {}
          for (const row of p.book_units ?? []) bookDetail[row.id] = row
          return (
            <div className="scard" key={sym} style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span style={{ fontWeight: 700, fontSize: 14 }}>{sym}</span>
                {p.timeframe ? <span className="dim" style={{ fontSize: 12 }}>الفريم {p.timeframe}</span> : null}
                <span className={`pill ${missing.length === 0 ? 'green' : 'amber'}`}
                      style={{ marginInlineStart: 'auto', fontSize: 12 }}>
                  {num(p.present)} / {num(p.expected)}
                </span>
              </div>

              {missing.length > 0 ? (
                <div className="pill amber" style={{ fontSize: 11 }}>
                  ناقص: {missing.map(unitName).join(' · ')}
                </div>
              ) : null}

              {/* ٢٠٢٦-٠٩-١٨: صفٌّ واحد لكل وحدة. كانت للدفتر كتلةٌ ثانية تحته
                  تعيد الثقة والعمر نفسيهما، وجديدها `اتجاه` و`مستويات` وحدهما —
                  فضُمّا إلى الصفّ وحُذفت الكتلة: ١٦ سطرًا أقلّ لكل رمز بلا فقد
                  حرف. (قياس جلسة اللوحات: ٧٨١ سطرًا و١٥ بطاقة على الصفحة.) */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: 3, fontSize: 12 }}>
                {cycle.filter((row) => !row.excluded).map((row) => (
                  <div key={row.id} style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                    <span style={{ minWidth: 92 }} title={row.id}>{unitName(row.id)}</span>
                    {row.present ? (
                      <>
                        <span className={`pill ${row.ready ? 'green' : 'grey'}`} style={{ fontSize: 11 }}>
                          {row.ready ? 'جاهزة' : 'مو جاهزة'}
                        </span>
                        {row.paced_by ? (
                          <span className="dim" style={{ fontSize: 11 }}>
                            {PACE_AR[row.paced_by] ?? arabicVisible(row.paced_by, 'إيقاع غير مترجَم')}
                          </span>
                        ) : null}
                        <span className="dim">ثقة {fieldVal(row.unknown_fields, 'confidence', row.confidence)}</span>
                        <span className="dim">وزن {fieldVal(row.unknown_fields, 'weight', row.weight)}</span>
                        {bookDetail[row.id]?.direction != null ? (
                          <span className="dim">اتجاه {fieldVal(bookDetail[row.id]?.unknown_fields, 'direction', bookDetail[row.id]?.direction)}</span>
                        ) : null}
                        {bookDetail[row.id]?.levels != null ? (
                          <span className="dim">مستويات <b className="num">{num(bookDetail[row.id]?.levels)}</b></span>
                        ) : null}
                        <span className="dim">تسليمات <b className="num">{num(row.deliveries)}</b></span>
                        {row.age_s != null ? <span className="dim">عمر <b className="num">{num(row.age_s)}</b>ث</span> : null}
                      </>
                    ) : (
                      <span className="pill red" style={{ fontSize: 11 }}>غائبة</span>
                    )}
                  </div>
                ))}
                {excluded.length > 0 ? (
                  <div className="dim" style={{ fontSize: 11 }}>
                    <b className="num">{num(excluded.length)}</b> مستثناة
                    ({excluded.map((r) => unitName(r.id)).join(' · ')}) —{' '}
                    {REASON_AR[excluded[0].reason ?? ''] ?? arabicVisible(excluded[0].reason ?? '', 'بلا سبب معلَن')}
                  </div>
                ) : null}
              </div>

            </div>
          )
        })}
      </div>
    </div>
  )
}

export default function Liquidity() {
  const liquidity = useStore((s) => s.liquidity)
  const syms = Object.keys(liquidity).sort()

  return (
    <div className="section chartsec">
      {/* بند ١٠ (ورقة ٩٩): لا صفحة فاضية وذرّات القسم حيّة — حالتها الفعلية بدل الفراغ */}
      {/* ٢٠٢٦-١٠-٠٨ (فكّ الأقسام عن القرار، ختم المالك «NQ»): مدير السيولة 250 وناشرها 260 أُرشفا — لا دورة سيولة مجمَّعة بعد اليوم، فلا «بانتظار». */}
      {syms.length === 0 ? (
        <>
          <div className="ss dim" style={{ marginBottom: 10, lineHeight: 1.8 }}>
            ما عاد في دورة سيولة مجمَّعة: مدير القسم وناشره أُرشفا مع فكّ الأقسام عن القرار. ذرّات السيولة تعطي حقائقها
            خامًا للاستراتيجيّات. تحت: حالة ذرّات القسم الحيّة.
          </div>
          <SectionAtomsHealth from={250} to={300} title="ذرّات قسم السيولة — حالتها الحيّة الآن" />
        </>
      ) : (
      <div className="cards" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))' }}>
        {syms.map((sym) => {
          const d = liquidity[sym]
          const lq = d.liquidity ?? ({} as LiqShape)
          const insufficient = d.status !== 'ok'
          const head = HEAD[d.signal] ?? { t: arabicVisible(d.signal, 'حالة غير معروفة'), c: 'grey' }
          const sweep = lq.sweep ?? { signal: 'none', direction: null, price: null }
          const fvg = lq.fvg ?? { signal: 'none', gap_top: null, gap_bottom: null }
          return (
            <div className="scard" key={sym} style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span style={{ fontWeight: 700, fontSize: 14 }}>{sym}</span>
                {/* ٢٠٢٦-٠٩-١٨: الشارة كانت تُعرض حتى على بطاقة أُعلن نقص
                    بياناتها — «فجوة هابطة» فوق «بيانات غير كافية» على الرمز
                    نفسه. وهي أبرز ما في البطاقة، فتُقرأ حكمًا. حكمٌ من بيانات
                    ناقصة لا يُعرض بلونه: يُقال النقص وحده. */}
                <span className={`pill ${insufficient ? 'grey' : head.c}`}
                      style={{ marginInlineStart: 'auto', fontSize: 12 }}>
                  {insufficient ? 'بانتظار الاكتمال' : head.t}
                </span>
              </div>

              {insufficient ? (
                <div className="dim" style={{ fontSize: 12 }}>
                  بيانات غير كافية بعد — وصل{' '}
                  <b className="num">{num(d.metadata?.present)}</b> من{' '}
                  <b className="num">{num(d.metadata?.expected)}</b> وحدة.
                </div>
              ) : (
                <>
                  <div style={{ display: 'flex', gap: 10, fontSize: 12, flexWrap: 'wrap' }}>
                    <span>الثقة <b className="num">{num(d.confidence)}</b></span>
                    <span>الجاهزية <b className="num">{num(d.current_depth)} / {num(d.required_depth)}</b></span>
                    <span>الضغط <b className="num">{num(d.liquidity_pressure)}</b></span>
                    <span>جودة السيولة <b className="num">{num(d.liquidity_quality)}</b></span>
                    {d.metadata?.timeframe ? <span className="dim">الفريم {d.metadata.timeframe}</span> : null}
                  </div>
                  <div style={{ display: 'flex', gap: 10, fontSize: 12, flexWrap: 'wrap' }}>
                    <span>التجمّع <b>{POOL[lq.pool] ?? arabicVisible(lq.pool, 'غير مترجَم')}</b></span>
                    <span className="dim">الجودة {d.quality === 'good' ? 'جيّدة' : 'ضعيفة'}</span>
                  </div>

                  <div style={{ display: 'flex', gap: 10, fontSize: 12 }}>
                    <span>سيولة شرائية (فوق) <b className="num">{num(lq.buyside_level)}</b></span>
                  </div>
                  <div style={{ display: 'flex', gap: 10, fontSize: 12 }}>
                    <span>سيولة بيعية (تحت) <b className="num">{num(lq.sellside_level)}</b></span>
                  </div>

                  <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                    {sweep.signal && sweep.signal !== 'none' ? (
                      <span className="pill amber" style={{ fontSize: 11 }}>
                        كنس {sweep.direction ? (SWEEP_DIR[sweep.direction] ?? arabicVisible(sweep.direction, 'جهة غير مترجَمة')) : ''} @ {num(sweep.price)}
                      </span>
                    ) : null}
                    {fvg.signal && fvg.signal !== 'none' ? (
                      <span className={`pill ${fvg.signal === 'fvg_bullish' ? 'green' : 'red'}`} style={{ fontSize: 11 }}>
                        فجوة {FVG[fvg.signal] ?? ''} [{num(fvg.gap_bottom)} – {num(fvg.gap_top)}]
                      </span>
                    ) : null}
                    {(!sweep.signal || sweep.signal === 'none') && (!fvg.signal || fvg.signal === 'none') ? (
                      <span className="pill grey" style={{ fontSize: 11 }}>لا كنس ولا فجوة الآن</span>
                    ) : null}
                  </div>
                </>
              )}
            </div>
          )
        })}
      </div>
      )}
      <LiquidityUnitsPanel />
      {/* بند ٩ (ورقة ٩٩): معاملات القسم الحقيقية بجدول واحد — بنمط صفحة التحليل (150) */}
      <SectionConfigTable from={250} to={300} title="معاملات ذرّات السيولة (250-299) — ضبط جماعي" />
    </div>
  )
}

type LiqShape = {
  pool: string
  buyside_level: number | null; sellside_level: number | null
  sweep: { signal: string; direction: string | null; price: number | null }
  fvg: { signal: string; gap_top: number | null; gap_bottom: number | null }
}
