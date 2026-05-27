# =========================================================
# SADIK BTC AI SCALPER
# =========================================================

import ccxt
import time
import os
import telebot
import threading
import pandas as pd

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

SYMBOL = "BTC/USDT:USDT"

TIMEFRAME = "5m"

MARGIN = 1

LEVERAGE = 20

bot_position = None

ai_model = None

LAST_API_CALL = 0

lock = False

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

                clean.append({

                    "momentum": float(
                        r.get("momentum") or 0
                    ),

                    "volume_ratio": float(
                        r.get("volume_ratio") or 0
                    ),

                    "volatility": float(
                        r.get("volatility") or 0
                    ),

                    "move_1": float(
                        r.get("move_1") or 0
                    ),

                    "move_3": float(
                        r.get("move_3") or 0
                    ),

                    "result": 1 if float(
                        r.get("pnl") or 0
                    ) > 0 else 0

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

            bot.send_message(

                CHAT_ID,

                "⚠️ AI için minimum 50 kapanmış trade gerekli"

            )

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

            n_estimators=300,

            max_depth=8,

            random_state=42

        )

        model.fit(X, y)

        ai_model = model

        print("BTC AI TRAINED")

    except Exception as e:

        print("TRAIN ERROR:", e)

# =========================================================
# GET DATA
# =========================================================

def get_data():

    try:

        ohlcv = safe_api_call(

            exchange.fetch_ohlcv,

            SYMBOL,

            timeframe=TIMEFRAME,

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

        move_5 = (
            (
                closes.iloc[-1]
                -
                closes.iloc[-6]
            )
            /
            closes.iloc[-6]
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

        if volatility < 0.08:
            return None

        if volume_ratio < 1.20:
            return None

        if abs(move_1) > 1.50:
            return None

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

        if probability < 85:
            return None

        if (
            prediction == 1
            and
            move_3 > 0
            and
            move_5 > 0
        ):

            return {

                "signal": "LONG",

                "score": round(probability),

                "momentum": momentum,

                "volume_ratio": volume_ratio,

                "volatility": volatility,

                "move_1": move_1,

                "move_3": move_3

            }

        if (
            prediction == 1
            and
            move_3 < 0
            and
            move_5 < 0
        ):

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

def get_real_size():

    try:

        positions = safe_api_call(

            exchange.fetch_positions,

            [SYMBOL]

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

        if get_real_size() > 0:

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
            SYMBOL
        )

        ticker = safe_api_call(
            exchange.fetch_ticker,
            SYMBOL
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
                SYMBOL,
                amount
            )

        )

        order = safe_api_call(

            exchange.create_market_order,

            SYMBOL,
            side,
            amount

        )

        if not order:

            lock = False
            return

        entry = order.get("average") or price

        bot_position = {

            "type": data["signal"],

            "entry": float(entry),

            "max_pnl": 0,

            "tp1": False,

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

🤖 BTC AI OPEN

📈 {data['signal']}

🔥 AI SCORE:
%{data['score']}

💰 ENTRY:
{round(entry,2)}

⚡ LEVERAGE:
{LEVERAGE}X

"""

        )

    except Exception as e:

        print("OPEN ERROR:", e)

    lock = False

# =========================================================
# SAVE MEMORY
# =========================================================

def save_trade_memory(pnl):

    try:

        if not bot_position:
            return

        features = bot_position["features"]

        supabase.table(
            "trades"
        ).insert({

            "symbol": SYMBOL,

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

        print("SAVE ERROR:", e)

# =========================================================
# CLOSE TRADE
# =========================================================

def close_trade(reason):

    global bot_position

    try:

        if not bot_position:
            return

        side = (
            "sell"
            if bot_position["type"] == "LONG"
            else "buy"
        )

        size = get_real_size()

        if size > 0:

            safe_api_call(

                exchange.create_market_order,

                SYMBOL,

                side,

                size,

                params={

                    "reduceOnly": True

                }

            )

        ticker = safe_api_call(
            exchange.fetch_ticker,
            SYMBOL
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

❌ BTC AI CLOSED

📉 {reason}

💰 PNL:
{round(pnl,2)} USDT

"""

        )

        bot_position = None

    except Exception as e:

        print("CLOSE ERROR:", e)

# =========================================================
# POSITION MANAGER
# =========================================================

def manage():

    global bot_position

    while True:

        try:

            if not bot_position:

                time.sleep(5)
                continue

            real_size = get_real_size()

            if real_size <= 0:

                save_trade_memory(0)

                train_ai()

                bot.send_message(
                    CHAT_ID,
                    "🧠 MANUAL CLOSE DETECTED"
                )

                bot_position = None

                time.sleep(2)

                continue

            ticker = safe_api_call(
                exchange.fetch_ticker,
                SYMBOL
            )

            if not ticker:

                time.sleep(2)
                continue

            price = ticker["last"]

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

            if pnl > bot_position["max_pnl"]:

                bot_position["max_pnl"] = pnl

            max_pnl = bot_position["max_pnl"]

            if (
                pnl >= 0.50
                and
                not bot_position["tp1"]
            ):

                bot_position["tp1"] = True

                bot.send_message(

                    CHAT_ID,

                    f"""

✅ TP1 HIT

💰 PROFIT:
{round(pnl,2)} USDT

"""

                )

            if pnl <= -0.70:

                close_trade(
                    "HARD STOP LOSS"
                )

                continue

            if (
                max_pnl >= 0.80
                and
                pnl <= 0.35
            ):

                close_trade(
                    "TRAILING PROFIT LOCK"
                )

                continue

            if (
                max_pnl >= 2.00
                and
                pnl <= 1.20
            ):

                close_trade(
                    "BIG WIN LOCK"
                )

                continue

            if pnl >= 3.50:

                close_trade(
                    "MEGA TAKE PROFIT"
                )

                continue

            time.sleep(5)

        except Exception as e:

            print("MANAGER ERROR:", e)

            time.sleep(5)

# =========================================================
# SCANNER
# =========================================================

def scanner():

    global bot_position

    while True:

        try:

            if ai_model is None:

                print("AI MODEL NOT READY")

                bot.send_message(

                    CHAT_ID,

                    "⚠️ AI MODEL NOT READY\nMinimum 50 trade memory gerekli"

                )

                time.sleep(30)

                continue

            if bot_position:

                time.sleep(5)
                continue

            df = get_data()

            if df is None:

                time.sleep(5)
                continue

            result = analyze(df)

            if not result:

                time.sleep(10)
                continue

            bot.send_message(

                CHAT_ID,

                f"""

🧠 BTC AI SIGNAL

📈 {result['signal']}

🔥 AI SCORE:
%{result['score']}

⚡ MOMENTUM:
{round(result['momentum'],2)}

📊 VOLUME:
{round(result['volume_ratio'],2)}X

🌪 VOLATILITY:
{round(result['volatility'],2)}%

"""

            )

            if result["score"] >= 85:

                open_trade(result)

            time.sleep(20)

        except Exception as e:

            print("SCANNER ERROR:", e)

            time.sleep(5)

# =========================================================
# START
# =========================================================

train_ai()

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

    f"""

🤖 SADIK BTC AI SCALPER STARTED

📊 {SYMBOL}

⚡ LEVERAGE:
{LEVERAGE}X

🧠 AI:
ACTIVE

"""

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
