# 🔍 Dip Bulucu — Sadık'ın elle işlemi için (emir vermez, sadece söyler)
# Sürüm D1.1 (23.11) — + 🔺 tepe short (2 günde ≥%30 yükseliş + tepeye %2 yakın → %3 yukarıdan limit short, stop %15, hedef %15)
# Sürüm D1.0 (23.11) — kural = K1.3 Dip Alım (15 aylık testte artı): 2 günde ≥%20 düşüş + fiyat 2 günlük dibe %2'den yakın
#   → %3 aşağıdan limit alış · stop %15 · hedef %15 · en çok 7 gün
import threading, time
import requests

V = "D1.1 (23.11 18:00)"
BG = "https://api.bitget.com/api/v2/mix/market/"
DUS, YAK, LIM, SL, TP = 0.20, 0.02, 0.03, 0.15, 0.15
L = {"liste": [], "t": 0, "hata": ""}
ESKI = {"BTC", "ETH", "XRP", "ADA", "DOGE", "TRX", "LTC", "BCH", "BNB", "XLM", "ETC", "DOT", "LINK", "SHIB", "AVAX", "XMR", "UNI", "ATOM", "FIL", "NEAR"}

def get(yol, **q):
    for _ in range(3):
        try:
            r = requests.get(BG + yol, params={"productType": "USDT-FUTURES", **q}, timeout=10).json()
            if r.get("code") == "00000": return r["data"]
        except Exception: pass
        time.sleep(0.5)
    return None

def bicim(x):
    return float(f"{x:.6g}")

TP_DUS, TP_YAK = 0.30, 0.02                                 # D1.1: tepe short — 2 günde ≥%30 yükseliş + tepeye %2 yakın (15 ayda 71 işlem, +42,9 $)

def analiz(s, tk=None):
    s = s.upper().strip().replace("/", "").replace("-", "").replace(" ", "")
    if not s.endswith("USDT"): s += "USDT"
    d = get("candles", symbol=s, granularity="4H", limit="100")
    if not d: return {"s": s[:-4], "hata": "Bu coin Bitget vadeli işlemlerde bulunamadı."}
    d = sorted(d, key=lambda x: int(x[0]))
    m = [[float(x[1]), float(x[2]), float(x[3]), float(x[4])] for x in d]     # açılış, yüksek, düşük, kapanış (son mum açık)
    if len(m) < 20: return {"s": s[:-4], "hata": "Coin çok yeni, yeterli mum yok."}
    if tk is None:
        t = get("ticker", symbol=s); tk = t[0] if t else {}
    c = float(tk.get("lastPr") or m[-1][3]); hac = float(tk.get("usdtVolume") or 0); g24 = float(tk.get("change24h") or 0) * 100
    son = m[-13:]                                                       # son 2 gün (12 kapanmış + açık mum)
    h2 = max(max(x[1] for x in son), c); l2 = min(min(x[2] for x in son), c)
    h7 = max(x[1] for x in m[-43:])
    dus = c / h2 - 1; yak = c / l2 - 1; cik = c / l2 - 1; tyak = 1 - c / h2
    kap = [x[3] for x in m[:-1]]; ma5 = sum(kap[-5:]) / 5
    r = {"s": s[:-4], "c": bicim(c), "g24": round(g24, 1), "h2": bicim(h2), "l2": bicim(l2), "h7": bicim(h7), "dus": round(dus * 100, 1),
         "yak": round(yak * 100, 1), "cik": round(cik * 100, 1), "tyak": round(tyak * 100, 1), "hac": round(hac / 1e6, 2), "eski": s[:-4] in ESKI, "notlar": [], "yon": ""}
    if dus <= -DUS:                                                     # 🔻 DİP tarafı → LONG
        r["yon"] = "long"; durdu = kap[-1] > ma5 and min(x[2] for x in m[-3:-1]) > l2
        if yak > YAK:
            r["k"] = "⛔" if yak > 0.06 else "⏳"
            r["baslik"] = "ALMA — dipten uzak, geç kaldın" if yak > 0.06 else "BEKLE — dibe yaklaşıyor, henüz alma"
            r["neden"] = f"2 günde %{abs(dus) * 100:.1f} düştü ama fiyat dipten (2 günlük en düşük {bicim(l2)}) %{yak * 100:.1f} yukarıda. Sinyal için {bicim(l2 * (1 + YAK))} ve altı lazım."
        else:
            lim = c * (1 - LIM)
            r["k"] = "✅"; r["baslik"] = "AL (LONG) — limit emirle"
            r["neden"] = f"2 günde %{abs(dus) * 100:.1f} düştü ve fiyat dibe çok yakın (%{yak * 100:.1f})."
            r["plan"] = {"lim": bicim(lim), "stop": bicim(lim * (1 - SL)), "hedef": bicim(lim * (1 + TP)), "gun": 7}
        r["notlar"].append("✓ 4 saatlikte düşüş durmuş görünüyor." if durdu else "⚠️ 4 saatlikte hâlâ düşüyor — limit emir aşağıda dursun, kovalama.")
    elif cik >= TP_DUS:                                                 # 🔺 TEPE tarafı → SHORT
        r["yon"] = "short"; durdu = kap[-1] < ma5 and max(x[1] for x in m[-3:-1]) < h2
        if tyak > TP_YAK:
            r["k"] = "⛔" if tyak > 0.06 else "⏳"
            r["baslik"] = "SHORT AÇMA — tepeden uzak, geç kaldın" if tyak > 0.06 else "BEKLE — tepeye yakın, henüz açma"
            r["neden"] = f"2 günde %{cik * 100:.1f} yükseldi ama fiyat tepeden (2 günlük en yüksek {bicim(h2)}) %{tyak * 100:.1f} aşağıda. Sinyal için {bicim(h2 * (1 - TP_YAK))} ve üstü lazım."
        else:
            lim = c * (1 + LIM)
            r["k"] = "✅"; r["baslik"] = "SHORT AÇ — limit emirle"
            r["neden"] = f"2 günde %{cik * 100:.1f} yükseldi ve fiyat tepeye çok yakın (%{tyak * 100:.1f})."
            r["plan"] = {"lim": bicim(lim), "stop": bicim(lim * (1 + SL)), "hedef": bicim(lim * (1 - TP)), "gun": 7}
        r["notlar"].append("✓ 4 saatlikte yükseliş durmuş görünüyor." if durdu else "⚠️ 4 saatlikte hâlâ yükseliyor — limit emir yukarıda dursun, kovalama.")
    else:
        r["k"] = "⛔"; r["baslik"] = "GİRME — ne dipte ne tepede"
        r["neden"] = f"Son 2 günde tepeden %{abs(dus) * 100:.1f} aşağıda, dipten %{cik * 100:.1f} yukarıda. Long için 2 günde ≥%20 düşüş, short için ≥%30 yükseliş lazım."
    if hac < 3e6: r["notlar"].append(f"⚠️ Hacim düşük ({hac / 1e6:.1f} M$/gün) — fiyat çok sert oynar.")
    if r["eski"]: r["notlar"].append("ℹ️ Eski/yavaş coin — sen bunlardan uzak durmak istemiştin.")
    r["notlar"].append(f"ℹ️ Bitget'teki %{g24:+.1f} sadece 24 saat öncesine göre; dip/tepe değildir.")
    return r

def tara():
    tk = get("tickers")
    if not tk: L["hata"] = "Bitget'e ulaşılamadı"; return
    ks = get("contracts") or []
    kripto = {x["symbol"] for x in ks if x.get("isRwa") != "YES" and x.get("symbolStatus") == "normal"}
    ad = [x for x in tk if x["symbol"] in kripto and float(x.get("usdtVolume") or 0) >= 1e6 and x["symbol"][:-4] not in ESKI]
    ad.sort(key=lambda x: float(x.get("change24h") or 0))
    out = []
    for x in ad[:35] + ad[-35:]:                                        # D1.1: en çok düşenler + en çok yükselenler
        try:
            r = analiz(x["symbol"], x)
            if "hata" not in r and r["yon"]: out.append(r)
        except Exception: pass
        time.sleep(0.08)
    out.sort(key=lambda r: ({"✅": 0, "⏳": 1, "⛔": 2}[r["k"]], min(r["yak"], r["tyak"])))
    L["liste"] = out[:16]; L["t"] = int(time.time()); L["hata"] = ""

def dongu():
    while True:
        try: tara()
        except Exception as e: L["hata"] = str(e)[:100]
        time.sleep(300)

def basla():
    threading.Thread(target=dongu, daemon=True).start()

def liste():
    return {"v": V, "t": L["t"], "liste": L["liste"], "hata": L["hata"]}
