import os
import time
import ccxt
import telebot
import threading

SYMBOL = "BTC/USDT:USDT"

LEV = 3
QTY = 0.00015

GRID_STEP = 0.004
LEVELS = 2

RECENTER_PCT = 0.015
STOP_LOSS = 0.02

bot = telebot.TeleBot(os.getenv("TELE_TOKEN"))
CHAT_ID = os.getenv("MY_CHAT_ID")

exchange = ccxt.bitget({
    "apiKey": os.getenv("BITGET_API"),
    "secret": os.getenv("BITGET_SEC"),
    "password": os.getenv("BITGET_PASS"),
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


# ===== TEST ORDER =====
def test_order():
    try:
        bot.send_message(CHAT_ID, "🧪 TEST ORDER GÖNDERİLİYOR")

        order = exchange.create_market_order(
            SYMBOL,
            "buy",
            0.0001,
            {"tdMode": "cross", "posSide": "long"}
        )

        bot.send_message(CHAT_ID, "✅ TEST LONG AÇILDI")

    except Exception as e:
        bot.send_message(CHAT_ID, f"❌ TEST HATA: {e}")
        print("TEST ERROR:", e)


# ===== GRID =====
def place_grid():
    global base_price, grid

    cancel_all()
    grid = {}

    base_price = get_price()

    exchange.set_leverage(LEV, SYMBOL)

    for i in range(1, LEVELS + 1):

        buy_price = base_price * (1 - GRID_STEP * i)
        sell_price = base_price * (1 + GRID_STEP * i)

        buy = exchange.create_limit_order(
            SYMBOL, "buy", QTY, buy_price,
            {"tdMode": "cross", "posSide": "long"}
        )

        sell = exchange.create_limit_order(
            SYMBOL, "sell", QTY, sell_price,
            {"tdMode": "cross", "posSide": "short"}
        )

        grid[buy["id"]] = ("buy", buy_price)
        grid[sell["id"]] = ("sell", sell_price)

    bot.send_message(CHAT_ID, "📊 GRID KURULDU")


# ===== STOP LOSS =====
def check_stop():
    try:
        positions = exchange.fetch_positions([SYMBOL])

        for p in positions:
            if float(p["contracts"]) > 0:
                pnl = float(p["unrealizedPnl"])

                if pnl < -STOP_LOSS:
                    cancel_all()
                    bot.send_message(CHAT_ID, "⛔ STOP LOSS ÇALIŞTI")
                    return True
    except:
        pass

    return False


# ===== MONITOR =====
def monitor():
    global last_price, base_price, grid

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

            # GRID RESET
            if abs(price - base_price) / base_price > RECENTER_PCT:
                bot.send_message(CHAT_ID, "♻️ GRID RESET")
                place_grid()
                time.sleep(3)
                continue

            open_orders = exchange.fetch_open_orders(SYMBOL)
            open_ids = [o["id"] for o in open_orders]

            for oid in list(grid.keys()):

                if oid not in open_ids:

                    side, p = grid.pop(oid)

                    bot.send_message(CHAT_ID, f"💰 {side.upper()} EXECUTED")

                    if side == "buy":
                        new_price = p * (1 + GRID_STEP)
                        o = exchange.create_limit_order(
                            SYMBOL, "sell", QTY, new_price,
                            {"tdMode": "cross", "posSide": "short"}
                        )
                        grid[o["id"]] = ("sell", new_price)

                    else:
                        new_price = p * (1 - GRID_STEP)
                        o = exchange.create_limit_order(
                            SYMBOL, "buy", QTY, new_price,
                            {"tdMode": "cross", "posSide": "long"}
                        )
                        grid[o["id"]] = ("buy", new_price)

            last_price = price

            time.sleep(3)

        except Exception as e:
            print("MONITOR ERROR:", e)
            time.sleep(5)


# ===== START =====
def start():
    exchange.fetch_balance()
    bot.send_message(CHAT_ID, "🤖 BOT BAŞLADI")

    test_order()  # 🔥 TEST BURADA

    time.sleep(5)

    place_grid()


threading.Thread(target=start, daemon=True).start()
threading.Thread(target=monitor, daemon=True).start()
