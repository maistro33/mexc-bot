#!/usr/bin/env python3
"""
SADIK TRADER v5 - Confluence Scoring + ATR SL + Balina Tespiti
Inspired by claude-trader (github.com/Byte-Ventures/claude-trader)
Adapted for Bitget Futures by Claude

Strateji:
- RSI + MACD + Bollinger + EMA confluence scoring (0-100)
- Skor >= 60 → LONG gir
- ATR tabanlı SL (sabit % değil, volatiliteye göre)
- Balina tespiti (3x hacim → sinyal güçlenir)
- BTC trend filtresi (UP/NEUTRAL_LONG → LONG)
- Trailing TP sistemi (sınırsız TP, SL giriş fiyatına)
- Fear & Greed Index filtresi
"""

import os, time, threading, logging, re, requests
import ccxt
import pandas as pd
import telebot
from supabase import create_client

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("SADIK")

# ─── CONFIG ───
TELE_TOKEN  = os.getenv("TELE_TOKEN", "")
CHAT_ID     = int(os.getenv("MY_CHAT_ID", "0"))
BITGET_API  = os.getenv("BITGET_API", "")
BITGET_SEC  = os.getenv("BITGET_SEC", "")
BITGET_PASS = os.getenv("BITGET_PASS", "")
SUPA_URL    = os.getenv("SUPABASE_URL", "")
SUPA_KEY    = os.getenv("SUPABASE_KEY", "")

LEVERAGE       = 5
MARGIN         = 10.0
POS_SIZE       = MARGIN * LEVERAGE   # 50$
COMMISSION     = 0.0006
MAX_OPEN       = 2
MIN_VOL_USDT   = 1_000_000  # Min 1M
MAX_VOL_USDT   = 5_000_000   # Max 5M
MAX_DAILY_LOSS = -10.0
SCAN_INTERVAL  = 60

# Confluence scoring eşiği
SIGNAL_THRESHOLD = 62  # 62+ → giriş yap

# ATR SL çarpanı
ATR_SL_MULTIPLIER    = 1.5   # SL = giriş - 1.5x ATR
ATR_SL_MIN_PCT       = 0.008  # Min SL %0.8
ATR_SL_MAX_PCT       = 0.025  # Max SL %2.5

# Trailing TP
TP_SEVIYELERI  = [0.5, 1.0, 1.5, 2.0, 3.0, 4.0, 5.0, 7.0, 10.0, 15.0]
TP_GERI_DONUS  = 0.40

# Kademeli kar koruma
GERI_CEKILME_PCT = 0.20
GERI_CEKILME_MIN = 0.30

# Balina tespiti
WHALE_VOL_THRESHOLD  = 3.0   # 3x ortalama hacim
WHALE_BOOST          = 8     # Skor +8

# Fear & Greed
FG_CACHE_SURE        = 900   # 15 dakika

BLACKLIST = {
    "BANANAS31","BSB","JCT","MEGA","ALLO","FTM","MU",
    "TURBO","MOODENG","SUNDOG","NEIRO","HMSTR","CATI","DOGS","MYRO",
    "BOME","SLERF","PNUT","ACT","GOAT","RGTI","SATL","WET","POET",
    "SOXL","SOXS","UVXY","SVIX","KORU","AMC","GME","CLOSED",
    "BICO","ARX","BEAT","ID","ALICE","XLM","BTW",
    "SHIB","DOGE","PEPE","FLOKI","BONK","WIF","MEME",
    "1000SHIB","1000DOGE","1000PEPE","1000FLOKI","1000BONK","1000WIF",
}

# ─── STATE ───
positions         = {}
pos_lock          = threading.Lock()
daily_pnl         = 0.0
recently_closed   = {}
closed_lock       = threading.Lock()
son_bakilan       = set()

btc_cache         = {"trend": "NEUTRAL", "price": 0, "chg": 0, "ts": 0}
btc_cache_lock    = threading.Lock()
BTC_CACHE_SURE    = 300

ticker_cache      = {}
ticker_cache_lock = threading.Lock()
ticker_cache_ts   = 0

fg_cache          = {"value": 50, "label": "Neutral", "ts": 0}
fg_cache_lock     = threading.Lock()

# ─── TELEGRAM ───
bot = telebot.TeleBot(TELE_TOKEN)
def tg(msg):
    try: bot.send_message(CHAT_ID, str(msg)[:4096])
    except Exception as e: log.warning(f"[TG] {e}")

# ─── SUPABASE ───
supa = None
if SUPA_URL and SUPA_KEY:
    try:
        supa = create_client(SUPA_URL, SUPA_KEY)
        log.info("[SUPA] OK")
    except Exception as e:
        log.error(f"[SUPA] {e}")

def save_trade(data):
    if not supa: return
    try: supa.table("gpt_trades").insert(data).execute()
    except Exception as e: log.error(f"[SAVE] {e}")

def load_recently_closed():
    if not supa: return
    try:
        import datetime
        ago = (datetime.datetime.utcnow() - datetime.timedelta(hours=2)).isoformat()
        r = supa.table("gpt_trades").select("symbol,created_at").eq(
            "signal","CLOSED").gte("created_at", ago).execute()
        for d in (r.data or []):
            sym = d["symbol"].replace("_CLOSED","")
            with closed_lock:
                recently_closed[sym] = time.time() - 3600
        log.info(f"[CLOSED] {len(r.data or [])} coin yuklendi")
    except Exception as e:
        log.warning(f"[CLOSED] {e}")

# ─── EXCHANGE ───
exchange = ccxt.bitget({
    "apiKey": BITGET_API, "secret": BITGET_SEC,
    "password": BITGET_PASS, "enableRateLimit": True,
    "options": {"defaultType": "swap"},
})
LAST_API = 0
api_lock = threading.Lock()

def safe_api(func, *args, **kwargs):
    global LAST_API
    for i in range(4):
        try:
            with api_lock:
                w = 0.6 - (time.time() - LAST_API)
                if w > 0: time.sleep(w)
                LAST_API = time.time()
            return func(*args, **kwargs)
        except ccxt.RateLimitExceeded:
            time.sleep(10)
        except Exception as e:
            log.warning(f"[API] {e}")
            time.sleep(2)
    return None

# ─── FEAR & GREED INDEX ───
def get_fear_greed():
    global fg_cache
    with fg_cache_lock:
        if time.time() - fg_cache["ts"] < FG_CACHE_SURE:
            return fg_cache["value"], fg_cache["label"]
    try:
        r = requests.get("https://api.alternative.me/fng/?limit=1", timeout=5)
        data = r.json()["data"][0]
        value = int(data["value"])
        label = data["value_classification"]
        with fg_cache_lock:
            fg_cache = {"value": value, "label": label, "ts": time.time()}
        log.info(f"[FG] Fear&Greed: {value} ({label})")
        return value, label
    except Exception as e:
        log.warning(f"[FG] {e}")
        return 50, "Neutral"

# ─── BTC TREND ───
def _fetch_btc_trend():
    try:
        raw1h  = safe_api(exchange.fetch_ohlcv, "BTC/USDT:USDT", "1h",  limit=100)
        raw15m = safe_api(exchange.fetch_ohlcv, "BTC/USDT:USDT", "15m", limit=50)
        if not raw1h: return "NEUTRAL", 0, 0

        df1h  = pd.DataFrame(raw1h, columns=["t","o","h","l","c","v"])
        price = float(df1h["c"].iloc[-1])

        e9_1h  = float(df1h["c"].ewm(span=9).mean().iloc[-1])
        e20_1h = float(df1h["c"].ewm(span=20).mean().iloc[-1])
        e50_1h = float(df1h["c"].ewm(span=50).mean().iloc[-1])

        chg4h  = (price - float(df1h["c"].iloc[-4]))  / float(df1h["c"].iloc[-4])  * 100
        chg24h = (price - float(df1h["c"].iloc[-24])) / float(df1h["c"].iloc[-24]) * 100

        trend_15m = "FLAT"
        pump_then_dump = False
        chg_15m = 0.0

        if raw15m:
            df15m = pd.DataFrame(raw15m, columns=["t","o","h","l","c","v"])
            e9_15  = df15m["c"].ewm(span=9).mean()
            e20_15 = df15m["c"].ewm(span=20).mean()
            trend_15m = "YUKARI" if float(e9_15.iloc[-1]) > float(e20_15.iloc[-1]) else "ASAGI"
            chg_15m = (price - float(df15m["c"].iloc[-8])) / float(df15m["c"].iloc[-8]) * 100
            son8 = df15m["c"].tail(8).values
            tepe = max(son8)
            tepe_idx = list(son8).index(tepe)
            if 1 <= tepe_idx <= 5:
                if (tepe - son8[0]) / son8[0] > 0.005 and (price - tepe) / tepe < -0.004:
                    pump_then_dump = True

        fiyat_e20_ustu = price > e20_1h
        ema_dizi_asagi = e9_1h < e20_1h

        if chg24h < -2.0: return "DOWN", price, chg24h
        if chg4h < -1.0 and trend_15m == "ASAGI": return "DOWN", price, chg24h
        if ema_dizi_asagi and chg4h < -0.5: return "DOWN", price, chg24h
        if pump_then_dump and chg_15m < -0.3: return "DOWN", price, chg24h

        if chg24h > 2.0: return "UP", price, chg24h
        if chg4h > 1.0 and trend_15m == "YUKARI" and fiyat_e20_ustu: return "UP", price, chg24h
        if e9_1h > e20_1h > e50_1h and chg4h > 0.5: return "UP", price, chg24h

        if chg24h < -1.0 or (chg4h < -0.3 and trend_15m == "ASAGI"):
            return "NEUTRAL_SHORT", price, chg24h
        if chg24h > 1.0 or (chg4h > 0.3 and trend_15m == "YUKARI" and fiyat_e20_ustu):
            return "NEUTRAL_LONG", price, chg24h

        return "NEUTRAL", price, chg24h
    except Exception as e:
        log.warning(f"[BTC_TREND] {e}")
        return "NEUTRAL", 0, 0

def get_btc_trend():
    global btc_cache
    with btc_cache_lock:
        if time.time() - btc_cache["ts"] < BTC_CACHE_SURE:
            return btc_cache["trend"], btc_cache["price"], btc_cache["chg"]
    trend, price, chg = _fetch_btc_trend()
    with btc_cache_lock:
        btc_cache = {"trend": trend, "price": price, "chg": chg, "ts": time.time()}
    log.info(f"[BTC_CACHE] {trend} ${price:,.0f} ({chg:+.1f}%)")
    return trend, price, chg

def get_btc_trend_force():
    global btc_cache
    trend, price, chg = _fetch_btc_trend()
    with btc_cache_lock:
        btc_cache = {"trend": trend, "price": price, "chg": chg, "ts": time.time()}
    return trend, price, chg

# ─── İNDİKATÖRLER ───
def calc_rsi(df, period=14):
    delta = df["c"].diff()
    gain  = delta.clip(lower=0).rolling(period).mean()
    loss  = (-delta.clip(upper=0)).rolling(period).mean()
    rs    = gain / loss.replace(0, 0.001)
    return float((100 - 100 / (1 + rs)).iloc[-1])

def calc_macd(df, fast=12, slow=26, signal=9):
    ema_fast   = df["c"].ewm(span=fast).mean()
    ema_slow   = df["c"].ewm(span=slow).mean()
    macd_line  = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal).mean()
    histogram  = macd_line - signal_line
    return float(macd_line.iloc[-1]), float(signal_line.iloc[-1]), float(histogram.iloc[-1])

def calc_bollinger(df, period=20, std=2.0):
    sma   = df["c"].rolling(period).mean()
    std_v = df["c"].rolling(period).std()
    upper = sma + std * std_v
    lower = sma - std * std_v
    price = float(df["c"].iloc[-1])
    u     = float(upper.iloc[-1])
    l     = float(lower.iloc[-1])
    pct_b = (price - l) / (u - l) if (u - l) > 0 else 0.5
    return pct_b, u, l

def calc_atr(df, period=14):
    high  = df["h"]
    low   = df["l"]
    close = df["c"]
    tr    = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low  - close.shift()).abs()
    ], axis=1).max(axis=1)
    return float(tr.rolling(period).mean().iloc[-1])

def calc_ema_crossover(df, fast=9, slow=21):
    ema_fast = df["c"].ewm(span=fast).mean()
    ema_slow = df["c"].ewm(span=slow).mean()
    fast_now  = float(ema_fast.iloc[-1])
    slow_now  = float(ema_slow.iloc[-1])
    fast_prev = float(ema_fast.iloc[-2])
    slow_prev = float(ema_slow.iloc[-2])
    gap_pct   = (fast_now - slow_now) / slow_now * 100
    crossed_up = fast_prev < slow_prev and fast_now > slow_now
    return fast_now > slow_now, crossed_up, gap_pct

def calc_volume_ratio(df, n=3):
    avg = float(df["v"].rolling(20).mean().iloc[-1])
    son = float(df["v"].tail(n).mean())
    return son / max(avg, 0.001)

# ─── CONFLUENCE SCORING ───
def confluence_score(df1h, df15m, df1m=None):
    """
    Çoklu indikatör confluence skoru (0-100)
    claude-trader'dan adapte edildi
    """
    try:
        score = 50  # Başlangıç nötr

        # ── RSI (ağırlık: 25) ──
        rsi_val = calc_rsi(df1h)
        rsi_15m = calc_rsi(df15m)

        if rsi_val < 35:
            rsi_score = 20  # Aşırı satım → güçlü al
        elif rsi_val < 45:
            rsi_score = 12  # Satım bölgesi → orta al
        elif rsi_val < 55:
            rsi_score = 0   # Nötr
        elif rsi_val < 65:
            rsi_score = -8  # Alım bölgesi → temkinli
        else:
            rsi_score = -20 # Aşırı alım → çok riskli

        # 15m RSI teyidi
        if rsi_15m < 45 and rsi_val < 50:
            rsi_score += 5
        elif rsi_15m > 55 and rsi_val > 50:
            rsi_score -= 5

        score += rsi_score

        # ── MACD (ağırlık: 25) ──
        macd, signal, hist = calc_macd(df1h)
        macd_15m, sig_15m, hist_15m = calc_macd(df15m)

        if hist > 0 and macd > signal:
            macd_score = 15 if hist > abs(macd) * 0.1 else 8
        elif hist < 0 and macd < signal:
            macd_score = -15 if abs(hist) > abs(macd) * 0.1 else -8
        else:
            macd_score = 0

        # 15m MACD teyidi
        if hist_15m > 0 and macd_score > 0:
            macd_score += 5
        elif hist_15m < 0 and macd_score < 0:
            macd_score -= 5

        score += macd_score

        # ── Bollinger Bands (ağırlık: 20) ──
        pct_b, upper, lower = calc_bollinger(df1h)
        pct_b_15m, _, _ = calc_bollinger(df15m)

        if pct_b < 0.15:
            bb_score = 18   # Alt banda çok yakın → güçlü al
        elif pct_b < 0.35:
            bb_score = 10   # Alt bölge → al
        elif pct_b < 0.65:
            bb_score = 0    # Orta → nötr
        elif pct_b < 0.85:
            bb_score = -8   # Üst bölge → temkinli
        else:
            bb_score = -18  # Üst banda çok yakın → riskli

        score += bb_score

        # ── EMA Crossover (ağırlık: 15) ──
        ema_yukari, crossed_up, gap_pct = calc_ema_crossover(df1h)

        if crossed_up:
            ema_score = 15  # Taze crossover → çok güçlü
        elif ema_yukari and gap_pct > 0.3:
            ema_score = 10  # EMA üstünde, güçlü gap
        elif ema_yukari:
            ema_score = 4   # EMA üstünde, küçük gap
        elif gap_pct < -0.3:
            ema_score = -10 # EMA altında, güçlü gap
        else:
            ema_score = -4  # EMA altında

        score += ema_score

        # ── Hacim (ağırlık: 15) ──
        vol_ratio = calc_volume_ratio(df1h)

        if vol_ratio >= 3.0:
            vol_score = 12  # Balina hareketi
        elif vol_ratio >= 2.0:
            vol_score = 8   # Yüksek hacim
        elif vol_ratio >= 1.5:
            vol_score = 4   # Hafif yüksek
        elif vol_ratio < 0.5:
            vol_score = -6  # Çok düşük hacim → güvenilmez
        else:
            vol_score = 0

        score += vol_score

        # ── Trend filtresi (ceza) ──
        ema9   = float(df1h["c"].ewm(span=9).mean().iloc[-1])
        ema21  = float(df1h["c"].ewm(span=21).mean().iloc[-1])
        ema50  = float(df1h["c"].ewm(span=50).mean().iloc[-1])
        price  = float(df1h["c"].iloc[-1])

        if price < ema50:
            score -= 10  # Uzun vadeli trend aşağı
        if ema9 < ema21:
            score -= 5   # Kısa vadeli trend aşağı

        # ── Skoru 0-100 arasına sıkıştır ──
        score = max(0, min(100, score))

        details = {
            "score": round(score),
            "rsi": round(rsi_val, 1),
            "rsi_score": rsi_score,
            "macd_hist": round(hist, 6),
            "macd_score": macd_score,
            "pct_b": round(pct_b, 2),
            "bb_score": bb_score,
            "ema_yukari": ema_yukari,
            "ema_score": ema_score,
            "vol_ratio": round(vol_ratio, 1),
            "vol_score": vol_score,
            "atr": calc_atr(df1h),
        }
        return score, details

    except Exception as e:
        log.warning(f"[SCORE] {e}")
        return 50, {}

# ─── KOİN ANALİZİ ───
def analyze_coin(symbol):
    try:
        r1h  = safe_api(exchange.fetch_ohlcv, symbol, "1h",  limit=60)
        r15m = safe_api(exchange.fetch_ohlcv, symbol, "15m", limit=40)
        r1m  = safe_api(exchange.fetch_ohlcv, symbol, "1m",  limit=20)

        if not r1h or len(r1h) < 30: return None
        if not r15m or len(r15m) < 20: return None

        df1h  = pd.DataFrame(r1h,  columns=["t","o","h","l","c","v"])
        df15m = pd.DataFrame(r15m, columns=["t","o","h","l","c","v"])
        df1m  = pd.DataFrame(r1m,  columns=["t","o","h","l","c","v"]) if r1m else None

        price   = float(df1h["c"].iloc[-1])
        atr     = calc_atr(df1h)
        pct_15m = (price - float(df15m["c"].iloc[-10])) / float(df15m["c"].iloc[-10]) * 100
        pct_1h  = (price - float(df1h["c"].iloc[-2]))   / float(df1h["c"].iloc[-2])   * 100
        pct_4h  = (price - float(df1h["c"].iloc[-5]))   / float(df1h["c"].iloc[-5])   * 100 if len(df1h) >= 5 else 0

        # Son 4h tepesinden uzaklık
        tepe_4h = 0.0
        if len(df1h) >= 5:
            en_yuksek = float(df1h["h"].tail(4).max())
            tepe_4h   = (price - en_yuksek) / en_yuksek * 100

        # Balina tespiti
        vol_ratio_1m = calc_volume_ratio(df1m, 3) if df1m is not None else 1.0
        whale_detected = vol_ratio_1m >= WHALE_VOL_THRESHOLD

        # Confluence skoru
        score, details = confluence_score(df1h, df15m, df1m)

        # Balina boost
        if whale_detected:
            score = min(100, score + WHALE_BOOST)
            details["whale"] = True
            details["vol_ratio_1m"] = round(vol_ratio_1m, 1)
        else:
            details["whale"] = False

        details["price"]    = price
        details["atr"]      = atr
        details["pct_15m"]  = pct_15m
        details["pct_1h"]   = pct_1h
        details["pct_4h"]   = pct_4h
        details["tepe_4h"]  = tepe_4h

        return details

    except Exception as e:
        log.warning(f"[ANALYZE] {symbol}: {e}")
        return None

# ─── KARAR VER ───
def karar_ver(data, btc_trend):
    if not data: return None, ""

    score    = data.get("score", 50)
    pct_15m  = data.get("pct_15m", 0)
    pct_1h   = data.get("pct_1h",  0)
    pct_4h   = data.get("pct_4h",  0)
    tepe_4h  = data.get("tepe_4h", 0)
    rsi      = data.get("rsi", 50)

    # BTC trend filtresi
    if btc_trend in ["DOWN", "NEUTRAL_SHORT", "NEUTRAL"]:
        return None, f"BTC {btc_trend} - bekleniyor"

    # Fear & Greed filtresi
    fg_value, fg_label = get_fear_greed()
    if fg_value <= 15:  # Extreme Fear (cok sert)
        return None, f"Extreme Fear ({fg_value}) - riskli"

    # Geç kalma filtresi
    if pct_15m > 6:
        return None, f"Gec kalindi (+{pct_15m:.1f}%)"

    # Coin trend filtresi
    if pct_1h < -2.0 and pct_4h < -3.0:
        return None, f"Coin dususte: 1h={pct_1h:.1f}% 4h={pct_4h:.1f}%"
    if tepe_4h < -5.0:
        return None, f"Tepeden cok uzak ({tepe_4h:.1f}%)"

    # RSI aşırı alım
    if rsi > 72:
        return None, f"RSI asiri alim ({rsi:.0f})"

    # Confluence skoru kontrolü
    if btc_trend == "UP":
        threshold = SIGNAL_THRESHOLD - 5  # UP'ta biraz daha esnek
    else:  # NEUTRAL_LONG
        threshold = SIGNAL_THRESHOLD

    if score >= threshold:
        whale_txt = " 🐋 BALINA!" if data.get("whale") else ""
        neden = (f"Skor:{score} RSI:{rsi:.0f} BB:{data.get('pct_b',0):.2f} "
                 f"MACD:{'+' if data.get('macd_hist',0)>0 else '-'} "
                 f"EMA:{'↑' if data.get('ema_yukari') else '↓'} "
                 f"Hacim:{data.get('vol_ratio',0):.1f}x{whale_txt}")
        return "LONG", neden

    return None, f"Skor yetersiz ({score}/{threshold})"

# ─── PNL ───
def hesap_pnl(pos, price):
    entry = pos["entry"]
    if pos["signal"] == "LONG":
        pnl_pct = (price - entry) / entry * 100
        pnl     = (price - entry) / entry * POS_SIZE - POS_SIZE * COMMISSION
    else:
        pnl_pct = (entry - price) / entry * 100
        pnl     = (entry - price) / entry * POS_SIZE - POS_SIZE * COMMISSION
    return pnl, pnl_pct

# ─── GİRİŞ KALİTE KONTROLÜ ───
def giris_momentum_ok(symbol, analiz_fiyati):
    try:
        t1 = safe_api(exchange.fetch_ticker, symbol)
        if not t1: return False, "Ticker alinamadi"
        f1 = float(t1["last"])
        time.sleep(4)
        t2 = safe_api(exchange.fetch_ticker, symbol)
        if not t2: return False, "Ticker2 alinamadi"
        f2 = float(t2["last"])
        tick = (f2 - f1) / f1 * 100

        if tick < -0.15:
            return False, f"Asagi gidiyor! {tick:.2f}%"

        # Son 5 mum kontrolü
        r1m = safe_api(exchange.fetch_ohlcv, symbol, "1m", limit=7)
        if r1m and len(r1m) >= 5:
            son5    = r1m[-5:]
            kirmizi = sum(1 for m in son5 if m[4] < m[1])
            if kirmizi >= 4:
                return False, f"Son 5 mumun {kirmizi}u kirmizi"

        slippage = abs(f2 - analiz_fiyati) / analiz_fiyati * 100
        if slippage > 0.3:
            return False, f"Slippage yuksek: %{slippage:.2f}"

        return True, f"OK tick:{tick:+.2f}%"
    except Exception as e:
        return False, str(e)

# ─── İŞLEM AÇ ───
def calc_amount(symbol, entry_price, sl_price):
    """Risk bazlı pozisyon büyüklüğü hesapla"""
    try:
        market = exchange.market(symbol)
        contract_size = market.get("contractSize") or 1
        risk_dist = abs(entry_price - sl_price)
        if risk_dist <= 0: return round(POS_SIZE / entry_price, 4)
        # Risk bazlı miktar
        amt_risk   = (MARGIN * 0.5) / (risk_dist * contract_size)
        # Marjin bazlı miktar
        amt_margin = POS_SIZE / entry_price
        amount = min(amt_risk, amt_margin)
        amount = float(exchange.amount_to_precision(symbol, amount))
        return max(amount, 0)
    except:
        return round(POS_SIZE / entry_price, 4)

def place_sl_order(symbol, amount, sl_price):
    """Borsaya gerçek stop loss emri gönder"""
    try:
        params = {
            "stopPrice": exchange.price_to_precision(symbol, sl_price),
            "reduceOnly": True,
            "triggerType": "mark_price",
        }
        order = safe_api(exchange.create_order, symbol, "market", "sell", amount, None, params)
        return order.get("id") if order else None
    except Exception as e:
        log.warning(f"[SL_EMIR] {symbol}: {e}")
        return None

def place_tp_order(symbol, amount, tp_price):
    """Borsaya gerçek take profit emri gönder"""
    try:
        params = {
            "stopPrice": exchange.price_to_precision(symbol, tp_price),
            "reduceOnly": True,
            "triggerType": "mark_price",
        }
        order = safe_api(exchange.create_order, symbol, "market", "sell", amount, None, params)
        return order.get("id") if order else None
    except Exception as e:
        log.warning(f"[TP_EMIR] {symbol}: {e}")
        return None

def cancel_order_safe(order_id, symbol):
    """Bekleyen emri iptal et"""
    if not order_id: return
    try:
        safe_api(exchange.cancel_order, order_id, symbol)
        log.info(f"[IPTAL] {symbol.split('/')[0]} emir {order_id} iptal edildi")
    except Exception as e:
        log.warning(f"[IPTAL] {symbol}: {e}")

def open_pos(symbol, yon, neden, btc_trend, atr=None):
    global daily_pnl
    if daily_pnl <= MAX_DAILY_LOSS: return False
    if yon == "SHORT": return False
    if btc_trend in ["DOWN", "NEUTRAL_SHORT", "NEUTRAL"]: return False

    t0 = safe_api(exchange.fetch_ticker, symbol)
    if not t0: return False
    analiz_fiyati = float(t0["last"])

    sym = symbol.split("/")[0]
    ok, neden_m = giris_momentum_ok(symbol, analiz_fiyati)
    if not ok:
        log.info(f"[MOMENTUM] {sym} reddedildi: {neden_m}")
        return False

    t2 = safe_api(exchange.fetch_ticker, symbol)
    if not t2: return False
    price = float(t2["last"])

    # ATR tabanlı SL
    if atr and atr > 0:
        sl_dist  = atr * ATR_SL_MULTIPLIER
        sl_dist  = max(sl_dist, price * ATR_SL_MIN_PCT)
        sl_dist  = min(sl_dist, price * ATR_SL_MAX_PCT)
        sl_price = price - sl_dist
    else:
        sl_price = price * (1 - 0.015)

    with pos_lock:
        sym_base = symbol.split("/")[0].upper()
        for ex in positions:
            if ex.split("/")[0].upper() == sym_base: return False
        with closed_lock:
            if sym_base in recently_closed:
                if time.time() - recently_closed[sym_base] < 7200: return False
        if len(positions) >= MAX_OPEN: return False

        positions[symbol] = {
            "signal":      "LONG",
            "entry":       price,
            "sl_price":    sl_price,
            "atr":         atr or 0,
            "sl_garantili": 0.0,
            "max_pnl":     0.0,
            "max_kar":     0.0,
            "neden":       neden,
            "btc_trend":   btc_trend,
            "open_time":   time.time(),
            "tp_seviye":   0,
            "tp_sl_price": 0.0,
            "son_tepe":    price,
            "amount":      0,
            "notional":    0,
            "tp_price":    0,
            "sl_order_id": None,
            "tp_order_id": None,
        }

    try:
        try: exchange.set_margin_mode("isolated", symbol)
        except: pass
        try: exchange.set_leverage(LEVERAGE, symbol)
        except: pass

        # Miktar hesapla
        amount = calc_amount(symbol, price, sl_price)
        if amount <= 0:
            with pos_lock: positions.pop(symbol, None)
            return False

        # Giriş emri
        order = exchange.create_order(symbol, "market", "buy", amount,
                                      params={"marginMode": "isolated"})
        if not order:
            with pos_lock: positions.pop(symbol, None)
            return False
        log.info(f"[EMIR] {sym} LONG id={order.get('id','?')} amount={amount}")

        # Gerçek TP fiyatı (ATR x 1.8)
        tp_price = price + (atr * 1.8) if atr else price * 1.015

        # Borsaya SL/TP emirleri gönder
        sl_order_id = place_sl_order(symbol, amount, sl_price)
        tp_order_id = place_tp_order(symbol, amount, tp_price)

        # Pozisyona SL/TP emir ID'lerini ekle
        with pos_lock:
            if symbol in positions:
                positions[symbol]["amount"]      = amount
                positions[symbol]["notional"]    = amount * price
                positions[symbol]["tp_price"]    = tp_price
                positions[symbol]["sl_order_id"] = sl_order_id
                positions[symbol]["tp_order_id"] = tp_order_id

    except Exception as e:
        log.error(f"[EMIR HATA] {sym}: {e}")
        with pos_lock: positions.pop(symbol, None)
        return False

    sl_pct = (price - sl_price) / price * 100
    tp_pct = (tp_price - price) / price * 100
    tg(f"📋 📈 {sym} LONG\nGiris: {price:.6f}\nSL: {sl_price:.6f} (-%{sl_pct:.1f})\nTP: {tp_price:.6f} (+%{tp_pct:.1f})\nBTC: {btc_trend}\n💬 {neden}")
    return True

# ─── İŞLEM KAPAT ───
def close_pos(symbol, reason, exit_price=None):
    global daily_pnl
    with pos_lock:
        pos = positions.pop(symbol, None)
    if not pos: return

    # Bekleyen SL/TP emirlerini iptal et
    cancel_order_safe(pos.get("sl_order_id"), symbol)
    cancel_order_safe(pos.get("tp_order_id"), symbol)

    try:
        amount = pos.get("amount", None)
        if not amount:
            try:
                tum_pos = safe_api(exchange.fetch_positions, [symbol])
                if tum_pos:
                    for p in tum_pos:
                        if p.get("symbol") == symbol and float(p.get("contracts") or 0) > 0:
                            amount = float(p["contracts"]); break
            except: pass
        if not amount: amount = round(POS_SIZE / pos["entry"], 4)
        safe_api(exchange.create_order, symbol, "market", "sell", amount, None,
                 {"reduceOnly": True})
    except Exception as e:
        if "22002" in str(e) or "No position" in str(e):
            log.info(f"[KAPAT] {symbol.split('/')[0]}: Borsada pozisyon yok")
        else:
            log.error(f"[KAPAT] {symbol.split('/')[0]}: {e}")

    if exit_price is None:
        t = safe_api(exchange.fetch_ticker, symbol)
        exit_price = t["last"] if t else pos["entry"]

    pnl, _ = hesap_pnl(pos, exit_price)
    sure    = int((time.time() - pos["open_time"]) / 60)
    daily_pnl += pnl

    sym_base = symbol.split("/")[0].upper()
    with closed_lock: recently_closed[sym_base] = time.time()

    try:
        save_trade({"symbol": symbol, "signal": "LONG",
                    "pnl": round(pnl, 4), "btc_trend": pos.get("btc_trend",""),
                    "sure_dk": sure, "reason": reason, "neden": pos.get("neden","")})
        save_trade({"symbol": sym_base+"_CLOSED", "signal": "CLOSED",
                    "pnl": 0, "reason": "recently_closed", "sure_dk": 0})
    except: pass

    if daily_pnl <= MAX_DAILY_LOSS:
        tg(f"⛔ GUNLUK LIMIT! {daily_pnl:+.2f}$")

    icon = "🟢" if pnl >= 0 else "🔴"
    tg(f"{icon} {symbol.split('/')[0]} KAPANDI\n{reason}\nPnL: {pnl:+.2f}$ | {sure}dk\nGunluk: {daily_pnl:+.2f}$")

# ─── YÖNETİM ───
def manage_loop():
    while True:
        time.sleep(30)
        try:
            with pos_lock: syms = list(positions.keys())
            if not syms: continue

            for symbol in syms:
                with pos_lock:
                    pos = positions.get(symbol)
                if not pos: continue

                t = safe_api(exchange.fetch_ticker, symbol)
                if not t: continue
                price        = t["last"]
                pnl, pnl_pct = hesap_pnl(pos, price)
                sure         = int((time.time() - pos["open_time"]) / 60)

                with pos_lock:
                    if symbol in positions:
                        if pnl > positions[symbol]["max_kar"]:
                            positions[symbol]["max_kar"] = pnl
                        if pnl_pct > positions[symbol]["max_pnl"]:
                            positions[symbol]["max_pnl"] = pnl_pct

                max_kar      = pos["max_kar"]
                tp_seviye    = pos.get("tp_seviye", 0)
                tp_sl_price  = pos.get("tp_sl_price", 0.0)
                entry        = pos["entry"]
                son_tepe     = pos.get("son_tepe", entry)

                # Erken zarar çıkışı (ilk 10dk)
                if sure <= 10 and pnl_pct <= -0.8:
                    close_pos(symbol, f"Erken zarar ({pnl_pct:.1f}%)", price)
                    continue

                # Son tepeyi güncelle
                if price > son_tepe:
                    with pos_lock:
                        if symbol in positions:
                            positions[symbol]["son_tepe"] = price

                # Trailing TP
                pct_from_entry = (price - entry) / entry * 100

                if tp_seviye < len(TP_SEVIYELERI):
                    hedef = TP_SEVIYELERI[tp_seviye]
                    if pct_from_entry >= hedef:
                        yeni_sl = entry if tp_seviye == 0 else entry * (1 + TP_SEVIYELERI[tp_seviye-1]/100)
                        with pos_lock:
                            if symbol in positions:
                                positions[symbol]["tp_seviye"]   = tp_seviye + 1
                                positions[symbol]["tp_sl_price"] = yeni_sl
                                positions[symbol]["son_tepe"]    = price
                        sym = symbol.split("/")[0]
                        sonraki = f"%{TP_SEVIYELERI[tp_seviye+1]}" if tp_seviye+1 < len(TP_SEVIYELERI) else "∞"
                        tg(f"🎯 {sym} TP{tp_seviye+1} HIT! +{pct_from_entry:.1f}%\n"
                           f"SL girise cizildi: {yeni_sl:.6f}\n"
                           f"Sonraki: {sonraki}\nSermaye icerde 🚀")

                # TP sonrası trailing stop
                if tp_seviye > 0:
                    tepe  = pos.get("son_tepe", price)
                    geri  = (tepe - price) / tepe * 100
                    if geri >= TP_GERI_DONUS:
                        close_pos(symbol, f"Trailing stop (tepeden -%{geri:.1f})", price)
                        continue
                    if tp_sl_price > 0 and price <= tp_sl_price:
                        close_pos(symbol, f"TP SL ({tp_sl_price:.6f})", price)
                        continue

                # Normal SL (TP yoksa) — ATR bazlı
                if tp_seviye == 0:
                    sl_p = pos.get("sl_price", 0)
                    if sl_p > 0 and price <= sl_p:
                        close_pos(symbol, f"Stop Loss ATR ({sl_p:.6f})", price)
                        continue
                    if pnl_pct <= -2.5:  # Güvenlik ağı
                        close_pos(symbol, "Stop Loss guvence -%2.5", price)
                        continue

                # Kademeli kar koruma (yedek, TP yoksa)
                if tp_seviye == 0 and max_kar >= GERI_CEKILME_MIN:
                    limit = max_kar * GERI_CEKILME_PCT
                    if (max_kar - pnl) >= limit and pnl > 0:
                        close_pos(symbol, f"Geri cekilme %{GERI_CEKILME_PCT*100:.0f}", price)
                        continue

                # Zaman aşımı 4 saat
                if sure >= 240:
                    close_pos(symbol, "Zaman asimi 4 saat", price)
                    continue

                # BTC trend değişti
                btc_now, _, _ = get_btc_trend_force()
                if btc_now == "DOWN" and pnl > 0:
                    close_pos(symbol, "BTC DOWN - kar al", price)
                    continue

        except Exception as e:
            log.error(f"[MANAGE] {e}")

# ─── TARAYICI ───
def scanner_loop():
    global son_bakilan, ticker_cache, ticker_cache_ts
    time.sleep(60)
    while True:
        try:
            if daily_pnl <= MAX_DAILY_LOSS:
                time.sleep(SCAN_INTERVAL); continue

            btc_trend, btc_price, btc_chg = get_btc_trend()
            log.info(f"[SCAN] BTC:{btc_trend} ${btc_price:,.0f} ({btc_chg:+.1f}%)")

            if btc_trend in ["NEUTRAL", "DOWN", "NEUTRAL_SHORT"]:
                log.info(f"[SCAN] BTC {btc_trend} - bekleniyor")
                time.sleep(SCAN_INTERVAL); continue

            # Fear & Greed kontrolü
            fg_val, fg_lbl = get_fear_greed()
            if fg_val <= 20:
                log.info(f"[SCAN] Extreme Fear ({fg_val}) - bekleniyor")
                time.sleep(SCAN_INTERVAL); continue

            with pos_lock:
                if len(positions) >= MAX_OPEN:
                    time.sleep(30); continue
                open_syms = set(positions.keys())

            tickers = safe_api(exchange.fetch_tickers)
            if not tickers:
                time.sleep(SCAN_INTERVAL); continue

            with ticker_cache_lock:
                ticker_cache    = tickers
                ticker_cache_ts = time.time()

            candidates = []
            for symbol, ticker in tickers.items():
                if not symbol.endswith("/USDT:USDT"): continue
                sym = symbol.split("/")[0]
                if sym in BLACKLIST: continue
                if symbol in open_syms: continue
                if sym in son_bakilan: continue

                qv    = ticker.get("quoteVolume") or 0
                pct   = ticker.get("percentage")  or 0
                price = float(ticker.get("last") or 0)
                if qv < MIN_VOL_USDT or qv > MAX_VOL_USDT: continue
                if price <= 0 or price > 50.0: continue

                if btc_trend == "UP"           and pct < 1.5: continue
                if btc_trend == "NEUTRAL_LONG" and pct < 1.0: continue
                if abs(pct) > 50: continue

                sym_base = sym.upper()
                with closed_lock:
                    if sym_base in recently_closed:
                        if time.time() - recently_closed[sym_base] < 7200: continue

                candidates.append({"symbol": symbol, "pct": pct, "qv": qv})

            import random
            yeni = [c for c in candidates if c["symbol"].split("/")[0] not in son_bakilan]
            if len(yeni) < 3:
                son_bakilan = set()
                yeni = candidates
            random.shuffle(yeni)
            candidates = yeni[:6]

            for c in candidates:
                son_bakilan.add(c["symbol"].split("/")[0])
            if len(son_bakilan) > 30:
                son_bakilan = set(list(son_bakilan)[-15:])

            if not candidates:
                time.sleep(SCAN_INTERVAL); continue

            log.info(f"[SCAN] {len(candidates)} aday | BTC:{btc_trend} FG:{fg_val}({fg_lbl})")

            for c in candidates:
                symbol = c["symbol"]
                sym    = symbol.split("/")[0]
                with pos_lock:
                    if len(positions) >= MAX_OPEN: break
                    if symbol in open_syms: continue

                data = analyze_coin(symbol)
                if not data: continue

                yon, neden = karar_ver(data, btc_trend)
                if yon:
                    open_pos(symbol, yon, neden, btc_trend, atr=data.get("atr"))
                    with pos_lock: open_syms = set(positions.keys())
                else:
                    log.info(f"[PAS] {sym}: {neden}")
                time.sleep(1)

            time.sleep(SCAN_INTERVAL)

        except Exception as e:
            log.error(f"[SCANNER] {e}")
            time.sleep(10)

# ─── GÜNLÜK SIFIRLAMA ───
def gunluk_reset_loop():
    global daily_pnl
    import datetime
    while True:
        try:
            simdi = datetime.datetime.now()
            yarin = (simdi + datetime.timedelta(days=1)).replace(
                     hour=0, minute=0, second=5, microsecond=0)
            bekle = (yarin - simdi).total_seconds()
            log.info(f"[RESET] {bekle/3600:.1f} saat sonra")
            time.sleep(bekle)
            eski = daily_pnl; daily_pnl = 0.0
            tg(f"🔄 Yeni gun! Dun: {eski:+.2f}$")
        except Exception as e:
            log.error(f"[RESET] {e}"); time.sleep(3600)

# ─── AÇIK POZİSYON YÜKLE ───
def load_open_positions():
    try:
        log.info("[YUKLE] Kontrol ediliyor...")
        raw = safe_api(exchange.fetch_positions)
        if not raw: log.info("[YUKLE] Yok"); return
        btc_trend, _, _ = get_btc_trend()
        yuklenen = 0
        for pos in raw:
            try:
                if float(pos.get("contracts") or 0) == 0: continue
                symbol = pos.get("symbol","")
                side   = pos.get("side","")
                entry  = float(pos.get("entryPrice") or 0)
                if not symbol or not side or entry == 0: continue
                yon = "LONG" if side == "long" else "SHORT"
                sl_price = entry * (1 - 0.015)
                with pos_lock:
                    if symbol not in positions:
                        positions[symbol] = {
                            "signal": yon, "entry": entry, "sl_price": sl_price,
                            "atr": 0, "sl_garantili": 0.0, "max_pnl": 0.0, "max_kar": 0.0,
                            "neden": "Onceki oturumdan", "btc_trend": btc_trend,
                            "open_time": time.time(), "tp_seviye": 0,
                            "tp_sl_price": 0.0, "son_tepe": entry,
                        }
                        yuklenen += 1
                        log.info(f"[YUKLE] {symbol.split('/')[0]} {yon} @ {entry}")
            except Exception as e:
                log.warning(f"[YUKLE] {e}")

        if yuklenen > 0:
            with pos_lock:
                lines = [f"♻️ {yuklenen} pozisyon yuklendi:\n"]
                for sym, p in positions.items():
                    t = safe_api(exchange.fetch_ticker, sym)
                    f = t["last"] if t else p["entry"]
                    pnl, _ = hesap_pnl(p, f)
                    lines.append(f"{'🟢' if pnl>=0 else '🔴'} {sym.split('/')[0]} | {pnl:+.2f}$")
            tg("\n".join(lines))
    except Exception as e:
        log.error(f"[YUKLE] {e}")

# ─── HEALTH ───
def health_server():
    from http.server import HTTPServer, BaseHTTPRequestHandler
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200); self.end_headers()
            fg, _ = get_fear_greed()
            with pos_lock:
                pstr = ",".join(f"{s.split('/')[0]}:{p['signal']}" for s,p in positions.items())
            self.wfile.write(
                f"OK|btc:{get_btc_trend()[0]}|fg:{fg}|pos:{len(positions)}({pstr})|pnl:{daily_pnl:+.2f}".encode()
            )
        def log_message(self, *a): pass
    HTTPServer(("0.0.0.0", 8080), H).serve_forever()

# ─── COIN BUL ───
def find_coin(text):
    words = re.findall(r'[A-Z0-9]+', text.upper())
    try:
        tickers = safe_api(exchange.fetch_tickers)
        if not tickers: return None
        for word in words:
            if len(word) < 3: continue
            sym = f"{word}/USDT:USDT"
            if sym in tickers and word not in BLACKLIST:
                return sym
    except: pass
    return None

# ─── TELEGRAM HANDLER ───
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
                bot.send_message(msg.chat.id, "📋 Acik pozisyon yok."); return
            lines = ["📋 POZISYONLAR\n"]
            for sym, pos in positions.items():
                t = safe_api(exchange.fetch_ticker, sym)
                if not t: continue
                price = t["last"]
                pnl, pnl_pct = hesap_pnl(pos, price)
                sure = int((time.time() - pos["open_time"]) / 60)
                tp   = pos.get("tp_seviye", 0)
                sl   = pos.get("sl_price", 0)
                lines.append(
                    f"{'🟢' if pnl>=0 else '🔴'} 📈 {sym.split('/')[0]} LONG\n"
                    f"   {pos['entry']:.6f} → {price:.6f}\n"
                    f"   PnL: {pnl:+.2f}$ ({pnl_pct:+.2f}%) | {sure}dk\n"
                    f"   SL: {sl:.6f} | TP seviye: {tp}\n"
                )
            bot.send_message(msg.chat.id, "\n".join(lines))
        return

    if "/istatistik" in lower:
        if not supa:
            bot.send_message(msg.chat.id, "Supabase yok."); return
        try:
            r    = supa.table("gpt_trades").select("pnl,signal").execute()
            data = [d for d in (r.data or []) if d.get("signal") not in ["CLOSED"]]
            if not data: bot.send_message(msg.chat.id, "Kayit yok."); return
            toplam = len(data)
            kazan  = sum(1 for d in data if float(d.get("pnl") or 0) > 0)
            net    = sum(float(d.get("pnl") or 0) for d in data)
            bot.send_message(msg.chat.id,
                f"📊 ISTATISTIK\nToplam: {toplam} | Kazanan: {kazan} (%{kazan/toplam*100:.0f})\n"
                f"Net: {net:+.2f}$\nGunluk: {daily_pnl:+.2f}$")
        except Exception as e:
            bot.send_message(msg.chat.id, f"Hata: {e}")
        return

    if "/btc" in lower:
        trend, price, chg = get_btc_trend()
        fg, fl = get_fear_greed()
        aciklama = {
            "UP":            "⬆️ Guclu yukari → LONG acar",
            "DOWN":          "⬇️ Guclu asagi  → BEKLER",
            "NEUTRAL_LONG":  "↗️ Hafif yukari → LONG acar",
            "NEUTRAL_SHORT": "↘️ Hafif asagi  → BEKLER",
            "NEUTRAL":       "↔️ Belirsiz     → BEKLER",
        }.get(trend, "")
        bot.send_message(msg.chat.id,
            f"BTC: {trend}\n${price:,.0f} ({chg:+.1f}%)\n{aciklama}\n\nFear&Greed: {fg} ({fl})")
        return

    if "kapat" in lower:
        with pos_lock: syms = list(positions.keys())
        if not syms:
            bot.send_message(msg.chat.id, "Acik pozisyon yok."); return
        kapatildi = False
        for symbol in syms:
            if symbol.split("/")[0].upper() in text.upper() or "hepsi" in lower:
                close_pos(symbol, "Kullanici istegi")
                kapatildi = True
        if not kapatildi:
            bot.send_message(msg.chat.id, f"Hangisini? {', '.join(s.split('/')[0] for s in syms)}")
        return

    if any(k in lower for k in ["long ac", "long aç"]):
        coin = find_coin(text)
        if coin:
            trend, _, _ = get_btc_trend()
            data = analyze_coin(coin)
            atr  = data.get("atr") if data else None
            if not open_pos(coin, "LONG", "Kullanici istegi", trend, atr=atr):
                bot.send_message(msg.chat.id, f"{coin.split('/')[0]} acilamadi.")
        else:
            bot.send_message(msg.chat.id, "Coin bulunamadi.")
        return

    coin = find_coin(text)
    if coin:
        sym = coin.split("/")[0]
        bot.send_message(msg.chat.id, f"{sym} analiz ediliyor...")
        data = analyze_coin(coin)
        if data:
            trend, _, _ = get_btc_trend()
            yon, neden  = karar_ver(data, trend)
            fg, fl = get_fear_greed()
            bot.send_message(msg.chat.id,
                f"📊 {sym} | Skor: {data.get('score',0)}/100\n"
                f"RSI: {data.get('rsi',0):.0f} | BB: {data.get('pct_b',0):.2f}\n"
                f"MACD: {'+ yukari' if data.get('macd_hist',0)>0 else '- asagi'}\n"
                f"EMA: {'↑ yukari' if data.get('ema_yukari') else '↓ asagi'}\n"
                f"Hacim: {data.get('vol_ratio',0):.1f}x {'🐋' if data.get('whale') else ''}\n"
                f"ATR SL: -%{data.get('atr',0)/data.get('price',1)*100:.1f}\n"
                f"BTC: {trend} | FG: {fg}({fl})\n\n"
                f"Karar: {yon or 'PAS'}\n{neden}")
        else:
            bot.send_message(msg.chat.id, f"{sym} veri alinamadi.")
        return

    bot.send_message(msg.chat.id,
        "Komutlar:\n/durum\n/istatistik\n/btc\nCOIN - analiz\nCOIN long ac\nhepsini kapat")

# ─── SHUTDOWN ───
import signal as sig_mod, sys

def shutdown(signum, frame):
    with pos_lock: syms = list(positions.keys())
    if syms:
        isimler = ", ".join(s.split("/")[0] for s in syms)
        tg(f"⏸ Bot yeniden basliyor...\n{len(syms)} pozisyon acik: {isimler}\n♻️ Basladiginda yuklenecek.")
    sys.exit(0)

sig_mod.signal(sig_mod.SIGTERM, shutdown)
sig_mod.signal(sig_mod.SIGINT,  shutdown)

# ─── MAIN ───
if __name__ == "__main__":
    print("SADIK TRADER v5 BASLIYOR...")
    load_recently_closed()
    load_open_positions()
    threading.Thread(target=health_server,     daemon=True).start()
    threading.Thread(target=manage_loop,       daemon=True).start()
    threading.Thread(target=scanner_loop,      daemon=True).start()
    threading.Thread(target=gunluk_reset_loop, daemon=True).start()
    fg, fl = get_fear_greed()
    tg(
        "🤖 SADIK TRADER v5 — CONFLUENCE SCORING\n\n"
        "📊 İndikatörler:\n"
        "  RSI (14) — %25 ağırlık\n"
        "  MACD (12/26/9) — %25 ağırlık\n"
        "  Bollinger Bands — %20 ağırlık\n"
        "  EMA Crossover (9/21) — %15 ağırlık\n"
        "  Hacim — %15 ağırlık\n\n"
        f"✅ Skor >= {SIGNAL_THRESHOLD} → LONG gir\n"
        "✅ ATR tabanlı SL (volatiliteye göre)\n"
        "✅ Balina tespiti (3x hacim +8 skor)\n"
        f"✅ Fear&Greed: {fg} ({fl})\n"
        "✅ Trailing TP (sınırsız)\n\n"
        "/durum /istatistik /btc"
    )
    while True:
        try: bot.infinity_polling(timeout=30, long_polling_timeout=30)
        except Exception as e:
            log.error(f"[BOT] {e}"); time.sleep(5)
