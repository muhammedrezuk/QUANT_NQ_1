// المخاطر (856) — الحالة الموحّدة العالمية من مدير المخاطر (500: risk.unified.state):
// قاطع الأمان · الخسارة اليومية · الخسائر المتتالية · عدد صفقات اليوم. يُنتَج عند حدث خسارة/إيقاف/تصفير.
// + تصفير القاطع عبر بوّابة الأوامر (901) بتأكيد — وسجلّ البوّابة (system.commands.state).
import { useStore } from '../core/store'
import { dangerCommand } from '../core/commands'
import { arabicHealth } from '../core/arabic'
import { SectionConfigTable } from '../components/SectionAtoms'

const money = (n?: number) => (n == null ? '—' : n.toLocaleString('ar-EG-u-nu-latn', { maximumFractionDigits: 2 }))

interface GatewayState { seen?: number; executed_halt?: number; executed_reset?: number; expired?: number; rejected?: number }

// ٢٠٢٦-٠٩-١٠ — بلاغ جلسة قسم القرار (450-499): «أربع صفقات فُتحت خلال ٦ ثوانٍ
// وضربها الوقف معًا بـ‎-324.52‎، بينما حارسي يسمح بثلاث. **المالك رأى الخسارة
// ولم يرَ الخرق.**» وقِستُ اللوحة: صفر بطاقة تعرض عدد المراكز المفتوحة لكل رمز
// مقابل سقفه — يُضبَط السقف من «تحكّم» (`SET_MAX_PER_SYMBOL`) ولا يُرى أثره قط.
//
// المصدران، كلٌّ من كود ناشره لا من تخمين:
//   • العدد: `platform.positions.state.by_symbol` — يبنيه 609 عدًّا للمراكز
//     الحقيقيّة لكل رمز (`atoms/قسم 600-649/609_مزامنة_المراكز/atom.py:250-257`).
//   • السقف: ٢٠٢٦-١٠-٠٨ (فكّ الأقسام عن القرار، ختم المالك «NQ»): كان من حارس المراكز 463 وقد أُرشف.
//     الحاجز الحيّ الآن طالب أمر الدخول 555: يردّ الطلب إن كان المفتوح على الرمز أكثر من عياره
//     `max_open_per_symbol` (`555/atom.py:335-339`)، ويعلن العيار في رسالة صحّته «مراكز/رمز=N»
//     (`555/entry_request_badge.py:39`). فأقصى ما يُفتح على رمزٍ = N + 1 — ولا بطاقة 414 تُفتح فوق مركزٍ قائم.
interface PosState { by_symbol?: Record<string, number>; open_count?: number }

function PositionsVsCap() {
  const pos = useStore((s) => s.streams['platform.positions.state']) as PosState | undefined
  const msg555 = useStore((s) => s.atoms[555]?.health?.message) ?? ''
  const capValue = (() => {
    const m = /مراكز\/رمز=(\d+)/.exec(msg555)
    return m ? Number(m[1]) + 1 : null
  })()
  const bySym = pos?.by_symbol
  const rows = bySym
    ? Object.entries(bySym)
      .filter(([, n]) => typeof n === 'number' && n > 0)
      .map(([sym, n]) => ({
        sym, n, limit: capValue, over: capValue != null && n > capValue,
      }))
      .sort((a, b) => (Number(b.over) - Number(a.over)) || b.n - a.n)
    : null
  const breached = rows ? rows.filter((r) => r.over) : []

  return (
    <div
      className="scard"
      style={{
        borderInlineStart: `4px solid var(--${breached.length ? 'red' : rows && rows.length ? 'green' : 'grey'})`,
      }}
    >
      <div className="st">المراكز المفتوحة مقابل السقف المسموح لكل رمز</div>
      {rows == null ? (
        <div className="ss dim">لم يصل حدث مراكز المنصّة بعد — لا رقم يُعرض، ولا يُخترع.</div>
      ) : rows.length === 0 ? (
        <div className="ss dim">لا مركز مفتوح الآن على أيّ رمز.</div>
      ) : (
        <>
          <div className={`sv ${breached.length ? 'red' : 'green'}`} style={{ fontSize: 20 }}>
            {breached.length
              ? `✗ خرق السقف على ${breached.length === 1 ? 'رمز واحد' : `${breached.length} رموز`}`
              : '✓ كل رمز داخل سقفه'}
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 8 }}>
            {rows.map((r) => (
              <span
                key={r.sym}
                className={`acctchip ${r.over ? 'red' : r.limit == null ? 'dim' : 'green'}`}
                title={r.limit == null
                  ? 'لم تصل رسالة طالب أمر الدخول (555) بعد، فالسقف الساري غير معروف — ولا يُخمَّن'
                  : `المفتوح ${r.n} · المسموح ${r.limit}`}
              >
                <b>{r.sym}</b>
                <em className="num">{r.n} / {r.limit ?? '—'}</em>
              </span>
            ))}
          </div>
          {breached.length ? (
            <div className="ss" style={{ marginTop: 8, lineHeight: 1.8, color: 'var(--amber)' }}>
              يحكم بالسقف طالب أمر الدخول (٥٥٥) — ويُضبَط عياره من جدول معاملات التنفيذ بصفحة «التنفيذ».
              وجود مراكز فوق السقف يعني أنّها فُتحت قبل أن يحكم الحارس — لا أنّه أذن بها.
            </div>
          ) : null}
          <div className="ss dim" style={{ marginTop: 6, fontSize: 11, lineHeight: 1.7 }}>
            العدد من مزامنة المراكز (٦٠٩) · والسقف <b>عيارٌ واحد يسري على كل الرموز</b>
            {capValue != null ? ` — يُفتح على الرمز حتى ${capValue} ثمّ يُردّ كلّ طلب دخول جديد` : ' لم يصل بعد'} — من رسالة
            طالب أمر الدخول (٥٥٥)، والبطاقة (٤١٤) لا تفتح بطاقةً فوق مركزٍ قائم أصلًا.
            {pos?.open_count != null ? ` إجمالي المفتوح: ${pos.open_count}.` : ''}
          </div>
        </>
      )}
    </div>
  )
}

export default function Risk() {
  const risk = useStore((s) => s.risk)
  const gw = useStore((s) => s.streams['system.commands.state']) as GatewayState | undefined

  const resetBtn = (
    <button
      className="btn"
      style={{ borderColor: 'var(--amber)', color: 'var(--amber)', marginTop: 10 }}
      title="يرفع الإيقاف — عبر بوّابة الأوامر (901) بتأكيد"
      onClick={async () => { const r = await dangerCommand('kill_switch_reset'); if (r.message) window.alert(r.message) }}
    >تصفير قاطع الأمان</button>
  )

  if (!risk) {
    return (
      <div className="section" style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
        <div className="empty">بانتظار أوّل حدث مخاطر من النواة… (لا صفقات بعد — تُنتَج عند أوّل نتيجة/إيقاف)</div>
        {/* المراكز مصدرها 609 لا 500، فلا يصحّ حجبها بغياب حدث المخاطر:
            مركزٌ مفتوح فوق سقفه لا ينتظر «أوّل نتيجة» ليصير خرقًا. */}
        <PositionsVsCap />
        <div className="scard">
          <div className="st">بوّابة الأوامر (901)</div>
          <div className="ss dim">{gw ? `نُفِّذ: إيقاف ${gw.executed_halt ?? 0} · تصفير ${gw.executed_reset ?? 0} · منتهي الصلاحية ${gw.expired ?? 0} · مرفوض ${gw.rejected ?? 0}` : 'ما وصل أمر بعد'}</div>
          {resetBtn}
        </div>
      </div>
    )
  }

  const kill = risk.kill_switch_state === true
  return (
    <div className="section" style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      <div className={`scard`} style={{ borderColor: kill ? 'var(--red)' : 'var(--glassb)' }}>
        <div className="st">قاطع الأمان</div>
        <div className={`sv ${kill ? 'red' : 'green'}`}>{kill ? '🛑 مُفعَّل — التداول موقوف' : '🟢 سليم — التداول مسموح'}</div>
        {/* ٢٠٢٦-٠٩-١٨: كان يُطبع خامًا — «السبب: RISK_DAILY_LIMIT». والأصل
            يبقى في تلميح الفأرة لمن يريد الرمز نفسه. */}
        {kill && risk.kill_switch_reason ? (
          <div className="ss red" title={String(risk.kill_switch_reason)}>
            السبب: {arabicHealth(String(risk.kill_switch_reason))}
          </div>
        ) : null}
        {/* ٢٠٢٦-١٠-٢٦ (فحص المشروع): كان «التصفير يدويّ فقط (لا يُصفَّر تلقائيًّا مع اليوم)» و«تحكّم» تقول غيره. والشيفرة
            (516 `_on_day`، حكم المالك ١٨/٠٩): حدّ الخسارة اليوميّة وحده يُسحب مع دوران اليوم، والباقي بيدك. */}
        {kill ? <div className="ss dim">حدّ الخسارة اليوميّة وحده يُسحب مع دوران اليوم، وخرقُ عدّ صفقات الجلسة يُسحب حين يزول سببه.
          أمّا الخسائر المتتالية وأمرك وكلّ سببٍ آخر، فلا يفكّها إلّا زرّ التصفير.</div> : null}
        {resetBtn}
        <div className="ss dim" style={{ marginTop: 6 }}>{gw ? `بوّابة الأوامر: إيقاف ${gw.executed_halt ?? 0} · تصفير ${gw.executed_reset ?? 0}` : 'بوّابة الأوامر: ما وصلها أمر بعد'}</div>
      </div>

      {/* ٢٠٢٦-١٠-٠٨ (فكّ الأقسام عن القرار، ختم المالك «NQ»): بطاقة «عيار المخاطرة» رُفعت — يطبّقه محرّك فرق المركز 581 وحده وقد أُرشف. */}
      <PositionsVsCap />

      {/* ٢٠٢٦-١٠-٢٦ (فحص المشروع، ختم «nq اصلح»): الغائب كان يُعرض صفرًا (`?? 0`) — «صفر خسائر متتالية» و«صفر صفقات» عن
          رقمٍ لم يصل. الغائب الآن «غير مقروء»، والصفر صفرٌ وصل فعلًا. */}
      <div className="cards">
        <div className="scard"><div className="st">الخسارة اليومية</div><div className={`sv num ${(risk.daily_loss_pct ?? 0) < 0 ? 'red' : risk.daily_loss_pct == null ? 'dim' : ''}`}>{risk.daily_loss_pct == null ? 'غير مقروء' : `${money(risk.daily_loss_pct)}%`}</div></div>
        <div className="scard"><div className="st">الخسائر المتتالية</div><div className={`sv num ${(risk.consecutive_losses ?? 0) >= 3 ? 'red' : risk.consecutive_losses == null ? 'dim' : ''}`}>{risk.consecutive_losses ?? 'غير مقروء'}</div></div>
        <div className="scard"><div className="st">صفقات اليوم</div><div className={`sv num ${risk.daily_trade_count == null ? 'dim' : ''}`}>{risk.daily_trade_count ?? 'غير مقروء'}</div></div>
      </div>

      <SectionConfigTable from={500} to={530} title="معاملات ذرّات المخاطر (500-529) — ضبط جماعي (قاطع 516 · حدود ربح 507 · حدود جلسة 506)" />
    </div>
  )
}
