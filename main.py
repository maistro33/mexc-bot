# GHOST KISA BOT  —  temiz yeniden yazım
# Strateji (tek ve basit): 5 dk'lık mum gövdesi >= EŞİK % ise, mum kapanınca yeni mumun başında gir.
#   TERSİNE : yükselene SAT (short), düşene AL (long)      [varsayılan]
#   TAKİP   : yükselene AL (long),  düşene SAT (short)
# Çıkış: kademeli kilit (+0.42 → +0.50 → +0.75 → +1.00$), BORSADA stop (açılışta hemen), satış yok.
#
# SÜRÜM GEÇMİŞİ (her değişiklikte VERSIYON ve buraya bir satır eklenir)
# v4.0 09.10 22:50  Sıfırdan temiz yazım: tek strateji çekirdeği (mum gövdesi, TERSİNE/TAKİP panelden), her 5 dk'da tek fiyat okuması,
#                   açılışta zorunlu borsa stopu, kaldıraç doğrulama + fazlayı küçültme, günlük limit artık kalıcı kilit DEĞİL
#                   (limit değişince/yeni günde bot otomatik devam eder), yeni panel, saat dilimi Stockholm
# v4.1 09.10 22:45  Yeni mod "ARALIK": coinin son N saatlik (varsayılan 4s) aralığında dipteyse AL, tepedeyse SAT (yatay gezen coinler; geniş/trend
#                   aralıklar atlanır). Panelden seçilir, 5 dk gövde modları duruyor.
VERSIYON = "v4.1 (09.10 22:45)"

import os, time, json, threading, datetime as dt
import ccxt, telebot
from telebot import types

E = os.getenv
MARJIN    = float(E("MARJIN", "1"))          # USDT / işlem
MAX_POS   = int(E("MAX_POS", "3"))
LEV_TAVAN = int(E("LEV_TAVAN", "20"))        # coinin izin verdiği en yüksek kaldıraç denenir (bu sayıyı geçmez)
SL_ORAN   = float(E("SL_ORAN", "0.8"))       # zarar stopu: marjinin bu oranı
COIN_SAYI = int(E("COIN_SAYI", "150"))       # hacme göre ilk N coin izlenir
MIN_SL_PCT = float(E("MIN_SL_PCT", "1.5"))   # stop fiyattan en az bu % uzak olmalı; değilse kaldıraç düşürülür
CHAT      = int(E("MY_CHAT_ID", "0"))
BAR       = 300                              # mum süresi (sn): 5 dakika

try:
    from zoneinfo import ZoneInfo
    TZ = ZoneInfo(E("TZ_ADI", "Europe/Stockholm")); dt.datetime.now(TZ)
except Exception:
    TZ = dt.timezone(dt.timedelta(hours=2))
def gun(t=None): return dt.datetime.fromtimestamp(t or time.time(), TZ).strftime("%Y-%m-%d")
def saat(t): return dt.datetime.fromtimestamp(t, TZ).strftime("%d.%m %H:%M")

DOSYA = "/data/ayar.json" if os.path.isdir("/data") else "ayar.json"
HARIC = "BTC ETH XRP ADA DOGE SOL BNB LTC BCH TRX LINK DOT AVAX XLM ETC ATOM SHIB PEPE".split()
HISSE = set("PLTR MRNA MSTU AAOI AXTI ORCL SOXL CRWV MUU TSLA NVDA AAPL MSFT AMZN GOOGL AMD INTC MSTR HOOD SPY QQQ NFLX BABA SMCI AVGO TSM MU PYPL UBER IONQ RGTI SOFI RIVN NIO".split())
LADDER = (125, 100, 75, 50, 30, 25, 20, 15, 10, 5, 3, 2)
A = {"v": 3, "calis": True, "mod": "ters", "esik": 5.0, "marjin": MARJIN, "max_pos": MAX_POS, "lev": LEV_TAVAN, "sl": SL_ORAN,
     "gunluk": 3.0, "bekle": 15, "pen": 48, "uc": 10, "gen": 8.0, "lv": [0.42, 0.50, 0.75, 1.00], "hk": True, "haric": list(HARIC)}
lev_cap = {}                 # coin -> borsanın kabul ettiği en yüksek kaldıraç
acik, yasak, gecmis = {}, {}, []
KIL = threading.RLock()
try:
    d = json.load(open(DOSYA)); a0 = d.get("A", {})
    if a0.get("v") == 3: A.update(a0)
    elif a0.get("haric"): A["haric"] = a0["haric"]          # eski sürümden sadece hariç listesini al
    acik.update(d.get("acik", {})); gecmis.extend(d.get("gecmis", [])); lev_cap.update(d.get("cap", {}))
except Exception: pass
def kaydet():
    try: json.dump({"A": A, "acik": acik, "gecmis": gecmis[-400:], "cap": lev_cap}, open(DOSYA, "w"))
    except Exception: pass

ex = ccxt.bitget({"apiKey": E("BITGET_API"), "secret": E("BITGET_SEC"), "password": E("BITGET_PASS"),
                  "options": {"defaultType": "swap"}, "enableRateLimit": True, "timeout": 30000})
bot = telebot.TeleBot(E("TELE_TOKEN", "x"), threaded=False)

def bakiye():
    try: return float(ex.fetch_balance()["USDT"]["total"])
    except Exception: return 0.0

def haber(m):
    print(m, flush=True)
    try: bot.send_message(CHAT, m)
    except Exception: pass

def temiz(s): return s.split("/")[0].lstrip("0123456789")

# ───────────────────────── kayıt / gerçek kâr-zarar ─────────────────────────
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

def duzelt():   # kapanıştan ~20 sn sonra tahmini PnL'yi borsanın gerçek (komisyonlu) rakamıyla değiştir
    for g in gecmis[-40:]:
        if g.get("g", 1) == 0 and time.time() - g["t"] > 20 and time.time() - g.get("d", 0) > 15:
            g["d"] = time.time(); v = gercek_pnl(g.get("id", ""), g["t"])
            if v is not None: g["pnl"], g["g"] = round(v, 3), 1
            elif time.time() - g["t"] > 900: g["g"] = 2
    kaydet()

def gun_toplam():
    b = gun()
    return sum(g["pnl"] for g in gecmis if gun(g["t"]) == b)

def limit_doldu():
    """Günlük zarar limiti dolu mu? (kalıcı kilit YOK: limit değişince ya da gün dönünce otomatik düzelir)"""
    return A["gunluk"] > 0 and gun_toplam() <= -A["gunluk"]

def durum():
    if not A["calis"]: return "⏹ DURDU (elle)"
    if limit_doldu(): return "⛔ LİMİT DOLDU (yeni giriş yok)"
    return "▶️ ÇALIŞIYOR"

# ───────────────────────── borsa işlemleri ─────────────────────────
def borsa_stop_iptal(sym, sid):
    if not sid: return
    for prm in ({"trigger": True}, {"stop": True}, {}):
        try: ex.cancel_order(sid, sym, prm); return
        except Exception: pass

def borsa_stop(sym, p, k, kilit):
    """Borsada stop-market (reduce-only). kilit: kâr kilidi (+) ya da zarar stopu (−), $ olarak. Döner: başarılı mı."""
    try:
        qty = float(p["contracts"]); cs = ex.market(sym).get("contractSize") or 1
        gir = float(p.get("entryPrice")); d = kilit / (qty * cs); uz = p["side"] == "long"
        fy = ex.price_to_precision(sym, gir + d if uz else gir - d)
        eski = k.get("sid")
        o = ex.create_order(sym, "market", "sell" if uz else "buy", qty, params={"stopLossPrice": fy, "reduceOnly": True, "marginMode": "isolated"})
        k["sid"] = o.get("id") or (o.get("info") or {}).get("orderId")
        if eski: borsa_stop_iptal(sym, eski)
        return fy
    except Exception as e:
        haber(f"⚠️ {sym.split(':')[0]} borsa stopu konamadı, bot takip ediyor: {str(e)[:110]}")
        return None

def kapat(sym, p, neden):
    yon = "sell" if p["side"] == "long" else "buy"
    ex.create_order(sym, "market", yon, p["contracts"], params={"reduceOnly": True, "marginMode": "isolated"})
    yasak[sym] = time.time() + A["bekle"] * 60
    kk = acik.pop(sym, {}); borsa_stop_iptal(sym, kk.get("sid")); z = kk.get("zirve", 0.0)
    logla(sym, p["side"], p["unrealizedPnl"], neden, z)
    haber(f"{'✅' if p['unrealizedPnl'] > 0 else '❌'} {sym.split(':')[0]} kapandı: {neden}\nPnL ≈ {p['unrealizedPnl']:+.2f}$ (gördüğü zirve {z:+.2f}$)")

def sl_fiyat(yon, giris, adet, cs, usd):
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

def ac(sym, yon, son, pct):
    """Pozisyon aç. Döner: True/False."""
    ad = sym.split(":")[0]
    with KIL:
        if sym in acik or len(acik) >= A["max_pos"]: return False
    mj = A["marjin"]; lev, hata = 0, ""
    for l in [l for l in LADDER if l <= min(A["lev"], lev_cap.get(sym, 999)) and 70 * (1 / l - 0.0105) >= MIN_SL_PCT]:
        ok, g, h = kaldirac_ayarla(sym, l, yon); hata = h or hata
        if ok and (g is None or abs(g - l) < 0.5): lev = l; break
        if ok and g is not None and g < l: lev_cap[sym] = int(g)
    if not lev:
        yasak[sym] = time.time() + 6 * 3600
        if hata: haber(f"⚠️ {ad} kaldıraç ayarlanamadı, atlandı: {hata}")
        return False
    m = ex.market(sym); cs = m.get("contractSize") or 1
    adet = ex.amount_to_precision(sym, mj * lev / son / cs)
    if float(adet) * son < 5.2: yasak[sym] = time.time() + 6 * 3600; return False
    try:
        ex.create_order(sym, "market", yon, float(adet), params={"marginMode": "isolated"})
    except Exception as e:
        if "40797" in str(e):      # borsa bu kaldıracı kabul etmiyor: bir basamak düşür, sonraki sinyalde dene
            alt = [l for l in LADDER if l < lev]
            if alt: lev_cap[sym] = alt[0]; yasak[sym] = time.time() + 20; haber(f"ℹ️ {ad} {lev}x kabul edilmedi, sonraki sinyalde {alt[0]}x denenecek"); return False
        yasak[sym] = time.time() + 3600; haber(f"⚠️ {ad} açılamadı: {str(e)[:120]}"); return False
    p = None
    for _ in range(4):                   # pozisyonu borsadan doğrula
        try: p = next(x for x in ex.fetch_positions([sym]) if x.get("contracts")); break
        except Exception: time.sleep(0.7)
    if not p:
        haber(f"🚨 {ad}: emir gitti ama pozisyon görünmedi. Bitget'ten kontrol et!"); yasak[sym] = time.time() + 3600; return False
    gl = float(p.get("leverage") or lev)
    if abs(gl - lev) > 0.5 or float(p.get("initialMargin") or 0) > mj * 1.5:     # kaldıraç uyuşmadı
        kalan = float(ex.amount_to_precision(sym, float(p["contracts"]) * gl / lev)) if 0 < gl < lev else 0.0
        fazla = float(ex.amount_to_precision(sym, float(p["contracts"]) - kalan)) if kalan else 0.0
        try:
            if kalan and fazla > 0 and kalan * son >= 5.2:     # fazlayı küçült: marjin kalsın, işleme devam
                ex.create_order(sym, "market", "sell" if p["side"] == "long" else "buy", fazla, params={"reduceOnly": True, "marginMode": "isolated"})
                lev_cap[sym] = int(gl); lev = int(gl); adet = ex.amount_to_precision(sym, kalan)
                p = next(x for x in ex.fetch_positions([sym]) if x.get("contracts"))
                haber(f"ℹ️ {ad}: {gl:g}x uygulandı, pozisyon küçültüldü, devam")
            else:
                raise RuntimeError("küçültülemedi")
        except Exception:
            try: p = next(x for x in ex.fetch_positions([sym]) if x.get("contracts")); kapat(sym, p, "KALDIRAÇ UYUŞMADI")
            except Exception: pass
            yasak[sym] = time.time() + 6 * 3600; haber(f"🚨 {ad}: kaldıraç uyuşmadı, pozisyon kapatıldı"); return False
    gir = float(p.get("entryPrice") or son); adet_f = float(p["contracts"])
    sl = round(A["sl"] * mj, 2); not_ = ""
    try:   # stop likidasyondan ÖNCE gelsin: likidasyon uzaklığının %70'ine daralt
        liq = float(p.get("liquidationPrice") or 0)
        if liq and sl / (adet_f * cs) > 0.7 * abs(gir - liq):
            sl = round(0.7 * abs(gir - liq) * adet_f * cs, 3); not_ = " (likidasyona yakın, daraltıldı)"
    except Exception: pass
    with KIL:
        acik[sym] = {"zirve": 0.0, "mj": mj, "sl": sl, "son": 0.0, "t": int(time.time()), "y": p["side"]}; kaydet()
        fy = borsa_stop(sym, p, acik[sym], -min(sl * 1.2, 0.85 * mj))     # ZORUNLU yedek stop: bot düşse bile korur
    ters = A["mod"] == "ters"
    sebep = f"5 dk mum %{pct:.1f} {'yükseldi' if (yon == 'sell') == ters else 'düştü'} → {'TERSİNE' if ters else 'TAKİP'}"
    if A["mod"] == "aralik": sebep = f"{A['pen']*5//60} saatlik aralık (%{pct:.1f} geniş) {'dibinde' if yon == 'buy' else 'tepesinde'} → ARALIK"
    haber(f"{'🟢 LONG' if yon == 'buy' else '🔴 SHORT'} {ad} · {lev}x izole · {mj}$\n"
          f"Sebep: {sebep}\n"
          f"Giriş {gir:g} | Bot stopu ≈ {sl_fiyat(yon, gir, adet_f, cs, sl):g} (−{sl}${not_})\n"
          f"{'🛡 Borsa yedek stopu: ' + str(fy) if fy else '⚠️ Borsa stopu YOK, bot takip ediyor'}\n"
          f"Kâr: kademeli kilit " + " → ".join(f"+{x*mj:.2f}$" for x in A["lv"]))
    return True

def yonet():
    """Açık pozisyonları yönet: kademeli kilit, stop. 2 sn'de bir çalışır."""
    with KIL:
        pos = [p for p in ex.fetch_positions() if p.get("contracts")]
        var = {p["symbol"] for p in pos}
        for s in [s for s in acik if s not in var]:      # dışarıda (borsa stopu/elle/likidasyon) kapanan
            borsa_stop_iptal(s, acik[s].get("sid")); logla(s, acik[s].get("y", "?"), acik[s].get("son", 0.0), "BORSADA KAPANDI", acik[s].get("zirve", 0.0))
            haber(f"ℹ️ {s.split(':')[0]} borsada kapandı (stop/elle), son görülen PnL ≈ {acik[s].get('son', 0.0):+.2f}$"); acik.pop(s); yasak[s] = time.time() + A["bekle"] * 60
        for p in pos:
            sym = p["symbol"]; pnl = p["unrealizedPnl"] or 0.0
            if sym not in acik:                              # elle açılan: devral
                mj = float(p.get("initialMargin") or A["marjin"])
                acik[sym] = {"zirve": max(pnl, 0.0), "mj": mj, "sl": round(A["sl"] * mj, 2), "son": pnl, "t": int(time.time()), "y": p["side"]}
            k = acik[sym]; k["son"] = pnl; k["zirve"] = max(k["zirve"], pnl)
            lv = k.get("lv") or A["lv"]; k["lv"] = lv; a_ = k.get("asama", 0); mj_ = k["mj"]
            try: lev_ = float(p.get("leverage") or 20)
            except Exception: lev_ = 20.0
            kl1 = 0.30 * mj_ + 0.0012 * mj_ * lev_ + 0.03 * mj_        # net ≈0.30$ kalsın: ücret + kayma payı
            e0 = max(lv[0] * mj_, kl1 + 0.05 * mj_)
            while a_ < len(lv) and pnl >= (e0 if a_ == 0 else lv[a_] * mj_): a_ += 1
            if a_ != k.get("asama", 0):
                k["asama"] = a_; k["kilit"] = kl1 if a_ == 1 else (e0 if a_ == 2 else lv[a_ - 2] * mj_) * 0.95
                haber(f"🔒 {sym.split(':')[0]} kademe {a_}/{len(lv)} → stop yukarı çekildi: +{k['kilit']:.2f}$ (pnl {pnl:+.2f}$)")
            if a_ >= 2 and k.get("kilit") is not None: k["kilit"] = max(k["kilit"], 0.65 * k["zirve"])
            if a_ >= len(lv) and len(lv) > 1: k["kilit"] = max(k.get("kilit") or 0, k["zirve"] - (lv[-1] - lv[-2]) * k["mj"])
            if k.get("kilit") is not None and k["kilit"] >= k.get("bsk", -9) + 0.05 * k["mj"]:
                borsa_stop(sym, p, k, k["kilit"]); k["bsk"] = k["kilit"]     # başarısız olsa da aynı seviyeyi tekrar deneme
            if k.get("kilit") is not None and pnl <= k["kilit"]: kapat(sym, p, "KADEME KİLİDİ")
            elif pnl <= -k["sl"] and k.get("kilit") is None: kapat(sym, p, "STOP")
        kaydet()

# ───────────────────────── strateji: 5 dk mum gövdesi ─────────────────────────
acilis = {}            # mum_no -> {sembol: fiyat, "_dogru": bool}
tarama_bid = [0]
hist = {}              # sembol -> son 5 dk kapanışları (aralık modu)
son_tarama = [0.0]
def fiyatlar():
    tk = ex.fetch_tickers()
    top = sorted((t for s, t in tk.items() if s.endswith(":USDT") and t.get("last")), key=lambda t: -(t.get("quoteVolume") or 0))[:COIN_SAYI]
    return {t["symbol"]: float(t["last"]) for t in top}

def uygun(s):
    b = temiz(s)
    if b in A["haric"] or (A["hk"] and b in HISSE): return False
    return s not in acik and time.time() >= yasak.get(s, 0)

def gecmis_yukle(px, butce=40):
    """Aralık modu için eksik 5 dk geçmişini borsadan al (bir kerelik; her bar'da en fazla `butce` sn)."""
    if A["mod"] != "aralik": return
    t0 = time.time()
    for sm in px:
        if sm == "_dogru" or len(hist.get(sm, [])) >= A["pen"] or time.time() - t0 > butce: continue
        try:
            m = ex.fetch_ohlcv(sm, "5m", limit=A["pen"] + 1)[:-1]       # son (açık) mum hariç
            hist[sm] = [float(x[4]) for x in m] + hist.get(sm, [])[-1:]
        except Exception: hist.setdefault(sm, [])

def aralik_girisleri(px):
    aday = []
    for sm, c in px.items():
        h = hist.get(sm, [])
        if sm == "_dogru" or len(h) < A["pen"] * 0.75 or not uygun(sm): continue
        w = h[-A["pen"]:] + [c]; hi, lo = max(w), min(w)
        gen = (hi / lo - 1) * 100
        if gen < 2.0 or gen > A["gen"]: continue                 # çok dar: kâr alanı yok · çok geniş: trend var
        pos = (c - lo) / (hi - lo)
        if pos <= A["uc"] / 100: aday.append((gen, sm, "buy", c, pos))
        elif pos >= 1 - A["uc"] / 100: aday.append((gen, sm, "sell", c, pos))
    for gen, sm, yon, c, pos in sorted(aday, reverse=True):
        with KIL:
            if len(acik) >= A["max_pos"]: break
        try: ac(sm, yon, c, gen)
        except Exception as e: haber(f"⚠️ {sm.split(':')[0]} giriş hatası: {str(e)[:120]}")

def tarama_adimi():
    """Her 5 dk'lık mum başında BİR kez çalışır: tüm fiyatları oku, biten mumun gövdesine bak, sinyal varsa gir."""
    simdi = time.time(); bid = int(simdi // BAR); gec = simdi - bid * BAR
    if tarama_bid[0] == bid: return
    tarama_bid[0] = bid
    px = fiyatlar(); son_tarama[0] = time.time()
    px["_dogru"] = gec < 20          # bu fiyatlar mumun gerçek açılışına yakın mı (restart ortası değil)
    onceki = acilis.get(bid - 1); acilis[bid] = px
    for b in [b for b in acilis if b < bid - 3]: acilis.pop(b)
    for sm, c in px.items():
        if sm != "_dogru": hist.setdefault(sm, []).append(c); del hist[sm][:-300]
    if A["mod"] == "aralik":
        try:
            if px["_dogru"] and gec < 45 and A["calis"] and not limit_doldu(): aralik_girisleri(px)
        finally: gecmis_yukle(px)
        return
    if not onceki or not onceki.get("_dogru") or gec > 45: return       # bir önceki mum güvenilir değilse ya da fiyat bayatsa girme
    if not A["calis"] or limit_doldu(): return
    sinyal = []
    for s, c in px.items():
        o = onceki.get(s)
        if s == "_dogru" or not o or not uygun(s): continue
        mv = (c / o - 1) * 100
        if abs(mv) >= A["esik"]: sinyal.append((abs(mv), s, mv, c))
    for _, s, mv, c in sorted(sinyal, reverse=True):
        with KIL:
            if len(acik) >= A["max_pos"]: break
        yukari = mv > 0
        yon = ("sell" if yukari else "buy") if A["mod"] == "ters" else ("buy" if yukari else "sell")
        try: ac(s, yon, c, abs(mv))
        except Exception as e: haber(f"⚠️ {s.split(':')[0]} giriş hatası: {str(e)[:120]}")

# ───────────────────────── panel ─────────────────────────
B = types.InlineKeyboardButton
POZ = {}
def sec(liste, mevcut, onek, fmt):
    return [B(("✅ " if mevcut == v else "") + fmt(v), callback_data=f"{onek}:{v}") for v in liste]

def pozlar():
    ps = [p for p in ex.fetch_positions() if p.get("contracts")]
    POZ.clear(); POZ.update({n: p["symbol"] for n, p in enumerate(ps)}); return ps

def strateji_yazi():
    if A["mod"] == "aralik": return f"ARALIK: son {A['pen']*5//60} saatlik aralığın alt %{A['uc']}'unda AL, üst %{A['uc']}'unda SAT (aralık %2–%{A['gen']:g})"
    return f"{'TERSİNE (yükselene sat, düşene al)' if A['mod'] == 'ters' else 'TAKİP (yükselene al, düşene sat)'} · 5 dk mum ≥ %{A['esik']:g}"

def ekran(e):
    k = types.InlineKeyboardMarkup(); geri = B("⬅️ Menü", callback_data="ana")
    if e == "poz":
        ps = pozlar(); sat = []
        for n, p in enumerate(ps):
            a = acik.get(p["symbol"], {}); g = p.get("entryPrice") or 0; adet = float(p["contracts"]); cs = p.get("contractSize") or 1
            sl = a.get("kilit") if a.get("kilit") is not None else -a.get("sl", 0)
            sat.append(f"{n+1}) {'🟢 LONG' if p['side'] == 'long' else '🔴 SHORT'} {p['symbol'].split(':')[0]} {p['leverage'] or '?'}x\n"
                       f"   PnL {p['unrealizedPnl']:+.2f}$ (zirve {a.get('zirve', 0):+.2f}$)\n"
                       f"   giriş {g:g} | stop {sl_fiyat(p['side'], g, adet, cs, -sl):g} ({'kilit +' if sl > 0 else ''}{sl:.2f}$)")
            k.row(B(f"❌ {n+1}. kapat", callback_data=f"k{n}"))
        k.row(geri, B("🔄 Yenile", callback_data="poz"))
        return "📋 AÇIK POZİSYONLAR\n\n" + ("\n\n".join(sat) or "Açık pozisyon yok."), k
    if e == "gec":
        k.row(geri, B("🔄 Yenile", callback_data="gec")); son = gecmis[-15:][::-1]
        satirlar = [f"{'✅' if g['pnl'] > 0 else '❌'} {saat(g['t'])} {g['s']} {g['y']} {g['pnl']:+.2f}$ {'✓' if g.get('g') == 1 else '≈'} {g['n']}" for g in son]
        return "📜 SON İŞLEMLER (✓ borsadan net, ≈ tahmin)\n\n" + ("\n".join(satirlar) or "Henüz işlem yok."), k
    if e == "ozet":
        k.row(geri); n = len(gecmis); w = [g["pnl"] for g in gecmis if g["pnl"] > 0]; l = [g["pnl"] for g in gecmis if g["pnl"] <= 0]
        top = sum(g["pnl"] for g in gecmis)
        return (f"📊 ÖZET\n\nBakiye: {bakiye():.2f}$\nBugün: {gun_toplam():+.2f}$\nToplam: {top:+.2f}$ ({n} işlem)\n"
                f"Kazanma: %{(len(w)/n*100 if n else 0):.0f} ({len(w)} kazanç / {len(l)} kayıp)\n"
                f"Ort. kazanç: {(sum(w)/len(w) if w else 0):+.2f}$ | Ort. kayıp: {(sum(l)/len(l) if l else 0):+.2f}$"), k
    if e == "ayar":
        k.row(B("— Strateji —", callback_data="ayar"))
        k.row(B(("✅ " if A["mod"] == "ters" else "") + "Tersine", callback_data="mod:ters"), B(("✅ " if A["mod"] == "takip" else "") + "Takip", callback_data="mod:takip"), B(("✅ " if A["mod"] == "aralik" else "") + "Aralık", callback_data="mod:aralik"))
        k.row(*sec((24, 48, 96), A["pen"], "pn", lambda v: f"Pencere {v*5//60}s"), *sec((5, 10, 15), A["uc"], "uc", lambda v: f"Uç %{v}"))
        k.row(*sec((3, 4, 5, 8), A["esik"], "es", lambda v: f"≥%{v}"))
        k.row(B("— Risk —", callback_data="ayar"))
        k.row(*sec((1, 2, 3, 5), A["marjin"], "mj", lambda v: f"{v}$"))
        k.row(*sec((10, 20, 50), A["lev"], "lev", lambda v: f"{v}x"))
        k.row(*sec((1, 2, 3, 5), A["max_pos"], "lim", lambda v: f"{v} işlem"))
        k.row(*sec((2, 3, 5, 10), A["gunluk"], "gl", lambda v: f"Limit −{v}$") + [B(("✅ " if not A["gunluk"] else "") + "Yok", callback_data="gl:0")])
        k.row(*sec((5, 15, 30), A["bekle"], "bk", lambda v: f"Bekle {v}dk"))
        k.row(B("— Kâr kilidi —", callback_data="ayar"))
        k.row(*sec(("42,50,75,100", "35,60,100,150", "50,100,150,250"), ",".join(str(int(x * 100)) for x in A["lv"]), "lvl", lambda v: v))
        k.row(B("Hisse senetleri " + ("❌ KAPALI (aç)" if A["hk"] else "✅ AÇIK (kapat)"), callback_data="hk"))
        k.row(B(f"🚫 Hariç coinler ({len(A['haric'])}) → /haric", callback_data="ayar"))
        k.row(geri)
        return (f"⚙️ AYARLAR\n\nStrateji: {strateji_yazi()}\nMarjin: {A['marjin']:g}$ · Kaldıraç tavanı {A['lev']}x · Max {A['max_pos']} işlem\n"
                f"Zarar stopu: marjinin %{A['sl']*100:.0f}'i (borsada yedek stop her işlemde)\nGünlük zarar limiti: {('−' + str(A['gunluk']) + '$') if A['gunluk'] else 'yok'} (gün dönünce/değişince kendiliğinden devam)\n"
                f"Kademeli kilit: " + " → ".join("+%" + str(int(x * 100)) for x in A["lv"]) + f"\nKapanan coine tekrar giriş beklemesi: {A['bekle']} dk"), k
    if e == "hep":
        k.row(B("✅ Evet, HEPSİNİ kapat", callback_data="hepE"), B("❌ Vazgeç", callback_data="ana"))
        return "🚨 Tüm pozisyonlar kapatılsın mı? (Otomatik giriş de durur)", k
    n = len(pozlar())
    k.row(B("🛑 DURDUR" if A["calis"] else "▶️ BAŞLAT", callback_data="tog"))
    k.row(B("📋 Pozisyonlar", callback_data="poz"), B("📜 Geçmiş", callback_data="gec"))
    k.row(B("📊 Özet", callback_data="ozet"), B("⚙️ Ayarlar", callback_data="ayar"))
    k.row(B("🚨 Tümünü Kapat", callback_data="hep"), B("🔄 Yenile", callback_data="ana"))
    return (f"🤖 GHOST KISA · {VERSIYON}\n━━━━━━━━━━━━━━━━\n{durum()}\n\n"
            f"💰 Bakiye {bakiye():.2f}$   📅 Bugün {gun_toplam():+.2f}$\n📌 Pozisyon {n}/{A['max_pos']}\n"
            f"🎯 {strateji_yazi()}"), k

@bot.message_handler(commands=["panel", "start", "durum", "gecmis"])
def pn(m):
    if m.chat.id != CHAT: return
    t, k = ekran("gec" if m.text.startswith("/gecmis") else "ana"); bot.send_message(CHAT, t, reply_markup=k)

def kaldirac_toplu(hedef):
    syms = [x for x, mk in ex.markets.items() if mk.get("swap") and mk.get("quote") == "USDT" and mk.get("active", True)]
    tam, dusuk, basarisiz = 0, 0, []
    for n, x in enumerate(syms):
        son = None
        for l in [l for l in LADDER if l <= hedef]:
            ok, g, h = kaldirac_ayarla(x, l, "buy")
            if ok and (g is None or abs(g - l) < 0.5): son = l; kaldirac_ayarla(x, l, "sell"); break
        if son: lev_cap[x] = son; tam += son == hedef; dusuk += son != hedef
        else: basarisiz.append(x.split("/")[0])
        if n and n % 150 == 0: bot.send_message(CHAT, f"… {n}/{len(syms)}")
    kaydet(); bot.send_message(CHAT, f"✅ Kaldıraç ayarı bitti (hedef {hedef}x): {tam} kontratta tuttu, {dusuk} kontrat daha düşük kabul etti, {len(basarisiz)} ayarlanamadı")

@bot.message_handler(commands=["kaldirac"])
def kaldirac_kmd(m):
    if m.chat.id != CHAT: return
    a = m.text.split(); hedef = int(a[1]) if len(a) > 1 and a[1].isdigit() else 20
    bot.send_message(CHAT, f"⏳ Tüm USDT-M kontratlarda {hedef}x ayarlanıyor…")
    threading.Thread(target=kaldirac_toplu, args=(hedef,), daemon=True).start()

@bot.message_handler(commands=["haric"])
def haric(m):
    if m.chat.id != CHAT: return
    a = m.text.split()[1:]
    if len(a) > 1 and a[0] in ("ekle", "sil"):
        for x in a[1:]:
            x = x.upper().replace("USDT", "").lstrip("0123456789")
            if a[0] == "ekle" and x not in A["haric"]: A["haric"].append(x)
            if a[0] == "sil" and x in A["haric"]: A["haric"].remove(x)
        kaydet()
    bot.send_message(CHAT, "🚫 Hariç tutulan coinler:\n" + " ".join(sorted(A["haric"])) + "\n\nEkle: /haric ekle PEPE FIL\nÇıkar: /haric sil PEPE")

@bot.callback_query_handler(func=lambda c: True)
def cb(c):
    if c.message.chat.id != CHAT: return
    d, uyari, e = c.data, "", "ana"
    try:
        if d in ("poz", "gec", "ozet", "ayar", "hep"): e = d
        elif d[0] == "k" and d[1:].isdigit():
            e = "poz"; sym = POZ.get(int(d[1:]))
            p = next((x for x in ex.fetch_positions() if x["symbol"] == sym and x.get("contracts")), None) if sym else None
            if not p: uyari = "pozisyon yok, yenile"
            else:
                with KIL: kapat(sym, p, "MANUEL")
        elif d == "tog": A["calis"] = not A["calis"]
        elif d == "hk": A["hk"] = not A["hk"]; e = "ayar"
        elif d.startswith("mod:"): A["mod"] = d[4:]; e = "ayar"
        elif d.startswith("pn:"): A["pen"] = int(d[3:]); e = "ayar"
        elif d.startswith("uc:"): A["uc"] = float(d[3:]); e = "ayar"
        elif d.startswith("es:"): A["esik"] = float(d[3:]); e = "ayar"
        elif d.startswith("mj:"): A["marjin"] = float(d[3:]); e = "ayar"
        elif d.startswith("lev:"): A["lev"] = int(d[4:]); e = "ayar"
        elif d.startswith("lim:"): A["max_pos"] = int(d[4:]); e = "ayar"
        elif d.startswith("gl:"): A["gunluk"] = float(d[3:]); e = "ayar"
        elif d.startswith("bk:"): A["bekle"] = int(d[3:]); e = "ayar"
        elif d.startswith("lvl:"): A["lv"] = [int(x) / 100 for x in d[4:].split(",")]; e = "ayar"
        elif d == "hepE":
            A["calis"] = False
            with KIL:
                for p in ex.fetch_positions():
                    if p.get("contracts"): kapat(p["symbol"], p, "MANUEL")
    except Exception as x: uyari = str(x)[:150]
    kaydet()
    try:
        t, k = ekran(e); bot.edit_message_text(t, c.message.chat.id, c.message.message_id, reply_markup=k)
    except Exception: pass
    try: bot.answer_callback_query(c.id, uyari)
    except Exception: pass

# ───────────────────────── ana döngü ─────────────────────────
def izle():          # pozisyon takibi: 2 sn'de bir
    while True:
        try: yonet(); duzelt()
        except Exception as e: print("hata yonet", repr(e)[:200], flush=True)
        time.sleep(2)

def tarama():        # her 5 dk mum başında BİR kez fiyat oku + sinyal
    hata_sayac = 0; son_kalp = 0.0
    while True:
        try:
            tarama_adimi(); hata_sayac = 0
        except Exception as e:
            hata_sayac += 1; print("hata tarama", repr(e)[:200], flush=True)
            if hata_sayac == 5: haber(f"⚠️ Fiyat okuma 5 kez üst üste hata verdi: {str(e)[:100]}")
        if time.time() - son_kalp > 600:
            son_kalp = time.time(); print(f"💓 {VERSIYON} {durum()} açık={len(acik)} bugün={gun_toplam():+.2f}$ son_tarama={int(time.time()-son_tarama[0]) if son_tarama[0] else -1}sn önce", flush=True)
        time.sleep(0.25)

if __name__ == "__main__":
    ex.load_markets()
    threading.Thread(target=lambda: bot.infinity_polling(skip_pending=True), daemon=True).start()
    haber(f"🤖 GHOST KISA {VERSIYON} hazır\n{durum()}\n🎯 {strateji_yazi()}\n💰 {A['marjin']:g}$ izole · ≤{A['lev']}x · max {A['max_pos']} işlem · limit {('−' + str(A['gunluk']) + '$') if A['gunluk'] else 'yok'}\n→ /panel")
    threading.Thread(target=izle, daemon=True).start()
    tarama()
