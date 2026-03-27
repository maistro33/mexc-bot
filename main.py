import os
import time
import ccxt
import telebot
import threading
import random

# ===== SETTINGS =====
LEV = 10
MARGIN = 3

TP1 = 0.30
SL = 0.30
TRAIL = 0.20
STEP = 0.20

SCAN_LIMIT = 40

# ===== API =====
bot = telebot.TeleBot(os.getenv("TELE_TOKEN"))
CHAT_ID = os.getenv("MY_CHAT_ID")

exchange = ccxt.bitget({
    "apiKey": os.getenv("BITGET_API"),
    "secret": os.getenv("BITGET_SEC"),
    "password": "Berfin33",
    "options": {"defaultType": "swap"},
})

active = None

def safe(x):
    try:
        return float(x)
    except:
        return 0

# ===== POSITION =====
def has_position():
    try:
        positions = exchange.fetch_positions()
        for p in positions:
            if abs(safe(p.get("contracts") or p.get("size"))) > 0:
                return True
        return False
    except:
        return False

def get_pnl(sym):
    try:
        positions = exchange.fetch_positions()
        for p in positions:
            if sym.replace("/", "") in p.get("symbol",""):
                return safe(p.get("unrealizedPnl"))
        return 0
    except:
        return 0

def get_qty(sym):
    try:
        positions = exchange.fetch_positions()
        for p in positions:
            if sym.replace("/", "") in p.get("symbol",""):
                return abs(safe(p.get("contracts") or p.get("size")))
        return 0
    except:
        return 0

# ===== TREND =====
def trend_5m(sym):
    try:
        candles = exchange.fetch_ohlcv(sym, "5m", limit=20)
        closes = [c[4] for c in candles]
        ema = sum(closes[-10:]) / 10
        return closes[-1] > ema
    except:
        return False

def entry_ok(sym):
    try:
        candles = exchange.fetch_ohlcv(sym, "1m", limit=3)
        return candles[-1][4] > candles[-2][4]
    except:
        return False

def not_pumped(sym):
    try:
        candles = exchange.fetch_ohlcv(sym, "1m", limit=5)
        closes = [c[4] for c in candles]
        move = (closes[-1] - closes[-5]) / closes[-5]
        return move < 0.02
    except:
        return False

# ===== SYMBOLS =====
def get_symbols():
    tickers = exchange.fetch_tickers()
    arr = []

    for sym, d in tickers.items():

        if "USDT" not in sym:
            continue

        vol = safe(d.get("quoteVolume"))
        if vol < 1000000 or vol > 5000000:
            continue

        arr.append(sym)

    random.shuffle(arr)
    return arr[:SCAN_LIMIT]

# ===== TRADE =====
def open_trade(sym):
    global active

    if active or has_position():
        return

    try:
        price = exchange.fetch_ticker(sym)["last"]
        qty = (MARGIN * LEV) / price

        exchange.set_leverage(LEV, sym)
        exchange.create_market_order(sym, "buy", qty)

        active = {
            "symbol": sym,
            "tp1": False,
            "max": 0,
            "step": 0
        }

        bot.send_message(CHAT_ID, f"🚀 LONG {sym}")

    except Exception as e:
        print(e)

# ===== MANAGE =====
def manage():
    global active

    while True:
        try:
            if not active:
                time.sleep(1)
                continue

            sym = active["symbol"]
            pnl = get_pnl(sym)

            # STEP
            if pnl > active["step"] + STEP:
                active["step"] = pnl
                bot.send_message(CHAT_ID, f"📈 {round(pnl,2)} USDT")

            # TP1
            if not active["tp1"] and pnl >= TP1:
                qty = get_qty(sym)
                exchange.create_market_order(sym, "sell", round(qty*0.5,6), params={"reduceOnly": True})

                active["tp1"] = True
                active["max"] = pnl

                bot.send_message(CHAT_ID, "💰 TP1")

            # TRAIL
            if active["tp1"]:
                if pnl > active["max"]:
                    active["max"] = pnl

                if active["max"] - pnl >= TRAIL:
                    qty = get_qty(sym)
                    if qty > 0:
                        exchange.create_market_order(sym, "sell", qty, params={"reduceOnly": True})

                    bot.send_message(CHAT_ID, f"🏁 EXIT {round(pnl,2)}")
                    active = None

            # SL
            if not active["tp1"] and pnl <= -SL:
                qty = get_qty(sym)
                if qty > 0:
                    exchange.create_market_order(sym, "sell", qty, params={"reduceOnly": True})

                bot.send_message(CHAT_ID, f"🛑 SL {round(pnl,2)}")
                active = None

            time.sleep(1)

        except Exception as e:
            print(e)
            time.sleep(2)

# ===== SCAN =====
def scan():
    while True:
        try:
            if active or has_position():
                time.sleep(1)
                continue

            for sym in get_symbols():

                if not trend_5m(sym):
                    continue

                if not not_pumped(sym):
                    continue

                if not entry_ok(sym):
                    continue

                open_trade(sym)
                break

            time.sleep(2)

        except:
            time.sleep(2)

# ===== START =====
threading.Thread(target=manage, daemon=True).start()
threading.Thread(target=scan, daemon=True).start()

bot.send_message(CHAT_ID, "🤖 FINAL BOT AKTİF")

bot.infinity_polling()
