import os, time, requests, ccxt, telebot, threading
import pandas as pd
from xgboost import XGBClassifier
import joblib

# ===== ENV =====
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# ===== SETTINGS =====
MAX_TRADES = 2
BASE_USDT = 3
LEVERAGE = 10

TP1_USDT = 0.6
TRAIL_GAP = 0.7
SL_USDT = -1.2

AI_WEIGHT = 3
COOLDOWN = 60
MAX_DAILY_LOSS = -5

# ===== TELEGRAM =====
bot = telebot.TeleBot(os.getenv("TELE_TOKEN"))
CHAT_ID = os.getenv("MY_CHAT_ID")

# ===== EXCHANGE =====
exchange = ccxt.bitget({
    "apiKey": os.getenv("BITGET_API"),
    "secret": os.getenv("BITGET_SEC"),
    "password": os.getenv("BITGET_PASS") or "Berfin33",
    "options": {"defaultType": "swap"},
    "enableRateLimit": True
})
exchange.load_markets()

# ===== DATABASE =====
def save_trade_db(data):
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
    if len(memory) < 50:
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

# ===== MARKET =====
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

# ===== FEATURES =====
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
    reason = []

    side = "long" if f["trend"] > 0 else "short"
    score += 2
    reason.append("trend")

    if abs(f["momentum"]) > 0:
        score += 1
        reason.append("momentum")

    if f["volume_spike"] > 1.2:
        score += 2
        reason.append("volume")

    if f["volume_spike"] > 2:
        score += 3
        reason.append("pump")

    if f["volume_spike"] > 3:
        score += 2
        reason.append("whale")

    if f["fake"] == 1:
        score -= 3
        reason.append("fake")

    if mode == "strong":
        score += 2
        reason.append("strong")

    conf = ai_score(f)
    final = score + (conf * AI_WEIGHT)

    if final < 2.2:
        return None

    return side, f, conf, reason

# ===== SYMBOLS =====
def symbols():
    try:
        t = exchange.fetch_tickers()
        s = [(k,v["quoteVolume"]) for k,v in t.items() if ":USDT" in k]
        s = [x for x in s if x[1] and 20000 < x[1] < 2000000]
        s.sort(key=lambda x:x[1], reverse=True)
        return [x[0] for x in s[:25]]
    except:
        return []

# ===== STATE =====
state = {}
cooldown = {}
daily_pnl = 0

# ===== SYNC (KRİTİK) =====
def sync_positions():
    try:
        pos = exchange.fetch_positions()

        for p in pos:
            qty = float(p.get("contracts") or 0)
            if qty <= 0:
                continue

            sym = p["symbol"]

            if sym not in state:
                state[sym] = {
                    "peak": 0,
                    "features": features(sym) or {
                        "trend": 0,
                        "momentum": 0,
                        "volume_spike": 0,
                        "price_change": 0,
                        "fake": 0
                    },
                    "tp": False
                }

                bot.send_message(CHAT_ID, f"♻️ SYNC {sym}")
    except:
        pass

# ===== ENGINE =====
def engine():
    global daily_pnl

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

                if sym in state:
                    continue

                if sym in cooldown and time.time() - cooldown[sym] < COOLDOWN:
                    continue

                d = decision(sym)
                if not d:
                    continue

                side, f, conf, reason = d

                price = exchange.fetch_ticker(sym)["last"]
                qty = (BASE_USDT * LEVERAGE) / price
                qty = float(exchange.amount_to_precision(sym, qty))

                exchange.set_leverage(LEVERAGE, sym)
                exchange.create_market_order(sym, "buy" if side=="long" else "sell", qty)

                state[sym] = {"peak": 0, "features": f, "tp": False}

                bot.send_message(CHAT_ID,
                    f"🚀 {sym} {side}\nAI:{round(conf,2)}\nMode:{market_mode()}\nReason:{','.join(reason)}"
                )

                break

            time.sleep(5)

        except Exception as e:
            print("ENGINE:", e)

# ===== MANAGE =====
def manage():
    global memory, model, daily_pnl

    while True:
        try:
            sync_positions()  # 💣 KRİTİK

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

                # ===== TP1 =====
                if not st["tp"] and pnl >= TP1_USDT:
                    close_qty = float(exchange.amount_to_precision(sym, qty * 0.5))
                    close_side = "sell" if p.get("side") in ["long","buy"] else "buy"

                    exchange.create_market_order(sym, close_side, close_qty, params={"reduceOnly": True})

                    st["tp"] = True
                    st["peak"] = pnl

                    bot.send_message(CHAT_ID, f"💰 TP1 {sym}")

                # ===== AI =====
                f_live = features(sym)
                if f_live:
                    reverse = (f_live["trend"] < 0 and p.get("side") in ["long","buy"]) or \
                              (f_live["trend"] > 0 and p.get("side") in ["short","sell"])

                    weak = abs(f_live["momentum"]) < 0.0007
                    low_vol = f_live["volume_spike"] < 0.9
                    ai_conf = ai_score(f_live)

                    if st["tp"] and pnl > 0.5 and ai_conf > 0.6:
                        continue

                    if reverse or (weak and low_vol) or (pnl < -0.3 and ai_conf < 0.45):
                        close_side = "sell" if p.get("side") in ["long","buy"] else "buy"

                        exchange.create_market_order(sym, close_side, qty, params={"reduceOnly": True})

                        bot.send_message(CHAT_ID,
                            f"🧠 EXIT {sym}\nPnL:{round(pnl,2)}\nAI:{round(ai_conf,2)}"
                        )

                        f = st["features"]
                        f["result"] = pnl
                        save_trade_db(f)

                        memory.append(f)

                        if len(memory) % 25 == 0:
                            new_model = train()
                            if new_model:
                                model = new_model

                        state.pop(sym)
                        cooldown[sym] = time.time()
                        daily_pnl += pnl
                        continue

                # ===== TRAILING =====
                if st["tp"] and pnl < st["peak"] - TRAIL_GAP:
                    close_side = "sell" if p.get("side") in ["long","buy"] else "buy"

                    exchange.create_market_order(sym, close_side, qty, params={"reduceOnly": True})

                    bot.send_message(CHAT_ID, f"🏁 CLOSE {sym} pnl:{round(pnl,2)}")

                    f = st["features"]
                    f["result"] = pnl
                    save_trade_db(f)

                    memory.append(f)

                    if len(memory) % 25 == 0:
                        new_model = train()
                        if new_model:
                            model = new_model

                    state.pop(sym)
                    cooldown[sym] = time.time()
                    daily_pnl += pnl

                # ===== SL =====
                if pnl <= SL_USDT:
                    close_side = "sell" if p.get("side") in ["long","buy"] else "buy"

                    exchange.create_market_order(sym, close_side, qty, params={"reduceOnly": True})

                    bot.send_message(CHAT_ID, f"❌ SL {sym} pnl:{round(pnl,2)}")

                    state.pop(sym)
                    cooldown[sym] = time.time()
                    daily_pnl += pnl

            time.sleep(1)

        except Exception as e:
            print("MANAGE:", e)

# ===== START =====
threading.Thread(target=engine, daemon=True).start()
threading.Thread(target=manage, daemon=True).start()

bot.send_message(CHAT_ID, "💣 FINAL AI BOT AKTİF")
bot.infinity_polling()
