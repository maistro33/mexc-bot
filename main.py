import os
import time
import ccxt
import telebot
import threading

# ===== SETTINGS =====
AGGR_VOLUME = 200_000
TOP_COINS = 100
MAX_TRADES = 2   # 🔥 agresif

bot = telebot.TeleBot(os.getenv("TELE_TOKEN"))
CHAT_ID = os.getenv("MY_CHAT_ID")

exchange = ccxt.bitget({
    "apiKey": os.getenv("BITGET_API"),
    "secret": os.getenv("BITGET_SEC"),
    "password": "Berfin33",
    "options": {"defaultType": "swap"},
    "enableRateLimit": True
})

exchange.load_markets()

active_trades = set()
trade_state = {}
last_trade_time = {}
trade_memory = {}

lock = threading.Lock()
current_margin = 5

# ===== SAFE =====
def safe(x):
    try: return float(x)
    except: return 0.0

def safe_api(call):
    try:
        return call()
    except:
        return None

# ===== ORDERBOOK =====
def ob(sym):
    o = safe_api(lambda: exchange.fetch_order_book(sym, 5))
    if not o: return 0
    b = sum(x[1] for x in o["bids"])
    a = sum(x[1] for x in o["asks"])
    return (b-a)/(b+a) if (b+a) else 0

# ===== LEVERAGE =====
def get_lev(sym):
    try:
        c = exchange.fetch_ohlcv(sym,"5m",20)
        cl = [x[4] for x in c]
        strength = abs(cl[-1]-cl[-5])/cl[-5]
        o = ob(sym)

        if strength>0.01 and o>0: return 12
        if strength>0.005: return 8
        return 5
    except:
        return 5

# ===== DECISION =====
def decide(sym):
    try:
        h1 = exchange.fetch_ohlcv(sym,"1h",50)
        m5 = exchange.fetch_ohlcv(sym,"5m",30)

        h1c = [x[4] for x in h1]
        m5c = [x[4] for x in m5]

        trend_big = h1c[-1] > sum(h1c[-20:])/20
        trend = m5c[-1] > sum(m5c[-10:])/10
        momentum = m5c[-1] > m5c[-3]

        up = m5c[-1] > m5c[-2] > m5c[-3]
        down = m5c[-1] < m5c[-2] < m5c[-3]

        highs = [x[2] for x in m5]
        lows = [x[3] for x in m5]

        fake_up = m5c[-1]>max(highs[-10:]) and m5c[-2]<max(highs[-10:])
        fake_down = m5c[-1]<min(lows[-10:]) and m5c[-2]>min(lows[-10:])

        o = ob(sym)

        # 🧠 MEMORY
        mem = trade_memory.get(sym)
        if mem:
            t = mem["win"]+mem["loss"]
            if t>=5:
                wr = mem["win"]/t
                if wr<0.4: return None

        if trend_big and trend and momentum and up and not fake_up and o>0:
            return "long"

        if (not trend_big) and (not trend) and (not momentum) and down and not fake_down and o<0:
            return "short"

        return None

    except:
        return None

# ===== EXIT =====
def exit_check(sym,pnl,dir,open_time):
    if time.time()-open_time<60: return False
    if abs(pnl)<0.4: return False

    try:
        m5 = exchange.fetch_ohlcv(sym,"5m",20)
        c = [x[4] for x in m5]

        trend = c[-1] > sum(c[-10:])/10
        momentum = c[-1] > c[-3]

        if dir=="long" and (not trend and not momentum):
            return True

        if dir=="short" and (trend and momentum):
            return True

        # 🔥 zarar büyüyorsa çık
        if pnl < -1:
            return True

        return False

    except:
        return False

# ===== SYMBOLS =====
def symbols():
    t = safe_api(lambda: exchange.fetch_tickers())
    if not t: return []

    f = [(s,safe(d.get("quoteVolume"))) for s,d in t.items() if ":USDT" in s]
    f = [x for x in f if x[1]>=AGGR_VOLUME]
    f.sort(key=lambda x:x[1],reverse=True)
    return [x[0] for x in f[:TOP_COINS]]

# ===== ENGINE =====
def engine():
    global current_margin

    while True:
        try:
            for sym in symbols():

                if len(active_trades)>=MAX_TRADES:
                    break

                if sym in active_trades:
                    continue

                if time.time()-last_trade_time.get(sym,0)<120:
                    continue

                t = safe_api(lambda: exchange.fetch_ticker(sym))
                if not t: continue

                price = safe(t["last"])
                if price<0.001 or price>200: continue

                d = decide(sym)
                if not d: continue

                with lock:

                    lev = get_lev(sym)

                    try: exchange.set_margin_mode("cross", sym)
                    except: pass
                    try: exchange.set_leverage(lev, sym)
                    except: pass

                    m = exchange.market(sym)
                    min_q = m['limits']['amount']['min'] or 0.001

                    qty = max((current_margin*lev)/price, min_q)
                    qty = float(exchange.amount_to_precision(sym, qty))

                    safe_api(lambda: exchange.create_market_order(
                        sym,"buy" if d=="long" else "sell",qty
                    ))

                    trade_state[sym] = {"dir":d,"time":time.time()}
                    active_trades.add(sym)
                    last_trade_time[sym]=time.time()

                    bot.send_message(CHAT_ID,f"🚀 {sym} {d} x{lev}")
                    break

            time.sleep(10)

        except:
            time.sleep(5)

# ===== MANAGE =====
def manage():
    global current_margin

    while True:
        try:
            pos = safe_api(lambda: exchange.fetch_positions())
            if not pos:
                time.sleep(5)
                continue

            for p in pos:

                qty = safe(p.get("contracts"))
                if qty<=0: continue

                sym = p["symbol"]
                if sym not in trade_state: continue

                dir = "long" if p["side"]=="long" else "short"
                pnl = safe(p.get("unrealizedPnl"))

                st = trade_state[sym]

                if exit_check(sym,pnl,dir,st["time"]):

                    safe_api(lambda: exchange.create_market_order(
                        sym,"sell" if dir=="long" else "buy",
                        qty,params={"reduceOnly":True}
                    ))

                    active_trades.discard(sym)
                    trade_state.pop(sym,None)

                    # 🧠 LEARNING
                    if sym not in trade_memory:
                        trade_memory[sym]={"win":0,"loss":0}

                    if pnl>0:
                        trade_memory[sym]["win"]+=1
                        current_margin+=1
                    else:
                        trade_memory[sym]["loss"]+=1
                        current_margin-=1

                    current_margin=max(3,min(15,current_margin))

                    bot.send_message(CHAT_ID,f"❌ {sym} {round(pnl,2)}")

            time.sleep(5)

        except:
            time.sleep(5)

# ===== START =====
bot.remove_webhook()
time.sleep(1)

threading.Thread(target=engine,daemon=True).start()
threading.Thread(target=manage,daemon=True).start()

bot.send_message(CHAT_ID,"🔥 ULTRA AI AKTİF")
bot.infinity_polling()
