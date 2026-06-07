# =========================================================
# SADIK BTC SCALP AI PRO
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

TIMEFRAME = "1m"

TREND_TIMEFRAME = "5m"
TREND15_TIMEFRAME = "15m"

MARGIN = 2

LEVERAGE = 20

NET_PROFIT_TARGET = 0.30
FEE_BUFFER = 0.06
TP1_USDT = NET_PROFIT_TARGET + FEE_BUFFER

TRAIL_TRIGGER = 0.40

TRAIL_STOP = 0.30

STOP_LOSS = -0.45

MEGA_TP = 1.50

bot_position = None

ai_model = None

LAST_API_CALL = 0

lock = False

# ================= V1 AI FILTERS =================
PULLBACK_PERCENT = 0.03
MARKET_AI_MIN_SCORE = 65
MIN_MOMENTUM = 0.15
MIN_VOLATILITY = 0.08
VOLUME_SPIKE_MIN = 1.20


# =========================================================
# API SAFE
# =========================================================

def safe_api_call(func, *args, **kwargs):

    global LAST_API_CALL

    for _ in range(5):

        try:

            now = time.time()

            wait = 0.3 - (
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

        print("AI TRAINED")

    except Exception as e:

        print("TRAIN ERROR:", e)

# =========================================================
# GET DATA
# =========================================================

def get_data(tf="1m"):

    try:

        ohlcv = safe_api_call(

            exchange.fetch_ohlcv,

            SYMBOL,

            timeframe=tf,

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
# ANALYZE
# =========================================================

def analyze():

    global ai_model

    try:

        df = get_data(TIMEFRAME)

        trend_df = get_data(TREND_TIMEFRAME)
        trend15_df = get_data(TREND15_TIMEFRAME)

        if df is None or trend_df is None or trend15_df is None:
            return None

        closes = df["c"]
        volumes = df["v"]

        trend_closes = trend_df["c"]
        trend15_closes = trend15_df["c"]

        ema9 = closes.ewm(span=9).mean()

        ema20 = closes.ewm(span=20).mean()

        trend_ema20 = trend_closes.ewm(span=20).mean()
        trend15_ema20 = trend15_closes.ewm(span=20).mean()

        price = closes.iloc[-1]

        low20 = closes.tail(20).min()
        high20 = closes.tail(20).max()

        move_from_low = ((price - low20) / low20) * 100
        move_from_high = ((high20 - price) / high20) * 100

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
        # FILTERS
        # =================================================

        if volatility < 0.05:
            return None

        if volume_ratio < 1.30:
            return None

        # =================================================
        # AI FILTER
        # =================================================

        ai_score = 70

        if ai_model is not None:

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

            ai_score = max(

                ai_model.predict_proba(
                    features_df
                )[0]

            ) * 100

        # =================================================
        # LONG
        # =================================================

        if (

            price > ema20.iloc[-1]

            and

            ema9.iloc[-1] > ema20.iloc[-1]

            and

            trend_closes.iloc[-1]
            >
            trend_ema20.iloc[-1]

            and

            trend15_closes.iloc[-1]
            >
            trend15_ema20.iloc[-1]

            and

            move_1 > 0

        ):

            return {

                "signal": "LONG",

                "score": round(ai_score),

                "momentum": momentum,

                "volume_ratio": volume_ratio,

                "volatility": volatility,

                "move_1": move_1,

                "move_3": move_3,
                "risk_score": market_ai_score(price, ema20.iloc[-1], trend_closes.iloc[-1], trend_ema20.iloc[-1]),
                "move_from_low": move_from_low,
                "move_from_high": move_from_high

            }

        # =================================================
        # SHORT
        # =================================================

        if (

            price < ema20.iloc[-1]

            and

            ema9.iloc[-1] < ema20.iloc[-1]

            and

            trend_closes.iloc[-1]
            <
            trend_ema20.iloc[-1]

            and

            trend15_closes.iloc[-1]
            <
            trend15_ema20.iloc[-1]

            and

            move_1 < 0

        ):

            return {

                "signal": "SHORT",

                "score": round(ai_score),

                "momentum": momentum,

                "volume_ratio": volume_ratio,

                "volatility": volatility,

                "move_1": move_1,

                "move_3": move_3,
                "risk_score": market_ai_score(price, ema20.iloc[-1], trend_closes.iloc[-1], trend_ema20.iloc[-1]),
                "move_from_low": move_from_low,
                "move_from_high": move_from_high

            }

        return None

    except Exception as e:

        print("ANALYZE ERROR:", e)

        return None


# =========================================================
# V1 HELPERS
# =========================================================

def market_ai_score(price, ema20, trend_price, trend_ema20):
    score = 50

    # LONG ve SHORT trendlerini eşit değerlendir
    if price > ema20:
        score += 15
    
    if trend_price > trend_ema20:
        score += 20

    return score

def pullback_ok(price, ema9):
    distance = abs(price - ema9) / price * 100
    return distance <= PULLBACK_PERCENT



# =========================================================
# V4-A MULTI AGENT SYSTEM
# =========================================================

def trend_agent(result):
    score = 50
    if result["momentum"] >= 0.15:
        score += 25
    if result["volume_ratio"] >= 1.5:
        score += 25
    return min(score, 100)

def market_agent(result):
    return int(result.get("risk_score", 50))

def whale_agent(result):
    score = 50
    if result["volume_ratio"] >= 2:
        score += 25
    if result["momentum"] >= 0.25:
        score += 25
    return min(score, 100)

def position_agent(result):
    score = 100
    move_from_low = result.get("move_from_low", 0)
    move_from_high = result.get("move_from_high", 0)

    if result["signal"] == "LONG":
        if move_from_low > 1.20:
            score -= 50
        elif move_from_low > 0.80:
            score -= 25

    if result["signal"] == "SHORT":
        if move_from_high > 1.20:
            score -= 50
        elif move_from_high > 0.80:
            score -= 25

    return max(score, 0)

def decision_agent(result):
    t = trend_agent(result)
    m = market_agent(result)
    w = whale_agent(result)
    p = position_agent(result)
    final_score = round(((result["score"] + t + m + w + p) / 5))
    return final_score, t, m, w, p

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

            "tp1_done": False,

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

🚀 BTC SCALP OPEN

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

❌ BTC SCALP CLOSED

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

                time.sleep(3)
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

            # =============================================
            # MAX PNL
            # =============================================

            if pnl > bot_position["max_pnl"]:

                bot_position["max_pnl"] = pnl

            max_pnl = bot_position["max_pnl"]

            # =============================================
            # RISK MANAGER V2
            # =============================================

            if max_pnl >= 0.15 and pnl <= 0:
                close_trade("BREAKEVEN PROTECT")
                continue

            if max_pnl >= 0.50 and pnl <= 0.15:
                close_trade("PROFIT LOCK 0.15")
                continue

            if max_pnl >= 0.50 and pnl <= 0.25:
                close_trade("PROFIT LOCK 0.25")
                continue

            # =============================================
            # TP1
            # =============================================

            if (

                pnl >= TP1_USDT

                and

                not bot_position["tp1_done"]

            ):

                bot_position["tp1_done"] = True

                bot.send_message(

                    CHAT_ID,

                    f"""

✅ TP1 HIT

💰 PROFIT:
{round(pnl,2)} USDT

"""

                )

            # =============================================
            # STOP LOSS
            # =============================================

            if pnl <= STOP_LOSS:

                close_trade(
                    "STOP LOSS"
                )

                continue

            # =============================================
            # TRAILING
            # =============================================

            if (

                max_pnl >= TRAIL_TRIGGER

                and

                pnl <= TRAIL_STOP

            ):

                close_trade(
                    "TRAILING STOP"
                )

                continue

            # =============================================
            # MEGA TP
            # =============================================

            if pnl >= MEGA_TP:

                close_trade(
                    "MEGA TAKE PROFIT"
                )

                continue

            time.sleep(3)

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

            if bot_position:

                time.sleep(3)
                continue

            result = analyze()

            if not result:

                time.sleep(5)
                continue

            bot.send_message(

                CHAT_ID,

                f"""

🧠 BTC SCALP SIGNAL

📈 {result['signal']}

🔥 AI SCORE:
%{round(result['score'])}

⚡ MOMENTUM:
{round(result['momentum'],2)}

📊 VOLUME:
{round(result['volume_ratio'],2)}X

🌪 VOLATILITY:
{round(result['volatility'],2)}%

"""

            )

            if result["volume_ratio"] < VOLUME_SPIKE_MIN:
                time.sleep(5)
                continue

            if result.get("risk_score", 0) < MARKET_AI_MIN_SCORE:
                time.sleep(5)
                continue

            if result["momentum"] < MIN_MOMENTUM:
                continue

            if result["volatility"] < MIN_VOLATILITY:
                continue

            # V2.5 Fake breakout filter
            df_check = get_data(TIMEFRAME)
            if df_check is not None and len(df_check) > 5:
                last_close = df_check["c"].iloc[-1]
                avg_close = df_check["c"].tail(5).mean()

                if result["signal"] == "LONG" and last_close < avg_close:
                    continue

                if result["signal"] == "SHORT" and last_close > avg_close:
                    continue

            final_score, trend_ai, market_ai, whale_ai, position_ai = decision_agent(result)

            bot.send_message(
                CHAT_ID,
                f"🤖 V4-A\nTrend AI: %{trend_ai}\nMarket AI: %{market_ai}\nWhale AI: %{whale_ai}\nPosition AI: %{position_ai}\nFinal Score: %{final_score}"
            )

            if result["score"] < 75:
                continue

            if final_score >= 75:

                open_trade(result)

            time.sleep(10)

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

🚀 SADIK BTC SCALP AI STARTED

📊 SYMBOL:
{SYMBOL}

⚡ LEVERAGE:
{LEVERAGE}X

💰 TP1:
{TP1_USDT} USDT

🛑 SL:
{STOP_LOSS} USDT

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
