// المحرّك الحيّ (١٤ §٦): WS → طابور → requestAnimationFrame → تحديث واحد لكل إطار.
// مهما انهمر البثّ، تصريف واحد لكل إطار شاشة — لا سحب دوري، لا رسم لكل حدث.
import { useStore, type AtomRec } from './store'
import { connectWs, govGet, type WsMsg } from './transport'
import { labelOf } from './i18n'

// أحداث مهمّة للمراقبة (بلا ضجيج التكّات/الساعة/الحالات المستمرّة)
// system.alert = تنبيه المُنذِر (831) لحظة صدور، بلا .state (الحالة ليست حدث مراقبة)
// إصلاح م-6 (ورقة ٤١، أمر المالك 2026-08-28): تصعيد المالك واستنفاد زوج التحوّط
// كانا يُنشران ولا يظهران بأي مكان — النظام «يصرخ» واللوحة لا تسمعه.
// ٢٠٢٦-٠٩-١٨: `perpetual.owner.escalation` و`perpetual.pair.state` خرجا من
// هنا — ناشرهما الوحيد ٥٧٨ أُرشفت بأمر المالك (`25b0cbb`)، فبقاؤهما يجعل
// المحرّك يترقّب حدثًا لا ناشرَ له.
const IMPORTANT = /provider_down|provider_recovered|feed_interrupted|feed_recovered|halt|order\.|execution\.|trade\.|\.rejected|hot_loaded|hot_unloaded|reloaded|system\.alert(?!\.state)|atom\.(started|stopped|failed|restarted|unhealthy)/i

// حزمة ج (ختم 22): أحداث القرار والتنفيذ التي تحمل `symbol` وتحتاج مفتاحًا مستقلًا لكل
// رمز (لا "آخر قيمة عامّة" مثل streams). عقود الأحداث مقروءة من الكود الفعلي لناشريها.
const SYMBOL_KEYED = new Set([
  // ٢٠٢٦-١٠-٠٨ (فكّ الأقسام عن القرار، ختم المالك «NQ»): سلسلة 450-458 و463 و466 و581 أُرشفت فخرجت أحداثها من هنا؛ والقرار من البطاقة 414.
  'strategy.card.state',             // 414 — بطاقة استمرار الاتّجاه لكلّ شمعة 5 د (حالتها وسببها وأرقامها)
  'decision.approved.state',         // 414 — الموافقة بالجهة والوقف والهدف (كانت من 466)
  'decision.gate.passed',            // 467 — بوابة (مرّت)
  'decision.gate.blocked',           // 467 — بوابة (محجوبة)
  'decision.gate.recorded',          // 467 — بوابة (انتظار مسجَّل)
  'execution.order.requested',       // 555 — طلب أمر الدخول (يحمل معرّف القرار = معرّف البطاقة)
  'knowledge.levels.state',          // 124 — المستويات الستّ والحركة لكلّ أصل (١٠-١٧، الخطوة 22)
  'structure.direction.state',       // 211 — كلّ فريم صاعد أو هابط لكلّ زوج (١٠-٢٢)
  // ٢٠٢٦-١٠-٠٩ (ختم المالك «NQ» — إلغاء مفاتيح السرعة إلى الأرشيف): `horizon.profile.state` خرج — ظلّ شخصيّة
  // الأفق أُرشف مع مفتاح الأفق، و523 لم يعد ينشره.
  // ٢٠٢٦-٠٩-١٨: `perpetual.entry.state` كان هنا لـ٥٧٦، وقد أُرشفت بأمر
  // المالك (`25b0cbb`) — والتفعيل الساري يُقرأ من بوّابة الأصول ٤٦٨ وحدها.
  // ٢٠٢٦-٠٩-٠٩ (أمر المالك «ما ضلّ شي اسمه قسم كريبتو»): أربع بطاقات كريبتو
  // كانت هنا، ولا ناشر لها على الناقل — مقيسًا بالمانيفستات وبالبثّ الحيّ.
])

// تفصيل موجز لحدث المراقبة من حمولته الحقيقيّة (رمز · جهة · سبب) — بلا حساب،
// نقل ما وصل فقط. الغياب يبقى غيابًا (بند 17 بدفتر 97: سطر الحدث كان بلا أي تفصيل).
function eventDetail(payload: unknown): string | undefined {
  if (!payload || typeof payload !== 'object') return undefined
  const p = payload as Record<string, unknown>
  const parts: string[] = []
  if (typeof p.symbol === 'string' && p.symbol) parts.push(p.symbol)
  if (p.side === 'BUY') parts.push('شراء')
  else if (p.side === 'SELL') parts.push('بيع')
  if (typeof p.reason === 'string' && p.reason) parts.push(String(p.reason))
  return parts.length ? parts.join(' · ') : undefined
}

/** يسطّح `risk.unified.state` — ٢٠٢٦-٠٩-٠٩ (ختم NQ).
 *  العلّة المقيسة: اللوحة تقرأ `kill_switch_state` و`daily_loss_pct`
 *  و`consecutive_losses` من جذر الحمولة، و٥٠٠ صار مجمِّعًا ينشرها داخل
 *  `accounts[<رقم الحساب>].risk`. فالجذر `undefined` دائمًا: قاطع الأمان
 *  لا يُعلَن مفعَّلًا أبدًا (الرئيسيّة تقول «🟢 النظام شغّال» وهو موقوف)،
 *  وقسم المخاطر يعرض صفرًا أبديًّا. نُجمّع هنا بأمانة: قاطع الأمان مفعَّل إن
 *  فعّله **أيّ** حساب، والخسارة أسوأ خسارة، والخسائر المتتالية أطول سلسلة،
 *  والصفقات مجموعها. وإن لم تصل `accounts` تُمرَّر الحمولة كما هي — لا اختراع. */
function flattenRisk(payload: unknown): unknown {
  if (!payload || typeof payload !== 'object') return payload
  const p = payload as Record<string, unknown>
  const accounts = p.accounts && typeof p.accounts === 'object'
    ? (p.accounts as Record<string, Record<string, unknown>>) : null
  if (!accounts) return p
  let seen = false
  let kill = false
  let killReason = ''
  let loss: number | undefined
  let streak: number | undefined
  let trades: number | undefined
  for (const entry of Object.values(accounts)) {
    const r = entry?.risk && typeof entry.risk === 'object'
      ? (entry.risk as Record<string, unknown>) : null
    if (!r) continue
    seen = true
    if (r.kill_switch_state === true) {
      kill = true
      if (typeof r.kill_switch_reason === 'string' && r.kill_switch_reason) killReason = r.kill_switch_reason
    }
    if (typeof r.daily_loss_pct === 'number') loss = loss == null ? r.daily_loss_pct : Math.min(loss, r.daily_loss_pct)
    if (typeof r.consecutive_losses === 'number') streak = Math.max(streak ?? 0, r.consecutive_losses)
    if (typeof r.daily_trade_count === 'number') trades = (trades ?? 0) + r.daily_trade_count
  }
  if (!seen) return p
  return {
    ...p,
    kill_switch_state: kill,
    kill_switch_reason: killReason,
    daily_loss_pct: loss,
    consecutive_losses: streak,
    daily_trade_count: trades,
  }
}

function enrich(atoms: AtomRec[], names: Record<number, string>): AtomRec[] {
  for (const a of atoms) {
    a.name_ar = names[a.id] ?? a.name
    const [txt, color] = labelOf(a)
    a.label_ar = txt
    a.color = color
  }
  return atoms
}

/** يبدأ المحرّك: يفتح البثّ، يجمّع الرسائل بطابور، يصرّفها مرّة كل إطار. يرجّع دالة إيقاف. */
export function startEngine(): () => void {
  const queue: WsMsg[] = []
  let raf = 0

  const pump = () => {
    if (queue.length) {
      const st = useStore.getState()
      let snapAtoms: AtomRec[] | null = null
      let snapMetrics: unknown = undefined
      const events: Array<[string, unknown]> = []
      for (const m of queue) {
        if (m.type === 'snapshot') { snapAtoms = m.atoms as AtomRec[]; snapMetrics = m.metrics }
        else events.push([m.name, m.payload])
        // ٢٠٢٦-٠٩-٠٩ (ختم NQ): صحّة البثّ من ترويسة كل رسالة — النواة تُرقّم
        // كل رسالة (`stream_sequence`) وتعلن الفقد (`dropped_total` و
        // `stream_gap`) حين يمتلئ طابورها، ولم يكن أيّ من الثلاثة يُقرأ:
        // تسقط أحداث والشاشة خضراء كاملة المظهر. تُقرأ من **كل** رسالة
        // بالترتيب لا من آخرها وحدها، وإلّا ضاعت فجوة واقعة داخل نفس الإطار.
        st.markStream(m.stream_sequence, m.dropped_total, m.stream_gap)
      }
      queue.length = 0
      st.markMsg()
      if (snapAtoms) st.setSnapshot(enrich(snapAtoms, st.namesAr), snapMetrics)
      const fired: string[] = []
      for (const [name, payload] of events) {
        st.setEvent(name, payload)
        fired.push(name)
        if (name === 'market.tick') {
          const p = payload as { symbol?: string; bid?: number; ask?: number; timestamp?: number; received_at?: number }
          if (p.symbol && typeof p.bid === 'number' && typeof p.ask === 'number') {
            st.setMarketTick(p.symbol, p.bid, p.ask, p.timestamp ?? p.received_at ?? 0)
          }
        }
        // تنفيذ ميتاتريدر على خريطة منفصلة عن تحليل سي‑تريدر:
        // feed.mt5.tick (618) هو التِكّ الحيّ؛ market.broker_tick يبقى توافقًا إن وصل.
        // لا يُدمجان مع market.tick ولا يُحوَّل طابعهما.
        if (name === 'feed.mt5.tick' || name === 'market.broker_tick') {
          const p = payload as { symbol?: string; bid?: number; ask?: number; spread?: number; provider?: string; timestamp?: number; received_at?: number }
          if (p.symbol && typeof p.bid === 'number' && typeof p.ask === 'number') {
            st.setBrokerTick(p.symbol, p.bid, p.ask,
              typeof p.spread === 'number' ? p.spread : p.ask - p.bid,
              p.provider ?? (name === 'feed.mt5.tick' ? 'mt5' : 'الوسيط'),
              p.timestamp ?? p.received_at ?? 0)
          }
        }
        if (name === 'analysis.raw.completed') {
          const p = payload as { account_id?: string; symbol?: string; timeframe?: string }
          if (p && p.symbol) {
            const scope = `${p.account_id ?? 'بلا حساب'}::${p.symbol}`
            st.setAnalysis(scope, payload as never)
            // بند أ١١ — جسم القسم من ١٦٦ (timeframe="section"): الثماني المدموجة
            // + بطاقتا المسارين {fast, slow} كما وصلت — يُخزَّن على حدة بلا حساب.
            if (p.timeframe === 'section') st.setSectionFusion(scope, payload as never)
          }
        }
        // §١٨/§١٩ — بطاقة القسم الحيّة تصل كما بناها `section_contract`.
        // ⛔ الواجهة لا تحسب اتجاهًا ولا ثقةً ولا عمقًا ولا وزنًا؛ تعرض ما وصل.
        if (name.endsWith('.section.live')) {
          const p = payload as { account_id?: string; broker?: string; symbol?: string; section_id?: string }
          if (p && p.account_id && p.broker && p.symbol && p.section_id) {
            st.setSectionCard(`${p.account_id}::${p.broker}::${p.symbol}::${p.section_id}`, payload as never)
          }
        }
        // إقفال 150 مرحلة ٢: الروم المتدفّق — قرار حيّ متدرّج بلا انتظار أحد.
        if (name === 'decision.room.state') {
          const p = payload as { account_id?: string; broker?: string; symbol?: string }
          if (p && p.symbol) st.setRoom(`${p.account_id ?? ''}::${p.broker ?? ''}::${p.symbol}`, payload as never)
        }
        // إقفال 150 مرحلة ٣: لوحة المحلّلين — كل محلّل يعلن نفسه.
        if (name === 'analysis.analysts.state') {
          const p = payload as { account_id?: string; broker?: string; symbol?: string }
          if (p && p.symbol) st.setAnalysts(`${p.account_id ?? ''}::${p.broker ?? ''}::${p.symbol}`, payload as never)
        }
        if (name === 'market.structure.updated') {
          const p = payload as { symbol?: string }
          if (p && p.symbol) st.setStructure(p.symbol, payload as never)
        }
        if (name === 'market.liquidity.updated') {
          const p = payload as { symbol?: string }
          if (p && p.symbol) st.setLiquidity(p.symbol, payload as never)
        }
        // ٢٠٢٦-٠٩-٠٩: لوحة وحدات ٢٥٠ — تُنشر منذ ٢٦-٠٨ وما كان لها قارئ.
        if (name === 'liquidity.units.state') {
          const p = payload as { symbol?: string }
          if (p && p.symbol) st.setLiquidityUnits(p.symbol, payload as never)
        }
        if (name === 'stats.cycle.collected') {
          const p = payload as { symbol?: string }
          if (p && p.symbol) st.setStats(p.symbol, payload as never)
        }
        if (name === 'probability.cycle.collected') {
          const p = payload as { symbol?: string }
          if (p && p.symbol) st.setProbability(p.symbol, payload as never)
        }
        // ٢٠٢٦-١٠-٠٨ (فكّ الأقسام عن القرار، ختم المالك «NQ»): دورتا الاستراتيجيّات (400) والقرار (450) أُرشف ناشراهما فحُذف قارئاهما.
        // حزمة ج — أحداث القرار والتنفيذ، كل حدث يبقى تحت رمزه.
        if (SYMBOL_KEYED.has(name)) {
          const p = payload as { symbol?: string }
          if (p && p.symbol) st.setSymbolStream(name, p.symbol, payload)
        }
        // ج٥ — عدّاد «رفض بلا أصل» (NO_PARENT_AUTHORITY) لكل رمز
        if (name === 'perpetual.entry.rejected') {
          const p = payload as { symbol?: string; reason?: string }
          if (p && p.symbol) {
            st.setSymbolStream(name, p.symbol, payload)
            if (p.reason === 'NO_PARENT_AUTHORITY') st.bumpAssetReject(p.symbol)
          }
        }
        if (name === 'risk.unified.state') st.setRisk(flattenRisk(payload) as never)
        // بوّابة التنفيذ الحقيقيّة (٥٥٢ — تُنشَر عند كل تغيير، لا صحّة مشتقّة)
        if (name === 'execution.gate.state') st.setGate(payload as never)
        // التنفيذ (عيلة ٥٥٠) — عرض فقط: حالة موحّدة + سجلّات دوّارة (وقت الوصول محلّي)
        if (name === 'execution.unified.state') st.setExecution(payload as never)
        if (name === 'execution.order.built') st.pushExecOrder({ ...(payload as object), kind: 'built', ts: Date.now() } as never)
        if (name === 'execution.order.skipped') st.pushExecOrder({ ...(payload as object), kind: 'skipped', ts: Date.now() } as never)
        if (name === 'trading.final_decision') st.pushExecOrder({ ...(payload as object), kind: 'final', ts: Date.now() } as never)
        if (name === 'execution.order.rejected') st.pushExecOrder({ ...(payload as object), kind: 'rejected', ts: Date.now() } as never)
        if (name === 'execution.manage.intent') st.pushExecManage({ ...(payload as object), stage: 'intent', ts: Date.now() } as never)
        if (name === 'execution.manage.command') st.pushExecManage({ ...(payload as object), stage: 'command', ts: Date.now() } as never)
        if (name === 'execution.manage.written') st.pushExecManage({ ...(payload as object), stage: 'written', ts: Date.now() } as never)
        if (name === 'market.outcome.realized') st.pushExecOutcome({ ...(payload as object), ts: Date.now() } as never)
        if (IMPORTANT.test(name)) st.pushEvent(name, eventDetail(payload))
      }
      if (fired.length) st.bumpFlows(fired)
    }
    schedule()
  }

  // ٢٠٢٦-٠٩-١٦ — عطبٌ قِيس بالتجربة: `requestAnimationFrame` **يتوقّف تمامًا**
  // حين تُخفى النافذة (قِيس: `document.hidden=true` و rAF لا يُستدعى خلال 1.5 ث).
  // فكان المحرّك يتوقّف عن التصريف، ويمتلئ الطابور، **ويُسقط الأقدم صامتًا**.
  // والمالك يعود إلى نافذته فيرى لوحةً مبنيّة على بقايا طابورٍ مقصوص — بلا
  // كلمة واحدة تقول إنّ شيئًا سقط. وهذا «صمتٌ يبدو خبرًا»، أخطر ما نحرسه.
  //
  // الحلّ في شقّين: (١) حين تُخفى النافذة يصرّف مؤقّتٌ كل ثانية بدل الإطار —
  // فلا يتراكم شيء أصلًا، والكلفة ثانيةٌ واحدة لا إطار في الستّين. (٢) وإن
  // سقط شيء رغم ذلك (دفقة أكبر من السقف داخل الثانية) **يُعَدّ ويُعلَن** على
  // «عدّادات النواة» — لا يُبتلع.
  const schedule = () => {
    if (typeof document !== 'undefined' && document.hidden) {
      raf = window.setTimeout(pump, 1000)
      return
    }
    raf = requestAnimationFrame(pump)
  }
  const cancel = () => {
    if (!raf) return
    // المعرّفان من عالمين مختلفين؛ الإلغاء المزدوج آمن ويغني عن تتبّع أيّهما جارٍ.
    cancelAnimationFrame(raf)
    window.clearTimeout(raf)
    raf = 0
  }
  // تبدُّل الرؤية يعيد الجدولة فورًا: العودة للظهور لا تنتظر انقضاء الثانية،
  // والاختفاء لا ينتظر إطارًا لن يأتي.
  const onVisibility = () => { cancel(); schedule() }
  if (typeof document !== 'undefined') {
    document.addEventListener('visibilitychange', onVisibility)
  }
  schedule()

  // اتصال واحد ببثّ النواة → كل رسالة تُدفع للطابور فقط (التصريف بالإطار).
  // الطابور محدود بلا نموّ ذاكرة (١٤ §٧) — وما يُسقَط يُحسب ويُعلَن.
  const CAP = 800
  const stopWs = connectWs(
    (m) => {
      queue.push(m)
      if (queue.length > CAP) {
        const lost = queue.length - CAP
        queue.splice(0, lost)
        useStore.getState().markClientDrop(lost)
      }
    },
    (open) => useStore.getState().setConn(open ? 'live' : 'down'),
  )

  // تحميل أوّلي (لحاق فوري قبل أول بثّ): أسماء عربية + لقطة ذرات مُثراة من الحوكمة
  govGet<Record<number, string>>('/gov/names')
    .then((n) => useStore.getState().setNames(n))
    .catch(() => { /* الخادم لسا مطفي */ })
  govGet<{ connected: boolean; atoms: AtomRec[] }>('/gov/atoms')
    .then((d) => { if (d.connected) useStore.getState().setSnapshot(d.atoms) })
    .catch(() => { /* النواة/الخادم مطفي */ })

  // ٢٠٢٦-٠٩-١٦: الذرّات المستبعَدة من الإقلاع ليست في `/gov/atoms` إطلاقًا —
  // النواة لم تُحمّلها. فبلا هذه القراءة تبقى **غائبة عن اللوحة كلّها**، وقائمة
  // القسم تعدّ المحمَّل وحده فتبدو مكتملة. التقرير ثابت لكل إقلاع، فيُقرأ مع
  // نبضة الأسماء لا مع نبضة الذرّات السريعة.
  const readBoot = () =>
    govGet<{ excluded?: number[] }>('/gov/boot-report')
      .then((d) => useStore.getState().setExcluded(Array.isArray(d?.excluded) ? d.excluded : []))
      .catch(() => { /* تقرير الإقلاع غير متاح — تبقى القائمة فارغة، ولا تُخترع */ })
  readBoot()

  // تحديث دوري للأسماء العربية → أي ذرة جديدة تاخد اسمها العربي بكل الأقسام لحالها
  const namesPoll = window.setInterval(() => {
    govGet<Record<number, string>>('/gov/names')
      .then((n) => useStore.getState().setNames(n))
      .catch(() => { /* الخادم مطفي */ })
    readBoot()
  }, 15000)

  // نبض REST دوري للذرات (احتياط قوي): يحدّث العدد/الحالة كل ٤ث حتى لو تعثّر WS أو التبويب غير الشبكة
  const atomsPoll = window.setInterval(() => {
    govGet<{ connected: boolean; atoms: AtomRec[] }>('/gov/atoms')
      .then((d) => { if (d.connected) useStore.getState().setSnapshot(d.atoms) })
      .catch(() => { /* الخادم مطفي */ })
  }, 4000)

  return () => {
    cancel()
    if (typeof document !== 'undefined') {
      document.removeEventListener('visibilitychange', onVisibility)
    }
    stopWs(); clearInterval(namesPoll); clearInterval(atomsPoll)
  }
}
