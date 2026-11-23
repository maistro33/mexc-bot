# 🔍 Dip Bulucu — Sadık'ın elle işlemi için (emir vermez, sadece söyler)
# Sürüm D1.0 (23.11) — kural = K1.3 Dip Alım (15 aylık testte artı): 2 günde ≥%20 düşüş + fiyat 2 günlük dibe %2'den yakın
#   → %3 aşağıdan limit alış · stop %15 · hedef %15 · en çok 7 gün
import threading, time
import requests

V = "D1.0 (23.11 17:15)"
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

def analiz(s, tk=None):
    s = s.upper().strip().replace("/", "").replace("-", "")
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
    h2 = max(x[1] for x in son); l2 = min(min(x[2] for x in son), c)
    h7 = max(x[1] for x in m[-43:])
    dus = c / h2 - 1; yak = c / l2 - 1; dus7 = c / h7 - 1
    kap = [x[3] for x in m[:-1]]; ma5 = sum(kap[-5:]) / 5
    durdu = kap[-1] > ma5 and min(x[2] for x in m[-3:-1]) > l2          # son kapanan mum MA5 üstünde ve son 2 mumda yeni dip yok
    lim = c * (1 - LIM)
    r = {"s": s[:-4], "c": bicim(c), "g24": round(g24, 1), "h2": bicim(h2), "l2": bicim(l2), "h7": bicim(h7), "dus": round(dus * 100, 1),
         "yak": round(yak * 100, 1), "dus7": round(dus7 * 100, 1), "durdu": durdu, "hac": round(hac / 1e6, 2), "eski": s[:-4] in ESKI, "notlar": []}
    if dus > -DUS:
        r["k"] = "⛔"; r["baslik"] = "ALMA — yeterince düşmemiş"
        r["neden"] = f"Son 2 günün tepesinden sadece %{abs(dus) * 100:.1f} aşağıda. Kural en az %20 düşüş ister."
    elif yak > YAK:
        r["k"] = "⛔" if yak > 0.06 else "⏳"
        r["baslik"] = "ALMA — dipten uzak, geç kaldın" if yak > 0.06 else "BEKLE — dibe yaklaşıyor, henüz alma"
        r["neden"] = f"2 günde %{abs(dus) * 100:.1f} düştü ama fiyat dipten (2 günlük en düşük {bicim(l2)}) %{yak * 100:.1f} yukarıda. Sinyal için dibe %2 yaklaşması lazım: {bicim(l2 * (1 + YAK))} ve altı."
    else:
        r["k"] = "✅"; r["baslik"] = "AL — limit emirle"
        r["neden"] = f"2 günde %{abs(dus) * 100:.1f} düştü ve fiyat dibe çok yakın (%{yak * 100:.1f})."
        r["plan"] = {"lim": bicim(lim), "stop": bicim(lim * (1 - SL)), "hedef": bicim(lim * (1 + TP))}
    if r["k"] != "⛔" or dus <= -DUS:
        r["notlar"].append("✓ 4 saatlikte düşüş durmuş görünüyor (son mum MA5 üstünde, yeni dip yok)." if durdu else "⚠️ 4 saatlikte hâlâ düşüyor (MA5 altında ya da yeni dip yapıyor) — limit emir aşağıda dursun, kovalama.")
    if hac < 3e6: r["notlar"].append(f"⚠️ Hacim düşük ({hac / 1e6:.1f} M$/gün) — fiyat çok sert oynar, küçük gir.")
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
    for x in ad[:45]:
        try:
            r = analiz(x["symbol"], x)
            if "hata" not in r and r["dus"] <= -DUS * 100: out.append(r)
        except Exception: pass
        time.sleep(0.08)
    out.sort(key=lambda r: ({"✅": 0, "⏳": 1, "⛔": 2}[r["k"]], r["yak"]))
    L["liste"] = out[:15]; L["t"] = int(time.time()); L["hata"] = ""

def dongu():
    while True:
        try: tara()
        except Exception as e: L["hata"] = str(e)[:100]
        time.sleep(300)

def basla():
    threading.Thread(target=dongu, daemon=True).start()

def liste():
    return {"v": V, "t": L["t"], "liste": L["liste"], "hata": L["hata"]}
