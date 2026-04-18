import os, time, ccxt, requests, telebot
import pandas as pd
from xgboost import XGBClassifier
import joblib

# ===== CONFIG =====
LEVERAGE = 5
BASE_USDT = 3

# ===== TELEGRAM =====
bot = telebot.TeleBot(os.getenv("TELE_TOKEN"))
CHAT_ID = os.getenv("MY_CHAT_ID")

def send(msg):
    try:
        bot.send_message(CHAT_ID, msg)
    except:
        pass

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
except:
    pass

# ===== SUPABASE =====
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

def save_trade(data):
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

# ===== COIN SEÇİCİ =====
def get_best_symbols():
    try:
        tickers = exchange.fetch_tickers()
        pairs = []

        for sym, t in tickers.items():
            if ":USDT" not in sym:
                continue
            if "BTC" in sym or "ETH" in sym:
                continue

            vol = t.get("quoteVolume") or 0

            if vol > 100000:
                pairs.append((sym, vol))

        pairs.sort(key=lambda x: x[1], reverse=True)
        return [p[0] for p in pairs[:5]]

    except:
        return []

# ===== FEATURES =====
def get_features(sym):
    try:
        ohlcv = exchange.fetch_ohlcv(sym, "1m", limit=30)
        df = pd.DataFrame(ohlcv, columns=["t","o","h","l","c","v"])

        return {
            "price_change": float(df["c"].iloc[-1] - df["c"].iloc[-2]),
            "volume": float(df["v"].iloc[-1]),
            "range": float(df["h"].iloc[-1] - df["l"].iloc[-1])
        }
    except:
        return None

# ===== TRAIN =====
def train_model(dataset):
    if len(dataset) < 20:
        return None

    try:
        df = pd.DataFrame(dataset)
        df = df.select_dtypes(include=["number"])

        if "result" not in df.columns:
            return None

        X = df.drop(columns=["result"])
        y = df["result"] > 0

        model = XGBClassifier(n_estimators=100)
        model.fit(X, y)

        joblib.dump(model, "model.pkl")
        return model
    except:
        return None

# ===== MODEL =====
model = None

try:
    if os.path.exists("model.pkl"):
        model = joblib.load("model.pkl")
    else:
        model = train_model(data)
except:
    model = None

# ===== AI =====
def ai_decision(f):
    global model

    if model is None:
        return 0.5

    try:
        df = pd.DataFrame([f])
        return model.predict_proba(df)[0][1]
    except:
        return 0.5

# ===== STATE =====
position = None
entry_price = 0
qty = 0

send("🤖 AI BOT AKTİF")

# ===== LOOP =====
while True:
    try:

        # ===== POZİSYON YOKSA =====
        if position is None:

            symbols = get_best_symbols()

            for sym in symbols:

                f = get_features(sym)
                if not f:
                    continue

                conf = ai_decision(f)
                price = exchange.fetch_ticker(sym)["last"]

                qty = (BASE_USDT * LEVERAGE) / price

                if conf > 0.52:
                    exchange.create_market_order(sym, "buy", qty)
                    position = {"sym": sym, "side": "long"}
                    entry_price = price
                    send(f"🚀 LONG {sym}\nAI: {round(conf,2)}")
                    break

                elif conf < 0.48:
                    exchange.create_market_order(sym, "sell", qty)
                    position = {"sym": sym, "side": "short"}
                    entry_price = price
                    send(f"🚀 SHORT {sym}\nAI: {round(conf,2)}")
                    break

        # ===== POZİSYON VARSA =====
        else:
            sym = position["sym"]
            side = position["side"]

            f = get_features(sym)
            if not f:
                time.sleep(5)
                continue

            conf = ai_decision(f)
            price = exchange.fetch_ticker(sym)["last"]

            pnl = (price - entry_price) if side == "long" else (entry_price - price)

            if abs(conf - 0.5) < 0.05 or pnl > 1 or pnl < -1:

                close_side = "sell" if side == "long" else "buy"
                exchange.create_market_order(sym, close_side, qty)

                f["result"] = pnl
                save_trade(f)
                data.append(f)

                if len(data) % 10 == 0:
                    model = train_model(data)

                send(f"❌ CLOSE {sym}\nPnL: {round(pnl,2)}\nAI: {round(conf,2)}")

                position = None

        time.sleep(10)

    except Exception as e:
        print("ERROR:", e)
        time.sleep(5)
