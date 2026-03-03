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
TOP_COINS = 50

TP1_RATIO = 0.30
TP2_RATIO = 0.40

TP1_PCT = 0.008   # +0.8%
TP2_PCT = 0.016   # +1.6%

TRAIL_GAP = 0.007  # %0.7 geri çekilme

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

def has_position():
    positions = exchange.fetch_positions()
    return any(safe(p.get("contracts")) > 0 for p in positions)

def get_position_qty(sym):
    pos = exchange.fetch_positions([sym])
    if not pos:
        return 0
    return safe(pos[0].get("contracts"))

def get_symbols():
    tickers = exchange.fetch_tickers()
    filtered = []

    for sym, data in tickers.items():
        if ":USDT" not in sym:
            continue
        if safe(data.get("quoteVolume")) < MIN_VOLUME:
            continue
        if abs(safe(data.get("percentage"))) < 2:
            continue
        filtered.append((sym, data["quoteVolume"]))

    filtered.sort(key=lambda x: x[1], reverse=True)
    return [x[0] for x in filtered[:TOP_COINS]]

# ================= BTC FILTER =================
def btc_trend_ok():
    btc = "BTC/USDT:USDT"
    h4 = exchange.fetch_ohlcv(btc, "4h", limit=60)
    closes = [c[4] for c in h4]
    ema = sum(closes[-50:]) / 50
    return closes[-1] > ema  # sadece long için izin

# ================= TREND =================
def trend_direction(sym):
    h4 = exchange.fetch_ohlcv(sym, "4h", limit=60)
    closes = [c[4] for c in h4]
    ema = sum(closes[-50:]) / 50

    if closes[-1] > ema:
        return "long"
    if closes[-1] < ema:
        return "short"
    return None

# ================= RETEST =================
def retest_signal(sym, direction):
    h1 = exchange.fetch_ohlcv(sym, "1h", limit=20)
    highs = [c[2] for c in h1]
    lows = [c[3] for c in h1]

    if direction == "long":
        return lows[-1] <= min(lows[-5:-1])
    else:
        return highs[-1] >= max(highs[-5:-1])

# ================= MOMENTUM =================
def momentum_confirm(sym, direction):
    m15 = exchange.fetch_ohlcv(sym, "15m", limit=10)
    last = m15[-1]
    prev = m15[-2]

    body = abs(last[4] - last[1])
    avg = sum(abs(c[4] - c[1]) for c in m15[:-1]) / 9

    if body > avg * 1.5:
        if direction == "long" and last[4] > prev[2]:
            return True
        if direction == "short" and last[4] < prev[3]:
            return True
    return False

# ================= RESISTANCE FILTER =================
def resistance_room(sym, direction):
    m15 = exchange.fetch_ohlcv(sym, "15m", limit=30)
    highs = [c[2] for c in m15]
    lows = [c[3] for c in m15]
    price = m15[-1][4]

    if direction == "long":
        recent_high = max(highs[-20:])
        return price < recent_high * 0.993  # %0.7 boşluk

    if direction == "short":
        recent_low = min(lows[-20:])
        return price > recent_low * 1.007

    return False

# ================= ENTRY =================
def open_position(sym, direction):
    global daily_trades

    price = safe(exchange.fetch_ticker(sym)["last"])
    qty = (MARGIN * LEV) / price
    qty = float(exchange.amount_to_precision(sym, qty))

    exchange.set_leverage(LEV, sym)
    side = "buy" if direction == "long" else "sell"
    exchange.create_market_order(sym, side, qty)

    trade_state[sym] = {
        "direction": direction,
        "entry": price,
        "tp1_hit": False,
        "tp2_hit": False,
        "max_price": price
    }

    daily_trades += 1
    bot.send_message(CHAT_ID, f"🚀 {sym} {direction.upper()} AÇILDI")

# ================= MANAGE =================
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

                state = trade_state[sym]
                direction = state["direction"]
                entry = state["entry"]
                price = safe(exchange.fetch_ticker(sym)["last"])
                side = "sell" if direction == "long" else "buy"

                if direction == "long" and price > state["max_price"]:
                    state["max_price"] = price
                if direction == "short" and price < state["max_price"]:
                    state["max_price"] = price

                # TP1
                if not state["tp1_hit"]:
                    if (direction == "long" and price >= entry * (1 + TP1_PCT)) or \
                       (direction == "short" and price <= entry * (1 - TP1_PCT)):
                        exchange.create_market_order(sym, side, qty * TP1_RATIO, params={"reduceOnly": True})
                        state["tp1_hit"] = True
                        bot.send_message(CHAT_ID, f"💰 TP1 {sym}")

                # TP2
                if state["tp1_hit"] and not state["tp2_hit"]:
                    if (direction == "long" and price >= entry * (1 + TP2_PCT)) or \
                       (direction == "short" and price <= entry * (1 - TP2_PCT)):
                        exchange.create_market_order(sym, side, qty * TP2_RATIO, params={"reduceOnly": True})
                        state["tp2_hit"] = True
                        bot.send_message(CHAT_ID, f"💰 TP2 {sym}")

                # TRAILING
                if state["tp2_hit"]:
                    if direction == "long":
                        if price <= state["max_price"] * (1 - TRAIL_GAP):
                            remaining = get_position_qty(sym)
                            exchange.create_market_order(sym, side, remaining, params={"reduceOnly": True})
                            trade_state.pop(sym)
                            bot.send_message(CHAT_ID, f"🏁 TRAILING EXIT {sym}")

                    if direction == "short":
                        if price >= state["max_price"] * (1 + TRAIL_GAP):
                            remaining = get_position_qty(sym)
                            exchange.create_market_order(sym, side, remaining, params={"reduceOnly": True})
                            trade_state.pop(sym)
                            bot.send_message(CHAT_ID, f"🏁 TRAILING EXIT {sym}")

            time.sleep(5)

        except Exception as e:
            print("MANAGE ERROR:", e)
            time.sleep(5)

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
                time.sleep(20)
                continue

            symbols = get_symbols()

            for sym in symbols:
                direction = trend_direction(sym)
                if not direction:
                    continue

                if direction == "long" and not btc_trend_ok():
                    continue

                if not retest_signal(sym, direction):
                    continue

                if not momentum_confirm(sym, direction):
                    continue

                if not resistance_room(sym, direction):
                    continue

                open_position(sym, direction)
                break

            time.sleep(30)

        except Exception as e:
            print("RUN ERROR:", e)
            time.sleep(30)

# ================= START =================
exchange.fetch_balance()

threading.Thread(target=manage, daemon=True).start()
threading.Thread(target=run, daemon=True).start()

bot.send_message(CHAT_ID, "🛡 ELITE TREND ENGINE AKTİF")
bot.infinity_polling()
