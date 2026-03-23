import os, time, ccxt, telebot, threading, random, json

# ===== CONFIG =====
LEV = 10
BASE_MARGIN = 1
MAX_POSITIONS = 2
SCAN_DELAY = 10
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
stats = {"total":0,"win":0,"loss":0,"profit":0}

DATA_FILE="memory.json"

def load_memory():
    try:
        with open(DATA_FILE,"r") as f:
            return json.load(f)
    except:
        return []

def save_memory(d):
    with open(DATA_FILE,"w") as f:
        json.dump(d,f)

trade_memory = load_memory()

def safe(x):
    try: return float(x)
    except: return 0

# ===== LOAD OLD POSITIONS =====
def load_positions():
    try:
        pos = exchange.fetch_positions()
        count=0
        for p in pos:
            if safe(p.get("contracts"))<=0:
                continue

            sym=p["symbol"]
            trade_state[sym]={
                "entry":safe(p["entryPrice"]),
                "dir":"long" if p["side"]=="long" else "short",
                "time":time.time()-60,
                "max":0
            }
            count+=1

        bot.send_message(CHAT_ID,f"♻️ {count} pozisyon yüklendi")

    except Exception as e:
        print(e)

# ===== SYMBOLS =====
def get_symbols():
    t=exchange.fetch_tickers()
    arr=[s for s in t if "USDT" in s and ":USDT" in s]
    random.shuffle(arr)
    return arr[:20]

# ===== ANALYSIS =====
def trend(sym):
    c=exchange.fetch_ohlcv(sym,"1h",limit=20)
    cl=[x[4] for x in c]
    return "bull" if cl[-1]>sum(cl[-10:])/10 else "bear"

def momentum(sym):
    c=exchange.fetch_ohlcv(sym,"5m",limit=3)
    ch=(c[-1][4]-c[-2][4])/c[-2][4]
    if ch>0.002: return "up"
    if ch<-0.002: return "down"
    return "flat"

def candle(sym):
    c=exchange.fetch_ohlcv(sym,"5m",limit=1)[0]
    body=abs(c[4]-c[1])
    rng=c[2]-c[3]
    if rng==0: return 0
    return body/rng

def whale(sym):
    ob=exchange.fetch_order_book(sym,10)
    bid=sum([b[1] for b in ob["bids"]])
    ask=sum([a[1] for a in ob["asks"]])
    if bid>ask*1.5: return 1
    if ask>bid*1.5: return -1
    return 0

def squeeze(sym):
    c=exchange.fetch_ohlcv(sym,"5m",limit=3)
    move=(c[-1][4]-c[-2][4])/c[-2][4]
    if move>0.02: return 1
    if move<-0.02: return -1
    return 0

# ===== LEARNING =====
def coin_score(sym):
    data=[t for t in trade_memory if t["symbol"]==sym]
    if len(data)<5: return 0
    return sum(t["roe"] for t in data)/len(data)

def hour_score():
    h=time.localtime().tm_hour
    data=[t for t in trade_memory if t["hour"]==h]
    if len(data)<5: return 0
    return sum(t["roe"] for t in data)/len(data)

# ===== AI DECISION =====
def ai_decision(sym):
    score=0

    score+=2 if trend(sym)=="bull" else -2
    score+=1 if momentum(sym)=="up" else -1 if momentum(sym)=="down" else 0
    score+=2 if candle(sym)>0.6 else 0
    score+=whale(sym)*2
    score+=squeeze(sym)*2

    score+=coin_score(sym)
    score+=hour_score()

    if score>=4: return "long"
    if score<=-4: return "short"
    return None

# ===== QTY FIX =====
def qty(sym,price):
    m=exchange.load_markets()[sym]
    min_qty=float(m.get('limits',{}).get('amount',{}).get('min',0))
    prec=int(m.get('precision',{}).get('amount',3))

    q=round((BASE_MARGIN*LEV)/price,prec)
    return max(q,min_qty)

# ===== OPEN =====
def open_trade(sym,dir):
    try:
        price=exchange.fetch_ticker(sym)["last"]
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

    if dir=="long" and price<=entry*(1-SL_PERCENT): return True
    if dir=="short" and price>=entry*(1+SL_PERCENT): return True

    if roe>st["max"]: st["max"]=roe

    if roe < st["max"]-10:
        return True

    return False

# ===== LOG =====
def log(sym,dir,roe):
    global trade_memory

    trade_memory.append({
        "symbol":sym,
        "roe":roe,
        "hour":time.localtime().tm_hour
    })

    save_memory(trade_memory)

    stats["total"]+=1
    stats["profit"]+=roe
    stats["win"]+=1 if roe>0 else 0
    stats["loss"]+=1 if roe<=0 else 0

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
                    trade_state[sym]={
                        "entry":safe(p["entryPrice"]),
                        "dir":"long" if p["side"]=="long" else "short",
                        "time":time.time()-60,
                        "max":0
                    }

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
            print(e)
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
            print(e)
            time.sleep(5)

# ===== START =====
print("🔥 FULL AI START")

load_positions()

threading.Thread(target=manage,daemon=True).start()
threading.Thread(target=scanner,daemon=True).start()
threading.Thread(target=bot.infinity_polling,daemon=True).start()

bot.send_message(CHAT_ID,"🔥 FULL AI AKTİF")

while True:
    time.sleep(60)
