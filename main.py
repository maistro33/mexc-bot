import os, time, ccxt, telebot, requests
import pandas as pd

# ===== CONFIG =====
LEVERAGE = 10
BASE_USDT = 5
MAX_POSITIONS = 2
COOLDOWN = 60
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
        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/trades?select=*&order=id.desc&limit=100",
            headers=HEADERS
        )
        return r.json()
    except:
        return []

def save_trade(data):
    try:
        requests.post(f"{SUPABASE_URL}/rest/v1/trades", headers=HEADERS, json=data)
    except:
        pass

data = load_data()

# ===== ANALYSIS =====
def analyze(sym):
    try:
        ohlcv = exchange.fetch_ohlcv(sym, "1m", limit=50)
        df = pd.DataFrame(ohlcv, columns=["t","o","h","l","c","v"])

        momentum = df["c"].iloc[-1] - df["c"].iloc[-3]
        volume = df["v"].iloc[-1]
        vol_avg = df["v"].rolling(10).mean().iloc[-1]

        volatility = (df["h"].max() - df["l"].min()) / df["c"].iloc[-1]

        ma5 = df["c"].rolling(5).mean().iloc[-1]
        ma20 = df["c"].rolling(20).mean().iloc[-1]

        trend = "LONG" if ma5 > ma20 else "SHORT" if ma5 < ma20 else "NONE"

        return {
            "momentum": momentum,
            "volume": volume,
            "vol_avg": vol_avg,
            "volatility": volatility,
            "trend": trend
        }
    except:
        return None

# ===== HYBRID AI =====
def ai_score(f):
    if len(data) < 20:
        return 0

    df = pd.DataFrame(data)

    # 🔥 FIX: result kontrol
    if "result" not in df.columns:
        return 0

    try:
        recent = df.tail(100)

        score = 0

        avg_result = recent["result"].mean()

        if avg_result > 0:
            score += 1
        else:
            score -= 1

        if f["momentum"] > 0:
            score += 1
        else:
            score -= 1

        return score
    except:
        return 0

# ===== DECISION =====
def decision(f):
    score = 0

    if f["momentum"] > 0:
        score += 1
    else:
        score -= 1

    if f["volume"] > f["vol_avg"] * 2:
        score -= 1

    if f["volatility"] > 0.02:
        score -= 1

    if abs(f["momentum"]) < 0.0001:
        score -= 1

    score += ai_score(f)

    return score

# ===== SYMBOLS =====
def symbols():
    try:
        t = exchange.fetch_tickers()

        BAD = ["PEPE","FLOKI","SHIB","XRP"]

        pairs = [(s, x.get("quoteVolume")) for s,x in t.items()
                 if ":USDT" in s
                 and x.get("quoteVolume")
                 and not any(b in s for b in BAD)]

        pairs.sort(key=lambda x: x[1], reverse=True)

        return [p[0] for p in pairs[:6]]
    except:
        return []

# ===== ORDER =====
def place_order(sym, side, qty):
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
        print(f"PAPER {side} {sym} {qty}")
        return {"paper": True}

# ===== STATE =====
positions = []
last_trade = {}
loss_streak = 0

send("🤖 V1200 HYBRID FINAL BAŞLADI")

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

            f = analyze(sym)
            if not f or f["trend"] == "NONE":
                continue

            score = decision(f)

            threshold = 2 if loss_streak >= 3 else 1
            if score < threshold:
                continue

            ticker = exchange.fetch_ticker(sym)
            price = ticker.get("last")

            if not price or price <= 0:
                continue

            qty = (BASE_USDT * LEVERAGE) / price
            side = "buy" if f["trend"] == "LONG" else "sell"

            if not place_order(sym, side, qty):
                continue

            positions.append({
                "sym": sym,
                "side": f["trend"],
                "entry": price,
                "qty": qty,
                "f": f,
                "peak": price
            })

            last_trade[sym] = time.time()
            send_open(sym, f["trend"], price)

        # EXIT
        for pos in positions[:]:

            sym = pos["sym"]
            side = pos["side"]
            entry = pos["entry"]
            qty = pos["qty"]
            f = pos["f"]

            ticker = exchange.fetch_ticker(sym)
            price = ticker.get("last")

            if not price:
                continue

            if side == "LONG" and price > pos["peak"]:
                pos["peak"] = price
            elif side == "SHORT" and price < pos["peak"]:
                pos["peak"] = price

            pnl = ((price-entry)/entry)*100*LEVERAGE if side=="LONG" else ((entry-price)/entry)*100*LEVERAGE
            usdt = ((price-entry)*qty) if side=="LONG" else ((entry-price)*qty)

            new_f = analyze(sym)
            trend = new_f["trend"] if new_f else "NONE"

            exit_flag = False

            if side == "LONG" and trend == "SHORT":
                exit_flag = True
            if side == "SHORT" and trend == "LONG":
                exit_flag = True

            if pnl > 3:
                if side == "LONG" and price < pos["peak"] * 0.995:
                    exit_flag = True
                if side == "SHORT" and price > pos["peak"] * 1.005:
                    exit_flag = True

            if pnl > 8 or pnl < -4:
                exit_flag = True

            if exit_flag:
                place_order(sym, "sell" if side=="LONG" else "buy", qty)

                f["result"] = pnl
                data.append(f)
                save_trade(f)

                send_close(sym, side, entry, price, pnl, usdt)

                if pnl < 0:
                    loss_streak += 1
                else:
                    loss_streak = 0

                positions.remove(pos)

        time.sleep(5)

    except Exception as e:
        print("ERR:", e)
        time.sleep(3)
