# يكتب الذرّات السبع 404–410 (الكود والتاريخ أوّلًا، والبيان آخرًا — كتابة البيان تُقلعها).
import pathlib, sys
sys.path.insert(0, r"C:\Users\NQ\QUANT_NQ")
from shared import facts_strategies as FS

SEC = pathlib.Path(r"C:\Users\NQ\QUANT_NQ\atoms\قسم 400-449")
FOLDER = {"404": "404_استراتيجية_الاتجاه", "405": "405_استراتيجية_الانعكاس", "406": "406_استراتيجية_الاختراق",
          "407": "407_استراتيجية_الارتداد", "408": "408_استراتيجية_الزخم", "409": "409_استراتيجية_المدى",
          "410": "410_استراتيجية_السيولة"}
ATOM = '''"""{sid} استراتيجيّة {ar} — على حقائق الأقسام وحدها (ختم المالك «NQ» ٢٠٢٦-١٠-١٠: «رجّعهم على الحيّ … كلّهن»).

القاعدة قاعدة النسخة المؤرشفة (سطح المكتب ⟵ أرشيف QUANT_NQ ⟵ فكّ الأقسام عن القرار)، ومدخلها حقيقة القسم بدل التِّكّ؛
المنطق كلّه في `shared/facts_strategies.py` (المقيس في `backtest/strategies_facts_2026-10-10/`)، والجسم في
`shared/facts_strategy_atom.py`.
"""
from core.contracts.atom import AtomBase
from shared.facts_strategy_atom import FactsStrategy

ATOM_VERSION = "3.0.0"


class Atom(FactsStrategy, AtomBase):
    STRATEGY = "{sid}"
'''
HIST = '''# تاريخ الذرّة {sid}

## ٢٠٢٦-١٠-١٠ — الإصدار `3.0.0` — بختم المالك «NQ»
- **عادت إلى الحيّ على حقائق الأقسام** بأمر المالك: «رجّعهم على الحيّ بهالأرقام» ثمّ «كلّهن» — لا تحليل فيها:
  تقرأ {needs} (والوقف من 202)، بعيارات ١٠-١٠ المعتمدة.
- الإطارات {frames} في جلستَي لندن 08:00⟵16:30 ونيويورك 09:30⟵16:00؛ الزناد إغلاق الدقيقة؛ الوقف خلف آخر قاع/قمّة
  خارجيّة (202) ضمن 15–45 نقطة للناسداك (5–15 نقطة أساس لغيره)؛ الهدف 3R وأثلاث المالك في 574.
- المقيس قبلها (23 يومًا 09-08⟵10-08، الناسداك، داخل عيّنة المعايرة): `backtest/strategies_facts_2026-10-10/summary_USTEC.md`.
- النسخة السابقة (التِّكّ) في أرشيف سطح المكتب كما هي.
'''
MAN = '''id: {sid}
name: Facts Strategy {name}
version: "3.0.0"
core_version: '>=1.0.0,<2.0.0'
critical: false
entrypoint: atom:Atom
dependencies: []
publishes:
- strategy.setup.proposed
- decision.approved.state
subscribes:
- market_data.candle_closed
- platform.account.state
- platform.positions.state
- structure.external.state
{subs}
startup_mode: auto
health:
  interval_ms: 30000
  timeout_ms: 5000
  failure_threshold: 3
  restart_on_failure: false
  max_restarts: 3
  restart_backoff_ms: 1000
config_schema:
  type: object
  properties:
    symbols:
      type: array
      items:
        type: string
  additionalProperties: false
config: {{}}
metadata:
  max_idle_s: 900
  name_ar: "استراتيجيّة {ar} (حقائق الأقسام)"
'''
step = sys.argv[1]
for sid, folder in FOLDER.items():
    d = SEC / folder
    meta = FS.STRATEGIES[sid]
    if step == "code":
        d.mkdir(exist_ok=True)
        (d / "atom.py").write_text(ATOM.format(sid=sid, ar=meta["ar"]), encoding="utf-8")
        (d / "التاريخ.md").write_text(HIST.format(sid=sid, needs=" · ".join(FS.NEEDS[sid]),
                                                  frames=" · ".join(meta["frames"])), encoding="utf-8")
    else:
        subs = "\n".join("- " + e for e in FS.NEEDS[sid])
        (d / "manifest.yaml").write_text(MAN.format(sid=sid, name=meta["name"], ar=meta["ar"], subs=subs), encoding="utf-8")
    print(step, sid, d.name)
