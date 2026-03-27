import os
import time
import ccxt
import telebot
import threading
import random

LEV = 10
MARGIN = 3

TP1_USDT = 0.30
STEP_SIZE = 0.20
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

# ================= OPEN POSITION CHECK =================

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

# ================= SYNC =================

def check_open_position():
    global active_trade
    try:
        positions = exchange.fetch_positions()
        for p in positions:
            qty = safe(p.get("contracts") or p.get("size"))
            if abs(qty) <= 0:
                continue

            sym = p.get("symbol")
            entry = safe(p.get("entryPrice") or p.get("avgPrice"))

            active_trade = {
                "symbol": sym,
                "entry": entry,
                "qty": qty,
                "tp1": False,
                "max_pnl": 0,
                "remaining_qty": qty,
                "last_step": 0
            }

            bot.send_message(CHAT_ID, f"🔄 SYNC {sym}")
            return
    except:
        pass

# ================= TREND =================

def trend_ok(sym):
    try:
        candles = exchange.fetch_ohlcv(sym, "1m", limit=20)
        closes = [c[4] for c in candles]
        ema = sum(closes[-10:]) / 10
        return closes[-1] > ema
    except:
        return False

# ================= COINS =================

def get_symbols():
    tickers = exchange.fetch_tickers()
    markets = exchange.load_markets()

    arr = []

    blacklist = [
        "BTC","ETH","BNB","XRP","ADA","SOL",
        "DOGE","PEPE","SHIB",
        "AVAX","LINK","UNI","LTC","ATOM","ETC","FIL"
    ]

    stock_keywords = [
        "ETF","STOCK","INDEX",
        "SPY","QQQ","DOW","NDX",
        "AAPL","TSLA","NVDA","META","AMZN","GOOG","MSFT",
        "MARA","COIN","RIOT","PLTR","BABA",
        "US30","NAS100","SPX","DJI"
    ]

    for sym, d in tickers.items():

        if "USDT" not in sym:
            continue

        s = sym.upper()

        if any(x in s for x in blacklist):
            continue

        if any(k in s for k in stock_keywords):
            continue

        market = markets.get(sym)
        if market:
            mtype = str(market.get("type", "")).lower()
            if "stock" in mtype or "index" in mtype:
                continue

        vol = safe(d.get("quoteVolume"))
        if vol < 1000000 or vol > 5000000:
            continue

        high = safe(d.get("high"))
        low = safe(d.get("low"))

        if low == 0:
            continue

        volatility = (high - low) / low
        if volatility < 0.03:
            continue

        arr.append(sym)

    random.shuffle(arr)
    return arr[:SCAN_LIMIT]

# ================= SETUP =================

def pullback(sym):
    try:
        candles = exchange.fetch_ohlcv(sym, "1m", limit=4)
        closes = [c[4] for c in candles]
        return closes[-2] < closes[-3]
    except:
        return False

def entry_filter(sym):
    try:
        candles = exchange.fetch_ohlcv(sym, "1m", limit=4)
        closes = [c[4] for c in candles]

        move = (closes[-1] - closes[-4]) / closes[-4]

        if move > 0.01:
            return False

        return True
    except:
        return False

def strong_breakout(sym):
    try:
        candles = exchange.fetch_ohlcv(sym, "1m", limit=3)

        open_price = candles[-1][1]
        close_price = candles[-1][4]
        high = candles[-1][2]

        body = close_price - open_price
        wick = high - close_price

        if body <= 0:
            return False

        if wick > body:
            return False

        return True

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

    if active_trade or has_open_position():
        return

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
            "remaining_qty": qty,
            "last_step": 0
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

            pnl_usdt = (price - entry) * qty
            side = "sell"

            # STEP
            while pnl_usdt >= active_trade["last_step"] + STEP_SIZE:
                active_trade["last_step"] += STEP_SIZE
                bot.send_message(CHAT_ID, f"📈 STEP {round(active_trade['last_step'],2)} USDT")

            # TP1
            if not active_trade["tp1"] and pnl_usdt >= TP1_USDT:

                close_qty = round(qty * 0.5, 6)

                exchange.create_market_order(
                    sym, side, close_qty, params={"reduceOnly": True}
                )

                active_trade["tp1"] = True
                active_trade["remaining_qty"] = max(qty - close_qty, 0)
                active_trade["max_pnl"] = max(pnl_usdt, TP1_USDT)

                bot.send_message(CHAT_ID, f"💰 TP1 {sym} +0.30 USDT")

            # TRAILING
            if active_trade["tp1"]:

                if pnl_usdt > active_trade["max_pnl"]:
                    active_trade["max_pnl"] = pnl_usdt

                drawdown = active_trade["max_pnl"] - pnl_usdt

                if drawdown >= TRAIL_STEP:

                    positions = exchange.fetch_positions()
                    real_qty = 0

                    for p in positions:
                        psym = p.get("symbol","")
                        if sym.replace("/", "").replace(":USDT","") in psym:
                            real_qty = abs(float(p.get("contracts") or p.get("size", 0)))

                    if real_qty > 0:
                        exchange.create_market_order(
                            sym,
                            side,
                            real_qty,
                            params={"reduceOnly": True}
                        )

                    bot.send_message(CHAT_ID, f"🏁 EXIT {sym} {round(pnl_usdt,2)} USDT")
                    active_trade = None
                    continue

            # SL (sadece TP1 öncesi)
            if not active_trade["tp1"] and pnl_usdt <= -SL_USDT:

                exchange.create_market_order(
                    sym, side, qty, params={"reduceOnly": True}
                )

                bot.send_message(CHAT_ID, f"🛑 SL {sym} {round(pnl_usdt,2)} USDT")
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
            if active_trade or has_open_position():
                time.sleep(1)
                continue

            symbols = get_symbols()

            for sym in symbols:

                if not trend_ok(sym):
                    continue

                if not pullback(sym):
                    continue

                if not entry_filter(sym):
                    continue

                if not breakout(sym):
                    continue

                if not strong_breakout(sym):
                    continue

                open_trade(sym)
                break

            time.sleep(2)

        except Exception as e:
            print("SCAN ERROR:", e)
            time.sleep(2)

# ================= START =================

print("🔥 FINAL V8.3 LOCKED")

check_open_position()

threading.Thread(target=manage, daemon=True).start()
threading.Thread(target=scanner, daemon=True).start()

bot.send_message(CHAT_ID, "🤖 BOT AKTİF V8.3 (SAFE MODE)")

bot.infinity_polling()
