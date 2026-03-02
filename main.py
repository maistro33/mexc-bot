import os
import time
import ccxt
import telebot
import threading
from datetime import datetime, timezone, timedelta

# ================= SETTINGS =================
LEV = 7
MARGIN = 7

MIN_VOLUME = 8_000_000
TOP_COINS = 80
SPREAD_LIMIT = 0.0015

MAX_TOTAL_POS = 1

SCALP_TP = 0.007   # %0.7
SCALP_SL = 0.005   # %0.5

VOL_FILTER = 0.005  # Son 5 mumda en az %0.5 hareket

COOLDOWN_MIN = 20

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

def cooldown_active(sym):
    return sym in cooldowns and now() < cooldowns[sym]

def set_cooldown(sym):
    cooldowns[sym] = now() + timedelta(minutes=COOLDOWN_MIN)

def spread_ok(sym):
    try:
        t = exchange.fetch_ticker(sym)
        if not t["ask"] or not t["bid"] or not t["last"]:
            return False
        return (t["ask"] - t["bid"]) / t["last"] <= SPREAD_LIMIT
    except:
        return False

def get_symbols():
    try:
        tickers = exchange.fetch_tickers()
        filtered = []
        for sym, data in tickers.items():
            if ":USDT" not in sym:
                continue
            if safe(data.get("quoteVolume")) >= MIN_VOLUME:
                filtered.append((sym, data["quoteVolume"]))
        filtered.sort(key=lambda x: x[1], reverse=True)
        return [x[0] for x in filtered[:TOP_COINS]]
    except:
        return []

def get_position_qty(sym):
    try:
        pos = exchange.fetch_positions([sym])
        if not pos:
            return 0
        return safe(pos[0].get("contracts"))
    except:
        return 0

# ================= MOMENTUM + VOLATILITY =================
def momentum_signal(sym):
    try:
        m5 = exchange.fetch_ohlcv(sym, "5m", limit=10)
        if not m5 or len(m5) < 10:
            return None

        highs = [c[2] for c in m5]
        lows = [c[3] for c in m5]
        closes = [c[4] for c in m5]

        # ---- VOLATILITY FILTER ----
        range_pct = (max(highs[-5:]) - min(lows[-5:])) / closes[-1]
        if range_pct < VOL_FILTER:
            return None

        last = m5[-1]
        prev = m5[-2]

        body = abs(last[4] - last[1])
        avg = sum(abs(c[4] - c[1]) for c in m5[:-1]) / 9

        if body > avg * 1.8:
            if last[4] > prev[2]:
                return "long"
            if last[4] < prev[3]:
                return "short"

        return None

    except:
        return None

# ================= OPEN POSITION =================
def open_position(sym, direction):
    with state_lock:

        if len(positions_state) >= MAX_TOTAL_POS:
            return

        if sym in positions_state:
            return

        if cooldown_active(sym):
            return

        price = safe(exchange.fetch_ticker(sym)["last"])
        if price <= 0:
            return

        qty = (MARGIN * LEV) / price
        qty = float(exchange.amount_to_precision(sym, qty))

        if qty <= 0:
            return

        exchange.set_leverage(LEV, sym)
        side = "buy" if direction == "long" else "sell"
        exchange.create_market_order(sym, side, qty)

        if direction == "long":
            tp = price * (1 + SCALP_TP)
            sl = price * (1 - SCALP_SL)
        else:
            tp = price * (1 - SCALP_TP)
            sl = price * (1 + SCALP_SL)

        positions_state[sym] = {
            "direction": direction,
            "tp": tp,
            "sl": sl
        }

        bot.send_message(CHAT_ID, f"⚡ VOL SCALP {sym} {direction}")

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
                if (direction == "long" and price <= state["sl"]) or \
                   (direction == "short" and price >= state["sl"]):

                    side = "sell" if direction == "long" else "buy"
                    exchange.create_market_order(sym, side, qty, params={"reduceOnly": True})

                    with state_lock:
                        positions_state.pop(sym, None)

                    set_cooldown(sym)
                    bot.send_message(CHAT_ID, f"❌ STOP {sym}")
                    continue

                # TP
                if (direction == "long" and price >= state["tp"]) or \
                   (direction == "short" and price <= state["tp"]):

                    side = "sell" if direction == "long" else "buy"
                    exchange.create_market_order(sym, side, qty, params={"reduceOnly": True})

                    with state_lock:
                        positions_state.pop(sym, None)

                    set_cooldown(sym)
                    bot.send_message(CHAT_ID, f"💰 TP {sym}")

            time.sleep(2)

        except Exception as e:
            print("MANAGE ERROR:", e)
            time.sleep(2)

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

                direction = momentum_signal(sym)
                if direction:
                    open_position(sym, direction)

            time.sleep(6)

        except Exception as e:
            print("RUN ERROR:", e)
            time.sleep(6)

# ================= START =================
threading.Thread(target=manage, daemon=True).start()
threading.Thread(target=run, daemon=True).start()

bot.send_message(CHAT_ID, "⚡ VOLATİLİTE FİLTRELİ SCALP ENGINE AKTİF")
bot.infinity_polling(timeout=60, long_polling_timeout=60)
