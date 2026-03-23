import os, time, ccxt, telebot, threading
import numpy as np
from tensorflow.keras.models import Sequential, load_model
from tensorflow.keras.layers import LSTM, Dense

# ===== CONFIG =====
LEV = 10
BASE_MARGIN = 1
MAX_POSITIONS = 2
SCAN_DELAY = 8

MODEL_FILE = "ai_model.h5"

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

# ===== MODEL =====
def create_model():
    model = Sequential()
    model.add(LSTM(64, return_sequences=True, input_shape=(20,1)))
    model.add(LSTM(64))
    model.add(Dense(1, activation="sigmoid"))
    model.compile(loss="binary_crossentropy", optimizer="adam")
    return model

def get_prices(sym):
    data = exchange.fetch_ohlcv(sym, "5m", limit=100)
    return [x[4] for x in data]

def prepare(prices):
    X, y = [], []
    for i in range(20, len(prices)-1):
        X.append(prices[i-20:i])
        y.append(1 if prices[i+1] > prices[i] else 0)

    X = np.array(X).reshape(-1,20,1)
    y = np.array(y)
    return X,y

def train_model():
    prices = get_prices("BTC/USDT:USDT")
    X,y = prepare(prices)

    if len(X) < 50:
        return None

    model = create_model()
    model.fit(X,y,epochs=3,batch_size=16,verbose=0)
    model.save(MODEL_FILE)

    bot.send_message(CHAT_ID,"🤖 AI eğitildi")
    return model

def load_ai():
    try:
        return load_model(MODEL_FILE)
    except:
        return None

model = load_ai()

# ===== AI =====
def ai_decision(sym):
    global model

    prices = get_prices(sym)

    if model is None:
        model = train_model()
        return None, 0

    seq = np.array(prices[-20:]).reshape(1,20,1)
    p = model.predict(seq,verbose=0)[0][0]

    if p > 0.6:
        return "long", p
    elif p < 0.4:
        return "short", p
    else:
        return None, p

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

        trade_state[sym] = {
            "dir":dir,
            "entry":price,
            "conf":conf
        }

        bot.send_message(CHAT_ID,f"🚀 {sym} {dir} | AI:{conf:.2f}")

    except Exception as e:
        print(e)

def close_trade(sym,conf):
    pos = exchange.fetch_positions()

    for p in pos:
        if p["symbol"]==sym and float(p["contracts"])>0:

            side = "sell" if trade_state[sym]["dir"]=="long" else "buy"

            exchange.create_market_order(sym,side,float(p["contracts"]),params={"reduceOnly":True})

            bot.send_message(CHAT_ID,f"🏁 {sym} kapandı | AI:{conf:.2f}")

            trade_state.pop(sym)
            break

# ===== MANAGE =====
def manage():
    while True:
        try:
            for sym in list(trade_state.keys()):
                current_dir = trade_state[sym]["dir"]

                decision, conf = ai_decision(sym)

                if decision and decision != current_dir:
                    close_trade(sym,conf)

            time.sleep(5)

        except:
            time.sleep(5)

# ===== SCAN =====
def scanner():
    symbols = ["BTC/USDT:USDT","ETH/USDT:USDT","SOL/USDT:USDT"]

    while True:
        try:
            if len(trade_state) >= MAX_POSITIONS:
                time.sleep(SCAN_DELAY)
                continue

            for sym in symbols:
                d,conf = ai_decision(sym)

                if d:
                    open_trade(sym,d,conf)
                    break

            time.sleep(SCAN_DELAY)

        except:
            time.sleep(5)

# ===== START =====
bot.send_message(CHAT_ID,"🤖 AI başlatıldı")

threading.Thread(target=manage,daemon=True).start()
threading.Thread(target=scanner,daemon=True).start()

while True:
    time.sleep(60)
