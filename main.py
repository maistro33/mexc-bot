import os
import time
import ccxt
import telebot
import threading
from datetime import datetime, timezone

# ================= SETTINGS =================
LEV = 5
MARGIN = 4
MAX_DAILY_TRADES = 3
MIN_VOLUME = 8_000_000
TOP_COINS = 120

TP1_RATIO = 0.30
TP2_RATIO = 0.40

TP1_PCT = 0.008
TP2_PCT = 0.016
TRAIL_GAP = 0.007

COOLDOWN_MINUTES = 60

# ================= TELEGRAM =================
bot = telebot.TeleBot(os.getenv("TELE_TOKEN"))
CHAT_ID = os.getenv("MY_CHAT_ID")

# ================= EXCHANGE =================
exchange = ccxt.bitget({
    "apiKey": os.getenv("BITGET_API"),
    "secret": os.getenv("BITGET_SEC"),
    "password": os.getenv("BITGET_PASS"),
    "options": {"defaultType": "swap"},
    "enableRateLimit": True,
})

# ================= STATE =================
trade_state = {}
cooldown = {}
daily_trades = 0
current_day = datetime.now(timezone.utc).day


# ================= HELPERS =================
def safe(x):
    try:
        return float(x)
    except:
        return 0.0

def reset_daily():
    global daily_trades, current_day
    now_day = datetime.now(timezone.utc).day
    if now_day != current_day:
        daily_trades = 0
        current_day = now_day

def safe_api(call):
    try:
        return call()
    except Exception as e:
        print("API ERROR:", str(e)[:200])
        time.sleep(5)
        return None

def has_position():
    positions = safe_api(lambda: exchange.fetch_positions())
    if not positions:
        return False
    return any(safe(p.get("contracts")) > 0 for p in positions)

def get_position_qty(sym):
    pos = safe_api(lambda: exchange.fetch_positions([sym]))
    if not pos:
        return 0
    return safe(pos[0].get("contracts"))

def get_symbols():
    tickers = safe_api(lambda: exchange.fetch_tickers())
    if not tickers:
        return []

    filtered = []
    for sym, data in tickers.items():
        if ":USDT" not in sym:
            continue
        if safe(data.get("quoteVolume")) < MIN_VOLUME:
            continue
        filtered.append((sym, data["quoteVolume"]))

    filtered.sort(key=lambda x: x[1], reverse=True)
    return [x[0] for x in filtered[:TOP_COINS]]

# ================= TREND =================
def trend_direction(sym):
    data = safe_api(lambda: exchange.fetch_ohlcv(sym, "4h", limit=60))
    if not data:
        return None

    closes = [c[4] for c in data]
    ema = sum(closes[-50:]) / 50

    if closes[-1] > ema:
        return "long"
    if closes[-1] < ema:
        return "short"
    return None

# ================= RETEST =================
def retest_signal(sym, direction):
    data = safe_api(lambda: exchange.fetch_ohlcv(sym, "1h", limit=20))
    if not data:
        return False

    highs = [c[2] for c in data]
    lows = [c[3] for c in data]

    if direction == "long":
        return lows[-1] <= min(lows[-5:-1])
    else:
        return highs[-1] >= max(highs[-5:-1])

# ================= MOMENTUM =================
def momentum_confirm(sym, direction):
    data = safe_api(lambda: exchange.fetch_ohlcv(sym, "15m", limit=10))
    if not data:
        return False

    last = data[-1]
    prev = data[-2]

    body = abs(last[4] - last[1])
    avg = sum(abs(c[4] - c[1]) for c in data[:-1]) / 9

    if body > avg * 1.4:
        if direction == "long" and last[4] > prev[2]:
            return True
        if direction == "short" and last[4] < prev[3]:
            return True
    return False

# ================= ENTRY =================
def open_position(sym, direction):
    global daily_trades

    ticker = safe_api(lambda: exchange.fetch_ticker(sym))
    if not ticker:
        return

    price = safe(ticker["last"])
    qty = (MARGIN * LEV) / price
    qty = float(exchange.amount_to_precision(sym, qty))

    try:
        exchange.set_leverage(LEV, sym)
    except:
        pass

    side = "buy" if direction == "long" else "sell"
    safe_api(lambda: exchange.create_market_order(sym, side, qty))

    trade_state[sym] = {
        "direction": direction,
        "entry": price,
        "tp1_hit": False,
        "tp2_hit": False,
        "extreme": price
    }

    daily_trades += 1
    bot.send_message(CHAT_ID, f"🚀 {sym} {direction.upper()} AÇILDI")

# ================= MANAGE =================
def manage():
    while True:
        try:
            positions = safe_api(lambda: exchange.fetch_positions())
            if not positions:
                time.sleep(8)
                continue

            for p in positions:
                qty = safe(p.get("contracts"))
                if qty <= 0:
                    continue

                sym = p["symbol"]
                if sym not in trade_state:
                    continue

                state = trade_state[sym]
                direction = state["direction"]
                entry = state["entry"]

                ticker = safe_api(lambda: exchange.fetch_ticker(sym))
                if not ticker:
                    continue

                price = safe(ticker["last"])
                side = "sell" if direction == "long" else "buy"

                # extreme tracking
                if direction == "long" and price > state["extreme"]:
                    state["extreme"] = price
                if direction == "short" and price < state["extreme"]:
                    state["extreme"] = price

                # TP1
                if not state["tp1_hit"]:
                    if (direction == "long" and price >= entry * (1 + TP1_PCT)) or \
                       (direction == "short" and price <= entry * (1 - TP1_PCT)):
                        safe_api(lambda: exchange.create_market_order(sym, side, qty * TP1_RATIO, params={"reduceOnly": True}))
                        state["tp1_hit"] = True
                        bot.send_message(CHAT_ID, f"💰 TP1 {sym}")

                # TP2
                if state["tp1_hit"] and not state["tp2_hit"]:
                    if (direction == "long" and price >= entry * (1 + TP2_PCT)) or \
                       (direction == "short" and price <= entry * (1 - TP2_PCT)):
                        safe_api(lambda: exchange.create_market_order(sym, side, qty * TP2_RATIO, params={"reduceOnly": True}))
                        state["tp2_hit"] = True
                        bot.send_message(CHAT_ID, f"💰 TP2 {sym}")

                # TRAILING
                if state["tp2_hit"]:
                    if direction == "long":
                        if price <= state["extreme"] * (1 - TRAIL_GAP):
                            remaining = get_position_qty(sym)
                            safe_api(lambda: exchange.create_market_order(sym, side, remaining, params={"reduceOnly": True}))
                            trade_state.pop(sym)
                            cooldown[sym] = time.time()
                            bot.send_message(CHAT_ID, f"🏁 TRAILING EXIT {sym}")

                    if direction == "short":
                        if price >= state["extreme"] * (1 + TRAIL_GAP):
                            remaining = get_position_qty(sym)
                            safe_api(lambda: exchange.create_market_order(sym, side, remaining, params={"reduceOnly": True}))
                            trade_state.pop(sym)
                            cooldown[sym] = time.time()
                            bot.send_message(CHAT_ID, f"🏁 TRAILING EXIT {sym}")

            time.sleep(8)

        except Exception as e:
            print("MANAGE LOOP ERROR:", e)
            time.sleep(8)

# ================= RUN =================
def run():
    global daily_trades

    while True:
        try:
            reset_daily()

            if daily_trades >= MAX_DAILY_TRADES:
                time.sleep(60)
                continue

            if has_position():
                time.sleep(30)
                continue

            symbols = get_symbols()
            if not symbols:
                time.sleep(30)
                continue

            for sym in symbols:

                # cooldown
                if sym in cooldown:
                    elapsed = (time.time() - cooldown[sym]) / 60
                    if elapsed < COOLDOWN_MINUTES:
                        continue

                direction = trend_direction(sym)
                if not direction:
                    continue
                if not retest_signal(sym, direction):
                    continue
                if not momentum_confirm(sym, direction):
                    continue

                open_position(sym, direction)
                break

            time.sleep(40)

        except Exception as e:
            print("RUN LOOP ERROR:", e)
            time.sleep(40)

# ================= START =================
print("BOT STARTING...")

threading.Thread(target=manage, daemon=True).start()
threading.Thread(target=run, daemon=True).start()

bot.send_message(CHAT_ID, "🛡 STABLE PRO ENGINE AKTİF")
bot.infinity_polling()
