import os
import time
import ccxt
import telebot
import threading
import random

# ===== CONFIG =====
LEV = 10
BASE_MARGIN = 3

TP_TRAIL = 0.005
SL_PCT = 0.012

MAX_POSITIONS = 4
SCAN_DELAY = 8

MIN_VOLUME = 2_000_000
MAX_SPREAD = 0.003

# ===== INIT =====
bot = telebot.TeleBot(os.getenv("TELE_TOKEN"))
CHAT_ID = os.getenv("MY_CHAT_ID")

exchange = ccxt.bitget({
    "apiKey": os.getenv("BITGET_API"),
    "secret": os.getenv("BITGET_SEC"),
    "password": os.getenv("BITGET_PASS"),
    "options": {"defaultType": "swap"},
    "enableRateLimit": True
})

markets = exchange.load_markets()
SYMBOLS = [s for s in markets if markets[s]["swap"] and "USDT" in s][:80]

trade_state = {}
trade_results = []
loss_streak = 0

# ===== UTILS =====
def safe(x):
    try:
        return float(x)
    except:
        return 0

def get_positions():
    try:
        return exchange.fetch_positions()
    except:
        return []

def get_qty(sym):
    for p in get_positions():
        if p["symbol"] == sym:
            return safe(p.get("contracts"))
    return 0

# ===== EDGE TRACK =====
def log_trade(entry, exit_price, direction):
    try:
        pnl = (exit_price - entry) / entry if direction == "long" else (entry - exit_price) / entry
        trade_results.append(pnl)
        if len(trade_results) > 50:
            trade_results.pop(0)
    except:
        pass

def send_stats():
    if not trade_results:
        return

    wins = [t for t in trade_results if t > 0]
    winrate = len(wins) / len(trade_results) * 100

    bot.send_message(
        CHAT_ID,
        f"📊 Trades: {len(trade_results)}\nWinrate: %{round(winrate,2)}"
    )

# ===== RISK =====
def update_loss(pnl):
    global loss_streak
    if pnl < 0:
        loss_streak += 1
    else:
        loss_streak = 0

def should_stop():
    return loss_streak >= 5

def get_size(score):
    size = BASE_MARGIN

    if loss_streak >= 3:
        size *= 0.5

    if score >= 3:
        size *= 1.2
    elif score == 1:
        size *= 0.7

    return size

# ===== MARKET =====
def detect_regime(sym):
    try:
        candles = exchange.fetch_ohlcv(sym, "5m", limit=20)
        closes = [c[4] for c in candles]

        change = (closes[-1] - closes[0]) / closes[0]

        if abs(change) > 0.01:
            return "trend"
        return "range"
    except:
        return None

def momentum(sym):
    try:
        ob = exchange.fetch_order_book(sym, limit=10)
        bid = sum([b[1] for b in ob["bids"]])
        ask = sum([a[1] for a in ob["asks"]])

        if bid > ask * 1.2:
            return "long"
        if ask > bid * 1.2:
            return "short"
    except:
        return None

def mean_reversion(sym):
    try:
        candles = exchange.fetch_ohlcv(sym, "5m", limit=15)
        closes = [c[4] for c in candles]

        avg = sum(closes) / len(closes)
        last = closes[-1]

        if last < avg * 0.995:
            return "long"
        if last > avg * 1.005:
            return "short"
    except:
        return None

# ===== CONFIDENCE =====
def confidence(sym):
    score = 0

    try:
        if exchange.fetch_ticker(sym)["quoteVolume"] > MIN_VOLUME:
            score += 1
    except:
        pass

    try:
        candles = exchange.fetch_ohlcv(sym, "1m", limit=3)
        change = (candles[-1][4] - candles[-2][4]) / candles[-2][4]
        if abs(change) > 0.002:
            score += 1
    except:
        pass

    try:
        if momentum(sym):
            score += 1
    except:
        pass

    return score

# ===== TRADE =====
def open_trade(sym, direction):
    try:
        if get_qty(sym) > 0:
            return

        ticker = exchange.fetch_ticker(sym)

        if ticker["quoteVolume"] < MIN_VOLUME:
            return

        spread = (ticker["ask"] - ticker["bid"]) / ticker["last"]
        if spread > MAX_SPREAD:
            return

        score = confidence(sym)

        if score < 1:
            return

        size = get_size(score)

        price = ticker["last"]
        qty = (size * LEV) / price
        qty = float(exchange.amount_to_precision(sym, qty))

        if qty <= 0:
            return

        exchange.set_leverage(LEV, sym)

        side = "buy" if direction == "long" else "sell"
        exchange.create_market_order(sym, side, qty)

        trade_state[sym] = {
            "entry": price,
            "direction": direction,
            "trail": price
        }

        bot.send_message(CHAT_ID, f"🚀 {sym} {direction} | score:{score}")

    except Exception as e:
        print("OPEN ERROR:", e)

# ===== MANAGER =====
def manage():
    while True:
        try:
            for p in get_positions():
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
                if (direction == "long" and price <= entry * (1 - SL_PCT)) or \
                   (direction == "short" and price >= entry * (1 + SL_PCT)):

                    exchange.create_market_order(sym, side, qty, params={"reduceOnly": True})

                    log_trade(entry, price, direction)
                    update_loss(-1)

                    trade_state.pop(sym)
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

                    log_trade(entry, price, direction)
                    update_loss(1 if price > entry else -1)

                    trade_state.pop(sym)

                    if len(trade_results) % 10 == 0:
                        send_stats()

            time.sleep(5)

        except Exception as e:
            print("MANAGE ERROR:", e)
            time.sleep(6)

# ===== SCANNER =====
def scanner():
    while True:
        try:
            if should_stop():
                time.sleep(30)
                continue

            random.shuffle(SYMBOLS)

            active = sum(1 for p in get_positions() if safe(p.get("contracts")) > 0)

            if active >= MAX_POSITIONS:
                time.sleep(SCAN_DELAY)
                continue

            for sym in SYMBOLS:
                if get_qty(sym) > 0:
                    continue

                regime = detect_regime(sym)

                if regime == "trend":
                    signal = momentum(sym)
                else:
                    signal = mean_reversion(sym)

                if signal:
                    open_trade(sym, signal)
                    break

            time.sleep(SCAN_DELAY)

        except Exception as e:
            print("SCAN ERROR:", e)
            time.sleep(10)

# ===== START =====
print("SMART BOT STARTED")

threading.Thread(target=manage, daemon=True).start()
threading.Thread(target=scanner, daemon=True).start()
threading.Thread(target=bot.infinity_polling, daemon=True).start()

while True:
    time.sleep(60)
