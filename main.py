import os, time, ccxt, requests, telebot
import pandas as pd
from xgboost import XGBClassifier

# ===== CONFIG =====
LEVERAGE = 10
BASE_USDT = 5
MAX_POSITIONS = 4
MODE = os.getenv("MODE", "PAPER")
COOLDOWN = 60

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

# ===== EXCHANGE =====
exchange = ccxt.bitget({
    "apiKey": os.getenv("BITGET_API"),
    "secret": os.getenv("BITGET_SEC"),
    "password": os.getenv("BITGET_PASS"),
    "options": {"defaultType": "swap"},
    "enableRateLimit": True
})

exchange.load_markets()

# ===== SUPABASE =====
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "resolution=merge-duplicates"
}

# ===== DATA =====
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
        mem = {}
        for d in r.json():
            mem[d["key"]] = d["score"]
        return mem
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
    if len(data) < 30:
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

def ai_score(f):
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
        return [p[0] for p in pairs[:20]]
    except:
        return ["BTC/USDT:USDT"]

# ===== ORDER =====
def place_order(sym, side, qty):
    try:
        if MODE == "REAL":
            exchange.set_leverage(LEVERAGE, sym)
            return exchange.create_market_order(sym, side, qty)
        else:
            return {"ok": True}
    except:
        return None

# ===== STATE =====
positions = []
last_trade = {}

send(f"🤖 V1300 TRUE AI BAŞLADI")

# ===== LOOP =====
while True:
    try:
        train()

        # ===== ENTRY =====
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

            if f["volume"] < 10000:
                continue

            price = exchange.fetch_ticker(sym)["last"]
            qty = (BASE_USDT * LEVERAGE) / price

            score = ai_score(f)

            # AGGRESSIVE
            if abs(score) < 0.0:
                continue

            side = "buy" if score > 0.5 else "sell"
            direction = "LONG" if side == "buy" else "SHORT"

            order = place_order(sym, side, qty)
            if not order:
                continue

            positions.append({
                "sym": sym,
                "side": direction,
                "entry": price,
                "qty": qty,
                "f": f,
                "peak": 0
            })

            last_trade[sym] = time.time()

            send(f"""🚀 TRADE AÇILDI

📊 {sym}
📈 Yön: {direction}

💰 Giriş: {round(price,4)}
💵 Margin: {BASE_USDT} USDT
⚡ Kaldıraç: {LEVERAGE}x""")

        # ===== EXIT =====
        for pos in positions[:]:
            sym = pos["sym"]
            side = pos["side"]
            entry = pos["entry"]
            qty = pos["qty"]
            f = pos["f"]

            price = exchange.fetch_ticker(sym)["last"]

            pnl = ((price-entry)/entry)*100*LEVERAGE if side=="LONG" else ((entry-price)/entry)*100*LEVERAGE
            usdt = ((price-entry)*qty) if side=="LONG" else ((entry-price)*qty)

            # TRAILING
            if pnl > pos["peak"]:
                pos["peak"] = pnl

            if pnl < -5 or (pos["peak"] > 3 and pnl < pos["peak"] - 2):

                place_order(sym, "sell" if side=="LONG" else "buy", qty)

                f["result"] = pnl
                data.append(f)
                save_trade(f)
                learn(f, pnl)

                send(f"""❌ TRADE KAPANDI

📊 {sym}
📈 Yön: {side}

💰 Giriş: {round(entry,4)}
💰 Çıkış: {round(price,4)}

📊 PnL: {round(pnl,2)}%
💵 Sonuç: {round(usdt,3)} USDT {"🟢 KAR" if pnl>0 else "🔴 ZARAR"}""")

                positions.remove(pos)

        time.sleep(5)

    except Exception as e:
        print("ERR:", e)
        time.sleep(3)
