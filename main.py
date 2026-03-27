import os
import time
import ccxt
import telebot
import threading
import random

LEV = 10
MARGIN = 3

TP1_USDT = 0.30
STEP_TRIGGER = 0.20
TRAIL_STEP = 0.20
SL_USDT = 0.30

SCAN_LIMIT = 50

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

# ================= POSITION =================

def has_open_position():
    try:
        positions = exchange.fetch_positions()
        for p in positions:
            qty = safe(p.get("contracts") or p.get("size"))
            if abs(qty) > 0:
                return True
        return False
    except:
        return False

def get_real_pnl(sym):
    try:
        positions = exchange.fetch_positions()
        for p in positions:
            psym = p.get("symbol","")
            if sym.replace("/", "").replace(":USDT","") in psym:
                return float(p.get("unrealizedPnl") or 0)
        return 0
    except:
        return 0

# ================= ENTRY =================

def overextended(sym):
    try:
        candles = exchange.fetch_ohlcv(sym, "1m", limit=6)
        closes = [c[4] for c in candles]
        move = (closes[-1] - closes[-5]) / closes[-5]
        return move > 0.018
    except:
        return True

def trend_ok(sym):
    try:
        candles = exchange.fetch_ohlcv(sym, "1m", limit=20)
        closes = [c[4] for c in candles]
        ema = sum(closes[-10:]) / 10
        return closes[-1] > ema
    except:
        return False

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

# ================= SYMBOL =================

def get_symbols():
    tickers = exchange.fetch_tickers()
    markets = exchange.load_markets()
    arr = []

    for sym, d in tickers.items():

        if "USDT" not in sym:
            continue

        vol = safe(d.get("quoteVolume"))
        if vol < 1000000 or vol > 5000000:
            continue

        market = markets.get(sym)
        if market:
            mtype = str(market.get("type","")).lower()
            if "stock" in mtype or "index" in mtype:
                continue

        arr.append(sym)

    random.shuffle(arr)
    return arr[:SCAN_LIMIT]

# ================= TRADE =================

def open_trade(sym):
    global active_trade

    if active_trade or has_open_position():
        return

    try:
        price = exchange.fetch_ticker(sym)["last"]
        qty = (MARGIN * LEV) / price

        exchange.set_leverage(LEV, sym)
        exchange.create_market_order(sym, "buy", qty)

        active_trade = {
            "symbol": sym,
            "tp1": False,
            "max_pnl": 0,
            "last_step": 0
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
            pnl = get_real_pnl(sym)

            side = "sell"

            # STEP (SADECE YUKARI)
            if pnl > active_trade["last_step"] + STEP_TRIGGER:
                active_trade["last_step"] = pnl
                bot.send_message(CHAT_ID, f"📈 STEP {round(pnl,2)} USDT")

            # TP1
            if not active_trade["tp1"] and pnl >= TP1_USDT:

                positions = exchange.fetch_positions()
                real_qty = 0

                for p in positions:
                    if sym.replace("/", "") in p.get("symbol",""):
                        real_qty = abs(float(p.get("contracts") or p.get("size") or 0))

                exchange.create_market_order(sym, side, round(real_qty*0.5,6), params={"reduceOnly": True})

                active_trade["tp1"] = True
                active_trade["max_pnl"] = pnl

                bot.send_message(CHAT_ID, f"💰 TP1 {round(pnl,2)} USDT")

            # TRAILING
            if active_trade["tp1"]:

                if pnl > active_trade["max_pnl"]:
                    active_trade["max_pnl"] = pnl

                if active_trade["max_pnl"] - pnl >= TRAIL_STEP:

                    positions = exchange.fetch_positions()
                    real_qty = 0

                    for p in positions:
                        if sym.replace("/", "") in p.get("symbol",""):
                            real_qty = abs(float(p.get("contracts") or p.get("size") or 0))

                    if real_qty > 0:
                        exchange.create_market_order(sym, side, real_qty, params={"reduceOnly": True})

                    bot.send_message(CHAT_ID, f"🏁 EXIT {round(pnl,2)} USDT")
                    active_trade = None
                    continue

            # SL (TP1 öncesi)
            if not active_trade["tp1"] and pnl <= -SL_USDT:

                positions = exchange.fetch_positions()
                real_qty = 0

                for p in positions:
                    if sym.replace("/", "") in p.get("symbol",""):
                        real_qty = abs(float(p.get("contracts") or p.get("size") or 0))

                exchange.create_market_order(sym, side, real_qty, params={"reduceOnly": True})

                bot.send_message(CHAT_ID, f"🛑 SL {round(pnl,2)} USDT")
                active_trade = None

            time.sleep(1)

        except Exception as e:
            print("ERR:", e)
            time.sleep(2)

# ================= SCANNER =================

def scanner():
    while True:
        try:
            if active_trade or has_open_position():
                time.sleep(1)
                continue

            symbols = get_symbols()

            for sym in symbols:

                if overextended(sym):
                    continue

                if not trend_ok(sym):
                    continue

                if not pullback(sym):
                    continue

                if not breakout(sym):
                    continue

                open_trade(sym)
                break

            time.sleep(2)

        except:
            time.sleep(2)

# ================= START =================

threading.Thread(target=manage, daemon=True).start()
threading.Thread(target=scanner, daemon=True).start()

bot.send_message(CHAT_ID, "🤖 BOT V6.6 (PNL FIX) AKTİF")
bot.infinity_polling()
