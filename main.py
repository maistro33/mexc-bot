# =========================================================
# SADIK FINAL FAST QUALITY BOT
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
LEVERAGE = 10

bot_position = None
manual_positions = []

signal_cache = {}
coin_cooldown = {}
loss_streak = {}
last_direction = {}

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

            wait_time = 0.8 - (now - LAST_API_CALL)

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

def get_data(sym):

    try:

        ohlcv = safe_api_call(
            exchange.fetch_ohlcv,
            sym,
            timeframe="5m",
            limit=120
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

        return df

    except Exception as e:

        print("DATA ERROR:", e)

        return None

# =========================================================
# BTC FILTER CACHE
# =========================================================

def btc_filter(signal):

    global btc_cache

    try:

        now = time.time()

        if now - btc_cache["time"] > 60:

            df = get_data("BTC/USDT:USDT")

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

        price = df["c"].iloc[-1]

        ema20 = df["ema20"].iloc[-1]
        ema50 = df["ema50"].iloc[-1]

        adx = calculate_adx(df)

        if adx < 18:
            return None, 0, "CHOP"

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

        if volume_ratio < 1.10:
            return None, 0, "LOW VOLUME"

        recent_move = abs(
            price - df["c"].iloc[-4]
        ) / df["c"].iloc[-4]

        if recent_move > 0.03:
            return None, 0, "PUMP"

        # =====================================================
        # LONG
        # =====================================================

        if ema20 > ema50:

            if not btc_filter("LONG"):
                return None, 0, "BTC FILTER"

            pullback_ok = (
                price <= ema20 * 1.008
            )

            if not pullback_ok:
                return None, 0, "NO PULLBACK"

            score = 90

            if adx > 25:
                score += 2

            return "LONG", score, "PULLBACK LONG"

        # =====================================================
        # SHORT
        # =====================================================

        if ema20 < ema50:

            if not btc_filter("SHORT"):
                return None, 0, "BTC FILTER"

            pullback_ok = (
                price >= ema20 * 0.992
            )

            if not pullback_ok:
                return None, 0, "NO PULLBACK"

            score = 90

            if adx > 25:
                score += 2

            return "SHORT", score, "PULLBACK SHORT"

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
        time.time() + 3600
    )

    last_direction[pos["sym"]] = pos["type"]

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

                if pnl >= 0.45 and not pos["tp1"]:

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
                # SMART PROFIT LOCK
                # =================================================

                if pos["max"] >= 0.45 and pnl <= 0.20:

                    close_trade(
                        pos,
                        "PROFIT LOCK 1",
                        is_manual
                    )

                    continue

                elif pos["max"] >= 0.80 and pnl <= 0.50:

                    close_trade(
                        pos,
                        "PROFIT LOCK 2",
                        is_manual
                    )

                    continue

                elif pos["max"] >= 1.20 and pnl <= 0.90:

                    close_trade(
                        pos,
                        "PROFIT LOCK 3",
                        is_manual
                    )

                    continue

                elif pos["max"] >= 1.80 and pnl <= 1.40:

                    close_trade(
                        pos,
                        "PROFIT LOCK 4",
                        is_manual
                    )

                    continue

                # =================================================
                # STOP LOSS
                # =================================================

                if pnl <= -0.60:

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

                        5000000
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

            )[:100]

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

                        if time.time() - old < 3600:
                            continue

                    df = get_data(sym)

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
💀 SIGNAL

📊 {sym}
📈 {sig}

🤖 SCORE: %{score}

📌 {reason}
""",
                        reply_markup=markup
                    )

                    if (
                        score >= 92
                        and
                        not bot_position
                    ):

                        open_trade(
                            signal_cache[safe]
                        )

                    time.sleep(0.5)

                except Exception as e:

                    print("PAIR ERROR:", e)

            time.sleep(8)

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
    "🤖 SADIK FINAL FAST QUALITY BOT STARTED"
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
