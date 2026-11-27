# Bütün Bitget USDT vadeli coinler (RWA hariç) — 15 dk mumlar, ~125 gün. Her coin: veri/<SYM>.npy  [ts, o, h, l, c, quoteVol]
import requests, time, os, numpy as np, sys
from concurrent.futures import ThreadPoolExecutor
BG = "https://api.bitget.com/api/v2/mix/market/"
def g(y, **q):
    for i in range(6):
        try:
            r = requests.get(BG + y, params={"productType": "USDT-FUTURES", **q}, timeout=20).json()
            if r.get("code") == "00000": return r["data"]
            if r.get("code") in ("429", "40429"): time.sleep(2 + i)
        except Exception: time.sleep(1 + i)
    return None
ks = [x for x in g("contracts") if x.get("isRwa") != "YES" and x.get("symbolStatus") == "normal"]
ss = [x["symbol"] for x in ks]
open("liste.txt", "w").write("\n".join(f'{x["symbol"]} {x.get("openTime") or ""}' for x in ks))
SON = int(time.time() // 900 * 900 * 1000); BAS = SON - 125 * 86400 * 1000
def al(s):
    yol = f"veri/{s}.npy"
    if os.path.exists(yol): return s, -1
    m = {}; end = SON
    while end > BAS:
        d = g("history-candles", symbol=s, granularity="15m", limit="200", endTime=str(end))
        if not d: break
        for x in d: m[int(x[0])] = [int(x[0])] + [float(v) for v in x[1:5]] + [float(x[6])]
        e2 = min(int(x[0]) for x in d) - 1
        if e2 >= end: break
        end = e2; time.sleep(0.05)
    if m:
        a = np.array([m[k] for k in sorted(m)], dtype=np.float64); np.save(yol, a); return s, len(a)
    return s, 0
n = 0
with ThreadPoolExecutor(10) as ex:
    for s, k in ex.map(al, ss):
        n += 1
        if n % 25 == 0: print(n, "/", len(ss), s, k, flush=True)
print("bitti", len(os.listdir("veri")))
