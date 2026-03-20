import os
import time
import ccxt
import telebot
import threading
import random

LEV = 10
MARGIN = 3

MAX_POSITIONS = 4

TP1_PCT = 0.012
STEP_PCT = 0.010
TP1_RATIO = 0.50

MIN_VOLUME = 1500000
MAX_SPREAD = 0.003
SCAN_DELAY = 6

SL_PCT = 0.025

API_DELAY = 0.2

bot = telebot.TeleBot(os.getenv("TELE_TOKEN"))
CHAT_ID = os.getenv("MY_CHAT_ID")

exchange = ccxt.bitget({
    "apiKey": os.getenv("BITGET_API"),
    "secret": os.getenv("BITGET_SEC"),
    "password": "Berfin33",
    "options": {"defaultType": "swap"},
    "enableRateLimit": True
})

markets = exchange.load_markets()
SYMBOLS = [s for s in markets if markets[s]["swap"] and "USDT" in s][:200]

trade_state = {}
cooldown = {}
COOLDOWN_TIME = 900


def safe_api_call(func,*args,**kwargs):
    for _ in range(5):
        try:
            time.sleep(API_DELAY)
            return func(*args,**kwargs)
        except:
            time.sleep(2)
    return None


def safe(x):
    try:
        return float(x)
    except:
        return 0


def get_qty(sym):
    pos = safe_api_call(exchange.fetch_positions,[sym])
    if not pos:
        return 0
    return safe(pos[0]["contracts"])


def btc_trend():
    candles = safe_api_call(exchange.fetch_ohlcv,"BTC/USDT:USDT","1h",limit=50)
    if not candles:
        return "neutral"

    closes=[c[4] for c in candles]
    ema=sum(closes[-20:])/20

    return "bull" if closes[-1] > ema else "bear"


# 🔥 BREAKOUT
def breakout_entry(sym):
    candles = safe_api_call(exchange.fetch_ohlcv, sym, "5m", limit=5)
    if not candles:
        return None

    highs = [c[2] for c in candles[:-1]]
    lows = [c[3] for c in candles[:-1]]
    last = candles[-1][4]

    if last > max(highs):
        return "long"

    if last < min(lows):
        return "short"

    return None


# 🔥 GÜÇLÜ MUM
def strong_candle(sym):
    candles = safe_api_call(exchange.fetch_ohlcv, sym, "5m", limit=2)
    if not candles:
        return False

    body = abs(candles[-1][4] - candles[-1][1])
    total = candles[-1][2] - candles[-1][3]

    if total == 0:
        return False

    return body / total > 0.55


# 🔥 MOMENTUM (güçlü yaptık)
def momentum(sym):
    candles = safe_api_call(exchange.fetch_ohlcv, sym, "1m", limit=3)
    if not candles:
        return False

    change = (candles[-1][4] - candles[-2][4]) / candles[-2][4]
    return abs(change) > 0.0025


def volume_spike(sym):
    candles = safe_api_call(exchange.fetch_ohlcv, sym, "5m", limit=6)
    if not candles:
        return False

    vols=[c[5] for c in candles]
    avg=sum(vols[:-1])/5

    return vols[-1] > avg * 1.2


def open_trade(sym,direction,label):
    if get_qty(sym) > 0:
        return

    ticker = safe_api_call(exchange.fetch_ticker,sym)
    if not ticker:
        return

    if ticker["quoteVolume"] < MIN_VOLUME:
        return

    spread = (ticker["ask"] - ticker["bid"]) / ticker["last"]
    if spread > MAX_SPREAD:
        return

    price = ticker["last"]
    qty = (MARGIN * LEV) / price
    qty = float(exchange.amount_to_precision(sym,qty))

    exchange.set_leverage(LEV,sym)

    side = "buy" if direction=="long" else "sell"
    exchange.create_market_order(sym,side,qty)

    trade_state[sym]={
        "entry":price,
        "direction":direction,
        "tp1":False,
        "step":0,
        "trail_stop":price
    }

    cooldown[sym]=time.time()

    bot.send_message(CHAT_ID,f"🚀 {label} {sym} {direction}")


def manage():
    while True:
        try:
            positions = safe_api_call(exchange.fetch_positions)
            if not positions:
                time.sleep(2)
                continue

            for p in positions:
                qty = safe(p.get("contracts"))
                if qty <= 0:
                    continue

                sym = p["symbol"]
                if sym not in trade_state:
                    continue

                state = trade_state[sym]

                ticker = safe_api_call(exchange.fetch_ticker,sym)
                if not ticker:
                    continue

                price = ticker["last"]
                entry = state["entry"]
                direction = state["direction"]

                side = "sell" if direction=="long" else "buy"

                # SL
                if (direction=="long" and price <= entry*(1-SL_PCT)) or \
                   (direction=="short" and price >= entry*(1+SL_PCT)):

                    exchange.create_market_order(sym,side,get_qty(sym),params={"reduceOnly":True})
                    trade_state.pop(sym)
                    bot.send_message(CHAT_ID,f"🛑 SL {sym}")
                    continue

                # TP1
                if not state["tp1"]:
                    if (direction=="long" and price>=entry*(1+TP1_PCT)) or \
                       (direction=="short" and price<=entry*(1-TP1_PCT)):

                        exchange.create_market_order(sym,side,get_qty(sym)*TP1_RATIO,params={"reduceOnly":True})
                        state["tp1"]=True
                        state["trail_stop"]=entry

                else:
                    step_price = entry * (1 + STEP_PCT * state["step"]) if direction=="long" else entry * (1 - STEP_PCT * state["step"])

                    if (direction=="long" and price>=step_price) or (direction=="short" and price<=step_price):
                        state["step"] += 1
                        state["trail_stop"] = entry * (1 + STEP_PCT * (state["step"]-1)) if direction=="long" else entry * (1 - STEP_PCT * (state["step"]-1))

                    if (direction=="long" and price <= state["trail_stop"]) or \
                       (direction=="short" and price >= state["trail_stop"]):

                        exchange.create_market_order(sym,side,get_qty(sym),params={"reduceOnly":True})
                        trade_state.pop(sym)
                        bot.send_message(CHAT_ID,f"🏁 EXIT {sym}")

            time.sleep(3)

        except:
            time.sleep(5)


def scanner():
    while True:
        try:
            random.shuffle(SYMBOLS)

            btc = btc_trend()

            positions = safe_api_call(exchange.fetch_positions)
            active = sum(1 for p in positions if safe(p.get("contracts"))>0)

            if active >= MAX_POSITIONS:
                time.sleep(SCAN_DELAY)
                continue

            for sym in SYMBOLS:

                if sym in cooldown and time.time()-cooldown[sym] < COOLDOWN_TIME:
                    continue

                if get_qty(sym) > 0:
                    continue

                # 🔥 BREAKOUT (EN ÖNCE)
                direction = breakout_entry(sym)
                if direction and strong_candle(sym):
                    open_trade(sym,direction,"breakout")
                    break

                # 🔥 MOMENTUM ENTRY
                if momentum(sym) and volume_spike(sym):

                    if btc == "bull":
                        open_trade(sym,"long","momentum")
                        break

                    elif btc == "bear":
                        open_trade(sym,"short","momentum")
                        break

            time.sleep(SCAN_DELAY)

        except:
            time.sleep(10)


print("BOT START")

threading.Thread(target=manage,daemon=True).start()
threading.Thread(target=scanner,daemon=True).start()

bot.send_message(CHAT_ID,"🤖 BOT AKTİF")

bot.infinity_polling()
