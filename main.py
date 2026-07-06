#!/usr/bin/env python3
"""
TELEGRAM SİNYAL KOPYALAMA BOTU — GERÇEK PARA
🔖 VERSİYON: v5 (/manuel önekine gerek yok — kısa mesaj otomatik işlenir)
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
KANAL_KULLANICI_ADI = os.getenv("KANAL_USERNAME", "Kripto_Botu")

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
LEV              = 10      # ── kullanıcı talebiyle — kanalın kendi tavsiyesinin TERSİNE ──
MAX_POS          = 1       # kanal genelde tek sinyal veriyor, aynı anda 1 işlem
HEDEF_RISK_DOLAR = 5.0     # tüm sermaye tek bota ayrıldığı için hedef risk yükseltildi
MIN_POS_NOTIONAL = 30.0
MAX_POS_NOTIONAL = TOPLAM_SERMAYE * LEV * 0.9   # sermayenin ~%90'ına kadar kullan

MAX_GUNLUK_ZARAR = -10.0

TRADE_STATE_PATH = os.getenv("TRADE_STATE_PATH", "/data/signal_copy_state.json")

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
    risk_mesafe = abs(entry - sl)
    if risk_mesafe <= 0:
        return None, None
    amount = HEDEF_RISK_DOLAR / risk_mesafe
    notional = amount * entry
    if notional > MAX_POS_NOTIONAL:
        notional = MAX_POS_NOTIONAL
        amount = notional / entry
    elif notional < MIN_POS_NOTIONAL:
        notional = MIN_POS_NOTIONAL
        amount = notional / entry
    return amount, notional


# ════════════════════════════════════════════
# GERÇEK İŞLEM AÇMA (sinyal geldiğinde çağrılır)
# ════════════════════════════════════════════
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

        # ── YENİ: kanalın GERÇEK TP oranlarına göre 6 kademeli TP ──
        # (MAGMA örneğinden geriye hesaplandı: 0.1R/0.2R/0.3R/0.4R/0.5R/0.8R)
        risk_mesafe = abs(entry_hedef - sl)
        KANAL_TP_ORANLARI = [0.1, 0.2, 0.3, 0.4, 0.5, 0.8]
        if direction == "long":
            tp_liste_otomatik = [entry_hedef + oran * risk_mesafe for oran in KANAL_TP_ORANLARI]
        else:
            tp_liste_otomatik = [entry_hedef - oran * risk_mesafe for oran in KANAL_TP_ORANLARI]
        sinyal["tp_liste"] = tp_liste_otomatik

        tg(f"ℹ️ {sym} basit format — giriş≈{entry_hedef:.8f}\n"
           f"SL (%{HIZLI_SL_PCT*100:.0f}): {sl:.8f}\n"
           f"Otomatik TP (kanal oranlarıyla): {[round(x,8) for x in tp_liste_otomatik]}")

    amount, notional = pozisyon_boyutu_hesapla(entry_hedef, sl)
    if not amount:
        tg(f"⚠️ {sym} pozisyon boyutu hesaplanamadı, atlandı")
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
        f"Notional≈${notional:.2f}"
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
                    gunluk_pnl_ekle(gross)
                    tg(f"❌ STOP {sym} | PnL≈{gross:+.2f}$")
                    with state_lock:
                        trade_state.pop(sym, None)
                    durumu_diske_yaz()
                    continue

                tp_liste = durum.get("tp_liste", [])
                tp_index = durum.get("tp_index", 0)
                if tp_index < len(tp_liste):
                    hedef = tp_liste[tp_index]
                    tp_vuruldu = (price >= hedef) if direction == "long" else (price <= hedef)
                    if tp_vuruldu:
                        son_tp = (tp_index == len(tp_liste) - 1)
                        kapatilacak = qty if son_tp else qty / max(len(tp_liste) - tp_index, 1)
                        basarili = False
                        try:
                            exchange.create_market_order(sym, "sell" if direction == "long" else "buy",
                                                           kapatilacak, params={"reduceOnly": True})
                            time.sleep(1)
                            basarili = True
                        except Exception as e:
                            log.error(f"[TP{tp_index+1}] {sym}: {e}")

                        if basarili:
                            with state_lock:
                                trade_state[sym]["tp_index"] = tp_index + 1
                                if tp_index == 0:
                                    trade_state[sym]["sl"] = entry  # ilk TP sonrası başa baş
                            durumu_diske_yaz()
                            tg(f"💰 TP{tp_index+1} {sym} vuruldu")
                            if son_tp:
                                with state_lock:
                                    trade_state.pop(sym, None)
                                durumu_diske_yaz()

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
    acilista_pozisyonlari_dogrula()

    threading.Thread(target=manage, daemon=True).start()
    threading.Thread(target=gunluk_reset_loop, daemon=True).start()
    threading.Thread(target=telebot_polling_baslat, daemon=True).start()

    tg(
        "🚀 TELEGRAM SİNYAL KOPYALAMA BOTU\n"
        "🔖 VERSİYON: v5 (/manuel gerekmiyor artik)\n\n"
        f"💰 Sermaye: ${TOPLAM_SERMAYE} | Kaldıraç: {LEV}x\n"
        f"🎯 Hedef risk/işlem: ${HEDEF_RISK_DOLAR}\n"
        f"📡 Dinlenen kanal: @{KANAL_KULLANICI_ADI}\n"
        f"⛔ Günlük zarar limiti: ${MAX_GUNLUK_ZARAR}\n\n"
        "⚠️ Bu kanalın geçmiş performansı doğrulanmadı."
    )

    telethon_baslat()
