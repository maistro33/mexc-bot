import os, time, json, ccxt, telebot, threading, joblib
import pandas as pd
from xgboost import XGBClassifier

# ===== SETTINGS =====
MAX_TRADES = 1
BASE_USDT = 5
LEVERAGE = 10
AI_CONF = 0.60

TP_USDT = 2.0
SL_USDT = -1.2
TRAIL_START = 0.7
TRAIL_GAP = 0.4

MEMORY_FILE = "memory.json"

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

# ===== MEMORY =====
def load_memory():
    if not os.path.exists(MEMORY_FILE):
        return []
    return json.load(open(MEMORY_FILE))

def save_memory(m):
    json.dump(m, open(MEMORY_FILE,"w"))

memory = load_memory()

# ===== DATA =====
def ohlcv(sym, tf="5m", limit=60):
    return exchange.fetch_ohlcv(sym, tf, limit=limit)

# ===== FEATURES =====
def features(sym):
    c = ohlcv(sym)
    df = pd.DataFrame(c, columns=["t","o","h","l","c","v"])

    df["volatility"] = (df["h"] - df["l"]) / df["c"]

    df["ema9"] = df["c"].ewm(span=9).mean()
    df["ema21"] = df["c"].ewm(span=21).mean()
    df["trend"] = df["ema9"] - df["ema21"]

    df["momentum"] = df["c"] - df["c"].shift(5)

    df["vol_avg"] = df["v"].rolling(10).mean()
    df["volume_spike"] = df["v"] / df["vol_avg"]

    df["fake"] = (
        (df["c"] < df["c"].shift(1)) & (df["c"].shift(1) > df["c"].shift(2))
    ).astype(int)

    # thinking score
    score = 0
    if df["volume_spike"].iloc[-1] > 1.5: score += 2
    if df["trend"].iloc[-1] > 0: score += 1
    if df["momentum"].iloc[-1] > 0: score += 1

    last = df.iloc[-1]

    return {
        "o": last["o"],
        "h": last["h"],
        "l": last["l"],
        "c": last["c"],
        "v": last["v"],
        "volatility": last["volatility"],
        "trend": last["trend"],
        "momentum": last["momentum"],
        "volume_spike": last["volume_spike"],
        "fake": last["fake"],
        "thinking": score
    }

# ===== MODEL =====
def train():
    if len(memory) < 50:
        return None

    df = pd.DataFrame(memory)
    X = df.drop(columns=["result"])
    y = df["result"]

    model = XGBClassifier(n_estimators=250)
    model.fit(X,y)

    joblib.dump(model,"model.pkl")
    return model

model = joblib.load("model.pkl") if os.path.exists("model.pkl") else None

# ===== PREDICT =====
def predict(sym):
    global model
    f = features(sym)

    if model:
        X = pd.DataFrame([f])
        p = model.predict_proba(X)[0]
        conf = max(p)

        if conf < AI_CONF:
            return None, conf, f

        direction = "long" if p[1] > p[0] else "short"
        return direction, conf, f

    # fallback
    if f["trend"] > 0:
        return "long", 0.5, f
    else:
        return "short", 0.5, f

# ===== SYMBOLS =====
def symbols():
    t = exchange.fetch_tickers()
    s = [(k,v["quoteVolume"]) for k,v in t.items() if ":USDT" in k]
    s = [x for x in s if x[1] and x[1] > 200000]
    s.sort(key=lambda x:x[1], reverse=True)
    return [x[0] for x in s[:30]]

# ===== STATE =====
state = {}

# ===== ENGINE =====
def engine():
    while True:
        try:
            pos = exchange.fetch_positions()
            open_count = sum(1 for p in pos if float(p.get("contracts") or 0) > 0)

            for sym in symbols():

                if open_count >= MAX_TRADES:
                    break

                if sym in state:
                    continue

                direction,conf,f = predict(sym)

                if not direction:
                    continue

                price = exchange.fetch_ticker(sym)["last"]
                qty = (BASE_USDT * LEVERAGE) / price
                qty = float(exchange.amount_to_precision(sym, qty))

                exchange.set_leverage(LEVERAGE, sym)

                exchange.create_market_order(
                    sym,
                    "buy" if direction=="long" else "sell",
                    qty
                )

                state[sym] = {"peak":0,"features":f}

                bot.send_message(CHAT_ID,f"{sym} {direction} {round(conf,2)}")
                break

            time.sleep(5)

        except Exception as e:
            print("ENGINE:",e)

# ===== MANAGE =====
def manage():
    global memory, model

    while True:
        try:
            pos = exchange.fetch_positions()

            for p in pos:
                qty = float(p.get("contracts") or 0)
                if qty <= 0:
                    continue

                sym = p["symbol"]
                pnl = float(p.get("unrealizedPnl") or 0)

                if sym not in state:
                    continue

                if pnl > state[sym]["peak"]:
                    state[sym]["peak"] = pnl

                peak = state[sym]["peak"]
                close = False

                if pnl > TP_USDT or pnl < SL_USDT:
                    close = True

                if peak > TRAIL_START and pnl < peak - TRAIL_GAP:
                    close = True

                if close:
                    exchange.create_market_order(
                        sym,
                        "sell" if p["side"]=="long" else "buy",
                        qty,
                        params={"reduceOnly":True}
                    )

                    f = state[sym]["features"]
                    f["result"] = 1 if pnl > 0 else 0

                    memory.append(f)
                    save_memory(memory)

                    if len(memory) % 25 == 0:
                        new_model = train()
                        if new_model:
                            model = new_model
                            bot.send_message(CHAT_ID,"AI UPDATED")

                    state.pop(sym)

                    bot.send_message(CHAT_ID,f"{sym} {round(pnl,2)}")

            time.sleep(3)

        except Exception as e:
            print("MANAGE:",e)

# ===== START =====
bot.remove_webhook()

threading.Thread(target=engine, daemon=True).start()
threading.Thread(target=manage, daemon=True).start()

bot.send_message(CHAT_ID,"🧠 AI HEDGE BOT AKTİF")
bot.infinity_polling()
