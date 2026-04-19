import os, time, ccxt, requests, telebot
import pandas as pd
from xgboost import XGBClassifier

LEVERAGE = 5
BASE_USDT = 3
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
    except:
        pass

exchange = ccxt.bitget({
    "apiKey": os.getenv("BITGET_API"),
    "secret": os.getenv("BITGET_SEC"),
    "password": os.getenv("BITGET_PASS"),
    "options": {"defaultType": "swap"},
    "enableRateLimit": True
})

try:
    exchange.load_markets()
except:
    pass

def place_order(sym, side, qty, price):
    try:
        if MODE == "REAL":
            return exchange.create_market_order(sym, side, qty)
        else:
            print(f"📊 PAPER {side} {sym} qty:{qty} price:{price}")
            return {"price": price}
    except Exception as e:
        print("ORDER ERROR:", e)
        return None

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
    except:
        pass

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

data = load_data()

model = None
last_update = 0
last_train = 0

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
                 if ":USDT" in s and "BTC" not in s and "ETH" not in s and x["quoteVolume"]]
        pairs.sort(key=lambda x: x[1], reverse=True)
        return [p[0] for p in pairs[:5]] if pairs else ["XRP/USDT:USDT"]
    except:
        return ["XRP/USDT:USDT"]

pos = None
entry = 0
qty = 0

send(f"🤖 V153 PRO MODE: {MODE}")

while True:
    try:

        if time.time() - last_train > 120:
            train_model()
            last_train = time.time()

        if pos is None:

            for sym in symbols():
                f = get_features(sym)
                if not f:
                    continue

                conf = ai(f)
                price = exchange.fetch_ticker(sym)["last"]
                qty = (BASE_USDT * LEVERAGE) / price

                if conf > 0.52:
                    place_order(sym, "buy", qty, price)
                    pos = {"sym": sym, "side": "long"}
                    entry = price
                    last_update = time.time()  # reset

                    send(f"""🚀 TRADE AÇILDI

📊 {sym}
📈 LONG
💰 Fiyat: {round(price,4)}
💵 Margin: {BASE_USDT}
⚡ Lev: {LEVERAGE}x
🤖 AI: {round(conf,2)}
""")
                    break

                elif conf < 0.48:
                    place_order(sym, "sell", qty, price)
                    pos = {"sym": sym, "side": "short"}
                    entry = price
                    last_update = time.time()

                    send(f"""🚀 TRADE AÇILDI

📊 {sym}
📉 SHORT
💰 Fiyat: {round(price,4)}
💵 Margin: {BASE_USDT}
⚡ Lev: {LEVERAGE}x
🤖 AI: {round(conf,2)}
""")
                    break

        else:
            sym = pos["sym"]
            side = pos["side"]

            f = get_features(sym)
            if not f:
                continue

            price = exchange.fetch_ticker(sym)["last"]

            pnl = ((price - entry)/entry)*100*LEVERAGE if side=="long" else ((entry-price)/entry)*100*LEVERAGE
            profit_usdt = (BASE_USDT * pnl) / 100

            if time.time() - last_update > 60:
                send(f"""📡 AKTİF TRADE

📊 {sym}
📈 {side.upper()}

💰 Giriş: {round(entry,4)}
💰 Şu an: {round(price,4)}

📊 PnL: {round(pnl,2)}%
💵 {round(profit_usdt,2)} USDT
""")
                last_update = time.time()

            if pnl < -5 or pnl > 4:

                order = place_order(sym, "sell" if side=="long" else "buy", qty, price)

                f["result"] = pnl
                data.append(f)
                save_trade(f)

                send(f"""❌ TRADE KAPANDI

📊 {sym}
📈 {side.upper()}

💰 Giriş: {round(entry,4)}
💰 Çıkış: {round(price,4)}

📊 PnL: {round(pnl,2)}%
💵 {round(profit_usdt,2)} USDT
""")

                pos = None

        time.sleep(12)

    except Exception as e:
        print("ERR:", e)
        time.sleep(5)
