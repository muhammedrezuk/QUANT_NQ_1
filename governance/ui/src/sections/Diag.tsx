// التشخيص (869) — صحة النواة + تقرير الإقلاع (منافذ حقيقية: /gov/health · /gov/boot-report)
// + محلّل الصمت الحيّ: ليش كل ذرة ساكتة ساكتة — على النظام الحيّ الحقيقي، بلا موك
// (الفكرة من أداة exercise.py القديمة؛ التنفيذ حيّ: مانيفستات /gov/graph + نبض الأحداث الفعلي).
import { useEffect, useMemo, useState } from 'react'
import { useStore } from '../core/store'
import { streamAr } from '../core/streams'
import { arabicHealth } from '../core/arabic'

interface Health { status: string; core_version: string; atom_count: number }
interface Boot {
  started_at: number; finished_at: number; success: boolean
  booted: number[]; failed: number[]; excluded: number[]; scan_failures: unknown[]
}
interface Wiring {
  pubs?: Record<string, number[]>; subs?: Record<string, number[]>
  foreign_pubs?: string[]; foreign_market?: string
}

// أحداث النبض/الساعة — وصولها لا يعني «وصلها مدخل شغل»، وإلا انفلَغت كل الذرات الدورية
const PULSE = new Set(['SYS_SECOND', 'SYS_DAY', 'kernel.clock.heartbeat', 'time.utc.synced'])

function Card({ t, v, c, sub }: { t: string; v: string; c?: string; sub?: string }) {
  return (
    <div className="scard">
      <div className="st">{t}</div>
      <div className={`sv ${c ?? ''}`}>{v}</div>
      {sub ? <div className="ss">{sub}</div> : null}
    </div>
  )
}

export default function Diag() {
  const [h, setH] = useState<Health | null>(null)
  const [b, setB] = useState<Boot | null>(null)
  const [wiring, setWiring] = useState<Wiring | null>(null)
  // `hosted_atom_ids` من مزرعة التحليل — `null` تعني «لم يصل الحقل» لا «صفر».
  const [farmHosted, setFarmHosted] = useState<number[] | null>(null)
  const atoms = useStore((s) => s.atoms)
  const flows = useStore((s) => s.flows)
  const namesAr = useStore((s) => s.namesAr)
  const telemetry = atoms[810]

  useEffect(() => {
    const load = () => {
      fetch('/gov/health').then((r) => r.json()).then(setH).catch(() => {})
      fetch('/gov/boot-report').then((r) => (r.ok ? r.json() : null)).then(setB).catch(() => {})
      fetch('/gov/transport-stats')
        .then((r) => (r.ok ? r.json() : null))
        .then((d: { analysis_farm?: { hosted_atom_ids?: number[] } } | null) => {
          const ids = d?.analysis_farm?.hosted_atom_ids
          setFarmHosted(Array.isArray(ids) ? ids : null)
        })
        .catch(() => { /* النقل غير متاح — يبقى «غير معروف» لا صفرًا */ })
    }
    const loadWiring = () =>
      fetch('/gov/graph').then((r) => r.json()).then(setWiring).catch(() => {})
    load(); loadWiring()
    const t = setInterval(load, 4000)
    const t2 = setInterval(loadWiring, 15000)
    return () => { clearInterval(t); clearInterval(t2) }
  }, [])

  const nameOf = (id: number) => namesAr[id] ?? `#${id}`

  const analysis = useMemo(() => {
    if (!wiring?.pubs || !wiring?.subs) return null
    const pubs = wiring.pubs, subs = wiring.subs
    const atomPub: Record<number, string[]> = {}
    const atomSub: Record<number, string[]> = {}
    for (const [ev, ids] of Object.entries(pubs)) for (const id of ids) (atomPub[id] ??= []).push(ev)
    for (const [ev, ids] of Object.entries(subs)) for (const id of ids) (atomSub[id] ??= []).push(ev)

    const fired = new Set(Object.keys(flows))
    const spoke = new Set<number>()
    for (const [idStr, evs] of Object.entries(atomPub)) {
      if (evs.some((e) => fired.has(e))) spoke.add(Number(idStr))
    }

    const groups: Record<string, Array<{ id: number; detail: string }>> = {}
    const push = (kind: string, id: number, detail: string) => (groups[kind] ??= []).push({ id, detail })

    for (const a of Object.values(atoms)) {
      if (a.state === 'stopped') { push('واقفة (بيد المالك)', a.id, ''); continue }
      if (spoke.has(a.id)) continue
      const myPubs = atomPub[a.id] ?? []
      const mySubs = (atomSub[a.id] ?? []).filter((e) => !e.startsWith('core.'))
      if (!myPubs.length) { push('مستهلِكة فقط — ما بتنشر أصلًا (طبيعي)', a.id, ''); continue }
      const work = mySubs.filter((e) => !PULSE.has(e))
      if (!work.length) { push('دورية — بتنشر على دورتها (طبيعي)', a.id, ''); continue }
      const orphan = work.filter((e) => !(pubs[e]?.length))
      if (orphan.length === work.length) { push('يتيمة — محدا بينشر مدخلها', a.id, streamAr(orphan[0])); continue }
      const firedWork = work.filter((e) => fired.has(e))
      if (!firedWork.length) {
        const upstream = new Set<number>()
        for (const e of work) for (const p of pubs[e] ?? []) if (!spoke.has(p)) upstream.add(p)
        push('مجوّعة — ناشر مدخلها ساكت', a.id,
          upstream.size ? 'تستنى: ' + [...upstream].slice(0, 3).map(nameOf).join(' · ') : '')
        continue
      }
      push('⚠ وصلها مدخلها وما نطقت — تستاهل تحقيق', a.id, 'وصلها: ' + streamAr(firedWork[0]))
    }

    // الوصلات المكسورة على مستوى النظام كله
    // ٢٠٢٦-٠٩-٠٩ (أمر المالك «ما ضلّ شي اسمه قسم كريبتو»): الفرز بقي كما هو —
    // الخادم يعلن أحداثًا غيابها صحيح بالتصميم — لكن تسمية السوق الغريب لم
    // يعد لها فرعان. السوق واحد: الفوركس.
    const foreign = new Set(wiring.foreign_pubs ?? [])
    const foreignMarket = 'الفوركس'
    const noPublisher: Array<{ ev: string; who: number[] }> = []
    const inheritedForex: Array<{ ev: string; who: number[] }> = []
    for (const [ev, ids] of Object.entries(subs)) {
      if ((pubs[ev]?.length) || PULSE.has(ev) || ev.startsWith('core.')) continue
      if (foreign.has(ev)) inheritedForex.push({ ev, who: ids })
      else noPublisher.push({ ev, who: ids })
    }
    const noListener: string[] = []
    for (const [ev, ids] of Object.entries(pubs)) {
      if (ids.length && !(subs[ev]?.length)) noListener.push(ev)
    }
    const forDashboard = (e: string) => /\.state$|\.snapshot$|\.synced$|\.collected$|\.updated$|\.completed$/.test(e)
    return { groups, spokeCount: spoke.size, noPublisher, inheritedForex, foreignMarket, noListener: noListener.filter((e) => !forDashboard(e)) }
  }, [wiring, atoms, flows, namesAr])

  const bootMs = b ? Math.round((b.finished_at - b.started_at) * 1000) : null
  const ORDER = ['⚠ وصلها مدخلها وما نطقت — تستاهل تحقيق', 'يتيمة — محدا بينشر مدخلها',
    'مجوّعة — ناشر مدخلها ساكت', 'واقفة (بيد المالك)', 'دورية — بتنشر على دورتها (طبيعي)',
    'مستهلِكة فقط — ما بتنشر أصلًا (طبيعي)']

  return (
    <div className="section" style={{ display: 'flex', flexDirection: 'column', gap: 14, overflow: 'auto' }}>
      <div className="cards">
        <Card t="النواة" v={h?.status === 'ok' ? 'سليمة' : '—'} c="green" sub={h ? `إصدار ${h.core_version}` : ''} />
        <Card t="عدد الذرات" v={h ? String(h.atom_count) : '—'} />
        <Card t="الإقلاع" v={b ? (b.success ? 'نجح' : 'فشل') : '—'} c={b?.success ? 'green' : 'red'} sub={bootMs != null ? `خلال ${bootMs} جزء من الثانية` : ''} />
        <Card t="أقلعت" v={b ? String(b.booted.length) : '—'} c="green" />
        <Card t="فشلت بالإقلاع" v={b ? String(b.failed.length) : '—'} c={b && b.failed.length ? 'red' : 'grey'} />
        {/* ٢٠٢٦-٠٩-١٦ (بلاغ جلسة ٤٥٠-٥٩٩، وقِسته بنفسي) — `excluded` كان
            **مُعلَنًا في النوع أعلاه ولا يُعرَض في أيّ مكان**. والقياس الحيّ:
            ٢٣٧ مانيفستًا على القرص · ٢٢٨ صفًّا تصل اللوحة · ٩ مستبعَدة
            (١٠٧ · ٢٥٦ · ٢٥٧ · ٢٥٨ · ٥٧٦ · ٥٧٨ · ٦٢٥ · ٦٢٦ · ٦٣٠).
            والفرق ٢٣٧−٩=٢٢٨ يطابق تمامًا.

            والخطر أنّ المستبعَدة **لا تظهر خضراء بل لا تظهر أصلًا**: فقائمة
            القسم تقول «١٢ ذرّة · سليمة ١٢» وهي تعدّ المحمَّل وحده، فيُقرأ
            القسم مكتملًا وذرّتان منه لم تُحمَّلا قط. غيابٌ يُقرأ اكتمالًا —
            وهو أخطر من شارةٍ حمراء. */}
        <Card
          t="مستبعَدة من الإقلاع"
          v={b ? String(b.excluded.length) : '—'}
          c={b && b.excluded.length ? 'amber' : 'grey'}
          sub={b && b.excluded.length
            ? 'لم تُحمَّل قط — ولا تظهر في أيّ قائمة ذرّات'
            : 'لا ذرّة مستبعَدة'}
        />
        <Card t="نطقت منذ فتح اللوحة" v={analysis ? String(analysis.spokeCount) : '—'} c="green" />
        <Card
          t="ناقل التلمترية (810)"
          v={!telemetry ? 'غير محمّل' : telemetry.health?.state === 'healthy' ? 'يعمل' : telemetry.health?.state === 'degraded' ? 'ينتظر بيانات' : 'متوقّف'}
          c={!telemetry ? 'grey' : telemetry.health?.state === 'healthy' ? 'green' : telemetry.health?.state === 'degraded' ? 'amber' : 'red'}
          // ٢٠٢٦-٠٩-١٦: كانت تُعرَض خامًا فيقرأ المالك `rows=6362 batches=48`.
          // القاموس كان يحمل ترجمتهما — العيب أنّ هذا الموضع لم يمرّ به أصلًا.
          sub={telemetry?.health?.message ? arabicHealth(telemetry.health.message) : 'لم تصل حالة الناقل بعد'}
        />
      </div>

      {/* ٢٠٢٦-٠٩-١٦ — معادلة الإغلاق، باقتراح جلسة النقل بعد أن حسمت القياس:
          كل ذرّة مسجَّلة يجب أن تقع في خانةٍ واحدة معروفة. ما لا يقع في خانة
          هو **العطب الحقيقيّ** ويستحقّ الإنذار وحده.

              المسجَّلة = أقلعتها النواة + مستضافة بالمزرعة + مستبعَدة + غير مفسَّرة

          وسبب وجودها: ظهر فرقٌ 228 مقابل 144 فبدا «٨٤ ذرّة بلا تفسير». وقِيس
          أنّ 82 منها تُظهر أرقامًا حيّة متحرّكة — فهي تعمل، لكنّها تُقلع داخل
          **عمليّات مزرعة التحليل** لا عمليّة النواة، وتقرير الإقلاع لا يراها.
          أي أنّ «booted» تعني «أقلعتها عمليّة النواة» لا «أقلعت».

          ⚠️ والحقل `hosted_atom_ids` أضافته جلسة النقل ولا يصير حيًّا قبل
          الإقلاع التالي (`transport/` لا تُحمَّل ساخنة). فحتى وصوله **لا
          يُعرَض رقمٌ للغامض**: يُقال «غير معروف بعد» — لأنّ عرض «٨٤ غير
          مفسَّرة» اليوم إنذارٌ كاذب، تفسيرُه موجود وإعلانه لم يصل. */}
      {b ? (() => {
        const hosted = farmHosted
        const registered = Object.keys(atoms).length + b.excluded.length
        const known = b.booted.length + b.excluded.length + (hosted?.length ?? 0)
        const rest = registered - known
        const ready = hosted != null
        return (
          <div
            className="scard"
            style={{ borderInlineStart: `4px solid var(--${!ready ? 'grey' : rest > 0 ? 'red' : 'green'})` }}
          >
            <div className="st" style={{ fontWeight: 700 }}>هل كل ذرّة مُحتَسَبة؟</div>
            <div className={`sv ${!ready ? 'grey' : rest > 0 ? 'red' : 'green'}`} style={{ fontSize: 19 }}>
              {!ready ? '— لسّا ما بنقدر نحسبها' : rest > 0 ? `✗ ${rest} ذرّة بلا تفسير` : '✓ كل ذرّة في خانتها'}
            </div>
            <div className="ss" style={{ marginTop: 6, lineHeight: 1.9 }}>
              <b>{registered}</b> مسجَّلة ={' '}
              <b>{b.booted.length}</b> أقلعتها النواة +{' '}
              <b>{hosted?.length ?? '؟'}</b> تستضيفها مزرعة التحليل +{' '}
              <b>{b.excluded.length}</b> مستبعَدة +{' '}
              <b>{ready ? rest : '؟'}</b> بلا تفسير
            </div>
            <div className="ss dim" style={{ marginTop: 6, lineHeight: 1.8 }}>
              {!ready
                ? 'عدد ما تستضيفه المزرعة لم يصل بعد — الحقل جديد ولا يصير حيًّا قبل إقلاع اللوحة والنواة من جديد. '
                  + 'ولا يُعرض رقمٌ للغامض قبل وصوله: تفسيرُه موجود وإعلانه متأخّر، وعرضه الآن إنذار كاذب.'
                : rest > 0
                  ? 'هذا الرقم هو الإنذار الحقيقيّ: ذرّات مسجَّلة لا تقول أيّ جهة أنّها تشغّلها.'
                  : '«أقلعتها النواة» تعني عمليّة النواة وحدها — وما تستضيفه المزرعة يُقلع في عمليّاتها، فلا يذكره تقرير الإقلاع.'}
            </div>
          </div>
        )
      })() : null}

      {b && b.excluded.length ? (
        <div className="scard" style={{ borderInlineStart: '4px solid var(--amber)' }}>
          <div className="st" style={{ fontWeight: 700 }}>
            ذرّات لم تُحمَّل في هذا الإقلاع — {b.excluded.length} ذرّة
          </div>
          <div className="ss dim" style={{ lineHeight: 1.85 }}>
            هذه الذرّات <b>غير موجودة في أيّ قائمة على اللوحة</b>: لا خضراء ولا حمراء، بل غائبة.
            فقائمة قسمها تعدّ المحمَّل وحده وتبدو مكتملة. المصدر تقرير الإقلاع نفسه
            (<span dir="ltr">/gov/boot-report</span>) لا استنتاج.
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 8 }}>
            {[...b.excluded].sort((x, y) => x - y).map((id) => (
              <span key={id} className="acctchip amber" title="مستبعَدة من الإقلاع — لم تُحمَّل بالنواة">
                <em className="num">{id}</em>
                <b>{namesAr[id] ?? 'بلا اسم عربيّ'}</b>
              </span>
            ))}
          </div>
          <div className="ss dim" style={{ marginTop: 8, fontSize: 11 }}>
            الاستبعاد قد يكون بأمرك (وضع تشغيل يدويّ) وقد يكون عطبًا — التقرير يقول «مستبعَدة»
            ولا يقول السبب، فلا يُخترع هنا سبب.
          </div>
        </div>
      ) : null}

      <div className="scard">
        <div className="st">لمحة المخازن (عيلة 700) — مين عم يحفظ ومين متعثّر</div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px 18px', marginTop: 8 }}>
          {Object.values(atoms).filter((a) => a.id >= 700 && a.id < 800).sort((a, b) => a.id - b.id).map((a) => (
            <span key={a.id} style={{ whiteSpace: 'nowrap', fontSize: 13 }}>
              <span style={{ color: a.color === 'green' ? 'var(--green)' : a.color === 'red' ? 'var(--red)' : a.color === 'amber' ? 'var(--amber)' : 'var(--dim)' }}>●</span>{' '}
              {a.name_ar ?? nameOf(a.id)} <span className="dim" style={{ fontSize: 11.5 }}>{a.label_ar ?? ''}</span>
            </span>
          ))}
          {Object.values(atoms).filter((a) => a.id >= 700 && a.id < 800).length === 0 ? <span className="dim">ما في ذرات مخازن محمّلة</span> : null}
        </div>
      </div>

      {analysis == null ? (
        <div className="scard"><div className="ss dim">محلّل الصمت بدو النسخة الجديدة من الخادم — أعد فتح «غرفة القيادة» مرّة وحدة.</div></div>
      ) : (
        <>
          <div className="scard">
            <div className="st">وصلات مكسورة (من عقود الذرات الحقيقية)</div>
            {analysis.noPublisher.length === 0 ? (
              <div className="ss" style={{ color: 'var(--green)' }}>ما في مدخل بلا ناشر — كل ذرة مدخلها موصول 🟢</div>
            ) : analysis.noPublisher.map(({ ev, who }) => (
              <div key={ev} className="ss" style={{ color: 'var(--red)' }}>
                {/* الاسم العربي من القاموس المشترك + الخام للتشخيص (بند 13 بدفتر 97) */}
                ● {streamAr(ev) === ev ? <>«{ev}»</> : <>{streamAr(ev)} <span className="dim">(«{ev}»)</span></>} محدا بينشره — وبيستنّاه: {who.slice(0, 4).map(nameOf).join(' · ')}
              </div>
            ))}
            {analysis.noListener.length ? (
              <div className="ss dim" style={{ marginTop: 6 }}>
                مخرجات بلا مستمع (ممكن مقصودة): {analysis.noListener.length} تيار
              </div>
            ) : null}
          </div>

          {/* اشتراكات فوركس موروثة — تُعلَن ولا تُخفى، ولا تُحسب عطلًا (٢٠٢٦-٠٨-٢٩) */}
          {analysis.inheritedForex.length ? (
            <div className="scard">
              <div className="st">اشتراكات موروثة عن {analysis.foreignMarket} — خارج عمل هذا السوق ({analysis.inheritedForex.length})</div>
              <div className="ss dim">
                هذه الذرّات منقولة عن {analysis.foreignMarket}، فحملت معها اشتراكات بأحداث
                <b> لا يَنشرها إلا ذاك السوق</b> (قِيس بالاسم من شجرة ذرّاته، لا بتخمين).
                لا ناشر لها هنا ولن يكون. <b>غيابها صحيح بالتصميم، لا عطل:</b>
                اشتراك بحدث لا يُنشَر لا يُستدعى أبدًا — صفر كلفة وصفر أثر.
              </div>
              <details style={{ marginTop: 6 }}>
                <summary className="ss dim" style={{ cursor: 'pointer' }}>عرض التفصيل</summary>
                {analysis.inheritedForex.map(({ ev, who }) => (
                  <div key={ev} className="ss dim" style={{ fontSize: 12 }}>
                    ● {streamAr(ev) === ev ? <>«{ev}»</> : <>{streamAr(ev)} <span className="dim">(«{ev}»)</span></>}
                    {' '}← {who.slice(0, 4).map(nameOf).join(' · ')}
                  </div>
                ))}
              </details>
            </div>
          ) : null}

          <div className="scard">
            <div className="st">لماذا الصمت؟ — تصنيف كل ذرة ساكتة بسببها (القياس منذ فتح اللوحة)</div>
            <div className="ss dim">ذرة بطيئة الدورة (نسخ احتياطي، أرشفة…) ممكن تبين ساكتة وهي سليمة — التصنيف بيوضّح.</div>
            {ORDER.filter((k) => analysis.groups[k]?.length).map((kind) => (
              <div key={kind} style={{ marginTop: 10 }}>
                <div style={{ fontWeight: 700, color: kind.startsWith('⚠') ? 'var(--amber)' : kind.includes('يتيمة') ? 'var(--red)' : 'var(--dim)' }}>
                  {kind} — {analysis.groups[kind].length}
                </div>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '3px 14px', marginTop: 4 }}>
                  {analysis.groups[kind].map(({ id, detail }) => (
                    <span key={id} style={{ fontSize: 12.5 }}>
                      {nameOf(id)}{detail ? <span className="dim"> ({detail})</span> : null}
                    </span>
                  ))}
                </div>
              </div>
            ))}
            {Object.keys(analysis.groups).length === 0 ? (
              <div className="ss" style={{ color: 'var(--green)' }}>كل الذرات نطقت منذ فتح اللوحة 🟢</div>
            ) : null}
          </div>
        </>
      )}
    </div>
  )
}
