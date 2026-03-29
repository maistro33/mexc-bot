import os
import time
import ccxt
import telebot
import threading

SYMBOL = "BTC/USDT:USDT"

LEV = 5
QTY = 0.0004
GRID_STEP = 0.0025
LEVELS = 4
RECENTER_PCT = 0.01

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
base_price = None  # 🔥 önemli fix

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

# ===== GRID KUR =====
def place_grid():
    global base_price

    cancel_all()

    base_price = get_price()  # 🔥 burada set ediliyor

    exchange.set_leverage(LEV, SYMBOL)

    for i in range(1, LEVELS + 1):

        buy_price = base_price * (1 - GRID_STEP * i)
        sell_price = base_price * (1 + GRID_STEP * i)

        buy = exchange.create_limit_order(SYMBOL, "buy", QTY, buy_price)
        sell = exchange.create_limit_order(SYMBOL, "sell", QTY, sell_price)

        grid[buy["id"]] = ("buy", buy_price)
        grid[sell["id"]] = ("sell", sell_price)

    bot.send_message(CHAT_ID, "🚀 PRO GRID KURULDU")

# ===== YENİ EMİR =====
def place_opposite(side, price):

    try:
        if side == "buy":
            new_price = price * (1 + GRID_STEP)
            order = exchange.create_limit_order(SYMBOL, "sell", QTY, new_price)
            grid[order["id"]] = ("sell", new_price)
            bot.send_message(CHAT_ID, f"📈 SELL {round(new_price,2)}")

        else:
            new_price = price * (1 - GRID_STEP)
            order = exchange.create_limit_order(SYMBOL, "buy", QTY, new_price)
            grid[order["id"]] = ("buy", new_price)
            bot.send_message(CHAT_ID, f"📉 BUY {round(new_price,2)}")

    except Exception as e:
        print("OPPOSITE ERROR:", e)

# ===== TAKİP =====
def monitor():
    global base_price

    while True:
        try:
            price = get_price()

            # 🔥 FIX: base_price kontrolü
            if base_price is None:
                time.sleep(2)
                continue

            # GRID RESET
            if abs(price - base_price) / base_price > RECENTER_PCT:
                bot.send_message(CHAT_ID, "♻️ GRID RESET")
                place_grid()
                time.sleep(3)
                continue

            open_orders = exchange.fetch_open_orders(SYMBOL)
            open_ids = [o["id"] for o in open_orders]

            for oid in list(grid.keys()):

                if oid not in open_ids:

                    side, p = grid.pop(oid)

                    bot.send_message(CHAT_ID, f"💰 {side.upper()} DOLDU")

                    place_opposite(side, p)

            time.sleep(2)

        except Exception as e:
            print("MONITOR ERROR:", e)
            time.sleep(5)

# ===== START =====
def start():
    exchange.fetch_balance()
    bot.send_message(CHAT_ID, "🤖 PRO AGRESİF GRID AKTİF")

    place_grid()

threading.Thread(target=start, daemon=True).start()
threading.Thread(target=monitor, daemon=True).start()

bot.infinity_polling()
