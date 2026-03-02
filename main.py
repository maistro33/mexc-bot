import os
import time
import ccxt
import telebot
import threading

# ===== SETTINGS =====
LEV = 10
MARGIN = 10
MAX_POS = 1
MIN_VOLUME = 5_000_000
TOP_COINS = 80
BUFFER_PCT = 0.0015

TP_SPLIT = [0.4, 0.3, 0.3]

# ===== TELEGRAM =====
bot = telebot.TeleBot(os.getenv("TELE_TOKEN"))
CHAT_ID = os.getenv("MY_CHAT_ID")

# ===== BITGET =====
exchange = ccxt.bitget({
    "apiKey": os.getenv("BITGET_API"),
    "secret": os.getenv("BITGET_SEC"),
    "password": "Berfin33",
    "options": {"defaultType": "swap"},
    "enableRateLimit": True,
    "timeout": 30000
})

# ===== HELPERS =====
def safe(x):
    try:
        return float(x)
    except:
        return 0.0

def get_candles(sym, tf, limit=100):
    return exchange.fetch_ohlcv(sym, tf, limit=limit)

def has_position():
    pos = exchange.fetch_positions()
    return any(safe(p.get("contracts")) > 0 for p in pos)

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

# ===== DIRECTION (1D KALDIRILDI) =====
def get_direction(sym):
    h4 = get_candles(sym, "4h", 50)

    h_high = [c[2] for c in h4]
    h_low  = [c[3] for c in h4]

    # Daha erken kırılım
    if h_high[-1] > max(h_high[-4:-1]):
        return "long"

    if h_low[-1] < min(h_low[-4:-1]):
        return "short"

    return None

# ===== LIQUIDITY (YUMUŞATILDI) =====
def liquidity_sweep(sym, direction):
    h1 = get_candles(sym, "1h", 30)
    highs = [c[2] for c in h1]
    lows  = [c[3] for c in h1]

    if direction == "long":
        return lows[-1] < min(lows[-5:])
    else:
        return highs[-1] > max(highs[-5:])

# ===== ENTRY MODEL =====
def entry_model(sym, direction):
    m15 = get_candles(sym, "15m", 60)

    o = [c[1] for c in m15]
    h = [c[2] for c in m15]
    l = [c[3] for c in m15]
    c_ = [c[4] for c in m15]

    body = abs(c_[-1] - o[-1])
    avg_body = sum(abs(c_[i] - o[i]) for i in range(-10, -1)) / 9

    # 1.5 → 1.2 yapıldı (erken momentum)
    if body < avg_body * 1.2:
        return None

    # FVG
    if direction == "long" and h[-3] < l[-1]:
        entry = (h[-3] + l[-1]) / 2
        swing_low = min(l[-15:])
        sl = swing_low - (swing_low * BUFFER_PCT)
        return {"entry": entry, "sl": sl}

    if direction == "short" and l[-3] > h[-1]:
        entry = (l[-3] + h[-1]) / 2
        swing_high = max(h[-15:])
        sl = swing_high + (swing_high * BUFFER_PCT)
        return {"entry": entry, "sl": sl}

    return None

# ===== TRADE STATE =====
trade_state = {}

# ===== POSITION MANAGER =====
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
                side = p["side"]
                direction = "long" if side == "long" else "short"

                price = safe(exchange.fetch_ticker(sym)["last"])

                if sym not in trade_state:
                    continue

                sl = trade_state[sym]["sl"]
                risk = abs(entry - sl)

                tp1 = entry + risk if direction == "long" else entry - risk
                tp2 = entry + 2*risk if direction == "long" else entry - 2*risk
                tp3 = entry + 3*risk if direction == "long" else entry - 3*risk

                # STOP
                if (direction == "long" and price <= sl) or \
                   (direction == "short" and price >= sl):

                    exchange.create_market_order(
                        sym,
                        "sell" if direction == "long" else "buy",
                        qty,
                        params={"reduceOnly": True}
                    )
                    bot.send_message(CHAT_ID, f"❌ STOP {sym}")
                    trade_state.pop(sym, None)
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

                # TP3
                if trade_state[sym]["tp2"] and \
                   ((direction == "long" and price >= tp3) or
                    (direction == "short" and price <= tp3)):

                    exchange.create_market_order(
                        sym,
                        "sell" if direction == "long" else "buy",
                        qty,
                        params={"reduceOnly": True}
                    )

                    bot.send_message(CHAT_ID, f"🏆 TP3 {sym}")
                    trade_state.pop(sym, None)

            time.sleep(5)

        except:
            time.sleep(5)

# ===== ENTRY LOOP =====
def run():
    while True:
        try:
            if has_position():
                time.sleep(20)
                continue

            symbols = get_symbols()

            for sym in symbols:

                direction = get_direction(sym)
                if not direction:
                    continue

                if not liquidity_sweep(sym, direction):
                    continue

                setup = entry_model(sym, direction)
                if not setup:
                    continue

                exchange.set_leverage(LEV, sym)

                price = safe(exchange.fetch_ticker(sym)["last"])
                notional = MARGIN * LEV
                qty = notional / price
                qty = float(exchange.amount_to_precision(sym, qty))

                side = "buy" if direction == "long" else "sell"

                exchange.create_market_order(sym, side, qty)

                trade_state[sym] = {
                    "sl": setup["sl"],
                    "tp1": False,
                    "tp2": False
                }

                bot.send_message(CHAT_ID, f"📈 {sym} {direction.upper()} AÇILDI")

                break

            time.sleep(25)

        except:
            time.sleep(25)

# ===== START =====
exchange.fetch_balance()

threading.Thread(target=manage, daemon=True).start()
threading.Thread(target=run, daemon=True).start()

bot.send_message(CHAT_ID, "SMC PRO BOT HIZLI FVG AKTİF")
bot.infinity_polling()
