import os, time, json, ccxt, telebot, threading, joblib
import pandas as pd
from xgboost import XGBClassifier

# ===== SETTINGS =====
MAX_TRADES = 2
BASE_USDT = 5
LEVERAGE = 10

AI_WEIGHT = 3
MEMORY_FILE = "memory.json"

TP1_USDT = 1.0
TRAIL_GAP = 0.4

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
    json.dump(m, open(MEMORY_FILE, "w"))

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
        (df["h"] > df["h"].shift(1)) &
        (df["c"] < df["h"].shift(1))
    ).astype(int)

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
        "fake": last["fake"]
    }

# ===== MARKET CONTEXT =====
def market_context():
    btc = ohlcv("BTC/USDT:USDT", limit=50)
    df = pd.DataFrame(btc, columns=["t","o","h","l","c","v"])

    ema20 = df["c"].ewm(span=20).mean().iloc[-1]
    ema50 = df["c"].ewm(span=50).mean().iloc[-1]

    return "bull" if ema20 > ema50 else "bear"

# ===== ENTRY =====
def entry_signal(f):
    if f["trend"] > 0 and f["momentum"] > 0 and f["volume_spike"] > 1.5:
        return "long"
    if f["trend"] < 0 and f["momentum"] < 0 and f["volume_spike"] > 1.5:
        return "short"
    return None

# ===== TRADER FILTER =====
def trader_filter(f, market_trend):
    score = 0

    if (market_trend == "bull" and f["trend"] > 0) or \
       (market_trend == "bear" and f["trend"] < 0):
        score += 2

    if abs(f["momentum"]) > 0:
        score += 1

    if f["volume_spike"] > 1.3:
        score += 2

    if f["fake"] == 1:
        score -= 3

    if f["volatility"] < 0.002:
        score -= 2

    return score

# ===== AI =====
def train():
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
    global model
    if not model:
        return 0.5

    X = pd.DataFrame([f])
    p = model.predict_proba(X)[0]
    return p[1]

# ===== DECISION =====
def smart_ai_decision(sym):
    market_trend = market_context()
    f = features(sym)

    entry = entry_signal(f)
    if not entry:
        return None

    t_score = trader_filter(f, market_trend)
    if t_score < 2:
        return None

    conf = ai_score(f)
    final_score = t_score + (conf * AI_WEIGHT)

    if final_score < 3:
        return None

    return {
        "side": entry,
        "features": f,
        "conf": conf
    }

# ===== SYMBOLS =====
def symbols():
    t = exchange.fetch_tickers()
    s = [(k,v["quoteVolume"]) for k,v in t.items() if ":USDT" in k]
    s = [x for x in s if x[1] and x[1] > 200000]
    s.sort(key=lambda x:x[1], reverse=True)
    return [x[0] for x in s[:20]]

# ===== STATE =====
state = {}
cooldown = {}
lock = threading.Lock()

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

                if sym in cooldown and time.time() - cooldown[sym] < 60:
                    continue

                decision = smart_ai_decision(sym)
                if not decision:
                    continue

                price = exchange.fetch_ticker(sym)["last"]
                qty = (BASE_USDT * LEVERAGE) / price
                qty = float(exchange.amount_to_precision(sym, qty))

                exchange.set_leverage(LEVERAGE, sym)

                exchange.create_market_order(
                    sym,
                    "buy" if decision["side"]=="long" else "sell",
                    qty
                )

                with lock:
                    state[sym] = {
                        "peak": 0,
                        "features": decision["features"],
                        "tp1_done": False
                    }

                bot.send_message(CHAT_ID, f"{sym} {decision['side']} AI:{round(decision['conf'],2)}")

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

                # ===== TP1 =====
                if not st["tp1_done"] and pnl >= TP1_USDT:

                    close_qty = float(exchange.amount_to_precision(sym, qty * 0.5))

                    side = p.get("side")
                    close_side = "sell" if side in ["long","buy"] else "buy"

                    exchange.create_market_order(
                        sym,
                        close_side,
                        close_qty,
                        params={"reduceOnly": True}
                    )

                    st["tp1_done"] = True

                    bot.send_message(CHAT_ID, f"{sym} 💰 TP1 HIT +1 USDT")

                    continue

                # ===== TRAILING =====
                if st["tp1_done"]:
                    if pnl < st["peak"] - TRAIL_GAP:

                        side = p.get("side")
                        close_side = "sell" if side in ["long","buy"] else "buy"

                        exchange.create_market_order(
                            sym,
                            close_side,
                            qty,
                            params={"reduceOnly": True}
                        )

                        f = st["features"]
                        f["result"] = pnl

                        memory.append(f)
                        save_memory(memory)

                        if len(memory) % 25 == 0:
                            new_model = train()
                            if new_model:
                                model = new_model
                                bot.send_message(CHAT_ID, "🧠 AI UPDATED")

                        state.pop(sym)
                        cooldown[sym] = time.time()

                        bot.send_message(CHAT_ID, f"{sym} 🏁 CLOSED {round(pnl,2)}")

                else:
                    # SL
                    if pnl < -1.2:
                        side = p.get("side")
                        close_side = "sell" if side in ["long","buy"] else "buy"

                        exchange.create_market_order(
                            sym,
                            close_side,
                            qty,
                            params={"reduceOnly": True}
                        )

                        state.pop(sym)
                        cooldown[sym] = time.time()

                        bot.send_message(CHAT_ID, f"{sym} ❌ SL")

            time.sleep(3)

        except Exception as e:
            print("MANAGE:", e)

# ===== START =====
bot.remove_webhook()

threading.Thread(target=engine, daemon=True).start()
threading.Thread(target=manage, daemon=True).start()

bot.send_message(CHAT_ID, "🚀 SADIK AI TRADER V3 AKTİF")
bot.infinity_polling()
