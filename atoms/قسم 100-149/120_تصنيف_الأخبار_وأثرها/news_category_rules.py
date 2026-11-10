"""قواعد الذرّة 120 — تصنيف العنوان بقوائم كلماتٍ مسمّاة، وسعر الناسداك عند لحظةٍ معلومة.

٢٠٢٦-١٠-٠٨ (ختم المالك «NQ» — المعرفة أوّلًا): وحدةٌ شقيقة بلا حالة ولا ناقل — دوالّ خالصة تُختبر وحدها.

⛔ حدٌّ معلَن: هذا **تصنيفٌ بمطابقة كلماتٍ** لا فهمٌ للمضمون. «Fed holds rates» و«Fed cuts rates» صنفٌ واحد
   (نقديّ)، و«ceasefire» تقع في الجيوسياسيّ كما تقع «war». الصنف يقول «ذُكرت كلمةٌ من القائمة» لا «ما الذي حدث».

المطابقة الإنكليزيّة بحدود الكلمة (`\\b`) مع جمعٍ اختياريّ بـ`s` فقط: «war» تطابق «war» و«wars» ولا تطابق «warns»
ولا «warning» ولا «Warner» — وهذه كانت علّة القائمة القديمة. والمسافة في العبارة تقبل الشرطة («rate-cut»).
والعربيّة بحدود الكلمة أيضًا مع سوابق الإلصاق (و · ف · ب · ل · ك · ال) ولواحق قليلة (ة · ي · ية · ات · ين) —
فـ«أبل» لا تطابق «مقابل». مقيس ٢٠٢٦-١٠-٠٨: صفر عنوانٍ عربيّ في قاعدة الجسر (من 1432)، فالقوائم العربيّة احتياطٌ معلَن.
"""
from __future__ import annotations

import re
from bisect import bisect_right
from typing import Any

MONETARY = "monetary"
GEOPOLITICS = "geopolitics"
TRADE = "trade"
COMPANIES = "companies"
DATA = "data"
OTHER = "other"
#: ترتيب العرض والعدّ. `other` آخرها: لا تُطابَق، بل تُعطى لعنوانٍ لم يقع في غيرها.
CATEGORIES = (MONETARY, GEOPOLITICS, TRADE, COMPANIES, DATA, OTHER)
LABELS_AR = {MONETARY: "نقديّ", GEOPOLITICS: "جيوسياسيّ", TRADE: "تجارة",
             COMPANIES: "شركات", DATA: "بيانات", OTHER: "أخرى"}

# ٢٠٢٦-١٠-٠٨ (ختم المالك «NQ» — المعرفة أوّلًا): القوائم من نصّ المالك، وما زيد عليها مرادفٌ للكلمة نفسها
# (رمز السهم مع اسم الشركة، والمدينة مع البلد، وعوائد السندات مع الفائدة، والاندماج والاستحواذ مع الشركات).
# كلمة «trade» وحدها **ليست** في القائمة: «close of trade» تتكرّر في عناوين البورصات اليوميّة (مقيس: «Mexico
# stocks lower at close of trade») — فالعبارات المركّبة وحدها. ومقيس على 1432 عنوانًا في قاعدة الجسر (١٠-٠٨):
# نقديّ 679 (منها 123 بكلمة العوائد وحدها) · أخرى 591 · بيانات 132 · شركات 80 · جيوسياسيّ 50 · تجارة 42
# (137 عنوانًا في أكثر من صنف).
TERMS_EN: dict[str, tuple[str, ...]] = {
    MONETARY: ("fed", "federal reserve", "fomc", "powell", "interest rate", "rate cut", "rate hike",
               "cut rates", "hike rates", "raise rates", "rate decision", "inflation", "hawkish", "dovish",
               "central bank", "monetary policy", "treasury yield", "bond yield", "note yield", "yields",
               "treasuries", "ecb", "boj", "boe"),
    GEOPOLITICS: ("war", "warfare", "attack", "attacked", "airstrike", "air strike", "missile", "sanction",
                  "conflict", "military", "troops", "invasion", "invade", "ceasefire", "cease-fire",
                  "taiwan", "iran", "iranian", "tehran", "russia", "russian", "kremlin", "putin", "ukraine",
                  "ukrainian", "kyiv", "israel", "israeli", "gaza", "hamas", "hezbollah", "houthi", "red sea",
                  "middle east", "hormuz", "north korea", "nato", "geopolitical", "terror", "terrorist",
                  "terrorism"),
    TRADE: ("tariff", "trade war", "trade deal", "trade talks", "trade tension", "trade agreement",
            "trade policy", "trade deficit", "trade balance", "trade dispute", "trade truce", "export control",
            "export ban", "import ban", "customs duties", "protectionism", "china", "chinese", "beijing",
            "xi jinping", "wto"),
    COMPANIES: ("apple", "aapl", "microsoft", "msft", "nvidia", "nvda", "amazon", "amzn", "tesla", "tsla",
                "meta", "meta platforms", "google", "googl", "goog", "alphabet", "earnings", "guidance",
                "profit", "revenue", "quarterly results", "eps", "ipo", "magnificent seven", "merger",
                "acquisition", "takeover"),
    DATA: ("jobs", "jobs report", "payroll", "nonfarm", "non-farm", "unemployment", "jobless", "employment",
           "labor market", "labour market", "jolts", "gdp", "gross domestic product", "retail sales", "pmi",
           "ism", "purchasing managers", "cpi", "ppi", "pce", "consumer confidence", "consumer sentiment",
           "durable goods", "housing starts", "industrial production", "factory orders", "economic data"),
}
TERMS_AR: dict[str, tuple[str, ...]] = {
    MONETARY: ("فيدرالي", "فدرالي", "الاحتياطي الفيدرالي", "فائدة", "باول", "تضخم", "البنك المركزي"),
    GEOPOLITICS: ("حرب", "حروب", "هجوم", "هجمات", "عقوبات", "صاروخ", "صواريخ", "نزاع", "صراع", "تايوان",
                  "إيران", "ايران", "روسيا", "روسي", "أوكرانيا", "اوكرانيا", "الشرق الأوسط", "الشرق الاوسط",
                  "إسرائيل", "اسرائيل", "غزة", "هرمز"),
    TRADE: ("رسوم جمركية", "جمركي", "تجارة", "تجاري", "الصين", "صيني"),
    COMPANIES: ("أبل", "آبل", "مايكروسوفت", "إنفيديا", "انفيديا", "أمازون", "امازون", "تسلا", "ميتا", "جوجل",
                "غوغل", "ألفابت", "أرباح", "ارباح", "توجيهات"),
    DATA: ("وظائف", "رواتب", "بطالة", "الناتج المحلي", "مبيعات التجزئة", "مديري المشتريات", "أسعار المستهلكين"),
}
#: عباراتٌ تُمحى قبل المطابقة لأنّ فيها كلمةً من القوائم بغير معناها: «profit-taking» جني أرباح السوق لا أرباح شركة.
SCRUB = re.compile(r"\bprofit[\s-]+taking\b", re.IGNORECASE)
#: وتُمحى للجيوسياسيّ وحده: «trade war» و«price war» حربٌ بالاسم لا بالسلاح (والأولى تبقى في صنف التجارة).
CATEGORY_SCRUB = {GEOPOLITICS: re.compile(
    r"\b(?:trade|tariff|currency|price|pricing|bidding|talent|culture|streaming)[\s-]+wars?\b", re.IGNORECASE)}
_AR_PREFIX = r"(?:[وفبلك]?(?:ال|لل)?)"
_AR_SUFFIX = r"(?:ة|ي|ية|ات|ين)?"


def _english(term: str) -> str:
    body = r"[\s-]+".join(re.escape(word) for word in term.split())
    return r"\b%ss?\b" % body


def _arabic(term: str) -> str:
    body = r"\s+".join(re.escape(word) for word in term.split())
    return r"(?<!\w)%s%s%s(?!\w)" % (_AR_PREFIX, body, _AR_SUFFIX)


PATTERNS = {name: re.compile("|".join([_english(t) for t in TERMS_EN[name]]
                                      + [_arabic(t) for t in TERMS_AR.get(name, ())]), re.IGNORECASE)
            for name in TERMS_EN}


def _text_for(name: str, headline: Any) -> str:
    text = SCRUB.sub(" ", str(headline or ""))
    scrub = CATEGORY_SCRUB.get(name)
    return scrub.sub(" ", text) if scrub is not None else text


def classify(headline: Any) -> list[str]:
    """أصناف العنوان بالترتيب المعلن — قد يقع في أكثر من صنف؛ وما لم يقع في شيءٍ ⟸ `other` وحده."""
    found = [name for name in CATEGORIES
             if name in PATTERNS and PATTERNS[name].search(_text_for(name, headline))]
    return found or [OTHER]


def matched_terms(headline: Any) -> dict[str, list[str]]:
    """الكلمات التي طابقت فعلًا لكلّ صنف — ليُرى لماذا صُنّف العنوان (للاختبار والتدقيق)."""
    found = {name: sorted({m.group(0).lower() for m in pattern.finditer(_text_for(name, headline))})
             for name, pattern in PATTERNS.items()}
    return {name: terms for name, terms in found.items() if terms}


def price_at(closes: list[tuple[float, float]], target: float,
             tolerance_s: float) -> tuple[bool, float | None]:
    """سعر الإغلاق المعروف عند اللحظة `target` من شموعٍ مغلقة `(وقت_الإغلاق، الإغلاق)` مرتّبة.

    يعود `(False, None)` ما لم تُغلق شمعةٌ عند `target` أو بعده — أي قبل أن تمرّ اللحظة نفسها في السوق، فلا
    تُملأ حركة 60 د قبل مرور 60 د. وبعدها `(True, إغلاق آخر شمعةٍ أُغلقت عند `target` أو قبله)` — ماضٍ لا مستقبل،
    أو `(True, None)` إن كان ذلك الإغلاق أبعد عن `target` من `tolerance_s` (فجوة: سوقٌ مغلق أو انقطاع) أو أقدم
    من المخزون.
    """
    if not closes or closes[-1][0] < target:
        return False, None
    index = bisect_right(closes, target, key=lambda row: row[0]) - 1
    if index < 0:
        return True, None
    close_at, price = closes[index]
    if target - close_at > tolerance_s:
        return True, None
    return True, price


def move_pct(base: float, price: float) -> float:
    """الحركة ٪ من سعر الخبر إلى سعرٍ لاحق — رقمٌ خام بإشارته."""
    return round((price - base) / base * 100, 4)
