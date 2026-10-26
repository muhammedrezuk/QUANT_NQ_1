"""NQ ENGINE — محرّك المسار الساخن: رحلة واحدة للحدث، ومالك واحد، وقرار واحد.

ورقة المالك «ورقة التنفيذ النهائية — NQ ENGINE» (٢٠٢٦-٠٩-١٧):

    Tick → NQ ENGINE → compiled graph → analysis → decision → risk → execution

المحرّك يحقّق **واجهة الناقل نفسها** التي تناديها النواة المختومة
(`subscribe · subscribe_all · publish · unsubscribe_all · stats ·
transport_stats · last_states · event_names · subscriber_count · drain ·
close`)، فيدخل من `governance/scripts/run_core.py` وحده و`core/` لا تُمَسّ.

الحزمة أربعة ملفّات:

    graph.py      — الرسم الساخن: مستهلكو كلّ حدث بترتيبٍ ثابت، وما يُنتج
                    كلّ مستهلك، وكشف الدورات، والختم
    scheduler.py  — مدخل المحرّك: لكلّ `Account×Symbol` طابورٌ لكلّ تِكّة
                    وحزمةٌ بإيقاع «الأحدث يكفي» — الحمل مسقوفٌ بعدد الرموز
    engine.py     — المحرّك نفسه: التصريف المباشر داخل دورة التِكّة، والمسار
                    البارد خارجها
    cold_host.py  — العمليّة الباردة (المرحلة F): المخازن والقياس والمراقبة في
                    مفسّرٍ مستقلّ، إيداعٌ بلا انتظار ولا IPC في المسار الساخن
"""
from .cold_host import ColdProcess
from .symbol_host import SymbolEngine, SymbolRouter
from .engine import NQEngine
from .graph import HotGraph, HotSubscription
from .scheduler import GLOBAL_SCOPE, ScopeScheduler, scope_of

__all__ = ["NQEngine", "ColdProcess", "SymbolEngine", "SymbolRouter", "HotGraph", "HotSubscription", "ScopeScheduler",
           "GLOBAL_SCOPE", "scope_of"]
