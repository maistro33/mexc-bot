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

TP1_PCT = 0.006
STEP_PCT = 0.005
TP1_RATIO = 0.50

MIN_VOLUME = 2000000
MAX_SPREAD = 0.003
SCAN_DELAY = 6

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
SYMBOLS = [s for s in markets if markets[s]["swap"] and "USDT" in s][:120]

trade_state = {}

def safe(x):
    try:
        return float(x)
    except:
        return 0


def get_qty(sym):
    try:
        pos = exchange.fetch_positions([sym])
        if not pos:
            return 0
        return safe(pos[0]["contracts"])
    except:
        return 0


def sync_positions():
    try:
        positions = exchange.fetch_positions()

        for p in positions:
            qty = safe(p.get("contracts"))
            if qty <= 0:
                continue

            sym = p["symbol"]
            entry = safe(p["entryPrice"])
            side = "long" if p["side"] == "long" else "short"

            trade_state[sym] = {
                "entry": entry,
                "direction": side,
                "tp1": False,
                "step": 0,
                "start": time.time()
            }

    except:
        pass


def btc_trend():

    try:
        candles = exchange.fetch_ohlcv("BTC/USDT:USDT","1h",limit=50)
        closes=[c[4] for c in candles]
        ema=sum(closes[-20:])/20

        if closes[-1] > ema:
            return "bull"

        return "bear"

    except:
        return "neutral"


def volume_spike(sym):

    try:
        candles=exchange.fetch_ohlcv(sym,"5m",limit=6)
        vols=[c[5] for c in candles]
        avg=sum(vols[:-1])/5

        return vols[-1] > avg*1.5
    except:
        return False


def orderbook_pressure(sym):

    try:
        ob=exchange.fetch_order_book(sym,limit=20)

        bid=sum([b[1] for b in ob["bids"]])
        ask=sum([a[1] for a in ob["asks"]])

        if bid > ask*1.5:
            return "long"

        if ask > bid*1.5:
            return "short"

        return None

    except:
        return None


def fake_breakout(sym):

    try:
        candles=exchange.fetch_ohlcv(sym,"5m",limit=5)

        highs=[c[2] for c in candles]
        lows=[c[3] for c in candles]

        last=candles[-1]

        if last[4] < highs[-2] and last[2] > highs[-2]:
            return True

        if last[4] > lows[-2] and last[3] < lows[-2]:
            return True

        return False

    except:
        return False


def liquidity_sweep(sym):

    try:
        candles=exchange.fetch_ohlcv(sym,"15m",limit=10)

        highs=[c[2] for c in candles]
        lows=[c[3] for c in candles]

        return highs[-1] > max(highs[:-1]) or lows[-1] < min(lows[:-1])

    except:
        return False


def short_squeeze(sym):

    try:
        candles = exchange.fetch_ohlcv(sym,"5m",limit=3)
        change=(candles[-1][4]-candles[-2][4])/candles[-2][4]

        return change > 0.02 and volume_spike(sym)

    except:
        return False


def long_squeeze(sym):

    try:
        candles = exchange.fetch_ohlcv(sym,"5m",limit=3)
        change=(candles[-2][4]-candles[-1][4])/candles[-2][4]

        return change > 0.02 and volume_spike(sym)

    except:
        return False


def liquidation_hunt(sym):

    try:
        candles = exchange.fetch_ohlcv(sym,"1m",limit=6)
        ranges=[c[2]-c[3] for c in candles]
        avg=sum(ranges[:-1])/5

        return ranges[-1] > avg*2.5

    except:
        return False


def early_pump(sym):

    try:
        candles = exchange.fetch_ohlcv(sym,"5m",limit=4)
        high=max([c[2] for c in candles[:-1]])

        return candles[-1][4] > high and volume_spike(sym)

    except:
        return False


def coinglass_whale():

    try:

        url="https://open-api.coinglass.com/api/pro/v1/futures/openInterest/ohlc"

        headers={
        "accept":"application/json",
        "coinglassSecret":os.getenv("COINGLASS_API")
        }

        r=requests.get(url,headers=headers,timeout=10).json()

        data=r.get("data",[])

        if not data:
            return None

        return data[0]["symbol"]

    except:
        return None


def whale_signal(sym):

    try:

        coin=coinglass_whale()

        if not coin:
            return False

        return coin in sym

    except:
        return False


def open_trade(sym,direction,label):

    try:

        if get_qty(sym) > 0:
            return

        ticker=exchange.fetch_ticker(sym)

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
        "start":time.time()
        }

        bot.send_message(CHAT_ID,f"🚀 {label.upper()} {sym} {direction}")

    except:
        pass


def manage():

    while True:

        try:

            pos=exchange.fetch_positions()

            for p in pos:

                qty=safe(p.get("contracts"))

                if qty<=0:
                    continue

                sym=p["symbol"]

                if sym not in trade_state:
                    continue

                state=trade_state[sym]

                price=exchange.fetch_ticker(sym)["last"]

                entry=state["entry"]

                direction=state["direction"]

                side="sell" if direction=="long" else "buy"

                if not state["tp1"]:

                    if (direction=="long" and price>=entry*(1+TP1_PCT)) or \
                       (direction=="short" and price<=entry*(1-TP1_PCT)):

                        exchange.create_market_order(sym,side,get_qty(sym)*TP1_RATIO,params={"reduceOnly":True})

                        state["tp1"]=True
                        state["step"]=1

                        bot.send_message(CHAT_ID,f"💰 TP1 {sym}")

                else:

                    step_price = entry * (1 + STEP_PCT * state["step"]) if direction=="long" else entry * (1 - STEP_PCT * state["step"])

                    if (direction=="long" and price>=step_price) or (direction=="short" and price<=step_price):

                        state["step"] += 1

                        bot.send_message(CHAT_ID,f"🔒 STEP {state['step']} LOCKED {sym}")

                    stop_price = entry * (1 + STEP_PCT * (state["step"]-1)) if direction=="long" else entry * (1 - STEP_PCT * (state["step"]-1))

                    if (direction=="long" and price<=stop_price) or (direction=="short" and price>=stop_price):

                        exchange.create_market_order(sym,side,get_qty(sym),params={"reduceOnly":True})

                        trade_state.pop(sym)

                        bot.send_message(CHAT_ID,f"🏁 STEP TRAILING {sym}")

            time.sleep(4)

        except:

            time.sleep(6)


def scanner():

    while True:

        try:

            random.shuffle(SYMBOLS)

            btc=btc_trend()

            positions=exchange.fetch_positions()

            active=sum(1 for p in positions if safe(p.get("contracts"))>0)

            if active >= MAX_POSITIONS:
                time.sleep(SCAN_DELAY)
                continue

            for sym in SYMBOLS:

                if get_qty(sym)>0:
                    continue

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

                if whale_signal(sym):

                    pressure=orderbook_pressure(sym)

                    if pressure:
                        open_trade(sym,pressure,"whale")
                        break

                if not volume_spike(sym):
                    continue

                if not liquidity_sweep(sym):
                    continue

                if not fake_breakout(sym):
                    continue

                pressure=orderbook_pressure(sym)

                if not pressure:
                    continue

                if pressure=="long" and btc=="bear":
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
