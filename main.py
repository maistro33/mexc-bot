import os, time, ccxt, telebot, requests
import pandas as pd

# ===== CONFIG =====
LEVERAGE = 10
BASE_USDT = 5
MAX_POSITIONS = 4
COOLDOWN = 120
MODE = "PAPER"

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json"
}

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

def send_open(sym, direction, price):
    send(f"""
🚀 TRADE AÇILDI

📊 {sym}
📈 Yön: {direction}

💰 Giriş: {round(price,4)}
💵 Margin: {BASE_USDT} USDT
⚡ Kaldıraç: {LEVERAGE}x
""")

def send_close(sym, side, entry, price, pnl, usdt):
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
def load_data():
    try:
        r = requests.get(f"{SUPABASE_URL}/rest/v1/trades?select=*&order=id.desc&limit=200", headers=HEADERS)
        return r.json()
    except:
        return []

def save_trade(d):
    try:
        requests.post(f"{SUPABASE_URL}/rest/v1/trades", headers=HEADERS, json=d)
    except:
        pass

data = load_data()

# ===== FEATURE =====
def features(sym):
    try:
        ohlcv = exchange.fetch_ohlcv(sym, "1m", limit=30)
        df = pd.DataFrame(ohlcv, columns=["t","o","h","l","c","v"])

        return {
            "momentum": float(df["c"].iloc[-1] - df["c"].iloc[-3]),
            "vol": float(df["v"].iloc[-1]),
            "vol_change": float(df["v"].iloc[-1] - df["v"].iloc[-3])
        }
    except:
        return None

# ===== PATTERN AI =====
def key(f):
    return f"{round(f['momentum'],3)}_{round(f['vol_change'],0)}"

memory = {}

def build_memory():
    global memory
    df = pd.DataFrame(data)

    if "result" not in df.columns:
        return

    for _, row in df.iterrows():
        k = key(row)
        if k not in memory:
            memory[k] = []

        memory[k].append(row["result"])

build_memory()

def ai_score(f):
    k = key(f)

    if k not in memory:
        return 0

    avg = sum(memory[k]) / len(memory[k])

    return avg / 10  # normalize

# ===== SYMBOLS =====
def symbols():
    t = exchange.fetch_tickers()

    pairs = [(s, x.get("quoteVolume")) for s,x in t.items()
             if ":USDT" in s and x.get("quoteVolume")]

    pairs.sort(key=lambda x: x[1], reverse=True)

    return [p[0] for p in pairs[:15]]

# ===== ORDER =====
def place(sym, side, qty):
    if MODE == "REAL":
        try:
            exchange.set_leverage(LEVERAGE, sym)
        except:
            pass
        try:
            return exchange.create_market_order(sym, side, qty)
        except:
            return None
    else:
        print("PAPER", sym, side)
        return {"ok": True}

# ===== STATE =====
positions = []
last_trade = {}

send("🤖 V1300 TRUE AI BAŞLADI")

# ===== LOOP =====
while True:
    try:

        # ENTRY
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

            score = ai_score(f)

            if abs(score) < 0.02:
                continue

            side = "buy" if score > 0 else "sell"
            direction = "LONG" if side == "buy" else "SHORT"

            price = exchange.fetch_ticker(sym)["last"]
            if not price:
                continue

            qty = (BASE_USDT * LEVERAGE) / price

            if not place(sym, side, qty):
                continue

            positions.append({
                "sym": sym,
                "side": direction,
                "entry": price,
                "qty": qty,
                "peak": price
            })

            last_trade[sym] = time.time()
            send_open(sym, direction, price)

        # EXIT
        for p in positions[:]:

            sym = p["sym"]
            side = p["side"]
            entry = p["entry"]
            qty = p["qty"]

            price = exchange.fetch_ticker(sym)["last"]
            if not price:
                continue

            if side == "LONG" and price > p["peak"]:
                p["peak"] = price
            elif side == "SHORT" and price < p["peak"]:
                p["peak"] = price

            pnl = ((price-entry)/entry)*100*LEVERAGE if side=="LONG" else ((entry-price)/entry)*100*LEVERAGE
            usdt = ((price-entry)*qty) if side=="LONG" else ((entry-price)*qty)

            # TRAILING
            exit_flag = False

            if side == "LONG" and price < p["peak"] * 0.996:
                exit_flag = True

            if side == "SHORT" and price > p["peak"] * 1.004:
                exit_flag = True

            # HARD EXIT (learning)
            if pnl > 10 or pnl < -6:
                exit_flag = True

            if exit_flag:
                place(sym, "sell" if side=="LONG" else "buy", qty)

                f = features(sym)
                if f:
                    f["result"] = pnl
                    data.append(f)
                    save_trade(f)

                send_close(sym, side, entry, price, pnl, usdt)

                positions.remove(p)

        time.sleep(5)

    except Exception as e:
        print("ERR:", e)
        time.sleep(3)
