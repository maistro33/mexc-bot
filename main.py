import os
import time
import ccxt
import telebot
import threading
import random

LEV = 10
MARGIN = 3

TP1 = 0.50
TRAIL_START = 0.70
STEP = 0.35
SL = 0.25

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

# ================= TREND =================

def trend_ok(sym):
    try:
        candles = exchange.fetch_ohlcv(sym, "1m", limit=20)
        closes = [c[4] for c in candles]
        ema = sum(closes[-10:]) / 10
        return closes[-1] > ema
    except:
        return False

# ================= COIN =================

def get_coin():
    tickers = exchange.fetch_tickers()
    arr = []

    blacklist = [
        "BTC","ETH","BNB","XRP","ADA","SOL",
        "DOGE","PEPE","SHIB","AVAX","LINK","UNI","LTC"
    ]

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

# ================= SETUP =================

def pullback(sym):
    try:
        candles = exchange.fetch_ohlcv(sym, "1m", limit=4)
        closes = [c[4] for c in candles]
        return closes[-2] < closes[-3]
    except:
        return False

def breakout(sym):
    try:
        candles = exchange.fetch_ohlcv(sym, "1m", limit=3)
        closes = [c[4] for c in candles]
        return closes[-1] > closes[-2]
    except:
        return False

# ================= TRADE =================

def open_trade(sym):
    global active_trade

    try:
        price = exchange.fetch_ticker(sym)["last"]
        qty = (MARGIN * LEV) / price

        exchange.set_leverage(LEV, sym)
        exchange.create_market_order(sym, "buy", qty)

        active_trade = {
            "symbol": sym,
            "entry": price,
            "qty": qty,
            "tp1": False,
            "max_pnl": 0,
            "remaining_qty": qty
        }

        bot.send_message(CHAT_ID, f"🚀 LONG {sym} {round(price,5)}")

    except Exception as e:
        print("TRADE ERROR:", e)

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

            if pnl > active_trade["max_pnl"]:
                active_trade["max_pnl"] = pnl

            side = "sell"

            # ================= TP1
            if not active_trade["tp1"] and pnl >= TP1:

                close_qty = qty * 0.5

                exchange.create_market_order(
                    sym, side, close_qty, params={"reduceOnly": True}
                )

                active_trade["tp1"] = True
                active_trade["remaining_qty"] = qty - close_qty

                bot.send_message(CHAT_ID, f"💰 TP1 {sym} +0.50$")

            # ================= TRAILING
            if active_trade["tp1"] and pnl >= TRAIL_START:

                if active_trade["max_pnl"] - pnl >= STEP:

                    exchange.create_market_order(
                        sym,
                        side,
                        active_trade["remaining_qty"],
                        params={"reduceOnly": True}
                    )

                    bot.send_message(CHAT_ID, f"🏁 TRAILING EXIT {sym} {round(pnl,2)}$")
                    active_trade = None
                    continue

            # ================= SL
            if pnl <= -SL:

                exchange.create_market_order(
                    sym, side, qty, params={"reduceOnly": True}
                )

                bot.send_message(CHAT_ID, f"🛑 SL {sym} {round(pnl,2)}$")
                active_trade = None

            time.sleep(1)

        except Exception as e:
            print("MANAGE ERROR:", e)
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

            if not trend_ok(sym):
                continue

            if not pullback(sym):
                continue

            if breakout(sym):
                open_trade(sym)

            time.sleep(2)

        except Exception as e:
            print("SCAN ERROR:", e)
            time.sleep(2)

# ================= START =================

print("🔥 CLEAN BOT FINAL TRAILING")

threading.Thread(target=manage, daemon=True).start()
threading.Thread(target=scanner, daemon=True).start()

bot.send_message(CHAT_ID, "🤖 BOT AKTİF FINAL TRAILING")

bot.infinity_polling()
