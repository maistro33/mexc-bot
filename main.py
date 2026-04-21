import os, time, ccxt, requests, telebot, threading
import pandas as pd
import numpy as np
from openai import OpenAI
from xgboost import XGBClassifier
import joblib

# ===== CONFIG =====
LEVERAGE = 10
BASE_USDT = 5
MODE = "PAPER"

# ===== TELEGRAM =====
TOKEN = os.getenv("TELE_TOKEN")
CHAT_ID = os.getenv("MY_CHAT_ID")
bot = telebot.TeleBot(TOKEN)

def send(msg):
    try:
        bot.send_message(CHAT_ID, msg)
    except:
        print(msg)

# ===== OPENAI =====
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ===== SUPABASE =====
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

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

def load_trades():
    try:
        headers = {
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}"
        }
        res = requests.get(f"{SUPABASE_URL}/rest/v1/trades?select=*", headers=headers)
        return res.json()
    except:
        return []

# ===== MODEL =====
MODEL_FILE = "ai_model.pkl"

def load_model():
    if os.path.exists(MODEL_FILE):
        return joblib.load(MODEL_FILE)
    return XGBClassifier(n_estimators=80, max_depth=5)

model = load_model()

def to_array(f):
    return [
        f["momentum"], f["volume"], f["vol_change"],
        f["trend"], f["rsi"], f["volatility"],
        f["fake"], f["whale"]
    ]

def train_model():
    data = load_trades()
    X, y = [], []

    for d in data:
        pnl = d.get("pnl")

        if pnl is None:
            continue

        required = ["momentum","volume","vol_change","trend","rsi","volatility","fake","whale"]
        if not all(k in d for k in required):
            continue

        X.append([
            d["momentum"], d["volume"], d["vol_change"],
            d["trend"], d["rsi"], d["volatility"],
            d["fake"], d["whale"]
        ])

        y.append(1 if pnl > 0 else 0)

    if len(X) < 20:
        send("⚠️ veri az")
        return

    model.fit(np.array(X), np.array(y))
    joblib.dump(model, MODEL_FILE)

    send(f"🧠 AI TRAINED ({len(X)})")

def predict(f):
    try:
        return model.predict_proba(np.array([to_array(f)]))[0][1]
    except:
        return 0.5

# ===== INDICATORS =====
def compute_rsi(series):
    delta = series.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain/(loss+1e-9)
    return 100-(100/(1+rs))

def features(sym):
    try:
        df = pd.DataFrame(exchange.fetch_ohlcv(sym,"1m",50),
                          columns=["t","o","h","l","c","v"])

        return {
            "momentum":float(df["c"].iloc[-1]-df["c"].iloc[-3]),
            "volume":float(df["v"].iloc[-1]),
            "vol_change":float(df["v"].iloc[-1]-df["v"].iloc[-3]),
            "trend":1 if df["c"].ewm(9).mean().iloc[-1] > df["c"].ewm(21).mean().iloc[-1] else 0,
            "rsi":float(compute_rsi(df["c"]).iloc[-1]),
            "volatility":float(df["h"].iloc[-1]-df["l"].iloc[-1]),
            "fake":0,
            "whale":1 if df["v"].iloc[-1]>df["v"].rolling(20).mean().iloc[-1]*2 else 0
        }
    except:
        return None

# ===== EXCHANGE =====
exchange = ccxt.bitget({
    "apiKey": os.getenv("BITGET_API"),
    "secret": os.getenv("BITGET_SEC"),
    "password": os.getenv("BITGET_PASS"),
    "options": {"defaultType": "swap"}
})

def price(sym):
    return exchange.fetch_ticker(sym)["last"]

def order(sym,side,qty):
    if MODE=="REAL":
        exchange.set_leverage(LEVERAGE,sym)
        return exchange.create_market_order(sym,side,qty)
    return True

# ===== CHAT AI =====
def chat_ai(sym, f, prob):
    prompt = f"{sym} analiz. RSI:{f['rsi']} Trend:{f['trend']} Güven:{round(prob,2)} kısa yorum yap"
    res = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[{"role":"user","content":prompt}]
    )
    return res.choices[0].message.content

# ===== STATE =====
pending={}
position=None

# ===== TELEGRAM =====
@bot.message_handler(func=lambda m: True)
def handle(m):
    global pending, position

    txt=m.text.upper()

    if "ANALIZ" in txt:
        sym=txt.split(" ")[1]+"/USDT:USDT"
        f=features(sym)

        prob=predict(f)

        send(chat_ai(sym,f,prob))
        send(f"GİR? EVET / HAYIR")

        pending={"sym":sym,"f":f,"prob":prob}

    elif txt=="EVET":
        sym=pending["sym"]
        pr=price(sym)
        qty=(BASE_USDT*LEVERAGE)/pr

        order(sym,"buy",qty)

        position={"sym":sym,"entry":pr,"qty":qty,"peak":0,"f":pending["f"]}
        send(f"🚀 {sym} AÇILDI {round(pr,4)}")

    elif txt=="KAPAT":
        pr=price(position["sym"])
        pnl=(pr-position["entry"])*position["qty"]

        save_trade({**position["f"],"pnl":pnl})

        send(f"❌ {round(pnl,2)} USDT")
        position=None

# ===== LOOP =====
def loop():
    global position

    while True:
        try:
            if position:
                pr=price(position["sym"])
                pnl=(pr-position["entry"])*position["qty"]

                if pnl > position["peak"]:
                    position["peak"]=pnl

                if pnl > 2:
                    send(f"🎯 +{round(pnl,2)} USDT")

                if position["peak"]>3 and pnl<position["peak"]-2:
                    send("⚠️ trailing exit")
                    position=None

                send(f"📊 {round(pnl,2)} USDT")

            time.sleep(20)

        except Exception as e:
            print(e)
            time.sleep(5)

# ===== START =====
train_model()
threading.Thread(target=loop,daemon=True).start()

send("🤖 V6000 ELITE AKTİF")
bot.infinity_polling()
