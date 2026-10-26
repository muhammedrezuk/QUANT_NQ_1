# -*- coding: utf-8 -*-
"""البِب — وحدة المسافة الواحدة في قواعد التداول (ختم المالك «nq» ٢٠٢٦-١٠-١٧: «بِب، استعمل بِب على كلّ السستم، ما في شي اسمه نقاط
أساس»). كانت قواعد الوقف والهامش و«لا مستوى أمامه» بنقاط الأساس (جزءٌ من عشرة آلاف من السعر)؛ صارت بالبِب، وأرقامها حُوّلت بأسعار
١٠-١٧ فلا يتغيّر سلوكٌ يومها (التفصيل في `trade_setup.MIN_STOP_PIPS` و`facts_strategies.STOP_PIPS`).

حجم البِب لكلّ أصل — العرف عند الوسطاء والمتداولين:
  العملات 0.0001 (أزواج الين 0.01) · الذهب 0.1 · الفضّة 0.01 · المؤشّرات (الناسداك · الداو · الإس آند بي) 1.0 نقطة · البتكوين 1.0 دولار.
وما لا يُعرف من الرموز ⟸ 1.0. (ونقاط الأساس في أسعار الفائدة — قرار الاحتياطيّ 25 نقطة أساس — شيءٌ آخر لا مسافة سعر، فلا تُحوَّل.)
"""
from __future__ import annotations

from typing import Any

PIP_BY_SYMBOL = {"USTEC": 1.0, "US30": 1.0, "US500": 1.0, "UK100": 1.0, "DE40": 1.0,
                 "XAUUSD": 0.1, "XAGUSD": 0.01, "BTCUSD": 1.0, "ETHUSD": 1.0}
FOREX_PIP = 0.0001
YEN_PIP = 0.01
DEFAULT_PIP = 1.0
_FOREX_LEN = 6


def _sym(symbol: Any) -> str:
    return str(symbol or "").strip().upper()


def is_forex(symbol: Any) -> bool:
    s = _sym(symbol)
    return len(s) == _FOREX_LEN and s.isalpha() and s not in PIP_BY_SYMBOL


def pip_size(symbol: Any) -> float:
    """قيمة البِب الواحد بوحدة السعر لهذا الرمز."""
    s = _sym(symbol)
    if s in PIP_BY_SYMBOL:
        return PIP_BY_SYMBOL[s]
    if is_forex(s):
        return YEN_PIP if s.endswith("JPY") else FOREX_PIP
    return DEFAULT_PIP


def to_pips(distance: float, symbol: Any) -> float:
    """مسافة سعرٍ ⟵ بِب."""
    return abs(float(distance)) / pip_size(symbol)


def from_pips(pips: float, symbol: Any) -> float:
    """بِب ⟵ مسافة سعر."""
    return float(pips) * pip_size(symbol)
