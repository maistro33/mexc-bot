import os, time, ccxt, requests, telebot
import pandas as pd
from xgboost import XGBClassifier

# ===== CONFIG =====
LEVERAGE = 10
BASE_USDT = 5
MAX_POSITIONS = 3
MODE = os.getenv("MODE", "PAPER")

# ===== TELEGRAM SAFE =====
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
        print(msg)

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
    print("MARKET ERROR:", e)

# ===== ORDER =====
def place_order(sym, side, qty):
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
            return {"ok": True}

    except Exception as e:
        print("ORDER ERROR:", e)
        return None

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

# ===== AI =====
model = None

def train():
    global model
    if len(data) < 20:
        return
    try:
        df = pd.DataFrame(data)
        if "result" not in df.columns:
            return
        X = df.drop(columns=["result"])
        y = df["result"] > 0
        model = XGBClassifier(n_estimators=50).fit(X, y)
    except:
        model = None

def ai(f):
    if model is None:
        return 0.5
    try:
        return model.predict_proba(pd.DataFrame([f]))[0][1]
    except:
        return 0.5

# ===== FEATURES =====
def features(sym):
    try:
        ohlcv = exchange.fetch_ohlcv(sym, "1m", limit=20)
        df = pd.DataFrame(ohlcv, columns=["t","o","h","l","c","v"])
        return {
            "momentum": float(df["c"].iloc[-1] - df["c"].iloc[-3]),
            "volume": float(df["v"].iloc[-1]),
            "vol_change": float(df["v"].iloc[-1] - df["v"].iloc[-3]),
        }
    except:
        return None

# ===== SYMBOLS =====
def symbols():
    try:
        t = exchange.fetch_tickers()
        pairs = [(s,x["quoteVolume"]) for s,x in t.items()
                 if ":USDT" in s and x["quoteVolume"]]
        pairs.sort(key=lambda x: x[1], reverse=True)
        return [p[0] for p in pairs[:10]]
    except:
        return ["XRP/USDT:USDT"]

# ===== STATE =====
positions = []
last_trade = {}

send(f"🤖 V201 HYBRID AI MODE: {MODE}")

# ===== LOOP =====
while True:
    try:

        train()

        # ===== ENTRY =====
        for sym in symbols():

            if len(positions) >= MAX_POSITIONS:
                break

            if sym in last_trade and time.time() - last_trade[sym] < 15:
                continue

            f = features(sym)
            if not f:
                continue

            conf = ai(f)

            price = exchange.fetch_ticker(sym)["last"]
            qty = (BASE_USDT * LEVERAGE) / price

            # ===== MIN QTY CHECK =====
            try:
                market = exchange.market(sym)
                min_qty = market.get("limits", {}).get("amount", {}).get("min", 0)
                if min_qty and qty < min_qty:
                    continue
            except:
                pass

            # ===== HYBRID LOGIC =====
            if conf > 0.55:
                side = "buy"
            elif conf < 0.45:
                side = "sell"
            else:
                if f["momentum"] > 0 and f["vol_change"] > 0:
                    side = "buy"
                elif f["momentum"] < 0 and f["vol_change"] > 0:
                    side = "sell"
                else:
                    continue

            order = place_order(sym, side, qty)
            if not order:
                continue

            positions.append({
                "sym": sym,
                "side": "long" if side=="buy" else "short",
                "entry": price,
                "qty": qty
            })

            last_trade[sym] = time.time()

            send(f"🚀 {side.upper()} {sym}\n💰 {round(price,4)}\n⚡ {LEVERAGE}x")

        # ===== EXIT =====
        for pos in positions[:]:

            sym = pos["sym"]
            side = pos["side"]
            entry = pos["entry"]
            qty = pos["qty"]

            price = exchange.fetch_ticker(sym)["last"]

            pnl = ((price-entry)/entry)*100*LEVERAGE if side=="long" else ((entry-price)/entry)*100*LEVERAGE

            if pnl > 3 or pnl < -4:

                order = place_order(sym, "sell" if side=="long" else "buy", qty)
                if not order:
                    continue

                f = features(sym)
                if f:
                    f["result"] = pnl
                    data.append(f)
                    save_trade(f)

                send(f"❌ CLOSE {sym}\nPnL: {round(pnl,2)}%")

                positions.remove(pos)

        time.sleep(5)

    except Exception as e:
        print("ERR:", e)
        time.sleep(3)
