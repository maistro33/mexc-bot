import os
import time
import ccxt
import telebot
import threading
import random

LEV = 10
MARGIN = 3

TP1_USDT = 0.20
STEP_USDT = 0.10
TP1_RATIO = 0.6

HARD_SL_PCT = 0.025
SCAN_DELAY = 2

bot = telebot.TeleBot(os.getenv("TELE_TOKEN"))
CHAT_ID = os.getenv("MY_CHAT_ID")

exchange = ccxt.bitget({
    "apiKey": os.getenv("BITGET_API"),
    "secret": os.getenv("BITGET_SEC"),
    "password": "Berfin33",
    "options": {"defaultType": "swap"},
})

trade_state = {}

def safe(x):
    try:
        return float(x)
    except:
        return 0

# ================= NORMALIZE SYMBOL =================

def norm(sym):
    return sym.replace(":USDT","")

# ================= SYNC =================

def sync_positions():
    try:
        positions = exchange.fetch_positions()

        for p in positions:

            qty = safe(
                p.get("contracts") or
                p.get("positionAmt") or
                p.get("size")
            )

            if abs(qty) <= 0:
                continue

            sym = norm(p.get("symbol"))

            side = "long" if p.get("side") == "long" else "short"

            entry = safe(
                p.get("entryPrice") or
                p.get("avgPrice") or
                p.get("markPrice")
            )

            trade_state[sym] = {
                "direction": side,
                "tp1": False,
                "max_pnl": 0,
                "entry": entry
            }

            bot.send_message(CHAT_ID, f"🔄 SYNC {sym} {side}")

    except Exception as e:
        print("SYNC ERROR:", e)

# ================= BTC TREND =================

def btc_trend():
    try:
        candles = exchange.fetch_ohlcv("BTC/USDT:USDT", "5m", limit=20)
        closes = [c[4] for c in candles]
        ema = sum(closes[-10:]) / 10
        return "long" if closes[-1] > ema else "short"
    except:
        return None

# ================= COINS =================

def get_symbols():
    arr = []
    tickers = exchange.fetch_tickers()

    blacklist = ["DOGE","PEPE","SHIB","FLOKI","BONK","AAVE","UNI","LINK"]

    for sym, d in tickers.items():

        if "USDT" not in sym:
            continue

        s = sym.upper()

        if any(x in s for x in ["BTC","ETH","BNB","XRP","ADA","SOL"]):
            continue

        if any(x in s for x in blacklist):
            continue

        vol = safe(d.get("quoteVolume"))
        if vol < 1000000 or vol > 20000000:
            continue

        ask = safe(d.get("ask"))
        bid = safe(d.get("bid"))
        last = safe(d.get("last"))

        if last == 0:
            continue

        spread = (ask - bid) / last
        if spread > 0.004:
            continue

        arr.append(sym)

    return arr[:40]

# ================= STRUCTURE =================

def structure(sym):
    try:
        candles = exchange.fetch_ohlcv(sym, "1m", limit=5)
        highs = [c[2] for c in candles]
        lows = [c[3] for c in candles]

        if highs[-1] > highs[-2] and lows[-1] > lows[-2]:
            return "long"

        if highs[-1] < highs[-2] and lows[-1] < lows[-2]:
            return "short"

        return None
    except:
        return None

# ================= TREND STRENGTH =================

def strong_trend(sym):
    try:
        candles = exchange.fetch_ohlcv(sym, "1m", limit=5)
        closes = [c[4] for c in candles]

        change = (closes[-1] - closes[0]) / closes[0]

        if change > 0.004:
            return "long"
        if change < -0.004:
            return "short"

        return None
    except:
        return None

# ================= FILTERS =================

def volatility(sym):
    try:
        candles = exchange.fetch_ohlcv(sym, "1m", limit=5)
        ranges = [(c[2] - c[3]) / c[4] for c in candles]
        return sum(ranges) / len(ranges) > 0.0015
    except:
        return False

def pullback(sym, direction):
    try:
        candles = exchange.fetch_ohlcv(sym, "1m", limit=3)
        c2, c3 = candles[-2], candles[-1]

        if direction == "long":
            return c3[4] <= c2[4]
        else:
            return c3[4] >= c2[4]
    except:
        return False

def momentum(sym):
    candles = exchange.fetch_ohlcv(sym, "1m", limit=3)
    return (candles[-1][4] - candles[-2][4]) / candles[-2][4]

def volume(sym):
    candles = exchange.fetch_ohlcv(sym, "5m", limit=5)
    avg = sum(c[5] for c in candles[:-1]) / 4
    return candles[-1][5] > avg * 1.1

# ================= RISK =================

def get_qty(sym):
    try:
        pos = exchange.fetch_positions([sym])
        if not pos:
            return 0
        return safe(pos[0]["contracts"])
    except:
        return 0

def current_direction_count(direction):
    count = 0
    positions = exchange.fetch_positions()
    for p in positions:
        if safe(p.get("contracts")) > 0:
            side = "long" if p["side"] == "long" else "short"
            if side == direction:
                count += 1
    return count

# ================= TRADE =================

def open_trade(sym, direction):
    try:
        sym_n = norm(sym)

        if get_qty(sym) > 0:
            return

        if current_direction_count(direction) >= 1:
            return

        price = exchange.fetch_ticker(sym)["last"]
        qty = (MARGIN * LEV) / price

        exchange.set_leverage(LEV, sym)

        side = "buy" if direction == "long" else "sell"
        exchange.create_market_order(sym, side, qty)

        trade_state[sym_n] = {
            "direction": direction,
            "tp1": False,
            "max_pnl": 0,
            "entry": price
        }

        bot.send_message(CHAT_ID, f"🚀 {sym_n} {direction} {round(price,5)}")

    except Exception as e:
        print("TRADE ERROR:", e)

# ================= MANAGE =================

def manage():
    while True:
        try:
            positions = exchange.fetch_positions()

            for p in positions:
                qty = safe(p.get("contracts") or p.get("size"))
                if abs(qty) <= 0:
                    continue

                sym = norm(p.get("symbol"))

                if sym not in trade_state:
                    continue

                state = trade_state[sym]
                pnl = safe(p.get("unrealizedPnl"))
                entry = state["entry"]
                price = exchange.fetch_ticker(p.get("symbol"))["last"]

                direction = state["direction"]
                side = "sell" if direction == "long" else "buy"

                # HARD SL
                if direction == "long" and price <= entry * (1 - HARD_SL_PCT):
                    exchange.create_market_order(p.get("symbol"), side, qty, params={"reduceOnly": True})
                    trade_state.pop(sym)
                    bot.send_message(CHAT_ID, f"🛑 SL {sym}")
                    continue

                if direction == "short" and price >= entry * (1 + HARD_SL_PCT):
                    exchange.create_market_order(p.get("symbol"), side, qty, params={"reduceOnly": True})
                    trade_state.pop(sym)
                    bot.send_message(CHAT_ID, f"🛑 SL {sym}")
                    continue

                if pnl > state["max_pnl"]:
                    state["max_pnl"] = pnl

                if not state["tp1"] and pnl >= TP1_USDT:
                    exchange.create_market_order(p.get("symbol"), side, qty * TP1_RATIO, params={"reduceOnly": True})
                    state["tp1"] = True
                    bot.send_message(CHAT_ID, f"💰 TP1 {sym}")

                if state["tp1"] and state["max_pnl"] - pnl >= STEP_USDT:
                    exchange.create_market_order(p.get("symbol"), side, qty, params={"reduceOnly": True})
                    trade_state.pop(sym)
                    bot.send_message(CHAT_ID, f"🏁 EXIT {sym}")

            time.sleep(2)

        except Exception as e:
            print("MANAGE ERROR:", e)
            time.sleep(5)

# ================= SCANNER =================

def scanner():
    while True:
        try:
            market_dir = btc_trend()

            positions = exchange.fetch_positions()
            active = sum(1 for p in positions if safe(p.get("contracts")) > 0)

            if active >= 2:
                time.sleep(2)
                continue

            symbols = get_symbols()
            random.shuffle(symbols)

            for sym in symbols:
                try:
                    s = structure(sym)
                    strong = strong_trend(sym)

                    if not s:
                        continue

                    if strong and s != strong:
                        continue

                    if market_dir and s != market_dir:
                        continue

                    if not volatility(sym):
                        continue

                    if not pullback(sym, s):
                        continue

                    if volume(sym):
                        m = momentum(sym)

                        if s == "long" and m > -0.0005:
                            open_trade(sym, "long")
                            break

                        if s == "short" and m < 0.0005:
                            open_trade(sym, "short")
                            break

                except:
                    continue

            time.sleep(SCAN_DELAY)

        except Exception as e:
            print("SCAN ERROR:", e)
            time.sleep(5)

# ================= START =================

print("🔥 FINAL STABLE BOT")

sync_positions()

threading.Thread(target=manage, daemon=True).start()
threading.Thread(target=scanner, daemon=True).start()

bot.send_message(CHAT_ID, "🤖 BOT AKTİF FINAL")

bot.infinity_polling()
