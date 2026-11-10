# -*- coding: utf-8 -*-
"""تشخيص على التعلّم وحده: توزيع (مدى الصندوق ÷ مدى اليوم) عند إغلاقات النوافذ، ونسبة الانفجارات."""
import sys

sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
sys.argv = [sys.argv[0], "noop"]
import squeeze as Q
R = Q.R

for m in (6, 12):
    bh, bl, okc = Q.BOX[m]
    ratios, brk = [], {0.10: 0, 0.15: 0, 0.20: 0, 0.25: 0}
    days = set()
    for j in range(Q.J0, Q.N5):
        tc = Q.m5[j][0] + 300
        if tc >= Q.SPLIT:
            break
        if not Q.WIN[j] or not okc[j] or Q.IDD[j] < 0:
            continue
        adr = R.ad1[Q.IDD[j]]
        x = (bh[j] - bl[j]) / adr
        ratios.append(x)
        cl = Q.m5[j][4]
        if cl > bh[j] or cl < bl[j]:
            for k in brk:
                if x <= k:
                    brk[k] += 1
    ratios.sort()
    qs = {p: round(ratios[int(p / 100 * (len(ratios) - 1))], 3) for p in (10, 25, 50, 75, 90)}
    share = {k: round(sum(1 for r in ratios if r <= k) / len(ratios), 3) for k in brk}
    print("م=%d إغلاقات=%d مئينات=%s حصّة≤ق=%s انفجارات≤ق=%s" % (m, len(ratios), qs, share, brk), flush=True)
lq = [Q.LOWQ[j - 1] for j in range(Q.J0, Q.N5) if Q.WIN[j] and Q.m5[j][0] + 300 < Q.SPLIT]
print("ربع متدحرج: حصّة الإغلاقات المنضغطة في النوافذ = %.3f" % (sum(lq) / len(lq)), flush=True)
adrs = sorted(R.ad1[Q.IDD[j]] for j in range(Q.J0, Q.N5) if Q.WIN[j] and Q.IDD[j] >= 0)
a5s = sorted(R.a5[j] for j in range(Q.J0, Q.N5) if Q.WIN[j])
print("مدى اليوم وسيط=%.1f · مدى 5د وسيط في النوافذ=%.1f" % (adrs[len(adrs) // 2], a5s[len(a5s) // 2]), flush=True)
