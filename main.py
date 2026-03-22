import os
import time
import ccxt
import telebot
import threading
import random

LEV = 10
MARGIN = 3

MAX_POSITIONS = 4
SL_PCT = 0.025
TP_TRAIL = 0.005

MIN_VOLUME = 1_000_000
MAX_SPREAD = 0.003
SCAN_DELAY = 5

loss_streak = 0
trade_state = {}
cooldown = {}

bot = telebot.TeleBot(os.getenv("TELE_TOKEN"))
CHAT_ID = os.getenv("MY_CHAT_ID")

exchange = ccxt.bitget({
    "apiKey": os.getenv("BITGET_API"),
    "secret": os.getenv("BITGET_SEC"),
    "password": os.getenv("BITGET_PASS"),
    "options": {"defaultType": "swap"},
    "enableRateLimit": True
})

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

# ===== AI SCANNER =====
def get_hot_symbols():
    try:
        tickers = exchange.fetch_tickers()
        candidates = []

        for sym, data in tickers.items():
            if "USDT" not in sym:
                continue

            if ":USDT" not in sym:
                continue

            vol = data.get("quoteVolume", 0)
            change = abs(data.get("percentage", 0))

            if vol < MIN_VOLUME:
                continue

            score = change * 2 + (vol / 1_000_000)

            candidates.append((sym, score))

        candidates.sort(key=lambda x: x[1], reverse=True)

        top = [c[0] for c in candidates[:20]]
        random.shuffle(top)

        return top[:10]

    except:
        return []

# ===== ANALYSIS =====
def multi_tf_signal(sym):
    try:
        h1 = exchange.fetch_ohlcv(sym, "1h", limit=20)
        m5 = exchange.fetch_ohlcv(sym, "5m", limit=20)

        h1_close = [c[4] for c in h1]
        m5_close = [c[4] for c in m5]

        trend = "long" if h1_close[-1] > sum(h1_close[-10:])/10 else "short"
        momentum = "long" if m5_close[-1] > m5_close[-3] else "short"

        if trend == momentum:
            return trend

        return None
    except:
        return None

def orderbook_pressure(sym):
    try:
        ob = exchange.fetch_order_book(sym, limit=20)
        bid = sum([b[1] for b in ob["bids"]])
        ask = sum([a[1] for a in ob["asks"]])

        if bid > ask * 1.5:
            return "long"
        if ask > bid * 1.5:
            return "short"
        return None
    except:
        return None

def ai_confidence(sym, direction):
    score = 0

    if multi_tf_signal(sym) == direction:
        score += 2

    if orderbook_pressure(sym) == direction:
        score += 1

    try:
        candles = exchange.fetch_ohlcv(sym,"1m",limit=3)
        change = (candles[-1][4]-candles[-2][4])/candles[-2][4]
        if abs(change) > 0.002:
            score += 1
    except:
        pass

    return score

# ===== RISK =====
def update_loss(pnl):
    global loss_streak
    loss_streak = loss_streak+1 if pnl < 0 else 0

def should_stop():
    return loss_streak >= 6

def get_size(score):
    size = MARGIN

    if loss_streak >= 3:
        size *= 0.5

    if score >= 4:
        size *= 1.3
    elif score <= 2:
        size *= 0.7

    return size

# ===== TRADE =====
def open_trade(sym, direction):
    try:
        if should_stop():
            return

        if get_qty(sym) > 0:
            return

        ticker = exchange.fetch_ticker(sym)

        spread = (ticker["ask"] - ticker["bid"]) / ticker["last"]
        if spread > MAX_SPREAD:
            return

        score = ai_confidence(sym, direction)

        if score < 2:
            return

        size = get_size(score)

        price = ticker["last"]
        qty = (size * LEV) / price
        qty = float(exchange.amount_to_precision(sym, qty))

        exchange.set_leverage(LEV, sym)

        side = "buy" if direction == "long" else "sell"
        exchange.create_market_order(sym, side, qty)

        trade_state[sym] = {
            "entry": price,
            "direction": direction,
            "trail": price
        }

        bot.send_message(CHAT_ID, f"🚀 AI {sym} {direction} score:{score}")

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

                side = "sell" if direction=="long" else "buy"

                # SL
                if (direction=="long" and price <= entry*(1-SL_PCT)) or \
                   (direction=="short" and price >= entry*(1+SL_PCT)):

                    exchange.create_market_order(sym,side,qty,params={"reduceOnly":True})
                    update_loss(-1)
                    trade_state.pop(sym)
                    bot.send_message(CHAT_ID,f"🛑 SL {sym}")
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

                if (direction=="long" and price <= state["trail"]) or \
                   (direction=="short" and price >= state["trail"]):

                    exchange.create_market_order(sym,side,qty,params={"reduceOnly":True})
                    update_loss(1 if price>entry else -1)
                    trade_state.pop(sym)
                    bot.send_message(CHAT_ID,f"🏁 EXIT {sym}")

            time.sleep(4)

        except Exception as e:
            print("MANAGE:", e)
            time.sleep(6)

# ===== SCANNER =====
def scanner():
    while True:
        try:
            if should_stop():
                time.sleep(30)
                continue

            symbols = get_hot_symbols()

            positions = exchange.fetch_positions()
            active = sum(1 for p in positions if safe(p.get("contracts")) > 0)

            if active >= MAX_POSITIONS:
                time.sleep(SCAN_DELAY)
                continue

            for sym in symbols:

                if get_qty(sym) > 0:
                    continue

                signal = multi_tf_signal(sym)

                if not signal:
                    continue

                open_trade(sym, signal)
                break

            time.sleep(SCAN_DELAY)

        except Exception as e:
            print("SCAN:", e)
            time.sleep(10)

# ===== START =====
print("SCANNER AI BOT STARTED")

threading.Thread(target=manage, daemon=True).start()
threading.Thread(target=scanner, daemon=True).start()
threading.Thread(target=bot.infinity_polling, daemon=True).start()

bot.send_message(CHAT_ID, "🤖 SCANNER AI BOT AKTİF")

while True:
    time.sleep(60)
