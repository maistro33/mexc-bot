import os, time, json, ccxt, telebot, threading, joblib
import pandas as pd
from xgboost import XGBClassifier

# ===== SETTINGS =====
MAX_TRADES = 2
BASE_USDT = 5
LEVERAGE = 10

TP1_USDT = 1.1
TRAIL_GAP = 0.5
SL_PERCENT = 0.02

AI_THRESHOLD = 0.4
AI_WEIGHT = 3

MAX_DAILY_LOSS = -5
COOLDOWN_TIME = 30

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
    try:
        return json.load(open(MEMORY_FILE))
    except:
        return []

def save_memory(m):
    try:
        json.dump(m, open(MEMORY_FILE, "w"))
    except:
        pass

memory = load_memory()

# ===== AI =====
def train():
    try:
        if len(memory) < 50:
            return None
        df = pd.DataFrame(memory)
        X = df.drop(columns=["result"])
        y = df["result"] > 0
        model = XGBClassifier(n_estimators=200)
        model.fit(X, y)
        joblib.dump(model, "model.pkl")
        return model
    except:
        return None

try:
    model = joblib.load("model.pkl")
except:
    model = None

def ai_score(f):
    try:
        if not model:
            return 0.5
        return model.predict_proba(pd.DataFrame([f]))[0][1]
    except:
        return 0.5

# ===== DATA =====
def ohlcv(sym, tf="5m", limit=100):
    try:
        return exchange.fetch_ohlcv(sym, tf, limit=limit)
    except:
        return []

# ===== INDICATORS =====
def indicators(df):
    df["ema9"] = df["c"].ewm(span=9).mean()
    df["ema21"] = df["c"].ewm(span=21).mean()
    df["trend"] = df["ema9"] - df["ema21"]

    df["momentum"] = df["c"] - df["c"].shift(5)

    delta = df["c"].diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss
    df["rsi"] = 100 - (100 / (1 + rs))

    ema12 = df["c"].ewm(span=12).mean()
    ema26 = df["c"].ewm(span=26).mean()
    df["macd"] = ema12 - ema26

    df["vol_avg"] = df["v"].rolling(10).mean()
    df["volume_spike"] = df["v"] / df["vol_avg"]

    df["range"] = (df["h"] - df["l"]) / df["c"]
    df["fake"] = ((df["h"] > df["h"].shift(1)) & (df["c"] < df["h"].shift(1))).astype(int)

    df["price_change"] = (df["c"] - df["c"].shift(3)) / df["c"]

    df = df.fillna(0)  # 🔥 FIX

    return df

# ===== FEATURES =====
def features(sym):
    try:
        data = ohlcv(sym)
        if not data:
            return None

        df = pd.DataFrame(data, columns=["t","o","h","l","c","v"])
        df = indicators(df)
        last = df.iloc[-1]

        return {
            "trend": float(last["trend"]),
            "momentum": float(last["momentum"]),
            "rsi": float(last["rsi"]),
            "macd": float(last["macd"]),
            "volume_spike": float(last["volume_spike"]),
            "range": float(last["range"]),
            "fake": int(last["fake"]),
            "price_change": float(last["price_change"])
        }

    except:
        return None

# ===== MARKET =====
def market_mode():
    try:
        df = pd.DataFrame(ohlcv("BTC/USDT:USDT", limit=50),
                          columns=["t","o","h","l","c","v"])
        ema20 = df["c"].ewm(span=20).mean().iloc[-1]
        ema50 = df["c"].ewm(span=50).mean().iloc[-1]
        return "bull" if ema20 > ema50 else "bear"
    except:
        return "bull"

# ===== SYMBOLS =====
def symbols():
    try:
        t = exchange.fetch_tickers()
        s = [(k, v["quoteVolume"]) for k, v in t.items() if ":USDT" in k]
        s = [x for x in s if x[1] and 20000 < x[1] < 5000000]
        s = [x for x in s if "BTC" not in x[0] and "ETH" not in x[0]]
        s.sort(key=lambda x: x[1], reverse=True)
        return [x[0] for x in s[:30]]
    except:
        return []

# ===== DECISION =====
def decision(sym):
    f = features(sym)
    if not f:
        return None

    market = market_mode()
    score = 0

    if (market == "bull" and f["trend"] > 0) or (market == "bear" and f["trend"] < 0):
        score += 2

    if f["volume_spike"] > 1.5:
        score += 2

    if f["rsi"] < 30 or f["rsi"] > 70:
        score += 1

    if f["fake"] == 1:
        score -= 2

    pump = f["volume_spike"] > 2 and abs(f["price_change"]) > 0.003
    whale = f["volume_spike"] > 3
    liquidation = abs(f["price_change"]) > 0.01 and f["volume_spike"] > 2.5

    if pump:
        score += 3
    if whale:
        score += 2
    if liquidation:
        score += 4

    conf = ai_score(f)
    final = score + (conf * AI_WEIGHT)

    if not (pump or liquidation):
        if conf < AI_THRESHOLD and final < 2:
            return None

    if f["trend"] > 0:
        return "long", f
    elif f["trend"] < 0:
        return "short", f

    return None

# ===== STATE =====
state = {}
cooldown = {}
daily_pnl = 0

# ===== CLOSE ALL =====
def close_all():
    try:
        pos = exchange.fetch_positions()
        for p in pos:
            qty = float(p.get("contracts") or 0)
            if qty > 0:
                sym = p["symbol"]
                side = str(p.get("side")).lower()
                exchange.create_market_order(sym,
                    "sell" if side=="long" else "buy",
                    qty,
                    params={"reduceOnly": True})
    except:
        pass

# ===== ENGINE =====
def engine():
    global daily_pnl

    while True:
        try:
            if daily_pnl <= MAX_DAILY_LOSS:
                close_all()
                time.sleep(60)
                continue

            pos = exchange.fetch_positions()
            open_count = sum(1 for p in pos if float(p.get("contracts") or 0) > 0)

            for sym in symbols():

                if open_count >= MAX_TRADES:
                    break

                if sym in state:
                    continue

                if sym in cooldown and time.time() - cooldown[sym] < COOLDOWN_TIME:
                    continue

                d = decision(sym)
                if not d:
                    continue

                side, f = d
                price = exchange.fetch_ticker(sym)["last"]

                qty = (BASE_USDT * LEVERAGE) / price
                qty = float(exchange.amount_to_precision(sym, qty))

                exchange.set_leverage(LEVERAGE, sym)
                exchange.create_market_order(sym,
                    "buy" if side=="long" else "sell",
                    qty)

                state[sym] = {
                    "entry": price,
                    "peak": 0,
                    "features": f,
                    "tp": False
                }

                bot.send_message(CHAT_ID, f"🚀 {sym} {side} OPEN")

                break

            time.sleep(4)

        except Exception as e:
            print("ENGINE:", e)

# ===== MANAGE =====
def manage():
    global daily_pnl, memory, model

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

                f_data = features(sym)
                if not f_data:
                    continue

                if sym not in state:
                    state[sym] = {
                        "entry": exchange.fetch_ticker(sym)["last"],
                        "peak": pnl,
                        "features": f_data,
                        "tp": False
                    }

                st = state[sym]

                if pnl > st["peak"]:
                    st["peak"] = pnl

                entry = st["entry"]
                price = exchange.fetch_ticker(sym)["last"]

                if side == "long" and price <= entry * (1 - SL_PERCENT):
                    close_side = "sell"
                elif side == "short" and price >= entry * (1 + SL_PERCENT):
                    close_side = "buy"
                else:
                    close_side = None

                if close_side:
                    exchange.create_market_order(sym, close_side, qty, params={"reduceOnly": True})
                    daily_pnl += pnl
                    state.pop(sym)
                    cooldown[sym] = time.time()
                    continue

                if pnl >= TP1_USDT and not st["tp"]:
                    close_qty = float(exchange.amount_to_precision(sym, qty * 0.5))
                    exchange.create_market_order(sym,
                        "sell" if side=="long" else "buy",
                        close_qty,
                        params={"reduceOnly": True})
                    st["tp"] = True

                if st["tp"] and pnl < st["peak"] - TRAIL_GAP:
                    exchange.create_market_order(sym,
                        "sell" if side=="long" else "buy",
                        qty,
                        params={"reduceOnly": True})

                    f = st["features"]
                    f["result"] = pnl
                    memory.append(f)
                    save_memory(memory)

                    if len(memory) % 25 == 0:
                        m = train()
                        if m:
                            model = m

                    daily_pnl += pnl
                    state.pop(sym)
                    cooldown[sym] = time.time()

            time.sleep(3)

        except Exception as e:
            print("MANAGE:", e)

# ===== START =====
bot.remove_webhook()

threading.Thread(target=engine, daemon=True).start()
threading.Thread(target=manage, daemon=True).start()

bot.send_message(CHAT_ID, "🚀 SADIK BOT V5.1 ULTRA FINAL AKTİF")
bot.infinity_polling()
