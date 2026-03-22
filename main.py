import os
import time
import ccxt
import telebot
import threading
import random

# ===== SAFE CONFIG =====
LEV = 10
MARGIN = 3
MAX_POSITIONS = 2

SL_PCT = 0.02
TP_TRAIL = 0.01

MIN_VOLUME = 2000000
MAX_SPREAD = 0.003
SCAN_DELAY = 8

loss_streak = 0

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
    try: return float(x)
    except: return 0

def get_qty(sym):
    try:
        pos = exchange.fetch_positions([sym])
        if not pos:
            return 0
        return safe(pos[0]["contracts"])
    except:
        return 0

# ===== 🚫 BAD COIN FILTER =====
def blacklist_filter(sym):
    bad_words = [
        "1000", "UP", "DOWN", "BULL", "BEAR",
        "RDNT", "LEVER", "ETF"
    ]

    for w in bad_words:
        if w in sym.upper():
            return False

    return True

# ===== SMART SCANNER =====
def get_hot_symbols():
    try:
        tickers = exchange.fetch_tickers()
        candidates = []

        for sym, data in tickers.items():

            if "USDT" not in sym:
                continue
            if ":USDT" not in sym:
                continue

            if not blacklist_filter(sym):
                continue  # 🔥 BURASI ÖNEMLİ

            vol = data.get("quoteVolume", 0)
            change = abs(data.get("percentage", 0))

            if vol < MIN_VOLUME:
                continue

            score = change * 2 + (vol / 1000000)
            candidates.append((sym, score))

        candidates.sort(key=lambda x: x[1], reverse=True)

        top = [c[0] for c in candidates[:15]]
        random.shuffle(top)

        return top[:5]

    except:
        return []

# ===== ANALYSIS =====
def should_trade(sym):
    try:
        h1 = exchange.fetch_ohlcv(sym, "1h", limit=20)
        m5 = exchange.fetch_ohlcv(sym, "5m", limit=10)

        h1_close = [c[4] for c in h1]
        m5_close = [c[4] for c in m5]

        trend_up = h1_close[-1] > sum(h1_close[-10:]) / 10
        momentum = (m5_close[-1] - m5_close[-3]) / m5_close[-3]

        high = max([c[2] for c in m5])
        low = min([c[3] for c in m5])
        vol = (high - low) / low

        # 🔥 STRONG FILTER
        if abs(momentum) < 0.005:
            return None

        if vol < 0.007:
            return None

        if trend_up and momentum > 0:
            return "long"

        if not trend_up and momentum < 0:
            return "short"

        return None

    except:
        return None

# ===== RISK =====
def update_loss(pnl):
    global loss_streak
    loss_streak = loss_streak+1 if pnl < 0 else 0

def should_stop():
    return loss_streak >= 4

# ===== TRADE =====
def open_trade(sym, direction):
    try:
        if should_stop():
            return

        if get_qty(sym) > 0:
            return

        if sym in cooldown:
            if time.time() - cooldown[sym] < 600:
                return

        ticker = exchange.fetch_ticker(sym)

        spread = (ticker["ask"] - ticker["bid"]) / ticker["last"]
        if spread > MAX_SPREAD:
            return

        price = ticker["last"]
        qty = (MARGIN * LEV) / price
        qty = float(exchange.amount_to_precision(sym, qty))

        if qty <= 0:
            return

        exchange.set_leverage(LEV, sym)

        side = "buy" if direction == "long" else "sell"
        exchange.create_market_order(sym, side, qty)

        trade_state[sym] = {
            "entry": price,
            "direction": direction,
            "trail": price,
            "time": time.time()
        }

        cooldown[sym] = time.time()

        bot.send_message(CHAT_ID, f"🧠 CLEAN {sym} {direction}")

    except Exception as e:
        print("OPEN:", e)

# ===== MANAGER =====
def manage():
    while True:
        try:
            pos = exchange.fetch_positions()

            for p in pos:
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

                side = "sell" if direction == "long" else "buy"

                # SL
                if (direction == "long" and price <= entry*(1-SL_PCT)) or \
                   (direction == "short" and price >= entry*(1+SL_PCT)):

                    exchange.create_market_order(sym, side, qty, params={"reduceOnly": True})
                    update_loss(-1)
                    trade_state.pop(sym)
                    bot.send_message(CHAT_ID, f"🛑 SL {sym}")
                    continue

                # MIN HOLD
                if time.time() - state["time"] < 20:
                    continue

                # PROFIT ONLY
                in_profit = (price > entry) if direction=="long" else (price < entry)

                if not in_profit:
                    continue

                # TRAILING
                if direction == "long":
                    new_trail = price * (1 - TP_TRAIL)
                    if new_trail > state["trail"]:
                        state["trail"] = new_trail
                else:
                    new_trail = price * (1 + TP_TRAIL)
                    if new_trail < state["trail"]:
                        state["trail"] = new_trail

                # EXIT
                if (direction == "long" and price <= state["trail"]) or \
                   (direction == "short" and price >= state["trail"]):

                    exchange.create_market_order(sym, side, qty, params={"reduceOnly": True})
                    update_loss(1 if price > entry else -1)
                    trade_state.pop(sym)
                    bot.send_message(CHAT_ID, f"🏁 EXIT {sym}")

            time.sleep(5)

        except Exception as e:
            print("MANAGE:", e)
            time.sleep(6)

# ===== SCANNER =====
def scanner():
    while True:
        try:
            if should_stop():
                time.sleep(60)
                continue

            symbols = get_hot_symbols()

            pos = exchange.fetch_positions()
            active = sum(1 for p in pos if safe(p.get("contracts")) > 0)

            if active >= MAX_POSITIONS:
                time.sleep(SCAN_DELAY)
                continue

            for sym in symbols:

                if get_qty(sym) > 0:
                    continue

                signal = should_trade(sym)

                if not signal:
                    continue

                open_trade(sym, signal)
                break

            time.sleep(SCAN_DELAY)

        except Exception as e:
            print("SCAN:", e)
            time.sleep(10)

# ===== START =====
print("CLEAN SAFE BOT STARTED")

threading.Thread(target=manage, daemon=True).start()
threading.Thread(target=scanner, daemon=True).start()
threading.Thread(target=bot.infinity_polling, daemon=True).start()

bot.send_message(CHAT_ID, "🧠 CLEAN SAFE BOT AKTİF")

while True:
    time.sleep(60)
