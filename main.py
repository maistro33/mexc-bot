import os, time, requests, ccxt, telebot, threading
import pandas as pd
from xgboost import XGBClassifier
import joblib

# ===== ENV =====
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# ===== SETTINGS =====
MAX_TRADES = 2
BASE_USDT = 3
LEVERAGE = 10

TP1_USDT = 0.6
TRAIL_GAP = 0.8
SL_USDT = -1.2

AI_WEIGHT = 3

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

# ===== DATABASE =====
def save_trade_db(data):
    try:
        requests.post(
            f"{SUPABASE_URL}/rest/v1/trades",
            headers={
                "apikey": SUPABASE_KEY,
                "Authorization": f"Bearer {SUPABASE_KEY}",
                "Content-Type": "application/json"
            },
            json=data
        )
    except:
        pass

def load_memory_db():
    try:
        res = requests.get(
            f"{SUPABASE_URL}/rest/v1/trades?select=*",
            headers={
                "apikey": SUPABASE_KEY,
                "Authorization": f"Bearer {SUPABASE_KEY}"
            }
        )
        return res.json()
    except:
        return []

memory = load_memory_db()

# ===== AI =====
def train():
    global memory
    if len(memory) < 50:
        return None
    df = pd.DataFrame(memory)
    X = df.drop(columns=["result"])
    y = df["result"] > 0
    model = XGBClassifier(n_estimators=200)
    model.fit(X, y)
    joblib.dump(model, "model.pkl")
    return model

model = joblib.load("model.pkl") if os.path.exists("model.pkl") else None

def ai_score(f):
    if not model:
        return 0.5
    return model.predict_proba(pd.DataFrame([f]))[0][1]

# ===== DATA =====
def ohlcv(sym, tf="5m", limit=100):
    return exchange.fetch_ohlcv(sym, tf, limit=limit)

# ===== FEATURES =====
def features(sym):
    df = pd.DataFrame(ohlcv(sym), columns=["t","o","h","l","c","v"])

    df["ema9"] = df["c"].ewm(span=9).mean()
    df["ema21"] = df["c"].ewm(span=21).mean()
    df["trend"] = df["ema9"] - df["ema21"]

    df["momentum"] = df["c"] - df["c"].shift(5)
    df["vol_avg"] = df["v"].rolling(10).mean()
    df["volume_spike"] = df["v"] / df["vol_avg"]

    df["range"] = (df["h"] - df["l"]) / df["c"]

    last = df.iloc[-1]

    return {
        "trend": float(last["trend"]),
        "momentum": float(last["momentum"]),
        "volume_spike": float(last["volume_spike"]),
        "range": float(last["range"])
    }

# ===== ENTRY =====
def entry_signal(f):
    if f["trend"] > 0 and f["momentum"] > 0:
        return "long"
    if f["trend"] < 0 and f["momentum"] < 0:
        return "short"
    return None

# ===== SYMBOLS =====
def symbols():
    t = exchange.fetch_tickers()
    s = [(k,v["quoteVolume"]) for k,v in t.items() if ":USDT" in k]
    s = [x for x in s if x[1] and 20000 < x[1] < 2000000]
    s.sort(key=lambda x:x[1], reverse=True)
    return [x[0] for x in s[:20]]

# ===== STATE =====
state = {}

# ===== ENGINE =====
def engine():
    while True:
        try:
            for sym in symbols():

                if sym in state:
                    continue

                f = features(sym)
                side = entry_signal(f)
                if not side:
                    continue

                conf = ai_score(f)
                if conf < 0.5:
                    continue

                price = exchange.fetch_ticker(sym)["last"]
                qty = (BASE_USDT * LEVERAGE) / price
                qty = float(exchange.amount_to_precision(sym, qty))

                exchange.set_leverage(LEVERAGE, sym)

                exchange.create_market_order(
                    sym,
                    "buy" if side=="long" else "sell",
                    qty
                )

                state[sym] = {
                    "peak": 0,
                    "features": f,
                    "tp": False
                }

                bot.send_message(CHAT_ID, f"{sym} {side} AI:{round(conf,2)}")
                break

            time.sleep(5)

        except Exception as e:
            print("ENGINE:", e)

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

                st = state[sym]

                if pnl > st["peak"]:
                    st["peak"] = pnl

                # TP1
                if not st["tp"] and pnl >= TP1_USDT:
                    close_qty = float(exchange.amount_to_precision(sym, qty * 0.5))
                    side = p.get("side")
                    close_side = "sell" if side in ["long","buy"] else "buy"

                    exchange.create_market_order(sym, close_side, close_qty, params={"reduceOnly": True})

                    st["tp"] = True
                    st["peak"] = pnl
                    bot.send_message(CHAT_ID, f"{sym} TP1")

                # TRAILING
                if st["tp"] and pnl < st["peak"] - TRAIL_GAP:
                    side = p.get("side")
                    close_side = "sell" if side in ["long","buy"] else "buy"

                    exchange.create_market_order(sym, close_side, qty, params={"reduceOnly": True})

                    f = st["features"]
                    f["result"] = pnl
                    save_trade_db(f)

                    memory.append(f)

                    if len(memory) % 25 == 0:
                        new_model = train()
                        if new_model:
                            model = new_model

                    state.pop(sym)

                # SL
                if pnl <= SL_USDT:
                    side = p.get("side")
                    close_side = "sell" if side in ["long","buy"] else "buy"

                    exchange.create_market_order(sym, close_side, qty, params={"reduceOnly": True})

                    state.pop(sym)
                    bot.send_message(CHAT_ID, f"{sym} SL")

            time.sleep(3)

        except Exception as e:
            print("MANAGE:", e)

# ===== START =====
threading.Thread(target=engine, daemon=True).start()
threading.Thread(target=manage, daemon=True).start()

bot.send_message(CHAT_ID, "🚀 AI DB BOT AKTİF")
bot.infinity_polling()
