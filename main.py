# ══════════════════════════════════════════════════════════════════════════════
#  📈 TREND KAĞIT BOTU — sadece KAĞIT (sanal para). Borsaya EMİR KODU YOK, API anahtarı GEREKMEZ.
#  Sürüm: K1.1 (21.11.2026) — eski/yavaş coinler (BTC, ETH, XRP, DOGE…) taranmaz
#
#  Neden bu tasarım (kod denetimi raporundaki dersler):
#   • Gerçek emir yolu yok → "stopsuz pozisyon", "şifresiz emir", "çift pozisyon" hataları imkânsız.
#   • Panelde hiçbir POST/değiştirme ucu yok; sadece okuma. PANEL_SIFRE tanımlıysa her sayfa şifreli.
#   • Risk HESABIN YÜZDESİ: işlem başı %1, açık toplam risk en çok %3, kaldıraç en çok 5x
#     ve stop her zaman likidasyondan çok önce (stop ≤ likidasyon mesafesinin %70'i).
#   • Maliyetler gerçekçi: giriş+çıkış komisyonu %0,06+%0,06, kayma %0,05+%0,05,
#     FUNDING her ödeme saatinde coinin o anki gerçek oranıyla düşülür/eklenir.
#   • Ölçüm: işlem sayısı, kazanma oranı, ortalama R, profit factor, en büyük düşüş — hepsi panelde.
#
#  Strateji (tek strateji): 4 saatlik mum kapanışında
#   LONG : kapanış son 55 mumun en yükseğini kırdı VE fiyat EMA200 üstünde
#   SHORT: kapanış son 55 mumun en düşüğünü kırdı VE fiyat EMA200 altında
#   Filtre: kırılım mumu (yüksek−düşük) ≥ 1,5 ATR ise girme (pompa/çöküş) · stop %15'ten uzaksa girme
#   Stop: 2 ATR · İz: son 20 mumun dibi/tepesi, sadece lehe ilerler · Hedef YOK (trend takibi)
#
#  Ortam değişkenleri (hepsi isteğe bağlı): PANEL_SIFRE, PORT, DATA_DIR (/data)
# ══════════════════════════════════════════════════════════════════════════════
import base64, json, os, threading, time, traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import requests
import scalp                                     # K1.4: ⚡ 5 dk Trend Scalp (ayrı kağıt) · K1.5: aynı sayfada sekme

V = "K1.7 (23.11 15:00)"
BG = "https://api.bitget.com/api/v2/mix/market/"
KLASOR = os.getenv("DATA_DIR") or ("/data" if os.path.isdir("/data") else ".")
DOSYA = os.path.join(KLASOR, "trend_kagit.json")
SIFRE = os.getenv("PANEL_SIFRE", "")

# ── ayarlar ──
BASLANGIC = 100.0          # sanal kasa $
RISK = 0.01                # işlem başı risk: kasanın %1'i (stop olursa kaybedilecek)
TOPLAM_RISK = 0.03         # açık işlemlerin toplam riski en çok %3
MAX_LEV = 5                # kaldıraç tavanı
N_GIRIS, N_IZ, K_ATR, MUM_MAX, STOP_MAX = 55, 20, 2.0, 1.5, 0.15
EVREN = 40                 # en hacimli 40 kripto (hisse/emtia hariç)
ESKI = {"BTC", "ETH", "XRP", "ADA", "DOGE", "TRX", "LTC", "BCH", "BNB", "XLM", "ETC", "DOT", "LINK", "SHIB", "AVAX", "XMR", "UNI", "ATOM", "FIL", "NEAR"}   # K1.1 (Sadık): eski/yavaş coinler taranmaz
TAKER, KAYMA = 0.0006, 0.0005
GUN_ZARAR = 0.03           # gün içinde kasanın %3'ü kaybedilirse o gün yeni işlem yok

KIL = threading.RLock()
S = {"v": 1, "kasa": BASLANGIC, "acik": {}, "gecmis": [], "log": [], "t0": int(time.time()), "blok": 0, "tepe": BASLANGIC, "dd": 0.0, "fon_t": {}}
D = {"fiyat": {}, "fon": {}, "hata": "", "tarama_t": 0, "yakin": [], "kripto": set()}

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
        if d.get("v") == 1: S.update(d)
    except Exception: pass

def log(m):
    with KIL: S["log"].append([int(time.time()), m]); del S["log"][:-200]
    print(time.strftime("%d.%m %H:%M"), m, flush=True)

def ad(s): return s.replace("USDT", "")

def get(yol, **q):
    for i in range(3):
        try:
            r = requests.get(BG + yol, params={"productType": "USDT-FUTURES", **q}, timeout=15).json()
            if r.get("code") == "00000": return r["data"]
            D["hata"] = f"{yol}: {r.get('msg')}"
        except Exception as e: D["hata"] = f"{yol}: {str(e)[:80]}"
        time.sleep(1 + i)
    return None

# ── göstergeler ──
def ema(c, n):
    a = 2 / (n + 1); e = c[0]
    for x in c[1:]: e += a * (x - e)
    return e
def atr(m, n=14):
    a = m[1][1] - m[1][2]
    for i in range(1, len(m)):
        tr = max(m[i][1] - m[i][2], abs(m[i][1] - m[i - 1][3]), abs(m[i][2] - m[i - 1][3]))
        a = (a * (n - 1) + tr) / n
    return a

def mumlar(s):   # kapanmış 4H mumlar: [açılış, yüksek, düşük, kapanış]
    d = get("candles", symbol=s, granularity="4H", limit="400")
    if not d: return None
    d = sorted(d, key=lambda x: int(x[0]))
    if int(d[-1][0]) + 4 * 3600 * 1000 > time.time() * 1000: d = d[:-1]
    return [[float(x[1]), float(x[2]), float(x[3]), float(x[4])] for x in d]

def evren():
    if not D["kripto"]:
        c = get("contracts") or []
        D["kripto"] = {x["symbol"] for x in c if x.get("isRwa") != "YES" and x.get("symbolStatus") == "normal"}
    tk = get("tickers") or []
    return [x["symbol"] for x in sorted(tk, key=lambda x: -float(x.get("usdtVolume") or 0))
            if x["symbol"] in D["kripto"] and x["symbol"] != "USDCUSDT" and x["symbol"][:-4] not in ESKI][:EVREN]

def ozkaynak():
    a = 0.0
    for s, q in S["acik"].items():
        c = D["fiyat"].get(s) or q["giris"]; a += q["adet"] * q["u"] * (c - q["giris"])
    return S["kasa"] + a

def acik_risk():
    return sum(q["adet"] * max(0.0, q["u"] * (q["giris"] - q["stop"])) for q in S["acik"].values())

def bugun_zarar():
    g0 = time.time() - time.time() % 86400
    return -sum(g["pnl"] for g in S["gecmis"] if g["tk"] >= g0)

# ── strateji ──
def tara():
    ev = list(dict.fromkeys(list(S["acik"]) + evren())); yakin = []; aday = []   # açık işlemler (eski coin olsa da) izlenmeye devam eder
    for s in ev:
        m = mumlar(s); time.sleep(0.05)
        if not m or len(m) < 260: continue
        c = [x[3] for x in m]; A = atr(m); e = ema(c, 200); son = c[-1]
        try: dip_bak(s, m)
        except Exception as ex: D["hata"] = "dip: " + str(ex)[:80]
        ust = max(x[1] for x in m[-N_GIRIS - 1:-1]); alt = min(x[2] for x in m[-N_GIRIS - 1:-1])
        if s in S["acik"]:                                      # iz: son 20 mumun dibi/tepesi, sadece lehe
            q = S["acik"][s]
            yeni = min(x[2] for x in m[-N_IZ:]) if q["u"] == 1 else max(x[1] for x in m[-N_IZ:])
            if q["u"] * (yeni - q["stop"]) > 0:
                q["stop"] = yeni; q["tik"] = q.get("tik", 0) + 1
                kk = q['adet'] * q['u'] * (yeni - q['giris']); log(f"▲ {ad(s)} iz {q['tik']}. kez ilerledi → stop {yeni:g} · " + (f"kâr kilitlendi {kk:+.2f} $" if kk > 0 else f"stop olursa {kk:+.2f} $ (henüz kâr kilitli değil)"))
            continue
        u = 1 if son > ust and son > e else -1 if son < alt and son < e else 0
        yakin.append({"s": ad(s), "yon": "long" if son > e else "short", "uz": round(((ust / son - 1) if son > e else (1 - alt / son)) * 100, 2)})
        if not u: continue
        mum = (m[-1][1] - m[-1][2]) / A
        if mum >= MUM_MAX: log(f"🚫 {ad(s)} kırılımı atlandı: mum {mum:.1f} ATR (pompa/çöküş)"); continue
        stop_m = K_ATR * A / son
        if stop_m > STOP_MAX: log(f"🚫 {ad(s)} atlandı: stop %{stop_m * 100:.0f} uzakta (çok oynak)"); continue
        aday.append((abs(son / (ust if u == 1 else alt) - 1), s, u, A, stop_m))
    taze = time.time() % 14400 < 900                             # mum kapanışından en çok 15 dk sonra gir (eski kırılıma girme)
    for _, s, u, A, stop_m in sorted(aday, reverse=True):
        if taze: ac(s, u, A, stop_m)
        else: log(f"⏭ {ad(s)} kırılımı eski (mum kapanışından >15 dk), girilmedi")
    with KIL: D["yakin"] = sorted(yakin, key=lambda x: x["uz"])[:10]; D["tarama_t"] = int(time.time())

def ac(s, u, A, stop_m):
    with KIL:
        oz = ozkaynak()
        if bugun_zarar() >= oz * GUN_ZARAR: log(f"⏸ {ad(s)} atlandı: günlük zarar sınırı (%{GUN_ZARAR * 100:.0f})"); return
        risk_d = oz * RISK
        if acik_risk() + risk_d > oz * TOPLAM_RISK: log(f"⏸ {ad(s)} atlandı: açık toplam risk %{TOPLAM_RISK * 100:.0f} dolu"); return
        p = D["fiyat"].get(s)
        if not p: return
        g = p * (1 + u * KAYMA); st = g - u * K_ATR * A
        adet = risk_d / abs(g - st); notional = adet * g
        lev = max(1, min(MAX_LEV, int(0.7 / stop_m)))           # stop, likidasyon mesafesinin (≈1/lev) en çok %70'i
        marj = notional / lev
        if marj > oz - sum(q["marj"] for q in S["acik"].values()): log(f"⏸ {ad(s)} atlandı: marj yetmiyor"); return
        ucret = notional * TAKER; S["kasa"] -= ucret
        S["acik"][s] = {"u": u, "giris": g, "stop": st, "stop0": st, "adet": adet, "marj": marj, "lev": lev, "t": int(time.time()),
                        "ucret": ucret, "fon": 0.0, "risk_d": risk_d}
        log(f"{'🔺 LONG' if u == 1 else '🔻 SHORT'} {ad(s)} @ {g:g} · stop {st:g} (%{stop_m * 100:.1f}) · risk {risk_d:.2f} $ · {notional:.1f} $ poz. · {lev}x · marj {marj:.2f} $")
    kaydet()

def kapat(s, cikis, neden):
    with KIL:
        q = S["acik"].pop(s); u = q["u"]
        brut = q["adet"] * u * (cikis - q["giris"]); ucret = q["adet"] * cikis * TAKER
        pnl = brut - ucret - q["ucret"] + q["fon"]
        S["kasa"] += brut - ucret
        R = pnl / q["risk_d"] if q["risk_d"] else 0
        S["gecmis"].append({"s": ad(s), "yon": "long" if u == 1 else "short", "giris": q["giris"], "cikis": cikis, "t": q["t"], "tk": int(time.time()),
                            "pnl": round(pnl, 3), "R": round(R, 2), "fon": round(q["fon"], 3), "ucret": round(q["ucret"] + ucret, 3), "neden": neden, "tik": q.get("tik", 0)})
        oz = ozkaynak(); S["tepe"] = max(S["tepe"], oz); S["dd"] = max(S["dd"], (S["tepe"] - oz) / S["tepe"])
        log(f"{'✅' if pnl > 0 else '❌'} {ad(s)} kapandı · {neden} · {pnl:+.2f} $ ({R:+.2f}R) · funding {q['fon']:+.3f} $")
    kaydet()

def fonlama():   # her coinin ödeme saatinde gerçek oranla funding uygula
    d = get("current-fund-rate")
    if not d: return
    D["fon"] = {x["symbol"]: (float(x["fundingRate"]), int(x["nextUpdate"]) / 1000) for x in d if x.get("nextUpdate")}
    with KIL:
        for s, q in S["acik"].items():
            r, nt = D["fon"].get(s, (0, 0))
            son = S["fon_t"].get(s, 0)
            if nt and nt != son and nt - time.time() < 30:      # ödeme anı
                c = D["fiyat"].get(s) or q["giris"]; f = -q["u"] * r * q["adet"] * c   # long + oranda öder
                q["fon"] += f; S["kasa"] += f; S["fon_t"][s] = nt

# ── K1.3 🔻→🔺 DİP ALIM (Sadık'ın fikri) ──────────────────────────────────────────────
# Son 2 günde (12 × 4H) tepeden ≥%20 düşmüş ve hâlâ dipte (2 günlük dibin en çok %2 üstünde) coin →
# %3 aşağıya LİMİT alış emri (2 gün geçerli). Dolarsa: stop %15, hedef %15, en çok 7 gün. İşlem başı 3 $ marj × 5x = 15 $.
# 15 ay / 21 coin testi: 90 işlem, %63 kazanan, +55 $, iki yarı da artı, en büyük düşüş 11 $ (uyarı: borsadan silinen coinler testte yok → biraz iyimser).
DP_DUS, DP_YAK, DP_LIM, DP_SL, DP_TP, DP_GUN, DP_MJ, DP_LEV, DP_MAX = 0.20, 0.02, 0.03, 0.15, 0.15, 7, 3.0, 5, 3
MAKER = 0.0002
for _k, _v in (("dp_bekleyen", {}), ("dp_acik", {}), ("dp_gecmis", []), ("dp_kasa", 100.0)): S.setdefault(_k, _v)

def dip_bak(s, m):
    if s[:-4] in ESKI or s in S["dp_acik"] or s in S["dp_bekleyen"]: return
    h = max(x[1] for x in m[-13:]); l = min(x[2] for x in m[-13:]); c = m[-1][3]; dus = c / h - 1
    D.setdefault("dp_yakin", {})[s] = round(dus * 100, 1)
    if dus > -DP_DUS or c > l * (1 + DP_YAK): return
    with KIL:
        if len(S["dp_acik"]) + len(S["dp_bekleyen"]) >= DP_MAX: log(f"⏸ 🔻 {ad(s)} dip sinyali ama 3 dip işlemi dolu"); return
        lim = c * (1 - DP_LIM); S["dp_bekleyen"][s] = {"lim": lim, "t": int(time.time()), "son": int(time.time()) + 2 * 86400, "dus": round(dus * 100, 1)}
    log(f"🔻→🔺 {ad(s)} 2 günde %{dus * 100:.1f} düştü, dipte · LİMİT ALIŞ {lim:g} (−%3) · 2 gün geçerli")

def dip_kontrol():
    now = time.time()
    with KIL:
        for s in list(S["dp_bekleyen"]):
            b = S["dp_bekleyen"][s]; c = D["fiyat"].get(s)
            if now > b["son"]: S["dp_bekleyen"].pop(s); log(f"⌛ {ad(s)} dip limit emri dolmadı, iptal"); continue
            if c and c < b["lim"]:
                S["dp_bekleyen"].pop(s); g = b["lim"]; adet = DP_MJ * DP_LEV / g
                S["dp_acik"][s] = {"giris": g, "adet": adet, "stop": g * (1 - DP_SL), "hedef": g * (1 + DP_TP), "t": int(now), "dus": b["dus"]}
                log(f"🔺 DİP LONG {ad(s)} @ {g:g} (limit doldu) · stop {g * (1 - DP_SL):g} · hedef {g * (1 + DP_TP):g} · 3 $ × 5x")
        for s in list(S["dp_acik"]):
            q = S["dp_acik"][s]; c = D["fiyat"].get(s)
            if not c: continue
            if c <= q["stop"]: dip_kapat(s, min(c, q["stop"]) * (1 - KAYMA), "stop", TAKER)
            elif c > q["hedef"]: dip_kapat(s, q["hedef"], "🎯 hedef", MAKER)
            elif now - q["t"] > DP_GUN * 86400: dip_kapat(s, c * (1 - KAYMA), "süre (7 gün)", TAKER)

def dip_kapat(s, cik, neden, ucret):
    q = S["dp_acik"].pop(s); n = q["adet"] * q["giris"]
    pnl = q["adet"] * (cik - q["giris"]) - n * MAKER - q["adet"] * cik * ucret
    S["dp_kasa"] += pnl
    S["dp_gecmis"].append({"s": ad(s), "giris": q["giris"], "cikis": cik, "t": q["t"], "tk": int(time.time()), "pnl": round(pnl, 3), "yuzde": round((cik / q["giris"] - 1) * 100, 2), "neden": neden})
    log(f"{'✅' if pnl > 0 else '❌'} DİP {ad(s)} kapandı · {neden} · {pnl:+.2f} $"); kaydet()

def dongu():
    yukle(); log(f"🚀 Trend KAĞIT {V} başladı · kasa {S['kasa']:.2f} $ · işlem başı risk %{RISK * 100:.0f} · emir kodu yok")
    son_fon = 0
    while True:
        try:
            tk = get("tickers") or []
            D["fiyat"] = {x["symbol"]: float(x["lastPr"]) for x in tk if x.get("lastPr")}
            for s in list(S["acik"]):                            # stop kontrolü (fiyat stopa değdi mi)
                q = S["acik"][s]; c = D["fiyat"].get(s)
                if c and q["u"] * (c - q["stop"]) <= 0:
                    kapat(s, min(c, q["stop"]) * (1 - KAYMA) if q["u"] == 1 else max(c, q["stop"]) * (1 + KAYMA), "stop" if q.get("tik") == 0 or not q.get("tik") else "🔒 iz stopu")
            dip_kontrol()
            if time.time() - son_fon > 20: son_fon = time.time(); fonlama()
            blok = int((time.time() - 60) // 14400)              # 4H mum kapanışından 1 dk sonra
            if blok != S["blok"]: S["blok"] = blok; tara(); kaydet()
            D["hata"] = ""
        except Exception as e:
            D["hata"] = str(e)[:140]; traceback.print_exc()
        time.sleep(5)

# ── metrikler ──
def veri():
    with KIL:
        G = S["gecmis"]; n = len(G); kaz = [g for g in G if g["pnl"] > 0]; kay = [g for g in G if g["pnl"] <= 0]
        bk = sum(g["pnl"] for g in kaz); bz = -sum(g["pnl"] for g in kay)
        P = []
        for s, q in S["acik"].items():
            c = D["fiyat"].get(s) or q["giris"]
            P.append({"s": ad(s), "yon": "long" if q["u"] == 1 else "short", "giris": q["giris"], "c": c, "stop": q["stop"], "stop0": q["stop0"],
                      "t": q["t"], "lev": q["lev"], "marj": round(q["marj"], 2), "pnl": round(q["adet"] * q["u"] * (c - q["giris"]) - q["ucret"] + q["fon"], 3),
                      "kilit": round(q["adet"] * q["u"] * (q["stop"] - q["giris"]), 3), "tik": q.get("tik", 0), "fon": round(q["fon"], 3)})
        oz = ozkaynak()
        return {"v": V, "t0": S["t0"], "kasa0": BASLANGIC, "oz": round(oz, 2), "n": n, "kaz": len(kaz), "r": round(sum(g["pnl"] for g in G), 2),
                "ortR": round(sum(g["R"] for g in G) / n, 2) if n else 0, "pf": round(bk / bz, 2) if bz else None,
                "dd": round(max(S["dd"], (S["tepe"] - oz) / S["tepe"] if S["tepe"] else 0) * 100, 1),
                "fon": round(sum(g["fon"] for g in G) + sum(q["fon"] for q in S["acik"].values()), 3), "ucret": round(sum(g["ucret"] for g in G), 3),
                "acik_risk": round(acik_risk(), 2), "P": P, "son": G[::-1][:50], "log": S["log"][::-1][:40], "yakin": D["yakin"],
                "tarama_t": D["tarama_t"], "hata": D["hata"],
                "dip": {"kasa": round(S["dp_kasa"] + sum(q["adet"] * ((D["fiyat"].get(s) or q["giris"]) - q["giris"]) for s, q in S["dp_acik"].items()), 2),
                        "n": len(S["dp_gecmis"]), "kaz": sum(g["pnl"] > 0 for g in S["dp_gecmis"]), "r": round(sum(g["pnl"] for g in S["dp_gecmis"]), 2),
                        "acik": [{"s": ad(s), "giris": q["giris"], "c": D["fiyat"].get(s) or q["giris"], "stop": q["stop"], "hedef": q["hedef"], "t": q["t"], "dus": q["dus"],
                                  "pnl": round(q["adet"] * ((D["fiyat"].get(s) or q["giris"]) - q["giris"]), 3)} for s, q in S["dp_acik"].items()],
                        "bekleyen": [{"s": ad(s), "lim": b["lim"], "c": D["fiyat"].get(s), "son": b["son"], "dus": b["dus"]} for s, b in S["dp_bekleyen"].items()],
                        "son": S["dp_gecmis"][::-1][:30], "yakin": sorted([{"s": ad(k), "dus": v} for k, v in (D.get("dp_yakin") or {}).items()], key=lambda x: x["dus"])[:6]}}

SAYFA = r"""<!doctype html><html lang="tr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Kağıt Botlar</title>
<style>:root{--bg:#0b1020;--kart:#141b2e;--kart2:#1a2340;--cizgi:#26304a;--y:#e8ecf5;--soluk:#8b95ad;--g:#22d39b;--r:#ff5c7a;--sari:#ffd166}
body{margin:0;background:var(--bg);color:var(--y);font:15px/1.45 -apple-system,system-ui,sans-serif}.w{max-width:640px;margin:auto;padding:16px}
h1{font-size:20px;margin:4px 0}h2{font-size:16px;margin:0 0 10px}.s{color:var(--soluk);font-size:13px}.alt2{font-size:11px;color:var(--soluk)}
.p{background:var(--kart);border:1px solid var(--cizgi);border-radius:16px;padding:14px;margin:12px 0}
.kartlar{display:grid;grid-template-columns:repeat(2,1fr);gap:10px;margin:12px 0}.k{background:linear-gradient(160deg,var(--kart2),var(--kart));border:1px solid var(--cizgi);border-radius:16px;padding:14px}
.n{font-size:22px;font-weight:800}.art{color:var(--g)}.eks{color:var(--r)}.r{display:flex;justify-content:space-between;gap:8px;padding:8px 0;border-bottom:1px solid #ffffff10}
.sek{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin:12px 0}.sek button{padding:11px;border-radius:12px;border:1px solid var(--cizgi);color:var(--soluk);font:700 15px system-ui;background:var(--kart)}
.sek button.on{color:#fff;background:linear-gradient(135deg,#5b8cff,#a56bff);border-color:transparent}
.chip{display:inline-block;font-size:11px;font-weight:700;padding:2px 8px;border-radius:99px;background:#ffffff14}.chip.l{background:#22d39b22;color:var(--g)}.chip.sh{background:#ff5c7a22;color:var(--r)}
.pz{border:1px solid var(--cizgi);border-radius:14px;padding:12px;margin-bottom:10px;background:var(--kart2)}.pz .ust{display:flex;justify-content:space-between;align-items:center}.pz b{font-size:16px}
.tbar{position:relative;height:10px;border-radius:6px;background:linear-gradient(90deg,#ff5c7a55,#33405a 40%,#22d39b55);margin:14px 0 4px}
.tbar b{position:absolute;top:-2px;width:2px;height:14px;background:#ffffff70}.tbar i{position:absolute;top:-4px;width:4px;height:18px;border-radius:2px;background:#fff}
.tbar u{position:absolute;top:-3px;width:3px;height:16px;border-radius:2px;background:var(--r)}
.ucl{display:flex;justify-content:space-between;font-size:11px;color:var(--soluk)}.tps{display:flex;gap:4px;flex-wrap:wrap;margin-top:8px}.tps span{font-size:11px;padding:2px 6px;border-radius:8px;background:#ffffff0d;color:var(--soluk)}
.tps span.ok{background:#22d39b26;color:var(--g);font-weight:800}.tik{margin-top:6px;font-size:12px;color:var(--sari);font-weight:700}
.u{background:#ff5c7a22;color:var(--r);padding:8px;border-radius:10px;display:none}</style></head><body><div class="w">
<h1>🤖 Kağıt botlar</h1><div class="s">Borsaya emir yok · sadece kağıt</div>
<div class="sek"><button id="bT" onclick="sek('T')">📈 Trend</button><button id="bS" onclick="sek('S')">⚡ 5 dk Scalp</button></div>

<div id="T"><div class="s" id="alt"></div><div class="u" id="u"></div>
<div class="kartlar" id="kart"></div>
<div class="p"><h2>💼 Açık işlemler</h2><div id="acik"></div></div>
<div class="p"><h2>🔻→🔺 Dip Alım <span class="s">(3 $ × 5x · ayrı kasa)</span></h2><div class="kartlar" id="dkart"></div><div id="dacik"></div><div id="dbek"></div><div class="s" style="margin-top:8px">2 günde en çok düşenler (≥%20 düşüş + dipte olunca limit alış):</div><div id="dyak"></div><div id="dson"></div>
<div class="s" style="margin-top:8px">Son 2 günde ≥%20 düşmüş ve hâlâ dipte olan coine <b>%3 aşağıdan limit alış</b> (2 gün geçerli) · stop %15 · hedef %15 · en çok 7 gün · en çok 3 işlem.</div></div>
<div class="p"><h2>👀 Kırılıma en yakın</h2><div class="s" id="tar"></div><div id="yak"></div></div>
<div class="p"><h2>📒 Kapanan</h2><div id="son"></div></div>
<div class="p s"><b>Kurallar.</b> 4 saatlik mum kapanışında son 55 mumun zirvesini (EMA200 üstünde) kırana LONG, dibini (EMA200 altında) kırana SHORT. Kırılım mumu ≥1,5 ATR ya da stop %15'ten uzaksa girmez. Stop 2 ATR, iz son 20 mumun dibi/tepesi, hedef yok.
<b>Risk:</b> işlem başı kasanın %1'i, açık toplam en çok %3, kaldıraç en çok 5x, günde %3 zararda yeni işlem yok. <b>Maliyet:</b> komisyon %0,06+%0,06, kayma %0,05+%0,05, funding gerçek oranla.</div>
<div class="p"><h2>🧾 Kayıt</h2><div class="s" id="log"></div></div></div>

<div id="S" style="display:none"><div class="s" id="salt"></div>
<div class="kartlar" id="skart"></div>
<div class="p"><h2>💼 Açık işlemler <span class="s" id="sadet"></span></h2><div id="sacik"></div></div>
<div class="p"><h2>🧭 4 saatlikte güçlü trenddeki coinler</h2><div class="s" id="str"></div><div class="s" style="margin-top:6px" id="star"></div><div id="sizle"></div></div>
<div class="p"><h2>📒 Kapanan</h2><div id="sson"></div></div>
<div class="p s"><b>Kural.</b> Bitget'te son 24 saatte en çok yükselen 30 coin (hacim ≥0,5 M$, 30 dk'da bir yenilenir). 4 saatlikte güçlü trend (EMA20>EMA50, 2 günde ≥%10) olan coinde 5 dk mum EMA20'ye geri çekilip trend yönünde dönünce girer; 15 dk'da da aynı yön (EMA20>EMA50) şart. Stop son 4 mumun dibi/tepesi.
<b>5 TP:</b> 1R · 1,5R · 2R · 2,5R · 3R. Stop girişe %2'den yakınsa girmez. TP1'de stop yerinde kalır; TP2 geçince stop TP1'e, TP3'te TP2'ye, TP4'te TP3'e çekilir (her biri ▲ tik); TP5'te kapanır. En çok 2 saat. 3 $ × 5x, en çok 10 açık, komisyon+kayma dahil.</div>
<div class="p"><h2>🧾 Kayıt</h2><div class="s" id="slog"></div></div></div></div><script>
const $=i=>document.getElementById(i),f=(x,d=2)=>Number(x).toLocaleString('tr-TR',{minimumFractionDigits:d,maximumFractionDigits:d}),sg=(x,d=2)=>(x>0?'+':'')+f(x,d),rk=x=>x>0?'art':x<0?'eks':'';
const fy=x=>{x=Number(x);return f(x,x>=1000?1:x>=1?4:6)},ts=t=>new Date(t*1000).toLocaleString('tr-TR',{timeZone:'Europe/Stockholm',day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'}),sa=t=>new Date(t*1000).toLocaleTimeString('tr-TR',{timeZone:'Europe/Stockholm',hour:'2-digit',minute:'2-digit'});
let AK='T';function sek(x){AK=x;$('T').style.display=x=='T'?'':'none';$('S').style.display=x=='S'?'':'none';$('bT').className=x=='T'?'on':'';$('bS').className=x=='S'?'on':'';try{localStorage.setItem('sek',x)}catch(e){};history.replaceState(null,'',x=='S'?'#scalp':'#trend');x=='T'?y():z()}
const kl=(x,a,b)=>Math.max(0,Math.min(100,x));
function bar(sol,sag,isaret){const pos=x=>kl((x-sol)/(sag-sol)*100);return pos}
async function y(){try{const d=await(await fetch('api',{cache:'no-store'})).json();
$('alt').textContent=`${d.v} · ${ts(d.t0)}'den beri`;$('u').textContent=d.hata;$('u').style.display=d.hata?'block':'none';
$('kart').innerHTML=`<div class="k"><div class="s">Kasa (kağıt)</div><div class="n ${rk(d.oz-d.kasa0)}">${f(d.oz)} $</div><div class="alt2">başlangıç ${f(d.kasa0,0)} $ · açık risk ${f(d.acik_risk)} $</div></div>
<div class="k"><div class="s">Kapanan</div><div class="n ${rk(d.r)}">${sg(d.r)} $</div><div class="alt2">${d.n} işlem · ${d.n?'%'+f(d.kaz/d.n*100,0)+' kârlı':'–'}</div></div>
<div class="k"><div class="s">Ort. R · PF</div><div class="n">${sg(d.ortR)}R · ${d.pf==null?'–':f(d.pf)}</div></div>
<div class="k"><div class="s">En büyük düşüş</div><div class="n eks">%${f(d.dd,1)}</div><div class="alt2">funding ${sg(d.fon,3)} $ · komisyon ${f(d.ucret,3)} $</div></div>`;
$('acik').innerHTML=d.P.map(p=>{const L=p.yon=='long',sol=p.stop0,uz=Math.abs(p.giris-p.stop0),sag=Math.max(L?p.c:0,0)||0,ust=L?Math.max(p.c,p.giris+uz*2):Math.min(p.c,p.giris-uz*2),pos=bar(sol,ust);
return `<div class="pz"><div class="ust"><div><b>${p.s}</b> <span class="chip ${L?'l':'sh'}">${p.yon.toUpperCase()} ${p.lev}x</span></div><b class="${rk(p.pnl)}">${sg(p.pnl)} $</b></div>
<div class="tbar"><b style="left:${pos(p.giris)}%"></b><u style="left:${pos(p.stop)}%"></u><i style="left:calc(${pos(p.c)}% - 2px)"></i></div>
<div class="ucl"><span>⛔ ${fy(p.stop)}</span><span>giriş ${fy(p.giris)}</span><span>şimdi ${fy(p.c)}</span></div>
<div class="tik">${p.tik?'▲ iz '+p.tik+'× ilerledi · ':''}${p.kilit>0?'🔒 kilitli '+sg(p.kilit)+' $':'<span class="s">stop olursa '+sg(p.kilit)+' $</span>'}</div><div class="alt2">${ts(p.t)} · funding ${sg(p.fon,3)} $</div></div>`}).join('')||'<div class="s">Açık işlem yok — kırılım bekleniyor.</div>';
$('tar').textContent=d.tarama_t?'son tarama '+ts(d.tarama_t)+' · her 4 saatte':'ilk tarama bekleniyor…';
$('yak').innerHTML=d.yakin.map(x=>`<div class="r"><b>${x.s}</b><span class="s">${x.yon=='long'?'zirveye':'dibe'} %${f(x.uz)}</span></div>`).join('');
$('son').innerHTML=d.son.map(g=>`<div class="r"><div><b>${g.s}</b> <span class="chip">${g.yon.toUpperCase()}</span><div class="s">${ts(g.tk)} · ${g.neden} · funding ${sg(g.fon,3)} $</div></div><div style="text-align:right"><b class="${rk(g.pnl)}">${sg(g.pnl)} $</b><div class="s">${sg(g.R)}R</div></div></div>`).join('')||'<div class="s">Henüz yok.</div>';
const P=d.dip;$('dkart').innerHTML=`<div class="k"><div class="s">Dip kasa</div><div class="n ${rk(P.kasa-100)}">${f(P.kasa)} $</div></div><div class="k"><div class="s">Kapanan</div><div class="n ${rk(P.r)}">${sg(P.r)} $</div><div class="alt2">${P.n} işlem · ${P.n?'%'+f(P.kaz/P.n*100,0)+' kârlı':'–'}</div></div>`;
$('dacik').innerHTML=P.acik.map(p=>{const pos=bar(p.stop,p.hedef);return `<div class="pz"><div class="ust"><div><b>${p.s}</b> <span class="chip l">LONG 5x</span></div><b class="${rk(p.pnl)}">${sg(p.pnl)} $</b></div>
<div class="tbar"><b style="left:${pos(p.giris)}%"></b><i style="left:calc(${pos(p.c)}% - 2px)"></i></div><div class="ucl"><span>⛔ ${fy(p.stop)}</span><span>giriş ${fy(p.giris)}</span><span>🎯 ${fy(p.hedef)}</span></div><div class="alt2">${ts(p.t)} · 2 günde %${f(p.dus,1)} düşmüştü</div></div>`}).join('');
$('dbek').innerHTML=P.bekleyen.map(b=>`<div class="r"><div><b>${b.s}</b> <span class="chip">⏳ LİMİT ALIŞ</span><div class="s">%${f(b.dus,1)} düştü · emir ${fy(b.lim)} · şimdi ${b.c?fy(b.c):'–'} · ${ts(b.son)}'e kadar</div></div></div>`).join('')||(P.acik.length?'':'<div class="s">Açık ya da bekleyen dip işlemi yok.</div>');
$('dyak').innerHTML=P.yakin.map(x=>`<div class="r"><b>${x.s}</b><span class="${x.dus<=-20?'eks':'s'}">2 günde %${f(x.dus,1)}</span></div>`).join('');
$('dson').innerHTML=P.son.map(g=>`<div class="r"><div><b>${g.s}</b><div class="s">${ts(g.tk)} · ${g.neden}</div></div><div style="text-align:right"><b class="${rk(g.pnl)}">${sg(g.pnl)} $</b><div class="s">%${sg(g.yuzde)}</div></div></div>`).join('');
$('log').innerHTML=d.log.slice(0,20).map(l=>ts(l[0])+' · '+l[1]).join('<br>');}catch(e){$('alt').textContent='⚠️ bağlantı yok'}}
async function z(){try{const d=await(await fetch('scalp/api',{cache:'no-store'})).json();
$('salt').textContent=`${d.v} · ${ts(d.t0)}'den beri · ${d.evren} coin`+(d.hata?' · ⚠️ '+d.hata:'');
$('skart').innerHTML=`<div class="k"><div class="s">Kasa (kağıt)</div><div class="n ${rk(d.oz-d.kasa0)}">${f(d.oz)} $</div><div class="alt2">açık ${sg(d.acik,3)} $</div></div>
<div class="k"><div class="s">Kapanan</div><div class="n ${rk(d.r)}">${sg(d.r)} $</div><div class="alt2">${d.n} işlem · ${d.n?'%'+f(d.kaz/d.n*100,0)+' kârlı':'–'}</div></div>
<div class="k"><div class="s">Ort. R · PF</div><div class="n">${sg(d.ortR,2)}R · ${d.pf==null?'–':f(d.pf)}</div></div>
<div class="k"><div class="s">Bugün</div><div class="n ${rk(d.bugun_r)}">${sg(d.bugun_r)} $</div><div class="alt2">${d.bugun_n} işlem</div></div>`;
$('sadet').textContent=d.P.length+'/10';
$('sacik').innerHTML=d.P.map(p=>{const L=p.yon=='long',pos=bar(p.stop0,p.tp[4]);
return `<div class="pz"><div class="ust"><div><b>${p.s}</b> <span class="chip ${L?'l':'sh'}">${p.yon.toUpperCase()} 5x</span> <span class="alt2">${sa(p.t)}</span></div><b class="${rk(p.pnl)}">${sg(p.pnl,3)} $</b></div>
<div class="tbar"><b style="left:${pos(p.giris)}%"></b>${p.tp.map((t,i)=>`<b style="left:${pos(t)}%;background:${i<p.tik?'var(--g)':'#22d39b66'}"></b>`).join('')}<u style="left:${pos(p.stop)}%;background:${p.tik?'var(--sari)':'var(--r)'}"></u><i style="left:calc(${pos(p.c)}% - 2px)"></i></div>
<div class="ucl"><span>⛔ ${fy(p.stop)}</span><span>giriş ${fy(p.giris)}</span><span>🎯 ${fy(p.tp[4])}</span></div>
<div class="tps">${p.tp.map((t,i)=>`<span class="${i<p.tik?'ok':''}">${i<p.tik?'✓ ':''}TP${i+1} ${fy(t)}</span>`).join('')}</div>
<div class="tik">${p.tik?`▲ iz ${p.tik}× · son ${sa(p.tik_t)} · `:''}${p.kilit>0?'🔒 kilitli '+sg(p.kilit,3)+' $':`<span class="s">${p.tik&&p.kilit>=0?'stop girişte':'stop olursa '+sg(p.kilit,3)+' $'}</span>`}</div></div>`}).join('')||'<div class="s">Açık işlem yok — sinyal bekleniyor (5 dk).</div>';
$('str').innerHTML=d.trend.map(t=>`${t.s} ${t.u==1?'↑':'↓'}%${t.guc}`).join(' · ')||'–';
$('star').textContent=d.tarama_t?'son 5 dk tarama '+ts(d.tarama_t)+' · EMA20\'ye en yakınlar:':'ilk tarama bekleniyor…';
$('sizle').innerHTML=d.izle.map(x=>`<div class="r"><b>${x.s}</b><span class="s">${x.yon=='long'?'LONG arar':'SHORT arar'} · EMA20'ye %${f(x.uz)}</span></div>`).join('');
$('sson').innerHTML=d.son.map(g=>`<div class="r"><div><b>${g.s}</b> <span class="chip">${g.yon.toUpperCase()}</span><div class="s">${ts(g.tk)} · ${Math.round((g.tk-g.t)/60)} dk · ${g.neden}</div></div><div style="text-align:right"><b class="${rk(g.pnl)}">${sg(g.pnl,3)} $</b><div class="s">${sg(g.R)}R</div></div></div>`).join('')||'<div class="s">Henüz yok.</div>';
$('slog').innerHTML=d.log.slice(0,25).map(l=>ts(l[0])+' · '+l[1]).join('<br>');}catch(e){$('salt').textContent='⚠️ bağlantı yok'}}
let ilk='T';try{ilk=localStorage.getItem('sek')||'T'}catch(e){};if(location.hash=='#scalp')ilk='S';if(location.hash=='#trend')ilk='T';
sek(ilk);setInterval(()=>AK=='T'?y():z(),8000);</script></body></html>"""

class Panel(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _izin(self):
        if not SIFRE: return True
        h = self.headers.get("Authorization", "")
        if h.startswith("Basic "):
            try:
                if base64.b64decode(h[6:]).decode().split(":", 1)[-1] == SIFRE: return True
            except Exception: pass
        self.send_response(401); self.send_header("WWW-Authenticate", 'Basic realm="Trend"'); self.end_headers(); return False
    def do_GET(self):
        if not self._izin(): return
        yol = self.path.split("?")[0].rstrip("/")
        if yol in ("", "/"): b, t = SAYFA.encode(), "text/html; charset=utf-8"
        elif yol == "/api": b, t = json.dumps(veri(), ensure_ascii=False).encode(), "application/json; charset=utf-8"
        elif yol == "/scalp": self.send_response(302); self.send_header("Location", "/#scalp"); self.end_headers(); return   # K1.5: tek sayfa, sekme
        elif yol == "/scalp/api": b, t = json.dumps(scalp.veri(), ensure_ascii=False).encode(), "application/json; charset=utf-8"
        else: self.send_response(404); self.end_headers(); return
        self.send_response(200); self.send_header("Content-Type", t); self.send_header("Cache-Control", "no-store"); self.end_headers(); self.wfile.write(b)

if __name__ == "__main__":
    threading.Thread(target=dongu, daemon=True).start(); scalp.basla()
    ThreadingHTTPServer(("0.0.0.0", int(os.getenv("PORT", "8080"))), Panel).serve_forever()
