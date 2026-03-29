import os
import time
import ccxt
import telebot
import threading

# ===== SETTINGS =====
LEV = 5  # artırdık

# ===== TELEGRAM =====
bot = telebot.TeleBot(os.getenv("TELE_TOKEN"))
CHAT_ID = os.getenv("MY_CHAT_ID")

# ===== BITGET =====
API_KEY = os.getenv("BITGET_API")
API_SEC = os.getenv("BITGET_SEC")
PASSPHRASE = "Berfin33"

exchange = ccxt.bitget({
    "apiKey": API_KEY,
    "secret": API_SEC,
    "password": PASSPHRASE,
    "options": {"defaultType": "swap"},
    "enableRateLimit": True
})

exchange.load_markets()

# ===== CONFIG =====
CONFIG = {
    "BTC/USDT:USDT": {
        "QTY": 0.0005,
        "STEP": 0.007,
        "TP": 1.2
    },
    "SOL/USDT:USDT": {
        "QTY": 0.5,
        "STEP": 0.01,
        "TP": 1.2
    }
}

positions = {}

# ===== PRICE =====
def get_price(sym):
    try:
        return exchange.fetch_ticker(sym)["last"]
    except:
        return 0

# ===== OPEN =====
def open_hedge(sym):
    try:
        cfg = CONFIG[sym]
        price = get_price(sym)
        qty = cfg["QTY"]

        exchange.set_leverage(LEV, sym)

        # LONG
        exchange.create_market_order(sym, "buy", qty)

        # SHORT
        exchange.create_market_order(sym, "sell", qty)

        positions[sym] = {
            "entry": price,
            "qty": qty
        }

        msg = f"🚀 HEDGE AÇILDI\n{sym}\nQTY: {qty}"
        print(msg)
        bot.send_message(CHAT_ID, msg)

    except Exception as e:
        print("OPEN ERROR:", e)

# ===== MANAGE =====
def manage():
    while True:
        try:
            for sym in list(positions.keys()):

                cfg = CONFIG[sym]
                pos = positions[sym]

                price = get_price(sym)
                entry = pos["entry"]
                qty = pos["qty"]

                long_pnl = (price - entry) * qty
                short_pnl = (entry - price) * qty

                # LONG TP
                if long_pnl >= cfg["TP"]:
                    exchange.create_market_order(
                        sym, "sell", qty,
                        params={"reduceOnly": True}
                    )

                    msg = f"💰 LONG TP\n{sym}\nPNL: {round(long_pnl,2)}"
                    print(msg)
                    bot.send_message(CHAT_ID, msg)

                # SHORT TP
                if short_pnl >= cfg["TP"]:
                    exchange.create_market_order(
                        sym, "buy", qty,
                        params={"reduceOnly": True}
                    )

                    msg = f"💰 SHORT TP\n{sym}\nPNL: {round(short_pnl,2)}"
                    print(msg)
                    bot.send_message(CHAT_ID, msg)

                # GRID RESET
                if abs(price - entry) / entry >= cfg["STEP"]:
                    open_hedge(sym)
                    del positions[sym]

            time.sleep(2)

        except Exception as e:
            print("MANAGE ERROR:", e)
            time.sleep(3)

# ===== START =====
def start_bot():
    exchange.fetch_balance()

    msg = "🤖 GRID BOT AKTİF (BALANCE FIX)"
    print(msg)
    bot.send_message(CHAT_ID, msg)

    for sym in CONFIG.keys():
        open_hedge(sym)

    manage()

# ===== RUN =====
threading.Thread(target=start_bot, daemon=True).start()

bot.infinity_polling()
