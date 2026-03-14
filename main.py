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
whale_symbols = [s for s in markets if markets[s]["swap"] and "USDT" in s]

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


def open_trade_whale(sym,direction,label):

    try:

        if get_qty(sym) > 0:
            return

        ticker=exchange.fetch_ticker(sym)

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

                if direction=="long" and price>state["extreme"]:
                    state["extreme"]=price

                if direction=="short" and price<state["extreme"]:
                    state["extreme"]=price

            time.sleep(4)

        except:
            time.sleep(6)


def scanner():

    while True:

        try:

            for sym in SYMBOLS:

                if get_qty(sym)>0:
                    continue

                ticker=exchange.fetch_ticker(sym)

                if ticker["quoteVolume"] < MIN_VOLUME:
                    continue

                pressure=None

                ob=exchange.fetch_order_book(sym)

                bid=sum([b[1] for b in ob["bids"]])
                ask=sum([a[1] for a in ob["asks"]])

                if bid>ask*1.5:
                    pressure="long"

                if ask>bid*1.5:
                    pressure="short"

                if pressure:

                    open_trade(sym,pressure,"normal")
                    break

            time.sleep(SCAN_DELAY)

        except:
            time.sleep(15)


def whale_engine():

    last=None

    while True:

        try:

            url="https://open-api.coinglass.com/api/pro/v1/futures/openInterest/ohlc"

            headers={
                "accept":"application/json",
                "coinglassSecret":os.getenv("COINGLASS_API")
            }

            r=requests.get(url,headers=headers,timeout=10).json()

            data=r.get("data",[])

            if not data:
                time.sleep(20)
                continue

            for d in data[:5]:

                coin=d.get("symbol")

                sym=coin+"/USDT:USDT"

                if sym not in whale_symbols:
                    continue

                if get_qty(sym)>0:
                    continue

                ob=exchange.fetch_order_book(sym)

                bid=sum([b[1] for b in ob["bids"]])
                ask=sum([a[1] for a in ob["asks"]])

                direction=None

                if bid>ask*1.5:
                    direction="long"

                if ask>bid*1.5:
                    direction="short"

                if not direction:
                    continue

                if last==sym:
                    continue

                open_trade_whale(sym,direction,"whale-engine")

                last=sym

                break

            time.sleep(20)

        except:
            time.sleep(30)


print("BOT STARTING")

threading.Thread(target=manage,daemon=True).start()
threading.Thread(target=scanner,daemon=True).start()
threading.Thread(target=whale_engine,daemon=True).start()

bot.send_message(CHAT_ID,"🤖 BOT AKTİF")

bot.infinity_polling()
