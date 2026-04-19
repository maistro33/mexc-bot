import os, time, ccxt, requests, telebot
import pandas as pd
from xgboost import XGBClassifier

# ===== CONFIG =====
LEVERAGE = 10
BASE_USDT = 5
MODE = os.getenv("MODE", "REAL")

# ===== TELEGRAM =====
TOKEN = os.getenv("TELE_TOKEN")
CHAT_ID = os.getenv("MY_CHAT_ID")

bot = telebot.TeleBot(TOKEN) if TOKEN else None

def send(msg):
    try:
        if bot and CHAT_ID:
            bot.send_message(CHAT_ID, msg)
        else:
            print(msg)
    except Exception as e:
        print("TELEGRAM ERROR:", e)

# ===== EXCHANGE =====
exchange = ccxt.bitget({
    "apiKey": os.getenv("BITGET_API"),
    "secret": os.getenv("BITGET_SEC"),
    "password": os.getenv("BITGET_PASS"),
    "options": {"defaultType": "swap"},
    "enableRateLimit": True
})

try:
    exchange.load_markets()
except Exception as e:
    print("MARKET LOAD ERROR:", e)

# ===== ORDER =====
def place_order(sym, side, qty, price):
    try:
        if qty <= 0:
            return None

        if MODE == "REAL":
            try:
                exchange.set_leverage(LEVERAGE, sym)
            except Exception as e:
                print("LEV ERROR:", e)

            return exchange.create_market_order(sym, side, qty)

        else:
            print(f"📊 PAPER {side} {sym} qty:{qty} price:{price}")
            return {"price": price}

    except Exception as e:
        print("ORDER ERROR:", e)
        return None

# ===== SUPABASE =====
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

def save_trade(data):
    try:
        if not data or "result" not in data:
            return

        requests.post(
            f"{SUPABASE_URL}/rest/v1/trades",
            headers={
                "apikey": SUPABASE_KEY,
                "Authorization": f"Bearer {SUPABASE_KEY}",
                "Content-Type": "application/json"
            },
            json=data
        )
    except Exception as e:
        print("SUPABASE ERROR:", e)

def load_data():
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

def load_learning():
    try:
        res = requests.get(
            f"{SUPABASE_URL}/rest/v1/learning?select=*",
            headers={
                "apikey": SUPABASE_KEY,
                "Authorization": f"Bearer {SUPABASE_KEY}"
            }
        )
        return {d["key"]: d["score"] for d in res.json()}
    except:
        return {}

def save_learning(key, score):
    try:
        if abs(score) < 8:
            requests.post(
                f"{SUPABASE_URL}/rest/v1/learning",
                headers={
                    "apikey": SUPABASE_KEY,
                    "Authorization": f"Bearer {SUPABASE_KEY}",
                    "Content-Type": "application/json"
                },
                json={"key": key, "score": score}
            )
    except:
        pass

data = load_data()
learning_memory = load_learning()

# ===== FEATURES =====
def get_features(sym):
    try:
        ohlcv = exchange.fetch_ohlcv(sym, "1m", limit=30)
        df = pd.DataFrame(ohlcv, columns=["t","o","h","l","c","v"])

        return {
            "price_change": float(df["c"].iloc[-1] - df["c"].iloc[-2]),
            "volume": float(df["v"].iloc[-1]),
            "range": float(df["h"].iloc[-1] - df["l"].iloc[-1]),
            "momentum": float(df["c"].iloc[-1] - df["c"].iloc[-5]),
            "vol_change": float(df["v"].iloc[-1] - df["v"].iloc[-5])
        }
    except:
        return None

# ===== LEARNING =====
def get_key(f):
    return f"{round(f['price_change'],2)}_{round(f['momentum'],2)}_{round(f['volume'],-3)}"

def get_score(f):
    return learning_memory.get(get_key(f), 0)

def update_learning(f, pnl):
    key = get_key(f)

    if key not in learning_memory:
        learning_memory[key] = 0

    if pnl > 3:
        learning_memory[key] += 3
    elif pnl > 1:
        learning_memory[key] += 2
    elif pnl > 0:
        learning_memory[key] += 1
    elif pnl < -3:
        learning_memory[key] -= 3
    elif pnl < -1:
        learning_memory[key] -= 2
    else:
        learning_memory[key] -= 1

    save_learning(key, learning_memory[key])

# ===== AI =====
model = None

def train_model():
    global model
    if len(data) < 10:
        return

    try:
        df = pd.DataFrame(data).select_dtypes(include=["number"])
        if "result" not in df.columns:
            return

        X = df.drop(columns=["result"])
        y = df["result"] > 0

        model = XGBClassifier(n_estimators=50).fit(X, y)
    except:
        model = None

def ai(f):
    if model is None:
        return 0.55 if f["momentum"] > 0 else 0.45
    try:
        return model.predict_proba(pd.DataFrame([f]))[0][1]
    except:
        return 0.5

# ===== ORDERBOOK =====
orderbook_cache = {}

def orderbook(sym):
    try:
        now = time.time()

        if sym in orderbook_cache and now - orderbook_cache[sym]["t"] < 10:
            return orderbook_cache[sym]["v"]

        ob = exchange.fetch_order_book(sym, limit=20)
        bids = sum([b[1] for b in ob["bids"]])
        asks = sum([a[1] for a in ob["asks"]])

        if bids > asks * 1.3:
            val = "buy"
        elif asks > bids * 1.3:
            val = "sell"
        else:
            val = "neutral"

        orderbook_cache[sym] = {"v": val, "t": now}
        return val

    except:
        return "neutral"

# ===== SYMBOLS =====
def symbols():
    try:
        t = exchange.fetch_tickers()
        pairs = [(s, x["quoteVolume"]) for s,x in t.items()
                 if ":USDT" in s and "BTC" not in s and "ETH" not in s and x["quoteVolume"]]

        pairs.sort(key=lambda x: x[1], reverse=True)

        return [p[0] for p in pairs[:5]] if pairs else ["XRP/USDT:USDT"]

    except:
        return ["XRP/USDT:USDT"]

# ===== STATE =====
pos = None
entry = 0
qty = 0
last_train = 0

last_trade_time = {}
last_side = {}
COOLDOWN = 90

send(f"🤖 V155 FINAL MODE: {MODE}")

# ===== LOOP =====
while True:
    try:

        if time.time() - last_train > 150:
            train_model()
            last_train = time.time()

        if pos is None:

            for sym in symbols():

                now = time.time()

                if sym in last_trade_time:
                    if now - last_trade_time[sym] < COOLDOWN:
                        continue

                f = get_features(sym)
                if not f:
                    continue

                score = get_score(f)
                if score < -3:
                    continue

                ob = orderbook(sym)
                if ob == "neutral":
                    continue

                conf = ai(f) + (score * 0.03)

                price = exchange.fetch_ticker(sym)["last"]
                qty = (BASE_USDT * LEVERAGE) / price

                market = exchange.market(sym)
                min_qty = market.get("limits", {}).get("amount", {}).get("min", 0)

                if min_qty and qty < min_qty:
                    continue

                if conf > 0.53 and ob == "buy":
                    if sym in last_side and last_side[sym] == "long":
                        continue

                    order = place_order(sym, "buy", qty, price)
                    if not order:
                        continue

                    pos = {"sym": sym, "side": "long"}
                    entry = price
                    last_trade_time[sym] = time.time()
                    last_side[sym] = "long"

                    send(f"🚀 LONG {sym}\n💰 {price}\n⚡ {LEVERAGE}x")
                    break

                elif conf < 0.47 and ob == "sell":
                    if sym in last_side and last_side[sym] == "short":
                        continue

                    order = place_order(sym, "sell", qty, price)
                    if not order:
                        continue

                    pos = {"sym": sym, "side": "short"}
                    entry = price
                    last_trade_time[sym] = time.time()
                    last_side[sym] = "short"

                    send(f"🚀 SHORT {sym}\n💰 {price}\n⚡ {LEVERAGE}x")
                    break

        else:
            sym = pos["sym"]
            side = pos["side"]

            f = get_features(sym)
            if not f:
                continue

            price = exchange.fetch_ticker(sym)["last"]

            pnl = ((price - entry)/entry)*100*LEVERAGE if side=="long" else ((entry-price)/entry)*100*LEVERAGE

            if pnl < -5:
                decision = "panic"
            elif pnl > 4:
                decision = "profit"
            else:
                decision = "hold"

            if decision != "hold":

                order = place_order(sym, "sell" if side=="long" else "buy", qty, price)
                if not order:
                    continue

                f["result"] = pnl
                data.append(f)
                save_trade(f)
                update_learning(f, pnl)

                send(f"❌ CLOSE {sym}\nPnL: {round(pnl,2)}%")

                pos = None

        time.sleep(10)

    except Exception as e:
        print("ERR:", e)
        time.sleep(5)
