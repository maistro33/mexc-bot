# Kısa momentum botu: yükselene LONG, düşene SHORT. İzole, her işlem 1 USDT marjin.
import os, time, json, threading, collections, ccxt, telebot
from telebot import types

E = os.getenv
MARJIN   = float(E("MARJIN", "1"))        # USDT / işlem
MAX_POS  = int(E("MAX_POS", "5"))
LEV_TAVAN= int(E("LEV_TAVAN", "15"))      # borsa izin verirse bu kadar (likidasyon SL'den sonra gelsin)
SL_USDT  = float(E("SL_USDT", "0.8"))     # bu kadar zarara ulaşınca kapat
TRAIL_ON = float(E("TRAIL_ON", "0.3"))    # kâr bu kadar olunca iz sürme başlar
TRAIL_GERI = float(E("TRAIL_GERI", "0.15"))  # zirveden bu kadar geri verirse kapat
HAREKET  = float(E("HAREKET", "3"))       # son PENCERE dakikada % hareket
PENCERE  = int(E("PENCERE", "10"))
BEKLE    = int(E("BEKLE_DK", "30"))       # kapanan coine tekrar girmeden bekleme
COIN_SAYI= int(E("COIN_SAYI", "150"))
CHAT = int(E("MY_CHAT_ID", "0"))

DOSYA = "/data/ayar.json" if os.path.isdir("/data") else "ayar.json"
A = {"marjin": MARJIN, "oto": True, "oran": 0.07, "max_pos": MAX_POS, "lev": LEV_TAVAN, "sl": SL_USDT, "calis": True}
try: A.update(json.load(open(DOSYA)))
except Exception: pass
def kaydet():
    try: json.dump(A, open(DOSYA, "w"))
    except Exception: pass
toplam = [0.0]

ex = ccxt.bitget({"apiKey": E("BITGET_API"), "secret": E("BITGET_SEC"), "password": E("BITGET_PASS"),
                  "options": {"defaultType": "swap"}, "enableRateLimit": True, "timeout": 30000})
bot = telebot.TeleBot(E("TELE_TOKEN", "x"), threaded=False)
acik, fiyat, yasak = {}, {}, {}   # acik[sym]={zirve}

def bakiye():
    try: return float(ex.fetch_balance()["USDT"]["total"])
    except Exception: return 0.0

def marjin():   # oto: bakiyenin %oran'ı (kâr büyüdükçe büyür, 1$ altına inmez)
    if not A["oto"]: return A["marjin"]
    return max(A["marjin"], int(bakiye() * A["oran"] * 10) / 10)

def haber(m):
    print(m, flush=True)
    try: bot.send_message(CHAT, m)
    except Exception: pass

def kapat(sym, p, neden):
    yon = "sell" if p["side"] == "long" else "buy"
    ex.create_order(sym, "market", yon, p["contracts"], params={"reduceOnly": True, "marginMode": "isolated"})
    yasak[sym] = time.time() + BEKLE * 60
    acik.pop(sym, None); toplam[0] += p['unrealizedPnl']
    haber(f"{'✅' if p['unrealizedPnl'] > 0 else '❌'} {sym.split(':')[0]} {neden} PnL≈{p['unrealizedPnl']:+.2f}$")

def ac(sym, yon, son):
    for lev in [l for l in (50, 30, 25, 20, 15, 10, 5, 3, 2) if l <= A['lev']]:
        try:
            ex.set_leverage(lev, sym, params={"marginMode": "isolated", "holdSide": "long" if yon == "buy" else "short"}); break
        except Exception: lev = 0
    if not lev: yasak[sym] = time.time() + 6 * 3600; return
    m = ex.market(sym)
    mj = marjin()
    adet = ex.amount_to_precision(sym, mj * lev / son / (m.get("contractSize") or 1))
    if float(adet) * son < 5.2: yasak[sym] = time.time() + 6 * 3600; return   # borsa min 5 USDT
    try:
        ex.create_order(sym, "market", yon, float(adet), params={"marginMode": "isolated"})
    except Exception as e:
        yasak[sym] = time.time() + 3600; haber(f"⚠️ {sym.split(':')[0]} açılamadı: {str(e)[:120]}"); return
    acik[sym] = {"zirve": 0.0, "mj": mj}
    haber(f"{'🟢 LONG' if yon == 'buy' else '🔴 SHORT'} {sym.split(':')[0]} {lev}x izole, {mj}$")

def yonet():
    pos = [p for p in ex.fetch_positions() if p.get("contracts")]
    for s in [s for s in acik if s not in {p["symbol"] for p in pos}]: acik.pop(s)   # dışarıda kapanan/likit olan
    for p in pos:
        sym = p["symbol"]; k = acik.setdefault(sym, {"zirve": 0.0})
        pnl = p["unrealizedPnl"] or 0.0
        k["zirve"] = max(k["zirve"], pnl)
        mj = float(p.get("initialMargin") or k.get("mj") or MARJIN)   # eşikler marjinle orantılı
        if pnl <= -A["sl"] * mj: kapat(sym, p, "STOP")
        elif k["zirve"] >= TRAIL_ON * mj and pnl <= k["zirve"] - TRAIL_GERI * mj: kapat(sym, p, "İZ SÜREN")
    return len(acik)

def tara():
    n = int(PENCERE * 60 / 10)
    tk = ex.fetch_tickers()
    top = sorted((t for s, t in tk.items() if s.endswith(":USDT") and t.get("last")), key=lambda t: -(t.get("quoteVolume") or 0))[:COIN_SAYI]
    for t in top:
        s, son = t["symbol"], t["last"]
        h = fiyat.setdefault(s, collections.deque(maxlen=n)); h.append(son)
        if len(h) < n or s in acik or time.time() < yasak.get(s, 0) or len(acik) >= A['max_pos'] or not A['calis']: continue
        lo, hi = min(h), max(h)
        if son >= lo * (1 + HAREKET / 100) and son >= hi * 0.997: ac(s, "buy", son)
        elif son <= hi * (1 - HAREKET / 100) and son <= lo * 1.003: ac(s, "sell", son)

def metin():
    ps = [p for p in ex.fetch_positions() if p.get("contracts")]
    satir = "\n".join(f"{'🟢' if p['side']=='long' else '🔴'} {p['symbol'].split(':')[0]} {p['unrealizedPnl']:+.2f}$" for p in ps) or "pozisyon yok"
    return (f"{'▶️ AÇIK' if A['calis'] else '⏹ DURDU'}\nBakiye {bakiye():.2f}$ | oturum PnL {toplam[0]:+.2f}$\n"
            f"Marjin {marjin():.1f}$ ({'oto %'+str(int(A['oran']*100)) if A['oto'] else 'sabit'}) | Max {A['max_pos']} | ≤{A['lev']}x | SL %{A['sl']*100:.0f}\n\n{satir}")

def klavye():
    b = lambda t, d: types.InlineKeyboardButton(t, callback_data=d)
    k = types.InlineKeyboardMarkup(row_width=3)
    k.add(b("⏹ Durdur" if A["calis"] else "▶️ Başlat", "tog"), b("🔄 Yenile", "yen"), b("🛑 Hepsini kapat", "hep"))
    k.add(b("Marjin −", "m-"), b("Oto-büyüme " + ("✅" if A["oto"] else "❌"), "oto"), b("Marjin +", "m+"))
    k.add(b("Max poz −", "p-"), b("Kaldıraç −", "l-"), b("Kaldıraç +", "l+"))
    k.add(b("Max poz +", "p+"), b("SL −", "s-"), b("SL +", "s+"))
    return k

@bot.message_handler(commands=["panel", "start", "durum"])
def pn(m):
    if m.chat.id == CHAT: bot.send_message(CHAT, metin(), reply_markup=klavye())

@bot.callback_query_handler(func=lambda c: True)
def cb(c):
    if c.message.chat.id != CHAT: return
    d = c.data
    if d == "tog": A["calis"] = not A["calis"]
    elif d == "oto": A["oto"] = not A["oto"]
    elif d == "m+": A["marjin"] = round(A["marjin"] + 0.5, 1)
    elif d == "m-": A["marjin"] = max(1.0, round(A["marjin"] - 0.5, 1))
    elif d == "p+": A["max_pos"] = min(10, A["max_pos"] + 1)
    elif d == "p-": A["max_pos"] = max(1, A["max_pos"] - 1)
    elif d == "l+": A["lev"] = min(20, A["lev"] + 5)
    elif d == "l-": A["lev"] = max(2, A["lev"] - 5)
    elif d == "s+": A["sl"] = min(0.9, round(A["sl"] + 0.05, 2))
    elif d == "s-": A["sl"] = max(0.2, round(A["sl"] - 0.05, 2))
    elif d == "hep":
        A["calis"] = False
        for p in ex.fetch_positions():
            if p.get("contracts"): kapat(p["symbol"], p, "MANUEL")
    kaydet()
    try: bot.edit_message_text(metin(), c.message.chat.id, c.message.message_id, reply_markup=klavye())
    except Exception: pass
    bot.answer_callback_query(c.id)

if __name__ == "__main__":
    ex.load_markets()
    threading.Thread(target=lambda: bot.infinity_polling(skip_pending=True), daemon=True).start()
    haber(f"Kısa bot hazır: {marjin()}$ izole, max {A['max_pos']}, ≤{A['lev']}x, SL %{A['sl']*100:.0f}, oto-büyüme {A['oto']}  → /panel")
    while True:
        try:
            tara(); yonet()
        except Exception as e: print("hata", e, flush=True)
        time.sleep(10)
