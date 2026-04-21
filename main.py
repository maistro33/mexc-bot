import os, time, ccxt, telebot, threading, requests
import pandas as pd
from openai import OpenAI

# ===== CONFIG =====
TOKEN = os.getenv("TELE_TOKEN")
CHAT_ID = os.getenv("MY_CHAT_ID")
OPENAI_KEY = os.getenv("OPENAI_API_KEY")

SUPA_URL = os.getenv("SUPABASE_URL")
SUPA_KEY = os.getenv("SUPABASE_KEY")

bot = telebot.TeleBot(TOKEN)
client = OpenAI(api_key=OPENAI_KEY)

exchange = ccxt.bitget({
    "apiKey": os.getenv("BITGET_API"),
    "secret": os.getenv("BITGET_SEC"),
    "password": os.getenv("BITGET_PASS"),
    "options": {"defaultType":"swap"},
    "enableRateLimit": True
})

# ===== STATE =====
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

# ===== SUPABASE =====
def save_trade(sym, pnl):
    try:
        headers = {
            "apikey": SUPA_KEY,
            "Authorization": f"Bearer {SUPA_KEY}",
            "Content-Type": "application/json"
        }
        requests.post(f"{SUPA_URL}/rest/v1/trades",
                      headers=headers,
                      json={"symbol": sym, "result": pnl})
    except:
        pass

# ===== DATA =====
def get_data(sym):
    try:
        ohlcv = exchange.fetch_ohlcv(sym, "1m", limit=50)
        if not ohlcv or len(ohlcv) < 10:
            return None
        df = pd.DataFrame(ohlcv, columns=["t","o","h","l","c","v"])
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

    prompt = f"{sym} {trend} Türkçe kısa yaz GIR/BEKLE % ver"

    try:
        r = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[{"role":"user","content":prompt}]
        )
        txt = r.choices[0].message.content
    except:
        txt = "GIR %60"

    conf = 60
    if "%" in txt:
        try:
            conf = int(txt.split("%")[1][:2])
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
        "chat": cid,
        "alert_time": 0,
        "exit_flag": False,
        "exit_time": 0
    })

    send(f"""
🚀 <b>TRADE AÇILDI</b>

📊 {sym}
📈 {signal} {icon(signal)}

💰 Entry: {round(price,4)}
💵 Size: {size} USDT
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

            # TP1
            if pct > 1 and p["sl"] != entry:
                p["sl"] = entry
                send(f"🎯 TP1 {p['sym']} +{round(pnl,2)} USDT\n🛡 SL entry", cid)

            # trailing
            if pct > 1:
                new_sl = entry + (p["peak"]/100)*entry*0.5 if p["side"]=="LONG" else entry - (p["peak"]/100)*entry*0.5
                if (p["side"]=="LONG" and new_sl > p["sl"]) or (p["side"]=="SHORT" and new_sl < p["sl"]):
                    p["sl"] = new_sl
                    send(f"🔼 SL → {round(new_sl,4)}", cid)

            # trend check
            df = get_data(p["sym"])
            if df is None:
                continue

            trend = "UP" if df.iloc[-1]["c"] > df.iloc[-1]["ema"] else "DOWN"

            now = time.time()

            # risk uyarı
            if now - p["alert_time"] > 20:
                p["alert_time"] = now

                if pct > 0:
                    send(f"📊 {p['sym']} +{round(pnl,2)} USDT\n👉 Devam?", cid)

                if (p["side"]=="LONG" and trend=="DOWN") or (p["side"]=="SHORT" and trend=="UP"):
                    send(f"⚠️ Trend ters {p['sym']}\n👉 Çık?", cid)
                    p["exit_flag"] = True
                    p["exit_time"] = now

            # non-blocking exit
            if p["exit_flag"]:
                if now - p["exit_time"] > 10:
                    send(f"🚨 AI ÇIKIŞ {p['sym']} {round(pnl,2)} USDT", cid)
                    save_trade(p["sym"], pnl)
                    positions.remove(p)

        time.sleep(5)

# ===== SCANNER =====
def scanner():
    while True:
        try:
            if len(positions) >= MAX_TRADES:
                time.sleep(10)
                continue

            tickers = exchange.fetch_tickers()
            coins = [c for c in tickers if ":USDT" in c]

            for sym in coins[:40]:
                df = get_data(sym)
                if df is None:
                    continue

                last = df.iloc[-1]

                if last["c"] > df["ema"].iloc[-1]:
                    send(f"""
💀 <b>FIRSAT</b>

📊 {sym}
📈 LONG

👉 analiz yaz
""", CHAT_ID)
                    break

            time.sleep(30)
        except:
            time.sleep(10)

# ===== TELEGRAM =====
@bot.message_handler(func=lambda m: True)
def handle(msg):
    text = msg.text.lower()
    cid = msg.chat.id

    print("GELEN:", text)

    if "analiz" in text:
        coin = text.replace("analiz","").strip().upper()
        analyze(coin + "/USDT:USDT", cid)

    elif text == "gir":
        open_trade(cid)

# ===== THREADS =====
threading.Thread(target=manage, daemon=True).start()
threading.Thread(target=scanner, daemon=True).start()

send("💀 MASTER AI STABLE AKTİF")
bot.infinity_polling()
