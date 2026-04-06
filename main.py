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
AI_THRESHOLD = 0.40

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
def ohlcv(sym):
    return exchange.fetch_ohlcv(sym, "5m", limit=120)

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

    df["fake"] = ((df["h"] > df["h"].shift(1)) & (df["c"] < df["h"].shift(1))).astype(int)

    last = df.iloc[-1]

    return {
        "c": float(last["c"]),
        "trend": float(last["trend"]),
        "momentum": float(last["momentum"]),
        "momentum2": float(last["momentum2"]),
        "volume_spike": float(last["volume_spike"]),
        "range": float(last["range"]),
        "fake": int(last["fake"])
    }

# ===== INSTITUTIONAL FILTER =====
def institutional_filter(f):

    # Fake pump
    if f["volume_spike"] > 3 and abs(f["momentum"]) < 0.001:
        return False

    # Stop hunt / likidite avı
    if f["range"] > 0.015 and f["volume_spike"] > 2:
        return False

    # Trend zayıf
    if abs(f["trend"]) < 0.0005:
        return False

    return True

# ===== ENTRY =====
def entry_signal(f):

    if not institutional_filter(f):
        return None

    if abs(f["momentum"]) / f["c"] > 0.004:
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
    return [x[0] for x in s[:20]]

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
                if market["limits"]["cost"]["min"] and qty * price < market["limits"]["cost"]["min"]:
                    continue

                qty = float(exchange.amount_to_precision(sym, qty))

                exchange.set_leverage(LEVERAGE, sym)
                exchange.create_market_order(sym, "buy" if side=="long" else "sell", qty)

                bot.send_message(CHAT_ID, f"📈 {sym} {side.upper()} OPEN")

                state[sym] = {
                    "peak": 0,
                    "features": f,
                    "tp1": False,
                    "warned": False,
                    "strong_msg": False
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
                    state[sym] = {
                        "peak": pnl,
                        "features": features(sym),
                        "tp1": False,
                        "warned": False,
                        "strong_msg": False
                    }

                st = state[sym]

                f_live = features(sym)
                trend_now = f_live["trend"]
                momentum_now = f_live["momentum"]
                volume_now = f_live["volume_spike"]

                reverse = (trend_now < 0 and momentum_now < 0) if side in ["long","buy"] else (trend_now > 0 and momentum_now > 0)
                weak = volume_now < 1.0
                strong = not reverse and volume_now > 1.3

                if (reverse or weak) and not st["warned"]:
                    st["warned"] = True
                    bot.send_message(CHAT_ID, f"⚠️ {sym} Trend zayıflıyor")

                if reverse and pnl < -0.7:
                    bot.send_message(CHAT_ID, f"❌ SMART EXIT {sym}")
                    exchange.create_market_order(sym, "sell" if side=="long" else "buy", qty, params={"reduceOnly": True})
                    state.pop(sym)
                    cooldown[sym] = time.time()
                    continue

                if strong and pnl > 0.3 and not st["strong_msg"]:
                    st["strong_msg"] = True
                    bot.send_message(CHAT_ID, f"✅ {sym} TREND STRONG")

                if pnl > st["peak"]:
                    st["peak"] = pnl

                if pnl > TP1_USDT and not st["tp1"]:
                    st["tp1"] = True
                    bot.send_message(CHAT_ID, f"💰 {sym} TP HIT")

                if st["tp1"] and pnl < st["peak"] - TRAIL_GAP:
                    bot.send_message(CHAT_ID, f"📉 {sym} TRAILING EXIT")
                    exchange.create_market_order(sym, "sell" if side=="long" else "buy", qty, params={"reduceOnly": True})
                    state.pop(sym)
                    cooldown[sym] = time.time()

                if pnl < -1.2:
                    bot.send_message(CHAT_ID, f"❌ {sym} SL")
                    exchange.create_market_order(sym, "sell" if side=="long" else "buy", qty, params={"reduceOnly": True})
                    state.pop(sym)
                    cooldown[sym] = time.time()

            time.sleep(4)

        except Exception as e:
            print("MANAGE:", e)

# ===== START =====
bot.remove_webhook()
threading.Thread(target=engine, daemon=True).start()
threading.Thread(target=manage, daemon=True).start()

bot.send_message(CHAT_ID, "🚀 V14 INSTITUTIONAL AKTİF")
bot.infinity_polling()
