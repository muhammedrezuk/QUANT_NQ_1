// الحسابان جنب بعض — عين المالك على التحليل مقابل التنفيذ.
// سي-تريدر = بيانات فقط. ميتاتريدر 5 = اللي بتنفتح عليه الصفقة.
// الأرقام من البثّ كما وصلت — الغائب يُعلَن غيابًا، لا اختراع.
import { useEffect, useState } from 'react'
import { useStore, atomStale, atomPartial } from '../core/store'

type Live = 'live' | 'partial' | 'silent' | 'unknown' | 'stale'

export type TwinAccounts = {
  analysisId: string | null
  analysisBroker: string | null
  execId: string | null
  execBroker: string | null
  execEquity: number | null
  execConnected: boolean | null
  tradeAllowed: boolean | null
  analysisLive: Live
  execLive: Live
  sameNumber: boolean
}

const asId = (v: unknown): string | null => {
  if (v == null || v === '') return null
  const s = String(v).trim()
  return s ? s : null
}

function liveOf(conn: string, flows: Record<string, number>, name: string, now: number): Live {
  if (conn !== 'live') return 'unknown'
  const t = flows[name]
  if (t == null) return 'silent'
  return (now - t) / 1000 < 30 ? 'live' : 'silent'
}

// الشارة تُخضِع التدفّق لحكم مصدره: مصدرٌ بائت ⇒ «بائت» لا «حيّ».
// السبب والقياس في تعريف `atomStale` بـ`core/store.ts`.

export function useTwinAccounts(): TwinAccounts {
  const conn = useStore((s) => s.conn)
  const flows = useStore((s) => s.flows)
  const analysis = useStore((s) => s.analysis)
  const rooms = useStore((s) => s.room)
  const fusion = useStore((s) => s.sectionFusion)
  const ct = useStore((s) => s.streams['feed.ctrader.tick']) as { account_id?: unknown; broker?: unknown } | undefined
  const term = useStore((s) => s.streams['platform.terminal_state']) as
    | { account_id?: unknown; connected?: boolean; trade_allowed?: boolean }
    | undefined
  const acc = useStore((s) => s.streams['platform.account.state']) as
    | { account_id?: unknown; broker?: unknown; equity?: number }
    | undefined
  const [now, setNow] = useState(() => performance.now())
  useEffect(() => {
    const id = window.setInterval(() => setNow(performance.now()), 1000)
    return () => window.clearInterval(id)
  }, [])

  const firstAnalysis = Object.values(analysis)[0]
  const firstRoom = Object.values(rooms)[0]
  const firstFusion = Object.values(fusion)[0]

  const analysisId = asId(ct?.account_id)
    ?? asId(firstAnalysis?.account_id)
    ?? asId(firstRoom?.account_id)
    ?? asId(firstFusion?.account_id)
  const analysisBroker = asId(ct?.broker) ?? asId(firstRoom?.broker) ?? asId(firstFusion?.broker)
  const execId = asId(term?.account_id) ?? asId(acc?.account_id)
  const execBroker = asId(acc?.broker)
  const execEquity = typeof acc?.equity === 'number' ? acc.equity : null
  const execConnected = term ? !!term.connected : null
  const tradeAllowed = term ? !!term.trade_allowed : null
  // 622 مصدر تغذية سي‑تريدر · 619 حالة حساب ميتاتريدر.
  // لماذا 619 لا 618: `updated_at` الذي يقرؤه 619 يكتبه الإكسبرت بـ`TimeGMT()`
  // — ساعة UTC صادقة — فيقيس `official − updated_at` عمرًا حقيقيًّا. أمّا
  // طوابع 618 فمن `MqlTick.time_msc` بوقت **خادم الوسيط** (مقيس على +3 ساعات
  // لهذا الوسيط)، فلا تصلح مقياس عمر، و618 لا يملك إلّا أثر آخر نشر — وهو
  // يعمى عن طابور متراكم. راجع `atomStale` بـ`core/store.ts`.
  const src622 = useStore((s) => s.atoms[622])
  const acct619 = useStore((s) => s.atoms[619])
  // ٢٠٢٦-٠٩-٠٩ (بلاغ المالك «سوق مثل نار» والشارة تقول بائت): ثلاث حالات
  // لا اثنتان. `degraded` عند 622 تعني رمزًا نائمًا خارج جلسته وقد سمّاه —
  // تنبيهٌ جزئيّ لا موت. و`unhealthy` وحدها موت. التفصيل في `atomStale`.
  //
  // وميتاتريدر يبقى حكمه عند 619 (`updated_at` بـ`TimeGMT`): تدفّقه يكذب —
  // يستهلك طابورًا متراكمًا فيبدو حيًّا وهو يبثّ الأمس. وحسابه واحد لا
  // رموز، فبياتُه بياتٌ كامل لا جزئيّ.
  const analysisFlow = liveOf(conn, flows, 'feed.ctrader.tick', now)
  const analysisLive: Live = atomStale(src622)
    ? 'stale'
    : (atomPartial(src622) && analysisFlow === 'live' ? 'partial' : analysisFlow)
  const execLive: Live = (atomStale(acct619) || atomPartial(acct619))
    ? 'stale'
    : liveOf(conn, flows, 'feed.mt5.tick', now)
  const sameNumber = !!(analysisId && execId && analysisId === execId)

  return {
    analysisId, analysisBroker, execId, execBroker, execEquity,
    execConnected, tradeAllowed, analysisLive, execLive, sameNumber,
  }
}

// «بائت» = التدفّق واصل والبيانات قديمة. أخطر من «صامت»: الصمت يُرى، والبيات
// يتنكّر حياةً — فيأخذ الأحمر ولا يُخفَّف. و«جزئيّ» أصفر: التغذية حيّة ورمزٌ
// نائم خارج جلسته — لا يُلوَّن أحمر فيصير إنذارًا يُعلَّم تجاهله.
const LIVE_AR: Record<Live, string> = {
  live: 'حيّ', partial: 'جزئيّ', silent: 'صامت', stale: 'بائت', unknown: 'لا نعرف',
}
const liveTone = (v: Live) =>
  (v === 'live' ? 'green' : v === 'partial' ? 'amber' : v === 'unknown' ? 'dim' : 'red')

export default function AccountsBar() {
  const a = useTwinAccounts()
  return (
    <div className="acctbar" aria-label="حساب التحليل وحساب التنفيذ">
      <span
        className={`acctchip analysis ${liveTone(a.analysisLive)}`}
        title="سي-تريدر — بيانات وتحليل فقط. ما بتنفتح عليه صفقة."
      >
        <i className="feeddot" />
        <b>تحليل</b>
        <em className="num">{a.analysisId ?? '—'}</em>
        <small>{LIVE_AR[a.analysisLive]}</small>
      </span>
      <span
        className={`acctchip exec ${a.execConnected === false ? 'red' : liveTone(a.execLive)}`}
        title="ميتاتريدر 5 — حساب التنفيذ. عليه بتنفتح الصفقة فعليًّا."
      >
        <i className="feeddot" />
        <b>تنفيذ</b>
        <em className="num">{a.execId ?? '—'}</em>
        <small>{a.execConnected === false ? 'مقطوع' : LIVE_AR[a.execLive]}</small>
      </span>
      {/* ٢٠٢٦-٠٩-١٠ (حكم المالك: «نفس الرقم… هي من لمّا كانت موجودة، لا هلق
          فوق ما بتقول غير نفس رقم»): الشارة كانت تقول «نفس الرقم» وحدها —
          جملةٌ لا تقول شيئًا لمن لا يعرف السياق. صارت تقول **ماذا يعني ذلك**
          و**ما أثره**، والرقم نفسه فيها. */}
      {a.sameNumber ? (
        <span className="acctchip amber"
          title="التصميم يفترض حسابين منفصلين: واحد للتحليل (سي-تريدر) وآخر للتنفيذ (ميتاتريدر). وجودهما برقم واحد يعني أنّ ما تراه تحليلًا وما يُنفَّذ يقرآن الحساب نفسه.">
          ⚠️ حساب واحد للتحليل والتنفيذ ({a.execId})
        </span>
      ) : null}
    </div>
  )
}

const money = (n: number) => n.toLocaleString('ar-EG-u-nu-latn', { minimumFractionDigits: 2, maximumFractionDigits: 2 })

export function AccountsPair() {
  const a = useTwinAccounts()
  return (
    <div className="acctpair">
      <div className="scard acctcard analysis">
        <div className="st">حساب التحليل — سي‑تريدر</div>
        <div className={`sv num ${liveTone(a.analysisLive)}`}>{a.analysisId ?? 'ما وصل'}</div>
        <div className="ss">بيانات وأسعار فقط — ما بتنفتح عليه صفقة أبدًا.</div>
        <div className="ss">{a.analysisBroker ? `الوسيط ${a.analysisBroker} · ` : ''}التغذية {LIVE_AR[a.analysisLive]}</div>
      </div>
      <div className="scard acctcard exec">
        <div className="st">حساب التنفيذ — ميتاتريدر 5</div>
        <div className={`sv num ${a.execConnected === false ? 'red' : liveTone(a.execLive)}`}>{a.execId ?? 'ما وصل'}</div>
        <div className="ss">عليه تُفتح الصفقات فعليًّا — منفصل عن التحليل.</div>
        <div className="ss">
          {a.execConnected == null ? 'الاتصال: ما وصل' : a.execConnected ? 'المنصّة متّصلة' : 'المنصّة مقطوعة'}
          {a.tradeAllowed == null ? '' : a.tradeAllowed ? ' · التداول مسموح' : ' · التداول موقف'}
          {a.execEquity != null ? ` · القيمة ${money(a.execEquity)}` : ''}
          {a.execBroker ? ` · ${a.execBroker}` : ''}
        </div>
      </div>
      {a.sameNumber ? (
        <div className="ss" style={{ gridColumn: '1 / -1', color: 'var(--amber)' }}>
          ⚠️ رقم الحساب واحد على الدورين. التصميم حسابان منفصلان: تحليل ≠ تنفيذ.
        </div>
      ) : null}
    </div>
  )
}
