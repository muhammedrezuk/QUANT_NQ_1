from __future__ import annotations

import sys

from pathlib import Path

from core.manifest_loader import scan

ROOT = Path(__file__).resolve().parents[1]
from build_registry.paths import RegistryAtomRoot
ATOM_ROOT = RegistryAtomRoot(ROOT)



# ٢٠٢٦-٠٩-٠٧ (قرار المالك): حُذفت شجرة الكريبتو — مشروع مستقلّ على
# جهاز آخر. الاختبارات التي تحرسها زالت معها؛ ما بقي يحرس الفوركس.


