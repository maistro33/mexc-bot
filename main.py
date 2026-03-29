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
exchange = ccxt.bitget({
    "apiKey": os.getenv("BITGET_API"),
    "secret": os.getenv("BITGET_SEC"),
    "password": "Berfin33",
    "options": {"defaultType": "swap"},
    "enableRateLimit": True
})

exchange.load_markets()

# ===== CONFIG (PRO AYAR) =====
CONFIG = {
    "BTC/USDT:USDT": {
        "QTY": 0.001,
        "STEP": 0.01,
        "TP": 4.0
    },
    "SOL/USDT:USDT": {
        "QTY": 1,
        "STEP": 0.015,
        "TP": 3.0
    }
}

positions = {}

# ===== POSITION CHECK =====
def has_position(sym):
    try:
        pos = exchange.fetch_positions()
        for p in pos:
            if sym in p["symbol"] and float(p["contracts"]) > 0:
                return True
        return False
    except:
        return False

# ===== PRICE =====
def get_price(sym):
    return exchange.fetch_ticker(sym)["last"]

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
                        sym,
                        "sell",
                        qty,
                        params={"reduceOnly": True}
                    )

                    bot.send_message(CHAT_ID, f"💰 TP\n{sym}\nPNL: {round(pnl,2)}")
                    del positions[sym]

                # GRID ADD (düşüşte ekleme)
                elif price < entry * (1 - cfg["STEP"]):
                    exchange.create_market_order(sym, "buy", qty)

                    positions[sym]["entry"] = (entry + price) / 2

                    bot.send_message(CHAT_ID, f"📉 GRID ADD\n{sym}")

            time.sleep(2)

        except Exception as e:
            print("MANAGE ERROR:", e)
            time.sleep(3)

# ===== START =====
def start():
    exchange.fetch_balance()
    bot.send_message(CHAT_ID, "🤖 PRO GRID BOT AKTİF")

    while True:
        for sym in CONFIG:
            open_trade(sym)

        time.sleep(15)

# ===== RUN =====
threading.Thread(target=start, daemon=True).start()
threading.Thread(target=manage, daemon=True).start()

bot.infinity_polling()
