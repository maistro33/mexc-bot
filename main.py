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
SL_USDT = 0.30

bot = telebot.TeleBot(os.getenv("TELE_TOKEN"))
CHAT_ID = os.getenv("MY_CHAT_ID")

BITGET_PASS = os.getenv("BITGET_PASS") or "Berfin33"

exchange = ccxt.bitget({
    "apiKey": os.getenv("BITGET_API"),
    "secret": os.getenv("BITGET_SEC"),
    "password": BITGET_PASS,
    "options": {"defaultType": "swap"},
    "enableRateLimit": True
})

active_trade = None

def safe(x):
    try:
        return float(x)
    except:
        return 0

# ================= PNL =================

def get_real_pnl(sym):
    try:
        positions = exchange.fetch_positions()
        for p in positions:
            if sym.split("/")[0] in p['symbol']:
                return float(p.get('unrealizedPnl', 0))
    except:
        return 0
    return 0

# ================= POSITION =================

def position_still_open(sym):
    try:
        positions = exchange.fetch_positions()
        for p in positions:
            if sym.split("/")[0] in p['symbol'] and float(p.get('contracts', 0)) > 0:
                return True
        return False
    except:
        return True

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

# ================= OVEREXTENDED =================

def overextended(sym):
    try:
        candles = exchange.fetch_ohlcv(sym, "1m", limit=5)
        closes = [c[4] for c in candles]
        return (closes[-1] - closes[-5]) / closes[-5] > 0.01
    except:
        return False

# ================= DIP REVERSAL =================

def dip_reversal(sym):
    try:
        candles = exchange.fetch_ohlcv(sym, "1m", limit=6)

        lows = [c[3] for c in candles]
        closes = [c[4] for c in candles]

        old_low = lows[-5]
        higher_low = lows[-1] > old_low
        bullish = closes[-1] > closes[-2]

        return higher_low and bullish
    except:
        return False

# ================= COINS =================

def get_coins():
    tickers = exchange.fetch_tickers()
    arr = []

    blacklist = ["BTC","ETH","BNB","XRP","ADA","SOL","DOGE","PEPE","SHIB"]

    for sym, d in tickers.items():

        if "USDT" not in sym:
            continue

        if any(x in sym for x in blacklist):
            continue

        vol = safe(d.get("quoteVolume"))

        if vol < 1_000_000 or vol > 3_000_000:
            continue

        arr.append(sym)

    random.shuffle(arr)
    return arr

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
            "qty": qty,
            "tp1": False,
            "max_pnl": 0,
            "remaining_qty": qty
        }

        bot.send_message(CHAT_ID, f"🚀 LONG {sym}")

    except Exception as e:
        print(e)

# ================= MANAGE =================

def manage():
    global active_trade

    while True:
        try:
            if not active_trade:
                time.sleep(1)
                continue

            sym = active_trade["symbol"]
            qty = active_trade["qty"]

            if not position_still_open(sym):
                active_trade = None
                continue

            pnl = get_real_pnl(sym)

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

                bot.send_message(CHAT_ID, f"💰 TP1 {round(pnl,2)}")

            # TRAILING
            if active_trade["tp1"] and pnl >= TRAIL_START:

                drawdown = active_trade["max_pnl"] - pnl

                if drawdown >= STEP:

                    exchange.create_market_order(
                        sym, side, active_trade["remaining_qty"],
                        params={"reduceOnly": True}
                    )

                    bot.send_message(CHAT_ID, f"🏁 EXIT {round(pnl,2)}")
                    active_trade = None
                    continue

            # SL
            if pnl <= -SL_USDT:

                exchange.create_market_order(
                    sym, side, qty, params={"reduceOnly": True}
                )

                bot.send_message(CHAT_ID, f"🛑 SL {round(pnl,2)}")
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

            coins = get_coins()

            for sym in coins:

                if not trend_ok(sym):
                    continue

                if not volume_spike(sym):
                    continue

                if overextended(sym):
                    continue

                # 🔥 EN KRİTİK
                if not dip_reversal(sym):
                    continue

                open_trade(sym)
                break

            time.sleep(2)

        except Exception as e:
            print("SCAN ERROR:", e)
            time.sleep(2)

# ================= START =================

threading.Thread(target=manage, daemon=True).start()
threading.Thread(target=scanner, daemon=True).start()

bot.send_message(CHAT_ID, "🤖 FINAL DİP BOT AKTİF")

bot.infinity_polling()
