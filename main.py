import os, time, ccxt, requests, telebot, random, threading
import pandas as pd
import numpy as np
from rl_agent import DQNAgent
from openai import OpenAI

# ===== CHAT AI =====
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def chat_ai(sym, f, confidence, action):
    try:
        direction = "LONG" if action==1 else "SHORT" if action==2 else "WAIT"

        prompt = f"""
You are a professional crypto trader.

Coin: {sym}
Trend: {"UP" if f["trend"]==1 else "DOWN"}
RSI: {f["rsi"]}
Volume: {f["volume"]}
Momentum: {f["momentum"]}
Confidence: {confidence}
Decision: {direction}

Explain briefly like a human trader.
"""

        res = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[{"role":"user","content":prompt}],
            temperature=0.7
        )
        return res.choices[0].message.content

    except Exception as e:
        return f"AI error: {e}"

# ===== CONFIG =====
LEVERAGE = 10
BASE_USDT = 5
MAX_POSITIONS = 4
MODE = os.getenv("MODE", "PAPER")
COOLDOWN_SYMBOL = 1800

# ===== TELEGRAM =====
TOKEN = os.getenv("TELE_TOKEN")
CHAT_ID = os.getenv("MY_CHAT_ID")
bot = telebot.TeleBot(TOKEN) if TOKEN else None

def send(msg):
    try:
        if bot and CHAT_ID:
            bot.send_message(CHAT_ID, msg)
        else:
            print(msg)
    except:
        print(msg)

# ===== INTERACTIVE MEMORY =====
user_last_analysis = {}

# ===== TELEGRAM THREAD =====
def telegram_loop():
    if not bot:
        return

    @bot.message_handler(func=lambda m: True)
    def handle_message(message):
        text = message.text.upper()

        if "ANALIZ" in text:
            try:
                sym = text.split(" ")[0] + "/USDT:USDT"
                f = features(sym)
                if not f:
                    send("❌ Veri yok")
                    return

                state = make_state(f)
                action = agent.act(state)
                confidence = get_confidence(state)

                reply = chat_ai(sym, f, confidence, action)
                send(reply)

                user_last_analysis[message.chat.id] = {
                    "sym": sym,
                    "features": f,
                    "confidence": confidence,
                    "action": action
                }

            except Exception as e:
                send(f"Hata: {e}")

        elif text == "GIR":
            open_trade_manual(message.chat.id)

        elif text == "KAPAT":
            close_trade_manual(message.chat.id)

    bot.infinity_polling()

# ===== EXCHANGE =====
exchange = ccxt.bitget({
    "apiKey": os.getenv("BITGET_API"),
    "secret": os.getenv("BITGET_SEC"),
    "password": os.getenv("BITGET_PASS"),
    "options": {"defaultType": "swap"},
    "enableRateLimit": True
})
exchange.load_markets()

# ===== AI =====
agent = DQNAgent(state_size=8, action_size=3)
agent.epsilon = 0.5
agent.epsilon_decay = 0.995

# ===== SUPABASE =====
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

def load_trades():
    try:
        headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
        return requests.get(f"{SUPABASE_URL}/rest/v1/trades?select=*", headers=headers).json()
    except:
        return []

def save_trade(data):
    try:
        headers = {
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json"
        }
        requests.post(f"{SUPABASE_URL}/rest/v1/trades", headers=headers, json=data)
    except:
        pass

def load_ai_memory():
    trades = load_trades()
    send(f"🧠 AI RESET ACTIVE — ({len(trades)} kayıt arşivde)")

# ===== STATS =====
stats = {"total":0,"win":0,"loss":0,"pnl_total":0}

def send_report():
    if stats["total"] < 10:
        return
    winrate = (stats["win"]/stats["total"])*100
    avg_pnl = stats["pnl_total"]/stats["total"]

    send(f"""🧠 AI RAPOR

📊 Trade: {stats["total"]}
🟢 Kazanç: {stats["win"]}
🔴 Zarar: {stats["loss"]}

📈 Winrate: {round(winrate,2)}%
💵 Avg PnL: {round(avg_pnl,2)}%
""")

# ===== BTC TREND =====
def btc_trend():
    try:
        ohlcv = exchange.fetch_ohlcv("BTC/USDT:USDT","5m",limit=50)
        df = pd.DataFrame(ohlcv,columns=["t","o","h","l","c","v"])
        return 1 if df["c"].ewm(9).mean().iloc[-1] > df["c"].ewm(21).mean().iloc[-1] else 0
    except:
        return 1

# ===== RSI =====
def compute_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(period).mean()
    rs = gain / (loss + 1e-9)
    return 100 - (100 / (1 + rs))

# ===== FEATURES =====
def features(sym):
    try:
        # ✅ FIX (RAVE ve benzeri coinler için)
        ohlcv = None

        try:
            ohlcv = exchange.fetch_ohlcv(sym,"1m",50)
        except:
            try:
                alt = sym.replace(":USDT","")
                ohlcv = exchange.fetch_ohlcv(alt,"1m",50)
            except:
                return None

        df = pd.DataFrame(ohlcv,columns=["t","o","h","l","c","v"])

        return {
            "momentum":float(df["c"].iloc[-1]-df["c"].iloc[-3]),
            "volume":float(df["v"].iloc[-1]),
            "vol_change":float(df["v"].iloc[-1]-df["v"].iloc[-3]),
            "trend":1 if df["c"].ewm(9).mean().iloc[-1] > df["c"].ewm(21).mean().iloc[-1] else 0,
            "rsi":float(compute_rsi(df["c"]).iloc[-1]),
            "volatility":float(df["h"].iloc[-1]-df["l"].iloc[-1]),
            "fake":1 if (df["h"].iloc[-1]>df["h"].iloc[-5:-1].max() and df["c"].iloc[-1]<df["h"].iloc[-1]*0.995) else 0,
            "whale":1 if df["v"].iloc[-1]>df["v"].iloc[-3]*2 else 0
        }
    except:
        return None

def make_state(f):
    return np.array([[f["momentum"],f["volume"],f["vol_change"],f["trend"],f["rsi"],f["volatility"],f["fake"],f["whale"]]])

def get_confidence(state):
    try:
        return float(np.max(agent.model.predict(state, verbose=0)[0]))
    except:
        return 0.5

# ===== PRICE =====
def get_price(sym):
    try:
        ticker = exchange.fetch_ticker(sym)
        return ticker.get("last") or ticker.get("close")
    except:
        return None

# ===== ORDER =====
def place_order(sym,side,qty):
    try:
        if MODE=="REAL":
            exchange.set_leverage(LEVERAGE,sym)
            return exchange.create_market_order(sym,side,qty)
        return {"ok":True}
    except:
        return None

# ===== MANUAL TRADE =====
def open_trade_manual(chat_id):
    data = user_last_analysis.get(chat_id)
    if not data:
        send("❌ Önce analiz yap")
        return

    sym = data["sym"]
    action = data["action"]
    confidence = data["confidence"]

    if action == 0 or confidence < 0.55:
        send("❌ Uygun değil")
        return

    price = get_price(sym)
    qty = (BASE_USDT*LEVERAGE)/price
    side = "buy" if action==1 else "sell"

    place_order(sym,side,qty)

    positions.append({
        "sym":sym,"side":"LONG" if action==1 else "SHORT",
        "entry":price,"qty":qty,"peak":0,
        "state":make_state(data["features"]),"action":action
    })

    send(f"🚀 MANUEL TRADE AÇILDI {sym}")

def close_trade_manual(chat_id):
    if not positions:
        send("❌ Pozisyon yok")
        return

    pos = positions[0]
    price = get_price(pos["sym"])

    place_order(pos["sym"],"sell" if pos["side"]=="LONG" else "buy",pos["qty"])

    send("❌ MANUEL KAPANDI")

    entry = pos["entry"]

    pnl = ((price - entry) / entry) * 100 * LEVERAGE \
        if pos["side"] == "LONG" else \
        ((entry - price) / entry) * 100 * LEVERAGE

    agent.remember(pos["state"], pos.get("action",1), pnl, pos["state"], True)
    agent.train(32)

    save_trade({
        "momentum": float(pos["state"][0][0]),
        "volume": float(pos["state"][0][1]),
        "vol_change": float(pos["state"][0][2]),
        "trend": float(pos["state"][0][3]),
        "rsi": float(pos["state"][0][4]),
        "volatility": float(pos["state"][0][5]),
        "fake": float(pos["state"][0][6]),
        "whale": float(pos["state"][0][7]),
        "result": float(pnl)
    })

    positions.clear()

# ===== SYMBOLS =====
def symbols():
    try:
        t=exchange.fetch_tickers()
        pairs=[(s,x["quoteVolume"]) for s,x in t.items() if ":USDT" in s and x["quoteVolume"]]
        pairs.sort(key=lambda x:x[1],reverse=True)
        top=[p[0] for p in pairs[:120]]
        return random.sample(top,min(20,len(top)))
    except:
        return ["BTC/USDT:USDT"]

# ===== STATE =====
positions=[]
last_trade={}
symbol_count={}

send("🤖 V3000 FINAL %100 AKTİF")
load_ai_memory()

threading.Thread(target=telegram_loop,daemon=True).start()

# ===== LOOP =====
while True:
    try:
        for sym in symbols():

            if len(positions)>=MAX_POSITIONS:
                break

            if sym in last_trade and time.time()-last_trade[sym]<COOLDOWN_SYMBOL:
                continue

            if symbol_count.get(sym,0)>=2:
                continue

            f=features(sym)
            if not f or f["volume"]<20000:
                continue

            if f["fake"]==1 or f["rsi"]>80 or f["rsi"]<20:
                continue

            price=get_price(sym)
            if not price:
                continue

            state=make_state(f)
            action=agent.act(state)

            confidence = get_confidence(state)
            if confidence < 0.55:
                continue

            btc = btc_trend()
            if action == 1 and btc == 0:
                continue
            if action == 2 and btc == 1:
                continue

            if action==0:
                continue

            direction="LONG" if action==1 else "SHORT"
            side="buy" if action==1 else "sell"

            qty=(BASE_USDT*LEVERAGE)/price

            if not place_order(sym,side,qty):
                continue

            positions.append({
                "sym":sym,"side":direction,"entry":price,"qty":qty,
                "peak":0,"state":state,"action":action
            })

            symbol_count[sym]=symbol_count.get(sym,0)+1
            last_trade[sym]=time.time()

            send(f"🚀 TRADE AÇILDI {sym}")

        time.sleep(5)

    except Exception as e:
        print("ERR:",e)
        time.sleep(3)
