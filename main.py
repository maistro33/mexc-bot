#!/usr/bin/env python3
"""
SADIK TRADER v3 - Multi-Timeframe + Kademeli Kar Koruma
DUZELTMELER:
- BTC trend tespiti daha hassas (EMA + RSI + momentum birlikte)
- NEUTRAL'da LONG/SHORT yonu hacim + RSI ile belirleniyor
- BTC DOWN'da kesinlikle LONG yok
- BTC UP'da kesinlikle SHORT yok
- NEUTRAL'da her iki yon acilabilir AMA ek filtreler var
- Gec kalma filtresi korundu
"""

import os, time, threading, logging, re
import ccxt
import pandas as pd
import requests as req
import telebot
from supabase import create_client

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("SADIK")

# CONFIG
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
MIN_VOL_USDT   = 1_000_000
MAX_VOL_USDT   = 5_000_000
MAX_DAILY_LOSS = -10.0
SCAN_INTERVAL  = 60

# Kademeli kar koruma
KAR_KADEMELERI = [
    (1.0, 0.30),
    (2.0, 0.80),
    (3.0, 1.50),
    (4.0, 2.50),
    (5.0, 3.50),
]
GERI_CEKILME = 0.30

BLACKLIST = {
    # Volatil/manipule coinler
    "BANANAS31","BSB","JCT","MEGA","ALLO","FTM","MU",
    "TURBO","MOODENG","SUNDOG","NEIRO","HMSTR","CATI","DOGS","MYRO",
    "BOME","SLERF","PNUT","ACT","GOAT","RGTI","SATL","WET","POET",
    "SOXL","SOXS","UVXY","SVIX","KORU","AMC","GME","CLOSED",
    # Veri analizine gore surekli zarar ettiren coinler
    "BICO","ARX","BEAT","ID","ALICE","XLM","BTW",
}

# STATE
positions       = {}
pos_lock        = threading.Lock()
daily_pnl       = 0.0
recently_closed = {}
closed_lock     = threading.Lock()
son_bakilan     = set()

# BTC TREND CACHE - her 5 dakikada bir guncellenir
btc_cache       = {"trend": "NEUTRAL", "price": 0, "chg": 0, "ts": 0}
btc_cache_lock  = threading.Lock()
BTC_CACHE_SURE  = 300  # 5 dakika

# TELEGRAM
bot = telebot.TeleBot(TELE_TOKEN)
def tg(msg):
    try: bot.send_message(CHAT_ID, str(msg)[:4096])
    except Exception as e: log.warning(f"[TG] {e}")

# SUPABASE
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

# EXCHANGE
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

# ─────────────────────────────────────────────
# BTC TREND — 1h + 15m birlikte, pump→dump yakala
# ─────────────────────────────────────────────
def _fetch_btc_trend():
    """Ham BTC trend hesaplamasi - direkt API cagrisi"""
    """
    UP            : Net yukari trend  → Sadece LONG
    DOWN          : Net asagi trend   → Sadece SHORT
    NEUTRAL_LONG  : Hafif yukari      → LONG oncelikli
    NEUTRAL_SHORT : Hafif asagi       → SHORT oncelikli
    NEUTRAL       : Gercekten belirsiz→ Cok secici
    """
    try:
        # 1h mum - orta vade
        raw1h = safe_api(exchange.fetch_ohlcv, "BTC/USDT:USDT", "1h",  limit=100)
        # 15m mum - kisa vade (pump→dump tespiti)
        raw15m = safe_api(exchange.fetch_ohlcv, "BTC/USDT:USDT", "15m", limit=50)

        if not raw1h: return "NEUTRAL", 0, 0

        df1h = pd.DataFrame(raw1h,  columns=["t","o","h","l","c","v"])
        price = float(df1h["c"].iloc[-1])

        # 1h EMA
        e9_1h  = float(df1h["c"].ewm(span=9).mean().iloc[-1])
        e20_1h = float(df1h["c"].ewm(span=20).mean().iloc[-1])
        e50_1h = float(df1h["c"].ewm(span=50).mean().iloc[-1])

        # Degisimler
        chg1h  = (price - float(df1h["c"].iloc[-2]))  / float(df1h["c"].iloc[-2])  * 100
        chg4h  = (price - float(df1h["c"].iloc[-4]))  / float(df1h["c"].iloc[-4])  * 100
        chg24h = (price - float(df1h["c"].iloc[-24])) / float(df1h["c"].iloc[-24]) * 100

        # 1h RSI
        delta = df1h["c"].diff()
        gain  = delta.clip(lower=0).rolling(14).mean()
        loss  = (-delta.clip(upper=0)).rolling(14).mean()
        rs    = gain / loss.replace(0, 0.001)
        rsi_1h = float((100 - 100 / (1 + rs)).iloc[-1])

        # 15m analiz - kisa vade
        pump_then_dump = False
        trend_15m = "FLAT"
        rsi_15m   = 50.0
        chg_15m   = 0.0

        if raw15m:
            df15m = pd.DataFrame(raw15m, columns=["t","o","h","l","c","v"])
            e9_15m  = df15m["c"].ewm(span=9).mean()
            e20_15m = df15m["c"].ewm(span=20).mean()

            # Son 15m EMA yonu
            if float(e9_15m.iloc[-1]) > float(e20_15m.iloc[-1]):
                trend_15m = "YUKARI"
            else:
                trend_15m = "ASAGI"

            # 15m RSI
            d15 = df15m["c"].diff()
            g15 = d15.clip(lower=0).rolling(14).mean()
            l15 = (-d15.clip(upper=0)).rolling(14).mean()
            rs15 = g15 / l15.replace(0, 0.001)
            rsi_15m = float((100 - 100 / (1 + rs15)).iloc[-1])

            # Son 2 saatlik 15m degisim
            chg_15m = (price - float(df15m["c"].iloc[-8])) / float(df15m["c"].iloc[-8]) * 100

            # Pump → Dump tespiti:
            # Son 8 mumda once yukselip sonra dustuyse
            son8 = df15m["c"].tail(8).values
            tepe = max(son8)
            tepe_idx = list(son8).index(tepe)
            if tepe_idx <= 5 and tepe_idx >= 1:  # Tepe ortada veya basinda
                durus = (price - tepe) / tepe * 100
                yukselis = (tepe - son8[0]) / son8[0] * 100
                if yukselis > 0.5 and durus < -0.4:
                    pump_then_dump = True
                    log.info(f"[BTC] Pump→Dump tespit: +{yukselis:.1f}% sonra {durus:.1f}%")

        # ── KARAR MATRISI ──

        # 1h EMA pozisyonu
        fiyat_e20_ustu  = price > e20_1h
        fiyat_e50_ustu  = price > e50_1h
        ema_dizi_yukari = e9_1h > e20_1h > e50_1h
        ema_dizi_asagi  = e9_1h < e20_1h

        # ── DOWN tespiti - cok daha hassas ──
        # Kural 1: 24h -2%+ dusus = kesinlikle DOWN
        if chg24h < -2.0:
            return "DOWN", price, chg24h

        # Kural 2: 4h -1%+ dusus ve 15m asagi trend
        if chg4h < -1.0 and trend_15m == "ASAGI":
            return "DOWN", price, chg24h

        # Kural 3: EMA asagi dizilimi + herhangi dusus
        if ema_dizi_asagi and chg4h < -0.5:
            return "DOWN", price, chg24h

        # Kural 4: Pump→dump
        if pump_then_dump and chg_15m < -0.3:
            return "DOWN", price, chg24h

        # ── UP tespiti ──
        if chg24h > 2.0:
            return "UP", price, chg24h
        if chg4h > 1.0 and trend_15m == "YUKARI" and fiyat_e20_ustu:
            return "UP", price, chg24h
        if ema_dizi_yukari and chg4h > 0.5:
            return "UP", price, chg24h

        # ── NEUTRAL_SHORT - hafif asagi ──
        if chg24h < -1.0 or (chg4h < -0.3 and trend_15m == "ASAGI"):
            return "NEUTRAL_SHORT", price, chg24h

        # ── NEUTRAL_LONG - hafif yukari ──
        if chg24h > 1.0 or (chg4h > 0.3 and trend_15m == "YUKARI" and fiyat_e20_ustu):
            return "NEUTRAL_LONG", price, chg24h

        return "NEUTRAL", price, chg24h

    except Exception as e:
        log.warning(f"[BTC_TREND] {e}")
        return "NEUTRAL", 0, 0

def get_btc_trend():
    """Cache'li BTC trend - 5dk'da bir API cagrir, arada cache doner"""
    global btc_cache
    with btc_cache_lock:
        if time.time() - btc_cache["ts"] < BTC_CACHE_SURE:
            return btc_cache["trend"], btc_cache["price"], btc_cache["chg"]
    # Cache suresi doldu, guncelle
    trend, price, chg = _fetch_btc_trend()
    with btc_cache_lock:
        btc_cache = {"trend": trend, "price": price, "chg": chg, "ts": time.time()}
    log.info(f"[BTC_CACHE] Guncellendi: {trend} ${price:,.0f} ({chg:+.1f}%)")
    return trend, price, chg

def get_btc_trend_force():
    """Cache'i bypass et, aninda guncelle - onemli kararlar icin"""
    global btc_cache
    trend, price, chg = _fetch_btc_trend()
    with btc_cache_lock:
        btc_cache = {"trend": trend, "price": price, "chg": chg, "ts": time.time()}
    return trend, price, chg

# ─────────────────────────────────────────────
# TEKNIK ANALIZ
# ─────────────────────────────────────────────
def ema_yonu(df):
    e9  = df["c"].ewm(span=9).mean()
    e20 = df["c"].ewm(span=20).mean()
    son_yukari = float(e9.iloc[-1]) > float(e20.iloc[-1])
    kesiyor_yukari = float(e9.iloc[-5]) < float(e20.iloc[-5]) and son_yukari
    kesiyor_asagi  = float(e9.iloc[-5]) > float(e20.iloc[-5]) and not son_yukari
    return son_yukari, kesiyor_yukari, kesiyor_asagi

def rsi(df):
    delta = df["c"].diff()
    gain  = delta.clip(lower=0).rolling(14).mean()
    loss  = (-delta.clip(upper=0)).rolling(14).mean()
    rs    = gain / loss.replace(0, 0.001)
    return float((100 - 100 / (1+rs)).iloc[-1])

def hacim(df, n=3):
    avg = float(df["v"].rolling(20).mean().iloc[-1])
    son = float(df["v"].tail(n).mean())
    return son / max(avg, 0.001)

def analyze_coin(symbol):
    """1m + 5m + 15m + 1h multi-timeframe analiz"""
    try:
        r1m  = safe_api(exchange.fetch_ohlcv, symbol, "1m",  limit=30)
        r5m  = safe_api(exchange.fetch_ohlcv, symbol, "5m",  limit=30)
        r15m = safe_api(exchange.fetch_ohlcv, symbol, "15m", limit=30)
        r1h  = safe_api(exchange.fetch_ohlcv, symbol, "1h",  limit=30)

        if not r15m or len(r15m) < 20: return None

        df1m  = pd.DataFrame(r1m,  columns=["t","o","h","l","c","v"]) if r1m  else None
        df5m  = pd.DataFrame(r5m,  columns=["t","o","h","l","c","v"]) if r5m  else None
        df15m = pd.DataFrame(r15m, columns=["t","o","h","l","c","v"])
        df1h  = pd.DataFrame(r1h,  columns=["t","o","h","l","c","v"]) if r1h  else None

        price = float(df15m["c"].iloc[-1])

        def trend(df):
            if df is None: return None
            yukari, _, _ = ema_yonu(df)
            return "YUKARI" if yukari else "ASAGI"

        t1m  = trend(df1m)
        t5m  = trend(df5m)
        t15m = trend(df15m)
        t1h  = trend(df1h)

        trendler    = [t for t in [t1m, t5m, t15m, t1h] if t]
        uyum_yukari = trendler.count("YUKARI")
        uyum_asagi  = trendler.count("ASAGI")

        _, k1m_yukari,  k1m_asagi  = ema_yonu(df1m)  if df1m  is not None else (None, False, False)
        _, k5m_yukari,  k5m_asagi  = ema_yonu(df5m)  if df5m  is not None else (None, False, False)
        _, k15m_yukari, k15m_asagi = ema_yonu(df15m)

        v1m  = hacim(df1m,  3) if df1m  is not None else 1.0
        v5m  = hacim(df5m,  3) if df5m  is not None else 1.0
        v15m = hacim(df15m, 3)

        rsi_val = rsi(df15m)

        # 1h RSI - ek filtre icin
        rsi_1h = rsi(df1h) if df1h is not None else rsi_val

        pct = (price - float(df15m["c"].iloc[-10])) / float(df15m["c"].iloc[-10]) * 100

        return {
            "price": price, "rsi": rsi_val, "rsi_1h": rsi_1h,
            "uyum_yukari": uyum_yukari, "uyum_asagi": uyum_asagi,
            "k1m_yukari": k1m_yukari, "k1m_asagi": k1m_asagi,
            "k5m_yukari": k5m_yukari, "k5m_asagi": k5m_asagi,
            "k15m_yukari": k15m_yukari, "k15m_asagi": k15m_asagi,
            "v1m": v1m, "v5m": v5m, "v15m": v15m,
            "pct": pct,
        }
    except Exception as e:
        log.warning(f"[ANALYZE] {symbol}: {e}")
        return None

# ─────────────────────────────────────────────
# KARAR VER — BTC trend'e gore akilli secim
# ─────────────────────────────────────────────
def karar_ver(data, btc_trend):
    if not data: return None, ""

    rsi_val = data["rsi"]
    rsi_1h  = data["rsi_1h"]
    uy      = data["uyum_yukari"]
    ua      = data["uyum_asagi"]
    v1m     = data["v1m"]
    v5m     = data["v5m"]
    pct     = data["pct"]

    # Gec kalma filtresi
    if abs(pct) > 20:
        return None, f"Gec kalindi ({pct:.1f}%)"
    if pct > 5:
        return None, f"LONG gec kalindi ({pct:.1f}%)"
    if pct < -5:
        return None, f"SHORT gec kalindi ({pct:.1f}%)"

    vol_ok = v1m >= 1.5 or v5m >= 1.5

    # ── BTC GUCLU YUKARI → Sadece LONG ──
    if btc_trend == "UP":
        if not vol_ok:
            return None, f"Hacim yetersiz (v1m:{v1m:.1f}x)"
        if data["k1m_yukari"] and uy >= 3 and 0 < pct < 3 and rsi_val < 68:
            return "LONG", f"BTC UP | 1m EMA kesti, {uy}/4 yukari, +{pct:.1f}%"
        if data["k5m_yukari"] and uy >= 3 and 0 < pct < 4 and rsi_val < 68:
            return "LONG", f"BTC UP | 5m EMA kesti, {uy}/4 yukari, +{pct:.1f}%"
        if v1m >= 2.5 and uy >= 3 and 0 < pct < 2 and rsi_val < 65:
            return "LONG", f"BTC UP | Hacim {v1m:.1f}x, {uy}/4 yukari, +{pct:.1f}%"
        return None, f"BTC UP ama LONG kosulu saglanamadi (Y:{uy} RSI:{rsi_val:.0f})"

    # ── BTC GUCLU ASAGI → Sadece SHORT ──
    if btc_trend == "DOWN":
        if not vol_ok:
            return None, f"Hacim yetersiz (v1m:{v1m:.1f}x)"
        if data["k1m_asagi"] and ua >= 3 and -3 < pct < 0 and rsi_val > 32:
            return "SHORT", f"BTC DOWN | 1m EMA kesti, {ua}/4 asagi, {pct:.1f}%"
        if data["k5m_asagi"] and ua >= 3 and -4 < pct < 0 and rsi_val > 32:
            return "SHORT", f"BTC DOWN | 5m EMA kesti, {ua}/4 asagi, {pct:.1f}%"
        if v1m >= 2.5 and ua >= 3 and -2 < pct < 0 and rsi_val > 35:
            return "SHORT", f"BTC DOWN | Hacim {v1m:.1f}x, {ua}/4 asagi, {pct:.1f}%"
        return None, f"BTC DOWN ama SHORT kosulu saglanamadi (A:{ua} RSI:{rsi_val:.0f})"

    # ── BTC ZAYIF YUKARI → LONG oncelikli, SHORT cok secici ──
    if btc_trend == "NEUTRAL_LONG":
        if not vol_ok:
            return None, f"Hacim yetersiz"
        # LONG - normal sartlar
        if data["k1m_yukari"] and uy >= 3 and 0 < pct < 3 and rsi_val < 65:
            return "LONG", f"BTC N-LONG | 1m EMA, {uy}/4, +{pct:.1f}%"
        if data["k5m_yukari"] and uy >= 3 and 0 < pct < 4 and rsi_val < 65:
            return "LONG", f"BTC N-LONG | 5m EMA, {uy}/4, +{pct:.1f}%"
        if v1m >= 2.5 and uy >= 3 and 0 < pct < 2 and rsi_val < 62:
            return "LONG", f"BTC N-LONG | Hacim {v1m:.1f}x"
        # SHORT - sadece cok guclu sinyal
        if data["k1m_asagi"] and ua == 4 and -2 < pct < 0 and rsi_val > 40 and v1m >= 2.0:
            return "SHORT", f"BTC N-LONG ama 4/4 asagi, {pct:.1f}%"
        return None, f"NEUTRAL_LONG kosul yok (Y:{uy} A:{ua})"

    # ── BTC ZAYIF ASAGI → SHORT oncelikli, LONG cok secici ──
    if btc_trend == "NEUTRAL_SHORT":
        if not vol_ok:
            return None, f"Hacim yetersiz"
        # SHORT - normal sartlar
        if data["k1m_asagi"] and ua >= 3 and -3 < pct < 0 and rsi_val > 35:
            return "SHORT", f"BTC N-SHORT | 1m EMA, {ua}/4, {pct:.1f}%"
        if data["k5m_asagi"] and ua >= 3 and -4 < pct < 0 and rsi_val > 35:
            return "SHORT", f"BTC N-SHORT | 5m EMA, {ua}/4, {pct:.1f}%"
        if v1m >= 2.5 and ua >= 3 and -2 < pct < 0 and rsi_val > 38:
            return "SHORT", f"BTC N-SHORT | Hacim {v1m:.1f}x"
        # LONG - sadece cok guclu sinyal
        if data["k1m_yukari"] and uy == 4 and 0 < pct < 2 and rsi_val < 60 and v1m >= 2.0:
            return "LONG", f"BTC N-SHORT ama 4/4 yukari, +{pct:.1f}%"
        return None, f"NEUTRAL_SHORT kosul yok (Y:{uy} A:{ua})"

    # ── GERCEKTEN NEUTRAL → HIC ISLEM ACMA ──
    if btc_trend == "NEUTRAL":
        return None, f"NEUTRAL: BTC belirsiz, bekleniyor (Y:{uy} A:{ua})"

    return None, f"Bilinmeyen trend: {btc_trend}"

# ─────────────────────────────────────────────
# PNL HESAP
# ─────────────────────────────────────────────
def hesap_pnl(pos, price):
    entry = pos["entry"]
    sig   = pos["signal"]
    if sig == "LONG":
        pnl_pct = (price - entry) / entry * 100 * LEVERAGE  # Gercek kaldıracli %
        pnl     = (price - entry) / entry * POS_SIZE - POS_SIZE * COMMISSION
    else:
        pnl_pct = (entry - price) / entry * 100 * LEVERAGE  # Gercek kaldıracli %
        pnl     = (entry - price) / entry * POS_SIZE - POS_SIZE * COMMISSION
    return pnl, pnl_pct

# ─────────────────────────────────────────────
# ISLEM AC
# ─────────────────────────────────────────────

def giris_momentum_ok(symbol, yon, analiz_fiyati):
    """
    Giris aninda 3 kontrol:
    1. Fiyat 3sn icinde dogru yonde mi gidiyor?
    2. Son 3 mum dogru yonde mi?
    3. Slippage kabul edilebilir mi?
    """
    try:
        t1 = safe_api(exchange.fetch_ticker, symbol)
        if not t1: return False, "Ticker alinamadi"
        fiyat1 = float(t1["last"])

        time.sleep(3)

        t2 = safe_api(exchange.fetch_ticker, symbol)
        if not t2: return False, "Ticker2 alinamadi"
        fiyat2 = float(t2["last"])

        tick_degisim = (fiyat2 - fiyat1) / fiyat1 * 100

        # Fiyat ters yonde gidiyorsa girme
        if yon == "SHORT" and tick_degisim > 0.15:
            return False, f"Geri donuyor! +{tick_degisim:.2f}% yukari gitti"
        if yon == "LONG" and tick_degisim < -0.15:
            return False, f"Geri donuyor! {tick_degisim:.2f}% asagi gitti"

        # Son 3 mum kontrolu
        r1m = safe_api(exchange.fetch_ohlcv, symbol, "1m", limit=5)
        if r1m and len(r1m) >= 3:
            son3    = r1m[-3:]
            kirmizi = sum(1 for m in son3 if m[4] < m[1])
            yesil   = sum(1 for m in son3 if m[4] > m[1])
            if yon == "SHORT" and yesil >= 2:
                return False, f"Son 3 mumun {yesil}u yesil - SHORT icin erken"
            if yon == "LONG" and kirmizi >= 2:
                return False, f"Son 3 mumun {kirmizi}u kirmizi - LONG icin erken"

        # Slippage kontrolu
        slippage = abs(fiyat2 - analiz_fiyati) / analiz_fiyati * 100
        if slippage > 0.5:
            return False, f"Slippage cok yuksek: %{slippage:.2f}"

        return True, f"OK | tick:{tick_degisim:+.2f}% | slippage:{slippage:.2f}%"

    except Exception as e:
        log.warning(f"[MOMENTUM] {e}")
        return False, f"Hata: {e}"

def open_pos(symbol, yon, neden, btc_trend):
    global daily_pnl
    if daily_pnl <= MAX_DAILY_LOSS: return False

    # BTC trend ile celisen islem KESINLIKLE ACMA
    if btc_trend == "DOWN" and yon == "LONG":
        log.info(f"[ENGEL] BTC DOWN, LONG engellendi: {symbol}")
        return False
    if btc_trend == "UP" and yon == "SHORT":
        log.info(f"[ENGEL] BTC UP, SHORT engellendi: {symbol}")
        return False

    # Analiz fiyatini al
    t0 = safe_api(exchange.fetch_ticker, symbol)
    if not t0: return False
    analiz_fiyati = float(t0["last"])

    # GIRIS MOMENTUM KONTROLU
    sym = symbol.split("/")[0]
    momentum_ok, momentum_neden = giris_momentum_ok(symbol, yon, analiz_fiyati)
    if not momentum_ok:
        log.info(f"[MOMENTUM] {sym} reddedildi: {momentum_neden}")
        return False
    log.info(f"[MOMENTUM] {sym} gecti: {momentum_neden}")

    # Guncel fiyati yeniden al (3sn gecti)
    t = safe_api(exchange.fetch_ticker, symbol)
    if not t: return False
    price    = float(t["last"])
    sl_price = price * (1 - 0.015) if yon == "LONG" else price * (1 + 0.015)

    with pos_lock:
        sym_base = symbol.split("/")[0].upper()
        for ex in positions:
            if ex.split("/")[0].upper() == sym_base: return False
        with closed_lock:
            if sym_base in recently_closed:
                if time.time() - recently_closed[sym_base] < 7200: return False
        if len(positions) >= MAX_OPEN: return False

        positions[symbol] = {
            "signal": yon, "entry": price,
            "sl_price": sl_price,
            "sl_garantili": 0.0,
            "max_pnl": 0.0,
            "max_kar": 0.0,
            "neden": neden, "btc_trend": btc_trend,
            "open_time": time.time(),
        }

    sym = symbol.split("/")[0]

    try:
        try:
            exchange.set_margin_mode("isolated", symbol)
        except Exception as me:
            log.warning(f"[MARGIN] {me}")

        try:
            exchange.set_leverage(LEVERAGE, symbol)
        except Exception as le:
            log.warning(f"[KALDIRAC] {le}")

        amount = round(POS_SIZE / price, 4)
        side   = "buy" if yon == "LONG" else "sell"
        order  = exchange.create_order(
            symbol, "market", side, amount,
            params={"marginMode": "isolated"}
        )
        log.info(f"[EMIR] BASARILI id={order.get('id','?')}")
    except Exception as e:
        log.error(f"[EMIR HATA] {sym}: {e}")
        with pos_lock:
            positions.pop(symbol, None)
        return False

    icon = "\U0001f4c8" if yon == "LONG" else "\U0001f4c9"
    tg(f"\U0001f4cb {icon} {sym} {yon}\nGiris: {price:.6f}\nSL: {sl_price:.6f} (-%1.5)\nBTC: {btc_trend}\n\U0001f4ac {neden}")
    log.info(f"[OPEN] {sym} {yon} | BTC:{btc_trend}")
    return True

# ─────────────────────────────────────────────
# ISLEM KAPAT
# ─────────────────────────────────────────────
def close_pos(symbol, reason, exit_price=None):
    global daily_pnl
    with pos_lock:
        pos = positions.pop(symbol, None)
    if not pos: return

    try:
        side = "sell" if pos["signal"] == "LONG" else "buy"
        # Borsadan gercek pozisyon miktarini al
        gercek_amount = None
        try:
            tum_pos = safe_api(exchange.fetch_positions, [symbol])
            if tum_pos:
                for p in tum_pos:
                    if p.get("symbol") == symbol and float(p.get("contracts") or 0) > 0:
                        gercek_amount = float(p["contracts"])
                        break
        except Exception as pe:
            log.warning(f"[KAPAT] Gercek miktar alinamadi: {pe}")
        # Gercek miktar yoksa hesapla
        if not gercek_amount or gercek_amount <= 0:
            gercek_amount = round(POS_SIZE / pos["entry"], 4)
            log.warning(f"[KAPAT] Hesaplanan miktar kullaniliyor: {gercek_amount}")
        else:
            log.info(f"[KAPAT] Borsadan alinan miktar: {gercek_amount}")
        safe_api(exchange.create_order, symbol, "market", side, gercek_amount, None, {
            "reduceOnly": True,
        })
    except Exception as e:
        err_str = str(e)
        if "22002" in err_str or "No position" in err_str:
            log.info(f"[KAPAT] {symbol.split('/')[0]}: Borsada pozisyon yok, bellek temizlendi")
        else:
            log.error(f"[KAPAT] {symbol.split('/')[0]}: {e}")

    if exit_price is None:
        t = safe_api(exchange.fetch_ticker, symbol)
        exit_price = t["last"] if t else pos["entry"]

    pnl, _ = hesap_pnl(pos, exit_price)
    sure    = int((time.time() - pos["open_time"]) / 60)
    daily_pnl += pnl

    sym_base = symbol.split("/")[0].upper()
    with closed_lock:
        recently_closed[sym_base] = time.time()

    try:
        save_trade({
            "symbol": symbol, "signal": pos["signal"],
            "pnl": round(pnl, 4), "tp_pct": pos.get("max_pnl", 0),
            "sl_pct": 1.5, "btc_trend": pos.get("btc_trend", ""),
            "sure_dk": sure, "reason": reason, "neden": pos.get("neden", ""),
        })
        save_trade({
            "symbol": sym_base + "_CLOSED", "signal": "CLOSED",
            "pnl": 0, "reason": "recently_closed", "sure_dk": 0,
        })
    except Exception as e:
        log.error(f"[SAVE] {e}")

    if daily_pnl <= MAX_DAILY_LOSS:
        tg(f"\u26d4 GUNLUK LIMIT! {daily_pnl:+.2f}$")

    icon = "\U0001f7e2" if pnl >= 0 else "\U0001f534"
    tg(f"{icon} {symbol.split('/')[0]} KAPANDI\n{reason}\nPnL: {pnl:+.2f}$ | {sure}dk\nGunluk: {daily_pnl:+.2f}$")

# ─────────────────────────────────────────────
# YÖNETİM — Kademeli kar koruma
# ─────────────────────────────────────────────
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

                max_kar = pos["max_kar"]

                # Stop Loss - pnl_pct kaldıracli oldugu icin %7.5 = fiyatta -%1.5
                SL_PCT = 1.5 * LEVERAGE  # Fiyat %1.5 = kaldıracli %7.5
                if pnl_pct <= -SL_PCT:
                    close_pos(symbol, f"Stop Loss -%{SL_PCT:.1f} (fiyat -%1.5)", price)
                    continue

                # Garantili kar
                sl_garantili = pos.get("sl_garantili", 0.0)
                if sl_garantili > 0 and pnl < sl_garantili:
                    close_pos(symbol, f"Kar garantisi ({sl_garantili:.2f}$)", price)
                    continue

                # Geri cekilme - oransal
                # Max karin %20si geri gelirse VE hala karda ise kapat
                geri_cekilme_limit = max_kar * GERI_CEKILME_PCT
                if (max_kar >= GERI_CEKILME_MIN and
                    (max_kar - pnl) >= geri_cekilme_limit and
                    pnl > 0):
                    close_pos(symbol, f"Geri cekilme %{GERI_CEKILME_PCT*100:.0f} (${max_kar-pnl:.2f})", price)
                    continue

                # Zaman asimi
                if sure >= 120:
                    close_pos(symbol, "Zaman asimi 2 saat", price)
                    continue

                # Kademeli SL
                yeni_garantili = pos.get("sl_garantili", 0.0)
                for kar_seviyesi, garantili in KAR_KADEMELERI:
                    if max_kar >= kar_seviyesi and garantili > yeni_garantili:
                        yeni_garantili = garantili

                if yeni_garantili > pos.get("sl_garantili", 0.0):
                    with pos_lock:
                        if symbol in positions:
                            positions[symbol]["sl_garantili"] = yeni_garantili
                            sym = symbol.split("/")[0]
                            tg(f"\U0001f512 {sym} SL guncellendi: ${yeni_garantili:.2f} garantilendi")

                # BTC trend degisti (cache bypass - kritik karar)
                btc_now, _, _ = get_btc_trend_force()
                if pos["signal"] == "LONG" and btc_now in ["DOWN"] and pnl > 0:
                    close_pos(symbol, "BTC DOWN - kar al", price)
                    continue
                if pos["signal"] == "SHORT" and btc_now in ["UP"] and pnl > 0:
                    close_pos(symbol, "BTC UP - kar al", price)
                    continue

        except Exception as e:
            log.error(f"[MANAGE] {e}")

# ─────────────────────────────────────────────
# TARAYICI
# ─────────────────────────────────────────────
def gunluk_reset_loop():
    """Her gece 00:00'da gunluk PnL'i sifirla"""
    global daily_pnl
    import datetime
    while True:
        try:
            simdi   = datetime.datetime.now()
            yarin   = (simdi + datetime.timedelta(days=1)).replace(
                        hour=0, minute=0, second=5, microsecond=0)
            bekle   = (yarin - simdi).total_seconds()
            log.info(f"[RESET] Gunluk sifirlama {bekle/3600:.1f} saat sonra")
            time.sleep(bekle)
            eski    = daily_pnl
            daily_pnl = 0.0
            tg(f"🔄 Yeni gun! Gunluk PnL sifirlandi.\nDun: {eski:+.2f}$\nBot calismaya devam ediyor.")
            log.info(f"[RESET] Gunluk PnL sifirlandi. Dun: {eski:+.2f}$")
        except Exception as e:
            log.error(f"[RESET] {e}")
            time.sleep(3600)

def scanner_loop():
    global son_bakilan
    time.sleep(60)
    while True:
        try:
            if daily_pnl <= MAX_DAILY_LOSS:
                time.sleep(SCAN_INTERVAL); continue

            btc_trend, btc_price, btc_chg = get_btc_trend()
            log.info(f"[SCAN] BTC:{btc_trend} ${btc_price:,.0f} ({btc_chg:+.1f}%)")

            with pos_lock:
                if len(positions) >= MAX_OPEN:
                    time.sleep(30); continue
                open_syms = set(positions.keys())

            tickers = safe_api(exchange.fetch_tickers)
            if not tickers:
                time.sleep(SCAN_INTERVAL); continue

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
                if qv < MIN_VOL_USDT: continue
                if qv > MAX_VOL_USDT: continue
                if price <= 0: continue
                if price > 5.0: continue

                # On filtre - BTC trend'e gore
                if btc_trend == "UP" and pct < 2: continue
                if btc_trend == "DOWN" and pct > -2: continue
                if btc_trend == "NEUTRAL_LONG" and pct < 1.5: continue
                if btc_trend == "NEUTRAL_SHORT" and pct > -1.5: continue
                if btc_trend == "NEUTRAL": continue  # NEUTRAL'da hic islem acma
                if abs(pct) > 50: continue

                sym_base = sym.upper()
                with closed_lock:
                    if sym_base in recently_closed:
                        if time.time() - recently_closed[sym_base] < 7200:
                            continue

                candidates.append({"symbol": symbol, "pct": pct, "qv": qv})

            # Rotasyon
            yeni = [c for c in candidates if c["symbol"].split("/")[0] not in son_bakilan]
            if len(yeni) < 3:
                son_bakilan = set()
                yeni = candidates

            import random
            random.shuffle(yeni)
            candidates = yeni[:6]

            for c in candidates:
                son_bakilan.add(c["symbol"].split("/")[0])
            if len(son_bakilan) > 30:
                son_bakilan = set(list(son_bakilan)[-15:])

            if not candidates:
                time.sleep(SCAN_INTERVAL); continue

            if btc_trend == "NEUTRAL":
                log.info(f"[SCAN] BTC NEUTRAL - bekleniyor, islem acilmayacak")
                time.sleep(SCAN_INTERVAL)
                continue
            log.info(f"[SCAN] {len(candidates)} aday | BTC:{btc_trend}")

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
                    open_pos(symbol, yon, neden, btc_trend)
                    with pos_lock: open_syms = set(positions.keys())
                else:
                    log.info(f"[PAS] {sym}: {neden}")

                time.sleep(1)

            time.sleep(SCAN_INTERVAL)

        except Exception as e:
            log.error(f"[SCANNER] {e}")
            time.sleep(10)

# ─────────────────────────────────────────────
# HEALTH
# ─────────────────────────────────────────────
def health_server():
    from http.server import HTTPServer, BaseHTTPRequestHandler
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200); self.end_headers()
            with pos_lock:
                pstr = ", ".join(
                    f"{s.split('/')[0]}:{p['signal']}"
                    for s, p in positions.items()
                )
            self.wfile.write(
                f"OK|btc:{get_btc_trend()[0]}|pos:{len(positions)}({pstr})|pnl:{daily_pnl:+.2f}".encode()
            )
        def log_message(self, *a): pass
    HTTPServer(("0.0.0.0", 8080), H).serve_forever()

# ─────────────────────────────────────────────
# COIN BUL
# ─────────────────────────────────────────────
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

# ─────────────────────────────────────────────
# TELEGRAM HANDLER
# ─────────────────────────────────────────────
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
                bot.send_message(msg.chat.id, "\U0001f4cb Acik pozisyon yok."); return
            lines = ["\U0001f4cb POZISYONLAR\n"]
            for sym, pos in positions.items():
                t = safe_api(exchange.fetch_ticker, sym)
                if not t: continue
                price = t["last"]
                pnl, pnl_pct = hesap_pnl(pos, price)
                sure  = int((time.time() - pos["open_time"]) / 60)
                garantili = pos.get("sl_garantili", 0.0)
                max_kar   = pos.get("max_kar", 0.0)
                icon  = "\U0001f7e2" if pnl >= 0 else "\U0001f534"
                sicon = "\U0001f4c8" if pos["signal"] == "LONG" else "\U0001f4c9"
                lines.append(
                    f"{icon} {sicon} {sym.split('/')[0]} {pos['signal']}\n"
                    f"   {pos['entry']:.6f} → {price:.6f}\n"
                    f"   PnL: {pnl:+.2f}$ ({pnl_pct:+.2f}%) | {sure}dk\n"
                    f"   Max kar: ${max_kar:.2f} | Garantili: ${garantili:.2f}\n"
                    f"   BTC trend: {pos.get('btc_trend','?')}\n"
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
                f"\U0001f4ca ISTATISTIK\n\n"
                f"Toplam: {toplam} | Kazanan: {kazan} (%{kazan/toplam*100:.0f})\n"
                f"Net: {net:+.2f}$\nGunluk: {daily_pnl:+.2f}$")
        except Exception as e:
            bot.send_message(msg.chat.id, f"Hata: {e}")
        return

    if "/btc" in lower:
        trend, price, chg = get_btc_trend()
        aciklama = {
            "UP":           "Guclu yukari trend → Sadece LONG",
            "DOWN":         "Guclu asagi trend  → Sadece SHORT",
            "NEUTRAL_LONG": "Hafif yukari → LONG oncelikli",
            "NEUTRAL_SHORT":"Hafif asagi  → SHORT oncelikli",
            "NEUTRAL":      "Belirsiz     → Cok secici",
        }.get(trend, "")
        bot.send_message(msg.chat.id,
            f"BTC: {trend}\n${price:,.0f} ({chg:+.1f}%)\n{aciklama}")
        return

    if "kapat" in lower:
        with pos_lock: syms = list(positions.keys())
        if not syms:
            bot.send_message(msg.chat.id, "Acik pozisyon yok."); return
        kapatildi = False
        for symbol in syms:
            sname = symbol.split("/")[0].upper()
            if sname in text.upper() or "hepsi" in lower or "hepsini" in lower:
                close_pos(symbol, "Kullanici istegi")
                kapatildi = True
        if not kapatildi:
            bot.send_message(msg.chat.id, f"Hangisini? {', '.join(s.split('/')[0] for s in syms)}")
        return

    if any(k in lower for k in ["long ac", "short ac", "long aç", "short aç"]):
        coin = find_coin(text)
        if coin:
            yon   = "LONG" if "long" in lower else "SHORT"
            trend, _, _ = get_btc_trend()
            if not open_pos(coin, yon, "Kullanici istegi", trend):
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
            bot.send_message(msg.chat.id,
                f"\U0001f4ca {sym}\n"
                f"BTC: {trend}\n"
                f"Uyum: {data['uyum_yukari']}/4 yukari | {data['uyum_asagi']}/4 asagi\n"
                f"Hacim 1m: {data['v1m']:.1f}x | 5m: {data['v5m']:.1f}x\n"
                f"RSI: {data['rsi']:.0f} (1h:{data['rsi_1h']:.0f}) | Hareket: {data['pct']:+.1f}%\n\n"
                f"Karar: {yon or 'PAS'}\n{neden}")
        else:
            bot.send_message(msg.chat.id, f"{sym} veri alinamadi.")
        return

    bot.send_message(msg.chat.id,
        "Komutlar:\n"
        "/durum     - Acik pozisyonlar\n"
        "/istatistik - Istatistik\n"
        "/btc       - BTC trend (detayli)\n"
        "COIN       - Analiz\n"
        "COIN long/short ac - Manuel ac\n"
        "hepsini kapat")

# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────
import signal as sig_mod, sys

def shutdown(signum, frame):
    with pos_lock:
        syms = list(positions.keys())
    if syms:
        isimler = ", ".join(s.split("/")[0] for s in syms)
        tg(f"\u23f8 Bot yeniden basliyor...\n{len(syms)} pozisyon borsada acik kaliyor: {isimler}\n\u267b\ufe0f Bot basladiginda otomatik yuklenecek.")
        log.info(f"[SHUTDOWN] {len(syms)} pozisyon acik birakiliyor: {isimler}")
    else:
        tg("\u23f8 Bot yeniden basliyor... Acik pozisyon yok.")
    sys.exit(0)

sig_mod.signal(sig_mod.SIGTERM, shutdown)
sig_mod.signal(sig_mod.SIGINT,  shutdown)


def load_open_positions():
    """Bot baslarken borsadaki acik pozisyonlari yukle."""
    try:
        log.info("[YUKLE] Borsadaki acik pozisyonlar kontrol ediliyor...")
        raw = safe_api(exchange.fetch_positions)
        if not raw:
            log.info("[YUKLE] Acik pozisyon bulunamadi")
            return

        btc_trend, _, _ = get_btc_trend()
        yuklenen = 0

        for pos in raw:
            try:
                contracts = float(pos.get("contracts") or 0)
                if contracts == 0:
                    continue
                symbol = pos.get("symbol", "")
                side   = pos.get("side", "")
                entry  = float(pos.get("entryPrice") or 0)
                if not symbol or not side or entry == 0:
                    continue
                yon      = "LONG" if side == "long" else "SHORT"
                sl_price = entry * (1 - 0.015) if yon == "LONG" else entry * (1 + 0.015)
                with pos_lock:
                    if symbol not in positions:
                        positions[symbol] = {
                            "signal":       yon,
                            "entry":        entry,
                            "sl_price":     sl_price,
                            "sl_garantili": 0.0,
                            "max_pnl":      0.0,
                            "max_kar":      0.0,
                            "neden":        "Onceki oturumdan yuklendi",
                            "btc_trend":    btc_trend,
                            "open_time":    time.time(),
                        }
                        yuklenen += 1
                        log.info(f"[YUKLE] {symbol.split('/')[0]} {yon} @ {entry}")
            except Exception as e:
                log.warning(f"[YUKLE] {e}")

        if yuklenen > 0:
            with pos_lock:
                lines = [f"\u267b\ufe0f {yuklenen} pozisyon yuklendi:\n"]
                for sym, p in positions.items():
                    t     = safe_api(exchange.fetch_ticker, sym)
                    fiyat = t["last"] if t else p["entry"]
                    pnl, pct = hesap_pnl(p, fiyat)
                    ic    = "\U0001f4c8" if p["signal"] == "LONG" else "\U0001f4c9"
                    dk    = "\U0001f7e2" if pnl >= 0 else "\U0001f534"
                    lines.append(f"{dk} {ic} {sym.split('/')[0]} {p['signal']} | PnL: {pnl:+.2f}$")
            tg("\n".join(lines))
        else:
            log.info("[YUKLE] Yuklenen pozisyon yok")

    except Exception as e:
        log.error(f"[YUKLE] {e}")

if __name__ == "__main__":
    print("SADIK TRADER v3 BASLIYOR...")
    load_recently_closed()
    load_open_positions()
    threading.Thread(target=health_server,     daemon=True).start()
    threading.Thread(target=manage_loop,       daemon=True).start()
    threading.Thread(target=scanner_loop,      daemon=True).start()
    threading.Thread(target=gunluk_reset_loop, daemon=True).start()
    tg(
        "\U0001f916 SADIK TRADER v3 — GUNCELLENDI\n\n"
        "BTC Trend Sistemi:\n"
        "⬆️ UP          → Sadece LONG\n"
        "⬇️ DOWN        → Sadece SHORT\n"
        "↗️ NEUTRAL_LONG  → LONG oncelikli\n"
        "↘️ NEUTRAL_SHORT → SHORT oncelikli\n"
        "↔️ NEUTRAL     → 4/4 uyum + yuksek hacim\n\n"
        "✅ EMA9/20/50 + RSI + momentum\n"
        "✅ Gec kalma filtresi korundu\n"
        "✅ Kademeli kar koruma aktif\n\n"
        "/durum /istatistik /btc"
    )
    while True:
        try: bot.infinity_polling(timeout=30, long_polling_timeout=30)
        except Exception as e:
            log.error(f"[BOT] {e}"); time.sleep(5)
