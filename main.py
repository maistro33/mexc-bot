import os, time, requests, ccxt, telebot, threading, random
import pandas as pd
from xgboost import XGBClassifier
import joblib
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

MAX_TRADES = 3
BASE_USDT = 3
LEVERAGE = 10

TP1 = 0.6
TRAIL_GAP = 0.4
SL_USDT = -1

STEP1 = 0.9
STEP2 = 1.2
ai_warned = {}

MIN_HOLD = 20
GLOBAL_COOLDOWN = 10

AI_WEIGHT = 3
COOLDOWN = 60

EXCLUDED_COINS = ["BTC","ETH","BNB"]

ai_conf_log = []
total_trades = 0
wins = 0
losses = 0
last_report = 0

bot_active = True
last_trade_time = 0

# === YENİ EKLENEN KORUMA ===
last_traded_symbol = None
symbol_lock = {}

bot = telebot.TeleBot(os.getenv("TELE_TOKEN"))
CHAT_ID = os.getenv("MY_CHAT_ID")

def send(msg):
    try:
        bot.send_message(CHAT_ID, msg)
    except:
        pass

exchange = ccxt.bitget({
    "apiKey": os.getenv("BITGET_API"),
    "secret": os.getenv("BITGET_SEC"),
    "password": os.getenv("BITGET_PASS") or "Berfin33",
    "options": {"defaultType": "swap"},
    "enableRateLimit": True
})
exchange.load_markets()

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

def train():
    global memory
    if len(memory) < 25:
        return None

    df = pd.DataFrame(memory)

    if "strategy" in df.columns:
        df["strategy"] = df["strategy"].astype("category").cat.codes

    X = df.drop(columns=["result"])
    y = df["result"] > 0

    model = XGBClassifier(n_estimators=120, max_depth=4, learning_rate=0.05)
    model.fit(X, y)
    joblib.dump(model, "model.pkl")
    return model

model = joblib.load("model.pkl") if os.path.exists("model.pkl") else None

def ai_score(f):
    global model
    try:
        if not model:
            new = train()
            if new:
                model = new
            return 0.5

        conf = model.predict_proba(pd.DataFrame([f]))[0][1]
        ai_conf_log.append(conf)

        if len(ai_conf_log) > 500:
            ai_conf_log.pop(0)

        return conf
    except:
        return 0.5

def ohlcv(sym):
    try:
        return exchange.fetch_ohlcv(sym, "5m", limit=100)
    except:
        return []

def whale_score(sym):
    try:
        t = exchange.fetch_ticker(sym)
        vol = t["quoteVolume"] or 0
        change = abs(t["percentage"] or 0)
        score = 0
        if vol > 500000: score += 2
        if change > 2: score += 2
        return score
    except:
        return 0

def funding_score(sym):
    try:
        f = exchange.fetch_funding_rate(sym)
        rate = f["fundingRate"]
        if rate > 0.01: return -2
        elif rate < -0.01: return 2
        return 0
    except:
        return 0

def features(sym):
    try:
        data = ohlcv(sym)
        df = pd.DataFrame(data, columns=["t","o","h","l","c","v"])

        df["ema9"] = df["c"].ewm(span=9).mean()
        df["ema21"] = df["c"].ewm(span=21).mean()

        df["trend"] = df["ema9"] - df["ema21"]
        df["momentum"] = df["c"] - df["c"].shift(5)

        df["vol_avg"] = df["v"].rolling(10).mean()
        df["volume_spike"] = df["v"] / df["vol_avg"]

        df["price_change"] = (df["c"] - df["c"].shift(3)) / df["c"]
        df["fake"] = ((df["h"] > df["h"].shift(1)) & (df["c"] < df["h"].shift(1))).astype(int)

        df["volatility"] = df["h"] - df["l"]

        df = df.fillna(0)
        last = df.iloc[-1]

        return {
            "trend": float(last["trend"]),
            "momentum": float(last["momentum"]),
            "volume_spike": float(last["volume_spike"]),
            "price_change": float(last["price_change"]),
            "fake": int(last["fake"]),
            "volatility": float(last["volatility"]),
            "whale": whale_score(sym),
            "funding": funding_score(sym)
        }
    except:
        return None

def market_mode(f):
    if f["volatility"] > 0.8 and f["volume_spike"] > 1.1:
        return "SNIPER"
    return "SCALP"

strategy_stats = {
    "trend": {"win":0,"loss":0},
    "breakout": {"win":0,"loss":0}
}

def strat_trend(f):
    return (f["trend"] > 0)*2 + (abs(f["momentum"])>0)

def strat_breakout(f):
    return (f["volume_spike"]>1.5)*3 + (abs(f["price_change"])>0.002)

def best_strategy():
    best = "trend"
    best_wr = 0
    for k,v in strategy_stats.items():
        t = v["win"]+v["loss"]
        if t < 5: continue
        wr = v["win"]/t
        if wr > best_wr:
            best_wr = wr
            best = k
    return best

def ai_report():
    global last_report
    if total_trades < 10: return
    if total_trades % 10 != 0: return
    if total_trades == last_report: return

    last_report = total_trades

    wr = (wins / total_trades) * 100 if total_trades else 0
    avg_ai = sum(ai_conf_log)/len(ai_conf_log) if ai_conf_log else 0

    send(f"""🤖 AI RAPOR

Toplam trade: {total_trades}
Win rate: %{round(wr,2)}

Trend:
✔ {strategy_stats['trend']['win']} / ❌ {strategy_stats['trend']['loss']}

Breakout:
✔ {strategy_stats['breakout']['win']} / ❌ {strategy_stats['breakout']['loss']}

AI ortalama güven: {round(avg_ai,2)}
""")

def decision(sym):
    f = features(sym)
    if not f: return None

    strat = "breakout" if random.random() < 0.2 else best_strategy()

    score = strat_trend(f) if strat=="trend" else strat_breakout(f)
    score += f["whale"]
    score += f["funding"]

    conf = ai_score(f)
    mode = market_mode(f)

    avg_ai = sum(ai_conf_log)/len(ai_conf_log) if ai_conf_log else 0.5

    if mode == "SCALP":
        if conf < 0.50: return None
    else:
        if conf < 0.65: return None

    if conf < avg_ai - 0.03:
       return None

    if f["fake"] == 1 and abs(f["momentum"]) < 0.1:
        return None

    final = score + (conf * AI_WEIGHT)

    if conf > 0.7:
        final += 2

    if final < 2:
        return None

    if conf > 0.65:
        side = "long" if f["momentum"] > 0 else "short"
    else:
        side = "long" if f["trend"] > 0 else "short"

    send(f"⚡ SİNYAL {sym}\nYön:{side}\nAI:{round(conf,2)}\nMode:{mode}\nStrat:{strat}")
    return side, f, strat

# === VOLUME FİLTRELİ SYMBOLS ===
def symbols():
    t = exchange.fetch_tickers()
    s = [(k,v["quoteVolume"]) for k,v in t.items() if ":USDT" in k]

    s = [x for x in s if x[1] and 1500000 <= x[1] <= 15000000]

    s = [x for x in s if not any(ex in x[0] for ex in EXCLUDED_COINS)]
    s.sort(key=lambda x:x[1], reverse=True)
    return [x[0] for x in s[:20]]

state = {}
cooldown = {}

def sync_positions():
    try:
        pos = exchange.fetch_positions()
        for p in pos:
            if float(p.get("contracts") or 0) <= 0:
                continue
            sym = p["symbol"]
            if sym not in state:
                ts = p.get("timestamp")
                state[sym] = {
                    "peak": 0,
                    "tp_done": False,
                    "features": features(sym) or {},
                    "open_time": (ts/1000 if ts else time.time()),
                    "strategy": best_strategy(),
                    "remaining_qty": float(p.get("contracts") or 0)
                }
                send(f"♻️ SYNC {sym}")
    except:
        pass

def engine():
    global last_trade_time, last_traded_symbol
    while True:
        try:
            if not bot_active:
                time.sleep(5)
                continue

            pos = exchange.fetch_positions()
            open_count = sum(1 for p in pos if float(p.get("contracts") or 0) > 0)

            for sym in symbols():
                if open_count >= MAX_TRADES: break
                if time.time() - last_trade_time < GLOBAL_COOLDOWN: continue
                if sym in state: continue
                if sym in cooldown and time.time() - cooldown[sym] < COOLDOWN: continue

                if sym == last_traded_symbol:
                    continue

                if sym in symbol_lock and time.time() - symbol_lock[sym] < 120:
                    continue

                d = decision(sym)
                if not d: continue

                side, f, strat = d
                price = exchange.fetch_ticker(sym)["last"]

                mode = market_mode(f)
                usdt_size = BASE_USDT * 1.7 if mode=="SNIPER" else BASE_USDT

                raw_qty = (usdt_size * LEVERAGE) / price
                qty = float(exchange.amount_to_precision(sym, raw_qty))

                if qty <= 0:
                    continue

                exchange.set_leverage(LEVERAGE, sym)
                exchange.create_market_order(sym, "buy" if side=="long" else "sell", qty)

                state[sym] = {
                    "peak":0,
                    "tp_done":False,
                    "features":f,
                    "open_time":time.time(),
                    "strategy":strat,
                    "remaining_qty": qty
                }

                last_trade_time = time.time()
                last_traded_symbol = sym
                symbol_lock[sym] = time.time()

                send(f"🚀 OPEN {sym}\nYön:{side}\nFiyat:{price}\nMode:{mode}\nStrat:{strat}")
                break

            time.sleep(5)

        except Exception as e:
            print("ENGINE:", e)

def manage():
    global memory, model, total_trades, wins, losses
    while True:
        try:
            sync_positions()
            pos = exchange.fetch_positions()

            for p in pos:
                qty = float(p.get("contracts") or 0)
                if qty <= 0: continue

                sym = p["symbol"]
                pnl = float(p.get("unrealizedPnl") or 0)

                if sym not in state: continue
                st = state[sym]

                if pnl > st["peak"]:
                    st["peak"] = pnl

                if time.time() - st["open_time"] < MIN_HOLD:
                    continue

                close_side = "sell" if p.get("side") in ["long","buy"] else "buy"

                def safe_close(percent):
                    close_qty = st["remaining_qty"] * percent
                    close_qty = float(exchange.amount_to_precision(sym, close_qty))
                    if close_qty <= 0:
                        return 0
                    return close_qty

                if not st["tp_done"] and pnl >= TP1:
                    close_qty = safe_close(0.25)
                    if close_qty > 0:
                        exchange.create_market_order(sym, close_side, close_qty, params={"reduceOnly":True})
                        st["remaining_qty"] -= close_qty
                        st["tp_done"] = True
                        st["peak"] = pnl
                        send(f"🟢 TP1 {sym}")

                if st["tp_done"]:
                    if "step1" not in st:
                        st["step1"] = False
                        st["step2"] = False

                    if not st["step1"] and pnl >= STEP1:
                        close_qty = safe_close(0.25)
                        if close_qty > 0:
                            exchange.create_market_order(sym, close_side, close_qty, params={"reduceOnly":True})
                            st["remaining_qty"] -= close_qty
                            st["step1"] = True
                            send(f"🟡 STEP1 {sym}")

                    if not st["step2"] and pnl >= STEP2:
                        close_qty = safe_close(0.25)
                        if close_qty > 0:
                            exchange.create_market_order(sym, close_side, close_qty, params={"reduceOnly":True})
                            st["remaining_qty"] -= close_qty
                            st["step2"] = True
                            send(f"🟠 STEP2 {sym}")

                if st["tp_done"] and pnl < st["peak"] - TRAIL_GAP:
                    if st["remaining_qty"] > 0:
                        exchange.create_market_order(sym, close_side, st["remaining_qty"], params={"reduceOnly":True})

                    f = st["features"]
                    f["result"] = pnl
                    f["strategy"] = st["strategy"]

                    save_trade_db(f)
                    memory.append(f)

                    if len(memory)%10==0:
                        new = train()
                        if new:
                            model = new

                    if pnl > 0:
                        wins += 1
                        strategy_stats[st["strategy"]]["win"] += 1
                    else:
                        losses += 1
                        strategy_stats[st["strategy"]]["loss"] += 1

                    total_trades += 1
                    ai_report()

                    state.pop(sym)
                    cooldown[sym] = time.time()

                if pnl <= SL_USDT:
                    if st["remaining_qty"] > 0:
                        exchange.create_market_order(sym, close_side, st["remaining_qty"], params={"reduceOnly":True})
                    state.pop(sym)

            time.sleep(1)

        except Exception as e:
            print("MANAGE:", e)

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
    bot.send_message(msg.chat.id, "🤖 BOT PANEL", reply_markup=panel_menu())

@bot.callback_query_handler(func=lambda call: True)
def callback(call):
    global bot_active

    if call.data == "status":
        pos = exchange.fetch_positions()
        open_count = sum(1 for p in pos if float(p.get("contracts") or 0) > 0)
        wr = (wins / total_trades * 100) if total_trades else 0

        bot.send_message(call.message.chat.id,
f"""📊 DURUM

Açık işlem: {open_count}
Toplam trade: {total_trades}
Win rate: %{round(wr,2)}
""")

    elif call.data == "positions":
        pos = exchange.fetch_positions()
        text = "📈 POZİSYONLAR\n\n"
        for p in pos:
            qty = float(p.get("contracts") or 0)
            if qty <= 0: continue
            pnl = float(p.get("unrealizedPnl") or 0)
            text += f"{p['symbol']} → {round(pnl,2)}$\n"

        bot.send_message(call.message.chat.id, text)

    elif call.data == "ai":
        avg_ai = sum(ai_conf_log)/len(ai_conf_log) if ai_conf_log else 0

        bot.send_message(call.message.chat.id,
f"""🤖 AI DURUM

Ortalama: {round(avg_ai,2)}
Trend: {strategy_stats['trend']}
Breakout: {strategy_stats['breakout']}
""")

    elif call.data == "stop":
        bot_active = False
        bot.send_message(call.message.chat.id, "🛑 BOT DURDURULDU")

    elif call.data == "start":
        bot_active = True
        bot.send_message(call.message.chat.id, "▶️ BOT BAŞLATILDI")

threading.Thread(target=engine, daemon=True).start()
threading.Thread(target=manage, daemon=True).start()

send("💣 FINAL MASTER AI FIXED AKTİF")
bot.infinity_polling()
