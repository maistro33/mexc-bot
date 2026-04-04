import os, time, json, ccxt, telebot, threading, joblib, numpy as np
import pandas as pd

# ===== SETTINGS =====
MAX_TRADES = 2
AI_CONF = 0.58          # 🔥 düşürüldü (önceden 0.65)
MIN_VOL = 0.002
BASE_USDT = 5
MEMORY_FILE = "memory.json"

TP_USDT = 1.5
SL_USDT = -1.0

bot = telebot.TeleBot(os.getenv("TELE_TOKEN"))
CHAT_ID = os.getenv("MY_CHAT_ID")

exchange = ccxt.bitget({
    "apiKey": os.getenv("BITGET_API"),
    "secret": os.getenv("BITGET_SEC"),
    "password": os.getenv("BITGET_PASS") or "Berfin33",
    "options": {"defaultType": "swap"},
    "enableRateLimit": True
})

exchange.load_markets()

# ===== MEMORY =====
def load_memory():
    if not os.path.exists(MEMORY_FILE):
        return []
    with open(MEMORY_FILE, "r") as f:
        return json.load(f)

def save_memory(data):
    with open(MEMORY_FILE, "w") as f:
        json.dump(data, f)

memory = load_memory()

# ===== AI TRAIN =====
def train_model():
    from xgboost import XGBClassifier

    data = []
    for sym in ["BTC/USDT:USDT","ETH/USDT:USDT"]:
        ohlcv = exchange.fetch_ohlcv(sym, "5m", limit=300)

        for c in ohlcv:
            t,o,h,l,cl,v = c
            vol=(h-l)/cl if cl else 0
            data.append([o,h,l,cl,v,vol])

    df = pd.DataFrame(data, columns=["o","h","l","c","v","vol"])
    df["r"] = df["c"].pct_change()
    df["t"] = (df["r"].shift(-1)>0).astype(int)
    df=df.dropna()

    X=df[["o","h","l","c","v","vol"]]
    y=df["t"]

    model=XGBClassifier(n_estimators=150)
    model.fit(X,y)
    joblib.dump(model,"ai_model.pkl")

if not os.path.exists("ai_model.pkl"):
    train_model()

model = joblib.load("ai_model.pkl")

# ===== HELPERS =====
def safe(x):
    try:return float(x)
    except:return 0

def trend(sym):
    c=exchange.fetch_ohlcv(sym,"5m",limit=20)
    closes=[x[4] for x in c]
    return "up" if closes[-1]>sum(closes)/len(closes) else "down"

def volume_spike(sym):
    c=exchange.fetch_ohlcv(sym,"5m",limit=5)
    vols=[x[5] for x in c]
    return vols[-1] > sum(vols[:-1])/6   # 🔥 yumuşatıldı

# ===== AI =====
def predict(sym):
    try:
        ohlcv=exchange.fetch_ohlcv(sym,"5m",limit=2)
        t,o,h,l,c,v=ohlcv[-1]

        vol=(h-l)/c if c else 0
        if vol < MIN_VOL:
            return None,0

        data=[[o,h,l,c,v,vol]]
        p=model.predict_proba(data)[0]
        conf=max(p)

        if conf < AI_CONF:
            return None,conf

        direction="long" if p[1]>p[0] else "short"

        tr=trend(sym)
        if direction=="long" and tr!="up":return None,conf
        if direction=="short" and tr!="down":return None,conf

        if not volume_spike(sym):
            return None,conf

        return direction,conf

    except:
        return None,0

# ===== SYMBOLS =====
def symbols():
    t=exchange.fetch_tickers()
    s=[(k,v["quoteVolume"]) for k,v in t.items() if ":USDT" in k]
    s=[x for x in s if safe(x[1])>200000]
    s.sort(key=lambda x:x[1],reverse=True)
    return [x[0] for x in s[:30]]

# ===== RECOVERY =====
trade_state = {}

def recover_positions():
    positions = exchange.fetch_positions()
    for p in positions:
        if safe(p.get("contracts")) > 0:
            sym = p["symbol"]
            trade_state[sym] = True
            bot.send_message(CHAT_ID, f"♻️ RECOVERED {sym}")

# ===== ENGINE =====
def engine():
    global memory

    while True:
        try:
            positions = exchange.fetch_positions()
            open_count = sum(1 for p in positions if safe(p.get("contracts"))>0)

            for sym in symbols():

                if open_count >= MAX_TRADES:
                    break

                if sym in trade_state:
                    continue

                direction,conf = predict(sym)
                if not direction:
                    continue

                success = sum(1 for m in memory if m["win"]) / len(memory) if memory else 0.5
                if success < 0.35:   # 🔥 biraz gevşetildi
                    continue

                usdt = BASE_USDT * (2 if conf>0.70 else 1)
                lev = 12 if conf>0.70 else 10

                price = safe(exchange.fetch_ticker(sym)["last"])

                market = exchange.market(sym)
                qty = (usdt * lev) / price

                min_qty = market.get('limits', {}).get('amount', {}).get('min', 0.001)
                if qty < min_qty:
                    qty = min_qty

                qty = float(exchange.amount_to_precision(sym, qty))

                if qty <= 0:
                    continue

                exchange.set_leverage(lev, sym)

                exchange.create_market_order(
                    sym,
                    "buy" if direction=="long" else "sell",
                    qty
                )

                trade_state[sym] = True

                bot.send_message(CHAT_ID,
                    f"🚀 {sym}\n{direction}\nconf:{round(conf,2)}\nlev:{lev}x\nsize:{usdt}$")

                break

            time.sleep(5)

        except Exception as e:
            print("ENGINE:",e)

# ===== MANAGE =====
def manage():
    global memory

    while True:
        try:
            positions = exchange.fetch_positions()

            for p in positions:
                qty = safe(p.get("contracts"))
                if qty <= 0:
                    continue

                sym = p["symbol"]
                pnl = safe(p.get("unrealizedPnl"))

                if pnl > TP_USDT or pnl < SL_USDT:

                    exchange.create_market_order(
                        sym,
                        "sell" if p["side"]=="long" else "buy",
                        qty,
                        params={"reduceOnly":True}
                    )

                    win = pnl > 0
                    memory.append({"symbol":sym,"win":win})
                    save_memory(memory)

                    trade_state.pop(sym, None)

                    bot.send_message(CHAT_ID,
                        f"{'✅ WIN' if win else '❌ LOSS'} {sym} {round(pnl,2)}")

            time.sleep(3)

        except Exception as e:
            print("MANAGE:",e)

# ===== START =====
bot.remove_webhook()

recover_positions()

threading.Thread(target=engine,daemon=True).start()
threading.Thread(target=manage,daemon=True).start()

bot.send_message(CHAT_ID,"🔥 Sadik Bot v5.2 FINAL BALANCED AKTİF")
bot.infinity_polling()
