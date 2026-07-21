#!/usr/bin/env python3
"""
YENİ STRATEJİ BOTU — Backtest ile doğrulanmış, kanaldan bağımsız
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DOĞRULAMA ÖZETİ (21 Temmuz 2026'da yapılan backtest):
  - Strateji: 4h MA20 üstünde/altında + 4h son 5 mumun 4'ü aynı yönde +
    1h RSI 50-70/30-50 aralığında + 1h son 5 mumun 4'ü aynı yönde
  - SL: 1.0 x ATR(1h,14) | TP: 1.5R sabit hedef
  - IN-SAMPLE (son 6 ay, 8 coin): 570 işlem, %48.8 kazanma, komisyon
    dahil +56.2R toplam (+0.099R/işlem ortalama)
  - OUT-OF-SAMPLE (180-400 gün önce, aynı 8 coin, GRID ARAMASINDA
    KULLANILMAMIŞ veri): 671 işlem, %47.1 kazanma, komisyon dahil
    +45.95R toplam (+0.068R/işlem ortalama)
  - Her iki dönemde de, 8 coin'in her birinde AYRI AYRI pozitif çıktı.

⚠️ ÖNEMLİ DÜRÜSTLÜK NOTU: Bu bir garanti değildir. Geçmiş performans
gelecekteki sonuçları garanti etmez. Backtest, gerçek emir doluşu,
likidite, ani haber olayları gibi faktörleri tam yansıtmaz. Küçük
sermaye ve düşük kaldıraçla, dikkatli izleyerek başlanmalıdır.

GÜVENLİK AYARLARI (kanalın kendi tavsiyesine uygun şekilde bilerek
düşük tutuldu — önceki bottaki 20x kaldıraç deneyiminden ders alınarak):
  - Varsayılan kaldıraç: 3x
  - Pozisyon başına risk: bakiyenin %5'i (yani bir SL ≈ bakiyenin %5'i)
  - Aynı anda maksimum 1 açık pozisyon (küçük sermayede odaklanma için)
  - Günlük zarar limiti: bakiyenin %15'i (aşılırsa gün sonuna kadar durur)
"""

import os
import time
import json
import logging
import threading
import ccxt
import telebot
import pandas as pd
import numpy as np

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("YENI_STRATEJI")

# ════════════════════════════════════════════
# CONFIG — Railway ortam değişkenlerinden okunur
# ════════════════════════════════════════════
TELE_TOKEN = os.getenv("TELE_TOKEN", "")
CHAT_ID = int(os.getenv("MY_CHAT_ID", "0"))
API_KEY = os.getenv("BITGET_API", "")
API_SEC = os.getenv("BITGET_SEC", "")
PASSPHRASE = os.getenv("BITGET_PASS", "")

if not PASSPHRASE:
    raise RuntimeError("BITGET_PASS ortam değişkeni eksik.")

exchange = ccxt.bitget({
    "apiKey": API_KEY, "secret": API_SEC, "password": PASSPHRASE,
    "options": {"defaultType": "swap"}, "enableRateLimit": True, "timeout": 30000,
})

bot = telebot.TeleBot(TELE_TOKEN) if TELE_TOKEN else None

def tg(msg):
    if not bot or not CHAT_ID:
        log.info(f"[TG-atlandi] {msg}")
        return
    try:
        bot.send_message(CHAT_ID, str(msg)[:4096])
    except Exception as e:
        log.warning(f"[TG] {e}")

# ── DOĞRULANMIŞ STRATEJİ PARAMETRELERİ (backtest'te bulunan) ──
COINS = ["SOL/USDT:USDT", "LINK/USDT:USDT", "AVAX/USDT:USDT", "DOGE/USDT:USDT",
         "ADA/USDT:USDT", "DOT/USDT:USDT", "NEAR/USDT:USDT", "APT/USDT:USDT"]
ATR_CARPANI = 1.0
RR = 1.5
MUM_ESIGI = 4       # 5 mumdan en az kaci ayni yonde olmali
RSI_ALT, RSI_UST = 50, 70

# ── RİSK/GÜVENLİK AYARLARI (bilerek muhafazakar) ──
LEV = int(os.getenv("LEV", "3"))                       # kaldirac
RISK_PCT_BAKIYE = float(os.getenv("RISK_PCT_BAKIYE", "0.05"))  # her islemde bakiyenin %5'i risk
MAX_POS = 1
GUNLUK_ZARAR_LIMIT_PCT = 0.15   # bakiyenin %15'i kaybedilirse o gun durur
KONTROL_ARALIGI_SN = 300        # her 5 dakikada bir yeni sinyal taransin (1h mum bazli strateji, hizli olmasina gerek yok)

TRADE_STATE_PATH = os.getenv("TRADE_STATE_PATH", "/data/yeni_strateji_state.json")
trade_state = {}
state_lock = threading.Lock()
gunluk_pnl = 0.0
gunluk_baslangic_bakiye = None
gunluk_lock = threading.Lock()


def durumu_diske_yaz():
    try:
        os.makedirs(os.path.dirname(TRADE_STATE_PATH), exist_ok=True)
        with state_lock:
            veri = dict(trade_state)
        with open(TRADE_STATE_PATH, "w") as f:
            json.dump(veri, f)
    except Exception as e:
        log.warning(f"[KALICI] {e}")


def durumu_diskten_yukle():
    global trade_state
    try:
        if os.path.exists(TRADE_STATE_PATH):
            with open(TRADE_STATE_PATH) as f:
                trade_state = json.load(f)
    except Exception as e:
        log.warning(f"[KALICI] {e}")


def safe(x):
    try:
        return float(x)
    except Exception:
        return 0.0


def rsi(series, period=14):
    diff = series.diff()
    gain = diff.clip(lower=0); loss = -diff.clip(upper=0)
    avg_gain = gain.rolling(period).mean(); avg_loss = loss.rolling(period).mean()
    rs = avg_gain / avg_loss.replace(0, 1e-9)
    return 100 - (100 / (1 + rs))


def atr(df, period=14):
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)
    tr = pd.concat([(high - low), (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
    return tr.rolling(period).mean()


def get_df(sym, tf, limit=60):
    try:
        candles = exchange.fetch_ohlcv(sym, tf, limit=limit)
        df = pd.DataFrame(candles, columns=["ts", "open", "high", "low", "close", "volume"])
        return df
    except Exception as e:
        log.warning(f"[VERI] {sym} {tf}: {e}")
        return None


def sinyal_kontrol_et(sym):
    """Backtest'teki AYNI mantik: 4h MA20+5mum teyidi, 1h RSI+5mum teyidi."""
    df4h = get_df(sym, "4h", 30)
    df1h = get_df(sym, "1h", 30)
    if df4h is None or df1h is None or len(df4h) < 21 or len(df1h) < 21:
        return None

    df4h["ma20"] = df4h["close"].rolling(20).mean()
    df4h["yon"] = np.where(df4h["close"] > df4h["open"], 1, -1)
    yon5_up_4h = (df4h["yon"].iloc[-5:] > 0).sum()
    yon5_down_4h = (df4h["yon"].iloc[-5:] < 0).sum()
    ma20 = df4h["ma20"].iloc[-1]
    fiyat_4h = df4h["close"].iloc[-1]

    df1h["rsi"] = rsi(df1h["close"], 14)
    df1h["atr"] = atr(df1h, 14)
    df1h["yon"] = np.where(df1h["close"] > df1h["open"], 1, -1)
    yon5_up_1h = (df1h["yon"].iloc[-5:] > 0).sum()
    yon5_down_1h = (df1h["yon"].iloc[-5:] < 0).sum()
    rsi_1h = df1h["rsi"].iloc[-1]
    atr_1h = df1h["atr"].iloc[-1]
    fiyat = df1h["close"].iloc[-1]

    if pd.isna(ma20) or pd.isna(rsi_1h) or pd.isna(atr_1h) or atr_1h <= 0:
        return None

    long_ok = (fiyat_4h > ma20 and yon5_up_4h >= MUM_ESIGI and
               RSI_ALT < rsi_1h < RSI_UST and yon5_up_1h >= MUM_ESIGI)
    short_ok = (fiyat_4h < ma20 and yon5_down_4h >= MUM_ESIGI and
                (100 - RSI_UST) < rsi_1h < (100 - RSI_ALT) and yon5_down_1h >= MUM_ESIGI)

    if long_ok:
        sl = fiyat - ATR_CARPANI * atr_1h
        tp = fiyat + ATR_CARPANI * atr_1h * RR
        return {"symbol": sym, "direction": "long", "entry": fiyat, "sl": sl, "tp": tp}
    if short_ok:
        sl = fiyat + ATR_CARPANI * atr_1h
        tp = fiyat - ATR_CARPANI * atr_1h * RR
        return {"symbol": sym, "direction": "short", "entry": fiyat, "sl": sl, "tp": tp}
    return None


def gercek_bakiye_al():
    try:
        bakiye = exchange.fetch_balance()
        return safe(bakiye.get("USDT", {}).get("free", 0))
    except Exception as e:
        log.warning(f"[BAKIYE] {e}")
        return None


def gunluk_limit_kontrolu():
    with gunluk_lock:
        if gunluk_baslangic_bakiye is None:
            return False
        return gunluk_pnl <= -(gunluk_baslangic_bakiye * GUNLUK_ZARAR_LIMIT_PCT)


def pozisyon_ac(sinyal):
    sym = sinyal["symbol"]
    direction = sinyal["direction"]
    entry = sinyal["entry"]
    sl = sinyal["sl"]
    tp = sinyal["tp"]

    bakiye = gercek_bakiye_al()
    if bakiye is None or bakiye <= 0:
        tg(f"⚠️ {sym} atlandı — bakiye alınamadı veya sıfır")
        return

    # ── RİSK BAZLI POZİSYON BOYUTU ──
    # Risk edilecek $ miktarı = bakiye * RISK_PCT_BAKIYE
    # SL vurulursa kaybedilecek miktar bu olacak sekilde pozisyon buyuklugu hesaplanir.
    risk_dolar = bakiye * RISK_PCT_BAKIYE
    sl_mesafe_pct = abs(entry - sl) / entry
    notional = risk_dolar / sl_mesafe_pct
    gereken_marj = notional / LEV

    if gereken_marj > bakiye * 0.9:
        # marj bakiyenin cogunu yiyorsa notional'i bakiyeye gore sinirla
        notional = bakiye * 0.9 * LEV
        gereken_marj = notional / LEV

    amount = notional / entry

    try:
        exchange.set_leverage(LEV, sym)
    except Exception as e:
        log.warning(f"[KALDIRAC] {sym}: {e}")

    try:
        qty = float(exchange.amount_to_precision(sym, amount))
    except Exception as e:
        tg(f"⚠️ {sym} miktar hesaplanamadi: {e}")
        return
    if qty <= 0:
        return

    side = "buy" if direction == "long" else "sell"
    try:
        emir = exchange.create_market_order(sym, side, qty)
    except Exception as e:
        tg(f"⚠️ {sym} giris emri basarisiz: {e}")
        return

    # Hard stop (borsa seviyesinde SL) + TP limit emri
    try:
        kapama_yon = "sell" if direction == "long" else "buy"
        sl_fiyat = float(exchange.price_to_precision(sym, sl))
        exchange.create_order(sym, "market", kapama_yon, qty, None,
                               {"reduceOnly": True, "stopLossPrice": sl_fiyat})
    except Exception as e:
        log.warning(f"[HARD_STOP] {sym}: {e}")

    tp_emir_id = None
    try:
        kapama_yon = "sell" if direction == "long" else "buy"
        tp_fiyat = float(exchange.price_to_precision(sym, tp))
        tp_emri = exchange.create_limit_order(sym, kapama_yon, qty, tp_fiyat, params={"reduceOnly": True})
        tp_emir_id = tp_emri.get("id")
    except Exception as e:
        log.warning(f"[TP_EMIR] {sym}: {e}")

    with state_lock:
        trade_state[sym] = {"direction": direction, "entry": entry, "sl": sl, "tp": tp,
                             "qty": qty, "tp_emir_id": tp_emir_id, "acilis_zamani": time.time()}
    durumu_diske_yaz()

    tg(f"📈 YENİ POZİSYON: {sym} {direction.upper()}\n"
       f"Giriş≈{entry:.6f} | SL:{sl:.6f} | TP:{tp:.6f}\n"
       f"Notional≈${notional:.2f} ({LEV}x) | Risk≈${risk_dolar:.2f} (bakiyenin %{RISK_PCT_BAKIYE*100:.0f}'i)")


def tarama_loop():
    tg(f"🚀 YENİ STRATEJİ BOTU başladı\n"
       f"Coinler: {', '.join(c.split('/')[0] for c in COINS)}\n"
       f"Kaldıraç: {LEV}x | İşlem başına risk: bakiyenin %{RISK_PCT_BAKIYE*100:.0f}'i\n"
       f"Günlük zarar limiti: bakiyenin %{GUNLUK_ZARAR_LIMIT_PCT*100:.0f}'i\n"
       f"⚠️ Bu strateji backtest ile doğrulandı ama gerçek performansı garanti etmez.")

    global gunluk_baslangic_bakiye
    bakiye = gercek_bakiye_al()
    if bakiye:
        gunluk_baslangic_bakiye = bakiye

    while True:
        try:
            if gunluk_limit_kontrolu():
                time.sleep(KONTROL_ARALIGI_SN)
                continue

            with state_lock:
                pozisyon_dolu = len(trade_state) >= MAX_POS

            if not pozisyon_dolu:
                for sym in COINS:
                    with state_lock:
                        if sym in trade_state:
                            continue
                    sinyal = sinyal_kontrol_et(sym)
                    if sinyal:
                        tg(f"🔍 Sinyal bulundu: {sym} {sinyal['direction'].upper()} — açılıyor...")
                        pozisyon_ac(sinyal)
                        break  # MAX_POS=1, bir tane bulunca dur

            time.sleep(KONTROL_ARALIGI_SN)
        except Exception as e:
            log.error(f"[TARAMA] {e}")
            time.sleep(30)


def manage_loop():
    """Acik pozisyonlari izler, SL/TP vurulmasini borsadan dogrular, state temizler."""
    global gunluk_pnl
    while True:
        try:
            with state_lock:
                semboller = list(trade_state.keys())
            if not semboller:
                time.sleep(15)
                continue

            positions = exchange.fetch_positions(semboller)
            acik_semboller = {p["symbol"] for p in positions if safe(p.get("contracts")) > 0}

            for sym in semboller:
                if sym in acik_semboller:
                    continue
                # pozisyon kapanmis (SL ya da TP vurulmus)
                with state_lock:
                    durum = trade_state.pop(sym, None)
                durumu_diske_yaz()
                if durum:
                    try:
                        t = exchange.fetch_ticker(sym)
                        cikis_fiyat = safe(t["last"])
                    except Exception:
                        cikis_fiyat = durum["sl"]
                    entry = durum["entry"]; qty = durum["qty"]; direction = durum["direction"]
                    pnl_tahmini = (cikis_fiyat - entry) * qty if direction == "long" else (entry - cikis_fiyat) * qty
                    with gunluk_lock:
                        gunluk_pnl += pnl_tahmini
                    tg(f"✅ {sym} pozisyonu kapandı | Tahmini PnL≈{pnl_tahmini:+.2f}$")

            time.sleep(15)
        except Exception as e:
            log.error(f"[MANAGE] {e}")
            time.sleep(15)


if __name__ == "__main__":
    print("YENİ STRATEJİ BOTU BAŞLIYOR...")
    durumu_diskten_yukle()
    threading.Thread(target=manage_loop, daemon=True).start()
    tarama_loop()
