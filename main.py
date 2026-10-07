# Kısa momentum botu: yükselene LONG, düşene SHORT. İzole, her işlem 1 USDT marjin.
import os, time, threading, collections, ccxt, telebot

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

ex = ccxt.bitget({"apiKey": E("BITGET_API"), "secret": E("BITGET_SEC"), "password": E("BITGET_PASS"),
                  "options": {"defaultType": "swap"}, "enableRateLimit": True, "timeout": 30000})
bot = telebot.TeleBot(E("TELE_TOKEN", "x"), threaded=False)
acik, fiyat, yasak, calisiyor = {}, {}, {}, [True]   # acik[sym]={zirve}

def haber(m):
    print(m, flush=True)
    try: bot.send_message(CHAT, m)
    except Exception: pass

def kapat(sym, p, neden):
    yon = "sell" if p["side"] == "long" else "buy"
    ex.create_order(sym, "market", yon, p["contracts"], params={"reduceOnly": True, "marginMode": "isolated"})
    yasak[sym] = time.time() + BEKLE * 60
    acik.pop(sym, None)
    haber(f"{'✅' if p['unrealizedPnl'] > 0 else '❌'} {sym.split(':')[0]} {neden} PnL≈{p['unrealizedPnl']:+.2f}$")

def ac(sym, yon, son):
    for lev in [l for l in (50, 30, 25, 20, 15, 10, 5, 3, 2) if l <= LEV_TAVAN]:
        try:
            ex.set_leverage(lev, sym, params={"marginMode": "isolated", "holdSide": "long" if yon == "buy" else "short"}); break
        except Exception: lev = 0
    if not lev: yasak[sym] = time.time() + 6 * 3600; return
    m = ex.market(sym)
    adet = ex.amount_to_precision(sym, MARJIN * lev / son / (m.get("contractSize") or 1))
    if float(adet) * son < 5.2: yasak[sym] = time.time() + 6 * 3600; return   # borsa min 5 USDT
    try:
        ex.create_order(sym, "market", yon, float(adet), params={"marginMode": "isolated"})
    except Exception as e:
        yasak[sym] = time.time() + 3600; haber(f"⚠️ {sym.split(':')[0]} açılamadı: {str(e)[:120]}"); return
    acik[sym] = {"zirve": 0.0}
    haber(f"{'🟢 LONG' if yon == 'buy' else '🔴 SHORT'} {sym.split(':')[0]} {lev}x izole, {MARJIN}$")

def yonet():
    pos = [p for p in ex.fetch_positions() if p.get("contracts")]
    for s in [s for s in acik if s not in {p["symbol"] for p in pos}]: acik.pop(s)   # dışarıda kapanan/likit olan
    for p in pos:
        sym = p["symbol"]; k = acik.setdefault(sym, {"zirve": 0.0})
        pnl = p["unrealizedPnl"] or 0.0
        k["zirve"] = max(k["zirve"], pnl)
        if pnl <= -SL_USDT: kapat(sym, p, "STOP")
        elif k["zirve"] >= TRAIL_ON and pnl <= k["zirve"] - TRAIL_GERI: kapat(sym, p, "İZ SÜREN")
    return len(acik)

def tara():
    n = int(PENCERE * 60 / 10)
    tk = ex.fetch_tickers()
    top = sorted((t for s, t in tk.items() if s.endswith(":USDT") and t.get("last")), key=lambda t: -(t.get("quoteVolume") or 0))[:COIN_SAYI]
    for t in top:
        s, son = t["symbol"], t["last"]
        h = fiyat.setdefault(s, collections.deque(maxlen=n)); h.append(son)
        if len(h) < n or s in acik or time.time() < yasak.get(s, 0) or len(acik) >= MAX_POS or not calisiyor[0]: continue
        lo, hi = min(h), max(h)
        if son >= lo * (1 + HAREKET / 100) and son >= hi * 0.997: ac(s, "buy", son)
        elif son <= hi * (1 - HAREKET / 100) and son <= lo * 1.003: ac(s, "sell", son)

@bot.message_handler(commands=["durum", "dur", "basla", "hepsinikapat"])
def kmd(m):
    if m.chat.id != CHAT: return
    c = m.text.split()[0][1:].split("@")[0]
    if c == "dur": calisiyor[0] = False
    if c == "basla": calisiyor[0] = True
    if c == "hepsinikapat":
        calisiyor[0] = False
        for p in ex.fetch_positions():
            if p.get("contracts"): kapat(p["symbol"], p, "MANUEL")
    bot.reply_to(m, f"{'AÇIK' if calisiyor[0] else 'DURDU'} | pozisyon {len(acik)}/{MAX_POS} | {list(acik)}")

if __name__ == "__main__":
    ex.load_markets()
    threading.Thread(target=lambda: bot.infinity_polling(skip_pending=True), daemon=True).start()
    haber(f"Kısa bot hazır: {MARJIN}$ izole, max {MAX_POS}, ≤{LEV_TAVAN}x, SL {SL_USDT}$, iz {TRAIL_ON}$/{TRAIL_GERI}$")
    while True:
        try:
            tara(); yonet()
        except Exception as e: print("hata", e, flush=True)
        time.sleep(10)
