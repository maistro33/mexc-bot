# ==============================
# 💀 SADIK BOT FINAL CONTROL AI
# ==============================

import os,time,ccxt,telebot,threading,requests
import pandas as pd
from openai import OpenAI
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

VERSION="FINAL CONTROL AI"

TOKEN=os.getenv("TELE_TOKEN")
CHAT_ID=os.getenv("MY_CHAT_ID")
OPENAI_KEY=os.getenv("OPENAI_API_KEY")

bot=telebot.TeleBot(TOKEN)
client=OpenAI(api_key=OPENAI_KEY)

exchange=ccxt.bitget({
    "apiKey": os.getenv("BITGET_API"),
    "secret": os.getenv("BITGET_SEC"),
    "password": os.getenv("BITGET_PASS"),
    "options": {"defaultType": "swap"},
    "enableRateLimit": True
})

positions=[]
signal_cache={}
best_signal=None

# ==============================
def send(msg, cid=None):
    try:
        bot.send_message(cid or CHAT_ID, msg)
    except:
        print(msg)

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
def ai_analyze(sym):

    df=get_data(sym)
    if df is None:
        return None

    price=df["c"].iloc[-1]
    ema=df["ema"].iloc[-1]
    trend="UP" if price>ema else "DOWN"

    try:
        r=client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{
                "role":"user",
                "content":f"""
                Coin:{sym}
                Trend:{trend}

                LONG SHORT NONE karar ver
                confidence yüzde ver
                kısa sebep yaz
                """
            }]
        )

        txt=r.choices[0].message.content

        signal="NONE"
        if "LONG" in txt.upper():
            signal="LONG"
        elif "SHORT" in txt.upper():
            signal="SHORT"

        return {
            "sym": sym,
            "signal": signal,
            "entry": price,
            "text": txt
        }

    except:
        return None

# ==============================
def scanner():
    global best_signal

    while True:
        try:
            tickers=list(exchange.fetch_tickers().keys())[:40]

            best=None

            for sym in tickers:

                if ":USDT" not in sym:
                    continue

                data=ai_analyze(sym)
                if not data:
                    continue

                if data["signal"]=="NONE":
                    continue

                best=data
                break

            if best:
                best_signal=best

                markup = InlineKeyboardMarkup()
                markup.add(
                    InlineKeyboardButton("✅ GİR", callback_data="enter"),
                    InlineKeyboardButton("❌ PAS", callback_data="pass")
                )

                send(f"""
🤖 AI SİNYAL

{best['sym']}
{best['signal']}

{best['text']}
""")

                bot.send_message(CHAT_ID, "İşlem:", reply_markup=markup)

        except Exception as e:
            print("SCAN:", e)

        time.sleep(60)

# ==============================
def open_trade(data, cid):

    positions.append({
        **data,
        "tp1_done":False,
        "tp2_done":False,
        "remaining":1.0,
        "chat":cid
    })

    send(f"🚀 TRADE AÇILDI {data['sym']}", cid)

# ==============================
def manage():
    while True:
        for p in positions[:]:

            try:
                price=exchange.fetch_ticker(p["sym"])["last"]
            except:
                continue

            pnl=((price-p["entry"])/p["entry"])*50 if p["signal"]=="LONG" else ((p["entry"]-price)/p["entry"])*50
            pnl=round(pnl,2)

            # TP1
            if not p["tp1_done"] and pnl>1:
                p["tp1_done"]=True
                p["remaining"]-=0.5
                send(f"🎯 TP1 {p['sym']} {pnl} USDT")

            # TP2
            elif not p["tp2_done"] and pnl>2:
                p["tp2_done"]=True
                p["remaining"]-=0.25
                send(f"🎯 TP2 {p['sym']} {pnl} USDT")

            # TP3
            elif pnl>3:
                send(f"🚀 TP3 {p['sym']} {pnl} USDT")
                positions.remove(p)
                continue

            # SL
            if pnl<-2:
                send(f"🛑 STOP {p['sym']} {pnl} USDT")
                positions.remove(p)
                continue

        time.sleep(5)

# ==============================
@bot.callback_query_handler(func=lambda call: True)
def callback(call):

    global best_signal

    cid=call.message.chat.id

    if call.data=="enter" and best_signal:
        open_trade(best_signal, cid)

    elif call.data=="pass":
        send("⛔ PAS", cid)

# ==============================
@bot.message_handler(commands=['panel'])
def panel(msg):

    text=f"💀 PANEL\nAçık: {len(positions)}\n"

    for p in positions:
        try:
            price=exchange.fetch_ticker(p["sym"])["last"]
            pnl=((price-p["entry"])/p["entry"])*50
            text+=f"\n{p['sym']} {round(pnl,2)}"
        except:
            pass

    bot.send_message(msg.chat.id,text)

# ==============================
threading.Thread(target=scanner, daemon=True).start()
threading.Thread(target=manage, daemon=True).start()

send(f"💀 BOT {VERSION} AKTİF")
bot.infinity_polling()
