import os, time, json, ccxt, telebot, threading, joblib
import pandas as pd
from xgboost import XGBClassifier

# ===== SETTINGS =====
MAX_TRADES = 2
BASE_USDT = 5
LEVERAGE = 10

AI_WEIGHT = 3
MEMORY_FILE = "memory.json"

TP1_USDT = 1.0
TRAIL_GAP = 0.4

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

# ===== MEMORY =====
memory_lock = threading.Lock()

def load_memory():
    if not os.path.exists(MEMORY_FILE):
        return []
    return json.load(open(MEMORY_FILE))

def save_memory(m):
    json.dump(m, open(MEMORY_FILE, "w"))

memory = load_memory()

# ===== DATA =====
def ohlcv(sym, tf="5m", limit=60):
    return exchange.fetch_ohlcv(sym, tf, limit=limit)

# ===== FEATURES =====
def features(sym):
    c = ohlcv(sym)
    df = pd.DataFrame(c, columns=["t","o","h","l","c","v"])

    df["volatility"] = (df["h"] - df["l"]) / df["c"]
    df["ema9"] = df["c"].ewm(span=9).mean()
    df["ema21"] = df["c"].ewm(span=21).mean()
    df["trend"] = df["ema9"] - df["ema21"]
    df["momentum"] = df["c"] - df["c"].shift(5)
    df["vol_avg"] = df["v"].rolling(10).mean()
    df["volume_spike"] = df["v"] / df["vol_avg"]

    df["fake"] = (
        (df["h"] > df["h"].shift(1)) &
        (df["c"] < df["h"].shift(1))
    ).astype(int)

    last = df.iloc[-1]

    return {
        "c": last["c"],
        "volatility": last["volatility"],
        "trend": last["trend"],
        "momentum": last["momentum"],
        "volume_spike": last["volume_spike"],
        "fake": last["fake"]
    }

# ===== MARKET =====
def market_context():
    btc = ohlcv("BTC/USDT:USDT", limit=50)
    df = pd.DataFrame(btc, columns=["t","o","h","l","c","v"])
    return "bull" if df["c"].ewm(span=20).mean().iloc[-1] > df["c"].ewm(span=50).mean().iloc[-1] else "bear"

# ===== ENTRY =====
def entry_signal(f):

    if abs(f["momentum"]) / f["c"] > 0.003:
        return None

    if abs(f["momentum"]) < 0.0005:
        return None

    if f["volume_spike"] > 2.5 and abs(f["momentum"]) < 0.001:
        return None

    if f["trend"] > 0 and f["momentum"] > 0 and f["volume_spike"] > 1.5:
        return "long"

    if f["trend"] < 0 and f["momentum"] < 0 and f["volume_spike"] > 1.5:
        return "short"

    return None

# ===== FILTER =====
def trader_filter(f, market_trend):
    score = 0

    if (market_trend == "bull" and f["trend"] > 0) or (market_trend == "bear" and f["trend"] < 0):
        score += 2

    if abs(f["momentum"]) > 0:
        score += 1

    if f["volume_spike"] > 1.3:
        score += 2

    if f["fake"] == 1:
        score -= 3

    if f["fake"] == 1 and f["volume_spike"] < 1.5:
        score -= 5

    if f["volatility"] < 0.002:
        score -= 2

    return score

# ===== AI =====
def train():
    if len(memory) < 50:
        return None
    df = pd.DataFrame(memory)
    model = XGBClassifier(n_estimators=200)
    model.fit(df.drop(columns=["result"]), df["result"] > 0)
    joblib.dump(model, "model.pkl")
    return model

model = joblib.load("model.pkl") if os.path.exists("model.pkl") else None

def ai_score(f):
    if not model:
        return 0.5
    return model.predict_proba(pd.DataFrame([f]))[0][1]

# ===== DECISION =====
def smart_ai_decision(sym):
    f = features(sym)
    entry = entry_signal(f)
    if not entry:
        return None

    score = trader_filter(f, market_context())
    if score < 2:
        return None

    conf = ai_score(f)
    if score + conf * AI_WEIGHT < 3:
        return None

    return {"side": entry, "features": f, "conf": conf}

# ===== SYMBOLS =====
def symbols():
    t = exchange.fetch_tickers()
    s = [(k,v["quoteVolume"]) for k,v in t.items() if ":USDT" in k]
    return [x[0] for x in sorted([x for x in s if x[1] and x[1] > 200000], key=lambda x:x[1], reverse=True)[:20]]

# ===== STATE =====
state = {}
cooldown = {}
lock = threading.Lock()

# ===== ENGINE =====
def engine():
    while True:
        try:
            pos = exchange.fetch_positions()

            for sym in symbols():

                # duplicate fix
                already_open = any(p["symbol"] == sym and float(p.get("contracts") or 0) > 0 for p in pos)
                if already_open:
                    continue

                if sym in state:
                    continue

                if sym in cooldown and time.time() - cooldown[sym] < 60:
                    continue

                decision = smart_ai_decision(sym)
                if not decision:
                    continue

                price = exchange.fetch_ticker(sym)["last"]
                qty = float(exchange.amount_to_precision(sym, (BASE_USDT * LEVERAGE) / price))

                exchange.set_leverage(LEVERAGE, sym)
                exchange.create_market_order(sym, "buy" if decision["side"]=="long" else "sell", qty)

                state[sym] = {
                    "peak": 0,
                    "features": decision["features"],
                    "tp1_done": False,
                    "warned": False
                }

                bot.send_message(CHAT_ID, f"{sym} {decision['side']} AI:{round(decision['conf'],2)}")
                break

            time.sleep(5)

        except Exception as e:
            print("ENGINE:", e)

# ===== MANAGE =====
def manage():
    global memory, model

    while True:
        try:
            pos = exchange.fetch_positions()

            for p in pos:
                qty = float(p.get("contracts") or 0)
                if qty <= 0:
                    continue

                sym = p["symbol"]
                pnl = float(p.get("unrealizedPnl") or 0)

                # state yoksa oluştur (KRİTİK FIX)
                if sym not in state:
                    state[sym] = {
                        "peak": pnl,
                        "features": features(sym),
                        "tp1_done": False,
                        "warned": False
                    }

                st = state[sym]

                f = features(sym)
                trend, mom, vol = f["trend"], f["momentum"], f["volume_spike"]
                side = str(p.get("side")).lower()

                reverse = (side in ["long","buy"] and trend < 0 and mom < 0) or (side in ["short","sell"] and trend > 0 and mom > 0)
                weak = vol < 1.0

                # ANALİZ MESAJI
                if (reverse or weak) and not st["warned"]:
                    st["warned"] = True
                    bot.send_message(CHAT_ID, f"{sym} ⚠️ ANALİZ\ntrend:{round(trend,5)} mom:{round(mom,5)} pnl:{round(pnl,2)}")

                # LOSS EXIT
                if (reverse and pnl < -0.3) or (weak and pnl < -0.8):
                    exchange.create_market_order(sym, "sell" if side in ["long","buy"] else "buy", qty, params={"reduceOnly": True})

                    st["features"]["result"] = pnl
                    with memory_lock:
                        memory.append(st["features"])
                        save_memory(memory)
                        print("MEMORY:", len(memory))
                        bot.send_message(CHAT_ID, f"📊 MEMORY: {len(memory)}")

                    state.pop(sym)
                    cooldown[sym] = time.time()
                    bot.send_message(CHAT_ID, f"{sym} 🧠 LOSS EXIT {round(pnl,2)}")
                    continue

                # PROFIT PROTECT
                if pnl > 0.8 and (reverse or weak):
                    exchange.create_market_order(sym, "sell" if side in ["long","buy"] else "buy", qty, params={"reduceOnly": True})

                    st["features"]["result"] = pnl
                    with memory_lock:
                        memory.append(st["features"])
                        save_memory(memory)
                        print("MEMORY:", len(memory))
                        bot.send_message(CHAT_ID, f"📊 MEMORY: {len(memory)}")

                    state.pop(sym)
                    cooldown[sym] = time.time()
                    bot.send_message(CHAT_ID, f"{sym} 💰 PROFIT PROTECT {round(pnl,2)}")
                    continue

                if pnl > st["peak"]:
                    st["peak"] = pnl

                if not st["tp1_done"] and pnl >= TP1_USDT:
                    exchange.create_market_order(sym, "sell" if side in ["long","buy"] else "buy", float(qty*0.5), params={"reduceOnly": True})
                    st["tp1_done"] = True
                    bot.send_message(CHAT_ID, f"{sym} 💰 TP1")
                    continue

                if st["tp1_done"] and pnl < st["peak"] - TRAIL_GAP:
                    exchange.create_market_order(sym, "sell" if side in ["long","buy"] else "buy", qty, params={"reduceOnly": True})

                    st["features"]["result"] = pnl
                    with memory_lock:
                        memory.append(st["features"])
                        save_memory(memory)
                        bot.send_message(CHAT_ID, f"📊 MEMORY: {len(memory)}")

                    state.pop(sym)
                    cooldown[sym] = time.time()
                    bot.send_message(CHAT_ID, f"{sym} 🏁 CLOSE")
                    continue

                if pnl < -1.2:
                    exchange.create_market_order(sym, "sell" if side in ["long","buy"] else "buy", qty, params={"reduceOnly": True})

                    st["features"]["result"] = pnl
                    with memory_lock:
                        memory.append(st["features"])
                        save_memory(memory)
                        bot.send_message(CHAT_ID, f"📊 MEMORY: {len(memory)}")

                    state.pop(sym)
                    cooldown[sym] = time.time()
                    bot.send_message(CHAT_ID, f"{sym} ❌ SL")

            time.sleep(3)

        except Exception as e:
            print("MANAGE:", e)

# ===== START =====
bot.remove_webhook()
threading.Thread(target=engine, daemon=True).start()
threading.Thread(target=manage, daemon=True).start()
bot.send_message(CHAT_ID, "🚀 SADIK AI TRADER V9 FINAL AKTİF")
bot.infinity_polling()
