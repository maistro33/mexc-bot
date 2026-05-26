# =========================================================
# SADIK REAL AI BOT
# =========================================================

import ccxt
import time
import os
import telebot
import threading
import pandas as pd
import numpy as np

from supabase import create_client

from sklearn.ensemble import RandomForestClassifier

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

    "options": {
        "defaultType": "swap"
    }
})

# =========================================================
# SETTINGS
# =========================================================

MARGIN = 2
LEVERAGE = 20

bot_position = None

coin_cooldown = {}

signal_cache = {}

LAST_API_CALL = 0

lock = False

ai_model = None

# =========================================================
# API SAFE
# =========================================================

def safe_api_call(func, *args, **kwargs):

    global LAST_API_CALL

    for _ in range(5):

        try:

            now = time.time()

            wait = 0.5 - (
                now - LAST_API_CALL
            )

            if wait > 0:
                time.sleep(wait)

            LAST_API_CALL = time.time()

            return func(
                *args,
                **kwargs
            )

        except Exception as e:

            print("API ERROR:", e)

            time.sleep(2)

    return None

# =========================================================
# LOAD AI DATA
# =========================================================

def load_ai_data():

    try:

        rows = supabase.table(
            "trades"
        ).select("*").execute()

        data = rows.data

        if not data:
            return None

        clean = []

        for r in data:

            try:

                momentum = float(
                    r.get("momentum") or 0
                )

                volume_ratio = float(
                    r.get("volume_ratio") or 0
                )

                volatility = float(
                    r.get("volatility") or 0
                )

                move_1 = float(
                    r.get("move_1") or 0
                )

                move_3 = float(
                    r.get("move_3") or 0
                )

                pnl = float(
                    r.get("pnl") or 0
                )

                result = 1 if pnl > 0 else 0

                clean.append({

                    "momentum": momentum,
                    "volume_ratio": volume_ratio,
                    "volatility": volatility,
                    "move_1": move_1,
                    "move_3": move_3,
                    "result": result

                })

            except:
                pass

        return pd.DataFrame(clean)

    except Exception as e:

        print("LOAD AI ERROR:", e)

        return None

# =========================================================
# TRAIN AI
# =========================================================

def train_ai():

    global ai_model

    try:

        df = load_ai_data()

        if df is None:
            return

        if len(df) < 50:

            print("NOT ENOUGH AI DATA")

            return

        X = df[[

            "momentum",
            "volume_ratio",
            "volatility",
            "move_1",
            "move_3"

        ]]

        y = df["result"]

        model = RandomForestClassifier(

            n_estimators=200,

            max_depth=6,

            random_state=42

        )

        model.fit(X, y)

        ai_model = model

        print(
            "REAL AI TRAINED SUCCESS"
        )

    except Exception as e:

        print("AI TRAIN ERROR:", e)

# =========================================================
# GET DATA
# =========================================================

def get_data(
    sym,
    timeframe="5m"
):

    try:

        ohlcv = safe_api_call(

            exchange.fetch_ohlcv,

            sym,

            timeframe=timeframe,

            limit=100

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

        return df

    except Exception as e:

        print("DATA ERROR:", e)

        return None

# =========================================================
# AI ANALYZE
# =========================================================

def analyze(df):

    global ai_model

    try:

        if ai_model is None:
            return None

        closes = df["c"]

        volumes = df["v"]

        price = closes.iloc[-1]

        # =================================================
        # FEATURES
        # =================================================

        move_1 = (

            (
                closes.iloc[-1]
                -
                closes.iloc[-2]
            )

            /

            closes.iloc[-2]

        ) * 100

        move_3 = (

            (
                closes.iloc[-1]
                -
                closes.iloc[-4]
            )

            /

            closes.iloc[-4]

        ) * 100

        momentum = abs(move_3)

        volume_avg = (

            volumes
            .rolling(20)
            .mean()
            .iloc[-1]

        )

        if volume_avg <= 0:
            return None

        volume_ratio = (

            volumes.iloc[-1]

            /

            volume_avg

        )

        volatility = (

            (
                df["h"].iloc[-1]
                -
                df["l"].iloc[-1]
            )

            /

            price

        ) * 100

        # =================================================
        # AI PREDICT
        # =================================================

        features = [[

            momentum,
            volume_ratio,
            volatility,
            move_1,
            move_3

        ]]

features_df = pd.DataFrame(

    features,

    columns=[

        "momentum",
        "volume_ratio",
        "volatility",
        "move_1",
        "move_3"

    ]

)

prediction = ai_model.predict(
    features_df
)[0]

probability = max(

    ai_model.predict_proba(
        features_df
    )[0]

) * 100

        if probability < 75:
            return None

        # =================================================
        # LONG
        # =================================================

        if prediction == 1 and move_3 > 0:

            return {

                "signal": "LONG",

                "score": round(probability),

                "momentum": momentum,

                "volume_ratio": volume_ratio,

                "volatility": volatility,

                "move_1": move_1,

                "move_3": move_3

            }

        # =================================================
        # SHORT
        # =================================================

        if prediction == 1 and move_3 < 0:

            return {

                "signal": "SHORT",

                "score": round(probability),

                "momentum": momentum,

                "volume_ratio": volume_ratio,

                "volatility": volatility,

                "move_1": move_1,

                "move_3": move_3

            }

        return None

    except Exception as e:

        print("ANALYZE ERROR:", e)

        return None

# =========================================================
# REAL POSITION SIZE
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

                or

                p.get("size")

                or 0

            )

            size = abs(float(size))

            if size > 0:
                return size

    except Exception as e:

        print("SIZE ERROR:", e)

    return 0

# =========================================================
# OPEN TRADE
# =========================================================

def open_trade(data):

    global bot_position
    global lock

    if lock:
        return

    if bot_position:
        return

    lock = True

    try:

        sym = data["sym"]

        if get_real_size(sym) > 0:

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

            sym

        )

        ticker = safe_api_call(

            exchange.fetch_ticker,

            sym

        )

        if not ticker:

            lock = False

            return

        price = ticker["last"]

        amount = (

            MARGIN * LEVERAGE

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

            lock = False

            return

        entry = order.get("average") or price

        bot_position = {

            "sym": sym,

            "type": data["signal"],

            "entry": float(entry),

            "max_pnl": 0,

            "open_time": time.time(),

            "ai_score": data["score"],

            "features": {

                "momentum": data["momentum"],

                "volume_ratio": data["volume_ratio"],

                "volatility": data["volatility"],

                "move_1": data["move_1"],

                "move_3": data["move_3"]

            }

        }

        bot.send_message(

            CHAT_ID,

            f"""

🤖 REAL AI OPEN

📊 {sym}

📈 {data['signal']}

🔥 AI SCORE:
%{data['score']}

💰 ENTRY:
{round(entry,5)}

"""

        )

    except Exception as e:

        print("OPEN ERROR:", e)

    lock = False

# =========================================================
# SAVE TRADE AI MEMORY
# =========================================================

def save_trade_memory(pnl):

    try:

        if not bot_position:
            return

        features = bot_position["features"]

        supabase.table(
            "trades"
        ).insert({

            "symbol": bot_position["sym"],

            "signal": bot_position["type"],

            "momentum": features["momentum"],

            "volume_ratio": features["volume_ratio"],

            "volatility": features["volatility"],

            "move_1": features["move_1"],

            "move_3": features["move_3"],

            "pnl": pnl,

            "ai_score": bot_position["ai_score"]

        }).execute()

    except Exception as e:

        print("SAVE MEMORY ERROR:", e)

# =========================================================
# CLOSE TRADE
# =========================================================

def close_trade(reason):

    global bot_position

    try:

        if not bot_position:
            return

        sym = bot_position["sym"]

        side = (

            "sell"

            if bot_position["type"] == "LONG"

            else "buy"

        )

        size = get_real_size(sym)

        if size > 0:

            safe_api_call(

                exchange.create_market_order,

                sym,

                side,

                size,

                params={

                    "reduceOnly": True

                }

            )

        ticker = safe_api_call(

            exchange.fetch_ticker,

            sym

        )

        pnl = 0

        if ticker:

            current_price = ticker["last"]

            if bot_position["type"] == "LONG":

                pnl_percent = (

                    (
                        current_price
                        -
                        bot_position["entry"]
                    )

                    /

                    bot_position["entry"]

                ) * 100

            else:

                pnl_percent = (

                    (
                        bot_position["entry"]
                        -
                        current_price
                    )

                    /

                    bot_position["entry"]

                ) * 100

            pnl = (

                pnl_percent / 100

            ) * (

                MARGIN * LEVERAGE

            )

        save_trade_memory(pnl)
        train_ai()

        bot.send_message(

            CHAT_ID,

            f"""

❌ REAL AI CLOSED

📊 {sym}

📉 {reason}

💰 PNL:
{round(pnl,2)} USDT

"""

        )

        coin_cooldown[sym] = (
            time.time() + 1800
        )

        bot_position = None

    except Exception as e:

        print("CLOSE ERROR:", e)

# =========================================================
# AI POSITION MANAGER
# =========================================================

def manage():

    global bot_position

    while True:

        try:

            if not bot_position:

                time.sleep(5)

                continue

            sym = bot_position["sym"]

            real_size = get_real_size(sym)

            if real_size <= 0:

                bot_position = None

                time.sleep(2)

                continue

            ticker = safe_api_call(

                exchange.fetch_ticker,

                sym

            )

            if not ticker:

                time.sleep(2)

                continue

            price = ticker["last"]

            # =================================================
            # PNL
            # =================================================

            if bot_position["type"] == "LONG":

                pnl_percent = (

                    (
                        price
                        -
                        bot_position["entry"]
                    )

                    /

                    bot_position["entry"]

                ) * 100

            else:

                pnl_percent = (

                    (
                        bot_position["entry"]
                        -
                        price
                    )

                    /

                    bot_position["entry"]

                ) * 100

            pnl = (

                pnl_percent / 100

            ) * (

                MARGIN * LEVERAGE

            )

            # =================================================
            # MAX PROFIT
            # =================================================

            if pnl > bot_position["max_pnl"]:

                bot_position["max_pnl"] = pnl

            max_pnl = bot_position["max_pnl"]

            # =================================================
            # HARD STOP LOSS
            # =================================================

            if pnl <= -1.00:

                close_trade(
                    "AI STOP LOSS"
                )

                continue

            # =================================================
            # AI PROFIT LOCK
            # =================================================

            if (

                max_pnl >= 1.050

                and

                pnl <= 0.80

            ):

                close_trade(
                    "AI PROFIT LOCK"
                )

                continue

            # =================================================
            # BIG WIN LOCK
            # =================================================

            if (

                max_pnl >= 4.00

                and

                pnl <= 2.80

            ):

                close_trade(
                    "BIG WIN LOCK"
                )

                continue

            # =================================================
            # MEGA TAKE PROFIT
            # =================================================

            if pnl >= 5:

                close_trade(
                    "MEGA TAKE PROFIT"
                )

                continue

            time.sleep(5)

        except Exception as e:

            print("MANAGE ERROR:", e)

            time.sleep(5)

# =========================================================
# AI SCANNER
# =========================================================

def scanner():

    global bot_position

    while True:

        try:

            if ai_model is None:

                print("AI MODEL NOT READY")

                time.sleep(10)

                continue

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

                        not any(

                            bad in x[0]

                            for bad in [

                                "BTC",
                                "ETH",
                                "BNB",
                                "XRP",
                                "DOGE"

                            ]

                        )

                        and

                        10000000

                        <=

                        (
                            x[1].get(
                                "quoteVolume",
                                0
                            ) or 0
                        )

                    )

                ],

                key=lambda x: (

                    x[1].get(
                        "quoteVolume",
                        0
                    ) or 0

                ),

                reverse=True

            )[:40]

            print(
                "AI SCANNING:",
                [x[0] for x in pairs]
            )

            for sym, data in pairs:

                try:

                    if bot_position:
                        break

                    if sym in coin_cooldown:

                        if (
                            time.time()
                            <
                            coin_cooldown[sym]
                        ):

                            continue

                    safe = (

                        sym.replace("/", "")

                        .replace(":", "")

                    )

                    if safe in signal_cache:

                        old = signal_cache[safe].get(
                            "time",
                            0
                        )

                        if (
                            time.time() - old
                            <
                            1800
                        ):

                            continue

                    df = get_data(
                        sym,
                        "5m"
                    )

                    if df is None:
                        continue

                    result = analyze(df)

                    if not result:
                        continue

                    signal_cache[safe] = {

                        "time": time.time()

                    }

                    bot.send_message(

                        CHAT_ID,

                        f"""

🤖 REAL AI SIGNAL

📊 {sym}

📈 {result['signal']}

🔥 AI PROBABILITY:
%{result['score']}

"""

                    )

                    # =========================================
                    # REAL AI AUTO ENTRY
                    # =========================================

                    if result["score"] >= 80:

                        open_trade({

                            "sym": sym,

                            "signal": result["signal"],

                            "score": result["score"],

                            "momentum": result["momentum"],

                            "volume_ratio": result["volume_ratio"],

                            "volatility": result["volatility"],

                            "move_1": result["move_1"],

                            "move_3": result["move_3"]

                        })

                    time.sleep(1)

                except Exception as e:

                    print("PAIR ERROR:", e)

            time.sleep(10)

        except Exception as e:

            print("SCANNER ERROR:", e)

            time.sleep(5)

# =========================================================
# TRAIN AI FIRST
# =========================================================

train_ai()

# =========================================================
# START THREADS
# =========================================================

threading.Thread(

    target=scanner,

    daemon=True

).start()

threading.Thread(

    target=manage,

    daemon=True

).start()

# =========================================================
# START MESSAGE
# =========================================================

bot.send_message(

    CHAT_ID,

    "🤖 REAL AI BOT STARTED"

)

# =========================================================
# POLLING
# =========================================================

while True:

    try:

        bot.infinity_polling(

            timeout=30,

            long_polling_timeout=30

        )

    except Exception as e:

        print("POLLING ERROR:", e)

        time.sleep(5)
