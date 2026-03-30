import os
import time
import ccxt
import telebot
import threading

SYMBOL = "BTC/USDT:USDT"

LEV = 5
QTY = 0.0003

GRID_STEP = 0.003
LEVELS = 3

SCALP_PCT = 0.002   # %0.2 scalp
RECENTER_PCT = 0.015  # %1.5 reset

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

    bot.send_message(CHAT_ID, "📊 HYBRID GRID KURULDU")

# ===== SCALP =====
def scalp_trade(price):
    try:
        qty = QTY
        exchange.create_market_order(SYMBOL, "buy", qty)
        time.sleep(1)

        sell_price = price * (1 + SCALP_PCT)

        exchange.create_limit_order(SYMBOL, "sell", qty, sell_price)

        bot.send_message(CHAT_ID, f"⚡ SCALP TRADE {round(price,2)}")

    except Exception as e:
        print("SCALP ERROR:", e)

# ===== MONITOR =====
def monitor():
    global last_price, base_price

    while True:
        try:
            price = get_price()

            if base_price is None:
                time.sleep(2)
                continue

            # 🔥 GRID RESET
            if abs(price - base_price) / base_price > RECENTER_PCT:
                bot.send_message(CHAT_ID, "♻️ RESET (TREND)")
                place_grid()
                time.sleep(2)
                continue

            # ⚡ SCALP fırsatı
            if last_price:
                change = (price - last_price) / last_price

                if change > SCALP_PCT:
                    scalp_trade(price)

            last_price = price

            open_orders = exchange.fetch_open_orders(SYMBOL)
            open_ids = [o["id"] for o in open_orders]

            for oid in list(grid.keys()):

                if oid not in open_ids:

                    side, p = grid.pop(oid)

                    bot.send_message(CHAT_ID, f"💰 {side.upper()}")

                    # ters emir
                    if side == "buy":
                        new_price = p * (1 + GRID_STEP)
                        o = exchange.create_limit_order(SYMBOL, "sell", QTY, new_price)
                        grid[o["id"]] = ("sell", new_price)

                    else:
                        new_price = p * (1 - GRID_STEP)
                        o = exchange.create_limit_order(SYMBOL, "buy", QTY, new_price)
                        grid[o["id"]] = ("buy", new_price)

            time.sleep(2)

        except Exception as e:
            print("MONITOR ERROR:", e)
            time.sleep(5)

# ===== START =====
def start():
    exchange.fetch_balance()
    bot.send_message(CHAT_ID, "🤖 HYBRID BOT AKTİF")

    place_grid()

threading.Thread(target=start, daemon=True).start()
threading.Thread(target=monitor, daemon=True).start()

bot.infinity_polling()
