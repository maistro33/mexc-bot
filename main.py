import os, time, requests, ccxt, telebot, threading
import pandas as pd
from xgboost import XGBClassifier
import joblib

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

MAX_TRADES = 2
BASE_USDT = 3
LEVERAGE = 10

TP1_USDT = 0.6
SL_USDT = -1.2

MIN_HOLD = 20
GLOBAL_COOLDOWN = 45

AI_WEIGHT = 3
COOLDOWN = 60
MAX_DAILY_LOSS = -5

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
                "Authorization": f"Bearer {SUPABASE_KEY}",  # ✅ FIX 1
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
def ohlcv(sym, tf="5m", limit=100):
    try:
        return exchange.fetch_ohlcv(sym, tf, limit=limit)
    except:
        return []

def market_mode():
    try:
        df = pd.DataFrame(ohlcv("BTC/USDT:USDT", limit=50), columns=["t","o","h","l","c","v"])
        ema20 = df["c"].ewm(span=20).mean().iloc[-1]
        ema50 = df["c"].ewm(span=50).mean().iloc[-1]
        diff = abs(ema20 - ema50) / df["c"].iloc[-1]

        if diff > 0.003:
            return "strong"
        elif diff > 0.0015:
            return "trend"
        else:
            return "chop"
    except:
        return "trend"

def features(sym):
    try:
        data = ohlcv(sym)
        if not data:
            return None

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

# ===== DECISION =====
def decision(sym):
    f = features(sym)
    if not f:
        return None

    mode = market_mode()
    if mode == "chop":
        return None

    if abs(f["price_change"]) > 0.004:
        return None

    score = 0

    side = "long" if f["trend"] > 0 else "short"
    score += 2

    if abs(f["momentum"]) > 0:
        score += 1

    if f["volume_spike"] > 1.2:
        score += 2

    if f["volume_spike"] > 2:
        score += 3

    if f["fake"] == 1:
        score -= 3

    if mode == "strong":
        score += 2

    conf = ai_score(f)
    final = score + (conf * AI_WEIGHT)

    if final < 2.2:
        return None

    return side, f, conf

def symbols():
    try:
        t = exchange.fetch_tickers()
        s = [(k,v["quoteVolume"]) for k,v in t.items() if ":USDT" in k]
        s = [x for x in s if x[1] and 20000 < x[1] < 2000000]
        s.sort(key=lambda x:x[1], reverse=True)
        return [x[0] for x in s[:25]]
    except:
        return []

state = {}
cooldown = {}
daily_pnl = 0

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
                    "features": features(sym) or {},
                    "tp": False,
                    "open_time": (ts/1000 if ts else time.time())
                }

                bot.send_message(CHAT_ID, f"♻️ SYNC {sym}")
    except:
        pass

# ===== ENGINE =====
def engine():
    global last_trade_time, daily_pnl

    while True:
        try:
            if daily_pnl <= MAX_DAILY_LOSS:
                time.sleep(60)
                continue

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

                side, f, conf = d

                price = exchange.fetch_ticker(sym)["last"]
                qty = float(exchange.amount_to_precision(sym, (BASE_USDT * LEVERAGE) / price))

                exchange.set_leverage(LEVERAGE, sym)
                exchange.create_market_order(sym, "buy" if side=="long" else "sell", qty)

                state[sym] = {
                    "peak": 0,
                    "features": f,
                    "tp": False,
                    "open_time": time.time()
                }

                last_trade_time = time.time()

                bot.send_message(CHAT_ID, f"🚀 {sym} {side} AI:{round(conf,2)}")
                break

            time.sleep(5)

        except Exception as e:
            print("ENGINE:", e)

# ===== MANAGE =====
def manage():
    global memory, model, daily_pnl

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

                # TP
                if not st["tp"] and pnl >= (TP1_USDT - 0.1):
                    close_qty = float(exchange.amount_to_precision(sym, qty * 0.5))
                    close_side = "sell" if p.get("side") in ["long","buy"] else "buy"
                    exchange.create_market_order(sym, close_side, close_qty, params={"reduceOnly": True})
                    st["tp"] = True
                    st["peak"] = pnl
                    bot.send_message(CHAT_ID, f"💰 TP1 {sym}")

                # SMART EXIT (FIX 2 EKLENDİ)
                f_live = features(sym)
                if f_live:
                    weak = abs(f_live["momentum"]) < 0.0007
                    ai_conf = ai_score(f_live)

                    if pnl > 0.3 and weak:
                        close_side = "sell" if p.get("side") in ["long","buy"] else "buy"
                        exchange.create_market_order(sym, close_side, qty, params={"reduceOnly": True})

                        # ✅ AI öğrenme kaydı eklendi
                        f = st["features"]
                        f["result"] = pnl
                        save_trade_db(f)
                        memory.append(f)

                        bot.send_message(CHAT_ID, f"🧠 SMART EXIT {sym}")

                        state.pop(sym)
                        continue

                # TRAILING
                if st["tp"]:
                    if pnl > 1:
                        gap = 0.15
                    elif pnl > 0.5:
                        gap = 0.2
                    else:
                        gap = 0.3

                    if pnl < st["peak"] - gap:
                        close_side = "sell" if p.get("side") in ["long","buy"] else "buy"
                        exchange.create_market_order(sym, close_side, qty, params={"reduceOnly": True})

                        f = st["features"]
                        f["result"] = pnl
                        save_trade_db(f)
                        memory.append(f)

                        bot.send_message(CHAT_ID, f"🏁 CLOSE {sym} pnl:{round(pnl,2)}")

                        state.pop(sym)
                        daily_pnl += pnl

                # SL
                if pnl <= SL_USDT:
                    close_side = "sell" if p.get("side") in ["long","buy"] else "buy"
                    exchange.create_market_order(sym, close_side, qty, params={"reduceOnly": True})

                    bot.send_message(CHAT_ID, f"❌ SL {sym}")

                    state.pop(sym)
                    daily_pnl += pnl

            time.sleep(1)

        except Exception as e:
            print("MANAGE:", e)

threading.Thread(target=engine, daemon=True).start()
threading.Thread(target=manage, daemon=True).start()

bot.send_message(CHAT_ID, "💣 FINAL V2 (FIXED) AKTİF")
bot.infinity_polling()
