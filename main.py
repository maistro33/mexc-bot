import os, time, ccxt, telebot, threading, random, json

# ===== CONFIG =====
LEV = 10
BASE_MARGIN = 1
MAX_POSITIONS = 2
SCAN_DELAY = 10

SL_PERCENT = 0.012
MIN_HOLD = 40
FEE = 0.08

# ===== AI SETTINGS =====
AI_SETTINGS = {
    "min_score": 6,
    "aggression": 1.0
}

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
trade_memory=[]

def safe(x):
    try: return float(x)
    except: return 0

# ===== AUTO OPTIMIZE =====
def auto_optimize():
    if len(trade_memory) < 20:
        return

    last = trade_memory[-20:]
    wins = [t for t in last if t["roe"] > 0]
    winrate = len(wins)/len(last)

    if winrate < 0.4:
        AI_SETTINGS["min_score"] += 1
        AI_SETTINGS["aggression"] *= 0.8

    elif winrate > 0.6:
        AI_SETTINGS["min_score"] -= 1
        AI_SETTINGS["aggression"] *= 1.1

    AI_SETTINGS["min_score"] = max(4, min(8, AI_SETTINGS["min_score"]))
    AI_SETTINGS["aggression"] = max(0.5, min(1.5, AI_SETTINGS["aggression"]))

# ===== KILL SWITCH =====
def kill_switch():
    if stats["profit"] < -10:
        return True
    return False

# ===== ANALYSIS =====
def trend(sym):
    c=exchange.fetch_ohlcv(sym,"1h",limit=20)
    cl=[x[4] for x in c]
    return 1 if cl[-1]>sum(cl[-10:])/10 else -1

def momentum(sym):
    c=exchange.fetch_ohlcv(sym,"5m",limit=3)
    ch=(c[-1][4]-c[-2][4])/c[-2][4]
    if ch>0.002: return 1
    if ch<-0.002: return -1
    return 0

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

# ===== AI DECISION =====
def ai_decision(sym):
    score = trend(sym)*2 + momentum(sym) + whale(sym)*2 + squeeze(sym)*2

    if score >= AI_SETTINGS["min_score"]:
        return "long"
    if score <= -AI_SETTINGS["min_score"]:
        return "short"
    return None

# ===== QTY =====
def qty(sym,price):
    return (BASE_MARGIN * AI_SETTINGS["aggression"] * LEV) / price

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
def log(sym,roe):
    trade_memory.append({"symbol":sym,"roe":roe})

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

                raw=((price-entry)/entry*100)*LEV if dir=="long" else ((entry-price)/entry*100)*LEV
                roe=raw-FEE

                if should_exit(sym,price,roe):
                    side="sell" if dir=="long" else "buy"
                    exchange.create_market_order(sym,side,safe(p["contracts"]),params={"reduceOnly":True})

                    log(sym,roe)
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
            if kill_switch():
                print("STOPPED - RISK")
                time.sleep(30)
                continue

            auto_optimize()

            if len(trade_state)>=MAX_POSITIONS:
                time.sleep(SCAN_DELAY)
                continue

            symbols=list(exchange.fetch_tickers().keys())

            for sym in symbols:
                if "USDT" not in sym or ":USDT" not in sym:
                    continue

                d=ai_decision(sym)
                if d:
                    open_trade(sym,d)
                    break

            time.sleep(SCAN_DELAY)

        except Exception as e:
            print(e)
            time.sleep(5)

# ===== START =====
print("🔥 FULL OTONOM AI START")

threading.Thread(target=manage,daemon=True).start()
threading.Thread(target=scanner,daemon=True).start()
threading.Thread(target=bot.infinity_polling,daemon=True).start()

bot.send_message(CHAT_ID,"🔥 FULL OTONOM AI AKTİF")

while True:
    time.sleep(60)
