import os, time, json, ccxt, telebot, threading, joblib
import pandas as pd
from xgboost import XGBClassifier

# ===== SETTINGS =====
MAX_TRADES = 2
BASE_USDT = 5
LEVERAGE = 10
MEMORY_FILE = "memory.json"

TP1_USDT = 1.2
TRAIL_GAP = 0.5

TRAIN_EVERY = 10
AI_THRESHOLD = 0.45   # 🔥 düşük tuttum → işlem açsın

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
memory_lock = threading.Lock()

def load_memory():
    if not os.path.exists(MEMORY_FILE):
        return []
    return json.load(open(MEMORY_FILE))

def save_memory(m):
    json.dump(m, open(MEMORY_FILE, "w"))

memory = load_memory()

# ===== AI PANEL =====
def ai_panel():
    if len(memory) < 5:
        return "📊 AI PANEL\nNot enough data yet..."

    wins = [x["result"] for x in memory if x["result"] > 0]
    losses = [x["result"] for x in memory if x["result"] <= 0]

    total = len(memory)
    winrate = round(len(wins)/total*100,2)

    avg_win = round(sum(wins)/len(wins),2) if wins else 0
    avg_loss = round(sum(losses)/len(losses),2) if losses else 0

    status = "Improving 🚀" if winrate > 50 else "Weak ⚠️"

    return f"""
📊 AI PANEL

Trades: {total}
Win: {len(wins)}
Loss: {len(losses)}
Winrate: {winrate}%

Avg Win: {avg_win}
Avg Loss: {avg_loss}

AI Status: {status}
"""

@bot.message_handler(commands=['panel'])
def send_panel(message):
    bot.send_message(CHAT_ID, ai_panel())

# ===== MODEL =====
def train_model():
    if len(memory) < 30:
        return None

    df = pd.DataFrame(memory)
    X = df.drop(columns=["result"])
    y = df["result"] > 0

    model = XGBClassifier(n_estimators=200)
    model.fit(X, y)

    joblib.dump(model, "model.pkl")
    return model

model = joblib.load("model.pkl") if os.path.exists("model.pkl") else None

def ai_confidence(f):
    global model
    if not model:
        return 0.5
    return model.predict_proba(pd.DataFrame([f]))[0][1]

# ===== DATA =====
def ohlcv(sym):
    return exchange.fetch_ohlcv(sym, "5m", limit=80)

# ===== FEATURES =====
def features(sym):
    df = pd.DataFrame(ohlcv(sym), columns=["t","o","h","l","c","v"])

    df["ema9"] = df["c"].ewm(span=9).mean()
    df["ema21"] = df["c"].ewm(span=21).mean()
    df["trend"] = df["ema9"] - df["ema21"]

    df["momentum"] = df["c"] - df["c"].shift(5)
    df["momentum2"] = df["c"] - df["c"].shift(10)

    df["vol_avg"] = df["v"].rolling(10).mean()
    df["volume_spike"] = df["v"] / df["vol_avg"]

    df["fake"] = ((df["h"] > df["h"].shift(1)) & (df["c"] < df["h"].shift(1))).astype(int)

    last = df.iloc[-1]

    return {
        "c": float(last["c"]),
        "trend": float(last["trend"]),
        "momentum": float(last["momentum"]),
        "momentum2": float(last["momentum2"]),
        "volume_spike": float(last["volume_spike"]),
        "fake": int(last["fake"])
    }

# ===== ENTRY =====
def entry_signal(f):

    if abs(f["momentum"]) / f["c"] > 0.004:
        return None

    if abs(f["trend"]) < 0.0005:
        return None

    if f["fake"] == 1 and f["volume_spike"] < 1.5:
        return None

    if f["volume_spike"] < 1.1:
        return None

    if f["momentum"] * f["momentum2"] < 0:
        return None

    if f["trend"] > 0 and f["momentum"] > 0:
        return "long"

    if f["trend"] < 0 and f["momentum"] < 0:
        return "short"

    return None

# ===== SYMBOLS =====
def symbols():
    t = exchange.fetch_tickers()
    s = [(k,v["quoteVolume"]) for k,v in t.items() if ":USDT" in k]
    s = [x for x in s if x[1] and x[1] > 200000]
    s.sort(key=lambda x:x[1], reverse=True)
    return [x[0] for x in s[:15]]

# ===== STATE =====
state = {}
cooldown = {}

# ===== ENGINE =====
def engine():
    while True:
        try:
            pos = exchange.fetch_positions()

            for sym in symbols():

                if any(p["symbol"] == sym and float(p.get("contracts") or 0) > 0 for p in pos):
                    continue

                if sym in cooldown and time.time() - cooldown[sym] < 90:
                    continue

                f = features(sym)
                side = entry_signal(f)

                if not side:
                    continue

                conf = ai_confidence(f)

                if conf < AI_THRESHOLD:
                    continue

                price = exchange.fetch_ticker(sym)["last"]
                qty = (BASE_USDT * LEVERAGE) / price

                market = exchange.market(sym)
                min_cost = market["limits"]["cost"]["min"]

                if min_cost and qty * price < min_cost:
                    continue

                qty = float(exchange.amount_to_precision(sym, qty))

                exchange.set_leverage(LEVERAGE, sym)
                exchange.create_market_order(sym, "buy" if side=="long" else "sell", qty)

                state[sym] = {
                    "peak": 0,
                    "features": f,
                    "tp1": False
                }

                break

            time.sleep(6)

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
                side = str(p.get("side")).lower()

                if sym not in state:
                    state[sym] = {"peak": pnl, "features": features(sym), "tp1": False}

                st = state[sym]

                if pnl > st["peak"]:
                    st["peak"] = pnl

                if pnl > 1.0 and pnl < st["peak"] - 0.4 or pnl < -1.0:

                    exchange.create_market_order(sym, "sell" if side=="long" else "buy", qty, params={"reduceOnly": True})

                    st["features"]["result"] = pnl

                    with memory_lock:
                        memory.append(st["features"])
                        save_memory(memory)

                        # PANEL AUTO
                        if len(memory) % 5 == 0:
                            bot.send_message(CHAT_ID, ai_panel())

                        # AUTO TRAIN
                        if len(memory) % TRAIN_EVERY == 0:
                            new_model = train_model()
                            if new_model:
                                model = new_model

                    state.pop(sym)
                    cooldown[sym] = time.time()

            time.sleep(4)

        except Exception as e:
            print("MANAGE:", e)

# ===== START =====
bot.remove_webhook()
threading.Thread(target=engine, daemon=True).start()
threading.Thread(target=manage, daemon=True).start()

bot.send_message(CHAT_ID, "🚀 V12 AI PANEL AKTİF")
bot.infinity_polling()
