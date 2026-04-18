
import os, time, requests, ccxt, telebot, threading
import pandas as pd
from xgboost import XGBClassifier
import joblib
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# ===== GLOBAL =====
BTC_SYMBOL = "BTC/USDT:USDT"

MIN_AI_CONF = 0.25
MAX_TRADES = 3
BASE_USDT = 3
LEVERAGE = 10

TP1 = 0.6
TP2 = 1.0
TP3 = 1.5
TP4 = 2.0

TRAIL_GAP = 0.25
SL_USDT = -1

MIN_HOLD = 20
GLOBAL_COOLDOWN = 30
COOLDOWN = 60

AI_WEIGHT = 3

# ===== STATE =====
recent_closed = {}
ai_conf_log = []
last_ai_conf = 0

memory = []

total_trades = 0
wins = 0
losses = 0
last_report = 0

bot_active = True
last_trade_time = 0

# ===== TELEGRAM =====
bot = telebot.TeleBot(os.getenv("TELE_TOKEN"))
CHAT_ID = os.getenv("MY_CHAT_ID")

def send(msg):
    try:
        bot.send_message(CHAT_ID, msg)
    except:
        pass

# ===== EXCHANGE =====
exchange = ccxt.bitget({
    "apiKey": os.getenv("BITGET_API"),
    "secret": os.getenv("BITGET_SEC"),
    "password": os.getenv("BITGET_PASS"),
    "options": {"defaultType": "swap"},
    "enableRateLimit": True
})

exchange.load_markets()

# ===== DB =====
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

def save_trade_db(data):
    try:
        requests.post(
            f"{SUPABASE_URL}/rest/v1/trades",
            headers={
                "apikey": SUPABASE_KEY,
                "Authorization": f"Bearer {SUPABASE_KEY}",
                "Content-Type": "application/json"
            },
            json=data
        )
    except:
        pass

def load_memory_db():
    try:
        res = requests.get(
            f"{SUPABASE_URL}/rest/v1/trades?select=*",
            headers={
                "apikey": SUPABASE_KEY,
                "Authorization": f"Bearer {SUPABASE_KEY}"
            }
        )
        return res.json()
    except:
        return []

memory = load_memory_db()

# ===== AI TRAIN =====
def train():
    global memory

    if len(memory) < 25:
        return None

    df = pd.DataFrame(memory)

    # sadece numeric kolonlar
    df = df.select_dtypes(include=["number"])

    if "result" not in df.columns:
        return None

    X = df.drop(columns=["result"])
    y = df["result"] > 0

    model = XGBClassifier(n_estimators=200)
    model.fit(X, y)

    joblib.dump(model, "model.pkl")
    return model

# ===== MODEL LOAD =====
model = None

try:
    if os.path.exists("model.pkl"):
        model = joblib.load("model.pkl")
    else:
        model = train()
except:
    model = None

# ===== AI SCORE =====
def ai_score(f):
    global last_ai_conf

    try:
        if model is None:
            last_ai_conf = 0.5
            return 0.5

        df = pd.DataFrame([f])

        conf = model.predict_proba(df)[0][1]

        ai_conf_log.append(conf)
        last_ai_conf = conf

        if len(ai_conf_log) > 200:
            ai_conf_log.pop(0)

        return conf

    except:
        last_ai_conf = 0.5
        return 0.5

# ===== DATA =====
def ohlcv(sym):
    try:
        return exchange.fetch_ohlcv(sym, "5m", limit=100)
    except:
        return []

# ===== FEATURES =====
def features(sym):
    try:
        data = ohlcv(sym)
        if not data:
            return None

        df = pd.DataFrame(data, columns=["t","o","h","l","c","v"])

        df["ema9"] = df["c"].ewm(span=9).mean()
        df["ema21"] = df["c"].ewm(span=21).mean()

        df["trend"] = df["ema9"] - df["ema21"]
        df["momentum"] = df["c"] - df["c"].shift(5)

        df["vol_avg"] = df["v"].rolling(10).mean()
        df["volume_spike"] = df["v"] / df["vol_avg"]

        df["price_change"] = (df["c"] - df["c"].shift(3)) / df["c"]

        df["fake"] = ((df["h"] > df["h"].shift(1)) & (df["c"] < df["h"].shift(1))).astype(int)

        df = df.fillna(0)
        last = df.iloc[-1]

        return {
            "trend": float(last["trend"]),
            "momentum": float(last["momentum"]),
            "volume_spike": float(last["volume_spike"]),
            "price_change": float(last["price_change"]),
            "fake": int(last["fake"])
        }

    except:
        return None


# ===== MARKET AI =====
def market_pro():
    try:
        data = exchange.fetch_ohlcv(BTC_SYMBOL, "5m", limit=50)
        df = pd.DataFrame(data, columns=["t","o","h","l","c","v"])

        ema9 = df["c"].ewm(span=9).mean()
        ema21 = df["c"].ewm(span=21).mean()
        momentum = df["c"].iloc[-1] - df["c"].iloc[-5]

        if ema9.iloc[-1] > ema21.iloc[-1] and momentum > 0:
            return "strong_bull"

        if ema9.iloc[-1] < ema21.iloc[-1] and momentum < 0:
            return "strong_bear"

        return "chop"

    except:
        return "chop"


# ===== WHALE =====
def whale_pro(sym):
    try:
        t = exchange.fetch_ticker(sym)
        vol = t.get("quoteVolume") or 0
        change = abs(t.get("percentage") or 0)

        score = 0
        if vol > 300000:
            score += 1
        if change > 2:
            score += 1
        if change > 4:
            score += 2

        return score

    except:
        return 0


# ===== ORDERBOOK =====
def orderbook_power(sym):
    try:
        ob = exchange.fetch_order_book(sym, limit=20)

        bids = sum([b[1] for b in ob["bids"]])
        asks = sum([a[1] for a in ob["asks"]])

        if bids > asks * 1.2:
            return 2
        elif asks > bids * 1.2:
            return -2

        return 0

    except:
        return 0


# ===== PUMP FILTER =====
def pump_killer(sym):
    try:
        t = exchange.fetch_ticker(sym)
        return abs(t.get("percentage") or 0) > 6
    except:
        return False


# ===== V9 SMART VOLUME =====
def smart_volume_filter(sym):
    try:
        data = exchange.fetch_ohlcv(sym, "1m", limit=20)
        df = pd.DataFrame(data, columns=["t","o","h","l","c","v"])

        short_vol = df["v"].tail(5).mean()
        long_vol = df["v"].mean()

        return short_vol > long_vol * 1.05

    except:
        return False


# ===== V9 DOUBLE CHECK =====
def double_check(sym, side):
    try:
        f = features(sym)
        if not f:
            return False

        if side == "long" and f["trend"] <= 0:
            return False

        if side == "short" and f["trend"] >= 0:
            return False

        return True

    except:
        return False


# ===== V9 DECISION =====
def decision_v9(sym):
    try:
        f = features(sym)
        if not f:
            return None

         if pump_killer(sym):
             return None

       if not smart_volume_filter(sym):
             return None

        market = market_pro()

        if market == "strong_bull" and f["trend"] <= 0:
            return None

        if market == "strong_bear" and f["trend"] >= 0:
            return None

        conf = ai_score(f)
        whale = whale_pro(sym)
        ob = orderbook_power(sym)

        score = 0

        # trend
        score += (f["trend"] > 0) * 2

        # momentum
        score += (abs(f["momentum"]) > 0)

        # volume
        score += (f["volume_spike"] > 1.2)

        # fake breakout ceza
        score -= (f["fake"] == 1) * 2

        # whale + orderbook
        score += whale + ob

        final_score = score + (conf * AI_WEIGHT)

        if conf < MIN_AI_CONF:
            return None

        if final_score < 1:
            return None

        side = "long" if f["trend"] > 0 else "short"

        if not double_check(sym, side):
            return None

        return side, f

    except:
        return None

# ===== AI EXIT =====
def position_ai(sym, st):
    try:
        if not st.get("features"):
            return False

        f_new = features(sym)
        if not f_new:
            return False

        conf_now = ai_score(f_new)
        conf_old = st.get("ai_conf", 0.5)

        # güvenli AI exit
        if conf_now < conf_old - 0.25:
            return True

        # güvenli momentum kontrolü
        if "momentum" in f_new and "momentum" in st["features"]:
            if f_new["momentum"] * st["features"]["momentum"] < 0:
                return True

        return False

    except:
        return False


# ===== SYMBOL SCAN =====
def fast_symbols():
    try:
        tickers = exchange.fetch_tickers()
        pairs = []

        for k, v in tickers.items():
            if ":USDT" not in k:
                continue
            if "BTC" in k or "ETH" in k:
                continue

            vol = v.get("quoteVolume") or 0
            change = abs(v.get("percentage") or 0)

            if vol > 20000 and change > 0.5:
                pairs.append((k, change))

        pairs.sort(key=lambda x: x[1], reverse=True)
        return [p[0] for p in pairs[:10]]

    except:
        return []


# ===== STATE =====
state = {}
cooldown = {}


# ===== SYNC POSITIONS =====
def sync_positions():
    try:
        pos = exchange.fetch_positions() or []

        for p in pos:
            qty = float(p.get("contracts") or 0)
            if qty <= 0:
                continue

            sym = p["symbol"]

            if sym not in state:
                ts = p.get("timestamp")

                f = features(sym)
                if not f:
                    continue

                # 🔥 GERÇEK SIDE FIX
                side = "long" if p.get("side") in ["long","buy"] else "short"

                state[sym] = {
                    "peak": 0,
                    "features": f,
                    "open_time": (ts/1000 if ts else time.time()),
                    "ai_conf": ai_score(f),
                    "side": side,
                    "tp1": False,
                    "tp2": False,
                    "tp3": False,
                    "tp4": False
                }

                send(f"♻️ SYNC {sym}")

    except:
        pass


# ===== ENGINE =====
def engine():
    global last_trade_time

    while True:
        try:
            if not bot_active:
                time.sleep(5)
                continue

            pos = exchange.fetch_positions() or []
            open_count = sum(1 for p in pos if float(p.get("contracts") or 0) > 0)

            for sym in fast_symbols():

                if open_count >= MAX_TRADES:
                    break

                if time.time() - last_trade_time < GLOBAL_COOLDOWN:
                    continue

                if sym in state:
                    continue

                if sym in cooldown and time.time() - cooldown[sym] < COOLDOWN:
                    continue

                if sym in recent_closed and time.time() - recent_closed[sym] < 300:
                    continue

                d = decision_v9(sym)
                if not d:
                    continue

                side, f = d

                price = exchange.fetch_ticker(sym)["last"]

                qty = float(exchange.amount_to_precision(
                    sym,
                    (BASE_USDT * LEVERAGE) / price
                ))

                # 🔥 qty güvenlik
                if qty <= 0:
                    continue

                exchange.set_leverage(LEVERAGE, sym)

                exchange.create_market_order(
                    sym,
                    "buy" if side == "long" else "sell",
                    qty
                )

                conf = ai_score(f)

                state[sym] = {
                    "peak": 0,
                    "features": f,
                    "open_time": time.time(),
                    "ai_conf": conf,
                    "side": side,
                    "tp1": False,
                    "tp2": False,
                    "tp3": False,
                    "tp4": False
                }

                last_trade_time = time.time()

                send(f"🚀 V9 OPEN {sym}\nSide:{side}\nAI:{round(conf,2)}")

                # 🔥 open_count fix
                open_count += 1

                break

            time.sleep(7)

        except Exception as e:
            print("ENGINE:", e)

# ===== AI REPORT =====
def ai_report():
    global last_report

    if total_trades < 10:
        return

    if total_trades % 10 != 0:
        return

    if total_trades == last_report:
        return

    last_report = total_trades

    wr = (wins / total_trades) * 100 if total_trades else 0
    avg_ai = sum(ai_conf_log)/len(ai_conf_log) if ai_conf_log else 0

    send(f"""🤖 AI RAPOR

Toplam trade: {total_trades}
Win rate: %{round(wr,2)}
AI ortalama güven: {round(avg_ai,2)}
""")


# ===== CLOSE HELPER =====
def close_trade(sym, st, pnl, close_side, qty):
    global memory, total_trades, wins, losses, model

    exchange.create_market_order(sym, close_side, qty, params={"reduceOnly":True})

    f = dict(st["features"])
    f["result"] = pnl

    save_trade_db(f)
    memory.append(f)

    total_trades += 1
    if pnl > 0:
        wins += 1
    else:
        losses += 1

    # AI öğrenme
    if len(memory) % 10 == 0:
        new_model = train()
        if new_model:
            model = new_model

    ai_report()

    recent_closed[sym] = time.time()
    state.pop(sym, None)
    cooldown[sym] = time.time()


# ===== MANAGE =====
def manage():
    global memory

    while True:
        try:
            sync_positions()
            pos = exchange.fetch_positions() or []

            for p in pos:
                qty = float(p.get("contracts") or 0)
                if qty <= 0:
                    continue

                sym = p["symbol"]
                pnl = float(p.get("unrealizedPnl") or 0)

                if sym not in state:
                    continue

                st = state[sym]
                close_side = "sell" if p.get("side") in ["long","buy"] else "buy"

                # ===== MIN HOLD =====
                if time.time() - st["open_time"] < MIN_HOLD:
                    continue

                # ===== PEAK =====
                if pnl > st["peak"]:
                    st["peak"] = pnl

                # ===== LIVE TREND KORUMA =====
                f_live = features(sym)
                if f_live:
                    if st["side"] == "long" and f_live["trend"] <= 0:
                        if position_ai(sym, st):
                            close_trade(sym, st, pnl, close_side, qty)
                            continue

                    elif st["side"] == "short" and f_live["trend"] >= 0:
                        if position_ai(sym, st):
                            close_trade(sym, st, pnl, close_side, qty)
                            continue

                # ===== AI EXIT =====
                if position_ai(sym, st):
                    close_trade(sym, st, pnl, close_side, qty)
                    continue

                # ===== TP SYSTEM =====
                if not st["tp1"] and pnl >= TP1:
                    part = float(exchange.amount_to_precision(sym, qty * 0.25))
                    exchange.create_market_order(sym, close_side, part, params={"reduceOnly":True})
                    st["tp1"] = True
                    st["peak"] = pnl

                if not st["tp2"] and pnl >= TP2:
                    part = float(exchange.amount_to_precision(sym, qty * 0.25))
                    exchange.create_market_order(sym, close_side, part, params={"reduceOnly":True})
                    st["tp2"] = True

                if not st["tp3"] and pnl >= TP3:
                    part = float(exchange.amount_to_precision(sym, qty * 0.25))
                    exchange.create_market_order(sym, close_side, part, params={"reduceOnly":True})
                    st["tp3"] = True

                if not st["tp4"] and pnl >= TP4:
                    part = float(exchange.amount_to_precision(sym, qty * 0.25))
                    exchange.create_market_order(sym, close_side, part, params={"reduceOnly":True})
                    st["tp4"] = True

                # ===== TRAILING (SADECE KARDA) =====
                if st["tp1"] and pnl < st["peak"] - TRAIL_GAP:
                    close_trade(sym, st, pnl, close_side, qty)
                    continue

                # ===== STOP LOSS =====
                if pnl <= SL_USDT:
                    close_trade(sym, st, pnl, close_side, qty)
                    continue

            time.sleep(1)

        except Exception as e:
            print("MANAGE:", e)


# ===== PANEL =====
def panel_menu():
    markup = InlineKeyboardMarkup()
    markup.add(
        InlineKeyboardButton("📊 Durum", callback_data="status"),
        InlineKeyboardButton("📈 Pozisyon", callback_data="positions")
    )
    markup.add(
        InlineKeyboardButton("🤖 AI", callback_data="ai"),
        InlineKeyboardButton("🛑 Stop", callback_data="stop")
    )
    markup.add(
        InlineKeyboardButton("▶️ Start", callback_data="start")
    )
    return markup


@bot.message_handler(commands=['panel'])
def panel(msg):
    bot.send_message(msg.chat.id, "🤖 V9 FINAL PANEL", reply_markup=panel_menu())


@bot.callback_query_handler(func=lambda call: True)
def callback(call):
    global bot_active

    if call.data == "status":
        pos = exchange.fetch_positions() or []
        open_count = sum(1 for p in pos if float(p.get("contracts") or 0) > 0)

        wr = (wins / total_trades * 100) if total_trades else 0

        bot.send_message(call.message.chat.id,
f"""📊 DURUM

Açık işlem: {open_count}
Toplam trade: {total_trades}
Win rate: %{round(wr,2)}
""")

    elif call.data == "positions":
        pos = exchange.fetch_positions() or []
        text = "📈 POZİSYONLAR\n\n"

        for p in pos:
            qty = float(p.get("contracts") or 0)
            if qty <= 0:
                continue

            pnl = float(p.get("unrealizedPnl") or 0)
            text += f"{p['symbol']} → {round(pnl,2)}$\n"

        bot.send_message(call.message.chat.id, text)

    elif call.data == "ai":
        avg_ai = sum(ai_conf_log)/len(ai_conf_log) if ai_conf_log else 0

        bot.send_message(call.message.chat.id,
f"""🤖 AI DURUM

Son AI: {round(last_ai_conf,2)}
Ortalama AI: {round(avg_ai,2)}
Analiz sayısı: {len(ai_conf_log)}

Trade: {total_trades}
Win: {wins}
Loss: {losses}
""")

    elif call.data == "stop":
        bot_active = False
        bot.send_message(call.message.chat.id, "🛑 BOT DURDU")

    elif call.data == "start":
        bot_active = True
        bot.send_message(call.message.chat.id, "▶️ BOT BAŞLADI")


# ===== START =====
threading.Thread(target=engine, daemon=True).start()
threading.Thread(target=manage, daemon=True).start()

send("💣 V9 FINAL AKTİF")
bot.infinity_polling()
