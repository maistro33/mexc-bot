import os
import time
import ccxt
import telebot
import threading
import random

LEV = 10
MARGIN = 3

MAX_POSITIONS = 4

TP1_PCT = 0.01
STEP_PCT = 0.008
TP1_RATIO = 0.50

MIN_VOLUME = 2000000
MAX_SPREAD = 0.003
SCAN_DELAY = 6

SL_PCT = 0.02

bot = telebot.TeleBot(os.getenv("TELE_TOKEN"))
CHAT_ID = os.getenv("MY_CHAT_ID")

exchange = ccxt.bitget({
    "apiKey": os.getenv("BITGET_API"),
    "secret": os.getenv("BITGET_SEC"),
    "password": os.getenv("BITGET_PASS"),
    "options": {"defaultType": "swap"},
    "enableRateLimit": True
})

markets = exchange.load_markets()
SYMBOLS = [s for s in markets if markets[s]["swap"] and "USDT" in s][:200]

trade_state = {}
cooldown = {}
COOLDOWN_TIME = 1800

# ================= SAFE =================
def safe_api_call(func,*args,**kwargs):
    for _ in range(3):
        try:
            return func(*args,**kwargs)
        except Exception as e:
            print("API ERROR:",e)
            time.sleep(2)
    return None

def safe(x):
    try:
        return float(x)
    except:
        return 0

# ================= CACHE =================
cache = {}

def cached_ohlcv(sym, tf, limit):
    key = f"{sym}-{tf}-{limit}"

    if key in cache:
        if time.time() - cache[key]["time"] < 5:
            return cache[key]["data"]

    data = safe_api_call(exchange.fetch_ohlcv, sym, tf, limit=limit)

    if data:
        cache[key] = {"data": data, "time": time.time()}

    return data

# ================= POSITION =================
def get_qty(sym):
    try:
        pos = safe_api_call(exchange.fetch_positions,[sym])
        if not pos:
            return 0
        return safe(pos[0]["contracts"])
    except:
        return 0

def position_direction_count(direction):
    try:
        positions = safe_api_call(exchange.fetch_positions)
        count = 0
        for p in positions:
            if safe(p.get("contracts")) > 0:
                if p["side"] == direction:
                    count += 1
        return count
    except:
        return 0

def active_positions():
    try:
        positions = safe_api_call(exchange.fetch_positions)
        return sum(1 for p in positions if safe(p.get("contracts")) > 0)
    except:
        return 0

def sync_positions():
    try:
        positions = safe_api_call(exchange.fetch_positions)
        if not positions:
            return

        for p in positions:
            qty = safe(p.get("contracts"))
            if qty <= 0:
                continue

            sym = p["symbol"]
            entry = safe(p.get("entryPrice"))
            side = "long" if p.get("side") == "long" else "short"

            trade_state[sym] = {
                "entry": entry,
                "direction": side,
                "tp1": False,
                "step": 0,
                "start": time.time(),
                "trail_stop": entry
            }

    except Exception as e:
        print("SYNC ERROR:", e)

# ================= MARKET =================
def btc_trend():
    try:
        candles = cached_ohlcv("BTC/USDT:USDT","1h",50)
        if not candles: return "neutral"
        closes=[c[4] for c in candles]
        ema=sum(closes[-20:])/20
        return "bull" if closes[-1] > ema else "bear"
    except:
        return "neutral"

def volatility_filter(sym):
    candles = cached_ohlcv(sym,"5m",10)
    if not candles: return False
    ranges=[c[2]-c[3] for c in candles]
    avg=sum(ranges[:-1])/9
    return ranges[-1] > avg*1.2

def micro_momentum(sym):
    candles = cached_ohlcv(sym,"1m",3)
    if not candles: return False
    change=(candles[-1][4]-candles[-2][4])/candles[-2][4]
    return abs(change) > 0.002

def volume_spike(sym):
    candles=cached_ohlcv(sym,"5m",6)
    if not candles: return False
    vols=[c[5] for c in candles]
    avg=sum(vols[:-1])/5
    return vols[-1] > avg*1.3

def liquidity_sweep(sym):
    candles=cached_ohlcv(sym,"15m",10)
    if not candles: return False
    highs=[c[2] for c in candles]
    lows=[c[3] for c in candles]
    return highs[-1] > max(highs[:-1]) or lows[-1] < min(lows[:-1])

def fake_breakout(sym):
    candles=cached_ohlcv(sym,"5m",5)
    if not candles: return False
    highs=[c[2] for c in candles]
    lows=[c[3] for c in candles]
    last=candles[-1]
    return (last[4] < highs[-2] and last[2] > highs[-2]) or (last[4] > lows[-2] and last[3] < lows[-2])

def early_breakout(sym):
    candles = cached_ohlcv(sym,"5m",3)
    if not candles: return False
    last = candles[-1]
    prev = candles[-2]
    return last[4] > prev[2]*0.998 and last[5] > prev[5]*1.2

def trend_start(sym):
    candles = cached_ohlcv(sym,"5m",5)
    if not candles: return False
    move = (candles[-1][4] - candles[-5][4]) / candles[-5][4]
    return abs(move) < 0.015

# ================= SMART MONEY =================
def whale_signal(sym):
    trades = safe_api_call(exchange.fetch_trades, sym, limit=50)
    if not trades: return False
    vols=[t["amount"] for t in trades]
    avg=sum(vols)/len(vols)
    return len([v for v in vols if v>avg*3])>=2

def open_interest_spike(sym):
    try:
        oi = safe_api_call(exchange.fetch_open_interest, sym)
        return oi and oi.get("openInterest",0)>0
    except:
        return False

def funding_squeeze(sym):
    try:
        fr = safe_api_call(exchange.fetch_funding_rate, sym)
        if not fr: return None
        if fr["fundingRate"] > 0.001:
            return "short"
        if fr["fundingRate"] < -0.001:
            return "long"
        return None
    except:
        return None

# ================= ORDERBOOK =================
def orderbook_pressure(sym):
    ob=safe_api_call(exchange.fetch_order_book,sym,20)
    if not ob: return None
    bid=sum([b[1] for b in ob["bids"]])
    ask=sum([a[1] for a in ob["asks"]])
    if bid > ask*1.5: return "long"
    if ask > bid*1.5: return "short"
    return None

# ================= AI =================
def signal_score(sym):
    score = 0
    if volatility_filter(sym): score+=1
    if micro_momentum(sym): score+=1
    if volume_spike(sym): score+=1
    if liquidity_sweep(sym): score+=1
    if not fake_breakout(sym): score+=1
    if whale_signal(sym): score+=2
    if open_interest_spike(sym): score+=2
    if early_breakout(sym): score+=1
    return score

# ================= TRADE =================
def open_trade(sym,direction,label):
    try:
        if get_qty(sym)>0:
            return

        ticker=safe_api_call(exchange.fetch_ticker,sym)
        if not ticker: return

        if ticker["quoteVolume"]<MIN_VOLUME:
            return

        spread=(ticker["ask"]-ticker["bid"])/ticker["last"]
        if spread>MAX_SPREAD:
            return

        price=ticker["last"]
        qty=(MARGIN*LEV)/price
        qty=float(exchange.amount_to_precision(sym,qty))

        exchange.set_leverage(LEV,sym)
        side="buy" if direction=="long" else "sell"
        exchange.create_market_order(sym,side,qty)

        trade_state[sym]={
            "entry":price,
            "direction":direction,
            "tp1":False,
            "step":0,
            "start":time.time(),
            "trail_stop":price
        }

        cooldown[sym]=time.time()
        bot.send_message(CHAT_ID,f"🚀 {label.upper()} {sym} {direction}")

    except Exception as e:
        print("TRADE ERROR:", e)

# ================= MANAGE =================
def manage():
    while True:
        try:
            pos=safe_api_call(exchange.fetch_positions)
            if not pos:
                time.sleep(4)
                continue

            for p in pos:
                qty=safe(p.get("contracts"))
                if qty<=0: continue

                sym=p["symbol"]
                if sym not in trade_state: continue

                state=trade_state[sym]
                ticker=safe_api_call(exchange.fetch_ticker,sym)
                if not ticker: continue
                price=ticker["last"]

                entry=state["entry"]
                direction=state["direction"]
                side="sell" if direction=="long" else "buy"

                if (direction=="long" and price<=entry*(1-SL_PCT)) or \
                   (direction=="short" and price>=entry*(1+SL_PCT)):

                    exchange.create_market_order(sym,side,get_qty(sym),params={"reduceOnly":True})
                    trade_state.pop(sym)
                    bot.send_message(CHAT_ID,f"🛑 HARD SL {sym}")
                    continue

                if not state["tp1"]:
                    if (direction=="long" and price>=entry*(1+TP1_PCT)) or \
                       (direction=="short" and price<=entry*(1-TP1_PCT)):

                        exchange.create_market_order(sym,side,get_qty(sym)*TP1_RATIO,params={"reduceOnly":True})
                        state["tp1"]=True
                        state["step"]=1
                        state["trail_stop"]=entry
                        bot.send_message(CHAT_ID,f"💰 TP1 {sym}")

                else:
                    step_price = entry*(1+STEP_PCT*state["step"]) if direction=="long" else entry*(1-STEP_PCT*state["step"])

                    if (direction=="long" and price>=step_price) or (direction=="short" and price<=step_price):
                        state["step"]+=1
                        state["trail_stop"]=entry*(1+STEP_PCT*(state["step"]-1)) if direction=="long" else entry*(1-STEP_PCT*(state["step"]-1))

                    if (direction=="long" and price<=state["trail_stop"]) or \
                       (direction=="short" and price>=state["trail_stop"]):

                        exchange.create_market_order(sym,side,get_qty(sym),params={"reduceOnly":True})
                        trade_state.pop(sym)
                        bot.send_message(CHAT_ID,f"🏁 TRAIL EXIT {sym}")

            time.sleep(4)

        except:
            time.sleep(6)

# ================= SCANNER =================
def scanner():
    while True:
        try:
            if active_positions() >= MAX_POSITIONS:
                time.sleep(SCAN_DELAY)
                continue

            random.shuffle(SYMBOLS)

            for sym in SYMBOLS:

                if sym in cooldown and time.time()-cooldown[sym] < COOLDOWN_TIME:
                    continue

                if get_qty(sym)>0:
                    continue

                fs = funding_squeeze(sym)
                if fs:
                    open_trade(sym, fs, "funding")
                    break

                if whale_signal(sym):
                    pressure=orderbook_pressure(sym)
                    if pressure:
                        open_trade(sym,pressure,"whale")
                        break

                if not trend_start(sym):
                    continue

                score = signal_score(sym)
                if score < 5:
                    continue

                pressure=orderbook_pressure(sym)

                if pressure == "long" and position_direction_count("long") >= 2:
                    continue

                if pressure == "short" and position_direction_count("short") >= 2:
                    continue

                if pressure:
                    open_trade(sym,pressure,"ai")
                    break

            time.sleep(SCAN_DELAY)

        except:
            time.sleep(15)

print("BOT STARTING")

sync_positions()

threading.Thread(target=manage,daemon=True).start()
threading.Thread(target=scanner,daemon=True).start()

bot.send_message(CHAT_ID,"🤖 FULL PRO BOT AKTİF")

bot.infinity_polling()
