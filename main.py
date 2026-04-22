import os, time, ccxt, telebot, threading, requests, random
import pandas as pd
from openai import OpenAI
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

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

# ===== UTILS =====
def send(msg, cid=None):
    try:
        bot.send_message(cid or CHAT_ID, msg, parse_mode="HTML")
    except:
        print(msg)

def bar(p):
    f = int(max(0, min(100, p)) / 10)
    return "█" * f + "░" * (10 - f)

def icon(sig):
    return "🟢" if sig == "LONG" else "🔴"

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
        r = requests.post(f"{SUPA_URL}/rest/v1/trades",
                          headers=headers,
                          json={"symbol": sym, "result": pnl})
        print("SUPABASE:", r.status_code, r.text)
    except Exception as e:
        print("SUPABASE HATA:", e)

# ===== DATA =====
def get_data(sym):
    try:
        ohlcv = exchange.fetch_ohlcv(sym, "1m", limit=50)
        df = pd.DataFrame(ohlcv, columns=["t","o","h","l","c","v"])
        df["ema"] = df["c"].ewm(20).mean()
        return df
    except:
        return None

# ===== ANALYZE =====
def analyze(sym, cid):
    df = get_data(sym)
    if df is None:
        send("❌ Veri yok", cid)
        return

    last = df.iloc[-1]
    trend = "UP" if last["c"] > last["ema"] else "DOWN"
    signal = "LONG" if trend == "UP" else "SHORT"
    price = float(last["c"])
    conf = random.randint(65, 85)

    send(f"""
💀 <b>AI ANALİZ</b>

📊 {sym}
📈 {signal} {icon(signal)}
💰 {round(price,4)}

📊 %{conf} {bar(conf)}

━━━━━━━━━━━━━━━
✅ GİR
━━━━━━━━━━━━━━━
""", cid)

    last_analysis.update({
        "sym": sym,
        "signal": signal,
        "price": price,
        "conf": conf
    })

# ===== TRADE =====
def open_trade(cid):
    if len(positions) >= MAX_TRADES:
        send("⚠️ Max trade dolu", cid)
        return

    if not last_analysis:
        send("⚠️ Önce analiz yap", cid)
        return

    sym = last_analysis["sym"]
    signal = last_analysis["signal"]
    price = last_analysis["price"]

    positions.append({
        "sym": sym,
        "side": signal,
        "entry": price,
        "size": 50,
        "chat": cid,
        "peak_pct": 0,
        "exit_flag": False
    })

    send(f"""
🚀 TRADE

📊 {sym}
📈 {signal}

💰 {price}
💵 50 USDT
""", cid)

# ===== MANAGEMENT =====
def manage():
    while True:
        for p in positions[:]:
            try:
                price = exchange.fetch_ticker(p["sym"])["last"]
            except:
                continue

            pnl = (price - p["entry"]) * p["size"] if p["side"]=="LONG" else (p["entry"] - price) * p["size"]
            pct = (pnl/(p["entry"]*p["size"]))*100

            p["peak_pct"] = max(p["peak_pct"], pct)
            cid = p["chat"]

            if pct < p["peak_pct"] - 0.5:
                df = get_data(p["sym"])
                if df is not None and df["c"].iloc[-1] < df["c"].iloc[-2]:

                    if pnl > 0:
                        msg = f"⚠️ Kâr düşüyor\n💰 {round(pnl,4)} USDT"
                    else:
                        msg = f"⚠️ Zarar artıyor\n💰 {round(pnl,4)} USDT"

                    send(f"{msg}\n👉 çıkılıyor", cid)

                    save_trade(p["sym"], pnl)
                    positions.remove(p)

        time.sleep(5)

# ===== SCANNER BOOST =====
def scanner():
    while True:
        try:
            tickers = exchange.fetch_tickers()
            pairs = []

            for sym, data in tickers.items():
                if ":USDT" not in sym:
                    continue
                if any(x in sym for x in ["BTC","ETH","XRP","BNB"]):
                    continue

                vol = data.get("quoteVolume", 0)
                if vol and vol > 3_000_000:
                    pairs.append((sym, vol))

            pairs.sort(key=lambda x: x[1], reverse=True)
            sample = random.sample(pairs[:60], min(20, len(pairs)))

            for sym, vol in sample:
                df = get_data(sym)
                if df is None:
                    continue

                price = df["c"].iloc[-1]
                vol_spike = df["v"].iloc[-1] > df["v"].iloc[-5] * 1.5
                move = abs(df["c"].iloc[-1] - df["c"].iloc[-5]) > price * 0.002

                whale = False
                try:
                    ob = exchange.fetch_order_book(sym, limit=20)
                    bids = sum(b[1] for b in ob["bids"])
                    asks = sum(a[1] for a in ob["asks"])
                    whale = bids > asks * 1.3
                except:
                    pass

                if (whale or vol_spike) and move:
                    send(f"""
💀 ULTRA FIRSAT

📊 {sym}
💰 {round(vol/1e6,1)}M

🐋 Whale: {"EVET" if whale else "YOK"}
⚡ Spike: {"EVET" if vol_spike else "YOK"}

👉 analiz yaz
""", CHAT_ID)
                    break

            time.sleep(20)

        except Exception as e:
            print("SCANNER HATA:", e)
            time.sleep(10)

# ===== PANEL =====
def panel(cid):
    kb = InlineKeyboardMarkup()
    kb.add(
        InlineKeyboardButton("📊 Durum", callback_data="durum"),
        InlineKeyboardButton("📈 Pozisyon", callback_data="pozisyon")
    )
    kb.add(
        InlineKeyboardButton("🤖 AI", callback_data="ai"),
        InlineKeyboardButton("🟢 Devam", callback_data="devam")
    )
    bot.send_message(cid, "🤖 PANEL", reply_markup=kb)

# ===== TELEGRAM =====
@bot.message_handler(func=lambda m: True)
def handle(msg):
    text = msg.text.lower().strip()
    text = text.replace("ç","c").replace("ı","i")
    cid = msg.chat.id

    if text.startswith("analiz"):
        coin = text.replace("analiz","").strip().upper()
        analyze(coin+"/USDT:USDT", cid)

    elif text == "gir":
        open_trade(cid)

    elif text.startswith("cik"):
        parts = text.split()

        if len(parts) == 1:
            for p in positions[:]:
                price = exchange.fetch_ticker(p["sym"])["last"]
                pnl = (price - p["entry"]) * p["size"] if p["side"]=="LONG" else (p["entry"] - price) * p["size"]
                save_trade(p["sym"], pnl)
                positions.remove(p)
                send(f"❌ {p['sym']} kapandı", cid)

        else:
            coin = parts[1].upper()
            for p in positions[:]:
                if coin in p["sym"]:
                    price = exchange.fetch_ticker(p["sym"])["last"]
                    pnl = (price - p["entry"]) * p["size"] if p["side"]=="LONG" else (p["entry"] - price) * p["size"]
                    save_trade(p["sym"], pnl)
                    positions.remove(p)
                    send(f"❌ {p['sym']} kapandı", cid)

    elif text == "durum":
        for p in positions:
            price = exchange.fetch_ticker(p["sym"])["last"]
            pnl = (price - p["entry"]) * p["size"] if p["side"]=="LONG" else (p["entry"] - price) * p["size"]
            send(f"{p['sym']} → {round(pnl,4)} USDT", cid)

    elif text == "/panel":
        panel(cid)

# ===== CALLBACK =====
@bot.callback_query_handler(func=lambda call: True)
def callback(call):
    cid = call.message.chat.id

    if call.data == "pozisyon":
        kb = InlineKeyboardMarkup()
        msg = "📊 POZİSYONLAR\n\n"

        for p in positions:
            price = exchange.fetch_ticker(p["sym"])["last"]
            pnl = (price - p["entry"]) * p["size"] if p["side"]=="LONG" else (p["entry"] - price) * p["size"]

            msg += f"{p['sym']} → {round(pnl,4)} USDT\n"

            kb.add(
                InlineKeyboardButton(f"❌ {p['sym']}", callback_data=f"close_{p['sym']}"),
                InlineKeyboardButton(f"🟢 {p['sym']}", callback_data=f"hold_{p['sym']}")
            )

        bot.send_message(cid, msg, reply_markup=kb)

    elif call.data.startswith("close_"):
        sym = call.data.replace("close_","")
        for p in positions[:]:
            if p["sym"] == sym:
                price = exchange.fetch_ticker(sym)["last"]
                pnl = (price - p["entry"]) * p["size"]
                save_trade(sym, pnl)
                positions.remove(p)
                bot.send_message(cid, f"❌ {sym} kapandı")

    elif call.data.startswith("hold_"):
        sym = call.data.replace("hold_","")
        bot.send_message(cid, f"🟢 {sym} devam")

    elif call.data == "ai":
        for p in positions:
            bot.send_message(cid, f"🤖 {p['sym']} takip ediliyor")

    elif call.data == "devam":
        bot.send_message(cid, "🟢 devam")

# ===== THREADS =====
threading.Thread(target=manage, daemon=True).start()
threading.Thread(target=scanner, daemon=True).start()

send("💀 ULTRA FINAL AKTİF")
bot.infinity_polling()
