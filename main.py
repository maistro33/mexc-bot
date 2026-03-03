import os
import time
import ccxt
import telebot
import threading
from datetime import datetime, timezone

# ================= SETTINGS =================
LEV = 10
FIXED_MARGIN = 2
MAX_DAILY_TRADES = 4
MIN_VOLUME = 10_000_000
TOP_COINS = 80

TP1_ROE = 12
TP2_ROE = 30
SL_ROE = -10

# HANTAL COIN BLACKLIST
BLACKLIST = ["BTC", "ETH", "BNB", "SOL", "XRP"]

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

        if safe(data.get("quoteVolume")) >= MIN_VOLUME:
            filtered.append((sym, data["quoteVolume"]))

    filtered.sort(key=lambda x: x[1], reverse=True)
    return [x[0] for x in filtered[:TOP_COINS]]

def calculate_qty(sym, price):
    market = exchange.market(sym)
    min_qty = market["limits"]["amount"]["min"]

    qty = (FIXED_MARGIN * LEV) / price
    qty = float(exchange.amount_to_precision(sym, qty))

    if qty < min_qty:
        return None
    return qty


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


# ================= ENTRY FILTER =================
def good_entry(sym, direction):
    m15 = exchange.fetch_ohlcv(sym, "15m", limit=20)
    closes = [c[4] for c in m15]
    opens = [c[1] for c in m15]

    ema20 = sum(closes[-20:]) / 20
    last_close = closes[-1]
    prev_close = closes[-2]

    # Pump filtresi
    if abs(last_close - prev_close) / prev_close > 0.012:
        return False

    if direction == "long":
        if last_close < ema20:
            return False

    if direction == "short":
        if last_close > ema20:
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
        "direction": direction
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

                # STOP
                if roe <= SL_ROE:
                    side = "sell" if direction == "long" else "buy"
                    exchange.create_market_order(sym, side, qty, params={"reduceOnly": True})
                    bot.send_message(CHAT_ID, f"❌ STOP {sym}")
                    continue

                # TP1
                if roe >= TP1_ROE:
                    side = "sell" if direction == "long" else "buy"
                    exchange.create_market_order(sym, side, qty * 0.5, params={"reduceOnly": True})
                    bot.send_message(CHAT_ID, f"💰 TP1 {sym}")

                # TP2
                if roe >= TP2_ROE:
                    side = "sell" if direction == "long" else "buy"
                    exchange.create_market_order(sym, side, qty, params={"reduceOnly": True})
                    bot.send_message(CHAT_ID, f"🏆 TP2 {sym}")

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

bot.send_message(CHAT_ID, "🔥 ALTCOIN PRO BOT AKTİF")
bot.infinity_polling()
