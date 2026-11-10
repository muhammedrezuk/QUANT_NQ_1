// حاكم التغيير (850) — عين المالك على التعديل الذاتي للعيارات.
//
// ٢٠٢٦-٠٩-١٠ — سؤال المالك: «شو هي صفحة؟ شو شغلها؟ ليش مو شغالة؟»
//
// كانت الصفحة تقرأ أربعة أحداث فقط، وتعرض «—» في كل بطاقة و«٠ / ٤ أحداث».
// والقياس كشف أنّ الأحداث الأربعة كلّها **أحداث حدوث** لا أحداث حالة:
//   • `adaptation.limits.state`  — 850 ينشره في `start()` مرّة واحدة عند الإقلاع.
//   • `adaptation.kill_switch.state` — 860 ينشره عند الرفع أو بأمر المالك فقط.
//   • `recalibration.proposed`  — 840 ينشره فقط إذا تجاوز الانحراف العتبة.
//   • `experiment.state`        — 850 ينشره فقط بعد وصول اقتراح.
// فاللوحة التي تفتح بعد الإقلاع لا ترى أيًّا منها أبدًا — لا لأنّ شيئًا معطَّل،
// بل لأنّها تنتظر بثًّا لا يُعاد. وهذا **كذب من نوع الصمت**: الحقيقة موجودة
// والشاشة فارغة.
//
// والحقيقة التي كانت مخفيّة خلف ذلك الفراغ (مقيسة من `/gov/atoms` الحيّ):
//   860 → `ADAPTATION_OFF:HOT_PATH_LATENCY_REGRESSION:150`
// أي أنّ مفتاح إيقاف التكيّف **مرفوع فعلًا**، والتعديل الذاتي موقوف، والسبب
// تراجع زمن القسم 150 — و«إعادته بأمر المالك وحده» (`reset: OWNER_COMMAND_ONLY`
// في حمولة 860). صفحةٌ تعرض «—» بدل ذلك تُخفي أهمّ ما فيها.
//
// فصارت الصفحة تقرأ من مصدرين وتُسمّي مصدر كل قيمة:
//   (١) الحدث الحيّ إن وصل — وهو الأدقّ.
//   (٢) سطر صحّة الذرّة من `/gov/atoms` — يبقى قائمًا ولا يذهب مع البثّ.
// والغائب عن المصدرين يبقى «—». لا اختراع قيمة ولا «سليم» بلا دليل.
import { useMemo, useState } from 'react'
import { useStore } from '../core/store'
import { arabicHealth } from '../core/arabic'

type Payload = Record<string, unknown>

const TH: React.CSSProperties = { padding: '6px 10px' }
const TD: React.CSSProperties = { padding: '6px 10px' }
const TR: React.CSSProperties = { borderTop: '1px solid var(--line)' }

function text(v: unknown): string {
  if (v == null || v === '') return '—'
  if (typeof v === 'boolean') return v ? 'نعم' : 'لا'
  if (typeof v === 'number') return String(v)
  return String(v)
}

function pick(p: Payload | undefined, keys: string[]): unknown {
  if (!p) return undefined
  for (const k of keys) if (p[k] != null) return p[k]
  return undefined
}

function Card({ title, value, sub, color = '', src }: {
  title: string; value: string; sub?: string; color?: string; src?: string
}) {
  return (
    <div className="scard">
      <div className="st">{title}</div>
      <div className={`sv ${color}`}>{value}</div>
      {sub ? <div className="ss dim">{sub}</div> : null}
      {src ? <div className="ss dim" style={{ fontSize: 11, opacity: 0.7 }}>المصدر: {src}</div> : null}
    </div>
  )
}

/**
 * سطر صحّة الذرّة يأتي بصيغة الآلة `sections=6 proposals=0`. و`arabicHealth`
 * يعرّب الاسم والقيمة ويُبقي `=` والمسافات — فيقرؤه المالك سطرَ عدّادات لا
 * جملة، وحكمه مسجَّل: «لا أقرأ بهذه الطريقة». هنا يُعاد ترقيمه فقط: نقطتان
 * بدل `=`، وفاصل «·» بين الأزواج. **لا تُترجَم قيمة ولا يُضاف رقم** — تنقيطٌ
 * لا تأليف.
 */
function healthLine(msg?: string | null): string {
  const ar = arabicHealth(msg)
  if (ar === '—') return ar
  const parts = ar.split(/\s+/).filter(Boolean)
  if (!parts.some((t) => t.includes('='))) return ar
  return parts.map((t) => (t.includes('=') ? t.replace('=', ': ') : t)).join(' · ')
}

/**
 * سبب رفع المفتاح يأتي من 860 بصيغة `CODE:<قسم>` — مثل
 * `HOT_PATH_LATENCY_REGRESSION:150`. و`arabicHealth` يقسّم بالمسافات فقط،
 * فالنقطتان تمنعانه من المطابقة ويُخرج «تفصيل تقني غير مترجم» (قِسناه حيًّا).
 * فهنا يُقصّ الرمز عن القسم، ويُترجم كلٌّ في موضعه.
 */
function reasonAr(raw?: string | null): string {
  const m = String(raw ?? '').trim()
  if (!m) return ''
  const parts = m.split(':')
  const code = arabicHealth(parts[0] ?? '')
  const tail = parts.slice(1).join(':').trim()
  return tail ? `${code} — عند القسم ${tail}` : code
}

/**
 * ٢٠٢٦-٠٩-١٠ — تصحيح من جلسة «قسم تحليل 150-199»، وتحقّقتُ منه بنفسي في
 * `atoms/قسم 800-849/820_محرك_القياس/atom.py:132`:
 *
 *   «publish-to-publish latency vs the latest tick of the same scope»
 *
 * أي أنّ `p99_ms` الذي يرفع المفتاح **يقيس انتشار التِكّة من وصولها إلى ظهور
 * بطاقة القسم — السلسلة كاملة**: التغذية والنقل وحلقة النواة، لا كفاءة ذرّات
 * القسم المسمّى. فكتابة «القسم ١٥٠» وحدها بالخطّ العريض توجّه المالك إلى
 * المكان الخطأ: **رقمٌ صادقٌ في مصدره كاذبٌ في موضعه**. والقسم المذكور هو
 * موضع تجاوز العتبة، لا الجهة المتسبّبة به — وقد قِيس ذلك: نفس الذرّة ونفس
 * اللحظة تعطي 134 مللي‑ثانية لرمز و82,930 لآخر، والفرق عمر التِكّة الواصلة.
 */
const LATENCY_TRIP_NOTE =
  'المقياس هنا هو انتشار التِكّة حتى ظهور بطاقة القسم — أي السلسلة كاملة (تغذية · نقل · حلقة النواة). فالقسم المذكور موضع تجاوز العتبة لا الجهة المتسبّبة، والسبب قد يكون في أيّ حلقة قبله.'
const isLatencyTrip = (raw?: string | null) =>
  String(raw ?? '').includes('HOT_PATH_LATENCY_REGRESSION')

/** حالة مفتاح إيقاف التكيّف كما تُقرأ من سطر صحّة 860 — `ADAPTATION_OFF:<سبب>` أو `ARMED`. */
function killFromHealth(msg?: string | null): { off: boolean | null; reason: string } {
  const m = String(msg ?? '').trim()
  if (!m) return { off: null, reason: '' }
  if (m === 'ARMED') return { off: false, reason: '' }
  if (!m.startsWith('ADAPTATION_OFF:')) return { off: null, reason: '' }
  return { off: true, reason: reasonAr(m.slice('ADAPTATION_OFF:'.length)) }
}

export default function ChangeGovernor() {
  const [view, setView] = useState<'overview' | 'experiments' | 'limits' | 'kill' | 'events'>('overview')
  const streams = useStore((s) => s.streams) as Record<string, unknown>
  const atoms = useStore((s) => s.atoms)
  const exp = streams['experiment.state'] as Payload | undefined
  const limits = streams['adaptation.limits.state'] as Payload | undefined
  const kill = streams['adaptation.kill_switch.state'] as Payload | undefined
  const proposed = streams['recalibration.proposed'] as Payload | undefined
  // الرقم الذي يرفع المفتاح فعلًا. ⚠️ الحدث يحمل `section` في حمولته ومفتاح
  // التيّار واحد، فالقيمة تُنسب **إلى القسم المكتوب فيها** لا إلى 150 افتراضًا
  // — وقد قِيس أنّه نادر (صفر عيّنة في تسعين ثانية)، فغيابه هو الحالة الغالبة.
  const lat = streams['measurement.latency.state'] as Payload | undefined
  const latSection = lat ? String(pick(lat, ['section']) ?? '') : ''
  const latP99 = typeof lat?.p99_ms === 'number' ? lat.p99_ms : null
  const seen = useMemo(() => [exp, limits, kill, proposed].filter(Boolean).length, [exp, limits, kill, proposed])

  const h840 = atoms[840]?.health?.message ?? null
  const h850 = atoms[850]?.health?.message ?? null
  const h860 = atoms[860]?.health?.message ?? null
  const h870 = atoms[870]?.health?.message ?? null
  const alive = (id: number) => atoms[id]?.state === 'running'

  // المفتاح: الحدث أوّلًا، ثمّ سطر الصحّة. ولا يُخترع «مسموح» من الفراغ.
  const hk = killFromHealth(h860)
  const killOff: boolean | null = kill
    ? (kill.adaptation_off === true ? true : kill.active === true ? false : null)
    : hk.off
  const killReason = kill ? String(pick(kill, ['reason']) ?? '') : ''
  const killSrc = kill ? 'الحدث الحيّ' : h860 ? 'سطر صحّة الذرّة ٨٦٠' : ''
  const killText = killOff == null ? '—' : killOff ? '⛔ موقوف' : '✅ مسموح'
  const killWhy = killOff === true
    ? (reasonAr(killReason) || hk.reason || 'رُفع المفتاح ولم يُذكر سبب')
    : killOff === false ? 'لم يُرفع المفتاح — التعديل الذاتي مسموح' : 'لم يصل المفتاح ولا سطر صحّته'

  // ٢٠٢٦-٠٩-١٦ (حارس `check_dashboard_fields.py`) — كنتُ أقرأ بدائل لا وجود لها.
  // مفاتيح `recalibration.proposed` من ناشرها 840 (`atom.py:177-181`):
  //   target · reason · overall_drift · evidence · proposal_id
  // فـ`pick(proposed, ['state','status','decision'])` **لا يطابق واحدًا منها**:
  // كانت البطاقة ستعرض «—» حتى عند وصول اقتراحٍ فعليّ — أي حدثٌ يصل والشاشة
  // تقول لا شيء. ومفاتيح `experiment.state` من 850 (`atom.py:158-165`):
  //   experiment_id · target · status · reason · magnitude · gates ·
  //   rollback_version · max_authority
  // فلا `state` ولا `phase` ولا `id` ولا `symbol`. البدائل الميتة تُحذف —
  // لا لأنّها تؤذي وحدها، بل لأنّها تُوهم قارئ الكود أنّ للحقل اسمين.
  const expState = text(pick(exp, ['status']))
  const proposedState = text(pick(proposed, ['reason']))

  return (
    <div className="section" style={{ display: 'flex', flexDirection: 'column', gap: 14, overflow: 'auto' }}>
      <div className="scard" style={{ borderInlineStart: '4px solid var(--accent)' }}>
        <div className="st" style={{ fontSize: 17 }}>🛡️ حاكم التغيير · الذرّة ٨٥٠</div>
        <div className="ss dim">
          هنا يظهر <b>تعديل النظام لعياراته بنفسه</b>: ماذا يُجرَّب، وما السقف المسموح، وهل المفتاح مرفوع.
          قراءة وتدقيق فقط — لا زرّ اعتماد ولا أمر يُرسَل من هذه الصفحة.
        </div>
      </div>

      {/* الحكم أوّلًا وبالخطّ العريض — لا يُدفن تحت بطاقات متشابهة. */}
      <div
        className="scard"
        style={{
          borderInlineStart: `4px solid var(--${killOff === true ? 'red' : killOff === false ? 'green' : 'grey'})`,
          background: killOff === true ? 'color-mix(in srgb, var(--red) 8%, transparent)' : undefined,
        }}
      >
        <div className="st">حالة التعديل الذاتي للعيارات</div>
        <div className={`sv ${killOff === true ? 'red' : killOff === false ? 'green' : 'grey'}`} style={{ fontSize: 22 }}>
          {killText}
        </div>
        <div className="ss" style={{ lineHeight: 1.85 }}>
          <b>السبب:</b> {killWhy}
          {killOff === true && isLatencyTrip(killReason || h860) ? (
            <>
              <br />
              <span className="dim">{LATENCY_TRIP_NOTE}</span>
            </>
          ) : null}
          {killOff === true ? (
            <>
              <br />
              <b style={{ color: 'var(--green)' }}>والتداول مستمرّ</b> — الموقوف هو تعديل العيارات تلقائيًّا،
              لا فتح الصفقات. العيارات ثابتة على آخر قيمة معتمَدة.
              <br />
              {isLatencyTrip(killReason || h860) ? (
                <>
                  <b>وإنزاله الآن لا يصمد</b> إن كان القياس ما زال فوق العتبة: ٨٦٠ يرفعه
                  مرّةً أخرى عند أوّل نشرة قياس تتجاوزها (`_on_latency` — لا تهدئة ولا مهلة).
                  العتبة من إعداد ٨٦٠ نفسه: ٥٠ مللي‑ثانية × ٣ = <b>١٥٠ مللي‑ثانية</b>.
                  <br />
                </>
              ) : null}
              <b>الإرجاع بيدك وحدك</b> — الذرّة ٨٦٠ لا تُنزل المفتاح إلّا بأمر مالك
              (`OWNER_COMMAND_ONLY`). الزرّ: صفحة «تحكّم» ← بطاقة «🧬 مفتاح التكيّف» ←
              «▶️ أعِد التكيّف». والمسار مفحوص من طرفيه: الزرّ ← ٩٠١ ← ٨٦٠.
            </>
          ) : null}
          {killSrc ? <><br /><span className="dim" style={{ fontSize: 11 }}>المصدر: {killSrc}</span></> : null}
        </div>
      </div>

      <div className="change-nav" role="tablist" aria-label="أقسام حاكم التغيير">
        {([['overview', 'نظرة عامة'], ['experiments', 'التجارب'], ['limits', 'الحدود'], ['kill', 'مفتاح الإيقاف'], ['events', 'الأحداث']] as const).map(([id, label]) => (
          <button key={id} className={`btn ${view === id ? 'active' : ''}`} onClick={() => setView(id)}>{label}</button>
        ))}
      </div>

      {view === 'overview' ? <div className="cards">
        <Card
          title="حاكم التغيير · ٨٥٠"
          value={exp ? arabicHealth(expState) : healthLine(h850)}
          sub={exp ? `${text(pick(exp, ['target']))} · ${text(pick(exp, ['experiment_id']))}` : 'لا تجربة جارية'}
          color={exp ? 'green' : alive(850) ? 'amber' : 'grey'}
          src={exp ? 'الحدث الحيّ' : h850 ? 'سطر صحّة الذرّة' : ''}
        />
        <Card
          title="محرّك الانحراف · ٨٤٠"
          value={healthLine(h840)}
          sub="يراقب الانحراف ويقترح المعايرة — ولا يغيّر شيئًا بنفسه"
          color={alive(840) ? 'green' : 'grey'}
          src={h840 ? 'سطر صحّة الذرّة' : ''}
        />
        <Card
          title="عقل المعايرة · ٨٧٠"
          value={healthLine(h870)}
          sub="يختار ما يُعاير ويقيس أثره"
          color={alive(870) ? 'green' : 'grey'}
          src={h870 ? 'سطر صحّة الذرّة' : ''}
        />
        <Card
          title="قياس الزمن مقابل العتبة"
          value={latP99 != null ? `${latP99.toLocaleString('ar-EG-u-nu-latn', { maximumFractionDigits: 1 })} / ١٥٠` : '—'}
          sub={latP99 != null
            ? `مللي‑ثانية · ${latSection ? `القسم ${latSection}` : 'القسم غير مذكور'} · ${latP99 > 150 ? 'فوق العتبة' : 'تحت العتبة'}`
            : 'حدث القياس لم يصل — وهو نادر بطبعه، لا يُنشَر مع كل تِكّة'}
          color={latP99 == null ? 'grey' : latP99 > 150 ? 'red' : 'green'}
          src={latP99 != null ? 'الحدث الحيّ' : ''}
        />
        <Card
          title="حدود التكيّف"
          value={limits ? text(pick(limits, ['max_change_per_day'])) : '—'}
          sub={limits
            ? `السقف اليوميّ · المستهلك اليوم: ${text(pick(limits, ['changes_today']))}`
            : 'ينشرها ٨٥٠ مرّة واحدة عند الإقلاع — واللوحة فتحت بعدها'}
          color={limits ? 'green' : 'grey'}
          src={limits ? 'الحدث الحيّ' : ''}
        />
        <Card
          title="اقتراح إعادة المعايرة"
          value={proposed ? arabicHealth(proposedState) : 'لا اقتراح'}
          sub={proposed
            ? `الهدف: ${text(pick(proposed, ['target']))} · انحراف ${text(pick(proposed, ['overall_drift']))}`
            : 'ينشره ٨٤٠ فقط عند تجاوز عتبة الانحراف'}
          color={proposed ? 'amber' : 'grey'}
          src={proposed ? 'الحدث الحيّ' : ''}
        />
      </div> : null}

      {view === 'experiments' ? <div className="scard">
        <div className="st">التجارب</div>
        <div className="ss">
          الحالة: {exp ? arabicHealth(expState) : healthLine(h850)} ·
          المعرّف: {text(pick(exp, ['experiment_id']))} ·
          الهدف: {text(pick(exp, ['target']))} ·
          المقدار: {text(pick(exp, ['magnitude']))}
        </div>
        <div className="ss dim">
          التجربة تبدأ حين يرفع ٨٤٠ اقتراحًا ويقبله ٨٥٠. ومع المفتاح مرفوعًا لا تبدأ تجربة أصلًا.
        </div>
      </div> : null}

      {view === 'limits' ? <div className="scard">
        <div className="st">حدود التكيّف</div>
        {limits ? (
          <div className="ss">
            خطوة: {text(pick(limits, ['max_change_per_step']))} ·
            يوم: {text(pick(limits, ['max_change_per_day']))} ·
            استُهلك اليوم: {text(pick(limits, ['changes_today']))} ·
            أقصى تجارب متزامنة: {text(pick(limits, ['max_active_experiments']))} ·
            مهلة سكون: {text(pick(limits, ['min_dwell_s']))} ث ·
            تهدئة: {text(pick(limits, ['cooldown_s']))} ث
          </div>
        ) : (
          <div className="ss dim" style={{ lineHeight: 1.85 }}>
            لم تصل. الذرّة ٨٥٠ تنشر هذه الحدود <b>في لحظة الإقلاع وحدها</b> (وعند الإيقاف)، فاللوحة
            التي تُفتح بعد ذلك لا تسمعها أبدًا. هذا نقص مُبلَّغ لجلسة القسم ٨٥٠-٨٩٩ — ولن تُخترَع هنا
            أرقام سقوف من مكان آخر.
          </div>
        )}
      </div> : null}

      {view === 'kill' ? <div className="scard">
        <div className="st">مفتاح إيقاف التكيّف · الذرّة ٨٦٠</div>
        <div className={`sv ${killOff === true ? 'red' : killOff === false ? 'green' : 'grey'}`}>{killText}</div>
        <div className="ss dim" style={{ lineHeight: 1.85 }}>
          السبب: {killWhy}
          {killOff === true && isLatencyTrip(killReason || h860) ? <><br />{LATENCY_TRIP_NOTE}</> : null}
          {kill ? <><br />عدد مرّات الرفع: {text(pick(kill, ['trips']))} · الرافع: {text(pick(kill, ['owner']))}</> : null}
          <br />
          يرتفع المفتاح وحده في حالتين: انحراف حادّ، أو تراجع زمن في أحد المسارات الحارّة
          (١٥٠ · ٣٥٠ · ٤٠٠). وينزل <b>بأمر المالك وحده</b> — لا يعيد نفسه حتى لو عاد الزمن سليمًا،
          حمايةً من تأرجحٍ يعايِر ويتراجع بلا وعي.
        </div>
      </div> : null}

      {view === 'events' ? <div className="scard">
        <div className="st">الأحداث الأربعة — ومن ينشر كلًّا منها</div>
        <div style={{ overflowX: 'auto' }}>
        <table className="tbl" style={{ width: '100%', fontSize: 12.5, borderCollapse: 'collapse', minWidth: 520 }}>
          <thead><tr className="dim" style={{ textAlign: 'right' }}>
            <th style={TH}>ما هو</th><th style={TH}>ناشره</th><th style={TH}>متى يُنشَر</th><th style={TH}>الحالة</th>
          </tr></thead>
          <tbody>
            <tr style={TR}>
              <td style={TD}>حدود التكيّف</td><td className="num" style={TD}>٨٥٠</td>
              <td style={TD}>عند الإقلاع مرّة واحدة</td>
              <td style={TD} className={limits ? 'green' : 'dim'}>{limits ? 'وصل' : 'لم يصل'}</td>
            </tr>
            <tr style={TR}>
              <td style={TD}>حالة التجربة</td><td className="num" style={TD}>٨٥٠</td>
              <td style={TD}>بعد قبول اقتراح معايرة</td>
              <td style={TD} className={exp ? 'green' : 'dim'}>{exp ? 'وصل' : 'لم يصل'}</td>
            </tr>
            <tr style={TR}>
              <td style={TD}>مفتاح إيقاف التكيّف</td><td className="num" style={TD}>٨٦٠</td>
              <td style={TD}>عند الرفع أو بأمر المالك</td>
              <td style={TD} className={kill ? 'green' : 'dim'}>{kill ? 'وصل' : 'لم يصل — والحالة تُقرأ من سطر الصحّة'}</td>
            </tr>
            <tr style={TR}>
              <td style={TD}>اقتراح إعادة المعايرة</td><td className="num" style={TD}>٨٤٠</td>
              <td style={TD}>عند تجاوز عتبة الانحراف</td>
              <td style={TD} className={proposed ? 'green' : 'dim'}>{proposed ? 'وصل' : 'لم يصل'}</td>
            </tr>
          </tbody>
        </table>
        </div>
        <div className="ss dim">وصل {seen} من ٤ منذ فتح اللوحة. الأربعة أحداث حدوث لا أحداث حالة.</div>
      </div> : null}

      <div className="scard">
        <div className="st" style={{ fontWeight: 700 }}>لماذا كانت الصفحة تبدو معطَّلة</div>
        <div className="ss dim" style={{ lineHeight: 1.9 }}>
          لأنّ أحداثها الأربعة <b>أحداث حدوث لا أحداث حالة</b>: كلٌّ منها يُنشَر في لحظته ولا يُعاد.
          فاللوحة التي تُفتح بعد الإقلاع تنتظر بثًّا لا يأتي، وتعرض «—» — فيُقرأ الفراغ عطبًا وهو ليس عطبًا.
          <br />
          والأسوأ أنّ الفراغ كان يُخفي حقيقةً: <b>المفتاح مرفوع والتعديل الذاتي موقوف</b>. فصارت الصفحة
          تقرأ سطر صحّة الذرّة أيضًا — وهو باقٍ لا يذهب مع البثّ — وتُسمّي مصدر كل قيمة تحتها.
          وما لا يصل من أيّ مصدر يبقى «—»: لا «سليم» بلا دليل.
        </div>
      </div>
    </div>
  )
}
