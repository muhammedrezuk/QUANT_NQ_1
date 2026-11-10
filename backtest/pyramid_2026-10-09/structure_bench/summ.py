import json
top = json.load(open("top.json", encoding="utf-8"))
print("== القمّة: موافقة جهة الجلسة (تعلّم ⟵ اختبار) — الأفضل على التعلّم ==")
rows = [r for r in top if r["train"]["n"] >= 300]
rows.sort(key=lambda r: -(r["train"]["agree"] or 0))
for r in rows[:14]:
    a, b = r["train"], r["test"]
    print(f'{r["frame"]:>3} lb{r["lb"]} {r["signal"]:<18} {r["session"]:<6} | تعلّم {a["agree"]:.3f} n={a["n"]:>4} م={a["mean_bps"]:>6} t={a["t"]} | اختبار {b["agree"]} n={b["n"]} م={b["mean_bps"]} t={b["t"]} | صعود {b["up_base"]}')
print("عدد ما تجاوز 0.55 في الاختبار:", sum(1 for r in top if (r["test"]["agree"] or 0) > 0.55 and r["test"]["n"] >= 200), "من", len(top))
mid = json.load(open("mid.json", encoding="utf-8"))
print("\n== الوسط: صفقات الكسر بأثلاث المالك — الأفضل على التعلّم (n ≥ 150) ==")
rows = [r for r in mid if (r["train"]["n"] or 0) >= 150]
rows.sort(key=lambda r: -(r["train"]["R_per"] or -9))
for r in rows[:14]:
    a, b = r["train"], r["test"]
    print(f'{r["frame"]:>3} lb{r["lb"]} {r["kind"]:<5} {r["filter"]:<4} | تعلّم n={a["n"]:>4} R={a["R_per"]} pf={a["pf"]} t3={a["t3%"]} | اختبار n={b["n"]:>4} R={b["R_per"]} pf={b["pf"]} وقف={b["stop%"]} t1={b["t1_be%"]} t2={b["t2%"]} t3={b["t3%"]} | وقوف {r["stops"]}')
print("\nأنصاف الاختبار لأفضل ثلاث:")
for r in rows[:3]:
    print(r["frame"], r["lb"], r["kind"], r["filter"], r["test_halves"])
best_t3 = max((r for r in mid if (r["test"]["n"] or 0) >= 50), key=lambda r: r["test"]["t3%"] or 0)
print("\nأعلى نسبة هدف ثالث في الاختبار:", best_t3["frame"], best_t3["lb"], best_t3["kind"], best_t3["filter"], best_t3["test"])
