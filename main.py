import os, time, ccxt, telebot, threading
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

# ===== SEND (FIXED) =====
def send(msg, chat_id=None):
    try:
        if chat_id:
            bot.send_message(chat_id, msg, parse_mode="HTML")
        else:
            bot.send_message(CHAT_ID, msg, parse_mode="HTML")
    except:
        print(msg)

# ===== DATA =====
def get_data(sym):
    try:
        df = pd.DataFrame(exchange.fetch_ohlcv(sym,"1m",50),
                          columns=["t","o","h","l","c","v"])
        df["ema"] = df["c"].ewm(20).mean()
        return df
    except:
        return None

# ===== STRUCTURE =====
def structure(df):
    h=df["h"]; l=df["l"]; last=df.iloc[-1]
    high=h.iloc[-5:-1].max(); low=l.iloc[-5:-1].min()

    if last["h"]>high and last["c"]<high: return "FAKE"
    if last["l"]<low and last["c"]>low: return "FAKE"

    if last["c"]>high: return "UP"
    if last["c"]<low: return "DOWN"
    return "NONE"

# ===== WHALE =====
def whale(sym,df):
    try:
        ob=exchange.fetch_order_book(sym,limit=20)
        bids=sum([b[1] for b in ob["bids"]])
        asks=sum([a[1] for a in ob["asks"]])
        return "BUY" if bids>asks else "SELL"
    except:
        return "NEUTRAL"

# ===== COIN PARSER =====
def extract_coin(text):
    words = text.upper().replace("/", " ").split()

    for w in words:
        if len(w) >= 3 and w.isalpha():
            return w

    return None

# ===== AI ANALYZE =====
def analyze_coin(sym, chat_id):
    df = get_data(sym)
    if df is None:
        send("❌ veri yok", chat_id)
        return

    last = df.iloc[-1]

    trend = "UP" if last["c"] > last["ema"] else "DOWN"
    s = structure(df)
    w = whale(sym, df)

    decision = "LONG" if trend=="UP" else "SHORT"

    # AI yorum
    try:
        prompt = f"""
Coin: {sym}
Trend: {trend}
Whale: {w}
Structure: {s}

Explain like a trader. Give entry advice.
"""
        res = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[{"role":"user","content":prompt}],
            temperature=0.7
        )
        comment = res.choices[0].message.content
    except:
        comment = "AI yorum alınamadı"

    price = float(last["c"])

    last_analysis["sym"] = sym
    last_analysis["signal"] = decision
    last_analysis["price"] = price

    send(f"""
💀 <b>AI ANALİZ</b>

📊 {sym}
📈 {decision}

🐋 {w} | 🧠 {s}

💰 {round(price,4)}

{comment}

👉 'gir' yaz
""", chat_id)

# ===== TRADE =====
def open_trade(chat_id):
    if not last_analysis:
        send("❌ önce analiz yap", chat_id)
        return

    sym = last_analysis["sym"]
    signal = last_analysis["signal"]
    price = last_analysis["price"]

    if signal == "LONG":
        tp = price * 1.01
        sl = price * 0.99
    else:
        tp = price * 0.99
        sl = price * 1.01

    positions.append({
        "sym": sym,
        "side": signal,
        "entry": price,
        "tp": tp,
        "sl": sl,
        "peak": 0,
        "tp1": False,
        "chat_id": chat_id
    })

    send(f"""
💀 <b>TRADE AÇILDI</b>

📊 {sym}
📈 {signal}

💰 {round(price,4)}

🎯 {round(tp,4)}
🛑 {round(sl,4)}
""", chat_id)

# ===== MANAGEMENT =====
def manage():
    for p in positions[:]:
        try:
            price = exchange.fetch_ticker(p["sym"])["last"]
        except:
            continue

        entry = p["entry"]

        pnl = ((price-entry)/entry)*100 if p["side"]=="LONG" else ((entry-price)/entry)*100
        p["peak"] = max(p["peak"], pnl)

        chat_id = p["chat_id"]

        if not p["tp1"] and pnl > 1:
            p["tp1"] = True
            send(f"🎯 TP1 {p['sym']} %{round(pnl,2)}", chat_id)

        if pnl < -1:
            send(f"❌ SL {p['sym']} %{round(pnl,2)}", chat_id)
            positions.remove(p)
            continue

        if p["tp1"] and pnl < p["peak"] - 0.5:
            send(f"📊 EXIT {p['sym']} %{round(pnl,2)}", chat_id)
            positions.remove(p)

# ===== TELEGRAM =====
@bot.message_handler(func=lambda m: True)
def handle(msg):
    text = msg.text.lower()
    chat_id = msg.chat.id

    print("GELEN:", text)  # DEBUG

    if "analiz" in text:
        coin = extract_coin(text)

        if not coin:
            send("❌ coin bulunamadı", chat_id)
            return

        sym = coin + "/USDT:USDT"
        analyze_coin(sym, chat_id)

    elif text == "gir":
        open_trade(chat_id)

    elif text == "kapat":
        positions.clear()
        send("Tüm işlemler kapatıldı", chat_id)

# ===== LOOP =====
def loop():
    while True:
        try:
            manage()
            time.sleep(5)
        except:
            time.sleep(5)

threading.Thread(target=loop, daemon=True).start()

send("💀 AI CHAT MODE AKTİF")
bot.infinity_polling()
