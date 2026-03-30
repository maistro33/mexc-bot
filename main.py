import os
import time
import ccxt
import telebot
import threading

SYMBOL = "INJ/USDT:USDT"

LEV = 5
QTY = 0.5

GRID_STEP = 0.003
LEVELS = 3

SCALP_PCT = 0.003
SHIFT_PCT = 0.008

FOLLOW_DIST = 0.0005
FOLLOW_UPDATE = 0.0007

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

# ===== PRICE =====
def get_price():
    return exchange.fetch_ticker(SYMBOL)["last"]

# ===== CLEAR =====
def cancel_all():
    try:
        orders = exchange.fetch_open_orders(SYMBOL)
        for o in orders:
            exchange.cancel_order(o["id"], SYMBOL)
    except:
        pass

# ===== GRID =====
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

    bot.send_message(CHAT_ID, "🚀 INJ BOT AKTİF (FINAL)")

# ===== FOLLOW (FİYATI TAKİP) =====
def update_follow(price):
    global follow_orders, last_follow_price

    if last_follow_price:
        change = abs(price - last_follow_price) / last_follow_price
        if change < FOLLOW_UPDATE:
            return

    last_follow_price = price

    # eski follow emirlerini sil
    for oid in list(follow_orders.keys()):
        try:
            exchange.cancel_order(oid, SYMBOL)
        except:
            pass
        follow_orders.pop(oid, None)

    # yeni emirler (fiyatın yakınında)
    buy = exchange.create_limit_order(SYMBOL, "buy", QTY, price * (1 - FOLLOW_DIST))
    sell = exchange.create_limit_order(SYMBOL, "sell", QTY, price * (1 + FOLLOW_DIST))

    follow_orders[buy["id"]] = ("buy", price)
    follow_orders[sell["id"]] = ("sell", price)

# ===== SCALP =====
def scalp_trade(price):
    try:
        exchange.create_market_order(SYMBOL, "buy", QTY)
        time.sleep(0.4)
        exchange.create_limit_order(SYMBOL, "sell", QTY, price * (1 + SCALP_PCT))
    except Exception as e:
        print("SCALP ERROR:", e)

# ===== MONITOR =====
def monitor():
    global last_price, base_price

    while True:
        try:
            price = get_price()

            # GRID RESET (trend yakalama)
            if abs(price - base_price) / base_price > SHIFT_PCT:
                bot.send_message(CHAT_ID, "♻️ RESET (TREND)")
                place_grid()
                time.sleep(1)
                continue

            # FOLLOW (fiyatı kovala)
            update_follow(price)

            # SCALP (filtreli)
            if last_price:
                change = abs(price - last_price) / last_price

                if change > SCALP_PCT * 1.5:
                    scalp_trade(price)

            last_price = price

            time.sleep(1)

        except Exception as e:
            print("MONITOR ERROR:", e)
            time.sleep(3)

# ===== START =====
def start():
    exchange.fetch_balance()
    bot.send_message(CHAT_ID, "🤖 BOT BAŞLADI (FINAL)")
    place_grid()

threading.Thread(target=start).start()
threading.Thread(target=monitor).start()
