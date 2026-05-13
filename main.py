# =========================================================
# SADIK BOT PRO IMPROVED VERSION
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

BLOCKED_COINS = [
    "BTC/USDT:USDT",
    "ETH/USDT:USDT",
    "BNB/USDT:USDT",
    "XAU/USDT:USDT",
    "XAG/USDT:USDT"
]

LAST_API_CALL = 0

# =========================================================
# API SAFE
# =========================================================

def safe_api_call(func, *args, **kwargs):

    global LAST_API_CALL

    for _ in range(5):

        try:

            now = time.time()

            wait_time = 1.1 - (now - LAST_API_CALL)

            if wait_time > 0:
                time.sleep(wait_time)

            LAST_API_CALL = time.time()

            return func(*args, **kwargs)

        except Exception as e:

            print("API ERROR:", e)

            try:
                bot.send_message(
                    CHAT_ID,
                    f"❌ API ERROR\n{str(e)}"
                )
            except:
                pass

            time.sleep(3)

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

        plus_di = 100 * (plus_dm.rolling(period).mean() / atr)
        minus_di = abs(100 * (minus_dm.rolling(period).mean() / atr))

        dx = abs(plus_di - minus_di) / (plus_di + minus_di) * 100

        adx = dx.rolling(period).mean()

        return adx.iloc[-1]

    except:
        return 0

# =========================================================
# DATA
# =========================================================

def get_data(sym):

    try:

        ohlcv = safe_api_call(
            exchange.fetch_ohlcv,
            sym,
            timeframe="5m",
            limit=150
        )

        if not ohlcv:
            return None

        df = pd.DataFrame(
            ohlcv,
            columns=["t", "o", "h", "l", "c", "v"]
        )

        df["ema20"] = df["c"].ewm(span=20).mean()
        df["ema50"] = df["c"].ewm(span=50).mean()

        return df

    except Exception as e:

        print("DATA ERROR:", e)
        return None

# =========================================================
# BTC FILTER
# =========================================================

def btc_filter(signal):

    try:

        df = get_data("BTC/USDT:USDT")

        if df is None:
            return False

        price = df["c"].iloc[-1]
        ema20 = df["ema20"].iloc[-1]
        ema50 = df["ema50"].iloc[-1]

        if signal == "LONG":
            return price > ema20 > ema50

        if signal == "SHORT":
            return price < ema20 < ema50

        return False

    except:
        return False

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
                or p.get("info", {}).get("total")
                or p.get("info", {}).get("openDelegateSize")
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

        if adx < 20:
            return None, 0, "CHOP MARKET"

        avg_vol = df["v"].rolling(20).mean().iloc[-1]

        if avg_vol <= 0:
            return None, 0, "BAD VOLUME"

        volume_ratio = df["v"].iloc[-1] / avg_vol

        if volume_ratio < 1.3:
            return None, 0, "LOW VOLUME"

        recent_move = abs(
            price - df["c"].iloc[-4]
        ) / df["c"].iloc[-4]

        if recent_move > 0.025:
            return None, 0, "PUMP DETECTED"

        # =====================================================
        # LONG
        # =====================================================

        if ema20 > ema50:

            if not btc_filter("LONG"):
                return None, 0, "BTC FILTER"

            pullback_ok = (
                price <= ema20 * 1.003
            )

            if not pullback_ok:
                return None, 0, "NO PULLBACK"

            score = 88

            if adx > 25:
                score += 4

            if volume_ratio > 1.8:
                score += 4

            return "LONG", score, "PULLBACK LONG"

        # =====================================================
        # SHORT
        # =====================================================

        if ema20 < ema50:

            if not btc_filter("SHORT"):
                return None, 0, "BTC FILTER"

            pullback_ok = (
                price >= ema20 * 0.997
            )

            if not pullback_ok:
                return None, 0, "NO PULLBACK"

            score = 88

            if adx > 25:
                score += 4

            if volume_ratio > 1.8:
                score += 4

            return "SHORT", score, "PULLBACK SHORT"

        return None, 0, "NO TREND"

    except Exception as e:

        print("ANALYZE ERROR:", e)

        return None, 0, "ERROR"

# =========================================================
# OPEN
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

        order = safe_api_call(
            exchange.create_market_order,
            data["sym"],
            side,
            float(amount)
        )

        if not order:

            bot.send_message(
                CHAT_ID,
                f"❌ ORDER FAILED\n{data['sym']}"
            )

            lock = False
            return

        entry = order.get("average") or price

        pos = {
            "sym": data["sym"],
            "type": data["signal"],
            "entry": float(entry),
            "max": 0,
            "tp1": False,
            "breakeven": False,
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

        try:
            bot.send_message(
                CHAT_ID,
                f"❌ OPEN ERROR\n{str(e)}"
            )
        except:
            pass

    lock = False

# =========================================================
# CLOSE
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

            time.sleep(2)

            remain = get_real_size(pos["sym"])

            if remain > 0:

                safe_api_call(
                    exchange.create_market_order,
                    pos["sym"],
                    side,
                    remain,
                    params={
                        "reduceOnly": True
                    }
                )

        ticker = safe_api_call(
            exchange.fetch_ticker,
            pos["sym"]
        )

        if not ticker:
            return

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

        if pnl < 0:

            loss_streak[pos["sym"]] = (
                loss_streak.get(pos["sym"], 0) + 1
            )

            coin_cooldown[pos["sym"]] = (
                time.time() + 7200
            )

        else:

            loss_streak[pos["sym"]] = 0

        last_direction[pos["sym"]] = pos["type"]

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

                    bot.send_message(
                        CHAT_ID,
                        f"⚠️ MANUAL CLOSE DETECTED\n{pos['sym']}"
                    )

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
                    pos["breakeven"] = True

                    bot.send_message(
                        CHAT_ID,
                        f"✅ TP1 HIT\n{pos['sym']}"
                    )

                # =================================================
                # BREAK EVEN
                # =================================================

                if pos["breakeven"]:

                    if pnl <= 0.05:

                        close_trade(
                            pos,
                            "BREAK EVEN",
                            is_manual
                        )

                        continue

                # =================================================
                # TRAILING
                # =================================================

                if pnl >= 0.80:

                    trail_gap = max(
                        0.25,
                        pos["max"] * 0.45
                    )

                    if pnl < (
                        pos["max"] - trail_gap
                    ):

                        close_trade(
                            pos,
                            "TRAIL",
                            is_manual
                        )

                        continue

                # =================================================
                # STOP
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

        time.sleep(4)

# =========================================================
# SCANNER
# =========================================================

def scanner():

    global bot_position

    while True:

        try:

            if bot_position:
                time.sleep(5)
                continue

            tickers = safe_api_call(
                exchange.fetch_tickers
            )

            if not tickers:

                time.sleep(5)
                continue

            pairs = sorted(
                tickers.items(),
                key=lambda x: x[1].get(
                    "quoteVolume",
                    0
                ) or 0,
                reverse=True
            )[:20]

            for sym, data in pairs:

                try:

                    if ":USDT" not in sym:
                        continue

                    if sym in BLOCKED_COINS:
                        continue

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

                        if time.time() - old < 1800:
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

                    if last_direction.get(sym) == sig:
                        continue

                    price = df["c"].iloc[-1]

                    signal_cache[safe] = {
                        "sym": sym,
                        "price": price,
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

                    if score >= 92:

                        open_trade(
                            signal_cache[safe]
                        )

                    time.sleep(1)

                except Exception as e:

                    print("PAIR ERROR:", e)

            time.sleep(10)

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
    "🤖 SADIK BOT PRO STARTED"
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
