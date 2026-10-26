import Now from './sections/Now'
import NewDashboard from './sections/NewDashboard'
import { useEffect, useMemo, useRef, useState } from 'react'
import { useStore } from './core/store'
import { startEngine } from './core/engine'
import { dangerCommand } from './core/commands'
import { getTabOrder, TAB_ORDER_EVENT } from './core/appearance'
import TouchClipboard from './components/TouchClipboard'
import FeedLeds from './components/FeedLeds'
import AccountsBar from './components/AccountsBar'
import Network from './sections/Network'
import AtomModal from './sections/AtomModal'
import Diag from './sections/Diag'
import Stats from './sections/Stats'
import Log from './sections/Log'
import Portfolios from './sections/Portfolios'
import Connection from './sections/Connection'
import Alerts from './sections/Alerts'
import Market from './sections/Market'
import Monitor from './sections/Monitor'
import Settings from './sections/Settings'
import Security from './sections/Security'
import Charts from './sections/Charts'
import Atoms from './sections/Atoms'
import Analysis from './sections/Analysis'
import Lab from './sections/Lab'
import Backtest from './sections/Backtest'
import Structure from './sections/Structure'
import Liquidity from './sections/Liquidity'
import Statistics from './sections/Statistics'
import Probability from './sections/Probability'
import Strategies from './sections/Strategies'
import Decision from './sections/Decision'
import Risk from './sections/Risk'
import Execution from './sections/Execution'
import Home from './sections/Home'
import Scripts from './sections/Scripts'
import Control from './sections/Control'
import ChangeGovernor from './sections/ChangeGovernor'
import NQ from './sections/NQ'
import News from './sections/News'
// ٢٠٢٦-١٠-١٧ (ختم المالك «NQ»، الخطوة 22): سياق اليوم — الزمن والجلسات والعطل والأخبار والمستويات والسنين والأداء.
import DayContext from './sections/DayContext'
// ٢٠٢٦-١٠-٢٢ (ختم المالك «NQ»): الاتّجاه بنظرة واحدة — كلّ الفريمات على كلّ زوج.
import Direction from './sections/Direction'
// ٢٠٢٦-٠٩-٠٩ (أمر المالك): «ما ضلّ شي اسمه قسم كريبتو ولا أي شي بخصّه — فوركس
// على حلّ». فالشاشات الثلاث (الكون · الحواس · الحكم) أُرشفت لسطح المكتب، ومعها
// كل منطق السوق الثاني من هذا الملفّ: تبديل السوق · لوحة ألوان الكريبتو ·
// قائمة أقسامه · تبويب MEXC. كان منطقًا ميتًا مؤجَّلًا، وصار مرفوعًا.
import { applyColors, loadColors } from './core/appearance'

// أقسام اللوحة — القائمة القانونية انتقلت لـ core/sections.ts (يقرأها محرّر
// ترتيب التبويبات بالإعدادات كمان — بند ١٥ج بورقة ٩٩). «الشبكة» = النظام العام.
import { SECTIONS, FAMILIES, SECTION_FAMILY, type SectionFamily } from './core/sections'

const pad = (n: number, l: number) => String(n).padStart(l, '0')

type MarketInfo = {
  market: 'forex'
  label: string
}

export default function App() {
  const [active, setActive] = useState('dashboard')
  // العائلة المفتوحة في صفّ الملاحة الأوّل. ما لا عائلة له يقع في «تقنيّ».
  const familyOf = (id: string): SectionFamily => SECTION_FAMILY[id] ?? 'tech'
  const [family, setFamily] = useState<SectionFamily>('daily')
  const ACTIVE_TAB_KEY = 'nq.active_tab'
  const goTo = (id: string) => {
    setActive(id)
    // فتحُ صفحةٍ من زرٍّ داخل صفحةٍ أخرى يفتح عائلتها معها — وإلّا بقي الصفّ
    // الثاني على عائلةٍ لا تحوي المفتوح، فيبدو التبويب مختفيًا.
    setFamily(familyOf(id))
    if (marketInfo?.market === 'forex') {
      try { localStorage.setItem(`${ACTIVE_TAB_KEY}.forex`, id) } catch { /* التخزين المحلي اختياري */ }
    }
  }
  const [marketInfo, setMarketInfo] = useState<MarketInfo | null>(
    () => ({ market: 'forex', label: 'فوركس' }),
  )
  useEffect(() => {
    fetch('/gov/market', { cache: 'no-store' })
      .then((r) => r.ok ? r.json() as Promise<MarketInfo> : null)
      .then((info) => { if (info) setMarketInfo(info) })
      .catch(() => {})
  }, [])
  // تذكّر آخر تبويب للفوركس فقط؛ التحديث الكامل لا يعيد المالك إلى البداية.
  useEffect(() => {
    if (marketInfo?.market !== 'forex') return
    try {
      const saved = localStorage.getItem(`${ACTIVE_TAB_KEY}.forex`)
      // ٢٠٢٦-٠٩-١٦ — نقلةٌ لمرّة واحدة إلى «شو صاير» بعد حكم المالك «ما عم
      // افهم شي منهم»: من كان محفوظًا عنده تبويبٌ تقنيّ افتراضيّ (لم يختره
      // بنفسه، إنّما بقي من آخر فتحة) يُفتح له الجديد مرّةً واحدة فقط ثمّ
      // يُحترَم اختياره بعدها أبدًا. ولا تُمسّ التبويبات التي اختارها فعلًا.
      const MOVED = 'nq.moved_to_now'
      // ٢٠٢٦-١٠-٢٢: زرّ «صفحة الباك تست وحدها» يفتح النافذة على `?tab=backtest` والمنظومة مطفأة.
      const asked = new URLSearchParams(window.location.search).get('tab')
      if (asked) {
        setActive(asked)
        setFamily(familyOf(asked))
        return
      }
      let target = saved
      try {
        if (!localStorage.getItem(MOVED)) {
          localStorage.setItem(MOVED, '1')
          if (!saved || saved === 'home' || saved === 'dashboard') target = 'now'
        }
      } catch { /* التخزين المحلي اختياري */ }
      if (target) setActive(target)
    } catch { /* التخزين المحلي اختياري */ }
  }, [marketInfo?.market])
  useEffect(() => {
    if (marketInfo?.market !== 'forex') return
    try { localStorage.setItem(`${ACTIVE_TAB_KEY}.forex`, active) } catch { /* التخزين المحلي اختياري */ }
  }, [active, marketInfo?.market])

  // بند ١٥ج (ورقة ٩٩) — ترتيب التبويبات بيد المالك من «الإعدادات › تخصيص الشكل»
  const [tabOrder, setTabOrder] = useState<string[]>(() => getTabOrder(SECTIONS.map((s) => s[0])))
  useEffect(() => {
    const onChange = () => setTabOrder(getTabOrder(SECTIONS.map((s) => s[0])))
    window.addEventListener(TAB_ORDER_EVENT, onChange)
    return () => window.removeEventListener(TAB_ORDER_EVENT, onChange)
  }, [])
  const orderedSections = useMemo(
    () => tabOrder
      .map((id) => SECTIONS.find((s) => s[0] === id))
      .filter((s): s is [string, string, boolean] => s != null),
    [tabOrder],
  )
  useEffect(() => { applyColors(loadColors()) }, [])
  const clockRef = useRef<HTMLDivElement>(null)
  const staleRef = useRef<HTMLDivElement>(null)
  const shellRef = useRef<HTMLDivElement>(null)

  // ختم المالك 2026-08-20: الثيم ثابت «داكن» — أزرار الثيمات أُزيلت من الشريط،
  // والألوان تُضبط من «الإعدادات › تخصيص الشكل» (بند ١٥ بورقة ٩٩).
  useEffect(() => { document.documentElement.setAttribute('data-theme', 'dark') }, [])

  // مراقب النسخة: لمّا يتغيّر بناء اللوحة، تعيد التحميل لحالها (بلا Ctrl+F5 يدوي)
  useEffect(() => {
    const own = Array.from(document.querySelectorAll('script[type="module"]'))
      .map((s) => (s as HTMLScriptElement).src).find((s) => s.includes('/assets/index-'))
    let base = own ? own.split('/').pop() ?? '' : ''
    const id = window.setInterval(async () => {
      try {
        const r = await fetch('/gov/version', { cache: 'no-store' })
        const { v } = (await r.json()) as { v?: string }
        if (!v || v === '?') return
        if (!base) { base = v; return }
        if (v !== base) window.location.reload()
      } catch { /* الخادم مطفي */ }
    }, 7000)
    return () => clearInterval(id)
  }, [])

  // ٢٠٢٦-٠٩-٠٩ (ختم NQ) — تمييز «النواة ساقطة» من «النواة محجوبة».
  // قياس ثلاث جلسات متوازية اليوم أثبت أنّهما عرَضان مختلفان: مرّة يموت مقبس
  // الاستماع نفسه (لا `Listen` إطلاقًا)، ومرّة **يستمع المقبس والحلقة محجوبة**
  // فتسقط الطلبات بمهلة ومصافحة البثّ تفشل. الشريط كان يسمّي الحالتين
  // «⛔ شغّل غرفة القيادة» — وهي نصيحة خاطئة في الثانية: النواة تعمل وتتداول،
  // وإعادة التشغيل تدور بالمالك في حلقة عبثيّة. نسأل الحوكمة عن النواة (لا
  // نخمّن): تردّ ⇒ حيّة والبثّ وحده منقطع · تنتهي مهلتها ⇒ محجوبة · تردّ خطأً
  // ⇒ ساقطة. ولا يُسأل إلّا حين يظهر الانقطاع، وكل خمس ثوانٍ لا كل إطار.
  const coreProbeRef = useRef<'unknown' | 'alive' | 'blocked' | 'down'>('unknown')
  useEffect(() => {
    const id = window.setInterval(async () => {
      if (useStore.getState().conn === 'live') { coreProbeRef.current = 'unknown'; return }
      const ctrl = new AbortController()
      const to = window.setTimeout(() => ctrl.abort(), 4000)
      try {
        const r = await fetch('/gov/health', { cache: 'no-store', signal: ctrl.signal })
        coreProbeRef.current = r.ok ? 'alive' : 'down'
      } catch (e) {
        // الإجهاض = مهلة انتهت ⇒ الحلقة محجوبة؛ غيره ⇒ لا وصول أصلًا
        coreProbeRef.current = (e as Error)?.name === 'AbortError' ? 'blocked' : 'down'
      } finally { window.clearTimeout(to) }
    }, 5000)
    return () => window.clearInterval(id)
  }, [])

  useEffect(() => {
    const stopEngine = startEngine()
    let raf = 0
    const tick = () => {
      const d = new Date()
      if (clockRef.current) {
        clockRef.current.textContent =
          `${pad(d.getHours(), 2)}:${pad(d.getMinutes(), 2)}:${pad(d.getSeconds(), 2)}.${pad(d.getMilliseconds(), 3)}`
      }
      const { conn, lastMsgAt } = useStore.getState()
      // النواة تسقط والمخزن يحتفظ بآخر لقطة. اللافتة تعلن ذلك.
      // لا نعيد كتابة className كل إطار — هذا كان يقلب اللوحة سوداء.
      //
      // ٢٠٢٦-٠٩-٠٩ (ختم NQ) — **مقطوعة** و**متجمّدة** ليستا حالة واحدة:
      // القياس الحيّ على سجلّ النواة أظهر صمتًا ٤٠٪ من الوقت (٤٦٩ ثانية من
      // ١١٧٢) بفجوات تبلغ ٦٦ ثانية، تتكرّر كل دقيقتين تقريبًا وتستمرّ **بعد
      // إعادة التشغيل**. في هذه الفجوات يبقى المقبس مفتوحًا ولا تصل رسالة:
      //   · فكانت اللوحة تُبقي كل شيء أخضر وأرقامها مجمّدة بلا أيّ تحذير —
      //     وهذا أسوأ من الشريط الأحمر: طمأنينة كاذبة على أرقام ميّتة.
      //   · وإن أُغلق المقبس قالت «شغّل غرفة القيادة» — وإعادة التشغيل لا
      //     تنفع لأنّ العلّة تجمّد لا انقطاع، فيدور المالك في حلقة عبثيّة.
      // الآن يُقاس الصمت مستقلًّا عن حال المقبس، ويُقال باسمه.
      if (staleRef.current && shellRef.current) {
        const silentMs = lastMsgAt ? performance.now() - lastMsgAt : null
        // ⚠️ ٢٠٢٦-٠٩-٠٩ (ختم NQ) — تصحيح ذاتيّ مقيس: المحرّك يقوده
        // `requestAnimationFrame`، والمتصفّح **يوقفه تمامًا في تبويب مخفي**.
        // فترْكُ اللوحة في تبويب خلفي يجمّد `lastMsgAt` بلا أن تتجمّد النواة —
        // وكان هذا السطر سيعلن «النواة تجمّدت» وهي سليمة تمامًا: كذبٌ كنتُ
        // أزرعه بينما أصلح غيره. قِسته حيًّا: `document.hidden === true`
        // والبثّ واصل والنواة تردّ في 0.18 ث. فلا حكم على الصمت والصفحة مخفيّة.
        const pageHidden = typeof document !== 'undefined' && document.hidden === true
        const stalled = conn === 'live' && !pageHidden && silentMs != null && silentMs > 15000
        const frozen = conn === 'down' || stalled
        const wantShell = frozen ? 'shell frozen' : 'shell'
        const wantBan = frozen ? 'staleban on' : 'staleban'
        if (shellRef.current.className !== wantShell) shellRef.current.className = wantShell
        if (staleRef.current.className !== wantBan) staleRef.current.className = wantBan
        if (frozen) {
          const secs = lastMsgAt ? Math.floor((performance.now() - lastMsgAt) / 1000) : null
          const since = secs === null ? null
            : secs < 60 ? `${secs} ثانية`
            : secs < 3600 ? `${Math.floor(secs / 60)} دقيقة`
            : `${Math.floor(secs / 3600)} ساعة و${Math.floor((secs % 3600) / 60)} دقيقة`
          const probe = coreProbeRef.current
          const text = stalled
            ? `⏸️ النواة متّصلة وصامتة منذ ${since} — تجمّدت، ما انقطعت. الأرقام معروضة قديمة. إعادة التشغيل لا تحلّ هذا.`
            : probe === 'blocked'
              ? `⏸️ النواة تعمل وحلقتها محجوبة — لا تردّ منذ ${since ?? 'قليل'}. تتداول وأنت لا تراها. إعادة التشغيل لا تحلّ هذا.`
              : probe === 'alive'
                ? `⚠️ النواة حيّة والبثّ وحده منقطع منذ ${since ?? 'قليل'} — الأرقام المعروضة قديمة. اللوحة تعيد الوصل وحدها.`
                : since === null
                  ? '⛔ النواة غير متّصلة — شغّل غرفة القيادة. المختبر يشتغل بدونها.'
                  : `⛔ النواة مقطوعة منذ ${since} — الأرقام الحيّة مجمّدة. المختبر يشتغل على بيانات تاريخية.`
          if (staleRef.current.textContent !== text) staleRef.current.textContent = text
        }
      }
      // ٢٠٢٦-٠٩-٠٣: مؤشّرات الاستلام رجعت للشريط العلوي — بلاطة التغذية
      // بالرئيسية مطفية افتراضيًا والمالك ما عنده عين غير اللوحة.
      raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => { cancelAnimationFrame(raf); stopEngine() }
  }, [marketInfo?.market])

  const activeLabel = SECTIONS.find((s) => s[0] === active)?.[1] ?? ''

  return (
    <div className="shell" ref={shellRef}>
      <div className="staleban" ref={staleRef} />
      <header className="hdr">
        <div className="brand">
          <span className="nqmark">NQ</span>
          <span className="nqname">غرفة القيادة الكمّية</span>
          <small>محمد رزوق</small>
        </div>
        {marketInfo && (
          <div className="market-switch" title="هذه اللوحة معزولة عن السوق الآخر">
            {marketInfo.label} · لوحة مستقلة
          </div>
        )}
        <button
          className="refreshbtn"
          title="تحديث كامل — يعيد تحميل اللوحة وكل البيانات من النواة"
          onClick={() => window.location.replace('/?v=' + Date.now())}
        >🔄 تحديث</button>
        <button
          className="haltbtn"
          title="يوقف كل إرسال الأوامر فورًا — عبر بوّابة الأوامر (901) بتأكيد"
          onClick={async () => { const r = await dangerCommand('halt'); if (r.message) window.alert(r.message) }}
        >⛔ إيقاف طارئ</button>
        <div className="hdr-right">
          <AccountsBar />
          <FeedLeds />
          <div className="clock num" ref={clockRef}>--:--:--.---</div>
        </div>
      </header>

      {/* ٢٠٢٦-٠٩-١٨ («صارت كم حال من تكرار… خفّف»): صفّان بدل حائطٍ من ٣٢ زرًّا.
          الأوّل عائلات، والثاني تبويبات العائلة المفتوحة وحدها. ولا تبويب
          يُحذف: من يبحث عن صفحةٍ يجدها في عائلتها، ومن يفتحها من زرٍّ داخل
          صفحةٍ أخرى تُفتح عائلتها معها تلقائيًّا (`goTo` أدناه). */}
      <nav className="nav nav-families">
        {FAMILIES.map(([key, label]) => {
          const count = orderedSections.filter(([id]) => familyOf(id) === key).length
          return (
            <button
              key={key}
              className={family === key ? 'active' : ''}
              onClick={() => setFamily(key)}
              title={`${count} صفحة`}
            >
              {label} <span className="dim num" style={{ fontSize: 10.5 }}>{count}</span>
            </button>
          )
        })}
      </nav>
      <nav className="nav">
        {orderedSections.filter(([id]) => familyOf(id) === family).map(([id, label, on]) => (
          <button key={id} className={active === id ? 'active' : ''} disabled={!on} onClick={() => on && goTo(id)}>
            {on ? label : `${label} · قريبًا`}
          </button>
        ))}
      </nav>

      <main className="workspace">
        {active === 'now' ? (
          <Now onGo={goTo} />
        ) : active === 'dashboard' ? (
          <NewDashboard />
        ) : active === 'direction' ? (
          <Direction />
        ) : active === 'context' ? (
          <DayContext />
        ) : active === 'home' ? (
          <Home onGo={goTo} />
        ) : active === 'control' ? (
          <Control />
        ) : active === 'change' ? (
          <ChangeGovernor />
        ) : active === 'network' ? (
          <Network />
        ) : active === 'atoms' ? (
          <Atoms />
        ) : active === 'market' ? (
          <Market />
        ) : active === 'charts' ? (
          <Charts />
        ) : active === 'analysis' ? (
          <Analysis />
        ) : active === 'lab' ? (
          <Lab />
        ) : active === 'backtest' ? (
          <Backtest />
        ) : active === 'structure' ? (
          <Structure />
        ) : active === 'liquidity' ? (
          <Liquidity />
        ) : active === 'statistics' ? (
          <Statistics />
        ) : active === 'probability' ? (
          <Probability />
        ) : active === 'strategies' ? (
          <Strategies />
        ) : active === 'decision' ? (
          <Decision />
        ) : active === 'risk' ? (
          <Risk />
        ) : active === 'execution' ? (
          <Execution />
        ) : active === 'diag' ? (
          <Diag />
        ) : active === 'stats' ? (
          <Stats />
        ) : active === 'log' ? (
          <Log />
        ) : active === 'portfolios' ? (
          <Portfolios />
        ) : active === 'connection' ? (
          <Connection />
        ) : active === 'alerts' ? (
          <Alerts />
        ) : active === 'monitor' ? (
          <Monitor />
        ) : active === 'settings' ? (
          <Settings />
        ) : active === 'security' ? (
          <Security />
        ) : active === 'scripts' ? (
          <Scripts />
        ) : active === 'news' ? (
          <News />
        ) : active === 'nq' ? (
          <NQ />
        ) : (
          <div className="placeholder">
            <div className="ph-title">قسم «{activeLabel}»</div>
            <div className="ph-sub">لسا مو مبني — يُركَّب فوق نفس البنية لمّا يجي دورو.</div>
          </div>
        )}
      </main>

      <footer className="status">
        <span>طبقة الحوكمة التفاعلية</span>
        <span className="grow">السوق: <span className="num">{marketInfo?.label ?? '...'}</span> · الحوكمة لا تخزّن — كل رقم من نظامك الحيّ</span>
      </footer>

      <AtomModal />
      <TouchClipboard />
    </div>
  )
}
