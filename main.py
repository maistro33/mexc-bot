#!/usr/bin/env python3
"""
SADIK TRADER v7 - Temiz & Stabil
Strateji:
- Dip bounce + yeşil mum konfirmasyonu
- ATR bazlı giriş (90sn bekle) + ATR bazlı SL
- BTC trend filtresi (dinamik skor eşiği)
- 6 TP seviyesi (%0.5 adım)
- Akıllı SL yönetimi (TP1→başabaş, TP2→nefes, TP3+→önceki TP)
- Trailing stop %0.60
- Fear&Greed filtresi
- Açılışta pozisyon yükle
"""

import os, time, threading, logging, re, requests
import ccxt
import pandas as pd
import telebot
from supabase import create_client

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("SADIK_V7")

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
SCAN_INTERVAL  = 45

# TP/SL
TP_PCTS        = [0.8, 1.5, 2.5, 3.5, 5.0, 7.0]  # Daha geniş TP'ler
SL_PCT         = 3.0    # Max stop %3
ATR_SL_MULT    = 1.0    # SL = giriş - ATR × 1.0
ATR_GIRIS_MULT = 0.3    # Giriş = fiyat - ATR × 0.3
ATR_GIRIS_SURE = 90     # Kaç saniye bekle
TP_TRAILING    = 0.60   # TP sonrası %0.60 geri dönerse kapat

# Tarama filtreleri
MIN_VOL_USDT  = 500_000
MAX_VOL_USDT  = 20_000_000
MIN_PRICE     = 0.0001
MAX_PRICE     = 5.0
FG_MIN        = 10      # Extreme Fear altında dur
RSI_MAX       = 70      # RSI bu üstünde giriş yapma
PCT_4H_MAX    = 10.0    # 4 saatte %10'dan fazla pompaladıysa geç
PCT_1H_MAX    = 6.0     # 1 saatte %6'dan fazla pompaladıysa geç

# Skor eşikleri (BTC trend'e göre)
SKOR_UP           = 3   # BTC UP → 3/8 yeterli
SKOR_NEUTRAL_LONG = 4   # BTC NEUTRAL_LONG → 4/8
SKOR_NEUTRAL_SHORT= 6   # BTC NEUTRAL_SHORT → 6/8 (çok seçici)
# BTC DOWN → hiç açma

BLACKLIST = {
    "BANANAS31","BSB","JCT","MEGA","ALLO","FTM","MU",
    "TURBO","MOODENG","SUNDOG","NEIRO","HMSTR","CATI","DOGS","MYRO",
    "BOME","SLERF","PNUT","RGTI","SATL","WET","POET",
    "SOXL","SOXS","UVXY","SVIX","KORU","AMC","GME",
    "SHIB","DOGE","PEPE","FLOKI","BONK","WIF","MEME",
    "1000SHIB","1000DOGE","1000PEPE","1000FLOKI","1000BONK","1000WIF",
}

# ════════════════════════════════════════
# STATE
# ════════════════════════════════════════
positions       = {}
pos_lock        = threading.Lock()
daily_pnl       = 0.0
recently_closed = {}
closed_lock     = threading.Lock()

btc_cache      = {"trend": "NEUTRAL_LONG", "price": 0, "chg": 0, "ts": 0}
btc_lock       = threading.Lock()
BTC_CACHE_TTL  = 180

fg_cache       = {"value": 50, "label": "Neutral", "ts": 0}
fg_lock        = threading.Lock()
FG_CACHE_TTL   = 600

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
    "apiKey": BITGET_API,
    "secret": BITGET_SEC,
    "password": BITGET_PASS,
    "enableRateLimit": True,
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
                if wait > 0:
                    time.sleep(wait)
                _last_api = time.time()
            return func(*args, **kwargs)
        except ccxt.RateLimitExceeded:
            time.sleep(10)
        except Exception as e:
            log.warning(f"[API] deneme {attempt+1}: {e}")
            time.sleep(2)
    return None

# ════════════════════════════════════════
# FEAR & GREED
# ════════════════════════════════════════
def get_fear_greed():
    with fg_lock:
        if time.time() - fg_cache["ts"] < FG_CACHE_TTL:
            return fg_cache["value"], fg_cache["label"]
    try:
        r = requests.get("https://api.alternative.me/fng/?limit=1", timeout=5)
        d = r.json()["data"][0]
        v, l = int(d["value"]), d["value_classification"]
        with fg_lock:
            fg_cache.update({"value": v, "label": l, "ts": time.time()})
        log.info(f"[FG] {v} ({l})")
        return v, l
    except:
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
        chg1h  = (price - float(df["c"].iloc[-2]))  / float(df["c"].iloc[-2])  * 100
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
        if time.time() - btc_cache["ts"] < BTC_CACHE_TTL:
            return btc_cache["trend"], btc_cache["price"], btc_cache["chg"]
    trend, price, chg = _hesapla_btc_trend()
    with btc_lock:
        btc_cache.update({"trend": trend, "price": price, "chg": chg, "ts": time.time()})
    log.info(f"[BTC] {trend} ${price:,.0f} ({chg:+.1f}%)")
    return trend, price, chg

# ════════════════════════════════════════
# İNDİKATÖRLER
# ════════════════════════════════════════
def rsi(series, period=14):
    delta = series.diff()
    gain  = delta.clip(lower=0).rolling(period).mean()
    loss  = (-delta.clip(upper=0)).rolling(period).mean()
    rs    = gain / loss.replace(0, 0.001)
    return float((100 - 100 / (1 + rs)).iloc[-1])

def macd_hist(series, fast=12, slow=26, signal=9):
    m = series.ewm(span=fast).mean() - series.ewm(span=slow).mean()
    return float((m - m.ewm(span=signal).mean()).iloc[-1])

def ema_cross_up(series, fast=9, slow=21):
    ef = series.ewm(span=fast).mean()
    es = series.ewm(span=slow).mean()
    return float(ef.iloc[-1]) > float(es.iloc[-1])

def bb_pct(series, period=20, std=2.0):
    sma = series.rolling(period).mean()
    sd  = series.rolling(period).std()
    u   = sma + std * sd
    l   = sma - std * sd
    p   = float(series.iloc[-1])
    return (p - float(l.iloc[-1])) / max(float(u.iloc[-1]) - float(l.iloc[-1]), 0.0001)

def vol_ratio(df, n=3):
    avg = float(df["v"].rolling(20).mean().iloc[-1])
    son = float(df["v"].tail(n).mean())
    return son / max(avg, 0.0001)

def atr14(df):
    h, l, c = df["h"], df["l"], df["c"]
    tr = pd.concat([h-l, (h-c.shift()).abs(), (l-c.shift()).abs()], axis=1).max(axis=1)
    return float(tr.rolling(14).mean().iloc[-1])

# ════════════════════════════════════════
# DİP BOUNCE ANALİZİ
# ════════════════════════════════════════
def dip_bounce(df1h, df15m):
    """
    4 kriter → 0-4 puan
    1. Fiyat son 8h'in alt %40'ında
    2. RSI dip'ten yukarı dönüyor (bounce)
    3. 15m'de kırmızı mumlar sonrası güçlü yeşil mum
    4. Son 20h'in destek bölgesine yakın
    """
    price     = float(df1h["c"].iloc[-1])
    son8_low  = float(df1h["l"].tail(8).min())
    son8_high = float(df1h["h"].tail(8).max())
    aralik    = max(son8_high - son8_low, 0.0001)

    # 1. Dip bölge
    dip_ok = price <= son8_low + aralik * 0.40

    # 2. RSI bounce (son 5 mumun en düşük RSI'ından yukarı dönüş)
    rsi_simdi = rsi(df1h["c"])
    rsi_min = rsi_simdi
    for i in range(2, 7):
        try:
            r = rsi(df1h["c"].iloc[:-i])
            if r < rsi_min:
                rsi_min = r
        except:
            pass
    rsi_bounce_ok = rsi_min < 45 and rsi_simdi > rsi_min + 2

    # 3. İlk yeşil mum (15m)
    son7 = df15m.tail(7)
    kirmizi = sum(1 for _, r in son7.iloc[:-1].iterrows() if float(r["c"]) < float(r["o"]))
    son = son7.iloc[-1]
    yesil_ok = (
        kirmizi >= 2
        and float(son["c"]) > float(son["o"])
        and abs(float(son["c"]) - float(son["o"])) / float(son["o"]) * 100 >= 0.15
    )

    # 4. Destek yakın
    destek = float(df1h["l"].tail(20).quantile(0.15))
    destek_ok = price <= destek * 1.02

    puan = sum([dip_ok, rsi_bounce_ok, yesil_ok, destek_ok])
    detay = {
        "dip":     "✅" if dip_ok     else "❌",
        "bounce":  f"✅ RSI {rsi_min:.0f}→{rsi_simdi:.0f}" if rsi_bounce_ok else f"❌ RSI {rsi_simdi:.0f}",
        "yesil":   "✅" if yesil_ok   else "❌",
        "destek":  "✅" if destek_ok  else "❌",
        "dip_puan": puan,
    }
    return puan, detay

# ════════════════════════════════════════
# SİNYAL SKORU (0-8)
# ════════════════════════════════════════
def sinyal_skoru(symbol):
    try:
        r1h  = safe_api(exchange.fetch_ohlcv, symbol, "1h",  limit=50)
        r15m = safe_api(exchange.fetch_ohlcv, symbol, "15m", limit=40)
        if not r1h  or len(r1h)  < 30: return 0, {}, 0
        if not r15m or len(r15m) < 20: return 0, {}, 0

        df1h  = pd.DataFrame(r1h,  columns=["t","o","h","l","c","v"])
        df15m = pd.DataFrame(r15m, columns=["t","o","h","l","c","v"])

        price  = float(df1h["c"].iloc[-1])
        rsi1h  = rsi(df1h["c"])
        rsi15m = rsi(df15m["c"])
        mac1h  = macd_hist(df1h["c"])
        mac15m = macd_hist(df15m["c"])
        ema_up = ema_cross_up(df1h["c"])
        bbp    = bb_pct(df1h["c"])
        vol1h  = vol_ratio(df1h)
        pct1h  = (price - float(df1h["c"].iloc[-2])) / float(df1h["c"].iloc[-2]) * 100
        pct4h  = (price - float(df1h["c"].iloc[-5])) / float(df1h["c"].iloc[-5]) * 100

        # ── Hard filtreler ──
        if rsi1h  > RSI_MAX:      return 0, {"red": f"RSI yüksek {rsi1h:.0f}"}, price
        if pct4h  > PCT_4H_MAX:   return 0, {"red": f"4h geç {pct4h:.1f}%"},   price
        if pct1h  > PCT_1H_MAX:   return 0, {"red": f"1h geç {pct1h:.1f}%"},   price
        if pct1h  < -4.0:         return 0, {"red": f"1h düşüyor {pct1h:.1f}%"}, price

        skor  = 0
        detay = {}

        # ── 4 Teknik indikatör ──
        # 1. RSI oversold
        if rsi1h < 48:
            skor += 1; detay["rsi"] = f"✅ {rsi1h:.0f}"
        elif rsi15m < 48:
            skor += 1; detay["rsi"] = f"✅ 15m:{rsi15m:.0f}"
        else:
            detay["rsi"] = f"❌ {rsi1h:.0f}"

        # 2. MACD pozitif
        if mac1h > 0:
            skor += 1; detay["macd"] = "✅ 1h+"
        elif mac15m > 0:
            skor += 1; detay["macd"] = "✅ 15m+"
        else:
            detay["macd"] = "❌"

        # 3. EMA yukarı
        if ema_up:
            skor += 1; detay["ema"] = "✅ ↑"
        else:
            detay["ema"] = "❌ ↓"

        # 4. Bollinger alt bölge
        if bbp < 0.55:
            skor += 1; detay["bb"] = f"✅ {bbp:.2f}"
        else:
            detay["bb"] = f"❌ {bbp:.2f}"

        # ── 4 Dip bounce kriteri ──
        dip_puan, dip_detay = dip_bounce(df1h, df15m)
        skor  += dip_puan
        detay.update(dip_detay)

        # Dip yoksa ceza
        if dip_puan == 0:
            skor = max(0, skor - 2)

        # Hacim bilgi
        detay["vol"]   = f"{'✅' if vol1h >= 1.8 else '⚠️'} {vol1h:.1f}x"
        detay["price"] = price
        detay["skor"]  = skor
        return skor, detay, price

    except Exception as e:
        log.warning(f"[SKOR] {symbol}: {e}")
        return 0, {}, 0

# ════════════════════════════════════════
# ATR GİRİŞ BEKLEMESİ
# ════════════════════════════════════════
def atr_giris_bekle(symbol, current_price, atr_val):
    """
    ATR × 0.3 kadar geri çekilmeyi 90sn bekle.
    Gelirse o fiyattan gir, gelmezse mevcut fiyattan gir.
    Fiyat %2 yukarı kaçarsa iptal et.
    """
    hedef    = current_price - atr_val * ATR_GIRIS_MULT
    tavan    = current_price * 1.02
    sym      = symbol.split("/")[0]
    log.info(f"[ATR_GİRİŞ] {sym} hedef:{hedef:.8f} tavan:{tavan:.8f}")

    for _ in range(int(ATR_GIRIS_SURE / 10)):
        time.sleep(10)
        t = safe_api(exchange.fetch_ticker, symbol)
        if not t:
            break
        p = float(t["last"])
        if p >= tavan:
            log.info(f"[ATR_GİRİŞ] {sym} fiyat kaçtı ({p:.8f}), iptal")
            return -1       # iptal
        if p <= hedef:
            log.info(f"[ATR_GİRİŞ] {sym} hedef yakalandı @ {p:.8f}")
            return p        # ideal giriş

    # Süre doldu, mevcut fiyattan gir
    t = safe_api(exchange.fetch_ticker, symbol)
    return float(t["last"]) if t else current_price

# ════════════════════════════════════════
# PNL
# ════════════════════════════════════════
def hesap_pnl(pos, price):
    entry   = pos["entry"]
    pct     = (price - entry) / entry * 100
    pnl     = (price - entry) / entry * POS_SIZE - POS_SIZE * COMMISSION
    return pnl, pct

# ════════════════════════════════════════
# İŞLEM AÇ
# ════════════════════════════════════════
def open_pos(symbol, skor, detay, btc_trend):
    global daily_pnl
    if daily_pnl <= MAX_DAILY_LOSS:
        return False

    sym = symbol.split("/")[0]

    # Anlık fiyat al
    t0 = safe_api(exchange.fetch_ticker, symbol)
    if not t0:
        return False
    current_price = float(t0["last"])

    # ATR hesapla
    try:
        r1h = safe_api(exchange.fetch_ohlcv, symbol, "1h", limit=20)
        df  = pd.DataFrame(r1h, columns=["t","o","h","l","c","v"])
        atr_val = atr14(df)
    except:
        atr_val = current_price * 0.015

    # ATR giriş bekle
    giris = atr_giris_bekle(symbol, current_price, atr_val)
    if giris == -1:
        return False   # fiyat kaçtı
    if giris <= 0:
        giris = current_price

    # SL: ATR × 1.5 ama max %5
    sl_atr = giris - atr_val * ATR_SL_MULT
    sl_pct = giris * (1 - SL_PCT / 100)
    sl     = round(max(sl_atr, sl_pct), 8)

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
                if time.time() - recently_closed[sym_base] < 14400:  # 4 saat
                    return False
        if len(positions) >= MAX_OPEN:
            return False

        # Pozisyon slotunu ayır
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
        try: exchange.set_margin_mode("isolated", symbol)
        except: pass
        try: exchange.set_leverage(LEVERAGE, symbol)
        except: pass

        amount = round(POS_SIZE / giris, 4)
        amount = float(exchange.amount_to_precision(symbol, amount))
        if amount <= 0:
            with pos_lock: positions.pop(symbol, None)
            return False

        order = exchange.create_order(
            symbol, "market", "buy", amount,
            params={"marginMode": "isolated"}
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
    sl_pct_goster = (giris - sl) / giris * 100
    tp_str = "\n".join([f"TP{i+1}: {tp:.8f} ──" for i, tp in enumerate(tps)])
    tg(
        f"📊 #{sym}USDT.P\n"
        f"🏁 LONG - Giriş: {giris:.8f}\n"
        f"🚫 Stop: {sl:.8f} (-%{sl_pct_goster:.1f})\n\n"
        f"💡 Pozisyon Detayları\n{tp_str}\n\n"
        f"📊 Skor: {skor}/8 | BTC: {btc_trend}\n"
        f"RSI:{detay.get('rsi','?')} MACD:{detay.get('macd','?')} "
        f"EMA:{detay.get('ema','?')} BB:{detay.get('bb','?')}\n"
        f"Dip:{detay.get('dip','?')} Bounce:{detay.get('bounce','?')}\n"
        f"Yeşil:{detay.get('yesil','?')} Destek:{detay.get('destek','?')} "
        f"Vol:{detay.get('vol','?')}\n"
        f"ATR: {atr_val:.8f}"
    )
    log.info(f"[AÇIK] {sym} @ {giris:.8f} skor:{skor} atr:{atr_val:.8f}")
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

    # Satış emri
    try:
        amount = pos.get("amount", 0)
        if not amount:
            amount = round(POS_SIZE / pos["entry"], 4)
        safe_api(
            exchange.create_order, symbol, "market", "sell", amount,
            None, {"reduceOnly": True}
        )
    except Exception as e:
        if "22002" not in str(e) and "No position" not in str(e):
            log.error(f"[KAPAT] {symbol.split('/')[0]}: {e}")

    # Çıkış fiyatı
    if exit_price is None:
        t = safe_api(exchange.fetch_ticker, symbol)
        exit_price = float(t["last"]) if t else pos["entry"]

    pnl, pnl_pct = hesap_pnl(pos, exit_price)
    sure = int((time.time() - pos["open_time"]) / 60)
    daily_pnl += pnl

    sym_base = symbol.split("/")[0].upper()
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

    if daily_pnl <= MAX_DAILY_LOSS:
        tg(f"⛔ GÜNLÜK LİMİT! {daily_pnl:+.2f}$")

    icon = "🟢" if pnl >= 0 else "🔴"
    tg(
        f"{icon} {sym_base} KAPANDI\n"
        f"{reason}\n"
        f"PnL: {pnl:+.2f}$ ({pnl_pct:+.1f}%) | {sure}dk\n"
        f"Günlük: {daily_pnl:+.2f}$"
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
                if daily_pnl <= MAX_DAILY_LOSS:
                    close_pos(symbol, "Günlük limit", price)
                    continue

                # ── TP seviyeleri ──
                if tp_idx < len(tps) and price >= tps[tp_idx]:
                    # SL yönetimi
                    if tp_idx == 0:
                        # TP1 → SL başabaşa çek
                        yeni_sl = entry
                    elif tp_idx == 1:
                        # TP2 → SL giriş + ATR×0.5 (nefes alanı)
                        yeni_sl = round(entry + atr_val * 0.5, 8)
                    else:
                        # TP3+ → SL bir önceki TP'ye çek
                        yeni_sl = tps[tp_idx - 1]

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
            if daily_pnl <= MAX_DAILY_LOSS:
                time.sleep(SCAN_INTERVAL)
                continue

            btc_trend, btc_price, btc_chg = get_btc_trend()

            # BTC DOWN → dur
            if btc_trend == "DOWN":
                log.info("[SCAN] BTC DOWN - bekleniyor")
                time.sleep(SCAN_INTERVAL)
                continue

            # BTC trend'e göre skor eşiği
            if btc_trend == "UP":
                esik = SKOR_UP
            elif btc_trend == "NEUTRAL_LONG":
                esik = SKOR_NEUTRAL_LONG
            else:  # NEUTRAL_SHORT
                esik = SKOR_NEUTRAL_SHORT

            # Fear & Greed
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

            # Tüm tickerleri çek
            tickers = safe_api(exchange.fetch_tickers)
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
                if pct < 0.2:      continue  # En az biraz pozitif

                sym_base = sym.upper()
                with closed_lock:
                    if sym_base in recently_closed:
                        if time.time() - recently_closed[sym_base] < 14400:  # 4 saat
                            continue

                candidates.append({"symbol": symbol, "pct": pct, "qv": qv})

            # Momentum'a göre sırala, sonra karıştır (hep aynı coin gelmesin)
            candidates.sort(key=lambda x: x["pct"], reverse=True)
            top4  = candidates[:4]   # En iyi 4'ü koru
            rest  = candidates[4:]   # Gerisini karıştır
            import random
            random.shuffle(rest)
            candidates = (top4 + rest)[:8]

            log.info(
                f"[SCAN] {len(candidates)} aday | "
                f"BTC:{btc_trend} esik:{esik} FG:{fg_val}"
            )

            for c in candidates:
                symbol = c["symbol"]
                sym    = symbol.split("/")[0]

                with pos_lock:
                    if len(positions) >= MAX_OPEN:
                        break
                    if symbol in open_syms:
                        continue

                skor, detay, price = sinyal_skoru(symbol)

                if skor >= esik:
                    log.info(f"[SİNYAL] {sym} skor:{skor}/8 esik:{esik} → GİRİYOR")
                    ok = open_pos(symbol, skor, detay, btc_trend)
                    if ok:
                        with pos_lock:
                            open_syms = set(positions.keys())
                else:
                    log.info(f"[PAS] {sym} skor:{skor}/8 esik:{esik}")

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
            eski = daily_pnl
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
            fg, _ = get_fear_greed()
            trend, _, _ = get_btc_trend()
            with pos_lock:
                pos_str = ",".join(s.split("/")[0] for s in positions)
            self.wfile.write(
                f"OK|btc:{trend}|fg:{fg}|pos:{len(positions)}({pos_str})|pnl:{daily_pnl:+.2f}".encode()
            )

        def log_message(self, *a):
            pass

    HTTPServer(("0.0.0.0", 8080), H).serve_forever()

# ════════════════════════════════════════
# AÇILIŞTA POZİSYON YÜKLE
# ════════════════════════════════════════
def load_open_positions():
    try:
        log.info("[YUKLE] Borsadaki açık pozisyonlar kontrol ediliyor...")
        raw = safe_api(exchange.fetch_positions)
        if not raw:
            log.info("[YUKLE] Açık pozisyon yok")
            return

        btc_trend, _, _ = get_btc_trend()
        yuklenen = 0
        lines    = ["♻️ Önceki pozisyonlar yüklendi:\n"]

        for p in raw:
            try:
                contracts = float(p.get("contracts") or 0)
                if contracts == 0:
                    continue
                symbol = p.get("symbol", "")
                side   = p.get("side", "")
                entry  = float(p.get("entryPrice") or 0)
                if not symbol or side != "long" or entry == 0:
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
                        t = safe_api(exchange.fetch_ticker, symbol)
                        now = float(t["last"]) if t else entry
                        pnl = (now - entry) / entry * POS_SIZE
                        icon = "🟢" if pnl >= 0 else "🔴"
                        lines.append(f"{icon} {symbol.split('/')[0]} @ {entry:.8f} | {pnl:+.2f}$")
                        log.info(f"[YUKLE] {symbol.split('/')[0]} LONG @ {entry}")
            except Exception as e:
                log.warning(f"[YUKLE] {e}")

        if yuklenen > 0:
            tg("\n".join(lines))
        else:
            log.info("[YUKLE] Yüklenecek pozisyon bulunamadı")

    except Exception as e:
        log.error(f"[YUKLE] {e}")

# ════════════════════════════════════════
# TELEGRAM HANDLER
# ════════════════════════════════════════
def find_coin(text):
    words = re.findall(r"[A-Z0-9]+", text.upper())
    try:
        tickers = safe_api(exchange.fetch_tickers)
        if not tickers:
            return None
        for w in words:
            if len(w) < 3:
                continue
            sym = f"{w}/USDT:USDT"
            if sym in tickers and w not in BLACKLIST:
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

    # /durum
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
                price = float(t["last"])
                pnl, pnl_pct = hesap_pnl(pos, price)
                sure   = int((time.time() - pos["open_time"]) / 60)
                tp_idx = pos.get("tp_idx", 0)
                lines.append(
                    f"{'🟢' if pnl>=0 else '🔴'} {sym.split('/')[0]} LONG\n"
                    f"   {pos['entry']:.8f} → {price:.8f}\n"
                    f"   PnL: {pnl:+.2f}$ ({pnl_pct:+.1f}%) | {sure}dk\n"
                    f"   SL: {pos['sl']:.8f} | TP{tp_idx} geçildi\n"
                )
            bot.send_message(msg.chat.id, "\n".join(lines))
        return

    # /istatistik
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
            bot.send_message(
                msg.chat.id,
                f"📊 İSTATİSTİK\n"
                f"Toplam: {toplam} | Kazanan: {kazan} (%{kazan/toplam*100:.0f})\n"
                f"Net PnL: {net:+.2f}$\n"
                f"Günlük: {daily_pnl:+.2f}$"
            )
        except Exception as e:
            bot.send_message(msg.chat.id, f"Hata: {e}")
        return

    # /btc
    if "/btc" in lower:
        trend, price, chg = get_btc_trend()
        fg, fl = get_fear_greed()
        aciklama = {
            "UP":           "⬆️ Güçlü → LONG açar (esik:3)",
            "NEUTRAL_LONG": "↗️ Normal → LONG açar (esik:4)",
            "NEUTRAL_SHORT":"↘️ Zayıf → Çok seçici (esik:6)",
            "DOWN":         "⬇️ Düşüş → BEKLER",
        }.get(trend, "↔️")
        bot.send_message(
            msg.chat.id,
            f"BTC: {trend}\n${price:,.0f} ({chg:+.1f}%)\n{aciklama}\n\n"
            f"Fear&Greed: {fg} ({fl})"
        )
        return

    # kapat
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
        skor, detay, price = sinyal_skoru(coin)
        trend, _, _ = get_btc_trend()
        fg, fl      = get_fear_greed()
        tps = [round(price * (1 + p / 100), 8) for p in TP_PCTS] if price > 0 else []
        sl  = round(price * (1 - SL_PCT / 100), 8) if price > 0 else 0
        tp_str = " | ".join([f"TP{i+1}:{tp:.6f}" for i, tp in enumerate(tps)])
        bot.send_message(
            msg.chat.id,
            f"📊 {sym} | Skor: {skor}/8\n"
            f"RSI:{detay.get('rsi','?')} MACD:{detay.get('macd','?')} "
            f"EMA:{detay.get('ema','?')} BB:{detay.get('bb','?')}\n"
            f"Dip:{detay.get('dip','?')} Bounce:{detay.get('bounce','?')}\n"
            f"Yeşil:{detay.get('yesil','?')} Destek:{detay.get('destek','?')} "
            f"Vol:{detay.get('vol','?')}\n"
            f"BTC: {trend} | FG: {fg} ({fl})\n\n"
            f"{'✅ GİRİLİR' if skor >= SKOR_NEUTRAL_LONG else '❌ PAS'} ({skor}/8)\n"
            f"SL: {sl:.8f}\n{tp_str}"
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
    print("SADIK TRADER v7 BAŞLIYOR...")
    load_open_positions()
    threading.Thread(target=health_server,     daemon=True).start()
    threading.Thread(target=manage_loop,       daemon=True).start()
    threading.Thread(target=scanner_loop,      daemon=True).start()
    threading.Thread(target=gunluk_reset_loop, daemon=True).start()

    fg, fl        = get_fear_greed()
    trend, price, chg = get_btc_trend()

    tg(
        "🤖 SADIK TRADER v7\n\n"
        "📊 Strateji:\n"
        "  ✅ Dip bounce + yeşil mum konfirm\n"
        "  ✅ ATR bazlı giriş (90sn bekle)\n"
        "  ✅ ATR bazlı SL\n"
        "  ✅ BTC dinamik skor eşiği\n"
        "  ✅ TP1→başabaş / TP2→nefes / TP3+→önceki TP\n"
        "  ✅ Trailing stop %0.60\n\n"
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
