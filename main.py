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

MIN_VOLUME = 8_000_000
TOP_COINS = 80
SPREAD_LIMIT = 0.0015

MAX_TOTAL_POS = 2
MAX_TREND = 1
MAX_SMALL = 1

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
state_lock = threading.Lock()

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
    return (t["ask"] - t["bid"]) / t["last"] <= SPREAD_LIMIT

def cooldown_active(sym):
    return sym in cooldowns and now() < cooldowns[sym]

def set_cooldown(sym, minutes):
    cooldowns[sym] = now() + timedelta(minutes=minutes)

def get_symbols():
    tickers = exchange.fetch_tickers()
    filtered = []
    for sym, data in tickers.items():
        if ":USDT" not in sym:
            continue
        if safe(data.get("quoteVolume")) >= MIN_VOLUME:
            filtered.append((sym, data["quoteVolume"]))
    filtered.sort(key=lambda x: x[1], reverse=True)
    return [x[0] for x in filtered[:TOP_COINS]]

def get_position_qty(sym):
    pos = exchange.fetch_positions([sym])
    if not pos:
        return 0
    return safe(pos[0].get("contracts"))

# ================= TREND FILTER =================
def trend_direction(sym):
    h4 = exchange.fetch_ohlcv(sym, "4h", limit=60)
    closes = [c[4] for c in h4]
    highs = [c[2] for c in h4]
    lows = [c[3] for c in h4]

    ema = sum(closes[-50:]) / 50

    if closes[-1] > ema and closes[-1] > highs[-2]:
        return "long"
    if closes[-1] < ema and closes[-1] < lows[-2]:
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
    with state_lock:

        trend_count = sum(1 for p in positions_state.values() if p["mode"] == "trend")
        small_count = sum(1 for p in positions_state.values() if p["mode"] in ["scalp","reversion"])

        if len(positions_state) >= MAX_TOTAL_POS:
            return
        if mode == "trend" and trend_count >= MAX_TREND:
            return
        if mode in ["scalp","reversion"] and small_count >= MAX_SMALL:
            return
        if sym in positions_state:
            return
        if cooldown_active(sym):
            return

        price = safe(exchange.fetch_ticker(sym)["last"])
        margin = TREND_MARGIN if mode == "trend" else SMALL_MARGIN
        qty = (margin * LEV) / price
        qty = float(exchange.amount_to_precision(sym, qty))

        if qty <= 0:
            return

        exchange.set_leverage(LEV, sym)
        side = "buy" if direction == "long" else "sell"
        exchange.create_market_order(sym, side, qty)

        positions_state[sym] = {
            "mode": mode,
            "direction": direction,
            "sl": price * 0.99 if direction=="long" else price * 1.01,
            "tp": price * 1.01 if direction=="long" else price * 0.99
        }

        bot.send_message(CHAT_ID, f"🚀 {mode.upper()} {sym} {direction}")

# ================= MANAGE =================
def manage():
    while True:
        try:
            with state_lock:
                symbols = list(positions_state.keys())

            for sym in symbols:
                state = positions_state.get(sym)
                if not state:
                    continue

                price = safe(exchange.fetch_ticker(sym)["last"])
                direction = state["direction"]
                qty = get_position_qty(sym)

                if qty <= 0:
                    with state_lock:
                        positions_state.pop(sym, None)
                    continue

                # STOP
                if (direction=="long" and price<=state["sl"]) or \
                   (direction=="short" and price>=state["sl"]):

                    side = "sell" if direction=="long" else "buy"
                    exchange.create_market_order(sym, side, qty, params={"reduceOnly": True})

                    with state_lock:
                        positions_state.pop(sym, None)

                    set_cooldown(sym, COOLDOWN_SMALL)
                    bot.send_message(CHAT_ID, f"❌ STOP {sym}")
                    continue

                # TP
                if (direction=="long" and price>=state["tp"]) or \
                   (direction=="short" and price<=state["tp"]):

                    side = "sell" if direction=="long" else "buy"
                    exchange.create_market_order(sym, side, qty, params={"reduceOnly": True})

                    with state_lock:
                        positions_state.pop(sym, None)

                    set_cooldown(sym, COOLDOWN_SMALL)
                    bot.send_message(CHAT_ID, f"💰 TP {sym}")

            time.sleep(3)

        except Exception as e:
            print("MANAGE ERROR:", e)
            time.sleep(3)

# ================= RUN =================
def run():
    while True:
        try:
            symbols = get_symbols()

            for sym in symbols:
                if cooldown_active(sym):
                    continue
                if not spread_ok(sym):
                    continue

                direction = trend_direction(sym)

                if direction:
                    open_position(sym, direction, "trend")

                if direction and momentum_signal(sym, direction):
                    open_position(sym, direction, "scalp")

                rev = reversion_signal(sym)
                if rev:
                    open_position(sym, rev, "reversion")

            time.sleep(8)

        except Exception as e:
            print("RUN ERROR:", e)
            time.sleep(8)

# ================= START =================
threading.Thread(target=manage, daemon=True).start()
threading.Thread(target=run, daemon=True).start()

bot.send_message(CHAT_ID, "🔥 3 MOTORLU STABİL ENGINE AKTİF (HARD LIMIT)")
bot.infinity_polling(timeout=60, long_polling_timeout=60)
