import os
import time
import ccxt
import telebot
import threading

# ===== SETTINGS =====
SAFE_VOLUME = 500_000
AGGR_VOLUME = 800_000

SAFE_LEV = 10
SAFE_MARGIN = 5

AGGR_LEV = 10
AGGR_MARGIN = 5

TOP_COINS = 200
BUFFER_PCT = 0.0015

TP_SPLIT = [0.4, 0.3, 0.3]

TRAIL_START = 0.008
TRAIL_GAP = 0.02

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

# ===== LIQUIDITY (ANA EDGE) =====
def liquidity_sweep(sym, direction):
    h1 = get_candles(sym, "1h", 30)

    if len(h1) < 5:
        return False

    highs = [c[2] for c in h1]
    lows  = [c[3] for c in h1]

    if direction == "long":
        return lows[-1] <= min(lows[:-3])
    else:
        return highs[-1] >= max(highs[:-3])

# ===== FILTERS =====
def volume_spike(sym):
    candles = get_candles(sym, "5m", 20)
    if len(candles) < 10:
        return False
    vols = [c[5] for c in candles]
    avg = sum(vols[:-1]) / len(vols[:-1])
    return vols[-1] > avg * 1.5

def orderbook_imbalance(sym):
    try:
        ob = exchange.fetch_order_book(sym, limit=10)
        bids = sum([b[1] for b in ob["bids"]])
        asks = sum([a[1] for a in ob["asks"]])
        if bids + asks == 0:
            return 0
        return (bids - asks) / (bids + asks)
    except:
        return 0

def fake_breakout(sym, direction):
    m5 = get_candles(sym, "5m", 15)
    if len(m5) < 5:
        return False
    highs = [c[2] for c in m5]
    lows = [c[3] for c in m5]

    if direction == "long":
        return highs[-1] < max(highs[:-3])
    else:
        return lows[-1] > min(lows[:-3])

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

# ===== RECOVERY =====
def load_open_positions():
    try:
        positions = exchange.fetch_positions()

        for p in positions:
            qty = safe(p.get("contracts"))
            if qty <= 0:
                continue

            sym = p["symbol"]
            entry = safe(p["entryPrice"])
            side = p["side"]

            if side == "long":
                sl = entry * 0.97
            else:
                sl = entry * 1.03

            trade_state[sym] = {
                "sl": sl,
                "tp1": False,
                "tp2": False,
                "trail_active": True,
                "trail_price": entry,
                "trail_started": False
            }

            bot.send_message(CHAT_ID, f"♻️ RECOVERED {sym}")

    except Exception as e:
        print("RECOVERY ERROR:", e)

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

                st = trade_state[sym]
                sl = st["sl"]
                risk = abs(entry - sl)

                tp1 = entry + risk if direction == "long" else entry - risk

                # STOP
                if (direction == "long" and price <= sl) or (direction == "short" and price >= sl):
                    exchange.create_market_order(sym, "sell" if direction == "long" else "buy", qty, params={"reduceOnly": True})
                    trade_state.pop(sym, None)
                    bot.send_message(CHAT_ID, f"❌ STOP {sym}")
                    continue

                # TP1
                if not st["tp1"] and ((direction == "long" and price >= tp1) or (direction == "short" and price <= tp1)):
                    exchange.create_market_order(sym, "sell" if direction == "long" else "buy", qty * TP_SPLIT[0], params={"reduceOnly": True})
                    st["tp1"] = True
                    st["sl"] = entry
                    st["trail_active"] = True
                    st["trail_price"] = price
                    bot.send_message(CHAT_ID, f"💰 TP1 {sym}")

                # TRAILING
                if st.get("trail_active"):
                    if direction == "long":
                        if price > st["trail_price"]:
                            st["trail_price"] = price
                        if (price - entry)/entry > TRAIL_START:
                            st["trail_started"] = True
                        if st["trail_started"] and price <= st["trail_price"] * (1 - TRAIL_GAP):
                            exchange.create_market_order(sym, "sell", qty, params={"reduceOnly": True})
                            trade_state.pop(sym, None)
                            bot.send_message(CHAT_ID, f"🔒 TRAIL EXIT {sym}")
                    else:
                        if price < st["trail_price"]:
                            st["trail_price"] = price
                        if (entry - price)/entry > TRAIL_START:
                            st["trail_started"] = True
                        if st["trail_started"] and price >= st["trail_price"] * (1 + TRAIL_GAP):
                            exchange.create_market_order(sym, "buy", qty, params={"reduceOnly": True})
                            trade_state.pop(sym, None)
                            bot.send_message(CHAT_ID, f"🔒 TRAIL EXIT {sym}")

            time.sleep(5)

        except Exception as e:
            print("MANAGE ERROR:", e)
            time.sleep(5)

# ===== ENTRY =====
def run():
    while True:
        try:
            if has_position():
                time.sleep(10)
                continue

            # ===== SAFE =====
            symbols = get_symbols(SAFE_VOLUME)

            for sym in symbols:
                direction = get_direction(sym)
                if not direction:
                    continue

                # 🔥 ANA EDGE GERİ
                if not liquidity_sweep(sym, direction):
                    continue

                setup = entry_model(sym, direction)
                if not setup:
                    continue

                imb = orderbook_imbalance(sym)

                if direction == "long" and imb < -0.4:
                    continue
                if direction == "short" and imb > 0.4:
                    continue

                if fake_breakout(sym, direction) and abs(imb) < 0.05:
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

                bot.send_message(CHAT_ID, f"🟢 SAFE {sym} {direction.upper()}")
                break
            else:
                # ===== AGGR =====
                symbols = get_symbols(AGGR_VOLUME)

                for sym in symbols:
                    direction = get_direction(sym)
                    if not direction:
                        continue

                    # 🔥 ANA EDGE GERİ
                    if not liquidity_sweep(sym, direction):
                        continue

                    setup = entry_model(sym, direction)
                    if not setup:
                        continue

                    price = safe(exchange.fetch_ticker(sym)["last"])
                    qty = (AGGR_MARGIN * AGGR_LEV) / price
                    qty = float(exchange.amount_to_precision(sym, qty))

                    exchange.set_leverage(AGGR_LEV, sym)
                    exchange.create_market_order(sym, "buy" if direction == "long" else "sell", qty)

                    trade_state[sym] = {
                        "sl": setup["sl"],
                        "tp1": False,
                        "tp2": False,
                        "trail_active": False,
                        "trail_price": 0,
                        "trail_started": False
                    }

                    bot.send_message(CHAT_ID, f"🔥 AGGR {sym} {direction.upper()}")
                    break

            time.sleep(15)

        except Exception as e:
            print("RUN ERROR:", e)
            time.sleep(15)

# ===== START =====
exchange.fetch_balance()
bot.remove_webhook()
time.sleep(1)

threading.Thread(target=manage, daemon=True).start()
threading.Thread(target=run, daemon=True).start()
threading.Thread(target=bot.infinity_polling, daemon=True).start()

time.sleep(2)

load_open_positions()

bot.send_message(CHAT_ID, "🔥 PRO FINAL (LIQUIDITY FIX) AKTİF")
