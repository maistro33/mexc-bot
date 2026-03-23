import os, time, ccxt, telebot, threading
import numpy as np
from tensorflow.keras.models import Sequential, load_model
from tensorflow.keras.layers import LSTM, Dense

LEV = 10
BASE_MARGIN = 1
MAX_POSITIONS = 2
SCAN_DELAY = 15
MODEL_FILE = "ai_model.h5"

bot = telebot.TeleBot(os.getenv("TELE_TOKEN"))
CHAT_ID = os.getenv("MY_CHAT_ID")

exchange = ccxt.bitget({
    "apiKey": os.getenv("BITGET_API"),
    "secret": os.getenv("BITGET_SEC"),
    "password": "Berfin33",
    "options": {"defaultType": "swap"},
    "enableRateLimit": True
})

trade_state = {}
model = None

# ===== MODEL =====
def create_model():
    m = Sequential()
    m.add(LSTM(64, return_sequences=True, input_shape=(20,1)))
    m.add(LSTM(64))
    m.add(Dense(1, activation="sigmoid"))
    m.compile(loss="binary_crossentropy", optimizer="adam")
    return m

def get_prices(sym):
    try:
        data = exchange.fetch_ohlcv(sym, "5m", limit=100)
        if not data or len(data) < 50:
            return None
        return [x[4] for x in data]
    except:
        return None

def prepare(prices):
    X,y = [],[]
    for i in range(20,len(prices)-1):
        X.append(prices[i-20:i])
        y.append(1 if prices[i+1]>prices[i] else 0)
    X = np.array(X).reshape(-1,20,1)
    y = np.array(y)
    return X,y

def train_model():
    global model
    prices = get_prices("BTC/USDT:USDT")
    if prices is None:
        return

    X,y = prepare(prices)
    if len(X) < 50:
        return

    model = create_model()
    model.fit(X,y,epochs=3,batch_size=16,verbose=0)
    model.save(MODEL_FILE)

    bot.send_message(CHAT_ID,"🤖 AI eğitildi")

def load_ai():
    global model
    try:
        model = load_model(MODEL_FILE)
    except:
        model = None

# ===== AI =====
def ai_decision(sym):
    global model

    try:
        prices = get_prices(sym)
        if prices is None:
            return None, 0

        if model is None:
            train_model()
            return None, 0

        seq = np.array(prices[-20:]).reshape(1,20,1)
        p = model.predict(seq,verbose=0)[0][0]

        if p > 0.6:
            return "long", p
        elif p < 0.4:
            return "short", p
        else:
            return None, p

    except Exception as e:
        print("AI ERROR:", e)
        return None, 0

# ===== TRADE =====
def qty(sym,price):
    return round((BASE_MARGIN*LEV)/price,3)

def open_trade(sym,dir,conf):
    try:
        price = exchange.fetch_ticker(sym)["last"]
        q = qty(sym,price)

        exchange.set_leverage(LEV,sym)
        side = "buy" if dir=="long" else "sell"

        exchange.create_market_order(sym,side,q)

        trade_state[sym] = {"dir":dir}

        bot.send_message(CHAT_ID,f"🚀 {sym} {dir} | AI:{conf:.2f}")

    except Exception as e:
        print("OPEN ERROR:", e)

def close_trade(sym,conf):
    try:
        pos = exchange.fetch_positions()
        for p in pos:
            if p["symbol"]==sym and float(p["contracts"])>0:

                side = "sell" if trade_state[sym]["dir"]=="long" else "buy"

                exchange.create_market_order(
                    sym, side, float(p["contracts"]),
                    params={"reduceOnly":True}
                )

                bot.send_message(CHAT_ID,f"🏁 {sym} kapandı | AI:{conf:.2f}")

                trade_state.pop(sym)
                break
    except Exception as e:
        print("CLOSE ERROR:", e)

# ===== MANAGE =====
def manage():
    while True:
        try:
            for sym in list(trade_state.keys()):
                current_dir = trade_state[sym]["dir"]

                d,conf = ai_decision(sym)

                if d and d != current_dir:
                    close_trade(sym,conf)

            time.sleep(5)
        except Exception as e:
            print("MANAGE ERROR:", e)
            time.sleep(5)

# ===== SCAN =====
def scanner():
    symbols = ["BTC/USDT:USDT","ETH/USDT:USDT","SOL/USDT:USDT"]

    while True:
        try:
            if len(trade_state)>=MAX_POSITIONS:
                time.sleep(SCAN_DELAY)
                continue

            for sym in symbols:
                d,conf = ai_decision(sym)

                if d:
                    open_trade(sym,d,conf)
                    break

            time.sleep(SCAN_DELAY)

        except Exception as e:
            print("SCAN ERROR:", e)
            time.sleep(5)

# ===== START =====
load_ai()
bot.send_message(CHAT_ID,"🤖 AI stabil başlatıldı")

threading.Thread(target=manage,daemon=True).start()
threading.Thread(target=scanner,daemon=True).start()

while True:
    time.sleep(60)
