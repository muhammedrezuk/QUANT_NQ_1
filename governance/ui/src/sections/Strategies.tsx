// الاستراتيجيات (٤٠٠-٤٤٩) — ٢٠٢٦-١٠-٠٨ (فكّ الأقسام عن القرار، ختم المالك «NQ»):
// كانت الصفحة بطاقة قسمٍ وصفيّة من مدير الاستراتيجيات 400 (`strategy.section.live`) — وقد أُرشف مع
// الاستراتيجيّات 404-410 ودمج الإشارات 413، فبقيت تقول «بانتظار» أبدًا.
// القسم الآن استراتيجيّةٌ تقرّر: بطاقة استمرار الاتّجاه 414، ومعها نافذة المالك 412 ونافذة الخبر 411
// وقواعد الدخول والخروج 401/402. هنا ملخّص آخر بطاقة لكلّ رمز وعدّاداتها؛ والتفصيل كاملًا بصفحة «القرار».
import { SectionAtomsHealth, SectionConfigTable } from '../components/SectionAtoms'
import { CardHealthStrip, CardLine, useCards } from '../components/TrendCard'

export default function Strategies() {
  const cards = useCards()
  const list = Object.values(cards).filter((c) => c?.symbol)
    .sort((a, b) => String(a.symbol).localeCompare(String(b.symbol)))

  return (
    <div className="section chartsec" style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div className="scard" style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, flexWrap: 'wrap' }}>
          <b style={{ fontSize: 15 }}>بطاقة استمرار الاتّجاه بعد الارتداد</b>
          <span className="num dim" style={{ fontSize: 11.5 }}>#414</span>
          <span className="ss dim" style={{ marginInlineStart: 'auto', marginTop: 0 }}>الاستراتيجيّة الوحيدة التي تقرّر الآن</span>
        </div>
        {list.length === 0
          ? <div className="ss dim" style={{ marginTop: 0 }}>ما وصلت بطاقة منذ فتح الشاشة — تُكتب مع إغلاق كل شمعة ٥ دقائق.</div>
          : list.map((c) => <CardLine key={c.symbol} card={c} />)}
        <CardHealthStrip compact />
        <div className="ss dim" style={{ marginTop: 0 }}>التفصيل الكامل — مصادر الحقائق، والموافقة، وهل وصلت التنفيذ — بصفحة «القرار».</div>
      </div>
      <SectionAtomsHealth from={400} to={450} title="ذرّات قسم الاستراتيجيات — حالتها الحيّة الآن"
        note="الخبر 411 والجلسة 412 يغذّيان البطاقة 414 · وقواعد الدخول والخروج 401/402 تعمل بجانبها." />
      <SectionConfigTable from={400} to={450} title="معاملات ذرّات الاستراتيجيات (400-449) — ضبط جماعي" />
    </div>
  )
}
