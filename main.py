import os
import time
import ccxt
import telebot
import threading
import random

LEV = 10
MARGIN = 3

TP1_USDT = 0.35
STEP_USDT = 0.40
SL_USDT = 0.50
TP1_RATIO = 0.70

SCAN_DELAY = 2
MODE = "AUTO"

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

CURRENT_MODE = "SAFE"
LAST_MODE_UPDATE = 0


def safe(x):
    try:
        return float(x)
    except:
        return 0


# ================= MODE =================

def set_mode_values():
    global MOMENTUM_THRESHOLD, VOLUME_MULT

    active = CURRENT_MODE if MODE == "AUTO" else MODE

    if active == "SAFE":
        MOMENTUM_THRESHOLD = 0.0015
        VOLUME_MULT = 1.1
    else:
        MOMENTUM_THRESHOLD = 0.0005
        VOLUME_MULT = 1.01


set_mode_values()


def detect_market_mode():
    try:
        candles = exchange.fetch_ohlcv("BTC/USDT:USDT", "5m", limit=20)
        ranges = [(c[2] - c[3]) / c[4] for c in candles]
        avg = sum(ranges) / len(ranges)

        return "AGGRESSIVE" if avg > 0.005 else "SAFE"
    except:
        return "SAFE"


# ================= FILTERS =================

def micro_momentum(sym):
    try:
        candles = exchange.fetch_ohlcv(sym, "1m", limit=3)
        change = (candles[-1][4] - candles[-2][4]) / candles[-2][4]
        return abs(change) > MOMENTUM_THRESHOLD
    except:
        return False


def volume_spike(sym):
    try:
        candles = exchange.fetch_ohlcv(sym, "5m", limit=6)
        vols = [c[5] for c in candles]
        avg = sum(vols[:-1]) / 5
        return vols[-1] > avg * VOLUME_MULT
    except:
        return False


def orderbook_pressure(sym):
    try:
        ob = exchange.fetch_order_book(sym, limit=10)
        bid = sum([b[1] for b in ob["bids"]])
        ask = sum([a[1] for a in ob["asks"]])

        if bid > ask * 1.2:
            return "long"
        if ask > bid * 1.2:
            return "short"
        return None
    except:
        return None


def trend_filter(sym):
    try:
        candles = exchange.fetch_ohlcv(sym, "5m", limit=20)
        closes = [c[4] for c in candles]
        ema = sum(closes[-10:]) / 10

        return "bull" if closes[-1] > ema else "bear"
    except:
        return "neutral"


def rsi_signal(sym):
    try:
        candles = exchange.fetch_ohlcv(sym, "5m", limit=20)
        closes = [c[4] for c in candles]

        gains, losses = [], []
        for i in range(1, len(closes)):
            diff = closes[i] - closes[i - 1]
            if diff > 0:
                gains.append(diff)
            else:
                losses.append(abs(diff))

        avg_gain = sum(gains[-14:]) / 14 if gains else 0
        avg_loss = sum(losses[-14:]) / 14 if losses else 1

        rs = avg_gain / avg_loss if avg_loss != 0 else 0
        rsi = 100 - (100 / (1 + rs))

        if rsi < 28:
            return "long"
        if rsi > 72:
            return "short"

        return None
    except:
        return None


def choose_strategy(sym):
    if rsi_signal(sym):
        return "reversal"
    return "momentum"


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

def open_trade(sym, direction, strategy):
    try:
        if get_qty(sym) > 0:
            return

        if current_direction_count(direction) >= 1:
            return

        if sym in cooldown and time.time() - cooldown[sym] < 300:
            return

        price = exchange.fetch_ticker(sym)["last"]
        qty = (MARGIN * LEV) / price

        exchange.set_leverage(LEV, sym)

        side = "buy" if direction == "long" else "sell"
        exchange.create_market_order(sym, side, qty)

        trade_state[sym] = {
            "entry": price,
            "direction": direction,
            "tp1": False,
            "max_pnl": 0,
            "breakeven": False,
            "tp1_time": 0
        }

        bot.send_message(
            CHAT_ID,
            f"🚀 {sym}\nDirection: {direction}\nStrategy: {strategy}\nEntry: {round(price,4)}"
        )

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

                pnl = safe(p.get("unrealizedPnl"))

                if pnl > state["max_pnl"]:
                    state["max_pnl"] = pnl

                direction = state["direction"]
                side = "sell" if direction == "long" else "buy"

                # SL
                if pnl <= -SL_USDT:
                    exchange.create_market_order(sym, side, qty, params={"reduceOnly": True})
                    trade_state.pop(sym)
                    cooldown[sym] = time.time()
                    bot.send_message(CHAT_ID, f"🛑 SL {sym} {round(pnl,2)}$")
                    continue

                # TP1
                if not state["tp1"] and pnl >= TP1_USDT:
                    exchange.create_market_order(sym, side, qty * TP1_RATIO, params={"reduceOnly": True})
                    state["tp1"] = True
                    state["tp1_time"] = time.time()
                    bot.send_message(CHAT_ID, f"💰 TP1 {sym} {round(pnl,2)}$")

                if state["tp1"]:

                    if time.time() - state["tp1_time"] < 40:
                        continue

                    if not state["breakeven"] and pnl >= TP1_USDT + STEP_USDT:
                        state["breakeven"] = True
                        bot.send_message(CHAT_ID, f"🟢 BE ACTIVE {sym}")

                    if state["breakeven"] and pnl <= 0:
                        exchange.create_market_order(sym, side, qty, params={"reduceOnly": True})
                        trade_state.pop(sym)
                        bot.send_message(CHAT_ID, f"⚖️ BE EXIT {sym}")
                        continue

                    if state["max_pnl"] - pnl >= STEP_USDT * 2:
                        exchange.create_market_order(sym, side, qty, params={"reduceOnly": True})
                        trade_state.pop(sym)
                        bot.send_message(CHAT_ID, f"🏁 EXIT {sym} {round(pnl,2)}$")
                        continue

            time.sleep(2)

        except:
            time.sleep(5)


# ================= SCANNER =================

def scanner():
    global CURRENT_MODE, LAST_MODE_UPDATE

    while True:
        try:
            if MODE == "AUTO" and time.time() - LAST_MODE_UPDATE > 60:
                new_mode = detect_market_mode()

                if new_mode != CURRENT_MODE:
                    CURRENT_MODE = new_mode
                    set_mode_values()
                    bot.send_message(CHAT_ID, f"🤖 AUTO → {CURRENT_MODE}")

                LAST_MODE_UPDATE = time.time()

            positions = exchange.fetch_positions()
            active = sum(1 for p in positions if safe(p.get("contracts")) > 0)

            if active >= 2:
                time.sleep(2)
                continue

            symbols = get_symbols()
            random.shuffle(symbols)

            for sym in symbols:

                if not micro_momentum(sym):
                    continue

                if not volume_spike(sym):
                    continue

                strategy = choose_strategy(sym)

                if strategy == "momentum":
                    direction = orderbook_pressure(sym)
                    if not direction:
                        continue
                else:
                    direction = rsi_signal(sym)
                    if not direction:
                        continue

                    trend = trend_filter(sym)

                    if direction == "short" and trend == "bull":
                        continue

                    if direction == "long" and trend == "bear":
                        continue

                open_trade(sym, direction, strategy)
                break

            time.sleep(SCAN_DELAY)

        except:
            time.sleep(5)


print("🔥 FINAL BOT START")

threading.Thread(target=manage, daemon=True).start()
threading.Thread(target=scanner, daemon=True).start()

bot.send_message(CHAT_ID, "🤖 FINAL STABİL BOT AKTİF")

bot.infinity_polling()
