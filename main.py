import os
import time
import ccxt
import telebot
import threading
import random

LEV = 10
MARGIN = 3

TP1_USDT = 0.60
TRAIL_START = 0.70
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
used_coins = set()

# ================= LOAD =================

def load_positions():
    global active_trades
    try:
        positions = exchange.fetch_positions()

        for p in positions:
            contracts = float(p.get('contracts', 0))
            if contracts == 0:
                continue

            side = "long" if contracts > 0 else "short"

            sym = p['symbol']

            active_trades.append({
                "symbol": sym,
                "qty": abs(contracts),
                "entry": float(p['entryPrice']),
                "tp1": False,
                "max_pnl": 0,
                "remaining_qty": abs(contracts),
                "side": side
            })

            used_coins.add(sym)

    except:
        pass

# ================= PRICE =================

def get_price(sym):
    try:
        return exchange.fetch_ticker(sym)["last"]
    except:
        return 0

# ================= POSITION =================

def position_open(sym):
    try:
        positions = exchange.fetch_positions()
        for p in positions:
            if sym.split("/")[0] in p['symbol'] and float(p.get('contracts', 0)) != 0:
                return True
        return False
    except:
        return True

# ================= TREND =================

def trend_direction_4h(sym):
    try:
        c = exchange.fetch_ohlcv(sym, "4h", limit=20)
        closes = [x[4] for x in c]
        avg = sum(closes)/len(closes)
        return "long" if closes[-1] > avg else "short"
    except:
        return None

def trend_5m(sym):
    try:
        c = exchange.fetch_ohlcv(sym, "5m", limit=20)
        closes = [x[4] for x in c]
        return closes[-1] > sum(closes)/len(closes)
    except:
        return False

# ================= FILTERS =================

def volume_spike(sym):
    try:
        c = exchange.fetch_ohlcv(sym, "1m", limit=10)
        v = [x[5] for x in c]
        return v[-1] > (sum(v[:-1])/len(v[:-1])) * 1.5
    except:
        return False

def dip_reversal(sym):
    try:
        c = exchange.fetch_ohlcv(sym, "1m", limit=6)
        lows = [x[3] for x in c]
        closes = [x[4] for x in c]
        return lows[-1] > lows[-5] and closes[-1] > closes[-2]
    except:
        return False

def too_late(sym):
    try:
        c = exchange.fetch_ohlcv(sym, "1m", limit=15)
        closes = [x[4] for x in c]
        return (closes[-1] - min(closes)) / min(closes) > 0.02
    except:
        return True

def first_move(sym):
    try:
        c = exchange.fetch_ohlcv(sym, "1m", limit=20)
        closes = [x[4] for x in c]
        return (closes[-1] - min(closes)) / min(closes) < 0.015
    except:
        return False

def ultra_entry(sym):
    try:
        c = exchange.fetch_ohlcv(sym, "1m", limit=4)
        return c[-2][4] > c[-2][1]
    except:
        return False

# ================= SNIPER AKTİF =================

def strong_dip(sym):
    try:
        c = exchange.fetch_ohlcv(sym, "1m", limit=10)
        lows = [x[3] for x in c]
        closes = [x[4] for x in c]

        return lows[-1] <= min(lows) * 1.002 and closes[-1] > closes[-2]
    except:
        return False

def strong_top(sym):
    try:
        c = exchange.fetch_ohlcv(sym, "1m", limit=10)
        highs = [x[2] for x in c]
        closes = [x[4] for x in c]

        return highs[-1] >= max(highs) * 0.998 and closes[-1] < closes[-2]
    except:
        return False

def short_pullback(sym):
    try:
        c = exchange.fetch_ohlcv(sym, "1m", limit=6)
        closes = [x[4] for x in c]
        return closes[-1] > closes[-2]
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

        if 1_000_000 < vol < 6_000_000:
            arr.append(sym)

    random.shuffle(arr)
    return arr

# ================= TRADE =================

def open_trade(sym, side):
    global active_trades, used_coins

    try:
        price = get_price(sym)
        qty = (MARGIN * LEV) / price

        exchange.set_leverage(LEV, sym)

        order_side = "buy" if side == "long" else "sell"

        exchange.create_market_order(sym, order_side, qty)

        active_trades.append({
            "symbol": sym,
            "qty": qty,
            "entry": price,
            "tp1": False,
            "max_pnl": 0,
            "remaining_qty": qty,
            "side": side
        })

        used_coins.add(sym)

        bot.send_message(CHAT_ID, f"🚀 {side.upper()} {sym}")

    except Exception as e:
        print(e)

# ================= MANAGE =================

def manage():
    global active_trades

    while True:
        try:
            for trade in active_trades[:]:

                sym = trade["symbol"]
                side = trade["side"]

                if not position_open(sym):
                    active_trades.remove(trade)
                    continue

                price = get_price(sym)

                if side == "long":
                    pnl = (price - trade["entry"]) * trade["qty"]
                    close_side = "sell"
                else:
                    pnl = (trade["entry"] - price) * trade["qty"]
                    close_side = "buy"

                if pnl > trade["max_pnl"]:
                    trade["max_pnl"] = pnl

                if not trade["tp1"] and pnl >= TP1_USDT:
                    close_qty = trade["qty"] * 0.5

                    exchange.create_market_order(
                        sym, close_side, close_qty, params={"reduceOnly": True}
                    )

                    trade["tp1"] = True
                    trade["remaining_qty"] = trade["qty"] - close_qty

                    bot.send_message(CHAT_ID, f"💰 TP1 {sym} {round(pnl,2)}")

                if trade["tp1"] and pnl >= TRAIL_START:
                    if trade["max_pnl"] - pnl >= STEP:
                        exchange.create_market_order(
                            sym, close_side, trade["remaining_qty"],
                            params={"reduceOnly": True}
                        )

                        bot.send_message(CHAT_ID, f"🏁 EXIT {sym} {round(pnl*0.7,2)}")
                        active_trades.remove(trade)

                if pnl <= -SL_USDT:
                    exchange.create_market_order(
                        sym, close_side, trade["qty"],
                        params={"reduceOnly": True}
                    )

                    bot.send_message(CHAT_ID, f"🛑 SL {sym} {round(pnl,2)}")
                    active_trades.remove(trade)

            time.sleep(1)

        except Exception as e:
            print("MANAGE ERROR:", e)
            time.sleep(2)

# ================= SCANNER =================

def scanner():
    global active_trades, used_coins

    while True:
        try:
            if len(active_trades) >= MAX_TRADES:
                time.sleep(1)
                continue

            coins = get_coins()

            for sym in coins:

                if any(t["symbol"] == sym for t in active_trades):
                    continue

                if sym in used_coins:
                    continue

                direction = trend_direction_4h(sym)
                if not direction:
                    continue

                if direction == "long":
                    if not trend_5m(sym):
                        continue
                    if not strong_dip(sym):
                        continue
                else:
                    if trend_5m(sym):
                        continue
                    if not short_pullback(sym):
                        continue
                    if not strong_top(sym):
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

                open_trade(sym, direction)
                break

            time.sleep(2)

        except Exception as e:
            print("SCAN ERROR:", e)
            time.sleep(2)

# ================= START =================

load_positions()

threading.Thread(target=manage, daemon=True).start()
threading.Thread(target=scanner, daemon=True).start()

bot.send_message(CHAT_ID, "🤖 FINAL V16 AKTİF (SNIPER + AKTİF)")

bot.infinity_polling()
