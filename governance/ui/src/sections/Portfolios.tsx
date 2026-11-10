// المحافظ (٨٥٨) — حسابك الحقيقي + الصفقات المفتوحة (بثّ حيّ: platform.account.state / positions.state).
import { useStore } from '../core/store'
import { SectionAtomsHealth } from '../components/SectionAtoms'
import { AccountsPair } from '../components/AccountsBar'
import { priceText, decimalsOfAll } from '../core/price'

interface Account { account_id: string; balance: number; equity: number; margin: number; free_margin: number; leverage: number; broker?: string }
// ٢٠٢٦-٠٩-١٠ (ختم NQ) — كذب ماليّ مقيس، واللوحة نفسها كانت تكشفه: البطاقة
// تقول «ربح مفتوح 0.00» وقيمة الحساب تفوق الرصيد. السبب: `floating_pnl`
// **غير موجود في `platform.positions.state` إطلاقًا** (حقوله: positions ·
// by_symbol · open_count …) — ناشره هو `portfolio.pnl.state`. نفس نمط
// `kill_switch_state`: حقل يُقرأ من حدثٍ لا يحويه فيبقى صفرًا أبديًّا.
// ومعه: كل صفقة تحمل `profit` (EURUSD = -12.88 مقيسًا) ولم يكن يُعرض.
interface Pos {
  ticket: number; symbol: string; side: string; volume: number
  entry_price: number; current_price: number
  profit?: number; swap?: number; commission?: number
}
interface Positions { positions: Pos[] }
interface PnlState { floating_pnl?: number; realized_pnl?: number; net_pnl?: number }

const money = (n?: number) => (n == null ? '—' : n.toLocaleString('ar-EG-u-nu-latn', { minimumFractionDigits: 2, maximumFractionDigits: 2 }))
const signed = (n?: number | null) => (n == null ? '—' : `${n >= 0 ? '+' : ''}${money(n)}`)

export default function Portfolios() {
  const acc = useStore((s) => s.streams['platform.account.state']) as Account | undefined
  // ٢٠٢٦-١٠-٢٦ (قانون صفقات المالك، ختم «NQ»): صفقات المنظومة وحدها من حاسب الصفقات المفتوحة — صفقات المالك مفصولةٌ هناك،
  // وربحه وخسارته في «شو صاير» ببطاقتها.
  const pos = useStore((s) => s.streams['portfolio.open_positions.state']) as Positions | undefined
  const pnlState = useStore((s) => s.streams['portfolio.pnl.state']) as PnlState | undefined
  if (!acc) {
    // بند ١٠ (ورقة ٩٩): بدل الفراغ — حالة ذرّات الجسر التي تجيب بيانات الحساب نفسها
    return (
      <div className="section chartsec">
        <AccountsPair />
        <div className="empty">جارِ استقبال بيانات حساب التنفيذ من النواة…</div>
        <SectionAtomsHealth ids={[618, 619, 609, 611]} title="ذرّات جسر الحساب — حالتها الحيّة الآن"
          note="الرصيد والصفقات من حساب التنفيذ: جسر ميتاتريدر 5 (618) · حالة الحساب (619) · مزامنة المراكز (609) · قارئ الصفقات (611). حساب سي‑تريدر بيانات فقط وما بيظهر هون كرصيد." />
      </div>
    )
  }
  const list = pos?.positions ?? []
  // المصدر الصحيح أوّلًا (٦٦٢ ينشره)، ومجموع أرباح الصفقات احتياطًا مقيسًا —
  // لا صفرٌ مكان مجهول: إن غاب الاثنان يُعلَن الغياب شرطةً.
  const sumProfit = list.length
    ? list.reduce((s, p) => s + (p.profit ?? 0) + (p.swap ?? 0) + (p.commission ?? 0), 0)
    : null
  const pnl = typeof pnlState?.floating_pnl === 'number' ? pnlState.floating_pnl : sumProfit
  return (
    <div className="section" style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div className="cards">
        <div className="scard"><div className="st">الرصيد</div><div className="sv num">${money(acc.balance)}</div><div className="ss">{acc.broker ?? ''}</div></div>
        {/* «الأسهم» كانت ترجمة غلط لـEquity — قيمة الحساب الفعليّة بالربح العائم */}
        <div className="scard"><div className="st">قيمة الحساب</div><div className="sv num">${money(acc.equity)}</div><div className="ss dim">الحساب كلّه — ومعه صفقاتك اليدويّة</div></div>
        <div className="scard">
          <div className="st">ربح مفتوح</div>
          <div className={`sv num ${pnl == null ? '' : pnl >= 0 ? 'green' : 'red'}`}>{signed(pnl)}</div>
          <div className="ss dim">
            {pnl == null ? 'ما وصل رقم — لا صفر مكان مجهول'
              : typeof pnlState?.floating_pnl === 'number' ? 'من حاسب الربح والخسارة'
              : 'مجموع أرباح الصفقات + السواب والعمولة'}
          </div>
        </div>
        <div className="scard"><div className="st">الهامش المستخدم</div><div className="sv num">${money(acc.margin)}</div></div>
        <div className="scard"><div className="st">السيولة الحرّة</div><div className="sv num">${money(acc.free_margin)}</div></div>
        {/* بند 6 (دفتر 97): كل رقم حساب يُوسم — هذا حساب «تنفيذ» (ميتاتريدر 5) */}
        <div className="scard"><div className="st">الرافعة</div><div className="sv num">1:{acc.leverage}</div><div className="ss">حساب تنفيذ {acc.account_id}</div></div>
      </div>
      <div className="loglist" style={{ flex: 1 }}>
        {!pos ? <div className="empty">ما وصلت صفقات المنظومة المفتوحة بعد</div> : list.length === 0 ? <div className="empty">لا صفقات مفتوحة للمنظومة</div> : null}
        {list.map((p) => (
          <div className="logrow" key={p.ticket}>
            <span className="ln">{p.symbol}</span>
            <span className={p.side === 'BUY' ? 'green' : 'red'}>{p.side === 'BUY' ? 'شراء' : 'بيع'}</span>
            <span className="dim num">حجم {p.volume}</span>
            {/* الأسعار بدقّتها كما بثّها الوسيط — لا خانتين ثابتتين */}
            <span className="dim num">دخول {priceText(p.entry_price, decimalsOfAll(p.entry_price, p.current_price))}</span>
            <span className="dim num">الآن {priceText(p.current_price, decimalsOfAll(p.entry_price, p.current_price))}</span>
            {/* ٢٠٢٦-٠٩-١٠ (ختم NQ): ربح كل صفقة كان موجودًا بالحمولة ولا يُعرض
                — فيرى المالك صفقاته بلا ربح ولا خسارة. مقيس: EURUSD -12.88 */}
            <span className="num" style={{ marginInlineStart: 'auto', fontWeight: 700, color: (p.profit ?? 0) >= 0 ? 'var(--green)' : 'var(--red)' }}>
              {signed(p.profit)}
              {(p.swap ?? 0) !== 0 || (p.commission ?? 0) !== 0 ? (
                <span className="dim" style={{ fontWeight: 400, fontSize: 10.5 }}>
                  {' '}(سواب {signed(p.swap)} · عمولة {signed(p.commission)})
                </span>
              ) : null}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}
