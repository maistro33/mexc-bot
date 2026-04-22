# ==============================
# 💀 SADIK BOT v14 + V21 FULL AI
# ==============================

import os,time,ccxt,telebot,threading,requests,random
import pandas as pd
from openai import OpenAI
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

VERSION="v21 FULL AI"

TOKEN=os.getenv("TELE_TOKEN")
CHAT_ID=os.getenv("MY_CHAT_ID")
OPENAI_KEY=os.getenv("OPENAI_API_KEY")

SUPA_URL=os.getenv("SUPABASE_URL")
SUPA_KEY=os.getenv("SUPABASE_KEY")

bot=telebot.TeleBot(TOKEN)
client=OpenAI(api_key=OPENAI_KEY)

exchange=ccxt.bitget({
"apiKey":os.getenv("BITGET_API"),
"secret":os.getenv("BITGET_SEC"),
"password":os.getenv("BITGET_PASS"),
"options":{"defaultType":"swap"},
"enableRateLimit":True
})

positions=[]
signal_cache=[]
event_log=[]
pending_trade={}
best_signal=None

# ==============================
def send(msg,cid=None):
    try: bot.send_message(cid or CHAT_ID,msg)
    except: print(msg)

# ==============================
def get_data(sym):
    try:
        ohlcv=exchange.fetch_ohlcv(sym,"1m",limit=50)
        df=pd.DataFrame(ohlcv,columns=["t","o","h","l","c","v"])
        df["ema"]=df["c"].ewm(20).mean()
        return df
    except:
        return None

# ==============================
def rsi(series,period=14):
    delta=series.diff()
    gain=(delta.where(delta>0,0)).rolling(period).mean()
    loss=(-delta.where(delta<0,0)).rolling(period).mean()
    rs=gain/(loss+1e-9)
    return 100-(100/(1+rs))

# ==============================
def market_status():
    try:
        df=get_data("BTC/USDT:USDT")
        return "🟢" if df["c"].iloc[-1]>df["ema"].iloc[-1] else "🔴"
    except:
        return "?"

# ==============================
def scanner():
    while True:
        try:
            for sym in exchange.fetch_tickers():

                if ":USDT" not in sym:
                    continue

                df=get_data(sym)
                if df is None:
                    continue

                price=df["c"].iloc[-1]
                ema=df["ema"].iloc[-1]

                move=abs(df["c"].iloc[-1]-df["c"].iloc[-5])/price
                vol=df["v"].iloc[-1]/(df["v"].iloc[-5]+1e-9)

                if move<0.003 or vol<1.5:
                    continue

                rsi_val=rsi(df["c"]).iloc[-1]
                if rsi_val>75 or rsi_val<25:
                    continue

                signal="LONG" if price>ema else "SHORT"

                signal_cache.append({
                    "id":sym.replace("/","").replace(":",""),
                    "sym":sym,
                    "signal":signal,
                    "entry":price,
                    "tp1":price*1.01,
                    "tp2":price*1.02,
                    "tp3":price*1.03,
                    "sl":price*0.98
                })

        except:
            time.sleep(5)

# ==============================
def open_trade(data,cid):
    positions.append({
        **data,
        "remaining":1.0,
        "chat":cid,
        "tp1_done":False,
        "tp2_done":False,
        "peak":0
    })
    send(f"🚀 {data['sym']} {data['signal']}",cid)

# ==============================
def manage():
    while True:
        for p in positions[:]:
            try:
                price=exchange.fetch_ticker(p["sym"])["last"]
            except:
                continue

            pnl=((price-p["entry"])/p["entry"])*50
            pnl=round(pnl,2)

            if pnl>p["peak"]:
                p["peak"]=pnl

            if pnl>1 and not p["tp1_done"]:
                p["tp1_done"]=True
                p["sl"]=p["entry"]
                send(f"TP1 {p['sym']}",p["chat"])

            if pnl>2 and not p["tp2_done"]:
                p["tp2_done"]=True
                send(f"TP2 {p['sym']}",p["chat"])

            if price<=p["sl"] or pnl<-3 or (pnl>2 and pnl<p["peak"]-3):
                send(f"EXIT {p['sym']} {pnl}",p["chat"])
                positions.remove(p)
                continue

            try:
                txt=f"{p['sym']} pnl:{pnl}"
                r=client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role":"user","content":txt}]
                )
                if "exit" in r.choices[0].message.content.lower():
                    send(f"AI EXIT {p['sym']}",p["chat"])
                    positions.remove(p)
            except:
                pass

        time.sleep(5)

# ==============================
def ai_scan():
    global best_signal

    while True:
        try:
            best=None
            best_score=0

            for sym in exchange.fetch_tickers():

                if ":USDT" not in sym:
                    continue

                df=get_data(sym)
                if df is None:
                    continue

                price=df["c"].iloc[-1]
                ema=df["ema"].iloc[-1]

                move=abs(df["c"].iloc[-1]-df["c"].iloc[-5])/price
                vol=df["v"].iloc[-1]/(df["v"].iloc[-5]+1e-9)

                score=0
                if price>ema: score+=1
                if move>0.003: score+=1
                if vol>1.5: score+=1

                conf=score/3

                if conf>best_score:
                    best_score=conf
                    best=(sym,price,conf)

            if best and best_score>0.6:
                sym,price,conf=best

                best_signal={
                    "sym":sym,
                    "entry":price,
                    "signal":"LONG",
                    "confidence":conf
                }

                send(f"📡 {sym} CONF:{round(conf*100)}% /gir")

            time.sleep(60)

        except:
            time.sleep(5)

# ==============================
@bot.message_handler(commands=['gir'])
def enter_best(msg):

    global best_signal

    if not best_signal:
        send("Sinyal yok",msg.chat.id)
        return

    s=best_signal

    data={
        "id":s["sym"].replace("/","").replace(":",""),
        "sym":s["sym"],
        "signal":s["signal"],
        "entry":s["entry"],
        "tp1":s["entry"]*1.01,
        "tp2":s["entry"]*1.02,
        "tp3":s["entry"]*1.03,
        "sl":s["entry"]*0.98
    }

    open_trade(data,msg.chat.id)

# ==============================
@bot.message_handler(commands=['ai'])
def ai_chat(msg):

    text=msg.text.replace("/ai","").strip()

    try:
        r=client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role":"user","content":text}]
        )
        bot.send_message(msg.chat.id,r.choices[0].message.content)
    except:
        send("AI hata",msg.chat.id)

# ==============================
def live_report():
    while True:
        for p in positions:
            try:
                price=exchange.fetch_ticker(p["sym"])["last"]
                pnl=((price-p["entry"])/p["entry"])*50
                send(f"{p['sym']} pnl:{round(pnl,2)}",p["chat"])
            except:
                pass
        time.sleep(30)

# ==============================
threading.Thread(target=scanner,daemon=True).start()
threading.Thread(target=manage,daemon=True).start()
threading.Thread(target=ai_scan,daemon=True).start()
threading.Thread(target=live_report,daemon=True).start()

send(f"💀 BOT {VERSION} AKTİF")
bot.infinity_polling()
