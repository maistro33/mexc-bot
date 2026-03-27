import os
import time
import ccxt
import telebot
import threading
import random

LEV = 10
MARGIN = 3

TP1_USDT = 0.30
TRAIL_START = 0.50
STEP = 0.20
SL_PERCENT = 2.5

DEBUG = False

bot = telebot.TeleBot(os.getenv("TELE_TOKEN"))
CHAT_ID = os.getenv("MY_CHAT_ID")

exchange = ccxt.bitget({
    "apiKey": os.getenv("BITGET_API"),
    "secret": os.getenv("BITGET_SEC"),
    "password": os.getenv("BITGET_PASS"),
    "options": {"defaultType": "swap"},
    "enableRateLimit": True
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
        candles = exchange.fetch_ohlcv(sym, "5m", limit=20)
        closes = [c[4] for c in candles]

        ema20 = sum(closes[-20:]) / 20
        ema5 = sum(closes[-5:]) / 5

        return closes[-1] > ema20 and ema5 > ema20
    except:
        return False

# ================= VOLUME =================

def volume_spike(sym):
    try:
        candles = exchange.fetch_ohlcv(sym, "1m", limit=10)
        volumes = [c[5] for c in candles]
        avg = sum(volumes[:-1]) / len(volumes[:-1])
        return volumes[-1] > avg * 1.5
    except:
        return False

# ================= BREAKOUT =================

def strong_breakout(sym):
    try:
        candles = exchange.fetch_ohlcv(sym, "1m", limit=6)

        highs = [c[2] for c in candles]
        closes = [c[4] for c in candles]

        breakout = closes[-1] > max(highs[:-1])
        strong = closes[-1] > closes[-2]

        return breakout and strong
    except:
        return False

# ================= COINS =================

def get_coins():
    tickers = exchange.fetch_tickers()
    arr = []

    blacklist = [
        "BTC","ETH","BNB","XRP","ADA","SOL",
        "DOGE","PEPE","SHIB","AVAX","LINK","UNI","LTC"
    ]

    for sym, d in tickers.items():

        if "USDT" not in sym:
            continue

        if any(x in sym for x in blacklist):
            continue

        vol = safe(d.get("quoteVolume"))

        # 1M - 3M
        if vol < 1_000_000 or vol > 3_000_000:
            continue

        arr.append(sym)

    random.shuffle(arr)
    return arr

# ================= POSITION CHECK =================

def check_open_position():
    global active_trade
    try:
        positions = exchange.fetch_positions()

        for p in positions:
            if float(p.get('contracts', 0)) > 0:
                active_trade = {
                    "symbol": p['symbol'],
                    "entry": float(p['entryPrice']),
                    "qty": float(p['contracts']),
                    "tp1": False,
                    "max_pnl": 0,
                    "remaining_qty": float(p['contracts'])
                }
                return True
    except:
        return False

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

            pnl = (price - entry) / entry * LEV * MARGIN

            if pnl > active_trade["max_pnl"]:
                active_trade["max_pnl"] = pnl

            side = "sell"

            # TP1
            if not active_trade["tp1"] and pnl >= TP1_USDT:

                close_qty = qty * 0.5

                exchange.create_market_order(
                    sym, side, close_qty, params={"reduceOnly": True}
                )

                active_trade["tp1"] = True
                active_trade["remaining_qty"] = qty - close_qty

                bot.send_message(CHAT_ID, f"💰 TP1 {sym} +0.30$")

            # TRAILING
            if active_trade["tp1"] and pnl >= TRAIL_START:

                drawdown = active_trade["max_pnl"] - pnl

                if drawdown >= STEP:

                    exchange.create_market_order(
                        sym,
                        side,
                        active_trade["remaining_qty"],
                        params={"reduceOnly": True}
                    )

                    bot.send_message(CHAT_ID, f"🏁 TRAILING EXIT {sym} {round(pnl,2)}$")
                    active_trade = None
                    continue

            # HARD SL (%2.5)
            if pnl <= -(SL_PERCENT / 100 * LEV * MARGIN):

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

            if check_open_position():
                time.sleep(2)
                continue

            coins = get_coins()

            for sym in coins:

                if not trend_ok(sym):
                    continue

                if not volume_spike(sym):
                    continue

                if not strong_breakout(sym):
                    continue

                time.sleep(1)

                if strong_breakout(sym):
                    print(f"ENTRY FOUND: {sym}")
                    open_trade(sym)
                    break

            time.sleep(2)

        except Exception as e:
            print("SCAN ERROR:", e)
            time.sleep(2)

# ================= START =================

print("🔥 FINAL BOT AKTİF")

threading.Thread(target=manage, daemon=True).start()
threading.Thread(target=scanner, daemon=True).start()

bot.send_message(CHAT_ID, "🤖 BOT AKTİF")

bot.infinity_polling()
