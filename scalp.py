# ⚡ 5 DK TREND SCALP — KAĞIT (Sadık'ın isteği, 22.11.2026). Borsaya emir kodu YOK.
# Sürüm S1.3 — stop %2'den yakınsa girmez · TP1'de stop yerinde kalır, TP2'den itibaren çekilir (6 günlük testte −7,5 $ → +17,8 $)
# S1.2 — 5 TP (1R·1,5R·2R·2,5R·3R): TP1 → stop girişe, TP2 → stop TP1'e … her kilit ▲ tik; TP5 = çıkış
# Evren: Bitget'te son 24 saatte EN ÇOK YÜKSELEN ilk 30 kripto (hisse/ETF hariç, hacim ≥0,5 M$), saatte bir yenilenir.
# Strateji (testlerde 5 dk'da en az kaybettiren): 4 saatlikte güçlü trend + 5 dk'da EMA20'ye geri çekilip dönüş
#   LONG : 4H kapanış > EMA20 > EMA50 ve son 2 günün dibinden ≥%10 yukarıda · 5 dk: önceki mum EMA20'ye değdi, bu mum yeşil ve EMA20 üstünde kapandı
#   SHORT: tam tersi
#   Stop: son 4 mumun dibi/tepesi · 5 TP (1R…3R), her TP stopu bir basamak çeker · En çok 2 saat · aynı coine kapanıştan sonra 15 dk girilmez
# Para: 100 $ kağıt kasa · işlem başı 3 $ marj × 5x = 15 $ · en çok 10 açık
# Maliyet: giriş/çıkış %0,06 taker + %0,03 kayma (hedef limit: %0,02)
# Dürüst not: 1 aylık 5 dk testinde bu kural işlem başı ≈ −0,12…−0,19R çıktı. Burada CANLI ölçülüyor.
import json, os, threading, time, traceback
import requests

V = "S1.3 (23.11 02:00 · sıfırlandı)"
BG = "https://api.bitget.com/api/v2/mix/market/"
KLASOR = os.getenv("DATA_DIR") or ("/data" if os.path.isdir("/data") else ".")
DOSYA = os.path.join(KLASOR, "scalp5.json")
KASA0, MJ, LEV, MAXA, EVREN = 100.0, 3.0, 5, 10, 30
TAKER, MAKER, KAYMA = 0.0006, 0.0002, 0.0003
GUC, RR, MAXDK, BEKLE = 0.10, 1.5, 120, 15 * 60
TPR = (1.0, 1.5, 2.0, 2.5, 3.0)
MINR = 0.02                                             # S1.3: stop girişe %2'den yakınsa girme (gürültüde patlıyordu)                         # S1.2: 5 TP (R katı)

def tp_kur(q):                                          # eski işlemlere de 5 TP ekle
    if "tp" not in q:
        d = abs(q["giris"] - q.get("stop0", q["stop"])); q.setdefault("stop0", q["stop"])
        q["tp"] = [q["giris"] + q["u"] * k * d for k in TPR]; q["hedef"] = q["tp"][-1]; q.setdefault("tik", 0); q.setdefault("tik_t", 0)
    return q

KIL = threading.RLock()
S = {"v": 2, "kasa": KASA0, "acik": {}, "gecmis": [], "log": [], "t0": int(time.time()), "son_kapanis": {}}
D = {"fiyat": {}, "trend": {}, "trend_t": 0, "evren": [], "kripto": set(), "hata": "", "tarama_t": 0, "izle": []}

def kaydet():
    with KIL:
        try:
            tmp = DOSYA + ".tmp"
            with open(tmp, "w") as f: json.dump(S, f); f.flush(); os.fsync(f.fileno())
            os.replace(tmp, DOSYA)
        except Exception as e: D["hata"] = "kayıt: " + str(e)[:80]

def yukle():
    try:
        with open(DOSYA) as f: d = json.load(f)
        if d.get("v") == 2: S.update(d)          # S1.3: v2 = 23.11 sıfırdan başlangıç (Sadık)
    except Exception: pass

def log(m):
    with KIL: S["log"].append([int(time.time()), m]); del S["log"][:-300]

def ad(s): return s.replace("USDT", "")

def get(yol, **q):
    for i in range(3):
        try:
            r = requests.get(BG + yol, params={"productType": "USDT-FUTURES", **q}, timeout=12).json()
            if r.get("code") == "00000": return r["data"]
        except Exception: pass
        time.sleep(0.5 + i)
    return None

def ema(c, n):
    a = 2 / (n + 1); e = c[0]; o = []
    for x in c: e += a * (x - e); o.append(e)
    return o

def mum(s, g, n):
    d = get("candles", symbol=s, granularity=g, limit=str(n))
    if not d: return None
    d = sorted(d, key=lambda x: int(x[0]))
    adim = {"5m": 300, "4H": 14400}[g] * 1000
    if int(d[-1][0]) + adim > time.time() * 1000: d = d[:-1]          # sadece kapanmış mumlar
    return [[float(x[1]), float(x[2]), float(x[3]), float(x[4])] for x in d]

def evren():
    if not D["kripto"]:
        c = get("contracts") or []
        D["kripto"] = {x["symbol"] for x in c if x.get("isRwa") != "YES" and x.get("symbolStatus") == "normal"}
    tk = get("tickers") or []
    # S1.1 (Sadık): Bitget "Change" sıralaması — son 24 saatte EN ÇOK YÜKSELEN ilk 30 kripto (hisse/ETF hariç, hacim ≥ 0,5 M$ — yoksa kağıt sonuç gerçekçi olmaz)
    return [x["symbol"] for x in sorted(tk, key=lambda x: -float(x.get("change24h") or 0))
            if x["symbol"] in D["kripto"] and x["symbol"] != "USDCUSDT" and float(x.get("usdtVolume") or 0) >= 500_000][:EVREN]

def trend_guncelle():                                   # saatte bir: 4H trend yönü
    D["evren"] = evren(); tr = {}
    for s in D["evren"]:
        m = mum(s, "4H", 100); time.sleep(0.04)
        if not m or len(m) < 60: continue
        c = [x[3] for x in m]; e20 = ema(c, 20)[-1]; e50 = ema(c, 50)[-1]; son = c[-1]
        dip = min(x[2] for x in m[-13:]); tepe = max(x[1] for x in m[-13:])
        if son > e20 > e50 and son / dip - 1 >= GUC: tr[s] = (1, round((son / dip - 1) * 100, 1))
        elif son < e20 < e50 and 1 - son / tepe >= GUC: tr[s] = (-1, round((1 - son / tepe) * 100, 1))
    with KIL: D["trend"] = tr; D["trend_t"] = int(time.time())
    log(f"🧭 4H trend: {len(tr)} coin güçlü trendde " + ", ".join(f"{ad(s)}{'↑' if u == 1 else '↓'}" for s, (u, _) in tr.items()))

def tara():                                             # her 5 dk mum kapanışında
    izle = []
    for s, (u, guc) in list(D["trend"].items()):
        if s in S["acik"] or time.time() - S["son_kapanis"].get(s, 0) < BEKLE: continue
        m = mum(s, "5m", 60); time.sleep(0.04)
        if not m or len(m) < 30: continue
        c = [x[3] for x in m]; e = ema(c, 20)
        izle.append({"s": ad(s), "yon": "long" if u == 1 else "short", "guc": guc, "uz": round((c[-1] / e[-1] - 1) * 100, 2)})
        dok = m[-2][2] <= e[-2] if u == 1 else m[-2][1] >= e[-2]
        don = (c[-1] > e[-1] and c[-1] > m[-1][0]) if u == 1 else (c[-1] < e[-1] and c[-1] < m[-1][0])
        if not (dok and don): continue
        st = min(x[2] for x in m[-4:]) * 0.998 if u == 1 else max(x[1] for x in m[-4:]) * 1.002
        p = D["fiyat"].get(s) or c[-1]; g = p * (1 + u * KAYMA); risk = abs(g - st) / g
        if not (MINR <= risk <= 0.05) or u * (g - st) <= 0: continue
        with KIL:
            if len(S["acik"]) >= MAXA: log(f"⏸ {ad(s)} sinyal ama 10 işlem dolu"); continue
            adet = MJ * LEV / g
            q = tp_kur({"u": u, "giris": g, "stop": st, "stop0": st, "adet": adet, "t": int(time.time()), "risk": risk}); S["acik"][s] = q
        log(f"{'🔺 LONG' if u == 1 else '🔻 SHORT'} {ad(s)} @ {g:g} · stop {st:g} (%{risk * 100:.2f}) · TP1 {q['tp'][0]:g} … TP5 {q['tp'][4]:g} · 4H trend %{guc}")
    with KIL: D["izle"] = sorted(izle, key=lambda x: abs(x["uz"]))[:10]; D["tarama_t"] = int(time.time())
    kaydet()

def kapat(s, cik, neden, ucret):
    with KIL:
        q = S["acik"].pop(s); u = q["u"]; n = q["adet"] * q["giris"]
        pnl = q["adet"] * u * (cik - q["giris"]) - n * TAKER - q["adet"] * cik * ucret
        S["kasa"] += pnl; S["son_kapanis"][s] = time.time()
        R = pnl / (n * q["risk"]) if q["risk"] else 0
        S["gecmis"].append({"s": ad(s), "yon": "long" if u == 1 else "short", "giris": q["giris"], "cikis": cik, "t": q["t"], "tk": int(time.time()),
                            "pnl": round(pnl, 3), "R": round(R, 2), "neden": neden})
        del S["gecmis"][:-3000]
    log(f"{'✅' if pnl > 0 else '❌'} {ad(s)} kapandı · {neden} · {pnl:+.3f} $ ({R:+.2f}R)"); kaydet()

def dongu():
    yukle(); log(f"🚀 5dk Trend Scalp KAĞIT {V} başladı · kasa {S['kasa']:.2f} $")
    son5 = 0
    while True:
        try:
            tk = get("tickers") or []
            D["fiyat"] = {x["symbol"]: float(x["lastPr"]) for x in tk if x.get("lastPr")}
            for s in list(S["acik"]):
                q = S["acik"][s]; c = D["fiyat"].get(s); u = q["u"]
                if not c: continue
                tp_kur(q); k = q["tik"]
                if u * (c - q["stop"]) <= 0: kapat(s, c * (1 - u * KAYMA), ("🔒 kâr kilidi (TP%d sonrası)" % k) if k >= 2 else "stop (TP1 görmüştü)" if k == 1 else "stop", TAKER)
                elif u * (c - q["tp"][4]) >= 0: kapat(s, q["tp"][4], "🎯 TP5", MAKER)
                elif k < 4 and u * (c - q["tp"][k]) >= 0:              # ▲ tik: TP geçildi → stop bir basamak yukarı
                    with KIL:
                        while k < 4 and u * (c - q["tp"][k]) >= 0: k += 1
                        yeni = q["tp"][k - 2] if k >= 2 else q["stop"]          # S1.3: TP1'de stop yerinde, TP2→TP1, TP3→TP2…
                        if u * (yeni - q["stop"]) > 0: q["stop"] = yeni
                        q["tik"] = k; q["tik_t"] = int(time.time())
                    log(f"▲ {ad(s)} TP{k} ✓ · stop → {q['stop']:g} · kilitli {q['adet'] * u * (q['stop'] - q['giris']):+.3f} $"); kaydet()
                elif time.time() - q["t"] > MAXDK * 60: kapat(s, c * (1 - u * KAYMA), "süre (2 sa)", TAKER)
            if time.time() - D["trend_t"] > 1800: trend_guncelle()
            b = int((time.time() - 8) // 300)
            if b != son5: son5 = b; tara()
            D["hata"] = ""
        except Exception as e:
            D["hata"] = str(e)[:140]; traceback.print_exc()
        time.sleep(3)

def basla(): threading.Thread(target=dongu, daemon=True).start()

def veri():
    with KIL:
        G = S["gecmis"]; n = len(G); kz = [g for g in G if g["pnl"] > 0]; bk = sum(g["pnl"] for g in kz); bz = -sum(g["pnl"] for g in G if g["pnl"] <= 0)
        P = []; ac = 0
        for s, q in S["acik"].items():
            c = D["fiyat"].get(s) or q["giris"]; p = q["adet"] * q["u"] * (c - q["giris"]); ac += p
            tp_kur(q)
            P.append({"s": ad(s), "yon": "long" if q["u"] == 1 else "short", "giris": q["giris"], "c": c, "stop": q["stop"], "stop0": q["stop0"], "tp": q["tp"], "tik": q["tik"], "tik_t": q["tik_t"],
                      "kilit": round(q["adet"] * q["u"] * (q["stop"] - q["giris"]), 3), "t": q["t"], "pnl": round(p, 3)})
        g0 = time.time() - time.time() % 86400; bugun = [g for g in G if g["tk"] >= g0]
        return {"v": V, "t0": S["t0"], "kasa0": KASA0, "oz": round(S["kasa"] + ac, 2), "acik": round(ac, 3), "n": n, "kaz": len(kz), "r": round(sum(g["pnl"] for g in G), 2),
                "ortR": round(sum(g["R"] for g in G) / n, 3) if n else 0, "pf": round(bk / bz, 2) if bz else None,
                "bugun_n": len(bugun), "bugun_r": round(sum(g["pnl"] for g in bugun), 2),
                "P": P, "son": G[::-1][:60], "log": S["log"][::-1][:40], "trend": [{"s": ad(s), "u": u, "guc": g} for s, (u, g) in D["trend"].items()],
                "izle": D["izle"], "tarama_t": D["tarama_t"], "hata": D["hata"], "evren": len(D["evren"])}

# S1.2: panel artık ana sayfada (Trend | Scalp sekmesi) — main.py içinde
