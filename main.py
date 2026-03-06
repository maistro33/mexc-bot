import os
import time
import ccxt
import telebot
import threading
import websocket
import json
from datetime import datetime

# ================= SETTINGS =================

LEV = 10
MARGIN = 4

MIN_VOLUME = 5_000_000
MAX_SPREAD = 0.003

WHALE_THRESHOLD = 150000
WHALE_DELAY = 1.2

last_whale_time = 0
whale_positions = {}

# ================= TELEGRAM =================

bot = telebot.TeleBot(os.getenv("TELE_TOKEN"))
CHAT_ID = os.getenv("MY_CHAT_ID")

# ================= EXCHANGE =================

exchange = ccxt.bitget({
"apiKey": os.getenv("BITGET_API"),
"secret": os.getenv("BITGET_SEC"),
"password": "Berfin33",
"options": {"defaultType": "swap"},
"enableRateLimit": True
})

# ================= HELPERS =================

def safe(x):
    try:
        return float(x)
    except:
        return 0


def get_all_usdt_pairs():

    try:

        markets = exchange.load_markets()

        pairs = []

        for m in markets:

            if "/USDT" in m and ":USDT" in m:

                coin = m.split("/")[0]

                pairs.append(coin + "USDT")

        return pairs[:50]

    except:

        return ["BTCUSDT","ETHUSDT","SOLUSDT"]


def orderbook_imbalance(sym):

    try:

        ob = exchange.fetch_order_book(sym, limit=20)

        bids = ob["bids"]
        asks = ob["asks"]

        bid_vol = sum([b[1] for b in bids])
        ask_vol = sum([a[1] for a in asks])

        if bid_vol > ask_vol * 1.8:
            return "long"

        if ask_vol > bid_vol * 1.8:
            return "short"

        return None

    except:
        return None


def volume_spike(sym):

    try:

        m5 = exchange.fetch_ohlcv(sym,"5m",limit=6)

        vols=[c[5] for c in m5]

        if vols[-1] > (sum(vols[:-1])/5)*2:
            return True

        return False

    except:
        return False


def liquidation_spike(sym):

    try:

        m1 = exchange.fetch_ohlcv(sym,"1m",limit=5)

        bodies=[abs(c[4]-c[1]) for c in m1]

        avg=sum(bodies[:-1])/4

        last=bodies[-1]

        if last > avg*3:
            return True

        return False

    except:
        return False


def get_qty(sym):

    try:

        pos = exchange.fetch_positions([sym])

        if not pos:
            return 0

        return safe(pos[0]["contracts"])

    except:

        return 0


# ================= ENTRY =================

def open_trade(sym,direction):

    try:

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

        bot.send_message(CHAT_ID,f"🚀 {sym} {direction}")

    except Exception as e:

        print("ENTRY ERROR",e)


# ================= WHALE ACTION =================

def whale_action(side,sym):

    global whale_positions

    try:

        direction = "long" if side=="buy" else "short"

        if sym not in whale_positions:

            if orderbook_imbalance(sym) != direction:
                return

            if not volume_spike(sym):
                return

            if not liquidation_spike(sym):
                return

            time.sleep(WHALE_DELAY)

            open_trade(sym,direction)

            whale_positions[sym] = direction

            bot.send_message(CHAT_ID,f"🐋 Whale OPEN {sym} {direction}")

        else:

            current = whale_positions[sym]

            if current != direction:

                qty=get_qty(sym)

                if qty>0:

                    close_side="sell" if current=="long" else "buy"

                    exchange.create_market_order(
                        sym,
                        close_side,
                        qty,
                        params={"reduceOnly":True}
                    )

                    bot.send_message(CHAT_ID,f"🐋 Whale EXIT {sym}")

                whale_positions.pop(sym)

    except Exception as e:

        print("WHALE ERROR",e)


# ================= WHALE STREAM =================

def whale_stream():

    global last_whale_time

    url="wss://ws.bitget.com/v2/ws/public"

    def on_message(ws,message):

        global last_whale_time

        try:

            data=json.loads(message)

            if "data" not in data:
                return

            for trade in data["data"]:

                symbol = trade["instId"]

                price=float(trade["price"])
                size=float(trade["size"])

                value=price*size

                if value > WHALE_THRESHOLD:

                    if time.time() - last_whale_time < 5:
                        return

                    last_whale_time = time.time()

                    side=trade["side"]

                    coin = symbol.replace("USDT","")

                    sym = coin + "/USDT:USDT"

                    whale_action(side,sym)

        except:
            pass


    def on_open(ws):

        pairs = get_all_usdt_pairs()

        args = []

        for p in pairs:

            args.append({
                "instType":"SPOT",
                "channel":"trade",
                "instId":p
            })

        sub={
            "op":"subscribe",
            "args":args
        }

        ws.send(json.dumps(sub))


    while True:

        try:

            ws=websocket.WebSocketApp(
                url,
                on_message=on_message,
                on_open=on_open
            )

            ws.run_forever()

        except:

            time.sleep(5)


# ================= START =================

print("BOT STARTING")

threading.Thread(target=whale_stream,daemon=True).start()

bot.send_message(CHAT_ID,"🤖 BOT AKTİF")

bot.infinity_polling()
