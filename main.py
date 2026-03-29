import os
import time
import ccxt
import telebot
import threading

LEV = 5

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

CONFIG = {
    "BTC/USDT:USDT": {
        "QTY": 0.0005,
        "TP": 0.5   # 🔥 hızlı kar
    }
}

position = None

def get_price(sym):
    return exchange.fetch_ticker(sym)["last"]

def open_trade():
    global position
    try:
        if position:
            return

        sym = "BTC/USDT:USDT"
        price = get_price(sym)

        exchange.set_leverage(LEV, sym)
        exchange.create_market_order(sym, "buy", CONFIG[sym]["QTY"])

        position = {
            "entry": price,
            "qty": CONFIG[sym]["QTY"]
        }

        bot.send_message(CHAT_ID, f"🚀 BTC LONG AÇILDI")

    except Exception as e:
        print("OPEN ERROR:", e)

def manage():
    global position

    while True:
        try:
            if not position:
                time.sleep(2)
                continue

            sym = "BTC/USDT:USDT"
            price = get_price(sym)

            pnl = (price - position["entry"]) * position["qty"]

            if pnl >= CONFIG[sym]["TP"]:
                exchange.create_market_order(
                    sym,
                    "sell",
                    position["qty"],
                    params={"reduceOnly": True}
                )

                bot.send_message(CHAT_ID, f"💰 KAR ALDI: {round(pnl,2)} USDT")
                position = None

            time.sleep(2)

        except Exception as e:
            print("MANAGE ERROR:", e)
            time.sleep(3)

def start():
    exchange.fetch_balance()
    bot.send_message(CHAT_ID, "🤖 BASİT BOT AKTİF")

    while True:
        open_trade()
        time.sleep(10)

threading.Thread(target=start, daemon=True).start()
threading.Thread(target=manage, daemon=True).start()

bot.infinity_polling()
