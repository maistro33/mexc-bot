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

SCAN_DELAY = 10
MIN_VOLUME = 1000000

SL_PERCENT = 0.01  # %1 hard stop

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

# ===== SAFE =====
def safe(x):
    try:
        return float(x)
    except:
        return 0

# ===== POS =====
def current_positions():
    try:
        pos = exchange.fetch_positions()
        return sum(1 for p in pos if safe(p.get("contracts")) > 0)
    except:
        return 0

# ===== SYMBOLS =====
def get_symbols():
    try:
        tickers = exchange.fetch_tickers()
        arr = []

        for sym, d in tickers.items():
            if "USDT" not in sym or ":USDT" not in sym:
                continue

            vol = safe(d.get("quoteVolume"))
            if vol < MIN_VOLUME:
                continue

            price = safe(d.get("last"))
            if price < 0.001:  # çöp coin filtresi
                continue

            change = abs(safe(d.get("percentage")))
            score = change + (vol / 1_000_000)

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

        if abs(mom) < 0.004:
            return None

        if trend and mom > 0:
            return "long"
        if not trend and mom < 0:
            return "short"

        return None

    except:
        return None

# ===== QTY FIX (FULL) =====
def format_qty(sym, price):
    try:
        markets = exchange.load_markets()

        if sym not in markets:
            return 0

        market = markets[sym]

        min_qty = market.get('limits', {}).get('amount', {}).get('min', 0)

        precision = market.get('precision', {}).get('amount', 3)
        if precision is None:
            precision = 3

        target = BASE_MARGIN * LEV
        raw = target / price

        qty = round(raw, precision)

        if qty < min_qty:
            qty = min_qty

        return float(qty)

    except Exception as e:
        print("QTY ERROR:", sym, e)
        return 0

# ===== STEP UPDATE =====
def update_step(sym, roe):
    state = trade_state[sym]
    if roe > state["max_roe"]:
        state["max_roe"] = roe

# ===== EXIT (SINIRSIZ STEP) =====
def should_exit(sym, price, roe):
    state = trade_state[sym]
    entry = state["entry"]
    direction = state["direction"]
    max_roe = state["max_roe"]

    # ⏳ MIN HOLD
    if time.time() - state["time"] < 25:
        return False

    # 🔴 HARD SL
    if direction == "long" and price <= entry * (1 - SL_PERCENT):
        return True

    if direction == "short" and price >= entry * (1 + SL_PERCENT):
        return True

    # 🚀 SINIRSIZ STEP
    step = int(max_roe / 10)
    locked_profit = (step - 1) * 10

    if step > 1 and roe < locked_profit:
        return True

    return False

# ===== OPEN =====
def open_trade(sym, direction):
    try:
        if current_positions() >= MAX_POSITIONS:
            return

        now = time.time()
        if sym in cooldown and now - cooldown[sym] < 300:
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
            "max_roe": 0
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
                entry = trade_state[sym]["entry"]
                direction = trade_state[sym]["direction"]

                side = "sell" if direction == "long" else "buy"

                roe = ((price - entry) / entry * 100) * LEV if direction == "long" \
                    else ((entry - price) / entry * 100) * LEV

                update_step(sym, roe)

                if should_exit(sym, price, roe):
                    exchange.create_market_order(sym, side, qty, params={"reduceOnly": True})
                    trade_state.pop(sym)
                    bot.send_message(CHAT_ID, f"🏁 EXIT {sym} ROE {roe:.2f}%")

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
print("🔥 FINAL ULTIMATE BOT STARTED")

threading.Thread(target=manage, daemon=True).start()
threading.Thread(target=scanner, daemon=True).start()
threading.Thread(target=bot.infinity_polling, daemon=True).start()

bot.send_message(CHAT_ID, "🔥 ULTIMATE BOT AKTİF")

while True:
    time.sleep(60)
