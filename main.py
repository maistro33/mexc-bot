#!/usr/bin/env python3
"""
FVG/SMC BOT — GERÇEK PARA SÜRÜMÜ
🔖 VERSİYON: v1
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DÜZELTİLEN GÜVENLİK AÇIKLARI (orijinal koddan):
  1. API şifresi artık ORTAM DEĞİŞKENİNDEN okunuyor, koda YAZILMIYOR.
  2. RESTART GÜVENLİĞİ: trade_state artık diske kaydediliyor. Bot yeniden
     başlarsa, borsadaki gerçek açık pozisyonlarla diskteki kayıtlı
     durumu KARŞILAŞTIRIR. Eşleşme bulamazsa (orijinal koddaki hata:
     KeyError sessizce yutulup pozisyon TAMAMEN YÖNETİMSİZ kalıyordu),
     bu sürüm hemen Telegram'dan UYARI gönderir VE pozisyona geçici
     güvenlik SL'i koyar — sessizce görmezden gelmez.
  3. RİSK BAZLI POZİSYON BOYUTU: sabit MARGIN×LEV yerine, her işlemde
     HEDEF DOLAR RİSKİ sabit tutulur, pozisyon büyüklüğü SL mesafesine
     (coinin kendi oynaklığına) göre hesaplanır.
  4. HANTAL COİN FİLTRESİ: hem minimum hacim hem minimum oynaklık şartı.

STRATEJİ (backtest ile doğrulanmış — bkz. fvg_backtest.py sonuçları):
  - Günlük + 4 saatlik trend teyidi
  - 1 saatlik likidite süpürmesi
  - 15 dakikalık FVG (Fair Value Gap) girişi
  - R bazlı kademeli TP (1R/2R/3R, %40/%30/%30) + TP1 sonrası başa baş

⚠️  ÖNEMLİ: Bu, GERÇEK PARA ile işlem açar. Backtest geçmişte iyi
sonuç vermiş olması, gelecekte de öyle olacağının garantisi DEĞİLDİR.
Sadece kaybetmeyi göze alabileceğin miktarla kullan.
"""

import os
import time
import json
import threading
import logging
import ccxt
import pandas as pd
import telebot

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("FVG_LIVE")

# ════════════════════════════════════════════
# CONFIG
# ════════════════════════════════════════════
TELE_TOKEN  = os.getenv("TELE_TOKEN", "")
CHAT_ID     = int(os.getenv("MY_CHAT_ID", "0"))
API_KEY     = os.getenv("BITGET_API", "")
API_SEC     = os.getenv("BITGET_SEC", "")
PASSPHRASE  = os.getenv("BITGET_PASS", "")   # ← artık koda yazılı DEĞİL

if not PASSPHRASE:
    raise RuntimeError("BITGET_PASS ortam değişkeni ayarlanmamış — güvenlik gereği "
                        "passphrase koda yazılmaz, Railway Variables'a eklenmeli.")

exchange = ccxt.bitget({
    "apiKey": API_KEY, "secret": API_SEC, "password": PASSPHRASE,
    "options": {"defaultType": "swap"}, "enableRateLimit": True, "timeout": 30000,
})

# ── Sermaye ve risk ──
MAX_POS           = 2        # 35$'ı 2 işleme bölüyoruz
LEV               = 10
TOPLAM_SERMAYE    = 35.0     # bilgi amaçlı — gerçek limit borsadan kontrol edilir
HEDEF_RISK_DOLAR  = 2.5      # her işlemde hedeflenen dolar riski (~toplamın %7'si / slot)
MIN_POS_NOTIONAL  = 30.0     # pozisyon en az bu kadar $ olsun (borsa asgari işlem büyüklüğü için)
MAX_POS_NOTIONAL  = (TOPLAM_SERMAYE / MAX_POS) * LEV * 1.2   # slot başına makul üst sınır

MAX_GUNLUK_ZARAR  = -8.0     # bu kadar (gerçek $) kaybedince gün için dur

# ── Hantal coin filtresi ──
MIN_VOLUME        = 20_000_000   # eskisi 5M idi — çok daha likit coinler
MIN_OYNAKLIK_PCT  = 3.0          # son 24s içinde en az %3 hareket etmemişse "hantal" sayılır
TOP_COINS         = 80

BUFFER_PCT = 0.0015
TP_SPLIT   = [0.4, 0.3, 0.3]

TRADE_STATE_PATH = os.getenv("TRADE_STATE_PATH", "/data/trade_state.json")

# ════════════════════════════════════════════
# TELEGRAM
# ════════════════════════════════════════════
bot = telebot.TeleBot(TELE_TOKEN)

def tg(msg):
    try:
        bot.send_message(CHAT_ID, str(msg)[:4096])
    except Exception as e:
        log.warning(f"[TG] {e}")

# ════════════════════════════════════════════
# YARDIMCI
# ════════════════════════════════════════════
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
# KALICI DURUM (trade_state) — RESTART GÜVENLİĞİ
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
        else:
            log.info("[KALICI] Kayıtlı durum bulunamadı (Volume bağlı değilse normal)")
    except Exception as e:
        log.warning(f"[KALICI] Yükleme başarısız: {e}")


def acilista_pozisyonlari_dogrula():
    """
    RESTART GÜVENLİĞİ — orijinal koddaki en kritik hatayı düzeltir:
    Borsadaki GERÇEK açık pozisyonları, diskteki kayıtlı trade_state ile
    karşılaştırır. Eşleşmeyen (sahipsiz) pozisyon bulursa SESSİZCE
    GEÇMEZ — hemen uyarır ve geçici güvenlik SL'i koyar.
    """
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
            tg(f"♻️ {sym} pozisyonu kayıtlı durumla eşleşti, yönetime devam ediliyor.")
            continue

        # ── SAHİPSİZ POZİSYON — orijinal bottaki hata burada oluşurdu ──
        direction = "long" if side == "long" else "short"
        guvenlik_sl_pct = 0.02  # %2 geçici güvenlik SL'i
        sl = entry * (1 - guvenlik_sl_pct) if direction == "long" else entry * (1 + guvenlik_sl_pct)

        with state_lock:
            trade_state[sym] = {
                "sl": sl, "tp1": False, "tp2": False,
                "direction": direction, "entry": entry,
                "kaynak": "kurtarilan_sahipsiz",
            }
        durumu_diske_yaz()
        tg(
            f"🚨 UYARI: {sym} için kayıtlı durum bulunamadı (muhtemelen restart sırasında "
            f"oluştu). SESSİZCE GEÇİLMEDİ — geçici %2 güvenlik SL'i kondu: {sl:.8f}. "
            f"Lütfen pozisyonu manuel kontrol et."
        )


# ════════════════════════════════════════════
# MARKET FİLTRESİ (+ HANTAL COİN ELEME)
# ════════════════════════════════════════════
def get_symbols():
    try:
        tickers = exchange.fetch_tickers()
    except Exception as e:
        log.warning(f"[TICKERS] {e}")
        return []

    filtered = []
    for sym, data in tickers.items():
        if ":USDT" not in sym:
            continue
        vol = safe(data.get("quoteVolume"))
        if vol < MIN_VOLUME:
            continue
        degisim = abs(safe(data.get("percentage")))
        if degisim < MIN_OYNAKLIK_PCT:
            continue  # ── HANTAL: son 24s'te yeterince hareket etmemiş ──
        filtered.append((sym, vol))

    filtered.sort(key=lambda x: x[1], reverse=True)
    return [x[0] for x in filtered[:TOP_COINS]]


# ════════════════════════════════════════════
# SİNYAL MANTIĞI (backtest'te doğrulanan, BİREBİR aynı mantık)
# ════════════════════════════════════════════
def get_direction(sym):
    d = get_candles(sym, "1d", 50)
    h4 = get_candles(sym, "4h", 50)
    if not d or not h4 or len(d) < 3 or len(h4) < 3:
        return None

    d_high = [c[2] for c in d]; d_low = [c[3] for c in d]
    h_high = [c[2] for c in h4]; h_low = [c[3] for c in h4]

    if d_high[-1] > d_high[-2] and h_high[-1] > h_high[-2]:
        return "long"
    if d_low[-1] < d_low[-2] and h_low[-1] < h_low[-2]:
        return "short"
    return None


def liquidity_sweep(sym, direction):
    h1 = get_candles(sym, "1h", 30)
    if not h1 or len(h1) < 30:
        return False
    highs = [c[2] for c in h1]; lows = [c[3] for c in h1]
    if direction == "long":
        return lows[-1] < min(lows[:-2])
    else:
        return highs[-1] > max(highs[:-2])


def entry_model(sym, direction):
    m15 = get_candles(sym, "15m", 60)
    if not m15 or len(m15) < 20:
        return None

    o = [c[1] for c in m15]; h = [c[2] for c in m15]
    l = [c[3] for c in m15]; c_ = [c[4] for c in m15]

    body = abs(c_[-1] - o[-1])
    avg_body = sum(abs(c_[i] - o[i]) for i in range(-10, -1)) / 9
    if body < avg_body * 1.5:
        return None

    if direction == "long" and h[-3] < l[-1]:
        entry = (h[-3] + l[-1]) / 2
        swing_low = min(l[-15:])
        sl = swing_low - (swing_low * BUFFER_PCT)
        return {"entry": entry, "sl": sl}

    if direction == "short" and l[-3] > h[-1]:
        entry = (l[-3] + h[-1]) / 2
        swing_high = max(h[-15:])
        sl = swing_high + (swing_high * BUFFER_PCT)
        return {"entry": entry, "sl": sl}

    return None


# ════════════════════════════════════════════
# RİSK BAZLI POZİSYON BOYUTU
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


def has_position():
    try:
        pos = exchange.fetch_positions()
        return any(safe(p.get("contracts")) > 0 for p in pos)
    except Exception as e:
        log.warning(f"[POS_CHECK] {e}")
        return True  # emin olamıyorsak GÜVENLİ tarafta kal, yeni işlem açma


# ════════════════════════════════════════════
# POZİSYON YÖNETİMİ (SL / TP1 / TP2 / TP3 + başa baş)
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
                side = p["side"]
                direction = "long" if side == "long" else "short"

                with state_lock:
                    durum = trade_state.get(sym)
                if not durum:
                    continue  # acilista_pozisyonlari_dogrula bunu zaten ele almış olmalı

                t = exchange.fetch_ticker(sym)
                if not t:
                    continue
                price = safe(t["last"])

                sl = durum["sl"]
                risk = abs(entry - sl)
                if risk <= 0:
                    continue

                tp1 = entry + risk if direction == "long" else entry - risk
                tp2 = entry + 2 * risk if direction == "long" else entry - 2 * risk
                tp3 = entry + 3 * risk if direction == "long" else entry - 3 * risk

                # ── STOP ──
                sl_vuruldu = (price <= sl) if direction == "long" else (price >= sl)
                if sl_vuruldu:
                    try:
                        exchange.create_market_order(sym, "sell" if direction == "long" else "buy",
                                                       qty, params={"reduceOnly": True})
                    except Exception as e:
                        log.error(f"[STOP] {sym}: {e}")
                    gross = (price - entry) * qty if direction == "long" else (entry - price) * qty
                    gunluk_pnl_ekle(gross)
                    tg(f"❌ STOP {sym} | PnL≈{gross:+.2f}$")
                    with state_lock:
                        trade_state.pop(sym, None)
                    durumu_diske_yaz()
                    continue

                # ── TP1 ──
                if not durum["tp1"] and ((direction == "long" and price >= tp1) or
                                           (direction == "short" and price <= tp1)):
                    part = qty * TP_SPLIT[0]
                    try:
                        exchange.create_market_order(sym, "sell" if direction == "long" else "buy",
                                                       part, params={"reduceOnly": True})
                    except Exception as e:
                        log.error(f"[TP1] {sym}: {e}")
                    with state_lock:
                        trade_state[sym]["tp1"] = True
                        trade_state[sym]["sl"] = entry  # başa baş
                    durumu_diske_yaz()
                    tg(f"💰 TP1 {sym} — SL başa baş'a çekildi")

                # ── TP2 ──
                elif durum["tp1"] and not durum["tp2"] and \
                        ((direction == "long" and price >= tp2) or (direction == "short" and price <= tp2)):
                    part = qty * TP_SPLIT[1]
                    try:
                        exchange.create_market_order(sym, "sell" if direction == "long" else "buy",
                                                       part, params={"reduceOnly": True})
                    except Exception as e:
                        log.error(f"[TP2] {sym}: {e}")
                    with state_lock:
                        trade_state[sym]["tp2"] = True
                    durumu_diske_yaz()
                    tg(f"🚀 TP2 {sym}")

                # ── TP3 (kapanış) ──
                elif durum["tp2"] and ((direction == "long" and price >= tp3) or
                                         (direction == "short" and price <= tp3)):
                    try:
                        exchange.create_market_order(sym, "sell" if direction == "long" else "buy",
                                                       qty, params={"reduceOnly": True})
                    except Exception as e:
                        log.error(f"[TP3] {sym}: {e}")
                    gross = (price - entry) * qty if direction == "long" else (entry - price) * qty
                    gunluk_pnl_ekle(gross)
                    tg(f"🏆 TP3 {sym} — pozisyon kapandı | PnL≈{gross:+.2f}$")
                    with state_lock:
                        trade_state.pop(sym, None)
                    durumu_diske_yaz()

            time.sleep(5)
        except Exception as e:
            log.error(f"[MANAGE] {e}")
            time.sleep(5)


# ════════════════════════════════════════════
# GİRİŞ DÖNGÜSÜ
# ════════════════════════════════════════════
def run():
    while True:
        try:
            if gunluk_limit_asildi():
                time.sleep(60)
                continue

            with state_lock:
                acik_sayisi = len(trade_state)
            if acik_sayisi >= MAX_POS:
                time.sleep(20)
                continue

            symbols = get_symbols()

            for sym in symbols:
                with state_lock:
                    if len(trade_state) >= MAX_POS or sym in trade_state:
                        continue

                direction = get_direction(sym)
                if not direction:
                    continue
                if not liquidity_sweep(sym, direction):
                    continue
                setup = entry_model(sym, direction)
                if not setup:
                    continue

                amount, notional = pozisyon_boyutu_hesapla(setup["entry"], setup["sl"])
                if not amount:
                    continue

                try:
                    exchange.set_leverage(LEV, sym)
                except Exception as e:
                    log.warning(f"[LEVERAGE] {sym}: {e}")

                t = exchange.fetch_ticker(sym)
                price = safe(t["last"])
                qty = float(exchange.amount_to_precision(sym, amount))
                if qty <= 0:
                    continue

                side = "buy" if direction == "long" else "sell"
                try:
                    exchange.create_market_order(sym, side, qty)
                except Exception as e:
                    tg(f"⚠️ {sym} giriş emri başarısız: {e}")
                    continue

                with state_lock:
                    trade_state[sym] = {
                        "sl": setup["sl"], "tp1": False, "tp2": False,
                        "direction": direction, "entry": price, "kaynak": "fvg_smc",
                    }
                durumu_diske_yaz()

                tg(
                    f"📈 {sym} {direction.upper()} AÇILDI\n"
                    f"Giriş≈{price:.8f} | SL:{setup['sl']:.8f}\n"
                    f"Notional≈${notional:.2f} | Hedef risk: ${HEDEF_RISK_DOLAR:.2f}"
                )
                break

            time.sleep(30)
        except Exception as e:
            log.error(f"[RUN] {e}")
            time.sleep(30)


# ════════════════════════════════════════════
# TELEGRAM KOMUTLARI
# ════════════════════════════════════════════
@bot.message_handler(commands=["durum"])
def durum_komutu(msg):
    with state_lock:
        if not trade_state:
            bot.send_message(msg.chat.id, "Açık pozisyon yok.")
            return
        satirlar = ["📋 AÇIK POZİSYONLAR\n"]
        for sym, d in trade_state.items():
            satirlar.append(f"{sym} [{d['direction'].upper()}] giriş:{d['entry']:.8f} SL:{d['sl']:.8f} "
                             f"TP1:{d['tp1']} TP2:{d['tp2']} kaynak:{d.get('kaynak','?')}")
        bot.send_message(msg.chat.id, "\n".join(satirlar))


# ════════════════════════════════════════════
# BAŞLANGIÇ
# ════════════════════════════════════════════
if __name__ == "__main__":
    print("FVG LIVE BOT (v1) BAŞLIYOR...")
    try:
        exchange.fetch_balance()
    except Exception as e:
        print(f"UYARI: bakiye kontrolü başarısız: {e}")

    durumu_diskten_yukle()
    acilista_pozisyonlari_dogrula()

    threading.Thread(target=manage, daemon=True).start()
    threading.Thread(target=run, daemon=True).start()

    tg(
        "🚀 FVG/SMC BOT — GERÇEK PARA\n"
        "🔖 VERSİYON: v1 (güvenlik açıkları düzeltildi)\n\n"
        f"💰 Sermaye: ${TOPLAM_SERMAYE} | Max eşzamanlı: {MAX_POS} işlem\n"
        f"🎯 Hedef risk/işlem: ${HEDEF_RISK_DOLAR}\n"
        f"🔍 Filtre: min hacim ${MIN_VOLUME/1_000_000:.0f}M, min oynaklık %{MIN_OYNAKLIK_PCT}\n"
        f"⛔ Günlük zarar limiti: ${MAX_GUNLUK_ZARAR}\n\n"
        "Komutlar: /durum"
    )

    while True:
        try:
            bot.infinity_polling(timeout=30, long_polling_timeout=30)
        except Exception as e:
            log.error(f"[BOT] {e}")
            time.sleep(5)
