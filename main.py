import os
import time
import ccxt
import telebot
import threading
from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

SAFE_VOLUME = 1_500_000
AGGR_VOLUME = 800_000

SAFE_LEV = 5
AGGR_LEV = 5

MARGIN = 3
TOP_COINS = 100

STEP_LEVELS = [1,2,3,4,5]

ANTI_DUMP_PCT = 0.04
MAX_TRADES = 1

MIN_TP_USDT = 0.50
FEE_BUFFER = 0.05

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

def safe(x):
    try: return float(x)
    except: return 0.0

def get_candles(sym, tf, limit=100):
    try: return exchange.fetch_ohlcv(sym, tf, limit=limit)
    except: return []

def total_open_positions():
    try:
        return sum(1 for p in exchange.fetch_positions() if safe(p.get("contracts")) > 0)
    except:
        return 0

# ===== AI =====
def ai_decision(sym, direction, score, ob):
    try:
        h1 = get_candles(sym,"1h",50)
        m5 = get_candles(sym,"5m",30)

        if len(h1)<30 or len(m5)<20:
            return "SKIP"

        closes1=[c[4] for c in h1]
        closes5=[c[4] for c in m5]

        trend = "UP" if closes1[-1] > sum(closes1[-20:])/20 else "DOWN"
        momentum = "UP" if closes5[-1] > closes5[-3] else "DOWN"

        highs=[c[2] for c in m5]
        lows=[c[3] for c in m5]

        range_size = max(highs[-10:]) - min(lows[-10:])
        range_pct = range_size / closes5[-1]

        prompt = f"""
You are a professional crypto trader.

Trend: {trend}
Momentum: {momentum}
Range: {range_pct}
Score: {score}
Orderbook: {ob}

Avoid range and weak setups.

Answer ONLY: LONG, SHORT or SKIP
"""

        res = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role":"user","content":prompt}],
            temperature=0.2
        )

        decision = res.choices[0].message.content.strip().upper()

        if decision not in ["LONG","SHORT"]:
            return "SKIP"

        return decision

    except Exception as e:
        print("AI ERROR:",e)
        return "SKIP"

def get_symbols(volume):
    try:
        t = exchange.fetch_tickers()
        f = [(s, safe(d.get("quoteVolume"))) for s,d in t.items() if ":USDT" in s]
        f = [x for x in f if x[1]>=volume]
        f.sort(key=lambda x:x[1], reverse=True)
        return [x[0] for x in f[:TOP_COINS]]
    except:
        return []

def get_direction(sym):
    d = get_candles(sym,"1d",50)
    if len(d)<5: return None
    highs=[c[2] for c in d]
    lows=[c[3] for c in d]
    if highs[-1]>highs[-5]: return "long"
    if lows[-1]<lows[-5]: return "short"
    return None

# ===== 🔥 FIXED ANTI-DUMP =====
def anti_dump(sym, pnl):
    try:
        if pnl > -0.3:
            return False

        c = get_candles(sym,"3m",3)
        if len(c)<3: return False

        change = abs(c[-1][4]-c[-3][4]) / c[-3][4]

        return change > ANTI_DUMP_PCT
    except:
        return False

def trend_filter(sym, direction):
    c = get_candles(sym,"15m",50)
    if len(c)<20: return True
    avg = sum(x[4] for x in c[-20:]) / 20
    return direction=="long" if c[-1][4]>avg else direction=="short"

def volume_spike(sym):
    c = get_candles(sym,"5m",20)
    if len(c)<10: return False
    v=[x[5] for x in c]
    return v[-1] > (sum(v[:-1])/len(v[:-1]))*1.5

def orderbook_imbalance(sym):
    try:
        ob = exchange.fetch_order_book(sym,10)
        bids=sum(b[1] for b in ob["bids"])
        asks=sum(a[1] for a in ob["asks"])
        return (bids-asks)/(bids+asks) if bids+asks else 0
    except:
        return 0

def calculate_score(sym, direction):
    score=0
    if volume_spike(sym): score+=2
    ob=orderbook_imbalance(sym)
    if direction=="long" and ob>0.1: score+=2
    if direction=="short" and ob<-0.1: score+=2
    return score

def sync_positions():
    try:
        for p in exchange.fetch_positions():
            qty = safe(p.get("contracts"))
            if qty<=0: continue
            sym = p["symbol"]
            entry = safe(p["entryPrice"])
            side = p["side"]
            direction = "long" if side=="long" else "short"

            if sym not in trade_state:
                sl = entry*0.98 if direction=="long" else entry*1.02
                trade_state[sym]={
                    "sl":sl,
                    "tp1":False,
                    "step":0,
                    "initial_risk":abs(entry-sl)
                }
                active_trades.add(sym)
                bot.send_message(CHAT_ID,f"♻️ SYNC {sym}")
    except:
        pass

def trade_engine(mode):
    while True:
        try:
            vol = SAFE_VOLUME if mode=="SAFE" else AGGR_VOLUME
            lev = SAFE_LEV if mode=="SAFE" else AGGR_LEV

            for sym in get_symbols(vol):

                if len(active_trades) >= MAX_TRADES:
                    break

                if sym in active_trades:
                    continue

                direction = get_direction(sym)
                if not direction:
                    continue

                if mode=="AGGRESSIVE" and not trend_filter(sym, direction):
                    continue

                score = calculate_score(sym, direction)
                if score < (4 if mode=="SAFE" else 3):
                    continue

                ob = orderbook_imbalance(sym)

                decision = ai_decision(sym, direction, score, ob)
                if decision == "SKIP":
                    continue

                if decision == "LONG":
                    direction="long"
                elif decision=="SHORT":
                    direction="short"

                price = safe(exchange.fetch_ticker(sym)["last"])
                qty = float(exchange.amount_to_precision(sym,(MARGIN*lev)/price))

                exchange.create_market_order(sym,"buy" if direction=="long" else "sell",qty)

                sl = price*0.98 if direction=="long" else price*1.02

                trade_state[sym]={
                    "sl":sl,
                    "tp1":False,
                    "step":0,
                    "initial_risk":abs(price-sl)
                }

                active_trades.add(sym)
                bot.send_message(CHAT_ID,f"🤖 AI {mode} {sym} {direction}")
                break

            time.sleep(10)

        except Exception as e:
            print("ENTRY ERROR:",e)
            time.sleep(10)

def manage():
    while True:
        try:
            sync_positions()

            for p in exchange.fetch_positions():

                qty = safe(p.get("contracts"))
                if qty<=0: continue

                sym = p["symbol"]
                if sym not in trade_state: continue

                entry = safe(p["entryPrice"])
                price = safe(exchange.fetch_ticker(sym)["last"])
                direction = "long" if p["side"]=="long" else "short"

                pnl = safe(p.get("unrealizedPnl"))

                st = trade_state[sym]

                if anti_dump(sym, pnl):
                    exchange.create_market_order(sym,"sell" if direction=="long" else "buy",qty,params={"reduceOnly":True})
                    trade_state.pop(sym,None)
                    active_trades.discard(sym)
                    bot.send_message(CHAT_ID,f"⚠️ ANTI-DUMP {sym}")
                    continue

                position_size = qty * price
                dynamic_tp = max(MIN_TP_USDT, position_size * 0.01) + FEE_BUFFER

                if not st["tp1"] and pnl >= dynamic_tp:
                    exchange.create_market_order(sym,"sell" if direction=="long" else "buy",qty*0.4,params={"reduceOnly":True})
                    st["tp1"]=True
                    st["sl"]=entry
                    bot.send_message(CHAT_ID,f"💰 TP1 {sym} {round(pnl,2)}")

                if st["tp1"]:
                    risk = st["initial_risk"]
                    r = abs(price-entry)/risk if risk>0 else 0

                    for lvl in STEP_LEVELS:
                        if r>=lvl and st["step"]<lvl:
                            st["step"]=lvl
                            st["sl"]=entry+(lvl-1)*risk if direction=="long" else entry-(lvl-1)*risk
                            bot.send_message(CHAT_ID,f"📈 STEP {lvl} {sym}")

                if (direction=="long" and price<=st["sl"]) or (direction=="short" and price>=st["sl"]):
                    exchange.create_market_order(sym,"sell" if direction=="long" else "buy",qty,params={"reduceOnly":True})
                    trade_state.pop(sym,None)
                    active_trades.discard(sym)
                    bot.send_message(CHAT_ID,f"❌ STOP {sym}")

            time.sleep(5)

        except Exception as e:
            print("MANAGE ERROR:",e)
            time.sleep(5)

exchange.fetch_balance()
bot.remove_webhook()
time.sleep(1)

sync_positions()

threading.Thread(target=trade_engine,args=("SAFE",),daemon=True).start()
threading.Thread(target=trade_engine,args=("AGGRESSIVE",),daemon=True).start()
threading.Thread(target=manage,daemon=True).start()

bot.send_message(CHAT_ID,"🔥 FINAL PRO AI BOT")
bot.infinity_polling()
