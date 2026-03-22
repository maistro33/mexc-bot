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

SL_PCT = 0.02
TP_TRAIL = 0.008

MIN_VOLUME = 2000000
MAX_SPREAD = 0.003
SCAN_DELAY = 8

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

def get_qty(sym):
    try:
        pos = exchange.fetch_positions([sym])
        if not pos:
            return 0
        return safe(pos[0]["contracts"])
    except:
        return 0

# ===== 🔥 SYNC (CRITICAL) =====
def sync_positions():
    try:
        positions = exchange.fetch_positions()

        for p in positions:
            qty = safe(p.get("contracts"))
            if qty <= 0:
                continue

            sym = p["symbol"]

            trade_state[sym] = {
                "entry": safe(p["entryPrice"]),
                "direction": "long" if p["side"] == "long" else "short",
                "trail": safe(p["entryPrice"]),
                "time": time.time()
            }

        print("SYNC DONE")

    except Exception as e:
        print("SYNC ERROR:", e)

# ===== FILTER =====
def blacklist(sym):
    bad = ["1000","UP","DOWN","BULL","BEAR","RDNT"]
    for b in bad:
        if b in sym.upper():
            return False
    return True

# ===== SCANNER =====
def get_symbols():
    try:
        tickers = exchange.fetch_tickers()
        arr = []

        for sym, data in tickers.items():

            if "USDT" not in sym or ":USDT" not in sym:
                continue

            if not blacklist(sym):
                continue

            vol = data.get("quoteVolume", 0)
            change = abs(data.get("percentage", 0))

            if vol < MIN_VOLUME:
                continue

            if change > 12:
                continue

            score = change * 2 + (vol / 1000000)
            arr.append((sym, score))

        arr.sort(key=lambda x: x[1], reverse=True)

        top = [x[0] for x in arr[:15]]
        random.shuffle(top)

        return top[:6]

    except:
        return []

# ===== ANALYSIS =====
def signal(sym):
    try:
        h1 = exchange.fetch_ohlcv(sym, "1h", limit=20)
        m5 = exchange.fetch_ohlcv(sym, "5m", limit=10)

        h1c = [c[4] for c in h1]
        m5c = [c[4] for c in m5]

        trend = h1c[-1] > sum(h1c[-10:])/10
        mom = (m5c[-1] - m5c[-3]) / m5c[-3]

        high = max([c[2] for c in m5])
        low = min([c[3] for c in m5])
        vol = (high - low) / low

        if abs(mom) < 0.005:
            return None, 0

        if vol < 0.007:
            return None, 0

        direction = None
        if trend and mom > 0:
            direction = "long"
        elif not trend and mom < 0:
            direction = "short"

        score = 0
        if direction:
            score += 2
        if abs(mom) > 0.008:
            score += 1
        if vol > 0.01:
            score += 1

        return direction, score

    except:
        return None, 0

# ===== QTY FIX =====
def format_qty(sym, qty):
    try:
        qty = float(exchange.amount_to_precision(sym, qty))
        market = exchange.market(sym)

        if market["precision"]["amount"] == 0:
            qty = int(qty)

        if qty < 1:
            return 0

        return qty
    except:
        return 0

# ===== TRADE =====
def open_trade(sym, direction, score):
    try:
        if get_qty(sym) > 0:
            return

        if sym in cooldown:
            if time.time() - cooldown[sym] < 600:
                return

        active = len(trade_state)

        if active >= MAX_POSITIONS:
            return

        if active == 0:
            size = BASE_MARGIN
        elif active == 1:
            if score < 3:
                return
            size = BASE_MARGIN * 0.7

        ticker = exchange.fetch_ticker(sym)

        spread = (ticker["ask"] - ticker["bid"]) / ticker["last"]
        if spread > MAX_SPREAD:
            return

        price = ticker["last"]
        raw_qty = (size * LEV) / price

        qty = format_qty(sym, raw_qty)

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

        bot.send_message(CHAT_ID, f"🚀 {sym} {direction} score:{score}")

    except Exception as e:
        print("OPEN:", e)

# ===== MANAGE =====
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

                    exchange.create_market_order(sym, side, qty, params={"reduceOnly": True})
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
                if (direction=="long" and price <= state["trail"]) or \
                   (direction=="short" and price >= state["trail"]):

                    exchange.create_market_order(sym, side, qty, params={"reduceOnly": True})
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
            symbols = get_symbols()

            for sym in symbols:
                direction, score = signal(sym)

                if not direction:
                    continue

                open_trade(sym, direction, score)

            time.sleep(SCAN_DELAY)

        except Exception as e:
            print("SCAN:", e)
            time.sleep(10)

# ===== START =====
print("ULTIMATE BOT STARTED")

sync_positions()  # 🔥 restart sonrası pozisyonları geri alır

threading.Thread(target=manage, daemon=True).start()
threading.Thread(target=scanner, daemon=True).start()
threading.Thread(target=bot.infinity_polling, daemon=True).start()

bot.send_message(CHAT_ID, "🧠 ULTIMATE BOT AKTİF")

while True:
    time.sleep(60)
