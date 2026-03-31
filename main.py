import os
import time
import ccxt
import telebot
import threading

# ===== SETTINGS =====
LEV = 10
MARGIN = 5

TP_USDT = 1.0
SL_PCT = 0.025

TRAIL_START = 0.01
TRAIL_GAP = 0.015

MIN_VOLUME = 1_000_000

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

def get_candles(sym, tf="15m", limit=50):
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

# ===== FILTERS =====
def volume_spike(sym):
    c = get_candles(sym, "5m", 20)
    if len(c) < 10:
        return False
    vols = [x[5] for x in c]
    avg = sum(vols[:-1]) / len(vols[:-1])
    return vols[-1] > avg * 1.3

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

def fake_breakout(sym):
    c = get_candles(sym, "5m", 15)
    highs = [x[2] for x in c]
    return highs[-1] < max(highs[:-3])

# ===== MARKET =====
def get_symbols():
    tickers = exchange.fetch_tickers()
    result = []

    for sym, data in tickers.items():
        if ":USDT" not in sym:
            continue

        vol = safe(data.get("quoteVolume"))
        if vol >= MIN_VOLUME:
            result.append(sym)

    return result[:60]

# ===== DUMP DETECTION =====
def is_dump(sym):
    c = get_candles(sym, "15m", 20)
    if len(c) < 15:
        return False

    start = c[-15][4]
    end = c[-1][4]

    drop = (start - end) / start

    return drop > 0.05  # %5+

# ===== PULLBACK =====
def pullback(sym):
    c = get_candles(sym, "15m", 30)

    highs = [x[2] for x in c]
    lows = [x[3] for x in c]

    last = c[-1][4]
    high = max(highs[-10:])
    low = min(lows[-10:])

    if high - low == 0:
        return False

    retrace = (last - low) / (high - low)

    return retrace > 0.3  # %30+

# ===== STATE =====
trade = {}

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
                price = safe(exchange.fetch_ticker(sym)["last"])
                pnl = safe(p.get("unrealizedPnl"))

                st = trade.get(sym)
                if not st:
                    continue

                # STOP LOSS
                if price >= st["sl"]:
                    exchange.create_market_order(sym, "buy", qty, params={"reduceOnly": True})
                    trade.pop(sym, None)
                    bot.send_message(CHAT_ID, f"❌ SL {sym}")
                    continue

                # TP1
                if not st["tp"] and pnl >= TP_USDT:
                    exchange.create_market_order(sym, "buy", qty * 0.5, params={"reduceOnly": True})
                    st["tp"] = True
                    st["trail"] = True
                    st["trail_price"] = price
                    bot.send_message(CHAT_ID, f"💰 TP1 {sym}")

                # TRAILING
                if st["trail"]:
                    if price < st["trail_price"]:
                        st["trail_price"] = price

                    if (entry - price)/entry > TRAIL_START:
                        st["trail_on"] = True

                    if st.get("trail_on") and price >= st["trail_price"] * (1 + TRAIL_GAP):
                        exchange.create_market_order(sym, "buy", qty, params={"reduceOnly": True})
                        trade.pop(sym, None)
                        bot.send_message(CHAT_ID, f"🔒 TRAIL EXIT {sym}")

            time.sleep(5)

        except Exception as e:
            print("MANAGE:", e)
            time.sleep(5)

# ===== ENTRY =====
def run():
    while True:
        try:
            if has_position():
                time.sleep(10)
                continue

            symbols = get_symbols()

            for sym in symbols:

                if not is_dump(sym):
                    continue

                if not pullback(sym):
                    continue

                imb = orderbook_imbalance(sym)

                if imb > 0.2:
                    continue

                if not volume_spike(sym):
                    continue

                if fake_breakout(sym):
                    continue

                price = safe(exchange.fetch_ticker(sym)["last"])
                qty = (MARGIN * LEV) / price
                qty = float(exchange.amount_to_precision(sym, qty))

                exchange.set_leverage(LEV, sym)
                exchange.create_market_order(sym, "sell", qty)

                sl = price * (1 + SL_PCT)

                trade[sym] = {
                    "sl": sl,
                    "tp": False,
                    "trail": False,
                    "trail_price": price
                }

                bot.send_message(CHAT_ID, f"💣 SHORT {sym}")
                break

            time.sleep(15)

        except Exception as e:
            print("RUN:", e)
            time.sleep(10)

# ===== START =====
exchange.fetch_balance()
bot.remove_webhook()
time.sleep(1)

threading.Thread(target=manage, daemon=True).start()
threading.Thread(target=run, daemon=True).start()
threading.Thread(target=bot.infinity_polling, daemon=True).start()

bot.send_message(CHAT_ID, "💣 SHORT HUNTER PRO AKTİF")
