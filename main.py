# =========================================================
# BTC SCALP PRO V2
# Bitget | 20x Kaldıraç | Telegram Bildirim
# Geliştirici notu: 20 USDT sermaye ile 20x kaldıraç
# yüksek risk içerir. Lütfen dikkatli kullanın.
# =========================================================

import ccxt
import time
import os
import threading
import pandas as pd
import numpy as np
import telebot

from supabase import create_client
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import cross_val_score

# =========================================================
# TELEGRAM
# =========================================================

TOKEN   = os.getenv("TELE_TOKEN")
CHAT_ID = int(os.getenv("MY_CHAT_ID"))
bot     = telebot.TeleBot(TOKEN)

# =========================================================
# SUPABASE
# =========================================================

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase     = create_client(SUPABASE_URL, SUPABASE_KEY)

# =========================================================
# EXCHANGE — Bitget Perpetual
# =========================================================

exchange = ccxt.bitget({
    "apiKey":   os.getenv("BITGET_API"),
    "secret":   os.getenv("BITGET_SEC"),
    "password": os.getenv("BITGET_PASS"),
    "enableRateLimit": True,
    "options": {"defaultType": "swap"}
})

# =========================================================
# AYARLAR
# =========================================================

SYMBOL          = "BTC/USDT:USDT"
TIMEFRAME_1M    = "1m"
TIMEFRAME_5M    = "5m"
TIMEFRAME_15M   = "15m"

MARGIN          = 1.5        # USDT — 20 USDT sermayede max %7.5 risk per işlem
LEVERAGE        = 20

# --- Kâr / Zarar Hedefleri ---
TP1_USDT        = 0.40       # İlk kâr hedefi (net)
TP2_USDT        = 0.90       # İkinci kâr hedefi
MEGA_TP_USDT    = 1.80       # Büyük hareket hedefi
STOP_LOSS_USDT  = -0.40      # Maksimum zarar

# --- Trailing Stop ---
TRAIL_TRIGGER   = 0.50       # Bu kârdan sonra trailing başlar
TRAIL_STOP      = 0.25       # Kârın bu altına düşerse kapat

# --- Dinamik Profit Lock ---
LOCK_LEVELS = [
    (0.30, 0.10),   # max_pnl >= 0.30 → min 0.10 koru
    (0.60, 0.30),   # max_pnl >= 0.60 → min 0.30 koru
    (1.00, 0.55),   # max_pnl >= 1.00 → min 0.55 koru
    (1.50, 0.90),   # max_pnl >= 1.50 → min 0.90 koru
]

# --- Günlük Zarar Limiti ---
MAX_DAILY_LOSS  = -3.0       # Gün içinde bu kadar zarar ederse bot durur
MAX_DAILY_TRADES = 20        # Gün içinde max işlem sayısı

# --- Sinyal Filtreleri ---
MIN_VOLUME_RATIO    = 1.40
MIN_VOLATILITY      = 0.06
MIN_MOMENTUM        = 0.12
MIN_AI_SCORE        = 70
MIN_FINAL_SCORE     = 72
MIN_TRAIN_SAMPLES   = 60

# =========================================================
# GLOBAL DURUM
# =========================================================

bot_position    = None
ai_model        = None
ai_accuracy     = 0.0

daily_pnl       = 0.0
daily_trades    = 0
day_start       = time.strftime("%Y-%m-%d")

LAST_API_CALL   = 0
_lock           = threading.Lock()   # Thread-safe lock

# =========================================================
# YARDIMCI: API GÜVENLI ÇAĞRI
# =========================================================

def safe_api(func, *args, **kwargs):
    global LAST_API_CALL
    for attempt in range(5):
        try:
            now  = time.time()
            wait = 0.35 - (now - LAST_API_CALL)
            if wait > 0:
                time.sleep(wait)
            LAST_API_CALL = time.time()
            return func(*args, **kwargs)
        except ccxt.RateLimitExceeded:
            time.sleep(3 * (attempt + 1))
        except ccxt.NetworkError:
            time.sleep(2)
        except Exception as e:
            print(f"[API] Hata ({attempt+1}/5): {e}")
            time.sleep(2)
    return None

# =========================================================
# YARDIMCI: GÜN SIFIRLA
# =========================================================

def check_day_reset():
    global daily_pnl, daily_trades, day_start
    today = time.strftime("%Y-%m-%d")
    if today != day_start:
        daily_pnl    = 0.0
        daily_trades = 0
        day_start    = today
        bot.send_message(CHAT_ID, "🌅 Yeni gün — günlük sayaçlar sıfırlandı.")

# =========================================================
# VERİ ÇEK
# =========================================================

def get_ohlcv(tf="1m", limit=150):
    try:
        raw = safe_api(exchange.fetch_ohlcv, SYMBOL, timeframe=tf, limit=limit)
        if not raw or len(raw) < 30:
            return None
        df = pd.DataFrame(raw, columns=["t","o","h","l","c","v"])
        return df
    except Exception as e:
        print(f"[DATA] {e}")
        return None

# =========================================================
# TEKNİK GÖSTERGELER
# =========================================================

def compute_indicators(df):
    c = df["c"]
    h = df["h"]
    l = df["l"]
    v = df["v"]

    # EMA
    ema9  = c.ewm(span=9,  adjust=False).mean()
    ema20 = c.ewm(span=20, adjust=False).mean()
    ema50 = c.ewm(span=50, adjust=False).mean()

    # RSI
    delta = c.diff()
    gain  = delta.clip(lower=0).rolling(14).mean()
    loss  = (-delta.clip(upper=0)).rolling(14).mean()
    rs    = gain / loss.replace(0, np.nan)
    rsi   = 100 - (100 / (1 + rs))

    # MACD
    macd_line   = c.ewm(span=12, adjust=False).mean() - c.ewm(span=26, adjust=False).mean()
    signal_line = macd_line.ewm(span=9, adjust=False).mean()
    macd_hist   = macd_line - signal_line

    # Bollinger Bantları
    bb_mid   = c.rolling(20).mean()
    bb_std   = c.rolling(20).std()
    bb_upper = bb_mid + 2 * bb_std
    bb_lower = bb_mid - 2 * bb_std
    bb_width = (bb_upper - bb_lower) / bb_mid * 100

    # ATR
    tr = pd.concat([
        h - l,
        (h - c.shift()).abs(),
        (l - c.shift()).abs()
    ], axis=1).max(axis=1)
    atr = tr.rolling(14).mean()

    # Hacim
    vol_avg   = v.rolling(20).mean()
    vol_ratio = v / vol_avg.replace(0, np.nan)

    # Momentum & Volatilite
    move_1 = (c.iloc[-1] - c.iloc[-2]) / c.iloc[-2] * 100
    move_3 = (c.iloc[-1] - c.iloc[-4]) / c.iloc[-4] * 100
    move_5 = (c.iloc[-1] - c.iloc[-6]) / c.iloc[-6] * 100

    price       = c.iloc[-1]
    low20       = c.tail(20).min()
    high20      = c.tail(20).max()
    range20     = high20 - low20

    volatility  = (h.iloc[-1] - l.iloc[-1]) / price * 100

    return {
        "price":       price,
        "ema9":        ema9.iloc[-1],
        "ema20":       ema20.iloc[-1],
        "ema50":       ema50.iloc[-1],
        "rsi":         rsi.iloc[-1],
        "macd_hist":   macd_hist.iloc[-1],
        "bb_upper":    bb_upper.iloc[-1],
        "bb_lower":    bb_lower.iloc[-1],
        "bb_width":    bb_width.iloc[-1],
        "atr":         atr.iloc[-1],
        "vol_ratio":   vol_ratio.iloc[-1],
        "move_1":      move_1,
        "move_3":      move_3,
        "move_5":      move_5,
        "momentum":    abs(move_3),
        "volatility":  volatility,
        "low20":       low20,
        "high20":      high20,
        "range20":     range20,
        "move_from_low":  (price - low20) / low20 * 100  if low20 > 0 else 0,
        "move_from_high": (high20 - price) / high20 * 100 if high20 > 0 else 0,
    }

# =========================================================
# AI: VERİ YÜKLE
# =========================================================

def load_ai_data():
    try:
        rows = supabase.table("trades").select("*").execute()
        data = rows.data
        if not data:
            return None

        records = []
        for r in data:
            try:
                records.append({
                    "momentum":    float(r.get("momentum")    or 0),
                    "vol_ratio":   float(r.get("volume_ratio") or 0),
                    "volatility":  float(r.get("volatility")  or 0),
                    "move_1":      float(r.get("move_1")      or 0),
                    "move_3":      float(r.get("move_3")      or 0),
                    "move_5":      float(r.get("move_5")      or 0),
                    "rsi":         float(r.get("rsi")         or 50),
                    "macd_hist":   float(r.get("macd_hist")   or 0),
                    "bb_width":    float(r.get("bb_width")    or 0),
                    "result":      1 if float(r.get("pnl") or 0) > 0 else 0
                })
            except:
                pass

        if len(records) < MIN_TRAIN_SAMPLES:
            return None

        return pd.DataFrame(records)

    except Exception as e:
        print(f"[AI-LOAD] {e}")
        return None

# =========================================================
# AI: EĞİT
# =========================================================

FEATURE_COLS = [
    "momentum","vol_ratio","volatility",
    "move_1","move_3","move_5",
    "rsi","macd_hist","bb_width"
]

def train_ai():
    global ai_model, ai_accuracy
    try:
        df = load_ai_data()
        if df is None:
            print("[AI] Yetersiz veri, eğitim atlandı.")
            return

        X = df[FEATURE_COLS]
        y = df["result"]

        model = RandomForestClassifier(
            n_estimators=400,
            max_depth=6,
            min_samples_leaf=5,
            random_state=42,
            class_weight="balanced"
        )

        # Cross-validation ile gerçek accuracy ölç
        scores = cross_val_score(model, X, y, cv=5, scoring="accuracy")
        ai_accuracy = round(scores.mean() * 100, 1)

        model.fit(X, y)
        ai_model = model

        print(f"[AI] Eğitim tamamlandı — CV Accuracy: %{ai_accuracy}")
        bot.send_message(CHAT_ID, f"🧠 AI Güncellendi\n📊 Doğruluk: %{ai_accuracy}\n📁 Veri: {len(df)} işlem")

    except Exception as e:
        print(f"[AI-TRAIN] {e}")

# =========================================================
# AI: SKOR HESAPLA
# =========================================================

def get_ai_score(ind):
    if ai_model is None:
        return 55  # Model yokken düşük tut, işlem açmasın

    try:
        feat = pd.DataFrame([[
            ind["momentum"],
            ind["vol_ratio"],
            ind["volatility"],
            ind["move_1"],
            ind["move_3"],
            ind["move_5"],
            ind["rsi"],
            ind["macd_hist"],
            ind["bb_width"],
        ]], columns=FEATURE_COLS)

        proba = ai_model.predict_proba(feat)[0]
        return round(max(proba) * 100)

    except Exception as e:
        print(f"[AI-SCORE] {e}")
        return 50

# =========================================================
# MULTI-AGENT SİSTEM V2
# =========================================================

def agent_trend(ind, ind5, ind15):
    """Trend uyumu: 1m, 5m, 15m hizalı mı?"""
    score = 0
    price = ind["price"]

    # 1m trend
    if price > ind["ema20"]:   score += 15
    if ind["ema9"] > ind["ema20"]: score += 10

    # 5m trend
    if ind5["price"] > ind5["ema20"]: score += 20
    if ind5["ema9"] > ind5["ema20"]:  score += 10

    # 15m trend (en ağırlıklı)
    if ind15["price"] > ind15["ema20"]: score += 25
    if ind15["ema9"] > ind15["ema20"]:  score += 20

    return min(score, 100)

def agent_trend_short(ind, ind5, ind15):
    score = 0
    price = ind["price"]

    if price < ind["ema20"]:   score += 15
    if ind["ema9"] < ind["ema20"]: score += 10
    if ind5["price"] < ind5["ema20"]: score += 20
    if ind5["ema9"] < ind5["ema20"]:  score += 10
    if ind15["price"] < ind15["ema20"]: score += 25
    if ind15["ema9"] < ind15["ema20"]:  score += 20

    return min(score, 100)

def agent_momentum(ind):
    """Momentum & hacim gücü"""
    score = 40
    if ind["momentum"] >= 0.20:  score += 20
    if ind["momentum"] >= 0.35:  score += 15
    if ind["vol_ratio"] >= 1.5:  score += 15
    if ind["vol_ratio"] >= 2.0:  score += 10
    return min(score, 100)

def agent_rsi(ind, signal):
    """RSI filtreleme — aşırı alım/satım kontrolü"""
    rsi = ind["rsi"]
    if signal == "LONG":
        if rsi < 30:   return 95   # Aşırı satım, güçlü LONG
        if rsi < 50:   return 80
        if rsi < 65:   return 65
        if rsi < 75:   return 40
        return 20                  # Aşırı alım, tehlikeli LONG
    else:
        if rsi > 70:   return 95
        if rsi > 50:   return 80
        if rsi > 35:   return 65
        if rsi > 25:   return 40
        return 20

def agent_position(ind, signal):
    """Geç giriş tespiti"""
    score = 100
    if signal == "LONG":
        mfl = ind["move_from_low"]
        if mfl > 1.5:  score -= 60
        elif mfl > 1.0: score -= 35
        elif mfl > 0.7: score -= 15
    else:
        mfh = ind["move_from_high"]
        if mfh > 1.5:  score -= 60
        elif mfh > 1.0: score -= 35
        elif mfh > 0.7: score -= 15
    return max(score, 0)

def agent_risk_reward(ind, signal):
    """Risk/Ödül oranı"""
    if signal == "LONG":
        risk   = max(ind["move_from_low"], 0.1)
        reward = max(2.0 - ind["move_from_low"], 0.1)
    else:
        risk   = max(ind["move_from_high"], 0.1)
        reward = max(2.0 - ind["move_from_high"], 0.1)

    rr = reward / risk
    if rr >= 3:   return 100
    if rr >= 2:   return 85
    if rr >= 1.5: return 70
    if rr >= 1:   return 50
    return 20

def agent_macd(ind, signal):
    """MACD histogram yönü"""
    hist = ind["macd_hist"]
    if signal == "LONG":
        if hist > 0:   return 80
        if hist > -5:  return 55
        return 30
    else:
        if hist < 0:   return 80
        if hist < 5:   return 55
        return 30

def decision(ind, ind5, ind15, signal, ai_score):
    """Tüm ajanları birleştir"""
    if signal == "LONG":
        t = agent_trend(ind, ind5, ind15)
    else:
        t = agent_trend_short(ind, ind5, ind15)

    m   = agent_momentum(ind)
    r   = agent_rsi(ind, signal)
    p   = agent_position(ind, signal)
    rr  = agent_risk_reward(ind, signal)
    mac = agent_macd(ind, signal)

    # Ağırlıklı ortalama
    final = round(
        ai_score * 0.25 +
        t        * 0.20 +
        m        * 0.15 +
        r        * 0.15 +
        p        * 0.10 +
        rr       * 0.10 +
        mac      * 0.05
    )

    return final, {"trend": t, "momentum": m, "rsi": r,
                   "position": p, "rr": rr, "macd": mac}

# =========================================================
# ANALİZ
# =========================================================

def analyze():
    df1  = get_ohlcv(TIMEFRAME_1M)
    df5  = get_ohlcv(TIMEFRAME_5M)
    df15 = get_ohlcv(TIMEFRAME_15M)

    if df1 is None or df5 is None or df15 is None:
        return None

    try:
        ind   = compute_indicators(df1)
        ind5  = compute_indicators(df5)
        ind15 = compute_indicators(df15)
    except Exception as e:
        print(f"[IND] {e}")
        return None

    # --- Temel Filtreler ---
    if ind["volatility"] < MIN_VOLATILITY:  return None
    if ind["vol_ratio"]  < MIN_VOLUME_RATIO: return None
    if ind["momentum"]   < MIN_MOMENTUM:    return None

    # --- RSI Aşırı Bölge Kontrolü ---
    rsi = ind["rsi"]
    if not (20 < rsi < 80):
        return None  # Çok aşırı bölgelerde işlem açma

    # --- Sinyal Belirle ---
    price  = ind["price"]
    signal = None

    long_cond = (
        price > ind["ema20"]
        and ind["ema9"] > ind["ema20"]
        and ind5["price"] > ind5["ema20"]
        and ind15["price"] > ind15["ema20"]
        and ind["move_1"] > 0
        and ind["macd_hist"] > -10
        and rsi < 70
    )

    short_cond = (
        price < ind["ema20"]
        and ind["ema9"] < ind["ema20"]
        and ind5["price"] < ind5["ema20"]
        and ind15["price"] < ind15["ema20"]
        and ind["move_1"] < 0
        and ind["macd_hist"] < 10
        and rsi > 30
    )

    if long_cond:
        signal = "LONG"
    elif short_cond:
        signal = "SHORT"
    else:
        return None

    # --- Fake Breakout Filtresi ---
    last5_avg = df1["c"].tail(5).mean()
    if signal == "LONG" and price < last5_avg:  return None
    if signal == "SHORT" and price > last5_avg: return None

    # --- AI Skoru ---
    ai_score = get_ai_score(ind)
    if ai_score < MIN_AI_SCORE:
        return None

    # --- Multi-Agent Karar ---
    final_score, agents = decision(ind, ind5, ind15, signal, ai_score)

    if final_score < MIN_FINAL_SCORE:
        return None

    return {
        "signal":       signal,
        "price":        price,
        "ai_score":     ai_score,
        "final_score":  final_score,
        "agents":       agents,
        "momentum":     ind["momentum"],
        "vol_ratio":    ind["vol_ratio"],
        "volatility":   ind["volatility"],
        "rsi":          ind["rsi"],
        "move_1":       ind["move_1"],
        "move_3":       ind["move_3"],
        "move_5":       ind["move_5"],
        "macd_hist":    ind["macd_hist"],
        "bb_width":     ind["bb_width"],
        "atr":          ind["atr"],
    }

# =========================================================
# POZİSYON BOYUTU
# =========================================================

def get_real_size():
    try:
        positions = safe_api(exchange.fetch_positions, [SYMBOL])
        if not positions:
            return 0
        for p in positions:
            size = abs(float(p.get("contracts") or p.get("size") or 0))
            if size > 0:
                return size
    except Exception as e:
        print(f"[SIZE] {e}")
    return 0

# =========================================================
# İŞLEM AÇ
# =========================================================

def open_trade(data):
    global bot_position, daily_trades

    with _lock:
        if bot_position:
            return
        if get_real_size() > 0:
            return

        check_day_reset()

        # --- Günlük Limitler ---
        if daily_pnl <= MAX_DAILY_LOSS:
            bot.send_message(CHAT_ID, "🛑 Günlük zarar limitine ulaşıldı. Bot bugün işlem açmıyor.")
            return
        if daily_trades >= MAX_DAILY_TRADES:
            bot.send_message(CHAT_ID, "🛑 Günlük max işlem sayısına ulaşıldı.")
            return

        try:
            side = "buy" if data["signal"] == "LONG" else "sell"

            safe_api(exchange.set_leverage, LEVERAGE, SYMBOL)

            ticker = safe_api(exchange.fetch_ticker, SYMBOL)
            if not ticker:
                return

            price  = ticker["last"]
            amount = (MARGIN * LEVERAGE) / price
            amount = float(exchange.amount_to_precision(SYMBOL, amount))

            order = safe_api(exchange.create_market_order, SYMBOL, side, amount)
            if not order:
                return

            entry = float(order.get("average") or price)

            bot_position = {
                "type":      data["signal"],
                "entry":     entry,
                "max_pnl":   0.0,
                "tp1_done":  False,
                "tp2_done":  False,
                "open_time": time.time(),
                "ai_score":  data["ai_score"],
                "features": {k: data[k] for k in [
                    "momentum","vol_ratio","volatility",
                    "move_1","move_3","move_5",
                    "rsi","macd_hist","bb_width"
                ]}
            }

            daily_trades += 1

            ag = data["agents"]
            bot.send_message(CHAT_ID, f"""
🚀 İŞLEM AÇILDI

📈 Yön: {data['signal']}
💰 Giriş: {round(entry, 2)} USDT
⚡ Kaldıraç: {LEVERAGE}x
🧠 AI Skoru: %{data['ai_score']}
🎯 Final Skor: %{data['final_score']}

📊 Ajan Skorları:
  Trend:    %{ag['trend']}
  Momentum: %{ag['momentum']}
  RSI:      %{ag['rsi']}
  Pozisyon: %{ag['position']}
  R/R:      %{ag['rr']}
  MACD:     %{ag['macd']}

📉 RSI: {round(data['rsi'], 1)}
🌪 Volatilite: {round(data['volatility'], 2)}%
📦 Hacim Oranı: {round(data['vol_ratio'], 2)}x
📅 Günlük İşlem: {daily_trades}/{MAX_DAILY_TRADES}
""")

        except Exception as e:
            print(f"[OPEN] {e}")

# =========================================================
# İŞLEM KAYDET
# =========================================================

def save_trade(pnl):
    try:
        if not bot_position:
            return
        f = bot_position["features"]
        supabase.table("trades").insert({
            "symbol":       SYMBOL,
            "signal":       bot_position["type"],
            "momentum":     f["momentum"],
            "volume_ratio": f["vol_ratio"],
            "volatility":   f["volatility"],
            "move_1":       f["move_1"],
            "move_3":       f["move_3"],
            "move_5":       f["move_5"],
            "rsi":          f["rsi"],
            "macd_hist":    f["macd_hist"],
            "bb_width":     f["bb_width"],
            "pnl":          pnl,
            "ai_score":     bot_position["ai_score"],
        }).execute()
    except Exception as e:
        print(f"[SAVE] {e}")

# =========================================================
# İŞLEM KAPAT
# =========================================================

def close_trade(reason):
    global bot_position, daily_pnl

    try:
        if not bot_position:
            return

        side = "sell" if bot_position["type"] == "LONG" else "buy"
        size = get_real_size()

        if size > 0:
            safe_api(
                exchange.create_market_order,
                SYMBOL, side, size,
                params={"reduceOnly": True}
            )

        ticker = safe_api(exchange.fetch_ticker, SYMBOL)
        pnl    = 0.0

        if ticker:
            cp = ticker["last"]
            if bot_position["type"] == "LONG":
                pnl_pct = (cp - bot_position["entry"]) / bot_position["entry"] * 100
            else:
                pnl_pct = (bot_position["entry"] - cp) / bot_position["entry"] * 100
            pnl = (pnl_pct / 100) * (MARGIN * LEVERAGE)

        daily_pnl += pnl

        save_trade(pnl)
        train_ai()

        emoji = "✅" if pnl > 0 else "❌"
        bot.send_message(CHAT_ID, f"""
{emoji} İŞLEM KAPANDI

📌 Neden: {reason}
💰 PNL: {round(pnl, 3)} USDT
📅 Günlük PNL: {round(daily_pnl, 3)} USDT
""")

        bot_position = None

    except Exception as e:
        print(f"[CLOSE] {e}")

# =========================================================
# POZİSYON YÖNETİCİSİ
# =========================================================

def manage():
    global bot_position

    while True:
        try:
            if not bot_position:
                time.sleep(3)
                continue

            # Manuel kapatma kontrolü
            real_size = get_real_size()
            if real_size <= 0:
                save_trade(0)
                bot.send_message(CHAT_ID, "🧠 Manuel kapatma tespit edildi.")
                bot_position = None
                time.sleep(2)
                continue

            ticker = safe_api(exchange.fetch_ticker, SYMBOL)
            if not ticker:
                time.sleep(2)
                continue

            price = ticker["last"]

            # PNL hesapla
            if bot_position["type"] == "LONG":
                pnl_pct = (price - bot_position["entry"]) / bot_position["entry"] * 100
            else:
                pnl_pct = (bot_position["entry"] - price) / bot_position["entry"] * 100

            pnl = (pnl_pct / 100) * (MARGIN * LEVERAGE)

            # Max PNL güncelle
            if pnl > bot_position["max_pnl"]:
                bot_position["max_pnl"] = pnl
            max_pnl = bot_position["max_pnl"]

            # --- Dinamik Profit Lock ---
            for threshold, floor in reversed(LOCK_LEVELS):
                if max_pnl >= threshold and pnl <= floor:
                    close_trade(f"PROFIT LOCK (max:{round(max_pnl,2)}, şu an:{round(pnl,2)})")
                    break
            else:

                # --- Stop Loss ---
                if pnl <= STOP_LOSS_USDT:
                    close_trade("STOP LOSS")
                    continue

                # --- Trailing Stop ---
                if max_pnl >= TRAIL_TRIGGER and pnl <= TRAIL_STOP:
                    close_trade("TRAILING STOP")
                    continue

                # --- TP1 Bildirim ---
                if pnl >= TP1_USDT and not bot_position["tp1_done"]:
                    bot_position["tp1_done"] = True
                    bot.send_message(CHAT_ID, f"✅ TP1 HIT — {round(pnl,2)} USDT")

                # --- TP2 Bildirim ---
                if pnl >= TP2_USDT and not bot_position["tp2_done"]:
                    bot_position["tp2_done"] = True
                    bot.send_message(CHAT_ID, f"🎯 TP2 HIT — {round(pnl,2)} USDT")

                # --- Mega TP ---
                if pnl >= MEGA_TP_USDT:
                    close_trade("MEGA TAKE PROFIT")
                    continue

                # --- Zaman Limiti (90 dk) ---
                elapsed = time.time() - bot_position["open_time"]
                if elapsed > 90 * 60 and pnl > 0:
                    close_trade("ZAMAN LİMİTİ (kârda)")
                    continue

            time.sleep(3)

        except Exception as e:
            print(f"[MANAGE] {e}")
            time.sleep(5)

# =========================================================
# TARAYICI
# =========================================================

def scanner():
    global bot_position

    while True:
        try:
            check_day_reset()

            # Günlük zarar limiti
            if daily_pnl <= MAX_DAILY_LOSS:
                time.sleep(60)
                continue

            if bot_position:
                time.sleep(5)
                continue

            result = analyze()

            if not result:
                time.sleep(8)
                continue

            open_trade(result)
            time.sleep(15)

        except Exception as e:
            print(f"[SCANNER] {e}")
            time.sleep(5)

# =========================================================
# BAŞLAT
# =========================================================

print("Bot başlatılıyor...")
train_ai()

threading.Thread(target=scanner, daemon=True).start()
threading.Thread(target=manage,  daemon=True).start()

bot.send_message(CHAT_ID, f"""
🚀 BTC SCALP PRO V2 BAŞLADI

📊 Sembol: {SYMBOL}
⚡ Kaldıraç: {LEVERAGE}x
💰 Margin/İşlem: {MARGIN} USDT
🧠 AI Modeli: {'Aktif' if ai_model else 'Veri bekleniyor'}
🎯 Min Final Skor: %{MIN_FINAL_SCORE}

🛑 Stop Loss: {STOP_LOSS_USDT} USDT
✅ TP1: {TP1_USDT} USDT
🎯 TP2: {TP2_USDT} USDT
🚀 Mega TP: {MEGA_TP_USDT} USDT
📅 Günlük Zarar Limiti: {MAX_DAILY_LOSS} USDT
""")

# =========================================================
# POLLING
# =========================================================

while True:
    try:
        bot.infinity_polling(timeout=30, long_polling_timeout=30)
    except Exception as e:
        print(f"[POLLING] {e}")
        time.sleep(5)
