import os, time, json, ccxt, telebot, threading, joblib
import pandas as pd

# ===== SETTINGS =====
MAX_TRADES = 1
BASE_USDT = 5
LEVERAGE = 10
AI_CONF = 0.60

TP_USDT = 1.5
SL_USDT = -1.0

TRAIL_START = 0.5
TRAIL_GAP = 0.3

MEMORY_FILE = "memory.json"

# ===== TELEGRAM =====
bot = telebot.TeleBot(os.getenv("TELE_TOKEN"))
CHAT_ID = os.getenv("MY_CHAT_ID")

# ===== EXCHANGE =====
exchange = ccxt.bitget({
    "apiKey": os.getenv("BITGET_API"),
    "secret": os.getenv("BITGET_SEC"),
    # 💣 FIX BURADA
    "password": os.getenv("BITGET_PASS") or "Berfin33",
    "options": {"defaultType": "swap"},
    "enableRateLimit": True
})

exchange.load_markets()

# ===== MEMORY =====
def load_memory():
    if not os.path.exists(MEMORY_FILE):
        return []
    return json.load(open(MEMORY_FILE))

def save_memory(m):
    json.dump(m, open(MEMORY_FILE,"w"))

memory = load_memory()
performance = {"wins":0,"loss":0}

# ===== MODEL =====
def train():
    from xgboost import XGBClassifier
    data=[]
    for s in ["BTC/USDT:USDT","ETH/USDT:USDT"]:
        o=exchange.fetch_ohlcv(s,"5m",limit=200)
        for c in o:
            t,op,h,l,cl,v=c
            vol=(h-l)/cl if cl else 0
            data.append([op,h,l,cl,v,vol])
    df=pd.DataFrame(data,columns=["o","h","l","c","v","vol"])
    df["r"]=df["c"].pct_change()
    df["t"]=(df["r"].shift(-1)>0).astype(int)
    df=df.dropna()
    X=df[["o","h","l","c","v","vol"]]
    y=df["t"]
    model=XGBClassifier(n_estimators=120)
    model.fit(X,y)
    joblib.dump(model,"ai_model.pkl")

if not os.path.exists("ai_model.pkl"):
    train()

model = joblib.load("ai_model.pkl")

# ===== HELPERS =====
def safe(x):
    try: return float(x)
    except: return 0

def ohlcv(sym, tf="5m", limit=50):
    return exchange.fetch_ohlcv(sym, tf, limit=limit)

# ===== LEVEL 3 FILTERS =====
def whale(sym):
    c = ohlcv(sym,"1m",10)
    vols = [x[5] for x in c]
    return vols[-1] > sum(vols[:-1]) / len(vols[:-1]) * 2

def squeeze(sym):
    c = ohlcv(sym,"5m",5)
    closes = [x[4] for x in c]
    if closes[-1] > max(closes[:-1]): return "short"
    if closes[-1] < min(closes[:-1]): return "long"
    return None

def regime(sym):
    c = ohlcv(sym,"5m",20)
    closes = [x[4] for x in c]
    move = abs(closes[-1] - closes[0]) / closes[0]
    return "trend" if move > 0.01 else "sideways"

# ===== AI =====
def predict(sym):
    try:
        c = ohlcv(sym,"5m",2)
        t,o,h,l,cl,v = c[-1]

        vol = (h-l)/cl if cl else 0
        if vol < 0.002:
            return None,0

        p = model.predict_proba([[o,h,l,cl,v,vol]])[0]
        conf = max(p)

        if conf < AI_CONF:
            return None,conf

        direction = "long" if p[1] > p[0] else "short"

        if regime(sym) == "sideways":
            return None,conf

        if not whale(sym):
            return None,conf

        sq = squeeze(sym)
        if sq == "long" and direction == "long":
            return None,conf
        if sq == "short" and direction == "short":
            return None,conf

        return direction,conf

    except:
        return None,0

# ===== SYMBOLS =====
def symbols():
    t = exchange.fetch_tickers()
    s = [(k,v["quoteVolume"]) for k,v in t.items() if ":USDT" in k]
    s = [x for x in s if safe(x[1]) > 200000]
    s.sort(key=lambda x:x[1], reverse=True)
    return [x[0] for x in s[:20]]

# ===== WINRATE =====
def winrate():
    t = performance["wins"] + performance["loss"]
    return performance["wins"]/t if t>0 else 0.5

# ===== STATE =====
trade_state = {}

def recover():
    pos = exchange.fetch_positions()
    for p in pos:
        if safe(p.get("contracts")) > 0:
            trade_state[p["symbol"]] = {"peak":0}

# ===== ENGINE =====
def engine():
    while True:
        try:
            pos = exchange.fetch_positions()
            open_count = sum(1 for p in pos if safe(p.get("contracts"))>0)

            for sym in symbols():

                if open_count >= MAX_TRADES:
                    break

                if sym in trade_state:
                    continue

                direction,conf = predict(sym)
                if not direction:
                    continue

                wr = winrate()
                usdt = 3 if wr<0.4 else 7 if wr>0.6 else 5

                price = safe(exchange.fetch_ticker(sym)["last"])
                qty = (usdt * LEVERAGE) / price
                qty = float(exchange.amount_to_precision(sym, qty))

                if qty <= 0:
                    continue

                exchange.set_leverage(LEVERAGE, sym)

                exchange.create_market_order(
                    sym,
                    "buy" if direction=="long" else "sell",
                    qty
                )

                trade_state[sym] = {"peak":0}

                bot.send_message(CHAT_ID,
                    f"🚀 {sym} {direction}\nconf:{round(conf,2)}")

                break

            time.sleep(5)

        except Exception as e:
            print("ENGINE:", e)

# ===== MANAGE =====
def manage():
    global memory

    while True:
        try:
            pos = exchange.fetch_positions()

            for p in pos:
                qty = safe(p.get("contracts"))
                if qty <= 0:
                    continue

                sym = p["symbol"]
                pnl = safe(p.get("unrealizedPnl"))

                if sym not in trade_state:
                    trade_state[sym] = {"peak":pnl}

                if pnl > trade_state[sym]["peak"]:
                    trade_state[sym]["peak"] = pnl

                peak = trade_state[sym]["peak"]

                close = False

                if pnl > TP_USDT or pnl < SL_USDT:
                    close = True

                if peak > TRAIL_START and pnl < peak - TRAIL_GAP:
                    close = True

                if close:
                    exchange.create_market_order(
                        sym,
                        "sell" if p["side"]=="long" else "buy",
                        qty,
                        params={"reduceOnly":True}
                    )

                    win = pnl > 0
                    memory.append({"symbol":sym,"win":win})
                    save_memory(memory)

                    if win:
                        performance["wins"] += 1
                    else:
                        performance["loss"] += 1

                    trade_state.pop(sym, None)

                    bot.send_message(CHAT_ID,
                        f"{'✅ WIN' if win else '❌ LOSS'} {sym} {round(pnl,2)}")

            time.sleep(3)

        except Exception as e:
            print("MANAGE:", e)

# ===== START =====
bot.remove_webhook()
recover()

threading.Thread(target=engine, daemon=True).start()
threading.Thread(target=manage, daemon=True).start()

bot.send_message(CHAT_ID,"🧠 Sadik AI v8 FINAL AKTİF")
bot.infinity_polling()
