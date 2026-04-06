import os, time, json, ccxt, telebot, threading, joblib
import pandas as pd
from xgboost import XGBClassifier

# ===== SETTINGS =====
MAX_TRADES = 2
RISK_PER_TRADE = 0.03
LEVERAGE = 5

TP1_USDT = 1.5
TRAIL_GAP = 0.6

AI_THRESHOLD = 0.40
MEMORY_FILE = "memory.json"

# GLOBAL RISK
MAX_TOTAL_LOSS = -3.0
MAX_DAILY_LOSS = -5.0

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

# ===== MODEL =====
def train_model():
    if len(memory) < 30:
        return None
    df = pd.DataFrame(memory)
    model = XGBClassifier(n_estimators=200)
    model.fit(df.drop(columns=["result"]), df["result"] > 0)
    joblib.dump(model, "model.pkl")
    return model

model = joblib.load("model.pkl") if os.path.exists("model.pkl") else None

def ai_confidence(f):
    if not model:
        return 0.5
    return model.predict_proba(pd.DataFrame([f]))[0][1]

# ===== DATA =====
def ohlcv(sym, tf="5m", limit=120):
    return exchange.fetch_ohlcv(sym, tf, limit=limit)

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

    df["range"] = (df["h"] - df["l"]) / df["c"]

    last = df.iloc[-1]

    return {
        "c": float(last["c"]),
        "trend": float(last["trend"]),
        "momentum": float(last["momentum"]),
        "momentum2": float(last["momentum2"]),
        "volume_spike": float(last["volume_spike"]),
        "range": float(last["range"])
    }

# ===== MULTI TIMEFRAME =====
def multi_tf_trend(sym):
    df = pd.DataFrame(ohlcv(sym, "15m"), columns=["t","o","h","l","c","v"])
    ema20 = df["c"].ewm(span=20).mean().iloc[-1]
    ema50 = df["c"].ewm(span=50).mean().iloc[-1]
    return "bull" if ema20 > ema50 else "bear"

# ===== SMART FILTER =====
def smart_filter(f):
    if abs(f["momentum"]) / f["c"] > 0.005:
        return False  # geç kaldı

    if f["volume_spike"] > 3 and abs(f["momentum"]) < 0.001:
        return False  # fake

    if f["range"] > 0.015:
        return False  # volatil

    return True

# ===== ENTRY =====
def entry_signal(sym, f):
    if not smart_filter(f):
        return None

    higher = multi_tf_trend(sym)

    if f["trend"] > 0 and f["momentum"] > 0 and higher == "bull":
        return "long"

    if f["trend"] < 0 and f["momentum"] < 0 and higher == "bear":
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

# ===== BALANCE =====
def get_balance():
    try:
        bal = exchange.fetch_balance()
        return bal["total"]["USDT"]
    except:
        return 100

# ===== ENGINE =====
def engine():
    while True:
        try:
            pos = exchange.fetch_positions()
            open_positions = [p for p in pos if float(p.get("contracts") or 0) > 0]

            if len(open_positions) >= MAX_TRADES:
                time.sleep(5)
                continue

            for sym in symbols():

                pos = exchange.fetch_positions()
                open_positions = [p for p in pos if float(p.get("contracts") or 0) > 0]

                if len(open_positions) >= MAX_TRADES:
                    break

                if any(p["symbol"] == sym and float(p.get("contracts") or 0) > 0 for p in pos):
                    continue

                if sym in cooldown and time.time() - cooldown[sym] < 60:
                    continue

                f = features(sym)
                side = entry_signal(sym, f)

                if not side:
                    continue

                conf = ai_confidence(f)
                if conf < AI_THRESHOLD:
                    continue

                price = exchange.fetch_ticker(sym)["last"]

                balance = get_balance()
                risk_amount = balance * RISK_PER_TRADE

                qty = (risk_amount * LEVERAGE) / price
                qty = float(exchange.amount_to_precision(sym, qty))

                exchange.set_leverage(LEVERAGE, sym)

                exchange.create_market_order(sym, "buy" if side=="long" else "sell", qty)

                bot.send_message(
                    CHAT_ID,
                    f"📈 {sym} {side.upper()} OPEN\nAI:{round(conf,2)}"
                )

                state[sym] = {
                    "peak": 0,
                    "features": f,
                    "tp": False,
                    "warned": False
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

            total_pnl = sum(float(p.get("unrealizedPnl") or 0) for p in pos)

            if total_pnl <= MAX_TOTAL_LOSS:
                bot.send_message(CHAT_ID, "🚨 GLOBAL STOP")
                for p in pos:
                    qty = float(p.get("contracts") or 0)
                    if qty > 0:
                        sym = p["symbol"]
                        side = str(p.get("side")).lower()
                        exchange.create_market_order(sym, "sell" if side=="long" else "buy", qty, params={"reduceOnly": True})
                continue

            for p in pos:
                qty = float(p.get("contracts") or 0)
                if qty <= 0:
                    continue

                sym = p["symbol"]
                pnl = float(p.get("unrealizedPnl") or 0)
                side = str(p.get("side")).lower()

                if sym not in state:
                    state[sym] = {"peak": pnl, "features": features(sym), "tp": False}

                st = state[sym]

                f_live = features(sym)

                reverse = (f_live["trend"] < 0 and f_live["momentum"] < 0) if side=="long" else (f_live["trend"] > 0 and f_live["momentum"] > 0)

                if reverse and pnl < -0.9:
                    bot.send_message(CHAT_ID, f"❌ SMART EXIT {sym}")
                    exchange.create_market_order(sym, "sell" if side=="long" else "buy", qty, params={"reduceOnly": True})
                    st["features"]["result"] = pnl

                    memory.append(st["features"])
                    save_memory(memory)

                    if len(memory) % 10 == 0:
                        new_model = train_model()
                        if new_model:
                            model = new_model

                    state.pop(sym)
                    continue

                if pnl > st["peak"]:
                    st["peak"] = pnl

                if pnl > TP1_USDT and not st["tp"]:
                    st["tp"] = True
                    bot.send_message(CHAT_ID, f"💰 TP {sym}")

                if st["tp"] and pnl < st["peak"] - TRAIL_GAP:
                    bot.send_message(CHAT_ID, f"📉 TRAIL {sym}")
                    exchange.create_market_order(sym, "sell" if side=="long" else "buy", qty, params={"reduceOnly": True})
                    state.pop(sym)

                if pnl < -1.2:
                    bot.send_message(CHAT_ID, f"❌ SL {sym}")
                    exchange.create_market_order(sym, "sell" if side=="long" else "buy", qty, params={"reduceOnly": True})
                    state.pop(sym)

            time.sleep(4)

        except Exception as e:
            print("MANAGE:", e)

# ===== START =====
bot.remove_webhook()

threading.Thread(target=engine, daemon=True).start()
threading.Thread(target=manage, daemon=True).start()

bot.send_message(CHAT_ID, "🚀 SMART AI TRADER AKTİF")
bot.infinity_polling()
