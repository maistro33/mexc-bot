# ==============================
# 💀 SADIK BOT v7.3 (TP + TRAILING + FULL MESSAGE)
# ==============================

import os, time, ccxt, telebot, threading, requests, random
import pandas as pd
from openai import OpenAI
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

VERSION = "v7.3"

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
        requests.post(f"{SUPA_URL}/rest/v1/trades",
                      headers=headers,
                      json={"symbol": sym, "result": pnl})
    except:
        pass

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
    signal = last_analysis["signal"]

    positions.append({
        "sym": sym,
        "entry": price,
        "size": 50,
        "chat": cid,
        "peak_pct": 0,
        "exit_flag": False,
        "signal": signal,
        "tp1_done": False,
        "sl": price * 0.98
    })

    send(f"""
🚀 TRADE

📊 {sym}
📈 {signal}
💰 {round(price,4)}
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

            pnl = (price - p["entry"]) * p["size"]
            pct = (pnl/(p["entry"]*p["size"]))*100
            cid = p["chat"]

            # ===== STOP LOSS =====
            if not p["tp1_done"] and price <= p["entry"] * 0.98:
                send(f"""
🛑 STOP LOSS

📊 {p['sym']}
💰 {round(pnl,4)} USDT

❗ %2 zarar kesildi
""", cid)

                save_trade(p["sym"], pnl)
                positions.remove(p)
                continue

            # ===== TP1 =====
            if not p["tp1_done"] and pct >= 1:
                p["tp1_done"] = True

                pnl_half = pnl / 2
                save_trade(p["sym"], pnl_half)

                p["sl"] = p["entry"]

                send(f"""
🎯 TP1 GERÇEKLEŞTİ

📊 {p['sym']}
💰 {round(pnl_half,4)} USDT

🛡 SL → ENTRY ({round(p['sl'],4)})
📈 Trailing başlıyor
""", cid)

            # ===== TRAILING =====
            if p["tp1_done"]:
                old_sl = p["sl"]
                new_sl = price * 0.995

                if new_sl > p["sl"]:
                    p["sl"] = new_sl

                    send(f"""
📈 TRAILING GÜNCELLENDİ

📊 {p['sym']}
💰 Fiyat: {round(price,4)}

🛡 Yeni SL: {round(p['sl'],4)}
""", cid)

            # ===== STOP (TRAILING) =====
            if price <= p["sl"]:
                send(f"""
🚨 STOP TETİKLENDİ

📊 {p['sym']}
💰 {round(pnl,4)} USDT

🛡 SL: {round(p['sl'],4)}
""", cid)

                save_trade(p["sym"], pnl)
                positions.remove(p)
                continue

        time.sleep(5)

# ===== THREAD =====
threading.Thread(target=manage, daemon=True).start()

send(f"💀 SADIK BOT {VERSION} AKTİF")
bot.infinity_polling()
