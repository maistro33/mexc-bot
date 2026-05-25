# =========================================================
# SADIK TREND MASTER AI BOT
# =========================================================

import ccxt
import time
import os
import telebot
import threading
import pandas as pd

from supabase import create_client
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# =========================================================
# TELEGRAM
# =========================================================

TOKEN = os.getenv("TELE_TOKEN")
CHAT_ID = int(os.getenv("MY_CHAT_ID"))

bot = telebot.TeleBot(TOKEN)

# =========================================================
# SUPABASE
# =========================================================

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase = create_client(
    SUPABASE_URL,
    SUPABASE_KEY
)

# =========================================================
# EXCHANGE
# =========================================================

exchange = ccxt.bitget({

    "apiKey": os.getenv("BITGET_API"),
    "secret": os.getenv("BITGET_SEC"),
    "password": os.getenv("BITGET_PASS"),

    "enableRateLimit": True,
    "rateLimit": 1200,
    "timeout": 30000,

    "options": {
        "defaultType": "swap",
        "adjustForTimeDifference": True
    }
})

# =========================================================
# SETTINGS
# =========================================================

MARGIN = 3
LEVERAGE = 5

bot_position = None
manual_positions = []

signal_cache = {}
coin_cooldown = {}

lock = False

LAST_API_CALL = 0

btc_cache = {
    "time": 0,
    "long": True,
    "short": True
}

# =========================================================
# API SAFE
# =========================================================

def safe_api_call(func, *args, **kwargs):

    global LAST_API_CALL

    for _ in range(5):

        try:

            now = time.time()

            wait_time = 0.7 - (now - LAST_API_CALL)

            if wait_time > 0:
                time.sleep(wait_time)

            LAST_API_CALL = time.time()

            return func(*args, **kwargs)

        except Exception as e:

            if "429" in str(e):

                print("429 RATE LIMIT")

                time.sleep(10)

                continue

            print("API ERROR:", e)

            time.sleep(2)

    return None

# =========================================================
# RSI
# =========================================================

def calculate_rsi(series, period=14):

    delta = series.diff()

    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()

    rs = avg_gain / avg_loss

    rsi = 100 - (100 / (1 + rs))

    return rsi

# =========================================================
# ADX
# =========================================================

def calculate_adx(df, period=14):

    try:

        high = df["h"]
        low = df["l"]
        close = df["c"]

        plus_dm = high.diff()
        minus_dm = low.diff()

        plus_dm[plus_dm < 0] = 0
        minus_dm[minus_dm > 0] = 0

        tr1 = high - low
        tr2 = abs(high - close.shift())
        tr3 = abs(low - close.shift())

        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

        atr = tr.rolling(period).mean()

        plus_di = 100 * (
            plus_dm.rolling(period).mean() / atr
        )

        minus_di = abs(
            100 * (
                minus_dm.rolling(period).mean() / atr
            )
        )

        dx = abs(
            plus_di - minus_di
        ) / (
            plus_di + minus_di
        ) * 100

        adx = dx.rolling(period).mean()

        return adx.iloc[-1]

    except:
        return 0

# =========================================================
# GET DATA
# =========================================================

def get_data(sym, timeframe="15m"):

    try:

        ohlcv = safe_api_call(
            exchange.fetch_ohlcv,
            sym,
            timeframe=timeframe,
            limit=150
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

        df["ema20"] = df["c"].ewm(
            span=20
        ).mean()

        df["ema50"] = df["c"].ewm(
            span=50
        ).mean()

        df["ema100"] = df["c"].ewm(
            span=100
        ).mean()

        df["rsi"] = calculate_rsi(
            df["c"]
        )

        return df

    except Exception as e:

        print("DATA ERROR:", e)

        return None

# =========================================================
# BTC FILTER
# =========================================================

def btc_filter(signal):

    global btc_cache

    try:

        now = time.time()

        if now - btc_cache["time"] > 120:

            df = get_data(
                "BTC/USDT:USDT",
                "1h"
            )

            if df is not None:

                price = df["c"].iloc[-1]

                ema20 = df["ema20"].iloc[-1]
                ema50 = df["ema50"].iloc[-1]

                btc_cache["long"] = (
                    price > ema20 > ema50
                )

                btc_cache["short"] = (
                    price < ema20 < ema50
                )

            btc_cache["time"] = now

        if signal == "LONG":
            return btc_cache["long"]

        if signal == "SHORT":
            return btc_cache["short"]

        return True

    except:
        return True

# =========================================================
# REAL SIZE
# =========================================================

def get_real_size(sym):

    try:

        positions = safe_api_call(
            exchange.fetch_positions,
            [sym]
        )

        if not positions:
            return 0

        for p in positions:

            size = (
                p.get("contracts")
                or p.get("size")
                or 0
            )

            size = abs(float(size))

            if size > 0:
                return size

    except Exception as e:

        print("SIZE ERROR:", e)

    return 0

# =========================================================
# ANALYZE
# =========================================================

def analyze(df, sym):

    try:

        df1h = get_data(
            sym,
            "1h"
        )

        if df1h is None:
            return None, 0, "NO 1H"

        price = df["c"].iloc[-1]

        ema20 = df["ema20"].iloc[-1]
        ema50 = df["ema50"].iloc[-1]
        ema100 = df["ema100"].iloc[-1]

        ema20_1h = df1h["ema20"].iloc[-1]
        ema50_1h = df1h["ema50"].iloc[-1]

        rsi = df["rsi"].iloc[-1]

        adx = calculate_adx(df)

        if adx < 20:
            return None, 0, "WEAK TREND"

        avg_vol = (
            df["v"]
            .rolling(20)
            .mean()
            .iloc[-1]
        )

        if avg_vol <= 0:
            return None, 0, "BAD VOLUME"

        volume_ratio = (
            df["v"].iloc[-1]
            / avg_vol
        )

        if volume_ratio < 1.40:
            return None, 0, "LOW VOLUME"

        recent_move = abs(
            price - df["c"].iloc[-5]
        ) / df["c"].iloc[-5]

        if recent_move > 0.05:
            return None, 0, "FAKE PUMP"

        # =====================================================
        # LONG
        # =====================================================

        if (

            ema20 > ema50 > ema100

            and

            ema20_1h > ema50_1h

        ):

            if not btc_filter("LONG"):
                return None, 0, "BTC FILTER"

            if rsi >= 68:
                return None, 0, "RSI HIGH"

            pullback_ok = (
                price <= ema20 * 1.015
            )

            if not pullback_ok:
                return None, 0, "NO PULLBACK"

            score = 94

            if adx > 28:
                score += 2

            if volume_ratio > 1.80:
                score += 2

            return "LONG", score, "TREND LONG"

        # =====================================================
        # SHORT
        # =====================================================

        if (

            ema20 < ema50 < ema100

            and

            ema20_1h < ema50_1h

        ):

            if not btc_filter("SHORT"):
                return None, 0, "BTC FILTER"

            if rsi <= 32:
                return None, 0, "RSI LOW"

            pullback_ok = (
                price >= ema20 * 0.985
            )

            if not pullback_ok:
                return None, 0, "NO PULLBACK"

            score = 94

            if adx > 28:
                score += 2

            if volume_ratio > 1.80:
                score += 2

            return "SHORT", score, "TREND SHORT"

        return None, 0, "NO TREND"

    except Exception as e:

        print("ANALYZE ERROR:", e)

        return None, 0, "ERROR"

# =========================================================
# OPEN TRADE
# =========================================================

def open_trade(data, is_manual=False):

    global bot_position
    global lock

    if lock:
        return

    if bot_position and not is_manual:
        return

    lock = True

    try:

        if get_real_size(data["sym"]) > 0:

            lock = False
            return

        side = (
            "buy"
            if data["signal"] == "LONG"
            else "sell"
        )

        safe_api_call(
            exchange.set_leverage,
            LEVERAGE,
            data["sym"]
        )

        ticker = safe_api_call(
            exchange.fetch_ticker,
            data["sym"]
        )

        if not ticker:

            lock = False
            return

        price = ticker["last"]

        amount = (
            MARGIN * LEVERAGE
        ) / price

        market = exchange.market(data["sym"])

        min_amount = (
            market.get("limits", {})
            .get("amount", {})
            .get("min", 0.001)
        )

        amount = max(amount, min_amount)

        amount = float(
            exchange.amount_to_precision(
                data["sym"],
                amount
            )
        )

        order = safe_api_call(
            exchange.create_market_order,
            data["sym"],
            side,
            amount
        )

        if not order:

            lock = False
            return

        entry = order.get("average") or price

        pos = {
            "sym": data["sym"],
            "type": data["signal"],
            "entry": float(entry),
            "max": 0,
            "tp1": False,
            "open_time": time.time()
        }

        if is_manual:
            manual_positions.append(pos)
        else:
            bot_position = pos

        bot.send_message(
            CHAT_ID,
            f"""
🚀 OPEN

📊 {data['sym']}
📈 {data['signal']}

💰 Entry: {round(entry, 5)}
"""
        )

    except Exception as e:

        print("OPEN ERROR:", e)

    lock = False

# =========================================================
# CLOSE TRADE
# =========================================================

def close_trade(pos, reason, is_manual=False):

    global bot_position

    try:

        side = (
            "sell"
            if pos["type"] == "LONG"
            else "buy"
        )

        size = get_real_size(pos["sym"])

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

        ticker = safe_api_call(
            exchange.fetch_ticker,
            pos["sym"]
        )

        pnl = 0

        if ticker:

            current_price = ticker["last"]

            if pos["type"] == "LONG":

                pnl_percent = (
                    (current_price - pos["entry"])
                    / pos["entry"]
                ) * 100

            else:

                pnl_percent = (
                    (pos["entry"] - current_price)
                    / pos["entry"]
                ) * 100

            pnl = (
                pnl_percent / 100
            ) * (
                MARGIN * LEVERAGE
            )

        bot.send_message(
            CHAT_ID,
            f"""
❌ CLOSED

📊 {pos['sym']}
📉 {reason}

💰 PNL: {round(pnl, 2)} USDT
"""
        )

    except Exception as e:

        print("CLOSE ERROR:", e)

    coin_cooldown[pos["sym"]] = (
        time.time() + 7200
    )

    if is_manual:

        if pos in manual_positions:
            manual_positions.remove(pos)

    else:

        bot_position = None

# =========================================================
# MANAGE
# =========================================================

def manage():

    global bot_position

    while True:

        try:

            all_positions = []

            if bot_position:
                all_positions.append((bot_position, False))

            for p in manual_positions[:]:
                all_positions.append((p, True))

            for pos, is_manual in all_positions:

                real_size = get_real_size(pos["sym"])

                if real_size <= 0:

                    if is_manual:

                        if pos in manual_positions:
                            manual_positions.remove(pos)

                    else:

                        bot_position = None

                    continue

                ticker = safe_api_call(
                    exchange.fetch_ticker,
                    pos["sym"]
                )

                if not ticker:
                    continue

                price = ticker["last"]

                if pos["type"] == "LONG":

                    pnl_percent = (
                        (price - pos["entry"])
                        / pos["entry"]
                    ) * 100

                else:

                    pnl_percent = (
                        (pos["entry"] - price)
                        / pos["entry"]
                    ) * 100

                pnl = (
                    pnl_percent / 100
                ) * (
                    MARGIN * LEVERAGE
                )

                if pnl > pos["max"]:
                    pos["max"] = pnl

                # =================================================
                # TP1
                # =================================================

                if pnl >= 0.80 and not pos["tp1"]:

                    pos["tp1"] = True

                    bot.send_message(
                        CHAT_ID,
                        f"""
✅ TP1 HIT

📊 {pos['sym']}

💰 PROFIT:
{round(pnl,2)} USDT
"""
                    )

                # =================================================
                # SMART TREND PROFIT LOCK
                # =================================================

                if pos["max"] >= 0.80 and pnl <= 0.45:

                    close_trade(
                        pos,
                        "LOCK 1",
                        is_manual
                    )

                    continue

                elif pos["max"] >= 1.50 and pnl <= 1.00:

                    close_trade(
                        pos,
                        "LOCK 2",
                        is_manual
                    )

                    continue

                elif pos["max"] >= 2.50 and pnl <= 1.80:

                    close_trade(
                        pos,
                        "LOCK 3",
                        is_manual
                    )

                    continue

                elif pos["max"] >= 4.00 and pnl <= 3.00:

                    close_trade(
                        pos,
                        "LOCK 4",
                        is_manual
                    )

                    continue

                # =================================================
                # STOP LOSS
                # =================================================

                if pnl <= -0.70:

                    close_trade(
                        pos,
                        "STOP LOSS",
                        is_manual
                    )

                    continue

        except Exception as e:

            print("MANAGE ERROR:", e)

        time.sleep(5)

# =========================================================
# SCANNER
# =========================================================

def scanner():

    global bot_position

    while True:

        try:

            tickers = safe_api_call(
                exchange.fetch_tickers
            )

            if not tickers:

                time.sleep(5)
                continue

            pairs = sorted(

                [

                    x for x in tickers.items()

                    if (

                        ":USDT" in x[0]

                        and

                        not any(bad in x[0] for bad in [

                            "BTC",
                            "ETH",
                            "BNB",
                            "SOL",
                            "XRP",
                            "DOGE",
                            "TON",
                            "PEPE",
                            "XAU",
                            "XAG"

                        ])

                        and

                        15000000
                        <= (
                            x[1].get(
                                "quoteVolume",
                                0
                            ) or 0
                        )
                        <= 400000000

                    )

                ],

                key=lambda x: x[1].get(
                    "quoteVolume",
                    0
                ) or 0,

                reverse=True

            )[:80]

            print(
                "TOP COINS:",
                [x[0] for x in pairs]
            )

            for sym, data in pairs:

                try:

                    if sym in coin_cooldown:

                        if time.time() < coin_cooldown[sym]:
                            continue

                    safe = (
                        sym.replace("/", "")
                        .replace(":", "")
                    )

                    if safe in signal_cache:

                        old = signal_cache[safe].get(
                            "signal_time",
                            0
                        )

                        if time.time() - old < 7200:
                            continue

                    df = get_data(
                        sym,
                        "15m"
                    )

                    if df is None:
                        continue

                    sig, score, reason = analyze(
                        df,
                        sym
                    )

                    if sig is None:
                        continue

                    signal_cache[safe] = {
                        "sym": sym,
                        "price": df["c"].iloc[-1],
                        "signal": sig,
                        "signal_time": time.time()
                    }

                    markup = InlineKeyboardMarkup()

                    markup.add(
                        InlineKeyboardButton(
                            "✅ MANUEL GİR",
                            callback_data=f"enter|{safe}"
                        )
                    )

                    bot.send_message(
                        CHAT_ID,
                        f"""
💀 TREND SIGNAL

📊 {sym}
📈 {sig}

🤖 SCORE: %{score}

📌 {reason}
""",
                        reply_markup=markup
                    )

                    if (
                        score >= 96
                        and
                        not bot_position
                    ):

                        open_trade(
                            signal_cache[safe]
                        )

                    time.sleep(1)

                except Exception as e:

                    print("PAIR ERROR:", e)

            time.sleep(15)

        except Exception as e:

            print("SCANNER ERROR:", e)

            time.sleep(5)

# =========================================================
# CALLBACK
# =========================================================

@bot.callback_query_handler(func=lambda call: True)
def callback(call):

    try:

        if call.data.startswith("enter|"):

            key = call.data.split("|")[1]

            data = signal_cache.get(key)

            if data:

                open_trade(
                    data,
                    True
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
    "🤖 SADIK TREND MASTER AI BOT STARTED"
)

while True:

    try:

        bot.infinity_polling(
            timeout=30,
            long_polling_timeout=30
        )

    except Exception as e:

        print("POLLING ERROR:", e)

        time.sleep(5)
