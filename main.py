
import os, time, requests, ccxt, telebot, threading
import pandas as pd
from xgboost import XGBClassifier
import joblib
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# ===== GLOBAL =====
BTC_SYMBOL = "BTC/USDT:USDT"

MIN_AI_CONF = 0.45
MAX_TRADES = 3
BASE_USDT = 3
LEVERAGE = 10

TP1 = 0.6
TRAIL_GAP = 0.25
SL_USDT = -1

STEP1 = 0.9
STEP2 = 1.2

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
    df = df.select_dtypes(include=["number"])

    if "result" not in df.columns:
        return None

    X = df.drop(columns=["result"])
    y = df["result"] > 0

    model = XGBClassifier(n_estimators=200)
    model.fit(X, y)

    joblib.dump(model, "model.pkl")
    return model

model = joblib.load("model.pkl") if os.path.exists("model.pkl") else None

try:
    if model is None:
        model = train()
except:
    model = None

# ===== AI SCORE (FIXED) =====
def ai_score(f):
    global last_ai_conf

    try:
        if not model:
            last_ai_conf = 0.5
            return 0.5

        conf = model.predict_proba(pd.DataFrame([f]))[0][1]

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
        vol = t["quoteVolume"] or 0
        change = abs(t["percentage"] or 0)

        score = 0
        if vol > 300000: score += 1
        if change > 2: score += 1
        if change > 4: score += 2

        return score
    except:
        return 0

# ===== PUMP FILTER =====
def pump_killer(sym):
    try:
        t = exchange.fetch_ticker(sym)
        return abs(t["percentage"] or 0) > 6
    except:
        return False

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

# ===== AI EXIT (SAFE FIXED) =====
def position_ai(sym, st):
    try:
        if not st.get("features"):
            return False

        f_new = features(sym)
        if not f_new:
            return False

        conf_now = ai_score(f_new)
        conf_old = st.get("ai_conf", 0.5)

        if conf_now < conf_old - 0.15:
            return True

        # 🔥 SAFE momentum check
        if "momentum" in f_new and "momentum" in st["features"]:
            if f_new["momentum"] * st["features"]["momentum"] < 0:
                return True

        # 🔥 SAFE trend check
        if "trend" in f_new and "trend" in st["features"]:
            if abs(f_new["trend"]) < abs(st["features"]["trend"]) * 0.4:
                return True

        return False
    except:
        return False

# ===== SYMBOL SCAN =====
def fast_symbols():
    try:
        tickers = exchange.fetch_tickers()
        pairs = []

        for k,v in tickers.items():
            if ":USDT" not in k:
                continue
            if "BTC" in k or "ETH" in k:
                continue

            vol = v.get("quoteVolume") or 0
            change = abs(v.get("percentage") or 0)

            score = 0
            if vol > 50000: score += 1
            if change > 1: score += 1
            if change > 3: score += 2

            if score >= 2:
                pairs.append((k, score))

        pairs.sort(key=lambda x:x[1], reverse=True)
        return [p[0] for p in pairs[:10]]

    except:
        return []

# ===== DECISION =====
def decision(sym):
    f = features(sym)
    if not f:
        return None

    if pump_killer(sym):
        return None

    market = market_pro()

    if market == "strong_bear" and f["trend"] > 0:
        return None

    if market == "strong_bull" and f["trend"] < 0:
        return None

    conf = ai_score(f)
    whale = whale_pro(sym)
    ob = orderbook_power(sym)

    score = 0
    score += (f["trend"] > 0) * 2
    score += (abs(f["momentum"]) > 0)
    score += whale + ob

    final = score + (conf * AI_WEIGHT)

    if conf < MIN_AI_CONF and score < 2:
        return None

    if final < 1:
        return None

    side = "long" if f["trend"] > 0 else "short"

    return side, f

# ===== STATE =====
state = {}
cooldown = {}

def sync_positions():
    try:
        pos = exchange.fetch_positions() or []

        for p in pos:
            if float(p.get("contracts") or 0) <= 0:
                continue

            sym = p["symbol"]

            if sym not in state:
                ts = p.get("timestamp")

                f = features(sym)
                if not f:
                    continue

                state[sym] = {
                    "peak": 0,
                    "tp_done": False,
                    "features": f,
                    "open_time": (ts/1000 if ts else time.time()),
                    "ai_conf": ai_score(f)
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

                d = decision(sym)
                if not d:
                    continue

                side, f = d

                price = exchange.fetch_ticker(sym)["last"]
                qty = float(exchange.amount_to_precision(sym, (BASE_USDT * LEVERAGE) / price))

                # 🔥 qty safety fix
                if qty <= 0:
                    continue

                exchange.set_leverage(LEVERAGE, sym)
                exchange.create_market_order(sym, "buy" if side=="long" else "sell", qty)

                conf = ai_score(f)

                state[sym] = {
                    "peak": 0,
                    "tp_done": False,
                    "features": f,
                    "open_time": time.time(),
                    "ai_conf": conf
                }

                last_trade_time = time.time()

                send(f"🚀 V8 OPEN {sym}\nSide:{side}\nAI:{round(conf,2)}")

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

# ===== MANAGE =====
def manage():
    global memory, total_trades, wins, losses, model

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

                # ===== AI EXIT =====
                if position_ai(sym, st):
                    exchange.create_market_order(sym, close_side, qty, params={"reduceOnly":True})

                    send(f"🧠 AI EXIT {sym}\nPnL:{round(pnl,2)}$")

                    recent_closed[sym] = time.time()
                    state.pop(sym, None)
                    cooldown[sym] = time.time()
                    continue

                # ===== PEAK =====
                if pnl > st["peak"]:
                    st["peak"] = pnl

                if time.time() - st["open_time"] < MIN_HOLD:
                    continue

                # ===== TP1 =====
                if not st["tp_done"] and pnl >= TP1:
                    close_qty = float(exchange.amount_to_precision(sym, qty * 0.25))
                    exchange.create_market_order(sym, close_side, close_qty, params={"reduceOnly":True})

                    st["tp_done"] = True
                    st["peak"] = pnl

                    send(f"🟢 TP1 {sym}\nPnL:{round(pnl,2)}$")

                # ===== STEP SYSTEM =====
                if st["tp_done"]:
                    if "step1" not in st:
                        st["step1"] = False
                        st["step2"] = False

                    if not st["step1"] and pnl >= STEP1:
                        close_qty = float(exchange.amount_to_precision(sym, qty * 0.25))
                        exchange.create_market_order(sym, close_side, close_qty, params={"reduceOnly":True})
                        st["step1"] = True
                        send(f"🟡 STEP1 {sym}")

                    if not st["step2"] and pnl >= STEP2:
                        close_qty = float(exchange.amount_to_precision(sym, qty * 0.25))
                        exchange.create_market_order(sym, close_side, close_qty, params={"reduceOnly":True})
                        st["step2"] = True
                        send(f"🟠 STEP2 {sym}")

                # ===== TRAIL CLOSE =====
                if st["tp_done"] and pnl < st["peak"] - TRAIL_GAP:
                    exchange.create_market_order(sym, close_side, qty, params={"reduceOnly":True})

                    send(f"🏁 TRAIL CLOSE {sym}\nPnL:{round(pnl,2)}$")

                    recent_closed[sym] = time.time()

                    f = dict(st["features"]) if st.get("features") else {}
                    f["result"] = pnl

                    save_trade_db(f)
                    memory.append(f)

                    if len(memory) % 10 == 0:
                        new = train()
                        if new:
                            model = new

                    total_trades += 1
                    if pnl > 0:
                        wins += 1
                    else:
                        losses += 1

                    ai_report()

                    state.pop(sym, None)
                    cooldown[sym] = time.time()

                # ===== STOP LOSS =====
                if pnl <= SL_USDT:
                    exchange.create_market_order(sym, close_side, qty, params={"reduceOnly":True})

                    send(f"🔴 STOP {sym}\nPnL:{round(pnl,2)}$")

                    recent_closed[sym] = time.time()

                    f = dict(st["features"]) if st.get("features") else {}
                    f["result"] = pnl

                    save_trade_db(f)
                    memory.append(f)

                    if len(memory) % 10 == 0:
                        new = train()
                        if new:
                            model = new

                    total_trades += 1
                    if pnl > 0:
                        wins += 1
                    else:
                        losses += 1

                    ai_report()

                    state.pop(sym, None)
                    cooldown[sym] = time.time()

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
    bot.send_message(msg.chat.id, "🤖 V8 PANEL", reply_markup=panel_menu())

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

send("💣 V8 FINAL AKTİF")
bot.infinity_polling()
