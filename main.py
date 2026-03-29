import os
import time
import ccxt
import telebot
import threading

# ===== AYAR =====
SYMBOL = "BTC/USDT:USDT"
LEV = 3
QTY = 0.0003
GRID_STEP = 0.003  # %0.3
LEVELS = 4

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

grid = {}

# ===== PRICE =====
def get_price():
    return exchange.fetch_ticker(SYMBOL)["last"]

# ===== GRID KUR =====
def place_initial_grid():
    price = get_price()
    exchange.set_leverage(LEV, SYMBOL)

    for i in range(1, LEVELS + 1):

        buy_price = price * (1 - GRID_STEP * i)
        sell_price = price * (1 + GRID_STEP * i)

        buy = exchange.create_limit_order(SYMBOL, "buy", QTY, buy_price)
        sell = exchange.create_limit_order(SYMBOL, "sell", QTY, sell_price)

        grid[buy["id"]] = ("buy", buy_price)
        grid[sell["id"]] = ("sell", sell_price)

    bot.send_message(CHAT_ID, "📊 GRID KURULDU")

# ===== YENİ GRID =====
def place_opposite(side, price):

    try:
        if side == "buy":
            new_price = price * (1 + GRID_STEP)
            order = exchange.create_limit_order(SYMBOL, "sell", QTY, new_price)
            grid[order["id"]] = ("sell", new_price)
            bot.send_message(CHAT_ID, f"📈 SELL KOYULDU {round(new_price,2)}")

        else:
            new_price = price * (1 - GRID_STEP)
            order = exchange.create_limit_order(SYMBOL, "buy", QTY, new_price)
            grid[order["id"]] = ("buy", new_price)
            bot.send_message(CHAT_ID, f"📉 BUY KOYULDU {round(new_price,2)}")

    except Exception as e:
        print("OPPOSITE ERROR:", e)

# ===== TAKİP =====
def monitor():

    while True:
        try:
            open_orders = exchange.fetch_open_orders(SYMBOL)
            open_ids = [o["id"] for o in open_orders]

            for order_id in list(grid.keys()):

                if order_id not in open_ids:

                    side, price = grid.pop(order_id)

                    bot.send_message(CHAT_ID, f"💰 {side.upper()} GERÇEKLEŞTİ")

                    place_opposite(side, price)

            time.sleep(3)

        except Exception as e:
            print("MONITOR ERROR:", e)
            time.sleep(5)

# ===== START =====
def start():
    exchange.fetch_balance()
    bot.send_message(CHAT_ID, "🤖 PROFESYONEL GRID AKTİF")

    place_initial_grid()

threading.Thread(target=start, daemon=True).start()
threading.Thread(target=monitor, daemon=True).start()

bot.infinity_polling()
