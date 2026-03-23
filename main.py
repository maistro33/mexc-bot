import os
import time
import ccxt
import telebot
import threading

# ===== CONFIG =====
LEV = 10
BASE_MARGIN = 1
MAX_POSITIONS = 2

SCAN_DELAY = 2
MIN_VOLUME = 300000

SL_PERCENT = 0.012
MIN_HOLD = 20

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

def safe(x):
    try:
        return float(x)
    except:
        return 0

# ===== SYMBOL FILTER (PUMP COINS ONLY) =====
def get_symbols():
    try:
        tickers = exchange.fetch_tickers()
        arr = []

        for sym, d in tickers.items():
            if "USDT" not in sym or ":USDT" not in sym:
                continue

            vol = safe(d.get("quoteVolume"))
            price = safe(d.get("last"))
            change = safe(d.get("percentage"))

            # sadece ucuz hızlı coinler
            if price < 0.001 or price > 5:
                continue

            # sadece yüksek hacim
            if vol < MIN_VOLUME or vol > 20000000:
                continue

            # sadece güçlü pump/dump
            if abs(change) < 5:
                continue

            score = abs(change)
            arr.append((sym, score))

        arr.sort(key=lambda x: x[1], reverse=True)
        return [x[0] for x in arr[:15]]

    except:
        return []

# ===== SIGNAL (PUMP ENTRY) =====
def signal(sym):
    try:
        m5 = exchange.fetch_ohlcv(sym, "5m", limit=10)
        closes = [c[4] for c in m5]
        highs = [c[2] for c in m5]
        lows = [c[3] for c in m5]
        vols = [c[5] for c in m5]

        avg_vol = sum(vols[:-1]) / len(vols[:-1])

        # güçlü mum
        body = abs(closes[-1] - closes[-2])
        candle_range = abs(highs[-1] - lows[-1])

        if candle_range == 0 or body < candle_range * 0.5:
            return None

        # volume spike
        vol_spike = vols[-1] > avg_vol * 1.5

        if not vol_spike:
            return None

        # yön belirleme
        if closes[-1] > closes[-2]:
            return "long"

        if closes[-1] < closes[-2]:
            return "short"

        return None

    except:
        return None

# ===== QTY =====
def format_qty(sym, price):
    try:
        target = BASE_MARGIN * LEV
        raw = target / price
        return float(exchange.amount_to_precision(sym, raw))
    except:
        return 0

# ===== STEP =====
def update_step(sym, roe):
    state = trade_state[sym]

    if roe > state["max_roe"]:
        state["max_roe"] = roe

    step = int(state["max_roe"] / 10)

    if step > state.get("last_step", -1):
        state["last_step"] = step

        bot.send_message(
            CHAT_ID,
            f"🔒 {sym} STEP {step}\n"
            f"ROE: {roe:.2f}%\n"
            f"MAX: {state['max_roe']:.2f}%"
        )

# ===== EXIT (SMART TRAILING) =====
def should_exit(sym, price, roe):
    state = trade_state[sym]
    entry = state["entry"]
    direction = state["direction"]
    max_roe = state["max_roe"]

    if time.time() - state["time"] < MIN_HOLD:
        return False

    # HARD STOP
    if direction == "long" and price <= entry * (1 - SL_PERCENT):
        return True

    if direction == "short" and price >= entry * (1 + SL_PERCENT):
        return True

    # BREAK EVEN
    if max_roe > 5:
        if direction == "long" and price <= entry:
            return True
        if direction == "short" and price >= entry:
            return True

    # TRAILING
    if max_roe < 5:
        trail = 2
    elif max_roe < 10:
        trail = 3
    elif max_roe < 20:
        trail = 5
    else:
        trail = 8

    return roe < (max_roe - trail)

# ===== OPEN =====
def open_trade(sym, direction):
    try:
        if current_positions() >= MAX_POSITIONS:
            return

        if sym in cooldown and time.time() - cooldown[sym] < 180:
            return

        price = exchange.fetch_ticker(sym)["last"]
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
            "max_roe": 0,
            "last_step": -1
        }

        cooldown[sym] = time.time()

        bot.send_message(
            CHAT_ID,
            f"🚀 ENTRY {sym}\n"
            f"Type: {direction.upper()}\n"
            f"Price: {price}"
        )

    except Exception as e:
        print("OPEN ERROR:", e)

# ===== POSITIONS =====
def current_positions():
    try:
        pos = exchange.fetch_positions()
        return sum(1 for p in pos if safe(p.get("contracts")) > 0)
    except:
        return 0

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

                roe = ((price - entry) / entry * 100) * LEV if direction == "long" else ((entry - price) / entry * 100) * LEV

                update_step(sym, roe)

                if should_exit(sym, price, roe):
                    exchange.create_market_order(sym, side, qty, params={"reduceOnly": True})
                    trade_state.pop(sym)

                    bot.send_message(
                        CHAT_ID,
                        f"🏁 EXIT {sym}\n"
                        f"Profit: {roe:.2f}%"
                    )

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
                time.sleep(0.1)

            time.sleep(SCAN_DELAY)

        except:
            time.sleep(10)

# ===== START =====
print("🔥 PRO SNIPER BOT STARTED")

threading.Thread(target=manage, daemon=True).start()
threading.Thread(target=scanner, daemon=True).start()
threading.Thread(target=bot.infinity_polling, daemon=True).start()

bot.send_message(CHAT_ID, "🔥 SNIPER BOT AKTİF")

while True:
    time.sleep(60)
