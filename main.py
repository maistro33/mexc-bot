#!/usr/bin/env python3
"""
TELEGRAM SİNYAL KOPYALAMA + AUTO TRADER BOTU — GERÇEK PARA
🔖 VERSİYON: v16.10-AUTO
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Belirtilen Telegram kanalını (https://t.me/Kripto_Botu gibi) dinler,
gelen sinyalleri ayrıştırır, Bitget'te GERÇEK PARA ile açar.
Ayrıca kendi "pro trader" stratejisiyle (trend + RSI + MACD + Bollinger)
kendi sinyallerini üretir ve işlem açar.

ÇALIŞTIRMA:
  - session_olustur.py'yi bir kez kendi bilgisayarında çalıştır.
  - STRING_SESSION, TG_API_ID, TG_API_HASH, TELE_TOKEN, BITGET_API,
    BITGET_SEC, BITGET_PASS, MY_CHAT_ID, KANAL_USERNAME gibi
    ortam değişkenlerini ayarla.
  - TRADE_MODE:
      SIGNAL_ONLY        → sadece kanal sinyalleri
      AUTO_ONLY          → sadece kendi strateji
      SIGNAL_AND_AUTO    → hem kanal hem kendi strateji (önerilen)

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
log = logging.getLogger("SIGNAL_COPY_AUTO")

# ════════════════════════════════════════════
# CONFIG
# ════════════════════════════════════════════
TELE_TOKEN   = os.getenv("TELE_TOKEN", "")       # kendi bildirim botun
CHAT_ID      = int(os.getenv("MY_CHAT_ID", "0"))
API_KEY      = os.getenv("BITGET_API", "")
API_SEC      = os.getenv("BITGET_SEC", "")
PASSPHRASE   = os.getenv("BITGET_PASS", "")

TG_API_ID    = int(os.getenv("TG_API_ID", "0"))
TG_API_HASH  = os.getenv("TG_API_HASH", "")
TG_STRING_SESSION = os.getenv("STRING_SESSION", "") or os.getenv("TG_SESSION", "")
KANAL_KULLANICI_ADI = os.getenv("KANAL_USERNAME", "FuturesKripto")

TRADE_MODE = os.getenv("TRADE_MODE", "SIGNAL_AND_AUTO").upper()

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
MARGIN_SABIT     = 10.0
LEV              = 10
MAX_POS          = 2
MIN_POS_NOTIONAL = 30.0

MAX_GUNLUK_ZARAR = -10.0

TRADE_STATE_PATH = os.getenv("TRADE_STATE_PATH", "/data/signal_copy_state.json")
TRADE_LOG_PATH = os.getenv("TRADE_LOG_PATH", "/data/signal_copy_log.json")
PORT = int(os.getenv("PORT", "8080"))

# ════════════════════════════════════════════
# TELEGRAM BİLDİRİM (kendi bot token'ın)
# ════════════════════════════════════════════
bot = telebot.TeleBot(TELE_TOKEN) if TELE_TOKEN else None


if bot:
    @bot.message_handler(commands=["manuel"])
    def manuel_sinyal_komutu(msg):
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
        parca = msg.text.replace("/kapat", "", 1).strip().upper()
        basari, mesaj = _pozisyon_kapat_yardimci(msg.chat.id, parca)
        bot.send_message(msg.chat.id, mesaj)

    KISA_MESAJ_UST_SINIR = 30

    def _pozisyon_kapat_yardimci(chat_id, parca):
        with state_lock:
            acik_semboller = list(trade_state.keys())

        if not acik_semboller:
            return False, "Açık pozisyon yok, kapatılacak bir şey bulunamadı."

        hedef_sym = None
        if parca:
            for sym in acik_semboller:
                if parca in sym.upper():
                    hedef_sym = sym
                    break
            if not hedef_sym:
                return False, (f"'{parca}' ile eşleşen açık pozisyon bulunamadı. "
                                f"Açık olanlar: {acik_semboller}")
        else:
            if len(acik_semboller) > 1:
                return False, (f"Birden fazla açık pozisyon var, hangisini kastettiğini belirt: "
                                f"{acik_semboller}\nÖrn: /kapat {acik_semboller[0].split('/')[0]}")
            hedef_sym = acik_semboller[0]

        bot.send_message(chat_id, f"⏳ {hedef_sym} kapatılıyor...")
        return manuel_pozisyon_kapat(hedef_sym)

    def komut_metni_ayikla(metin):
        temiz = metin.strip()
        if not temiz or len(temiz) > KISA_MESAJ_UST_SINIR:
            return None, None

        if re.search(r"\bkapat\b", temiz, re.IGNORECASE):
            sembol_parca = re.sub(r"\bkapat\b", "", temiz, flags=re.IGNORECASE)
            sembol_parca = re.sub(r"\bet\b", "", sembol_parca, flags=re.IGNORECASE).strip().upper()
            return "kapat", sembol_parca

        sinyal = hizli_sinyal_ayristir(temiz)
        if sinyal:
            return "ac", sinyal

        return None, None

    @bot.message_handler(func=lambda m: m.text and not m.text.startswith("/"))
    def komutsuz_hizli_giris(msg):
        tur, veri = komut_metni_ayikla(msg.text)

        if tur == "kapat":
            basari, mesaj = _pozisyon_kapat_yardimci(msg.chat.id, veri)
            bot.send_message(msg.chat.id, mesaj)
            return

        if tur == "ac":
            sinyal = veri
            bot.send_message(msg.chat.id, f"⚡ Hızlı giriş algılandı: {sinyal['symbol']} {sinyal['direction'].upper()}")
            sinyali_isle(sinyal)
            return

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


def gercek_dolus_bilgisi_al(emir, sym, tahmini_fiyat):
    fiyat = safe(emir.get("average")) or safe(emir.get("price"))
    komisyon = 0.0
    try:
        fee = emir.get("fee")
        if fee:
            komisyon = safe(fee.get("cost"))
    except Exception:
        pass

    if not fiyat:
        try:
            time.sleep(0.5)
            detay = exchange.fetch_order(emir.get("id"), sym)
            fiyat = safe(detay.get("average")) or safe(detay.get("price"))
            fee = detay.get("fee")
            if fee:
                komisyon = safe(fee.get("cost"))
        except Exception as e:
            log.warning(f"[DOLUS] {sym} emir detayı alınamadı, tahmini fiyata dönülüyor: {e}")

    if not fiyat:
        fiyat = tahmini_fiyat

    return fiyat, komisyon


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
    durumu_telegrama_yedekle()


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
# TELEGRAM ÜZERİNDEN KALICI YEDEK (v16.8)
# ════════════════════════════════════════════
STATE_PIN_ETIKETI = "🗄️ BOT_DURUM_YEDEK (dokunma — otomatik güncellenir)"
_pin_message_id = None
_pin_lock = threading.Lock()


def durumu_telegrama_yedekle():
    global _pin_message_id
    if not bot or not CHAT_ID:
        return
    try:
        with state_lock:
            veri_state = dict(trade_state)
        try:
            with bekleyen_lock:
                veri_bekleyen = {
                    sym: {"sinyal": k["sinyal"], "gozlem_str": k["gozlem_str"],
                          "eklenme_zamani": k["eklenme_zamani"]}
                    for sym, k in bekleyen_sinyaller.items()
                }
        except NameError:
            veri_bekleyen = {}

        icerik = json.dumps({"trade_state": veri_state, "bekleyen_sinyaller": veri_bekleyen})
        metin = f"{STATE_PIN_ETIKETI}\n{icerik}"
        if len(metin) > 4000:
            log.warning("[TG_YEDEK] Durum verisi çok büyük (>4000 karakter), Telegram'a yazılamadı")
            return

        with _pin_lock:
            if _pin_message_id:
                try:
                    bot.edit_message_text(metin, CHAT_ID, _pin_message_id)
                    return
                except Exception:
                    pass

            gonderilen = bot.send_message(CHAT_ID, metin)
            _pin_message_id = gonderilen.message_id
            try:
                bot.pin_chat_message(CHAT_ID, _pin_message_id, disable_notification=True)
            except Exception as e:
                log.warning(f"[TG_YEDEK] Sabitleme başarısız (yine de çalışmaya devam eder): {e}")
    except Exception as e:
        log.warning(f"[TG_YEDEK] Telegram'a yazma başarısız: {e}")


def durumu_telegramdan_yukle():
    global trade_state, _pin_message_id
    if not bot or not CHAT_ID:
        return
    try:
        chat = bot.get_chat(CHAT_ID)
        pinned = getattr(chat, "pinned_message", None)
        if not pinned or not pinned.text or STATE_PIN_ETIKETI not in pinned.text:
            log.info("[TG_YEDEK] Sabitlenmiş durum mesajı bulunamadı, boş başlanıyor")
            return
        _pin_message_id = pinned.message_id
        json_kismi = pinned.text.split("\n", 1)[1]
        veri = json.loads(json_kismi)

        yuklenen_state = veri.get("trade_state", {})
        with state_lock:
            trade_state.update(yuklenen_state)

        yuklenen_bekleyen = veri.get("bekleyen_sinyaller", {})
        with bekleyen_lock:
            for sym, kayit in yuklenen_bekleyen.items():
                bekleyen_sinyaller[sym] = kayit

        if yuklenen_state or yuklenen_bekleyen:
            tg(f"♻️ Telegram yedeğinden geri yüklendi: {len(yuklenen_state)} açık işlem, "
               f"{len(yuklenen_bekleyen)} bekleyen sinyal")
    except Exception as e:
        log.warning(f"[TG_YEDEK] Telegram'dan yükleme başarısız: {e}")


# ════════════════════════════════════════════
# TRADE LOG
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


def acik_pozisyonlara_kademeli_sl_uygula():
    with state_lock:
        semboller = list(trade_state.keys())

    for sym in semboller:
        with state_lock:
            durum = trade_state.get(sym)
        if not durum:
            continue

        tp_index = durum.get("tp_index", 0)
        tp_liste = durum.get("tp_liste", [])
        entry = durum.get("entry")
        direction = durum.get("direction")
        mevcut_sl = durum.get("sl")

        if tp_index == 0 or not tp_liste or entry is None or mevcut_sl is None or direction is None:
            continue

        if tp_index == 1:
            onerilen_sl = entry * (1 - TP1_BREAKEVEN_TAMPON_PCT) if direction == "long" \
                          else entry * (1 + TP1_BREAKEVEN_TAMPON_PCT)
        else:
            hedef_index = tp_index - 2
            if hedef_index < 0 or hedef_index >= len(tp_liste):
                continue
            onerilen_sl = tp_liste[hedef_index]

        sl_iyilesir_mi = (direction == "long" and onerilen_sl > mevcut_sl) or \
                          (direction == "short" and onerilen_sl < mevcut_sl)
        if sl_iyilesir_mi:
            with state_lock:
                trade_state[sym]["sl"] = onerilen_sl
            durumu_diske_yaz()
            tg(f"🔄 {sym} — bot güncellendi, yeni kademeli SL kuralı UYGULANDI: "
               f"{mevcut_sl:.8f} → {onerilen_sl:.8f} (TP{tp_index} zaten vurulmuş durumdaydı)")


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
# SİNYAL AYRIŞTIRMA
# ════════════════════════════════════════════
HIZLI_SL_PCT = 0.02
MAX_SL_PCT = 0.03

def hizli_sinyal_ayristir(metin):
    m = re.search(r"\b([A-Za-z][A-Za-z0-9]{1,10})\b.*?\b(LONG|SHORT)\b", metin, re.IGNORECASE)
    if not m:
        return None
    sembol = m.group(1).upper()
    if sembol in ("LONG", "SHORT", "AC", "KAPAT"):
        return None
    yon = "long" if m.group(2).upper() == "LONG" else "short"
    return {"symbol": f"{sembol}/USDT:USDT", "direction": yon, "entry": None, "sl": None, "tp_liste": []}


def sinyal_ayristir(metin):
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
    if entry <= 0:
        return None, None
    notional = MARGIN_SABIT * LEV
    amount = notional / entry
    return amount, notional


def gercek_bakiye_yeterli_mi(gereken_marj):
    try:
        bakiye = exchange.fetch_balance()
        serbest_usdt = safe(bakiye.get("USDT", {}).get("free", 0))
    except Exception as e:
        log.warning(f"[BAKIYE] Kontrol edilemedi: {e}")
        return True
    return serbest_usdt >= gereken_marj


TP_OLCEK_CARPANI = 2.0

TP_DILIM_ORANLARI = [0.15, 0.15, 0.15]
TP_SAYISI_KULLANILAN = 3

TP1_BREAKEVEN_TAMPON_PCT = 0.0015

TRAILING_GERI_CEKILME_PCT = 0.035

TRAILING_BILDIRIM_ESIK_PCT = 0.01

TP1_EK_GENISLETME_CARPANI = 1.5


def tp_olcekle(entry, sl, tp_liste, direction, carpan=TP_OLCEK_CARPANI):
    risk_mesafe = abs(entry - sl)
    if risk_mesafe <= 0 or not tp_liste:
        return tp_liste
    yeni_liste = []
    for i, tp in enumerate(tp_liste):
        oran = abs(tp - entry) / risk_mesafe
        yeni_oran = oran * carpan
        if i == 0:
            yeni_oran *= TP1_EK_GENISLETME_CARPANI
        yeni_tp = entry + yeni_oran * risk_mesafe if direction == "long" else entry - yeni_oran * risk_mesafe
        yeni_liste.append(yeni_tp)
    return yeni_liste


# ════════════════════════════════════════════
# PRO TRADER STRATEJİ (AUTO TRADER)
# ════════════════════════════════════════════
def calc_macd_hist(kapaniş_listesi, hizli=12, yavas=26, sinyal=9):
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


def calc_sma(kapaniş_listesi, period=20):
    import pandas as pd
    s = pd.Series(kapaniş_listesi)
    orta = s.rolling(period).mean()
    son = orta.iloc[-1]
    return float(son) if not pd.isna(son) else None


def calc_rsi(kapaniş_listesi, period=14):
    import pandas as pd
    s = pd.Series(kapaniş_listesi)
    fark = s.diff()
    kazanc = fark.clip(lower=0)
    kayip = -fark.clip(upper=0)
    ort_kazanc = kazanc.rolling(period).mean()
    ort_kayip = kayip.rolling(period).mean()
    rs = ort_kazanc / ort_kayip.replace(0, 0.0001)
    rsi = 100 - (100 / (1 + rs))
    son = rsi.iloc[-1]
    return float(son) if not pd.isna(son) else None


def generate_auto_signal(pairs):
    """
    Pro trader mantığıyla kendi sinyallerini üretir.
    """
    for sym in pairs:
        try:
            h4 = get_candles(sym, "4h", 30)
            h1 = get_candles(sym, "1h", 40)
            if not h4 or not h1 or len(h4) < 21 or len(h1) < 35:
                continue

            h4_kapanis = [c[4] for c in h4]
            h1_kapanis = [c[4] for c in h1]
            current_price = h4_kapanis[-1]

            ma20_4h = calc_sma(h4_kapanis, 20)
            if ma20_4h is None:
                continue

            rsi_1h = calc_rsi(h1_kapanis, 14)
            if rsi_1h is None:
                continue

            macd_1h = calc_macd_hist(h1_kapanis, 12, 26, 9)
            if macd_1h is None:
                continue

            boll_4h = calc_bollinger_yuzdeB(h4_kapanis, 20, 2.0)
            if boll_4h is None:
                continue

            long_cond = (
                current_price > ma20_4h and
                rsi_1h > 50 and
                macd_1h > 0 and
                boll_4h > 0.8
            )

            short_cond = (
                current_price < ma20_4h and
                rsi_1h < 50 and
                macd_1h < 0 and
                boll_4h < 0.2
            )

            direction = None
            if long_cond:
                direction = "long"
            elif short_cond:
                direction = "short"
            else:
                continue

            sl_pct = 0.025
            sl = current_price * (1 - sl_pct) if direction == "long" else current_price * (1 + sl_pct)

            risk = abs(current_price - sl)
            tp1 = current_price + 2 * risk if direction == "long" else current_price - 2 * risk
            tp2 = current_price + 3 * risk if direction == "long" else current_price - 3 * risk

            sinyal = {
                "symbol": sym,
                "direction": direction,
                "entry": current_price,
                "sl": sl,
                "tp_liste": [tp1, tp2]
            }
            return sinyal

        except Exception as e:
            log.warning(f"[AUTO] {sym} analiz hatası: {e}")
            continue

    return None


def auto_trader_loop():
    """
    Belirli bir periyotta kendi sinyallerini üretir ve açar.
    """
    pairs = [
        "BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT",
        "MAGIC/USDT:USDT", "RNDR/USDT:USDT", "AAVE/USDT:USDT"
    ]

    while True:
        try:
            if gunluk_limit_asildi():
                tg("⚠️ Günlük zarar limiti aşıldı, auto trader durduruldu.")
                time.sleep(60)
                continue

            with state_lock:
                acik_semboller = list(trade_state.keys())

            if len(acik_semboller) >= MAX_POS:
                log.info("[AUTO] Maksimum açık pozisyon sayısı ulaştı, bekleniyor...")
                time.sleep(5 * 60)
                continue

            sinyal = generate_auto_signal(pairs)
            if not sinyal:
                log.info("[AUTO] Bugün yeni sinyal bulunamadı.")
                time.sleep(5 * 60)
                continue

            if sinyal["symbol"] in acik_semboller:
                log.warning(f"[AUTO] {sinyal['symbol']} zaten açık, yeni sinyal üretilmedi.")
                time.sleep(5 * 60)
                continue

            tg(f"🤖 AUTO TRADER: {sinyal['symbol']} {sinyal['direction'].upper()} sinyali üretildi.")
            sinyali_isle(sinyal)

            time.sleep(5 * 60)

        except Exception as e:
            log.error(f"[AUTO_LOOP] {e}")
            time.sleep(60)


# ════════════════════════════════════════════
# POSİSYON YÖNETİMİ ve İŞLEM AÇMA
# ════════════════════════════════════════════
bekleyen_sinyaller = {}
bekleyen_lock = threading.Lock()


def durum_dukkan():
    while True:
        try:
            manage()
            time.sleep(5)
        except Exception as e:
            log.error(f"[MANAGE] {e}")
            time.sleep(10)


def manage():
    try:
        pozisyonlar = exchange.fetch_positions()
    except Exception as e:
        log.warning(f"[POS] fetch_positions: {e}")
        return

    for p in pozisyonlar:
        qty = safe(p.get("contracts"))
        if qty <= 0:
            continue
        sym = p["symbol"]
        entry = safe(p.get("entryPrice"))
        side = p.get("side")
        direction = "long" if side == "long" else "short"

        with state_lock:
            durum = trade_state.get(sym)
        if not durum:
            continue

        current = entry  # basit yaklaşım; gerçek yönetimde live ticker kullanılabilir

        tp_liste = durum.get("tp_liste", [])
        tp_index = durum.get("tp_index", 0)

        if tp_index < len(tp_liste):
            tp_target = tp_liste[tp_index]
            if direction == "long" and current >= tp_target:
                log.info(f"[TP] {sym} TP{tp_index+1} vurdu: {tp_target:.8f}")
                dilim = tp_liste[tp_index]
                kapat_pismi(sym, tp_index, dilim)
                with state_lock:
                    trade_state[sym]["tp_index"] = tp_index + 1
                durumu_diske_yaz()
                return

        guvenlik_sl = durum.get("sl")
        if guvenlik_sl:
            if direction == "long" and current <= guvenlik_sl:
                log.info(f"[SL] {sym} stop: {guvenlik_sl:.8f}")
                manuel_pozisyon_kapat(sym)
                return
            if direction == "short" and current >= guvenlik_sl:
                log.info(f"[SL] {sym} stop: {guvenlik_sl:.8f}")
                manuel_pozisyon_kapat(sym)
                return


def kapanis_pnl_hesapla(sym, entry, direction, kapanis_fiyat, miktar):
    gorev = (kapanis_fiyat - entry) if direction == "long" else (entry - kapanis_fiyat)
    pnl_usdt = gorev * miktar
    return pnl_usdt


def manuel_pozisyon_kapat(sym):
    try:
        pozisyonlar = exchange.fetch_positions()
    except Exception as e:
        tg(f"⚠️ Kapatma sırasında pozisyon listesi alınamadı: {e}")
        return False, "Kapatma başarısız: pozisyon listesi alınamadı."

    hedef = None
    for p in pozisyonlar:
        if p["symbol"] == sym:
            hedef = p
            break
    if not hedef:
        tg(f"⚠️ {sym} için açık pozisyon bulunamadı.")
        return False, f"{sym} için açık pozisyon bulunamadı."

    side = hedef.get("side")
    direction = "long" if side == "long" else "short"
    qty = safe(hedef.get("contracts"))
    if qty <= 0:
        return False, f"{sym} pozisyonu zaten açık değil."

    order_side = "sell" if direction == "long" else "buy"
    try:
        emir = exchange.create_order(sym, "market", order_side, qty, params={"reduceOnly": True})
    except Exception as e:
        tg(f"⚠️ Kapatma emri gönderilemedi: {e}")
        return False, f"Kapatma emri gönderilemedi: {e}"

    giriş_fiyat = safe(hedef.get("entryPrice"))
    dolus_fiyat, komisyon = gercek_dolus_bilgisi_al(emir, sym, giriş_fiyat)

    pnl_usdt = kapanis_pnl_hesapla(sym, giriş_fiyat, direction, dolus_fiyat, qty)

    with gunluk_lock:
        gunluk_pnl += pnl_usdt

    with state_lock:
        if sym in trade_state:
            del trade_state[sym]
    durumu_diske_yaz()

    kayit = {
        "symbol": sym,
        "direction": direction,
        "entry": giriş_fiyat,
        " kapatılma_fiyat ": dolus_fiyat,
        " miktar ": qty,
        " pnl_usdt ": pnl_usdt,
        " komisyon ": komisyon,
        " zaman": time.time()
    }
    trade_log_kaydet(kayit)

    tg(f"✅ {sym} KAPATILDI: giriş={giriş_fiyat:.8f} kapanış={dolus_fiyat:.8f} "
       f"pnl={pnl_usdt:+.2f}$ (komisyon={komisyon:.4f}$)")

    return True, f"{sym} başarılı kapatıldı."


def kapat_pismi(sym, tp_index, target):
    try:
        pozisyonlar = exchange.fetch_positions()
    except Exception as e:
        tg(f"⚠️ TP pışmı için pozisyon listesi alınamadı: {e}")
        return

    hedef = None
    for p in pozisyonlar:
        if p["symbol"] == sym:
            hedef = p
            break
    if not hedef:
        return

    side = hedef.get("side")
    direction = "long" if side == "long" else "short"
    qty = safe(hedef.get("contracts"))
    if qty <= 0:
        return

    # reduceOnly LIMIT emri
    try:
        emir = exchange.create_order(sym, "limit", "sell" if direction == "long" else "buy",
                                      qty, target, params={"reduceOnly": True, "timeInForce": "GTC"})
    except Exception as e:
        log.warning(f"[TP_LIMIT] {sym} TP{tp_index+1} limiti konulamadı: {e}")
        return

    tg(f"🎯 {sym} TP{tp_index+1} limit emri konuldu: {target:.8f}")


def sinyali_isle(sinyal):
    sym = sinyal["symbol"]
    direction = sinyal["direction"]

    if gunluk_limit_asildi():
        tg("⚠️ Günlük zarar limiti aşıldı, yeni işlem açılmıyor.")
        return

    with state_lock:
        if sym in trade_state:
            tg(f"⚠️ {sym} zaten açık, yeni işlem açılmıyor.")
            return
        if len(trade_state) >= MAX_POS:
            tg("⚠️ Maksimum açık pozisyon sayısı ulaştı, yeni işlem açılmıyor.")
            return

    entry = sinyal.get("entry")
    if entry is None:
        try:
            ticker = exchange.fetch_ticker(sym)
            entry = safe(ticker.get("last")) or safe(ticker.get("quoteLast"))
        except Exception as e:
            tg(f"⚠️ {sym} giriş fiyatı alınamadı: {e}")
            return

    sl = sinyal.get("sl")
    if sl is None:
        sl_pct = HIZLI_SL_PCT
        sl = entry * (1 - sl_pct) if direction == "long" else entry * (1 + sl_pct)

    sl_pct_from_entry = abs(entry - sl) / entry
    if sl_pct_from_entry > MAX_SL_PCT:
        sl = entry * (1 - MAX_SL_PCT) if direction == "long" else entry * (1 + MAX_SL_PCT)

    tp_liste = sinyal.get("tp_liste", [])
    if tp_liste:
        tp_liste = tp_olcekle(entry, sl, tp_liste, direction)
        tp_liste = tp_liste[:TP_SAYISI_KULLANILAN]
    else:
        risk = abs(entry - sl)
        tp_liste = [
            entry + 2 * risk if direction == "long" else entry - 2 * risk,
            entry + 3 * risk if direction == "long" else entry - 3 * risk,
            entry + 4 * risk if direction == "long" else entry - 4 * risk,
        ]

    amount, notional = pozisyon_boyutu_hesapla(entry, sl)
    if not amount or not notional:
        tg(f"⚠️ {sym} için pozisyon boyutu hesaplanamadı.")
        return

    if not notional >= MIN_POS_NOTIONAL:
        tg(f"⚠️ {sym} notional ({notional:.2f}$) minimumdan küçük.")
        return

    marj = notional / LEV
    if not gercek_bakiye_yeterli_mi(marj):
        tg(f"⚠️ Bakiye yetersiz: gerekli={marj:.2f}$")
        return

    side = "buy" if direction == "long" else "sell"
    try:
        emir = exchange.create_order(sym, "market", side, amount)
    except Exception as e:
        tg(f"⚠️ {sym} işlem açma emri gönderilemedi: {e}")
        return

    dolus_fiyat, komisyon = gercek_dolus_bilgisi_al(emir, sym, entry)

    with state_lock:
        trade_state[sym] = {
            "sl": sl,
            "tp_liste": tp_liste,
            "tp_index": 0,
            "direction": direction,
            "entry": dolus_fiyat,
            "kaynak": sinyal.get("kaynak", "kanal")
        }
    durumu_diske_yaz()

    tg(f"🚀 {sym} {direction.upper()} AÇILDI: "
       f"giriş={dolus_fiyat:.8f} SL={sl:.8f} TP={tp_liste[0]:.8f} "
       f"marj={marj:.2f}$ kom={komisyon:.4f}$")


# ════════════════════════════════════════════
# ANA BAŞLATMA
# ════════════════════════════════════════════
def main():
    trade_log_yukle()
    durumu_diskten_yukle()
    durumu_telegramdan_yukle()

    exchange.load_marks()
    acilista_pozisyonlari_dogrula()
    acik_pozisyonlara_kademeli_sl_uygula()

    threading.Thread(target=gunluk_reset_loop, daemon=True).start()
    threading.Thread(target=durum_dukkan, daemon=True).start()

    trade_mode = os.getenv("TRADE_MODE", "SIGNAL_AND_AUTO").upper()

    if trade_mode in ("AUTO_ONLY", "SIGNAL_AND_AUTO"):
        threading.Thread(target=auto_trader_loop, daemon=True).start()
        tg("🤖 AUTO TRADER modu aktif.")

    if trade_mode in ("SIGNAL_ONLY", "SIGNAL_AND_AUTO"):
        threading.Thread(target=telebot_polling_baslat, daemon=True).start()
        tg("📨 Sinyal kopyalama modu aktif.")

        client = TelegramClient(TG_STRING_SESSION, TG_API_ID, TG_API_HASH)

        async def on_message(event):
            if event.channel_id is None:
                return
            kanal = await client.get_entity(KANAL_KULLANICI_ADI)
            if event.channel_id != kanal.id:
                return
            metin = event.message.text
            if not metin:
                return
            log.info(f"[SIGNAL] {metin[:100]}")
            sinyal = sinyal_ayristir(metin)
            if not sinyal:
                sinyal = hizli_sinyal_ayristir(metin)
            if not sinyal:
                return
            sinyali_isle(sinyal)

        @client.on(events.NewMessage())
        def _(event):
            asyncio.get_event_loop().run_until_complete(on_message(event))

        client.start()
        client.run_until_disconnected()


if __name__ == "__main__":
    main()
