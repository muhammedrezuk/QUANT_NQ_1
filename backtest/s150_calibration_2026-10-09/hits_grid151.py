# -*- coding: utf-8 -*-
"""151 — «كم من 100» لكلّ تركيبة (سريع/بطيء/ميل) على إطارٍ وجلسة، في الخزائن الثلاث.

لكلّ تركيبة: حين قال حكم الذرّة «صاعد» كم مرّة صعد السعر حتّى نهاية الجلسة، وحين قال «هابط» كم مرّة هبط،
وكم مرّة صعد السعر أصلًا (اشترِ دائمًا). الزيادة = (صاعد − صعد أصلًا) + (هابط − هبط أصلًا): ما تضيفه الذرّة
على «اشترِ دائمًا» و«بع دائمًا» معًا، بنقاط من 100. الترتيب بالاكتشاف وحده؛ التحقّق والخزنة للحكم.

الاستعمال:  python hits_grid151.py --frame 5m --target ny [--fact pattern] [--in DIR]
"""
import argparse
import json
import pathlib
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import eval151 as E  # noqa: E402


def hits(s, r):
    up, dn = s == 1, s == -1
    if up.sum() < 20 or dn.sum() < 20:
        return None
    base = float((r > 0).mean()) * 100
    uh = float((r[up] > 0).mean()) * 100
    dh = float((r[dn] < 0).mean()) * 100
    return {"up": round(uh, 1), "dn": round(dh, 1), "base": round(base, 1),
            "edge": round((uh - base) + (dh - (100 - base)), 1), "n_up": int(up.sum()), "n_dn": int(dn.sum())}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--frame", required=True)
    ap.add_argument("--target", required=True)
    ap.add_argument("--fact", default="pattern")
    ap.add_argument("--in", dest="inp", default=str(E.SCRATCH / "out2"))
    a = ap.parse_args()
    sess = E.sessions() if a.target in ("london", "ny") else {}
    rows = []
    for f in sorted(pathlib.Path(a.inp).glob(f"{a.frame}_*.npz")):
        z = np.load(f)
        cfg = json.loads(str(z["cfg"]))
        idx, r, tt = E.targets(z, a.frame, sess)[a.target]
        s = E.facts_of(z, E.quantiles(z))[a.fact][idx]
        row = {"cfg": f.stem[len(a.frame) + 1:], "fast": cfg["ema_fast"], "slow": cfg["ema_slow"],
               "k": cfg["slope_lookback"]}
        for p, (p0, p1) in E.PERIODS.items():
            m = (tt >= p0) & (tt < p1)
            row[p] = hits(s[m], r[m])
        rows.append(row)
    rows = [r for r in rows if r["disc"]]
    rows.sort(key=lambda r: -r["disc"]["edge"])
    out = E.D / f"hits_{a.frame}_{a.target}_{a.fact}.json"
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    cell = lambda h: f"ص{h['up']:5.1f} ه{h['dn']:5.1f} أصلًا{h['base']:5.1f} زيادة{h['edge']:+5.1f}" if h else "—"  # noqa: E731
    for r in rows:
        print(f"{r['fast']:>3}/{r['slow']:<3} ميل{r['k']:>2} | {cell(r['disc'])} | {cell(r['val'])} | {cell(r['vault'])}")


if __name__ == "__main__":
    main()
