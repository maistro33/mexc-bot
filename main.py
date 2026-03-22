import os
import time
import ccxt
import telebot
import threading
import random

# ===== CONFIG =====
LEV = 10
BASE_MARGIN = 1
MAX_POSITIONS = 2

SCAN_DELAY = 12
MIN_VOLUME = 800000

STEP_SIZE = 1.0
SL_PERCENT = 0.0035
MIN_HOLD = 8

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

# ===== SIGNAL =====
def signal(sym):
    try:
        h1 = exchange.fetch_ohlcv(sym, "1h", limit=20)
        m5 = exchange.fetch_ohlcv(sym, "5m", limit=10)

        h1c = [c[4] for c in h1]
        m5c = [c[4] for c in m5]

        trend = h1c[-1] > sum(h1c[-10:]) / 10
        mom = (m5c[-1] - m5c[-3]) / m5c[-3]

        high = max(c[2] for c in m5)
        low = min(c[3] for c in m5)
        vol = (high - low) / low

        if abs(mom) < 0.006:
            return None

        if vol < 0.006:
            return None

        if trend and mom > 0:
            return "long"

        if not trend and mom < 0:
            return "short"

        return None

    except:
        return None

# ===== QTY FIX (EN ÖNEMLİ) =====
def format_qty(sym, price):
    try:
        market = exchange.market(sym)

        min_qty = market.get("limits", {}).get("amount", {}).get("min", 0)

        target = max(BASE_MARGIN * LEV, 5)
        raw_qty = target / price

        qty = float(exchange.amount_to_precision(sym, raw_qty))

        if min_qty and qty < min_qty:
            qty = min_qty

        return qty

    except Exception as e:
        print("QTY FIX ERROR:", e)
        return 0

# ===== TRAILING =====
def update_trailing(sym, roe):
    state = trade_state[sym]

    step = int(roe / STEP_SIZE)

    if step > state["max_step"]:
        state["max_step"] = step

    state["trail_level"] = state["max_step"] - 1

# ===== EXIT =====
def should_exit(sym, price, roe):
    state = trade_state[sym]

    entry = state["entry"]
    direction = state["direction"]

    # HARD SL
    if direction == "long":
        if price <= entry * (1 - SL_PERCENT):
            return True

    if direction == "short":
        if price >= entry * (1 + SL_PERCENT):
            return True

    # MIN HOLD
    if time.time() - state["time"] < MIN_HOLD:
        return False

    # TRAILING
    current_step = int(roe / STEP_SIZE)

    if current_step < state["trail_level"]:
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
            print("QTY ERROR:", sym)
            return

        exchange.set_leverage(LEV, sym)

        side = "buy" if direction == "long" else "sell"
        exchange.create_market_order(sym, side, qty)

        trade_state[sym] = {
            "entry": price,
            "direction": direction,
            "time": time.time(),
            "max_step": 0,
            "trail_level": 0
        }

        cooldown[sym] = time.time()

        bot.send_message(CHAT_ID, f"🚀 {sym} {direction}")

    except Exception as e:
        print("OPEN ERROR:", e)

# ===== MANAGER =====
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
                entry = trade_state[sym]["entry"]
                direction = trade_state[sym]["direction"]

                side = "sell" if direction == "long" else "buy"

                roe = ((price - entry) / entry * 100) * LEV if direction == "long" else ((entry - price) / entry * 100) * LEV

                update_trailing(sym, roe)

                if should_exit(sym, price, roe):
                    exchange.create_market_order(sym, side, qty, params={"reduceOnly": True})
                    trade_state.pop(sym)
                    bot.send_message(CHAT_ID, f"❌ CLOSE {sym} ROE {roe:.2f}%")

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
print("FINAL PRO BOT STARTED")

threading.Thread(target=manage, daemon=True).start()
threading.Thread(target=scanner, daemon=True).start()
threading.Thread(target=bot.infinity_polling, daemon=True).start()

bot.send_message(CHAT_ID, "🔥 FINAL PRO BOT AKTİF")

while True:
    time.sleep(60)
