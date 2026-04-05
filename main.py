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
    "password": os.getenv("BITGET_PASS") or "Berfin33",
    "options": {"defaultType": "swap"},
    "enableRateLimit": True
})

exchange.load_markets()

# ===== HELPERS =====
def safe(x):
    try:
        return float(x)
    except:
        return 0

def ohlcv(sym, tf="5m", limit=50):
    return exchange.fetch_ohlcv(sym, tf, limit=limit)

# ===== BTC MARKET FILTER =====
def btc_ok():
    try:
        c = ohlcv("BTC/USDT:USDT","5m",20)
        closes = [x[4] for x in c]
        move = abs(closes[-1] - closes[0]) / closes[0]
        return move > 0.003
    except:
        return False

# ===== THINKING AI =====
def thinking_ai(sym):
    try:
        c = ohlcv(sym, "5m", 30)
        closes = [x[4] for x in c]
        highs = [x[2] for x in c]
        lows = [x[3] for x in c]
        vols = [x[5] for x in c]

        # VOLATILITY FILTER
        volatility = (highs[-1] - lows[-1]) / closes[-1]
        if volatility < 0.002:
            return False

        # MARKET STRUCTURE
        move = (closes[-1] - closes[0]) / closes[0]
        if move < 0.003:
            return False
        if move > 0.08:
            return False

        score = 0

        # TREND PHASE
        recent = (closes[-1] - closes[-5]) / closes[-5]
        if 0.002 < recent < 0.02:
            score += 3
        elif recent > 0.05:
            return False

        # VOLUME
        avg_vol = sum(vols[:-1]) / len(vols[:-1])
        if vols[-1] > avg_vol * 1.5:
            score += 2
        else:
            return False

        # CLEAN STRUCTURE
        if closes[-1] > closes[-2] > closes[-3]:
            score += 1

        # FAKE BREAKOUT
        if closes[-1] < closes[-2] and closes[-2] > closes[-3]:
            return False

        return score >= 4

    except:
        return False

# ===== SCANNER =====
def momentum(sym):
    try:
        c = ohlcv(sym,"5m",10)
        return (c[-1][4] - c[0][4]) / c[0][4]
    except:
        return 0

def symbols():
    try:
        t = exchange.fetch_tickers()
        s = [(k,v["quoteVolume"]) for k,v in t.items() if ":USDT" in k]
        s = [x for x in s if safe(x[1]) > 200000]
        s.sort(key=lambda x:x[1], reverse=True)
        return [x[0] for x in s[:50]]
    except:
        return []

def top_movers():
    scores = []
    for sym in symbols():
        try:
            scores.append((sym, momentum(sym)))
        except:
            continue
    scores.sort(key=lambda x:x[1], reverse=True)
    return [s[0] for s in scores[:10]]

# ===== AI MODEL =====
def train():
    from xgboost import XGBClassifier
    data = []

    for s in ["BTC/USDT:USDT","ETH/USDT:USDT"]:
        o = ohlcv(s,"5m",200)
        for c in o:
            t,op,h,l,cl,v = c
            vol = (h-l)/cl if cl else 0
            data.append([op,h,l,cl,v,vol])

    df = pd.DataFrame(data,columns=["o","h","l","c","v","vol"])
    df["r"] = df["c"].pct_change()
    df["t"] = (df["r"].shift(-1)>0).astype(int)
    df = df.dropna()

    X = df[["o","h","l","c","v","vol"]]
    y = df["t"]

    model = XGBClassifier(n_estimators=120)
    model.fit(X,y)
    joblib.dump(model,"ai_model.pkl")

if not os.path.exists("ai_model.pkl"):
    train()

model = joblib.load("ai_model.pkl")

# ===== PREDICT =====
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

        return direction,conf

    except:
        return None,0

# ===== STATE =====
trade_state = {}

# ===== ENGINE =====
def engine():
    while True:
        try:
            if not btc_ok():
                time.sleep(5)
                continue

            pos = exchange.fetch_positions()
            open_count = sum(1 for p in pos if safe(p.get("contracts")) > 0)

            for sym in top_movers():

                if open_count >= MAX_TRADES:
                    break

                if sym in trade_state:
                    continue

                direction,conf = predict(sym)
                if not direction:
                    continue

                if not thinking_ai(sym):
                    continue

                ticker = exchange.fetch_ticker(sym)
                price = safe(ticker.get("last"))

                if price <= 0:
                    continue

                qty = (BASE_USDT * LEVERAGE) / price
                qty = float(exchange.amount_to_precision(sym, qty))

                if qty <= 0:
                    continue

                exchange.set_leverage(LEVERAGE, sym)

                exchange.create_market_order(
                    sym,
                    "buy" if direction=="long" else "sell",
                    qty
                )

                trade_state[sym] = {
                    "peak": 0,
                    "entry": price
                }

                bot.send_message(
                    CHAT_ID,
                    f"🧠 {sym} {direction}\nconf:{round(conf,2)}"
                )

                break

            time.sleep(5)

        except Exception as e:
            print("ENGINE:", e)

# ===== MANAGE =====
def manage():
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
                    trade_state[sym] = {"peak": pnl}

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

                    trade_state.pop(sym, None)

                    bot.send_message(
                        CHAT_ID,
                        f"{sym} {round(pnl,2)} USDT"
                    )

            time.sleep(3)

        except Exception as e:
            print("MANAGE:", e)

# ===== START =====
bot.remove_webhook()

threading.Thread(target=engine, daemon=True).start()
threading.Thread(target=manage, daemon=True).start()

bot.send_message(CHAT_ID,"🧠 THINKING AI v11 FIXED AKTİF")
bot.infinity_polling()
