import os
import time
import ccxt
import telebot
import threading
import random

LEV = 10
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

    blacklist = ["BTC","ETH","BNB","XRP","ADA","SOL","DOGE","PEPE","SHIB"]

    for sym, d in tickers.items():

        if "USDT" not in sym:
            continue

        s = sym.upper()

        if any(x in s for x in blacklist):
            continue

        vol = safe(d.get("quoteVolume"))

        if vol < 1000000 or vol > 5000000:
            continue

        arr.append(sym)

    return random.choice(arr) if arr else None

# ================= DİP + ONAY =================

def dip_signal(sym):
    try:
        candles = exchange.fetch_ohlcv(sym, "1m", limit=7)
        closes = [c[4] for c in candles]

        falling = closes[-6] > closes[-5] > closes[-4] > closes[-3]
        green1 = closes[-2] > closes[-3]
        green2 = closes[-1] > closes[-2]

        return falling and green1 and green2
    except:
        return False

# ================= TRADE =================

def open_trade(sym):
    global active_trade

    price = exchange.fetch_ticker(sym)["last"]
    qty = (MARGIN * LEV) / price

    exchange.set_leverage(LEV, sym)
    exchange.create_market_order(sym, "buy", qty)

    active_trade = {
        "symbol": sym,
        "entry": price,
        "qty": qty
    }

    bot.send_message(CHAT_ID, f"🚀 LONG {sym} {round(price,5)}")

# ================= MANAGE =================

def manage():
    global active_trade

    while True:
        try:
            if not active_trade:
                time.sleep(1)
                continue

            sym = active_trade["symbol"]
            entry = active_trade["entry"]
            qty = active_trade["qty"]

            price = exchange.fetch_ticker(sym)["last"]

            pnl = (price - entry) * (MARGIN * LEV) / entry

            if pnl >= TP:
                exchange.create_market_order(sym, "sell", qty, params={"reduceOnly": True})
                bot.send_message(CHAT_ID, f"💰 TP {sym} {round(pnl,2)}$")
                active_trade = None

            elif pnl <= -SL:
                exchange.create_market_order(sym, "sell", qty, params={"reduceOnly": True})
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

            if dip_signal(sym):
                open_trade(sym)

            time.sleep(2)

        except:
            time.sleep(2)

# ================= START =================

print("🔥 DIP BOT FINAL")

threading.Thread(target=manage, daemon=True).start()
threading.Thread(target=scanner, daemon=True).start()

bot.send_message(CHAT_ID, "🤖 BOT AKTİF FINAL")

bot.infinity_polling()
