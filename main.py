import os, time, requests, ccxt, telebot, threading
import pandas as pd
from xgboost import XGBClassifier
import joblib

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

MAX_TRADES = 2
BASE_USDT = 3
LEVERAGE = 10

TP1 = 0.6
TRAIL_GAP = 0.25
SL_USDT = -1.2

MIN_HOLD = 20
GLOBAL_COOLDOWN = 30

AI_WEIGHT = 3
COOLDOWN = 60

last_trade_time = 0

bot = telebot.TeleBot(os.getenv("TELE_TOKEN"))
CHAT_ID = os.getenv("MY_CHAT_ID")

exchange = ccxt.bitget({
    "apiKey": os.getenv("BITGET_API"),
    "secret": os.getenv("BITGET_SEC"),
    "password": os.getenv("BITGET_PASS") or "Berfin33",
    "options": {"defaultType": "swap"},
    "enableRateLimit": True
})
exchange.load_markets()

# ===== DB =====
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
    if len(memory) < 25:
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
    try:
        if not model:
            return 0.5
        return model.predict_proba(pd.DataFrame([f]))[0][1]
    except:
        return 0.5

# ===== DATA =====
def ohlcv(sym):
    try:
        return exchange.fetch_ohlcv(sym, "5m", limit=100)
    except:
        return []

# ===== WHALE =====
def whale_score(sym):
    try:
        t = exchange.fetch_ticker(sym)
        vol = t["quoteVolume"] or 0
        change = abs(t["percentage"] or 0)

        score = 0
        if vol > 500000:
            score += 2
        if change > 2:
            score += 2

        return score
    except:
        return 0

# ===== FUNDING =====
def funding_score(sym):
    try:
        f = exchange.fetch_funding_rate(sym)
        rate = f["fundingRate"]

        if rate > 0.01:
            return -2
        elif rate < -0.01:
            return 2
        return 0
    except:
        return 0

def features(sym):
    try:
        data = ohlcv(sym)
        df = pd.DataFrame(data, columns=["t","o","h","l","c","v"])

        df["ema9"] = df["c"].ewm(span=9).mean()
        df["ema21"] = df["c"].ewm(span=21).mean()

        df["trend"] = df["ema9"] - df["ema21"]
        df["momentum"] = df["c"] - df["c"].shift(5)

        df["vol_avg"] = df["v"].rolling(10).mean()
        df["volume_spike"] = df["v"] / df["vol_avg"]

        df["price_change"] = (df["c"] - df["c"].shift(3)) / df["c"]
        df["fake"] = ((df["h"] > df["h"].shift(1)) & (df["c"] < df["h"].shift(1))).astype(int)

        df = df.fillna(0)
        last = df.iloc[-1]

        return {
            "trend": float(last["trend"]),
            "momentum": float(last["momentum"]),
            "volume_spike": float(last["volume_spike"]),
            "price_change": float(last["price_change"]),
            "fake": int(last["fake"])
        }
    except:
        return None

# ===== STRATEGY =====
strategy_stats = {
    "trend": {"win":0,"loss":0},
    "breakout": {"win":0,"loss":0}
}

def strat_trend(f):
    return (f["trend"] > 0)*2 + (abs(f["momentum"])>0)

def strat_breakout(f):
    return (f["volume_spike"]>1.5)*3 + (abs(f["price_change"])>0.002)

def best_strategy():
    best = "trend"
    best_wr = 0
    for k,v in strategy_stats.items():
        t = v["win"]+v["loss"]
        if t < 5:
            continue
        wr = v["win"]/t
        if wr > best_wr:
            best_wr = wr
            best = k
    return best

# ===== DECISION =====
def decision(sym):
    f = features(sym)
    if not f:
        return None

    strat = best_strategy()
    score = strat_trend(f) if strat=="trend" else strat_breakout(f)

    score += whale_score(sym)
    score += funding_score(sym)

    conf = ai_score(f)
    final = score + (conf * AI_WEIGHT)

    if final < 2:
        return None

    side = "long" if f["trend"] > 0 else "short"

    return side, f, strat

# ===== SYMBOLS =====
def symbols():
    t = exchange.fetch_tickers()
    s = [(k,v["quoteVolume"]) for k,v in t.items() if ":USDT" in k]
    s = [x for x in s if x[1] and 20000 < x[1] < 2000000]
    s.sort(key=lambda x:x[1], reverse=True)
    return [x[0] for x in s[:20]]

# ===== STATE =====
state = {}
cooldown = {}

# ===== SYNC =====
def sync_positions():
    try:
        pos = exchange.fetch_positions()
        for p in pos:
            qty = float(p.get("contracts") or 0)
            if qty <= 0:
                continue

            sym = p["symbol"]

            if sym not in state:
                ts = p.get("timestamp")

                state[sym] = {
                    "peak": 0,
                    "tp_done": False,
                    "features": features(sym) or {},
                    "open_time": (ts/1000 if ts else time.time()),
                    "strategy": best_strategy()  # FIX
                }

                bot.send_message(CHAT_ID, f"♻️ SYNC {sym}")
    except:
        pass

# ===== ENGINE =====
def engine():
    global last_trade_time

    while True:
        try:
            pos = exchange.fetch_positions()
            open_count = sum(1 for p in pos if float(p.get("contracts") or 0) > 0)

            for sym in symbols():

                if open_count >= MAX_TRADES:
                    break

                if time.time() - last_trade_time < GLOBAL_COOLDOWN:
                    continue

                if sym in state:
                    continue

                if sym in cooldown and time.time() - cooldown[sym] < COOLDOWN:
                    continue

                d = decision(sym)
                if not d:
                    continue

                side, f, strat = d

                price = exchange.fetch_ticker(sym)["last"]
                qty = float(exchange.amount_to_precision(sym, (BASE_USDT*LEVERAGE)/price))

                exchange.set_leverage(LEVERAGE, sym)
                exchange.create_market_order(sym, "buy" if side=="long" else "sell", qty)

                state[sym] = {
                    "peak": 0,
                    "tp_done": False,
                    "features": f,
                    "open_time": time.time(),
                    "strategy": strat
                }

                last_trade_time = time.time()

                bot.send_message(CHAT_ID, f"🚀 {sym} {side} STRAT:{strat}")
                break

            time.sleep(5)

        except Exception as e:
            print("ENGINE:", e)

# ===== MANAGE =====
def manage():
    global memory, model

    while True:
        try:
            sync_positions()

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

                if time.time() - st["open_time"] < MIN_HOLD:
                    continue

                close_side = "sell" if p.get("side") in ["long","buy"] else "buy"

                # TP1
                if not st["tp_done"] and pnl >= TP1:
                    close_qty = float(exchange.amount_to_precision(sym, qty * 0.25))
                    exchange.create_market_order(sym, close_side, close_qty, params={"reduceOnly":True})
                    st["tp_done"] = True
                    st["peak"] = pnl

                # TRAILING
                if st["tp_done"]:
                    if pnl > st["peak"]:
                        st["peak"] = pnl

                    if pnl < st["peak"] - TRAIL_GAP:
                        exchange.create_market_order(sym, close_side, qty, params={"reduceOnly":True})

                        f = st["features"]
                        f["result"] = pnl
                        save_trade_db(f)
                        memory.append(f)

                        if len(memory)%25==0:
                            new = train()
                            if new:
                                model = new

                        state.pop(sym)

                # SL
                if pnl <= SL_USDT:
                    exchange.create_market_order(sym, close_side, qty, params={"reduceOnly":True})

                    # FIX learning
                    f = st["features"]
                    f["result"] = pnl
                    save_trade_db(f)
                    memory.append(f)

                    state.pop(sym)

            time.sleep(1)

        except Exception as e:
            print("MANAGE:", e)

threading.Thread(target=engine, daemon=True).start()
threading.Thread(target=manage, daemon=True).start()

bot.send_message(CHAT_ID, "💣 FINAL LEVEL 10 (FIXED) AKTİF")
bot.infinity_polling()
