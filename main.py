import os
import time
import ccxt
import telebot
import threading
import random

LEV = 10
MARGIN = 2

TP = 0.25
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

# ================= VOLATİL COİN =================

def get_coin():
    tickers = exchange.fetch_tickers()
    candidates = []

    for sym, d in tickers.items():

        if "USDT" not in sym:
            continue

        vol = safe(d.get("quoteVolume"))
        if vol < 1000000:
            continue

        high = safe(d.get("high"))
        low = safe(d.get("low"))

        if high == 0 or low == 0:
            continue

        volatility = (high - low) / low

        if volatility > 0.03:  # %3 hareket
            candidates.append(sym)

    if not candidates:
        return None

    return random.choice(candidates)

# ================= MOMENTUM =================

def momentum(sym):
    candles = exchange.fetch_ohlcv(sym, "1m", limit=3)
    return (candles[-1][4] - candles[-2][4]) / candles[-2][4]

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
        "entry": price
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

            price = exchange.fetch_ticker(sym)["last"]

            pnl = (price - entry) if direction == "long" else (entry - price)

            pnl = pnl * (MARGIN * LEV) / entry

            side = "sell" if direction == "long" else "buy"

            # TP
            if pnl >= TP:
                exchange.create_market_order(sym, side, None, params={"reduceOnly": True})
                bot.send_message(CHAT_ID, f"💰 TP {sym} {round(pnl,2)}$")
                active_trade = None

            # SL
            elif pnl <= -SL:
                exchange.create_market_order(sym, side, None, params={"reduceOnly": True})
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

            m = momentum(sym)

            if m > 0.002:
                open_trade(sym, "long")

            elif m < -0.002:
                open_trade(sym, "short")

            time.sleep(2)

        except:
            time.sleep(2)

# ================= START =================

print("🔥 SIMPLE SCALP BOT")

threading.Thread(target=manage, daemon=True).start()
threading.Thread(target=scanner, daemon=True).start()

bot.send_message(CHAT_ID, "🤖 SIMPLE BOT AKTİF")

bot.infinity_polling()
