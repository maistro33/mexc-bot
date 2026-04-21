import os, time, ccxt, telebot, random, threading
import pandas as pd
import numpy as np
from rl_agent import DQNAgent

# ===== CONFIG =====
LEVERAGE = 10
BASE_USDT = 5
MAX_POSITIONS = 4
MODE = os.getenv("MODE", "PAPER")

# ===== TELEGRAM =====
TOKEN = os.getenv("TELE_TOKEN")
CHAT_ID = os.getenv("MY_CHAT_ID")
bot = telebot.TeleBot(TOKEN) if TOKEN else None

def send(msg):
    try:
        if bot and CHAT_ID:
            bot.send_message(CHAT_ID, msg, parse_mode="Markdown")
        else:
            print(msg)
    except:
        print(msg)

# ===== RATE LIMIT =====
last_msg = 0
def safe_send(msg):
    global last_msg
    if time.time() - last_msg < 1.5:
        return
    last_msg = time.time()
    send(msg)

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

def safe_predict(state):
    try:
        if not hasattr(agent,"model") or agent.model is None:
            return 0.5, 0
        q = agent.model.predict(state, verbose=0)[0]
        return float(np.max(q)), int(np.argmax(q))
    except:
        return 0.5, 0

# ===== GLOBAL =====
positions=[]
pending={}
symbols_cache=[]
last_symbols=0
last_trade={}
last_live_time=0

# ===== BTC FILTER =====
def btc_trend():
    try:
        df=pd.DataFrame(exchange.fetch_ohlcv("BTC/USDT:USDT","5m",50),
                        columns=["t","o","h","l","c","v"])
        return 1 if df["c"].ewm(9).mean().iloc[-1] > df["c"].ewm(21).mean().iloc[-1] else 0
    except:
        return 1

# ===== SYMBOL CACHE =====
def get_symbols():
    global symbols_cache,last_symbols
    if time.time()-last_symbols<60 and symbols_cache:
        return random.sample(symbols_cache,min(20,len(symbols_cache)))
    try:
        t=exchange.fetch_tickers()
        pairs=[(s,x["quoteVolume"]) for s,x in t.items() if ":USDT" in s and x["quoteVolume"]]
        pairs.sort(key=lambda x:x[1],reverse=True)
        symbols_cache=[p[0] for p in pairs[:120]]
        last_symbols=time.time()
    except:
        symbols_cache=["BTC/USDT:USDT"]
    return random.sample(symbols_cache,min(20,len(symbols_cache)))

# ===== INDICATORS =====
def compute_rsi(series):
    delta=series.diff()
    gain=delta.clip(lower=0).rolling(14).mean()
    loss=(-delta.clip(upper=0)).rolling(14).mean()
    rs=gain/(loss+1e-9)
    return 100-(100/(1+rs))

def features(sym):
    try:
        df=pd.DataFrame(exchange.fetch_ohlcv(sym,"1m",50),
                        columns=["t","o","h","l","c","v"])
        ema9=df["c"].ewm(9).mean().iloc[-1]
        ema21=df["c"].ewm(21).mean().iloc[-1]

        return {
            "momentum":float(df["c"].iloc[-1]-df["c"].iloc[-3]),
            "volume":float(df["v"].iloc[-1]),
            "vol_change":float(df["v"].iloc[-1]-df["v"].iloc[-3]),
            "trend":1 if ema9>ema21 else 0,
            "rsi":float(compute_rsi(df["c"]).iloc[-1]),
            "volatility":float(df["h"].iloc[-1]-df["l"].iloc[-1]),
            "fake":0,
            "whale":0
        }
    except:
        return None

def make_state(f):
    return np.array([[f[k] for k in ["momentum","volume","vol_change","trend","rsi","volatility","fake","whale"]]])

# ===== PRICE =====
def get_price(sym):
    try:
        t=exchange.fetch_ticker(sym)
        return t.get("last") or t.get("close")
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

# ===== MESSAGES =====
def msg_open(sym,side,price,conf):
    return f"🚀 {sym}\n📈 {side}\n🧠 {round(conf,2)}\n💰 {round(price,6)}"

def msg_close(sym,side,entry,price,pnl):
    return f"❌ {sym}\n{round(pnl,2)}% {'🟢' if pnl>0 else '🔴'}"

def msg_live(sym,pnl):
    return f"📊 {sym} {round(pnl,2)}%"

def msg_analysis(sym,f,conf):
    return f"🧠 {sym}\nRSI:{round(f['rsi'],1)} Trend:{f['trend']} Conf:{round(conf,2)}\nEVET / HAYIR"

# ===== TELEGRAM =====
def tg():
    if not bot: return

    @bot.message_handler(func=lambda m: True)
    def handle(m):
        txt=m.text.upper()

        if "ANALIZ" in txt:
            sym=txt.replace("/","").split(" ")[0]+"/USDT:USDT"
            f=features(sym)
            if not f:
                safe_send("❌ Veri yok")
                return

            state=make_state(f)
            conf,act=safe_predict(state)

            safe_send(msg_analysis(sym,f,conf))
            pending[m.chat.id]={"sym":sym,"act":act,"conf":conf}

        elif txt=="EVET":
            d=pending.get(m.chat.id)
            if not d or d["act"]==0:
                safe_send("❌ Trade yok")
                return

            sym=d["sym"]
            price=get_price(sym)
            if not price:
                return

            qty=(BASE_USDT*LEVERAGE)/price
            side="buy" if d["act"]==1 else "sell"

            place_order(sym,side,qty)

            positions.append({"sym":sym,"side":"LONG" if d["act"]==1 else "SHORT","entry":price,"qty":qty,"peak":0})

            safe_send(msg_open(sym,positions[-1]["side"],price,d["conf"]))
            pending.pop(m.chat.id,None)

    bot.infinity_polling(none_stop=True,interval=1)

threading.Thread(target=tg,daemon=True).start()

safe_send("🤖 V4013 FINAL AKTİF")

# ===== LOOP =====
while True:
    try:
        global last_live_time
        btc=btc_trend()

        for sym in get_symbols():

            time.sleep(0.2)

            if sym in last_trade and time.time()-last_trade[sym]<1800:
                continue

            if any(p["sym"]==sym for p in positions):
                continue

            f=features(sym)
            if not f or f["volume"]<20000:
                continue

            price=get_price(sym)
            if not price:
                continue

            state=make_state(f)
            conf,act=safe_predict(state)

            if act==0 or conf<0.55:
                continue

            if act==1 and btc==0:
                continue
            if act==2 and btc==1:
                continue

            qty=(BASE_USDT*LEVERAGE)/price
            side="buy" if act==1 else "sell"

            place_order(sym,side,qty)

            positions.append({"sym":sym,"side":"LONG" if act==1 else "SHORT","entry":price,"qty":qty,"peak":0})

            last_trade[sym]=time.time()

            safe_send(msg_open(sym,positions[-1]["side"],price,conf))

        for pos in positions[:]:
            price=get_price(pos["sym"])
            if not price:
                continue

            pnl=((price-pos["entry"])/pos["entry"])*100*LEVERAGE if pos["side"]=="LONG" else ((pos["entry"]-price)/pos["entry"])*100*LEVERAGE

            if pnl>pos["peak"]:
                pos["peak"]=pnl

            if time.time()-last_live_time>30:
                last_live_time=time.time()
                safe_send(msg_live(pos["sym"],pnl))

            close=False
            if pnl<-4 or (pos["peak"]>3 and pnl<pos["peak"]-2):
                close=True

            if close:
                place_order(pos["sym"],"sell" if pos["side"]=="LONG" else "buy",pos["qty"])
                safe_send(msg_close(pos["sym"],pos["side"],pos["entry"],price,pnl))
                positions.remove(pos)

        time.sleep(5)

    except Exception as e:
        print("ERR:",e)
        time.sleep(3)
