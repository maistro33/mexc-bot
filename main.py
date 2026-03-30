import os
import time
import ccxt
import telebot
import threading

# ===== AYAR =====
SYMBOL = "BTC/USDT:USDT"

LEV = 5
QTY = 0.0003

GRID_STEP = 0.0015
LEVELS = 4

SCALP_PCT = 0.0007   # 🔥 hızlı scalp
SHIFT_PCT = 0.007    # 🔥 daha erken reset

FOLLOW_DIST = 0.0004  # 🔥 çok yakın takip
FOLLOW_UPDATE = 0.001  # 🔥 %0.1 değişmeden güncelleme yok

# ===== TELEGRAM =====
bot = telebot.TeleBot(os.getenv("TELE_TOKEN"))
CHAT_ID = os.getenv("MY_CHAT_ID")

# ===== BORSA =====
exchange = ccxt.bitget({
    "apiKey": os.getenv("BITGET_API"),
    "secret": os.getenv("BITGET_SEC"),
    "password": "Berfin33",
    "options": {"defaultType": "swap"},
    "enableRateLimit": True
})

exchange.load_markets()

# ===== GLOBAL =====
grid = {}
base_price = None
last_price = None

follow_orders = {}
last_follow_price = None

# ===== PRICE =====
def get_price():
    return exchange.fetch_ticker(SYMBOL)["last"]

# ===== TEMİZLE =====
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

    bot.send_message(CHAT_ID, "📊 GRID AKTİF")

# ===== FOLLOW =====
def update_follow(price):
    global follow_orders, last_follow_price

    try:
        # sadece yeterli hareket varsa güncelle
        if last_follow_price:
            change = abs(price - last_follow_price) / last_follow_price
            if change < FOLLOW_UPDATE:
                return

        last_follow_price = price

        # eski emirleri sil
        for oid in list(follow_orders.keys()):
            try:
                exchange.cancel_order(oid, SYMBOL)
            except:
                pass
            follow_orders.pop(oid, None)

        # yeni emirler
        buy_price = price * (1 - FOLLOW_DIST)
        sell_price = price * (1 + FOLLOW_DIST)

        buy = exchange.create_limit_order(SYMBOL, "buy", QTY, buy_price)
        sell = exchange.create_limit_order(SYMBOL, "sell", QTY, sell_price)

        follow_orders[buy["id"]] = ("buy", buy_price)
        follow_orders[sell["id"]] = ("sell", sell_price)

    except Exception as e:
        print("FOLLOW ERROR:", e)

# ===== SCALP =====
def scalp_trade(price):
    try:
        exchange.create_market_order(SYMBOL, "buy", QTY)
        time.sleep(0.3)

        tp = price * (1 + SCALP_PCT)
        exchange.create_limit_order(SYMBOL, "sell", QTY, tp)

        bot.send_message(CHAT_ID, f"⚡ SCALP {round(price,2)}")

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

            # 🔄 RESET
            if abs(price - base_price) / base_price > SHIFT_PCT:
                bot.send_message(CHAT_ID, "🔄 RESET")
                place_grid()
                continue

            # 🔥 FOLLOW
            update_follow(price)

            # ⚡ SCALP
            if last_price:
                change = abs(price - last_price) / last_price
                if change > SCALP_PCT:
                    scalp_trade(price)

            last_price = price

            # GRID kontrol
            open_orders = exchange.fetch_open_orders(SYMBOL)
            open_ids = [o["id"] for o in open_orders]

            for oid in list(grid.keys()):
                if oid not in open_ids:

                    side, p = grid.pop(oid)

                    bot.send_message(CHAT_ID, f"💰 {side.upper()}")

                    if side == "buy":
                        new_price = p * (1 + GRID_STEP)
                        o = exchange.create_limit_order(SYMBOL, "sell", QTY, new_price)
                        grid[o["id"]] = ("sell", new_price)

                    else:
                        new_price = p * (1 - GRID_STEP)
                        o = exchange.create_limit_order(SYMBOL, "buy", QTY, new_price)
                        grid[o["id"]] = ("buy", new_price)

            time.sleep(1.5)

        except Exception as e:
            print("MONITOR ERROR:", e)
            time.sleep(3)

# ===== START =====
def start():
    exchange.fetch_balance()
    bot.send_message(CHAT_ID, "🚀 FINAL BOT AKTİF")

    place_grid()

threading.Thread(target=start, daemon=True).start()
threading.Thread(target=monitor, daemon=True).start()

while True:
    time.sleep(60)
