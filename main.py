import os
import time
import ccxt
import telebot
import threading

# ===== SETTINGS =====
SAFE_VOLUME = 2_000_000
SAFE_LEV = 10
SAFE_MARGIN = 5

TOP_COINS = 130
BUFFER_PCT = 0.0015

TP_SPLIT = [0.4, 0.3, 0.3]

TRAIL_START = 0.01
TRAIL_GAP = 0.015

# ===== TELEGRAM =====
bot = telebot.TeleBot(os.getenv("TELE_TOKEN"))
CHAT_ID = os.getenv("MY_CHAT_ID")

# ===== EXCHANGE =====
exchange = ccxt.bitget({
    "apiKey": os.getenv("BITGET_API"),
    "secret": os.getenv("BITGET_SEC"),
    "password": "Berfin33",
    "options": {"defaultType": "swap"},
    "enableRateLimit": True
})

exchange.load_markets()

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

# ===== SHORT PULLBACK SYSTEM =====
def short_pullback_entry(sym):
    m5 = get_candles(sym, "5m", 30)
    if len(m5) < 20:
        return None

    closes = [c[4] for c in m5]
    highs  = [c[2] for c in m5]
    lows   = [c[3] for c in m5]

    drop = (highs[-10] - lows[-1]) / highs[-10]
    if drop < 0.04:
        return None

    bounce = (closes[-1] - lows[-3]) / lows[-3]
    if bounce < 0.01:
        return None

    last = m5[-1]
    prev = m5[-2]

    if last[4] < last[1] and prev[4] > prev[1]:
        entry = last[4]
        sl = max(highs[-10:]) * (1 + BUFFER_PCT)

        return {"entry": entry, "sl": sl}

    return None

# ===== MARKET =====
def get_symbols(volume):
    try:
        tickers = exchange.fetch_tickers()
        filtered = []
        for sym, data in tickers.items():
            if ":USDT" not in sym:
                continue
            vol = safe(data.get("quoteVolume"))
            if vol >= volume:
                filtered.append((sym, vol))
        filtered.sort(key=lambda x: x[1], reverse=True)
        return [x[0] for x in filtered[:TOP_COINS]]
    except:
        return []

def get_direction(sym):
    d = get_candles(sym, "1d", 50)
    if len(d) < 5:
        return None

    highs = [c[2] for c in d]
    lows = [c[3] for c in d]

    if highs[-1] > highs[-5]:
        return "long"
    if lows[-1] < lows[-5]:
        return "short"

    return None

def entry_model(sym, direction):
    m15 = get_candles(sym, "15m", 60)
    if len(m15) < 20:
        return None

    o = [c[1] for c in m15]
    h = [c[2] for c in m15]
    l = [c[3] for c in m15]
    c_ = [c[4] for c in m15]

    body = abs(c_[-1] - o[-1])
    avg = sum(abs(c_[i] - o[i]) for i in range(-10, -1)) / 9

    if body < avg * 0.9:
        return None

    if direction == "long" and l[-1] > l[-3]:
        return {"entry": c_[-1], "sl": min(l[-15:]) * (1 - BUFFER_PCT)}

    if direction == "short" and h[-1] < h[-3]:
        return {"entry": c_[-1], "sl": max(h[-15:]) * (1 + BUFFER_PCT)}

    return None

# ===== STATE =====
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
                if sym not in trade_state:
                    continue

                entry = safe(p["entryPrice"])
                side = p["side"]
                direction = "long" if side == "long" else "short"
                price = safe(exchange.fetch_ticker(sym)["last"])
                pnl = safe(p.get("unrealizedPnl"))

                st = trade_state[sym]
                sl = st["sl"]

                TP_USDT = 1.0

                if (direction == "long" and price <= sl) or (direction == "short" and price >= sl):
                    exchange.create_market_order(sym, "sell" if direction == "long" else "buy", qty, params={"reduceOnly": True})
                    trade_state.pop(sym, None)
                    bot.send_message(CHAT_ID, f"❌ STOP {sym}")
                    continue

                if not st["tp1"] and pnl >= TP_USDT:
                    exchange.create_market_order(sym, "sell" if direction == "long" else "buy", qty * TP_SPLIT[0], params={"reduceOnly": True})
                    st["tp1"] = True
                    st["sl"] = entry
                    st["trail_active"] = True
                    st["trail_price"] = price
                    bot.send_message(CHAT_ID, f"💰 TP1 {sym}")

                if st.get("trail_active"):
                    if direction == "long":
                        if price > st["trail_price"]:
                            st["trail_price"] = price
                        if st["trail_started"] and price <= st["trail_price"] * (1 - TRAIL_GAP):
                            exchange.create_market_order(sym, "sell", qty, params={"reduceOnly": True})
                            trade_state.pop(sym, None)
                            bot.send_message(CHAT_ID, f"🔒 TRAIL EXIT {sym}")
                    else:
                        if price < st["trail_price"]:
                            st["trail_price"] = price
                        if st["trail_started"] and price >= st["trail_price"] * (1 + TRAIL_GAP):
                            exchange.create_market_order(sym, "buy", qty, params={"reduceOnly": True})
                            trade_state.pop(sym, None)
                            bot.send_message(CHAT_ID, f"🔒 TRAIL EXIT {sym}")

            time.sleep(5)

        except Exception as e:
            print("MANAGE ERROR:", e)

# ===== ENTRY =====
def run():
    while True:
        try:
            if has_position():
                time.sleep(10)
                continue

            symbols = get_symbols(SAFE_VOLUME)

            for sym in symbols:

                # 🔥 SHORT PRIORITY
                pb = short_pullback_entry(sym)
                if pb:
                    direction = "short"
                    setup = pb
                else:
                    direction = get_direction(sym)
                    if not direction:
                        continue

                    setup = entry_model(sym, direction)
                    if not setup:
                        continue

                price = safe(exchange.fetch_ticker(sym)["last"])
                qty = (SAFE_MARGIN * SAFE_LEV) / price
                qty = float(exchange.amount_to_precision(sym, qty))

                exchange.set_leverage(SAFE_LEV, sym)
                exchange.create_market_order(sym, "buy" if direction == "long" else "sell", qty)

                trade_state[sym] = {
                    "sl": setup["sl"],
                    "tp1": False,
                    "tp2": False,
                    "trail_active": False,
                    "trail_price": 0,
                    "trail_started": False
                }

                bot.send_message(CHAT_ID, f"🟢 {direction.upper()} {sym}")
                break

            time.sleep(10)

        except Exception as e:
            print("RUN ERROR:", e)

# ===== START =====
exchange.fetch_balance()
bot.remove_webhook()

threading.Thread(target=manage, daemon=True).start()
threading.Thread(target=run, daemon=True).start()
threading.Thread(target=bot.infinity_polling, daemon=True).start()

bot.send_message(CHAT_ID, "🔥 SHORT AV BOT AKTİF")
