import os
import time
import ccxt
import telebot
import threading
import random

# ================= SETTINGS =================

LEV = 10
BASE_MARGIN = 3
MAX_MARGIN = 5
MIN_MARGIN = 2
GROWTH_RATE = 0.3

TP1_USDT = 0.25
SL_USDT = 0.30
TP1_RATIO = 0.6

SCAN_DELAY = 2

# ================= GLOBAL =================

current_margin = BASE_MARGIN
win_streak = 0

bot = telebot.TeleBot(os.getenv("TELE_TOKEN"))
CHAT_ID = os.getenv("MY_CHAT_ID")

exchange = ccxt.bitget({
    "apiKey": os.getenv("BITGET_API"),
    "secret": os.getenv("BITGET_SEC"),
    "password": "Berfin33",
    "options": {"defaultType": "swap"},
})

trade_state = {}

# ================= HELPERS =================

def safe(x):
    try:
        return float(x)
    except:
        return 0

# ================= LOT CONTROL =================

def update_margin(pnl):
    global current_margin, win_streak

    if pnl > 0:
        win_streak += 1
        growth = current_margin * GROWTH_RATE
        current_margin = min(MAX_MARGIN, current_margin + growth)

        bot.send_message(CHAT_ID, f"📈 WIN {win_streak} | LOT → {round(current_margin,2)}$")

    else:
        win_streak = 0
        current_margin = BASE_MARGIN

        bot.send_message(CHAT_ID, f"📉 RESET | LOT → {round(current_margin,2)}$")

# ================= DYNAMIC STEP =================

def dynamic_step(pnl):
    if pnl < 0.4:
        return 0.40
    elif pnl < 0.8:
        return 0.30
    else:
        return 0.20

# ================= PRO SYNC =================

def sync_positions():
    try:
        positions = exchange.fetch_positions()

        for p in positions:
            qty = safe(p.get("contracts"))
            if qty <= 0:
                continue

            sym = p["symbol"]
            side = "long" if p["side"] == "long" else "short"
            pnl = safe(p.get("unrealizedPnl"))

            trade_state[sym] = {
                "direction": side,
                "tp1": True,
                "max_pnl": pnl,
                "breakeven": True,
                "tp1_time": time.time(),
                "last_report": pnl,
                "milestones": set(),
                "warned": False
            }

            bot.send_message(CHAT_ID, f"🔄 SYNC {sym} {round(pnl,2)}$")

    except:
        pass

# ================= COIN FILTER =================

def get_symbols():
    arr = []
    tickers = exchange.fetch_tickers()

    for sym, d in tickers.items():

        if "USDT" not in sym:
            continue

        s = sym.upper()

        if any(x in s for x in ["BTC","ETH","BNB","XRP","ADA","SOL","DOGE","DOT","TRX"]):
            continue

        vol = safe(d.get("quoteVolume"))
        if vol < 2000000 or vol > 20000000:
            continue

        ask = safe(d.get("ask"))
        bid = safe(d.get("bid"))
        last = safe(d.get("last"))
        if last == 0:
            continue

        spread = (ask - bid) / last
        if spread > 0.004:
            continue

        change = abs(safe(d.get("percentage")))
        if change < 2:
            continue

        arr.append(sym)

    return arr[:40]

# ================= INDICATORS =================

def trend(sym):
    candles = exchange.fetch_ohlcv(sym, "5m", limit=20)
    closes = [c[4] for c in candles]
    ema = sum(closes[-10:]) / 10
    return "long" if closes[-1] > ema else "short"

def momentum(sym):
    candles = exchange.fetch_ohlcv(sym, "1m", limit=3)
    return (candles[-1][4] - candles[-2][4]) / candles[-2][4]

def volume(sym):
    candles = exchange.fetch_ohlcv(sym, "5m", limit=5)
    avg = sum(c[5] for c in candles[:-1]) / 4
    return candles[-1][5] > avg

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

# ================= OPEN TRADE =================

def open_trade(sym, direction):
    global current_margin

    try:
        if get_qty(sym) > 0:
            return

        if current_direction_count(direction) >= 1:
            return

        price = exchange.fetch_ticker(sym)["last"]
        qty = (current_margin * LEV) / price

        exchange.set_leverage(LEV, sym)

        side = "buy" if direction == "long" else "sell"
        exchange.create_market_order(sym, side, qty)

        trade_state[sym] = {
            "direction": direction,
            "tp1": False,
            "max_pnl": 0,
            "breakeven": False,
            "tp1_time": time.time(),
            "last_report": 0,
            "milestones": set(),
            "warned": False
        }

        bot.send_message(CHAT_ID, f"🚀 {sym} {direction} | LOT: {round(current_margin,2)}$")

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

                # MAX PNL
                if pnl > state["max_pnl"]:
                    state["max_pnl"] = pnl
                    state["warned"] = False

                direction = state["direction"]
                side = "sell" if direction == "long" else "buy"

                # SL
                if pnl <= -SL_USDT:
                    exchange.create_market_order(sym, side, qty, params={"reduceOnly": True})
                    update_margin(pnl)
                    trade_state.pop(sym)
                    bot.send_message(CHAT_ID, f"🛑 SL {sym}")
                    continue

                # TP1
                if not state["tp1"] and pnl >= TP1_USDT:
                    exchange.create_market_order(sym, side, qty * TP1_RATIO, params={"reduceOnly": True})
                    state["tp1"] = True
                    state["tp1_time"] = time.time()
                    bot.send_message(CHAT_ID, f"💰 TP1 {sym}")

                if state["tp1"]:

                    if time.time() - state["tp1_time"] < 30:
                        continue

                    # BE
                    if not state["breakeven"] and pnl >= 0.65:
                        state["breakeven"] = True
                        bot.send_message(CHAT_ID, f"🟢 BE {sym}")

                    if state["breakeven"] and pnl <= 0:
                        exchange.create_market_order(sym, side, qty, params={"reduceOnly": True})
                        update_margin(pnl)
                        trade_state.pop(sym)
                        bot.send_message(CHAT_ID, f"⚖️ BE EXIT {sym}")
                        continue

                    # STEP
                    step = dynamic_step(state["max_pnl"])

                    if state["max_pnl"] - pnl >= step:
                        exchange.create_market_order(sym, side, qty, params={"reduceOnly": True})
                        update_margin(pnl)
                        trade_state.pop(sym)
                        bot.send_message(CHAT_ID, f"📉 STEP EXIT {sym} {round(pnl,2)}$")
                        continue

            time.sleep(2)

        except:
            time.sleep(5)

# ================= SCANNER =================

def scanner():
    while True:
        try:
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

                    if abs(m) > 0.004:
                        continue

                    if abs(m) < 0.001:
                        continue

                    if volume(sym):

                        if t == "long" and m > 0:
                            open_trade(sym, "long")
                            break

                        if t == "short" and m < 0:
                            open_trade(sym, "short")
                            break

                except:
                    continue

            time.sleep(SCAN_DELAY)

        except:
            time.sleep(5)

# ================= START =================

print("🔥 ULTIMATE FINAL BOT START")

sync_positions()

threading.Thread(target=manage, daemon=True).start()
threading.Thread(target=scanner, daemon=True).start()

bot.send_message(CHAT_ID, "🤖 BOT AKTİF")

bot.infinity_polling()
