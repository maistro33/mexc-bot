# =========================================================
# SADIK ULTIMATE AI BOT FINAL VERSION
# =========================================================

import ccxt
import time
import os
import telebot
import threading
import pandas as pd

from telebot.types import InlineKeyboardMarkup
from telebot.types import InlineKeyboardButton

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

MARGIN = 3
LEVERAGE = 10

bot_position = None

LAST_API_CALL = 0

signal_cache = {}

coin_cooldown = {}

# =========================================================
# API SAFE
# =========================================================

def safe_api_call(func, *args, **kwargs):

    global LAST_API_CALL

    for _ in range(5):

        try:

            now = time.time()

            wait_time = 2.2 - (now - LAST_API_CALL)

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
# GET DATA
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
            columns=[
                "t",
                "o",
                "h",
                "l",
                "c",
                "v"
            ]
        )

        # EMA

        df["ema20"] = df["c"].ewm(
            span=20
        ).mean()

        df["ema50"] = df["c"].ewm(
            span=50
        ).mean()

        # RSI

        delta = df["c"].diff()

        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)

        avg_gain = gain.rolling(14).mean()
        avg_loss = loss.rolling(14).mean()

        rs = avg_gain / avg_loss

        df["rsi"] = 100 - (
            100 / (1 + rs)
        )

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

            return (
                price > ema20 > ema50
            )

        if direction == "SHORT":

            return (
                price < ema20 < ema50
            )

        return False

    except:

        return False

# =========================================================
# BEST COINS
# =========================================================

def get_best_coins():

    try:

        tickers = safe_api_call(
            exchange.fetch_tickers
        )

        if not tickers:
            return []

        selected = []

        for sym, data in tickers.items():

            try:

                if ":USDT" not in sym:
                    continue

                if any(x in sym for x in [
                    "XAU",
                    "XAG"
                ]):
                    continue

                volume = (
                    data.get(
                        "quoteVolume",
                        0
                    ) or 0
                )

                if volume < 10000000:
                    continue

                df = get_data(sym)

                if df is None:
                    continue

                volatility = (
                    (
                        df["h"].iloc[-1]
                        - df["l"].iloc[-1]
                    )
                    / df["c"].iloc[-1]
                ) * 100

                if volatility < 1:
                    continue

                selected.append(
                    (
                        sym,
                        volume,
                        volatility
                    )
                )

            except:
                pass

        selected = sorted(
            selected,
            key=lambda x: (
                x[1],
                x[2]
            ),
            reverse=True
        )

        return [
            x[0]
            for x in selected[:15]
        ]

    except Exception as e:

        print("COIN SELECT ERROR:", e)

        return []

# =========================================================
# ANALYZE
# =========================================================

def analyze(sym):

    try:

        df5 = get_data(sym, "5m")
        df15 = get_data(sym, "15m")

        if df5 is None:
            return None

        if df15 is None:
            return None

        price = df5["c"].iloc[-1]

        ema20_5 = df5["ema20"].iloc[-1]
        ema50_5 = df5["ema50"].iloc[-1]

        ema20_15 = df15["ema20"].iloc[-1]
        ema50_15 = df15["ema50"].iloc[-1]

        rsi = df5["rsi"].iloc[-1]

        avg_vol = (
            df5["v"]
            .rolling(20)
            .mean()
            .iloc[-1]
        )

        if avg_vol <= 0:
            return None

        volume_ratio = (
            df5["v"].iloc[-1]
            / avg_vol
        )

        # =================================================
        # LONG
        # =================================================

        if (

            ema20_5 > ema50_5
            and
            ema20_15 > ema50_15
            and
            btc_filter("LONG")

        ):

            if rsi > 74:
                return None

            if volume_ratio < 1.2:
                return None

            pullback = (
                price <= ema20_5 * 1.003
            )

            if not pullback:
                return None

            return {
                "signal": "LONG",
                "score": 90
            }

        # =================================================
        # SHORT
        # =================================================

        if (

            ema20_5 < ema50_5
            and
            ema20_15 < ema50_15
            and
            btc_filter("SHORT")

        ):

            if rsi < 26:
                return None

            if volume_ratio < 1.2:
                return None

            pullback = (
                price >= ema20_5 * 0.997
            )

            if not pullback:
                return None

            return {
                "signal": "SHORT",
                "score": 90
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
                balance.get(
                    "USDT",
                    {}
                ).get(
                    "free",
                    0
                )
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

        entry = (
            order.get("average")
            or price
        )

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

    # =========================
    # COOLDOWN
    # =========================

    coin_cooldown[pos["sym"]] = (
        time.time() + 3600
    )

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

            # =================================================
            # REAL PNL USDT
            # =================================================

            if pos["type"] == "LONG":

                pnl_percent = (
                    (
                        price
                        - pos["entry"]
                    )
                    / pos["entry"]
                ) * 100

            else:

                pnl_percent = (
                    (
                        pos["entry"]
                        - price
                    )
                    / pos["entry"]
                ) * 100

            pnl_usdt = (
                pnl_percent / 100
            ) * (
                MARGIN * LEVERAGE
            )

            if pnl_usdt > pos["max"]:
                pos["max"] = pnl_usdt

            # =================================================
            # TP1 / BREAKEVEN
            # =================================================

            if pnl_usdt >= 0.45 and not pos["tp1"]:

                pos["tp1"] = True

                bot.send_message(
                    CHAT_ID,
                    f"""
✅ BREAKEVEN AKTIF

📊 {pos['sym']}

💰 PROFIT: {round(pnl_usdt,2)} USDT
"""
                )

            # =================================================
            # PROFIT LOCK
            # =================================================

            if pos["tp1"]:

                if pnl_usdt <= 0.20:

                    close_trade(
                        pos,
                        "PROFIT LOCK"
                    )

                    continue

            # =================================================
            # TRAILING
            # =================================================

            if pnl_usdt >= 1.00:

                trail_gap = 0.35

                if pnl_usdt < (
                    pos["max"] - trail_gap
                ):

                    close_trade(
                        pos,
                        "TRAILING TAKE PROFIT"
                    )

                    continue

            # =================================================
            # STOP LOSS
            # =================================================

            if pnl_usdt <= -0.60:

                close_trade(
                    pos,
                    "STOP LOSS"
                )

                continue

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

            coins = get_best_coins()

            print("BEST COINS:", coins)

            for sym in coins:

                try:

                    # =========================
                    # COOLDOWN FILTER
                    # =========================

                    if sym in coin_cooldown:

                        if (
                            time.time()
                            < coin_cooldown[sym]
                        ):

                            continue

                    safe = (
                        sym.replace("/", "")
                        .replace(":", "")
                    )

                    if safe in signal_cache:

                        old = signal_cache[safe]

                        if (
                            time.time()
                            - old
                        ) < 1800:

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
💀 AI SIGNAL

📊 {sym}
📈 {signal}

🤖 SCORE: %90
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
    "🤖 SADIK ULTIMATE AI BOT STARTED"
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
