import os
import time
import ccxt
import telebot
import threading
import random
import json

# ===== CONFIG =====
LEV = 10
BASE_MARGIN = 2
MAX_POSITIONS = 2

SCAN_DELAY = 10
MIN_VOLUME = 1000000

SL_PERCENT = 0.012
MIN_HOLD = 40

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

# ===== DATA =====
trade_state = {}
cooldown = {}
stats = {"total":0,"win":0,"loss":0,"profit":0}

DATA_FILE = "memory.json"

def load_memory():
    try:
        with open(DATA_FILE,"r") as f:
            return json.load(f)
    except:
        return []

def save_memory(data):
    with open(DATA_FILE,"w") as f:
        json.dump(data,f)

trade_memory = load_memory()

# ===== SAFE =====
def safe(x):
    try: return float(x)
    except: return 0

# ===== SYMBOLS =====
def get_symbols():
    tickers = exchange.fetch_tickers()
    arr = []
    for sym,d in tickers.items():
        if "USDT" not in sym or ":USDT" not in sym:
            continue
        if safe(d.get("quoteVolume")) < MIN_VOLUME:
            continue
        arr.append(sym)
    random.shuffle(arr)
    return arr[:20]

# ===== TREND =====
def get_trend(sym):
    c = exchange.fetch_ohlcv(sym,"1h",limit=20)
    closes=[x[4] for x in c]
    return "bull" if closes[-1] > sum(closes[-10:])/10 else "bear"

# ===== MOMENTUM =====
def momentum(sym):
    c = exchange.fetch_ohlcv(sym,"5m",limit=3)
    ch=(c[-1][4]-c[-2][4])/c[-2][4]
    if ch>0.002: return "up"
    if ch<-0.002: return "down"
    return "flat"

# ===== CANDLE AI =====
def candle(sym):
    c = exchange.fetch_ohlcv(sym,"5m",limit=1)[0]
    body=abs(c[4]-c[1])
    rng=c[2]-c[3]
    if rng==0: return "weak"
    if body/rng>0.6: return "strong"
    return "weak"

# ===== WHALE =====
def whale(sym):
    ob = exchange.fetch_order_book(sym,limit=10)
    bid=sum([b[1] for b in ob["bids"]])
    ask=sum([a[1] for a in ob["asks"]])
    if bid>ask*1.5: return "long"
    if ask>bid*1.5: return "short"
    return None

# ===== SQUEEZE =====
def squeeze(sym):
    c = exchange.fetch_ohlcv(sym,"5m",limit=3)
    move=(c[-1][4]-c[-2][4])/c[-2][4]
    if move>0.02: return "long"
    if move<-0.02: return "short"
    return None

# ===== AI DECISION =====
def ai_decision(sym):
    t=get_trend(sym)
    m=momentum(sym)
    c=candle(sym)
    w=whale(sym)
    s=squeeze(sym)

    score=0

    if t=="bull": score+=2
    if t=="bear": score-=2

    if m=="up": score+=1
    if m=="down": score-=1

    if c=="strong": score+=1

    if w=="long": score+=2
    if w=="short": score-=2

    if s=="long": score+=2
    if s=="short": score-=2

    if score>=4: return "long"
    if score<=-4: return "short"
    return None

# ===== QTY =====
def qty(sym,price):
    return float(exchange.amount_to_precision(sym,(BASE_MARGIN*LEV)/price))

# ===== OPEN =====
def open_trade(sym,dir):
    try:
        ticker=exchange.fetch_ticker(sym)
        price=ticker["last"]
        q=qty(sym,price)

        exchange.set_leverage(LEV,sym)
        side="buy" if dir=="long" else "sell"
        exchange.create_market_order(sym,side,q)

        trade_state[sym]={"entry":price,"dir":dir,"time":time.time(),"max":0}

        bot.send_message(CHAT_ID,f"🚀 {sym} {dir}")
    except Exception as e:
        print(e)

# ===== EXIT =====
def should_exit(sym,price,roe):
    st=trade_state[sym]

    if time.time()-st["time"]<MIN_HOLD:
        return False

    entry=st["entry"]
    dir=st["dir"]

    if dir=="long" and price<=entry*(1-SL_PERCENT):
        return True
    if dir=="short" and price>=entry*(1+SL_PERCENT):
        return True

    if roe>st["max"]:
        st["max"]=roe

    if roe < st["max"]-10:
        return True

    return False

# ===== LOG =====
def log(sym,dir,roe):
    global trade_memory

    trade_memory.append({"symbol":sym,"roe":roe})
    save_memory(trade_memory)

    stats["total"]+=1
    stats["profit"]+=roe

    if roe>0: stats["win"]+=1
    else: stats["loss"]+=1

# ===== MANAGE =====
def manage():
    while True:
        try:
            pos=exchange.fetch_positions()
            for p in pos:
                if safe(p.get("contracts"))<=0:
                    continue

                sym=p["symbol"]
                if sym not in trade_state:
                    continue

                price=exchange.fetch_ticker(sym)["last"]
                entry=trade_state[sym]["entry"]
                dir=trade_state[sym]["dir"]

                roe=((price-entry)/entry*100)*LEV if dir=="long" else ((entry-price)/entry*100)*LEV

                if should_exit(sym,price,roe):
                    side="sell" if dir=="long" else "buy"
                    exchange.create_market_order(sym,side,safe(p["contracts"]),params={"reduceOnly":True})

                    log(sym,dir,roe)
                    trade_state.pop(sym)

                    bot.send_message(CHAT_ID,f"🏁 EXIT {sym} {roe:.2f}%")

            time.sleep(2)

        except Exception as e:
            print("MANAGE:",e)
            time.sleep(3)

# ===== SCANNER =====
def scanner():
    while True:
        try:
            if len(trade_state)>=MAX_POSITIONS:
                time.sleep(SCAN_DELAY)
                continue

            for sym in get_symbols():
                d=ai_decision(sym)
                if d:
                    open_trade(sym,d)
                    break

            time.sleep(SCAN_DELAY)

        except Exception as e:
            print("SCAN:",e)
            time.sleep(5)

# ===== START =====
print("🔥 FINAL AI BOT STARTED")

threading.Thread(target=manage,daemon=True).start()
threading.Thread(target=scanner,daemon=True).start()
threading.Thread(target=bot.infinity_polling,daemon=True).start()

bot.send_message(CHAT_ID,"🔥 FINAL AI AKTİF")

while True:
    time.sleep(60)
