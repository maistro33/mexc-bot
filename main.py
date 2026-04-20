import os, time, ccxt, requests, telebot, random
import pandas as pd
import numpy as np
from rl_agent import DQNAgent

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
agent.epsilon_decay = 0.995

# ===== SUPABASE =====
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

def load_trades():
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
        headers = {
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json"
        }
        requests.post(f"{SUPABASE_URL}/rest/v1/trades", headers=headers, json=data)
    except Exception as e:
        print("SUPABASE ERROR:", e)

def load_ai_memory():
    trades = load_trades()
    for t in trades:
        try:
            state = np.array([[t["momentum"],t["volume"],t["vol_change"],t["trend"],t["rsi"],t["volatility"],t["fake"],t["whale"]]])
            reward = t["result"]
            action = 1 if reward > 0 else 2
            agent.remember(state, action, reward, state, True)
        except:
            continue

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
        ohlcv = exchange.fetch_ohlcv(sym,"1m",limit=50)
        df = pd.DataFrame(ohlcv,columns=["t","o","h","l","c","v"])

        return {
            "momentum":float(df["c"].iloc[-1]-df["c"].iloc[-3]),
            "volume":float(df["v"].iloc[-1]),
            "vol_change":float(df["v"].iloc[-1]-df["v"].iloc[-3]),
            "trend":1 if df["c"].ewm(span=9).mean().iloc[-1] > df["c"].ewm(span=21).mean().iloc[-1] else 0,
            "rsi":float(compute_rsi(df["c"]).iloc[-1]),
            "volatility":float(df["h"].iloc[-1]-df["l"].iloc[-1]),
            "fake":1 if (df["h"].iloc[-1]>df["h"].iloc[-5:-1].max() and df["c"].iloc[-1]<df["h"].iloc[-1]*0.995) else 0,
            "whale":1 if df["v"].iloc[-1]>df["v"].iloc[-3]*2 else 0
        }
    except:
        return None

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

# ===== PRICE =====
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
symbol_count={}

send("🤖 V1900.1 CLEAN FINAL BAŞLADI")
load_ai_memory()

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

            send(f"🚀 TRADE AÇILDI\n📊 {sym}\n📈 {direction}\n💰 {round(price,6)}")

        for pos in positions[:]:
            sym=pos["sym"]
            price=get_price(sym)
            if not price:
                continue

            entry=pos["entry"]
            pnl=((price-entry)/entry)*100*LEVERAGE if pos["side"]=="LONG" else ((entry-price)/entry)*100*LEVERAGE

            if pnl>pos["peak"]:
                pos["peak"]=pnl

            close=False

            if pnl < -4:
                close=True
            elif pos["peak"] > 4 and pnl < pos["peak"] - 3:
                close=True
            elif pos["peak"] > 2 and pnl < pos["peak"] - 2:
                close=True

            if close:
                place_order(sym,"sell" if pos["side"]=="LONG" else "buy",pos["qty"])

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

                symbol_count[sym] = max(0, symbol_count.get(sym,1)-1)

                if pnl < 0:
                    last_trade[sym] = time.time() + 1800

                positions.remove(pos)

        time.sleep(5)

    except Exception as e:
        print("ERR:",e)
        time.sleep(3)
