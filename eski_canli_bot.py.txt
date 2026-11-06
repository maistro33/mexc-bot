# GHOST DİP BOT  —  sadece LONG, sadece en çok düşüp dibi görmüş coinler, stop yok, geniş kâr al
#
# GİRİŞ (tek kural, indikatör yok):
#   Bitget USDT-M vadeli listesi 24 saatlik değişime göre sıralanır, EN ÇOK DÜŞEN ilk 30 coin alınır (en az %10 düşmüş).
#   "Dibi görmüş" şartı: son 1 saatte en az %1 toparlanmış olmalı. Şartı sağlayan en çok düşmüş coinden başlanır, LONG açılır.
#   Hisse/altın/emtia coinleri, hariç listesi ve günlük hacmi 1M$ altı coinler alınmaz. Her 5 dakikada bir taranır.
# ÇIKIŞ:
#   Kâr al: pozisyon kârı +0.50$ (1$ marjin, 10x'te fiyat +%5) olunca kapatılır. ZARAR STOPU YOK (varsayılan):
#   zarar en fazla marjin kadardır (izole, likidasyon). İstenirse panelden stop açılabilir.
#
# TEST (gerçek Bitget 1 dk verisi, 76 coin, 31 gün, komisyon dahil, 1$ marjin 10x, stop yok, kâr al +0.50$):
#   Son 14 gün günde −0.9$, önceki 17 gün günde +0.4$ (günde ~8 işlem, kazanma %56-70, işlemlerin %25-33'ü likidasyon).
#   Başa baş civarı. Kanıtlanmış kâr avantajı YOK.
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
# v6.0 12.10 14:10  YENİ STRATEJİ "DİP": en çok düşen 30 coin içinden son 1 saatte toparlanmaya başlayana LONG. 10x, zarar stopu YOK (varsayılan),
#                   sabit kâr al (+0.50$ / 1$ marjin). Kademeli/iz süren kilit kaldırıldı. Varsayılan en çok 3 işlem. Ayarlar yeni dosyada (ayar6.json).
# v6.1 12.10 14:30  ÇIKIŞ SEÇENEĞİ: "Kâr kilitle + iz süren" (varsayılan) veya "Sabit kâr al". Kilit modunda kâr +0.30$ net (1$ marjin) seviyesine
#                   gelince kilitlenir ve borsaya stop olarak konur, sonra kilit zirvenin 0.30$ gerisinden yukarı taşınır. Test: sabit kâr al ile benzer sonuç.
# v7.0 12.10 22:40  WEB PANELİ (canlı): renkli, canlı izlenen panel + kontroller: Durdur/Başlat, pozisyon kapat, "Kârı koru" (stop o anki kâra
#                   çekilir, borsaya da konur), "Stop ekle", tümünü kapat, elle işlem açma (coin/yön/marjin/kaldıraç; otomatik işlem sayısına
#                   dahil değil), dip adayları "dip yapmaya ne kadar kaldı" çubuğuyla, bütün ayarlar, bakiye eğrisi, kazanma oranı / başa baş göstergesi.
#                   Panel sadece PANEL_SIFRE tanımlıysa açılır. Kâr kilidi (ve Kârı koru) artık "sabit kâr al" modunda da çalışır. Telegram paneli aynen duruyor.
# v7.1 12.10 22:50  SHORT SİNYALLERİ: en çok yükselen 30 coin (24s ≥ eşik) içinden son 1 saatte ≥%1 geri düşen = "tepe yaptı" → 🔴 SHORT sinyali.
#                   Panelde sinyaller (SHORT aç düğmesiyle) ve "Tepe adayları" listesi, Telegram bildirimi. Bot short'a kendisi GİRMEZ:
#                   short'ları kullanıcı panelden açar (test edilmedi).
# v7.2 13.10 18:30  BORSA SIRALAMASI: panelde borsanın 24s en çok yükselen İLK 5 ve en çok düşen SON 5 coini (hisse/hariç/1M$ altı yok),
#                   her birinin "ne zamandır" o listede olduğu, son 1 saat değişimi ve LONG/SHORT aç düğmeleriyle. Süre bot açılınca sıfırlanır.
#                   "Durdur" düğmesi "🤖 Oto giriş: AÇIK/KAPALI" oldu (kapalıyken bot kendi açmaz; sinyal, elle açma ve pozisyon yönetimi sürer).
# v7.3 13.10 18:45  TEPE / DİP ZAMANI: sıralamada ve tepe/dip listelerinde her coinin son 7 günün zirvesini (yükselenler) ya da dibini
#                   (düşenler) NE ZAMAN gördüğü ("3 sa önce", "2 gün önce") ve şu an o tepenin ne kadar altında / dibin ne kadar üstünde olduğu.
#                   Bilgi coin adının altında (telefonda taşmaz); LONG/SHORT düğmeleri alt alta. Panel başlığında CANLI SAAT (İsveç saati,
#                   saniyede bir) ve "son güncelleme" göstergesi; sürüm ayrı yazılır (eskiden sürüm tarihi saat sanılabiliyordu).
VERSIYON = "v7.3 (13.10 18:45)"

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
DOSYA, KAYIT = KLASOR + "ayar6.json", KLASOR + "islem.jsonl"
HARIC = "BTC ETH XRP ADA DOGE SOL BNB LTC BCH TRX LINK DOT AVAX XLM ETC ATOM SHIB PEPE".split()
HISSE = set()                               # hisse/altın/emtia: açılışta borsadan otomatik doldurulur (isRwa)

# ───────────────────────── ayarlar ─────────────────────────
A = {"v": 6, "calis": True, "marjin": 1.0, "lev": 10, "max_pos": 3, "sl": 0.0, "tp": 0.5, "cikis": "kilit", "net": 0.3, "iz": 0.3,
     "liste": 30, "minp": 10.0, "don": 1.0, "gunluk": 5.0, "bekle": 15, "elle": True, "short_oto": False, "haric": list(HARIC)}
# panelde gösterilen ayarlar: anahtar -> (başlık, seçenekler, yazım)
AYAR = {
    "liste":  ("DÜŞENLER LİSTESİ (ilk kaç coin)",        (10, 20, 30),              lambda v: f"İlk {v}"),
    "minp":   ("EN AZ 24 SAATLİK DÜŞÜŞ",                 (5.0, 10.0, 15.0, 20.0),   lambda v: f"%-{v:g}"),
    "don":    ("DİBİ GÖRMÜŞ: SON 1 SAATTE TOPARLANMA",    (0.0, 1.0, 2.0),           lambda v: f"≥%{v:g}" if v else "Bakma"),
    "cikis":  ("ÇIKIŞ ŞEKLİ",                            ("kilit", "tp"),           lambda v: {"kilit": "Kâr kilitle + iz süren", "tp": "Sabit kâr al"}[v]),
    "net":    ("KİLİT: NET KÂR (1$ marjin için)",         (0.2, 0.3, 0.5),           lambda v: f"+{v:g}$"),
    "iz":     ("İZ SÜREN: ZİRVEDEN GERİ PAY (1$ için)",   (0.2, 0.3, 0.5),           lambda v: f"{v:g}$"),
    "tp":     ("SABİT KÂR AL (1$ marjin için)",           (0.3, 0.5, 0.8, 1.0),      lambda v: f"+{v:g}$"),
    "sl":     ("ZARAR STOPU (marjinin oranı)",           (0.0, 0.5, 0.8),           lambda v: f"%{v*100:g}" if v else "Yok"),
    "marjin": ("MARJİN (işlem başı)",                   (1.0, 2.0, 3.0, 5.0),      lambda v: f"{v:g}$"),
    "lev":    ("KALDIRAÇ (en çok)",                     (5, 10, 20),               lambda v: f"{v}x"),
    "max_pos": ("AYNI ANDA İŞLEM",                      (1, 2, 3, 5),              lambda v: str(v)),
    "gunluk": ("GÜNLÜK ZARAR LİMİTİ",                   (2.0, 3.0, 5.0, 10.0, 0.0), lambda v: f"-{v:g}$" if v else "Yok"),
    "bekle":  ("AYNI COİNE TEKRAR (kârdan sonra)",      (5, 15, 30, 60),           lambda v: f"{v} dk"),
}
acik, yasak, gecmis, lev_cap = {}, {}, [], {}
EGRI = []                                   # [[ts, toplam bakiye]] yarım saatte bir (web paneli bakiye eğrisi)
ADAY = {"t": 0, "liste": [], "tepe": []}                # son taramanın sonucu (panelde "Adaylar")
KIL = threading.RLock()
try:
    d = json.load(open(DOSYA))
    if d.get("A", {}).get("v") == 6: A.update(d["A"])
    acik.update(d.get("acik", {})); gecmis.extend(d.get("gecmis", [])); lev_cap.update(d.get("cap", {})); EGRI.extend(d.get("egri", []))
except Exception: pass

def kaydet():
    try: json.dump({"A": A, "acik": acik, "gecmis": gecmis[-1500:], "cap": lev_cap, "egri": EGRI[-2000:]}, open(DOSYA, "w"))
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
         "t0": k.get("t"), "p24": k.get("p24"), "p1": k.get("p1"), "sira": k.get("sira"), "k": "e" if k.get("elle") else "d"}
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
    if not A["calis"]: return "🤖 OTO GİRİŞ KAPALI (sinyal + elle işlem)"
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

SON_HATA = [""]                             # son açılış denemesinin hata mesajı (web paneli gösterir)
def ac(sym, yon, son, p24, sira, p1=None, mj=None, lev_ust=None, elle_acilis=False):
    """İzole pozisyon aç (stop açıksa borsaya stop da koyar). elle_acilis: panelden açılan, en çok işlem sınırına dahil değil. Döner: True/False."""
    SON_HATA[0] = ""
    with KIL:
        if sym in acik: SON_HATA[0] = "bu coinde zaten açık pozisyon var"; return False
        if not elle_acilis and oto_sayi() >= A["max_pos"]: return False
    mj = mj or A["marjin"]; lev, hata = 0, ""
    for l in [l for l in LADDER if l <= min(lev_ust or A["lev"], lev_cap.get(sym, 999)) and 70 * (1 / l - 0.0105) >= MIN_SL_PCT]:
        ok, g, h = kaldirac_ayarla(sym, l, yon); hata = h or hata
        if ok and (g is None or abs(g - l) < 0.5): lev = l; break
        if ok and g is not None and g < l: lev_cap[sym] = int(g)
    if not lev:
        yasak[sym] = time.time() + 6 * 3600
        if hata: haber(f"⚠️ {ad(sym)} kaldıraç ayarlanamadı, atlandı: {hata}")
        SON_HATA[0] = "kaldıraç ayarlanamadı " + hata[:80]; return False
    cs = ex.market(sym).get("contractSize") or 1
    adet = ex.amount_to_precision(sym, mj * lev / son / cs)
    if float(adet) * cs * son < 5.2:                                                         # borsanın en küçük emir tutarının altında
        if not elle_acilis: yasak[sym] = time.time() + 6 * 3600
        SON_HATA[0] = f"pozisyon {float(adet) * cs * son:.2f}$, borsanın en küçük emri 5$ (marjin ya da kaldıracı artır)"; return False
    try:
        ex.create_order(sym, "market", yon, float(adet), params={"marginMode": "isolated"})
    except Exception as e:
        if "40797" in str(e):          # borsa bu kaldıracı kabul etmiyor: bir basamak düşür, sonraki sinyalde dene
            alt = [l for l in LADDER if l < lev]
            if alt: lev_cap[sym] = alt[0]; yasak[sym] = time.time() + 20; haber(f"ℹ️ {ad(sym)} {lev}x kabul edilmedi, sonraki sinyalde {alt[0]}x denenecek"); return False
        yasak[sym] = time.time() + 3600; haber(f"⚠️ {ad(sym)} açılamadı: {str(e)[:120]}"); SON_HATA[0] = str(e)[:120]; return False
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
    sl = round(A["sl"] * mj, 3) if A["sl"] else None; not_ = ""; fy = None
    try: liq = float(p.get("liquidationPrice") or 0)
    except Exception: liq = 0.0
    if sl and liq and sl / (adet_f * cs) > 0.7 * abs(gir - liq):          # stop likidasyondan ÖNCE gelsin
        sl = round(0.7 * abs(gir - liq) * adet_f * cs, 3); not_ = " (likidasyona yakın, daraltıldı)"
    with KIL:
        acik[sym] = {"zirve": 0.0, "mj": mj, "sl": sl, "son": 0.0, "t": int(time.time()), "y": p["side"], "lev": lev, "p24": round(p24, 1) if p24 is not None else None,
                     "sira": sira, "p1": round(p1, 1) if p1 is not None else None, "elle_acilis": elle_acilis}
        if sl: fy = borsa_stop(sym, p, acik[sym], -min(sl * 1.2, 0.85 * mj))
        kaydet()
    haber(f"{'🟢 LONG' if yon == 'buy' else '🔴 SHORT'} {ad(sym)} · {lev}x izole · {mj:g}$\n"
          + ("Sebep: ✋ panelden elle açıldı\n" if elle_acilis else
             f"Sebep: 24 saatte %{p24:+.1f} (düşenlerde {sira}. sıra)" + (f", son 1 saatte %{p1:+.1f} toparlandı" if p1 is not None else "") + "\n") +
          f"Giriş {gir:g}\n" + cikis_yazi(mj, lev) + "\n"
          + (f"🛑 Stop −{sl:g}${not_} ≈ {sl_fiyat(yon, gir, adet_f, cs, sl):g}" + (f" (borsada: {fy})" if fy else "") if sl
             else f"🛑 Stop YOK · likidasyon ≈ {liq:g} (zarar en fazla {mj:g}$)"))
    return True

def kilit_seviye(mj, lev):
    """İlk kilit ($, brüt): net hedef + komisyon + kayma payı. e0: kilidin devreye girdiği kâr."""
    kl1 = (A["net"] + 0.0012 * lev + 0.03) * mj
    return kl1, kl1 + 0.05 * mj

def cikis_yazi(mj, lev):
    if A["cikis"] == "tp": return f"🎯 Kâr al: +{A['tp'] * mj:.2f}$ (≈ fiyat +%{A['tp'] * 100 / lev:.1f})"
    kl1, e0 = kilit_seviye(mj, lev)
    return f"🔒 Kâr +{e0:.2f}$ olunca +{kl1:.2f}$ kilitlenir (net ≈ +{A['net'] * mj:.2f}$), sonra zirvenin {A['iz'] * mj:.2f}$ gerisinden takip"

POZ_C = {"list": [], "t": 0}               # son pozisyon okuması (web paneli bunu kullanır, borsaya ek yük yok)

def yonet():
    """Açık pozisyonları yönet: kâr al (+tp), stop açıksa zarar stopu. 2 sn'de bir çalışır."""
    with KIL:
        pos = [p for p in ex.fetch_positions() if p.get("contracts")]
        var = {p["symbol"] for p in pos}
        for s in [s for s in acik if s not in var]:          # borsada kapanmış (stop emri / elle / likidasyon)
            k = acik.pop(s); borsa_stop_iptal(s, k.get("sid")); son = k.get("son", 0.0)
            if k.get("kilit") is not None: son, neden = k["kilit"], "KİLİT (borsa)"          # borsadaki kilit stopu çalıştı
            elif son <= -0.6 * k.get("mj", 1): neden = "LİKİDASYON" if not k.get("sl") else "STOP (borsa)"
            else: neden = "BORSADA KAPANDI"
            logla(s, k.get("y", "?"), son, neden, k)
            yasak[s] = time.time() + (A["bekle"] * 60 if son > 0 else max(A["bekle"] * 60, 2 * 3600))
            haber(f"{'✅' if son > 0 else '❌'} {ad(s)} borsada kapandı: {neden}\nPnL ≈ {son:+.2f}$ (gerçek rakam birazdan Geçmiş'e yazılır)")
        for p in pos:
            sym = p["symbol"]; pnl = p.get("unrealizedPnl") or 0.0
            if sym not in acik:                               # elle açılan pozisyon
                if not A["elle"]: continue
                mj = float(p.get("initialMargin") or A["marjin"])
                acik[sym] = {"zirve": max(pnl, 0.0), "mj": mj, "sl": round(A["sl"] * mj, 3) if A["sl"] else None, "son": pnl, "t": int(time.time()), "y": p["side"], "elle": True}
                haber(f"ℹ️ {ad(sym)}: elle açılan pozisyon devralındı (kâr al +{A['tp'] * mj:.2f}$, " + (f"stop −{acik[sym]['sl']:g}$)" if acik[sym]["sl"] else "stop yok)"))
            k = acik[sym]; k["son"] = pnl; k["zirve"] = max(k["zirve"], pnl); mj = k["mj"]
            if A["cikis"] == "tp":
                if pnl >= A["tp"] * mj: kapat(sym, p, "KÂR AL"); continue
            else:
                try: lev = float(p.get("leverage") or k.get("lev") or 10)
                except Exception: lev = 10.0
                kl1, e0 = kilit_seviye(mj, lev)
                if k["zirve"] >= e0:                           # kilit: en az ilk kilit, sonra zirvenin "iz" kadar gerisi
                    yeni = max(kl1, k["zirve"] - A["iz"] * mj)
                    if k.get("kilit") is None: haber(f"🔒 {ad(sym)} kâr kilitlendi: +{yeni:.2f}$ (pnl {pnl:+.2f}$), kilit zirveyi takip edecek")
                    k["kilit"] = max(k.get("kilit") if k.get("kilit") is not None else -9e9, yeni)
            if k.get("kilit") is not None and k["kilit"] >= k.get("bsk", -9) + 0.05 * mj:
                borsa_stop(sym, p, k, k["kilit"]); k["bsk"] = k["kilit"]              # borsaya kilit stopu (başarısız olsa da aynı seviyeyi tekrar deneme)
            if k.get("kilit") is not None and pnl <= k["kilit"]: kapat(sym, p, "KÂR KORUMA" if k.get("koru") and k["kilit"] < 0.3 * mj else "KİLİT"); continue
            if k.get("sl") and k.get("kilit") is None and pnl <= -k["sl"]: kapat(sym, p, "STOP")
        POZ_C["list"], POZ_C["t"] = pos, time.time()
        kaydet()

# ───────────────────────── strateji: en çok düşüp dibi görmüş coinlere long ─────────────────────────
tarama_bid, son_tarama = [0], [0.0]
SIN_BILDIRIM = {}                           # sembol -> son "bot giremedi" sinyal bildirimi zamanı
TICK = {}                                   # sembol -> (fiyat, 24s %): elle işlem açma ekranı için

def dusenler():
    """Borsanın 24s en çok düşenler sıralaması (hisse/emtia, hariç listesi ve hacmi 1M$ altı olanlar yok). Döner: [(sembol, fiyat, 24s %)], en çok düşen başta."""
    L = []
    for s, t in ex.fetch_tickers().items():
        if not s.endswith(":USDT") or not t.get("last"): continue
        try: TICK[s] = (float(t["last"]), float(t.get("percentage") if t.get("percentage") is not None else float((t.get("info") or {}).get("change24h") or 0) * 100))
        except Exception: pass
        b = temiz(s)
        if b in HISSE or (ex.markets.get(s, {}).get("base") in HISSE) or b in A["haric"]: continue
        if float(t.get("quoteVolume") or 0) < MIN_HACIM: continue
        p24 = t.get("percentage")
        if p24 is None:
            try: p24 = float((t.get("info") or {}).get("change24h")) * 100
            except Exception: continue
        HEPSI.append((float(p24), s, float(t["last"])))
        if float(p24) <= -A["minp"]: L.append((float(p24), s, float(t["last"])))
        if float(p24) >= A["minp"]: YUK.append((float(p24), s, float(t["last"])))
    L.sort()
    return [(s, c, p) for p, s, c in L[:A["liste"]]]

HEPSI = []                                  # dusenler() taramasında uygun TÜM coinler (borsa sıralaması için)
SIRA = {"ilk": [], "son": [], "t": 0}       # borsa sıralaması: ilk 5 yükselen / son 5 düşen
SIRA_T = {"ilk": {}, "son": {}}             # sembol -> o listeye giriş zamanı
BOT_T0 = time.time()
ZB = {}                                     # sembol -> (bid, bilgi): tepe/dip zamanı önbelleği (5 dk'da bir)
def zirve(sym, c, bid):
    """Son 7 günün (1s mumlar) zirvesi ve dibi: kaç saat önce görüldü, şu an ondan % uzaklık. Döner dict veya None."""
    o = ZB.get(sym)
    if o and o[0] == bid: return o[1]
    try:
        m = ex.fetch_ohlcv(sym, "1h", limit=168)
        if not m: return None
        hi = max(m, key=lambda x: float(x[2])); lo = min(m, key=lambda x: float(x[3]))
        H_, L_ = max(float(hi[2]), c), min(float(lo[3]), c); simdi = time.time()
        th = 0 if c >= float(hi[2]) else max(0, (simdi - int(hi[0]) / 1000 - 1800) / 3600)   # mumun ortası
        tl = 0 if c <= float(lo[3]) else max(0, (simdi - int(lo[0]) / 1000 - 1800) / 3600)
        b_ = {"tz": round(th, 1), "tf": round((c / H_ - 1) * 100, 1), "dz": round(tl, 1), "df": round((c / L_ - 1) * 100, 1)}
        ZB[sym] = (bid, b_); return b_
    except Exception: return None

def sira_guncelle(bid):
    L = sorted(HEPSI, reverse=True); HEPSI.clear()
    if len(L) < 10: return
    simdi = time.time()
    for ad_, grup in (("ilk", L[:5]), ("son", L[-5:][::-1])):
        eski = SIRA_T[ad_]; yeni = {}; out = []
        for n, (p, s, c) in enumerate(grup):
            yeni[s] = eski.get(s, simdi)
            out.append({"s": ad(s).split("/")[0], "sym": s, "p24": round(p, 1), "p1": bir_saat(s, c, bid), "sira": n + 1,
                        "dk": int((simdi - yeni[s]) / 60), "en_az": yeni[s] <= BOT_T0 + 60, "z": zirve(s, c, bid)})
        SIRA_T[ad_] = yeni; SIRA[ad_] = out
    SIRA["t"] = int(simdi)

YUK = []                                    # dusenler() taramasında toplanan yükselenler (tepe adayları için)
def yukselenler():
    L = sorted(YUK, reverse=True)[:A["liste"]]; YUK.clear()
    return [(s, c, p) for p, s, c in L]

def bir_saat(sym, son, bid):
    """Son 1 saatlik değişim (%), 5 dk mumlardan, zaman damgasına göre. Okunamazsa None."""
    try:
        m = ex.fetch_ohlcv(sym, "5m", limit=16)
        ac_ = {int(x[0]) // 1000: float(x[1]) for x in m}
        r60 = ac_.get(bid * BAR - 3600)
        if r60 is None and len(m) >= 14: r60 = float(m[-13][1]) if int(m[-1][0]) // 1000 >= bid * BAR else float(m[-12][1])
        return (son / r60 - 1) * 100 if r60 else None
    except Exception: return None

def oto_sayi():
    """Otomatik açılan (elle açılmamış / devralınmamış) pozisyon sayısı: en çok işlem sınırı sadece bunlara uygulanır."""
    return sum(1 for k in acik.values() if not k.get("elle") and not k.get("elle_acilis"))

def uygun(s):
    return s not in acik and time.time() >= yasak.get(s, 0)

def tarama_adimi():
    """Her 5 dakikanın başında BİR kez çalışır: düşenler listesini oku, dibi görmüş olanlara (son 1 saatte toparlanan) sırayla LONG aç."""
    simdi = time.time(); bid = int(simdi // BAR)
    if tarama_bid[0] == bid: return
    tarama_bid[0] = bid; taze = simdi - bid * BAR < 45          # bot yeni açıldıysa ilk tarama sadece ekran için, giriş yok
    YUK.clear(); HEPSI.clear(); L = dusenler(); T_ = yukselenler(); liste = []
    try: sira_guncelle(bid)
    except Exception as e: print("sıralama hatası:", e)
    for n, (s, c, p) in enumerate(L):
        p1 = bir_saat(s, c, bid) if A["don"] else None
        hazir = (not A["don"]) or (p1 is not None and p1 >= A["don"])
        liste.append({"s": ad(s), "sym": s, "c": c, "p24": p, "p1": p1, "sira": n + 1, "hazir": hazir, "acik": s in acik, "yasak": time.time() < yasak.get(s, 0)})
    tepe = []
    for n, (s, c, p) in enumerate(T_):
        p1 = bir_saat(s, c, bid) if A["don"] else None
        hazir = (not A["don"]) or (p1 is not None and p1 <= -A["don"])
        tepe.append({"s": ad(s), "sym": s, "c": c, "p24": p, "p1": p1, "sira": n + 1, "hazir": hazir, "acik": s in acik, "yasak": time.time() < yasak.get(s, 0), "yon": "sell"})
    for x in liste[:15] + tepe[:15]:
        x["z"] = zirve(x["sym"], x["c"], bid)
    ADAY["t"], ADAY["liste"], ADAY["tepe"] = int(time.time()), liste, tepe; son_tarama[0] = time.time()
    if not taze: return
    if not A["calis"] or limit_doldu(): sinyal_bildir(liste); sinyal_bildir(tepe); return
    for x in liste:                                             # en çok düşmüş olandan başla
        with KIL:
            if oto_sayi() >= A["max_pos"]: break
        if not x["hazir"] or not uygun(x["sym"]): continue
        try: ac(x["sym"], "buy", x["c"], x["p24"], x["sira"], x["p1"])
        except Exception as e: haber(f"⚠️ {x['s']} giriş hatası: {str(e)[:120]}")
    if A.get("short_oto"):
        for x in tepe:
            with KIL:
                if oto_sayi() >= A["max_pos"]: break
            if not x["hazir"] or not uygun(x["sym"]): continue
            try: ac(x["sym"], "sell", x["c"], x["p24"], x["sira"], x["p1"])
            except Exception as e: haber(f"⚠️ {x['s']} short giriş hatası: {str(e)[:120]}")
    sinyal_bildir(liste); sinyal_bildir(tepe)

def sinyal_bildir(liste):
    """Bot hazır bir sinyale giremediyse (yer dolu / durdu / limit) Telegram'a haber ver: coin başına saatte en çok bir kez."""
    neden = "bot durduruldu" if not A["calis"] else ("günlük limit doldu" if limit_doldu() else f"yer dolu ({oto_sayi()}/{A['max_pos']})")
    for x in liste:
        s = x["sym"]; short = x.get("yon") == "sell"
        if not x["hazir"] or s in acik or time.time() < yasak.get(s, 0) or time.time() - SIN_BILDIRIM.get(s, 0) < 3600: continue
        SIN_BILDIRIM[s] = time.time()
        n_ = "short'lar elle açılıyor" if short and not A.get("short_oto") else neden
        haber(f"🔔 SİNYAL: {x['s']} " + ("🔴 SHORT" if short else "🟢 LONG") + f"\n24 saatte %{x['p24']:+.1f}, son 1 saatte %{(x['p1'] or 0):+.1f} "
              + ("geri düştü (tepe yaptı)" if short else "toparlandı (dip yaptı)") + f"\nBot girmedi: {n_}. Web panelinden elle açabilirsin.")

# ───────────────────────── panel ─────────────────────────
B = types.InlineKeyboardButton
POZ = {}

def pozlar():
    ps = [p for p in ex.fetch_positions() if p.get("contracts")]
    POZ.clear(); POZ.update({n: p["symbol"] for n, p in enumerate(ps)}); return ps

def strateji_yazi():
    return (f"Sadece LONG: 24 saatte en az %{A['minp']:g} düşmüş ilk {A['liste']} coin"
            + (f", son 1 saatte ≥%{A['don']:g} toparlananlar" if A["don"] else "")
            + (f" · kâr al +{A['tp'] * A['marjin']:.2f}$ · " if A["cikis"] == "tp" else f" · kâr kilidi +{A['net'] * A['marjin']:.2f}$ + iz süren · ")
            + (f"stop −{A['sl'] * A['marjin']:.2f}$" if A["sl"] else "stop YOK"))

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
            sl = a.get("sl"); mj = a.get("mj", A["marjin"]); tp = A["tp"] * mj
            dk = int((time.time() - a["t"]) / 60) if a.get("t") else 0
            try: liq = float(p.get("liquidationPrice") or 0)
            except Exception: liq = 0.0
            sat.append(f"{n+1}) {'🟢 LONG' if p['side'] == 'long' else '🔴 SHORT'} {ad(p['symbol'])} {p.get('leverage') or '?'}x · {dk} dk\n"
                       f"   PnL {(p.get('unrealizedPnl') or 0):+.2f}$ (zirve {a.get('zirve', 0):+.2f}$)\n"
                       + (f"   giriş {g:g} | 🔒 kilit +{a['kilit']:.2f}$ ≈ {sl_fiyat(p['side'], g, adet, cs, -a['kilit']):g}\n" if a.get("kilit") is not None
                          else f"   giriş {g:g} | kâr al {sl_fiyat(p['side'], g, adet, cs, -tp):g} (+{tp:.2f}$)\n" if A["cikis"] == "tp"
                          else f"   giriş {g:g} | kilit +{kilit_seviye(mj, float(p.get('leverage') or 10))[1]:.2f}$'da başlar\n")
                       + (f"   stop {sl_fiyat(p['side'], g, adet, cs, sl):g} (−{sl:.2f}$)" if sl else f"   stop yok · likidasyon {liq:g}"))
            k.row(B(f"❌ {n+1}. {ad(p['symbol']).split('/')[0]} kapat", callback_data=f"k{n}"))
        k.row(geri, B("🔄 Yenile", callback_data="poz"))
        return "📋 AÇIK POZİSYONLAR\n\n" + ("\n\n".join(sat) or "Açık pozisyon yok."), k
    if e == "aday":
        k.row(geri, B("🔄 Yenile", callback_data="aday")); L = ADAY["liste"]
        if not ADAY["t"]: return "🔎 ADAYLAR\n\nHenüz tarama yapılmadı (ilk tarama en geç 5 dk içinde).", k
        sat = []
        for x in L[:30]:
            im = "📌 açık" if x["acik"] else ("⏱ beklemede" if x["yasak"] else ("✅ hazır" if x["hazir"] else "⏳ dip bekleniyor"))
            p1 = f" · 1s %{x['p1']:+.1f}" if x.get("p1") is not None else ""
            sat.append(f"{x['sira']:>2}. {x['s'].split('/')[0]}  %{x['p24']:+.1f}{p1}  {im}")
        return (f"🔎 DÜŞENLER (son tarama {saat(ADAY['t'])[-5:]})\nBot boş yer oldukça listenin en üstündeki hazır coine LONG açar.\n\n"
                + ("\n".join(sat) or f"Şu an 24 saatte %{A['minp']:g}'dan fazla düşen coin yok.")), k
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
        return (f"⚙️ AYARLAR\n\n🎯 {strateji_yazi()}\n\n💵 {A['marjin']:g}$ izole · ≤{A['lev']}x · en çok {A['max_pos']} işlem\n"
                + cikis_yazi(A["marjin"], A["lev"]) + "\n"
                + (f"🛑 Zarar stopu: −{A['sl'] * A['marjin']:.2f}$ (borsada da durur)\n" if A["sl"] else f"🛑 Zarar stopu YOK: işlem başı zarar en fazla marjin ({A['marjin']:g}$), likidasyonla kapanır\n")
                + f"📉 Günlük zarar limiti: {('−' + format(A['gunluk'], 'g') + '$') if A['gunluk'] else 'yok'}\n"
                f"⏱ Tekrar giriş: kârdan sonra {A['bekle']} dk, zarardan sonra 2 saat"), k
    if e == "yardim":
        k.row(geri)
        return ("❓ YARDIM\n\nBot ne yapar: Bitget vadeli listesini 24 saatlik değişime göre sıralar ve en çok düşen coinlere bakar (hisse/emtia hariç). "
                "Son 1 saatte toparlanmaya başlamış olanlara (dibi görmüş) LONG açar. Short açmaz. Her 5 dakikada bir tarar.\n\n"
                "Çıkış: varsayılan olarak kâr belli seviyeye gelince KİLİTLENİR (borsaya stop konur) ve kilit zirveyi takip eder; panelden sabit kâr al da seçilebilir. Zarar stopu varsayılan olarak YOK: işlem ters giderse likidasyonla kapanır ve o işlemin marjini kaybedilir.\n\n"
                "Dürüst not: 31 günlük gerçek veride bu kural başa baş civarında çıktı (bir dönem hafif eksi, bir dönem hafif artı). "
                "İşlemlerin yaklaşık dörtte biri likidasyonla kapandı. Kâr garantisi yoktur.\n\n"
                "Komutlar:\n/panel – ana menü\n/adaylar – düşenler listesi\n/gecmis – son işlemler\n/ozet – istatistik\n"
                "/haric – hariç coin listesi (ekle/sil)\n/kayit – tüm işlemlerin dosyası"), k
    if e == "hep":
        k.row(B("✅ Evet, HEPSİNİ kapat", callback_data="hepE"), B("❌ Vazgeç", callback_data="ana"))
        return "🚨 Tüm pozisyonlar kapatılsın mı? (Otomatik giriş de durur)", k
    ps = pozlar(); n = len(ps); ucan = sum(p.get("unrealizedPnl") or 0 for p in ps)
    k.row(B("🤖 Oto giriş: AÇIK → kapat" if A["calis"] else "🤖 Oto giriş: KAPALI → aç", callback_data="tog"))
    k.row(B(f"📋 Pozisyonlar ({n})", callback_data="poz"), B("🔎 Düşenler", callback_data="aday"))
    k.row(B("📜 Geçmiş", callback_data="gec"), B("📊 Özet", callback_data="ozet"))
    k.row(B("⚙️ Ayarlar", callback_data="ayar"), B("❓ Yardım", callback_data="yardim"))
    k.row(B("🚨 Tümünü Kapat", callback_data="hep"), B("🔄 Yenile", callback_data="ana"))
    tr = f"{int(time.time() - son_tarama[0])} sn önce" if son_tarama[0] else "bekleniyor"
    return (f"👻 GHOST DİP · {VERSIYON}\n━━━━━━━━━━━━━━━━\n{durum()}\n\n"
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

# ───────────────────────── web paneli (canlı) ─────────────────────────
import base64
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
PANEL_SIFRE = E("PANEL_SIFRE", "")
BAK = {"top": 0.0, "bos": 0.0, "t": 0}
MJ_EL, LEV_EL = (1.0, 2.0, 3.0, 5.0), (5, 10, 20)

def bakiye_dongu():
    """20 sn'de bir bakiye; yarım saatte bir bakiye eğrisine nokta."""
    while True:
        try:
            u = ex.fetch_balance().get("USDT") or {}
            BAK.update(top=float(u.get("total") or 0), bos=float(u.get("free") or 0), t=time.time())
            if BAK["top"] > 0 and (not EGRI or time.time() - EGRI[-1][0] >= 1800):
                EGRI.append([int(time.time()), round(BAK["top"], 3)]); kaydet()
        except Exception as e: print("bakiye hata", repr(e)[:120], flush=True)
        time.sleep(20)

def poz_veri(p):
    sym = p["symbol"]; k = acik.get(sym, {}); yon = 1 if p["side"] == "long" else -1
    mj = k.get("mj") or float(p.get("initialMargin") or A["marjin"])
    gir = float(p.get("entryPrice") or 0); adet = float(p["contracts"]); cs = float(p.get("contractSize") or 1)
    pnl = float(p.get("unrealizedPnl") or 0)
    c = float(p.get("markPrice") or 0) or (gir + pnl / (adet * cs) * yon if adet else gir)
    try: liq = float(p.get("liquidationPrice") or 0)
    except Exception: liq = 0.0
    try: lev = float(p.get("leverage") or k.get("lev") or A["lev"])
    except Exception: lev = float(A["lev"])
    fiyat = lambda usd: gir + usd / (adet * cs) * yon if adet else gir
    kilit, sl = k.get("kilit"), k.get("sl")
    if A["cikis"] == "tp": hedef_usd, hedef_ad = A["tp"] * mj, "kâr al"
    else: hedef_usd, hedef_ad = kilit_seviye(mj, lev)[1], "kilit başlar"
    hedef_f = fiyat(hedef_usd)
    sol = liq if liq else fiyat(-mj)
    sag = max(hedef_f * yon, fiyat(k.get("zirve", 0.0)) * yon, c * yon) * yon
    def konum(x):
        d = (x - gir) * yon
        v = 50 * (1 + d / abs(gir - sol)) if d < 0 and gir != sol else (50 + 50 * d / abs(sag - gir) if sag != gir else 50)
        return round(max(2, min(98, v)), 1)
    return {"s": ad(sym).split("/")[0], "sym": sym, "y": p["side"], "lev": lev, "gir": gir, "c": c, "pnl": round(pnl, 3),
            "yuzde": round((c / gir - 1) * 100 * yon, 2) if gir else 0, "mj": mj, "liq": liq, "liq_uz": round(abs(c - liq) / c * 100, 1) if liq and c else None,
            "kilit": kilit, "kilit_f": fiyat(kilit) if kilit is not None else None, "kilit_pos": konum(fiyat(kilit)) if kilit is not None else None,
            "hedef_ad": hedef_ad, "hedef_usd": round(hedef_usd, 2), "hedef_f": hedef_f, "sl": sl, "sl_f": fiyat(-sl) if sl else None,
            "pos": konum(c), "dk": int((time.time() - k["t"]) / 60) if k.get("t") else None, "elle": bool(k.get("elle") or k.get("elle_acilis")),
            "yonetim": bool(k), "koru": bool(k.get("koru"))}

def api_veri():
    with KIL:
        P = [poz_veri(p) for p in POZ_C["list"] if p.get("contracts")]
        G = list(gecmis)
    w = [g["pnl"] for g in G if g["pnl"] > 0]; l = [g["pnl"] for g in G if g["pnl"] <= 0]
    ok_ = sum(w) / len(w) if w else 0; oz = sum(l) / len(l) if l else 0
    adaylar = []
    for x in ADAY["liste"]:
        p1 = x.get("p1"); kalan = round(A["don"] - p1, 2) if (A["don"] and p1 is not None and p1 < A["don"]) else None
        d = "acik" if x["sym"] in acik else ("yasak" if time.time() < yasak.get(x["sym"], 0) else
             ("hazir" if x["hazir"] else ("dusuyor" if (p1 is not None and p1 < 0) else "bek")))
        adaylar.append({"s": x["s"].split("/")[0], "sym": x["sym"], "p24": round(x["p24"], 1), "p1": round(p1, 2) if p1 is not None else None, "kalan": kalan, "d": d, "z": x.get("z"),
                        "dol": 100 if x["hazir"] else (max(0, min(100, p1 / A["don"] * 100)) if (A["don"] and p1 is not None) else 0)})
    tepeler = []
    for x in ADAY.get("tepe", []):
        p1 = x.get("p1"); kalan = round(A["don"] + p1, 2) if (A["don"] and p1 is not None and p1 > -A["don"]) else None
        d = "acik" if x["sym"] in acik else ("yasak" if time.time() < yasak.get(x["sym"], 0) else
             ("hazir" if x["hazir"] else ("yukseliyor" if (p1 is not None and p1 > 0) else "bek")))
        tepeler.append({"s": x["s"].split("/")[0], "sym": x["sym"], "p24": round(x["p24"], 1), "p1": round(p1, 2) if p1 is not None else None, "kalan": kalan, "d": d, "z": x.get("z"),
                        "dol": 100 if x["hazir"] else (max(0, min(100, -p1 / A["don"] * 100)) if (A["don"] and p1 is not None) else 0)})
    bugun = [g for g in G if gun(g["t"]) == gun()]
    return {"v": VERSIYON, "calis": A["calis"], "durum": durum(), "limit": limit_doldu(),
            "bak": round(BAK["top"], 3), "bos": round(BAK["bos"], 3), "bugun": round(sum(g["pnl"] for g in bugun), 3), "bugun_n": len(bugun), "gunluk": A["gunluk"],
            "poz": P, "oto": oto_sayi(), "max_pos": A["max_pos"], "acik_pnl": round(sum(x["pnl"] for x in P), 3),
            "ozet": {"n": len(G), "kaz": len(w), "kaz_y": round(len(w) / len(G) * 100) if G else None, "gerek": round(abs(oz) / (abs(oz) + ok_) * 100) if w and l else None,
                     "ort_k": round(ok_, 2), "ort_z": round(oz, 2), "top": round(sum(g["pnl"] for g in G), 2)},
            "egri": EGRI[-400:], "sira": {"ilk": [dict(x, p1=round(x["p1"], 2) if x["p1"] is not None else None) for x in SIRA["ilk"]],
                                    "son": [dict(x, p1=round(x["p1"], 2) if x["p1"] is not None else None) for x in SIRA["son"]]}, "aday": adaylar, "tepe": tepeler, "short_oto": bool(A.get("short_oto")), "tarama": max(0, int(time.time() - son_tarama[0])) if son_tarama[0] else None, "don": A["don"],
            "gec": [{"s": g["s"].split("/")[0], "y": g["y"], "pnl": g["pnl"], "n": g["n"], "t": g["t"], "sure": int((g["t"] - g["t0"]) / 60) if g.get("t0") else None,
                     "kesin": g.get("g") == 1} for g in G[-40:][::-1]],
            "strateji": strateji_yazi(), "cikis_yazi": cikis_yazi(A["marjin"], A["lev"]),
            "ayar": [{"k": a, "t": t, "cur": A[a], "o": [{"v": v, "l": f(v)} for v in o]} for a, (t, o, f) in AYAR.items()], "elle": A["elle"],
            "mj_el": MJ_EL, "lev_el": LEV_EL, "mj_def": A["marjin"], "lev_def": A["lev"]}

def coin_listesi():
    L = []
    for s, m in ex.markets.items():
        if not (m.get("swap") and s.endswith(":USDT") and m.get("active", True)): continue
        if m.get("base") in HISSE: continue
        f, p24 = TICK.get(s, (None, None)); L.append({"s": m.get("base"), "sym": s, "c": f, "p24": round(p24, 1) if p24 is not None else None})
    return sorted(L, key=lambda x: x["s"])

def islem(d):
    """Panelden gelen komut. Döner: (ok, mesaj)."""
    act = d.get("act"); sym = d.get("sym")
    if act == "tog":
        A["calis"] = not A["calis"]; kaydet(); haber(f"{'🤖 Otomatik giriş AÇILDI' if A['calis'] else '🤖 Otomatik giriş KAPATILDI (sinyaller ve elle işlem devam)'} (web paneli)")
        return True, "Otomatik giriş açık" if A["calis"] else "Otomatik giriş kapalı: bot kendi açmaz, sinyaller/elle açma/yönetim sürer"
    if act == "ayar":
        degisen = []
        for a, v in (d.get("ayar") or {}).items():
            if a == "elle":
                if A["elle"] != bool(v): A["elle"] = bool(v); degisen.append("elle açılanları yönet")
                continue
            if a == "short_oto":
                if bool(A.get("short_oto")) != bool(v): A["short_oto"] = bool(v); degisen.append("otomatik SHORT " + ("AÇIK" if v else "kapalı"))
                continue
            if a not in AYAR: continue
            ops = AYAR[a][1]; m = next((o for o in ops if (o == v if isinstance(o, str) else abs(float(o) - float(v)) < 1e-9)), None)
            if m is None: return False, f"geçersiz değer: {a}"
            if A[a] != m: A[a] = m; degisen.append(f"{AYAR[a][0].split(' (')[0]} → {AYAR[a][2](m)}")
        kaydet()
        if degisen: haber("⚙️ Ayarlar web panelinden değişti: " + ", ".join(degisen))
        return True, "Ayarlar kaydedildi" if degisen else "Değişiklik yok"
    if act == "hep":
        with KIL:
            n = 0
            for p in ex.fetch_positions():
                if p.get("contracts"): kapat(p["symbol"], p, "MANUEL (panel)"); n += 1
        A["calis"] = False; kaydet()
        return True, f"{n} pozisyon kapatıldı, bot durduruldu"
    if act == "ac":
        q = str(sym or "").upper().replace("USDT", "").replace("/", "").replace(":", "").strip()
        s = sym if sym in ex.markets else f"{q}/USDT:USDT"
        if s not in ex.markets: return False, f"{q} bulunamadı"
        if ex.markets[s].get("base") in HISSE: return False, "hisse/emtia coinleri açılmıyor"
        yon = "sell" if d.get("yon") == "sell" else "buy"
        try: mj = float(d.get("mj")); lev = int(d.get("lev"))
        except Exception: return False, "marjin/kaldıraç hatalı"
        if mj not in MJ_EL or lev not in LEV_EL: return False, "marjin/kaldıraç seçeneklerin dışında"
        try:
            t = ex.fetch_ticker(s); c = float(t["last"]); p24 = t.get("percentage")
        except Exception as e: return False, f"fiyat alınamadı: {str(e)[:80]}"
        ok = ac(s, yon, c, p24, None, None, mj=mj, lev_ust=lev, elle_acilis=True)
        return (True, f"{q} {'LONG' if yon == 'buy' else 'SHORT'} açıldı") if ok else (False, "Açılamadı: " + (SON_HATA[0] or "bilinmeyen hata"))
    with KIL:
        p = poz_oku(sym) if sym else None
        if not p: return False, "pozisyon bulunamadı (kapanmış olabilir)"
        k = acik.get(sym); pnl = float(p.get("unrealizedPnl") or 0)
        if act == "kapat":
            kapat(sym, p, "MANUEL (panel)"); return True, f"{ad(sym)} kapatıldı ({pnl:+.2f}$)"
        if not k: return False, "bot bu pozisyonu yönetmiyor (Ayarlar: elle açılanları yönet)"
        mj = k["mj"]
        if act == "koru":
            if pnl < 0.06 * mj: return False, "pozisyon yeterince kârda değil"
            yeni = round(pnl - 0.03 * mj, 3)
            k["kilit"] = max(k["kilit"], yeni) if k.get("kilit") is not None else yeni; k["koru"] = True
            fy = borsa_stop(sym, p, k, k["kilit"]); k["bsk"] = k["kilit"]; kaydet()
            haber(f"🛡️ {ad(sym)} kâr koruma: fiyat geri düşerse en az +{k['kilit']:.2f}$ ile kapanır" + (f" (borsada stop {fy})" if fy else ""))
            return True, f"Kâr korundu: en az +{k['kilit']:.2f}$"
        if act == "stop":
            sl = 0.5 * mj if pnl > -0.45 * mj else min(0.9 * mj, -pnl + 0.1 * mj)
            k["sl"] = round(sl, 3)
            fy = borsa_stop(sym, p, k, -k["sl"]) if k.get("kilit") is None else None; kaydet()
            haber(f"🛑 {ad(sym)} stop eklendi: −{k['sl']:.2f}$" + (f" (borsada {fy})" if fy else ""))
            return True, f"Stop eklendi: en fazla −{k['sl']:.2f}$"
    return False, "bilinmeyen komut"

class Panel(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _izin(self):
        h = self.headers.get("Authorization", "")
        if h.startswith("Basic "):
            try:
                if base64.b64decode(h[6:]).decode().split(":", 1)[-1] == PANEL_SIFRE: return True
            except Exception: pass
        self.send_response(401); self.send_header("WWW-Authenticate", 'Basic realm="Ghost Dip"'); self.end_headers(); return False
    def _yaz(self, b, tip="application/json; charset=utf-8", kod=200):
        self.send_response(kod); self.send_header("Content-Type", tip); self.send_header("Cache-Control", "no-store"); self.end_headers(); self.wfile.write(b)
    def do_GET(self):
        if not self._izin(): return
        yol = self.path.split("?")[0].rstrip("/")
        try:
            if yol.endswith("/api/coinler"): self._yaz(json.dumps(coin_listesi(), ensure_ascii=False).encode())
            elif yol.endswith("/api"): self._yaz(json.dumps(api_veri(), ensure_ascii=False).encode())
            elif yol == "": self._yaz(SAYFA.encode(), "text/html; charset=utf-8")
            else: self._yaz(b"{}", kod=404)
        except Exception as e: self._yaz(json.dumps({"hata": str(e)[:200]}).encode(), kod=500)
    def do_POST(self):
        if not self._izin(): return
        try:
            n = int(self.headers.get("Content-Length") or 0); d = json.loads(self.rfile.read(n) or b"{}")
            ok, msg = islem(d)
        except Exception as e: ok, msg = False, str(e)[:200]
        self._yaz(json.dumps({"ok": ok, "msg": msg}, ensure_ascii=False).encode())

def panel_baslat():
    if not PANEL_SIFRE:
        print("Web paneli KAPALI: PANEL_SIFRE tanımlı değil (canlı hesap için şifresiz panel açılmaz)", flush=True); return
    port = int(E("PORT", "8080"))
    threading.Thread(target=lambda: ThreadingHTTPServer(("0.0.0.0", port), Panel).serve_forever(), daemon=True).start()
    print(f"Web paneli açık: port {port}", flush=True)

SAYFA = r"""<!doctype html><html lang="tr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Ghost Dip</title>
<style>
:root{--bg:#0b1020;--kart:#131a2e;--kart2:#1a2340;--cizgi:#26304f;--yazi:#e8ecf8;--soluk:#8b95b5;--yesil:#22d39b;--kirmizi:#ff5c7a;--sari:#ffc857;--mavi:#5b8cff;--mor:#a56bff}
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:radial-gradient(1200px 600px at 10% -10%,#163a4a 0,transparent 60%),radial-gradient(900px 500px at 110% 0,#3a1d5a 0,transparent 55%),var(--bg);color:var(--yazi);font:15px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;min-height:100vh}
.sar{max-width:1100px;margin:0 auto;padding:16px 16px 96px}
header{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:14px;flex-wrap:wrap}
.logo{font-weight:800;font-size:22px;background:linear-gradient(90deg,#22d39b,#5b8cff,#a56bff);-webkit-background-clip:text;background-clip:text;color:transparent}
.alt{color:var(--soluk);font-size:12px}.sag{display:flex;gap:8px;align-items:center}
.pill{display:inline-flex;align-items:center;gap:6px;font-size:12px;font-weight:700;padding:5px 10px;border-radius:99px}
.p-ok{color:var(--yesil);background:rgba(34,211,155,.12);border:1px solid rgba(34,211,155,.35)}.p-dur{color:var(--kirmizi);background:rgba(255,92,122,.12);border:1px solid rgba(255,92,122,.35)}
.nokta{width:8px;height:8px;border-radius:50%;background:currentColor;animation:nab 1.6s infinite}@keyframes nab{50%{opacity:.35}}
.btn{border:0;border-radius:12px;padding:9px 14px;font-weight:800;font-size:13px;color:#fff;cursor:pointer;font-family:inherit}.btn:disabled{opacity:.5}
.b-dur{background:linear-gradient(135deg,#ff5c7a,#d93a5c)}.b-bas{background:linear-gradient(135deg,#22d39b,#14a57a)}.b-ghost{background:#222c4c;color:var(--yazi);border:1px solid var(--cizgi)}.b-mor{background:linear-gradient(135deg,#5b8cff,#a56bff)}
.kartlar{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:14px}
.k{background:linear-gradient(160deg,var(--kart2),var(--kart));border:1px solid var(--cizgi);border-radius:16px;padding:14px;position:relative;overflow:hidden}
.k:before{content:"";position:absolute;inset:0 0 auto 0;height:3px;background:var(--renk,var(--mavi))}
.k .e{color:var(--soluk);font-size:11px;text-transform:uppercase;letter-spacing:.6px}.k .d{font-size:23px;font-weight:800;margin-top:4px;font-variant-numeric:tabular-nums}.k .a{font-size:12px;color:var(--soluk);margin-top:2px}
.pan{background:var(--kart);border:1px solid var(--cizgi);border-radius:16px;padding:14px;margin-bottom:14px;scroll-margin-top:12px}
.pan h2{margin:0 0 10px;font-size:15px;display:flex;align-items:center;gap:8px}.pan h2 .r{margin-left:auto;font-weight:500;color:var(--soluk);font-size:12px}
.art{color:var(--yesil)}.eks{color:var(--kirmizi)}
.rozet{display:inline-block;font-size:10px;font-weight:800;padding:2px 7px;border-radius:6px;margin-left:6px;letter-spacing:.4px}
.L{background:rgba(34,211,155,.15);color:var(--yesil)}.S{background:rgba(255,92,122,.15);color:var(--kirmizi)}.Y{background:rgba(255,200,87,.15);color:var(--sari)}.M{background:rgba(91,140,255,.15);color:var(--mavi)}
.gauge{height:10px;border-radius:99px;background:#0d1326;position:relative;margin-top:8px}.gauge i{position:absolute;inset:0 auto 0 0;border-radius:99px;background:linear-gradient(90deg,#5b8cff,#22d39b)}.gauge b{position:absolute;top:-4px;width:2px;height:18px;background:var(--sari)}
.poz{border:1px solid var(--cizgi);border-radius:14px;padding:12px;margin-bottom:10px;background:linear-gradient(160deg,#151d36,#121a30)}
.poz .ust{display:flex;align-items:center;gap:4px;flex-wrap:wrap}.poz .ust .kz{margin-left:auto;text-align:right;font-weight:800;font-size:17px}
.poz .bilgi{display:flex;justify-content:space-between;color:var(--soluk);font-size:12px;margin:6px 0 10px}
.yol{position:relative;height:12px;border-radius:99px;background:linear-gradient(90deg,rgba(255,92,122,.55),rgba(255,92,122,.12) 45%,rgba(34,211,155,.12) 55%,rgba(34,211,155,.55))}
.yol .giris{position:absolute;left:50%;top:-3px;width:2px;height:18px;background:#8b95b5}.yol .kilit{position:absolute;top:-3px;width:3px;height:18px;background:var(--sari)}
.yol .imlec{position:absolute;top:-5px;width:22px;height:22px;margin-left:-11px;border-radius:50%;background:#fff;border:4px solid var(--yesil);box-shadow:0 0 12px rgba(34,211,155,.6);transition:left .6s}
.yol .imlec.kir{border-color:var(--kirmizi);box-shadow:0 0 12px rgba(255,92,122,.6)}
.etiket{display:flex;justify-content:space-between;font-size:11px;color:var(--soluk);margin-top:6px;gap:6px}
.not2{font-size:12px;color:#c5cbe0;background:rgba(255,255,255,.04);border-radius:8px;padding:6px 8px;margin-top:8px}
.alt2{display:flex;gap:8px;margin-top:10px}.alt2 .btn{flex:1;padding:8px}
table{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums}th{color:var(--soluk);font-weight:600;font-size:11px;text-transform:uppercase;text-align:right;padding:6px;border-bottom:1px solid var(--cizgi)}
th:first-child,td:first-child{text-align:left}td{text-align:right;padding:9px 6px;border-bottom:1px solid rgba(38,48,79,.6);font-size:14px}
.chip{display:inline-block;padding:3px 8px;border-radius:99px;font-size:11px;font-weight:700;white-space:nowrap}
.c-y{background:rgba(34,211,155,.15);color:var(--yesil)}.c-g{background:rgba(139,149,181,.12);color:var(--soluk)}.c-m{background:rgba(91,140,255,.15);color:var(--mavi)}.c-k{background:rgba(255,92,122,.15);color:var(--kirmizi)}
.ac{background:linear-gradient(135deg,#22d39b,#14a57a);color:#fff;border:0;border-radius:8px;padding:5px 10px;font-weight:800;font-size:12px;cursor:pointer;margin-left:6px}
.dp{display:flex;align-items:center;gap:8px;justify-content:flex-end}.dbar{flex:1;height:8px;border-radius:99px;background:#0d1326;overflow:hidden;min-width:50px}.dbar i{display:block;height:100%;border-radius:99px}.dp span{font-size:12px;white-space:nowrap}
.sinyal{display:flex;align-items:center;gap:10px;border:1px solid rgba(34,211,155,.35);background:linear-gradient(135deg,rgba(34,211,155,.12),rgba(91,140,255,.08));border-radius:14px;padding:10px 12px;margin-bottom:8px}
.dp{flex-wrap:wrap;row-gap:4px}.dp .dbar{flex:1 1 60px;min-width:50px}.zz{font-size:11px;color:var(--soluk);font-weight:500;margin-top:2px;white-space:normal}.nw{white-space:nowrap}
table.sira td:nth-child(2),td.cz{text-align:left;max-width:150px}.ikib{display:flex;flex-direction:column;gap:4px;align-items:flex-end}
.saat{font-variant-numeric:tabular-nums;font-weight:700;color:var(--metin,#e8ecf8)}
.ikili{display:grid;grid-template-columns:1fr 1fr;gap:14px}@media(max-width:700px){.ikili{grid-template-columns:1fr}}.sbas{font-weight:700;font-size:14px;margin:4px 0 6px}
.sira td .mini{border:0;border-radius:8px;padding:4px 7px;font-weight:700;font-size:10px;color:#fff;cursor:pointer;margin:0}.mini.l{background:linear-gradient(135deg,#22d39b,#14a97a)}.mini.s{background:linear-gradient(135deg,#ff5c7a,#d93a5c)}
.sinyal.ss{border-color:rgba(255,92,122,.4);background:linear-gradient(135deg,rgba(255,92,122,.12),rgba(165,107,255,.08))}.sinyal b{font-size:16px}.sinyal .btn{margin-left:auto}
.ayar{margin-bottom:12px}.ayar .bas{font-size:12px;color:var(--soluk);margin-bottom:6px;display:flex;justify-content:space-between;gap:8px}
.seg{display:flex;gap:6px;flex-wrap:wrap}.seg span{flex:1;min-width:52px;text-align:center;padding:9px 6px;border-radius:10px;background:#0f1630;border:1px solid var(--cizgi);font-weight:700;font-size:13px;color:#c5cbe0;cursor:pointer;user-select:none}
.seg span.on{background:linear-gradient(135deg,rgba(91,140,255,.35),rgba(165,107,255,.35));border-color:#7c8cff;color:#fff}
.seg span.on.yl{background:rgba(34,211,155,.3);border-color:var(--yesil)}.seg span.on.kr{background:rgba(255,92,122,.3);border-color:var(--kirmizi)}
.anahtar{display:flex;align-items:center;justify-content:space-between;padding:10px 0;border-top:1px solid rgba(38,48,79,.6);gap:10px}
.tog{width:46px;height:26px;border-radius:99px;background:var(--yesil);position:relative;cursor:pointer;flex:none}.tog:after{content:"";position:absolute;right:3px;top:3px;width:20px;height:20px;border-radius:50%;background:#fff}.tog.off{background:#2a3352}.tog.off:after{right:auto;left:3px}
.ozet-ayar{background:rgba(91,140,255,.08);border:1px dashed rgba(91,140,255,.4);border-radius:12px;padding:10px;font-size:13px;color:#c5cbe0;margin-bottom:12px}
.genis{width:100%;padding:12px;font-size:15px}
input{width:100%;background:#0f1630;border:1px solid var(--cizgi);border-radius:10px;padding:11px 12px;color:var(--yazi);font:inherit;font-weight:700}
.iki{display:grid;grid-template-columns:1fr 1fr;gap:14px}.iki2{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.bos{color:var(--soluk);text-align:center;padding:14px;font-size:14px}
.uyari{background:rgba(255,200,87,.1);border:1px solid rgba(255,200,87,.4);color:var(--sari);padding:8px 12px;border-radius:12px;margin-bottom:12px;font-size:13px;display:none}
.nav{position:fixed;left:0;right:0;bottom:0;background:rgba(13,19,38,.95);border-top:1px solid var(--cizgi);display:flex;justify-content:space-around;padding:8px 0 14px;backdrop-filter:blur(8px);z-index:5}
.nav a{text-align:center;font-size:11px;color:var(--soluk);text-decoration:none}.nav a b{display:block;font-size:20px}
.toast{position:fixed;left:50%;bottom:86px;transform:translateX(-50%);background:#1f2a4d;border:1px solid var(--cizgi);padding:10px 16px;border-radius:12px;font-weight:700;font-size:14px;display:none;z-index:9;max-width:90%;text-align:center}
svg text{fill:var(--soluk)}
@media(max-width:820px){.kartlar{grid-template-columns:repeat(2,1fr)}.iki{grid-template-columns:1fr}.k .d{font-size:20px}}
</style></head><body><div class="sar">
<header><div><div class="logo">🌊 GHOST DİP</div><div class="alt">🕒 <span class="saat" id="saat">--:--:--</span> İsveç · <span id="guncel">bağlanıyor…</span></div><div class="alt" id="alt">CANLI HESAP · yükleniyor…</div></div>
<div class="sag"><span class="pill p-ok" id="durum"><span class="nokta"></span><span id="durumy">…</span></span><button class="btn b-dur" id="tog" onclick="tog()">🤖 Oto giriş</button></div></header>
<div class="uyari" id="uyari"></div>
<div class="kartlar">
 <div class="k" style="--renk:var(--mavi)"><div class="e">Bakiye</div><div class="d" id="bak">–</div><div class="a" id="bos"></div></div>
 <div class="k" id="kbug" style="--renk:var(--yesil)"><div class="e">Bugün</div><div class="d" id="bug">–</div><div class="a" id="bugn"></div></div>
 <div class="k" style="--renk:var(--mor)"><div class="e">Açık pozisyon</div><div class="d" id="npoz">–</div><div class="a" id="apnl"></div></div>
 <div class="k" style="--renk:var(--sari)"><div class="e">Kazanma</div><div class="d" id="kaz">–</div><div class="a" id="ger"></div><div class="gauge"><i id="gi" style="width:0"></i><b id="gb" style="display:none"></b></div></div>
</div>
<div class="pan" id="sinyaller"><h2>🔔 Sinyaller <span class="r" id="tarama"></span></h2><div id="sin"></div></div>
<div class="pan"><h2>📈 Bakiye eğrisi <span class="r">yarım saatte bir</span></h2><svg id="egri" viewBox="0 0 1000 200" preserveAspectRatio="none" style="width:100%;height:170px"></svg></div>
<div class="iki">
 <div class="pan" id="pozisyon"><h2>💼 Açık pozisyonlar <span class="r">canlı</span></h2><div id="poz"></div></div>
 <div class="pan" id="adaylar"><h2>🎯 Düşenler · dip adayları <span class="r">her 5 dk</span></h2>
  <div class="alt" style="margin-bottom:8px" id="aday_acik"></div><div id="aday"></div></div>
</div>
<div class="pan" id="sira"><h2>🏆 Borsa sıralaması <span class="r">24 saat · her 5 dk</span></h2>
 <div class="alt" style="margin-bottom:8px">Borsada en çok yükselen ilk 5 ve en çok düşen son 5 coin. Coin adının altında: son 7 günün tepesini/dibini <b>ne zaman</b> gördü, şu an ondan ne kadar uzakta ve ne zamandır listede.</div>
 <div class="ikili"><div><div class="sbas art">🚀 En çok yükselen 5</div><div id="sira_ilk"></div></div><div><div class="sbas eks">💥 En çok düşen 5</div><div id="sira_son"></div></div></div></div>
<div class="pan" id="tepeler"><h2>📉 Yükselenler · tepe adayları <span class="r">SHORT için · her 5 dk</span></h2>
 <div class="alt" style="margin-bottom:8px">Çok yükselmiş bir coin son 1 saatte <b>%1 geri düşünce</b> "tepe yaptı" sayılır ve 🔴 SHORT sinyali çıkar. Bot bunlara girmez, sen açarsın.</div><div id="tepe"></div></div>
<div class="pan" id="elle"><h2>➕ Elle işlem aç <span class="r">istediğin coine, sen karar ver</span></h2>
 <div class="ayar"><div class="bas"><span>COİN</span><span id="e_fiyat"></span></div><input id="e_coin" list="coinler" placeholder="🔎 coin yaz (örn. ERA)" autocomplete="off" oninput="eOzet()"><datalist id="coinler"></datalist></div>
 <div class="ayar"><div class="bas"><span>YÖN</span></div><div class="seg" id="e_yon"><span data-v="buy" class="on yl">🟢 LONG</span><span data-v="sell">🔴 SHORT</span></div></div>
 <div class="iki2"><div class="ayar"><div class="bas"><span>MARJİN</span></div><div class="seg" id="e_mj"></div></div><div class="ayar"><div class="bas"><span>KALDIRAÇ</span></div><div class="seg" id="e_lev"></div></div></div>
 <div class="ozet-ayar" id="e_ozet">Coin seç.</div>
 <button class="btn b-bas genis" onclick="elleAc()">İşlemi aç</button>
 <div class="alt" style="margin-top:8px;text-align:center">Açmadan önce onay sorulur. Çıkışı bot yönetir. Bu işlem otomatik işlem sayısına dahil edilmez.</div>
</div>
<div class="pan" id="ayarlar"><h2>⚙️ İşlem ayarları <span class="r">yeni açılan işlemlere uygulanır</span></h2>
 <div class="ozet-ayar" id="a_ozet"></div><div class="iki" id="a_seg"></div>
 <div class="anahtar"><span>Elle açtığım işlemleri bot yönetsin<br><span class="alt">Bitget'ten kendin açtığın pozisyonlara da kilit/stop uygular</span></span><div class="tog" id="a_elle" onclick="this.classList.toggle('off');degisti()"></div></div>
 <button class="btn b-mor genis" id="kaydet" onclick="ayarKaydet()">💾 Ayarları kaydet</button>
</div>
<div class="pan" id="gecmis"><h2>📜 Kapanan işlemler <span class="r" id="gec_r"></span></h2><div id="gec"></div></div>
</div>
<div class="nav"><a href="#"><b>🏠</b>Özet</a><a href="#pozisyon"><b>💼</b>Pozisyon</a><a href="#adaylar"><b>🎯</b>Dip</a><a href="#tepeler"><b>📉</b>Tepe</a><a href="#sira"><b>🏆</b>Sıra</a><a href="#elle"><b>➕</b>Elle aç</a><a href="#ayarlar"><b>⚙️</b>Ayarlar</a><a href="#gecmis"><b>📜</b>Geçmiş</a></div>
<div class="toast" id="toast"></div>
<script>
let D=null,COIN={},ayarDegisti=false,ayarCizildi=false,eYon='buy',eMj=null,eLev=null;
const $=id=>document.getElementById(id);
const f=(x,d=2)=>x==null?'–':Number(x).toLocaleString('tr-TR',{minimumFractionDigits:d,maximumFractionDigits:d});
const sg=(x,d=2)=>x==null?'–':(x>0?'+':'')+f(x,d);const rk=x=>x>0?'art':(x<0?'eks':'');
const fy=x=>x==null||!isFinite(x)?'–':(x>=100?f(x,2):x>=1?f(x,4):Number(x).toLocaleString('tr-TR',{maximumSignificantDigits:4}));
const sure=m=>m==null?'':(m>=60?Math.floor(m/60)+' sa '+(m%60)+' dk':m+' dk');
function toast(m,ok=true){const t=$('toast');t.textContent=m;t.style.borderColor=ok?'var(--yesil)':'var(--kirmizi)';t.style.display='block';clearTimeout(t._t);t._t=setTimeout(()=>t.style.display='none',3500)}
async function post(d){try{const r=await fetch('api/islem',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(d)});const j=await r.json();toast(j.msg,j.ok);yenile();return j}catch(e){toast('Bağlantı hatası',false)}}
function tog(){if(!D)return;if(confirm(D.calis?'Otomatik giriş KAPATILSIN mı?\nBot kendi işlem açmaz. Sinyaller, elle açma ve açık işlemlerin yönetimi devam eder.':'Otomatik giriş AÇILSIN mı?\nBot sinyallere kendisi de LONG açar.'))post({act:'tog'})}
function kapat(sym,s,p){if(confirm(`${s} pozisyonu şimdi kapatılsın mı?\nŞu anki sonuç: ${sg(p)} $`))post({act:'kapat',sym})}
function koru(sym,s,p){if(confirm(`${s}: kâr korunsun mu?\nFiyat geri düşerse işlem yaklaşık ${sg(p)} $ kârla kapanır (borsaya stop konur).`))post({act:'koru',sym})}
function stopEkle(sym,s){if(confirm(`${s} pozisyonuna zarar stopu eklensin mi?\n(Zarar yaklaşık 0,50 $'ı geçmesin diye; zaten bunun ötesindeyse biraz daha aşağıya konur.)`))post({act:'stop',sym})}
function hepsi(){if(confirm('🚨 TÜM pozisyonlar kapatılacak ve bot durdurulacak. Emin misin?')&&confirm('Son kez: hepsi kapatılsın mı?'))post({act:'hep'})}
function sinyalAc(sym,s,yon='buy'){const mj=D.mj_def,lev=D.lev_def,L=yon=='buy';if(confirm(`${s} ${L?'🟢 LONG':'🔴 SHORT'} açılsın mı?\n${f(mj,0)} $ marjin × ${lev}x = ${f(mj*lev,0)} $ pozisyon\nÇıkışı bot yönetir.`))post({act:'ac',sym,yon,mj,lev})}
function egri(e){const s=$('egri');if(!e||e.length<2){s.innerHTML='<text x="500" y="105" text-anchor="middle" font-size="14">Eğri birkaç saat içinde oluşur</text>';return}
 const v=e.map(x=>x[1]),bas=v[0],mn=Math.min(...v),mx=Math.max(...v),pad=Math.max((mx-mn)*.15,bas*.02),lo=mn-pad,hi=mx+pad,W=1000,H=190;
 const X=i=>i*(W/(v.length-1)),Y=y=>H-(y-lo)/(hi-lo)*H+5;const p=v.map((y,i)=>`${X(i).toFixed(1)},${Y(y).toFixed(1)}`).join(' ');const up=v[v.length-1]>=bas,c=up?'#22d39b':'#ff5c7a';
 s.innerHTML=`<defs><linearGradient id="gd" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="${c}" stop-opacity=".45"/><stop offset="1" stop-color="${c}" stop-opacity="0"/></linearGradient></defs>
 <line x1="0" x2="1000" y1="${Y(bas)}" y2="${Y(bas)}" stroke="#8b95b5" stroke-dasharray="4 5"/><polygon points="0,200 ${p} 1000,200" fill="url(#gd)"/><polyline points="${p}" fill="none" stroke="${c}" stroke-width="3" vector-effect="non-scaling-stroke"/>
 <text x="6" y="${Y(bas)-5}" font-size="12">başlangıç ${f(bas)} $</text><text x="994" y="16" font-size="13" text-anchor="end" fill="${c}" font-weight="700">${f(v[v.length-1])} $</text>`}
function pozKart(p){const L=p.y=='long';const kir=p.pnl<0;
 let not;if(p.kilit!=null)not=`🔒 Kâr kilitli: fiyat geri düşse bile en az <b>${sg(p.kilit)} $</b> ile kapanır.`;
 else if(p.pnl>0)not=`Kâr henüz kilitli değil. <b>🛡️ Kârı koru</b>: fiyat geri düşerse işlemi şu anki kârla (${sg(p.pnl)} $) kapatır.`;
 else not=p.sl?`Zararda. Stop var: zarar en fazla <b>${f(p.sl)} $</b>.`:`Zararda. Stop yok: fiyat likidasyona inerse bu işlemde en fazla <b>${f(p.mj)} $</b> kaybedilir.`;
 if(!p.yonetim)not='⚠️ Bot bu pozisyonu yönetmiyor (Ayarlar → elle açtığım işlemleri bot yönetsin).';
 const sagEt=p.kilit!=null?`<span class="art">kilit ${fy(p.kilit_f)} · izliyor ↑</span>`:`<span>${p.hedef_ad} ${sg(p.hedef_usd)}$ → ${fy(p.hedef_f)}</span>`;
 const solEt=p.sl?`<span class="eks">stop ${fy(p.sl_f)}</span>`:`<span class="eks">likidasyon ${fy(p.liq)}${p.liq_uz!=null&&kir?` (%${f(p.liq_uz,1)} uzakta)`:''}</span>`;
 const b1=p.pnl>0?`<button class="btn b-ghost" onclick="koru('${p.sym}','${p.s}',${p.pnl})">🛡️ Kârı koru</button>`:(p.sl?'':`<button class="btn b-ghost" onclick="stopEkle('${p.sym}','${p.s}')">🛑 Stop ekle</button>`);
 return `<div class="poz"><div class="ust"><b>${p.s}</b><span class="rozet ${L?'L':'S'}">${L?'LONG':'SHORT'} ${f(p.lev,0)}x</span>${p.elle?'<span class="rozet M">✋ elle</span>':''}${p.kilit!=null?`<span class="rozet Y">🔒 ${sg(p.kilit)}$</span>`:''}
 <div class="kz ${rk(p.pnl)}">${sg(p.pnl)} $<div class="alt ${rk(p.yuzde)}">${sg(p.yuzde)}%</div></div></div>
 <div class="not2">${not}</div><div class="bilgi"><span>giriş ${fy(p.gir)} · şimdi ${fy(p.c)} · ${f(p.mj,0)}$</span><span>${sure(p.dk)}</span></div>
 <div class="yol"><div class="giris"></div>${p.kilit_pos!=null?`<div class="kilit" style="left:${p.kilit_pos}%"></div>`:''}<div class="imlec ${kir?'kir':''}" style="left:${p.pos}%"></div></div>
 <div class="etiket">${solEt}<span>giriş</span>${sagEt}</div>
 <div class="alt2">${b1}<button class="btn b-dur" onclick="kapat('${p.sym}','${p.s}',${p.pnl})">✕ Kapat</button></div></div>`}
function adayCiz(d){const A=d.aday;$('aday_acik').innerHTML=d.don?`Bot, sert düşmüş bir coin son 1 saatte <b>%${f(d.don,0)} toparlanınca</b> "dip yaptı" sayar ve alır. Çubuk o noktaya ne kadar kaldığını gösterir.`:'Toparlanma şartı kapalı: listedeki coinler hemen alınabilir.';
 if(!A.length){$('aday').innerHTML='<div class="bos">Şu an eşiği geçen düşüş yok.</div>';return}
 $('aday').innerHTML='<table><tr><th style="text-align:left">Coin</th><th>24s</th><th style="width:44%">Dip yapmaya</th></tr>'+A.slice(0,15).map(x=>{let h;
  if(x.d=='acik')h='<span class="chip c-m">📌 işlemde</span>';else if(x.d=='yasak')h='<span class="chip c-g">⏱ beklemede</span>';
  else if(x.d=='hazir')h=`<div class="dbar"><i style="width:100%;background:var(--yesil)"></i></div><span class="art">✅ dip yaptı</span><button class="ac" onclick="sinyalAc('${x.sym}','${x.s}')">Aç</button>`;
  else if(x.d=='dusuyor')h=`<div class="dbar"><i style="width:0"></i></div><span class="eks">↓ düşüyor</span>`;
  else h=`<div class="dbar"><i style="width:${x.dol}%;background:${x.dol>=50?'var(--sari)':'var(--soluk)'}"></i></div><span style="color:${x.dol>=50?'var(--sari)':'var(--soluk)'}">${x.kalan!=null?'%'+f(x.kalan,1)+' kaldı':'veri yok'}</span>`;
  return `<tr><td class="cz"><b>${x.s}</b>${zD(x.z)}</td><td class="eks nw">%${f(x.p24,1)}</td><td><div class="dp">${h}</div></td></tr>`}).join('')+'</table>'}
function sinyalCiz(d){const HL=d.aday.filter(x=>x.d=='hazir'),HS=(d.tepe||[]).filter(x=>x.d=='hazir');let h='';
 h+=HL.length?HL.map(x=>`<div class="sinyal"><div><b>${x.s}</b> <span class="rozet L">🟢 LONG</span><div class="alt">24s %${f(x.p24,1)} · son 1 saat %${sg(x.p1,1)} · dip yaptı</div></div><button class="btn b-bas" onclick="sinyalAc('${x.sym}','${x.s}','buy')">LONG aç</button></div>`).join('')+
  `<div class="alt" style="margin-bottom:10px">🟢 ${!d.calis?'Oto giriş kapalı: LONG sinyallerini sen açarsın.':(d.oto>=d.max_pos?`Bot dolu (${d.oto}/${d.max_pos}): bu LONG'lara kendisi giremiyor, sen açabilirsin.`:'Bot boş yer bulunca LONG sinyallerine kendisi de girer.')}</div>`
  :(()=>{const y=d.aday.filter(x=>x.d=='bek'&&x.kalan!=null).sort((a,b)=>a.kalan-b.kalan)[0];return `<div class="alt" style="padding:4px 0 10px">🟢 LONG sinyali yok.${y?` En yakın: <b>${y.s}</b>, dip yapmaya %${f(y.kalan,1)} kaldı.`:''}</div>`})();
 h+=HS.length?HS.map(x=>`<div class="sinyal ss"><div><b>${x.s}</b> <span class="rozet S">🔴 SHORT</span><div class="alt">24s %${sg(x.p24,1)} · son 1 saat %${sg(x.p1,1)} · tepe yaptı</div></div><button class="btn b-dur" onclick="sinyalAc('${x.sym}','${x.s}','sell')">SHORT aç</button></div>`).join('')+
  '<div class="alt">🔴 SHORT sinyallerine bot girmez, sen açarsın. (Bu kural test edilmedi.)</div>'
  :(()=>{const y=(d.tepe||[]).filter(x=>x.d=='bek'&&x.kalan!=null).sort((a,b)=>a.kalan-b.kalan)[0];return `<div class="alt" style="padding:4px 0">🔴 SHORT sinyali yok.${y?` En yakın: <b>${y.s}</b>, tepe yapmaya %${f(y.kalan,1)} kaldı.`:''}</div>`})();
 $('sin').innerHTML=h}
let SONV=0;const SAATF=new Intl.DateTimeFormat('tr-TR',{timeZone:'Europe/Stockholm',hour:'2-digit',minute:'2-digit',second:'2-digit'}),GUNF=new Intl.DateTimeFormat('tr-TR',{timeZone:'Europe/Stockholm',day:'2-digit',month:'2-digit'});
function saatYaz(){const n=new Date();$('saat').textContent=GUNF.format(n)+' '+SAATF.format(n);const g=SONV?Math.round((Date.now()-SONV)/1000):null;
 $('guncel').innerHTML=g==null?'bağlanıyor…':(g<15?'<span class="art">● canlı</span>':`<span class="eks">● ${g} sn önce güncellendi</span>`)}
setInterval(saatYaz,1000);setTimeout(saatYaz,50);
function sureY(dk,ea){const t=dk<60?`${dk} dk`:(dk<1440?`${Math.floor(dk/60)} sa ${dk%60} dk`:`${Math.floor(dk/1440)} gün ${Math.floor(dk%1440/60)} sa`);return (ea?'≥ ':'')+t}
function zaman(h){return h==null?'–':(h<1?'şimdi':(h<24?`${Math.round(h)} sa önce`:`${Math.floor(h/24)} gün ${Math.round(h%24)} sa önce`))}
function zT(z){return !z?'':'<div class="zz">'+(z.tz<1&&z.tf>-0.5?'<span class="art">🔺 şu an tepede</span>':`🔺 ${zaman(z.tz)} · <span class="nw">tepeden %${f(z.tf,1)}</span>`)+'</div>'}
function zD(z){return !z?'':'<div class="zz">'+(z.dz<1&&z.df<0.5?'<span class="eks">🔻 şu an dipte</span>':`🔻 ${zaman(z.dz)} · <span class="nw">dipten %+${f(z.df,1)}</span>`)+'</div>'}
function siraCiz(d){const S=d.sira||{};const tab=(A,ilk)=>!A||!A.length?'<div class="bos">Veri bekleniyor (ilk tarama).</div>':
 '<table class="sira"><tr><th>#</th><th style="text-align:left">Coin</th><th>24s</th><th>1 sa</th><th></th></tr>'+A.map(x=>
 `<tr><td>${x.sira}</td><td><b>${x.s}</b>${ilk?zT(x.z):zD(x.z)}<div class="zz">⏱ listede ${sureY(x.dk,x.en_az)}</div></td><td class="${ilk?'art':'eks'} nw">%${sg(x.p24,1)}</td><td class="${rk(x.p1)} nw">${x.p1!=null?'%'+sg(x.p1,1):'–'}</td>`+
 `<td><div class="ikib"><button class="mini l" onclick="sinyalAc('${x.sym}','${x.s}','buy')">LONG</button><button class="mini s" onclick="sinyalAc('${x.sym}','${x.s}','sell')">SHORT</button></div></td></tr>`).join('')+'</table>';
 $('sira_ilk').innerHTML=tab(S.ilk,true);$('sira_son').innerHTML=tab(S.son,false)}
function tepeCiz(d){const A=d.tepe||[];
 if(!A.length){$('tepe').innerHTML='<div class="bos">Şu an eşiği geçen yükseliş yok.</div>';return}
 $('tepe').innerHTML='<table><tr><th style="text-align:left">Coin</th><th>24s</th><th style="width:44%">Tepe yapmaya</th></tr>'+A.slice(0,15).map(x=>{let h;
  if(x.d=='acik')h='<span class="chip c-m">📌 işlemde</span>';else if(x.d=='yasak')h='<span class="chip c-g">⏱ beklemede</span>';
  else if(x.d=='hazir')h=`<div class="dbar"><i style="width:100%;background:var(--kirmizi)"></i></div><span class="eks">✅ tepe yaptı</span><button class="ac" style="background:linear-gradient(135deg,#ff5c7a,#d93a5c)" onclick="sinyalAc('${x.sym}','${x.s}','sell')">Short</button>`;
  else if(x.d=='yukseliyor')h=`<div class="dbar"><i style="width:0"></i></div><span class="art">↑ yükseliyor</span>`;
  else h=`<div class="dbar"><i style="width:${x.dol}%;background:${x.dol>=50?'var(--sari)':'var(--soluk)'}"></i></div><span style="color:${x.dol>=50?'var(--sari)':'var(--soluk)'}">${x.kalan!=null?'%'+f(x.kalan,1)+' kaldı':'veri yok'}</span>`;
  return `<tr><td class="cz"><b>${x.s}</b>${zT(x.z)}</td><td class="art nw">%${sg(x.p24,1)}</td><td><div class="dp">${h}</div></td></tr>`}).join('')+'</table>'}
function ayarCiz(d){$('a_seg').innerHTML='';const sol=document.createElement('div'),sag=document.createElement('div');
 d.ayar.forEach((a,i)=>{const el=document.createElement('div');el.className='ayar';el.innerHTML=`<div class="bas"><span>${a.t}</span></div><div class="seg" data-k="${a.k}">`+a.o.map(o=>`<span data-v='${JSON.stringify(o.v)}' class="${JSON.stringify(o.v)==JSON.stringify(a.cur)?'on':''}">${o.l}</span>`).join('')+'</div>';(i%2?sag:sol).appendChild(el)});
 $('a_seg').append(sol,sag);$('a_elle').className='tog'+(d.elle?'':' off');
 document.querySelectorAll('#a_seg .seg span').forEach(s=>s.onclick=()=>{s.parentNode.querySelectorAll('span').forEach(x=>x.classList.remove('on'));s.classList.add('on');degisti()});ayarDegisti=false;$('kaydet').textContent='💾 Ayarları kaydet'}
function degisti(){ayarDegisti=true;$('kaydet').textContent='💾 Ayarları kaydet (kaydedilmedi)'}
async function ayarKaydet(){const a={};document.querySelectorAll('#a_seg .seg').forEach(s=>{const on=s.querySelector('.on');if(on)a[s.dataset.k]=JSON.parse(on.dataset.v)});a.elle=!$('a_elle').classList.contains('off');
 const j=await post({act:'ayar',ayar:a});if(j&&j.ok){ayarCizildi=false}}
function segKur(id,vals,def,fmt,cb){const el=$(id);el.innerHTML=vals.map(v=>`<span data-v="${v}" class="${v==def?'on':''}">${fmt(v)}</span>`).join('');el.querySelectorAll('span').forEach(s=>s.onclick=()=>{el.querySelectorAll('span').forEach(x=>x.classList.remove('on','yl','kr'));s.classList.add('on');cb(s.dataset.v);eOzet()})}
function eOzet(){const q=$('e_coin').value.trim().toUpperCase().replace('USDT','');const c=COIN[q];const mj=eMj||D?.mj_def,lev=eLev||D?.lev_def;
 if(!c){$('e_fiyat').textContent='';$('e_ozet').innerHTML=q?'Coin bulunamadı. Listeden seç.':'Coin seç.';return}
 $('e_fiyat').innerHTML=c.c?`şimdi ${fy(c.c)} · 24s <span class="${rk(c.p24)}">%${sg(c.p24,1)}</span>`:'';const L=eYon=='buy',poz=mj*lev,liq=c.c?c.c*(1-(L?1:-1)*(0.95/lev)):null;
 $('e_ozet').innerHTML=`Açılacak: <b>${q} ${L?'🟢 LONG':'🔴 SHORT'} · ${f(poz,0)} $ pozisyon (${f(mj,0)} $ × ${lev}x)</b>${liq?` · likidasyon ≈ ${fy(liq)} (fiyat %${f(95/lev,1)} ${L?'düşerse':'yükselirse'})`:''} · çıkışı bot yönetir`+(poz<5.2?'<br><span class="eks">⚠️ Pozisyon 5 $\'ın altında, borsa kabul etmez.</span>':'')}
function elleAc(){const q=$('e_coin').value.trim().toUpperCase().replace('USDT','');const c=COIN[q];if(!c){toast('Önce listeden bir coin seç',false);return}
 const mj=+(eMj||D.mj_def),lev=+(eLev||D.lev_def);if(confirm(`${q} ${eYon=='buy'?'🟢 LONG':'🔴 SHORT'} açılsın mı?\n${f(mj,0)} $ marjin × ${lev}x = ${f(mj*lev,0)} $ pozisyon (gerçek para)`))post({act:'ac',sym:c.sym,yon:eYon,mj,lev})}
async function coinler(){try{const L=await (await fetch('api/coinler')).json();COIN={};L.forEach(c=>COIN[c.s]=c);$('coinler').innerHTML=L.map(c=>`<option value="${c.s}">`).join('')}catch(e){}}
async function yenile(){try{const d=await (await fetch('api',{cache:'no-store'})).json();if(d.hata)throw d.hata;D=d;
 $('alt').textContent=`CANLI HESAP · sürüm ${d.v.split(' ')[0]} · Bitget USDT-M · izole`;SONV=Date.now();
 const dur=!d.calis||d.limit;$('durum').className='pill '+(dur?'p-dur':'p-ok');$('durumy').textContent=!d.calis?'SİNYAL + ELLE':(d.limit?'GÜNLÜK LİMİT':'ÇALIŞIYOR');
 $('tog').textContent=d.calis?'🤖 Oto giriş: AÇIK':'🤖 Oto giriş: KAPALI';$('tog').className='btn '+(d.calis?'b-dur':'b-bas');
 $('bak').textContent=f(d.bak)+' $';$('bos').textContent='kullanılabilir '+f(d.bos)+' $';
 $('bug').textContent=sg(d.bugun)+' $';$('bug').className='d '+rk(d.bugun);$('kbug').style.setProperty('--renk',d.bugun>=0?'var(--yesil)':'var(--kirmizi)');
 $('bugn').textContent=`${d.bugun_n} işlem · limit ${d.gunluk?'−'+f(d.gunluk,0)+' $':'yok'}`;
 $('npoz').textContent=`${d.oto} / ${d.max_pos}`;$('apnl').innerHTML=`${d.poz.length>d.oto?`+${d.poz.length-d.oto} elle · `:''}açık K/Z <span class="${rk(d.acik_pnl)}">${sg(d.acik_pnl)} $</span>`;
 const o=d.ozet;$('kaz').textContent=o.kaz_y!=null?'%'+o.kaz_y:'–';$('ger').textContent=o.n?(o.gerek!=null?`gereken %${o.gerek} · ${o.n} işlem`:`${o.n} işlem`):'henüz işlem yok';
 $('gi').style.width=(o.kaz_y||0)+'%';if(o.gerek!=null){$('gb').style.display='block';$('gb').style.left=o.gerek+'%'}
 $('tarama').textContent=d.tarama!=null?`son tarama ${d.tarama} sn önce`:'tarama bekleniyor';
 egri(d.egri);sinyalCiz(d);adayCiz(d);tepeCiz(d);siraCiz(d);
 $('poz').innerHTML=d.poz.length?d.poz.map(pozKart).join('')+`<button class="btn b-dur genis" onclick="hepsi()">🚨 Tümünü kapat</button>`:'<div class="bos">Açık pozisyon yok.</div>';
 if(!ayarDegisti)ayarCiz(d);
 $('a_ozet').innerHTML=`<b>${d.strateji}</b><br>${d.cikis_yazi}`;
 if(!eMj){segKur('e_mj',d.mj_el,d.mj_def,v=>f(v,0)+' $',v=>eMj=+v);segKur('e_lev',d.lev_el,d.lev_def,v=>v+'x',v=>eLev=+v);eMj=d.mj_def;eLev=d.lev_def;eOzet()}
 $('gec_r').innerHTML=o.n?`toplam <span class="${rk(o.top)}">${sg(o.top)} $</span> · ort ${sg(o.ort_k)} / ${sg(o.ort_z)}`:'';
 $('gec').innerHTML=d.gec.length?'<table><tr><th>Coin</th><th>Süre</th><th>Çıkış</th><th>Sonuç</th></tr>'+d.gec.slice(0,25).map(g=>{const n=g.n||'';let c='c-g',e='';
  if(/KİLİT|KÂR/.test(n)){c='c-y';e='🔒 '}else if(/LİKİDASYON/.test(n)){c='c-k';e='💥 '}else if(/STOP/.test(n)){c='c-k';e='🛑 '}else if(/MANUEL/.test(n)){c='c-m';e='✋ '}
  return `<tr><td><b>${g.s}</b><span class="rozet ${g.y=='long'||g.y=='buy'?'L':'S'}">${g.y=='long'||g.y=='buy'?'L':'S'}</span><div class="alt">${new Date(g.t*1000).toLocaleString('tr-TR',{timeZone:'Europe/Stockholm',day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'})}</div></td><td>${sure(g.sure)}</td><td><span class="chip ${c}">${e}${n.toLowerCase()}</span></td><td class="${rk(g.pnl)}"><b>${sg(g.pnl)} $</b><div class="alt">${g.kesin?'borsadan net':'tahmini'}</div></td></tr>`}).join('')+'</table>':'<div class="bos">Henüz kapanan işlem yok.</div>';
 $('uyari').style.display='none';
}catch(e){$('uyari').style.display='block';$('uyari').textContent='⚠️ Bağlantı yok ya da bot yeniden başlıyor, tekrar deneniyor…'}}
document.querySelectorAll('#e_yon span').forEach(s=>s.onclick=()=>{document.querySelectorAll('#e_yon span').forEach(x=>x.classList.remove('on','yl','kr'));s.classList.add('on',s.dataset.v=='buy'?'yl':'kr');eYon=s.dataset.v;eOzet()});
coinler();yenile();setInterval(yenile,4000);setInterval(coinler,300000);
</script></body></html>
"""

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
    haber(f"👻 GHOST DİP {VERSIYON} hazır\n{durum()}\n🎯 {strateji_yazi()}\n"
          f"💵 {A['marjin']:g}$ izole · ≤{A['lev']}x · en çok {A['max_pos']} işlem · limit {('−' + format(A['gunluk'], 'g') + '$') if A['gunluk'] else 'yok'}\n→ /panel")
    threading.Thread(target=izle, daemon=True).start()
    threading.Thread(target=bakiye_dongu, daemon=True).start()
    panel_baslat()
    tarama()
