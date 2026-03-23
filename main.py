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

SCAN_DELAY = 2
MIN_VOLUME = 1000000

SL_PERCENT = 0.012
MIN_HOLD = 40

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

# ===== 🔥 SYNC POSITIONS =====
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
                "time": time.time(),
                "max_roe": 0,
                "last_step": -1
            }

            print(f"SYNCED: {sym}")

    except Exception as e:
        print("SYNC ERROR:", e)

def current_positions():
    try:
        pos = exchange.fetch_positions()
        return sum(1 for p in pos if safe(p.get("contracts")) > 0)
    except:
        return 0

# ===== SYMBOLS (PUMP ODAKLI) =====
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

            if vol < MIN_VOLUME:
                continue

            if price < 0.01:
                continue

            # 🔥 SADECE HAREKETLİ COINLER
            if abs(change) < 2:
                continue

            score = abs(change) + (vol / 1_000_000)

            arr.append((sym, score))

        arr.sort(key=lambda x: x[1], reverse=True)
        top = [x[0] for x in arr[:20]]

        random.shuffle(top)
        return top

    except:
        return []

# ===== SNIPER =====
def signal(sym):
    try:
        h1 = exchange.fetch_ohlcv(sym, "1h", limit=20)
        m5 = exchange.fetch_ohlcv(sym, "5m", limit=6)

        h1c = [c[4] for c in h1]
        closes = [c[4] for c in m5]
        vols = [c[5] for c in m5]

        avg_vol = sum(vols[:-1]) / len(vols[:-1])

        # ===== GEÇ KALMA FİLTRESİ =====
        move = (closes[-1] - closes[-3]) / closes[-3]
        move_down = (closes[-3] - closes[-1]) / closes[-3]

        if move > 0.008:
            return None

        if move_down > 0.008:
            return None

        # ===== ERKEN PUMP =====
        early_pump = vols[-1] > avg_vol * 1.3 and closes[-1] > closes[-2] * 1.001

        # ===== ERKEN DUMP =====
        early_dump = vols[-1] > avg_vol * 1.3 and closes[-1] < closes[-2] * 0.999

        trend = h1c[-1] > sum(h1c[-10:]) / 10

        pump = closes[-3] < closes[-2] * 1.001
        pullback = closes[-2] > closes[-1]
        breakout = closes[-1] > closes[-2] * 0.999

        if early_pump:
            return "long"

        if early_dump:
            return "short"

        if trend and pump and pullback and breakout:
            return "long"

        pump_s = closes[-3] > closes[-2] * 0.999
        pullback_s = closes[-2] < closes[-1]
        breakout_s = closes[-1] < closes[-2] * 1.001

        if (not trend) and pump_s and pullback_s and breakout_s:
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
            f"🔒 {sym}\nSTEP {step}\nROE: {roe:.2f}%"
        )

# ===== EXIT =====
def should_exit(sym, price, roe):
    state = trade_state[sym]
    entry = state["entry"]
    direction = state["direction"]
    max_roe = state["max_roe"]

    if time.time() - state["time"] < MIN_HOLD:
        return False

    if direction == "long" and price <= entry * (1 - SL_PERCENT):
        return True

    if direction == "short" and price >= entry * (1 + SL_PERCENT):
        return True

    step = int(max_roe / 10)

    if step == 1:
        locked = 5
    elif step == 2:
        locked = 10
    else:
        locked = (step - 1) * 10

    if roe < locked:
        return True

    return False

# ===== OPEN =====
def open_trade(sym, direction):
    try:
        if current_positions() >= MAX_POSITIONS:
            return

        if sym in cooldown and time.time() - cooldown[sym] < 300:
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
print("🔥 FINAL PRO BOT STARTED (SYNC ENABLED)")

sync_positions()

threading.Thread(target=manage, daemon=True).start()
threading.Thread(target=scanner, daemon=True).start()
threading.Thread(target=bot.infinity_polling, daemon=True).start()

bot.send_message(CHAT_ID, "🔥 BOT AKTİF (PUMP SNIPER MODE)")

while True:
    time.sleep(60)
