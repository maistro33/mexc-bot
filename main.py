#!/usr/bin/env python3
"""
SADIK SCALP v1 - Saf Scalp Botu
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Strateji (Basit & Hızlı):
  1. Hacim Patlaması  → Son 1m hacim 2x+ ortalama
  2. Alım Baskısı     → %65+ alım yoğunluğu  
  3. RSI              → 30-55 arası (ne tepede ne dipte)
  4. BTC              → DOWN değil
  5. Limit Emir       → ATR×0.2 aşağı, 20sn bekle, sonra market

TP/SL (Hızlı Scalp):
  - TP1: ATR × 1.0  (hızlı kar al)
  - TP2: ATR × 2.0  (devam ederse)
  - SL:  ATR × 1.0  (dar stop, hızlı çık)
  - Max süre: 20 dakika
"""

import os, time, threading, logging, re, random, requests
import ccxt
import pandas as pd
import telebot
from supabase import create_client

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("SCALP_V1")

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
MAX_DAILY_LOSS = -10.0
SCAN_INTERVAL  = 20   # 20sn'de bir tara

# TP/SL — Net ~1$ kar hedefi
TP1_PCT       = 2.1   # TP1 = +%2.1 (net ~1$)
TP2_PCT       = 4.0   # TP2 = +%4.0 (devam ederse)
SL_PCT        = 1.0   # SL  = -%1.0
ATR_LIMIT     = 0.1   # Limit emir ATR×0.1 aşağı (daha yakın)
LIMIT_BEKLE   = 20    # 20sn limit bekle
MAX_SURE      = 25    # 25 dakika max
TP_TRAILING   = 0.40  # TP2 sonrası trailing
TP1_DIREKT    = True  # TP1'e ulaşınca direkt kapat

# Scalp filtreleri
VOL_SPIKE_MIN = 2.0   # 2x hacim
ALIM_MIN      = 65.0  # %65 alım
RSI_MIN       = 30    # RSI alt sınır
RSI_MAX       = 60    # RSI üst sınır
PCT_1M_MAX    = 2.0   # 1m'de %2'den fazla pompa = geç kaldın
MIN_VOL_USDT  = 500_000
MAX_VOL_USDT  = 20_000_000
MIN_PRICE     = 0.0001
MAX_PRICE     = 5.0
FG_MIN        = 10

TICKER_TTL    = 20    # 20sn ticker cache

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
BTC_TTL   = 120

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
            time.sleep(10)
        except ccxt.NetworkError as e:
            log.warning(f"[API] Network: {e}")
            time.sleep(3)
        except Exception as e:
            log.warning(f"[API] {attempt+1}: {e}")
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
        raw = safe_api(exchange.fetch_ohlcv, "BTC/USDT:USDT", "15m", limit=30)
        if not raw:
            return "NEUTRAL_LONG", 0, 0
        df     = pd.DataFrame(raw, columns=["t","o","h","l","c","v"])
        price  = float(df["c"].iloc[-1])
        chg1h  = (price - float(df["c"].iloc[-5]))  / float(df["c"].iloc[-5])  * 100
        chg4h  = (price - float(df["c"].iloc[-17])) / float(df["c"].iloc[-17]) * 100

        if chg1h < -1.0 or chg4h < -2.0:
            trend = "DOWN"
        elif chg1h > 1.0 or chg4h > 2.0:
            trend = "UP"
        else:
            trend = "NEUTRAL_LONG"

        with btc_lock:
            btc_cache.update({"trend": trend, "price": price, "chg": chg4h, "ts": time.time()})
        log.info(f"[BTC] {trend} ${price:,.0f} 1h:{chg1h:+.1f}%")
        return trend, price, chg4h
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
# SCALP SİNYAL TESPİTİ
# ════════════════════════════════════════
def scalp_sinyal(symbol):
    """
    Saf scalp sinyali:
    1. 1m hacim patlaması 2x+
    2. Alım baskısı %65+
    3. RSI 30-55 arası
    4. 1m'de geç kalmadı (%2'den az hareket)
    """
    try:
        # 1m verisi
        r1m = safe_api(exchange.fetch_ohlcv, symbol, "1m", limit=30)
        if not r1m or len(r1m) < 15:
            return False, {}

        df1m  = pd.DataFrame(r1m, columns=["t","o","h","l","c","v"])
        price = float(df1m["c"].iloc[-1])

        # Hacim patlaması
        son_hacim = float(df1m["v"].iloc[-1])
        ort_hacim = float(df1m["v"].iloc[:-1].tail(20).mean())
        vol_oran  = son_hacim / max(ort_hacim, 0.0001)

        # Alım oranı (son 3 tamamlanmış mum)
        son3 = df1m.tail(4).iloc[:-1]
        alim = sum(float(r["v"]) for _, r in son3.iterrows() if float(r["c"]) > float(r["o"]))
        toplam = float(son3["v"].sum())
        alim_orani = alim / max(toplam, 0.0001) * 100

        # RSI (1m)
        rsi_val = calc_rsi(df1m["c"], period=9)  # 9 periyot scalp için daha hızlı

        # Geç kalma kontrolü
        pct_1m = (price - float(df1m["c"].iloc[-3])) / float(df1m["c"].iloc[-3]) * 100
        if pct_1m > PCT_1M_MAX:
            return False, {"red": f"Geç +{pct_1m:.1f}%"}

        # ATR (1h verisiyle)
        r1h = safe_api(exchange.fetch_ohlcv, symbol, "1h", limit=15)
        if not r1h or len(r1h) < 14:
            return False, {"red": "ATR veri yok"}
        df1h    = pd.DataFrame(r1h, columns=["t","o","h","l","c","v"])
        atr_val = calc_atr(df1h)

        # Tüm koşullar
        gecti = (
            vol_oran   >= VOL_SPIKE_MIN  and
            alim_orani >= ALIM_MIN       and
            RSI_MIN    <= rsi_val <= RSI_MAX
        )

        detay = {
            "vol":     round(vol_oran, 1),
            "alim":    round(alim_orani, 1),
            "rsi":     round(rsi_val, 1),
            "pct":     round(pct_1m, 2),
            "atr":     atr_val,
            "price":   price,
            "son5_low": float(df1m["l"].tail(5).min()),  # Son 5 mumun dibi
        }
        return gecti, detay

    except Exception as e:
        log.warning(f"[SİNYAL] {symbol}: {e}")
        return False, {}

# ════════════════════════════════════════
# PNL
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

    sym     = symbol.split("/")[0]
    price   = detay["price"]
    atr_val = detay["atr"]
    son5_low = detay.get("son5_low", price)

    # En iyi limit fiyat: son 5 mumun dibi ile ATR×0.3 aşağısının büyüğü
    # Yani destek seviyesine koy ama çok uzak olmasın
    limit_atr = round(price - atr_val * 0.3, 8)
    limit_p   = round(max(son5_low * 1.001, limit_atr), 8)  # Destek biraz üstü

    sl  = round(limit_p * (1 - SL_PCT / 100), 8)
    tp1 = round(limit_p * (1 + TP1_PCT / 100), 8)
    tp2 = round(limit_p * (1 + TP2_PCT / 100), 8)
    tps = [tp1, tp2]

    with pos_lock:
        sym_base = sym.upper()
        if symbol in positions: return False
        for ex in positions:
            if ex.split("/")[0].upper() == sym_base: return False
        with closed_lock:
            if sym_base in recently_closed:
                if time.time() - recently_closed[sym_base] < 1800: return False  # 30dk bekle
        if len(positions) >= MAX_OPEN: return False
        if günlük_limit_asıldı(): return False

        positions[symbol] = {
            "entry":     limit_p,
            "sl":        sl,
            "tps":       tps,
            "tp_idx":    0,
            "max_price": limit_p,
            "open_time": time.time(),
            "amount":    0,
            "btc_trend": btc_trend,
            "atr":       atr_val,
            "pending":   True,
        }

    try:
        try: exchange.set_margin_mode("isolated", symbol, params={"marginCoin": "USDT"})
        except: pass
        try: exchange.set_leverage(LEVERAGE, symbol, params={"marginCoin": "USDT"})
        except: pass

        amount = round(POS_SIZE / limit_p, 4)
        amount = float(exchange.amount_to_precision(symbol, amount))
        if amount <= 0:
            with pos_lock: positions.pop(symbol, None)
            return False

        limit_p_str = float(exchange.price_to_precision(symbol, limit_p))
        gercek_fiyat = None

        # Limit emir
        order = safe_api(
            exchange.create_order,
            symbol, "limit", "buy", amount, limit_p_str,
            {"marginMode": "isolated", "marginCoin": "USDT", "timeInForce": "GTC"}
        )

        if order:
            order_id = order.get("id")
            log.info(f"[LİMİT] {sym} @ {limit_p_str:.8f}")

            # 20sn bekle
            for _ in range(4):
                time.sleep(5)
                durum = safe_api(exchange.fetch_order, order_id, symbol)
                if durum and durum.get("status") == "closed":
                    gercek_fiyat = float(durum.get("average") or limit_p_str)
                    log.info(f"[LİMİT] {sym} doldu @ {gercek_fiyat:.8f}")
                    break

            if not gercek_fiyat:
                try: safe_api(exchange.cancel_order, order_id, symbol)
                except: pass
                log.info(f"[İPTAL] {sym} limit dolmadı, pas geçildi")
                with pos_lock: positions.pop(symbol, None)
                return False

        if not gercek_fiyat:
            with pos_lock: positions.pop(symbol, None)
            return False

        # Gerçek fiyata göre sabit yüzde TP/SL
        sl_g  = round(gercek_fiyat * (1 - SL_PCT  / 100), 8)
        tp1_g = round(gercek_fiyat * (1 + TP1_PCT / 100), 8)
        tp2_g = round(gercek_fiyat * (1 + TP2_PCT / 100), 8)

        with pos_lock:
            if symbol in positions:
                positions[symbol].update({
                    "entry":   gercek_fiyat,
                    "sl":      sl_g,
                    "tps":     [tp1_g, tp2_g],
                    "amount":  amount,
                    "pending": False,
                })

    except Exception as e:
        log.error(f"[EMIR] {sym}: {e}")
        with pos_lock: positions.pop(symbol, None)
        return False

    sl_pct  = (gercek_fiyat - sl_g)  / gercek_fiyat * 100
    tp1_pct = (tp1_g - gercek_fiyat) / gercek_fiyat * 100
    tp2_pct = (tp2_g - gercek_fiyat) / gercek_fiyat * 100

    tg(
        f"⚡ #{sym}USDT.P SCALP\n"
        f"🏁 Giriş: {gercek_fiyat:.8f}\n"
        f"🚫 SL: {sl_g:.8f} (-%{SL_PCT})\n"
        f"🎯 TP1: {tp1_g:.8f} (+%{TP1_PCT})\n"
        f"🎯 TP2: {tp2_g:.8f} (+%{TP2_PCT})\n\n"
        f"Hacim: {detay['vol']:.1f}x | Alım: %{detay['alim']:.0f}\n"
        f"RSI: {detay['rsi']:.0f} | 1m: {detay['pct']:+.1f}%\n"
        f"BTC: {btc_trend} | Max: {MAX_SURE}dk"
    )
    log.info(f"[AÇIK] {sym} @ {gercek_fiyat:.8f}")
    return True

# ════════════════════════════════════════
# İŞLEM KAPAT
# ════════════════════════════════════════
def close_pos(symbol, reason, exit_price=None):
    with pos_lock:
        pos = positions.pop(symbol, None)
    if not pos:
        return

    sym    = symbol.split("/")[0]
    amount = pos.get("amount", 0)
    if not amount or amount <= 0:
        amount = round(POS_SIZE / pos["entry"], 4)

    try:
        pos_list = safe_api(exchange.fetch_positions, [symbol])
        if pos_list:
            for p in pos_list:
                c = float(p.get("contracts") or 0)
                if c > 0 and p.get("side") == "long":
                    amount = c
                    break
    except: pass

    try:
        safe_api(
            exchange.create_order,
            symbol, "market", "sell", amount, None,
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
        save_trade({
            "symbol": symbol, "signal": "LONG",
            "pnl": round(pnl, 4), "sure_dk": sure,
            "reason": reason, "btc_trend": pos.get("btc_trend", ""),
        })
    except: pass

    if yeni_toplam <= MAX_DAILY_LOSS:
        tg(f"⛔ GÜNLÜK LİMİT! {yeni_toplam:+.2f}$")

    icon = "🟢" if pnl >= 0 else "🔴"
    tg(f"{icon} {sym_base} KAPANDI\n{reason}\nPnL: {pnl:+.2f}$ ({pnl_pct:+.1f}%) | {sure}dk\nGünlük: {yeni_toplam:+.2f}$")

# ════════════════════════════════════════
# YÖNETİM DÖNGÜSÜ
# ════════════════════════════════════════
def manage_loop():
    while True:
        time.sleep(5)  # Scalp için 5sn kontrol
        try:
            with pos_lock:
                syms = list(positions.keys())
            if not syms:
                continue

            for symbol in syms:
                with pos_lock:
                    pos = positions.get(symbol)
                if not pos or pos.get("pending"):
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
                atr_val      = pos.get("atr", entry * 0.01)

                # Max fiyat güncelle
                if price > max_price:
                    with pos_lock:
                        if symbol in positions:
                            positions[symbol]["max_price"] = price
                    max_price = price

                # SL
                if price <= sl:
                    close_pos(symbol, f"🚫 SL ({sl:.8f})", price)
                    continue

                # Scalp max süre — 20 dakika
                if sure >= MAX_SURE:
                    close_pos(symbol, f"⏰ Süre doldu ({MAX_SURE}dk)", price)
                    continue

                # Günlük limit
                if günlük_limit_asıldı():
                    close_pos(symbol, "Günlük limit", price)
                    continue

                # TP seviyeleri
                if tp_idx < len(tps) and price >= tps[tp_idx]:
                    sym = symbol.split("/")[0]

                    if tp_idx == 0:
                        # TP1 → Direkt kapat, net ~1$ kar al
                        close_pos(symbol, f"🎯 TP1 +{pnl_pct:.1f}% (net ~1$)", price)
                        continue
                    else:
                        # TP2 → SL'yi TP1'e çek, trailing devreye girer
                        yeni_sl = tps[0]
                        with pos_lock:
                            if symbol in positions:
                                positions[symbol]["tp_idx"] = tp_idx + 1
                                positions[symbol]["sl"]     = yeni_sl
                        tg(f"🎯 {sym} TP2! +{pnl_pct:.1f}%\nSL→{yeni_sl:.8f}")
                        tp_idx += 1

                # TP2 sonrası trailing
                if tp_idx > 1:
                    geri = (max_price - price) / max_price * 100
                    if geri >= TP_TRAILING:
                        close_pos(symbol, f"Trailing -%{geri:.1f}", price)
                        continue

        except Exception as e:
            log.error(f"[MANAGE] {e}")

# ════════════════════════════════════════
# TARAYICI
# ════════════════════════════════════════
def scanner_loop():
    time.sleep(10)
    while True:
        try:
            if günlük_limit_asıldı():
                time.sleep(SCAN_INTERVAL)
                continue

            btc_trend, btc_price, _ = get_btc_trend()

            if btc_trend == "DOWN":
                log.info("[SCAN] BTC DOWN")
                time.sleep(SCAN_INTERVAL)
                continue

            fg_val, _ = get_fear_greed()
            if fg_val <= FG_MIN:
                log.info(f"[SCAN] Extreme Fear {fg_val}")
                time.sleep(SCAN_INTERVAL)
                continue

            with pos_lock:
                if len(positions) >= MAX_OPEN:
                    time.sleep(10)
                    continue
                open_syms = set(positions.keys())

            tickers = get_tickers_cached()
            if not tickers:
                time.sleep(SCAN_INTERVAL)
                continue

            # Aday filtrele
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
                if abs(pct) > 20: continue
                if pct < 0.3: continue  # En az %0.3 hareket

                sym_base = sym.upper()
                with closed_lock:
                    if sym_base in recently_closed:
                        if time.time() - recently_closed[sym_base] < 1800: continue

                candidates.append({"symbol": symbol, "pct": pct})

            # En yüksek momentumlu 8'i al
            candidates.sort(key=lambda x: x["pct"], reverse=True)
            top3  = candidates[:3]
            rest  = candidates[3:]
            random.shuffle(rest)
            candidates = (top3 + rest)[:8]

            log.info(f"[SCAN] {len(candidates)} aday | BTC:{btc_trend} FG:{fg_val}")

            for c in candidates:
                symbol = c["symbol"]
                sym    = symbol.split("/")[0]

                with pos_lock:
                    if len(positions) >= MAX_OPEN: break
                    if symbol in open_syms: continue

                gecti, detay = scalp_sinyal(symbol)

                if gecti:
                    log.info(f"[SCALP] {sym} Vol:{detay['vol']:.1f}x Alım:%{detay['alim']:.0f} RSI:{detay['rsi']:.0f}")
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
                        log.info(f"[PAS] {sym}: Vol:{detay.get('vol',0):.1f}x Alım:%{detay.get('alim',0):.0f} RSI:{detay.get('rsi',0):.0f}")

                time.sleep(0.8)

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
            yarin = (simdi + datetime.timedelta(days=1)).replace(hour=0, minute=0, second=5, microsecond=0)
            time.sleep((yarin - simdi).total_seconds())
            with daily_pnl_lock:
                eski = daily_pnl; daily_pnl = 0.0
            tg(f"🔄 Yeni gün! Dün: {eski:+.2f}$")
        except Exception as e:
            log.error(f"[RESET] {e}"); time.sleep(3600)

# ════════════════════════════════════════
# HEALTH SERVER
# ════════════════════════════════════════
def health_server():
    from http.server import HTTPServer, BaseHTTPRequestHandler
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200); self.end_headers()
            trend, _, _ = get_btc_trend()
            fg, _       = get_fear_greed()
            with pos_lock:
                ps = ",".join(s.split("/")[0] for s in positions)
            with daily_pnl_lock:
                pnl = daily_pnl
            self.wfile.write(f"OK|btc:{trend}|fg:{fg}|pos:{len(positions)}({ps})|pnl:{pnl:+.2f}".encode())
        def log_message(self, *a): pass
    HTTPServer(("0.0.0.0", 8080), H).serve_forever()

# ════════════════════════════════════════
# AÇILIŞTA POZİSYON YÜKLE
# ════════════════════════════════════════
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
                atr_val = entry * 0.01
                with pos_lock:
                    if symbol not in positions:
                        positions[symbol] = {
                            "entry":     entry,
                            "sl":        round(entry * (1 - SL_PCT / 100), 8),
                            "tps":       [round(entry * (1 + TP1_PCT / 100), 8), round(entry * (1 + TP2_PCT / 100), 8)],
                            "tp_idx":    0,
                            "max_price": entry,
                            "open_time": time.time(),
                            "amount":    contracts,
                            "btc_trend": btc_trend,
                            "atr":       atr_val,
                            "pending":   False,
                        }
                        yuklenen += 1
                        t = safe_api(exchange.fetch_ticker, symbol)
                        now = float(t["last"]) if t else entry
                        pnl = (now - entry) * contracts
                        lines.append(f"{'🟢' if pnl>=0 else '🔴'} {symbol.split('/')[0]} @ {entry:.8f} | {pnl:+.2f}$")
            except Exception as e:
                log.warning(f"[YUKLE] {e}")
        if yuklenen > 0:
            tg("\n".join(lines))
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

    # ── SINYAL FORWARD TESPİTİ ──
    # O bottan forward edilen sinyali tanı ve işle
    # Format: 📊 #XPLUSDT.P veya LONG - Giriş Fiyatı: 0.10369
    if ("🏁 long" in lower or "long - giriş" in lower or "#" in text) and "usdt" in text.upper():
        # Coin adını çek — #XPLUSDT.P formatından
        import re as re2
        match = re2.search(r'#([A-Z0-9]+)USDT', text.upper())
        if not match:
            match = re2.search(r'\b([A-Z0-9]{2,10})USDT', text.upper())
        
        if match:
            coin_adi = match.group(1)
            symbol   = f"{coin_adi}/USDT:USDT"
            
            try:
                tickers = get_tickers_cached()
                if symbol not in tickers:
                    bot.send_message(msg.chat.id, f"❌ {coin_adi} bulunamadı.")
                    return
            except:
                pass

            if coin_adi in BLACKLIST:
                bot.send_message(msg.chat.id, f"❌ {coin_adi} blacklist'te.")
                return

            bot.send_message(msg.chat.id, f"📡 Sinyal alındı: {coin_adi}\n🔍 Analiz ediliyor...")
            
            # Analiz et
            gecti, detay = scalp_sinyal(symbol)
            trend, _, _  = get_btc_trend()

            if trend == "DOWN":
                bot.send_message(msg.chat.id, f"❌ {coin_adi} — BTC DOWN, giriş yapılmıyor.")
                return

            if günlük_limit_asıldı():
                bot.send_message(msg.chat.id, "❌ Günlük limit aşıldı.")
                return

            with pos_lock:
                if len(positions) >= MAX_OPEN:
                    bot.send_message(msg.chat.id, f"❌ Max pozisyon ({MAX_OPEN}) dolu.")
                    return

            if gecti:
                bot.send_message(msg.chat.id, 
                    f"✅ {coin_adi} filtreler geçti!\n"
                    f"Hacim:{detay.get('vol',0):.1f}x Alım:%{detay.get('alim',0):.0f} RSI:{detay.get('rsi',0):.0f}\n"
                    f"Limit emir açılıyor...")
                threading.Thread(
                    target=open_pos,
                    args=(symbol, detay, trend),
                    daemon=True
                ).start()
            else:
                bot.send_message(msg.chat.id,
                    f"❌ {coin_adi} filtreler geçemedi\n"
                    f"Hacim:{detay.get('vol',0):.1f}x {'✅' if detay.get('vol',0)>=VOL_SPIKE_MIN else '❌'}\n"
                    f"Alım:%{detay.get('alim',0):.0f} {'✅' if detay.get('alim',0)>=ALIM_MIN else '❌'}\n"
                    f"RSI:{detay.get('rsi',0):.0f} {'✅' if RSI_MIN<=detay.get('rsi',0)<=RSI_MAX else '❌'}"
                )
            return

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
                    f"{'🟢' if pnl>=0 else '🔴'} {sym.split('/')[0]}\n"
                    f"   {pos['entry']:.8f}→{price:.8f}\n"
                    f"   PnL:{pnl:+.2f}$ ({pct:+.1f}%) | {sure}dk\n"
                    f"   SL:{pos['sl']:.8f} TP{pos.get('tp_idx',0)}\n"
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
                f"📊 İSTATİSTİK\nToplam:{toplam} Kazanan:{kazan} (%{kazan/toplam*100:.0f})\nNet:{net:+.2f}$\nGünlük:{gunluk:+.2f}$")
        except Exception as e:
            bot.send_message(msg.chat.id, f"Hata: {e}")
        return

    if "/btc" in lower:
        trend, price, chg = get_btc_trend()
        fg, fl = get_fear_greed()
        bot.send_message(msg.chat.id, f"BTC: {trend}\n${price:,.0f} ({chg:+.1f}%)\nFG: {fg} ({fl})")
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
            f"1m: {detay.get('pct',0):+.1f}%\n"
            f"BTC: {trend}\n\n"
            f"{'✅ GİRİLİR' if gecti else '❌ PAS'}"
        )
        return

    bot.send_message(msg.chat.id, "Komutlar:\n/durum\n/istatistik\n/btc\nCOIN kapat / hepsi kapat")

# ════════════════════════════════════════
# SHUTDOWN
# ════════════════════════════════════════
import signal as sig_mod, sys

def shutdown(signum, frame):
    with pos_lock: syms = list(positions.keys())
    if syms: tg(f"⏸ Yeniden başlıyor...\n{len(syms)} pozisyon açık.")
    sys.exit(0)

sig_mod.signal(sig_mod.SIGTERM, shutdown)
sig_mod.signal(sig_mod.SIGINT, shutdown)

# ════════════════════════════════════════
# MAIN
# ════════════════════════════════════════
if __name__ == "__main__":
    print("SADIK SCALP v1 BAŞLIYOR...")
    load_open_positions()
    threading.Thread(target=health_server,     daemon=True).start()
    threading.Thread(target=manage_loop,       daemon=True).start()
    threading.Thread(target=scanner_loop,      daemon=True).start()
    threading.Thread(target=gunluk_reset_loop, daemon=True).start()

    fg, fl            = get_fear_greed()
    trend, price, chg = get_btc_trend()

    tg(
        "⚡ SADIK SCALP v1\n\n"
        "📊 Strateji:\n"
        "  ✅ Hacim patlaması 2x+\n"
        "  ✅ Alım baskısı %65+\n"
        "  ✅ RSI 30-55 arası\n"
        "  ✅ BTC DOWN değil\n"
        "  ✅ Limit→Market emir\n\n"
        f"⚡ TP1: +%{TP1_PCT} → Direkt kapat (~1$ net)\n"
        f"⚡ TP2: +%{TP2_PCT} → Trailing %{TP_TRAILING}\n"
        f"🚫 SL: -%{SL_PCT} | Max: {MAX_SURE}dk\n\n"
        f"BTC: {trend} ${price:,.0f}\n"
        f"Fear&Greed: {fg} ({fl})\n\n"
        "/durum /istatistik /btc"
    )

    while True:
        try:
            bot.infinity_polling(timeout=30, long_polling_timeout=30)
        except Exception as e:
            log.error(f"[BOT] {e}"); time.sleep(5)
