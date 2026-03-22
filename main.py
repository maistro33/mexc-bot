import os
import time
import ccxt
import telebot
import threading
import random

# ===== CONFIG =====
LEV = 10
BASE_MARGIN = 2
MAX_POSITIONS = 2

SCAN_DELAY = 12
MIN_VOLUME = 1000000

STEP_SIZE = 1.2       # %1.2 step
SL_PERCENT = 0.008    # %0.8 hard stop
MIN_HOLD = 30         # minimum bekleme

bot = telebot.TeleBot(os.getenv("TELE_TOKEN"))
CHAT_ID = os.getenv("MY_CHAT_ID")

exchange = ccxt.bitget({
    "apiKey": os.getenv("BITGET_API"),
    "secret": os.getenv("BITGET_SEC"),
    "password": "Berfin33",
    "options": {"defaultType": "swap"},
    "enableRateLimit": True
})

trade_state = {}
cooldown = {}

# ===== UTILS =====
def safe(x):
    try:
        return float(x)
    except:
        return 0

# ===== POSITION COUNT =====
def current_positions():
    try:
        pos = exchange.fetch_positions()
        return sum(1 for p in pos if safe(p.get("contracts")) > 0)
    except:
        return 0

# ===== SYMBOL SCAN =====
def get_symbols():
    try:
        tickers = exchange.fetch_tickers()
        arr = []

        for sym, d in tickers.items():
            if "USDT" not in sym or ":USDT" not in sym:
                continue

            vol = d.get("quoteVolume", 0)
            if vol < MIN_VOLUME:
                continue

            change = abs(d.get("percentage", 0))
            score = change * 2 + (vol / 1_000_000)

            arr.append((sym, score))

        arr.sort(key=lambda x: x[1], reverse=True)
        top = [x[0] for x in arr[:20]]

        random.shuffle(top)
        return top

    except:
        return []

# ===== SIGNAL (RETEST ENTRY) =====
def signal(sym):
    try:
        m5 = exchange.fetch_ohlcv(sym, "5m", limit=6)

        c1 = m5[-1][4]
        c2 = m5[-2][4]
        c3 = m5[-3][4]

        # LONG
        pump = (c2 - c3) / c3 > 0.005
        pullback = c1 < c2
        confirm = c1 > c3

        if pump and pullback and confirm:
            return "long"

        # SHORT
        pump_down = (c3 - c2) / c3 > 0.005
        pullback_up = c1 > c2
        confirm_down = c1 < c3

        if pump_down and pullback_up and confirm_down:
            return "short"

        return None

    except:
        return None

# ===== QTY FIX =====
def format_qty(sym, price):
    try:
        market = exchange.market(sym)

        min_qty = market['limits']['amount']['min']

        target_usdt = BASE_MARGIN * LEV
        raw_qty = target_usdt / price

        qty = float(exchange.amount_to_precision(sym, raw_qty))

        if qty < min_qty:
            return 0

        return qty

    except:
        return 0

# ===== TRAILING UPDATE =====
def update_trailing(sym, price):
    state = trade_state[sym]
    entry = state["entry"]
    direction = state["direction"]

    profit = (price - entry) / entry if direction == "long" else (entry - price) / entry
    step = int(profit / (STEP_SIZE / 100))

    if step > state["step"]:
        state["step"] = step

        if direction == "long":
            new_stop = entry * (1 + (step - 1) * (STEP_SIZE / 100))
            if new_stop > state["trail_price"]:
                state["trail_price"] = new_stop

        else:
            new_stop = entry * (1 - (step - 1) * (STEP_SIZE / 100))
            if new_stop < state["trail_price"]:
                state["trail_price"] = new_stop

# ===== EXIT =====
def should_exit(sym, price):
    state = trade_state[sym]

    entry = state["entry"]
    direction = state["direction"]

    # HARD SL
    if direction == "long" and price <= entry * (1 - SL_PERCENT):
        return True

    if direction == "short" and price >= entry * (1 + SL_PERCENT):
        return True

    # MIN HOLD
    if time.time() - state["time"] < MIN_HOLD:
        return False

    # TRAILING STOP
    if direction == "long" and price <= state["trail_price"]:
        return True

    if direction == "short" and price >= state["trail_price"]:
        return True

    return False

# ===== OPEN TRADE =====
def open_trade(sym, direction):
    try:
        if current_positions() >= MAX_POSITIONS:
            return

        if sym in cooldown and time.time() - cooldown[sym] < 300:
            return

        ticker = exchange.fetch_ticker(sym)
        price = ticker["last"]

        qty = format_qty(sym, price)
        if qty <= 0:
            return

        exchange.set_leverage(LEV, sym)

        side = "buy" if direction == "long" else "sell"
        exchange.create_market_order(sym, side, qty)

        trade_state[sym] = {
            "entry": price,
            "direction": direction,
            "time": time.time(),
            "step": 0,
            "trail_price": price
        }

        cooldown[sym] = time.time()

        bot.send_message(CHAT_ID, f"🚀 {sym} {direction}")

    except Exception as e:
        print("OPEN ERROR:", e)

# ===== MANAGE =====
def manage():
    while True:
        try:
            positions = exchange.fetch_positions()

            for p in positions:
                qty = safe(p.get("contracts"))
                if qty <= 0:
                    continue

                sym = p["symbol"]

                if sym not in trade_state:
                    continue

                price = exchange.fetch_ticker(sym)["last"]
                direction = trade_state[sym]["direction"]

                side = "sell" if direction == "long" else "buy"

                update_trailing(sym, price)

                if should_exit(sym, price):
                    exchange.create_market_order(sym, side, qty, params={"reduceOnly": True})
                    trade_state.pop(sym)
                    bot.send_message(CHAT_ID, f"❌ CLOSE {sym}")

            time.sleep(2)

        except Exception as e:
            print("MANAGE ERROR:", e)
            time.sleep(3)

# ===== SCANNER =====
def scanner():
    while True:
        try:
            for sym in get_symbols():
                d = signal(sym)
                if d:
                    open_trade(sym, d)
                time.sleep(0.3)

            time.sleep(SCAN_DELAY)

        except:
            time.sleep(10)

# ===== START =====
print("FINAL STABLE BOT STARTED")

threading.Thread(target=manage, daemon=True).start()
threading.Thread(target=scanner, daemon=True).start()
threading.Thread(target=bot.infinity_polling, daemon=True).start()

bot.send_message(CHAT_ID, "🔥 FINAL BOT AKTİF")

while True:
    time.sleep(60)
