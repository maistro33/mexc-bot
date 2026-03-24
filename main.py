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

SCAN_DELAY = 1.5
COOLDOWN_TIME = 600

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
LAST_RESULT = {}

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
        MOMENTUM_THRESHOLD = 0.0008
        VOLUME_MULT = 1.02


set_mode_values()


def detect_market_mode():
    try:
        candles = exchange.fetch_ohlcv("BTC/USDT:USDT", "5m", limit=20)
        ranges = [(c[2] - c[3]) / c[4] for c in candles]
        avg = sum(ranges) / len(ranges)

        return "AGGRESSIVE" if avg > 0.005 else "SAFE"
    except:
        return "SAFE"


# ================= TELEGRAM =================

@bot.message_handler(commands=['mode'])
def change_mode(message):
    global MODE
    text = message.text.lower()

    if "safe" in text:
        MODE = "SAFE"
    elif "aggressive" in text:
        MODE = "AGGRESSIVE"
    elif "auto" in text:
        MODE = "AUTO"

    set_mode_values()
    bot.send_message(CHAT_ID, f"⚙️ MODE → {MODE}")


# ================= MARKET =================

def get_symbols():
    arr = []
    tickers = exchange.fetch_tickers()

    for sym, d in tickers.items():
        if "USDT" not in sym:
            continue

        if safe(d.get("quoteVolume")) > 50000:
            arr.append(sym)

    return arr[:50]


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


# ================= STRATEGY =================

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


def get_pnl(entry, price, direction, qty):
    if direction == "long":
        return (price - entry) * qty * LEV
    else:
        return (entry - price) * qty * LEV


# ================= TRADE =================

def open_trade(sym, direction, strategy):
    try:
        if get_qty(sym) > 0:
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
            "step": 0,
            "trail_stop": -999
        }

        bot.send_message(
            CHAT_ID,
            f"🚀 {sym}\n"
            f"Direction: {direction}\n"
            f"Strategy: {strategy}\n"
            f"Entry: {round(price,4)}\n"
            f"Qty: {round(qty,2)}"
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
                price = exchange.fetch_ticker(sym)["last"]

                entry = state["entry"]
                direction = state["direction"]

                side = "sell" if direction == "long" else "buy"

                pnl = get_pnl(entry, price, direction, qty)

                if pnl <= -SL_USDT:
                    exchange.create_market_order(sym, side, qty, params={"reduceOnly": True})
                    trade_state.pop(sym)
                    bot.send_message(CHAT_ID, f"🛑 SL {sym} {round(pnl,2)}$")
                    continue

                if not state["tp1"] and pnl >= TP1_USDT:
                    exchange.create_market_order(sym, side, qty * TP1_RATIO, params={"reduceOnly": True})
                    state["tp1"] = True
                    state["step"] = 1
                    state["trail_stop"] = pnl - STEP_USDT
                    bot.send_message(CHAT_ID, f"💰 TP1 {sym} {round(pnl,2)}$")

                elif state["tp1"]:
                    if pnl >= TP1_USDT + STEP_USDT * state["step"]:
                        state["step"] += 1
                        state["trail_stop"] = pnl - STEP_USDT

                    if pnl <= state["trail_stop"]:
                        exchange.create_market_order(sym, side, qty, params={"reduceOnly": True})
                        trade_state.pop(sym)
                        bot.send_message(CHAT_ID, f"🏁 EXIT {sym} {round(pnl,2)}$")

            time.sleep(2)

        except:
            time.sleep(5)


# ================= SCANNER =================

def scanner():
    global CURRENT_MODE, LAST_MODE_UPDATE

    while True:
        try:
            # AUTO MODE FIX (SPAM YOK)
            if MODE == "AUTO" and time.time() - LAST_MODE_UPDATE > 60:
                new_mode = detect_market_mode()

                if new_mode != CURRENT_MODE:
                    CURRENT_MODE = new_mode
                    set_mode_values()
                    bot.send_message(CHAT_ID, f"🤖 AUTO → {CURRENT_MODE}")

                LAST_MODE_UPDATE = time.time()

            symbols = get_symbols()
            random.shuffle(symbols)

            for sym in symbols:

                if get_qty(sym) > 0:
                    continue

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

                open_trade(sym, direction, strategy)
                break

            time.sleep(SCAN_DELAY)

        except:
            time.sleep(5)


print("🔥 BOT STARTING")

threading.Thread(target=manage, daemon=True).start()
threading.Thread(target=scanner, daemon=True).start()

bot.send_message(CHAT_ID, "🤖 BOT AKTİF (FINAL FIXED)")

bot.infinity_polling()
