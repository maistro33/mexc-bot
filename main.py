import os
import time
import ccxt
import telebot
import threading
import random

LEV = 10
MARGIN = 3

MAX_POSITIONS = 4

TP1_PCT = 0.009
STEP_PCT = 0.008
TP1_RATIO = 0.50

MIN_VOLUME = 2000000
MAX_SPREAD = 0.003
SCAN_DELAY = 6

TIMEOUT = 21600
SL_PCT = 0.025

# ===== NEW =====
TP_TRAIL = 0.005
loss_streak = 0
trade_results = []

bot = telebot.TeleBot(os.getenv("TELE_TOKEN"))
CHAT_ID = os.getenv("MY_CHAT_ID")

exchange = ccxt.bitget({
    "apiKey": os.getenv("BITGET_API"),
    "secret": os.getenv("BITGET_SEC"),
    "password": os.getenv("BITGET_PASS"),
    "options": {"defaultType": "swap"},
    "enableRateLimit": True
})

markets = exchange.load_markets()
SYMBOLS = [s for s in markets if markets[s]["swap"] and "USDT" in s][:80]

trade_state = {}
cooldown = {}
COOLDOWN_TIME = 1800

# ===== NEW FUNCTIONS =====

def log_trade(entry, exit_price, direction):
    try:
        pnl = (exit_price-entry)/entry if direction=="long" else (entry-exit_price)/entry
        trade_results.append(pnl)
        if len(trade_results) > 50:
            trade_results.pop(0)
    except:
        pass

def update_loss(pnl):
    global loss_streak
    loss_streak = loss_streak+1 if pnl<0 else 0

def should_stop():
    return loss_streak >= 5

def get_size():
    if loss_streak >= 3:
        return MARGIN * 0.5
    return MARGIN

def confidence(sym):
    score = 0
    try:
        if exchange.fetch_ticker(sym)["quoteVolume"] > MIN_VOLUME:
            score += 1
    except: pass
    try:
        candles = exchange.fetch_ohlcv(sym,"1m",limit=3)
        change=(candles[-1][4]-candles[-2][4])/candles[-2][4]
        if abs(change)>0.002:
            score += 1
    except: pass
    return score

def detect_regime(sym):
    try:
        candles = exchange.fetch_ohlcv(sym,"5m",limit=20)
        closes=[c[4] for c in candles]
        change=(closes[-1]-closes[0])/closes[0]
        if abs(change)>0.01:
            return "trend"
        return "range"
    except:
        return None

# ===== ORIGINAL =====

def safe(x):
    try:
        return float(x)
    except:
        return 0


def get_qty(sym):
    try:
        pos = exchange.fetch_positions([sym])
        if not pos:
            return 0
        return safe(pos[0]["contracts"])
    except:
        return 0


def open_trade(sym,direction,label):
    try:
        if should_stop():
            return

        if get_qty(sym) > 0:
            return

        ticker=exchange.fetch_ticker(sym)

        if ticker["quoteVolume"] < MIN_VOLUME:
            return

        spread=(ticker["ask"]-ticker["bid"])/ticker["last"]
        if spread > MAX_SPREAD:
            return

        score = confidence(sym)
        if score < 1:
            return

        size = get_size()

        price=ticker["last"]
        qty=(size*LEV)/price
        qty=float(exchange.amount_to_precision(sym,qty))

        exchange.set_leverage(LEV,sym)

        side="buy" if direction=="long" else "sell"
        exchange.create_market_order(sym,side,qty)

        trade_state[sym]={
            "entry":price,
            "direction":direction,
            "tp1":False,
            "step":0,
            "start":time.time(),
            "trail":price
        }

        cooldown[sym]=time.time()

        bot.send_message(CHAT_ID,f"🚀 {label.upper()} {sym} {direction}")

    except:
        pass


def manage():
    while True:
        try:
            pos=exchange.fetch_positions()

            for p in pos:
                qty=safe(p.get("contracts"))
                if qty<=0:
                    continue

                sym=p["symbol"]

                if sym not in trade_state:
                    continue

                state=trade_state[sym]
                price=exchange.fetch_ticker(sym)["last"]

                entry=state["entry"]
                direction=state["direction"]

                side="sell" if direction=="long" else "buy"

                # SL
                if (direction=="long" and price <= entry*(1-SL_PCT)) or \
                   (direction=="short" and price >= entry*(1+SL_PCT)):

                    exchange.create_market_order(sym,side,get_qty(sym),params={"reduceOnly":True})
                    log_trade(entry,price,direction)
                    update_loss(-1)
                    trade_state.pop(sym)
                    bot.send_message(CHAT_ID,f"🛑 SL {sym}")
                    continue

                # TRAILING
                if direction == "long":
                    new_trail = price * (1 - TP_TRAIL)
                    if new_trail > state["trail"]:
                        state["trail"] = new_trail
                else:
                    new_trail = price * (1 + TP_TRAIL)
                    if new_trail < state["trail"]:
                        state["trail"] = new_trail

                if (direction=="long" and price <= state["trail"]) or \
                   (direction=="short" and price >= state["trail"]):

                    exchange.create_market_order(sym,side,get_qty(sym),params={"reduceOnly":True})
                    log_trade(entry,price,direction)
                    update_loss(1 if price>entry else -1)
                    trade_state.pop(sym)
                    bot.send_message(CHAT_ID,f"🏁 EXIT {sym}")

            time.sleep(4)

        except:
            time.sleep(6)


def scanner():
    while True:
        try:
            random.shuffle(SYMBOLS)

            positions=exchange.fetch_positions()
            active=sum(1 for p in positions if safe(p.get("contracts"))>0)

            if active >= MAX_POSITIONS:
                time.sleep(SCAN_DELAY)
                continue

            for sym in SYMBOLS:

                if sym in cooldown:
                    if time.time()-cooldown[sym] < COOLDOWN_TIME:
                        continue

                if get_qty(sym)>0:
                    continue

                regime = detect_regime(sym)

                if regime == "trend":
                    pressure = orderbook_pressure(sym)
                else:
                    pressure = orderbook_pressure(sym)

                if not pressure:
                    continue

                open_trade(sym,pressure,"smart")

                break

            time.sleep(SCAN_DELAY)

        except:
            time.sleep(15)


def orderbook_pressure(sym):
    try:
        ob=exchange.fetch_order_book(sym,limit=20)
        bid=sum([b[1] for b in ob["bids"]])
        ask=sum([a[1] for a in ob["asks"]])
        if bid > ask*1.5:
            return "long"
        if ask > bid*1.5:
            return "short"
        return None
    except:
        return None


print("BOT STARTING")

threading.Thread(target=manage,daemon=True).start()
threading.Thread(target=scanner,daemon=True).start()
threading.Thread(target=bot.infinity_polling,daemon=True).start()

bot.send_message(CHAT_ID,"🤖 SMART BOT AKTİF")

while True:
    time.sleep(60)
