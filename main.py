import os, time, ccxt, telebot, threading, requests, random
import pandas as pd
from openai import OpenAI

# ===== CONFIG =====
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
MAX_TRADES = 3

# ===== UI =====
def bar(p):
    f = int(p/10)
    return "█"*f + "░"*(10-f)

def icon(sig):
    return "🟢" if sig=="LONG" else "🔴"

def send(msg, cid=None):
    try:
        bot.send_message(cid or CHAT_ID, msg, parse_mode="HTML")
    except:
        print(msg)

# ===== DATA =====
def get_data(sym):
    try:
        df = pd.DataFrame(exchange.fetch_ohlcv(sym,"1m",50),
                          columns=["t","o","h","l","c","v"])
        if len(df) < 20:
            return None
        df["ema"] = df["c"].ewm(20).mean()
        return df
    except:
        return None

# ===== AI ANALYZE =====
def analyze(sym, cid):
    df = get_data(sym)
    if df is None:
        send(f"❌ Veri yok: {sym}", cid)
        return

    last = df.iloc[-1]
    trend = "UP" if last["c"] > last["ema"] else "DOWN"
    signal = "LONG" if trend=="UP" else "SHORT"
    price = float(last["c"])

    try:
        prompt = f"""
Coin: {sym}
Trend: {trend}

Türkçe kısa yaz:
GIR veya BEKLE
Güç yüzdesi ver
"""
        r = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[{"role":"user","content":prompt}]
        )
        txt = r.choices[0].message.content
        print("AI:", txt)
    except Exception as e:
        print("AI ERROR:", e)
        txt = "BEKLE %50"

    conf = 50
    if "%" in txt:
        try:
            conf = int(''.join(filter(str.isdigit, txt)))
        except:
            pass

    decision = "GİR" if "GIR" in txt.upper() else "BEKLE"

    send(f"""
💀 <b>AI ANALİZ</b>

📊 {sym}
📈 {signal} {icon(signal)}
💰 {round(price,4)}

📊 GÜÇ: %{conf} {bar(conf)}

━━━━━━━━━━━━━━━
{'✅ GİR' if decision=='GİR' else '⏳ BEKLE'}
━━━━━━━━━━━━━━━
""", cid)

    last_analysis.update({
        "sym": sym,
        "signal": signal,
        "price": price
    })

# ===== TRADE =====
def open_trade(cid):
    if len(positions) >= MAX_TRADES:
        send("⚠️ Max 3 trade", cid)
        return

    sym = last_analysis["sym"]
    signal = last_analysis["signal"]
    price = last_analysis["price"]

    size = 50
    sl = price*0.99 if signal=="LONG" else price*1.01

    positions.append({
        "sym": sym,
        "side": signal,
        "entry": price,
        "size": size,
        "sl": sl,
        "peak": 0,
        "chat": cid
    })

    send(f"""
🚀 <b>TRADE</b>

📊 {sym}
📈 {signal} {icon(signal)}

💰 {round(price,4)}
💵 {size} USDT
🛑 SL: {round(sl,4)}
""", cid)

# ===== MANAGEMENT =====
def manage():
    while True:
        for p in positions[:]:
            try:
                price = exchange.fetch_ticker(p["sym"])["last"]
            except:
                continue

            entry = p["entry"]
            size = p["size"]

            pnl = (price-entry)*size if p["side"]=="LONG" else (entry-price)*size
            pct = (pnl/(entry*size))*100

            p["peak"] = max(p["peak"], pct)
            cid = p["chat"]

            if pct > 1 and p["sl"] != entry:
                p["sl"] = entry
                send(f"🎯 TP1 {p['sym']} +{round(pnl,2)} USDT", cid)

        time.sleep(5)

# ===== SMART SCANNER =====
def scanner():
    while True:
        try:
            tickers = exchange.fetch_tickers()

            # 🔥 TOP VOLUME + RANDOM
            pairs = [(s, x['quoteVolume']) for s,x in tickers.items()
                     if ":USDT" in s and x.get('quoteVolume')]

            pairs.sort(key=lambda x: x[1], reverse=True)

            # BTC ETH XRP çıkar
            filtered = [p[0] for p in pairs if not any(x in p[0] for x in ["BTC","ETH","XRP"])]

            sample = random.sample(filtered[:100], min(20, len(filtered)))

            for sym in sample:
                df = get_data(sym)
                if df is None:
                    continue

                last = df.iloc[-1]

                # 🔥 VOLATILITY + TREND
                move = abs(df["c"].iloc[-1] - df["c"].iloc[-5])

                if move > df["c"].iloc[-1]*0.002:
                    send(f"""
💀 <b>FIRSAT</b>

📊 {sym}
📈 HAREKET VAR

👉 analiz yaz
""", CHAT_ID)
                    break

            time.sleep(20)

        except Exception as e:
            print("SCAN ERR:", e)
            time.sleep(10)

# ===== TELEGRAM =====
@bot.message_handler(func=lambda m: True)
def handle(msg):
    text = msg.text.lower()
    cid = msg.chat.id

    if "analiz" in text:
        coin = text.replace("analiz","").strip().upper()
        analyze(coin + "/USDT:USDT", cid)

    elif text == "gir":
        open_trade(cid)

# ===== THREADS =====
threading.Thread(target=manage, daemon=True).start()
threading.Thread(target=scanner, daemon=True).start()

send("💀 MASTER AI FIXED AKTİF")
bot.infinity_polling()
