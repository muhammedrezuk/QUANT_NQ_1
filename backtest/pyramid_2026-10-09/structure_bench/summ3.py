import json
top = json.load(open("top.json", encoding="utf-8"))
print("== القمّة (2018 ⟵ 2026، اختبار من 2024-02-19) ==")
rows = [r for r in top if r["train"]["n"] >= 300]
print("أعلى موافقة في الاختبار:", max((r["test"]["agree"] or 0) for r in rows), "· عدد ما تجاوز 0.55:", sum(1 for r in rows if (r["test"]["agree"] or 0) > 0.55), "من", len(rows))
for r in sorted(rows, key=lambda r: -(r["test"]["t"] or -9))[:6]:
    a, b = r["train"], r["test"]
    print(f'{r["frame"]:>3} lb{r["lb"]} {r["signal"]:<18} {r["session"]:<6} | تعلّم {a["agree"]} م={a["mean_bps"]} t={a["t"]} | اختبار {b["agree"]} n={b["n"]} م={b["mean_bps"]} t={b["t"]} | صعود {b["up_base"]}')
mid = json.load(open("mid.json", encoding="utf-8"))
print("\n== الوسط: صفقات الكسر (وقف 15–50 نقطة من آخر قمّة/قاع، 3R، أثلاث) ==")
for r in sorted(mid, key=lambda r: -((r["train"]["R_per"] or -9) if (r["train"]["n"] or 0) >= 100 else -9))[:16]:
    a, b = r["train"], r["test"]
    print(f'{r["frame"]:>3} lb{r["lb"]} {r["kind"]:<5} {r["filter"]:<4} | تعلّم n={a["n"]:>4} R={a["R_per"]} pf={a["pf"]} t3={a["t3%"]} | اختبار n={b["n"]:>4} R={b["R_per"]} pf={b["pf"]} وقف={b["stop%"]} t1={b["t1_be%"]} t2={b["t2%"]} t3={b["t3%"]} | {r["stops"]}')
