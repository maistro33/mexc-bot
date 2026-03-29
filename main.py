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

# 🔥 SADECE BTC
CONFIG = {
    "BTC/USDT:USDT": {
        "QTY": 0.0005,
        "STEP": 0.01,
        "TP": 2.0
    }
}

positions = {}

def get_price(sym):
    return exchange.fetch_ticker(sym)["last"]

def open_trade(sym):
    try:
        if sym in positions:
            return

        cfg = CONFIG[sym]
        price = get_price(sym)
        qty = cfg["QTY"]

        exchange.set_leverage(LEV, sym)
        exchange.create_market_order(sym, "buy", qty)

        positions[sym] = {"entry": price, "qty": qty}

        bot.send_message(CHAT_ID, f"🚀 BTC LONG AÇILDI")

    except Exception as e:
        print("OPEN ERROR:", e)

def manage():
    while True:
        try:
            for sym in list(positions.keys()):
                cfg = CONFIG[sym]
                pos = positions[sym]

                price = get_price(sym)
                entry = pos["entry"]
                qty = pos["qty"]

                pnl = (price - entry) * qty

                # TP
                if pnl >= cfg["TP"]:
                    exchange.create_market_order(
                        sym,
                        "sell",
                        qty,
                        params={"reduceOnly": True}
                    )

                    bot.send_message(CHAT_ID, f"💰 TP {round(pnl,2)}$")
                    del positions[sym]

                # GRID ADD
                elif price < entry * (1 - cfg["STEP"]):
                    exchange.create_market_order(sym, "buy", qty)
                    positions[sym]["entry"] = (entry + price) / 2

                    bot.send_message(CHAT_ID, f"📉 GRID ADD BTC")

            time.sleep(2)

        except Exception as e:
            print("MANAGE ERROR:", e)
            time.sleep(3)

def start():
    exchange.fetch_balance()
    bot.send_message(CHAT_ID, "🤖 BTC GRID BOT AKTİF")

    while True:
        for sym in CONFIG:
            open_trade(sym)

        time.sleep(15)

threading.Thread(target=start, daemon=True).start()
threading.Thread(target=manage, daemon=True).start()

bot.infinity_polling()
