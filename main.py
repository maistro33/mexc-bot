# ⚡ MOMENTUM AVCISI — KAĞIT bot (borsaya emir YOK). Sürüm M1.1 (24.11)
# M1.1: + 🪜 MERDİVEN modu (ayrı sekme, ayrı 100 $ kağıt kasa) — 15 dk'da yükselen dipler+tepeler, son tepe kırılınca LONG (tersi SHORT);
#       stop son dibin altında (en çok %3), her yeni yükselen dipte stop yukarı (▲), TP yok, en çok 12 saat. 3 aylık testte tutmamıştı — kağıtta izleniyor.
# Sadık: "Bitget'i tarasın, o an hızlı yükselen/düşen coinleri bulsun, işlem açsın; RSI/MACD yok, eski coin yok; panel borsadaki gibi güzel olsun."
# Backtest YAPILMADAN yazıldı (Sadık istedi) — kağıtta izlenecek.
# KURAL (her dakika, en hareketli 40 coin, günlük hacim ≥ 1 M$ — Sadık):
#   giriş : son 15 dk'da ≥ %3 hareket + son 15 dk hacmi önceki 15 dk'ların ortalamasının ≥ 3 katı + fiyat hareketin ucunda (uç noktaya %0,8'den yakın)
#           → hareket yönünde market (komisyon %0,06 + kayma %0,05)
#   çıkış : stop %2,5 · TP'ler %1,5 arayla (TP1..TP5, sonra devam) · TP2'de stop TP1'e, TP3'te TP2'ye… (▲ tik) · en çok 2 saat
#   para  : 100 $ kağıt kasa · işlem başı 3 $ × 5x · en çok 5 açık · aynı coine kapanıştan sonra 1 saat girilmez
import json, os, threading, time, traceback, base64, hmac
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import requests

V = "M1.1 (24.11 23:45)"
BG = "https://api.bitget.com/api/v2/mix/market/"
KASA0, MJ, LEV, MAXA = 100.0, 3.0, 5, 5
HAREKET, HACIM_KAT, UC, EVREN, MIN_HAC = 0.03, 3.0, 0.008, 40, 1e6
SL, TP_ADIM, MAXDK, BEKLE = 0.025, 0.015, 120, 3600
TAKER, MAKER, KAYMA = 0.0006, 0.0002, 0.0005
ESKI = {"BTC", "ETH", "XRP", "ADA", "DOGE", "TRX", "LTC", "BCH", "BNB", "XLM", "ETC", "DOT", "LINK", "SHIB", "AVAX", "XMR", "UNI", "ATOM",
        "FIL", "NEAR", "SOL", "HBAR", "AAVE", "QNT", "ALGO", "VET", "ICP", "EOS", "XTZ", "THETA", "MKR", "AXS", "SAND", "MANA"}
KLASOR = os.getenv("DATA_DIR") or ("/data" if os.path.isdir("/data") else ".")
DOSYA = os.path.join(KLASOR, "momentum.json")
KIL = threading.RLock()
S = {"v": 1, "nakit": KASA0, "acik": {}, "gecmis": [], "log": [], "t0": int(time.time()), "son_kapanis": {}}
R = {"nakit": KASA0, "acik": {}, "gecmis": [], "log": [], "t0": int(time.time()), "son_kapanis": {}, "bar": 0}     # 🪜 merdiven hesabı (S["mr"])
MR_W, MR_MINR, MR_MAXR, MR_MAXBAR = 3, 0.003, 0.03, 48
D = {"fiyat": {}, "radar": [], "tarama_t": 0, "hata": "", "mum": {}, "kripto": set(), "kripto_t": 0}

def get(yol, **q):
    for i in range(3):
        try:
            r = requests.get(BG + yol, params={"productType": "USDT-FUTURES", **q}, timeout=10).json()
            if r.get("code") == "00000": return r["data"]
        except Exception: pass
        time.sleep(0.5 + i)
    return None

def log(m):
    with KIL: S["log"].append([int(time.time()), m]); del S["log"][:-150]
    print(m, flush=True)

def kaydet():
    with KIL:
        tmp = DOSYA + ".tmp"
        with open(tmp, "w") as f: json.dump(dict(S, mr=R), f, ensure_ascii=False); f.flush(); os.fsync(f.fileno())
        os.replace(tmp, DOSYA)

def yukle():
    try:
        d = json.load(open(DOSYA))
        if d.get("v") == 1: S.update(d)
        R.update(S.pop("mr", {}) or {})
    except Exception: pass

def ad(s): return s[:-4]

def mumlar(s, g, n):
    d = get("candles", symbol=s, granularity=g, limit=str(n))
    if not d: return None
    return [[int(x[0]), float(x[1]), float(x[2]), float(x[3]), float(x[4]), float(x[5])] for x in sorted(d, key=lambda x: int(x[0]))]

# ───────────────────────── İŞLEM ─────────────────────────
def ac(s, u, c, neden):
    g = c * (1 + u * KAYMA); adet = MJ * LEV / g
    tp = [g * (1 + u * TP_ADIM * k) for k in range(1, 6)]
    with KIL:
        S["nakit"] -= MJ + MJ * LEV * TAKER
        S["acik"][s] = {"u": u, "giris": g, "stop": g * (1 - u * SL), "stop0": g * (1 - u * SL), "tp": tp, "tik": 0, "tik_t": 0,
                        "adet": adet, "t": int(time.time()), "neden": neden}
    log(f"{'🟢 LONG' if u == 1 else '🔴 SHORT'} {ad(s)} @ {g:.6g} · {neden} · stop {g * (1 - u * SL):.6g} · TP1 {tp[0]:.6g}")
    kaydet()

def kapat(s, cik, neden, ucret):
    with KIL:
        q = S["acik"].pop(s, None)
        if not q: return
        u = q["u"]; brut = q["adet"] * u * (cik - q["giris"]) - q["adet"] * cik * ucret
        S["nakit"] += MJ + brut
        top = brut - MJ * LEV * TAKER                                   # giriş komisyonu dahil net
        S["gecmis"].append({"s": ad(s), "yon": "long" if u == 1 else "short", "giris": q["giris"], "cik": cik, "t": q["t"], "tk": int(time.time()),
                            "pnl": round(top, 3), "neden": neden, "tik": q["tik"]})
        del S["gecmis"][:-300]; S["son_kapanis"][s] = time.time()
    log(f"{'💰' if top > 0 else '🔻'} {ad(s)} kapandı · {neden} · {top:+.3f} $"); kaydet()

def yonet():
    for s, q in list(S["acik"].items()):
        c = D["fiyat"].get(s)
        if not c: continue
        u = q["u"]; k = q["tik"]
        if u * (c - q["stop"]) <= 0:
            kapat(s, c * (1 - u * KAYMA), ("🔒 kâr kilidi (TP%d sonrası)" % k) if k >= 2 else "⛔ stop", TAKER); continue
        if time.time() - q["t"] > MAXDK * 60: kapat(s, c * (1 - u * 0.0003), "⌛ süre (2 saat)", TAKER); continue
        if u * (c - q["tp"][k]) >= 0:
            with KIL:
                while u * (c - q["tp"][k]) >= 0:
                    k += 1
                    if k >= len(q["tp"]) - 1: q["tp"].append(q["tp"][-1] + u * q["giris"] * TP_ADIM)
                yeni = q["tp"][k - 2] if k >= 2 else q["stop"]
                if u * (yeni - q["stop"]) > 0: q["stop"] = yeni
                q["tik"] = k; q["tik_t"] = int(time.time())
            kil = q["adet"] * u * (q["stop"] - q["giris"])
            log(f"▲ {ad(s)} TP{k} ✓ · " + (f"stop → {q['stop']:.6g} · kilitli {kil:+.3f} $" if k >= 2 else "stop yerinde")); kaydet()

# ───────────────────────── TARAMA ─────────────────────────
def kripto_listesi():
    if time.time() - D["kripto_t"] < 3600 and D["kripto"]: return D["kripto"]
    ks = get("contracts") or []
    if ks: D["kripto"] = {x["symbol"] for x in ks if x.get("isRwa") != "YES" and x.get("symbolStatus") == "normal"}; D["kripto_t"] = time.time()
    return D["kripto"]

def tara(tk):
    kr = kripto_listesi()
    ad_ = [x for x in tk if x["symbol"] in kr and x["symbol"].endswith("USDT") and ad(x["symbol"]) not in ESKI and float(x.get("usdtVolume") or 0) >= MIN_HAC]
    ad_.sort(key=lambda x: -abs(float(x.get("change24h") or 0)))
    ad_ = ad_[:EVREN]; hac = {x["symbol"]: float(x.get("usdtVolume") or 0) for x in ad_}
    with ThreadPoolExecutor(6) as ex: MM = dict(zip([x["symbol"] for x in ad_], ex.map(lambda x: mumlar(x["symbol"], "1m", 100), ad_)))
    radar = []
    for s, m in MM.items():
        if not m or len(m) < 80: continue
        c = D["fiyat"].get(s) or m[-1][4]
        h15 = c / m[-16][4] - 1                                          # son 15 dk hareket
        onceki = [sum(x[5] for x in m[-15 * (j + 2):-15 * (j + 1)]) for j in range(4)]
        v15 = sum(x[5] for x in m[-15:]); ort = sum(onceki) / 4; kat = v15 / ort if ort > 0 else 0
        son15 = m[-15:]; tepe = max([x[2] for x in son15] + [c]); dip = min([x[3] for x in son15] + [c])
        u = 1 if h15 > 0 else -1; uc = (1 - c / tepe) if u == 1 else (c / dip - 1)
        sinyal = abs(h15) >= HAREKET and kat >= HACIM_KAT and uc <= UC
        radar.append({"s": ad(s), "c": c, "h15": round(h15 * 100, 2), "kat": round(kat, 1), "hac": round(hac.get(s, 0) / 1e6, 1),
                      "spark": [x[4] for x in m[-100::4]], "sinyal": sinyal})
        if sinyal and s not in S["acik"] and len(S["acik"]) < MAXA and time.time() - S["son_kapanis"].get(s, 0) >= BEKLE and S["nakit"] >= MJ * 1.1:
            ac(s, u, c, f"15 dk'da {h15 * 100:+.1f}% · hacim {kat:.1f}×")
    radar.sort(key=lambda r: -abs(r["h15"]))
    D["radar"] = radar[:12]; D["tarama_t"] = int(time.time())

def grafik_guncelle():
    for s in list(S["acik"]):
        if time.time() - D["mum"].get(s, {}).get("t", 0) > 50:
            m = mumlar(s, "15m", 40)
            if m: D["mum"][s] = {"t": time.time(), "m": [x[1:5] for x in m]}
    for s in list(R["acik"]):
        if time.time() - D["mum"].get(s, {}).get("t", 0) > 50:
            m = mumlar(s, "15m", 40)
            if m: D["mum"][s] = {"t": time.time(), "m": [x[1:5] for x in m]}
    for s in list(D["mum"]):
        if s not in S["acik"] and s not in R["acik"]: D["mum"].pop(s, None)

# ───────────────────────── 🪜 MERDİVEN ─────────────────────────
def rlog(m):
    with KIL: R["log"].append([int(time.time()), m]); del R["log"][:-150]
    print("MR", m, flush=True)

def kapali15(s, n=100):
    m = mumlar(s, "15m", n)
    if not m: return None
    if m[-1][0] + 900_000 > time.time() * 1000: m = m[:-1]             # oluşan mumu at
    return m

def salinimlar(m, w=MR_W):
    """Onaylı fraktal tepe/dipler: (mum_indeksi, seviye). Bir tepe w mum sonra onaylanır."""
    H = [x[2] for x in m]; L = [x[3] for x in m]; sh, sl = [], []
    for j in range(w, len(m) - w):
        if H[j] == max(H[j - w:j + w + 1]) and H[j] > max(H[j - w:j]): sh.append((m[j][0], H[j]))      # (mum zamanı, seviye)
        if L[j] == min(L[j - w:j + w + 1]) and L[j] < min(L[j - w:j]): sl.append((m[j][0], L[j]))
    return sh, sl

def r_kapat(s, cik, neden):
    with KIL:
        q = R["acik"].pop(s, None)
        if not q: return
        u = q["u"]; brut = q["adet"] * u * (cik - q["giris"]) - q["adet"] * cik * TAKER
        R["nakit"] += MJ + brut; top = brut - MJ * LEV * TAKER
        R["gecmis"].append({"s": ad(s), "yon": "long" if u == 1 else "short", "giris": q["giris"], "cik": cik, "t": q["t"], "tk": int(time.time()),
                            "pnl": round(top, 3), "neden": neden, "tik": q["tik"]})
        del R["gecmis"][:-300]; R["son_kapanis"][s] = time.time()
    rlog(f"{'💰' if top > 0 else '🔻'} {ad(s)} kapandı · {neden} · {top:+.3f} $"); kaydet()

def r_yonet():                                                          # her 4 sn: stop kontrolü
    for s, q in list(R["acik"].items()):
        c = D["fiyat"].get(s)
        if c and q["u"] * (c - q["stop"]) <= 0:
            r_kapat(s, c * (1 - q["u"] * KAYMA), "🔒 merdiven bozuldu (kâr kilitli)" if q["u"] * (q["stop"] - q["giris"]) > 0 else "⛔ merdiven bozuldu (stop)")

def r_tara(tk):                                                         # her 15 dk mum kapanışında
    kr = kripto_listesi()
    ad_ = [x for x in tk if x["symbol"] in kr and ad(x["symbol"]) not in ESKI and float(x.get("usdtVolume") or 0) >= MIN_HAC]
    ad_.sort(key=lambda x: -abs(float(x.get("change24h") or 0))); ad_ = ad_[:EVREN]
    semboller = list({x["symbol"] for x in ad_} | set(R["acik"]))
    with ThreadPoolExecutor(6) as ex: MM = dict(zip(semboller, ex.map(kapali15, semboller)))
    izle = []
    for s in semboller:
        m = MM.get(s)
        if not m or len(m) < 30: continue
        sh, sl = salinimlar(m); C = [x[4] for x in m]
        q = R["acik"].get(s)
        if q:                                                           # ▲ merdiveni day: yeni onaylı dip (long) / tepe (short) stopu ilerletir
            q["bar"] = q.get("bar", 0) + 1; u = q["u"]; son = sl[-1] if u == 1 and sl else sh[-1] if u == -1 and sh else None
            if son and son[0] > q.get("son_j", 0):
                q["son_j"] = son[0]; aday = son[1] * (1 - u * 0.001)
                if u * (aday - q["stop"]) > 0:
                    q["stop"] = aday; q["tik"] += 1; q["tik_t"] = int(time.time())
                    rlog(f"▲ {ad(s)} yeni {'yükselen dip' if u == 1 else 'alçalan tepe'} · stop → {q['stop']:.6g} · kilitli {q['adet'] * u * (q['stop'] - q['giris']):+.3f} $")
            D["mum"][s] = {"t": time.time(), "m": [x[1:5] for x in m[-40:]]}
            if q["bar"] >= MR_MAXBAR: r_kapat(s, (D["fiyat"].get(s) or C[-1]) * (1 - u * 0.0003), "⌛ süre (12 saat)")
            continue
        if len(sh) < 2 or len(sl) < 2: continue
        yuk = sl[-1][1] > sl[-2][1] and sh[-1][1] > sh[-2][1]; dus = sh[-1][1] < sh[-2][1] and sl[-1][1] < sl[-2][1]
        if yuk or dus: izle.append({"s": ad(s), "yon": "long" if yuk else "short", "c": C[-1], "esik": sh[-1][1] if yuk else sl[-1][1],
                                    "uz": round(abs(C[-1] / (sh[-1][1] if yuk else sl[-1][1]) - 1) * 100, 2), "spark": C[-24:]})
        u = 1 if (yuk and C[-1] > sh[-1][1] and C[-2] <= sh[-1][1]) else -1 if (dus and C[-1] < sl[-1][1] and C[-2] >= sl[-1][1]) else 0
        if not u or len(R["acik"]) >= MAXA or time.time() - R["son_kapanis"].get(s, 0) < BEKLE or R["nakit"] < MJ * 1.1: continue
        c = D["fiyat"].get(s) or C[-1]; g = c * (1 + u * KAYMA); st = sl[-1][1] * 0.999 if u == 1 else sh[-1][1] * 1.001; rk = u * (g - st) / g
        if not (MR_MINR <= rk <= MR_MAXR): continue
        with KIL:
            R["nakit"] -= MJ + MJ * LEV * TAKER
            R["acik"][s] = {"u": u, "giris": g, "stop": st, "stop0": st, "adet": MJ * LEV / g, "t": int(time.time()), "tik": 0, "tik_t": 0, "bar": 0,
                            "son_j": (sl[-1][0] if u == 1 else sh[-1][0]), "neden": f"merdiven {'yukarı' if u == 1 else 'aşağı'} kırıldı · stop %{rk * 100:.1f}"}
        rlog(f"{'🟢 LONG' if u == 1 else '🔴 SHORT'} {ad(s)} @ {g:.6g} · son {'tepe' if u == 1 else 'dip'} kırıldı · stop {st:.6g} (%{rk * 100:.1f})"); kaydet()
    izle.sort(key=lambda x: x["uz"]); D["mr_izle"] = izle[:10]; D["mr_t"] = int(time.time())
    kaydet()

def dongu():
    yukle(); log(f"⚡ Momentum Avcısı {V} başladı · kağıt")
    son_tara = 0
    while True:
        try:
            tk = get("tickers")
            if tk:
                D["fiyat"] = {x["symbol"]: float(x["lastPr"]) for x in tk if x.get("lastPr")}
                yonet(); r_yonet()
                if time.time() - son_tara >= 60: son_tara = time.time(); tara(tk); grafik_guncelle()
                b = int((time.time() - 6) // 900)
                if b != R.get("bar"):
                    R["bar"] = b
                    try: r_tara(tk)
                    except Exception as e: D["hata"] = "merdiven: " + str(e)[:100]; traceback.print_exc()
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
                      "tp": q["tp"][:max(5, q["tik"] + 2)], "tik": q["tik"], "tik_t": q["tik_t"], "t": q["t"], "neden": q["neden"], "pnl": round(p, 3),
                      "roe": round(p / MJ * 100, 1), "kilit": round(q["adet"] * u * (q["stop"] - q["giris"]), 3), "mum": D["mum"].get(s, {}).get("m", [])})
        G = S["gecmis"]; n = len(G); kaz = sum(1 for g in G if g["pnl"] > 0)
        art = sum(g["pnl"] for g in G if g["pnl"] > 0); eks = -sum(g["pnl"] for g in G if g["pnl"] < 0)
        gun = time.strftime("%Y-%m-%d", time.gmtime(time.time() + 3600))
        bugun = sum(g["pnl"] for g in G if time.strftime("%Y-%m-%d", time.gmtime(g["tk"] + 3600)) == gun)
        oz = S["nakit"] + MJ * len(S["acik"]) + acik_pnl
        RP = []; racik = 0
        for s, q in R["acik"].items():
            c = D["fiyat"].get(s) or q["giris"]; u = q["u"]; p = q["adet"] * u * (c - q["giris"]) - q["adet"] * c * TAKER - MJ * LEV * TAKER; racik += p + MJ * LEV * TAKER
            RP.append({"s": ad(s), "yon": "long" if u == 1 else "short", "giris": q["giris"], "c": c, "stop": q["stop"], "stop0": q["stop0"], "tik": q["tik"],
                       "tik_t": q["tik_t"], "t": q["t"], "neden": q["neden"], "pnl": round(p, 3), "roe": round(p / MJ * 100, 1),
                       "kilit": round(q["adet"] * u * (q["stop"] - q["giris"]), 3), "mum": D["mum"].get(s, {}).get("m", [])})
        RG = R["gecmis"]; rart = sum(g["pnl"] for g in RG if g["pnl"] > 0); reks = -sum(g["pnl"] for g in RG if g["pnl"] < 0)
        mr = {"oz": round(R["nakit"] + MJ * len(R["acik"]) + racik, 2), "n": len(RG), "kaz": sum(1 for g in RG if g["pnl"] > 0), "pf": round(rart / reks, 2) if reks else None,
              "bugun": round(sum(g["pnl"] for g in RG if time.strftime("%Y-%m-%d", time.gmtime(g["tk"] + 3600)) == gun), 2), "acik_n": len(RP), "P": RP,
              "izle": D.get("mr_izle", []), "son": RG[-25:][::-1], "log": R["log"][-30:][::-1], "t": D.get("mr_t", 0)}
        return {"v": V, "oz": round(oz, 2), "kasa0": KASA0, "n": n, "kaz": kaz, "pf": round(art / eks, 2) if eks else None, "bugun": round(bugun, 2),
                "acik_n": len(P), "maxa": MAXA, "P": P, "radar": D["radar"], "son": G[-25:][::-1], "log": S["log"][-30:][::-1],
                "tarama_t": D["tarama_t"], "hata": D["hata"], "t0": S["t0"], "mr": mr, "kural": {"hareket": HAREKET * 100, "hacim": HACIM_KAT, "sl": SL * 100, "tp": TP_ADIM * 100, "mj": MJ, "lev": LEV}}

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
