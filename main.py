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

MAX_TRADES = 2

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

active_trades = []

# ================= LOAD =================

def load_positions():
    global active_trades
    try:
        positions = exchange.fetch_positions()
        for p in positions:
            if float(p.get('contracts', 0)) > 0:

                sym = p['symbol']

                active_trades.append({
                    "symbol": sym,
                    "qty": float(p['contracts']),
                    "tp1": False,
                    "max_pnl": 0,
                    "remaining_qty": float(p['contracts'])
                })

        print("Açık işlemler yüklendi:", len(active_trades))

    except:
        pass

# ================= PNL =================

def get_pnl(sym):
    try:
        positions = exchange.fetch_positions()
        for p in positions:
            if sym.split("/")[0] in p['symbol']:
                return float(p.get('unrealizedPnl', 0))
    except:
        return 0
    return 0

# ================= POSITION =================

def position_open(sym):
    try:
        positions = exchange.fetch_positions()
        for p in positions:
            if sym.split("/")[0] in p['symbol'] and float(p.get('contracts', 0)) > 0:
                return True
        return False
    except:
        return True

# ================= FILTERS =================

def trend_ok(sym):
    try:
        candles = exchange.fetch_ohlcv(sym, "5m", limit=20)
        closes = [c[4] for c in candles]
        return closes[-1] > sum(closes[-20:])/20
    except:
        return False

def volume_spike(sym):
    try:
        candles = exchange.fetch_ohlcv(sym, "1m", limit=10)
        vols = [c[5] for c in candles]
        return vols[-1] > (sum(vols[:-1])/len(vols[:-1])) * 1.5
    except:
        return False

def dip_reversal(sym):
    try:
        candles = exchange.fetch_ohlcv(sym, "1m", limit=6)
        lows = [c[3] for c in candles]
        closes = [c[4] for c in candles]
        return lows[-1] > lows[-5] and closes[-1] > closes[-2]
    except:
        return False

def too_late(sym):
    try:
        candles = exchange.fetch_ohlcv(sym, "1m", limit=15)
        closes = [c[4] for c in candles]
        return (closes[-1] - min(closes)) / min(closes) > 0.02
    except:
        return True

def first_move(sym):
    try:
        candles = exchange.fetch_ohlcv(sym, "1m", limit=20)
        closes = [c[4] for c in candles]
        return (closes[-1] - min(closes)) / min(closes) < 0.012
    except:
        return False

def ultra_entry(sym):
    try:
        candles = exchange.fetch_ohlcv(sym, "1m", limit=4)
        return candles[-2][4] > candles[-2][1] and candles[-1][4] > candles[-2][4]
    except:
        return False

# ================= COINS =================

def get_coins():
    tickers = exchange.fetch_tickers()
    arr = []

    blacklist = ["BTC","ETH","BNB","XRP","ADA","SOL"]

    for sym, d in tickers.items():
        if "USDT" not in sym:
            continue
        if any(x in sym for x in blacklist):
            continue

        vol = float(d.get("quoteVolume") or 0)

        if 1_000_000 < vol < 3_000_000:
            arr.append(sym)

    random.shuffle(arr)
    return arr

# ================= TRADE =================

def open_trade(sym):
    global active_trades

    try:
        price = exchange.fetch_ticker(sym)["last"]
        qty = (MARGIN * LEV) / price

        exchange.set_leverage(LEV, sym)
        exchange.create_market_order(sym, "buy", qty)

        active_trades.append({
            "symbol": sym,
            "qty": qty,
            "tp1": False,
            "max_pnl": 0,
            "remaining_qty": qty
        })

        bot.send_message(CHAT_ID, f"🚀 LONG {sym}")

    except Exception as e:
        print(e)

# ================= MANAGE =================

def manage():
    global active_trades

    while True:
        try:
            for trade in active_trades[:]:

                sym = trade["symbol"]

                if not position_open(sym):
                    active_trades.remove(trade)
                    continue

                pnl = get_pnl(sym)

                if pnl > trade["max_pnl"]:
                    trade["max_pnl"] = pnl

                side = "sell"

                # TP1
                if not trade["tp1"] and pnl >= TP1_USDT:
                    close_qty = trade["qty"] * 0.5

                    exchange.create_market_order(sym, side, close_qty, params={"reduceOnly": True})

                    trade["tp1"] = True
                    trade["remaining_qty"] = trade["qty"] - close_qty

                    bot.send_message(CHAT_ID, f"💰 TP1 {sym}")

                # TRAILING
                if trade["tp1"] and pnl >= TRAIL_START:
                    if trade["max_pnl"] - pnl >= STEP:
                        exchange.create_market_order(sym, side, trade["remaining_qty"], params={"reduceOnly": True})
                        bot.send_message(CHAT_ID, f"🏁 EXIT {sym}")
                        active_trades.remove(trade)

                # SL
                if pnl <= -SL_USDT:
                    exchange.create_market_order(sym, side, trade["qty"], params={"reduceOnly": True})
                    bot.send_message(CHAT_ID, f"🛑 SL {sym}")
                    active_trades.remove(trade)

            time.sleep(1)

        except Exception as e:
            print("MANAGE ERROR:", e)
            time.sleep(2)

# ================= SCANNER =================

def scanner():
    global active_trades

    while True:
        try:
            if len(active_trades) >= MAX_TRADES:
                time.sleep(1)
                continue

            coins = get_coins()

            for sym in coins:

                if any(t["symbol"] == sym for t in active_trades):
                    continue

                if not trend_ok(sym):
                    continue

                if not volume_spike(sym):
                    continue

                if not dip_reversal(sym):
                    continue

                if too_late(sym):
                    continue

                if not first_move(sym):
                    continue

                if not ultra_entry(sym):
                    continue

                open_trade(sym)
                break

            time.sleep(2)

        except Exception as e:
            print("SCAN ERROR:", e)
            time.sleep(2)

# ================= START =================

load_positions()

threading.Thread(target=manage, daemon=True).start()
threading.Thread(target=scanner, daemon=True).start()

bot.send_message(CHAT_ID, "🤖 FINAL V7 (2 TRADE) AKTİF")

bot.infinity_polling()
