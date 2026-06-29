#!/usr/bin/env python3
"""
SADIK TRADER v9 - Hacim Patlaması Stratejisi
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Strateji (Basit & Etkili):
  1. Hacim Patlaması  → Son 1-5dk hacim 2x+ artış
  2. Alım Baskısı     → %65+ alım yoğunluğu
  3. BTC Filtresi     → DOWN değilse gir
  4. RSI Filtresi     → 68 altında
  5. Limit → Market   → Önce limit, 30sn dolmazsa market

TP/SL (ATR Bazlı - Kanıtlanmış R:R):
  - Giriş: Limit ATR×0.2 aşağı (30sn), sonra market
  - TP1: ATR × 1.5
  - TP2: ATR × 3.0  
  - TP3: ATR × 5.0
  - SL:  ATR × 2.0
"""

import os, time, threading, logging, re, random, requests
import ccxt
import pandas as pd
import telebot
from supabase import create_client

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("SADIK_V9")

# ════════════════════════════════════════
# CONFIG
# ════════════════════════════════════════
TELE_TOKEN  = os.getenv("TELE_TOKEN", "")
CHAT_ID     = int(os.getenv("MY_CHAT_ID", "0"))
BITGET_API  = os.getenv("BITGET_API", "")
BITGET_SEC  = os.getenv("BITGET_SEC", "")
BITGET_PASS = os.getenv("BITGET_PASS", "")
SUPA_URL    = os.getenv("SUPABASE_URL", "")
SUPA_KEY    = os.getenv("SUPABASE_KEY", "")

# İşlem parametreleri
LEVERAGE       = 5
MARGIN         = 10.0
POS_SIZE       = MARGIN * LEVERAGE   # 50$
COMMISSION     = 0.0006
MAX_OPEN       = 2
MAX_DAILY_LOSS = -15.0
SCAN_INTERVAL  = 30   # Daha sık tara

# TP/SL — ATR bazlı
ATR_TP1        = 1.5
ATR_TP2        = 3.0
ATR_TP3        = 5.0
ATR_SL         = 2.0
ATR_LIMIT      = 0.2   # Limit emir ATR×0.2 aşağı
LIMIT_BEKLE    = 30    # 30sn limit bekle, sonra market
TP_TRAILING    = 0.60  # TP1 sonrası %0.60 geri dönerse kapat

# Hacim filtresi
VOL_SPIKE_MIN  = 2.0   # 2x ortalama hacim
ALIM_MIN       = 65.0  # %65+ alım baskısı
RSI_MAX        = 68    # RSI üst sınır
MIN_VOL_USDT   = 500_000
MAX_VOL_USDT   = 20_000_000
MIN_PRICE      = 0.0001
MAX_PRICE      = 5.0
FG_MIN         = 10

# Ticker cache
TICKER_TTL     = 30   # 30sn cache

BLACKLIST = {
    "BANANAS31","BSB","JCT","MEGA","ALLO","FTM","MU",
    "TURBO","MOODENG","SUNDOG","NEIRO","HMSTR","CATI","DOGS","MYRO",
    "BOME","SLERF","PNUT","RGTI","SATL","WET","POET",
    "SOXL","SOXS","UVXY","SVIX","KORU","AMC","GME",
    "SHIB","DOGE","PEPE","FLOKI","BONK","WIF","MEME",
    "1000SHIB","1000DOGE","1000PEPE","1000FLOKI","1000BONK","1000WIF",
    "COOKIE",
}

# ════════════════════════════════════════
# STATE
# ════════════════════════════════════════
positions       = {}
pos_lock        = threading.Lock()
daily_pnl       = 0.0
daily_pnl_lock  = threading.Lock()
recently_closed = {}
closed_lock     = threading.Lock()

btc_cache = {"trend": "NEUTRAL_LONG", "price": 0, "chg": 0, "ts": 0}
btc_lock  = threading.Lock()
BTC_TTL   = 180

fg_cache = {"value": 50, "label": "Neutral", "ts": 0}
fg_lock  = threading.Lock()
FG_TTL   = 600

ticker_cache    = {}
ticker_cache_ts = 0
ticker_lock     = threading.Lock()

# ════════════════════════════════════════
# TELEGRAM
# ════════════════════════════════════════
bot = telebot.TeleBot(TELE_TOKEN)

def tg(msg):
    try:
        bot.send_message(CHAT_ID, str(msg)[:4096])
    except Exception as e:
        log.warning(f"[TG] {e}")

# ════════════════════════════════════════
# SUPABASE
# ════════════════════════════════════════
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

# ════════════════════════════════════════
# EXCHANGE
# ════════════════════════════════════════
exchange = ccxt.bitget({
    "apiKey":   BITGET_API,
    "secret":   BITGET_SEC,
    "password": BITGET_PASS,
    "enableRateLimit": True,
    "options":  {"defaultType": "swap"},
})

_last_api = 0
_api_lock = threading.Lock()

def safe_api(func, *args, **kwargs):
    global _last_api
    for attempt in range(4):
        try:
            with _api_lock:
                wait = 0.5 - (time.time() - _last_api)
                if wait > 0:
                    time.sleep(wait)
                _last_api = time.time()
            return func(*args, **kwargs)
        except ccxt.RateLimitExceeded:
            log.warning("[API] Rate limit, 10sn bekleniyor")
            time.sleep(10)
        except ccxt.NetworkError as e:
            log.warning(f"[API] Network hatası: {e}")
            time.sleep(3)
        except Exception as e:
            log.warning(f"[API] Hata deneme {attempt+1}: {e}")
            time.sleep(2)
    return None

def get_tickers_cached():
    global ticker_cache, ticker_cache_ts
    with ticker_lock:
        if time.time() - ticker_cache_ts < TICKER_TTL and ticker_cache:
            return ticker_cache
    tickers = safe_api(exchange.fetch_tickers)
    if tickers:
        with ticker_lock:
            ticker_cache    = tickers
            ticker_cache_ts = time.time()
    return tickers

# ════════════════════════════════════════
# GÜNLÜK PNL
# ════════════════════════════════════════
def günlük_limit_asıldı():
    with daily_pnl_lock:
        return daily_pnl <= MAX_DAILY_LOSS

def pnl_ekle(miktar):
    global daily_pnl
    with daily_pnl_lock:
        daily_pnl += miktar
        return daily_pnl

# ════════════════════════════════════════
# FEAR & GREED
# ════════════════════════════════════════
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

# ════════════════════════════════════════
# BTC TREND
# ════════════════════════════════════════
def get_btc_trend():
    with btc_lock:
        if time.time() - btc_cache["ts"] < BTC_TTL:
            return btc_cache["trend"], btc_cache["price"], btc_cache["chg"]
    try:
        raw = safe_api(exchange.fetch_ohlcv, "BTC/USDT:USDT", "1h", limit=50)
        if not raw:
            return "NEUTRAL_LONG", 0, 0
        df     = pd.DataFrame(raw, columns=["t","o","h","l","c","v"])
        price  = float(df["c"].iloc[-1])
        chg4h  = (price - float(df["c"].iloc[-5]))  / float(df["c"].iloc[-5])  * 100
        chg24h = (price - float(df["c"].iloc[-25])) / float(df["c"].iloc[-25]) * 100
        ema9   = float(df["c"].ewm(span=9).mean().iloc[-1])
        ema21  = float(df["c"].ewm(span=21).mean().iloc[-1])
        ema50  = float(df["c"].ewm(span=50).mean().iloc[-1])

        if chg24h < -3.0 or chg4h < -1.5:
            trend = "DOWN"
        elif chg24h > 2.0 or (chg4h > 1.0 and ema9 > ema21 > ema50):
            trend = "UP"
        elif chg4h < -0.8 or chg24h < -1.0:
            trend = "NEUTRAL_SHORT"
        else:
            trend = "NEUTRAL_LONG"

        with btc_lock:
            btc_cache.update({"trend": trend, "price": price, "chg": chg24h, "ts": time.time()})
        log.info(f"[BTC] {trend} ${price:,.0f} ({chg24h:+.1f}%)")
        return trend, price, chg24h
    except Exception as e:
        log.warning(f"[BTC] {e}")
        return "NEUTRAL_LONG", 0, 0

# ════════════════════════════════════════
# İNDİKATÖRLER
# ════════════════════════════════════════
def calc_rsi(series, period=14):
    delta = series.diff()
    gain  = delta.clip(lower=0).rolling(period).mean()
    loss  = (-delta.clip(upper=0)).rolling(period).mean()
    rs    = gain / loss.replace(0, 0.001)
    return float((100 - 100 / (1 + rs)).iloc[-1])

def calc_atr(df, period=14):
    h, l, c = df["h"], df["l"], df["c"]
    tr = pd.concat([
        h - l,
        (h - c.shift()).abs(),
        (l - c.shift()).abs()
    ], axis=1).max(axis=1)
    return float(tr.rolling(period).mean().iloc[-1])

# ════════════════════════════════════════
# HACİM PATLAMASI TESPİTİ
# ════════════════════════════════════════
def hacim_patlamasi_var_mi(symbol):
    """
    Son 1-5 dakikada anlık hacim patlaması var mı?
    - Son 1m hacmi ortalamadan 2x+ fazla
    - Alım baskısı %65+
    - Fiyat yükseliyor
    """
    try:
        r1m = safe_api(exchange.fetch_ohlcv, symbol, "1m", limit=25)
        if not r1m or len(r1m) < 10:
            return False, {}, 0

        df1m = pd.DataFrame(r1m, columns=["t","o","h","l","c","v"])
        price = float(df1m["c"].iloc[-1])

        # Son mum hacmi vs ortalama
        son_hacim = float(df1m["v"].iloc[-1])
        ort_hacim = float(df1m["v"].iloc[:-1].mean())
        vol_oran  = son_hacim / max(ort_hacim, 0.0001)

        # Son 3 mumun alım oranı
        son3 = df1m.tail(4).iloc[:-1]
        alim_hacim   = sum(float(r["v"]) for _, r in son3.iterrows() if float(r["c"]) > float(r["o"]))
        toplam_hacim = float(son3["v"].sum())
        alim_orani   = alim_hacim / max(toplam_hacim, 0.0001) * 100

        # Fiyat yükseliyor mu?
        fiyat_yukselis = float(df1m["c"].iloc[-1]) > float(df1m["c"].iloc[-4])

        # RSI kontrolü
        rsi_val = calc_rsi(df1m["c"])

        # ATR hesapla
        r1h = safe_api(exchange.fetch_ohlcv, symbol, "1h", limit=20)
        if not r1h or len(r1h) < 15:
            return False, {}, price
        df1h    = pd.DataFrame(r1h, columns=["t","o","h","l","c","v"])
        atr_val = calc_atr(df1h)

        # Geç kalma kontrolü — son 5m'de çok pompaladıysa giriş yapma
        pct_5m = (price - float(df1m["c"].iloc[-6])) / float(df1m["c"].iloc[-6]) * 100
        if pct_5m > 3.0:
            return False, {"red": f"Geç kalındı +{pct_5m:.1f}%"}, price

        gecti = (
            vol_oran  >= VOL_SPIKE_MIN and
            alim_orani >= ALIM_MIN     and
            fiyat_yukselis             and
            rsi_val   < RSI_MAX
        )

        detay = {
            "vol_oran":   round(vol_oran, 1),
            "alim_orani": round(alim_orani, 1),
            "rsi":        round(rsi_val, 1),
            "pct_5m":     round(pct_5m, 2),
            "atr":        atr_val,
            "price":      price,
        }
        return gecti, detay, price

    except Exception as e:
        log.warning(f"[HACİM] {symbol}: {e}")
        return False, {}, 0

# ════════════════════════════════════════
# PNL HESABI
# ════════════════════════════════════════
def hesap_pnl(pos, price):
    entry   = pos["entry"]
    amount  = pos.get("amount", POS_SIZE / entry)
    pnl     = (price - entry) * amount - POS_SIZE * COMMISSION
    pnl_pct = (price - entry) / entry * 100
    return pnl, pnl_pct

# ════════════════════════════════════════
# İŞLEM AÇ
# ════════════════════════════════════════
def open_pos(symbol, detay, btc_trend):
    if günlük_limit_asıldı():
        return False

    sym      = symbol.split("/")[0]
    price    = detay["price"]
    atr_val  = detay["atr"]

    # TP/SL hesapla
    limit_fiyat = round(price - atr_val * ATR_LIMIT, 8)
    sl          = round(limit_fiyat - atr_val * ATR_SL, 8)
    tp1         = round(limit_fiyat + atr_val * ATR_TP1, 8)
    tp2         = round(limit_fiyat + atr_val * ATR_TP2, 8)
    tp3         = round(limit_fiyat + atr_val * ATR_TP3, 8)
    tps         = [tp1, tp2, tp3]

    with pos_lock:
        sym_base = sym.upper()
        if symbol in positions: return False
        for ex in positions:
            if ex.split("/")[0].upper() == sym_base: return False
        with closed_lock:
            if sym_base in recently_closed:
                if time.time() - recently_closed[sym_base] < 14400: return False
        if len(positions) >= MAX_OPEN: return False
        if günlük_limit_asıldı(): return False

        positions[symbol] = {
            "entry":     limit_fiyat,
            "sl":        sl,
            "tps":       tps,
            "tp_idx":    0,
            "max_price": limit_fiyat,
            "open_time": time.time(),
            "amount":    0,
            "btc_trend": btc_trend,
            "atr":       atr_val,
            "pending":   True,  # Emir dolmadan yönetme
        }

    try:
        try: exchange.set_margin_mode("isolated", symbol, params={"marginCoin": "USDT"})
        except: pass
        try: exchange.set_leverage(LEVERAGE, symbol, params={"marginCoin": "USDT"})
        except: pass

        amount = round(POS_SIZE / limit_fiyat, 4)
        amount = float(exchange.amount_to_precision(symbol, amount))
        if amount <= 0:
            with pos_lock: positions.pop(symbol, None)
            return False

        limit_fiyat_p = float(exchange.price_to_precision(symbol, limit_fiyat))
        gercek_fiyat  = None

        # Önce limit emir dene
        order = safe_api(
            exchange.create_order,
            symbol, "limit", "buy", amount, limit_fiyat_p,
            {"marginMode": "isolated", "marginCoin": "USDT", "timeInForce": "GTC"}
        )

        if order:
            order_id = order.get("id")
            log.info(f"[LİMİT] {sym} emir:{order_id} @ {limit_fiyat_p:.8f}")

            # 30sn bekle
            for _ in range(6):
                time.sleep(5)
                durum = safe_api(exchange.fetch_order, order_id, symbol)
                if durum and durum.get("status") == "closed":
                    gercek_fiyat = float(durum.get("average") or limit_fiyat_p)
                    log.info(f"[LİMİT] {sym} doldu @ {gercek_fiyat:.8f}")
                    break

            # Dolmadıysa iptal et
            if not gercek_fiyat:
                try: safe_api(exchange.cancel_order, order_id, symbol)
                except: pass
                log.info(f"[LİMİT] {sym} dolmadı, market emirle giriyor")

        # Market emirle gir (limit dolmadıysa)
        if not gercek_fiyat:
            t = safe_api(exchange.fetch_ticker, symbol)
            if not t:
                with pos_lock: positions.pop(symbol, None)
                return False
            market_fiyat = float(t["last"])

            # Fiyat çok kaçtıysa iptal et
            if market_fiyat > price * 1.015:
                log.info(f"[İPTAL] {sym} fiyat kaçtı: {market_fiyat:.8f}")
                with pos_lock: positions.pop(symbol, None)
                return False

            m_order = safe_api(
                exchange.create_order,
                symbol, "market", "buy", amount, None,
                {"marginMode": "isolated", "marginCoin": "USDT"}
            )
            if not m_order:
                with pos_lock: positions.pop(symbol, None)
                return False
            gercek_fiyat = market_fiyat
            log.info(f"[MARKET] {sym} giriş @ {gercek_fiyat:.8f}")

        # TP/SL'yi gerçek fiyata göre güncelle
        sl_gercek  = round(gercek_fiyat - atr_val * ATR_SL, 8)
        tp1_gercek = round(gercek_fiyat + atr_val * ATR_TP1, 8)
        tp2_gercek = round(gercek_fiyat + atr_val * ATR_TP2, 8)
        tp3_gercek = round(gercek_fiyat + atr_val * ATR_TP3, 8)

        with pos_lock:
            if symbol in positions:
                positions[symbol].update({
                    "entry":   gercek_fiyat,
                    "sl":      sl_gercek,
                    "tps":     [tp1_gercek, tp2_gercek, tp3_gercek],
                    "amount":  amount,
                    "pending": False,
                })

    except Exception as e:
        log.error(f"[EMIR] {sym}: {e}")
        with pos_lock: positions.pop(symbol, None)
        return False

    # Telegram bildirimi
    sl_pct  = (gercek_fiyat - sl_gercek)  / gercek_fiyat * 100
    tp1_pct = (tp1_gercek - gercek_fiyat) / gercek_fiyat * 100
    tp2_pct = (tp2_gercek - gercek_fiyat) / gercek_fiyat * 100
    tp3_pct = (tp3_gercek - gercek_fiyat) / gercek_fiyat * 100
    rr      = tp1_pct / sl_pct if sl_pct > 0 else 0

    tg(
        f"📊 #{sym}USDT.P\n"
        f"🏁 LONG - Giriş: {gercek_fiyat:.8f}\n"
        f"🚫 Stop: {sl_gercek:.8f} (-%{sl_pct:.1f})\n\n"
        f"💡 Pozisyon Detayları\n"
        f"TP1: {tp1_gercek:.8f} (+%{tp1_pct:.1f}) ──\n"
        f"TP2: {tp2_gercek:.8f} (+%{tp2_pct:.1f}) ──\n"
        f"TP3: {tp3_gercek:.8f} (+%{tp3_pct:.1f}) ──\n\n"
        f"📊 BTC: {btc_trend}\n"
        f"Hacim: {detay['vol_oran']:.1f}x | Alım: %{detay['alim_orani']:.0f}\n"
        f"RSI: {detay['rsi']:.0f} | 5m: {detay['pct_5m']:+.1f}%\n"
        f"R:R = 1:{rr:.1f} | ATR: {atr_val:.6f}"
    )
    log.info(f"[AÇIK] {sym} @ {gercek_fiyat:.8f} sl:{sl_gercek:.8f} atr:{atr_val:.8f}")
    return True

# ════════════════════════════════════════
# İŞLEM KAPAT
# ════════════════════════════════════════
def close_pos(symbol, reason, exit_price=None):
    global daily_pnl

    with pos_lock:
        pos = positions.pop(symbol, None)
    if not pos:
        return

    sym    = symbol.split("/")[0]
    amount = pos.get("amount", 0)

    if not amount or amount <= 0:
        amount = round(POS_SIZE / pos["entry"], 4)

    # Borsadan gerçek miktar al
    try:
        pos_list = safe_api(exchange.fetch_positions, [symbol])
        if pos_list:
            for p in pos_list:
                contracts = float(p.get("contracts") or 0)
                if contracts > 0 and p.get("side") == "long":
                    amount = contracts
                    break
    except Exception as e:
        log.warning(f"[KAPAT_POS] {sym}: {e}")

    # Kapanış emri
    try:
        safe_api(
            exchange.create_order,
            symbol, "market", "sell", amount, None,
            {"reduceOnly": True, "marginCoin": "USDT"}
        )
    except Exception as e:
        err = str(e)
        if "22002" in err or "No position" in err or "position not exist" in err.lower():
            log.info(f"[KAPAT] {sym}: Borsada pozisyon yok")
        else:
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
        save_trade({
            "symbol": symbol, "signal": "LONG",
            "pnl": round(pnl, 4), "sure_dk": sure,
            "reason": reason, "btc_trend": pos.get("btc_trend", ""),
        })
    except: pass

    if yeni_toplam <= MAX_DAILY_LOSS:
        tg(f"⛔ GÜNLÜK LİMİT! {yeni_toplam:+.2f}$")

    icon = "🟢" if pnl >= 0 else "🔴"
    tg(
        f"{icon} {sym_base} KAPANDI\n"
        f"{reason}\n"
        f"PnL: {pnl:+.2f}$ ({pnl_pct:+.1f}%) | {sure}dk\n"
        f"Günlük: {yeni_toplam:+.2f}$"
    )

# ════════════════════════════════════════
# YÖNETİM DÖNGÜSÜ
# ════════════════════════════════════════
def manage_loop():
    while True:
        time.sleep(8)
        try:
            with pos_lock:
                syms = list(positions.keys())
            if not syms:
                continue

            for symbol in syms:
                with pos_lock:
                    pos = positions.get(symbol)
                if not pos:
                    continue

                # Emir bekleniyorsa yönetme
                if pos.get("pending"):
                    continue

                t = safe_api(exchange.fetch_ticker, symbol)
                if not t:
                    continue

                price        = float(t["last"])
                pnl, pnl_pct = hesap_pnl(pos, price)
                sure         = int((time.time() - pos["open_time"]) / 60)
                entry        = pos["entry"]
                sl           = pos["sl"]
                tps          = pos["tps"]
                tp_idx       = pos.get("tp_idx", 0)
                max_price    = pos.get("max_price", entry)
                atr_val      = pos.get("atr", entry * 0.015)

                # Max fiyatı güncelle
                if price > max_price:
                    with pos_lock:
                        if symbol in positions:
                            positions[symbol]["max_price"] = price
                    max_price = price

                # Stop Loss
                if price <= sl:
                    close_pos(symbol, f"🚫 Stop Loss ({sl:.8f})", price)
                    continue

                # Erken zarar (ilk 8dk)
                if sure <= 8 and pnl_pct <= -1.5:
                    close_pos(symbol, f"Erken zarar ({pnl_pct:.1f}%)", price)
                    continue

                # Zaman aşımı 3 saat
                if sure >= 180:
                    close_pos(symbol, "Zaman aşımı 3 saat", price)
                    continue

                # Günlük limit
                if günlük_limit_asıldı():
                    close_pos(symbol, "Günlük limit", price)
                    continue

                # TP seviyeleri
                if tp_idx < len(tps) and price >= tps[tp_idx]:
                    if tp_idx == 0:
                        yeni_sl = entry                           # başabaş
                    elif tp_idx == 1:
                        yeni_sl = tps[0]                         # TP1 seviyesi
                    else:
                        yeni_sl = tps[tp_idx - 1]                # önceki TP

                    with pos_lock:
                        if symbol in positions:
                            positions[symbol]["tp_idx"] = tp_idx + 1
                            positions[symbol]["sl"]     = yeni_sl

                    sym     = symbol.split("/")[0]
                    sonraki = f"{tps[tp_idx+1]:.8f}" if tp_idx + 1 < len(tps) else "∞"
                    tg(
                        f"🎯 {sym} TP{tp_idx+1} HIT! +{pnl_pct:.1f}%\n"
                        f"SL → {yeni_sl:.8f}\n"
                        f"Sonraki TP: {sonraki}"
                    )
                    tp_idx += 1

                # TP1 sonrası trailing stop
                if tp_idx > 0:
                    geri = (max_price - price) / max_price * 100
                    if geri >= TP_TRAILING:
                        close_pos(symbol, f"Trailing stop (tepeden -%{geri:.1f})", price)
                        continue

        except Exception as e:
            log.error(f"[MANAGE] {e}")

# ════════════════════════════════════════
# TARAYICI
# ════════════════════════════════════════
def scanner_loop():
    time.sleep(15)
    while True:
        try:
            if günlük_limit_asıldı():
                time.sleep(SCAN_INTERVAL)
                continue

            btc_trend, btc_price, btc_chg = get_btc_trend()

            # BTC DOWN → dur
            if btc_trend == "DOWN":
                log.info("[SCAN] BTC DOWN - bekleniyor")
                time.sleep(SCAN_INTERVAL)
                continue

            fg_val, fg_lbl = get_fear_greed()
            if fg_val <= FG_MIN:
                log.info(f"[SCAN] Extreme Fear ({fg_val}) - bekleniyor")
                time.sleep(SCAN_INTERVAL)
                continue

            with pos_lock:
                if len(positions) >= MAX_OPEN:
                    time.sleep(15)
                    continue
                open_syms = set(positions.keys())

            tickers = get_tickers_cached()
            if not tickers:
                time.sleep(SCAN_INTERVAL)
                continue

            # Aday filtrele — hacim artışı olan coinler
            candidates = []
            for symbol, ticker in tickers.items():
                if not symbol.endswith("/USDT:USDT"): continue
                sym = symbol.split("/")[0]
                if sym in BLACKLIST: continue
                if symbol in open_syms: continue

                qv    = ticker.get("quoteVolume") or 0
                pct   = ticker.get("percentage")  or 0
                price = float(ticker.get("last")   or 0)

                if qv    < MIN_VOL_USDT or qv > MAX_VOL_USDT: continue
                if price < MIN_PRICE    or price > MAX_PRICE:  continue
                if abs(pct) > 25: continue
                if pct < 0.5: continue   # En az %0.5 hareket

                sym_base = sym.upper()
                with closed_lock:
                    if sym_base in recently_closed:
                        if time.time() - recently_closed[sym_base] < 14400: continue

                candidates.append({"symbol": symbol, "pct": pct, "qv": qv})

            # En yüksek momentumlu 10 coin
            candidates.sort(key=lambda x: x["pct"], reverse=True)
            top5   = candidates[:5]
            rest   = candidates[5:]
            random.shuffle(rest)
            candidates = (top5 + rest)[:10]

            log.info(f"[SCAN] {len(candidates)} aday | BTC:{btc_trend} FG:{fg_val}")

            for c in candidates:
                symbol = c["symbol"]
                sym    = symbol.split("/")[0]

                with pos_lock:
                    if len(positions) >= MAX_OPEN: break
                    if symbol in open_syms: continue

                # Hacim patlaması kontrolü
                gecti, detay, price = hacim_patlamasi_var_mi(symbol)

                if gecti:
                    log.info(
                        f"[SİNYAL] {sym} "
                        f"Hacim:{detay['vol_oran']:.1f}x "
                        f"Alım:%{detay['alim_orani']:.0f} "
                        f"RSI:{detay['rsi']:.0f} → GİRİYOR"
                    )
                    threading.Thread(
                        target=open_pos,
                        args=(symbol, detay, btc_trend),
                        daemon=True
                    ).start()
                    with pos_lock:
                        open_syms = set(positions.keys())
                else:
                    if detay.get("red"):
                        log.info(f"[PAS] {sym}: {detay['red']}")
                    else:
                        log.info(
                            f"[PAS] {sym}: "
                            f"Hacim:{detay.get('vol_oran',0):.1f}x "
                            f"Alım:%{detay.get('alim_orani',0):.0f}"
                        )

                time.sleep(1)

            time.sleep(SCAN_INTERVAL)

        except Exception as e:
            log.error(f"[SCANNER] {e}")
            time.sleep(10)

# ════════════════════════════════════════
# GÜNLÜK SIFIRLAMA
# ════════════════════════════════════════
def gunluk_reset_loop():
    global daily_pnl
    import datetime
    while True:
        try:
            simdi = datetime.datetime.now()
            yarin = (simdi + datetime.timedelta(days=1)).replace(
                hour=0, minute=0, second=5, microsecond=0
            )
            time.sleep((yarin - simdi).total_seconds())
            with daily_pnl_lock:
                eski      = daily_pnl
                daily_pnl = 0.0
            tg(f"🔄 Yeni gün! Dün: {eski:+.2f}$")
        except Exception as e:
            log.error(f"[RESET] {e}")
            time.sleep(3600)

# ════════════════════════════════════════
# HEALTH SERVER
# ════════════════════════════════════════
def health_server():
    from http.server import HTTPServer, BaseHTTPRequestHandler
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            fg, _       = get_fear_greed()
            trend, _, _ = get_btc_trend()
            with pos_lock:
                pos_str = ",".join(s.split("/")[0] for s in positions)
            with daily_pnl_lock:
                pnl = daily_pnl
            self.wfile.write(
                f"OK|btc:{trend}|fg:{fg}|pos:{len(positions)}({pos_str})|pnl:{pnl:+.2f}".encode()
            )
        def log_message(self, *a): pass
    HTTPServer(("0.0.0.0", 8080), H).serve_forever()

# ════════════════════════════════════════
# AÇILIŞTA POZİSYON YÜKLE
# ════════════════════════════════════════
def load_open_positions():
    try:
        log.info("[YUKLE] Kontrol ediliyor...")
        raw = safe_api(exchange.fetch_positions)
        if not raw:
            log.info("[YUKLE] Pozisyon yok")
            return

        if raw:
            log.info(f"[YUKLE] Alan formatı: {list(raw[0].keys())}")

        btc_trend, _, _ = get_btc_trend()
        yuklenen = 0
        lines    = ["♻️ Önceki pozisyonlar yüklendi:\n"]

        for p in raw:
            try:
                contracts = float(p.get("contracts") or p.get("size") or 0)
                symbol    = p.get("symbol", "")
                side      = p.get("side", "")
                entry     = float(p.get("entryPrice") or 0)

                if contracts == 0 or not symbol or side != "long" or entry == 0:
                    continue

                atr_val = entry * 0.015
                tps = [
                    round(entry + atr_val * ATR_TP1, 8),
                    round(entry + atr_val * ATR_TP2, 8),
                    round(entry + atr_val * ATR_TP3, 8),
                ]
                sl = round(entry - atr_val * ATR_SL, 8)

                with pos_lock:
                    if symbol not in positions:
                        positions[symbol] = {
                            "entry":     entry,
                            "sl":        sl,
                            "tps":       tps,
                            "tp_idx":    0,
                            "max_price": entry,
                            "open_time": time.time(),
                            "amount":    contracts,
                            "btc_trend": btc_trend,
                            "atr":       atr_val,
                            "pending":   False,
                        }
                        yuklenen += 1
                        t   = safe_api(exchange.fetch_ticker, symbol)
                        now = float(t["last"]) if t else entry
                        pnl = (now - entry) * contracts - POS_SIZE * COMMISSION
                        icon = "🟢" if pnl >= 0 else "🔴"
                        lines.append(f"{icon} {symbol.split('/')[0]} @ {entry:.8f} | {pnl:+.2f}$")
                        log.info(f"[YUKLE] {symbol.split('/')[0]} LONG @ {entry}")
            except Exception as e:
                log.warning(f"[YUKLE] {e}")

        if yuklenen > 0:
            tg("\n".join(lines))
        else:
            log.info("[YUKLE] Yüklenecek pozisyon yok")
    except Exception as e:
        log.error(f"[YUKLE] {e}")

# ════════════════════════════════════════
# TELEGRAM HANDLER
# ════════════════════════════════════════
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

    if "/durum" in lower:
        with pos_lock:
            if not positions:
                bot.send_message(msg.chat.id, "📋 Açık pozisyon yok.")
                return
            lines = ["📋 POZİSYONLAR\n"]
            for sym, pos in positions.items():
                t = safe_api(exchange.fetch_ticker, sym)
                if not t: continue
                price        = float(t["last"])
                pnl, pnl_pct = hesap_pnl(pos, price)
                sure         = int((time.time() - pos["open_time"]) / 60)
                tp_idx       = pos.get("tp_idx", 0)
                lines.append(
                    f"{'🟢' if pnl>=0 else '🔴'} {sym.split('/')[0]} LONG\n"
                    f"   {pos['entry']:.8f} → {price:.8f}\n"
                    f"   PnL: {pnl:+.2f}$ ({pnl_pct:+.1f}%) | {sure}dk\n"
                    f"   SL: {pos['sl']:.8f} | TP{tp_idx} geçildi\n"
                )
            bot.send_message(msg.chat.id, "\n".join(lines))
        return

    if "/istatistik" in lower:
        if not supa:
            bot.send_message(msg.chat.id, "Supabase bağlı değil.")
            return
        try:
            r    = supa.table("gpt_trades").select("pnl,signal").execute()
            data = [d for d in (r.data or []) if d.get("signal") == "LONG"]
            if not data:
                bot.send_message(msg.chat.id, "Kayıt yok.")
                return
            toplam = len(data)
            kazan  = sum(1 for d in data if float(d.get("pnl") or 0) > 0)
            net    = sum(float(d.get("pnl") or 0) for d in data)
            with daily_pnl_lock:
                gunluk = daily_pnl
            bot.send_message(
                msg.chat.id,
                f"📊 İSTATİSTİK\n"
                f"Toplam: {toplam} | Kazanan: {kazan} (%{kazan/toplam*100:.0f})\n"
                f"Net PnL: {net:+.2f}$\n"
                f"Günlük: {gunluk:+.2f}$"
            )
        except Exception as e:
            bot.send_message(msg.chat.id, f"Hata: {e}")
        return

    if "/btc" in lower:
        trend, price, chg = get_btc_trend()
        fg, fl = get_fear_greed()
        bot.send_message(
            msg.chat.id,
            f"BTC: {trend}\n${price:,.0f} ({chg:+.1f}%)\n\n"
            f"Fear&Greed: {fg} ({fl})"
        )
        return

    if "kapat" in lower:
        with pos_lock:
            syms = list(positions.keys())
        if not syms:
            bot.send_message(msg.chat.id, "Açık pozisyon yok.")
            return
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
        bot.send_message(msg.chat.id, f"🔍 {sym} analiz ediliyor...")
        gecti, detay, price = hacim_patlamasi_var_mi(coin)
        trend, _, _ = get_btc_trend()
        fg, fl      = get_fear_greed()
        bot.send_message(
            msg.chat.id,
            f"📊 {sym}\n"
            f"Fiyat: {price:.8f}\n"
            f"Hacim: {detay.get('vol_oran', 0):.1f}x {'✅' if detay.get('vol_oran', 0) >= VOL_SPIKE_MIN else '❌'}\n"
            f"Alım: %{detay.get('alim_orani', 0):.0f} {'✅' if detay.get('alim_orani', 0) >= ALIM_MIN else '❌'}\n"
            f"RSI: {detay.get('rsi', 0):.0f} {'✅' if detay.get('rsi', 0) < RSI_MAX else '❌'}\n"
            f"5m hareket: {detay.get('pct_5m', 0):+.1f}%\n"
            f"BTC: {trend} | FG: {fg} ({fl})\n\n"
            f"{'✅ GİRİLİR' if gecti else '❌ PAS'}"
        )
        return

    bot.send_message(
        msg.chat.id,
        "Komutlar:\n/durum\n/istatistik\n/btc\nCOIN_ADI - analiz\nCOIN kapat / hepsi kapat"
    )

# ════════════════════════════════════════
# SHUTDOWN
# ════════════════════════════════════════
import signal as sig_mod, sys

def shutdown(signum, frame):
    with pos_lock:
        syms = list(positions.keys())
    if syms:
        tg(f"⏸ Bot yeniden başlıyor...\n{len(syms)} pozisyon açık, yüklenecek.")
    sys.exit(0)

sig_mod.signal(sig_mod.SIGTERM, shutdown)
sig_mod.signal(sig_mod.SIGINT,  shutdown)

# ════════════════════════════════════════
# MAIN
# ════════════════════════════════════════
if __name__ == "__main__":
    print("SADIK TRADER v9 BAŞLIYOR...")
    load_open_positions()
    threading.Thread(target=health_server,     daemon=True).start()
    threading.Thread(target=manage_loop,       daemon=True).start()
    threading.Thread(target=scanner_loop,      daemon=True).start()
    threading.Thread(target=gunluk_reset_loop, daemon=True).start()

    fg, fl            = get_fear_greed()
    trend, price, chg = get_btc_trend()

    tg(
        "🤖 SADIK TRADER v9 — HACİM PATLAMASI STRATEJİSİ\n\n"
        "📊 Strateji:\n"
        "  ✅ Anlık hacim patlaması (2x+)\n"
        "  ✅ Alım baskısı %65+\n"
        "  ✅ BTC DOWN değil\n"
        "  ✅ RSI 68 altı\n"
        "  ✅ Limit → Market emir\n\n"
        "🎯 ATR Bazlı TP/SL:\n"
        f"  TP1: ATR×{ATR_TP1} | TP2: ATR×{ATR_TP2} | TP3: ATR×{ATR_TP3}\n"
        f"  SL:  ATR×{ATR_SL}\n\n"
        f"BTC: {trend} ${price:,.0f} ({chg:+.1f}%)\n"
        f"Fear&Greed: {fg} ({fl})\n\n"
        "/durum /istatistik /btc"
    )

    while True:
        try:
            bot.infinity_polling(timeout=30, long_polling_timeout=30)
        except Exception as e:
            log.error(f"[BOT] {e}")
            time.sleep(5)
