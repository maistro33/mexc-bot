import os
import time
import ccxt
import telebot
import threading
from datetime import datetime, timezone

# ================= SETTINGS =================
LEV = 10
FIXED_MARGIN = 4
MAX_DAILY_TRADES = 4
MIN_VOLUME = 10_000_000
TOP_COINS = 80

TP1_ROE = 15
TP2_ROE = 32
TRAIL_TRIGGER = 38
TRAIL_GAP = 15
SL_ROE = -8

BLACKLIST = ["BTC", "ETH", "BNB", "SOL", "XRP"]

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

def ema(values, period):
    if len(values) < period:
        return None
    k = 2 / (period + 1)
    ema_val = sum(values[:period]) / period
    for price in values[period:]:
        ema_val = price * k + ema_val * (1 - k)
    return ema_val

def rsi(values, period=14):
    if len(values) < period + 1:
        return 50

    gains = []
    losses = []

    for i in range(-period, 0):
        diff = values[i] - values[i - 1]
        if diff > 0:
            gains.append(diff)
            losses.append(0)
        else:
            gains.append(0)
            losses.append(abs(diff))

    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period

    if avg_loss == 0:
        return 100

    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def atr(ohlcv, period=14):
    if len(ohlcv) < period + 1:
        return 0

    trs = []
    for i in range(1, len(ohlcv)):
        high = ohlcv[i][2]
        low = ohlcv[i][3]
        prev_close = ohlcv[i - 1][4]
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        trs.append(tr)

    return sum(trs[-period:]) / period

def reset_daily():
    global daily_trades, current_day
    now_day = datetime.now(timezone.utc).day
    if now_day != current_day:
        daily_trades = 0
        current_day = now_day

def has_position():
    positions = exchange.fetch_positions()
    return any(safe(p.get("contracts")) > 0 for p in positions)

def get_symbols():
    tickers = exchange.fetch_tickers()
    filtered = []

    for sym, data in tickers.items():
        if ":USDT" not in sym:
            continue

        base = sym.split("/")[0]
        if base in BLACKLIST:
            continue

        if safe(data.get("quoteVolume")) < MIN_VOLUME:
            continue

        if safe(data.get("percentage")) < 2:
            continue

        filtered.append((sym, data["quoteVolume"]))

    filtered.sort(key=lambda x: x[1], reverse=True)
    return [x[0] for x in filtered[:TOP_COINS]]

def calculate_qty(sym, price):
    balance = exchange.fetch_balance()
    usdt = balance["USDT"]["free"]

    if usdt < 4.5:
        return None

    position_value = FIXED_MARGIN * LEV
    qty = position_value / price
    qty = float(exchange.amount_to_precision(sym, qty))

    market = exchange.market(sym)
    min_qty = market["limits"]["amount"]["min"]

    if qty < min_qty:
        return None

    return qty

# ================= TREND =================
def trend_direction(sym):
    h4 = exchange.fetch_ohlcv(sym, "4h", limit=210)
    closes = [c[4] for c in h4]

    ema200 = ema(closes, 200)
    if not ema200:
        return None

    if closes[-1] > ema200:
        return "long"
    if closes[-1] < ema200:
        return "short"
    return None

# ================= ENTRY =================
def good_entry(sym, direction):
    m15 = exchange.fetch_ohlcv(sym, "15m", limit=50)

    closes = [c[4] for c in m15]
    highs = [c[2] for c in m15]
    lows = [c[3] for c in m15]
    volumes = [c[5] for c in m15]

    ema20 = ema(closes, 20)
    if not ema20:
        return False

    current = closes[-1]
    rsi_val = rsi(closes)

    highest_10 = max(highs[-10:])
    lowest_10 = min(lows[-10:])
    volume_avg = sum(volumes[-20:]) / 20
    volume_now = volumes[-1]

    if atr(m15) < current * 0.002:
        return False

    if direction == "long":
        if current < ema20:
            return False
        if rsi_val > 68:
            return False
        if current >= highest_10 * 0.997:
            return False
        if volume_now < volume_avg:
            return False

    if direction == "short":
        if current > ema20:
            return False
        if rsi_val < 32:
            return False
        if current <= lowest_10 * 1.003:
            return False
        if volume_now < volume_avg:
            return False

    return True

# ================= OPEN =================
def open_position(sym, direction):
    global daily_trades

    price = safe(exchange.fetch_ticker(sym)["last"])
    qty = calculate_qty(sym, price)

    if qty is None:
        return

    exchange.set_leverage(LEV, sym)
    side = "buy" if direction == "long" else "sell"

    exchange.create_market_order(sym, side, qty)

    trade_state[sym] = {
        "tp1": False,
        "tp2": False,
        "max_roe": 0
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
                direction = "long" if p["side"] == "long" else "short"
                roe = safe(p.get("percentage"))
                side = "sell" if direction == "long" else "buy"

                if sym not in trade_state:
                    trade_state[sym] = {"tp1": False, "tp2": False, "max_roe": roe}

                if roe > trade_state[sym]["max_roe"]:
                    trade_state[sym]["max_roe"] = roe

                max_roe = trade_state[sym]["max_roe"]

                if roe <= SL_ROE:
                    exchange.create_market_order(sym, side, qty, params={"reduceOnly": True})
                    trade_state.pop(sym, None)
                    bot.send_message(CHAT_ID, f"❌ STOP {sym}")
                    continue

                if roe >= TP1_ROE and not trade_state[sym]["tp1"]:
                    exchange.create_market_order(sym, side, qty * 0.3, params={"reduceOnly": True})
                    trade_state[sym]["tp1"] = True
                    bot.send_message(CHAT_ID, f"💰 TP1 30% {sym}")

                if roe >= TP2_ROE and not trade_state[sym]["tp2"]:
                    exchange.create_market_order(sym, side, qty * 0.4, params={"reduceOnly": True})
                    trade_state[sym]["tp2"] = True
                    bot.send_message(CHAT_ID, f"💰 TP2 40% {sym}")

                if max_roe >= TRAIL_TRIGGER:
                    if roe <= max_roe - TRAIL_GAP:
                        exchange.create_market_order(sym, side, qty, params={"reduceOnly": True})
                        trade_state.pop(sym, None)
                        bot.send_message(CHAT_ID, f"🏁 TRAILING EXIT {sym}")

            time.sleep(5)

        except Exception as e:
            print("MANAGE ERROR:", e)
            time.sleep(5)

# ================= RUN =================
def run():
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

                if not good_entry(sym, direction):
                    continue

                open_position(sym, direction)
                break

            time.sleep(20)

        except Exception as e:
            print("RUN ERROR:", e)
            time.sleep(20)

# ================= START =================
exchange.fetch_balance()
threading.Thread(target=manage, daemon=True).start()
threading.Thread(target=run, daemon=True).start()

bot.send_message(CHAT_ID, "🔥 BOT AKTİF")
bot.infinity_polling()
