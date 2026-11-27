# 🎯 ÜÇLÜ ONAY — KAĞIT scalp bot (borsaya emir YOK). Sürüm U1.0 (27.11)
# Sadık: "bütün botları kaldıralım, 1 yeni scalp: 2 günlük trend var mı, sonra 1 saatlik, sonra 15 dakika — aynı yöndeyse işlem açsın"
# 3 aylık 15 dk verisinde (40 coin, 54 ayar denendi) 4 dönemin dördünde de artı kalan TEK ayar seçildi:
#   giriş (her 15 dk mum kapanışı): 2 gün önceye göre ≥ %10 yükseliş + son 1 saat yükselmiş (1s mum yeşil ve önceki 1s kapanışın üstü)
#          + son 15 dk mumu yeşil → LONG · tam tersi → SHORT · market giriş
#   çıkış: stop %4 · TP'ler %1 arayla (sınırsız) · TP2'de stop TP1'e, TP3'te TP2'ye… (▲) · en çok 6 saat
#   para : 100 $ kağıt · 3 $ × 5x · en çok 30 açık · aynı coine 30 dk sonra tekrar
#   test : 3 ayda 4.679 işlem, %60 kazanan, +85,9 $ (dönemler +2,2 / +10,6 / +14,5 / +61,2) — avantaj ince (işlem başı ~2 sent), kârın çoğu son dönemde
# U1.1: stop %4 → %8 (Sadık: biraz geniş) — 3 ayda +85,9 → +123,2 $, dört dönemde de artı (+17 / +7 / +20 / +81)
# Eski Momentum botları (ani patlama / merdiven / serbest) arsiv/ klasöründe.
import json, os, threading, time, traceback, base64, hmac
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import requests

V = "U1.1 (27.11 10:15)"
BG = "https://api.bitget.com/api/v2/mix/market/"
KASA0, MJ, LEV, MAXA = 100.0, 3.0, 5, 30
GUN2, SL, TP_ADIM, MAX_SAAT, BEKLE = 0.10, 0.08, 0.01, 6, 1800
EVREN, MIN_HAC = 40, 3e6
TAKER, MAKER, KAYMA = 0.0006, 0.0002, 0.0005
ESKI = {"BTC", "ETH", "XRP", "ADA", "DOGE", "TRX", "LTC", "BCH", "BNB", "XLM", "ETC", "DOT", "LINK", "SHIB", "AVAX", "XMR", "UNI", "ATOM",
        "FIL", "NEAR", "SOL", "HBAR", "AAVE", "QNT", "ALGO", "VET", "ICP", "EOS", "XTZ", "THETA", "MKR", "AXS", "SAND", "MANA"}
KLASOR = os.getenv("DATA_DIR") or ("/data" if os.path.isdir("/data") else ".")
DOSYA = os.path.join(KLASOR, "uclu.json")
KIL = threading.RLock()
S = {"v": 1, "nakit": KASA0, "acik": {}, "gecmis": [], "log": [], "t0": int(time.time()), "son_kapanis": {}, "bar": 0}
D = {"fiyat": {}, "izle": [], "tarama_t": 0, "hata": "", "mum": {}, "kripto": set(), "kripto_t": 0}

def get(yol, **q):
    for i in range(3):
        try:
            r = requests.get(BG + yol, params={"productType": "USDT-FUTURES", **q}, timeout=10).json()
            if r.get("code") == "00000": return r["data"]
        except Exception: pass
        time.sleep(0.5 + i)
    return None

def log(m):
    with KIL: S["log"].append([int(time.time()), m]); del S["log"][:-200]
    print(m, flush=True)

def kaydet():
    with KIL:
        tmp = DOSYA + ".tmp"
        with open(tmp, "w") as f: json.dump(S, f, ensure_ascii=False); f.flush(); os.fsync(f.fileno())
        os.replace(tmp, DOSYA)

def yukle():
    try:
        d = json.load(open(DOSYA))
        if d.get("v") == 1: S.update(d)
    except Exception: pass

def ad(s): return s[:-4]

def mumlar(s, g, n):
    d = get("candles", symbol=s, granularity=g, limit=str(n))
    if not d: return None
    return [[int(x[0]), float(x[1]), float(x[2]), float(x[3]), float(x[4])] for x in sorted(d, key=lambda x: int(x[0]))]

def kapali15(s):
    m = mumlar(s, "15m", 200)
    if not m: return None
    if m[-1][0] + 900_000 > time.time() * 1000: m = m[:-1]             # oluşan mumu at
    return m

def kripto_listesi():
    if time.time() - D["kripto_t"] < 3600 and D["kripto"]: return D["kripto"]
    ks = get("contracts") or []
    if ks: D["kripto"] = {x["symbol"] for x in ks if x.get("isRwa") != "YES" and x.get("symbolStatus") == "normal"}; D["kripto_t"] = time.time()
    return D["kripto"]

# ───────────────────────── İŞLEM ─────────────────────────
def tp_fiyat(q, k): return q["giris"] * (1 + q["u"] * TP_ADIM * (k + 1))      # k=0 → TP1

def ac(s, u, c, neden):
    g = c * (1 + u * KAYMA)
    with KIL:
        S["nakit"] -= MJ + MJ * LEV * TAKER
        S["acik"][s] = {"u": u, "giris": g, "stop": g * (1 - u * SL), "stop0": g * (1 - u * SL), "tik": 0, "tik_t": 0, "tikler": [],
                        "adet": MJ * LEV / g, "t": int(time.time()), "neden": neden}
    log(f"{'🟢 LONG' if u == 1 else '🔴 SHORT'} {ad(s)} @ {g:.6g} · {neden} · stop {g * (1 - u * SL):.6g} · TP1 {g * (1 + u * TP_ADIM):.6g}")

def kapat(s, cik, neden):
    with KIL:
        q = S["acik"].pop(s, None)
        if not q: return
        u = q["u"]; brut = q["adet"] * u * (cik - q["giris"]) - q["adet"] * cik * TAKER
        S["nakit"] += MJ + brut; top = brut - MJ * LEV * TAKER
        S["gecmis"].append({"s": ad(s), "yon": "long" if u == 1 else "short", "giris": q["giris"], "cik": cik, "t": q["t"], "tk": int(time.time()),
                            "pnl": round(top, 3), "neden": neden, "tik": q["tik"]})
        del S["gecmis"][:-500]; S["son_kapanis"][s] = time.time()
    log(f"{'💰' if top > 0 else '🔻'} {ad(s)} kapandı · {neden} · {top:+.3f} $"); kaydet()

def yonet():                                                            # her 4 sn
    for s, q in list(S["acik"].items()):
        c = D["fiyat"].get(s)
        if not c: continue
        u = q["u"]; k = q["tik"]
        if u * (c - q["stop"]) <= 0:
            kapat(s, c * (1 - u * KAYMA), (f"🔒 kâr kilidi (TP{k} sonrası)" if u * (q["stop"] - q["giris"]) > 0 else "⛔ stop")); continue
        if time.time() - q["t"] > MAX_SAAT * 3600: kapat(s, c * (1 - u * 0.0003), f"⌛ süre ({MAX_SAAT} saat)"); continue
        if u * (c - tp_fiyat(q, k)) >= 0:
            with KIL:
                while u * (c - tp_fiyat(q, k)) >= 0:
                    q["tikler"].append([int(time.time()), tp_fiyat(q, k), f"TP{k + 1}"]); k += 1
                del q["tikler"][:-15]
                if k >= 2 and u * (tp_fiyat(q, k - 2) - q["stop"]) > 0: q["stop"] = tp_fiyat(q, k - 2)
                q["tik"] = k; q["tik_t"] = int(time.time())
            log(f"▲ {ad(s)} TP{k} ✓ · " + (f"stop → {q['stop']:.6g} · kilitli {q['adet'] * u * (q['stop'] - q['giris']):+.3f} $" if k >= 2 else "stop yerinde")); kaydet()

# ───────────────────────── TARAMA (her 15 dk kapanışı) ─────────────────────────
def tara(tk):
    kr = kripto_listesi()
    ad_ = [x for x in tk if x["symbol"] in kr and ad(x["symbol"]) not in ESKI and float(x.get("usdtVolume") or 0) >= MIN_HAC]
    ad_.sort(key=lambda x: -abs(float(x.get("change24h") or 0))); ad_ = ad_[:EVREN]
    hac = {x["symbol"]: float(x.get("usdtVolume") or 0) for x in ad_}
    ss = [x["symbol"] for x in ad_]
    with ThreadPoolExecutor(8) as ex: MM = dict(zip(ss, ex.map(kapali15, ss)))
    izle = []
    for s in ss:
        m = MM.get(s)
        if not m or len(m) < 194: continue
        C = [x[4] for x in m]; O = [x[1] for x in m]
        g2 = C[-1] / C[-193] - 1                                        # 2 gün (192 × 15 dk)
        s1 = 1 if (C[-1] > O[-4] and C[-1] > C[-5]) else -1 if (C[-1] < O[-4] and C[-1] < C[-5]) else 0     # son 1 saat
        d15 = 1 if C[-1] > O[-1] else -1 if C[-1] < O[-1] else 0        # son 15 dk mumu
        t2 = 1 if g2 >= GUN2 else -1 if g2 <= -GUN2 else 0
        if t2: izle.append({"s": ad(s), "c": C[-1], "g2": round(g2 * 100, 1), "s1": s1, "d15": d15, "tam": t2 == s1 == d15, "hac": round(hac.get(s, 0) / 1e6, 1),
                            "spark": C[-96::4]})
        if t2 and t2 == s1 == d15 and s not in S["acik"] and len(S["acik"]) < MAXA and time.time() - S["son_kapanis"].get(s, 0) >= BEKLE \
                and S["nakit"] >= MJ * 1.1:
            ac(s, t2, D["fiyat"].get(s) or C[-1], f"2 gün {g2 * 100:+.0f}% · 1s ✓ · 15dk ✓")
        if s in S["acik"] or t2: D["mum"][s] = {"t": time.time(), "m": m[-40:]}
    izle.sort(key=lambda x: (not x["tam"], -abs(x["g2"])))
    D["izle"] = izle[:15]; D["tarama_t"] = int(time.time()); kaydet()

def grafik_guncelle():
    ist = [s for s in S["acik"] if time.time() - D["mum"].get(s, {}).get("t", 0) > 50]
    if ist:
        with ThreadPoolExecutor(8) as ex:
            for s, m in zip(ist, ex.map(lambda s: mumlar(s, "15m", 40), ist)):
                if m: D["mum"][s] = {"t": time.time(), "m": m}
    for s in list(D["mum"]):
        if s not in S["acik"] and time.time() - D["mum"][s]["t"] > 1800: D["mum"].pop(s, None)

def dongu():
    yukle(); log(f"🎯 Üçlü Onay {V} başladı · kağıt"); son_g = 0
    while True:
        try:
            tk = get("tickers")
            if tk:
                D["fiyat"] = {x["symbol"]: float(x["lastPr"]) for x in tk if x.get("lastPr")}
                yonet()
                b = int((time.time() - 6) // 900)
                if b != S.get("bar"):
                    S["bar"] = b
                    try: tara(tk)
                    except Exception as e: D["hata"] = "tarama: " + str(e)[:100]; traceback.print_exc()
                if time.time() - son_g >= 60: son_g = time.time(); grafik_guncelle()
            D["hata"] = "" if tk else "Bitget'e ulaşılamadı"
        except Exception as e: D["hata"] = str(e)[:120]; traceback.print_exc()
        time.sleep(4)

def veri():
    with KIL:
        P = []; acik_pnl = 0
        for s, q in S["acik"].items():
            c = D["fiyat"].get(s) or q["giris"]; u = q["u"]
            p = q["adet"] * u * (c - q["giris"]) - q["adet"] * c * TAKER - MJ * LEV * TAKER; acik_pnl += p + MJ * LEV * TAKER
            P.append({"s": ad(s), "yon": "long" if u == 1 else "short", "giris": q["giris"], "c": c, "stop": q["stop"], "stop0": q["stop0"],
                      "tp": [tp_fiyat(q, k) for k in range(max(5, q["tik"] + 2))], "tik": q["tik"], "tik_t": q["tik_t"], "t": q["t"], "neden": q["neden"],
                      "pnl": round(p, 3), "roe": round(p / MJ * 100, 1), "kilit": round(q["adet"] * u * (q["stop"] - q["giris"]), 3),
                      "mum": D["mum"].get(s, {}).get("m", []), "tikler": q.get("tikler", [])})
        P.sort(key=lambda p: -p["pnl"])
        G = S["gecmis"]; n = len(G); kaz = sum(1 for g in G if g["pnl"] > 0)
        art = sum(g["pnl"] for g in G if g["pnl"] > 0); eks = -sum(g["pnl"] for g in G if g["pnl"] < 0)
        gun = time.strftime("%Y-%m-%d", time.gmtime(time.time() + 3600))
        bugun = sum(g["pnl"] for g in G if time.strftime("%Y-%m-%d", time.gmtime(g["tk"] + 3600)) == gun)
        return {"v": V, "oz": round(S["nakit"] + MJ * len(S["acik"]) + acik_pnl, 2), "kasa0": KASA0, "n": n, "kaz": kaz, "pf": round(art / eks, 2) if eks else None,
                "bugun": round(bugun, 2), "acik_n": len(P), "maxa": MAXA, "P": P, "izle": D["izle"], "son": G[-30:][::-1], "log": S["log"][-30:][::-1],
                "tarama_t": D["tarama_t"], "hata": D["hata"], "t0": S["t0"],
                "kural": {"g2": GUN2 * 100, "sl": SL * 100, "tp": TP_ADIM * 100, "saat": MAX_SAAT, "mj": MJ, "lev": LEV, "maxa": MAXA}}

SAYFA = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "panel.html"), encoding="utf-8").read()

class Panel(BaseHTTPRequestHandler):
    def _izin(self):
        sif = os.getenv("PANEL_SIFRE", "")
        if not sif: return True
        a = self.headers.get("Authorization", "")
        try:
            if a.startswith("Basic ") and hmac.compare_digest(base64.b64decode(a[6:]).decode().split(":", 1)[1], sif): return True
        except Exception: pass
        self.send_response(401); self.send_header("WWW-Authenticate", 'Basic realm="panel"'); self.end_headers(); return False

    def do_GET(self):
        if not self._izin(): return
        yol = self.path.split("?")[0].rstrip("/")
        if yol == "/api": b, t = json.dumps(veri(), ensure_ascii=False).encode(), "application/json; charset=utf-8"
        else: b, t = SAYFA.encode(), "text/html; charset=utf-8"
        self.send_response(200); self.send_header("Content-Type", t); self.send_header("Cache-Control", "no-store"); self.end_headers(); self.wfile.write(b)

    def log_message(self, *a): pass

if __name__ == "__main__":
    threading.Thread(target=dongu, daemon=True).start()
    ThreadingHTTPServer(("0.0.0.0", int(os.getenv("PORT", "8080"))), Panel).serve_forever()
