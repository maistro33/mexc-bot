import os
import time
import ccxt
import telebot
import threading
import random

LEV = 10
MARGIN = 3

MAX_POSITIONS = 3

TP1_USDT = 0.20
STEP_USDT = 0.15
SL_USDT = 0.40
TP1_RATIO = 0.70

MIN_VOLUME = 2000000
MAX_SPREAD = 0.003
SCAN_DELAY = 1.5

COOLDOWN_TIME = 600

bot = telebot.TeleBot(os.getenv("TELE_TOKEN"))
CHAT_ID = os.getenv("MY_CHAT_ID")

exchange = ccxt.bitget({
    "apiKey": os.getenv("BITGET_API"),
    "secret": os.getenv("BITGET_SEC"),
    "password": "Berfin33",
    "options": {"defaultType": "swap"},
    "enableRateLimit": True
})

trade_state = {}
cooldown = {}
LAST_RESULT = {}
trade_log = []

START_BALANCE = None
DAILY_LOSS_LIMIT = 0.05


def safe(x):
    try:
        return float(x)
    except:
        return 0


# ================= COIN FILTER =================
def get_symbols():
    arr = []
    tickers = exchange.fetch_tickers()

    for sym, d in tickers.items():

        if "USDT" not in sym:
            continue

        s = sym.upper()

        if any(x in s for x in [
            "BTC","ETH","BNB","SOL","XRP","ADA","DOGE","DOT",
            "LTC","TRX","AVAX","MATIC","LINK","ATOM"
        ]):
            continue

        if "1000" in s:
            continue

        price = safe(d.get("last"))
        vol = safe(d.get("quoteVolume"))
        ch = abs(safe(d.get("percentage")))

        if price < 1.2 and vol > 50000 and ch > 2:
            arr.append(sym)

    return arr[:80]


# ================= EXTRA FILTERS =================

def volatility_strength(sym):
    try:
        candles = exchange.fetch_ohlcv(sym, "5m", limit=10)
        ranges = [(c[2] - c[3]) / c[4] for c in candles]
        avg = sum(ranges) / len(ranges)
        return avg > 0.008
    except:
        return False


def fake_breakout_filter(sym):
    try:
        candles = exchange.fetch_ohlcv(sym, "5m", limit=3)
        high = candles[-2][2]
        low = candles[-2][3]
        close = candles[-1][4]
        return close < high and close > low
    except:
        return False


def btc_trend():
    try:
        candles = exchange.fetch_ohlcv("BTC/USDT:USDT","1h",limit=50)
        closes=[c[4] for c in candles]
        ema=sum(closes[-20:])/20
        return "bull" if closes[-1] > ema else "bear"
    except:
        return "neutral"


def volatility_filter(sym):
    try:
        candles = exchange.fetch_ohlcv(sym,"5m",limit=10)
        ranges=[c[2]-c[3] for c in candles]
        avg=sum(ranges[:-1])/9
        return ranges[-1] > avg*1.1
    except:
        return False


def micro_momentum(sym):
    try:
        candles = exchange.fetch_ohlcv(sym,"1m",limit=3)
        change=(candles[-1][4]-candles[-2][4])/candles[-2][4]
        return abs(change) > 0.0015
    except:
        return False


def volume_spike(sym):
    try:
        candles=exchange.fetch_ohlcv(sym,"5m",limit=6)
        vols=[c[5] for c in candles]
        avg=sum(vols[:-1])/5
        return vols[-1] > avg*1.1
    except:
        return False


def orderbook_pressure(sym):
    try:
        ob=exchange.fetch_order_book(sym,limit=20)
        bid=sum([b[1] for b in ob["bids"]])
        ask=sum([a[1] for a in ob["asks"]])
        if bid > ask*1.4:
            return "long"
        if ask > bid*1.4:
            return "short"
        return None
    except:
        return None


# ================= RISK =================

def get_balance():
    try:
        bal = exchange.fetch_balance()
        return bal["total"]["USDT"]
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


def get_pnl(entry, price, direction, qty):
    if direction == "long":
        return (price - entry) * qty * LEV
    else:
        return (entry - price) * qty * LEV


def current_direction_count(direction):
    count = 0
    positions = exchange.fetch_positions()

    for p in positions:
        qty = safe(p.get("contracts"))
        if qty <= 0:
            continue

        side = "long" if p["side"] == "long" else "short"

        if side == direction:
            count += 1

    return count


# ================= TRADE =================

def open_trade(sym, direction):
    try:
        global trade_log

        if get_qty(sym) > 0:
            return

        if current_direction_count(direction) >= 1:
            return

        ticker = exchange.fetch_ticker(sym)

        if ticker["quoteVolume"] < MIN_VOLUME:
            return

        spread = (ticker["ask"] - ticker["bid"]) / ticker["last"]
        if spread > MAX_SPREAD:
            return

        price = ticker["last"]
        qty = (MARGIN * LEV) / price
        qty = float(exchange.amount_to_precision(sym, qty))

        exchange.set_leverage(LEV, sym)

        side = "buy" if direction == "long" else "sell"
        exchange.create_market_order(sym, side, qty)

        trade_state[sym] = {
            "entry": price,
            "direction": direction,
            "tp1": False,
            "step": 0,
            "trail_stop": -999
        }

        trade_log.append(time.time())

        bot.send_message(CHAT_ID, f"🚀 {sym} {direction}")

    except:
        pass


# ================= MANAGE =================

def manage():
    while True:
        try:
            positions = exchange.fetch_positions()

            for p in positions:
                qty = safe(p.get("contracts"))
                if qty <= 0:
                    continue

                sym = p["symbol"]

                if sym not in trade_state:
                    continue

                state = trade_state[sym]
                price = exchange.fetch_ticker(sym)["last"]

                entry = state["entry"]
                direction = state["direction"]

                side = "sell" if direction == "long" else "buy"

                pnl = get_pnl(entry, price, direction, qty)

                # SL
                if pnl <= -SL_USDT:
                    exchange.create_market_order(sym, side, qty, params={"reduceOnly": True})
                    LAST_RESULT[sym] = "loss"
                    cooldown[sym] = time.time()
                    trade_state.pop(sym)
                    bot.send_message(CHAT_ID, f"🛑 SL {sym} {round(pnl,2)}$")
                    continue

                # TP1
                if not state["tp1"] and pnl >= TP1_USDT:
                    exchange.create_market_order(sym, side, qty * TP1_RATIO, params={"reduceOnly": True})
                    state["tp1"] = True
                    state["step"] = 1
                    state["trail_stop"] = pnl - STEP_USDT
                    LAST_RESULT[sym] = "win"
                    bot.send_message(CHAT_ID, f"💰 TP1 {sym}")

                elif state["tp1"]:
                    if pnl >= TP1_USDT + STEP_USDT * state["step"]:
                        state["step"] += 1
                        state["trail_stop"] = pnl - STEP_USDT
                        bot.send_message(CHAT_ID, f"🔒 STEP {state['step']}")

                    if pnl <= state["trail_stop"]:
                        exchange.create_market_order(sym, side, qty, params={"reduceOnly": True})
                        trade_state.pop(sym)
                        bot.send_message(CHAT_ID, f"🏁 EXIT {sym}")

            time.sleep(2)

        except:
            time.sleep(5)


# ================= SCANNER =================

def scanner():
    global START_BALANCE

    while True:
        try:
            if START_BALANCE is None:
                START_BALANCE = get_balance()

            if get_balance() < START_BALANCE * (1 - DAILY_LOSS_LIMIT):
                time.sleep(60)
                continue

            symbols = get_symbols()
            random.shuffle(symbols)

            btc = btc_trend()

            trade_log[:] = [t for t in trade_log if time.time() - t < 600]
            if len(trade_log) >= 5:
                time.sleep(2)
                continue

            positions = exchange.fetch_positions()
            active = sum(1 for p in positions if safe(p.get("contracts")) > 0)

            if active >= MAX_POSITIONS:
                time.sleep(SCAN_DELAY)
                continue

            for sym in symbols:

                if sym in cooldown and LAST_RESULT.get(sym) == "loss":
                    if time.time() - cooldown[sym] < COOLDOWN_TIME:
                        continue

                if get_qty(sym) > 0:
                    continue

                if not volatility_strength(sym):
                    continue

                if fake_breakout_filter(sym):
                    continue

                if not volatility_filter(sym):
                    continue

                if not micro_momentum(sym):
                    continue

                if not volume_spike(sym):
                    continue

                pressure = orderbook_pressure(sym)

                if not pressure:
                    continue

                if pressure == "long" and btc == "bear":
                    continue

                if pressure == "short" and btc == "bull":
                    continue

                open_trade(sym, pressure)

            time.sleep(SCAN_DELAY)

        except:
            time.sleep(5)


print("🔥 BOT STARTING")

threading.Thread(target=manage, daemon=True).start()
threading.Thread(target=scanner, daemon=True).start()

bot.send_message(CHAT_ID, "🤖 BOT AKTİF (UPGRADE)")

bot.infinity_polling()
