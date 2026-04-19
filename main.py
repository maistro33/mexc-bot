import os, time, ccxt, requests, telebot
import pandas as pd
from xgboost import XGBClassifier

# ===== CONFIG =====
LEVERAGE = 10
BASE_USDT = 5
MAX_POSITIONS = 3
MODE = os.getenv("MODE", "PAPER")
COOLDOWN = 90

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
    except:
        print(msg)

# ===== TELEGRAM PRO =====
def send_open(sym, direction, price):
    try:
        send(f"""
🚀 TRADE AÇILDI

📊 {sym}
📈 Yön: {direction}

💰 Giriş: {round(price,4)}
💵 Margin: {BASE_USDT} USDT
⚡ Kaldıraç: {LEVERAGE}x
""")
    except:
        pass

def send_close(sym, side, entry, price, pnl, usdt):
    try:
        emoji = "🟢 KAR" if usdt > 0 else "🔴 ZARAR"
        send(f"""
❌ TRADE KAPANDI

📊 {sym}
📈 Yön: {side}

💰 Giriş: {round(entry,4)}
💰 Çıkış: {round(price,4)}

📊 PnL: {round(pnl,2)}%
💵 Sonuç: {round(usdt,3)} USDT {emoji}
""")
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

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "resolution=merge-duplicates"
}

def save_trade(data):
    try:
        requests.post(f"{SUPABASE_URL}/rest/v1/trades", headers=HEADERS, json=data)
    except:
        pass

def load_data():
    try:
        r = requests.get(f"{SUPABASE_URL}/rest/v1/trades?select=*", headers=HEADERS)
        return r.json()
    except:
        return []

data = load_data()

# ===== MEMORY =====
def load_memory():
    try:
        r = requests.get(f"{SUPABASE_URL}/rest/v1/learning?select=*", headers=HEADERS)
        return {d["key"]: d["score"] for d in r.json()}
    except:
        return {}

memory = load_memory()

def save_memory(key, score):
    try:
        requests.post(
            f"{SUPABASE_URL}/rest/v1/learning?on_conflict=key",
            headers=HEADERS,
            json={"key": key, "score": score}
        )
    except:
        pass

def pattern_key(f):
    return f"{round(f['momentum'],3)}_{round(f['vol_change'],0)}"

def is_bad(f):
    return memory.get(pattern_key(f), 0) < -3

def learn(f, pnl):
    k = pattern_key(f)
    if k not in memory:
        memory[k] = 0

    if pnl < -3:
        memory[k] -= 2
    elif pnl < 0:
        memory[k] -= 1
    elif pnl > 3:
        memory[k] += 2
    else:
        memory[k] += 1

    save_memory(k, memory[k])

# ===== AI =====
model = None

def train():
    global model
    if len(data) < 20:
        return
    try:
        df = pd.DataFrame(data)
        if not all(col in df.columns for col in ["momentum","volume","vol_change","result"]):
            return

        X = df[["momentum","volume","vol_change"]]
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

        BAD_COINS = ["PEPE","FLOKI","SHIB"]

        pairs = [(s, x.get("quoteVolume")) for s, x in t.items()
                 if ":USDT" in s
                 and x.get("quoteVolume")
                 and "BTC" not in s
                 and "ETH" not in s
                 and not any(bad in s for bad in BAD_COINS)
                 ]

        pairs.sort(key=lambda x: x[1], reverse=True)

        return [p[0] for p in pairs[:10]]

    except:
        return ["XRP/USDT:USDT"]

# ===== ORDER =====
def place_order(sym, side, qty):
    try:
        if MODE == "REAL":
            try:
                exchange.set_leverage(LEVERAGE, sym)
            except:
                pass
            return exchange.create_market_order(sym, side, qty)
        else:
            print(f"PAPER {side} {sym} {qty}")
            return {"ok": True}
    except:
        return None

# ===== STATE =====
positions = []
last_trade = {}
last_side = {}

send(f"🤖 V900 FINAL MODE: {MODE}")

# ===== LOOP =====
while True:
    try:

        train()

        for sym in symbols():

            if len(positions) >= MAX_POSITIONS:
                break

            if sym in last_trade and time.time() - last_trade[sym] < COOLDOWN:
                continue

            if any(p["sym"] == sym for p in positions):
                continue

            f = features(sym)
            if not f:
                continue

            if is_bad(f):
                continue

            if f["volume"] < 10000:
                continue

            ticker = exchange.fetch_ticker(sym)
            price = ticker.get("last")

            if not price or price <= 0:
                continue

            qty = (BASE_USDT * LEVERAGE) / price

            try:
                market = exchange.market(sym)
                min_qty = market.get("limits", {}).get("amount", {}).get("min", 0)
                if min_qty and qty < min_qty:
                    continue
            except:
                pass

            conf = ai(f)

            if conf > 0.55:
                side, direction = "buy", "LONG"
            elif conf < 0.45:
                side, direction = "sell", "SHORT"
            else:
                side = "buy" if f["momentum"] > 0 else "sell"
                direction = "LONG" if side=="buy" else "SHORT"

            if sym in last_side:
                if last_side[sym] != direction:
                    if time.time() - last_trade.get(sym, 0) < COOLDOWN:
                        continue

            order = place_order(sym, side, qty)
            if not order:
                continue

            positions.append({
                "sym": sym,
                "side": direction,
                "entry": price,
                "qty": qty,
                "f": f
            })

            last_trade[sym] = time.time()
            last_side[sym] = direction

            send_open(sym, direction, price)

        for pos in positions[:]:

            sym = pos["sym"]
            side = pos["side"]
            entry = pos["entry"]
            qty = pos["qty"]
            f = pos["f"]

            if not entry or entry <= 0:
                positions.remove(pos)
                continue

            ticker = exchange.fetch_ticker(sym)
            price = ticker.get("last")

            if not price or price <= 0:
                continue

            pnl = ((price-entry)/entry)*100*LEVERAGE if side=="LONG" else ((entry-price)/entry)*100*LEVERAGE
            usdt = ((price - entry) * qty) if side=="LONG" else ((entry - price) * qty)

            if pnl > 3 or pnl < -5:

                place_order(sym, "sell" if side=="LONG" else "buy", qty)

                f["result"] = pnl
                data.append(f)
                save_trade(f)
                learn(f, pnl)

                send_close(sym, side, entry, price, pnl, usdt)

                positions.remove(pos)

        time.sleep(5)

    except Exception as e:
        print("ERR:", e)
        time.sleep(3)
