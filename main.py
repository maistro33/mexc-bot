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

# 🔥 SENİN BAKİYEYE GÖRE
QTY = 0.0001
GRID_STEP = 0.003
LEVELS = 2   # düşürdük!

def get_price():
    return exchange.fetch_ticker(SYMBOL)["last"]

def place_grid():
    try:
        price = get_price()
        exchange.set_leverage(LEV, SYMBOL)

        for i in range(1, LEVELS + 1):

            buy_price = price * (1 - GRID_STEP * i)
            sell_price = price * (1 + GRID_STEP * i)

            exchange.create_limit_order(SYMBOL, "buy", QTY, buy_price)
            exchange.create_limit_order(SYMBOL, "sell", QTY, sell_price)

        bot.send_message(CHAT_ID, "📊 GRID YERLEŞTİRİLDİ")

    except Exception as e:
        print("GRID ERROR:", e)

def loop():
    while True:
        try:
            open_orders = exchange.fetch_open_orders(SYMBOL)

            # Eğer emir yoksa tekrar kur
            if len(open_orders) < 2:
                place_grid()

            time.sleep(10)

        except Exception as e:
            print("LOOP ERROR:", e)
            time.sleep(5)

def start():
    exchange.fetch_balance()
    bot.send_message(CHAT_ID, "🤖 GRID BOT FIX AKTİF")

    place_grid()

threading.Thread(target=start, daemon=True).start()
threading.Thread(target=loop, daemon=True).start()

bot.infinity_polling()
