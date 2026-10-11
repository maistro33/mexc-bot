# GHOST YÜKSELEN BOT  —  basit bot: sadece LONG, sadece borsanın en çok yükselenleri
#
# GİRİŞ (tek kural, indikatör yok):
#   Bitget USDT-M vadeli listesi 24 saatlik değişime göre sıralanır (borsadaki "Change" sıralamasının aynısı, hisse/altın/emtia hariç).
#   İlk 30 (ayarlanabilir) coin sırayla denenir: boş yer varsa en üstteki uygun coine LONG açılır. Her 5 dakikada bir taranır.
#   Short YOK. Hariç listesindeki coinler (BTC, ETH vb.) ve günlük hacmi 1M$ altı coinler alınmaz.
# ÇIKIŞ:
#   Zarar stopu (marjinin oranı) borsada emir olarak durur. Kâr ilk kilide ulaşınca kilitlenir,
#   sonra kilit ZİRVEYİ TAKİP EDER (iz süren): kâr büyüdükçe kilit de yükselir.
#
# TEST (gerçek Bitget 1 dk verisi, 76 coin, 31 gün, komisyon + 1 dk gecikme dahil, 1$ marjin 20x, 5 işlem):
#   "En çok yükselenlere long" günde ~100 işlem açtı. Son 14 günde her çıkış ayarında ZARAR (günde −3$ ile −5$),
#   önceki 17 günde küçük kilitle zarar (−2$/gün), geniş kilitle başa baş. Kanıtlanmış kâr avantajı YOK.
#   Not: test verisinde en hacimli 40 coin yoktu, canlı liste onları da içerir; yani test birebir aynı liste değil.
#
# SÜRÜM GEÇMİŞİ (her değişiklikte VERSIYON ve buraya bir satır eklenir)
# v5.0 11.10 22:50  Sıfırdan yazım: tek giriş kuralı (24s hareketlisi 1 saatte dönünce), iz süren kilit (zirveyi takip),
#                   yeni panel (Adaylar, Özet, Günlük tablo, Ayarlar, Yardım), gece yarısı günlük rapor, /kayit işlem dosyası.
#                   Eski modlar (tersine/takip/aralık/defter/mikro/gölge) tamamen kaldırıldı. Ayarlar yeni dosyada (ayar5.json), eski istatistik karışmaz.
# v5.1 11.10 23:20  SÜREKLİ MOD (varsayılan AÇIK, Ayarlar'dan kapatılır): dönüş sinyali yokken boş kalan yerler 15 dakikalık harekete göre doldurulur
#                   (son 15 dk'da ≥%2.5 oynayan coine TERS yönde girilir). Amaç bot hiç boş durmasın. TEST: bu mod günde ~95 işlem açar ama
#                   31 günlük veride günde −1.4$ ile −3.5$ arası ZARAR etti (1$ marjin). Özet ekranı Dönüş / Sürekli işlemlerini ayrı gösterir.
# v5.2 12.10 00:00  BASİT BOT: dönüş kuralı ve sürekli mod KALDIRILDI. Tek kural: borsanın 24s en çok yükselenler listesinin ilk 30'una sırayla LONG.
#                   Short yok. "Hantal = en hacimli 40" filtresi kaldırıldı (günün en çok yükselenlerini listeden atıyordu: CKB, MAGIC, S, LUMIA gibi);
#                   hariç listesi (BTC, ETH vb.) ve hisse filtresi duruyor. Adaylar ekranı artık yükselenler sıralamasını gösterir.
VERSIYON = "v5.2 (12.10 00:00)"

import os, time, json, threading, datetime as dt
import ccxt, telebot
from telebot import types

E = os.getenv
CHAT = int(E("MY_CHAT_ID", "0"))
BAR = 300                                   # tarama aralığı (sn): 5 dakika
MIN_SL_PCT = 1.5                            # stop fiyattan en az bu % uzak olmalı; değilse kaldıraç düşürülür
MIN_HACIM = 1_000_000                       # 24s hacmi bundan düşük coinler taranmaz ($)
LADDER = (125, 100, 75, 50, 30, 25, 20, 15, 10, 5, 3, 2)

try:
    from zoneinfo import ZoneInfo
    TZ = ZoneInfo(E("TZ_ADI", "Europe/Stockholm")); dt.datetime.now(TZ)
except Exception:
    TZ = dt.timezone(dt.timedelta(hours=2))
def gun(t=None): return dt.datetime.fromtimestamp(t or time.time(), TZ).strftime("%Y-%m-%d")
def saat(t): return dt.datetime.fromtimestamp(t, TZ).strftime("%d.%m %H:%M")

KLASOR = "/data/" if os.path.isdir("/data") else ""
DOSYA, KAYIT = KLASOR + "ayar5.json", KLASOR + "islem.jsonl"
HARIC = "BTC ETH XRP ADA DOGE SOL BNB LTC BCH TRX LINK DOT AVAX XLM ETC ATOM SHIB PEPE".split()
HISSE = set()                               # hisse/altın/emtia: açılışta borsadan otomatik doldurulur (isRwa)

# ───────────────────────── ayarlar ─────────────────────────
A = {"v": 5, "calis": True, "marjin": 1.0, "lev": 20, "max_pos": 5, "sl": 0.8, "net": 0.10, "iz": 0.10,
     "liste": 30, "minp": 0.0, "gunluk": 5.0, "bekle": 15, "elle": True, "haric": list(HARIC)}
# panelde gösterilen ayarlar: anahtar -> (başlık, seçenekler, yazım)
AYAR = {
    "liste":  ("YÜKSELENLER LİSTESİ (ilk kaç coin)",     (10, 20, 30),              lambda v: f"İlk {v}"),
    "minp":   ("EN AZ 24 SAATLİK YÜKSELİŞ",              (0.0, 5.0, 10.0),          lambda v: f"%{v:g}" if v else "Fark etmez"),
    "marjin": ("MARJİN (işlem başı)",                   (1.0, 2.0, 3.0, 5.0),      lambda v: f"{v:g}$"),
    "lev":    ("KALDIRAÇ (en çok)",                     (10, 20, 50),              lambda v: f"{v}x"),
    "max_pos": ("AYNI ANDA İŞLEM",                      (1, 2, 3, 5, 8),           lambda v: str(v)),
    "sl":     ("ZARAR STOPU (marjinin oranı)",          (0.5, 0.65, 0.8),          lambda v: f"%{v*100:g}"),
    "net":    ("İLK KİLİT: NET KÂR (1$ marjin için)",   (0.10, 0.20, 0.30, 0.50),  lambda v: f"+{v:g}$"),
    "iz":     ("İZ SÜREN: ZİRVEDEN GERİ PAY (1$ için)", (0.10, 0.15, 0.20, 0.30),  lambda v: f"{v:g}$"),
    "gunluk": ("GÜNLÜK ZARAR LİMİTİ",                   (2.0, 3.0, 5.0, 10.0, 0.0), lambda v: f"-{v:g}$" if v else "Yok"),
    "bekle":  ("AYNI COİNE TEKRAR (kârdan sonra)",      (5, 15, 30, 60),           lambda v: f"{v} dk"),
}
acik, yasak, gecmis, lev_cap = {}, {}, [], {}
ADAY = {"t": 0, "liste": []}                # son taramanın sonucu (panelde "Adaylar")
KIL = threading.RLock()
try:
    d = json.load(open(DOSYA))
    if d.get("A", {}).get("v") == 5: A.update(d["A"])
    acik.update(d.get("acik", {})); gecmis.extend(d.get("gecmis", [])); lev_cap.update(d.get("cap", {}))
except Exception: pass

def kaydet():
    try: json.dump({"A": A, "acik": acik, "gecmis": gecmis[-1500:], "cap": lev_cap}, open(DOSYA, "w"))
    except Exception: pass

def kayit_yaz(d):
    try:
        with open(KAYIT, "a") as f: f.write(json.dumps(d, ensure_ascii=False) + "\n")
    except Exception: pass

ex = ccxt.bitget({"apiKey": E("BITGET_API"), "secret": E("BITGET_SEC"), "password": E("BITGET_PASS"),
                  "options": {"defaultType": "swap"}, "enableRateLimit": True, "timeout": 30000})
bot = telebot.TeleBot(E("TELE_TOKEN", "x"), threaded=False)

def haber(m):
    print(m, flush=True)
    try: bot.send_message(CHAT, m)
    except Exception: pass

def bakiye():
    try: return float(ex.fetch_balance()["USDT"]["total"])
    except Exception: return 0.0

def ad(sym): return sym.split(":")[0]
def temiz(sym): return sym.split("/")[0].lstrip("0123456789")

# ───────────────────────── kayıt / gerçek kâr-zarar ─────────────────────────
def logla(sym, yon, pnl, neden, k):
    try: mid = ex.market(sym)["id"]
    except Exception: mid = ad(sym).replace("/", "")
    g = {"t": int(time.time()), "s": ad(sym), "id": mid, "y": yon, "pnl": round(pnl, 3), "n": neden, "z": round(k.get("zirve", 0.0), 2), "g": 0,
         "t0": k.get("t"), "p24": k.get("p24"), "sira": k.get("sira"), "k": "e" if k.get("elle") else "y"}
    gecmis.append(g); kaydet()

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

def duzelt():
    """Kapanıştan ~20 sn sonra tahmini PnL'yi borsanın gerçek (komisyonlu) rakamıyla değiştir ve işlem dosyasına yaz."""
    degisti = False
    for g in gecmis[-40:]:
        if g.get("g", 1) == 0 and time.time() - g["t"] > 20 and time.time() - g.get("d", 0) > 15:
            g["d"] = time.time(); v = gercek_pnl(g.get("id", ""), g["t"]); degisti = True
            if v is not None: g["pnl"], g["g"] = round(v, 3), 1
            elif time.time() - g["t"] > 900: g["g"] = 2          # gerçeği alınamadı: tahmin kalır
            if g["g"]: kayit_yaz({k: v for k, v in g.items() if k not in ("d", "id")})
    if degisti: kaydet()

def gun_toplam(b=None):
    b = b or gun()
    return sum(g["pnl"] for g in gecmis if gun(g["t"]) == b)

def limit_doldu():
    """Günlük zarar limiti dolu mu? (kalıcı kilit YOK: limit değişince ya da gün dönünce kendiliğinden devam eder)"""
    return A["gunluk"] > 0 and gun_toplam() <= -A["gunluk"]

def durum():
    if not A["calis"]: return "⏹ DURDU (elle)"
    if limit_doldu(): return "⛔ GÜNLÜK LİMİT DOLDU (yeni giriş yok)"
    return "▶️ ÇALIŞIYOR"

# ───────────────────────── borsa işlemleri ─────────────────────────
def borsa_stop_iptal(sym, sid):
    if not sid: return
    for prm in ({"trigger": True}, {"stop": True}, {}):
        try: ex.cancel_order(sid, sym, prm); return
        except Exception: pass

def borsa_stop(sym, p, k, kilit):
    """Borsada stop-market (reduce-only). kilit: kâr kilidi (+) ya da zarar stopu (−), $ olarak. Döner: stop fiyatı ya da None."""
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
        haber(f"⚠️ {ad(sym)} borsa stopu konamadı, bot takip ediyor: {str(e)[:110]}")
        return None

def kapat(sym, p, neden):
    pnl = p.get("unrealizedPnl") or 0.0
    ex.create_order(sym, "market", "sell" if p["side"] == "long" else "buy", p["contracts"], params={"reduceOnly": True, "marginMode": "isolated"})
    yasak[sym] = time.time() + (A["bekle"] * 60 if pnl > 0 else max(A["bekle"] * 60, 2 * 3600))      # zararla kapanan coine 2 saat yok
    k = acik.pop(sym, {}); borsa_stop_iptal(sym, k.get("sid"))
    logla(sym, p["side"], pnl, neden, k)
    haber(f"{'✅' if pnl > 0 else '❌'} {ad(sym)} kapandı: {neden}\nPnL ≈ {pnl:+.2f}$ (gördüğü zirve {k.get('zirve', 0.0):+.2f}$)")

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

def poz_oku(sym):
    return next((x for x in ex.fetch_positions([sym]) if x.get("contracts")), None)

def ac(sym, yon, son, p24, sira):
    """İzole pozisyon aç + borsaya zorunlu yedek stop koy. Döner: True/False."""
    with KIL:
        if sym in acik or len(acik) >= A["max_pos"]: return False
    mj = A["marjin"]; lev, hata = 0, ""
    for l in [l for l in LADDER if l <= min(A["lev"], lev_cap.get(sym, 999)) and 70 * (1 / l - 0.0105) >= MIN_SL_PCT]:
        ok, g, h = kaldirac_ayarla(sym, l, yon); hata = h or hata
        if ok and (g is None or abs(g - l) < 0.5): lev = l; break
        if ok and g is not None and g < l: lev_cap[sym] = int(g)
    if not lev:
        yasak[sym] = time.time() + 6 * 3600
        if hata: haber(f"⚠️ {ad(sym)} kaldıraç ayarlanamadı, atlandı: {hata}")
        return False
    cs = ex.market(sym).get("contractSize") or 1
    adet = ex.amount_to_precision(sym, mj * lev / son / cs)
    if float(adet) * cs * son < 5.2: yasak[sym] = time.time() + 6 * 3600; return False          # borsanın en küçük emir tutarının altında
    try:
        ex.create_order(sym, "market", yon, float(adet), params={"marginMode": "isolated"})
    except Exception as e:
        if "40797" in str(e):          # borsa bu kaldıracı kabul etmiyor: bir basamak düşür, sonraki sinyalde dene
            alt = [l for l in LADDER if l < lev]
            if alt: lev_cap[sym] = alt[0]; yasak[sym] = time.time() + 20; haber(f"ℹ️ {ad(sym)} {lev}x kabul edilmedi, sonraki sinyalde {alt[0]}x denenecek"); return False
        yasak[sym] = time.time() + 3600; haber(f"⚠️ {ad(sym)} açılamadı: {str(e)[:120]}"); return False
    p = None
    for _ in range(4):                 # pozisyonu borsadan doğrula
        try:
            p = poz_oku(sym)
            if p: break
        except Exception: pass
        time.sleep(0.7)
    if not p:
        haber(f"🚨 {ad(sym)}: emir gitti ama pozisyon görünmedi. Bitget'ten kontrol et!"); yasak[sym] = time.time() + 3600; return False
    gl = float(p.get("leverage") or lev)
    if abs(gl - lev) > 0.5 or float(p.get("initialMargin") or 0) > mj * 1.5:          # kaldıraç uyuşmadı: fazlayı küçült, olmazsa kapat
        try:
            kalan = float(ex.amount_to_precision(sym, float(p["contracts"]) * gl / lev)) if 0 < gl < lev else 0.0
            fazla = float(ex.amount_to_precision(sym, float(p["contracts"]) - kalan)) if kalan else 0.0
            if not (kalan and fazla > 0 and kalan * cs * son >= 5.2): raise RuntimeError("küçültülemedi")
            ex.create_order(sym, "market", "sell" if p["side"] == "long" else "buy", fazla, params={"reduceOnly": True, "marginMode": "isolated"})
            lev_cap[sym] = int(gl); lev = int(gl); p = poz_oku(sym)
            haber(f"ℹ️ {ad(sym)}: {gl:g}x uygulandı, pozisyon küçültüldü, devam")
        except Exception:
            try:
                p = poz_oku(sym)
                if p: kapat(sym, p, "KALDIRAÇ UYUŞMADI")
            except Exception: pass
            yasak[sym] = time.time() + 6 * 3600; haber(f"🚨 {ad(sym)}: kaldıraç uyuşmadı, pozisyon kapatıldı"); return False
    gir = float(p.get("entryPrice") or son); adet_f = float(p["contracts"])
    sl = round(A["sl"] * mj, 3); not_ = ""
    try:      # stop likidasyondan ÖNCE gelsin: likidasyon uzaklığının %70'ine daralt
        liq = float(p.get("liquidationPrice") or 0)
        if liq and sl / (adet_f * cs) > 0.7 * abs(gir - liq):
            sl = round(0.7 * abs(gir - liq) * adet_f * cs, 3); not_ = " (likidasyona yakın, daraltıldı)"
    except Exception: pass
    with KIL:
        acik[sym] = {"zirve": 0.0, "mj": mj, "sl": sl, "son": 0.0, "t": int(time.time()), "y": p["side"], "lev": lev, "p24": round(p24, 1), "sira": sira}
        fy = borsa_stop(sym, p, acik[sym], -min(sl * 1.2, 0.85 * mj))          # ZORUNLU yedek stop: bot düşse bile korur
        kaydet()
    kl1, e0 = kilit_seviye(mj, lev)
    haber(f"{'🟢 LONG' if yon == 'buy' else '🔴 SHORT'} {ad(sym)} · {lev}x izole · {mj:g}$\n"
          f"Sebep: 24 saatte %{p24:+.1f}, yükselenler listesinde {sira}. sırada\n"
          f"Giriş {gir:g} | Bot stopu ≈ {sl_fiyat(yon, gir, adet_f, cs, sl):g} (−{sl:g}${not_})\n"
          f"{'🛡 Borsa yedek stopu: ' + str(fy) if fy else '⚠️ Borsa stopu YOK, bot takip ediyor'}\n"
          f"Kâr: +{e0:.2f}$ görünce +{kl1:.2f}$ kilitlenir, sonra kilit zirvenin {A['iz'] * mj:.2f}$ gerisinden takip eder")
    return True

def kilit_seviye(mj, lev):
    """İlk kilit ($, brüt): net hedef + komisyon + kayma payı. e0: kilidin devreye girdiği kâr."""
    kl1 = (A["net"] + 0.0012 * lev + 0.03) * mj
    return kl1, kl1 + 0.05 * mj

def yonet():
    """Açık pozisyonları yönet: zarar stopu + iz süren kâr kilidi. 2 sn'de bir çalışır."""
    with KIL:
        pos = [p for p in ex.fetch_positions() if p.get("contracts")]
        var = {p["symbol"] for p in pos}
        for s in [s for s in acik if s not in var]:          # borsada kapanmış (stop emri / elle / likidasyon)
            k = acik.pop(s); borsa_stop_iptal(s, k.get("sid")); son = k.get("son", 0.0)
            if k.get("kilit") is not None: son, neden = k["kilit"], "KİLİT (borsa)"          # borsadaki kilit emri çalıştı: tahmin = kilit seviyesi
            elif son <= -0.6 * k.get("sl", 9): neden = "STOP (borsa)"
            else: neden = "BORSADA KAPANDI"
            logla(s, k.get("y", "?"), son, neden, k)
            yasak[s] = time.time() + (A["bekle"] * 60 if son > 0 else max(A["bekle"] * 60, 2 * 3600))
            haber(f"{'✅' if son > 0 else '❌'} {ad(s)} borsada kapandı: {neden}\nPnL ≈ {son:+.2f}$ (gerçek rakam birazdan Geçmiş'e yazılır)")
        for p in pos:
            sym = p["symbol"]; pnl = p.get("unrealizedPnl") or 0.0
            if sym not in acik:                               # elle açılan pozisyon
                if not A["elle"]: continue
                mj = float(p.get("initialMargin") or A["marjin"])
                acik[sym] = {"zirve": max(pnl, 0.0), "mj": mj, "sl": round(A["sl"] * mj, 3), "son": pnl, "t": int(time.time()), "y": p["side"], "elle": True}
                haber(f"ℹ️ {ad(sym)}: elle açılan pozisyon devralındı (stop −{acik[sym]['sl']:g}$, iz süren kilit açık)")
            k = acik[sym]; k["son"] = pnl; k["zirve"] = max(k["zirve"], pnl); mj = k["mj"]
            try: lev = float(p.get("leverage") or k.get("lev") or 20)
            except Exception: lev = 20.0
            kl1, e0 = kilit_seviye(mj, lev)
            if k["zirve"] >= e0:                               # kilit: en az ilk kilit, sonra zirvenin "iz" kadar gerisi
                yeni = max(kl1, k["zirve"] - A["iz"] * mj)
                if k.get("kilit") is None: haber(f"🔒 {ad(sym)} kâr kilitlendi: +{yeni:.2f}$ (pnl {pnl:+.2f}$), kilit zirveyi takip edecek")
                k["kilit"] = max(k.get("kilit") or 0.0, yeni)
            if k.get("kilit") is not None and k["kilit"] >= k.get("bsk", -9) + 0.05 * mj:
                borsa_stop(sym, p, k, k["kilit"]); k["bsk"] = k["kilit"]          # başarısız olsa da aynı seviyeyi tekrar deneme
            if k.get("kilit") is not None and pnl <= k["kilit"]: kapat(sym, p, "KİLİT")
            elif k.get("kilit") is None and pnl <= -k["sl"]: kapat(sym, p, "STOP")
        kaydet()

# ───────────────────────── strateji: en çok yükselenlere long ─────────────────────────
tarama_bid, son_tarama = [0], [0.0]

def yukselenler():
    """Borsanın 24s en çok yükselenler sıralaması (hisse/emtia, hariç listesi ve hacmi 1M$ altı olanlar yok). Döner: [(sembol, fiyat, 24s %)], en çok yükselen başta."""
    L = []
    for s, t in ex.fetch_tickers().items():
        if not s.endswith(":USDT") or not t.get("last"): continue
        b = temiz(s)
        if b in HISSE or (ex.markets.get(s, {}).get("base") in HISSE) or b in A["haric"]: continue
        if float(t.get("quoteVolume") or 0) < MIN_HACIM: continue
        p24 = t.get("percentage")
        if p24 is None:
            try: p24 = float((t.get("info") or {}).get("change24h")) * 100
            except Exception: continue
        if float(p24) > A["minp"]: L.append((float(p24), s, float(t["last"])))
    L.sort(reverse=True)
    return [(s, c, p) for p, s, c in L[:A["liste"]]]

def uygun(s):
    return s not in acik and time.time() >= yasak.get(s, 0)

def tarama_adimi():
    """Her 5 dakikanın başında BİR kez çalışır: yükselenler listesini oku, boş yer varsa sırayla en üstteki uygun coine LONG aç."""
    simdi = time.time(); bid = int(simdi // BAR)
    if tarama_bid[0] == bid: return
    tarama_bid[0] = bid; taze = simdi - bid * BAR < 45          # bot yeni açıldıysa ilk tarama sadece ekran için, giriş yok
    L = yukselenler()
    ADAY["t"] = int(time.time()); son_tarama[0] = time.time()
    ADAY["liste"] = [{"s": ad(s), "p24": p, "sira": n + 1, "acik": s in acik, "yasak": time.time() < yasak.get(s, 0)} for n, (s, c, p) in enumerate(L)]
    if not (taze and A["calis"]) or limit_doldu(): return
    for n, (s, c, p24) in enumerate(L):                         # sıralamanın en üstünden başla
        with KIL:
            if len(acik) >= A["max_pos"]: break
        if not uygun(s): continue
        try: ac(s, "buy", c, p24, n + 1)
        except Exception as e: haber(f"⚠️ {ad(s)} giriş hatası: {str(e)[:120]}")

# ───────────────────────── panel ─────────────────────────
B = types.InlineKeyboardButton
POZ = {}

def pozlar():
    ps = [p for p in ex.fetch_positions() if p.get("contracts")]
    POZ.clear(); POZ.update({n: p["symbol"] for n, p in enumerate(ps)}); return ps

def strateji_yazi():
    return f"Sadece LONG: 24 saatte en çok yükselen ilk {A['liste']} coine sırayla" + (f" (en az %{A['minp']:g} yükselmiş)" if A["minp"] else "")

def ist(L):
    """İşlem listesinin kısa istatistiği."""
    if not L: return "işlem yok"
    w = [g["pnl"] for g in L if g["pnl"] > 0]; l = [g["pnl"] for g in L if g["pnl"] <= 0]
    return f"{sum(g['pnl'] for g in L):+.2f}$ · {len(L)} işlem · kazanma %{100 * len(w) / len(L):.0f}"

def ekran(e):
    k = types.InlineKeyboardMarkup(); geri = B("⬅️ Menü", callback_data="ana")
    if e == "poz":
        ps = pozlar(); sat = []
        for n, p in enumerate(ps):
            a = acik.get(p["symbol"], {}); g = p.get("entryPrice") or 0; adet = float(p["contracts"]); cs = p.get("contractSize") or 1
            sl = a.get("kilit") if a.get("kilit") is not None else -a.get("sl", 0)
            dk = int((time.time() - a["t"]) / 60) if a.get("t") else 0
            sat.append(f"{n+1}) {'🟢 LONG' if p['side'] == 'long' else '🔴 SHORT'} {ad(p['symbol'])} {p.get('leverage') or '?'}x · {dk} dk\n"
                       f"   PnL {(p.get('unrealizedPnl') or 0):+.2f}$ (zirve {a.get('zirve', 0):+.2f}$)\n"
                       f"   giriş {g:g} | stop {sl_fiyat(p['side'], g, adet, cs, -sl):g} ({'🔒 kilit +' if sl > 0 else ''}{sl:.2f}$)")
            k.row(B(f"❌ {n+1}. {ad(p['symbol']).split('/')[0]} kapat", callback_data=f"k{n}"))
        k.row(geri, B("🔄 Yenile", callback_data="poz"))
        return "📋 AÇIK POZİSYONLAR\n\n" + ("\n\n".join(sat) or "Açık pozisyon yok."), k
    if e == "aday":
        k.row(geri, B("🔄 Yenile", callback_data="aday")); L = ADAY["liste"]
        if not ADAY["t"]: return "🔎 ADAYLAR\n\nHenüz tarama yapılmadı (ilk tarama en geç 5 dk içinde).", k
        sat = []
        for x in L[:30]:
            im = "📌 açık" if x["acik"] else ("⏱ beklemede" if x["yasak"] else "")
            sat.append(f"{x['sira']:>2}. {x['s'].split('/')[0]}  %{x['p24']:+.1f}  {im}")
        return (f"🔎 YÜKSELENLER (son tarama {saat(ADAY['t'])[-5:]})\nBot boş yer oldukça listenin en üstündeki uygun coine LONG açar.\n\n"
                + ("\n".join(sat) or "Şu an listeye giren coin yok.")), k
    if e == "gec":
        k.row(geri, B("🔄 Yenile", callback_data="gec")); son = gecmis[-15:][::-1]
        sat = [f"{'✅' if g['pnl'] > 0 else '❌'} {saat(g['t'])} {g['s'].split('/')[0]} {'L' if g['y'] in ('long', 'buy') else 'S'} {g['pnl']:+.2f}$ {'✓' if g.get('g') == 1 else '≈'} {g['n']}" for g in son]
        return "📜 SON 15 İŞLEM (✓ borsadan net, ≈ tahmin)\n\n" + ("\n".join(sat) or "Henüz işlem yok."), k
    if e == "ozet":
        k.row(B("📅 Günlük tablo", callback_data="gunler"), geri)
        n = len(gecmis); w = [g["pnl"] for g in gecmis if g["pnl"] > 0]; l = [g["pnl"] for g in gecmis if g["pnl"] <= 0]
        ok_ = sum(w) / len(w) if w else 0; oz = sum(l) / len(l) if l else 0
        bas = f"%{100 * abs(oz) / (abs(oz) + ok_):.0f}" if w and l else "–"
        coin = {}
        for g in gecmis: coin[g["s"].split("/")[0]] = coin.get(g["s"].split("/")[0], 0) + g["pnl"]
        sira = sorted(coin.items(), key=lambda x: x[1])
        return (f"📊 ÖZET ({VERSIYON} ile başlayan işlemler)\n\n💰 Bakiye: {bakiye():.2f}$\n📅 Bugün: {ist([g for g in gecmis if gun(g['t']) == gun()])}\n"
                f"📈 Toplam: {sum(g['pnl'] for g in gecmis):+.2f}$ ({n} işlem)\n\n"
                f"Kazanma: %{(len(w) / n * 100 if n else 0):.0f} ({len(w)} kazanç / {len(l)} kayıp)\n"
                f"Ort. kazanç: {ok_:+.2f}$ | Ort. kayıp: {oz:+.2f}$\n"
                f"Başa baş için gereken kazanma: {bas}\n\n"
                f"🟢 Long: {ist([g for g in gecmis if g['y'] in ('long', 'buy')])}\n🔴 Short: {ist([g for g in gecmis if g['y'] in ('short', 'sell')])}\n\n"
                + (f"En iyi coin: {sira[-1][0]} {sira[-1][1]:+.2f}$\nEn kötü coin: {sira[0][0]} {sira[0][1]:+.2f}$" if sira else "")), k
    if e == "gunler":
        k.row(B("📊 Özet", callback_data="ozet"), geri); sat = []
        for i in range(7):
            b = gun(time.time() - i * 86400); L = [g for g in gecmis if gun(g["t"]) == b]
            sat.append(f"{'🟩' if sum(g['pnl'] for g in L) > 0 else '🟥' if L else '⬜'} {b[8:]}.{b[5:7]}  {ist(L)}")
        return "📅 SON 7 GÜN\n\n" + "\n".join(sat), k
    if e == "ayar":
        for a, (baslik, secenek, fmt) in AYAR.items():
            k.row(B(f"— {baslik} —", callback_data="ayar"))
            k.row(*[B(("✅ " if A[a] == v else "") + fmt(v), callback_data=f"s:{a}:{n}") for n, v in enumerate(secenek)])
        k.row(B("Elle açtığım işlemler: " + ("✅ bot yönetsin" if A["elle"] else "❌ bot dokunmasın"), callback_data="elle"))
        k.row(B(f"🚫 Hariç coinler ({len(A['haric'])}) → /haric", callback_data="ayar"))
        k.row(geri)
        kl1, e0 = kilit_seviye(A["marjin"], A["lev"])
        return (f"⚙️ AYARLAR\n\n🎯 {strateji_yazi()}\n\n💵 {A['marjin']:g}$ izole · ≤{A['lev']}x · en çok {A['max_pos']} işlem\n"
                f"🛑 Zarar stopu: −{A['sl'] * A['marjin']:.2f}$ (borsada yedek stop her işlemde)\n"
                f"🔒 Kâr: +{e0:.2f}$ görünce +{kl1:.2f}$ kilitlenir (net ≈ +{A['net'] * A['marjin']:.2f}$), sonra zirvenin {A['iz'] * A['marjin']:.2f}$ gerisinden takip\n"
                f"📉 Günlük zarar limiti: {('−' + format(A['gunluk'], 'g') + '$') if A['gunluk'] else 'yok'}\n"
                f"⏱ Tekrar giriş: kârdan sonra {A['bekle']} dk, zarardan sonra 2 saat"), k
    if e == "yardim":
        k.row(geri)
        return ("❓ YARDIM\n\nBot ne yapar: Bitget vadeli listesini 24 saatlik yükselişe göre sıralar (borsadaki Change sıralaması, hisse/emtia hariç). "
                "Boş yer oldukça listenin en üstündeki uygun coine LONG açar. Short açmaz. Her 5 dakikada bir tarar.\n\n"
                "Çıkış: zarar stopu borsada durur. Kâr ilk kilide ulaşınca kilitlenir, sonra kilit zirveyi takip eder.\n\n"
                "Dürüst not: 31 günlük gerçek veride bu kural son 14 günde günde 3-5$ zarar etti, önceki 17 günde zarar ile başa baş arasında kaldı (1$ marjin). "
                "Kâr garantisi yoktur.\n\n"
                "Komutlar:\n/panel – ana menü\n/adaylar – yükselenler listesi\n/gecmis – son işlemler\n/ozet – istatistik\n"
                "/haric – hariç coin listesi (ekle/sil)\n/kayit – tüm işlemlerin dosyası"), k
    if e == "hep":
        k.row(B("✅ Evet, HEPSİNİ kapat", callback_data="hepE"), B("❌ Vazgeç", callback_data="ana"))
        return "🚨 Tüm pozisyonlar kapatılsın mı? (Otomatik giriş de durur)", k
    ps = pozlar(); n = len(ps); ucan = sum(p.get("unrealizedPnl") or 0 for p in ps)
    k.row(B("🛑 DURDUR" if A["calis"] else "▶️ BAŞLAT", callback_data="tog"))
    k.row(B(f"📋 Pozisyonlar ({n})", callback_data="poz"), B("🔎 Yükselenler", callback_data="aday"))
    k.row(B("📜 Geçmiş", callback_data="gec"), B("📊 Özet", callback_data="ozet"))
    k.row(B("⚙️ Ayarlar", callback_data="ayar"), B("❓ Yardım", callback_data="yardim"))
    k.row(B("🚨 Tümünü Kapat", callback_data="hep"), B("🔄 Yenile", callback_data="ana"))
    tr = f"{int(time.time() - son_tarama[0])} sn önce" if son_tarama[0] else "bekleniyor"
    return (f"👻 GHOST YÜKSELEN · {VERSIYON}\n━━━━━━━━━━━━━━━━\n{durum()}\n\n"
            f"💰 Bakiye {bakiye():.2f}$\n📅 Bugün {gun_toplam():+.2f}$ ({sum(1 for g in gecmis if gun(g['t']) == gun())} işlem)\n"
            f"📌 Pozisyon {n}/{A['max_pos']}" + (f" · açık PnL {ucan:+.2f}$" if n else "") + f"\n🔎 Son tarama: {tr}\n\n🎯 {strateji_yazi()}"), k

KOMUT = {"/gecmis": "gec", "/adaylar": "aday", "/ozet": "ozet", "/ayar": "ayar", "/yardim": "yardim"}
@bot.message_handler(commands=["panel", "start", "durum", "gecmis", "adaylar", "ozet", "ayar", "yardim"])
def pn(m):
    if m.chat.id != CHAT: return
    try: t, k = ekran(KOMUT.get(m.text.split()[0].split("@")[0], "ana")); bot.send_message(CHAT, t, reply_markup=k)
    except Exception as x: bot.send_message(CHAT, f"⚠️ Panel açılamadı: {str(x)[:150]}")

@bot.message_handler(commands=["kayit"])
def kayit_gonder(m):
    if m.chat.id != CHAT: return
    try: bot.send_document(CHAT, open(KAYIT, "rb"), caption=f"Tüm işlemler ({VERSIYON})")
    except Exception: bot.send_message(CHAT, "Henüz kayıtlı işlem yok.")

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
        if d in ("poz", "aday", "gec", "ozet", "gunler", "ayar", "yardim", "hep"): e = d
        elif d[0] == "k" and d[1:].isdigit():
            e = "poz"; sym = POZ.get(int(d[1:]))
            with KIL:
                p = poz_oku(sym) if sym else None
                if not p: uyari = "pozisyon yok, yenile"
                else: kapat(sym, p, "MANUEL")
        elif d == "tog": A["calis"] = not A["calis"]
        elif d == "elle": A["elle"] = not A["elle"]; e = "ayar"
        elif d.startswith("s:"):
            _, a, n = d.split(":"); A[a] = AYAR[a][1][int(n)]; e = "ayar"
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

def gunluk_rapor(b):
    L = [g for g in gecmis if gun(g["t"]) == b]
    if L: haber(f"🌙 GÜN SONU {b[8:]}.{b[5:7]}\n{ist(L)}\n💰 Bakiye {bakiye():.2f}$")

def tarama():        # her 5 dakikanın başında BİR kez tara
    hata_sayac = 0; son_kalp = 0.0; bugun = gun()
    while True:
        try:
            tarama_adimi(); hata_sayac = 0
        except Exception as e:
            hata_sayac += 1; print("hata tarama", repr(e)[:200], flush=True)
            if hata_sayac == 5: haber(f"⚠️ Tarama 5 kez üst üste hata verdi: {str(e)[:100]}")
        if gun() != bugun:
            try: gunluk_rapor(bugun)
            except Exception: pass
            bugun = gun()
        if time.time() - son_kalp > 600:
            son_kalp = time.time(); print(f"💓 {VERSIYON} {durum()} açık={len(acik)} bugün={gun_toplam():+.2f}$ aday={len(ADAY['liste'])}", flush=True)
        time.sleep(0.25)

def hisse_yukle():
    """Hisse/altın/emtia (Bitget isRwa=YES) coinlerini tanı: bunlar hiç taranmaz."""
    try:
        for m in ex.markets.values():
            if str((m.get("info") or {}).get("isRwa", "")).upper() == "YES": HISSE.add(m.get("base"))
    except Exception as e: print("rwa liste hatası (markets)", repr(e)[:100], flush=True)
    try:
        import requests
        for x in requests.get("https://api.bitget.com/api/v2/mix/market/contracts?productType=USDT-FUTURES", timeout=15).json().get("data") or []:
            if x.get("isRwa") == "YES": HISSE.add(x["baseCoin"])
    except Exception as e: print("rwa liste hatası (api)", repr(e)[:100], flush=True)
    print(f"hisse/emtia listesi: {len(HISSE)} sembol", flush=True)

if __name__ == "__main__":
    ex.load_markets(); hisse_yukle()
    threading.Thread(target=lambda: bot.infinity_polling(skip_pending=True), daemon=True).start()
    haber(f"👻 GHOST YÜKSELEN {VERSIYON} hazır\n{durum()}\n🎯 {strateji_yazi()}\n"
          f"💵 {A['marjin']:g}$ izole · ≤{A['lev']}x · en çok {A['max_pos']} işlem · limit {('−' + format(A['gunluk'], 'g') + '$') if A['gunluk'] else 'yok'}\n→ /panel")
    threading.Thread(target=izle, daemon=True).start()
    tarama()
