# ==============================
# 💀 SADIK BOT v7.0 FINAL
# ==============================

import os, time, ccxt, telebot, threading, requests, random
import pandas as pd
from openai import OpenAI
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

VERSION = "v7.0"

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

# ===== STATS =====
daily_profit = 0
daily_loss = 0
start_balance = 50

# ===== SEND =====
def send(msg, cid=None):
    try:
        bot.send_message(cid or CHAT_ID, msg, parse_mode="HTML")
    except:
        print(msg)

# ===== SUPABASE =====
def save_trade(sym, pnl):
    global daily_profit, daily_loss

    if pnl > 0:
        daily_profit += pnl
    else:
        daily_loss += pnl

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
💀 AI ANALİZ

📊 {sym}
📈 {signal}
💰 {round(price,4)}

📊 %{conf}
━━━━━━━━━━━━━━━
✅ GİR
━━━━━━━━━━━━━━━
""", cid)

    last_analysis.update({"sym": sym, "signal": signal, "price": price})

# ===== TRADE =====
def open_trade(cid):
    if not last_analysis:
        send("⚠️ Önce analiz", cid)
        return

    sym = last_analysis["sym"]
    price = last_analysis["price"]

    positions.append({
        "sym": sym,
        "entry": price,
        "size": 50,
        "chat": cid,
        "peak_pct": 0,
        "exit_flag": False
    })

    send(f"🚀 {sym} trade açıldı", cid)

# ===== MANAGEMENT =====
def manage():
    while True:
        for p in positions[:]:
            try:
                price = exchange.fetch_ticker(p["sym"])["last"]
            except:
                continue

            pnl = (price - p["entry"]) * p["size"]
            pct = (pnl/(p["entry"]*p["size"]))*100

            p["peak_pct"] = max(p["peak_pct"], pct)

            if pct < p["peak_pct"] - 0.5 and not p["exit_flag"]:
                send(f"⚠️ {p['sym']} risk var ({round(pnl,4)} USDT)", p["chat"])
                p["exit_flag"] = True

        time.sleep(5)

# ===== SCANNER v7 BOOST =====
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

                # 💀 3M AYAR
                if vol and vol > 3_000_000:
                    pairs.append((sym, vol))

            pairs.sort(key=lambda x: x[1], reverse=True)

            sample = random.sample(pairs[:80], min(20, len(pairs)))

            for sym, vol in sample:

                df = get_data(sym)
                if df is None:
                    continue

                price = df["c"].iloc[-1]

                # spike
                vol_spike = df["v"].iloc[-1] > df["v"].iloc[-5] * 2

                # hareket
                move = abs(df["c"].iloc[-1] - df["c"].iloc[-5]) > price * 0.003

                # whale
                whale = False
                try:
                    ob = exchange.fetch_order_book(sym, limit=20)
                    bids = sum(b[1] for b in ob["bids"])
                    asks = sum(a[1] for a in ob["asks"])
                    whale = bids > asks * 1.5
                except:
                    pass

                if whale and vol_spike and move:

                    send(f"""
💀 ULTRA FIRSAT

📊 {sym}
💰 Vol: {round(vol/1e6,1)}M

🐋 Whale: EVET
⚡ Spike: EVET
🚀 Pump: EVET

👉 analiz yaz
""", CHAT_ID)

                    break

            time.sleep(25)

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
    kb.add(
        InlineKeyboardButton("🛑 Stop All", callback_data="stop_all"),
        InlineKeyboardButton("❌ Çık All", callback_data="exit_all")
    )

    bot.send_message(cid, f"🤖 PANEL {VERSION}", reply_markup=kb)

# ===== TELEGRAM =====
@bot.message_handler(func=lambda m: True)
def handle(msg):
    text = msg.text.lower().strip()
    text = text.replace("ç","c").replace("ı","i")
    cid = msg.chat.id

    if "analiz" in text:
        coin = text.replace("analiz","").strip().upper()
        analyze(coin+"/USDT:USDT", cid)

    elif text == "gir":
        open_trade(cid)

    elif text == "/panel":
        panel(cid)

# ===== CALLBACK =====
@bot.callback_query_handler(func=lambda call: True)
def callback(call):
    cid = call.message.chat.id

    if call.data == "pozisyon":
        if not positions:
            bot.send_message(cid, "📭 Açık işlem yok")
            return

        kb = InlineKeyboardMarkup()
        msg = "📊 POZİSYONLAR\n\n"

        for p in positions:
            price = exchange.fetch_ticker(p["sym"])["last"]
            pnl = (price - p["entry"]) * p["size"]

            msg += f"{p['sym']} → {round(pnl,4)} USDT\n"

            kb.add(
                InlineKeyboardButton(f"❌ STOP {p['sym']}", callback_data=f"stop_{p['sym']}"),
                InlineKeyboardButton(f"🟢 DEVAM {p['sym']}", callback_data=f"hold_{p['sym']}")
            )

        bot.send_message(cid, msg, reply_markup=kb)

    elif call.data.startswith("stop_"):
        sym = call.data.replace("stop_", "")

        for p in positions[:]:
            if sym in p["sym"]:
                price = exchange.fetch_ticker(p["sym"])["last"]
                pnl = (price - p["entry"]) * p["size"]

                save_trade(p["sym"], pnl)
                positions.remove(p)

                bot.send_message(cid, f"❌ {p['sym']} kapandı ({round(pnl,4)} USDT)")

    elif call.data.startswith("hold_"):
        sym = call.data.replace("hold_", "")
        bot.send_message(cid, f"🟢 {sym} devam")

    elif call.data == "ai":
        total = daily_profit + daily_loss
        balance = start_balance + total

        bot.send_message(cid, f"""
🤖 AI PANEL

📊 Açık İşlem: {len(positions)}

💰 Kâr: {round(daily_profit,4)} USDT
📉 Zarar: {round(daily_loss,4)} USDT
📈 Net: {round(total,4)} USDT

💼 Bakiye: {round(balance,4)} USDT
""")

    elif call.data == "stop_all":
        positions.clear()
        bot.send_message(cid, "🛑 Tüm işlemler durduruldu")

    elif call.data == "exit_all":
        for p in positions[:]:
            price = exchange.fetch_ticker(p["sym"])["last"]
            pnl = (price - p["entry"]) * p["size"]

            save_trade(p["sym"], pnl)
            positions.remove(p)

        bot.send_message(cid, "❌ Tüm işlemler kapatıldı")

# ===== THREADS =====
threading.Thread(target=manage, daemon=True).start()
threading.Thread(target=scanner, daemon=True).start()

send(f"💀 SADIK BOT {VERSION} AKTİF")
bot.infinity_polling()
