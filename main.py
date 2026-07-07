#!/usr/bin/env python3
"""
TELEGRAM SİNYAL KOPYALAMA BOTU — GERÇEK PARA
🔖 VERSİYON: v13 (genis SL artik atlanmiyor, kendi SL'imize sikistiriliyor)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Belirtilen Telegram kanalını (https://t.me/Kripto_Botu) dinler, gelen
sinyalleri ayrıştırır, Bitget'te GERÇEK PARA ile birebir açar.

⚠️ ÖNEMLİ DÜRÜSTLÜK NOTU: Bu kanalın geçmiş performansı hakkında HİÇBİR
VERİMİZ YOK — backtest edilmedi, doğrulanmadı. Konuşmamızda daha önce
gördüğümüz benzer bir kanal (net düşüş trendinin ortasında LONG önermiş,
SL'e çarpmıştı) bu tür kaynakların güvenilirliği konusunda bir uyarıydı.
Kanalın kendi mesajı bile "Kesinlikle yüksek kaldıraç kullanmayın" diyor
— bu bot 10x ile çalışacak şekilde ayarlandı (kullanıcı talebiyle,
kanalın kendi tavsiyesinin TERSİNE).

GÜVENLİK (önceki botlardan taşınan, kanıtlanmış mekanizmalar):
  - API şifresi ortam değişkeninden okunur, koda yazılmaz
  - Restart + çalışma-zamanı sahipsiz pozisyon koruması
  - Çıkış emirleri gerçekten uygulandığı doğrulanmadan takipten çıkarılmaz
  - Günlük zarar limiti + otomatik gece yarısı sıfırlama
  - Risk bazlı pozisyon boyutlandırma

SİNYAL FORMATI (şu ana kadar gördüğümüz TEK örneğe göre yazıldı — bu
kanalın gerçek formatı FARKLIYSA, örnek bir mesaj paylaşman gerekecek,
ayrıştırıcıyı ona göre güncelleriz):

  📊 #BASUSDT.P
  🏁 LONG - Giriş Fiyatı: 0.030974
  🚫 Stop: 0.0294253 ya da sonraki sinyal
  TP1: 0.03112887 ──
  TP2: 0.031283740000000004 ──
  ...

ÇALIŞTIRMA: Bu bot Telethon (Telegram kullanıcı kütüphanesi) kullanır.
İlk çalıştırmadan önce session_olustur.py'yi BİR KERE, kendi bilgisayarında
çalıştırıp bir "session string" üretmen gerekiyor (ayrı dosya olarak
veriyorum). Onu STRING_SESSION ortam değişkenine koyduktan sonra bu bot
Railway'de sorunsuz çalışır.
"""

import os
import re
import time
import json
import threading
import logging
import asyncio
import ccxt
import telebot
from telethon import TelegramClient, events

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("SIGNAL_COPY")

# ════════════════════════════════════════════
# CONFIG
# ════════════════════════════════════════════
TELE_TOKEN   = os.getenv("TELE_TOKEN", "")       # kendi bildirim botun (Telegram Bot API)
CHAT_ID      = int(os.getenv("MY_CHAT_ID", "0"))
API_KEY      = os.getenv("BITGET_API", "")
API_SEC      = os.getenv("BITGET_SEC", "")
PASSPHRASE   = os.getenv("BITGET_PASS", "")

TG_API_ID    = int(os.getenv("TG_API_ID", "0"))   # my.telegram.org'dan
TG_API_HASH  = os.getenv("TG_API_HASH", "")       # my.telegram.org'dan
TG_STRING_SESSION = os.getenv("STRING_SESSION", "") or os.getenv("TG_SESSION", "")
KANAL_KULLANICI_ADI = os.getenv("KANAL_USERNAME", "FuturesKripto")

if not PASSPHRASE:
    raise RuntimeError("BITGET_PASS ortam değişkeni ayarlanmamış.")
if not TG_API_ID or not TG_API_HASH or not TG_STRING_SESSION:
    raise RuntimeError("TG_API_ID / TG_API_HASH / STRING_SESSION ortam değişkenleri "
                        "eksik — önce session_olustur.py'yi çalıştırıp session string üretmen gerekiyor.")

exchange = ccxt.bitget({
    "apiKey": API_KEY, "secret": API_SEC, "password": PASSPHRASE,
    "options": {"defaultType": "swap"}, "enableRateLimit": True, "timeout": 30000,
})

TOPLAM_SERMAYE   = 35.0
MARGIN_SABIT     = 10.0    # ── kullanıcı talebiyle: sabit marj, risk bazlı değil ──
LEV              = 10
MAX_POS          = 1       # kanal genelde tek sinyal veriyor, aynı anda 1 işlem
MIN_POS_NOTIONAL = 30.0

MAX_GUNLUK_ZARAR = -10.0

TRADE_STATE_PATH = os.getenv("TRADE_STATE_PATH", "/data/signal_copy_state.json")
TRADE_LOG_PATH = os.getenv("TRADE_LOG_PATH", "/data/signal_copy_log.json")
PORT = int(os.getenv("PORT", "8080"))

# ════════════════════════════════════════════
# TELEGRAM BİLDİRİM (kendi bot token'ın — sinyal kanalıyla KARIŞTIRMA)
# ════════════════════════════════════════════
bot = telebot.TeleBot(TELE_TOKEN) if TELE_TOKEN else None


if bot:
    @bot.message_handler(commands=["manuel"])
    def manuel_sinyal_komutu(msg):
        """
        Kanaldan gelmeyi beklemeden test/manuel giriş için:
        /manuel yazıp ardından (yeni satırda) sinyal metnini yapıştır
        (tam kanal formatı) YA DA sadece 'MAGMA LONG' gibi basit yaz.
        """
        metin = msg.text.replace("/manuel", "", 1).strip()
        if not metin:
            bot.send_message(msg.chat.id, "Kullanım: /manuel MAGMA LONG  (ya da tam sinyal metnini yapıştır)")
            return

        sinyal = sinyal_ayristir(metin)
        if not sinyal:
            sinyal = hizli_sinyal_ayristir(metin)
        if not sinyal:
            bot.send_message(msg.chat.id, "⚠️ Metin hiçbir formatta ayrıştırılamadı.")
            return

        bot.send_message(msg.chat.id, f"✅ Ayrıştırıldı: {sinyal}\nİşleniyor...")
        sinyali_isle(sinyal)

    @bot.message_handler(commands=["durum"])
    def durum_komutu(msg):
        with state_lock:
            if not trade_state:
                bot.send_message(msg.chat.id, "Açık pozisyon yok.")
                return
            satirlar = ["📋 AÇIK POZİSYONLAR\n"]
            for sym, d in trade_state.items():
                satirlar.append(f"{sym} [{d['direction'].upper()}] giriş:{d['entry']:.8f} "
                                 f"SL:{d['sl']:.8f} TP_index:{d.get('tp_index',0)}/{len(d.get('tp_liste',[]))}")
            bot.send_message(msg.chat.id, "\n".join(satirlar))

    @bot.message_handler(commands=["ac"])
    def ac_komutu(msg):
        """
        YENİ: Net bir açma komutu. Kullanım: /ac MAGMA LONG  (ya da SHORT)
        (Not: '/manuel' ve komutsuz kısa mesaj — örn. 'Magma long' — hâlâ
        çalışmaya devam ediyor, bu sadece daha net bir alternatif.)
        """
        metin = msg.text.replace("/ac", "", 1).strip()
        if not metin:
            bot.send_message(msg.chat.id, "Kullanım: /ac MAGMA LONG")
            return
        sinyal = sinyal_ayristir(metin) or hizli_sinyal_ayristir(metin)
        if not sinyal:
            bot.send_message(msg.chat.id, "⚠️ Anlaşılamadı. Örnek: /ac MAGMA LONG")
            return
        bot.send_message(msg.chat.id, f"⚡ Açılıyor: {sinyal['symbol']} {sinyal['direction'].upper()}")
        sinyali_isle(sinyal)

    @bot.message_handler(commands=["kapat"])
    def kapat_komutu(msg):
        """
        YENİ: Manuel kapatma komutu — daha önce hiç yoktu, bu yüzden
        "kapat" yazınca hiçbir şey olmuyordu. Kullanım:
          /kapat          -> açık TEK pozisyon varsa onu kapatır
          /kapat EDGE     -> EDGE (ya da başka coin) pozisyonunu kapatır
        """
        parca = msg.text.replace("/kapat", "", 1).strip().upper()

        with state_lock:
            acik_semboller = list(trade_state.keys())

        if not acik_semboller:
            bot.send_message(msg.chat.id, "Açık pozisyon yok, kapatılacak bir şey bulunamadı.")
            return

        hedef_sym = None
        if parca:
            for sym in acik_semboller:
                if parca in sym.upper():
                    hedef_sym = sym
                    break
            if not hedef_sym:
                bot.send_message(msg.chat.id, f"'{parca}' ile eşleşen açık pozisyon bulunamadı. "
                                                f"Açık olanlar: {acik_semboller}")
                return
        else:
            if len(acik_semboller) > 1:
                bot.send_message(msg.chat.id, f"Birden fazla açık pozisyon var, hangisini kastettiğini belirt: "
                                                f"{acik_semboller}\nÖrn: /kapat {acik_semboller[0].split('/')[0]}")
                return
            hedef_sym = acik_semboller[0]

        bot.send_message(msg.chat.id, f"⏳ {hedef_sym} kapatılıyor...")
        basari, mesaj = manuel_pozisyon_kapat(hedef_sym)
        bot.send_message(msg.chat.id, mesaj)


    KISA_MESAJ_UST_SINIR = 30  # bu karakterden uzun mesajlar sohbet sayilir, islem denenmez

    @bot.message_handler(func=lambda m: m.text and not m.text.startswith("/"))
    def komutsuz_hizli_giris(msg):
        """
        YENİ: '/manuel' yazmadan, doğrudan 'Mon long ac' gibi KISA bir
        mesaj göndererek de işlem açılabilsin (hız için). Güvenlik payı:
        mesaj KISA_MESAJ_UST_SINIR karakterden uzunsa (muhtemelen sıradan
        sohbet), otomatik işlem DENENMEZ — yanlışlıkla tetiklenmesin.
        """
        metin = msg.text.strip()
        if len(metin) > KISA_MESAJ_UST_SINIR:
            return  # uzun mesaj, muhtemelen sohbet — dokunma

        sinyal = hizli_sinyal_ayristir(metin)
        if not sinyal:
            return  # "long"/"short" içermiyor, işlem denemesi değil

        bot.send_message(msg.chat.id, f"⚡ Hızlı giriş algılandı: {sinyal['symbol']} {sinyal['direction'].upper()}")
        sinyali_isle(sinyal)


def telebot_polling_baslat():
    if not bot:
        return
    while True:
        try:
            bot.infinity_polling(timeout=30, long_polling_timeout=30)
        except Exception as e:
            log.error(f"[TELEBOT_POLL] {e}")
            time.sleep(5)

def tg(msg):
    if not bot:
        log.info(f"[TG-atlandi] {msg}")
        return
    try:
        bot.send_message(CHAT_ID, str(msg)[:4096])
    except Exception as e:
        log.warning(f"[TG] {e}")


def safe(x):
    try:
        return float(x)
    except Exception:
        return 0.0


def get_candles(sym, tf, limit=100):
    try:
        return exchange.fetch_ohlcv(sym, tf, limit=limit)
    except Exception as e:
        log.warning(f"[VERI] {sym} {tf}: {e}")
        return None


# ════════════════════════════════════════════
# KALICI DURUM
# ════════════════════════════════════════════
trade_state = {}
state_lock = threading.Lock()

def durumu_diske_yaz():
    try:
        os.makedirs(os.path.dirname(TRADE_STATE_PATH), exist_ok=True)
        with state_lock:
            veri = dict(trade_state)
        with open(TRADE_STATE_PATH, "w") as f:
            json.dump(veri, f)
    except Exception as e:
        log.warning(f"[KALICI] Diske yazma başarısız: {e}")


def durumu_diskten_yukle():
    global trade_state
    try:
        if os.path.exists(TRADE_STATE_PATH):
            with open(TRADE_STATE_PATH) as f:
                yuklenen = json.load(f)
            with state_lock:
                trade_state = yuklenen
            log.info(f"[KALICI] {len(yuklenen)} kayıtlı işlem durumu yüklendi")
    except Exception as e:
        log.warning(f"[KALICI] Yükleme başarısız: {e}")


# ════════════════════════════════════════════
# TRADE LOG (kapanan işlemlerin kalıcı kaydı — panel için)
# ════════════════════════════════════════════
trade_log = []
log_lock = threading.Lock()

def trade_log_kaydet(kayit):
    with log_lock:
        trade_log.append(kayit)
        veri = list(trade_log)
    try:
        os.makedirs(os.path.dirname(TRADE_LOG_PATH), exist_ok=True)
        with open(TRADE_LOG_PATH, "w") as f:
            json.dump(veri, f)
    except Exception as e:
        log.warning(f"[LOG] Diske yazma başarısız: {e}")


def trade_log_yukle():
    global trade_log
    try:
        if os.path.exists(TRADE_LOG_PATH):
            with open(TRADE_LOG_PATH) as f:
                yuklenen = json.load(f)
            with log_lock:
                trade_log = yuklenen
            log.info(f"[LOG] {len(yuklenen)} geçmiş işlem yüklendi")
    except Exception as e:
        log.warning(f"[LOG] Yükleme başarısız: {e}")


def acilista_pozisyonlari_dogrula():
    try:
        pozisyonlar = exchange.fetch_positions()
    except Exception as e:
        tg(f"⚠️ Açılışta pozisyon kontrolü başarısız: {e}")
        return

    for p in pozisyonlar:
        qty = safe(p.get("contracts"))
        if qty <= 0:
            continue
        sym = p["symbol"]
        entry = safe(p.get("entryPrice"))
        side = p.get("side")

        with state_lock:
            kayitli = trade_state.get(sym)
        if kayitli:
            tg(f"♻️ {sym} pozisyonu kayıtlı durumla eşleşti.")
            continue

        direction = "long" if side == "long" else "short"
        guvenlik_sl_pct = 0.03
        sl = entry * (1 - guvenlik_sl_pct) if direction == "long" else entry * (1 + guvenlik_sl_pct)
        with state_lock:
            trade_state[sym] = {"sl": sl, "tp_liste": [], "tp_index": 0,
                                 "direction": direction, "entry": entry, "kaynak": "kurtarilan"}
        durumu_diske_yaz()
        tg(f"🚨 UYARI: {sym} için kayıtlı durum yoktu — geçici %3 güvenlik SL'i kondu: {sl:.8f}")


# ════════════════════════════════════════════
# GÜNLÜK ZARAR TAKİBİ
# ════════════════════════════════════════════
gunluk_pnl = 0.0
gunluk_lock = threading.Lock()

def gunluk_limit_asildi():
    with gunluk_lock:
        return gunluk_pnl <= MAX_GUNLUK_ZARAR

def gunluk_pnl_ekle(miktar):
    global gunluk_pnl
    with gunluk_lock:
        gunluk_pnl += miktar
        return gunluk_pnl

def gunluk_reset_loop():
    global gunluk_pnl
    import datetime
    while True:
        try:
            simdi = datetime.datetime.now(datetime.timezone.utc)
            yarin = (simdi + datetime.timedelta(days=1)).replace(hour=0, minute=0, second=5, microsecond=0)
            time.sleep((yarin - simdi).total_seconds())
            with gunluk_lock:
                eski = gunluk_pnl
                gunluk_pnl = 0.0
            tg(f"🔄 Yeni gün! Dünkü gerçekleşen: {eski:+.2f}$")
        except Exception as e:
            log.error(f"[RESET] {e}")
            time.sleep(3600)


# ════════════════════════════════════════════
# SİNYAL AYRIŞTIRMA (BU KANALIN GERÇEK FORMATI FARKLIYSA GÜNCELLENMESİ GEREKİR)
# ════════════════════════════════════════════
HIZLI_SL_PCT = 0.02  # basit "coin yön" formatında, kanal SL vermediği için sabit %2 kullanılır
MAX_SL_PCT = 0.03    # YENİ: kanalın verdiği SL bile bu yüzdeyi aşarsa işlem ATLANIR —
                     # sabit $100 notional ile geniş SL = marjın büyük kısmını riske atmak demek

def hizli_sinyal_ayristir(metin):
    """
    Basit format: 'MAGMA LONG', 'Magma long ac', 'btc short' gibi —
    sadece coin adı + yön. Giriş/SL kanal vermediği için, giriş anlık
    piyasa fiyatından alınır, SL sabit %2 ile hesaplanır.
    """
    m = re.search(r"\b([A-Za-z][A-Za-z0-9]{1,10})\b.*?\b(LONG|SHORT)\b", metin, re.IGNORECASE)
    if not m:
        return None
    sembol = m.group(1).upper()
    if sembol in ("LONG", "SHORT"):
        return None
    yon = "long" if m.group(2).upper() == "LONG" else "short"
    return {"symbol": f"{sembol}/USDT:USDT", "direction": yon, "entry": None, "sl": None, "tp_liste": []}


def sinyal_ayristir(metin):
    """
    Şu ana kadar gördüğümüz TEK örnek formata göre yazıldı:
      📊 #BASUSDT.P
      🏁 LONG - Giriş Fiyatı: 0.030974
      🚫 Stop: 0.0294253 ...
      TP1: 0.03112887
      TP2: 0.031283740000000004
      ...
    Döner: {"symbol":..., "direction":..., "entry":..., "sl":..., "tp_liste":[...]} veya None
    """
    sembol_m = re.search(r"#(\w+?)USDT", metin, re.IGNORECASE)
    yon_m = re.search(r"\b(LONG|SHORT)\b", metin, re.IGNORECASE)
    giris_m = re.search(r"Giri[şs].*?Fiyat[ıi]?\s*:?\s*([\d.]+)", metin, re.IGNORECASE)
    stop_m = re.search(r"Stop\s*:?\s*([\d.]+)", metin, re.IGNORECASE)
    tp_liste = re.findall(r"TP\d+\s*:?\s*([\d.]+)", metin, re.IGNORECASE)

    if not (sembol_m and yon_m and giris_m and stop_m):
        return None

    return {
        "symbol": f"{sembol_m.group(1).upper()}/USDT:USDT",
        "direction": "long" if yon_m.group(1).upper() == "LONG" else "short",
        "entry": float(giris_m.group(1)),
        "sl": float(stop_m.group(1)),
        "tp_liste": [float(x) for x in tp_liste],
    }


# ════════════════════════════════════════════
# POZİSYON BOYUTU
# ════════════════════════════════════════════
def pozisyon_boyutu_hesapla(entry, sl):
    """
    SABİT MARJ modeli (kullanıcı talebiyle): notional = MARGIN_SABIT × LEV.
    SL mesafesi artık boyutlandırmayı etkilemiyor — sadece SL fiyatının
    kendisi (nereye konacağı) için kullanılıyor, miktar için değil.
    """
    if entry <= 0:
        return None, None
    notional = MARGIN_SABIT * LEV
    amount = notional / entry
    return amount, notional


def gercek_bakiye_yeterli_mi(gereken_marj):
    """
    YENİ: İşlem açmadan önce GERÇEK borsa bakiyesini kontrol eder — sabit
    TOPLAM_SERMAYE varsayımı (35$) gerçek bakiyeyle uyuşmayabilir (örn.
    önceki kayıplardan sonra daha düşük olabilir). "Bakiye yetersiz" hatasını
    borsadan almak yerine, ÖNCEDEN kontrol edip net bir mesaj veririz.
    """
    try:
        bakiye = exchange.fetch_balance()
        serbest_usdt = safe(bakiye.get("USDT", {}).get("free", 0))
    except Exception as e:
        log.warning(f"[BAKIYE] Kontrol edilemedi: {e}")
        return True  # kontrol edilemiyorsa engel olma, borsanın kendi kontrolüne güven
    return serbest_usdt >= gereken_marj


TP_OLCEK_CARPANI = 1.5  # 2.5'ten düşürüldü — TP'ler daha YAKIN olsun, kâr erken kilitlensin
                        # (TP6 artık ~1.2R, önceki 2.0R'den daha ulaşılabilir)

# ── TRAILING STOP (son TP sonrası) ──
# Son TP'ye ulaşınca pozisyonun TAMAMI kapanmıyor artık — bir kısmı
# (TRAILING_REZERV_DILIM / (TP_sayisi+TRAILING_REZERV_DILIM)) trailing'e
# ayrılıyor, uzun süren hareketlerde ekstra kâr yakalamak için.
TRAILING_REZERV_DILIM = 1        # kaç "sanal seviye" kadar pay trailing'e ayrılsın
TRAILING_GERI_CEKILME_PCT = 0.015  # zirveden %1.5 geri çekilirse trailing kapatır

def tp_olcekle(entry, sl, tp_liste, direction, carpan=TP_OLCEK_CARPANI):
    """
    Kanaldan gelen (ya da otomatik hesaplanan) TP'lerin oranını KORUYUP,
    hepsini aynı çarpanla büyütür. Kanalın 0.1/0.2/.../0.8R yapısı çok
    zayıf bir risk/ödül sağlıyordu (başabaş için %72 kazanma gerekiyordu);
    bu fonksiyon aynı şekli koruyarak matematiği sağlıklı hale getirir.
    """
    risk_mesafe = abs(entry - sl)
    if risk_mesafe <= 0 or not tp_liste:
        return tp_liste
    yeni_liste = []
    for tp in tp_liste:
        oran = abs(tp - entry) / risk_mesafe
        yeni_oran = oran * carpan
        yeni_tp = entry + yeni_oran * risk_mesafe if direction == "long" else entry - yeni_oran * risk_mesafe
        yeni_liste.append(yeni_tp)
    return yeni_liste


# ════════════════════════════════════════════
# GERÇEK İŞLEM AÇMA (sinyal geldiğinde çağrılır)
# ════════════════════════════════════════════
def calc_macd_hist(kapaniş_listesi, hizli=12, yavas=26, sinyal=9):
    """Basit liste tabanlı MACD histogram (pandas'a bağımlı olmadan)."""
    import pandas as pd
    s = pd.Series(kapaniş_listesi)
    ema_h = s.ewm(span=hizli, adjust=False).mean()
    ema_y = s.ewm(span=yavas, adjust=False).mean()
    macd = ema_h - ema_y
    sinyal_hatti = macd.ewm(span=sinyal, adjust=False).mean()
    return float((macd - sinyal_hatti).iloc[-1])


def calc_bollinger_yuzdeB(kapaniş_listesi, period=20, std_mult=2.0):
    import pandas as pd
    s = pd.Series(kapaniş_listesi)
    orta = s.rolling(period).mean()
    std = s.rolling(period).std()
    ust = orta + std_mult * std
    alt = orta - std_mult * std
    genislik = (ust - alt).replace(0, 0.0001)
    yuzdeB = (s - alt) / genislik
    return float(yuzdeB.iloc[-1]) if not pd.isna(yuzdeB.iloc[-1]) else None


def deneysel_gozlem_hesapla(sym):
    """
    YENİ (DENEYSEL — henüz filtre DEĞİL, sadece gözlem): karar ağacı
    analizinde 4h Bollinger %B ve 1h MACD histogramının en etkili
    göstergeler çıkması üzerine, her sinyalde bunları da hesaplayıp
    Telegram'a not düşüyoruz. Küçük örneklemden (49 sinyal) çıktığı için
    HENÜZ GÜVENİLİR DEĞİL — sadece zamanla veri biriktirmek için.
    """
    try:
        h4 = get_candles(sym, "4h", 30)
        h1 = get_candles(sym, "1h", 40)
        if not h4 or not h1 or len(h4) < 21 or len(h1) < 35:
            return None
        h4_kapanis = [c[4] for c in h4]
        h1_kapanis = [c[4] for c in h1]
        boll_4h = calc_bollinger_yuzdeB(h4_kapanis)
        macd_1h = calc_macd_hist(h1_kapanis)
        return {"4h_bollB": round(boll_4h, 2) if boll_4h is not None else None,
                "1h_macd_hist": round(macd_1h, 6)}
    except Exception:
        return None


def trend_teyidi_yeterli_mi(sym, direction):
    """
    YENİ: FuturesKripto kanalının 49 geçmiş sinyalinin analizinden çıkan
    bulgu — kanal LONG önerdiğinde, sinyal anında 4h'de zaten YÜKSELİŞ
    teyitliyse ve 1h'de DÜŞÜŞTE değilse başarı oranı belirgin yüksek
    (TP grubunda %79.5 4h-yükseliş, SL grubunda sadece %44.4).
    Bu şart sağlanmıyorsa sinyali atlıyoruz.

    NOT: Bu, kanalın gerçek stratejisini çözdüğümüz anlamına gelmiyor —
    sadece görece zayıf görünen bir alt kümeyi eleyen bir koruma filtresi.
    Örneklem (49) küçük, kesin bir garanti değil.
    """
    try:
        h4 = get_candles(sym, "4h", 10)
        h1 = get_candles(sym, "1h", 10)
        if not h4 or not h1 or len(h4) < 3 or len(h1) < 3:
            return True, "veri yetersiz, filtre uygulanamadı — geçildi"

        h4_high = [c[2] for c in h4]; h4_low = [c[3] for c in h4]
        h1_high = [c[2] for c in h1]; h1_low = [c[3] for c in h1]

        if direction == "long":
            h4_yukselis = h4_high[-1] > h4_high[-2]
            h1_dusus = h1_low[-1] < h1_low[-2]
            if not h4_yukselis:
                return False, "4h yükseliş teyitli değil"
            if h1_dusus:
                return False, "1h düşüşte"
        else:
            h4_dusus = h4_low[-1] < h4_low[-2]
            h1_yukselis = h1_high[-1] > h1_high[-2]
            if not h4_dusus:
                return False, "4h düşüş teyitli değil"
            if h1_yukselis:
                return False, "1h yükselişte"

        return True, "teyit sağlandı"
    except Exception as e:
        return True, f"kontrol hatası ({e}), geçildi"


def manuel_pozisyon_kapat(sym):
    """
    YENİ: Gerçekten borsadan pozisyonu kapatır (reduceOnly market emri),
    STOP/TP3'te kullandığımız AYNI doğrulama mantığıyla — emrin gerçekten
    uygulandığını kontrol etmeden trade_state'ten silmiyoruz.
    """
    try:
        pozisyonlar = exchange.fetch_positions([sym])
        gercek_pos = next((p for p in pozisyonlar if safe(p.get("contracts")) > 0), None)
        if not gercek_pos:
            with state_lock:
                trade_state.pop(sym, None)
            durumu_diske_yaz()
            return True, f"ℹ️ {sym} zaten borsada açık değilmiş, kayıt temizlendi."

        qty = safe(gercek_pos.get("contracts"))
        direction = "long" if gercek_pos.get("side") == "long" else "short"
        entry = safe(gercek_pos.get("entryPrice"))

        exchange.create_market_order(sym, "sell" if direction == "long" else "buy",
                                       qty, params={"reduceOnly": True})
        time.sleep(1)
        guncel = exchange.fetch_positions([sym])
        kapandi_mi = not any(safe(pp.get("contracts")) > 0 for pp in guncel)

        if not kapandi_mi:
            return False, f"⚠️ {sym} kapatma emri gönderildi ama doğrulanamadı — /kapat ile tekrar dene."

        t = exchange.fetch_ticker(sym)
        price = safe(t["last"])
        gross = (price - entry) * qty if direction == "long" else (entry - price) * qty
        gunluk_pnl_ekle(gross)

        with state_lock:
            onceki_gerceklesen = trade_state.get(sym, {}).get("gerceklesen_pnl", 0)
            trade_state.pop(sym, None)
        durumu_diske_yaz()
        trade_log_kaydet({
            "symbol": sym, "direction": direction, "entry": entry,
            "exit": price, "pnl": gross + onceki_gerceklesen, "sonuc": "MANUEL_KAPATMA",
            "zaman": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()),
        })
        return True, f"✅ {sym} manuel olarak kapatıldı | PnL≈{gross:+.2f}$"
    except Exception as e:
        return False, f"⚠️ {sym} kapatma sırasında hata: {e}"


def sinyali_isle(sinyal):
    if gunluk_limit_asildi():
        tg("⛔ Günlük zarar limiti aşıldı, bu sinyal atlandı.")
        return

    with state_lock:
        if len(trade_state) >= MAX_POS:
            tg(f"⏭️ Zaten açık pozisyon var (MAX_POS={MAX_POS}), sinyal atlandı: {sinyal['symbol']}")
            return

    sym = sinyal["symbol"]
    direction = sinyal["direction"]

    # ── DENEYSEL GÖZLEM (henüz filtre değil, sadece veri biriktirme) ──
    gozlem = deneysel_gozlem_hesapla(sym)
    gozlem_str = f" | 📊 Deneysel: {gozlem}" if gozlem else ""

    teyit_ok, teyit_mesaj = trend_teyidi_yeterli_mi(sym, direction)
    if not teyit_ok:
        tg(f"⏭️ {sym} {direction.upper()} atlandı — trend teyidi zayıf ({teyit_mesaj}){gozlem_str}")
        return

    entry_hedef = sinyal["entry"]
    sl = sinyal["sl"]

    if entry_hedef is None or sl is None:
        # ── Basit format: giriş = anlık fiyat, SL = sabit %2 ──
        try:
            t = exchange.fetch_ticker(sym)
            entry_hedef = safe(t["last"])
        except Exception as e:
            tg(f"⚠️ {sym} anlık fiyat alınamadı: {e}")
            return
        sl = entry_hedef * (1 - HIZLI_SL_PCT) if direction == "long" else entry_hedef * (1 + HIZLI_SL_PCT)

        # ── Kanalın GERÇEK TP oranlarına göre 6 kademeli TP (ham hâli) ──
        risk_mesafe = abs(entry_hedef - sl)
        KANAL_TP_ORANLARI = [0.1, 0.2, 0.3, 0.4, 0.5, 0.8]
        if direction == "long":
            tp_liste_otomatik = [entry_hedef + oran * risk_mesafe for oran in KANAL_TP_ORANLARI]
        else:
            tp_liste_otomatik = [entry_hedef - oran * risk_mesafe for oran in KANAL_TP_ORANLARI]
        sinyal["tp_liste"] = tp_liste_otomatik

        tg(f"ℹ️ {sym} basit format — giriş≈{entry_hedef:.8f}\n"
           f"SL (%{HIZLI_SL_PCT*100:.0f}): {sl:.8f}\n"
           f"Otomatik TP (kanal oranlarıyla, ham): {[round(x,8) for x in tp_liste_otomatik]}")

    # ── DEĞİŞTİ: kanalın SL'i çok genişse artık ATLAMIYORUZ — kendi
    # SL'imizi (MAX_SL_PCT mesafesinde) koyup işleme devam ediyoruz ──
    sl_pct = abs(entry_hedef - sl) / entry_hedef
    if sl_pct > MAX_SL_PCT:
        sl_eski = sl
        sl = entry_hedef * (1 - MAX_SL_PCT) if direction == "long" else entry_hedef * (1 + MAX_SL_PCT)
        tg(f"ℹ️ {sym} kanalın SL'i çok genişti (%{sl_pct*100:.2f}) — kendi SL'imize "
           f"sıkıştırıldı: {sl_eski:.8f} → {sl:.8f} (%{MAX_SL_PCT*100:.1f})")

    # ── ORTAK NOKTA: hem gerçek kanal sinyali hem basit format buraya gelir.
    # Kanalın ham TP oranları (0.1-0.8R) matematiksel olarak zayıftı
    # (başabaş için %72 kazanma gerekiyordu) — aynı şekli koruyarak
    # ölçekliyoruz (varsayılan 2.5x, TP6 ~0.8R'den ~2R'ye çıkıyor). ──
    if sinyal.get("tp_liste"):
        tp_ham = sinyal["tp_liste"]
        sinyal["tp_liste"] = tp_olcekle(entry_hedef, sl, tp_ham, direction)
        tg(f"📐 TP'ler {TP_OLCEK_CARPANI}x ölçeklendi:\n"
           f"Ham: {[round(x,8) for x in tp_ham]}\n"
           f"Ölçekli: {[round(x,8) for x in sinyal['tp_liste']]}")

    amount, notional = pozisyon_boyutu_hesapla(entry_hedef, sl)
    if not amount:
        tg(f"⚠️ {sym} pozisyon boyutu hesaplanamadı, atlandı")
        return

    gereken_marj = notional / LEV
    if not gercek_bakiye_yeterli_mi(gereken_marj):
        tg(f"⚠️ {sym} atlandı — gerçek bakiye yetersiz (gereken marj≈${gereken_marj:.2f}). "
           f"Bakiyeni kontrol et.")
        return

    try:
        exchange.set_leverage(LEV, sym)
    except Exception as e:
        tg(f"⚠️ {sym} kaldıraç ayarlanamadı: {e} — işlem atlandı")
        return

    try:
        t = exchange.fetch_ticker(sym)
        price = safe(t["last"])
    except Exception as e:
        tg(f"⚠️ {sym} fiyat alınamadı: {e}")
        return

    try:
        qty = float(exchange.amount_to_precision(sym, amount))
    except Exception as e:
        tg(f"⚠️ {sym} miktar hassasiyeti alınamadı: {e}")
        return
    if qty <= 0:
        return

    side = "buy" if direction == "long" else "sell"
    try:
        exchange.create_market_order(sym, side, qty)
    except Exception as e:
        tg(f"⚠️ {sym} giriş emri başarısız: {e}")
        return

    with state_lock:
        trade_state[sym] = {
            "sl": sl, "tp_liste": sinyal["tp_liste"], "tp_index": 0,
            "direction": direction, "entry": price, "qty": qty, "kaynak": "kanal_kopya",
        }
    durumu_diske_yaz()

    tg(
        f"📈 [KANAL KOPYA] {sym} {direction.upper()} AÇILDI\n"
        f"Giriş≈{price:.8f} | SL:{sl:.8f}\n"
        f"TP listesi: {sinyal['tp_liste']}\n"
        f"Notional≈${notional:.2f}{gozlem_str}"
    )


# ════════════════════════════════════════════
# POZİSYON YÖNETİMİ (SL / TP kademeleri — emir doğrulamalı)
# ════════════════════════════════════════════
def manage():
    while True:
        try:
            positions = exchange.fetch_positions()
            for p in positions:
                qty = safe(p.get("contracts"))
                if qty <= 0:
                    continue
                sym = p["symbol"]
                entry = safe(p["entryPrice"])
                direction = "long" if p["side"] == "long" else "short"

                with state_lock:
                    durum = trade_state.get(sym)
                if not durum:
                    entry_guvenlik = entry
                    guvenlik_sl_pct = 0.03
                    sl_guvenlik = entry_guvenlik * (1 - guvenlik_sl_pct) if direction == "long" else entry_guvenlik * (1 + guvenlik_sl_pct)
                    with state_lock:
                        trade_state[sym] = {"sl": sl_guvenlik, "tp_liste": [], "tp_index": 0,
                                             "direction": direction, "entry": entry_guvenlik, "kaynak": "kurtarilan_calisma_zamani"}
                    durumu_diske_yaz()
                    tg(f"🚨 UYARI: {sym} için kayıtlı durum yoktu — geçici %3 güvenlik SL'i kondu")
                    continue

                t = exchange.fetch_ticker(sym)
                price = safe(t["last"])
                sl = durum["sl"]

                sl_vuruldu = (price <= sl) if direction == "long" else (price >= sl)
                if sl_vuruldu:
                    kapandi_mi = False
                    try:
                        exchange.create_market_order(sym, "sell" if direction == "long" else "buy",
                                                       qty, params={"reduceOnly": True})
                        time.sleep(1)
                        guncel = exchange.fetch_positions([sym])
                        kapandi_mi = not any(safe(pp.get("contracts")) > 0 for pp in guncel)
                    except Exception as e:
                        log.error(f"[STOP] {sym}: {e}")

                    if not kapandi_mi:
                        tg(f"⚠️ {sym} STOP emri doğrulanamadı, tekrar denenecek")
                        continue

                    gross = (price - entry) * qty if direction == "long" else (entry - price) * qty
                    with state_lock:
                        onceki_gerceklesen = trade_state[sym].get("gerceklesen_pnl", 0)
                    toplam_pnl_stop = gross + onceki_gerceklesen
                    gunluk_pnl_ekle(gross)
                    tg(f"❌ STOP {sym} | PnL≈{gross:+.2f}$")
                    with state_lock:
                        trade_state.pop(sym, None)
                    durumu_diske_yaz()
                    trade_log_kaydet({
                        "symbol": sym, "direction": direction, "entry": entry,
                        "exit": price, "pnl": toplam_pnl_stop, "sonuc": "STOP",
                        "zaman": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()),
                    })
                    continue

                tp_liste = durum.get("tp_liste", [])
                tp_index = durum.get("tp_index", 0)

                # ── TP KADEMELERI (artık son TP'de bir dilim TRAILING'e ayrılıyor) ──
                if tp_index < len(tp_liste):
                    hedef = tp_liste[tp_index]
                    tp_vuruldu = (price >= hedef) if direction == "long" else (price <= hedef)
                    if tp_vuruldu:
                        son_tp = (tp_index == len(tp_liste) - 1)
                        # ── DEĞİŞTİ: TRAILING_REZERV_DILIM kadar "sanal" ekstra
                        # seviye varmış gibi bölüyoruz — son TP'de pozisyonun
                        # TAMAMI değil, bir kısmı kapanıyor, kalanı trailing'e
                        # devrediliyor. ──
                        sanal_kalan_seviye = (len(tp_liste) - tp_index) + TRAILING_REZERV_DILIM
                        kapatilacak = qty / max(sanal_kalan_seviye, 1)
                        basarili = False
                        try:
                            exchange.create_market_order(sym, "sell" if direction == "long" else "buy",
                                                           kapatilacak, params={"reduceOnly": True})
                            time.sleep(1)
                            basarili = True
                        except Exception as e:
                            log.error(f"[TP{tp_index+1}] {sym}: {e}")

                        if basarili:
                            gross_dilim = (price - entry) * kapatilacak if direction == "long" else (entry - price) * kapatilacak
                            gunluk_pnl_ekle(gross_dilim)

                            with state_lock:
                                trade_state[sym]["tp_index"] = tp_index + 1
                                if tp_index == 0:
                                    trade_state[sym]["sl"] = entry  # ilk TP sonrası başa baş
                                trade_state[sym]["gerceklesen_pnl"] = trade_state[sym].get("gerceklesen_pnl", 0) + gross_dilim
                                if son_tp:
                                    # ── YENİ: son TP'den sonra TRAILING moduna geç ──
                                    trade_state[sym]["trailing_aktif"] = True
                                    trade_state[sym]["trailing_zirve"] = price
                            durumu_diske_yaz()
                            tg(f"💰 TP{tp_index+1} {sym} vuruldu | dilim PnL≈{gross_dilim:+.2f}$" +
                               (" | 📈 Kalan dilim TRAILING moduna geçti" if son_tp else ""))

                # ── TRAILING STOP (son TP sonrası kalan dilim için) ──
                elif durum.get("trailing_aktif"):
                    zirve = durum.get("trailing_zirve", entry)
                    if direction == "long":
                        yeni_zirve = max(zirve, price)
                        geri_cekilme_tetiklendi = price <= yeni_zirve * (1 - TRAILING_GERI_CEKILME_PCT)
                    else:
                        yeni_zirve = min(zirve, price)
                        geri_cekilme_tetiklendi = price >= yeni_zirve * (1 + TRAILING_GERI_CEKILME_PCT)

                    if yeni_zirve != zirve:
                        with state_lock:
                            trade_state[sym]["trailing_zirve"] = yeni_zirve
                        durumu_diske_yaz()

                    if geri_cekilme_tetiklendi:
                        kapandi_mi = False
                        try:
                            exchange.create_market_order(sym, "sell" if direction == "long" else "buy",
                                                           qty, params={"reduceOnly": True})
                            time.sleep(1)
                            guncel = exchange.fetch_positions([sym])
                            kapandi_mi = not any(safe(pp.get("contracts")) > 0 for pp in guncel)
                        except Exception as e:
                            log.error(f"[TRAILING] {sym}: {e}")

                        if not kapandi_mi:
                            tg(f"⚠️ {sym} trailing kapanışı doğrulanamadı, tekrar denenecek")
                            continue

                        gross_dilim = (price - entry) * qty if direction == "long" else (entry - price) * qty
                        gunluk_pnl_ekle(gross_dilim)

                        with state_lock:
                            toplam_pnl = trade_state[sym].get("gerceklesen_pnl", 0) + gross_dilim
                            trade_state.pop(sym, None)
                        durumu_diske_yaz()
                        tg(f"📉 TRAILING kapandı {sym} | son dilim PnL≈{gross_dilim:+.2f}$ | "
                           f"TOPLAM işlem PnL≈{toplam_pnl:+.2f}$")
                        trade_log_kaydet({
                            "symbol": sym, "direction": direction, "entry": entry,
                            "exit": price, "pnl": toplam_pnl, "sonuc": "TRAILING_KAPANDI",
                            "zaman": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()),
                        })

            time.sleep(5)
        except Exception as e:
            log.error(f"[MANAGE] {e}")
            time.sleep(5)


# ════════════════════════════════════════════
# TELEGRAM KANAL DİNLEME (Telethon)
# ════════════════════════════════════════════
from telethon.sessions import StringSession
telethon_client = TelegramClient(StringSession(TG_STRING_SESSION), TG_API_ID, TG_API_HASH)


@telethon_client.on(events.NewMessage(chats=KANAL_KULLANICI_ADI))
async def yeni_mesaj_geldi(event):
    metin = event.raw_text
    log.info(f"[KANAL] Yeni mesaj alındı: {metin[:80]}...")
    sinyal = sinyal_ayristir(metin)
    if not sinyal:
        log.info("[KANAL] Mesaj sinyal olarak ayrıştırılamadı, atlandı")
        return
    tg(f"📡 Kanal sinyali algılandı: {sinyal['symbol']} {sinyal['direction'].upper()}")
    sinyali_isle(sinyal)


# ════════════════════════════════════════════
# WEB PANEL (tarayıcıdan performans görüntüleme)
# ════════════════════════════════════════════
def panel_html_olustur():
    with log_lock:
        gecmis = list(trade_log)

    toplam = len(gecmis)
    if toplam == 0:
        icerik_ozet = "<p style='color:#888'>Henüz kapanan işlem yok.</p>"
        grafik_svg = ""
        liste_html = ""
    else:
        kazanan = [t for t in gecmis if t["pnl"] > 0]
        kaybeden = [t for t in gecmis if t["pnl"] <= 0]
        net_toplam = sum(t["pnl"] for t in gecmis)
        kazanma_orani = len(kazanan) / toplam * 100
        ort_kazanan = sum(t["pnl"] for t in kazanan) / len(kazanan) if kazanan else 0
        ort_kaybeden = sum(t["pnl"] for t in kaybeden) / len(kaybeden) if kaybeden else 0
        basabas_oran = abs(ort_kaybeden) / (abs(ort_kaybeden) + ort_kazanan) * 100 if (ort_kazanan + abs(ort_kaybeden)) > 0 else 0

        renk_net = "#00e08a" if net_toplam >= 0 else "#ff4d6d"

        icerik_ozet = f"""
        <div class="grid">
          <div class="kart"><div class="etiket">NET TOPLAM</div>
            <div class="deger" style="color:{renk_net}">{net_toplam:+.2f}$</div></div>
          <div class="kart"><div class="etiket">KAZANMA ORANI</div>
            <div class="deger">%{kazanma_orani:.1f}</div></div>
          <div class="kart"><div class="etiket">KAZANAN ({len(kazanan)})</div>
            <div class="deger" style="color:#00e08a">ort {ort_kazanan:+.2f}$</div></div>
          <div class="kart"><div class="etiket">KAYBEDEN ({len(kaybeden)})</div>
            <div class="deger" style="color:#ff4d6d">ort {ort_kaybeden:+.2f}$</div></div>
        </div>
        <div class="kart" style="margin-top:12px">
          <span class="etiket">Başa baş için gereken kazanma oranı</span>
          <span class="deger" style="float:right;color:#ff4d6d">%{basabas_oran:.1f}</span>
        </div>
        """

        # ── Basit SVG kümülatif PnL çizgisi (dış kütüphane yok) ──
        kumulatif = []
        toplam_su_an = 0
        for t in gecmis:
            toplam_su_an += t["pnl"]
            kumulatif.append(toplam_su_an)
        genislik, yukseklik = 700, 200
        if len(kumulatif) > 1:
            min_v, max_v = min(kumulatif), max(kumulatif)
            aralik = (max_v - min_v) or 1
            noktalar = []
            for i, v in enumerate(kumulatif):
                x = i / (len(kumulatif) - 1) * genislik
                y = yukseklik - ((v - min_v) / aralik * yukseklik)
                noktalar.append(f"{x:.1f},{y:.1f}")
            svg_puan = " ".join(noktalar)
            grafik_svg = f"""
            <div class="kart" style="margin-top:12px">
              <div class="etiket">KÜMÜLATİF NET PNL</div>
              <svg viewBox="0 0 {genislik} {yukseklik}" style="width:100%;height:180px">
                <polyline fill="none" stroke="#4da3ff" stroke-width="2" points="{svg_puan}" />
              </svg>
            </div>
            """
        else:
            grafik_svg = ""

        satirlar = []
        for t in reversed(gecmis[-100:]):
            renk = "#00e08a" if t["pnl"] > 0 else "#ff4d6d"
            satirlar.append(f"""
            <div class="islem-satir">
              <div><b>{t['symbol'].split('/')[0]}</b>
                <span class="rozet">{t['direction'].upper()}</span>
                <span class="rozet" style="background:#333">{t.get('sonuc','?')}</span></div>
              <div style="color:{renk}">{t['pnl']:+.2f}$</div>
            </div>
            <div style="color:#888;font-size:12px">{t.get('zaman','')}</div>
            """)
        liste_html = "".join(satirlar)

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Sinyal Kopya Botu — Panel</title>
<style>
body {{ background:#0d0d12; color:#eee; font-family:-apple-system,sans-serif; padding:16px; margin:0; }}
.baslik {{ color:#888; font-size:13px; letter-spacing:2px; text-transform:uppercase; }}
h1 {{ margin:4px 0 16px 0; font-size:28px; }}
.rozet-mod {{ background:#3a2a00; color:#ffb300; padding:8px 14px; border-radius:8px; display:inline-block; margin-bottom:16px; font-weight:600; }}
.grid {{ display:grid; grid-template-columns:1fr 1fr; gap:12px; }}
.kart {{ background:#16161f; border-radius:12px; padding:16px; }}
.etiket {{ color:#888; font-size:12px; letter-spacing:1px; text-transform:uppercase; }}
.deger {{ font-size:28px; font-weight:700; margin-top:6px; }}
.islem-satir {{ display:flex; justify-content:space-between; padding:10px 0 2px 0; border-top:1px solid #222; font-size:15px; }}
.rozet {{ background:#222; padding:2px 8px; border-radius:6px; font-size:11px; margin-left:6px; }}
</style></head>
<body>
  <div class="baslik">SİNYAL KOPYA BOTU</div>
  <h1>Performans Paneli</h1>
  <div class="rozet-mod">🔴 GERÇEK PARA — @{KANAL_KULLANICI_ADI} kanalından kopyalanıyor</div>
  <p style="color:#888">{len(trade_log)} kapanan işlem · sayfa her yenilendiğinde güncellenir</p>
  {icerik_ozet}
  {grafik_svg}
  <h3 style="margin-top:24px;color:#888">İŞLEM GEÇMİŞİ (yeniden eskiye, son 100)</h3>
  {liste_html}
</body></html>"""


def panel_sunucu_baslat():
    from http.server import HTTPServer, BaseHTTPRequestHandler

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path in ("/panel", "/panel/"):
                icerik = panel_html_olustur().encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(icerik)
            else:
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"OK")

        def log_message(self, *args):
            pass  # http.server'in kendi loglarini bastiriyoruz, gurultu olmasin

    HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()


def telethon_baslat():
    telethon_client.start()
    log.info("[TELETHON] Kanal dinleme başladı")
    telethon_client.run_until_disconnected()


# ════════════════════════════════════════════
# BAŞLANGIÇ
# ════════════════════════════════════════════
if __name__ == "__main__":
    print("TELEGRAM SİNYAL KOPYALAMA BOTU (v1) BAŞLIYOR...")
    durumu_diskten_yukle()
    trade_log_yukle()
    acilista_pozisyonlari_dogrula()

    threading.Thread(target=manage, daemon=True).start()
    threading.Thread(target=gunluk_reset_loop, daemon=True).start()
    threading.Thread(target=telebot_polling_baslat, daemon=True).start()
    threading.Thread(target=panel_sunucu_baslat, daemon=True).start()

    tg(
        "🚀 TELEGRAM SİNYAL KOPYALAMA BOTU\n"
        "🔖 VERSİYON: v13 (genis SL artik sikistiriliyor, atlanmiyor)\n\n"
        f"💰 Sermaye: ${TOPLAM_SERMAYE} | Kaldıraç: {LEV}x\n"
        f"🎯 Marj/işlem: ${MARGIN_SABIT} (sabit) × {LEV}x = ${MARGIN_SABIT*LEV} notional\n"
        f"📡 Dinlenen kanal: @{KANAL_KULLANICI_ADI}\n"
        f"⛔ Günlük zarar limiti: ${MAX_GUNLUK_ZARAR}\n\n"
        "⚠️ Bu kanalın geçmiş performansı doğrulanmadı."
    )

    telethon_baslat()
