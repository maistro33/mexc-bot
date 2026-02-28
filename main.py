import os
import time
import ccxt
import telebot
import threading

# ===== SETTINGS =====
LEV = 10
MARGIN = 10
MIN_VOLUME = 5_000_000
TOP_COINS = 80
BUFFER_PCT = 0.0015
CRISIS_DROP_PCT = -5
TP_SPLIT = [0.4, 0.3, 0.3]

# ===== TELEGRAM =====
TELE_TOKEN = os.getenv("TELE_TOKEN")
CHAT_ID = os.getenv("MY_CHAT_ID")

bot = telebot.TeleBot(TELE_TOKEN)

# ===== BITGET =====
exchange = ccxt.bitget({
    "apiKey": os.getenv("BITGET_API"),
    "secret": os.getenv("BITGET_SEC"),
    "password": "Berfin33",
    "options": {"defaultType": "swap"},
    "enableRateLimit": True,
    "timeout": 30000
})

# ===== HELPERS =====
def safe(x):
    try:
        return float(x)
    except:
        return 0.0

def get_candles(sym, tf, limit=100):
    return exchange.fetch_ohlcv(sym, tf, limit=limit)

def has_position():
    pos = exchange.fetch_positions()
    return any(safe(p.get("contracts")) > 0 for p in pos)

# ===== CRISIS MODE =====
def crisis_mode():
    try:
        btc = exchange.fetch_ticker("BTC/USDT:USDT")
        pct = safe(btc.get("percentage"))
        d = get_candles("BTC/USDT:USDT", "1d", 5)
        lows = [c[3] for c in d]
        lower_low = lows[-1] < lows[-2]
        return pct <= CRISIS_DROP_PCT and lower_low
    except:
        return False

# ===== MARKET FILTER =====
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

# ===== DIRECTION =====
def get_direction(sym):
    d = get_candles(sym, "1d", 20)
    h4 = get_candles(sym, "4h", 20)

    if d[-1][2] > d[-2][2] and h4[-1][2] > h4[-2][2]:
        return "long"

    if d[-1][3] < d[-2][3] and h4[-1][3] < h4[-2][3]:
        return "short"

    return None

# ===== LIQUIDITY =====
def liquidity_sweep(sym, direction):
    h1 = get_candles(sym, "1h", 30)
    highs = [c[2] for c in h1]
    lows = [c[3] for c in h1]

    if direction == "long":
        return lows[-1] < min(lows[:-2])
    else:
        return highs[-1] > max(highs[:-2])

# ===== DISCIPLINED ENTRY =====
def entry_model(sym, direction):
    m15 = get_candles(sym, "15m", 60)
    h = [c[2] for c in m15]
    l = [c[3] for c in m15]
    o = [c[1] for c in m15]
    c_ = [c[4] for c in m15]

    body = abs(c_[-1] - o[-1])
    avg_body = sum(abs(c_[i] - o[i]) for i in range(-10, -1)) / 9

    if body < avg_body * 1.5:
        return None

    if direction == "long" and h[-3] < l[-1]:
        entry = (h[-3] + l[-1]) / 2
        swing_low = min(l[-15:])
        sl = swing_low - (swing_low * BUFFER_PCT)
        return {"entry": entry, "sl": sl}

    if direction == "short" and l[-3] > h[-1]:
        entry = (l[-3] + h[-1]) / 2
        swing_high = max(h[-15:])
        sl = swing_high + (swing_high * BUFFER_PCT)
        return {"entry": entry, "sl": sl}

    return None

# ===== AGGRESSIVE ENTRY =====
def aggressive_entry(sym, direction):
    if crisis_mode():
        return None

    m15 = get_candles(sym, "15m", 20)
    o = [c[1] for c in m15]
    h = [c[2] for c in m15]
    l = [c[3] for c in m15]
    c_ = [c[4] for c in m15]
    v = [c[5] for c in m15]

    body = abs(c_[-1] - o[-1])
    avg_body = sum(abs(c_[i] - o[i]) for i in range(-11, -1)) / 10
    avg_vol = sum(v[-11:-1]) / 10

    if body < avg_body * 2.5:
        return None

    if v[-1] < avg_vol * 2:
        return None

    if direction == "long":
        entry = l[-1] + (h[-1] - l[-1]) * 0.3
        sl = l[-1] - (l[-1] * BUFFER_PCT)
    else:
        entry = h[-1] - (h[-1] - l[-1]) * 0.3
        sl = h[-1] + (h[-1] * BUFFER_PCT)

    return {"entry": entry, "sl": sl}

# ===== TRADE STATE =====
trade_state = {}

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
                entry = safe(p["entryPrice"])
                direction = "long" if p["side"] == "long" else "short"
                price = safe(exchange.fetch_ticker(sym)["last"])

                sl = trade_state[sym]["sl"]
                risk = abs(entry - sl)

                tp1 = entry + risk if direction == "long" else entry - risk
                tp2 = entry + 2*risk if direction == "long" else entry - 2*risk
                tp3 = entry + 3*risk if direction == "long" else entry - 3*risk

                if (direction == "long" and price <= sl) or \
                   (direction == "short" and price >= sl):
                    exchange.create_market_order(
                        sym,
                        "sell" if direction == "long" else "buy",
                        qty,
                        params={"reduceOnly": True}
                    )
                    trade_state.pop(sym, None)
                    bot.send_message(CHAT_ID, f"❌ STOP {sym}")
                    continue

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
                    bot.send_message(CHAT_ID, f"💰 TP1 {sym}")

                if trade_state[sym]["tp2"] and \
                   ((direction == "long" and price >= tp3) or
                    (direction == "short" and price <= tp3)):
                    exchange.create_market_order(
                        sym,
                        "sell" if direction == "long" else "buy",
                        qty,
                        params={"reduceOnly": True}
                    )
                    trade_state.pop(sym, None)
                    bot.send_message(CHAT_ID, f"🏆 TP3 {sym}")

            time.sleep(5)
        except Exception as e:
            bot.send_message(CHAT_ID, f"MANAGER ERROR: {e}")
            time.sleep(5)

# ===== ENTRY LOOP =====
def run():
    while True:
        try:
            if has_position():
                time.sleep(20)
                continue

            symbols = get_symbols()
            CRISIS = crisis_mode()

            for sym in symbols:

                direction = get_direction(sym)
                if not direction:
                    continue

                if CRISIS and direction == "long":
                    continue

                if not liquidity_sweep(sym, direction):
                    continue

                setup = aggressive_entry(sym, direction)

                if not setup:
                    setup = entry_model(sym, direction)

                if not setup:
                    continue

                exchange.set_leverage(LEV, sym)

                price = safe(exchange.fetch_ticker(sym)["last"])
                qty = (MARGIN * LEV) / price
                qty = float(exchange.amount_to_precision(sym, qty))

                side = "buy" if direction == "long" else "sell"

                exchange.create_market_order(sym, side, qty)

                trade_state[sym] = {
                    "sl": setup["sl"],
                    "tp1": False,
                    "tp2": False
                }

                bot.send_message(CHAT_ID, f"📈 {sym} {direction.upper()} AÇILDI")

                break

            time.sleep(30)
        except Exception as e:
            bot.send_message(CHAT_ID, f"RUN ERROR: {e}")
            time.sleep(30)

# ===== START =====
bot.send_message(CHAT_ID, "🚀 HIBRIT SMC PRO AKTİF")

threading.Thread(target=manage, daemon=True).start()
threading.Thread(target=run, daemon=True).start()

bot.infinity_polling()
