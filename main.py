import os
import time
import ccxt
import telebot
import threading

# ===== AYARLAR =====
LEV = 10
MARGIN = 10
MIN_VOLUME = 5_000_000
TOP_COINS = 120
BUFFER_PCT = 0.0015
CRISIS_DROP_PCT = -5
TP_SPLIT = [0.4, 0.6]

# ===== TELEGRAM =====
TELE_TOKEN = os.getenv("TELE_TOKEN")
CHAT_ID = os.getenv("MY_CHAT_ID")
bot = telebot.TeleBot(TELE_TOKEN)

def safe_send(text):
    try:
        bot.send_message(CHAT_ID, text)
    except Exception as e:
        print("Telegram error:", e)

# ===== BITGET =====
exchange = ccxt.bitget({
    "apiKey": os.getenv("BITGET_API"),
    "secret": os.getenv("BITGET_SEC"),
    "password": os.getenv("BITGET_PASS"),
    "options": {"defaultType": "swap"},
    "enableRateLimit": True,
    "timeout": 30000
})

trade_state = {}
last_report = 0
symbols_cache = []
last_symbol_update = 0

# ===== HELPERS =====
def safe(x):
    try:
        return float(x)
    except:
        return 0.0

def get_candles(sym, tf, limit=100):
    try:
        return exchange.fetch_ohlcv(sym, tf, limit=limit)
    except:
        return []

def has_position():
    try:
        pos = exchange.fetch_positions()
        return any(safe(p.get("contracts")) > 0 for p in pos)
    except:
        return False

# ===== VOLATILITY FILTER =====
def volatility_filter(sym):
    h1 = get_candles(sym, "1h", 50)
    if len(h1) < 20:
        return False
    ranges = [(c[2] - c[3]) / c[4] for c in h1[-20:]]
    avg_range = sum(ranges) / len(ranges)
    return avg_range > 0.008

# ===== NEW COIN FILTER =====
def is_new_coin(sym):
    d = get_candles(sym, "1d", 200)
    return len(d) < 120

# ===== MOMENTUM FILTER =====
def momentum_filter(sym):
    h4 = get_candles(sym, "4h", 20)
    if len(h4) < 10:
        return False
    move = (h4[-1][4] - h4[-10][4]) / h4[-10][4]
    return abs(move) > 0.05

# ===== CRISIS =====
def crisis_mode():
    try:
        btc = exchange.fetch_ticker("BTC/USDT:USDT")
        last = safe(btc.get("last"))
        openp = safe(btc.get("open"))
        if openp == 0:
            return False
        pct = (last - openp) / openp * 100
        return pct <= CRISIS_DROP_PCT
    except:
        return False

# ===== SYMBOLS (CACHE 10 DK) =====
def get_symbols():
    global symbols_cache, last_symbol_update

    if time.time() - last_symbol_update < 600:
        return symbols_cache

    try:
        tickers = exchange.fetch_tickers()
        filtered = []

        for sym, data in tickers.items():
            if ":USDT" not in sym:
                continue

            vol = safe(data.get("quoteVolume"))
            if vol < MIN_VOLUME:
                continue

            if not volatility_filter(sym):
                continue

            if not momentum_filter(sym) and not is_new_coin(sym):
                continue

            filtered.append((sym, vol))

        filtered.sort(key=lambda x: x[1], reverse=True)
        symbols_cache = [x[0] for x in filtered[:TOP_COINS]]
        last_symbol_update = time.time()
        return symbols_cache

    except:
        return []

# ===== TREND =====
def get_direction(sym):
    d = get_candles(sym, "1d", 20)
    h4 = get_candles(sym, "4h", 20)

    if len(d) < 2 or len(h4) < 2:
        return None

    if d[-1][2] > d[-2][2] and h4[-1][2] > h4[-2][2]:
        return "long"

    if d[-1][3] < d[-2][3] and h4[-1][3] < h4[-2][3]:
        return "short"

    return None

# ===== SWEEP =====
def liquidity_sweep(sym, direction):
    h1 = get_candles(sym, "1h", 30)
    if len(h1) < 5:
        return False

    highs = [c[2] for c in h1]
    lows = [c[3] for c in h1]

    if direction == "long":
        return lows[-1] < min(lows[-4:-1])
    else:
        return highs[-1] > max(highs[-4:-1])

# ===== ENTRY =====
def entry_model(sym, direction):
    m15 = get_candles(sym, "15m", 60)
    if len(m15) < 20:
        return None

    h = [c[2] for c in m15]
    l = [c[3] for c in m15]
    o = [c[1] for c in m15]
    c_ = [c[4] for c in m15]

    body = abs(c_[-1] - o[-1])
    avg_body = sum(abs(c_[i] - o[i]) for i in range(-10, -1)) / 9

    if body < avg_body * 1.2:
        return None

    if direction == "long" and h[-3] < l[-1]:
        entry = (h[-3] + l[-1]) / 2
        swing_low = min(l[-15:])
        sl = swing_low * (1 - BUFFER_PCT)
        return {"entry": entry, "sl": sl}

    if direction == "short" and l[-3] > h[-1]:
        entry = (l[-3] + h[-1]) / 2
        swing_high = max(h[-15:])
        sl = swing_high * (1 + BUFFER_PCT)
        return {"entry": entry, "sl": sl}

    return None

# ===== MANAGER =====
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

                entry = safe(p["entryPrice"])
                direction = "long" if p["side"] == "long" else "short"
                price = safe(exchange.fetch_ticker(sym)["last"])

                sl = trade_state[sym]["sl"]
                risk = abs(entry - sl)

                tp1 = entry + risk if direction == "long" else entry - risk
                tp3 = entry + 3*risk if direction == "long" else entry - 3*risk

                # STOP
                if (direction == "long" and price <= sl) or \
                   (direction == "short" and price >= sl):

                    exchange.create_market_order(
                        sym,
                        "sell" if direction == "long" else "buy",
                        qty,
                        params={"reduceOnly": True}
                    )

                    trade_state.pop(sym, None)
                    safe_send(f"STOP {sym}")
                    continue

                # TP1
                if not trade_state[sym]["tp1"] and \
                   ((direction == "long" and price >= tp1) or
                    (direction == "short" and price <= tp1)):

                    part = qty * TP_SPLIT[0]

                    exchange.create_market_order(
                        sym,
                        "sell" if direction == "long" else "buy",
                        part,
                        params={"reduceOnly": True}
                    )

                    trade_state[sym]["tp1"] = True
                    trade_state[sym]["sl"] = entry
                    safe_send(f"TP1 {sym}")

                # TP3
                if trade_state[sym]["tp1"] and \
                   ((direction == "long" and price >= tp3) or
                    (direction == "short" and price <= tp3)):

                    qty = safe(p.get("contracts"))

                    exchange.create_market_order(
                        sym,
                        "sell" if direction == "long" else "buy",
                        qty,
                        params={"reduceOnly": True}
                    )

                    trade_state.pop(sym, None)
                    safe_send(f"TP3 {sym}")

            time.sleep(5)

        except:
            time.sleep(5)

# ===== RUN LOOP =====
def run():
    global last_report

    while True:
        try:
            symbols = get_symbols()
            if not symbols:
                time.sleep(30)
                continue

            if has_position():
                time.sleep(30)
                continue

            for sym in symbols:
                direction = get_direction(sym)
                if not direction:
                    continue

                if crisis_mode() and direction == "long" and not is_new_coin(sym):
                    continue

                if not liquidity_sweep(sym, direction):
                    continue

                setup = entry_model(sym, direction)
                if not setup:
                    continue

                exchange.set_leverage(LEV, sym)

                price = safe(exchange.fetch_ticker(sym)["last"])
                qty = (MARGIN * LEV) / price
                qty = float(exchange.amount_to_precision(sym, qty))

                if qty <= 0:
                    continue

                side = "buy" if direction == "long" else "sell"
                exchange.create_market_order(sym, side, qty)

                trade_state[sym] = {"sl": setup["sl"], "tp1": False}
                safe_send(f"{sym} {direction.upper()} AÇILDI")

                break

            time.sleep(30)

        except Exception as e:
            print("Run error:", e)
            time.sleep(30)

# ===== START =====
safe_send("HIBRIT SMC PRO STABLE AKTIF")

threading.Thread(target=manage, daemon=True).start()
threading.Thread(target=run, daemon=True).start()

bot.infinity_polling()
