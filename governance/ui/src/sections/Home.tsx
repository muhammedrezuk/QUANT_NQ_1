// الرئيسية (850) v8 «حاملة البلاطات» — ختم المالك ٢٠٢٦-٠٨-٢٠.
// أمره الحرفيّ: «حط مجموع كل اللوحات بهي لوحة… وأنا بصغّر وبكبّر بالطول وبالعرض
// وبغيّر المكان» ثمّ «كل موجود عيّفهم — ضيف الناقص بس».
// لذلك: **لا يُعاد بناء أي قسم هنا.** الأقسام تُركَّب كما هي (نفس شيفرتها ونفس
// أرقامها) داخل بلاطات، والمكتوب هنا هو الناقص فقط: الحكم بجملة · جدول الرموز ·
// الحاجبون · صحّة الأسطول · المال · التغذية.
// القوانين من ورقتَي ٩٩ و٩٧: أرقام أجنبية (١) · صفر إنكليزي خام (١/٢ج) ·
// لا زرّ ميّت · لا حقل مخترع — والغياب يُعلَن غيابًا.
import { useEffect, useMemo, useState } from 'react'
import { DecisionDialsCard } from './Settings'
import { useStore } from '../core/store'
import { readGate } from '../core/gate'
import { TileBoard, useLayout, type Layout, type TileDef } from '../components/Tiles'
import { arabicHealth } from '../core/arabic'
import { priceText } from '../core/price'
import { CardBar, CardStatusPill, cardHint, sideAr, useCards } from '../components/TrendCard'
import { EarlyWarningStrip } from '../components/EarlyWarning'

// ── الأقسام تُركَّب كما هي ──
import Network from './Network'
import Charts from './Charts'
import Control from './Control'
import Analysis from './Analysis'
import Market from './Market'
import Risk from './Risk'
import Alerts from './Alerts'
import Monitor from './Monitor'
import Execution from './Execution'
import Atoms from './Atoms'
import Portfolios from './Portfolios'
import Log from './Log'
import Connection from './Connection'
import NQ from './NQ'

interface Account { account_id?: string; balance?: number; equity?: number }
interface Pos { symbol: string; profit?: number | null; swap?: number | null; commission?: number | null }
// ٢٠٢٦-٠٩-١٦ (حارس `check_dashboard_fields.py`): `floating_pnl` **ليس** من حقول
// `platform.positions.state` — ناشره الوحيد 609 لا يضعه (قِيست مفاتيحه كلّها).
// فكان سطر «الربح العائم» هنا يعرض «—» أبدًا مهما بلغ الربح أو الخسارة، وهو
// الكذب نفسه الذي أُصلح في «المحافظ» يوم ٠٩-١٠ وبقي حيًّا هنا. الناشر الصحيح
// `portfolio.pnl.state`، والبديل الصادق مجموع أرباح الصفقات كما تُحسب أدناه.
interface Positions { positions?: Pos[] }
interface PnlState { floating_pnl?: number }
interface Term { trade_allowed?: boolean }
interface Tg { running: boolean; paired: boolean; token: boolean }

const money = (n?: number | null) => (n == null ? '—'
  : n.toLocaleString('ar-EG-u-nu-latn', { minimumFractionDigits: 2, maximumFractionDigits: 2 }))
const int = (n?: number | null) => (n == null ? '—' : n.toLocaleString('ar-EG-u-nu-latn'))

// ٢٠٢٦-١٠-٠٨ (فكّ الأقسام عن القرار، ختم المالك «NQ»): أعمدة التحليل والثقة والبنية والاستراتيجيات والقرار وحاجبو 454 حُذفت — ناشروها (166 · 210 · 400 · 450 · 454) أُرشفوا؛ والقرار عمودٌ واحد من البطاقة 414.

function ageOfTick(ts: number, now: number): [string, string] {
  const ms = ts > 1e11 ? ts : ts * 1000
  const s = Math.max(0, (now - ms) / 1000)
  if (s < 3) return ['حيّ', 'var(--green)']
  if (s < 15) return [`${Math.round(s)} ث`, 'var(--green)']
  if (s < 60) return [`${Math.round(s)} ث`, 'var(--amber)']
  return [`${Math.round(s / 60)} د`, 'var(--red)']
}

// `t` = مصدر الرقم، يظهر عند المرور بالمؤشّر. رقمٌ ماليّ بلا مصدرٍ معروف
// يُقرأ يقينًا وهو ليس كذلك — ومصدره جزء من صدقه.
function Line({ k, v, c, t }: { k: string; v: string; c?: string; t?: string }) {
  return (
    <div title={t} style={{ display: 'flex', justifyContent: 'space-between', gap: 8, fontSize: 11.5, lineHeight: 1.6, minWidth: 0, padding: '0 9px' }}>
      <span className="dim" style={{ flex: 'none' }}>{k}</span>
      <span className="num" style={{ color: c, fontWeight: 600, textAlign: 'end', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{v}</span>
    </div>
  )
}

const DEFAULT_LAYOUT: Layout = {
  verdict: { x: 0, y: 0, w: 12, h: 1, on: true },
  symbols: { x: 0, y: 1, w: 7, h: 4, on: true },
  blockers: { x: 7, y: 1, w: 5, h: 2, on: true },
  money: { x: 7, y: 3, w: 5, h: 2, on: true },
  charts: { x: 0, y: 5, w: 7, h: 7, on: true },
  risk: { x: 7, y: 5, w: 5, h: 4, on: true },
  alerts: { x: 7, y: 9, w: 5, h: 3, on: true },
  fleet: { x: 0, y: 12, w: 4, h: 3, on: false },
  feed: { x: 4, y: 12, w: 4, h: 3, on: false },
  network: { x: 0, y: 12, w: 8, h: 6, on: false },
  analysis: { x: 0, y: 12, w: 12, h: 6, on: false },
  market: { x: 0, y: 12, w: 6, h: 5, on: false },
  execution: { x: 0, y: 12, w: 12, h: 6, on: false },
  control: { x: 0, y: 12, w: 12, h: 6, on: false },
  atoms: { x: 0, y: 12, w: 12, h: 6, on: false },
  portfolios: { x: 0, y: 12, w: 6, h: 4, on: false },
  log: { x: 0, y: 12, w: 6, h: 5, on: false },
  monitor: { x: 0, y: 12, w: 6, h: 5, on: false },
  connection: { x: 0, y: 12, w: 6, h: 4, on: false },
  nq: { x: 0, y: 12, w: 4, h: 5, on: false },
  dials: { x: 0, y: 12, w: 6, h: 5, on: false },
}

export default function Home({ onGo }: { onGo: (id: string) => void }) {
  const atoms = useStore((s) => s.atoms)
  const acc = useStore((s) => s.streams['platform.account.state']) as Account | undefined
  // ٢٠٢٦-١٠-٢٦ (قانون صفقات المالك، ختم «NQ»): صفقات المنظومة وحدها من حاسب الصفقات المفتوحة — صفقات المالك مفصولةٌ هناك.
  const posState = useStore((s) => s.streams['portfolio.open_positions.state']) as Positions | undefined
  const pnlState = useStore((s) => s.streams['portfolio.pnl.state']) as PnlState | undefined
  const term = useStore((s) => s.streams['platform.terminal_state']) as Term | undefined
  const risk = useStore((s) => s.risk)
  const gate = useStore((s) => s.gate)
  const market = useStore((s) => s.market)
  const conn = useStore((s) => s.conn)
  const flows = useStore((s) => s.flows)
  // ٢٠٢٦-١٠-٠٨ (فكّ الأقسام عن القرار، ختم المالك «NQ»): آخر بطاقة لكلّ رمز من 414 — حلّت محلّ أرقام الأهليّة 455/456 المؤرشفة.
  const cards = useCards()

  // ٢٠٢٦-٠٩-١٨: سطر «زوج التحوّط» حُذف — ناشره الوحيد ٥٧٨ أُرشف بأمر المالك
  // (`25b0cbb`). وكان يقول «لا زوج بعد» إلى الأبد، فيُقرأ انتظارًا لا غيابًا.
  const dialState = useStore((s) => s.streams['dial.profile.state']) as
    { profiles?: Array<{ dial?: number; hedge_target?: number }> } | undefined
  const profile = dialState?.profiles?.[0]
  const dialPct = typeof profile?.dial === 'number' ? profile.dial : null
  const hedge = typeof profile?.hedge_target === 'number' ? profile.hedge_target : null

  const [tg, setTg] = useState<Tg | null>(null)
  const [now, setNow] = useState(() => Date.now())
  const { layout, save, reset } = useLayout(DEFAULT_LAYOUT)

  useEffect(() => {
    let alive = true
    const ask = () => fetch('/gov/telegram').then((r) => r.json())
      .then((j: Tg) => { if (alive) setTg(j) }).catch(() => { if (alive) setTg(null) })
    ask()
    const id = window.setInterval(ask, 5000)
    return () => { alive = false; window.clearInterval(id) }
  }, [])
  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(id)
  }, [])

  const fleet = useMemo(() => {
    const sick: Array<{ id: number; name: string; state: string }> = []
    let running = 0
    for (const a of Object.values(atoms)) {
      if (a.state === 'running') running++
      const hs = a.health?.state
      if (hs && hs !== 'healthy') sick.push({ id: a.id, name: a.name_ar ?? a.name, state: hs })
    }
    sick.sort((x, y) => x.id - y.id)
    return { total: Object.keys(atoms).length, running, sick }
  }, [atoms])

  const cardList = useMemo(
    () => Object.values(cards).filter((c) => c?.symbol).sort((a, b) => String(a.symbol).localeCompare(String(b.symbol))),
    [cards])

  const symbols = useMemo(() => Object.keys(market).sort(), [market])
  const posBySym = useMemo(() => {
    const m: Record<string, { n: number; pnl: number }> = {}
    for (const p of posState?.positions ?? []) {
      const e = (m[p.symbol] ??= { n: 0, pnl: 0 }); e.n++; e.pnl += p.profit ?? 0
    }
    return m
  }, [posState])

  const feedAge = (...names: string[]) => {
    let best = Infinity
    for (const n of names) { const t = flows[n]; if (t) best = Math.min(best, (performance.now() - t) / 1000) }
    return best
  }
  const feedTxt = (age: number): [string, string] => {
    if (conn !== 'live') return ['لا نعرف', 'var(--dim)']
    if (age === Infinity) return ['صامت', 'var(--red)']
    if (age < 10) return ['حيّ', 'var(--green)']
    if (age < 60) return [`${Math.round(age)} ث`, 'var(--amber)']
    return [`${Math.round(age / 60)} د`, 'var(--red)']
  }

  const pnlList = posState?.positions
  const pnl = typeof pnlState?.floating_pnl === 'number'
    ? pnlState.floating_pnl
    : pnlList && pnlList.length
      ? pnlList.reduce((s, p) => s + (p.profit ?? 0) + (p.swap ?? 0) + (p.commission ?? 0), 0)
      : null
  const pnlFrom = typeof pnlState?.floating_pnl === 'number'
    ? 'من حاسب الربح والخسارة'
    : pnl != null ? 'مجموع أرباح الصفقات + السواب والعمولة' : 'ما وصل رقم'
  const kill = risk?.kill_switch_state === true
  // ٢٠٢٦-٠٩-٠٩ (ختم NQ): `execution.halted` غير موجود بحمولة ٥٥٠ الموحّدة
  // (مقيسًا على البثّ الحيّ)؛ `halted` الحقيقيّ ينشره ٥٥٢ ببوّابة التنفيذ.
  // ٢٠٢٦-١٠-٢٦ (فحص المشروع، ختم «nq اصلح»): علّتا «شو صاير» القديمتان كانتا هنا حيّتين — الغائب يُقرأ «مقفولة بقرارك»،
  // وإيقاف الحارس لحسابٍ يُقرأ «إيقاف طارئ… رفعه بيدك». القراءة الآن مشتركة مع «شو صاير» (`core/gate.ts`).
  const g = readGate(gate, atoms[552])

  const verdict: [string, string, string?] =
    conn !== 'live' ? ['⛔ النواة مقطوعة — ما في قراءة حيّة', 'var(--red)', 'شغّل «غرفة القيادة» أو افحص الاتصال']
      : kill ? ['🛑 التداول موقوف — قاطع الأمان مُفعَّل', 'var(--red)', 'التصفير بيدك من «المخاطر»']
        : g.ownerHalt ? ['🛑 إيقاف طارئ فعّال — كل الأوامر مقفولة', 'var(--red)', 'رفعه بيدك من «تحكّم»']
          : g.guardHalt ? ['⛔ موقوف بحارس — مش عطل', 'var(--red)', 'حارس أوقف الحساب لحاله — التفصيل في «شو صاير»']
            : !g.known ? ['⚠️ حال بوّابة التنفيذ غير مقروء', 'var(--amber)', 'ما وصلت حالها لهالشاشة — اقرأها من «التنفيذ»']
              : !g.open ? ['🔒 يحلّل ولا يفتح صفقات — البوّابة مقفولة', 'var(--amber)', 'فتحها من «التنفيذ» أو «تحكّم»']
                : fleet.sick.length ? [`⚠️ البوّابة مفتوحة — و${int(fleet.sick.length)} ذرّة مش سليمة`, 'var(--amber)', 'أسماؤها ببلاطة «صحّة الأسطول»']
                  : ['🟢 النظام شغّال — الأمر الصالح بيوصل للمنصّة فعليًّا', 'var(--green)']

  const th: React.CSSProperties = { padding: '3px 8px', textAlign: 'start', fontWeight: 500, borderBottom: '1px solid var(--glassb)', whiteSpace: 'nowrap' }
  const td: React.CSSProperties = { padding: '4px 8px', borderBottom: '1px solid var(--glassb)', whiteSpace: 'nowrap' }

  const defs: TileDef[] = [
    {
      id: 'verdict', title: 'الحكم بلمحة', go: 'control',
      render: () => (
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '4px 10px', minWidth: 0 }}>
          <span style={{ fontSize: 14, fontWeight: 800, color: verdict[1], whiteSpace: 'nowrap' }}>{verdict[0]}</span>
          {verdict[2] ? <span className="dim" style={{ fontSize: 11.5, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{verdict[2]}</span> : null}
        </div>
      ),
    },
    {
      id: 'symbols', title: 'الرموز — سعر · عمر · قرار البطاقة · مركز', go: 'decision',
      render: () => (
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12, tableLayout: 'fixed' }}>
          <thead>
            <tr className="dim" style={{ fontSize: 10.5 }}>
              <th style={{ ...th, width: '14%' }}>الرمز</th><th style={{ ...th, width: '18%' }}>السعر</th>
              <th style={{ ...th, width: '10%' }}>العمر</th><th style={{ ...th, width: '40%' }}>قرار البطاقة</th>
              <th style={{ ...th, width: '18%' }}>المركز</th>
            </tr>
          </thead>
          <tbody>
            {symbols.map((sym) => {
              const card = cards[sym]
              const p = posBySym[sym]
              const age = ageOfTick(market[sym].ts, now)
              const [sideTxt, sideTone] = sideAr(card?.side)
              return (
                <tr key={sym}>
                  <td style={{ ...td, fontWeight: 700 }}>{sym}</td>
                  {/* ٢٠٢٦-٠٩-١٠ (ختم NQ): كان `money` يقصّ السعر إلى خانتين،
                      فيرى المالك `EURUSD 1.16` و`GBPUSD 1.35` — سعرٌ لا يُقرأ.
                      الآن الدقّة من القيمة كما بثّتها النواة. */}
                  <td className="num" style={td}>{priceText(market[sym].bid)}</td>
                  <td className="num" style={{ ...td, color: age[1], fontSize: 11 }}>{age[0]}</td>
                  {/* البطاقة تعمل على رموزٍ محدّدة في إعدادها — وغيرها «لا بطاقة» لا حياد. */}
                  <td style={{ ...td, overflow: 'hidden', textOverflow: 'ellipsis' }} title={card ? cardHint(card.status) : undefined}>
                    {card
                      ? <><CardStatusPill status={card.status} style={{ fontSize: 10.5, padding: '0 6px' }} />{card.side ? <b style={{ color: `var(--${sideTone})`, marginInlineStart: 5 }}>{sideTxt}</b> : null}</>
                      : <span className="dim">لا بطاقة لهذا الرمز</span>}
                  </td>
                  <td className="num" style={{ ...td, color: p ? (p.pnl >= 0 ? 'var(--green)' : 'var(--red)') : 'var(--dim)', fontWeight: p ? 700 : 400 }}>
                    {p ? `${int(p.n)} · ${money(p.pnl)}` : '—'}
                  </td>
                </tr>
              )
            })}
            {symbols.length === 0 ? <tr><td style={td} colSpan={5} className="dim">بانتظار أوّل سعر من النواة…</td></tr> : null}
          </tbody>
        </table>
      ),
    },
    {
      id: 'blockers', title: 'مين واقف بوجه الصفقة', go: 'execution',
      render: () => (
        <div style={{ padding: '5px 9px' }}>
          {/* ١ — قرار البطاقة لكلّ رمز: «مفتوحة» صفقةٌ انبعتت، وغيرها سببُ عدم الدخول بجملة */}
          {cardList.length === 0 ? (
            <span className="dim" style={{ fontSize: 11.5 }}>
              {atoms[414] ? 'ما وصلت بطاقة منذ فتح الشاشة — تُكتب مع إغلاق كل شمعة ٥ دقائق' : 'بطاقة استمرار الاتّجاه (414) غير محمّلة'}
            </span>
          ) : cardList.map((c) => (
            <div key={c.symbol} style={{ fontSize: 11, marginBottom: 3, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}
              title={cardHint(c.status) || undefined}>
              <b className="num">{c.symbol}</b>{' '}
              <CardStatusPill status={c.status} style={{ fontSize: 10.5, padding: '0 6px' }} />{' '}
              <span className="dim">{cardHint(c.status)}</span>
            </div>
          ))}

          {/* ٢ — الأصل: مفعَّل أم مفصول عند بوّابة الأصول ٤٦٨ */}
          <div className="dim" style={{ fontSize: 10.5, marginTop: 5, borderTop: '1px solid var(--line)', paddingTop: 5 }}>
            {/* ٢٠٢٦-٠٩-٠٩ (ختم NQ): كانت رسالة الصحّة تُعرض خامًا بالإنكليزيّة
                (`PENDING_OR_ORPHANED_RESOLUTION` · `allowed=1 seen=12562 blocked=8790`)
                على لوحة مواصفتها عربيّة. المترجم `arabicHealth` موجود ويُستعمل
                في «تحكّم» و«التنفيذ» — ولم يكن موصولًا هنا.
                ٢٠٢٦-٠٩-١٨: وسطر «الأصل» من ٥٧٦ حُذف مع أرشفة الذرّة — بقيت
                بوّابة الأصول ٤٦٨ وحدها، وهي الحاكم الفعليّ لمرور التِكّة. */}
            <div style={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
              بوّابة الأصول (468): {arabicHealth(atoms[468]?.health?.message)}
            </div>
          </div>
        </div>
      ),
    },
    {
      id: 'money', title: 'المال', go: 'portfolios',
      render: () => (<div style={{ paddingTop: 4 }}>
        <Line k="حساب التنفيذ" v={(acc as { account_id?: string } | undefined)?.account_id ?? 'ما وصل'} />
        <Line k="القيمة / الرصيد" v={acc ? `${money(acc.equity)} · ${money(acc.balance)}` : '—'} />
        <Line
          k="الربح العائم"
          v={pnl == null ? 'ما وصل رقم' : `${pnl >= 0 ? '+' : ''}${money(pnl)}`}
          c={pnl == null ? 'var(--dim)' : pnl >= 0 ? 'var(--green)' : 'var(--red)'}
          t={pnlFrom}
        />
        <Line k="صفقات مفتوحة" v={int(posState?.positions?.length ?? null)} />
        <Line k="التعرّض / التحوّط" v={`${dialPct == null ? '—' : `${Math.round(dialPct)}%`} · ${hedge == null ? '—' : `${Math.round(hedge * 100)}%`}`} />
      </div>),
    },
    {
      id: 'fleet', title: 'صحّة الأسطول', go: 'atoms',
      render: () => (<div style={{ paddingTop: 4 }}>
        {/* ٢٠٢٦-٠٩-٠٩ (ختم NQ): كانت «مسجّلة» — والرقم هو المحمَّل بالنواة وحده
            (٢٢٨ مقيسًا) لا ما على القرص (٢٣٧). «مسجّلة» تُقرأ أنّها كلّ ذرّات
            المشروع، فتسعٌ غير محمَّلة تختفي بلا أثر. الاسم يطابق ما يُقاس. */}
        <Line k="محمَّلة / شغّالة" v={`${int(fleet.total)} · ${int(fleet.running)}`} />
        <Line k="مش سليمة" v={int(fleet.sick.length)} c={fleet.sick.length ? 'var(--red)' : 'var(--green)'} />
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 3, padding: '4px 9px' }}>
          {fleet.sick.map((s) => (
            <span key={s.id} className="num" title={`${s.name} — ${s.state}`}
              style={{ fontSize: 10.5, padding: '1px 5px', borderRadius: 5, border: '1px solid var(--glassb)', color: s.state === 'unhealthy' ? 'var(--red)' : 'var(--amber)' }}>{s.id}</span>
          ))}
        </div>
      </div>),
    },
    {
      id: 'feed', title: 'السوق والاتصال', go: 'market',
      render: () => (<div style={{ paddingTop: 4 }}>
        <Line k="الاتصال بالنواة" v={conn === 'live' ? 'حيّ' : conn === 'down' ? 'مقطوع' : 'جارٍ'} c={conn === 'live' ? 'var(--green)' : 'var(--red)'} />
        {(() => { const f = feedTxt(feedAge('feed.mt5.tick', 'platform.terminal_state', 'platform.account.state')); return <Line k="المنصّة" v={f[0]} c={f[1]} /> })()}
        {(() => { const f = feedTxt(feedAge('feed.ctrader.tick')); return <Line k="سي‑تريدر" v={f[0]} c={f[1]} /> })()}
        <Line k="تلغرام" v={!tg ? 'لا نعرف' : tg.running && tg.paired ? 'حيّ' : tg.running ? 'بلا اقتران' : tg.token ? 'متوقّف' : 'غير مفعّل'}
          c={tg?.running && tg?.paired ? 'var(--green)' : 'var(--amber)'} />
        <Line k="التداول عند المنصّة" v={term == null ? '—' : term.trade_allowed ? 'مسموح' : 'موقوف'} c={term?.trade_allowed ? 'var(--green)' : 'var(--amber)'} />
        <Line k="رموز تبثّ الآن" v={int(symbols.length)} />
      </div>),
    },

    { id: 'control', title: 'تحكّم', go: 'control', render: () => <Control /> },
    // ── الأقسام كما هي، بلا إعادة بناء ──
    { id: 'charts', title: 'الشارت', go: 'charts', render: () => <Charts /> },
    { id: 'risk', title: 'المخاطر', go: 'risk', render: () => <Risk /> },
    { id: 'alerts', title: 'التنبيهات', go: 'alerts', render: () => <Alerts /> },
    { id: 'network', title: 'الشبكة', go: 'network', render: () => <Network /> },
    { id: 'analysis', title: 'التحليل', go: 'analysis', render: () => <Analysis /> },
    { id: 'market', title: 'السوق', go: 'market', render: () => <Market /> },
    { id: 'execution', title: 'التنفيذ', go: 'execution', render: () => <Execution /> },
    { id: 'atoms', title: 'الذرات', go: 'atoms', render: () => <Atoms /> },
    { id: 'portfolios', title: 'المحافظ', go: 'portfolios', render: () => <Portfolios /> },
    { id: 'log', title: 'السجل', go: 'log', render: () => <Log /> },
    { id: 'monitor', title: 'المراقبة', go: 'monitor', render: () => <Monitor /> },
    { id: 'connection', title: 'الاتصال', go: 'connection', render: () => <Connection /> },
    { id: 'nq', title: 'ذرّة NQ', go: 'nq', render: () => <NQ /> },
    { id: 'dials', title: 'عيارات القرار', go: 'settings', render: () => <DecisionDialsCard /> },
  ]

  return (
    // ٢٠٢٦-٠٩-١٠ (بلاغ المالك «أكل كل صفحة على كلمتين، مافي دولاب لا تحت»):
    // الجذر كان `height: 100%` مع `overflow: hidden`، و`TileBoard` داخله يطلب
    // `height: 100%` أيضًا — فيقيسها على كامل الإطار لا على الباقي بعد شريطَي
    // الإنذار والقرار. النتيجة: الصفحة أطول من إطارها بـ70 بكسل مقيسة على
    // 1280×700، **والفائض يُقصّ بلا دولاب في أيّ مكان**. صار الجذر عمودًا
    // مرنًا واللوح يأخذ الباقي وحده (`flex: 1` + `minHeight: 0`)، فلا قصّ ولا
    // فائض. ولوح البطاقات يملك دولابه الداخليّ أصلًا.
    <div
      className="section"
      style={{
        height: '100%', width: '100%', minWidth: 0, minHeight: 0,
        display: 'flex', flexDirection: 'column', overflow: 'hidden',
      }}
    >
      {/* الإنذار المبكّر + شريط القرار العلويّ.
          ٢٠٢٦-١٠-٠٨ (فكّ الأقسام عن القرار، ختم المالك «NQ»): «الروم» (451) أُرشف — الشريط صار بطاقة 414. */}
      <EarlyWarningStrip />
      <CardBar />
      <div style={{ flex: 1, minHeight: 0, minWidth: 0, display: 'flex' }}>
        <div style={{ flex: 1, minHeight: 0, minWidth: 0 }}>
          <TileBoard defs={defs} layout={layout} save={save} reset={reset} onGo={onGo} />
        </div>
      </div>
    </div>
  )
}
