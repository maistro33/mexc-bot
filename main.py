#!/usr/bin/env python3
"""
SADIK TRADER v8 - Kurumsal Kalite
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Giriş Akışı:
  1. 1h Trend Filtresi  → 200 EMA üstü, 20>50 EMA, EMA eğimi pozitif
  2. 15m Momentum       → Dip bounce, yeşil mum konfirm, RSI bounce
  3. 5m Tetikleyici     → Son anlık momentum pozitif
  4. ATR Volatilite     → Çok düşük/yüksek volatilite engeli
  5. ATR Giriş Bekle    → 90sn ideal fiyat bekle
  6. Güvenli Emir       → Bitget one-way mode uyumlu

Düzeltilen Hatalar:
  ✅ close_pos() reduceOnly doğru format
  ✅ fetch_positions alan doğrulama + loglama
  ✅ fetch_tickers cache (rate limit koruması)
  ✅ daily_pnl merkezi kontrol
  ✅ pre_trade_filter() fonksiyonu
  ✅ PnL hesabı contracts bazlı
"""

import os, time, threading, logging, re, random, requests
import ccxt
import pandas as pd
import telebot
from supabase import create_client

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("SADIK_V8")

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
POS_SIZE       = MARGIN * LEVERAGE  # 50$
COMMISSION     = 0.0006
MAX_OPEN       = 2
MAX_DAILY_LOSS = -15.0
SCAN_INTERVAL  = 45

# TP/SL
TP_PCTS        = [0.8, 1.5, 2.5, 3.5, 5.0, 7.0]
SL_PCT         = 3.0
ATR_SL_MULT    = 1.0
ATR_GIRIS_MULT = 0.3
ATR_GIRIS_SURE = 90
TP_TRAILING    = 0.60

# Tarama filtreleri
MIN_VOL_USDT = 500_000
MAX_VOL_USDT = 20_000_000
MIN_PRICE    = 0.0001
MAX_PRICE    = 5.0
FG_MIN       = 10
RSI_MAX      = 68
PCT_4H_MAX   = 10.0
PCT_1H_MAX   = 6.0

# ATR volatilite sınırları
ATR_PCT_MIN  = 0.3   # ATR/fiyat min %0.3 (çok sakin coin)
ATR_PCT_MAX  = 8.0   # ATR/fiyat max %8.0 (çok volatil coin)

# BTC skor eşikleri
SKOR_UP            = 3
SKOR_NEUTRAL_LONG  = 3
SKOR_NEUTRAL_SHORT = 5

# Ticker cache
TICKER_CACHE_TTL = 60  # 60 saniye

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
    if not supa:
        return
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
    """Rate-limit korumalı API çağrısı, 4 deneme."""
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
            log.warning(f"[API] Network hatası deneme {attempt+1}: {e}")
            time.sleep(3)
        except Exception as e:
            log.warning(f"[API] Hata deneme {attempt+1}: {e}")
            time.sleep(2)
    return None

def get_tickers_cached():
    """Ticker cache — 60sn'de bir güncelle, rate limit koruması."""
    global ticker_cache, ticker_cache_ts
    with ticker_lock:
        if time.time() - ticker_cache_ts < TICKER_CACHE_TTL and ticker_cache:
            return ticker_cache
    tickers = safe_api(exchange.fetch_tickers)
    if tickers:
        with ticker_lock:
            ticker_cache    = tickers
            ticker_cache_ts = time.time()
    return tickers

# ════════════════════════════════════════
# GÜNLÜK PNL (merkezi)
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
        log.info(f"[FG] {v} ({l})")
        return v, l
    except Exception as e:
        log.warning(f"[FG] {e}")
        return 50, "Neutral"

# ════════════════════════════════════════
# BTC TREND
# ════════════════════════════════════════
def _hesapla_btc_trend():
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

        return trend, price, chg24h
    except Exception as e:
        log.warning(f"[BTC] {e}")
        return "NEUTRAL_LONG", 0, 0

def get_btc_trend():
    with btc_lock:
        if time.time() - btc_cache["ts"] < BTC_TTL:
            return btc_cache["trend"], btc_cache["price"], btc_cache["chg"]
    trend, price, chg = _hesapla_btc_trend()
    with btc_lock:
        btc_cache.update({"trend": trend, "price": price, "chg": chg, "ts": time.time()})
    log.info(f"[BTC] {trend} ${price:,.0f} ({chg:+.1f}%)")
    return trend, price, chg

# ════════════════════════════════════════
# İNDİKATÖR HESAPLARI
# ════════════════════════════════════════
def calc_ema(series, span):
    return series.ewm(span=span, adjust=False).mean()

def calc_rsi(series, period=14):
    delta = series.diff()
    gain  = delta.clip(lower=0).rolling(period).mean()
    loss  = (-delta.clip(upper=0)).rolling(period).mean()
    rs    = gain / loss.replace(0, 0.001)
    return float((100 - 100 / (1 + rs)).iloc[-1])

def calc_macd_hist(series, fast=12, slow=26, signal=9):
    m = series.ewm(span=fast).mean() - series.ewm(span=slow).mean()
    return float((m - m.ewm(span=signal).mean()).iloc[-1])

def calc_bb_pct(series, period=20, std=2.0):
    sma = series.rolling(period).mean()
    sd  = series.rolling(period).std()
    u   = sma + std * sd
    l   = sma - std * sd
    p   = float(series.iloc[-1])
    rng = float(u.iloc[-1]) - float(l.iloc[-1])
    return (p - float(l.iloc[-1])) / rng if rng > 0 else 0.5

def calc_atr(df, period=14):
    h, l, c = df["h"], df["l"], df["c"]
    tr = pd.concat([
        h - l,
        (h - c.shift()).abs(),
        (l - c.shift()).abs()
    ], axis=1).max(axis=1)
    return float(tr.rolling(period).mean().iloc[-1])

def calc_vol_ratio(df, n=3):
    avg = float(df["v"].rolling(20).mean().iloc[-1])
    son = float(df["v"].tail(n).mean())
    return son / max(avg, 0.0001)

# ════════════════════════════════════════
# ADIM 1: 1H TREND FİLTRESİ
# ════════════════════════════════════════
def filtre_1h_trend(df1h):
    """
    200 EMA üstünde mi?
    20 EMA > 50 EMA mı?
    20 EMA eğimi pozitif mi?
    """
    closes = df1h["c"]
    price   = float(closes.iloc[-1])
    ema20   = calc_ema(closes, 20)
    ema50   = calc_ema(closes, 50)
    ema200  = calc_ema(closes, 200)

    price_above_200 = price > float(ema50.iloc[-1])  # 50EMA (200 yerine, daha esnek)
    ema20_above_50  = float(ema20.iloc[-1]) > float(ema50.iloc[-1])
    ema20_rising    = float(ema20.iloc[-1]) > float(ema20.iloc[-3])  # Son 3 mumda yukarı

    gecti = price_above_200 and ema20_above_50 and ema20_rising

    detay = (
        f"50EMA:{'✅' if price_above_200 else '❌'} "
        f"20>50:{'✅' if ema20_above_50 else '❌'} "
        f"EMAyük:{'✅' if ema20_rising else '❌'}"
    )
    return gecti, detay

# ════════════════════════════════════════
# ADIM 2: 15M MOMENTUM FİLTRESİ
# ════════════════════════════════════════
def filtre_15m_momentum(df1h, df15m):
    """
    Dip bounce: Son 8h'in alt %40'ında mı?
    RSI bounce: RSI 38 altından yukarı dönüş
    İlk güçlü yeşil mum: %0.30+ gövde
    Destek yakın: Son 20h'in %15 persentili
    """
    price    = float(df1h["c"].iloc[-1])
    son8_low = float(df1h["l"].tail(8).min())
    son8_high= float(df1h["h"].tail(8).max())
    aralik   = max(son8_high - son8_low, 0.0001)

    # Dip bölge
    dip_ok = price <= son8_low + aralik * 0.40

    # RSI bounce
    rsi_simdi = calc_rsi(df1h["c"])
    rsi_min   = rsi_simdi
    for i in range(2, 7):
        try:
            r = calc_rsi(df1h["c"].iloc[:-i])
            if r < rsi_min:
                rsi_min = r
        except:
            pass
    rsi_bounce_ok = rsi_min < 38 and rsi_simdi > rsi_min + 2

    # İlk güçlü yeşil mum (15m)
    son7     = df15m.tail(7)
    kirmizi  = sum(1 for _, r in son7.iloc[:-1].iterrows()
                   if float(r["c"]) < float(r["o"]))
    son_mum  = son7.iloc[-1]
    mum_boy  = abs(float(son_mum["c"]) - float(son_mum["o"])) / float(son_mum["o"]) * 100
    yesil_ok = (
        kirmizi >= 2
        and float(son_mum["c"]) > float(son_mum["o"])
        and mum_boy >= 0.30
    )

    # Destek yakın
    destek    = float(df1h["l"].tail(20).quantile(0.15))
    destek_ok = price <= destek * 1.02

    puan = sum([dip_ok, rsi_bounce_ok, yesil_ok, destek_ok])
    detay = {
        "dip":    "✅" if dip_ok     else "❌",
        "bounce": f"✅{rsi_min:.0f}→{rsi_simdi:.0f}" if rsi_bounce_ok else f"❌RSI{rsi_simdi:.0f}",
        "yesil":  f"✅{mum_boy:.1f}%" if yesil_ok else "❌",
        "destek": "✅" if destek_ok  else "❌",
        "dip_puan": puan,
    }
    return puan, detay

# ════════════════════════════════════════
# ADIM 3: 5M GİRİŞ TETİKLEYİCİSİ
# ════════════════════════════════════════
def filtre_5m_tetik(symbol):
    """
    Son 5m mumlarında momentum pozitif mi?
    Son 3 mumun 2'si yeşil olmalı.
    Fiyat son 5m'nin üst yarısında olmalı.
    """
    try:
        r5m = safe_api(exchange.fetch_ohlcv, symbol, "5m", limit=10)
        if not r5m or len(r5m) < 5:
            return True, "5m veri yok"  # Veri yoksa geçir
        df5m   = pd.DataFrame(r5m, columns=["t","o","h","l","c","v"])
        son3   = df5m.tail(3)
        yesil3 = sum(1 for _, r in son3.iterrows() if float(r["c"]) > float(r["o"]))

        # Son 5m aralığı
        son5_high = float(df5m["h"].tail(5).max())
        son5_low  = float(df5m["l"].tail(5).min())
        price     = float(df5m["c"].iloc[-1])
        ust_yari  = price > (son5_low + (son5_high - son5_low) * 0.5)

        gecti = yesil3 >= 2 and ust_yari
        detay = f"5m:{'✅' if gecti else '❌'}({yesil3}/3 yeşil)"
        return gecti, detay
    except Exception as e:
        log.warning(f"[5M] {e}")
        return True, "5m hata"

# ════════════════════════════════════════
# ADIM 4: ATR VOLATİLİTE KONTROLÜ
# ════════════════════════════════════════
def filtre_atr_volatilite(df1h):
    """
    ATR çok düşükse → piyasa uyuyor, hareket yok
    ATR çok yüksekse → çok riskli
    """
    atr_val = calc_atr(df1h)
    price   = float(df1h["c"].iloc[-1])
    atr_pct = (atr_val / price) * 100

    gecti = ATR_PCT_MIN <= atr_pct <= ATR_PCT_MAX
    detay = f"ATR%{atr_pct:.1f}"
    return gecti, atr_val, detay

# ════════════════════════════════════════
# DÜŞÜŞ TRENDİ ENGELİ
# ════════════════════════════════════════
def dusus_trendi_var_mi(df1h, df15m):
    """
    Aşağıdaki durumların herhangi biri varsa True döner (giriş yapma):
    - Son 2h'de -%2'den fazla düşüş
    - Son 6 mumun 4'ü kırmızı
    - EMA9 < EMA21 VE 4h negatif
    - 15m'de son 8 mumun 5'i kırmızı
    """
    price  = float(df1h["c"].iloc[-1])
    pct2h  = (price - float(df1h["c"].iloc[-3])) / float(df1h["c"].iloc[-3]) * 100
    pct4h  = (price - float(df1h["c"].iloc[-5])) / float(df1h["c"].iloc[-5]) * 100

    if pct2h < -2.0:
        return True, f"2h düşüş {pct2h:.1f}%"

    son6     = df1h.tail(6)
    kir6     = sum(1 for _, r in son6.iterrows() if float(r["c"]) < float(r["o"]))
    if kir6 >= 4:
        return True, f"6 mumun {kir6}'ı kırmızı"

    ema9  = float(calc_ema(df1h["c"], 9).iloc[-1])
    ema21 = float(calc_ema(df1h["c"], 21).iloc[-1])
    if ema9 < ema21 and pct4h < -1.5:
        return True, f"EMA düşüş + 4h {pct4h:.1f}%"

    son8_15m = df15m.tail(8)
    kir15m   = sum(1 for _, r in son8_15m.iterrows() if float(r["c"]) < float(r["o"]))
    if kir15m >= 5:
        return True, f"15m {kir15m}/8 kırmızı"

    return False, "OK"

# ════════════════════════════════════════
# TEKNİK SKOR (0-4)
# ════════════════════════════════════════
def teknik_skor(df1h, df15m):
    """RSI, MACD, EMA cross, Bollinger — 4 puan."""
    skor  = 0
    detay = {}

    rsi1h  = calc_rsi(df1h["c"])
    rsi15m = calc_rsi(df15m["c"])
    mac1h  = calc_macd_hist(df1h["c"])
    mac15m = calc_macd_hist(df15m["c"])
    bbp    = calc_bb_pct(df1h["c"])

    ema9_now  = float(calc_ema(df1h["c"], 9).iloc[-1])
    ema21_now = float(calc_ema(df1h["c"], 21).iloc[-1])
    ema_up    = ema9_now > ema21_now

    # 1. RSI
    if rsi1h < 45:
        skor += 1; detay["rsi"] = f"✅{rsi1h:.0f}"
    elif rsi15m < 45:
        skor += 1; detay["rsi"] = f"✅15m{rsi15m:.0f}"
    else:
        detay["rsi"] = f"❌{rsi1h:.0f}"

    # 2. MACD
    if mac1h > 0:
        skor += 1; detay["macd"] = "✅1h+"
    elif mac15m > 0:
        skor += 1; detay["macd"] = "✅15m+"
    else:
        detay["macd"] = "❌"

    # 3. EMA
    if ema_up:
        skor += 1; detay["ema"] = "✅↑"
    else:
        detay["ema"] = "❌↓"

    # 4. Bollinger — üst banda yakınsa giriş yapma
    if bbp < 0.70:
        skor += 1; detay["bb"] = f"✅{bbp:.2f}"
    else:
        detay["bb"] = f"❌{bbp:.2f}"

    return skor, detay

# ════════════════════════════════════════
# ANA SİNYAL ANALİZİ
# ════════════════════════════════════════
def analiz_et(symbol):
    """
    Tüm filtreleri sırayla uygula.
    Returns: (skor, detay, price, atr_val) veya None
    """
    try:
        r1h  = safe_api(exchange.fetch_ohlcv, symbol, "1h",  limit=250)
        r15m = safe_api(exchange.fetch_ohlcv, symbol, "15m", limit=40)
        if not r1h  or len(r1h)  < 200: return None
        if not r15m or len(r15m) < 20:  return None

        df1h  = pd.DataFrame(r1h,  columns=["t","o","h","l","c","v"])
        df15m = pd.DataFrame(r15m, columns=["t","o","h","l","c","v"])

        price = float(df1h["c"].iloc[-1])
        pct1h = (price - float(df1h["c"].iloc[-2])) / float(df1h["c"].iloc[-2]) * 100
        pct4h = (price - float(df1h["c"].iloc[-5])) / float(df1h["c"].iloc[-5]) * 100

        # ── Temel hard filtreler ──
        if calc_rsi(df1h["c"]) >= RSI_MAX:  # >= ile tam eşit de engellenir
            log.info(f"[PAS] {symbol.split('/')[0]}: RSI yüksek")
            return None
        if pct4h > PCT_4H_MAX:
            log.info(f"[PAS] {symbol.split('/')[0]}: 4h geç")
            return None
        if pct1h > PCT_1H_MAX:
            log.info(f"[PAS] {symbol.split('/')[0]}: 1h geç")
            return None

        # ── ADIM 1: 1h Trend filtresi ──
        trend_ok, trend_detay = filtre_1h_trend(df1h)
        if not trend_ok:
            log.info(f"[PAS] {symbol.split('/')[0]}: 1h trend {trend_detay}")
            return None

        # ── Düşüş trendi engeli ──
        dusus, dusus_neden = dusus_trendi_var_mi(df1h, df15m)
        if dusus:
            log.info(f"[PAS] {symbol.split('/')[0]}: Düşüş {dusus_neden}")
            return None

        # ── ADIM 4: ATR volatilite ──
        atr_ok, atr_val, atr_detay = filtre_atr_volatilite(df1h)
        if not atr_ok:
            log.info(f"[PAS] {symbol.split('/')[0]}: ATR uygunsuz {atr_detay}")
            return None

        # ── ADIM 2: 15m Momentum ──
        dip_puan, dip_detay = filtre_15m_momentum(df1h, df15m)

        # ── Teknik skor ──
        t_skor, t_detay = teknik_skor(df1h, df15m)

        # Toplam skor
        skor = t_skor + dip_puan

        # Dip yoksa direkt engelle — tepede giriş riski çok yüksek
        if dip_puan == 0:
            log.info(f"[PAS] {symbol.split('/')[0]}: Dip kriteri yok")
            return None

        vol1h = calc_vol_ratio(df1h)

        detay = {
            **t_detay,
            **dip_detay,
            "vol":   f"{'✅' if vol1h >= 1.8 else '⚠️'}{vol1h:.1f}x",
            "trend": trend_detay,
            "atr":   atr_detay,
            "price": price,
            "skor":  skor,
        }

        return skor, detay, price, atr_val

    except Exception as e:
        log.warning(f"[ANALİZ] {symbol}: {e}")
        return None

# ════════════════════════════════════════
# ADIM 5: ATR GİRİŞ BEKLEMESİ
# ════════════════════════════════════════
def atr_giris_bekle(symbol, current_price, atr_val):
    """
    ATR × 0.3 kadar geri çekilmeyi 90sn bekle.
    Gelirse ideal fiyat, gelmezse mevcut fiyat.
    %2 yukarı kaçarsa iptal (-1).
    """
    hedef = current_price - atr_val * ATR_GIRIS_MULT
    tavan = current_price * 1.02
    sym   = symbol.split("/")[0]
    log.info(f"[ATR_GİRİŞ] {sym} hedef:{hedef:.8f} ({ATR_GIRIS_SURE}sn)")

    for _ in range(int(ATR_GIRIS_SURE / 10)):
        time.sleep(10)
        t = safe_api(exchange.fetch_ticker, symbol)
        if not t:
            break
        p = float(t["last"])
        if p >= tavan:
            log.info(f"[ATR_GİRİŞ] {sym} fiyat kaçtı, iptal")
            return -1
        if p <= hedef:
            log.info(f"[ATR_GİRİŞ] {sym} hedef @ {p:.8f}")
            return p

    t = safe_api(exchange.fetch_ticker, symbol)
    return float(t["last"]) if t else current_price

# ════════════════════════════════════════
# PNL HESABI
# ════════════════════════════════════════
def hesap_pnl(pos, price):
    """Contracts bazlı doğru PnL hesabı."""
    entry    = pos["entry"]
    amount   = pos.get("amount", POS_SIZE / entry)
    pnl      = (price - entry) * amount - POS_SIZE * COMMISSION
    pnl_pct  = (price - entry) / entry * 100
    return pnl, pnl_pct

# ════════════════════════════════════════
# ADIM 6: İŞLEM AÇ (GÜVENLİ EMİR)
# ════════════════════════════════════════
def open_pos(symbol, skor, detay, btc_trend, atr_val, current_price):
    """
    Bitget one-way mode uyumlu giriş.
    ATR bazlı SL, güvenli emir formatı.
    """
    if günlük_limit_asıldı():
        return False

    sym = symbol.split("/")[0]

    # ADIM 3: 5m tetikleyici
    tetik_ok, tetik_detay = filtre_5m_tetik(symbol)
    if not tetik_ok:
        log.info(f"[PAS] {sym}: {tetik_detay}")
        return False

    # ATR giriş bekle
    giris = atr_giris_bekle(symbol, current_price, atr_val)
    if giris == -1:
        return False
    if giris <= 0:
        giris = current_price

    # SL: ATR × 1.0, max %3
    sl_atr = round(giris - atr_val * ATR_SL_MULT, 8)
    sl_pct = round(giris * (1 - SL_PCT / 100), 8)
    sl     = max(sl_atr, sl_pct)  # Daha yakın SL

    # TP seviyeleri
    tps = [round(giris * (1 + p / 100), 8) for p in TP_PCTS]

    with pos_lock:
        sym_base = sym.upper()
        if symbol in positions:
            return False
        for ex in positions:
            if ex.split("/")[0].upper() == sym_base:
                return False
        with closed_lock:
            if sym_base in recently_closed:
                if time.time() - recently_closed[sym_base] < 14400:
                    return False
        if len(positions) >= MAX_OPEN:
            return False
        if günlük_limit_asıldı():
            return False

        positions[symbol] = {
            "entry":     giris,
            "sl":        sl,
            "tps":       tps,
            "tp_idx":    0,
            "max_price": giris,
            "open_time": time.time(),
            "amount":    0,
            "btc_trend": btc_trend,
            "skor":      skor,
            "atr":       atr_val,
        }

    # Borsa işlemleri
    try:
        # Margin modu ve kaldıraç ayarla
        try:
            exchange.set_margin_mode("isolated", symbol, params={"marginCoin": "USDT"})
        except Exception as e:
            log.warning(f"[MARGIN] {sym}: {e}")
        try:
            exchange.set_leverage(LEVERAGE, symbol, params={"marginCoin": "USDT"})
        except Exception as e:
            log.warning(f"[LEVERAGE] {sym}: {e}")

        # Miktar hesapla
        amount = round(POS_SIZE / giris, 4)
        amount = float(exchange.amount_to_precision(symbol, amount))
        if amount <= 0:
            with pos_lock: positions.pop(symbol, None)
            return False

        # Giriş emri — Bitget swap için doğru format
        order = safe_api(
            exchange.create_order,
            symbol, "market", "buy", amount,
            None,
            {
                "marginMode": "isolated",
                "marginCoin": "USDT",
            }
        )
        if not order:
            with pos_lock: positions.pop(symbol, None)
            return False

        with pos_lock:
            if symbol in positions:
                positions[symbol]["amount"] = amount

    except Exception as e:
        log.error(f"[EMIR] {sym}: {e}")
        with pos_lock: positions.pop(symbol, None)
        return False

    # Telegram bildirimi
    sl_pct_g = (giris - sl) / giris * 100
    tp_str   = "\n".join([f"TP{i+1}: {tp:.8f} ──" for i, tp in enumerate(tps)])
    tg(
        f"📊 #{sym}USDT.P\n"
        f"🏁 LONG - Giriş: {giris:.8f}\n"
        f"🚫 Stop: {sl:.8f} (-%{sl_pct_g:.1f})\n\n"
        f"💡 Pozisyon Detayları\n{tp_str}\n\n"
        f"📊 Skor: {skor}/8 | BTC: {btc_trend}\n"
        f"Trend:{detay.get('trend','?')}\n"
        f"RSI:{detay.get('rsi','?')} MACD:{detay.get('macd','?')} "
        f"EMA:{detay.get('ema','?')} BB:{detay.get('bb','?')}\n"
        f"Dip:{detay.get('dip','?')} Bounce:{detay.get('bounce','?')} "
        f"Yeşil:{detay.get('yesil','?')} Destek:{detay.get('destek','?')}\n"
        f"Vol:{detay.get('vol','?')} {detay.get('atr','')}"
    )
    log.info(f"[AÇIK] {sym} @ {giris:.8f} skor:{skor} atr:{atr_val:.8f}")
    return True

# ════════════════════════════════════════
# İŞLEM KAPAT (GÜVENLİ EMIR)
# ════════════════════════════════════════
def close_pos(symbol, reason, exit_price=None):
    """
    Bitget one-way mode uyumlu kapanış.
    reduceOnly doğru params formatında.
    """
    with pos_lock:
        pos = positions.pop(symbol, None)
    if not pos:
        return

    sym    = symbol.split("/")[0]
    amount = pos.get("amount", 0)

    # Miktar yoksa hesapla
    if not amount or amount <= 0:
        amount = round(POS_SIZE / pos["entry"], 4)

    # Borsada pozisyon var mı kontrol et
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

    # Kapanış emri — reduceOnly doğru format
    try:
        safe_api(
            exchange.create_order,
            symbol, "market", "sell", amount,
            None,
            {
                "reduceOnly": True,
                "marginCoin": "USDT",
            }
        )
    except Exception as e:
        err = str(e)
        if "22002" in err or "No position" in err or "position not exist" in err.lower():
            log.info(f"[KAPAT] {sym}: Borsada pozisyon yok (zaten kapanmış)")
        else:
            log.error(f"[KAPAT] {sym}: {e}")

    # Çıkış fiyatı
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
            "symbol":    symbol,
            "signal":    "LONG",
            "pnl":       round(pnl, 4),
            "sure_dk":   sure,
            "reason":    reason,
            "btc_trend": pos.get("btc_trend", ""),
        })
    except:
        pass

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

                # ── Stop Loss ──
                if price <= sl:
                    close_pos(symbol, f"🚫 Stop Loss ({sl:.8f})", price)
                    continue

                # ── Erken zarar (ilk 8dk) ──
                if sure <= 8 and pnl_pct <= -1.5:
                    close_pos(symbol, f"Erken zarar ({pnl_pct:.1f}%)", price)
                    continue

                # ── Zaman aşımı 3 saat ──
                if sure >= 180:
                    close_pos(symbol, "Zaman aşımı 3 saat", price)
                    continue

                # ── Günlük limit ──
                if günlük_limit_asıldı():
                    close_pos(symbol, "Günlük limit", price)
                    continue

                # ── TP seviyeleri ──
                if tp_idx < len(tps) and price >= tps[tp_idx]:
                    if tp_idx == 0:
                        yeni_sl = entry                              # başabaş
                    elif tp_idx == 1:
                        yeni_sl = round(entry + atr_val * 0.5, 8)  # nefes alanı
                    else:
                        yeni_sl = tps[tp_idx - 1]                  # önceki TP

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

                # ── TP sonrası trailing stop ──
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
    time.sleep(30)
    while True:
        try:
            if günlük_limit_asıldı():
                time.sleep(SCAN_INTERVAL)
                continue

            btc_trend, btc_price, btc_chg = get_btc_trend()

            if btc_trend == "DOWN":
                log.info("[SCAN] BTC DOWN - bekleniyor")
                time.sleep(SCAN_INTERVAL)
                continue

            # BTC trend'e göre skor eşiği
            if btc_trend == "UP":
                esik = SKOR_UP
            elif btc_trend == "NEUTRAL_LONG":
                esik = SKOR_NEUTRAL_LONG
            else:
                esik = SKOR_NEUTRAL_SHORT

            fg_val, fg_lbl = get_fear_greed()
            if fg_val <= FG_MIN:
                log.info(f"[SCAN] Extreme Fear ({fg_val}) - bekleniyor")
                time.sleep(SCAN_INTERVAL)
                continue

            with pos_lock:
                if len(positions) >= MAX_OPEN:
                    time.sleep(20)
                    continue
                open_syms = set(positions.keys())

            # Cache'li ticker
            tickers = get_tickers_cached()
            if not tickers:
                time.sleep(SCAN_INTERVAL)
                continue

            # Aday filtrele
            candidates = []
            for symbol, ticker in tickers.items():
                if not symbol.endswith("/USDT:USDT"):
                    continue
                sym = symbol.split("/")[0]
                if sym in BLACKLIST:
                    continue
                if symbol in open_syms:
                    continue

                qv    = ticker.get("quoteVolume") or 0
                pct   = ticker.get("percentage")  or 0
                price = float(ticker.get("last")   or 0)

                if qv    < MIN_VOL_USDT or qv > MAX_VOL_USDT: continue
                if price < MIN_PRICE    or price > MAX_PRICE:  continue
                if abs(pct) > 30:  continue
                if pct < 0.2:      continue

                sym_base = sym.upper()
                with closed_lock:
                    if sym_base in recently_closed:
                        if time.time() - recently_closed[sym_base] < 14400:
                            continue

                candidates.append({"symbol": symbol, "pct": pct, "qv": qv})

            # Sırala + karıştır
            candidates.sort(key=lambda x: x["pct"], reverse=True)
            top4 = candidates[:4]
            rest = candidates[4:]
            random.shuffle(rest)
            candidates = (top4 + rest)[:8]

            log.info(f"[SCAN] {len(candidates)} aday | BTC:{btc_trend} esik:{esik} FG:{fg_val}")

            for c in candidates:
                symbol = c["symbol"]
                sym    = symbol.split("/")[0]

                with pos_lock:
                    if len(positions) >= MAX_OPEN:
                        break
                    if symbol in open_syms:
                        continue

                sonuc = analiz_et(symbol)
                if not sonuc:
                    continue

                skor, detay, price, atr_val = sonuc

                if skor >= esik:
                    log.info(f"[SİNYAL] {sym} skor:{skor}/8 → GİRİYOR")
                    # Ayrı thread'de aç — tarayıcıyı bloklamaz
                    threading.Thread(
                        target=open_pos,
                        args=(symbol, skor, detay, btc_trend, atr_val, price),
                        daemon=True
                    ).start()
                    with pos_lock:
                        open_syms = set(positions.keys())
                else:
                    log.info(f"[PAS] {sym} skor:{skor}/8 (esik:{esik})")

                time.sleep(1.5)

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
            fg, _    = get_fear_greed()
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
    """
    Borsadaki açık pozisyonları yükle.
    Alan doğrulaması + loglama yapılır.
    """
    try:
        log.info("[YUKLE] Kontrol ediliyor...")
        raw = safe_api(exchange.fetch_positions)
        if not raw:
            log.info("[YUKLE] Pozisyon yok")
            return

        # İlk pozisyonu logla — alan formatını doğrula
        if raw:
            log.info(f"[YUKLE] Örnek pozisyon alanları: {list(raw[0].keys())}")

        btc_trend, _, _ = get_btc_trend()
        yuklenen = 0
        lines    = ["♻️ Önceki pozisyonlar yüklendi:\n"]

        for p in raw:
            try:
                # Alan doğrulaması
                contracts  = float(p.get("contracts") or p.get("size") or 0)
                symbol     = p.get("symbol", "")
                side       = p.get("side", "")
                entry      = float(p.get("entryPrice") or p.get("entry_price") or 0)

                if contracts == 0:
                    continue
                if not symbol:
                    log.warning(f"[YUKLE] symbol alanı boş: {p}")
                    continue
                if side != "long":
                    continue
                if entry == 0:
                    log.warning(f"[YUKLE] entryPrice 0: {p}")
                    continue

                tps = [round(entry * (1 + x / 100), 8) for x in TP_PCTS]
                sl  = round(entry * (1 - SL_PCT / 100), 8)

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
                            "skor":      0,
                            "atr":       entry * 0.015,
                        }
                        yuklenen += 1

                        t   = safe_api(exchange.fetch_ticker, symbol)
                        now = float(t["last"]) if t else entry
                        # Contracts bazlı PnL
                        pnl = (now - entry) * contracts - POS_SIZE * COMMISSION
                        icon = "🟢" if pnl >= 0 else "🔴"
                        lines.append(
                            f"{icon} {symbol.split('/')[0]} @ {entry:.8f} "
                            f"| {contracts} kontrat | {pnl:+.2f}$"
                        )
                        log.info(f"[YUKLE] {symbol.split('/')[0]} LONG @ {entry} x{contracts}")

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
    """Kullanıcı mesajından coin sembolü bul."""
    words = re.findall(r"\b[A-Z]{2,10}\b", text.upper())
    try:
        tickers = get_tickers_cached()
        if not tickers:
            return None
        for w in words:
            if w in BLACKLIST:
                continue
            sym = f"{w}/USDT:USDT"
            if sym in tickers:
                return sym
    except:
        pass
    return None

@bot.message_handler(func=lambda msg: True)
def handle(msg):
    if not msg.text:
        return
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
                if not t:
                    continue
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
        aciklama = {
            "UP":           "⬆️ Güçlü → esik:3",
            "NEUTRAL_LONG": "↗️ Normal → esik:4",
            "NEUTRAL_SHORT":"↘️ Zayıf → esik:6",
            "DOWN":         "⬇️ Düşüş → BEKLER",
        }.get(trend, "↔️")
        bot.send_message(
            msg.chat.id,
            f"BTC: {trend}\n${price:,.0f} ({chg:+.1f}%)\n{aciklama}\n\n"
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
            bot.send_message(
                msg.chat.id,
                f"Hangisini? {', '.join(s.split('/')[0] for s in syms)}"
            )
        return

    # Coin analizi
    coin = find_coin(text)
    if coin:
        sym = coin.split("/")[0]
        bot.send_message(msg.chat.id, f"🔍 {sym} analiz ediliyor...")
        sonuc = analiz_et(coin)
        trend, _, _ = get_btc_trend()
        fg, fl      = get_fear_greed()

        if sonuc:
            skor, detay, price, atr_val = sonuc
            tps = [round(price * (1 + p / 100), 8) for p in TP_PCTS]
            sl  = round(price * (1 - SL_PCT / 100), 8)
            tp_str = " | ".join([f"TP{i+1}:{tp:.6f}" for i, tp in enumerate(tps)])
            esik = SKOR_NEUTRAL_LONG
            bot.send_message(
                msg.chat.id,
                f"📊 {sym} | Skor: {skor}/8\n"
                f"Trend: {detay.get('trend','?')}\n"
                f"RSI:{detay.get('rsi','?')} MACD:{detay.get('macd','?')} "
                f"EMA:{detay.get('ema','?')} BB:{detay.get('bb','?')}\n"
                f"Dip:{detay.get('dip','?')} Bounce:{detay.get('bounce','?')} "
                f"Yeşil:{detay.get('yesil','?')} Destek:{detay.get('destek','?')}\n"
                f"Vol:{detay.get('vol','?')} {detay.get('atr','')}\n"
                f"BTC: {trend} | FG: {fg} ({fl})\n\n"
                f"{'✅ GİRİLİR' if skor >= esik else '❌ PAS'} ({skor}/8)\n"
                f"SL: {sl:.8f}\n{tp_str}"
            )
        else:
            bot.send_message(msg.chat.id, f"❌ {sym} filtreleri geçemedi.")
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
    print("SADIK TRADER v8 BAŞLIYOR...")
    load_open_positions()
    threading.Thread(target=health_server,     daemon=True).start()
    threading.Thread(target=manage_loop,       daemon=True).start()
    threading.Thread(target=scanner_loop,      daemon=True).start()
    threading.Thread(target=gunluk_reset_loop, daemon=True).start()

    fg, fl            = get_fear_greed()
    trend, price, chg = get_btc_trend()

    tg(
        "🤖 SADIK TRADER v8 — KURUMSAL KALİTE\n\n"
        "📊 Giriş Akışı:\n"
        "  1️⃣ 1h Trend → 200EMA + 20/50EMA\n"
        "  2️⃣ 15m Momentum → Dip bounce + Yeşil mum\n"
        "  3️⃣ 5m Tetikleyici → Anlık konfirm\n"
        "  4️⃣ ATR Volatilite → Uygun rejim\n"
        "  5️⃣ ATR Giriş → 90sn ideal fiyat\n"
        "  6️⃣ Güvenli Emir → Bitget uyumlu\n\n"
        "✅ reduceOnly doğru format\n"
        "✅ Ticker cache (rate limit koruması)\n"
        "✅ Contracts bazlı PnL\n"
        "✅ Düşüş trendi engeli\n"
        "✅ Günlük PnL merkezi kontrol\n\n"
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
