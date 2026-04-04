import os
import time
import ccxt
import telebot
import threading
import pandas as pd
import joblib
import numpy as np

# ===== SETTINGS =====
AGGR_VOLUME = 200_000
TOP_COINS = 30
MAX_TRADES = 2

TP1_USDT = 0.25
TRAIL_GAP = 0.01

AI_CONFIDENCE = 0.60   # 💣 sadece güçlü sinyal
MIN_VOLATILITY = 0.002 # 💣 düşük hareket yok

# ===== TELEGRAM =====
bot = telebot.TeleBot(os.getenv("TELE_TOKEN"))
CHAT_ID = os.getenv("MY_CHAT_ID")

# ===== EXCHANGE =====
exchange = ccxt.bitget({
    "apiKey": os.getenv("BITGET_API"),
    "secret": os.getenv("BITGET_SEC"),
    "password": os.getenv("BITGET_PASS") or "Berfin33",
    "options": {"defaultType": "swap"},
    "enableRateLimit": True
})

exchange.load_markets()

# ===== AUTO AI TRAIN =====
def train_model():
    from xgboost import XGBClassifier

    print("🤖 MODEL YOK → TRAIN")

    data = []
    symbols = ["BTC/USDT:USDT", "ETH/USDT:USDT"]

    for sym in symbols:
        ohlcv = exchange.fetch_ohlcv(sym, "5m", limit=300)

        for c in ohlcv:
            t,o,h,l,close,v = c
            vol = (h-l)/close if close else 0
            data.append([o,h,l,close,v,vol])

    df = pd.DataFrame(data, columns=[
        "open","high","low","close","volume","volatility"
    ])

    df["return"] = df["close"].pct_change()
    df["target"] = (df["return"].shift(-1) > 0).astype(int)
    df = df.dropna()

    X = df[["open","high","low","close","volume","volatility"]]
    y = df["target"]

    model = XGBClassifier(n_estimators=120)
    model.fit(X, y)

    joblib.dump(model, "ai_model.pkl")
    print("✅ MODEL HAZIR")

# ===== LOAD =====
if not os.path.exists("ai_model.pkl"):
    train_model()

model = joblib.load("ai_model.pkl")

# ===== GLOBAL =====
active_trades = set()
trade_state = {}
lock = threading.Lock()

# ===== SAFE =====
def safe(x):
    try: return float(x)
    except: return 0.0

def safe_api(call):
    try:
        return call()
    except:
        return None

# ===== TREND =====
def get_trend(sym):
    c = exchange.fetch_ohlcv(sym, "5m", limit=20)
    closes = [x[4] for x in c]
    avg = sum(closes)/len(closes)
    return "up" if closes[-1] > avg else "down"

# ===== AI =====
def ai_predict(sym):
    try:
        ohlcv = exchange.fetch_ohlcv(sym, "5m", limit=2)
        if not ohlcv:
            return None, 0

        t,o,h,l,c,v = ohlcv[-1]
        vol = (h-l)/c if c else 0

        # 💣 volatility filter
        if vol < MIN_VOLATILITY:
            return None, 0

        data = [[o,h,l,c,v,vol]]

        proba = model.predict_proba(data)[0]
        confidence = max(proba)

        if confidence < AI_CONFIDENCE:
            return None, confidence

        direction = "long" if proba[1] > proba[0] else "short"

        # 💣 trend filter
        trend = get_trend(sym)
        if direction == "long" and trend != "up":
            return None, confidence
        if direction == "short" and trend != "down":
            return None, confidence

        return direction, confidence

    except Exception as e:
        print("AI ERROR:", e)
        return None, 0

# ===== SYMBOLS =====
def get_symbols():
    t = safe_api(lambda: exchange.fetch_tickers())
    if not t:
        return []

    f = [(s, safe(d.get("quoteVolume"))) for s,d in t.items() if ":USDT" in s]
    f = [x for x in f if x[1] >= AGGR_VOLUME]
    f.sort(key=lambda x: x[1], reverse=True)

    return [x[0] for x in f[:TOP_COINS]]

# ===== ENGINE =====
def engine():
    while True:
        try:
            positions = safe_api(lambda: exchange.fetch_positions())
            open_count = 0

            if positions:
                for p in positions:
                    if safe(p.get("contracts")) > 0:
                        open_count += 1

            for sym in get_symbols():

                if open_count >= MAX_TRADES:
                    break

                if sym in trade_state:
                    continue

                ticker = safe_api(lambda: exchange.fetch_ticker(sym))
                if not ticker:
                    continue

                price = safe(ticker["last"])
                if price <= 0:
                    continue

                direction, conf = ai_predict(sym)
                if not direction:
                    continue

                with lock:
                    lev = 10

                    try: exchange.set_margin_mode("cross", sym)
                    except: pass

                    try: exchange.set_leverage(lev, sym)
                    except: pass

                    qty = (5 * lev) / price
                    qty = float(exchange.amount_to_precision(sym, qty))

                    safe_api(lambda: exchange.create_market_order(
                        sym,
                        "buy" if direction=="long" else "sell",
                        qty
                    ))

                    trade_state[sym] = {
                        "direction": direction,
                        "entry": price,
                        "tp1": False,
                        "trail_active": False,
                        "trail_price": price,
                        "closing": False
                    }

                    active_trades.add(sym)
                    bot.send_message(CHAT_ID, f"🚀 {sym} {direction} ({round(conf,2)})")
                    break

            time.sleep(5)

        except Exception as e:
            print("ENGINE ERROR:", e)
            time.sleep(5)

# ===== MANAGE =====
def manage():
    while True:
        try:
            positions = safe_api(lambda: exchange.fetch_positions())
            if not positions:
                time.sleep(5)
                continue

            for p in positions:

                qty = safe(p.get("contracts"))
                if qty <= 0:
                    continue

                sym = p["symbol"]
                if sym not in trade_state:
                    continue

                st = trade_state[sym]

                if st.get("closing"):
                    continue

                direction = "long" if p["side"] == "long" else "short"
                price = safe(exchange.fetch_ticker(sym)["last"])
                entry = st["entry"]

                # TP1
                if not st["tp1"] and safe(p.get("unrealizedPnl")) >= TP1_USDT:
                    part = qty * 0.4

                    safe_api(lambda: exchange.create_market_order(
                        sym,
                        "sell" if direction=="long" else "buy",
                        part,
                        params={"reduceOnly": True}
                    ))

                    st["tp1"] = True
                    st["trail_active"] = True
                    st["trail_price"] = price

                    bot.send_message(CHAT_ID, f"💰 TP1 {sym}")

                # TRAILING
                if st["trail_active"]:
                    if direction == "long":
                        if price > st["trail_price"]:
                            st["trail_price"] = price

                        if price <= st["trail_price"] * (1 - TRAIL_GAP):
                            st["closing"] = True
                            safe_api(lambda: exchange.create_market_order(
                                sym, "sell", qty, params={"reduceOnly": True}
                            ))
                            active_trades.discard(sym)
                            trade_state.pop(sym, None)
                            bot.send_message(CHAT_ID, f"🔒 EXIT {sym}")

                    else:
                        if price < st["trail_price"]:
                            st["trail_price"] = price

                        if price >= st["trail_price"] * (1 + TRAIL_GAP):
                            st["closing"] = True
                            safe_api(lambda: exchange.create_market_order(
                                sym, "buy", qty, params={"reduceOnly": True}
                            ))
                            active_trades.discard(sym)
                            trade_state.pop(sym, None)
                            bot.send_message(CHAT_ID, f"🔒 EXIT {sym}")

                # STOP LOSS
                loss_pct = abs(price - entry) / entry
                if loss_pct >= 0.02:
                    st["closing"] = True
                    safe_api(lambda: exchange.create_market_order(
                        sym,
                        "sell" if direction=="long" else "buy",
                        qty,
                        params={"reduceOnly": True}
                    ))
                    active_trades.discard(sym)
                    trade_state.pop(sym, None)
                    bot.send_message(CHAT_ID, f"❌ STOP {sym}")

            time.sleep(3)

        except Exception as e:
            print("MANAGE ERROR:", e)
            time.sleep(5)

# ===== START =====
exchange.fetch_balance()
bot.remove_webhook()

threading.Thread(target=engine, daemon=True).start()
threading.Thread(target=manage, daemon=True).start()

bot.send_message(CHAT_ID, "🔥 Sadik Bot v3.0 AI AKTİF")
bot.infinity_polling()
