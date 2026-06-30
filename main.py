#!/usr/bin/env python3
"""
SADIK SCALP v2 - Temiz & Kontrollü
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
İki mod:
  1. OTOMATİK: Hacim patlaması + RSI + Alım baskısı → limit emir
  2. MANUEL: Sen sinyal gönder → sinyaldeki fiyatlarla limit emir

TP/SL:
  - Otomatik: TP1 +%2.1 (direkt kapat ~1$), TP2 +%4.0, SL -%1.0
  - Manuel: Sinyaldeki TP/SL kullan, sırayla yönet
"""

import os, time, threading, logging, re, random, requests
import ccxt
import pandas as pd
import telebot
from supabase import create_client

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("SCALP_V2")

# ════════════════════════════════════════════
# CONFIG
# ════════════════════════════════════════════
TELE_TOKEN   = os.getenv("TELE_TOKEN", "")
CHAT_ID      = int(os.getenv("MY_CHAT_ID", "0"))
BITGET_API   = os.getenv("BITGET_API", "")
BITGET_SEC   = os.getenv("BITGET_SEC", "")
BITGET_PASS  = os.getenv("BITGET_PASS", "")
SUPA_URL     = os.getenv("SUPABASE_URL", "")
SUPA_KEY     = os.getenv("SUPABASE_KEY", "")

LEVERAGE        = 5
MARGIN          = 10.0
POS_SIZE        = MARGIN * LEVERAGE   # 50$
COMMISSION      = 0.0006
MAX_OPEN_AUTO   = 2    # Bot kendi açarsa max 2
MAX_OPEN_MANUEL = 3    # Sen sinyal gönderirsen max 3
MAX_DAILY_LOSS  = -10.0
SCAN_INTERVAL   = 20

# Otomatik mod TP/SL
AUTO_TP1_PCT  = 2.1   # +%2.1 → direkt kapat (~1$ net)
AUTO_TP2_PCT  = 4.0   # +%4.0 → trailing
AUTO_SL_PCT   = 1.0   # -%1.0
AUTO_TRAILING = 0.40  # TP2 sonrası %0.40 geri dönerse kapat
MAX_SURE      = 240   # Max 4 saat (pratik limit)

# Manuel mod — sinyaldeki TP/SL kullan
MANUEL_SL_PCT  = 1.0   # Sinyalde SL yoksa varsayılan -%1.0
MANUEL_BEKLE   = 300   # 5 dakika (300sn) limit emir bekle
MANUEL_TRAILING = 0.40  # TP sonrası trailing

# Limit emir
LIMIT_ALTI_PCT = 0.1   # Fiyatın %0.1 altına limit koy (daha kolay dolar)

# Tarama
VOL_SPIKE_MIN = 2.0
ALIM_MIN      = 65.0
RSI_MIN       = 30
RSI_MAX       = 60
PCT_1M_MAX    = 2.0
MIN_VOL_USDT  = 500_000
MAX_VOL_USDT  = 20_000_000
MIN_PRICE     = 0.0001
MAX_PRICE     = 5.0
FG_MIN        = 10
TICKER_TTL    = 20
BTC_TTL       = 120
FG_TTL        = 600
RECENTLY_TTL  = 1800   # 30dk aynı coin tekrar açılmaz

BLACKLIST = {
    "BANANAS31","BSB","JCT","MEGA","ALLO","FTM","MU",
    "TURBO","MOODENG","SUNDOG","NEIRO","HMSTR","CATI","DOGS","MYRO",
    "BOME","SLERF","PNUT","RGTI","SATL","WET","POET",
    "SOXL","SOXS","UVXY","SVIX","KORU","AMC","GME",
    "SHIB","DOGE","PEPE","FLOKI","BONK","WIF","MEME",
    "1000SHIB","1000DOGE","1000PEPE","1000FLOKI","1000BONK","1000WIF",
    "COOKIE",
}

# ════════════════════════════════════════════
# STATE
# ════════════════════════════════════════════
positions       = {}
pos_lock        = threading.Lock()
daily_pnl       = 0.0
daily_pnl_lock  = threading.Lock()
recently_closed = {}
closed_lock     = threading.Lock()

btc_cache  = {"trend": "NEUTRAL_LONG", "price": 0, "chg": 0, "ts": 0}
btc_lock   = threading.Lock()
fg_cache   = {"value": 50, "label": "Neutral", "ts": 0}
fg_lock    = threading.Lock()
ticker_cache    = {}
ticker_cache_ts = 0
ticker_lock     = threading.Lock()

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
# SUPABASE
# ════════════════════════════════════════════
supa = None
if SUPA_URL and SUPA_KEY:
    try:
        supa = create_client(SUPA_URL, SUPA_KEY)
        log.info("[SUPA] Bağlandı")
    except Exception as e:
        log.error(f"[SUPA] {e}")

def save_trade(data):
    if not supa: return
    try:
        supa.table("gpt_trades").insert(data).execute()
    except Exception as e:
        log.error(f"[SAVE] {e}")

# ════════════════════════════════════════════
# EXCHANGE
# ════════════════════════════════════════════
exchange = ccxt.bitget({
    "apiKey": BITGET_API, "secret": BITGET_SEC,
    "password": BITGET_PASS, "enableRateLimit": True,
    "options": {"defaultType": "swap"},
})

_last_api = 0
_api_lock = threading.Lock()

def safe_api(func, *args, **kwargs):
    global _last_api
    for attempt in range(4):
        try:
            with _api_lock:
                wait = 0.5 - (time.time() - _last_api)
                if wait > 0: time.sleep(wait)
                _last_api = time.time()
            return func(*args, **kwargs)
        except ccxt.RateLimitExceeded:
            time.sleep(10)
        except ccxt.NetworkError as e:
            log.warning(f"[API] Network: {e}"); time.sleep(3)
        except Exception as e:
            log.warning(f"[API] {attempt+1}: {e}"); time.sleep(2)
    return None

def get_tickers_cached():
    global ticker_cache, ticker_cache_ts
    with ticker_lock:
        if time.time() - ticker_cache_ts < TICKER_TTL and ticker_cache:
            return ticker_cache
    t = safe_api(exchange.fetch_tickers)
    if t:
        with ticker_lock:
            ticker_cache = t
            ticker_cache_ts = time.time()
    return t

# ════════════════════════════════════════════
# PNL
# ════════════════════════════════════════════
def günlük_limit_asıldı():
    with daily_pnl_lock:
        return daily_pnl <= MAX_DAILY_LOSS

def pnl_ekle(miktar):
    global daily_pnl
    with daily_pnl_lock:
        daily_pnl += miktar
        return daily_pnl

# ════════════════════════════════════════════
# FEAR & GREED
# ════════════════════════════════════════════
def get_fear_greed():
    with fg_lock:
        if time.time() - fg_cache["ts"] < FG_TTL:
            return fg_cache["value"], fg_cache["label"]
    try:
        r = requests.get("https://api.alternative.me/fng/?limit=1", timeout=5)
        d = r.json()["data"][0]
        v, l = int(d["value"]), d["value_classification"]
        with fg_lock:
            fg_cache.update({"value": v, "label": l, "ts": time.time()})
        return v, l
    except:
        return 50, "Neutral"

# ════════════════════════════════════════════
# BTC TREND
# ════════════════════════════════════════════
def get_btc_trend():
    with btc_lock:
        if time.time() - btc_cache["ts"] < BTC_TTL:
            return btc_cache["trend"], btc_cache["price"], btc_cache["chg"]
    try:
        raw = safe_api(exchange.fetch_ohlcv, "BTC/USDT:USDT", "15m", limit=30)
        if not raw: return "NEUTRAL_LONG", 0, 0
        df    = pd.DataFrame(raw, columns=["t","o","h","l","c","v"])
        price = float(df["c"].iloc[-1])
        chg1h = (price - float(df["c"].iloc[-5])) / float(df["c"].iloc[-5]) * 100
        chg4h = (price - float(df["c"].iloc[-17])) / float(df["c"].iloc[-17]) * 100
        if chg1h < -1.0 or chg4h < -2.0:
            trend = "DOWN"
        elif chg1h > 1.0 or chg4h > 2.0:
            trend = "UP"
        else:
            trend = "NEUTRAL_LONG"
        with btc_lock:
            btc_cache.update({"trend": trend, "price": price, "chg": chg4h, "ts": time.time()})
        log.info(f"[BTC] {trend} ${price:,.0f}")
        return trend, price, chg4h
    except Exception as e:
        log.warning(f"[BTC] {e}")
        return "NEUTRAL_LONG", 0, 0

# ════════════════════════════════════════════
# İNDİKATÖRLER
# ════════════════════════════════════════════
def calc_rsi(series, period=9):
    delta = series.diff()
    gain  = delta.clip(lower=0).rolling(period).mean()
    loss  = (-delta.clip(upper=0)).rolling(period).mean()
    rs    = gain / loss.replace(0, 0.001)
    return float((100 - 100 / (1 + rs)).iloc[-1])

def calc_atr(df, period=14):
    h, l, c = df["h"], df["l"], df["c"]
    tr = pd.concat([h-l, (h-c.shift()).abs(), (l-c.shift()).abs()], axis=1).max(axis=1)
    return float(tr.rolling(period).mean().iloc[-1])

# ════════════════════════════════════════════
# SCALP SİNYAL TESPİTİ
# ════════════════════════════════════════════
def scalp_sinyal(symbol):
    try:
        r1m = safe_api(exchange.fetch_ohlcv, symbol, "1m", limit=30)
        if not r1m or len(r1m) < 15:
            return False, {}

        df1m  = pd.DataFrame(r1m, columns=["t","o","h","l","c","v"])
        price = float(df1m["c"].iloc[-1])

        # Hacim patlaması — son 1 mum (anlık)
        son_hacim = float(df1m["v"].iloc[-1])
        ort_hacim = float(df1m["v"].iloc[:-1].tail(20).mean())
        vol_oran  = son_hacim / max(ort_hacim, 0.0001)

        # Hacim patlaması — son 3 mum (yakın geçmiş, momentum devam ediyor mu)
        son3_hacim = float(df1m["v"].tail(3).sum())
        ort3_hacim = float(df1m["v"].iloc[:-3].tail(20).mean()) * 3
        vol_oran_3m = son3_hacim / max(ort3_hacim, 0.0001)

        # İkisinden büyük olanı kullan
        vol_oran_final = max(vol_oran, vol_oran_3m)

        # Alım oranı (son 3 tamamlanmış mum)
        son3 = df1m.tail(4).iloc[:-1]
        alim = sum(float(r["v"]) for _, r in son3.iterrows() if float(r["c"]) > float(r["o"]))
        toplam = float(son3["v"].sum())
        alim_orani = alim / max(toplam, 0.0001) * 100

        # RSI (9 periyot — scalp için hızlı)
        rsi_val = calc_rsi(df1m["c"])

        # Geç kalma kontrolü — son 3 dakikada çok pompaladıysa
        pct_3m = (price - float(df1m["c"].iloc[-4])) / float(df1m["c"].iloc[-4]) * 100
        if pct_3m > 4.0:
            return False, {"red": f"Geç kalındı 3m+{pct_3m:.1f}%"}

        # ATR (1h verisiyle)
        r1h = safe_api(exchange.fetch_ohlcv, symbol, "1h", limit=15)
        if not r1h or len(r1h) < 14:
            return False, {"red": "ATR veri yok"}
        df1h    = pd.DataFrame(r1h, columns=["t","o","h","l","c","v"])
        atr_val = calc_atr(df1h)

        gecti = (
            vol_oran_final >= VOL_SPIKE_MIN and
            alim_orani      >= ALIM_MIN      and
            RSI_MIN         <= rsi_val <= RSI_MAX
        )

        return gecti, {
            "vol":     round(vol_oran_final, 1),
            "alim":    round(alim_orani, 1),
            "rsi":     round(rsi_val, 1),
            "pct":     round(pct_3m, 2),
            "atr":     atr_val,
            "price":   price,
            "son5_low": float(df1m["l"].tail(5).min()),
        }

    except Exception as e:
        log.warning(f"[SİNYAL] {symbol}: {e}")
        return False, {}

# ════════════════════════════════════════════
# PNL HESABI
# ════════════════════════════════════════════
def hesap_pnl(pos, price):
    entry   = pos["entry"]
    amount  = pos.get("amount", POS_SIZE / max(entry, 0.000001))
    pnl     = (price - entry) * amount - POS_SIZE * COMMISSION
    pnl_pct = (price - entry) / entry * 100
    return pnl, pnl_pct

# ════════════════════════════════════════════
# BORSA EMİR YARDIMCILARI
# ════════════════════════════════════════════
def borsa_hazirla(symbol):
    """Margin modu ve kaldıraç ayarla."""
    try: exchange.set_margin_mode("isolated", symbol, params={"marginCoin": "USDT"})
    except: pass
    try: exchange.set_leverage(LEVERAGE, symbol, params={"marginCoin": "USDT"})
    except: pass

def limit_emir_ac(symbol, fiyat, amount, bekle_sn=300):
    """
    Limit emir aç, bekle_sn saniye bekle.
    Döner: (gerçek_fiyat, order_id) veya (None, None)
    """
    try:
        fiyat_p = float(exchange.price_to_precision(symbol, fiyat))
        order = safe_api(
            exchange.create_order, symbol, "limit", "buy", amount, fiyat_p,
            {"marginMode": "isolated", "marginCoin": "USDT", "timeInForce": "GTC"}
        )
        if not order:
            return None, None

        order_id = order.get("id")
        adim     = 5
        for _ in range(bekle_sn // adim):
            time.sleep(adim)
            durum = safe_api(exchange.fetch_order, order_id, symbol)
            if durum and durum.get("status") == "closed":
                return float(durum.get("average") or fiyat_p), order_id

        # Süre doldu → iptal
        try: safe_api(exchange.cancel_order, order_id, symbol)
        except: pass
        return None, None

    except Exception as e:
        log.error(f"[LİMİT] {symbol}: {e}")
        return None, None

def pozisyon_slot_al(symbol, entry, sl, tps, btc_trend, atr, mod="auto"):
    """
    Pozisyon slotunu al. Döner: True/False
    Kontroller: duplicate, recently_closed, max_open
    """
    sym_base = symbol.split("/")[0].upper()
    max_open = MAX_OPEN_AUTO if mod == "auto" else MAX_OPEN_MANUEL

    with pos_lock:
        if symbol in positions:
            return False
        for ex in positions:
            if ex.split("/")[0].upper() == sym_base:
                return False
        with closed_lock:
            if sym_base in recently_closed:
                if mod == "auto" and time.time() - recently_closed[sym_base] < RECENTLY_TTL:
                    return False
        if len(positions) >= max_open:
            return False
        if günlük_limit_asıldı():
            return False

        positions[symbol] = {
            "entry":     entry,
            "sl":        sl,
            "tps":       tps,
            "tp_idx":    0,
            "max_price": entry,
            "open_time": time.time(),
            "amount":    0,
            "btc_trend": btc_trend,
            "atr":       atr,
            "pending":   True,
            "mod":       mod,
        }
        return True

# ════════════════════════════════════════════
# OTOMATİK POZİSYON AÇ
# ════════════════════════════════════════════
def open_pos_auto(symbol, detay, btc_trend):
    """Hacim patlaması sinyaliyle otomatik giriş."""
    if günlük_limit_asıldı(): return False

    sym      = symbol.split("/")[0]
    price    = detay["price"]
    atr_val  = detay["atr"]
    son5_low = detay.get("son5_low", price)

    # Limit fiyat — fiyatın altında, destek bölgesine yakın
    limit_alt = round(price * (1 - LIMIT_ALTI_PCT / 100), 8)
    son5_safe = min(son5_low * 1.001, price * 0.999)
    limit_p   = round(max(son5_safe, limit_alt), 8)
    limit_p   = min(limit_p, price * 0.999)  # Kesinlikle fiyatın altında

    # TP/SL
    sl  = round(limit_p * (1 - AUTO_SL_PCT  / 100), 8)
    tp1 = round(limit_p * (1 + AUTO_TP1_PCT / 100), 8)
    tp2 = round(limit_p * (1 + AUTO_TP2_PCT / 100), 8)

    # Slot al
    if not pozisyon_slot_al(symbol, limit_p, sl, [tp1, tp2], btc_trend, atr_val, "auto"):
        return False

    def _ac():
        try:
            borsa_hazirla(symbol)
            amount = float(exchange.amount_to_precision(symbol, round(POS_SIZE / limit_p, 4)))
            if amount <= 0:
                with pos_lock: positions.pop(symbol, None)
                return

            gercek, _ = limit_emir_ac(symbol, limit_p, amount, bekle_sn=300)

            if not gercek:
                with pos_lock: positions.pop(symbol, None)
                tg(f"⏰ {sym} limit dolmadı, iptal.")
                return

            # SL/TP gerçek fiyata göre güncelle
            sl_g  = round(gercek * (1 - AUTO_SL_PCT  / 100), 8)
            tp1_g = round(gercek * (1 + AUTO_TP1_PCT / 100), 8)
            tp2_g = round(gercek * (1 + AUTO_TP2_PCT / 100), 8)

            with pos_lock:
                if symbol in positions:
                    positions[symbol].update({
                        "entry":   gercek,
                        "sl":      sl_g,
                        "tps":     [tp1_g, tp2_g],
                        "amount":  amount,
                        "pending": False,
                    })

            tg(
                f"⚡ #{sym}USDT.P SCALP\n"
                f"🏁 Giriş: {gercek:.8f}\n"
                f"🚫 SL: {sl_g:.8f} (-%{AUTO_SL_PCT})\n"
                f"🎯 TP1: {tp1_g:.8f} (+%{AUTO_TP1_PCT}) → Direkt kapat\n"
                f"🎯 TP2: {tp2_g:.8f} (+%{AUTO_TP2_PCT}) → Trailing\n\n"
                f"Hacim: {detay['vol']:.1f}x | Alım: %{detay['alim']:.0f} | RSI: {detay['rsi']:.0f}\n"
                f"BTC: {btc_trend}"
            )
            log.info(f"[AUTO] {sym} @ {gercek:.8f}")

        except Exception as e:
            log.error(f"[AUTO_AC] {sym}: {e}")
            with pos_lock: positions.pop(symbol, None)

    threading.Thread(target=_ac, daemon=True).start()
    return True

# ════════════════════════════════════════════
# MANUEL POZİSYON AÇ (Sinyal Forward)
# ════════════════════════════════════════════
def open_pos_manuel(symbol, giris, sl, tps, btc_trend, bekle_sn=MANUEL_BEKLE):
    """Kullanıcının gönderdiği sinyaldeki fiyatlarla giriş."""
    sym = symbol.split("/")[0]

    # ATR (sadece miktar hesabı için)
    try:
        r1h = safe_api(exchange.fetch_ohlcv, symbol, "1h", limit=15)
        df1h = pd.DataFrame(r1h, columns=["t","o","h","l","c","v"])
        atr_val = calc_atr(df1h)
    except:
        atr_val = giris * 0.01

    # Slot al
    if not pozisyon_slot_al(symbol, giris, sl, tps, btc_trend, atr_val, "manuel"):
        return False, "Slot alınamadı"

    def _ac():
        try:
            borsa_hazirla(symbol)
            amount = float(exchange.amount_to_precision(symbol, round(POS_SIZE / giris, 4)))
            if amount <= 0:
                with pos_lock: positions.pop(symbol, None)
                tg(f"❌ {sym} miktar hesaplanamadı.")
                return

            tg(f"📡 {sym} limit emir açılıyor @ {giris:.8f}\n{bekle_sn}sn bekleniyor...")

            gercek, _ = limit_emir_ac(symbol, giris, amount, bekle_sn=bekle_sn)

            if not gercek:
                with pos_lock: positions.pop(symbol, None)
                tg(f"⏰ {sym} limit dolmadı (5dk), iptal edildi.")
                return

            # SL — sinyeldeki değer her zaman giriş fiyatının altında olmalı
            # sl değişkeni dışarıdan geliyor (sinyal parse'dan)
            if sl and sl > 0 and sl < gercek * 0.990:
                sl_gercek = sl  # Sinyeldeki SL geçerli (en az %1 aşağıda)
            else:
                # Geçersiz veya yoksa gerçek giriş fiyatından hesapla
                sl_gercek = round(gercek * (1 - MANUEL_SL_PCT / 100), 8)
                log.info(f"[MANUEL] {sym} SL varsayılan: {sl_gercek:.8f} (giriş: {gercek:.8f})")

            # TP'leri güncelle — sinyaldeki oranı koru, gerçek fiyata uygula
            if tps:
                tp_oran = [(tp - giris) / giris for tp in tps]
                tps_gercek = [round(gercek * (1 + r), 8) for r in tp_oran]
            else:
                tps_gercek = [round(gercek * (1 + AUTO_TP1_PCT/100), 8)]

            with pos_lock:
                if symbol in positions:
                    positions[symbol].update({
                        "entry":   gercek,
                        "sl":      sl_gercek,
                        "tps":     tps_gercek,
                        "amount":  amount,
                        "pending": False,
                    })

            sl_pct = (gercek - sl_gercek) / gercek * 100
            tp_str = "\n".join([f"TP{i+1}: {tp:.8f} ──" for i, tp in enumerate(tps_gercek)])
            tg(
                f"✅ #{sym}USDT.P LONG (Sinyal)\n"
                f"🏁 Giriş: {gercek:.8f}\n"
                f"🚫 SL: {sl_gercek:.8f} (-%{sl_pct:.1f})\n\n"
                f"{tp_str}\n\n"
                f"BTC: {btc_trend}"
            )
            log.info(f"[MANUEL] {sym} @ {gercek:.8f}")

        except Exception as e:
            log.error(f"[MANUEL_AC] {sym}: {e}")
            with pos_lock: positions.pop(symbol, None)
            tg(f"❌ {sym} emir hatası: {e}")

    threading.Thread(target=_ac, daemon=True).start()
    return True, "OK"

# ════════════════════════════════════════════
# İŞLEM KAPAT
# ════════════════════════════════════════════
def close_pos(symbol, reason, exit_price=None):
    with pos_lock:
        pos = positions.pop(symbol, None)
    if not pos: return

    sym    = symbol.split("/")[0]
    amount = pos.get("amount", 0)
    if not amount or amount <= 0:
        amount = round(POS_SIZE / pos["entry"], 4)

    # Borsadan gerçek miktar
    try:
        pos_list = safe_api(exchange.fetch_positions, [symbol])
        if pos_list:
            for p in pos_list:
                c = float(p.get("contracts") or 0)
                if c > 0 and p.get("side") == "long":
                    amount = c; break
    except: pass

    try:
        safe_api(
            exchange.create_order, symbol, "market", "sell", amount, None,
            {"reduceOnly": True, "marginCoin": "USDT"}
        )
    except Exception as e:
        err = str(e)
        if "22002" not in err and "No position" not in err:
            log.error(f"[KAPAT] {sym}: {e}")

    if exit_price is None:
        t = safe_api(exchange.fetch_ticker, symbol)
        exit_price = float(t["last"]) if t else pos["entry"]

    pnl, pnl_pct = hesap_pnl(pos, exit_price)
    sure         = int((time.time() - pos["open_time"]) / 60)
    yeni_toplam  = pnl_ekle(pnl)

    sym_base = sym.upper()
    with closed_lock:
        recently_closed[sym_base] = time.time()

    try:
        save_trade({"symbol": symbol, "signal": "LONG", "pnl": round(pnl, 4),
                    "sure_dk": sure, "reason": reason, "btc_trend": pos.get("btc_trend", "")})
    except: pass

    if yeni_toplam <= MAX_DAILY_LOSS:
        tg(f"⛔ GÜNLÜK LİMİT! {yeni_toplam:+.2f}$")

    icon = "🟢" if pnl >= 0 else "🔴"
    tg(f"{icon} {sym_base} KAPANDI\n{reason}\nPnL: {pnl:+.2f}$ ({pnl_pct:+.1f}%) | {sure}dk\nGünlük: {yeni_toplam:+.2f}$")

# ════════════════════════════════════════════
# YÖNETİM DÖNGÜSÜ
# ════════════════════════════════════════════
def manage_loop():
    while True:
        time.sleep(5)
        try:
            with pos_lock:
                syms = list(positions.keys())
            if not syms: continue

            for symbol in syms:
                with pos_lock:
                    pos = positions.get(symbol)
                if not pos or pos.get("pending"): continue

                t = safe_api(exchange.fetch_ticker, symbol)
                if not t: continue

                price        = float(t["last"])
                pnl, pnl_pct = hesap_pnl(pos, price)
                sure         = int((time.time() - pos["open_time"]) / 60)
                entry        = pos["entry"]
                sl           = pos["sl"]
                tps          = pos["tps"]
                tp_idx       = pos.get("tp_idx", 0)
                max_price    = pos.get("max_price", entry)
                mod          = pos.get("mod", "auto")

                # Max fiyat güncelle
                if price > max_price:
                    with pos_lock:
                        if symbol in positions:
                            positions[symbol]["max_price"] = price
                    max_price = price

                # SL kontrolü
                if price <= sl:
                    close_pos(symbol, f"🚫 SL ({sl:.8f})", price)
                    continue

                # Max süre
                if sure >= MAX_SURE:
                    close_pos(symbol, f"⏰ Süre doldu ({MAX_SURE}dk)", price)
                    continue

                # Günlük limit
                if günlük_limit_asıldı():
                    close_pos(symbol, "Günlük limit", price)
                    continue

                # TP yönetimi
                if tp_idx < len(tps) and price >= tps[tp_idx]:
                    sym = symbol.split("/")[0]

                    if mod == "auto" and tp_idx == 0:
                        # Otomatik mod: TP1 → direkt kapat (~1$ net)
                        close_pos(symbol, f"🎯 TP1 +{pnl_pct:.1f}%", price)
                        continue

                    else:
                        # Manuel mod veya TP2+: SL bir önceki TP'ye çek
                        if tp_idx == 0:
                            # TP1 sonrası SL → gerçek giriş fiyatını borsadan al
                            try:
                                pos_list = safe_api(exchange.fetch_positions, [symbol])
                                gercek_giris = entry  # varsayılan
                                if pos_list:
                                    for p in pos_list:
                                        if float(p.get("contracts") or 0) > 0 and p.get("side") == "long":
                                            gercek_giris = float(p.get("entryPrice") or entry)
                                            break
                            except:
                                gercek_giris = entry
                            yeni_sl = round(gercek_giris * 0.9995, 8)  # %0.05 altı (slippage payı)
                        else:
                            yeni_sl = tps[tp_idx - 1]  # Önceki TP

                        with pos_lock:
                            if symbol in positions:
                                positions[symbol]["tp_idx"] = tp_idx + 1
                                positions[symbol]["sl"]     = yeni_sl

                        sonraki = f"{tps[tp_idx+1]:.8f}" if tp_idx + 1 < len(tps) else "∞"
                        tg(f"🎯 {sym} TP{tp_idx+1}! +{pnl_pct:.1f}%\nSL → {yeni_sl:.8f}\nSonraki: {sonraki}")
                        tp_idx += 1

                # TP1+ sonrası trailing stop
                if mod == "auto" and tp_idx > 0:
                    # Otomatik mod: TP1 sonrası trailing
                    geri = (max_price - price) / max_price * 100
                    if geri >= AUTO_TRAILING:
                        close_pos(symbol, f"Trailing -%{geri:.1f}", price)
                        continue
                elif mod == "manuel" and len(tps) >= 5 and tp_idx >= 5:
                    # Manuel mod (5 TP'li): TP5 sonrası trailing
                    geri = (max_price - price) / max_price * 100
                    # 0.50$ trailing = %1.0 (50$ pozisyonun %1'i)
                    if geri >= 1.0:
                        close_pos(symbol, f"Trailing -%{geri:.1f}", price)
                        continue

        except Exception as e:
            log.error(f"[MANAGE] {e}")

# ════════════════════════════════════════════
# TARAYICI
# ════════════════════════════════════════════
def scanner_loop():
    """Otomatik tarama KAPALI — sadece manuel sinyal forward ile işlem açılır."""
    log.info("[SCANNER] Otomatik tarama devre dışı, sadece manuel sinyal bekleniyor.")
    while True:
        time.sleep(300)  # Sadece yaşam belirtisi, işlem açmaz

# ════════════════════════════════════════════
# GÜNLÜK SIFIRLAMA
# ════════════════════════════════════════════
def gunluk_reset_loop():
    global daily_pnl
    import datetime
    while True:
        try:
            simdi = datetime.datetime.now()
            yarin = (simdi + datetime.timedelta(days=1)).replace(hour=0, minute=0, second=5, microsecond=0)
            time.sleep((yarin - simdi).total_seconds())
            with daily_pnl_lock:
                eski = daily_pnl; daily_pnl = 0.0
            tg(f"🔄 Yeni gün! Dün: {eski:+.2f}$")
        except Exception as e:
            log.error(f"[RESET] {e}"); time.sleep(3600)

# ════════════════════════════════════════════
# HEALTH SERVER
# ════════════════════════════════════════════
def health_server():
    from http.server import HTTPServer, BaseHTTPRequestHandler
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200); self.end_headers()
            trend, _, _ = get_btc_trend()
            fg, _       = get_fear_greed()
            with pos_lock: ps = ",".join(s.split("/")[0] for s in positions)
            with daily_pnl_lock: pnl = daily_pnl
            self.wfile.write(f"OK|btc:{trend}|fg:{fg}|pos:{len(positions)}({ps})|pnl:{pnl:+.2f}".encode())
        def log_message(self, *a): pass
    HTTPServer(("0.0.0.0", 8080), H).serve_forever()

# ════════════════════════════════════════════
# AÇILIŞTA POZİSYON YÜKLE
# ════════════════════════════════════════════
def load_open_positions():
    try:
        raw = safe_api(exchange.fetch_positions)
        if not raw: return
        btc_trend, _, _ = get_btc_trend()
        yuklenen = 0
        lines = ["♻️ Pozisyonlar yüklendi:\n"]
        for p in raw:
            try:
                contracts = float(p.get("contracts") or 0)
                symbol    = p.get("symbol", "")
                side      = p.get("side", "")
                entry     = float(p.get("entryPrice") or 0)
                if contracts == 0 or not symbol or side != "long" or entry == 0: continue
                sl  = round(entry * (1 - AUTO_SL_PCT / 100), 8)
                tp1 = round(entry * (1 + AUTO_TP1_PCT / 100), 8)
                tp2 = round(entry * (1 + AUTO_TP2_PCT / 100), 8)
                with pos_lock:
                    if symbol not in positions:
                        positions[symbol] = {
                            "entry": entry, "sl": sl, "tps": [tp1, tp2],
                            "tp_idx": 0, "max_price": entry,
                            "open_time": time.time(), "amount": contracts,
                            "btc_trend": btc_trend, "atr": entry * 0.01,
                            "pending": False, "mod": "auto",
                        }
                        yuklenen += 1
                        t = safe_api(exchange.fetch_ticker, symbol)
                        now = float(t["last"]) if t else entry
                        pnl = (now - entry) * contracts
                        icon = "🟢" if pnl >= 0 else "🔴"
                        lines.append(f"{icon} {symbol.split('/')[0]} @ {entry:.8f} | {pnl:+.2f}$")
            except Exception as e:
                log.warning(f"[YUKLE] {e}")
        if yuklenen > 0:
            tg("\n".join(lines))
    except Exception as e:
        log.error(f"[YUKLE] {e}")

# ════════════════════════════════════════════
# SİNYAL PARSE
# ════════════════════════════════════════════
def sinyal_parse(text):
    """
    Metinden coin adı, giriş fiyatı, SL ve TP'leri çıkar.
    FuturesKripto ve TradingView formatlarını destekler.
    Döner: (coin_adi, giris, sl, tps) veya None
    """
    text_up = text.upper()

    # Coin adı
    match = re.search(r'#([A-Z0-9]+)USDT', text_up)
    if not match:
        match = re.search(r'\$([A-Z0-9]+)\s*\|', text_up)
    if not match:
        match = re.search(r'\b([A-Z]{2,10})USDT\b', text_up)
    if not match:
        return None
    coin_adi = match.group(1)

    # Giriş fiyatı
    giris = None
    for pattern in [
        r'Giri[şs]\s*Fiyat[ıi]\s*[:\s]+([0-9.]+)',
        r'Price[:\s]+([0-9.]+)',
        r'LONG[^\n]*\n\s*([0-9.]+)',
    ]:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            giris = float(m.group(1))
            break

    # SL — "Stop: 0.0256025 ya da sonraki sinyal" formatını da destekle
    sl = None
    m = re.search(r'Stop[:\s]+([0-9.]+)', text, re.IGNORECASE)
    if m:
        sl = float(m.group(1))

    # TP'ler
    tps = [float(x) for x in re.findall(r'TP\d+[:\s]+([0-9.]+)', text)]

    return coin_adi, giris, sl, tps

# ════════════════════════════════════════════
# TELEGRAM HANDLER
# ════════════════════════════════════════════
def find_coin(text):
    words = re.findall(r"\b[A-Z]{2,10}\b", text.upper())
    try:
        tickers = get_tickers_cached()
        if not tickers: return None
        for w in words:
            if w in BLACKLIST: continue
            sym = f"{w}/USDT:USDT"
            if sym in tickers: return sym
    except: pass
    return None

@bot.message_handler(func=lambda msg: True)
def handle(msg):
    if not msg.text: return
    threading.Thread(target=handle_async, args=(msg,), daemon=True).start()

def handle_async(msg):
    text  = msg.text.strip()
    lower = text.lower()

    # ── SİNYAL TESPİTİ ──
    # FuturesKripto: "🏁 LONG" veya "#XXXUSDT.P"
    # TradingView: "TradingView" veya "$XXX | #XXXUSDT"
    sinyal_var = (
        "🏁 long" in lower or
        "long - giri" in lower or
        "tradingview" in lower or
        (("#" in text or "$" in text) and "usdt" in text.upper())
    )

    if sinyal_var:
        sonuc = sinyal_parse(text)
        if sonuc:
            coin_adi, giris, sl, tps = sonuc
            symbol = f"{coin_adi}/USDT:USDT"

            # Format tespiti: FuturesKripto mu TradingView mı?
            is_futureskripto = "🏁 long" in lower or "long - giri" in lower
            is_tradingview   = "tradingview" in lower

            # Kontroller
            try:
                tickers = get_tickers_cached()
                if tickers and symbol not in tickers:
                    bot.send_message(msg.chat.id, f"❌ {coin_adi} Bitget'te bulunamadı.")
                    return
            except: pass

            if coin_adi in BLACKLIST:
                bot.send_message(msg.chat.id, f"❌ {coin_adi} blacklist'te.")
                return

            if günlük_limit_asıldı():
                bot.send_message(msg.chat.id, "❌ Günlük limit aşıldı.")
                return

            with pos_lock:
                if len(positions) >= MAX_OPEN_MANUEL:
                    bot.send_message(msg.chat.id, f"❌ Max pozisyon ({MAX_OPEN_MANUEL}) dolu.")
                    return

            trend, _, _ = get_btc_trend()

            # ── FuturesKripto formatı: giriş + SL + TP'lerin HEPSİ sinyalden ──
            if is_futureskripto:
                if not giris or not sl or not tps:
                    bot.send_message(
                        msg.chat.id,
                        f"❌ {coin_adi} sinyal eksik (giriş/SL/TP okunamadı).\n"
                        f"Giriş:{giris} SL:{sl} TP sayısı:{len(tps) if tps else 0}"
                    )
                    return
                if sl >= giris:
                    bot.send_message(msg.chat.id, f"❌ {coin_adi} SL geçersiz (giriş altında değil).")
                    return
                # Sinyaldeki değerler birebir kullanılacak

            # ── TradingView formatı: sadece coin/fiyat al, SL/TP bizim bot hesaplar ──
            elif is_tradingview:
                if not giris:
                    t0 = safe_api(exchange.fetch_ticker, symbol)
                    if not t0:
                        bot.send_message(msg.chat.id, f"❌ {coin_adi} fiyat alınamadı.")
                        return
                    giris = float(t0["last"])

                # ATR bazlı sağlam SL/TP hesapla
                try:
                    r1h = safe_api(exchange.fetch_ohlcv, symbol, "1h", limit=15)
                    df1h = pd.DataFrame(r1h, columns=["t","o","h","l","c","v"])
                    atr_val = calc_atr(df1h)
                    atr_pct = (atr_val / giris) * 100
                    # SL: ATR bazlı ama min %1, max %3
                    sl_pct = max(1.0, min(atr_pct * 1.2, 3.0))
                except:
                    sl_pct = MANUEL_SL_PCT

                sl  = round(giris * (1 - sl_pct / 100), 8)
                tps = [
                    round(giris * (1 + sl_pct * 1.5 / 100), 8),  # TP1 = SL×1.5 (R:R 1:1.5)
                    round(giris * (1 + sl_pct * 3.0 / 100), 8),  # TP2 = SL×3.0
                ]

            # ── Bilinmeyen format: en güvenli varsayılanlar ──
            else:
                if not giris:
                    t0 = safe_api(exchange.fetch_ticker, symbol)
                    if not t0:
                        bot.send_message(msg.chat.id, f"❌ {coin_adi} fiyat alınamadı.")
                        return
                    giris = float(t0["last"])
                if not sl:
                    sl = round(giris * (1 - MANUEL_SL_PCT / 100), 8)
                if not tps:
                    tps = [round(giris * (1 + AUTO_TP1_PCT / 100), 8)]

            bot.send_message(
                msg.chat.id,
                f"📡 {coin_adi} sinyali alındı [{'FuturesKripto' if is_futureskripto else 'TradingView' if is_tradingview else 'Bilinmeyen'}]\n"
                f"Giriş: {giris} | SL: {sl}\n"
                f"TP sayısı: {len(tps)} | Limit emir açılıyor..."
            )

            ok, mesaj = open_pos_manuel(symbol, giris, sl, tps, trend)
            if not ok:
                bot.send_message(msg.chat.id, f"❌ {coin_adi}: {mesaj}")
            return

    # ── KOMUTLAR ──
    if "/durum" in lower:
        with pos_lock:
            if not positions:
                bot.send_message(msg.chat.id, "📋 Açık pozisyon yok."); return
            lines = ["📋 POZİSYONLAR\n"]
            for sym, pos in positions.items():
                t = safe_api(exchange.fetch_ticker, sym)
                if not t: continue
                price = float(t["last"])
                pnl, pct = hesap_pnl(pos, price)
                sure = int((time.time() - pos["open_time"]) / 60)
                lines.append(
                    f"{'🟢' if pnl>=0 else '🔴'} {sym.split('/')[0]} [{pos.get('mod','?')}]\n"
                    f"   {pos['entry']:.8f}→{price:.8f}\n"
                    f"   PnL:{pnl:+.2f}$ ({pct:+.1f}%) | {sure}dk\n"
                    f"   SL:{pos['sl']:.8f} TP{pos.get('tp_idx',0)}/{len(pos.get('tps',[]))}\n"
                )
            bot.send_message(msg.chat.id, "\n".join(lines))
        return

    if "/istatistik" in lower:
        if not supa:
            bot.send_message(msg.chat.id, "Supabase yok."); return
        try:
            r    = supa.table("gpt_trades").select("pnl,signal").execute()
            data = [d for d in (r.data or []) if d.get("signal") == "LONG"]
            if not data:
                bot.send_message(msg.chat.id, "Kayıt yok."); return
            toplam = len(data)
            kazan  = sum(1 for d in data if float(d.get("pnl") or 0) > 0)
            net    = sum(float(d.get("pnl") or 0) for d in data)
            with daily_pnl_lock: gunluk = daily_pnl
            bot.send_message(msg.chat.id,
                f"📊 İSTATİSTİK\nToplam:{toplam} Kazanan:{kazan} (%{kazan/toplam*100:.0f})\n"
                f"Net:{net:+.2f}$ | Günlük:{gunluk:+.2f}$")
        except Exception as e:
            bot.send_message(msg.chat.id, f"Hata: {e}")
        return

    if "/btc" in lower:
        trend, price, chg = get_btc_trend()
        fg, fl = get_fear_greed()
        bot.send_message(msg.chat.id, f"BTC: {trend}\n${price:,.0f} ({chg:+.1f}%)\nFG: {fg} ({fl})")
        return

    # ── "COIN long aç" KOMUTU ──
    if "long ac" in lower or "long aç" in lower:
        coin = find_coin(text)
        if not coin:
            bot.send_message(msg.chat.id, "❌ Coin bulunamadı.")
            return

        coin_adi = coin.split("/")[0]

        if coin_adi in BLACKLIST:
            bot.send_message(msg.chat.id, f"❌ {coin_adi} blacklist'te.")
            return

        if günlük_limit_asıldı():
            bot.send_message(msg.chat.id, "❌ Günlük limit aşıldı.")
            return

        with pos_lock:
            if len(positions) >= MAX_OPEN_MANUEL:
                bot.send_message(msg.chat.id, f"❌ Max pozisyon ({MAX_OPEN_MANUEL}) dolu.")
                return
            if coin in positions:
                bot.send_message(msg.chat.id, f"❌ {coin_adi} zaten açık.")
                return

        t0 = safe_api(exchange.fetch_ticker, coin)
        if not t0:
            bot.send_message(msg.chat.id, f"❌ {coin_adi} fiyat alınamadı.")
            return
        price_now = float(t0["last"])

        # ATR bazlı sağlam SL/TP
        try:
            r1h = safe_api(exchange.fetch_ohlcv, coin, "1h", limit=15)
            df1h = pd.DataFrame(r1h, columns=["t","o","h","l","c","v"])
            atr_val = calc_atr(df1h)
            atr_pct = (atr_val / price_now) * 100
            sl_pct = max(1.0, min(atr_pct * 1.2, 3.0))
        except:
            sl_pct = MANUEL_SL_PCT

        sl  = round(price_now * (1 - sl_pct / 100), 8)
        # TP'ler 50$ pozisyona göre USDT hedefleri:
        # TP1~+1$, TP2~+1.7$, TP3~+2$, TP4~+2.5$, TP5~+3$
        tps = [
            round(price_now * (1 + 2.1 / 100), 8),   # TP1 ~+1$
            round(price_now * (1 + 3.5 / 100), 8),   # TP2 ~+1.75$
            round(price_now * (1 + 4.1 / 100), 8),   # TP3 ~+2$
            round(price_now * (1 + 5.1 / 100), 8),   # TP4 ~+2.5$
            round(price_now * (1 + 6.1 / 100), 8),   # TP5 ~+3$
        ]

        trend, _, _ = get_btc_trend()

        bot.send_message(
            msg.chat.id,
            f"📡 {coin_adi} manuel long açılıyor\n"
            f"Fiyat: {price_now:.8f} | SL: -%{sl_pct:.1f}\n"
            f"Limit emir koyuluyor..."
        )

        ok, mesaj = open_pos_manuel(coin, price_now, sl, tps, trend, bekle_sn=180)
        if not ok:
            bot.send_message(msg.chat.id, f"❌ {coin_adi}: {mesaj}")
        return

    if "kapat" in lower:
        with pos_lock: syms = list(positions.keys())
        if not syms:
            bot.send_message(msg.chat.id, "Açık pozisyon yok."); return
        kapatildi = False
        for symbol in syms:
            if symbol.split("/")[0].upper() in text.upper() or "hepsi" in lower:
                close_pos(symbol, "Kullanıcı isteği")
                kapatildi = True
        if not kapatildi:
            bot.send_message(msg.chat.id, f"Hangisini? {', '.join(s.split('/')[0] for s in syms)}")
        return

    # Coin analizi
    coin = find_coin(text)
    if coin:
        sym = coin.split("/")[0]
        bot.send_message(msg.chat.id, f"🔍 {sym} analiz...")
        gecti, detay = scalp_sinyal(coin)
        trend, _, _  = get_btc_trend()
        bot.send_message(msg.chat.id,
            f"⚡ {sym} SCALP ANALİZ\n"
            f"Hacim: {detay.get('vol',0):.1f}x {'✅' if detay.get('vol',0)>=VOL_SPIKE_MIN else '❌'}\n"
            f"Alım: %{detay.get('alim',0):.0f} {'✅' if detay.get('alim',0)>=ALIM_MIN else '❌'}\n"
            f"RSI: {detay.get('rsi',0):.0f} {'✅' if RSI_MIN<=detay.get('rsi',0)<=RSI_MAX else '❌'}\n"
            f"1m: {detay.get('pct',0):+.1f}%\nBTC: {trend}\n\n"
            f"{'✅ GİRİLİR' if gecti else '❌ PAS'}"
        )
        return

    bot.send_message(msg.chat.id, "Komutlar:\n/durum\n/istatistik\n/btc\nCOIN long aç\nCOIN kapat / hepsi kapat")

# ════════════════════════════════════════════
# SHUTDOWN
# ════════════════════════════════════════════
import signal as sig_mod, sys

def shutdown(signum, frame):
    with pos_lock: syms = list(positions.keys())
    if syms: tg(f"⏸ Yeniden başlıyor...\n{len(syms)} pozisyon açık.")
    sys.exit(0)

sig_mod.signal(sig_mod.SIGTERM, shutdown)
sig_mod.signal(sig_mod.SIGINT, shutdown)

# ════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════
if __name__ == "__main__":
    print("SADIK SCALP v2 BAŞLIYOR...")
    load_open_positions()
    threading.Thread(target=health_server,     daemon=True).start()
    threading.Thread(target=manage_loop,       daemon=True).start()
    threading.Thread(target=scanner_loop,      daemon=True).start()
    threading.Thread(target=gunluk_reset_loop, daemon=True).start()

    fg, fl            = get_fear_greed()
    trend, price, chg = get_btc_trend()

    tg(
        "⚡ SADIK SCALP v2 — MANUEL MOD\n\n"
        "🔇 Otomatik tarama KAPALI\n\n"
        "📡 Sadece sinyal forward ile çalışır:\n"
        "  Sinyali bota gönder → Sinyaldeki TP/SL kullanır\n"
        "  5 dakika limit emir bekler\n"
        "  TP1→TP2→...→TP6 sırayla yönetilir\n"
        "  Trailing YOK, SL bir önceki TP'ye çekilir\n\n"
        f"Max {MAX_OPEN_MANUEL} pozisyon | SL varsayılan -%{MANUEL_SL_PCT}\n\n"
        f"BTC: {trend} ${price:,.0f}\n"
        f"Fear&Greed: {fg} ({fl})\n\n"
        "/durum /istatistik /btc"
    )

    while True:
        try:
            bot.infinity_polling(timeout=30, long_polling_timeout=30)
        except Exception as e:
            log.error(f"[BOT] {e}"); time.sleep(5)
