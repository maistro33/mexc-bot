import os
import time
import ccxt
import telebot
import threading

SYMBOL = "INJ/USDT:USDT"

LEV = 5
QTY = 2

GRID_STEP = 0.002
LEVELS = 4

SCALP_PCT = 0.0012
SHIFT_PCT = 0.008

FOLLOW_DIST = 0.0004
FOLLOW_UPDATE = 0.0005

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

grid = {}
base_price = None
last_price = None
follow_orders = {}
last_follow_price = None

def get_price():
    return exchange.fetch_ticker(SYMBOL)["last"]

def cancel_all():
    try:
        orders = exchange.fetch_open_orders(SYMBOL)
        for o in orders:
            exchange.cancel_order(o["id"], SYMBOL)
    except:
        pass

def place_grid():
    global base_price
    cancel_all()
    base_price = get_price()
    exchange.set_leverage(LEV, SYMBOL)

    for i in range(1, LEVELS + 1):
        buy_price = base_price * (1 - GRID_STEP * i)
        sell_price = base_price * (1 + GRID_STEP * i)

        buy = exchange.create_limit_order(SYMBOL, "buy", QTY, buy_price)
        sell = exchange.create_limit_order(SYMBOL, "sell", QTY, sell_price)

        grid[buy["id"]] = ("buy", buy_price)
        grid[sell["id"]] = ("sell", sell_price)

    bot.send_message(CHAT_ID, "🚀 INJ BOT AKTİF")

def update_follow(price):
    global follow_orders, last_follow_price

    if last_follow_price:
        change = abs(price - last_follow_price) / last_follow_price
        if change < FOLLOW_UPDATE:
            return

    last_follow_price = price

    for oid in list(follow_orders.keys()):
        try:
            exchange.cancel_order(oid, SYMBOL)
        except:
            pass
        follow_orders.pop(oid, None)

    buy = exchange.create_limit_order(SYMBOL, "buy", QTY, price * (1 - FOLLOW_DIST))
    sell = exchange.create_limit_order(SYMBOL, "sell", QTY, price * (1 + FOLLOW_DIST))

    follow_orders[buy["id"]] = ("buy", price)
    follow_orders[sell["id"]] = ("sell", price)

def scalp_trade(price):
    try:
        exchange.create_market_order(SYMBOL, "buy", QTY)
        time.sleep(0.3)
        exchange.create_limit_order(SYMBOL, "sell", QTY, price * (1 + SCALP_PCT))
    except:
        pass

def monitor():
    global last_price, base_price

    while True:
        try:
            price = get_price()

            if abs(price - base_price) / base_price > SHIFT_PCT:
                place_grid()
                continue

            update_follow(price)

            if last_price:
                if abs(price - last_price) / last_price > SCALP_PCT:
                    scalp_trade(price)

            last_price = price
            time.sleep(1)

        except:
            time.sleep(2)

def start():
    exchange.fetch_balance()
    place_grid()

threading.Thread(target=start).start()
threading.Thread(target=monitor).start()
