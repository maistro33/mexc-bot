import os
import time
import ccxt
import telebot
import threading
import random
import json

# ===== CONFIG =====
LEV = 10
BASE_MARGIN = 1
MAX_POSITIONS = 2

SCAN_DELAY = 15
MIN_VOLUME = 800000
MAX_SPREAD = 0.005
MIN_NOTIONAL = 5

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
last_trade_time = time.time()

# ===== UTILS =====
def safe(x):
    try: return float(x)
    except: return 0

# ===== MEMORY =====
def load_stats():
    try:
        with open("stats.json", "r") as f:
            return json.load(f)
    except:
        return {}

def save_stats(stats):
    with open("stats.json", "w") as f:
        json.dump(stats, f)

def update_stats(sym, profit):
    stats = load_stats()
    if sym not in stats:
        stats[sym] = {"win": 0, "loss": 0, "streak": 0}

    if profit > 0:
        stats[sym]["win"] += 1
        stats[sym]["streak"] += 1
    else:
        stats[sym]["loss"] += 1
        stats[sym]["streak"] = 0

    save_stats(stats)

# ===== GLOBAL PERF =====
def global_performance():
    stats = load_stats()
    wins = sum(v["win"] for v in stats.values())
    loss = sum(v["loss"] for v in stats.values())
    total = wins + loss
    return (wins / total) if total > 0 else 0.5

# ===== ADAPTIVE =====
def adaptive_thresholds():
    global last_trade_time

    perf = global_performance()
    no_trade = time.time() - last_trade_time

    mom = 0.004
    vol = 0.006

    if no_trade > 300:
        mom -= 0.001
        vol -= 0.001

    if perf > 0.65:
        mom += 0.002
        vol += 0.002

    if perf < 0.4:
        mom -= 0.001
        vol -= 0.001

    return mom, vol

# ===== POSITIONS =====
def current_positions():
    try:
        positions = exchange.fetch_positions()
        return sum(1 for p in positions if safe(p.get("contracts")) > 0)
    except:
        return 0

# ===== FILTER =====
def blacklist(sym):
    bad = ["1000","UP","DOWN","BULL","BEAR"]
    return not any(b in sym.upper() for b in bad)

# ===== SCAN =====
def get_symbols():
    try:
        tickers = exchange.fetch_tickers()
        candidates = []

        for sym, data in tickers.items():
            if "USDT" not in sym or ":USDT" not in sym:
                continue
            if not blacklist(sym):
                continue

            vol = data.get("quoteVolume", 0)
            if vol < MIN_VOLUME:
                continue

            change = abs(data.get("percentage", 0))
            price = data.get("last", 0)
            if price <= 0:
                continue

            score = change * 2 + (vol / 1_000_000)
            candidates.append((sym, score))

        candidates.sort(key=lambda x: x[1], reverse=True)
        pool = candidates[:120]
        top = [x[0] for x in pool[:20]]

        random.shuffle(top)
        return top

    except:
        return []

# ===== SIGNAL =====
def signal(sym):
    try:
        mom_thr, vol_thr = adaptive_thresholds()

        h1 = exchange.fetch_ohlcv(sym, "1h", limit=20)
        m5 = exchange.fetch_ohlcv(sym, "5m", limit=10)

        h1c = [c[4] for c in h1]
        m5c = [c[4] for c in m5]

        trend = h1c[-1] > sum(h1c[-10:])/10
        mom = (m5c[-1] - m5c[-3]) / m5c[-3]

        high = max(c[2] for c in m5)
        low = min(c[3] for c in m5)
        vol = (high - low) / low

        # 🔥 güçlü sinyal şartı
        if abs(mom) < mom_thr * 1.2 or vol < vol_thr:
            return None, 0

        direction = "long" if trend and mom > 0 else "short" if not trend and mom < 0 else None

        score = 2
        if abs(mom) > mom_thr * 1.5: score += 1
        if vol > vol_thr * 1.5: score += 1

        return direction, score

    except:
        return None, 0

# ===== QTY =====
def format_qty(sym, price, size):
    try:
        target = max(size * LEV, 10)
        raw = target / price
        qty = float(exchange.amount_to_precision(sym, raw))
        return qty if qty >= 1 else 0
    except:
        return 0

# ===== AI EXIT =====
def ai_manage(sym, price, entry, direction):
    try:
        state = trade_state[sym]

        # 🔥 min hold
        if time.time() - state["time"] < 60:
            return "hold"

        m1 = exchange.fetch_ohlcv(sym, "1m", limit=10)
        closes = [c[4] for c in m1]

        momentum = (closes[-1] - closes[-3]) / closes[-3]

        roe = ((price-entry)/entry*100)*LEV if direction=="long" else ((entry-price)/entry*100)*LEV

        # 🔥 kâr koruma
        if roe > 2:
            return "hold"

        # 🔥 exit daha akıllı
        if direction=="long" and momentum < -0.004 and roe < -3:
            return "exit"

        if direction=="short" and momentum > 0.004 and roe < -3:
            return "exit"

        if roe > 25:
            return "exit"

        return "hold"

    except:
        return "hold"

# ===== TRADE =====
def open_trade(sym, direction, score):
    global last_trade_time

    try:
        if current_positions() >= MAX_POSITIONS:
            return

        now = time.time()

        # 🔥 cooldown
        if sym in cooldown and now - cooldown[sym] < 300:
            return

        size = BASE_MARGIN

        ticker = exchange.fetch_ticker(sym)
        price = ticker["last"]

        qty = format_qty(sym, price, size)
        if qty <= 0:
            print("QTY ERROR:", sym)
            return

        exchange.set_leverage(LEV, sym)
        side = "buy" if direction=="long" else "sell"

        exchange.create_market_order(sym, side, qty)

        trade_state[sym] = {
            "entry": price,
            "direction": direction,
            "partial_done": False,
            "adds": 0,
            "time": time.time()
        }

        cooldown[sym] = time.time()
        last_trade_time = time.time()

        bot.send_message(CHAT_ID, f"🚀 {sym} {direction}")

    except Exception as e:
        print("OPEN:", e)

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
                side = "sell" if direction=="long" else "buy"

                roe = ((price-entry)/entry*100)*LEV if direction=="long" else ((entry-price)/entry*100)*LEV

                if qty * price < MIN_NOTIONAL:
                    continue

                # PARTIAL
                if not trade_state[sym]["partial_done"] and roe > 10:
                    exchange.create_market_order(sym, side, qty*0.5, params={"reduceOnly": True})
                    trade_state[sym]["partial_done"] = True

                # ADD
                if trade_state[sym]["adds"] < 2 and roe > 8:
                    exchange.create_market_order(sym, "buy" if direction=="long" else "sell", qty*0.5)
                    trade_state[sym]["adds"] += 1

                # EXIT
                if ai_manage(sym, price, entry, direction) == "exit":
                    exchange.create_market_order(sym, side, qty, params={"reduceOnly": True})
                    update_stats(sym, roe)
                    trade_state.pop(sym)

            time.sleep(5)

        except:
            time.sleep(6)

# ===== SCANNER =====
def scanner():
    while True:
        try:
            for sym in get_symbols():
                d, s = signal(sym)
                if d:
                    open_trade(sym, d, s)
                time.sleep(0.3)

            time.sleep(SCAN_DELAY)
        except:
            time.sleep(10)

# ===== START =====
print("ULTIMATE ADAPTIVE BOT STARTED")

threading.Thread(target=manage, daemon=True).start()
threading.Thread(target=scanner, daemon=True).start()
threading.Thread(target=bot.infinity_polling, daemon=True).start()

bot.send_message(CHAT_ID, "🔥 FINAL BOT AKTİF")

while True:
    time.sleep(60)
