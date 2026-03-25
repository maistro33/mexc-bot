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

# ================= LOT =================

def update_margin(pnl):
    global current_margin, win_streak

    if pnl > 0:
        win_streak += 1
        current_margin = min(MAX_MARGIN, current_margin + current_margin * GROWTH_RATE)

        bot.send_message(CHAT_ID, f"""
📈 LOT ARTTI
━━━━━━━━━━━━
Yeni Lot: {round(current_margin,2)}$
Win: {win_streak}
━━━━━━━━━━━━
""")
    else:
        win_streak = 0
        current_margin = BASE_MARGIN

        bot.send_message(CHAT_ID, f"""
📉 LOT RESET
━━━━━━━━━━━━
Lot: {round(current_margin,2)}$
━━━━━━━━━━━━
""")

# ================= SMART STEP =================

def dynamic_step(sym, pnl):

    try:
        candles = exchange.fetch_ohlcv(sym, "5m", limit=5)
        ranges = [(c[2] - c[3]) / c[4] for c in candles]
        vol = sum(ranges) / len(ranges)
    except:
        vol = 0.01

    base_step = pnl * 0.4

    if vol > 0.02:
        step = base_step * 1.2
    elif vol < 0.01:
        step = base_step * 0.8
    else:
        step = base_step

    return max(step, 0.15)

# ================= SYNC =================

def sync_positions():
    try:
        positions = exchange.fetch_positions()

        for p in positions:
            if safe(p.get("contracts")) <= 0:
                continue

            sym = p["symbol"]
            pnl = safe(p.get("unrealizedPnl"))

            trade_state[sym] = {
                "direction": "long" if p["side"] == "long" else "short",
                "tp1": True,
                "max_pnl": pnl,
                "breakeven": True,
                "tp1_time": time.time(),
            }

            bot.send_message(CHAT_ID, f"🔄 SYNC {sym} | {round(pnl,2)}$")

    except:
        pass

# ================= FILTER =================

def get_symbols():
    arr = []
    tickers = exchange.fetch_tickers()

    for sym, d in tickers.items():

        if "USDT" not in sym:
            continue

        if any(x in sym for x in ["BTC","ETH","BNB","XRP","ADA","SOL"]):
            continue

        vol = safe(d.get("quoteVolume"))
        if vol < 2000000 or vol > 20000000:
            continue

        if abs(safe(d.get("percentage"))) < 2:
            continue

        arr.append(sym)

    return arr[:30]

# ================= INDICATORS =================

def trend(sym):
    candles = exchange.fetch_ohlcv(sym, "5m", limit=20)
    closes = [c[4] for c in candles]
    return "long" if closes[-1] > sum(closes[-10:]) / 10 else "short"

def momentum(sym):
    candles = exchange.fetch_ohlcv(sym, "1m", limit=3)
    return (candles[-1][4] - candles[-2][4]) / candles[-2][4]

def volume(sym):
    candles = exchange.fetch_ohlcv(sym, "5m", limit=5)
    avg = sum(c[5] for c in candles[:-1]) / 4
    return candles[-1][5] > avg

# ================= OPEN =================

def open_trade(sym, direction):
    global current_margin

    try:
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
        }

        bot.send_message(CHAT_ID, f"""
🚀 YENİ TRADE
━━━━━━━━━━━━
💰 {sym}
📊 {direction.upper()}
━━━━━━━━━━━━
""")

    except:
        pass

# ================= MANAGE =================

def manage():
    while True:
        try:
            positions = exchange.fetch_positions()

            for p in positions:
                if safe(p.get("contracts")) <= 0:
                    continue

                sym = p["symbol"]
                if sym not in trade_state:
                    continue

                state = trade_state[sym]
                pnl = safe(p.get("unrealizedPnl"))

                if pnl > state["max_pnl"]:
                    state["max_pnl"] = pnl

                direction = state["direction"]
                side = "sell" if direction == "long" else "buy"

                # SL
                if pnl <= -SL_USDT:
                    exchange.create_market_order(sym, side, p["contracts"], params={"reduceOnly": True})
                    update_margin(pnl)
                    trade_state.pop(sym)

                    bot.send_message(CHAT_ID, f"""
🛑 STOP LOSS
━━━━━━━━━━━━
💰 {sym}
📉 Küçük zarar
━━━━━━━━━━━━
""")
                    continue

                # TP1
                if not state["tp1"] and pnl >= TP1_USDT:
                    exchange.create_market_order(sym, side, p["contracts"] * TP1_RATIO, params={"reduceOnly": True})
                    state["tp1"] = True
                    state["tp1_time"] = time.time()

                    bot.send_message(CHAT_ID, f"""
💰 KÂR ALINDI ✅
━━━━━━━━━━━━
💰 {sym}
📈 {round(pnl,2)}$
━━━━━━━━━━━━
""")

                if state["tp1"]:

                    if time.time() - state["tp1_time"] < 20:
                        continue

                    # BE
                    if not state["breakeven"] and pnl >= 0.65:
                        state["breakeven"] = True

                        bot.send_message(CHAT_ID, f"""
🟢 RİSK SIFIRLANDI
━━━━━━━━━━━━
💰 {sym}
━━━━━━━━━━━━
""")

                    if state["breakeven"] and pnl <= 0:
                        exchange.create_market_order(sym, side, p["contracts"], params={"reduceOnly": True})
                        update_margin(pnl)
                        trade_state.pop(sym)

                        bot.send_message(CHAT_ID, f"⚖️ BE EXIT {sym}")
                        continue

                    # SMART STEP
                    step = dynamic_step(sym, state["max_pnl"])

                    if state["max_pnl"] - pnl >= step:
                        exchange.create_market_order(sym, side, p["contracts"], params={"reduceOnly": True})
                        update_margin(pnl)
                        trade_state.pop(sym)

                        bot.send_message(CHAT_ID, f"""
🏆 TRADE KAPANDI
━━━━━━━━━━━━
💰 {sym}
📊 {round(pnl,2)}$
━━━━━━━━━━━━
""")

            time.sleep(2)

        except:
            time.sleep(5)

# ================= SCANNER =================

def scanner():
    while True:
        try:
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

print("🔥 PRO BOT START")

sync_positions()

threading.Thread(target=manage, daemon=True).start()
threading.Thread(target=scanner, daemon=True).start()

bot.send_message(CHAT_ID, "🤖 PRO BOT AKTİF")

bot.infinity_polling()
