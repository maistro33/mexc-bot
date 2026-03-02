import os
import time
import ccxt
import telebot
import threading
from datetime import datetime, timezone, timedelta

# ================= SETTINGS =================
LEV = 10
TREND_MARGIN = 10
SMALL_MARGIN = 5

MIN_VOLUME = 20_000_000
TOP_COINS = 80
SPREAD_LIMIT = 0.0015

MAX_DAILY_STOPS = 3

SCALP_TP = 0.006
SCALP_SL = 0.005

REV_TP = 0.005
REV_SL = 0.004

COOLDOWN_TREND = 60
COOLDOWN_SMALL = 30

# ================= TELEGRAM =================
bot = telebot.TeleBot(os.getenv("TELE_TOKEN"), threaded=True)
CHAT_ID = os.getenv("MY_CHAT_ID")
bot.remove_webhook()

# ================= EXCHANGE =================
exchange = ccxt.bitget({
    "apiKey": os.getenv("BITGET_API"),
    "secret": os.getenv("BITGET_SEC"),
    "password": "Berfin33",
    "options": {"defaultType": "swap"},
    "enableRateLimit": True,
})

# ================= STATE =================
positions_state = {}
cooldowns = {}
daily_stops = 0
last_day = datetime.now(timezone.utc).day

# ================= HELPERS =================
def safe(x):
    try:
        return float(x)
    except:
        return 0.0

def now():
    return datetime.now(timezone.utc)

def spread_ok(sym):
    t = exchange.fetch_ticker(sym)
    sp = (t["ask"] - t["bid"]) / t["last"]
    return sp <= SPREAD_LIMIT

def cooldown_active(sym):
    if sym not in cooldowns:
        return False
    return now() < cooldowns[sym]

def set_cooldown(sym, minutes):
    cooldowns[sym] = now() + timedelta(minutes=minutes)

def get_symbols():
    tickers = exchange.fetch_tickers()
    filtered = []
    for sym, data in tickers.items():
        if ":USDT" not in sym:
            continue
        vol = safe(data.get("quoteVolume"))
        if vol >= MIN_VOLUME:
            filtered.append((sym, vol))
    filtered.sort(key=lambda x: x[1], reverse=True)
    return [x[0] for x in filtered[:TOP_COINS]]

def get_position_qty(sym):
    pos = exchange.fetch_positions([sym])
    if not pos:
        return 0
    return safe(pos[0].get("contracts"))

# ================= STRONG TREND FILTER =================
def trend_direction(sym):
    h4 = exchange.fetch_ohlcv(sym, "4h", limit=60)

    closes = [c[4] for c in h4]
    highs = [c[2] for c in h4]
    lows = [c[3] for c in h4]

    ema = sum(closes[-50:]) / 50

    # Structure break condition
    last_close = closes[-1]
    prev_high = highs[-2]
    prev_low = lows[-2]

    if last_close > ema and last_close > prev_high:
        return "long"

    if last_close < ema and last_close < prev_low:
        return "short"

    return None

# ================= MOMENTUM =================
def momentum_signal(sym, direction):
    m5 = exchange.fetch_ohlcv(sym, "5m", limit=10)
    last = m5[-1]
    prev = m5[-2]

    body = abs(last[4] - last[1])
    avg = sum(abs(c[4]-c[1]) for c in m5[:-1]) / 9

    if body > avg * 1.8:
        if direction == "long" and last[4] > prev[2]:
            return True
        if direction == "short" and last[4] < prev[3]:
            return True

    return False

# ================= REVERSION =================
def reversion_signal(sym):
    m5 = exchange.fetch_ohlcv(sym, "5m", limit=30)
    closes = [c[4] for c in m5]
    mean = sum(closes) / len(closes)
    dev = (closes[-1] - mean) / mean

    if dev > 0.01:
        return "short"

    if dev < -0.01:
        return "long"

    return None

# ================= OPEN POSITION =================
def open_position(sym, direction, mode):

    if sym in positions_state:
        return

    if cooldown_active(sym):
        return

    price = safe(exchange.fetch_ticker(sym)["last"])

    margin = TREND_MARGIN if mode == "trend" else SMALL_MARGIN
    notional = margin * LEV
    qty = notional / price
    qty = float(exchange.amount_to_precision(sym, qty))

    if qty <= 0:
        return

    exchange.set_leverage(LEV, sym)

    side = "buy" if direction == "long" else "sell"
    exchange.create_market_order(sym, side, qty)

    if mode == "trend":
        sl = price * 0.99 if direction=="long" else price * 1.01
        tp1 = price * 1.01 if direction=="long" else price * 0.99
        tp2 = price * 1.02 if direction=="long" else price * 0.98

        positions_state[sym] = {
            "mode": "trend",
            "direction": direction,
            "sl": sl,
            "tp1": tp1,
            "tp2": tp2,
            "tp1_hit": False
        }

    elif mode == "scalp":
        sl = price * (1-SCALP_SL) if direction=="long" else price*(1+SCALP_SL)
        tp = price * (1+SCALP_TP) if direction=="long" else price*(1-SCALP_TP)

        positions_state[sym] = {
            "mode": "scalp",
            "direction": direction,
            "sl": sl,
            "tp": tp
        }

    else:
        sl = price * (1-REV_SL) if direction=="long" else price*(1+REV_SL)
        tp = price * (1+REV_TP) if direction=="long" else price*(1-REV_TP)

        positions_state[sym] = {
            "mode": "reversion",
            "direction": direction,
            "sl": sl,
            "tp": tp
        }

    bot.send_message(CHAT_ID, f"🚀 {mode.upper()} {sym} {direction}")

# ================= MANAGE =================
def manage():
    global daily_stops, last_day

    while True:
        try:
            if now().day != last_day:
                daily_stops = 0
                last_day = now().day

            for sym in list(positions_state.keys()):
                state = positions_state[sym]
                price = safe(exchange.fetch_ticker(sym)["last"])
                direction = state["direction"]
                qty = get_position_qty(sym)

                if qty <= 0:
                    positions_state.pop(sym)
                    continue

                # STOP
                if (direction=="long" and price<=state["sl"]) or \
                   (direction=="short" and price>=state["sl"]):

                    side = "sell" if direction=="long" else "buy"
                    exchange.create_market_order(sym, side, qty, params={"reduceOnly": True})

                    daily_stops += 1
                    set_cooldown(sym, COOLDOWN_TREND if state["mode"]=="trend" else COOLDOWN_SMALL)
                    positions_state.pop(sym)
                    bot.send_message(CHAT_ID, f"❌ STOP {sym}")
                    continue

                # TREND TP1
                if state["mode"]=="trend" and not state["tp1_hit"]:
                    if (direction=="long" and price>=state["tp1"]) or \
                       (direction=="short" and price<=state["tp1"]):

                        close_qty = qty * 0.4
                        side = "sell" if direction=="long" else "buy"
                        exchange.create_market_order(sym, side, close_qty, params={"reduceOnly": True})

                        state["tp1_hit"] = True
                        state["sl"] = state["tp1"]

                        bot.send_message(CHAT_ID, f"💰 TP1 {sym}")

                # TREND TP2
                if state["mode"]=="trend" and state["tp1_hit"]:
                    if (direction=="long" and price>=state["tp2"]) or \
                       (direction=="short" and price<=state["tp2"]):

                        close_qty = qty * 0.5
                        side = "sell" if direction=="long" else "buy"
                        exchange.create_market_order(sym, side, close_qty, params={"reduceOnly": True})

                        state["sl"] = price * (0.995 if direction=="long" else 1.005)

                        bot.send_message(CHAT_ID, f"🚀 TP2 {sym}")

                # SCALP / REVERSION TP
                if state["mode"] in ["scalp", "reversion"]:
                    if (direction=="long" and price>=state["tp"]) or \
                       (direction=="short" and price<=state["tp"]):

                        side = "sell" if direction=="long" else "buy"
                        exchange.create_market_order(sym, side, qty, params={"reduceOnly": True})

                        set_cooldown(sym, COOLDOWN_SMALL)
                        positions_state.pop(sym)
                        bot.send_message(CHAT_ID, f"💰 TP {sym}")

            time.sleep(3)

        except Exception as e:
            print("MANAGE ERROR:", e)
            time.sleep(3)

# ================= RUN =================
def run():
    global daily_stops

    while True:
        try:
            if daily_stops >= MAX_DAILY_STOPS:
                time.sleep(30)
                continue

            symbols = get_symbols()

            trend_open = any(p["mode"]=="trend" for p in positions_state.values())
            small_open = any(p["mode"] in ["scalp","reversion"] for p in positions_state.values())

            for sym in symbols:

                if cooldown_active(sym):
                    continue

                if not spread_ok(sym):
                    continue

                if sym in positions_state:
                    continue

                direction = trend_direction(sym)

                # TREND SLOT
                if direction and not trend_open:
                    open_position(sym, direction, "trend")
                    trend_open = True
                    break

                # SMALL SLOT
                if not small_open and direction:
                    if momentum_signal(sym, direction):
                        open_position(sym, direction, "scalp")
                        small_open = True
                        break

                if not small_open:
                    rev = reversion_signal(sym)
                    if rev:
                        open_position(sym, rev, "reversion")
                        small_open = True
                        break

            time.sleep(8)

        except Exception as e:
            print("RUN ERROR:", e)
            time.sleep(8)

# ================= START =================
threading.Thread(target=manage, daemon=True).start()
threading.Thread(target=run, daemon=True).start()

bot.send_message(CHAT_ID, "🔥 3 MOTORLU STABİL ENGINE AKTİF")
bot.infinity_polling(timeout=60, long_polling_timeout=60)
