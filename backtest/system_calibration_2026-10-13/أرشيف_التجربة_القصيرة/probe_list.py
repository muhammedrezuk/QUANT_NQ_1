import os, sys, sqlite3, json
os.environ["CALIB_SCRATCH"] = r"C:\Users\NQ\QUANT_NQ\backtest\system_calibration_2026-10-13\work\probe"
sys.path.insert(0, r"C:\Users\NQ\QUANT_NQ\backtest\s150_calibration_2026-10-09")
import calib_day as C
cat = C.catalog()
need = []
for a in ("151","152","156","163","165","202","204","254","310","315","358"):
    for x in C.chain(cat, a):
        if x not in need: need.append(x)
print("chain", need)
for a in need:
    g = C.grid(cat, a)
    print(a, cat[a]["dir"].name, [s for s in cat[a]["sub"]], json.dumps(cat[a]["config"])[:300], "| tags:", [t for t,_ in g if t.startswith("all")])
db = sqlite3.connect(C.HIST, uri=True)
print(db.execute("select min(period_start), max(period_start), count(*) from candles_history where symbol='USTEC' and period='M1'").fetchone())
