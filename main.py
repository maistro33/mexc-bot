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

SCAN_DELAY = 8
SL_PERCENT = 0.012
MIN_HOLD = 25
FEE = 0.08

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

# ===== SYNC =====
def sync_positions():
    try:
        positions = exchange.fetch_positions()

        for p in positions:
            qty = safe(p.get("contracts"))
            if qty <= 0:
                continue

            sym = p["symbol"]
            entry = safe(p.get("entryPrice"))
            side = p.get("side")

            direction = "long" if side == "long" else "short"

            trade_state[sym] = {
                "entry": entry,
                "direction": direction,
                "time": time.time() - 60,
                "max_roe": 0
            }

    except Exception as e:
        print("SYNC ERROR:", e)

# ===== SYMBOL FILTER (MEME ONLY) =====
def get_symbols():
    try:
        tickers = exchange.fetch_tickers()
        arr = []

        for sym, d in tickers.items():

            if "USDT" not in sym or ":USDT" not in sym:
                continue

            # ❌ büyük coinleri tamamen sil
            if any(x in sym for x in ["BTC","ETH","SOL","BNB","XRP","ADA","DOGE","TRX","AVAX","LINK","DOT"]):
                continue

            price = safe(d.get("last"))
            vol = safe(d.get("quoteVolume"))
            change = safe(d.get("percentage"))

            # 🔥 meme coin
            if price > 5:
                continue

            # 🔥 hacim şart
            if vol < 300000:
                continue

            # 🔥 pump şart
            if abs(change) < 2:
                continue

            score = abs(change) + (vol / 1_000_000)

            arr.append((sym, score))

        arr.sort(key=lambda x: x[1], reverse=True)

        return [x[0] for x in arr[:15]]

    except:
        return []

# ===== REVERSAL SNIPER =====
def signal(sym):
    try:
        m5 = exchange.fetch_ohlcv(sym, "5m", limit=6)
        closes = [c[4] for c in m5]

        move = (closes[-1] - closes[-4]) / closes[-4]

        # 🔥 pump → short
        if move > 0.03:
            if closes[-1] < closes[-2]:
                return "short"

        # 🔥 dump → long
        if move < -0.03:
            if closes[-1] > closes[-2]:
                return "long"

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

# ===== EXIT (SCALP PRO) =====
def should_exit(sym, price, roe):
    state = trade_state[sym]
    entry = state["entry"]
    direction = state["direction"]

    if time.time() - state["time"] < MIN_HOLD:
        return False

    # HARD SL
    if direction == "long" and price <= entry * (1 - SL_PERCENT):
        return True

    if direction == "short" and price >= entry * (1 + SL_PERCENT):
        return True

    # MAX UPDATE
    if roe > state["max_roe"]:
        state["max_roe"] = roe

    maxr = state["max_roe"]

    # 🔥 micro trailing
    if maxr > 2:
        if roe < maxr - 1.2:
            return True

    if maxr > 4:
        if roe < maxr - 1.8:
            return True

    if maxr > 7:
        if roe < maxr - 2.5:
            return True

    # küçük kâr kaçırma
    if roe > 1 and roe < maxr - 0.8:
        return True

    return False

# ===== OPEN =====
def open_trade(sym, direction):
    try:
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
            "max_roe": 0
        }

        cooldown[sym] = time.time()

        bot.send_message(CHAT_ID, f"🎯 SNIPER {sym} {direction}")

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

                raw = ((price - entry) / entry * 100) * LEV if direction == "long" \
                    else ((entry - price) / entry * 100) * LEV

                roe = raw - FEE

                if should_exit(sym, price, roe):
                    exchange.create_market_order(sym, side, qty, params={"reduceOnly": True})
                    trade_state.pop(sym)
                    bot.send_message(CHAT_ID, f"🏁 EXIT {sym} {roe:.2f}%")

            time.sleep(2)

        except Exception as e:
            print("MANAGE ERROR:", e)
            time.sleep(3)

# ===== SCANNER =====
def scanner():
    while True:
        try:
            for sym in get_symbols():
                if len(trade_state) >= MAX_POSITIONS:
                    break

                d = signal(sym)
                if d:
                    open_trade(sym, d)

                time.sleep(0.3)

            time.sleep(SCAN_DELAY)

        except:
            time.sleep(10)

# ===== START =====
print("🔥 MEME SNIPER STARTED")

sync_positions()

threading.Thread(target=manage, daemon=True).start()
threading.Thread(target=scanner, daemon=True).start()
threading.Thread(target=bot.infinity_polling, daemon=True).start()

bot.send_message(CHAT_ID, "🔥 MEME SNIPER AKTİF")

while True:
    time.sleep(60)
