# =========================================================
# SADIK BOT FINAL STABLE HIGH WINRATE VERSION
# =========================================================

import ccxt
import time
import os
import telebot
import threading
import pandas as pd

from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# =========================================================
# TELEGRAM
# =========================================================

TOKEN = os.getenv("TELE_TOKEN")
CHAT_ID = int(os.getenv("MY_CHAT_ID"))

bot = telebot.TeleBot(TOKEN)

# =========================================================
# EXCHANGE
# =========================================================

exchange = ccxt.bitget({
    "apiKey": os.getenv("BITGET_API"),
    "secret": os.getenv("BITGET_SEC"),
    "password": os.getenv("BITGET_PASS"),

    "enableRateLimit": True,

    "options": {
        "defaultType": "swap",
        "adjustForTimeDifference": True
    }
})

# =========================================================
# SETTINGS
# =========================================================

MARGIN = 5
LEVERAGE = 3

bot_position = None

LAST_API_CALL = 0

signal_cache = {}

BLOCKED_COINS = [
    "BTC/USDT:USDT",
    "ETH/USDT:USDT",
    "BNB/USDT:USDT",
    "XRP/USDT:USDT",
    "SOL/USDT:USDT",
    "DOGE/USDT:USDT",
    "ADA/USDT:USDT",
    "TRX/USDT:USDT",
    "XAU/USDT:USDT",
    "XAG/USDT:USDT"
]

# =========================================================
# API SAFE
# =========================================================

def safe_api_call(func, *args, **kwargs):

    global LAST_API_CALL

    for _ in range(5):

        try:

            now = time.time()

            wait_time = 2.5 - (now - LAST_API_CALL)

            if wait_time > 0:
                time.sleep(wait_time)

            LAST_API_CALL = time.time()

            return func(*args, **kwargs)

        except Exception as e:

            if "429" in str(e):

                print("429 RATE LIMIT")

                time.sleep(20)

                continue

            print("API ERROR:", e)

            time.sleep(5)

    return None

# =========================================================
# DATA
# =========================================================

def get_data(sym, tf="5m", limit=200):

    try:

        ohlcv = safe_api_call(
            exchange.fetch_ohlcv,
            sym,
            timeframe=tf,
            limit=limit
        )

        if not ohlcv:
            return None

        df = pd.DataFrame(
            ohlcv,
            columns=["t", "o", "h", "l", "c", "v"]
        )

        df["ema20"] = df["c"].ewm(span=20).mean()
        df["ema50"] = df["c"].ewm(span=50).mean()

        delta = df["c"].diff()

        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)

        avg_gain = gain.rolling(14).mean()
        avg_loss = loss.rolling(14).mean()

        rs = avg_gain / avg_loss

        df["rsi"] = 100 - (100 / (1 + rs))

        return df

    except Exception as e:

        print("DATA ERROR:", e)

        return None

# =========================================================
# BTC FILTER
# =========================================================

def btc_filter(direction):

    try:

        btc = get_data(
            "BTC/USDT:USDT",
            "15m"
        )

        if btc is None:
            return False

        price = btc["c"].iloc[-1]

        ema20 = btc["ema20"].iloc[-1]
        ema50 = btc["ema50"].iloc[-1]

        if direction == "LONG":
            return price > ema20 > ema50

        if direction == "SHORT":
            return price < ema20 < ema50

        return False

    except:
        return False

# =========================================================
# ANALYZE
# =========================================================

def analyze(sym):

    try:

        df_5m = get_data(sym, "5m")
        df_15m = get_data(sym, "15m")

        if df_5m is None:
            return None

        if df_15m is None:
            return None

        price = df_5m["c"].iloc[-1]

        ema20_5m = df_5m["ema20"].iloc[-1]
        ema50_5m = df_5m["ema50"].iloc[-1]

        ema20_15m = df_15m["ema20"].iloc[-1]
        ema50_15m = df_15m["ema50"].iloc[-1]

        rsi = df_5m["rsi"].iloc[-1]

        avg_vol = df_5m["v"].rolling(20).mean().iloc[-1]

        if avg_vol <= 0:
            return None

        volume_ratio = (
            df_5m["v"].iloc[-1] / avg_vol
        )

        if volume_ratio < 1.5:
            return None

        # =================================================
        # LONG
        # =================================================

        if (
            ema20_5m > ema50_5m
            and ema20_15m > ema50_15m
            and btc_filter("LONG")
        ):

            if rsi > 72:
                return None

            pullback = (
                price <= ema20_5m * 1.002
            )

            if not pullback:
                return None

            return {
                "signal": "LONG",
                "score": 95
            }

        # =================================================
        # SHORT
        # =================================================

        if (
            ema20_5m < ema50_5m
            and ema20_15m < ema50_15m
            and btc_filter("SHORT")
        ):

            if rsi < 28:
                return None

            pullback = (
                price >= ema20_5m * 0.998
            )

            if not pullback:
                return None

            return {
                "signal": "SHORT",
                "score": 95
            }

        return None

    except Exception as e:

        print("ANALYZE ERROR:", e)

        return None

# =========================================================
# OPEN TRADE
# =========================================================

def open_trade(sym, signal):

    global bot_position

    if bot_position:
        return

    try:

        balance = safe_api_call(
            exchange.fetch_balance
        )

        try:

            usdt = (
                balance.get("USDT", {})
                .get("free", 0)
            )

        except:

            usdt = 0

        if usdt < MARGIN:

            bot.send_message(
                CHAT_ID,
                "❌ YETERSIZ BAKIYE"
            )

            return

        side = (
            "buy"
            if signal == "LONG"
            else "sell"
        )

        safe_api_call(
            exchange.set_leverage,
            LEVERAGE,
            sym
        )

        ticker = safe_api_call(
            exchange.fetch_ticker,
            sym
        )

        if not ticker:
            return

        price = ticker["last"]

        usable_margin = MARGIN * 0.90

        amount = (
            usable_margin * LEVERAGE
        ) / price

        amount = float(
            exchange.amount_to_precision(
                sym,
                amount
            )
        )

        order = safe_api_call(
            exchange.create_market_order,
            sym,
            side,
            amount
        )

        if not order:

            bot.send_message(
                CHAT_ID,
                f"❌ ORDER FAILED\n{sym}"
            )

            return

        entry = order.get("average") or price

        bot_position = {
            "sym": sym,
            "type": signal,
            "entry": entry,
            "max": 0,
            "tp1": False
        }

        bot.send_message(
            CHAT_ID,
            f"""
🚀 OPEN

📊 {sym}
📈 {signal}

💰 Entry: {round(entry, 5)}
"""
        )

    except Exception as e:

        print("OPEN ERROR:", e)

# =========================================================
# CLOSE TRADE
# =========================================================

def close_trade(pos, reason):

    global bot_position

    try:

        side = (
            "sell"
            if pos["type"] == "LONG"
            else "buy"
        )

        positions = safe_api_call(
            exchange.fetch_positions,
            [pos["sym"]]
        )

        size = 0

        if positions:

            for p in positions:

                size = abs(float(
                    p.get("contracts")
                    or p.get("size")
                    or 0
                ))

        if size > 0:

            safe_api_call(
                exchange.create_market_order,
                pos["sym"],
                side,
                size,
                params={
                    "reduceOnly": True
                }
            )

        bot.send_message(
            CHAT_ID,
            f"""
❌ CLOSE

📊 {pos['sym']}
📉 {reason}
"""
        )

    except Exception as e:

        print("CLOSE ERROR:", e)

    bot_position = None

# =========================================================
# MANAGE
# =========================================================

def manage():

    global bot_position

    while True:

        try:

            if not bot_position:

                time.sleep(5)
                continue

            pos = bot_position

            ticker = safe_api_call(
                exchange.fetch_ticker,
                pos["sym"]
            )

            if not ticker:
                continue

            price = ticker["last"]

            if pos["type"] == "LONG":

                pnl = (
                    (price - pos["entry"])
                    / pos["entry"]
                ) * 100

            else:

                pnl = (
                    (pos["entry"] - price)
                    / pos["entry"]
                ) * 100

            if pnl > pos["max"]:
                pos["max"] = pnl

            # TP1

            if pnl >= 0.7 and not pos["tp1"]:

                pos["tp1"] = True

                bot.send_message(
                    CHAT_ID,
                    f"✅ TP1 HIT\n{pos['sym']}"
                )

            # TRAILING

            if pnl >= 1.2:

                if pnl < (
                    pos["max"] - 0.4
                ):

                    close_trade(
                        pos,
                        "TRAIL"
                    )

            # STOP LOSS

            if pnl <= -0.8:

                close_trade(
                    pos,
                    "STOP LOSS"
                )

        except Exception as e:

            print("MANAGE ERROR:", e)

        time.sleep(5)

# =========================================================
# SCANNER
# =========================================================

def scanner():

    while True:

        try:

            if bot_position:

                time.sleep(10)
                continue

            tickers = safe_api_call(
                exchange.fetch_tickers
            )

            if not tickers:

                time.sleep(10)
                continue

            pairs = sorted(
                tickers.items(),
                key=lambda x: x[1].get(
                    "quoteVolume",
                    0
                ) or 0,
                reverse=True
            )[:8]

            for sym, data in pairs:

                try:

                    if ":USDT" not in sym:
                        continue

                    if sym in BLOCKED_COINS:
                        continue

                    safe = (
                        sym.replace("/", "")
                        .replace(":", "")
                    )

                    if safe in signal_cache:

                        old = signal_cache[safe]

                        if time.time() - old < 3600:
                            continue

                    result = analyze(sym)

                    if not result:
                        continue

                    signal = result["signal"]

                    signal_cache[safe] = time.time()

                    markup = InlineKeyboardMarkup()

                    markup.add(
                        InlineKeyboardButton(
                            "✅ MANUEL GİR",
                            callback_data=f"{sym}|{signal}"
                        )
                    )

                    bot.send_message(
                        CHAT_ID,
                        f"""
💀 HIGH WINRATE SIGNAL

📊 {sym}
📈 {signal}

🤖 SCORE: %95
""",
                        reply_markup=markup
                    )

                    open_trade(
                        sym,
                        signal
                    )

                    time.sleep(3)

                except Exception as e:

                    print("PAIR ERROR:", e)

            time.sleep(30)

        except Exception as e:

            print("SCANNER ERROR:", e)

            time.sleep(10)

# =========================================================
# CALLBACK
# =========================================================

@bot.callback_query_handler(func=lambda c: True)
def callback(call):

    try:

        data = call.data.split("|")

        sym = data[0]
        signal = data[1]

        open_trade(
            sym,
            signal
        )

    except Exception as e:

        print("CALLBACK ERROR:", e)

# =========================================================
# START
# =========================================================

threading.Thread(
    target=scanner,
    daemon=True
).start()

threading.Thread(
    target=manage,
    daemon=True
).start()

bot.send_message(
    CHAT_ID,
    "🤖 SADIK FINAL BOT STARTED"
)

while True:

    try:

        bot.infinity_polling(
            timeout=60,
            long_polling_timeout=60,
            skip_pending=True
        )

    except Exception as e:

        print("POLLING ERROR:", e)

        time.sleep(5)
