import os
import time
import ccxt
import telebot
import threading
from datetime import datetime, timezone

# ===== SETTINGS =====
LEV = 10
RISK_PCT = 0.05
MAX_DAILY_STOPS = 3
MIN_VOLUME = 20_000_000
TOP_COINS = 40
BUFFER_PCT = 0.002
TP_SPLIT = [0.4, 0.3, 0.3]
SPREAD_LIMIT = 0.0015

# ===== TELEGRAM =====
TELE_TOKEN = os.getenv("TELE_TOKEN")
CHAT_ID = os.getenv("MY_CHAT_ID")

bot = telebot.TeleBot(TELE_TOKEN, threaded=True)
bot.remove_webhook()  # webhook temizle

# ===== BITGET =====
exchange = ccxt.bitget({
    "apiKey": os.getenv("BITGET_API"),
    "secret": os.getenv("BITGET_SEC"),
    "password": os.getenv("BITGET_PASS"),
    "options": {"defaultType": "swap"},
    "enableRateLimit": True,
})

# ===== STATE =====
trade_state = {}
daily_stops = 0
last_day = datetime.now(timezone.utc).day

# ===== HELPERS =====
def safe(x):
    try:
        return float(x)
    except:
        return 0.0

def get_candles(sym, tf, limit=100):
    return exchange.fetch_ohlcv(sym, tf, limit=limit)

def get_balance():
    return safe(exchange.fetch_balance()['total']['USDT'])

def has_position():
    positions = exchange.fetch_positions()
    return any(safe(p.get("contracts")) > 0 for p in positions)

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

# ===== TREND =====
def get_direction(sym):
    h4 = get_candles(sym, "4h", 100)
    closes = [c[4] for c in h4]
    ema = sum(closes[-50:]) / 50
    if closes[-1] > ema:
        return "long"
    elif closes[-1] < ema:
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

# ===== ENTRY MODEL =====
def entry_model(sym, direction):
    m15 = get_candles(sym, "15m", 60)
    o = [c[1] for c in m15]
    h = [c[2] for c in m15]
    l = [c[3] for c in m15]
    c_ = [c[4] for c in m15]

    body = abs(c_[-1] - o[-1])
    avg_body = sum(abs(c_[i] - o[i]) for i in range(-10, -1)) / 9

    if body < avg_body * 1.5:
        return None

    if direction == "long" and h[-3] < l[-1]:
        swing_low = min(l[-20:])
        sl = swing_low * (1 - BUFFER_PCT)
        entry = (h[-3] + l[-1]) / 2
        return {"entry": entry, "sl": sl}

    if direction == "short" and l[-3] > h[-1]:
        swing_high = max(h[-20:])
        sl = swing_high * (1 + BUFFER_PCT)
        entry = (l[-3] + h[-1]) / 2
        return {"entry": entry, "sl": sl}

    return None

# ===== MANAGE =====
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
                side = p["side"]
                direction = "long" if side == "long" else "short"
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

                # TRAILING (15m)
                if trade_state[sym]["tp2"]:
                    m15 = get_candles(sym, "15m", 10)
                    lows = [c[3] for c in m15]
                    highs = [c[2] for c in m15]

                    if direction == "long":
                        new_sl = min(lows[-5:])
                        trade_state[sym]["sl"] = max(trade_state[sym]["sl"], new_sl)
                    else:
                        new_sl = max(highs[-5:])
                        trade_state[sym]["sl"] = min(trade_state[sym]["sl"], new_sl)

            time.sleep(5)

        except Exception as e:
            print("MANAGE ERROR:", e)
            time.sleep(5)

# ===== ENTRY LOOP =====
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

            symbols = get_symbols()

            for sym in symbols:

                ticker = exchange.fetch_ticker(sym)
                spread = (ticker["ask"] - ticker["bid"]) / ticker["last"]

                if spread > SPREAD_LIMIT:
                    continue

                direction = get_direction(sym)
                if not direction:
                    continue

                if not liquidity_sweep(sym, direction):
                    continue

                setup = entry_model(sym, direction)
                if not setup:
                    continue

                balance = get_balance()
                risk_amount = balance * RISK_PCT
                sl_distance = abs(setup["entry"] - setup["sl"])

                if sl_distance == 0:
                    continue

                qty = risk_amount / sl_distance
                qty = float(exchange.amount_to_precision(sym, qty))

                exchange.set_leverage(LEV, sym)

                # LIMIT → 10 dk → MARKET fallback
                try:
                    order = exchange.create_limit_order(
                        sym,
                        "buy" if direction == "long" else "sell",
                        qty,
                        setup["entry"]
                    )
                    time.sleep(600)
                    status = exchange.fetch_order(order["id"], sym)

                    if status["status"] != "closed":
                        exchange.cancel_order(order["id"], sym)
                        exchange.create_market_order(
                            sym,
                            "buy" if direction == "long" else "sell",
                            qty
                        )
                except:
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

# ===== START =====
threading.Thread(target=manage, daemon=True).start()
threading.Thread(target=run, daemon=True).start()

bot.send_message(CHAT_ID, "🔥 SMC HYBRID BOT AKTİF (7/24)")
bot.infinity_polling(timeout=60, long_polling_timeout=60)
