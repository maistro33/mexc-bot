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
    "options": {
        "defaultType": "swap"
    },
    "enableRateLimit": True
})

# =========================================================
# SETTINGS
# =========================================================

MARGIN = 3
LEVERAGE = 7

bot_position = None
manual_positions = []

signal_cache = {}

last_signal_time = 0
last_close_time = 0

lock = False

coin_cooldown = {}

BLOCKED_COINS = [
    "BTC/USDT:USDT",
    "ETH/USDT:USDT",
    "BNB/USDT:USDT"
]

# =========================================================
# DATA
# =========================================================

def get_data(sym):

    try:

        ohlcv = exchange.fetch_ohlcv(
            sym,
            timeframe="5m",
            limit=100
        )

        df = pd.DataFrame(
            ohlcv,
            columns=["t", "o", "h", "l", "c", "v"]
        )

        df["ema"] = df["c"].ewm(span=20).mean()

        return df

    except Exception as e:

        print("DATA ERROR:", e)
        return None

# =========================================================
# BTC FILTER
# =========================================================

def btc_filter(signal):

    try:

        btc = get_data("BTC/USDT:USDT")

        if btc is None:
            return False

        btc_price = btc["c"].iloc[-1]
        btc_ema = btc["ema"].iloc[-1]

        if signal == "LONG" and btc_price < btc_ema:
            return False

        if signal == "SHORT" and btc_price > btc_ema:
            return False

        return True

    except Exception as e:

        print("BTC FILTER ERROR:", e)
        return False

# =========================================================
# SUPABASE AI STATS
# =========================================================

def get_coin_stats(symbol, side):

    try:

        rows = supabase.table("trades") \
            .select("pnl") \
            .eq("symbol", symbol) \
            .eq("side", side) \
            .limit(100) \
            .execute()

        data = rows.data

        if not data:
            return 50

        wins = 0

        for r in data:

            if float(r["pnl"]) > 0:
                wins += 1

        wr = (wins / len(data)) * 100

        return wr

    except Exception as e:

        print("AI STATS ERROR:", e)

        return 50

# =========================================================
# SAVE TRADE
# =========================================================

def save_trade(pos, pnl, reason):

    try:

        result = "WIN" if pnl > 0 else "LOSS"

        data = {

            "symbol": pos["sym"],

            "side": pos["type"],

            "entry_price": float(pos["entry"]),

            "exit_price": float(pos.get("last_price", 0)),

            "pnl": float(round(pnl, 4)),

            "result": result,

            "close_reason": reason,

            "created_at": pd.Timestamp.utcnow().isoformat()
        }

        supabase.table("trades").insert(data).execute()

    except Exception as e:

        print("SAVE TRADE ERROR:", e)

# =========================================================
# ANALYZE
# =========================================================

def analyze(df, sym):

    try:

        price = df["c"].iloc[-1]

        ema_now = df["ema"].iloc[-1]
        ema_prev = df["ema"].iloc[-5]

        # =================================================
        # VOLUME FILTER
        # =================================================

        avg_vol = df["v"].rolling(15).mean().iloc[-1]

        if avg_vol <= 0:
            return None, 0, "Volume invalid"

        volume_ratio = (
            df["v"].iloc[-1] / avg_vol
        )

        if volume_ratio < 1.8:
            return None, 0, "Weak volume"

        # =================================================
        # VOLATILITY FILTER
        # =================================================

        volatility = (
            df["h"].iloc[-1] - df["l"].iloc[-1]
        ) / price

        if volatility < 0.006:
            return None, 0, "Low volatility"

        # =================================================
        # MOMENTUM FILTER
        # =================================================

        change = abs(
            price - df["c"].iloc[-5]
        ) / df["c"].iloc[-5]

        if change < 0.004:
            return None, 0, "Weak move"

        # =================================================
        # CANDLE FILTER
        # =================================================

        body = abs(
            df["c"].iloc[-1] - df["o"].iloc[-1]
        )

        candle_range = (
            df["h"].iloc[-1] - df["l"].iloc[-1]
        )

        if candle_range <= 0:
            return None, 0, "Bad candle"

        body_ratio = body / candle_range

        if body_ratio < 0.50:
            return None, 0, "Fake breakout"

        # =================================================
        # EMA DISTANCE
        # =================================================

        ema_distance = abs(
            price - ema_now
        ) / ema_now

        if ema_distance > 0.015:
            return None, 0, "Too extended"

        # =================================================
        # OLD MOVE FILTER
        # =================================================

        recent_high = df["h"].rolling(20).max().iloc[-2]
        recent_low = df["l"].rolling(20).min().iloc[-2]

        # =================================================
        # LONG
        # =================================================

        if ema_now > ema_prev and price > ema_now:

            if not btc_filter("LONG"):
                return None, 0, "BTC bearish"

            distance_from_low = (
                price - recent_low
            ) / recent_low

            if distance_from_low > 0.04:
                return None, 0, "Move too old"

            historical_wr = get_coin_stats(
                sym,
                "LONG"
            )

            score = 70

            if historical_wr >= 55:
                score += 10

            if historical_wr >= 65:
                score += 10

            if historical_wr >= 75:
                score += 5

            return (
                "LONG",
                score,
                f"AI WR %{round(historical_wr,1)}"
            )

        # =================================================
        # SHORT
        # =================================================

        if ema_now < ema_prev and price < ema_now:

            if not btc_filter("SHORT"):
                return None, 0, "BTC bullish"

            distance_from_high = (
                recent_high - price
            ) / recent_high

            if distance_from_high > 0.04:
                return None, 0, "Move too old"

            historical_wr = get_coin_stats(
                sym,
                "SHORT"
            )

            score = 70

            if historical_wr >= 55:
                score += 10

            if historical_wr >= 65:
                score += 10

            if historical_wr >= 75:
                score += 5

            return (
                "SHORT",
                score,
                f"AI WR %{round(historical_wr,1)}"
            )

        return None, 0, "No trend"

    except Exception as e:

        print("ANALYZE ERROR:", e)

        return None, 0, "Analyze error"

# =========================================================
# REAL POSITION SIZE
# =========================================================

def get_real_size(sym):

    try:

        positions = exchange.fetch_positions([sym])

        for p in positions:

            psym = p["symbol"].replace("/", "").replace(":USDT", "")
            csym = sym.replace("/", "").replace(":USDT", "")

            if psym != csym:
                continue

            size = (
                p.get("contracts")
                or p.get("contractSize")
                or p.get("size")
                or p.get("info", {}).get("total")
                or 0
            )

            size = abs(float(size))

            if size > 0:
                return size

    except Exception as e:

        print("SIZE ERROR:", e)

    return 0

# =========================================================
# RESTORE POSITIONS
# =========================================================

def restore_positions():

    global bot_position

    try:

        positions = exchange.fetch_positions()

        for p in positions:

            try:

                size = (
                    p.get("contracts")
                    or p.get("contractSize")
                    or p.get("size")
                    or 0
                )

                size = abs(float(size))

                if size <= 0:
                    continue

                side = str(
                    p.get("side", "")
                ).lower()

                if side == "long":
                    ptype = "LONG"
                else:
                    ptype = "SHORT"

                entry = float(
                    p.get("entryPrice")
                    or p.get("markPrice")
                    or 0
                )

                if entry <= 0:
                    continue

                bot_position = {
                    "sym": p["symbol"],
                    "type": ptype,
                    "entry": entry,
                    "max": 0,
                    "trailing": False,
                    "open_time": time.time()
                }

                bot.send_message(
                    CHAT_ID,
                    f"♻️ RESTORE {p['symbol']}"
                )

                break

            except:
                pass

    except Exception as e:

        print("RESTORE ERROR:", e)

# =========================================================
# OPEN TRADE
# =========================================================

def open_trade(data, is_manual):

    global bot_position
    global manual_positions
    global lock

    if lock:
        return

    if not is_manual and bot_position:
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

        exchange.set_leverage(
            LEVERAGE,
            data["sym"]
        )

        ticker = exchange.fetch_ticker(
            data["sym"]
        )

        real_price = ticker["last"]

        amount = (
            MARGIN * LEVERAGE
        ) / real_price

        order = exchange.create_market_order(
            data["sym"],
            side,
            float(amount)
        )

        entry_price = (
            order.get("average")
            or real_price
        )

        pos = {
            "sym": data["sym"],
            "type": data["signal"],
            "entry": float(entry_price),
            "max": 0,
            "trailing": False,
            "open_time": time.time()
        }

        if is_manual:

            manual_positions.append(pos)

            bot.send_message(
                CHAT_ID,
                f"🧑 MANUEL AÇILDI\n\n{data['sym']}"
            )

        else:

            bot_position = pos

            bot.send_message(
                CHAT_ID,
                f"🤖 BOT AÇTI\n\n{data['sym']}"
            )

    except Exception as e:

        print("OPEN ERROR:", e)

    lock = False

# =========================================================
# CLOSE TRADE
# =========================================================

def close_trade(pos, reason, is_manual):

    global bot_position
    global manual_positions
    global last_close_time

    try:

        side = (
            "sell"
            if pos["type"] == "LONG"
            else "buy"
        )

        size = get_real_size(pos["sym"])

        if size > 0:

            exchange.create_market_order(
                pos["sym"],
                side,
                size,
                params={
                    "reduceOnly": True
                }
            )

        current_price = exchange.fetch_ticker(
            pos["sym"]
        )["last"]

        pos["last_price"] = current_price

        if pos["type"] == "LONG":

            pnl = (
                (current_price - pos["entry"])
                / pos["entry"]
            ) * (
                MARGIN * LEVERAGE
            )

        else:

            pnl = (
                (pos["entry"] - current_price)
                / pos["entry"]
            ) * (
                MARGIN * LEVERAGE
            )

        save_trade(
            pos,
            pnl,
            reason
        )

        coin_cooldown[pos["sym"]] = time.time()

        bot.send_message(
            CHAT_ID,
            f"""
⛔ POZİSYON KAPANDI

📊 {pos['sym']}
📉 Sebep: {reason}
💰 PNL: {round(pnl,2)} USDT
"""
        )

    except Exception as e:

        print("CLOSE ERROR:", e)

    if is_manual:

        if pos in manual_positions:
            manual_positions.remove(pos)

    else:

        bot_position = None
        last_close_time = time.time()

# =========================================================
# SCANNER
# =========================================================

def scanner():

    global last_signal_time
    global bot_position
    global last_close_time

    while True:

        try:

            if time.time() - last_close_time < 15:

                time.sleep(3)
                continue

            tickers = exchange.fetch_tickers()

            top = sorted(
                tickers.items(),
                key=lambda x: x[1].get(
                    "quoteVolume",
                    0
                ) or 0,
                reverse=True
            )[:40]

            for sym, data in top:

                try:

                    if time.time() - last_signal_time < 10:
                        continue

                    if ":USDT" not in sym:
                        continue

                    if sym in BLOCKED_COINS:
                        continue

                    if sym in coin_cooldown:

                        if (
                            time.time()
                            - coin_cooldown[sym]
                        ) < 900:

                            continue

                    df = get_data(sym)

                    if df is None:
                        continue

                    safe = (
                        sym.replace("/", "")
                        .replace(":", "")
                    )

                    if safe in signal_cache:

                        if (
                            time.time()
                            - signal_cache[safe]["t"]
                        ) < 120:

                            continue

                    sig, score, reason = analyze(
                        df,
                        sym
                    )

                    if sig is None:
                        continue

                    price = df["c"].iloc[-1]

                    signal_cache[safe] = {
                        "sym": sym,
                        "price": price,
                        "signal": sig,
                        "t": time.time()
                    }

                    decision = (
                        "🔥 GİR"
                        if not bot_position
                        else "❌ PAS"
                    )

                    markup = InlineKeyboardMarkup()

                    markup.add(
                        InlineKeyboardButton(
                            "✅ GİR",
                            callback_data=f"enter|{safe}"
                        )
                    )

                    bot.send_message(
                        CHAT_ID,
                        f"""
💀 AKILLI SİNYAL

📊 {sym}
📈 {sig}
💰 {round(price,4)}

🤖 Güç: %{score}
🤖 Karar: {decision}

📊 Sebep:
{reason}
""",
                        reply_markup=markup
                    )

                    last_signal_time = time.time()

                    if (
                        score >= 90
                        and not bot_position
                    ):

                        open_trade(
                            signal_cache[safe],
                            False
                        )

                    time.sleep(1)

                except Exception as e:

                    print("PAIR ERROR:", e)

            time.sleep(8)

        except Exception as e:

            print("SCAN ERROR:", e)
            time.sleep(5)

# =========================================================
# MANAGE
# =========================================================

def manage():

    global bot_position
    global manual_positions

    while True:

        try:

            all_positions = []

            if bot_position:

                all_positions.append(
                    (bot_position, False)
                )

            for p in manual_positions[:]:

                all_positions.append(
                    (p, True)
                )

            for pos, is_manual in all_positions:

                try:

                    if (
                        time.time()
                        - pos["open_time"]
                    ) < 8:

                        continue

                    ticker = exchange.fetch_ticker(
                        pos["sym"]
                    )

                    price = ticker["last"]

                    pos["last_price"] = price

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

                    if (
                        pnl >= 0.30
                        and not pos["trailing"]
                    ):

                        pos["trailing"] = True

                        bot.send_message(
                            CHAT_ID,
                            f"""
🔒 TRAILING AKTİF

📊 {pos['sym']}
💰 {round(pnl,2)} USDT
"""
                        )

                    if pos["trailing"]:

                        trail_gap = max(
                            0.15,
                            pos["max"] * 0.35
                        )

                        if pnl < (
                            pos["max"]
                            - trail_gap
                        ):

                            close_trade(
                                pos,
                                "TRAIL",
                                is_manual
                            )

                            continue

                    if pnl <= -0.40:

                        close_trade(
                            pos,
                            "SL",
                            is_manual
                        )

                        continue

                except Exception as e:

                    print("POSITION ERROR:", e)

        except Exception as e:

            print("MANAGE ERROR:", e)

        time.sleep(2)

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

restore_positions()

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
    "💀 BOT AKTİF (AI SUPABASE VERSION)"
)

bot.infinity_polling()
