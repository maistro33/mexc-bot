import os
import time
import ccxt
import telebot
import threading
from datetime import datetime, timezone

# ===== SETTINGS =====
LEV = 10
FIXED_RISK_USDT = 2
MAX_DAILY_STOPS = 3
MIN_VOLUME = 20_000_000
TOP_COINS = 80
BUFFER_PCT = 0.002
TP_SPLIT = [0.4, 0.3, 0.3]
SPREAD_LIMIT = 0.0015
TRAIL_CANDLES = 8

# ===== TELEGRAM =====
bot = telebot.TeleBot(os.getenv("TELE_TOKEN"), threaded=True)
bot.remove_webhook()
CHAT_ID = os.getenv("MY_CHAT_ID")

# ===== BITGET =====
exchange = ccxt.bitget({
    "apiKey": os.getenv("BITGET_API"),
    "secret": os.getenv("BITGET_SEC"),
    "password": "Berfin33",
    "options": {"defaultType": "swap"},
    "enableRateLimit": True,
})

# ===== STATE =====
trade_state = {}
daily_stops = 0
last_day = datetime.now(timezone.utc).day

def safe(x):
    try:
        return float(x)
    except:
        return 0.0

def get_balance():
    return safe(exchange.fetch_balance()['total']['USDT'])

def get_candles(sym, tf, limit=100):
    return exchange.fetch_ohlcv(sym, tf, limit=limit)

def has_position():
    positions = exchange.fetch_positions()
    return any(safe(p.get("contracts")) > 0 for p in positions)

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

def get_direction(sym):
    h4 = get_candles(sym, "4h", 100)
    closes = [c[4] for c in h4]
    ema = sum(closes[-50:]) / 50
    if closes[-1] > ema:
        return "long"
    elif closes[-1] < ema:
        return "short"
    return None

def entry_model(sym, direction):
    m15 = get_candles(sym, "15m", 50)
    highs = [c[2] for c in m15]
    lows = [c[3] for c in m15]
    closes = [c[4] for c in m15]

    if direction == "long":
        if closes[-1] > max(highs[-10:-1]):
            sl = min(lows[-10:])
            return {"entry": closes[-1], "sl": sl}
    else:
        if closes[-1] < min(lows[-10:-1]):
            sl = max(highs[-10:])
            return {"entry": closes[-1], "sl": sl}
    return None

def manage():
    global daily_stops, last_day

    while True:
        try:
            if datetime.now(timezone.utc).day != last_day:
                daily_stops = 0
                last_day = datetime.now(timezone.utc).day

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
                tp2 = entry + 2*risk if direction == "long" else entry - 2*risk

                # STOP
                if (direction == "long" and price <= sl) or \
                   (direction == "short" and price >= sl):

                    exchange.create_market_order(
                        sym,
                        "sell" if direction == "long" else "buy",
                        qty,
                        params={"reduceOnly": True}
                    )
                    daily_stops += 1
                    trade_state.pop(sym, None)
                    bot.send_message(CHAT_ID, f"❌ STOP {sym}")
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
                    bot.send_message(CHAT_ID, f"💰 TP1 {sym}")

                # TP2
                if trade_state[sym]["tp1"] and not trade_state[sym]["tp2"] and \
                   ((direction == "long" and price >= tp2) or
                    (direction == "short" and price <= tp2)):

                    part = qty * TP_SPLIT[1]
                    exchange.create_market_order(
                        sym,
                        "sell" if direction == "long" else "buy",
                        part,
                        params={"reduceOnly": True}
                    )

                    trade_state[sym]["tp2"] = True
                    bot.send_message(CHAT_ID, f"🚀 TP2 {sym}")

                # TRAILING
                if trade_state[sym]["tp2"]:
                    m15 = get_candles(sym, "15m", TRAIL_CANDLES + 2)
                    lows = [c[3] for c in m15]
                    highs = [c[2] for c in m15]

                    if direction == "long":
                        new_sl = min(lows[-TRAIL_CANDLES:])
                        trade_state[sym]["sl"] = max(sl, new_sl)
                    else:
                        new_sl = max(highs[-TRAIL_CANDLES:])
                        trade_state[sym]["sl"] = min(sl, new_sl)

            time.sleep(5)

        except Exception as e:
            print("MANAGE ERROR:", e)
            time.sleep(5)

def run():
    global daily_stops

    while True:
        try:
            if daily_stops >= MAX_DAILY_STOPS:
                time.sleep(60)
                continue

            if has_position():
                time.sleep(15)
                continue

            for sym in get_symbols():

                ticker = exchange.fetch_ticker(sym)
                spread = (ticker["ask"] - ticker["bid"]) / ticker["last"]
                if spread > SPREAD_LIMIT:
                    continue

                direction = get_direction(sym)
                if not direction:
                    continue

                setup = entry_model(sym, direction)
                if not setup:
                    continue

                sl_distance = abs(setup["entry"] - setup["sl"])
                if sl_distance <= 0:
                    continue

                qty = FIXED_RISK_USDT / sl_distance

                market = exchange.market(sym)
                precision = market['precision']['amount']

                if precision == 0:
                    qty = int(qty)
                else:
                    qty = round(qty, precision)

                if qty <= 0:
                    continue

                exchange.set_leverage(LEV, sym)

                exchange.create_market_order(
                    sym,
                    "buy" if direction == "long" else "sell",
                    qty
                )

                trade_state[sym] = {
                    "sl": setup["sl"],
                    "tp1": False,
                    "tp2": False
                }

                bot.send_message(CHAT_ID, f"📈 {sym} {direction.upper()} AÇILDI")
                break

            time.sleep(20)

        except Exception as e:
            print("RUN ERROR:", e)
            time.sleep(20)

threading.Thread(target=manage, daemon=True).start()
threading.Thread(target=run, daemon=True).start()

bot.send_message(CHAT_ID, "🔥 SABİT 2 USDT RISK BOT AKTİF")
bot.infinity_polling(timeout=60, long_polling_timeout=60)
