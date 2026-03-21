import os
import time
import ccxt
import telebot
import threading
import requests
import random

LEV = 10
MARGIN = 3

MAX_POSITIONS = 4
BALINA_LIMIT = 1

TP1_PCT = 0.007
STEP_PCT = 0.006
TP1_RATIO = 0.50

MIN_VOLUME = 2000000
MAX_SPREAD = 0.003
SCAN_DELAY = 6

TIMEOUT = 21600
SL_PCT = 0.02

bot = telebot.TeleBot(os.getenv("TELE_TOKEN"))
CHAT_ID = os.getenv("MY_CHAT_ID")

exchange = ccxt.bitget({
    "apiKey": os.getenv("BITGET_API"),
    "secret": os.getenv("BITGET_SEC"),
    "password": "Berfin33",
    "options": {"defaultType": "swap"},
    "enableRateLimit": True
})

markets = exchange.load_markets()
SYMBOLS = [s for s in markets if markets[s]["swap"] and "USDT" in s][:200]

trade_state = {}
cooldown = {}
COOLDOWN_TIME = 1800

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

def get_qty(sym):
    try:
        pos = safe_api_call(exchange.fetch_positions,[sym])
        if not pos:
            return 0
        return safe(pos[0]["contracts"])
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
    except:
        pass

def btc_trend():
    try:
        candles = safe_api_call(exchange.fetch_ohlcv,"BTC/USDT:USDT","1h",limit=50)
        if not candles:
            return "neutral"
        closes=[c[4] for c in candles]
        ema=sum(closes[-20:])/20
        return "bull" if closes[-1] > ema else "bear"
    except:
        return "neutral"

def btc_short_breakdown(sym):
    candles = safe_api_call(exchange.fetch_ohlcv, sym,"5m",limit=6)
    if not candles:
        return False
    lows=[c[3] for c in candles[:-1]]
    return candles[-1][4] < min(lows)

def volatility_filter(sym):
    candles = safe_api_call(exchange.fetch_ohlcv, sym,"5m",limit=10)
    if not candles:
        return False
    ranges=[c[2]-c[3] for c in candles]
    avg=sum(ranges[:-1])/9
    return ranges[-1] > avg*1.2

def micro_momentum(sym):
    candles = safe_api_call(exchange.fetch_ohlcv, sym,"1m",limit=3)
    if not candles:
        return False
    change=(candles[-1][4]-candles[-2][4])/candles[-2][4]
    return abs(change) > 0.002

def funding_filter(sym):
    try:
        fr = safe_api_call(exchange.fetch_funding_rate, sym)
        if not fr:
            return True
        return abs(fr["fundingRate"]) > 0.0005
    except:
        return True

def volume_spike(sym):
    candles = safe_api_call(exchange.fetch_ohlcv, sym,"5m",limit=6)
    if not candles:
        return False
    vols=[c[5] for c in candles]
    avg=sum(vols[:-1])/5
    return vols[-1] > avg*1.3

def orderbook_pressure(sym):
    ob = safe_api_call(exchange.fetch_order_book, sym,limit=20)
    if not ob:
        return None
    bid=sum([b[1] for b in ob["bids"]])
    ask=sum([a[1] for a in ob["asks"]])
    if bid > ask*1.5:
        return "long"
    if ask > bid*1.5:
        return "short"
    return None

def fake_breakout(sym):
    candles = safe_api_call(exchange.fetch_ohlcv, sym,"5m",limit=5)
    if not candles:
        return False
    highs=[c[2] for c in candles]
    lows=[c[3] for c in candles]
    last=candles[-1]
    return (last[4] < highs[-2] and last[2] > highs[-2]) or (last[4] > lows[-2] and last[3] < lows[-2])

def liquidity_sweep(sym):
    candles = safe_api_call(exchange.fetch_ohlcv, sym,"15m",limit=10)
    if not candles:
        return False
    highs=[c[2] for c in candles]
    lows=[c[3] for c in candles]
    return highs[-1] > max(highs[:-1]) or lows[-1] < min(lows[:-1])

def short_squeeze(sym):
    candles = safe_api_call(exchange.fetch_ohlcv, sym,"5m",limit=3)
    if not candles:
        return False
    change=(candles[-1][4]-candles[-2][4])/candles[-2][4]
    return change > 0.02 and volume_spike(sym)

def long_squeeze(sym):
    candles = safe_api_call(exchange.fetch_ohlcv, sym,"5m",limit=3)
    if not candles:
        return False
    change=(candles[-2][4]-candles[-1][4])/candles[-2][4]
    return change > 0.02 and volume_spike(sym)

def liquidation_hunt(sym):
    candles = safe_api_call(exchange.fetch_ohlcv, sym,"1m",limit=6)
    if not candles:
        return False
    ranges=[c[2]-c[3] for c in candles]
    avg=sum(ranges[:-1])/5
    return ranges[-1] > avg*2.5

def early_pump(sym):
    candles = safe_api_call(exchange.fetch_ohlcv, sym,"5m",limit=4)
    if not candles:
        return False
    high=max([c[2] for c in candles[:-1]])
    return candles[-1][4] > high and volume_spike(sym)

def whale_signal(sym):
    return False

def early_breakout(sym):
    candles = safe_api_call(exchange.fetch_ohlcv, sym,"5m",limit=3)
    if not candles:
        return False
    last = candles[-1]
    prev = candles[-2]
    return last[4] > prev[2]*0.998 and last[5] > prev[5]*1.2

def market_filter(sym):
    candles = safe_api_call(exchange.fetch_ohlcv, sym,"5m",limit=10)
    if not candles:
        return False
    closes = [c[4] for c in candles]
    move = abs(closes[-1] - closes[0]) / closes[0]
    return move > 0.01

def overextended_filter(sym):
    candles = safe_api_call(exchange.fetch_ohlcv, sym,"5m",limit=3)
    if not candles:
        return False
    move = (candles[-1][4] - candles[-3][4]) / candles[-3][4]
    return abs(move) < 0.025

def late_entry_filter(sym):
    candles = safe_api_call(exchange.fetch_ohlcv, sym,"1m",limit=3)
    if not candles:
        return False
    c1 = (candles[-1][4] - candles[-2][4]) / candles[-2][4]
    c2 = (candles[-2][4] - candles[-3][4]) / candles[-3][4]
    return abs(c1) < 0.006 and abs(c2) < 0.006

def smart_entry_filter(sym):
    candles = safe_api_call(exchange.fetch_ohlcv, sym,"5m",limit=4)
    if not candles:
        return False
    last = candles[-1]
    prev = candles[-2]
    breakout_up = last[4] > prev[2]
    breakout_down = last[4] < prev[3]
    fake_up = last[2] > prev[2] and last[4] < prev[2]
    fake_down = last[3] < prev[3] and last[4] > prev[3]
    if fake_up or fake_down:
        return False
    body = abs(last[4] - last[1])
    rng = last[2] - last[3]
    if rng == 0:
        return False
    if body / rng < 0.3:
        return False
    return breakout_up or breakout_down

def open_trade(sym,direction,label):
    try:
        if get_qty(sym) > 0:
            return

        ticker = safe_api_call(exchange.fetch_ticker,sym)
        if not ticker:
            return

        if ticker["quoteVolume"] < MIN_VOLUME:
            return

        spread=(ticker["ask"]-ticker["bid"])/ticker["last"]
        if spread > MAX_SPREAD:
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

def manage():
    while True:
        try:
            pos = safe_api_call(exchange.fetch_positions)
            if not pos:
                time.sleep(4)
                continue

            for p in pos:
                qty=safe(p.get("contracts"))
                if qty<=0:
                    continue

                sym=p["symbol"]
                if sym not in trade_state:
                    continue

                state=trade_state[sym]
                ticker = safe_api_call(exchange.fetch_ticker,sym)
                if not ticker:
                    continue

                price=ticker["last"]
                entry=state["entry"]
                direction=state["direction"]
                side="sell" if direction=="long" else "buy"

                if (direction=="long" and price <= entry*(1-SL_PCT)) or \
                   (direction=="short" and price >= entry*(1+SL_PCT)):

                    exchange.create_market_order(sym,side,get_qty(sym),params={"reduceOnly":True})
                    trade_state.pop(sym)
                    bot.send_message(CHAT_ID,f"🛑 HARD SL {sym}")
                    continue

            time.sleep(4)

        except:
            time.sleep(6)

def scanner():
    while True:
        try:
            random.shuffle(SYMBOLS)
            btc=btc_trend()

            positions = safe_api_call(exchange.fetch_positions)
            if not positions:
                time.sleep(5)
                continue

            active=sum(1 for p in positions if safe(p.get("contracts"))>0)

            if active >= MAX_POSITIONS:
                time.sleep(SCAN_DELAY)
                continue

            for sym in SYMBOLS:

                if sym in cooldown and time.time()-cooldown[sym] < COOLDOWN_TIME:
                    continue

                if get_qty(sym)>0:
                    continue

                if btc=="bear" and btc_short_breakdown(sym):
                    pressure=orderbook_pressure(sym)
                    if pressure=="short":
                        open_trade(sym,"short","btc_short")
                        break

                if early_breakout(sym):
                    pressure = orderbook_pressure(sym)
                    if pressure:
                        open_trade(sym,pressure,"early")
                        break

                if not volatility_filter(sym): continue
                if not micro_momentum(sym): continue
                if not market_filter(sym): continue
                if not overextended_filter(sym): continue
                if not late_entry_filter(sym): continue
                if not smart_entry_filter(sym): continue
                if not funding_filter(sym): continue

                if short_squeeze(sym):
                    open_trade(sym,"long","squeeze")
                    break

                if long_squeeze(sym):
                    open_trade(sym,"short","squeeze")
                    break

                if liquidation_hunt(sym):
                    pressure=orderbook_pressure(sym)
                    if pressure:
                        open_trade(sym,pressure,"liquidation")
                        break

                if early_pump(sym):
                    open_trade(sym,"long","pump")
                    break

                if not volume_spike(sym): continue
                if not liquidity_sweep(sym): continue
                if not fake_breakout(sym): continue

                pressure=orderbook_pressure(sym)

                if not pressure:
                    continue
                if pressure=="long" and btc=="bear":
                    continue
                if pressure=="short" and btc=="bull":
                    continue

                open_trade(sym,pressure,"normal")
                break

            time.sleep(SCAN_DELAY)

        except:
            time.sleep(15)

print("BOT STARTING")

sync_positions()

threading.Thread(target=manage,daemon=True).start()
threading.Thread(target=scanner,daemon=True).start()

bot.send_message(CHAT_ID,"🤖 BOT AKTİF")

bot.infinity_polling()
