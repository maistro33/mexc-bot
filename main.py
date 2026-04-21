import os, time, ccxt, telebot, requests
import pandas as pd
from openai import OpenAI

# ===== CONFIG =====
TOKEN = os.getenv("TELE_TOKEN")
CHAT_ID = os.getenv("MY_CHAT_ID")
OPENAI_KEY = os.getenv("OPENAI_API_KEY")

bot = telebot.TeleBot(TOKEN)
client = OpenAI(api_key=OPENAI_KEY)

# ===== EXCHANGE =====
exchange = ccxt.bitget({
    "apiKey": os.getenv("BITGET_API"),
    "secret": os.getenv("BITGET_SEC"),
    "password": os.getenv("BITGET_PASS"),
    "options": {"defaultType":"swap"},
    "enableRateLimit": True
})

# ===== STATE =====
last_analysis = {}
positions = []

# ===== HELPERS =====
def send(msg):
    try:
        bot.send_message(CHAT_ID, msg)
    except:
        print(msg)

def get_data(sym):
    df = pd.DataFrame(exchange.fetch_ohlcv(sym,"1m",50),
                      columns=["t","o","h","l","c","v"])
    df["ema"] = df["c"].ewm(20).mean()
    return df

def structure(df):
    h=df["h"]; l=df["l"]; last=df.iloc[-1]
    high=h.iloc[-5:-1].max(); low=l.iloc[-5:-1].min()
    if last["c"]>high: return "UP"
    if last["c"]<low: return "DOWN"
    return "NONE"

def whale(sym,df):
    ob=exchange.fetch_order_book(sym,limit=20)
    bids=sum([b[1] for b in ob["bids"]])
    asks=sum([a[1] for a in ob["asks"]])
    if bids>asks: return "BUY"
    return "SELL"

# ===== ANALYZE =====
def analyze_coin(sym):
    try:
        df = get_data(sym)
        last = df.iloc[-1]

        trend = "UP" if last["c"] > last["ema"] else "DOWN"
        w = whale(sym,df)
        s = structure(df)

        prompt = f"""
Coin: {sym}
Trend: {trend}
Whale: {w}
Structure: {s}

Explain like a trader.
"""

        res = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[{"role":"user","content":prompt}]
        )

        comment = res.choices[0].message.content

        decision = "LONG" if trend=="UP" else "SHORT"

        last_analysis["sym"]=sym
        last_analysis["decision"]=decision
        last_analysis["price"]=float(last["c"])

        send(f"""
💀 ANALİZ

📊 {sym}
📈 {decision}

🐋 {w} | 🧠 {s}

{comment}

👉 'gir' yaz
""")

    except Exception as e:
        send(f"Hata: {e}")

# ===== TRADE =====
def open_trade():
    if not last_analysis:
        send("Önce analiz yap")
        return

    sym = last_analysis["sym"]
    signal = last_analysis["decision"]
    price = last_analysis["price"]

    if signal=="LONG":
        tp = price*1.01
        sl = price*0.99
    else:
        tp = price*0.99
        sl = price*1.01

    positions.append({
        "sym":sym,
        "side":signal,
        "entry":price,
        "tp":tp,
        "sl":sl,
        "peak":0,
        "tp1":False
    })

    send(f"""
💀 TRADE AÇILDI

📊 {sym}
📈 {signal}
💰 {price}

🎯 {round(tp,4)}
🛑 {round(sl,4)}
""")

# ===== MANAGEMENT =====
def manage():
    for p in positions[:]:
        price = exchange.fetch_ticker(p["sym"])["last"]
        entry = p["entry"]

        pnl = ((price-entry)/entry)*100 if p["side"]=="LONG" else ((entry-price)/entry)*100
        p["peak"]=max(p["peak"],pnl)

        if not p["tp1"] and pnl>1:
            p["tp1"]=True
            send(f"🎯 TP1 {p['sym']} %{round(pnl,2)}")

        if pnl<-1:
            send(f"❌ SL {p['sym']} %{round(pnl,2)}")
            positions.remove(p)
            continue

        if p["tp1"] and pnl<p["peak"]-0.5:
            send(f"📊 EXIT {p['sym']} %{round(pnl,2)}")
            positions.remove(p)

# ===== TELEGRAM =====
@bot.message_handler(func=lambda m: True)
def handle(msg):
    text = msg.text.lower()

    if "analiz" in text:
        coin = text.split(" ")[0].upper()
        sym = coin + "/USDT:USDT"
        analyze_coin(sym)

    elif text == "gir":
        open_trade()

    elif text == "kapat":
        positions.clear()
        send("Tüm işlemler kapatıldı")

# ===== LOOP =====
def loop():
    while True:
        try:
            manage()
            time.sleep(5)
        except:
            time.sleep(5)

import threading
threading.Thread(target=loop,daemon=True).start()

send("💀 AI CHAT MODE AKTİF")
bot.infinity_polling()
