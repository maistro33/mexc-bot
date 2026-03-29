import os
import time
import ccxt
import telebot
import threading

# ===== SETTINGS =====
LEV = 5

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
        "STEP": 0.005,
        "TP": 1.0
    },
    "SOL/USDT:USDT": {
        "QTY": 0.5,
        "STEP": 0.008,
        "TP": 1.0
    }
}

positions = {}

# ===== PRICE =====
def get_price(sym):
    return exchange.fetch_ticker(sym)["last"]

# ===== CHECK POSITION =====
def has_position(sym):
    try:
        positions = exchange.fetch_positions()
        for p in positions:
            if sym in p["symbol"] and float(p["contracts"]) > 0:
                return True
        return False
    except:
        return False

# ===== OPEN =====
def open_trade(sym):
    try:
        if has_position(sym):
            return

        cfg = CONFIG[sym]
        price = get_price(sym)
        qty = cfg["QTY"]

        exchange.set_leverage(LEV, sym)

        exchange.create_market_order(sym, "buy", qty)

        positions[sym] = {
            "entry": price,
            "qty": qty
        }

        bot.send_message(CHAT_ID, f"🚀 LONG AÇILDI\n{sym}")

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

                pnl = (price - entry) * qty

                # TP
                if pnl >= cfg["TP"]:
                    exchange.create_market_order(
                        sym, "sell", qty,
                        params={"reduceOnly": True}
                    )

                    bot.send_message(CHAT_ID, f"💰 TP {sym} {round(pnl,2)}")
                    del positions[sym]

                # GRID ADD (düşüşte ekleme)
                elif price < entry * (1 - cfg["STEP"]):
                    exchange.create_market_order(sym, "buy", qty)

                    positions[sym]["entry"] = (entry + price) / 2

                    bot.send_message(CHAT_ID, f"📉 GRID ADD {sym}")

            time.sleep(2)

        except Exception as e:
            print("MANAGE ERROR:", e)
            time.sleep(3)

# ===== START =====
def start_bot():
    exchange.fetch_balance()

    bot.send_message(CHAT_ID, "🤖 GRID BOT AKTİF (ONE WAY FINAL)")

    while True:
        for sym in CONFIG.keys():
            open_trade(sym)

        time.sleep(10)

threading.Thread(target=start_bot, daemon=True).start()
threading.Thread(target=manage, daemon=True).start()

bot.infinity_polling()
