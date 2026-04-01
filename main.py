import os
import time
import ccxt
import telebot
import threading

# ===== SETTINGS =====
SAFE_VOLUME = 1_500_000
AGGR_VOLUME = 800_000

SAFE_LEV = 7
AGGR_LEV = 7

MARGIN = 5
TOP_COINS = 100

TP_SPLIT = [0.4, 0.3, 0.3]
TRAIL_GAP = 0.01

TP1_USDT = 0.80
STEP_LEVELS = [1, 2, 3, 4, 5]

ANTI_DUMP_PCT = 0.004

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

exchange.load_markets()

# ===== GLOBAL =====
active_trades = set()
trade_state = {}

# ===== HELPERS =====
def safe(x):
    try: return float(x)
    except: return 0.0

def get_candles(sym, tf, limit=100):
    try: return exchange.fetch_ohlcv(sym, tf, limit=limit)
    except: return []

# ===== MARKET =====
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
    d = get_candles(sym, "1d", 50)
    if len(d)<5: return None
    highs=[c[2] for c in d]
    lows=[c[3] for c in d]
    if highs[-1]>highs[-5]: return "long"
    if lows[-1]<lows[-5]: return "short"
    return None

# ===== ANTI DUMP =====
def anti_dump(sym):
    try:
        c = get_candles(sym, "1m", 3)
        if len(c) < 2: return False
        change = abs(c[-1][4] - c[-2][4]) / c[-2][4]
        return change > ANTI_DUMP_PCT
    except:
        return False

# ===== TREND =====
def trend_filter(sym, direction):
    c = get_candles(sym, "15m", 50)
    if len(c)<20: return True
    avg = sum(x[4] for x in c[-20:]) / 20
    return direction == "long" if c[-1][4] > avg else direction == "short"

# ===== SIGNAL =====
def volume_spike(sym):
    c = get_candles(sym, "5m", 20)
    if len(c)<10: return False
    v=[x[5] for x in c]
    return v[-1] > (sum(v[:-1])/len(v[:-1]))*1.5

def orderbook_imbalance(sym):
    try:
        ob = exchange.fetch_order_book(sym, 10)
        bids = sum(b[1] for b in ob["bids"])
        asks = sum(a[1] for a in ob["asks"])
        return (bids-asks)/(bids+asks) if bids+asks else 0
    except:
        return 0

def calculate_score(sym, direction):
    score = 0
    if volume_spike(sym): score+=2
    ob = orderbook_imbalance(sym)
    if direction=="long" and ob>0.1: score+=2
    if direction=="short" and ob<-0.1: score+=2
    return score

# ===== RECOVERY =====
def load_open_positions():
    try:
        for p in exchange.fetch_positions():
            qty = safe(p.get("contracts"))
            if qty<=0: continue
            sym = p["symbol"]
            entry = safe(p["entryPrice"])
            sl = entry*0.98
            trade_state[sym]={
                "sl":sl,
                "tp1":False,
                "step":0,
                "initial_risk":abs(entry-sl)
            }
            active_trades.add(sym)
    except:
        pass

# ===== ENTRY =====
def trade_engine(mode):
    while True:
        try:
            vol = SAFE_VOLUME if mode=="SAFE" else AGGR_VOLUME
            lev = SAFE_LEV if mode=="SAFE" else AGGR_LEV

            for sym in get_symbols(vol):

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
                bot.send_message(CHAT_ID,f"🚀 {mode} {sym} {direction}")
                break

            time.sleep(10)

        except Exception as e:
            print("ENTRY ERROR:",e)
            time.sleep(10)

# ===== MANAGE =====
def manage():
    while True:
        try:
            for p in exchange.fetch_positions():

                qty = safe(p.get("contracts"))
                if qty<=0: continue

                sym = p["symbol"]
                if sym not in trade_state: continue

                entry = safe(p["entryPrice"])
                price = safe(exchange.fetch_ticker(sym)["last"])
                direction = "long" if p["side"]=="long" else "short"

                st = trade_state[sym]

                # anti dump
                if anti_dump(sym):
                    exchange.create_market_order(sym,"sell" if direction=="long" else "buy",qty,params={"reduceOnly":True})
                    trade_state.pop(sym,None)
                    active_trades.discard(sym)
                    bot.send_message(CHAT_ID,f"⚠️ ANTI-DUMP {sym}")
                    continue

                pnl = safe(p.get("unrealizedPnl"))

                # TP1
                if not st["tp1"] and pnl >= TP1_USDT:
                    exchange.create_market_order(sym,"sell" if direction=="long" else "buy",qty*0.4,params={"reduceOnly":True})
                    st["tp1"]=True
                    st["sl"]=entry
                    bot.send_message(CHAT_ID,f"💰 TP1 {sym} {round(pnl,2)}")

                # STEP
                if st["tp1"]:
                    risk = st["initial_risk"]
                    r = abs(price-entry)/risk if risk>0 else 0

                    for lvl in STEP_LEVELS:
                        if r>=lvl and st["step"]<lvl:
                            st["step"]=lvl
                            st["sl"]=entry+(lvl-1)*risk if direction=="long" else entry-(lvl-1)*risk
                            bot.send_message(CHAT_ID,f"📈 STEP {lvl} {sym}")

                # STOP
                if (direction=="long" and price<=st["sl"]) or (direction=="short" and price>=st["sl"]):
                    exchange.create_market_order(sym,"sell" if direction=="long" else "buy",qty,params={"reduceOnly":True})
                    trade_state.pop(sym,None)
                    active_trades.discard(sym)
                    bot.send_message(CHAT_ID,f"❌ STOP {sym}")

            time.sleep(5)

        except Exception as e:
            print("MANAGE ERROR:",e)
            time.sleep(5)

# ===== START =====
exchange.fetch_balance()
bot.remove_webhook()
time.sleep(1)

load_open_positions()

threading.Thread(target=trade_engine,args=("SAFE",),daemon=True).start()
threading.Thread(target=trade_engine,args=("AGGRESSIVE",),daemon=True).start()
threading.Thread(target=manage,daemon=True).start()

bot.send_message(CHAT_ID,"🔥 BOT AKTİF (FINAL STABLE)")
bot.infinity_polling()
