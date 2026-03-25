import os
import time
import ccxt
import telebot
import threading
import random

LEV = 10
MARGIN = 3

TP1_USDT = 0.20
STEP_USDT = 0.12
TP1_RATIO = 0.6

HARD_SL_PCT = 0.025

SCAN_DELAY = 2

bot = telebot.TeleBot(os.getenv("TELE_TOKEN"))
CHAT_ID = os.getenv("MY_CHAT_ID")

exchange = ccxt.bitget({
    "apiKey": os.getenv("BITGET_API"),
    "secret": os.getenv("BITGET_SEC"),
    "password": "Berfin33",
    "options": {"defaultType": "swap"},
})

trade_state = {}

def safe(x):
    try:
        return float(x)
    except:
        return 0

# ================= BTC TREND =================

def btc_trend():
    try:
        candles = exchange.fetch_ohlcv("BTC/USDT:USDT", "5m", limit=20)
        closes = [c[4] for c in candles]
        ema = sum(closes[-10:]) / 10
        return "long" if closes[-1] > ema else "short"
    except:
        return None

# ================= COINS =================

def get_symbols():
    arr = []
    tickers = exchange.fetch_tickers()

    blacklist = ["DOGE","PEPE","SHIB","FLOKI","BONK","AAVE","UNI","LINK"]

    for sym, d in tickers.items():

        if "USDT" not in sym:
            continue

        s = sym.upper()

        if any(x in s for x in [
            "BTC","ETH","BNB","XRP","ADA","SOL","DOT","TRX"
        ]):
            continue

        if any(x in s for x in blacklist):
            continue

        vol = safe(d.get("quoteVolume"))

        if vol < 1500000 or vol > 25000000:
            continue

        ask = safe(d.get("ask"))
        bid = safe(d.get("bid"))
        last = safe(d.get("last"))

        if last == 0:
            continue

        spread = (ask - bid) / last

        if spread > 0.004:
            continue

        arr.append(sym)

    return arr[:40]

# ================= INDICATORS =================

def trend(sym):
    candles = exchange.fetch_ohlcv(sym, "5m", limit=20)
    closes = [c[4] for c in candles]
    ema = sum(closes[-10:]) / 10
    return "long" if closes[-1] > ema else "short"

# 🔥 STRUCTURE + DUMP FILTER
def valid_structure(sym, direction):
    try:
        candles = exchange.fetch_ohlcv(sym, "1m", limit=5)
        closes = [c[4] for c in candles]

        change = (closes[-1] - closes[0]) / closes[0]

        if direction == "long":
            return change > -0.003  # dump varsa girme
        else:
            return change < 0.003
    except:
        return False

# 🔥 VOLATILITY FILTER
def volatility(sym):
    try:
        candles = exchange.fetch_ohlcv(sym, "1m", limit=5)
        ranges = [(c[2] - c[3]) / c[4] for c in candles]
        return sum(ranges) / len(ranges) > 0.0015
    except:
        return False

# 🔥 PULLBACK (denge)
def pullback_entry(sym, direction):
    try:
        candles = exchange.fetch_ohlcv(sym, "1m", limit=3)
        c2, c3 = candles[-2], candles[-1]

        if direction == "long":
            return c3[4] <= c2[4]
        else:
            return c3[4] >= c2[4]
    except:
        return False

def momentum(sym):
    candles = exchange.fetch_ohlcv(sym, "1m", limit=3)
    return (candles[-1][4] - candles[-2][4]) / candles[-2][4]

def volume(sym):
    candles = exchange.fetch_ohlcv(sym, "5m", limit=5)
    avg = sum(c[5] for c in candles[:-1]) / 4
    return candles[-1][5] > avg * 1.1

# ================= RISK =================

def get_qty(sym):
    try:
        pos = exchange.fetch_positions([sym])
        if not pos:
            return 0
        return safe(pos[0]["contracts"])
    except:
        return 0

def current_direction_count(direction):
    count = 0
    positions = exchange.fetch_positions()
    for p in positions:
        if safe(p.get("contracts")) > 0:
            side = "long" if p["side"] == "long" else "short"
            if side == direction:
                count += 1
    return count

# ================= TRADE =================

def open_trade(sym, direction):
    try:
        if get_qty(sym) > 0:
            return

        if current_direction_count(direction) >= 1:
            return

        price = exchange.fetch_ticker(sym)["last"]
        qty = (MARGIN * LEV) / price

        exchange.set_leverage(LEV, sym)

        side = "buy" if direction == "long" else "sell"
        exchange.create_market_order(sym, side, qty)

        trade_state[sym] = {
            "direction": direction,
            "tp1": False,
            "max_pnl": 0,
            "breakeven": False,
            "tp1_time": 0,
            "entry": price
        }

        bot.send_message(
            CHAT_ID,
            f"🚀 {sym}\nYön: {direction}\nGiriş: {round(price,6)}\nMiktar: {round(qty,4)}"
        )

    except:
        pass

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
                pnl = safe(p.get("unrealizedPnl"))
                entry = state["entry"]
                price = exchange.fetch_ticker(sym)["last"]

                direction = state["direction"]
                side = "sell" if direction == "long" else "buy"

                # HARD SL
                if direction == "long":
                    if price <= entry * (1 - HARD_SL_PCT):
                        pct = ((price - entry) / entry) * 100
                        exchange.create_market_order(sym, side, qty, params={"reduceOnly": True})
                        trade_state.pop(sym)
                        bot.send_message(CHAT_ID, f"🛑 HARD SL {sym}\nPnL: {round(pnl,2)}$\n{round(pct,2)}%")
                        continue
                else:
                    if price >= entry * (1 + HARD_SL_PCT):
                        pct = ((entry - price) / entry) * 100
                        exchange.create_market_order(sym, side, qty, params={"reduceOnly": True})
                        trade_state.pop(sym)
                        bot.send_message(CHAT_ID, f"🛑 HARD SL {sym}\nPnL: {round(pnl,2)}$\n{round(pct,2)}%")
                        continue

                if pnl > state["max_pnl"]:
                    state["max_pnl"] = pnl

                # TP1
                if not state["tp1"] and pnl >= TP1_USDT:
                    exchange.create_market_order(sym, side, qty * TP1_RATIO, params={"reduceOnly": True})
                    state["tp1"] = True
                    state["tp1_time"] = time.time()
                    bot.send_message(CHAT_ID, f"💰 TP1 {sym} {round(pnl,2)}$")

                if state["tp1"]:

                    if time.time() - state["tp1_time"] < 20:
                        continue

                    if not state["breakeven"] and pnl >= TP1_USDT + STEP_USDT:
                        state["breakeven"] = True
                        bot.send_message(CHAT_ID, f"🟢 BE {sym}")

                    if state["breakeven"] and pnl <= 0:
                        exchange.create_market_order(sym, side, qty, params={"reduceOnly": True})
                        trade_state.pop(sym)
                        bot.send_message(CHAT_ID, f"⚖️ BE EXIT {sym}")
                        continue

                    if state["max_pnl"] - pnl >= STEP_USDT:
                        bot.send_message(CHAT_ID, f"📉 STEP {sym}")
                        pct = ((price - entry) / entry) * 100 if direction == "long" else ((entry - price) / entry) * 100
                        exchange.create_market_order(sym, side, qty, params={"reduceOnly": True})
                        trade_state.pop(sym)
                        bot.send_message(CHAT_ID, f"🏁 EXIT {sym}\nPnL: {round(pnl,2)}$\n{round(pct,2)}%")
                        continue

            time.sleep(2)

        except:
            time.sleep(5)

# ================= SCANNER =================

def scanner():
    while True:
        try:
            market_dir = btc_trend()

            positions = exchange.fetch_positions()
            active = sum(1 for p in positions if safe(p.get("contracts")) > 0)

            if active >= 2:
                time.sleep(2)
                continue

            symbols = get_symbols()
            random.shuffle(symbols)

            for sym in symbols:
                try:
                    t = trend(sym)
                    m = momentum(sym)

                    if market_dir and t != market_dir:
                        continue

                    if not valid_structure(sym, t):
                        continue

                    if not volatility(sym):
                        continue

                    if not pullback_entry(sym, t):
                        continue

                    if volume(sym):

                        if t == "long" and m > -0.0005:
                            open_trade(sym, "long")
                            break

                        if t == "short" and m < 0.0005:
                            open_trade(sym, "short")
                            break

                except:
                    continue

            time.sleep(SCAN_DELAY)

        except:
            time.sleep(5)

# ================= START =================

print("🔥 SMART SNIPER BOT V3")

sync_positions()

threading.Thread(target=manage, daemon=True).start()
threading.Thread(target=scanner, daemon=True).start()

bot.send_message(CHAT_ID, "🤖 BOT AKTİF V3")

bot.infinity_polling()
