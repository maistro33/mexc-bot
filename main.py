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

def get_position(sym=None):
    try:
        positions = exchange.fetch_positions()
        for p in positions:
            qty = abs(safe(p.get("contracts") or p.get("size")))
            if qty <= 0:
                continue

            psym = p.get("symbol", "")

            if sym is None:
                return p

            if sym.split("/")[0] in psym:
                return p

        return None
    except:
        return None

def has_position():
    return get_position() is not None

def get_qty(sym):
    p = get_position(sym)
    if not p:
        return 0
    return abs(safe(p.get("contracts") or p.get("size")))

def get_pnl(sym):
    p = get_position(sym)
    if not p:
        return 0
    return safe(p.get("unrealizedPnl"))

# ===== TREND =====

def trend_5m(sym):
    try:
        candles = exchange.fetch_ohlcv(sym, "5m", limit=20)
        closes = [c[4] for c in candles]
        ema = sum(closes[-10:]) / 10
        return closes[-1] > ema
    except:
        return False

def trend_strength(sym):
    try:
        candles = exchange.fetch_ohlcv(sym, "5m", limit=10)
        closes = [c[4] for c in candles]
        move = (closes[-1] - closes[0]) / closes[0]
        return move > 0.01
    except:
        return False

# ===== ENTRY FILTER =====

def not_pumped(sym):
    try:
        candles = exchange.fetch_ohlcv(sym, "1m", limit=5)
        closes = [c[4] for c in candles]
        move = (closes[-1] - closes[-5]) / closes[-5]
        return move < 0.02
    except:
        return False

def structure_ok(sym):
    try:
        candles = exchange.fetch_ohlcv(sym, "1m", limit=6)
        lows = [c[3] for c in candles]
        highs = [c[2] for c in candles]

        hl = lows[-1] > lows[-3]
        hh = highs[-1] > highs[-2]

        return hl and hh
    except:
        return False

def buyer_strong(sym):
    try:
        candles = exchange.fetch_ohlcv(sym, "1m", limit=2)

        o = candles[-1][1]
        c = candles[-1][4]
        h = candles[-1][2]

        body = c - o
        wick = h - c

        return body > 0 and body > wick
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

    if has_position():
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

# ===== SYNC =====

def sync_position():
    global active

    p = get_position()
    if p:
        active = {
            "symbol": p.get("symbol"),
            "tp1": False,
            "max": 0,
            "step": 0
        }
        bot.send_message(CHAT_ID, "🔄 SYNC")

# ===== MANAGE =====

def manage():
    global active

    while True:
        try:
            if not has_position():
                active = None
                time.sleep(1)
                continue

            if not active:
                sync_position()

            sym = active["symbol"]
            pnl = get_pnl(sym)

            # STEP
            if pnl > active["step"] + STEP:
                active["step"] = pnl
                bot.send_message(CHAT_ID, f"📈 {round(pnl,2)} USDT")

            # TP1
            if not active["tp1"] and pnl >= TP1:
                qty = get_qty(sym)
                if qty > 0:
                    exchange.create_market_order(
                        sym, "sell", round(qty * 0.5, 6),
                        params={"reduceOnly": True}
                    )

                active["tp1"] = True
                active["max"] = pnl
                bot.send_message(CHAT_ID, f"💰 TP1 {round(pnl,2)}")

            # TRAILING
            if active["tp1"]:
                if pnl > active["max"]:
                    active["max"] = pnl

                if active["max"] - pnl >= TRAIL:
                    qty = get_qty(sym)

                    if qty > 0:
                        exchange.create_market_order(
                            sym, "sell", qty,
                            params={"reduceOnly": True}
                        )

                        time.sleep(1)

                        if has_position():
                            qty = get_qty(sym)
                            if qty > 0:
                                exchange.create_market_order(
                                    sym, "sell", qty,
                                    params={"reduceOnly": True}
                                )

                    bot.send_message(CHAT_ID, f"🏁 EXIT {round(pnl,2)}")
                    active = None
                    continue

            # SL
            if not active["tp1"] and pnl <= -SL:
                qty = get_qty(sym)
                if qty > 0:
                    exchange.create_market_order(
                        sym, "sell", qty,
                        params={"reduceOnly": True}
                    )

                bot.send_message(CHAT_ID, f"🛑 SL {round(pnl,2)}")
                active = None

            time.sleep(1)

        except Exception as e:
            print("ERR:", e)
            time.sleep(2)

# ===== SCAN =====

def scan():
    while True:
        try:
            if has_position():
                time.sleep(1)
                continue

            for sym in get_symbols():

                if not trend_5m(sym):
                    continue

                if not trend_strength(sym):
                    continue

                if not not_pumped(sym):
                    continue

                if not structure_ok(sym):
                    continue

                if not buyer_strong(sym):
                    continue

                open_trade(sym)
                break

            time.sleep(2)

        except:
            time.sleep(2)

# ===== START =====

sync_position()

threading.Thread(target=manage, daemon=True).start()
threading.Thread(target=scan, daemon=True).start()

bot.send_message(CHAT_ID, "🤖 FINAL V2 AKTİF")

bot.infinity_polling()
