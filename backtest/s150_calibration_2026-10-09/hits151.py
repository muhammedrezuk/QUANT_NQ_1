# -*- coding: utf-8 -*-
"""151 بلغة المالك: «كم مرّة من 100 تصيب؟» — للعيار الحيّ ولأفضل عيارٍ في الاكتشاف.

الإصابة: قالت الحقيقة «صاعد» فصعد السعر بعدها، أو «هابط» فهبط. وبجانبها «اشترِ دائمًا»: كم مرّة من 100 صعد
السعر أصلًا في العيّنات نفسها — فالإصابة لا تعني شيئًا إلّا إن زادت عليه في الصاعد وعلى عكسه في الهابط.
"""
import json
import pathlib
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import eval151 as E  # noqa: E402

FACT_NAMES = {"pattern": "حكم الذرّة (صاعد/هابط)", "slow": "الإغلاق فوق/تحت متوسّط 20"}
TARGET_NAMES = {"H1": "الشمعة التالية", "H12": "بعد 12 شمعة", "london": "جلسة لندن", "ny": "جلسة نيويورك"}


def hits(s, r):
    up, dn = s == 1, s == -1
    n = int(up.sum() + dn.sum())
    if n < 30:
        return None
    ok = int(((r > 0) & up).sum() + ((r < 0) & dn).sum())
    return {"n": n, "hit": round(100 * ok / n, 1), "up_hit": round(100 * float((r[up] > 0).mean()), 1),
            "dn_hit": round(100 * float((r[dn] < 0).mean()), 1), "base_up": round(100 * float((r > 0).mean()), 1)}


def main():
    inp = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else E.SCRATCH / "out")
    sess = E.sessions()
    out = []
    for frame in ("5m", "15m", "1h", "4h", "1d"):
        z = np.load(inp / f"{frame}_live.npz")
        facts = E.facts_of(z, E.quantiles(z))
        for tg, (idx, r, tt) in E.targets(z, frame, sess).items():
            if tg not in TARGET_NAMES:
                continue
            for fact in FACT_NAMES:
                s = facts[fact][idx]
                row = {"frame": frame, "fact": fact, "target": tg}
                for p, (p0, p1) in E.PERIODS.items():
                    m = (tt >= p0) & (tt < p1)
                    row[p] = hits(s[m], r[m])
                out.append(row)
    (E.D / "hits_live.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    for row in out:
        cells = []
        for p in ("disc", "val", "vault"):
            h = row[p]
            cells.append(f"{h['hit']:5.1f} (ص{h['up_hit']:5.1f} ه{h['dn_hit']:5.1f} | صعد أصلًا {h['base_up']:5.1f}) n{h['n']}"
                         if h else "—")
        print(row["frame"], FACT_NAMES[row["fact"]], TARGET_NAMES[row["target"]], " || ".join(cells))


if __name__ == "__main__":
    main()
