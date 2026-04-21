import os, time, ccxt, telebot, threading, requests, random
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
    "options": {"defaultType": "swap"},
    "enableRateLimit": True
})

positions = []
last_analysis = {}
MAX_TRADES = 3

# ===== UI =====
def bar(p):
    p = max(0, min(100, p))
    f = int(p / 10)
    return "█" * f + "░" * (10 - f)

def icon(sig):
    return "🟢" if sig == "LONG" else "🔴"

def send(msg, cid=None):
    try:
        bot.send_message(cid or CHAT_ID, msg, parse_mode="HTML")
    except Exception as e:
        print("SEND ERROR:", e)

# ===== SUPABASE =====
def save_trade(sym, pnl):
    if not SUPA_URL or not SUPA_KEY:
        return
    try:
        headers = {
            "apikey": SUPA_KEY,
            "Authorization": f"Bearer {SUPA_KEY}",
            "Content-Type": "application/json"
        }
        requests.post(f"{SUPA_URL}/rest/v1/trades",
                      headers=headers,
                      json={"symbol": sym, "result": pnl})
    except Exception as e:
        print("SUPA ERROR:", e)

# ===== DATA (RETRY) =====
def get_data(sym):
    for _ in range(3):
        try:
            ohlcv = exchange.fetch_ohlcv(sym, "1m", limit=50)
            if not ohlcv or len(ohlcv) < 20:
                time.sleep(0.5)
                continue

            df = pd.DataFrame(ohlcv, columns=["t","o","h","l","c","v"])
            df["ema"] = df["c"].ewm(20).mean()
            return df

        except Exception as e:
            print("DATA ERR:", sym, e)
            time.sleep(0.5)
    return None

# ===== AI =====
def analyze(sym, cid):
    df = get_data(sym)
    if df is None:
        return

    last = df.iloc[-1]
    trend = "UP" if last["c"] > last["ema"] else "DOWN"
    signal = "LONG" if trend == "UP" else "SHORT"
    price = float(last["c"])

    try:
        prompt = f"{sym} {trend} Türkçe kısa: GIR/BEKLE ve %"
        r = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[{"role":"user","content":prompt}]
        )
        txt = r.choices[0].message.content
    except Exception as e:
        print("AI ERR:", e)
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

📊 %{conf} {bar(conf)}

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
        send("⚠️ Max trade dolu", cid)
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

💰 {price}
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

            # TP1
            if pct > 1 and p["sl"] != entry:
                p["sl"] = entry
                send(f"🎯 TP1 {p['sym']} +{round(pnl,2)} USDT", cid)

            # trailing
            if pct > 1:
                new_sl = entry + (p["peak"]/100)*entry*0.5 if p["side"]=="LONG" else entry - (p["peak"]/100)*entry*0.5
                if (p["side"]=="LONG" and new_sl > p["sl"]) or (p["side"]=="SHORT" and new_sl < p["sl"]):
                    p["sl"] = new_sl
                    send(f"🔼 SL → {round(new_sl,4)}", cid)

        time.sleep(5)

# ===== ULTRA SCANNER =====
def scanner():
    while True:
        try:
            tickers = exchange.fetch_tickers()

            pairs = []
            for sym, data in tickers.items():

                if ":USDT" not in sym:
                    continue

                # ağır coinleri çıkar
                if any(x in sym for x in ["BTC","ETH","XRP","BNB"]):
                    continue

                vol = data.get("quoteVolume", 0)

                if vol and vol > 3_000_000:
                    pairs.append((sym, vol))

            pairs.sort(key=lambda x: x[1], reverse=True)

            sample = random.sample(pairs[:100], min(25, len(pairs)))

            for sym, vol in sample:

                df = get_data(sym)
                if df is None:
                    continue

                price = df["c"].iloc[-1]

                # ===== VOLUME SPIKE =====
                vol_now = df["v"].iloc[-1]
                vol_prev = df["v"].iloc[-5]
                vol_spike = vol_now > vol_prev * 2

                # ===== MOMENTUM =====
                move = abs(df["c"].iloc[-1] - df["c"].iloc[-5])
                momentum = move > price * 0.003

                # ===== WHALE =====
                whale = False
                try:
                    ob = exchange.fetch_order_book(sym, limit=20)
                    bids = sum([b[1] for b in ob["bids"]])
                    asks = sum([a[1] for a in ob["asks"]])
                    whale = bids > asks * 1.5
                except:
                    pass

                # ===== PUMP DETECTOR =====
                pump = (df["c"].iloc[-1] > df["c"].iloc[-3] * 1.005)

                if vol_spike and momentum and (whale or pump):

                    send(f"""
💀 <b>ULTRA FIRSAT</b>

📊 {sym}
💰 Vol: {round(vol/1e6,1)}M

🐋 Whale: {'EVET' if whale else 'YOK'}
⚡ Spike: EVET
🚀 Pump: {'EVET' if pump else 'YOK'}

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

send("💀 ULTRA MASTER AI AKTİF")
bot.infinity_polling()
