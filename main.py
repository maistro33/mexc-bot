import os
import time
import ccxt
import telebot
import threading
from datetime import datetime, timezone

# ================= SETTINGS =================
LEV = 5
FIXED_MARGIN = 2        # HER İŞLEM 2 USDT
MAX_DAILY_TRADES = 3
MIN_VOLUME = 10_000_000
TOP_COINS = 50
BUFFER = 0.003          # %0.3 SL buffer
TP1_ROE = 8             # %8 ROE
TP2_ROE = 18            # %18 ROE
TRAIL_TRIGGER = 12      # %12 ROE sonrası trailing
TRAIL_STEP = 5          # %5 geri gelirse kapat

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


# ================= PUMP FILTER =================
def avoid_top_entry(sym, direction):
    m15 = exchange.fetch_ohlcv(sym, "15m", limit=5)
    last = m15[-1]
    prev = m15[-2]

    move = abs(last[4] - prev[4]) / prev[4]

    if move > 0.015:  # %1.5 tek mum pump
        return False

    return True


# ================= ENTRY =================
def open_position(sym, direction):
    global daily_trades

    price = safe(exchange.fetch_ticker(sym)["last"])

    exchange.set_leverage(LEV, sym)

    qty = (FIXED_MARGIN * LEV) / price
    qty = float(exchange.amount_to_precision(sym, qty))

    side = "buy" if direction == "long" else "sell"
    exchange.create_market_order(sym, side, qty)

    trade_state[sym] = {
        "direction": direction,
        "entry": price,
        "tp1_hit": False,
        "peak_roe": 0
    }

    daily_trades += 1
    bot.send_message(CHAT_ID, f"🛡 {sym} {direction.upper()} AÇILDI")


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

                entry = safe(p["entryPrice"])
                direction = trade_state[sym]["direction"]
                price = safe(exchange.fetch_ticker(sym)["last"])

                roe = safe(p.get("percentage"))

                # STOP LOSS %6 ROE
                if roe <= -6:
                    side = "sell" if direction == "long" else "buy"
                    exchange.create_market_order(sym, side, qty, params={"reduceOnly": True})
                    trade_state.pop(sym)
                    bot.send_message(CHAT_ID, f"❌ STOP {sym}")
                    continue

                # TP1
                if not trade_state[sym]["tp1_hit"] and roe >= TP1_ROE:
                    close_qty = qty * 0.5
                    side = "sell" if direction == "long" else "buy"
                    exchange.create_market_order(sym, side, close_qty, params={"reduceOnly": True})
                    trade_state[sym]["tp1_hit"] = True
                    bot.send_message(CHAT_ID, f"💰 TP1 {sym}")

                # TP2
                if roe >= TP2_ROE:
                    side = "sell" if direction == "long" else "buy"
                    exchange.create_market_order(sym, side, qty, params={"reduceOnly": True})
                    trade_state.pop(sym)
                    bot.send_message(CHAT_ID, f"🏆 TP2 {sym}")
                    continue

                # TRAILING
                if roe > trade_state[sym]["peak_roe"]:
                    trade_state[sym]["peak_roe"] = roe

                if trade_state[sym]["peak_roe"] >= TRAIL_TRIGGER:
                    if roe <= trade_state[sym]["peak_roe"] - TRAIL_STEP:
                        side = "sell" if direction == "long" else "buy"
                        exchange.create_market_order(sym, side, qty, params={"reduceOnly": True})
                        trade_state.pop(sym)
                        bot.send_message(CHAT_ID, f"🔄 TRAIL {sym}")

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
                time.sleep(15)
                continue

            symbols = get_symbols()

            for sym in symbols:
                direction = trend_direction(sym)
                if not direction:
                    continue

                if not avoid_top_entry(sym, direction):
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

bot.send_message(CHAT_ID, "🛡 SAVUNMA TREND ENGINE PRO AKTİF")
bot.infinity_polling()
