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
MAX_SPREAD = 0.003

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

# ===== UTILS =====
def safe(x):
    try: return float(x)
    except: return 0

# ===== AI MEMORY =====
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
        stats[sym] = {"win": 0, "loss": 0}

    if profit > 0:
        stats[sym]["win"] += 1
    else:
        stats[sym]["loss"] += 1

    save_stats(stats)

# ===== AI RISK =====
def ai_risk_size(sym, score):
    try:
        stats = load_stats()
        mult = 1

        if sym in stats:
            w = stats[sym]["win"]
            l = stats[sym]["loss"]
            t = w + l

            if t > 5:
                wr = w / t
                if wr > 0.7:
                    mult = 1.3
                elif wr < 0.4:
                    mult = 0.5

        if score >= 4:
            mult += 0.2

        return BASE_MARGIN * mult
    except:
        return BASE_MARGIN

# ===== SYNC =====
def sync_positions():
    try:
        positions = exchange.fetch_positions()

        for p in positions:
            qty = safe(p.get("contracts"))
            if qty <= 0:
                continue

            sym = p["symbol"]

            # 🔥 eski trade = güvenli mod
            trade_state[sym] = {
                "entry": safe(p["entryPrice"]),
                "direction": "long" if p["side"] == "long" else "short",
                "time": time.time(),
                "partial_done": True,
                "adds": 1
            }

        print("SYNC DONE")
    except:
        pass

# ===== FILTER =====
def blacklist(sym):
    bad = ["1000","UP","DOWN","BULL","BEAR"]
    return not any(b in sym.upper() for b in bad)

# ===== FULL MARKET SCAN =====
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

        # 🔥 120 havuz
        pool = candidates[:120]

        # 🔥 20 aktif
        top = [x[0] for x in pool[:20]]

        random.shuffle(top)
        return top

    except Exception as e:
        print("SCAN ERROR:", e)
        return []

# ===== SIGNAL =====
def signal(sym):
    try:
        h1 = exchange.fetch_ohlcv(sym, "1h", limit=20)
        m5 = exchange.fetch_ohlcv(sym, "5m", limit=10)

        h1c = [c[4] for c in h1]
        m5c = [c[4] for c in m5]

        trend = h1c[-1] > sum(h1c[-10:])/10
        mom = (m5c[-1] - m5c[-3]) / m5c[-3]

        high = max(c[2] for c in m5)
        low = min(c[3] for c in m5)
        vol = (high - low) / low

        if abs(mom) < 0.005 or vol < 0.007:
            return None, 0

        direction = "long" if trend and mom > 0 else "short" if not trend and mom < 0 else None

        score = 0
        if direction: score += 2
        if abs(mom) > 0.008: score += 1
        if vol > 0.01: score += 1

        # AI FILTER
        stats = load_stats()
        if sym in stats:
            t = stats[sym]["win"] + stats[sym]["loss"]
            if t > 5:
                wr = stats[sym]["win"] / t
                if wr < 0.4:
                    return None, 0

        return direction, score

    except:
        return None, 0

# ===== QTY =====
def format_qty(sym, price, size):
    try:
        target = max(size * LEV, 10)
        raw = target / price

        qty = float(exchange.amount_to_precision(sym, raw))
        market = exchange.market(sym)

        if market["precision"]["amount"] == 0:
            qty = int(qty)

        return qty if qty >= 1 else 0
    except:
        return 0

# ===== AI DECISION =====
def ai_manage(sym, price, entry, direction):
    try:
        m1 = exchange.fetch_ohlcv(sym, "1m", limit=10)
        m5 = exchange.fetch_ohlcv(sym, "5m", limit=5)

        m1c = [c[4] for c in m1]
        m5c = [c[4] for c in m5]

        mom1 = (m1c[-1] - m1c[-3]) / m1c[-3]
        mom5 = (m5c[-1] - m5c[-3]) / m5c[-3]

        high = max(c[2] for c in m1)
        low = min(c[3] for c in m1)
        vol = (high - low) / low

        roe = ((price-entry)/entry*100)*LEV if direction=="long" else ((entry-price)/entry*100)*LEV

        score = 0

        if direction == "long":
            if mom1 > 0: score += 1
            if mom5 > 0: score += 1
        else:
            if mom1 < 0: score += 1
            if mom5 < 0: score += 1

        if vol > 0.003:
            score += 1

        if roe < 0 and score >= 2:
            return "hold"

        if roe < -5 and score <= 1:
            return "exit"

        if roe > 5 and score >= 2:
            return "hold"

        if roe > 10 and score <= 1:
            return "exit"

        if roe > 25:
            return "exit"

        return "hold"

    except:
        return "hold"

# ===== TRADE =====
def open_trade(sym, direction, score):
    try:
        if len(trade_state) >= MAX_POSITIONS:
            return

        size = ai_risk_size(sym, score)
        if len(trade_state) == 1:
            size *= 0.7

        ticker = exchange.fetch_ticker(sym)
        spread = (ticker["ask"]-ticker["bid"]) / ticker["last"]

        if spread > MAX_SPREAD:
            return

        price = ticker["last"]
        qty = format_qty(sym, price, size)

        if qty <= 0:
            return

        exchange.set_leverage(LEV, sym)
        side = "buy" if direction=="long" else "sell"

        exchange.create_market_order(sym, side, qty)

        trade_state[sym] = {
            "entry": price,
            "direction": direction,
            "time": time.time(),
            "partial_done": False,
            "adds": 0
        }

        bot.send_message(CHAT_ID, f"🚀 {sym} {direction} AI")

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

                state = trade_state[sym]
                price = exchange.fetch_ticker(sym)["last"]

                entry = state["entry"]
                direction = state["direction"]
                side = "sell" if direction=="long" else "buy"

                roe = ((price-entry)/entry*100)*LEV if direction=="long" else ((entry-price)/entry*100)*LEV

                # ===== PARTIAL =====
                if not state["partial_done"] and roe > 10:
                    exchange.create_market_order(sym, side, qty*0.5, params={"reduceOnly": True})
                    state["partial_done"] = True
                    bot.send_message(CHAT_ID, f"💰 PARTIAL {sym}")

                # ===== PYRAMID =====
                if state["adds"] < 2 and roe > 8:
                    exchange.create_market_order(sym, "buy" if direction=="long" else "sell", qty*0.5)
                    state["adds"] += 1
                    bot.send_message(CHAT_ID, f"📈 ADD {sym}")

                # ===== AI EXIT =====
                decision = ai_manage(sym, price, entry, direction)

                if decision == "exit":
                    exchange.create_market_order(sym, side, qty, params={"reduceOnly": True})
                    update_stats(sym, roe)
                    trade_state.pop(sym)
                    bot.send_message(CHAT_ID, f"🧠 AI CLOSE {sym}")

            time.sleep(5)

        except Exception as e:
            print("MANAGE:", e)
            time.sleep(6)

# ===== SCANNER =====
def scanner():
    while True:
        try:
            for sym in get_symbols():
                direction, score = signal(sym)
                if direction:
                    open_trade(sym, direction, score)

            time.sleep(SCAN_DELAY)
        except:
            time.sleep(10)

# ===== START =====
print("ULTIMATE AI BOT STARTED")

sync_positions()

threading.Thread(target=manage, daemon=True).start()
threading.Thread(target=scanner, daemon=True).start()
threading.Thread(target=bot.infinity_polling, daemon=True).start()

bot.send_message(CHAT_ID, "🔥 FINAL AI BOT AKTİF")

while True:
    time.sleep(60)
