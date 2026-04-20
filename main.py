import os, time, ccxt, requests, telebot, random
import pandas as pd
import numpy as np
from rl_agent import DQNAgent

# ===== CONFIG =====
LEVERAGE = 10
BASE_USDT = 5
MAX_POSITIONS = 4
MODE = os.getenv("MODE", "PAPER")
COOLDOWN_SYMBOL = 600

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
agent.epsilon = 1.0
agent.epsilon_decay = 0.996

# ===== SUPABASE =====
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

def load_trades():
    if not SUPABASE_URL or not SUPABASE_KEY:
        return []
    try:
        headers = {
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}"
        }
        r = requests.get(f"{SUPABASE_URL}/rest/v1/trades?select=*", headers=headers)
        return r.json()
    except:
        return []

def save_trade(data):
    try:
        if not SUPABASE_URL or not SUPABASE_KEY:
            return
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
    count = 0
    for t in trades:
        try:
            state = np.array([[
                t.get("momentum",0),
                t.get("volume",0),
                t.get("vol_change",0),
                t.get("trend",0),
                t.get("rsi",50),
                t.get("volatility",0),
                t.get("fake",0),
                t.get("whale",0)
            ]])
            reward = t.get("result",0)
            action = 1 if reward > 0 else 2
            agent.remember(state, action, reward, state, True)
            count += 1
        except:
            continue
    print("AI memory loaded:", count)

# ===== PERFORMANCE =====
stats = {"total":0,"win":0,"loss":0,"pnl_total":0}

def send_report():
    if stats["total"] < 10:
        return
    winrate = (stats["win"]/stats["total"])*100
    avg_pnl = stats["pnl_total"]/stats["total"]
    learning = min(100, (winrate*0.6)+(avg_pnl*10))
    level = "ACEMİ" if learning < 30 else "GELİŞİYOR" if learning < 60 else "İYİ" if learning < 80 else "GÜÇLÜ"

    send(f"""🧠 AI RAPOR

📊 Trade: {stats["total"]}
🟢 Kazanç: {stats["win"]}
🔴 Zarar: {stats["loss"]}

📈 Winrate: {round(winrate,2)}%
💵 Avg PnL: {round(avg_pnl,2)}%

🧠 Öğrenme: %{round(learning,1)}
📊 Seviye: {level}
""")

# ===== BTC TREND =====
def btc_trend():
    try:
        ohlcv = exchange.fetch_ohlcv("BTC/USDT:USDT","5m",limit=50)
        df = pd.DataFrame(ohlcv,columns=["t","o","h","l","c","v"])
        ema20=df["c"].ewm(span=20).mean()
        ema50=df["c"].ewm(span=50).mean()
        return 1 if ema20.iloc[-1]>ema50.iloc[-1] else 0
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
        ohlcv=exchange.fetch_ohlcv(sym,"1m",limit=50)
        df=pd.DataFrame(ohlcv,columns=["t","o","h","l","c","v"])

        momentum=float(df["c"].iloc[-1]-df["c"].iloc[-3])
        volume=float(df["v"].iloc[-1])
        vol_change=float(df["v"].iloc[-1]-df["v"].iloc[-3])

        ema9=df["c"].ewm(span=9).mean()
        ema21=df["c"].ewm(span=21).mean()
        trend=1 if ema9.iloc[-1]>ema21.iloc[-1] else 0

        rsi=float(compute_rsi(df["c"]).iloc[-1])
        volatility=float(df["h"].iloc[-1]-df["l"].iloc[-1])

        fake=1 if (df["h"].iloc[-1]>df["h"].iloc[-5:-1].max() and df["c"].iloc[-1]<df["h"].iloc[-1]*0.995) else 0
        whale=1 if df["v"].iloc[-1]>df["v"].iloc[-3]*2 else 0

        return {
            "momentum":momentum,
            "volume":volume,
            "vol_change":vol_change,
            "trend":trend,
            "rsi":rsi,
            "volatility":volatility,
            "fake":fake,
            "whale":whale,
            "btc": btc_trend()
        }
    except:
        return None

# ===== STATE =====
def make_state(f):
    return np.array([[f["momentum"],f["volume"],f["vol_change"],f["trend"],f["rsi"],f["volatility"],f["fake"],f["whale"]]])

# ===== SYMBOLS =====
def symbols():
    try:
        t=exchange.fetch_tickers()
        pairs=[(s,x["quoteVolume"]) for s,x in t.items() if ":USDT" in s and x["quoteVolume"]]
        pairs.sort(key=lambda x:x[1],reverse=True)
        return random.sample([p[0] for p in pairs[:30]],10)
    except:
        return ["BTC/USDT:USDT"]

# ===== PRICE FIX =====
def get_price(sym):
    try:
        ticker = exchange.fetch_ticker(sym)
        price = ticker.get("last") or ticker.get("close") or ticker.get("bid") or ticker.get("ask")
        if not price or price <= 0:
            return None
        return price
    except:
        return None

# ===== ORDER =====
def place_order(sym,side,qty):
    try:
        if MODE=="REAL":
            exchange.set_leverage(LEVERAGE,sym)
            return exchange.create_market_order(sym,side,qty)
        else:
            return {"ok":True}
    except:
        return None

# ===== STATE =====
positions=[]
last_trade={}
last_side={}

send("🤖 V1800 FINAL PRO BAŞLADI")
load_ai_memory()

# ===== LOOP =====
while True:
    try:
        for sym in symbols():

            if len(positions)>=MAX_POSITIONS:
                break

            if sym in last_trade and time.time()-last_trade[sym]<COOLDOWN_SYMBOL:
                continue

            if any(p["sym"]==sym for p in positions):
                continue

            f=features(sym)
            if not f or f["volume"]<10000:
                continue

            price = get_price(sym)
            if not price:
                continue

            # FILTERS
            if f["fake"] == 1:
                continue
            if f["rsi"] > 80 or f["rsi"] < 20:
                continue

            qty=(BASE_USDT*LEVERAGE)/price

            state=make_state(f)
            action=agent.act(state)

            if action==0 and random.random()<0.3:
                action=random.choice([1,2])

            direction = "LONG" if action==1 else "SHORT"
            side = "buy" if action==1 else "sell"

            # BTC FILTER
            if f["btc"] == 1 and direction == "SHORT":
                continue
            if f["btc"] == 0 and direction == "LONG":
                continue

            if sym in last_side and last_side[sym]!=direction:
                continue

            if not place_order(sym,side,qty):
                continue

            positions.append({
                "sym":sym,"side":direction,"entry":price,"qty":qty,
                "peak":0,"state":state,"action":action
            })

            last_trade[sym]=time.time()
            last_side[sym]=direction

            send(f"""🚀 TRADE AÇILDI

📊 {sym}
📈 Yön: {direction}

💰 Giriş: {round(price,6)}
💵 Margin: {BASE_USDT} USDT
⚡ Kaldıraç: {LEVERAGE}x""")

        for pos in positions[:]:
            sym=pos["sym"]; side=pos["side"]
            entry=pos["entry"]; qty=pos["qty"]

            price = get_price(sym)
            if not price:
                continue

            pnl=((price-entry)/entry)*100*LEVERAGE if side=="LONG" else ((entry-price)/entry)*100*LEVERAGE
            usdt=((price-entry)*qty) if side=="LONG" else ((entry-price)*qty)

            if pnl>pos["peak"]:
                pos["peak"]=pnl

            if pnl<-3 or (pnl>2 and pos["peak"]>2 and pnl<pos["peak"]-3):

                place_order(sym,"sell" if side=="LONG" else "buy",qty)

                agent.remember(pos["state"],pos["action"],pnl,pos["state"],True)
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

                stats["total"]+=1
                stats["pnl_total"]+=pnl
                stats["win"]+=1 if pnl>0 else 0
                stats["loss"]+=1 if pnl<=0 else 0

                if stats["total"]%10==0:
                    send_report()

                send(f"""❌ TRADE KAPANDI

📊 {sym}
📈 Yön: {side}

💰 Giriş: {round(entry,6)}
💰 Çıkış: {round(price,6)}

📊 PnL: {round(pnl,2)}%
💵 Sonuç: {round(usdt,3)} USDT {"🟢 KAR" if pnl>0 else "🔴 ZARAR"}""")

                last_trade[sym]=time.time()
                positions.remove(pos)

        time.sleep(5)

    except Exception as e:
        print("ERR:",e)
        time.sleep(3)
