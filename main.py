# Kısa momentum botu: yükselene LONG, düşene SHORT. İzole, her işlem 1 USDT marjin.
import os, time, json, threading, collections, ccxt, telebot
from telebot import types

# SÜRÜM GEÇMİŞİ (her değişiklikte VERSIYON ve buraya bir satır eklenir)
# v3.0 08.10 16:25  4 basamaklı kademeli kilit (30/50/75/100), basamak 1 kilidi +0.12$, 2. basamaktan sonra stop zirvenin %65'i,
#                   40797 kaldıraç hatasında bir basamak düşürüp tekrar dene, açılışta sürüm yazısı
# v3.5 08.10 22:55  Yeni giriş MOD=mum15 (varsayılan): her 15 dk kapanışında, 15 dk mum aralığı (yüksek-düşük) >= %8 olan ve YUTAN (engulfing) ya da SABAH/AKŞAM YILDIZI formasyonu yapan coine formasyon yönünde gir. env: MUM15_ARALIK (varsayılan 8). Önceki: MOD=fitil / mum / pencere
# v3.4 08.10 22:30  Yeni giriş MOD=fitil (varsayılan): her 15 dk mum kapanışında 4 saatlik + 1 saatlik + 15 dk son kapanmış mumların HEPSİ aynı yönde fitil bırakmış ve fitil yönünde kapanmışsa gir (altta fitil+yeşil=LONG, üstte fitil+kırmızı=SHORT). Eski yöntemler: env MOD=mum / MOD=pencere
# v3.3 08.10 21:20  Giriş: kayan pencere yerine 5 dk'lık MUM GÖVDESİ (açılış→kapanış) >= %3 ise, mum kapanır kapanmaz yeni mumun başında gir (MOD=mum; eski yöntem için env MOD=pencere)
# v3.2 08.10 21:05  Hisse/ETF sembolleri otomatik hariç (panelde aç/kapa), giriş penceresi 10dk→5dk (%3), basamak 1 = net ~0.30$ kalacak şekilde (ücret+kayma eklenir), kilit1 = net 0.30$
# v3.1 08.10 16:40  Borsa tarafı kilit stopu (stop-market, reduce-only). VARSAYILAN KAPALI, panelde Ayarlar > Borsa stop ile açılır. Hata olursa bot-içi stop aynen devam eder.
VERSIYON = "v3.5 (08.10 22:55)"
E = os.getenv
MARJIN   = float(E("MARJIN", "1"))        # USDT / işlem
MAX_POS  = int(E("MAX_POS", "5"))
LEV_TAVAN= int(E("LEV_TAVAN", "125"))     # coinin izin verdiği en yüksek kaldıraç denenir (bu sayıyı geçmez)
SL_USDT  = float(E("SL_USDT", "0.8"))     # bu kadar zarara ulaşınca kapat
TRAIL_ON = float(E("TRAIL_ON", "0.3"))    # kâr bu kadar olunca iz sürme başlar
TRAIL_GERI = float(E("TRAIL_GERI", "0.15"))  # zirveden bu kadar geri verirse kapat
MUM15_ARALIK = float(E("MUM15_ARALIK", "8"))   # 15 dk mumun yüksek-düşük aralığı en az bu % olmalı
FITIL    = float(E("FITIL", "0.4"))     # fitil, mum boyunun (yüksek-düşük) en az bu kadarı olmalı
HAREKET  = float(E("HAREKET", "3"))       # son PENCERE dakikada % hareket
PENCERE  = int(E("PENCERE", "5"))
MOD      = E("MOD", "mum15")        # "mum": mum gövdesi sinyali (yeni mum başında giriş), "pencere": eski kayan pencere
BEKLE    = int(E("BEKLE_DK", "30"))       # kapanan coine tekrar girmeden bekleme
COIN_SAYI= int(E("COIN_SAYI", "150"))
MIN_SL_PCT = float(E("MIN_SL_PCT", "1.5"))   # stop fiyattan en az bu kadar uzak olmalı; değilse kaldıraç düşürülür (0 = kapalı)
CHAT = int(E("MY_CHAT_ID", "0"))

DOSYA = "/data/ayar.json" if os.path.isdir("/data") else "ayar.json"
A = {"v": 2, "marjin": MARJIN, "oto": False, "oran": 0.07, "max_pos": MAX_POS, "lev": LEV_TAVAN, "sl": SL_USDT, "tp": float(E("TP", "0.35")), "iz": False, "kademe": False, "bs": False, "hk": True, "lv": [0.42, 0.50, 0.75, 1.00], "gunluk": 1.0, "haric": "BTC ETH XRP ADA DOGE SOL BNB LTC BCH TRX LINK DOT AVAX XLM ETC ATOM SHIB PEPE".split(), "calis": True}
HISSE = set("PLTR MRNA MSTU AAOI AXTI ORCL SOXL CRWV MUU TSLA NVDA AAPL MSFT AMZN GOOGL AMD INTC MSTR HOOD SPY QQQ NFLX BABA SMCI AVGO TSM MU PYPL UBER IONQ RGTI SOFI RIVN NIO".split())   # hisse/ETF perpetual sembolleri
LADDER = (125, 100, 75, 50, 30, 25, 20, 15, 10, 5, 3, 2)
lev_cap = {}   # coin -> borsanın kabul ettiği en yüksek kaldıraç (kalıcı)
acik, fiyat, yasak, gecmis = {}, {}, {}, []   # acik[sym]={zirve, mj, sl(USD), son}
try:
    d = json.load(open(DOSYA))
    if d.get("A", {}).get("v") == 2: A.update(d["A"])      # eski sürüm ayarlarını (oto-büyüme, düşük kaldıraç) yok say
    acik.update(d.get("acik", {})); gecmis.extend(d.get("gecmis", [])); lev_cap.update(d.get("cap", {}))
except Exception: pass
def kaydet():
    try: json.dump({"A": A, "acik": acik, "gecmis": gecmis[-300:], "cap": lev_cap}, open(DOSYA, "w"))
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

def logla(sym, yon, pnl, neden, z=0.0):
    try: mid = ex.market(sym)["id"]
    except Exception: mid = sym.split(":")[0].replace("/", "")
    gecmis.append({"t": int(time.time()), "s": sym.split(":")[0], "id": mid, "y": yon, "pnl": round(pnl, 3), "n": neden, "z": round(z, 2), "g": 0}); kaydet()

hata_goster = [True]
def gercek_pnl(mid, t):
    """Borsanın pozisyon geçmişinden NET kâr/zarar (komisyon + fonlama dahil). Bulunamazsa None."""
    try:
        r = ex.private_mix_get_v2_mix_position_history_position({"productType": "USDT-FUTURES", "symbol": mid, "limit": "20"})
        for x in (r.get("data") or {}).get("list", []):
            if abs(int(x.get("utime") or 0) / 1000 - t) < 120:
                return float(x.get("netProfit") if x.get("netProfit") not in (None, "") else x.get("pnl"))
    except Exception as e:
        if hata_goster[0]: hata_goster[0] = False; haber(f"⚠️ Gerçek kâr/zarar borsadan okunamadı (tahmin gösteriliyor): {str(e)[:150]}")
    return None

def duzelt():   # kapanışlardan ~20 sn sonra tahmini PnL'yi borsanın gerçek (komisyonlu) rakamıyla değiştir
    for g in gecmis[-40:]:
        if g.get("g", 1) == 0 and time.time() - g["t"] > 20 and time.time() - g.get("d", 0) > 15:
            g["d"] = time.time(); v = gercek_pnl(g.get("id", ""), g["t"])
            if v is not None: g["pnl"], g["g"] = round(v, 3), 1
            elif time.time() - g["t"] > 900: g["g"] = 2     # bulunamadı, tahmin kalsın
    kaydet()

def borsa_stop_iptal(sym, sid):
    if not sid: return
    for prm in ({"trigger": True}, {"stop": True}, {}):
        try: ex.cancel_order(sid, sym, prm); return
        except Exception: pass

def borsa_stop(sym, p, k, kilit):
    """Kilit seviyesine BORSADA stop-market (reduce-only) koy. Hata olursa bot-içi stop devam eder. Döner: başarılı mı."""
    try:
        qty = float(p["contracts"]); cs = ex.market(sym).get("contractSize") or 1
        gir = float(p.get("entryPrice")); d = kilit / (qty * cs); uz = p["side"] == "long"
        fy = ex.price_to_precision(sym, gir + d if uz else gir - d)
        eski = k.get("sid")
        o = ex.create_order(sym, "market", "sell" if uz else "buy", qty, params={"stopLossPrice": fy, "reduceOnly": True, "marginMode": "isolated"})
        k["sid"] = o.get("id") or (o.get("info") or {}).get("orderId")
        if eski: borsa_stop_iptal(sym, eski)
        haber(f"🛡 {sym.split(':')[0]} borsada stop kondu: {fy} (kilit +{kilit:.2f}$)")
        return True
    except Exception as e:
        haber(f"⚠️ {sym.split(':')[0]} borsa stop konamadı, bot takip ediyor: {str(e)[:110]}")
        return False

def kapat(sym, p, neden):
    yon = "sell" if p["side"] == "long" else "buy"
    ex.create_order(sym, "market", yon, p["contracts"], params={"reduceOnly": True, "marginMode": "isolated"})
    yasak[sym] = time.time() + BEKLE * 60
    kk = acik.pop(sym, {}); borsa_stop_iptal(sym, kk.get("sid")); z = kk.get("zirve", 0.0); logla(sym, p['side'], p['unrealizedPnl'], neden, z)
    haber(f"{'✅' if p['unrealizedPnl'] > 0 else '❌'} {sym.split(':')[0]} {neden} PnL≈{p['unrealizedPnl']:+.2f}$ (gördüğü zirve {z:+.2f}$)")

def sl_fiyat(yon, giris, adet, cs, usd):   # stop tutarı (USD) -> fiyat
    d = usd / (adet * cs)
    return giris - d if yon in ("buy", "long") else giris + d

def kaldirac_ayarla(sym, lev, yon):
    """Kaldıracı ayarla, borsadaki GERÇEK değeri oku. Döner: (ayar_basarili, gercek_lev|None, hata)."""
    taraf = "long" if yon == "buy" else "short"; ok, hata = False, ""
    for params in ({"holdSide": taraf}, {}, {"marginMode": "isolated", "holdSide": taraf}):
        try: ex.set_leverage(lev, sym, params); ok = True; break
        except Exception as e: hata = str(e)[:150]
    gercek = None
    if ok:
        try:
            r = ex.fetch_leverage(sym, {"marginMode": "isolated"})
            v = r.get(taraf + "Leverage") or r.get("leverage"); gercek = float(v) if v else None
        except Exception: pass
    return ok, gercek, hata

def ac(sym, yon, son, hr=0.0):
    lev, hata = 0, ""
    for l in [l for l in LADDER if l <= min(A['lev'], lev_cap.get(sym, 999)) and 70 * (1 / l - 0.0105) >= MIN_SL_PCT]:
        ok, g, h = kaldirac_ayarla(sym, l, yon); hata = h or hata
        if ok and (g is None or abs(g - l) < 0.5): lev = l; break   # tuttu
        if ok and g is not None and g < l: lev_cap[sym] = int(g)   # borsa daha düşüğünü uyguladı: öğren
    if not lev:
        yasak[sym] = time.time() + 6 * 3600
        if hata: haber(f"⚠️ {sym.split(':')[0]} kaldıraç ayarlanamadı, atlandı: {hata}")
        return
    m = ex.market(sym)
    mj = marjin()
    adet = ex.amount_to_precision(sym, mj * lev / son / (m.get("contractSize") or 1))
    if float(adet) * son < 5.2: yasak[sym] = time.time() + 6 * 3600; return   # borsa min 5 USDT
    cs0 = m.get("contractSize") or 1; prm = {"marginMode": "isolated"}; tp_not = ""
    tp_oran = 0 if A["kademe"] else A["tp"]
    if tp_oran > 0:   # kâr al emri BORSADA durur: bot 2 sn geç kalsa da tepede kapanır (kademeli modda SON hedef)
        d = tp_oran * mj / (float(adet) * cs0)
        prm["takeProfit"] = {"triggerPrice": ex.price_to_precision(sym, son + d if yon == "buy" else son - d)}
    try:
        ex.create_order(sym, "market", yon, float(adet), params=prm)
    except Exception as e:
        if "takeProfit" in prm:      # borsa TP'yi kabul etmediyse TP'siz aç, bot takip etsin
            prm.pop("takeProfit"); tp_not = "\n⚠️ Borsa tarafı TP konamadı, bot takip ediyor"
            try: ex.create_order(sym, "market", yon, float(adet), params=prm); e = None
            except Exception as e2: e = e2
        if e and "40797" in str(e):      # borsa bu coin için bu kaldıracı kabul etmiyor: bir basamak düşür, bir sonraki taramada tekrar dene
            alt = [l for l in LADDER if l < lev]
            if alt: lev_cap[sym] = alt[0]; yasak[sym] = time.time() + 20; haber(f"ℹ️ {sym.split(':')[0]} {lev}x kabul edilmedi, {alt[0]}x ile tekrar denenecek"); return
        if e:
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
    kd = (" | Kademe kilidi: " + " → ".join(f"+{x*mj:.2f}$" for x in A["lv"]) + " (her basamakta stop bir basamak geriye kilitlenir, satış yok)") if A["kademe"] else ""
    izm = f" | İz süren: +{TRAIL_ON*mj:.2f}$ olunca başlar, zirveden {TRAIL_GERI*mj:.2f}$ geri verirse kapatır" if A["iz"] else ""
    sebep = (f"15 dk büyük mum (%{hr:.0f} aralık) yutan/yıldız formasyonu, formasyon yönünde giriş" if MOD == "mum15" else
             "4s + 1s + 15dk mumların hepsinde " + ("altta fitil, yeşil kapanış" if yon == "buy" else "üstte fitil, kırmızı kapanış") if MOD == "fitil" else
             f"{PENCERE} dk'lık mum {'+' if yon == 'buy' else '-'}%{hr:.1f} gövde, mum kapanınca yeni mumun başında giriş" if MOD == "mum"
             else f"son {PENCERE} dk {'+' if yon == 'buy' else '-'}%{hr:.1f} hareket (momentum)")
    haber(f"{'🟢 LONG' if yon == 'buy' else '🔴 SHORT'} {sym.split(':')[0]} {lev}x izole, {mj}$\n"
          f"Sebep: {sebep}\n"
          f"Giriş ≈ {son:g} | Stop ≈ {sl_fiyat(yon, son, float(adet), cs, sl):g} (−{sl}${not_})\n"
          f"Kâr al: {('+'+format(tp_oran*mj,'.2f')+'$ (borsada)') if tp_oran else 'kademeli kilit'}{izm}{kd}{tp_not}")

def yonet():
    pos = [p for p in ex.fetch_positions() if p.get("contracts")]
    var = {p["symbol"] for p in pos}
    for s in [s for s in acik if s not in var]:      # dışarıda (elle/likidasyon) kapanan
        borsa_stop_iptal(s, acik[s].get("sid")); logla(s, "?", acik[s].get("son", 0.0), "BORSADA KAPANDI (TP/stop/elle)", acik[s].get("zirve", 0.0)); haber(f"ℹ️ {s.split(':')[0]} borsada kapandı, son görülen PnL≈{acik[s].get('son', 0.0):+.2f}$"); acik.pop(s); yasak[s] = time.time() + BEKLE * 60   # borsada kapananı da bekleme listesine al
    for p in pos:
        sym = p["symbol"]; pnl = p["unrealizedPnl"] or 0.0
        if sym not in acik:                          # bot kapanıp açılınca / elle açılan: devral
            mj = float(p.get("initialMargin") or MARJIN)
            acik[sym] = {"zirve": max(pnl, 0.0), "mj": mj, "sl": round(A["sl"] * mj, 2), "son": pnl}
        k = acik[sym]; k["son"] = pnl; k["zirve"] = max(k["zirve"], pnl)
        if A["kademe"]:                                  # satış yok: kademe aşılınca kilit yükselir, son hedefte hepsi satılır
            lv = k.get("lv") or A["lv"]; k["lv"] = lv; a_ = k.get("asama", 0); mj_ = k["mj"]
            try: lev_ = float(p.get("leverage") or 20)
            except Exception: lev_ = 20.0
            kl1 = 0.30 * mj_ + 0.0012 * mj_ * lev_ + 0.03 * mj_        # net 0.30$ kalsın: + borsa ücreti (giriş+çıkış) + kayma payı
            e0 = max(lv[0] * mj_, kl1 + 0.05 * mj_)                     # 1. basamak, kilidin en az 0.05$ üstünde olmalı
            while a_ < len(lv) and pnl >= (e0 if a_ == 0 else lv[a_] * mj_): a_ += 1
            if a_ != k.get("asama", 0):
                k["asama"] = a_; k["kilit"] = kl1 if a_ == 1 else (e0 if a_ == 2 else lv[a_ - 2] * mj_) * 0.95
                haber(f"🔒 {sym.split(':')[0]} kademe {a_}/{len(lv)} aşıldı → stop yukarı çekildi: +{k['kilit']:.2f}$ (pnl {pnl:+.2f}$)")
            if a_ >= 2 and k.get("kilit") is not None:   # 2. basamaktan sonra kilit zirvenin en az %65'i: kârın çoğunu geri verme
                k["kilit"] = max(k["kilit"], 0.65 * k["zirve"])
            if a_ >= len(lv) and len(lv) > 1:   # son basamak aşıldı: satış yok, zirveyi bir basamak geriden izle
                k["kilit"] = max(k.get("kilit") or 0, k["zirve"] - (lv[-1] - lv[-2]) * k["mj"])
            if A.get("bs") and k.get("kilit") is not None and k["kilit"] >= k.get("bsk", -9) + 0.05 * k["mj"]:
                borsa_stop(sym, p, k, k["kilit"]); k["bsk"] = k["kilit"]      # başarısız olsa da aynı seviyeyi tekrar deneme (mesaj yağmuru olmasın)
            if k.get("kilit") is not None and pnl <= k["kilit"]: kapat(sym, p, "KADEME KİLİDİ")
            elif pnl <= -k["sl"] and k.get("kilit") is None: kapat(sym, p, "STOP")
        elif A["tp"] > 0 and pnl >= A["tp"] * k["mj"]: kapat(sym, p, "KÂR AL")
        elif pnl <= -k["sl"]: kapat(sym, p, "STOP")
        elif A["iz"] and k["zirve"] >= TRAIL_ON * k["mj"] and pnl <= k["zirve"] - TRAIL_GERI * k["mj"]: kapat(sym, p, "İZ SÜREN")
    kaydet()
    return len(acik)

bar = {}   # coin -> (mum_no, mum_açılış_fiyatı)
def mum_sinyal(s, son, simdi):
    """Her PENCERE dakikalık mum kapandığında önceki mumun açılış->kapanış gövdesine bak. Döner: (yon, yüzde) ya da None."""
    bid = int(simdi // (PENCERE * 60)); o = bar.get(s); sonuc = None
    if o is None or o[0] != bid:
        if o is not None and o[0] == bid - 1 and o[1]:
            mv = son / o[1] - 1
            if mv >= HAREKET / 100: sonuc = ("buy", mv * 100)
            elif mv <= -HAREKET / 100: sonuc = ("sell", -mv * 100)
        bar[s] = (bid, son)
    return sonuc

fitil_bid = [0]
def mum_ok(c, d, minr):
    """c = [ts, açılış, yüksek, düşük, kapanış, hacim]. d=1: altta fitil + yeşil, d=-1: üstte fitil + kırmızı."""
    o, h, l, cl = c[1], c[2], c[3], c[4]; r = h - l
    if not o or r <= 0 or r / o < minr: return False
    if d == 1: return cl > o and (min(o, cl) - l) / r >= FITIL
    return cl < o and (h - max(o, cl)) / r >= FITIL

def fitil_yon(s):
    """15 dk -> 1 saat -> 4 saat son KAPANMIŞ mumların hepsi aynı yönde fitil bırakmış mı. Döner: 'buy'/'sell'/None."""
    k15 = ex.fetch_ohlcv(s, "15m", limit=3)
    if len(k15) < 3: return None
    d = 1 if mum_ok(k15[-2], 1, 0.005) else (-1 if mum_ok(k15[-2], -1, 0.005) else 0)
    if not d: return None
    for tf, minr in (("1h", 0.01), ("4h", 0.02)):
        k = ex.fetch_ohlcv(s, tf, limit=3)
        if len(k) < 3 or not mum_ok(k[-2], d, minr): return None
    return "buy" if d == 1 else "sell"

def mum15_yon(s):
    """Son 3 KAPANMIŞ 15 dk mum: c0 (en yeni), c1, c2. c0 aralığı >= MUM15_ARALIK % ve yutan ya da sabah/akşam yıldızı ise (yon, aralık%) döner."""
    k = ex.fetch_ohlcv(s, "15m", limit=4)
    if len(k) < 4: return None
    c2, c1, c0 = k[-4], k[-3], k[-2]
    o0, h0, l0, x0 = c0[1], c0[2], c0[3], c0[4]
    if not o0 or (h0 - l0) / o0 * 100 < MUM15_ARALIK: return None
    for d in (1, -1):
        a0, b0, a1, b1, a2, b2 = (c0[1], c0[4], c1[1], c1[4], c2[1], c2[4]) if d == 1 else (-c0[1], -c0[4], -c1[1], -c1[4], -c2[1], -c2[4])
        yutan = b0 > a0 and b1 < a1 and a0 <= b1 and b0 >= a1 and abs(b0 - a0) > abs(b1 - a1)
        yildiz = b2 < a2 and abs(b1 - a1) < 0.3 * (c1[2] - c1[3] + 1e-12) and b0 > a0 and b0 > (a2 + b2) / 2
        if yutan or yildiz: return ("buy" if d == 1 else "sell", (h0 - l0) / o0 * 100)
    return None

def tara():
    if A["calis"] and A["gunluk"] > 0 and gun_toplam() <= -A["gunluk"]:   # günlük zarar limiti: otomatik girişi durdur
        A["calis"] = False; kaydet()
        haber(f"🛑 Günlük zarar limiti doldu (≈{gun_toplam():+.2f}$ ≤ −{A['gunluk']}$). Otomatik giriş durdu, açık işlemler yönetilmeye devam ediyor. Yeniden başlatmak için /panel.")
    n = int(PENCERE * 60 / 10)
    tk = ex.fetch_tickers()
    top = sorted((t for s, t in tk.items() if s.endswith(":USDT") and t.get("last")), key=lambda t: -(t.get("quoteVolume") or 0))[:COIN_SAYI]
    if MOD in ("fitil", "mum15"):
        simdi = time.time(); bid = int(simdi // 900)
        if fitil_bid[0] != bid and simdi - bid * 900 < 150 and A["calis"]:   # her 15 dk mum kapanışında bir kez tara (ilk 150 sn içinde)
            fitil_bid[0] = bid; adet = 0
            for t in top:
                s, son = t["symbol"], t["last"]; b = s.split("/")[0].lstrip("0123456789")
                if b in A["haric"] or (A.get("hk", True) and b in HISSE) or s in acik or time.time() < yasak.get(s, 0): continue
                if len(acik) >= A["max_pos"]: break
                try:
                    if MOD == "mum15":
                        sg = mum15_yon(s)
                        if sg: ac(s, sg[0], son, sg[1]); adet += 1
                    else:
                        yon = fitil_yon(s)
                        if yon: ac(s, yon, son, 0.0); adet += 1
                except Exception as e: print("hata fitil", s, e, flush=True)
            print(f"{MOD} taraması bitti: {adet} giriş, {time.time()-simdi:.0f} sn", flush=True)
        return
    for t in top:
        s, son = t["symbol"], t["last"]
        if s.split("/")[0].lstrip("0123456789") in A["haric"]: continue   # hariç tutulan eski/yavaş coinler
        if A.get("hk", True) and s.split("/")[0].lstrip("0123456789") in HISSE: continue   # hisse/ETF sembolleri kapalı
        if MOD in ("fitil", "mum15"):
            continue
        if MOD == "mum":
            sg = mum_sinyal(s, son, time.time())
            if sg and s not in acik and time.time() >= yasak.get(s, 0) and len(acik) < A['max_pos'] and A['calis']: ac(s, sg[0], son, sg[1])
            continue
        h = fiyat.setdefault(s, collections.deque(maxlen=n)); h.append(son)
        if len(h) < n or s in acik or time.time() < yasak.get(s, 0) or len(acik) >= A['max_pos'] or not A['calis']: continue
        lo, hi = min(h), max(h)
        if son >= lo * (1 + HAREKET / 100) and son >= hi * 0.997: ac(s, "buy", son, (son / lo - 1) * 100)
        elif son <= hi * (1 - HAREKET / 100) and son <= lo * 1.003: ac(s, "sell", son, (1 - son / hi) * 100)

POZ = {}   # düğme numarası -> sembol
B = types.InlineKeyboardButton
def sec(liste, mevcut, onek, fmt):   # seçenek satırı, seçili olan ✅
    return [B(("✅ " if mevcut == v else "") + fmt(v), callback_data=f"{onek}:{v}") for v in liste]

def pozlar():
    ps = [p for p in ex.fetch_positions() if p.get("contracts")]
    POZ.clear(); POZ.update({n: p["symbol"] for n, p in enumerate(ps)}); return ps

def gun_toplam():
    bug = time.strftime("%Y-%m-%d", time.localtime())
    return sum(g["pnl"] for g in gecmis if time.strftime("%Y-%m-%d", time.localtime(g["t"])) == bug)

def ekran(e):
    """Döner: (metin, klavye). Ekranlar: ana, poz, gec, ayar, ozet, hep"""
    k = types.InlineKeyboardMarkup(); geri = B("⬅️ Menüye Dön", callback_data="ana")
    if e == "poz":
        ps = pozlar(); sat = []
        for n, p in enumerate(ps):
            a = acik.get(p["symbol"], {}); g = p.get("entryPrice") or 0
            sat.append(f"{n+1}) {'🟢' if p['side']=='long' else '🔴'} {p['symbol'].split(':')[0]} {p['leverage'] or '?'}x  {p['unrealizedPnl']:+.2f}$\n"
                       f"   giriş {g:g} | stop {sl_fiyat(p['side'], g, p['contracts'], p.get('contractSize') or 1, a.get('sl', 0)):g} (−{a.get('sl', 0)}$)")
            k.row(B(f"❌ {n+1}", callback_data=f"k{n}"), B("lev−", callback_data=f"a{n}"), B("lev+", callback_data=f"b{n}"),
                  B("SL−", callback_data=f"c{n}"), B("SL+", callback_data=f"d{n}"))
        k.row(geri, B("🔄 Yenile", callback_data="poz"))
        return "📋 Pozisyonlar\n\n" + ("\n".join(sat) or "pozisyon yok"), k
    if e == "gec":
        k.row(geri); son = gecmis[-15:][::-1]
        return ("📜 Son işlemler (✓ = borsadan gerçek net, komisyon dahil; ≈ = tahmin)\n" + ("\n".join(f"{time.strftime('%d.%m %H:%M', time.localtime(g['t']))} {g['s']} {g['y']} {g['pnl']:+.2f}$ {'✓' if g.get('g') == 1 else '≈'} (zirve {g.get('z', 0):+.2f}) {g['n']}" for g in son) or "henüz yok")), k
    if e == "ozet":
        k.row(geri); n = len(gecmis); w = sum(1 for g in gecmis if g["pnl"] > 0)
        return (f"📊 Özet\nBakiye {bakiye():.2f}$\nBugün ≈{gun_toplam():+.2f}$\nToplam ≈{sum(g['pnl'] for g in gecmis):+.2f}$ ({n} işlem, %{(w/n*100 if n else 0):.0f} kazanç)"), k
    if e == "ayar":
        k.row(*sec((1, 2, 3, 5), A["marjin"], "mj", lambda v: f"${v}"))
        k.row(*sec((50, 60, 70, 80), int(A["sl"] * 100), "sl", lambda v: f"SL %{v}"))
        k.row(*sec((0, 0.3, 0.35, 0.5, 1.0), A["tp"], "tp", lambda v: "TP yok" if not v else f"TP %{int(v*100)}"))
        k.row(B(f"🚫 Hariç coinler ({len(A['haric'])}) → /haric", callback_data="ayar"))
        k.row(*sec((0.5, 1.0, 2.0, 0), A["gunluk"], "gl", lambda v: f"Günlük −{v}$" if v else "Limit yok"))
        k.row(B("Kademeli kilit " + ("✅ AÇIK (kapat)" if A["kademe"] else "❌ KAPALI (aç)"), callback_data="kd"))
        k.row(B("Hisse senetleri " + ("❌ KAPALI (aç)" if A.get("hk", True) else "✅ AÇIK (kapat)"), callback_data="hk"))
        k.row(B("Borsa stop " + ("✅ AÇIK (kapat)" if A.get("bs") else "❌ KAPALI (aç) [deneme]"), callback_data="bs"))
        k.row(*sec(("42,50,75,100", "35,60,100,150", "50,100,150,250"), ",".join(str(int(x * 100)) for x in A["lv"]), "lvl", lambda v: v))
        k.row(B("İz süren " + ("✅ AÇIK (kapat)" if A["iz"] else "❌ KAPALI (aç)"), callback_data="iz"))
        k.row(B("Oto-büyüme " + ("✅ AÇIK (kapat)" if A["oto"] else "❌ KAPALI (aç)"), callback_data="oto"))
        k.row(geri)
        return f"⚙️ Ayarlar\nMarjin/işlem: {A['marjin']}$ ({'oto %'+str(int(A['oran']*100)) if A['oto'] else 'sabit'})\nStop: marjinin %{A['sl']*100:.0f}'i (likidasyona göre daralır)\nGünlük zarar limiti: {('−'+str(A['gunluk'])+'$') if A['gunluk'] else 'yok'}\nKademeli kilit: {('AÇIK ' + ' → '.join('+%' + str(int(x * 100)) for x in A['lv']) + ' (her basamakta stop bir geri kilitlenir, satış yok)') if A['kademe'] else 'KAPALI'}\nKâr al (tek TP): {'yok' if not A['tp'] else '+%'+str(int(A['tp']*100))+' (borsada durur)'}\nİz süren: {'AÇIK (+%'+str(int(TRAIL_ON*100))+' başlar, %'+str(int(TRAIL_GERI*100))+' geri verirse kapatır)' if A['iz'] else 'KAPALI (tek TP)'}", k
    if e == "hep":
        k.row(B("✅ Evet, HEPSİNİ kapat", callback_data="hepE"), B("❌ Vazgeç", callback_data="ana"))
        return "🚨 Tüm pozisyonlar kapatılsın mı? (otomatik giriş de durur)", k
    # ana
    n = len(pozlar())
    k.row(B("📋 Pozisyonlar", callback_data="poz"), B("📜 Geçmiş", callback_data="gec"))
    k.row(B("🛑 Otomatik Girişi Durdur" if A["calis"] else "▶️ Otomatik Girişi Başlat", callback_data="tog"))
    k.row(B("📊 Özet", callback_data="ozet"), B("⚙️ Ayarlar", callback_data="ayar"))
    k.row(*sec((10, 20, 50, 75, 125), A["lev"], "lev", lambda v: f"{v}x"))
    k.row(*sec((1, 2, 3, 5, 6), A["max_pos"], "lim", lambda v: f"{v} işlem"))
    k.row(B("🚨 Tümünü Kapat", callback_data="hep")); k.row(B("🔄 Yenile", callback_data="ana"))
    return (f"{'▶️ OTOMATİK AÇIK' if A['calis'] else '⏹ DURDU'} | {VERSIYON} | Bakiye {bakiye():.2f}$ | Bugün ≈{gun_toplam():+.2f}$\n"
            f"Pozisyon {n}/{A['max_pos']} | Marjin {marjin():.1f}$ | kaldıraç tavanı {A['lev']}x"), k

@bot.message_handler(commands=["panel", "start", "durum", "gecmis"])
def pn(m):
    if m.chat.id != CHAT: return
    t, k = ekran("gec" if m.text.startswith("/gecmis") else "ana"); bot.send_message(CHAT, t, reply_markup=k)

def kaldirac_toplu(hedef):
    """Tüm USDT-M kontratlarda kaldıracı hedefe ayarla; kabul etmeyenlerde borsanın izin verdiği en yükseği bul."""
    syms = [x for x, mk in ex.markets.items() if mk.get("swap") and mk.get("quote") == "USDT" and mk.get("active", True)]
    tam, dusuk, basarisiz, hatalar = 0, 0, [], {}
    for n, x in enumerate(syms):
        son = None
        for l in [l for l in LADDER if l <= hedef]:
            ok, g, h = kaldirac_ayarla(x, l, "buy")
            if ok and (g is None or abs(g - l) < 0.5):
                son = l; kaldirac_ayarla(x, l, "sell"); break
            if h: hatalar[h[:90]] = hatalar.get(h[:90], 0) + 1
        if son: lev_cap[x] = son; tam += son == hedef; dusuk += son != hedef
        else: basarisiz.append(x.split("/")[0])
        if n and n % 150 == 0: bot.send_message(CHAT, f"… {n}/{len(syms)}")
    kaydet()
    dus = sorted(((v, k.split("/")[0]) for k, v in lev_cap.items() if v < hedef))
    bot.send_message(CHAT, f"✅ Kaldıraç ayarı bitti (hedef {hedef}x)\n{tam} kontratta {hedef}x tuttu\n{dusuk} kontrat {hedef}x kabul etmedi (en yüksek kabul edilen kaydedildi)\n"
                     f"{len(basarisiz)} kontratta hiç ayarlanamadı\n" + ("\nDüşük olanlardan örnek: " + ", ".join(f"{k} {v}x" for v, k in dus[:15]) if dus else "")
                     + ("\n\nHatalar:\n" + "\n".join(f"{c}× {k}" for k, c in list(hatalar.items())[:4]) if hatalar else ""))

@bot.message_handler(commands=["kaldirac"])
def kaldirac_kmd(m):   # /kaldirac 20  -> tüm coinlerde 20x'e ayarla (izin verilmeyenlerde en yükseği)
    if m.chat.id != CHAT: return
    a = m.text.split(); hedef = int(a[1]) if len(a) > 1 and a[1].isdigit() else 20
    bot.send_message(CHAT, f"⏳ Tüm USDT-M kontratlarda {hedef}x ayarlanıyor, birkaç dakika sürebilir…")
    threading.Thread(target=kaldirac_toplu, args=(hedef,), daemon=True).start()

@bot.message_handler(commands=["haric"])
def haric(m):   # /haric  |  /haric ekle PEPE FIL  |  /haric sil PEPE
    if m.chat.id != CHAT: return
    a = m.text.split()[1:]
    if len(a) > 1 and a[0] in ("ekle", "sil"):
        for x in a[1:]:
            x = x.upper().replace("USDT", "").lstrip("0123456789")
            if a[0] == "ekle" and x not in A["haric"]: A["haric"].append(x)
            if a[0] == "sil" and x in A["haric"]: A["haric"].remove(x)
        kaydet()
    bot.send_message(CHAT, "🚫 Hariç tutulan coinler (bot bunlara girmez):\n" + " ".join(sorted(A["haric"])) + "\n\nEkle: /haric ekle PEPE FIL\nÇıkar: /haric sil PEPE")

def pozisyon(n):
    sym = POZ.get(n)
    return sym, next((p for p in ex.fetch_positions() if p["symbol"] == sym and p.get("contracts")), None)

@bot.callback_query_handler(func=lambda c: True)
def cb(c):
    if c.message.chat.id != CHAT: return
    d, uyari, e = c.data, "", "ana"
    try:
        if d in ("poz", "gec", "ozet", "ayar", "hep"): e = d
        elif d[0] in "kabcd" and d[1:].isdigit():
            e = "poz"; sym, p = pozisyon(int(d[1:]))
            if not p: uyari = "pozisyon yok, yenile"
            elif d[0] == "k": kapat(sym, p, "MANUEL")
            elif d[0] in "ab":
                yeni = max(1, int(p["leverage"] or 1) + (-5 if d[0] == "a" else 5))
                ex.set_leverage(yeni, sym, params={"marginMode": "isolated", "holdSide": p["side"]}); uyari = f"{yeni}x"
            else: acik[sym]["sl"] = max(0.1, round(acik[sym]["sl"] + (-0.1 if d[0] == "c" else 0.1), 2))
        elif d == "tog": A["calis"] = not A["calis"]
        elif d == "iz": A["iz"] = not A["iz"]; e = "ayar"
        elif d == "oto": A["oto"] = not A["oto"]; e = "ayar"
        elif d.startswith("mj:"): A["marjin"] = float(d[3:]); e = "ayar"
        elif d.startswith("gl:"): A["gunluk"] = float(d[3:]); e = "ayar"
        elif d == "kd": A["kademe"] = not A["kademe"]; e = "ayar"
        elif d == "bs": A["bs"] = not A.get("bs"); e = "ayar"
        elif d == "hk": A["hk"] = not A.get("hk", True); e = "ayar"
        elif d.startswith("lvl:"): A["lv"] = [int(x) / 100 for x in d[4:].split(",")]; e = "ayar"
        elif d.startswith("tp:"): A["tp"] = float(d[3:]); e = "ayar"
        elif d.startswith("sl:"): A["sl"] = int(d[3:]) / 100; e = "ayar"
        elif d.startswith("lev:"): A["lev"] = int(d[4:])
        elif d.startswith("lim:"): A["max_pos"] = int(d[4:])
        elif d == "hepE":
            A["calis"] = False
            for p in ex.fetch_positions():
                if p.get("contracts"): kapat(p["symbol"], p, "MANUEL")
    except Exception as x: uyari = str(x)[:150]
    kaydet()
    try:
        t, k = ekran(e); bot.edit_message_text(t, c.message.chat.id, c.message.message_id, reply_markup=k)
    except Exception: pass
    bot.answer_callback_query(c.id, uyari)

if __name__ == "__main__":
    ex.load_markets()
    threading.Thread(target=lambda: bot.infinity_polling(skip_pending=True), daemon=True).start()
    haber(f"Kısa bot {VERSIYON} hazır: {marjin()}$ izole, max {A['max_pos']}, ≤{A['lev']}x, SL %{A['sl']*100:.0f}, oto-büyüme {A['oto']}  → /panel")
    def izle():          # pozisyon takibi ayrı ve hızlı (2 sn): stop/iz süren gecikmesin
        while True:
            try: yonet(); duzelt()
            except Exception as e: print("hata yonet", e, flush=True)
            time.sleep(2)
    threading.Thread(target=izle, daemon=True).start()
    while True:          # tarama / giriş (10 sn)
        try: tara()
        except Exception as e: print("hata tara", e, flush=True)
        time.sleep(10)
