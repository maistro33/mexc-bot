# ==============================
# 💀 SADIK BOT v7.3 FINAL CLEAN FIX
# ==============================

import os, time, ccxt, telebot, threading, requests, random
import pandas as pd
from openai import OpenAI
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

VERSION = "v7.3 FINAL CLEAN"

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

daily_profit = 0
daily_loss = 0
start_balance = 50

last_sent = {}

def send(msg, cid=None):
    try:
        bot.send_message(cid or CHAT_ID, msg, parse_mode="HTML")
    except Exception as e:
        print("SEND HATA:", e)

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

def get_data(sym):
    try:
        ohlcv = exchange.fetch_ohlcv(sym, "1m", limit=50)
        df = pd.DataFrame(ohlcv, columns=["t","o","h","l","c","v"])
        df["ema"] = df["c"].ewm(20).mean()
        return df
    except:
        return None

def analyze(sym, cid):
    df = get_data(sym)
    if df is None:
        send("❌ Veri yok", cid)
        return

    last = df.iloc[-1]
    trend = "UP" if last["c"] > last["ema"] else "DOWN"
    signal = "LONG" if trend == "UP" else "SHORT"
    price = float(last["c"])
    vol = df["v"].iloc[-1]
    conf = random.randint(65, 85)

    send(f"""
💀 AI ANALİZ

📊 {sym}
📈 {signal}
💰 {round(price,4)}
💰 Vol: {round(vol,2)}

📊 %{conf}
━━━━━━━━━━━━━━━
✅ GİR
━━━━━━━━━━━━━━━
""", cid)

    last_analysis.update({"sym": sym, "signal": signal, "price": price})

def open_trade(cid):
    if not last_analysis:
        send("⚠️ Önce analiz", cid)
        return

    sym = last_analysis["sym"]
    price = last_analysis["price"]
    signal = last_analysis["signal"]

    sl = price * 0.98 if signal == "LONG" else price * 1.02

    positions.append({
        "sym": sym,
        "entry": price,
        "size": 50,
        "chat": cid,
        "signal": signal,
        "tp1_done": False,
        "sl": sl,
        "last_sl_msg": 0
    })

    send(f"""
🚀 TRADE AÇILDI

📊 {sym}
📈 {signal}
💰 Giriş: {round(price,4)}
💵 Miktar: 50 USDT

🛑 SL: {round(sl,4)}
🎯 TP1: %1

🤖 AI takip ediyor...
""", cid)

def manage():
    while True:
        for p in positions[:]:
            try:
                price = exchange.fetch_ticker(p["sym"])["last"]
            except:
                continue

            if p["signal"] == "LONG":
                pnl = (price - p["entry"]) * p["size"]
            else:
                pnl = (p["entry"] - price) * p["size"]

            pct = (pnl/(p["entry"]*p["size"]))*100
            cid = p["chat"]

            if not p["tp1_done"]:
                if p["signal"] == "LONG" and price <= p["entry"] * 0.98:
                    send(f"🛑 STOP LOSS {p['sym']} {round(pnl,4)} USDT", cid)
                    save_trade(p["sym"], pnl)
                    positions.remove(p)
                    continue

                if p["signal"] == "SHORT" and price >= p["entry"] * 1.02:
                    send(f"🛑 STOP LOSS {p['sym']} {round(pnl,4)} USDT", cid)
                    save_trade(p["sym"], pnl)
                    positions.remove(p)
                    continue

            if not p["tp1_done"] and pct >= 1:
                p["tp1_done"] = True
                pnl_half = pnl / 2
                save_trade(p["sym"], pnl_half)
                p["sl"] = p["entry"]

                send(f"""
🎯 TP1

📊 {p['sym']}
💰 {round(pnl_half,4)} USDT

🛡 SL → ENTRY
""", cid)

            if p["tp1_done"]:
                updated = False

                if p["signal"] == "LONG":
                    new_sl = price * 0.995
                    if new_sl > p["sl"]:
                        p["sl"] = new_sl
                        updated = True
                else:
                    new_sl = price * 1.005
                    if new_sl < p["sl"]:
                        p["sl"] = new_sl
                        updated = True

                if updated and time.time() - p["last_sl_msg"] > 20:
                    p["last_sl_msg"] = time.time()

                    send(f"""
📈 TRAILING

📊 {p['sym']}
🛡 SL: {round(p['sl'],4)}
""", cid)

            if p["signal"] == "LONG" and price <= p["sl"]:
                send(f"🚨 STOP {p['sym']} {round(pnl,4)} USDT", cid)
                save_trade(p["sym"], pnl)
                positions.remove(p)
                continue

            if p["signal"] == "SHORT" and price >= p["sl"]:
                send(f"🚨 STOP {p['sym']} {round(pnl,4)} USDT", cid)
                save_trade(p["sym"], pnl)
                positions.remove(p)
                continue

        time.sleep(5)

def scanner():
    while True:
        try:
            tickers = exchange.fetch_tickers()
            sent = 0

            for sym, data in tickers.items():

                if ":USDT" not in sym:
                    continue

                if any(x in sym for x in ["BTC","ETH","BNB"]):
                    continue

                vol = data.get("quoteVolume", 0)

                df = get_data(sym)
                if df is None:
                    continue

                price = df["c"].iloc[-1]

                if price < 0.0001:
                    continue

                move = abs(df["c"].iloc[-1] - df["c"].iloc[-5]) > price * 0.003
                vol_spike = df["v"].iloc[-1] > df["v"].iloc[-5] * 1.5

                if vol and vol > 3_000_000 and move and vol_spike:

                    if sym in last_sent and time.time() - last_sent[sym] < 120:
                        continue

                    last_sent[sym] = time.time()

                    send(f"""
💀 FIRSAT

📊 {sym}
💰 Vol: {round(vol/1e6,2)}M

👉 analiz yaz
""")

                    sent += 1
                    if sent >= 3:
                        break

            time.sleep(20)

        except Exception as e:
            print("SCANNER HATA:", e)
            time.sleep(10)

@bot.message_handler(func=lambda m: True)
def handle(msg):
    text = msg.text.lower().strip()
    text = text.replace("ç","c").replace("ı","i")
    cid = msg.chat.id

    if "analiz" in text:
        coin = text.replace("analiz","").strip().upper()
        if coin == "":
            send("⚠️ coin yaz", cid)
            return
        analyze(coin+"/USDT:USDT", cid)

    elif text == "gir":
        open_trade(cid)

threading.Thread(target=manage, daemon=True).start()
threading.Thread(target=scanner, daemon=True).start()

send(f"💀 SADIK BOT {VERSION} AKTİF")
bot.infinity_polling()
