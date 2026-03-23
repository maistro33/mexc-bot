import os, time, ccxt, telebot, threading, json
from sklearn.ensemble import RandomForestClassifier

# ===== CONFIG =====
LEV = 10
BASE_MARGIN = 1
MAX_POSITIONS = 2
SCAN_DELAY = 10
MIN_VOLUME = 100000
MIN_CONF = 0.65

# ===== TELEGRAM =====
bot = telebot.TeleBot(os.getenv("TELE_TOKEN"))
CHAT_ID = os.getenv("MY_CHAT_ID")

# ===== EXCHANGE =====
exchange = ccxt.bitget({
    "apiKey": os.getenv("BITGET_API"),
    "secret": os.getenv("BITGET_SEC"),
    "password": "Berfin33",
    "options": {"defaultType": "swap"},
    "enableRateLimit": True
})

trade_state = {}
stats = {"total":0,"win":0,"loss":0,"profit":0}
DATA_FILE="memory.json"

def load_memory():
    try:
        return json.load(open(DATA_FILE))
    except:
        return []

def save_memory(d):
    json.dump(d, open(DATA_FILE,"w"))

trade_memory = load_memory()

def safe(x):
    try: return float(x)
    except: return 0

# ===== FEATURE (NUMPY YOK) =====
def get_features(sym):
    try:
        c5 = exchange.fetch_ohlcv(sym,"5m",limit=30)
        c1h = exchange.fetch_ohlcv(sym,"1h",limit=20)

        closes5 = [x[4] for x in c5]
        highs5 = [x[2] for x in c5]
        lows5 = [x[3] for x in c5]
        vol5 = [x[5] for x in c5]

        closes1h = [x[4] for x in c1h]

        volatility = (max(highs5)-min(lows5)) / min(lows5)

        mom = (closes5[-1]-closes5[-5]) / closes5[-5]

        trend1h = 1 if closes1h[-1] > sum(closes1h)/len(closes1h) else -1

        vol_avg = sum(vol5)/len(vol5)
        vol_spike = vol5[-1]/vol_avg if vol_avg else 0

        body = abs(c5[-1][4]-c5[-1][1])
        rng = c5[-1][2]-c5[-1][3]
        candle = body/rng if rng else 0

        return [volatility, mom, trend1h, vol_spike, candle]

    except:
        return None

# ===== AI =====
ml_model = None

def train_model():
    global ml_model
    X,y = [],[]

    for t in trade_memory:
        if "features" not in t:
            continue
        X.append(t["features"])
        y.append(1 if t["roe"]>0 else 0)

    if len(X) < 40:
        return

    ml_model = RandomForestClassifier(n_estimators=150)
    ml_model.fit(X,y)

    print("🤖 AI TRAINED")

def ai_decision(sym):
    f = get_features(sym)

    if ml_model and f:
        try:
            p = ml_model.predict_proba([f])[0][1]

            print(f"AI {sym}: {p:.2f}")

            if p > MIN_CONF:
                return "long"
            elif p < (1-MIN_CONF):
                return "short"
        except:
            pass

    return None

def ai_exit(sym,dir):
    f = get_features(sym)

    if ml_model and f:
        try:
            p = ml_model.predict_proba([f])[0][1]

            if dir=="long" and p<0.45:
                return True
            if dir=="short" and p>0.55:
                return True
        except:
            pass

    return False

# ===== FILTER =====
def allow_trade(sym):
    try:
        t = exchange.fetch_ticker(sym)

        if t["quoteVolume"] < MIN_VOLUME:
            return False

        if (t["ask"] - t["bid"]) > t["last"]*0.002:
            return False

    except:
        return False

    return True

# ===== TRADE =====
def qty(sym,price):
    return round((BASE_MARGIN*LEV)/price,3)

def open_trade(sym,dir):
    try:
        price = exchange.fetch_ticker(sym)["last"]
        q = qty(sym,price)

        exchange.set_leverage(LEV,sym)
        side = "buy" if dir=="long" else "sell"

        exchange.create_market_order(sym,side,q)

        trade_state[sym]={"dir":dir}

        bot.send_message(CHAT_ID,f"🚀 {sym} {dir}")

    except Exception as e:
        print("OPEN:",e)

def close_trade(sym):
    pos = exchange.fetch_positions()

    for p in pos:
        if p["symbol"]==sym and safe(p["contracts"])>0:

            side = "sell" if trade_state[sym]["dir"]=="long" else "buy"

            exchange.create_market_order(sym,side,safe(p["contracts"]),params={"reduceOnly":True})

            trade_state.pop(sym)
            bot.send_message(CHAT_ID,f"🏁 {sym} kapandı")
            break

# ===== LOG =====
def log(sym,roe):
    trade_memory.append({
        "symbol":sym,
        "roe":roe,
        "features":get_features(sym)
    })

    save_memory(trade_memory)

    stats["total"]+=1
    stats["profit"]+=roe
    stats["win"]+=1 if roe>0 else 0
    stats["loss"]+=1 if roe<=0 else 0

    if stats["total"]%10==0:
        train_model()

# ===== MANAGE =====
def manage():
    while True:
        try:
            pos = exchange.fetch_positions()

            for p in pos:
                if safe(p.get("contracts"))<=0:
                    continue

                sym = p["symbol"]
                dir = "long" if p["side"]=="long" else "short"

                if ai_exit(sym,dir):
                    close_trade(sym)

            time.sleep(3)

        except:
            time.sleep(5)

# ===== SCANNER =====
def scanner():
    while True:
        try:
            if len(trade_state)>=MAX_POSITIONS:
                time.sleep(SCAN_DELAY)
                continue

            symbols = list(exchange.fetch_tickers().keys())

            for sym in symbols:

                if "USDT" not in sym or ":USDT" not in sym:
                    continue

                if not allow_trade(sym):
                    continue

                d = ai_decision(sym)

                if d:
                    open_trade(sym,d)
                    break

            time.sleep(SCAN_DELAY)

        except:
            time.sleep(5)

# ===== START =====
print("🔥 STABLE AI START")

train_model()

threading.Thread(target=manage,daemon=True).start()
threading.Thread(target=scanner,daemon=True).start()
threading.Thread(target=bot.infinity_polling,daemon=True).start()

bot.send_message(CHAT_ID,"🤖 STABLE AI AKTİF")

while True:
    time.sleep(60)
