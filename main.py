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

SCALP_PCT = 0.002
RECENTER_PCT = 0.015
STOP_LOSS = 0.02

TREND_THRESHOLD = 0.004
trend_position = False

SCALP_COOLDOWN = 30
last_scalp_time = 0

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

# ===== LEVERAGE SAFE =====
def set_leverage_safe():
    try:
        exchange.set_leverage(LEV, SYMBOL)
    except Exception as e:
        print("LEV ERROR:", e)

# ===== GRID =====
def place_grid():
    global base_price

    cancel_all()
    base_price = get_price()

    set_leverage_safe()

    for i in range(1, LEVELS + 1):

        buy_price = base_price * (1 - GRID_STEP * i)
        sell_price = base_price * (1 + GRID_STEP * i)

        buy = exchange.create_limit_order(
            SYMBOL, "buy", QTY, buy_price,
            {"reduceOnly": False}
        )

        sell = exchange.create_limit_order(
            SYMBOL, "sell", QTY, sell_price,
            {"reduceOnly": False}
        )

        grid[buy["id"]] = ("buy", buy_price)
        grid[sell["id"]] = ("sell", sell_price)

    bot.send_message(CHAT_ID, "📊 HYBRID GRID KURULDU")

# ===== SCALP (PASİF) =====
def scalp_trade(price):
    return

# ===== TREND =====
def trend_trade(direction):
    global trend_position

    if trend_position:
        return

    try:
        if direction == "up":
            exchange.create_market_order(
                SYMBOL,
                "buy",
                QTY,
                {"reduceOnly": False}
            )
            bot.send_message(CHAT_ID, "🚀 TREND LONG")

        else:
            exchange.create_market_order(
                SYMBOL,
                "sell",
                QTY,
                {"reduceOnly": False}
            )
            bot.send_message(CHAT_ID, "🔻 TREND SHORT")

        trend_position = True

    except Exception as e:
        print("TREND ERROR:", e)

# ===== STOP LOSS =====
def check_stop():
    try:
        positions = exchange.fetch_positions([SYMBOL])

        for p in positions:
            if float(p["contracts"]) > 0:
                pnl = float(p["unrealizedPnl"])

                if pnl < -STOP_LOSS:
                    cancel_all()
                    bot.send_message(CHAT_ID, "⛔ STOP LOSS")
                    return True
    except:
        pass

    return False

# ===== MONITOR =====
def monitor():
    global last_price, base_price

    while True:
        try:
            price = get_price()

            if base_price is None:
                time.sleep(2)
                continue

            # STOP LOSS
            if check_stop():
                time.sleep(5)
                continue

            if last_price:
                change = (price - last_price) / last_price

                # TREND
                if abs(change) > TREND_THRESHOLD:
                    if change > 0:
                        trend_trade("up")
                    else:
                        trend_trade("down")

            # GRID RESET
            if abs(price - base_price) / base_price > RECENTER_PCT:
                bot.send_message(CHAT_ID, "♻️ RESET (TREND)")
                place_grid()
                time.sleep(2)
                continue

            last_price = price

            open_orders = exchange.fetch_open_orders(SYMBOL)
            open_ids = [o["id"] for o in open_orders]

            for oid in list(grid.keys()):

                if oid not in open_ids:

                    side, p = grid.pop(oid)

                    bot.send_message(CHAT_ID, f"💰 {side.upper()}")

                    if side == "buy":
                        new_price = p * (1 + GRID_STEP)
                        o = exchange.create_limit_order(
                            SYMBOL, "sell", QTY, new_price,
                            {"reduceOnly": False}
                        )
                        grid[o["id"]] = ("sell", new_price)

                    else:
                        new_price = p * (1 - GRID_STEP)
                        o = exchange.create_limit_order(
                            SYMBOL, "buy", QTY, new_price,
                            {"reduceOnly": False}
                        )
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

# 🔥 BU ÇOK ÖNEMLİ
bot.infinity_polling()
