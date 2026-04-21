import os, time, ccxt, telebot, threading
import pandas as pd
from openai import OpenAI

TOKEN = os.getenv("TELE_TOKEN")
CHAT_ID = os.getenv("MY_CHAT_ID")
OPENAI_KEY = os.getenv("OPENAI_API_KEY")

bot = telebot.TeleBot(TOKEN)
client = OpenAI(api_key=OPENAI_KEY)

exchange = ccxt.bitget({
    "apiKey": os.getenv("BITGET_API"),
    "secret": os.getenv("BITGET_SEC"),
    "password": os.getenv("BITGET_PASS"),
    "options": {"defaultType":"swap"},
    "enableRateLimit": True
})

positions = []
last_analysis = {}

def send(msg, chat_id=None):
    try:
        bot.send_message(chat_id or CHAT_ID, msg)
    except:
        print(msg)

def get_data(sym):
    try:
        ohlcv = exchange.fetch_ohlcv(sym, "1m", limit=50)
        if not ohlcv: return None
        df = pd.DataFrame(ohlcv, columns=["t","o","h","l","c","v"])
        df["ema"] = df["c"].ewm(20).mean()
        return df
    except:
        return None

def analyze(sym, chat_id):
    df = get_data(sym)
    if df is None:
        send("❌ Veri yok", chat_id)
        return

    last = df.iloc[-1]
    trend = "UP" if last["c"] > last["ema"] else "DOWN"
    decision = "LONG" if trend=="UP" else "SHORT"
    price = float(last["c"])

    prompt = f"""
Coin: {sym}
Trend: {trend}

Türkçe kısa yaz.
GIR / BEKLE yaz.
Güç yüzdesi ver.
"""

    try:
        res = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[{"role":"user","content":prompt}]
        )
        comment = res.choices[0].message.content
    except:
        comment = "AI hata"

    last_analysis["sym"]=sym
    last_analysis["signal"]=decision
    last_analysis["price"]=price

    send(f"""
💀 AI ANALİZ

{sym}
{decision}
{price}

{comment}

👉 gir
""", chat_id)

def open_trade(chat_id):
    if not last_analysis:
        send("Analiz yok", chat_id)
        return

    sym = last_analysis["sym"]
    signal = last_analysis["signal"]
    price = last_analysis["price"]

    margin = 5
    leverage = 10
    size = margin * leverage

    if signal=="LONG":
        tp = price * 1.01
        sl = price * 0.99
    else:
        tp = price * 0.99
        sl = price * 1.01

    positions.append({
        "sym": sym,
        "side": signal,
        "entry": price,
        "size": size,
        "tp": tp,
        "sl": sl,
        "peak": 0,
        "chat_id": chat_id,
        "last_alert": 0
    })

    send(f"""
💀 TRADE AÇILDI

{sym} {signal}
Entry: {price}

TP: {tp}
SL: {sl}
""", chat_id)

def manage():
    for p in positions[:]:
        try:
            price = exchange.fetch_ticker(p["sym"])["last"]
        except:
            continue

        entry = p["entry"]
        size = p["size"]

        pnl = (price-entry)*size if p["side"]=="LONG" else (entry-price)*size
        pnl_pct = (pnl/(entry*size))*100

        p["peak"] = max(p["peak"], pnl_pct)

        chat_id = p["chat_id"]

        # TP1
        if pnl_pct > 1 and p["sl"] != entry:
            p["sl"] = entry
            send(f"🎯 TP1 geldi\n🛡 SL girişe çekildi\n💰 {round(pnl,2)} USDT", chat_id)

        # TRAILING
        if pnl_pct > 1:
            new_sl = entry + (p["peak"]/100)*entry*0.5 if p["side"]=="LONG" else entry - (p["peak"]/100)*entry*0.5
            if (p["side"]=="LONG" and new_sl > p["sl"]) or (p["side"]=="SHORT" and new_sl < p["sl"]):
                p["sl"] = new_sl
                send(f"🔼 SL güncellendi: {round(new_sl,4)}", chat_id)

        # RISK ANALYSIS
        df = get_data(p["sym"])
        if df is None: continue

        last = df.iloc[-1]
        trend = "UP" if last["c"] > last["ema"] else "DOWN"

        now = time.time()

        # TEHLİKE
        if (p["side"]=="LONG" and trend=="DOWN") or (p["side"]=="SHORT" and trend=="UP"):
            if now - p["last_alert"] > 10:
                p["last_alert"] = now
                send(f"🚨 Trend ters! Çıkılıyor\n💰 {round(pnl,2)} USDT", chat_id)
                positions.remove(p)

def handle(msg):
    text = msg.text.lower()
    chat_id = msg.chat.id

    if "analiz" in text:
        coin = text.split(" ")[0].upper()
        sym = coin + "/USDT:USDT"
        analyze(sym, chat_id)

    elif text == "gir":
        open_trade(chat_id)

bot.message_handler(func=lambda m: True)(handle)

def loop():
    while True:
        manage()
        time.sleep(3)

threading.Thread(target=loop, daemon=True).start()

send("💀 AI TRADER AKTİF")
bot.infinity_polling()
