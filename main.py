import os
import time
import ccxt
import telebot
import threading
from datetime import datetime, timezone

# ================= SETTINGS =================
LEV = 5
MARGIN = 6
MAX_DAILY_TRADES = 1
MIN_VOLUME = 8_000_000
TOP_COINS = 50
BUFFER = 0.0015

TP_SPLIT = 0.5  # %50 TP1

# ================= TELEGRAM =================
bot = telebot.TeleBot(os.getenv("TELE_TOKEN"))
CHAT_ID = os.getenv("MY_CHAT_ID")

# ================= EXCHANGE =================
exchange = ccxt.bitget({
    "apiKey": os.getenv("BITGET_API"),
    "secret": os.getenv("BITGET_SEC"),
    "password": "Berfin33",
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

def has_position():
    positions = exchange.fetch_positions()
    return any(safe(p.get("contracts")) > 0 for p in positions)

def get_position_qty(sym):
    pos = exchange.fetch_positions([sym])
    if not pos:
        return 0
    return safe(pos[0].get("contracts"))


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
    closes = [c[4] for c in h1]

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


# ================= ENTRY =================
def open_position(sym, direction):
    global daily_trades

    price = safe(exchange.fetch_ticker(sym)["last"])
    qty = (MARGIN * LEV) / price
    qty = float(exchange.amount_to_precision(sym, qty))

    exchange.set_leverage(LEV, sym)
    side = "buy" if direction == "long" else "sell"
    exchange.create_market_order(sym, side, qty)

    if direction == "long":
        sl = price * 0.99
        tp1 = price * 1.01
        tp2 = price * 1.02
    else:
        sl = price * 1.01
        tp1 = price * 0.99
        tp2 = price * 0.98

    trade_state[sym] = {
        "direction": direction,
        "sl": sl,
        "tp1": tp1,
        "tp2": tp2,
        "tp1_hit": False
    }

    daily_trades += 1
    bot.send_message(CHAT_ID, f"🛡 TREND {sym} {direction.upper()} AÇILDI")


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

                direction = trade_state[sym]["direction"]
                price = safe(exchange.fetch_ticker(sym)["last"])
                state = trade_state[sym]

                # STOP
                if (direction == "long" and price <= state["sl"]) or \
                   (direction == "short" and price >= state["sl"]):

                    side = "sell" if direction == "long" else "buy"
                    exchange.create_market_order(sym, side, qty, params={"reduceOnly": True})
                    trade_state.pop(sym)
                    bot.send_message(CHAT_ID, f"❌ STOP {sym}")
                    continue

                # TP1
                if not state["tp1_hit"] and \
                   ((direction == "long" and price >= state["tp1"]) or
                    (direction == "short" and price <= state["tp1"])):

                    close_qty = qty * TP_SPLIT
                    side = "sell" if direction == "long" else "buy"
                    exchange.create_market_order(sym, side, close_qty, params={"reduceOnly": True})
                    state["tp1_hit"] = True
                    state["sl"] = price  # break even
                    bot.send_message(CHAT_ID, f"💰 TP1 {sym}")

                # TP2
                if state["tp1_hit"] and \
                   ((direction == "long" and price >= state["tp2"]) or
                    (direction == "short" and price <= state["tp2"])):

                    side = "sell" if direction == "long" else "buy"
                    exchange.create_market_order(sym, side, qty, params={"reduceOnly": True})
                    trade_state.pop(sym)
                    bot.send_message(CHAT_ID, f"🏆 TP2 {sym}")

            time.sleep(5)

        except:
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

                if not retest_signal(sym, direction):
                    continue

                if not momentum_confirm(sym, direction):
                    continue

                open_position(sym, direction)
                break

            time.sleep(30)

        except:
            time.sleep(30)


# ================= START =================
exchange.fetch_balance()

threading.Thread(target=manage, daemon=True).start()
threading.Thread(target=run, daemon=True).start()

bot.send_message(CHAT_ID, "🛡 SAVUNMA TREND ENGINE AKTİF")
bot.infinity_polling()
