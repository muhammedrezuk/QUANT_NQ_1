"""404 استراتيجيّة الاتّجاه — على حقائق الأقسام وحدها (ختم المالك «NQ» ٢٠٢٦-١٠-١٠: «رجّعهم على الحيّ … كلّهن»).

القاعدة قاعدة النسخة المؤرشفة (سطح المكتب ⟵ أرشيف QUANT_NQ ⟵ فكّ الأقسام عن القرار)، ومدخلها حقيقة القسم بدل التِّكّ؛
المنطق كلّه في `shared/facts_strategies.py` (المقيس في `backtest/strategies_facts_2026-10-10/`)، والجسم في
`shared/facts_strategy_atom.py`.
"""
from core.contracts.atom import AtomBase
from shared import strategy_switch
from shared.facts_strategy_atom import FactsStrategy

ATOM_VERSION = "3.1.1"


class Atom(FactsStrategy, AtomBase):
    STRATEGY = "404"

    async def _evaluate(self, symbol, m, close):
        # 2026-10-17 (owner seal "NQ"): only the strategies named in shared/strategy_switch.json send decisions.
        if not strategy_switch.active(self.STRATEGY):
            self._bump("PAUSED_BY_OWNER")
            return
        await super()._evaluate(symbol, m, close)
