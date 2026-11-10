"""Start the market-specific governance dashboard.

Run one process per market. Both serve the same React build but each process
reads only its own core endpoint and runtime data root.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Forex dashboard")
    parser.add_argument("--market", choices=("forex",), default="forex")
    parser.add_argument("--port", type=int, default=None, help="Internal governance port")
    args = parser.parse_args()
    os.environ["QUANT_GOV_MARKET"] = args.market
    # الجذور تُشتقّ من `shared/runtime_paths.py` (المالك) — هنا نضبط عقد الإقلاع
    # فقط، ولا نبني أيّ مسار بيانات يدويًّا (check_path_authority يحرس ذلك).
    # ٢٠٢٦-٠٩-٠٣ (فصل ٢٣ · بند ٨): اللوحة يجب أن تقرأ الجذر القانوني نفسه الذي
    # يكتبه المُقلِع — `forex_runtime/var`. بلا هذا الضبط
    # كان `server.py` يحسب أباه فيقلع في مجلّد بلا `var` (قِيس: available=false
    # على قاعدة موجودة). المالك يظلّ يتقدّم: setdefault لا يدوس ما ضبطه المستخدم.
    _runtime = ROOT / "forex_runtime"
    if _runtime.is_dir():
        os.environ.setdefault("QUANT_RUNTIME_ROOT", str(_runtime))
        os.environ.setdefault("QUANT_CORE_STATE_ROOT", str(_runtime / "var"))
        os.environ.setdefault("QUANT_ANALYSIS_SETTINGS_DB",
                              str(_runtime / "var" / "store" / "analysis_settings.db"))
    os.environ["QUANT_GOV_CORE"] = "http://127.0.0.1:8010"
    os.environ["QUANT_GOV_PORT"] = str(args.port or 8090)
    # ٢٠٢٦-٠٨-٣١ (ختم NQ): كان هنا فرضٌ لـ`NQ_NEWS_DB` و`NQ_BRIDGE_DB` على
    # `var/<السوق>/news.db` و`bridge.db` — **وكلاهما لم يوجد قطّ** (مقاس:
    # الثلاثة مسارات غير موجودة). و`server.py` يقرأ `NQ_NEWS_DB` أوّلًا، فكان
    # الفرض يدوس الافتراض الموثَّق (جسر ميتاتريدر `nq_brain.db`) ويجعل
    # `/gov/news` و`/gov/calendar` يردّان `available:false` وقائمة فارغة —
    # بينما الجسر يحمل 391 خبرًا و1130 حدثًا مكتوبة قبل دقائق.
    # هذا نفس العطل الذي يصفه تعليق `server.py:63-67` كمُصلَح: أُصلح هناك
    # بالافتراض، ونُقض هنا بالفرض. لا يُعاد ضبطهما: الفوركس يقرأ جسر
    # ميتاتريدر. (٢٠٢٦-٠٩-٠٧: أُزيل فرع السوق الثاني — سوق واحد.)
    # `MARKET` في `server.py` بلا حاجة لمتغيّر بيئة.
    from governance.server import main as server_main
    server_main()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
