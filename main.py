import os
import time
import ccxt
import telebot
import threading
import random

LEV = 15
MARGIN = 2

TP = 0.35
SL = 0.20

bot = telebot.TeleBot(os.getenv("TELE_TOKEN"))
CHAT_ID = os.getenv("MY_CHAT_ID")

exchange = ccxt.bitget({
    "apiKey": os.getenv("BITGET_API"),
    "secret": os.getenv("BITGET_SEC"),
    "password": "Berfin33",
    "options": {"defaultType": "swap"},
})

active_trade = None

def safe(x):
    try:
        return float(x)
    except:
        return 0

# ================= COIN =================

def get_coin():
    tickers = exchange.fetch_tickers()
    arr = []

    for sym, d in tickers.items():

        if "USDT" not in sym:
            continue

        vol = safe(d.get("quoteVolume"))
        if vol < 1000000:
            continue

        high = safe(d.get("high"))
        low = safe(d.get("low"))

        if low == 0:
            continue

        volat = (high - low) / low

        if volat > 0.03:
            arr.append(sym)

    return random.choice(arr) if arr else None

# ================= MOMENTUM =================

def momentum(sym):
    candles = exchange.fetch_ohlcv(sym, "1m", limit=4)

    last = candles[-1][4]
    prev = candles[-2][4]

    return (last - prev) / prev

# ================= FAKE FILTER =================

def fake_move(sym):
    candles = exchange.fetch_ohlcv(sym, "1m", limit=4)

    c1 = candles[-4][4]
    c2 = candles[-3][4]
    c3 = candles[-2][4]
    c4 = candles[-1][4]

    # ani spike varsa girme
    move = abs(c4 - c1) / c1

    return move > 0.01  # %1 üstü ani hareket

# ================= TRADE =================

def open_trade(sym, direction):
    global active_trade

    price = exchange.fetch_ticker(sym)["last"]
    qty = (MARGIN * LEV) / price

    exchange.set_leverage(LEV, sym)

    side = "buy" if direction == "long" else "sell"
    exchange.create_market_order(sym, side, qty)

    active_trade = {
        "symbol": sym,
        "direction": direction,
        "entry": price,
        "qty": qty
    }

    bot.send_message(CHAT_ID, f"🚀 {sym} {direction} {round(price,5)}")

# ================= MANAGE =================

def manage():
    global active_trade

    while True:
        try:
            if not active_trade:
                time.sleep(1)
                continue

            sym = active_trade["symbol"]
            direction = active_trade["direction"]
            entry = active_trade["entry"]
            qty = active_trade["qty"]

            price = exchange.fetch_ticker(sym)["last"]

            pnl = (price - entry) if direction == "long" else (entry - price)
            pnl = pnl * (MARGIN * LEV) / entry

            side = "sell" if direction == "long" else "buy"

            if pnl >= TP:
                exchange.create_market_order(sym, side, qty, params={"reduceOnly": True})
                bot.send_message(CHAT_ID, f"💰 TP {sym} {round(pnl,2)}$")
                active_trade = None

            elif pnl <= -SL:
                exchange.create_market_order(sym, side, qty, params={"reduceOnly": True})
                bot.send_message(CHAT_ID, f"🛑 SL {sym} {round(pnl,2)}$")
                active_trade = None

            time.sleep(1)

        except:
            time.sleep(2)

# ================= SCANNER =================

def scanner():
    global active_trade

    while True:
        try:
            if active_trade:
                time.sleep(1)
                continue

            sym = get_coin()
            if not sym:
                time.sleep(2)
                continue

            if fake_move(sym):
                continue

            m = momentum(sym)

            if m > 0.002:
                open_trade(sym, "long")

            elif m < -0.002:
                open_trade(sym, "short")

            time.sleep(2)

        except:
            time.sleep(2)

# ================= START =================

print("🔥 OPTIMIZED SCALP BOT")

threading.Thread(target=manage, daemon=True).start()
threading.Thread(target=scanner, daemon=True).start()

bot.send_message(CHAT_ID, "🤖 OPTIMIZED BOT AKTİF")

bot.infinity_polling()
