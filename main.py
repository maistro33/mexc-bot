# Kısa momentum botu: yükselene LONG, düşene SHORT. İzole, her işlem 1 USDT marjin.
import os, time, json, threading, collections, ccxt, telebot
from telebot import types

E = os.getenv
MARJIN   = float(E("MARJIN", "1"))        # USDT / işlem
MAX_POS  = int(E("MAX_POS", "5"))
LEV_TAVAN= int(E("LEV_TAVAN", "125"))     # coinin izin verdiği en yüksek kaldıraç denenir (bu sayıyı geçmez)
SL_USDT  = float(E("SL_USDT", "0.8"))     # bu kadar zarara ulaşınca kapat
TRAIL_ON = float(E("TRAIL_ON", "0.3"))    # kâr bu kadar olunca iz sürme başlar
TRAIL_GERI = float(E("TRAIL_GERI", "0.15"))  # zirveden bu kadar geri verirse kapat
HAREKET  = float(E("HAREKET", "3"))       # son PENCERE dakikada % hareket
PENCERE  = int(E("PENCERE", "10"))
BEKLE    = int(E("BEKLE_DK", "30"))       # kapanan coine tekrar girmeden bekleme
COIN_SAYI= int(E("COIN_SAYI", "150"))
CHAT = int(E("MY_CHAT_ID", "0"))

DOSYA = "/data/ayar.json" if os.path.isdir("/data") else "ayar.json"
A = {"v": 2, "marjin": MARJIN, "oto": False, "oran": 0.07, "max_pos": MAX_POS, "lev": LEV_TAVAN, "sl": SL_USDT, "calis": True}
LADDER = (125, 100, 75, 50, 30, 25, 20, 15, 10, 5, 3, 2)
lev_cap = {}   # coin -> son başarılı kaldıraç
acik, fiyat, yasak, gecmis = {}, {}, {}, []   # acik[sym]={zirve, mj, sl(USD), son}
try:
    d = json.load(open(DOSYA))
    if d.get("A", {}).get("v") == 2: A.update(d["A"])      # eski sürüm ayarlarını (oto-büyüme, düşük kaldıraç) yok say
    acik.update(d.get("acik", {})); gecmis.extend(d.get("gecmis", []))
except Exception: pass
def kaydet():
    try: json.dump({"A": A, "acik": acik, "gecmis": gecmis[-300:]}, open(DOSYA, "w"))
    except Exception: pass

ex = ccxt.bitget({"apiKey": E("BITGET_API"), "secret": E("BITGET_SEC"), "password": E("BITGET_PASS"),
                  "options": {"defaultType": "swap"}, "enableRateLimit": True, "timeout": 30000})
bot = telebot.TeleBot(E("TELE_TOKEN", "x"), threaded=False)

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

def logla(sym, yon, pnl, neden):
    gecmis.append({"t": int(time.time()), "s": sym.split(":")[0], "y": yon, "pnl": round(pnl, 3), "n": neden}); kaydet()

def kapat(sym, p, neden):
    yon = "sell" if p["side"] == "long" else "buy"
    ex.create_order(sym, "market", yon, p["contracts"], params={"reduceOnly": True, "marginMode": "isolated"})
    yasak[sym] = time.time() + BEKLE * 60
    acik.pop(sym, None); logla(sym, p['side'], p['unrealizedPnl'], neden)
    haber(f"{'✅' if p['unrealizedPnl'] > 0 else '❌'} {sym.split(':')[0]} {neden} PnL≈{p['unrealizedPnl']:+.2f}$")

def sl_fiyat(yon, giris, adet, cs, usd):   # stop tutarı (USD) -> fiyat
    d = usd / (adet * cs)
    return giris - d if yon in ("buy", "long") else giris + d

def kaldirac_ayarla(sym, lev, yon):
    """Kaldıracı ayarla ve borsadaki GERÇEK değeri oku. Döner: gerçek kaldıraç (okunamazsa None)."""
    taraf = "long" if yon == "buy" else "short"
    for params in ({"marginMode": "isolated", "holdSide": taraf}, {"marginMode": "isolated"}, {}):
        try: ex.set_leverage(lev, sym, params); break
        except Exception: pass
    try:
        r = ex.fetch_leverage(sym, {"marginMode": "isolated"})
        v = r.get(taraf + "Leverage") or r.get("leverage")
        return float(v) if v else None
    except Exception: return None

def ac(sym, yon, son, hr=0.0):
    lev = 0
    for l in [l for l in LADDER if l <= min(A['lev'], lev_cap.get(sym, 999))]:
        g = kaldirac_ayarla(sym, l, yon)
        if g is None or abs(g - l) < 0.5: lev = l; lev_cap[sym] = l; break      # tuttu (okunamıyorsa sonradan doğrulanır)
    if not lev: yasak[sym] = time.time() + 6 * 3600; return
    m = ex.market(sym)
    mj = marjin()
    adet = ex.amount_to_precision(sym, mj * lev / son / (m.get("contractSize") or 1))
    if float(adet) * son < 5.2: yasak[sym] = time.time() + 6 * 3600; return   # borsa min 5 USDT
    try:
        ex.create_order(sym, "market", yon, float(adet), params={"marginMode": "isolated"})
    except Exception as e:
        yasak[sym] = time.time() + 3600; haber(f"⚠️ {sym.split(':')[0]} açılamadı: {str(e)[:120]}"); return
    try:
        p = next(x for x in ex.fetch_positions([sym]) if x.get("contracts"))
        if abs(float(p.get("leverage") or lev) - lev) > 0.5 or float(p.get("initialMargin") or 0) > mj * 1.5:
            kapat(sym, p, "KALDIRAÇ UYUŞMADI"); yasak[sym] = time.time() + 6 * 3600
            haber(f"🚨 {sym.split(':')[0]}: istenen {lev}x ama borsada {p.get('leverage')}x oldu, pozisyonu kapattım"); return
    except StopIteration: pass
    except Exception: pass
    cs = m.get("contractSize") or 1; sl = round(A["sl"] * mj, 2); not_ = ""
    try:   # stop likidasyondan ÖNCE gelsin: likidasyon uzaklığının %70'ine daralt
        liq, gir = float(p.get("liquidationPrice") or 0), float(p.get("entryPrice") or son)
        if liq and sl / (float(adet) * cs) > 0.7 * abs(gir - liq):
            sl = round(0.7 * abs(gir - liq) * float(adet) * cs, 3); not_ = " (likidasyona yakın olduğu için daraltıldı)"
    except Exception: pass
    acik[sym] = {"zirve": 0.0, "mj": mj, "sl": sl, "son": 0.0}; kaydet()
    haber(f"{'🟢 LONG' if yon == 'buy' else '🔴 SHORT'} {sym.split(':')[0]} {lev}x izole, {mj}$\n"
          f"Sebep: son {PENCERE} dk {'+' if yon == 'buy' else '-'}%{hr:.1f} hareket (momentum)\n"
          f"Giriş ≈ {son:g} | Stop ≈ {sl_fiyat(yon, son, float(adet), cs, sl):g} (−{sl}${not_})\n"
          f"İz süren: kâr +{TRAIL_ON*mj:.2f}$ olunca başlar, zirveden {TRAIL_GERI*mj:.2f}$ geri verirse kapatır")

def yonet():
    pos = [p for p in ex.fetch_positions() if p.get("contracts")]
    var = {p["symbol"] for p in pos}
    for s in [s for s in acik if s not in var]:      # dışarıda (elle/likidasyon) kapanan
        logla(s, "?", acik[s].get("son", 0.0), "DIŞARIDA KAPANDI"); acik.pop(s)
    for p in pos:
        sym = p["symbol"]; pnl = p["unrealizedPnl"] or 0.0
        if sym not in acik:                          # bot kapanıp açılınca / elle açılan: devral
            mj = float(p.get("initialMargin") or MARJIN)
            acik[sym] = {"zirve": max(pnl, 0.0), "mj": mj, "sl": round(A["sl"] * mj, 2), "son": pnl}
        k = acik[sym]; k["son"] = pnl; k["zirve"] = max(k["zirve"], pnl)
        if pnl <= -k["sl"]: kapat(sym, p, "STOP")
        elif k["zirve"] >= TRAIL_ON * k["mj"] and pnl <= k["zirve"] - TRAIL_GERI * k["mj"]: kapat(sym, p, "İZ SÜREN")
    kaydet()
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
        if son >= lo * (1 + HAREKET / 100) and son >= hi * 0.997: ac(s, "buy", son, (son / lo - 1) * 100)
        elif son <= hi * (1 - HAREKET / 100) and son <= lo * 1.003: ac(s, "sell", son, (1 - son / hi) * 100)

POZ = {}   # düğme numarası -> sembol

def metin():
    ps = [p for p in ex.fetch_positions() if p.get("contracts")]
    POZ.clear(); satir = []
    for n, p in enumerate(ps):
        POZ[n] = p["symbol"]; k = acik.get(p["symbol"], {})
        satir.append(f"{n+1}) {'🟢' if p['side']=='long' else '🔴'} {p['symbol'].split(':')[0]} {p['leverage'] or '?'}x  {p['unrealizedPnl']:+.2f}$  giriş {p.get('entryPrice') or 0:g} | stop {sl_fiyat(p['side'], p.get('entryPrice') or 0, p['contracts'], p.get('contractSize') or 1, k.get('sl', 0)):g} (−{k.get('sl', 0)}$)")
    bug = time.strftime("%Y-%m-%d", time.localtime()); gun = sum(g["pnl"] for g in gecmis if time.strftime("%Y-%m-%d", time.localtime(g["t"])) == bug)
    return (f"{'▶️ AÇIK' if A['calis'] else '⏹ DURDU'}  Bakiye {bakiye():.2f}$\nBugün ≈{gun:+.2f}$ | toplam ≈{sum(g['pnl'] for g in gecmis):+.2f}$ ({len(gecmis)} işlem)\n"
            f"Marjin {marjin():.1f}$ ({'oto %'+str(int(A['oran']*100)) if A['oto'] else 'sabit'}) | Max {A['max_pos']} | ≤{A['lev']}x | SL %{A['sl']*100:.0f}\n\n" + ("\n".join(satir) or "pozisyon yok"))

def klavye():
    b = lambda t, d: types.InlineKeyboardButton(t, callback_data=d)
    k = types.InlineKeyboardMarkup(row_width=4)
    for n, sym in POZ.items():
        k.add(b(f"❌{n+1}", f"k{n}"), b(f"{n+1} lev−", f"a{n}"), b(f"{n+1} lev+", f"b{n}"), b(f"{n+1} SL−", f"c{n}"), b(f"{n+1} SL+", f"d{n}"))
    k.add(b("⏹ Durdur" if A["calis"] else "▶️ Başlat", "tog"), b("🔄 Yenile", "yen"), b("📜 Geçmiş", "gec"))
    k.add(b("Marjin −", "m-"), b("Oto " + ("✅" if A["oto"] else "❌"), "oto"), b("Marjin +", "m+"))
    k.add(b("Max poz −", "p-"), b("Kaldıraç −", "l-"), b("Kaldıraç +", "l+"))
    k.add(b("Max poz +", "p+"), b("SL% −", "s-"), b("SL% +", "s+"), b("🛑 Hepsini kapat", "hep"))
    return k

def gecmis_metin():
    son = gecmis[-15:][::-1]
    return "📜 Son işlemler (PnL≈, komisyon hariç)\n" + ("\n".join(f"{time.strftime('%d.%m %H:%M', time.localtime(g['t']))} {g['s']} {g['y']} {g['pnl']:+.2f}$ {g['n']}" for g in son) or "henüz yok")

@bot.message_handler(commands=["panel", "start", "durum", "gecmis"])
def pn(m):
    if m.chat.id != CHAT: return
    if m.text.startswith("/gecmis"): return bot.send_message(CHAT, gecmis_metin())
    t = metin(); bot.send_message(CHAT, t, reply_markup=klavye())

def pozisyon(n):
    sym = POZ.get(n)
    return sym, next((p for p in ex.fetch_positions() if p["symbol"] == sym and p.get("contracts")), None)

@bot.callback_query_handler(func=lambda c: True)
def cb(c):
    if c.message.chat.id != CHAT: return
    d, uyari = c.data, ""
    try:
        if d == "gec": return bot.send_message(CHAT, gecmis_metin()), bot.answer_callback_query(c.id)
        if d[0] in "kabcd" and d[1:].isdigit():
            sym, p = pozisyon(int(d[1:]))
            if not p: uyari = "pozisyon yok, yenile"
            elif d[0] == "k": kapat(sym, p, "MANUEL")
            elif d[0] in "ab":
                yeni = max(1, int(p["leverage"] or 1) + (-1 if d[0] == "a" else 1) * 5)
                ex.set_leverage(yeni, sym, params={"marginMode": "isolated", "holdSide": p["side"]}); uyari = f"{yeni}x"
            else: acik[sym]["sl"] = max(0.2, round(acik[sym]["sl"] + (-0.2 if d[0] == "c" else 0.2), 2))
        elif d == "tog": A["calis"] = not A["calis"]
        elif d == "oto": A["oto"] = not A["oto"]
        elif d == "m+": A["marjin"] = round(A["marjin"] + 0.5, 1)
        elif d == "m-": A["marjin"] = max(1.0, round(A["marjin"] - 0.5, 1))
        elif d == "p+": A["max_pos"] = min(10, A["max_pos"] + 1)
        elif d == "p-": A["max_pos"] = max(1, A["max_pos"] - 1)
        elif d == "l+": A["lev"] = next((x for x in sorted(LADDER) if x > A["lev"]), 125)
        elif d == "l-": A["lev"] = next((x for x in sorted(LADDER, reverse=True) if x < A["lev"]), 2)
        elif d == "s+": A["sl"] = min(0.9, round(A["sl"] + 0.05, 2))
        elif d == "s-": A["sl"] = max(0.2, round(A["sl"] - 0.05, 2))
        elif d == "hep":
            A["calis"] = False
            for p in ex.fetch_positions():
                if p.get("contracts"): kapat(p["symbol"], p, "MANUEL")
    except Exception as e: uyari = str(e)[:150]
    kaydet()
    try: bot.edit_message_text(metin(), c.message.chat.id, c.message.message_id, reply_markup=klavye())
    except Exception: pass
    bot.answer_callback_query(c.id, uyari)

if __name__ == "__main__":
    ex.load_markets()
    threading.Thread(target=lambda: bot.infinity_polling(skip_pending=True), daemon=True).start()
    haber(f"Kısa bot hazır: {marjin()}$ izole, max {A['max_pos']}, ≤{A['lev']}x, SL %{A['sl']*100:.0f}, oto-büyüme {A['oto']}  → /panel")
    while True:
        try:
            tara(); yonet()
        except Exception as e: print("hata", e, flush=True)
        time.sleep(10)
