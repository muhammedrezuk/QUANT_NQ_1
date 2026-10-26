// الإحصاء التحليلي (٨٦٤) — الإحصاءات المتدحرجة لكل رمز من مدير الإحصاء (٣٠٠: stats.cycle.collected):
// ١٧ إحصاء (متوسط·وسيط·انحراف·التواء·تفلطح·درجةZ·شذوذ·ارتباط·انحدار…). قيمة كلٍّ من metadata.value.
import { useStore } from '../core/store'
import { SectionAtomsHealth, SectionConfigTable } from '../components/SectionAtoms'

// أسماء عربية مؤكَّدة من ذرات ٣٠١..٣١٨ (id لكل ذرة)
const STAT_AR: Record<string, string> = {
  mean: 'المتوسط', median: 'الوسيط', mode: 'المنوال', std: 'الانحراف المعياري',
  variance: 'التباين', cv: 'معامل الاختلاف', range: 'المدى', zscore: 'درجة Z',
  skewness: 'الالتواء', kurtosis: 'التفلطح', outlier: 'الشذوذ', distribution: 'التوزيع',
  correlation: 'الارتباط', regression: 'الانحدار', r_squared: 'معامل التحديد',
  quality: 'جودة البيانات', period_compare: 'مقارنة الفترات',
}
const ORDER = Object.keys(STAT_AR)
const fmt = (n?: number) => (n == null ? '—' : n.toLocaleString('ar-EG-u-nu-latn', { maximumFractionDigits: 4 }))

export default function Statistics() {
  const stats = useStore((s) => s.stats)
  const syms = Object.keys(stats).sort()

  return (
    <div className="section chartsec">
      {/* بند ١٠ (ورقة ٩٩): «الإحصاء» صرخة المالك — 18 ذرّة شغّالة وصفحة فاضية.
          الفراغ صار يحمل حالة ذرّات القسم الفعلية بدل السواد. */}
      {/* ٢٠٢٦-١٠-٠٨ (فكّ الأقسام عن القرار، ختم المالك «NQ»): مدير الإحصاء 300 أُرشف — لا دورة إحصاء مجمَّعة بعد اليوم، فلا «بانتظار». */}
      {syms.length === 0 ? (
        <>
          <div className="ss dim" style={{ marginBottom: 10, lineHeight: 1.8 }}>
            ما عاد في دورة إحصاء مجمَّعة: مدير القسم أُرشف مع فكّ الأقسام عن القرار. ذرّات الإحصاء تعطي حقائقها خامًا
            للاستراتيجيّات. تحت: حالة ذرّات القسم الحيّة.
          </div>
          <SectionAtomsHealth from={300} to={350} title="ذرّات قسم الإحصاء — حالتها الحيّة الآن" />
        </>
      ) : (
      <div className="cards" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))' }}>
        {syms.map((sym) => {
          const results = stats[sym]?.results ?? {}
          return (
            <div className="scard" key={sym} style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <div style={{ fontWeight: 700, fontSize: 14 }}>{sym}</div>
                {stats[sym]?.timeframe ? <span className="pill grey" style={{ marginInlineStart: 'auto', fontSize: 11 }}>الفريم {stats[sym].timeframe}</span> : null}
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '2px 10px', fontSize: 11.5 }}>
                {ORDER.map((uid) => {
                  const u = results[uid]
                  if (!u) return null
                  const v = u.metadata?.value
                  return (
                    <div key={uid} style={{ display: 'flex', justifyContent: 'space-between', gap: 6, borderBottom: '1px solid var(--glassb)', padding: '1px 0' }}>
                      <span className="dim">{STAT_AR[uid]}</span>
                      <b className="num">{fmt(v)}</b>
                    </div>
                  )
                })}
              </div>
              {Object.keys(results).length === 0 ? <div className="dim" style={{ fontSize: 11 }}>لم تتجمّع إحصاءات بعد.</div> : null}
            </div>
          )
        })}
      </div>
      )}
      {/* بند ٩ (ورقة ٩٩): معاملات القسم الحقيقية بجدول واحد — بنمط صفحة التحليل (150) */}
      <SectionConfigTable from={300} to={350} title="معاملات ذرّات الإحصاء (300-349) — ضبط جماعي" />
    </div>
  )
}
