import os, time, ccxt, requests, telebot
import pandas as pd
from xgboost import XGBClassifier

LEVERAGE = 10
BASE_USDT = 5
MODE = os.getenv("MODE", "REAL")

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

exchange = ccxt.bitget({
    "apiKey": os.getenv("BITGET_API"),
    "secret": os.getenv("BITGET_SEC"),
    "password": os.getenv("BITGET_PASS"),
    "options": {"defaultType": "swap"},
    "enableRateLimit": True
})

exchange.load_markets()

def place_order(sym, side, qty, price):
    try:
        if qty <= 0:
            return None

        if MODE == "REAL":
            try:
                exchange.set_leverage(LEVERAGE, sym)
            except:
                pass

            return exchange.create_market_order(sym, side, qty)

        else:
            print(f"PAPER {side} {sym} {qty}")
            return {"price": price}

    except Exception as e:
        print("ORDER ERROR:", e)
        return None

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

def save_trade(data):
    try:
        r = requests.post(
            f"{SUPABASE_URL}/rest/v1/trades",
            headers={
                "apikey": SUPABASE_KEY,
                "Authorization": f"Bearer {SUPABASE_KEY}",
                "Content-Type": "application/json"
            },
            json=data
        )
        if r.status_code not in [200,201]:
            print("SUPABASE FAIL:", r.text)
    except Exception as e:
        print("SUPABASE ERROR:", e)

def load_data():
    try:
        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/trades?select=*",
            headers={
                "apikey": SUPABASE_KEY,
                "Authorization": f"Bearer {SUPABASE_KEY}"
            }
        )
        return r.json()
    except:
        return []

data = load_data()

model = None

def train_model():
    global model
    if len(data) < 10:
        return
    try:
        df = pd.DataFrame(data)
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

def symbols():
    try:
        t = exchange.fetch_tickers()
        pairs = [(s, x["quoteVolume"]) for s,x in t.items()
                 if ":USDT" in s and x["quoteVolume"]]

        pairs.sort(key=lambda x: x[1], reverse=True)
        return [p[0] for p in pairs[:5]]
    except:
        return ["XRP/USDT:USDT"]

pos = None
entry = 0
qty = 0
last_train = 0
last_trade_time = {}
COOLDOWN = 30

send(f"🤖 V157 FINAL MODE: {MODE}")

while True:
    try:

        if time.time() - last_train > 120:
            train_model()
            last_train = time.time()

        if pos is None:

            for sym in symbols():

                if sym in last_trade_time:
                    if time.time() - last_trade_time[sym] < COOLDOWN:
                        continue

                f = get_features(sym)
                if not f:
                    continue

                conf = ai(f)

                price = exchange.fetch_ticker(sym)["last"]
                qty = (BASE_USDT * LEVERAGE) / price

                if conf > 0.51:
                    order = place_order(sym, "buy", qty, price)
                    if not order:
                        continue

                    pos = {"sym": sym, "side": "long"}
                    entry = price
                    last_trade_time[sym] = time.time()

                    send(f"🚀 LONG {sym} {price}")
                    break

                elif conf < 0.49:
                    order = place_order(sym, "sell", qty, price)
                    if not order:
                        continue

                    pos = {"sym": sym, "side": "short"}
                    entry = price
                    last_trade_time[sym] = time.time()

                    send(f"🚀 SHORT {sym} {price}")
                    break

        else:
            sym = pos["sym"]
            side = pos["side"]

            price = exchange.fetch_ticker(sym)["last"]

            pnl = ((price - entry)/entry)*100*LEVERAGE if side=="long" else ((entry-price)/entry)*100*LEVERAGE

            if pnl < -5 or pnl > 4:

                order = place_order(sym, "sell" if side=="long" else "buy", qty, price)
                if not order:
                    continue

                f = get_features(sym)
                if f:
                    f["result"] = pnl
                    data.append(f)
                    save_trade(f)

                send(f"❌ CLOSE {sym} {round(pnl,2)}%")
                pos = None

        time.sleep(8)

    except Exception as e:
        print("ERR:", e)
        time.sleep(5)
