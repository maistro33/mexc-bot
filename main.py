import os
import time
import ccxt
import telebot
import threading
import requests

LEV = 10
MARGIN = 3

MAX_POSITIONS = 3
BALINA_LIMIT = 1
MAX_WHALE_POSITION = 1

TP1_PCT = 0.006
TP2_PCT = 0.012
TRAIL_GAP = 0.008

TP1_RATIO = 0.50
TP2_RATIO = 0.25

MIN_VOLUME = 5000000
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

last_whale_coin=None
last_whale_time=0

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

        coin=data[0]["symbol"]

        return coin

    except:
        return None

def whale_engine():

    global last_whale_coin,last_whale_time

    while True:

        try:

            coin=coinglass_whale()

            if not coin:
                time.sleep(30)
                continue

            sym=f"{coin}/USDT:USDT"

            if sym not in markets:
                time.sleep(30)
                continue

            if sym==last_whale_coin and time.time()-last_whale_time<900:
                time.sleep(30)
                continue

            if get_qty(sym)>0:
                time.sleep(30)
                continue

            ticker=exchange.fetch_ticker(sym)

            price=ticker["last"]

            qty=(MARGIN*LEV)/price
            qty=float(exchange.amount_to_precision(sym,qty))

            exchange.set_leverage(LEV,sym)

            exchange.create_market_order(sym,"buy",qty)

            trade_state[sym]={
            "entry":price,
            "direction":"long",
            "tp1":False,
            "tp2":False,
            "be":False,
            "extreme":price,
            "start":time.time()
            }

            last_whale_coin=sym
            last_whale_time=time.time()

            bot.send_message(CHAT_ID,f"🐋 WHALE DETECTED {sym} long")

            time.sleep(60)

        except:

            time.sleep(60)

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

def volume_spike(sym):
    try:
        candles=exchange.fetch_ohlcv(sym,"5m",limit=6)
        vols=[c[5] for c in candles]
        avg=sum(vols[:-1])/5

        if vols[-1] > avg*1.5:
            return True

        return False
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
        "tp2":False,
        "be":False,
        "extreme":price,
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

                elapsed=time.time()-state["start"]

                if elapsed>14400:
                    exchange.create_market_order(sym,side,get_qty(sym),params={"reduceOnly":True})
                    trade_state.pop(sym)
                    bot.send_message(CHAT_ID,f"⏰ TIME EXIT {sym}")
                    continue

                if direction=="long" and price>state["extreme"]:
                    state["extreme"]=price

                if direction=="short" and price<state["extreme"]:
                    state["extreme"]=price

                if not state["tp1"]:

                    if (direction=="long" and price>=entry*(1+TP1_PCT)) or \
                       (direction=="short" and price<=entry*(1-TP1_PCT)):

                        exchange.create_market_order(sym,side,qty*TP1_RATIO,params={"reduceOnly":True})

                        state["tp1"]=True
                        state["be"]=True

                        bot.send_message(CHAT_ID,f"💰 TP1 {sym}")

                elif state["be"]:

                    if direction=="long" and price<=entry:

                        exchange.create_market_order(sym,side,get_qty(sym),params={"reduceOnly":True})
                        trade_state.pop(sym)
                        bot.send_message(CHAT_ID,f"⚖️ BREAKEVEN {sym}")
                        continue

                    if direction=="short" and price>=entry:

                        exchange.create_market_order(sym,side,get_qty(sym),params={"reduceOnly":True})
                        trade_state.pop(sym)
                        bot.send_message(CHAT_ID,f"⚖️ BREAKEVEN {sym}")
                        continue

                if not state["tp2"]:

                    if (direction=="long" and price>=entry*(1+TP2_PCT)) or \
                       (direction=="short" and price<=entry*(1-TP2_PCT)):

                        exchange.create_market_order(sym,side,qty*TP2_RATIO,params={"reduceOnly":True})
                        state["tp2"]=True
                        bot.send_message(CHAT_ID,f"💰 TP2 {sym}")

                elif state["tp2"]:

                    if direction=="long":

                        if price<=state["extreme"]*(1-TRAIL_GAP):

                            exchange.create_market_order(sym,side,get_qty(sym),params={"reduceOnly":True})
                            trade_state.pop(sym)
                            bot.send_message(CHAT_ID,f"🏁 TRAILING {sym}")

                    else:

                        if price>=state["extreme"]*(1+TRAIL_GAP):

                            exchange.create_market_order(sym,side,get_qty(sym),params={"reduceOnly":True})
                            trade_state.pop(sym)
                            bot.send_message(CHAT_ID,f"🏁 TRAILING {sym}")

            time.sleep(4)

        except:
            time.sleep(6)

print("BOT STARTING")

threading.Thread(target=manage,daemon=True).start()
threading.Thread(target=whale_engine,daemon=True).start()

bot.send_message(CHAT_ID,"🤖 BOT AKTİF")

bot.infinity_polling()
