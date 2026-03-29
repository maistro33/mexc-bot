import os
import time
import ccxt
import telebot
import threading

LEV = 3

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

SYMBOL = "BTC/USDT:USDT"
QTY = 0.0003
GRID_STEP = 0.003  # %0.3
LEVELS = 6

grid_orders = []

def get_price():
    return exchange.fetch_ticker(SYMBOL)["last"]

def place_grid():
    global grid_orders

    try:
        price = get_price()
        exchange.set_leverage(LEV, SYMBOL)

        for i in range(1, LEVELS + 1):

            buy_price = price * (1 - GRID_STEP * i)
            sell_price = price * (1 + GRID_STEP * i)

            # BUY LIMIT
            buy = exchange.create_limit_order(
                SYMBOL,
                "buy",
                QTY,
                buy_price
            )

            # SELL LIMIT
            sell = exchange.create_limit_order(
                SYMBOL,
                "sell",
                QTY,
                sell_price
            )

            grid_orders.append((buy["id"], sell["id"]))

        bot.send_message(CHAT_ID, "📊 GRID KURULDU")

    except Exception as e:
        print("GRID ERROR:", e)

def monitor():
    global grid_orders

    while True:
        try:
            open_orders = exchange.fetch_open_orders(SYMBOL)
            open_ids = [o["id"] for o in open_orders]

            # doldurulan emirleri kontrol et
            for buy_id, sell_id in grid_orders[:]:

                if buy_id not in open_ids:
                    bot.send_message(CHAT_ID, "📉 BUY gerçekleşti")
                    grid_orders.remove((buy_id, sell_id))

                if sell_id not in open_ids:
                    bot.send_message(CHAT_ID, "📈 SELL gerçekleşti")
                    grid_orders.remove((buy_id, sell_id))

            # eğer azaldıysa yeniden kur
            if len(grid_orders) < LEVELS:
                place_grid()

            time.sleep(5)

        except Exception as e:
            print("MONITOR ERROR:", e)
            time.sleep(5)

def start():
    exchange.fetch_balance()
    bot.send_message(CHAT_ID, "🤖 GERÇEK GRID BOT AKTİF")

    place_grid()

threading.Thread(target=start, daemon=True).start()
threading.Thread(target=monitor, daemon=True).start()

bot.infinity_polling()
