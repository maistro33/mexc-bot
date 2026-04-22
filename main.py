# ==============================
# 💀 SADIK BOT v14 PRO PANEL
# ==============================

import os, time, ccxt, telebot, threading, requests
import pandas as pd
from openai import OpenAI
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

VERSION = "v14 PRO PANEL"

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
signal_cache = []
event_log = []

# ==============================
def send(msg, cid=None):
    try:
        bot.send_message(cid or CHAT_ID, msg)
    except Exception as e:
        print(e)

# ==============================
def get_data(sym):
    try:
        ohlcv = exchange.fetch_ohlcv(sym, "1m", limit=50)
        df = pd.DataFrame(ohlcv, columns=["t","o","h","l","c","v"])
        df["ema"] = df["c"].ewm(20).mean()
        return df
    except:
        return None

# ==============================
def market_status():
    try:
        df = get_data("BTC/USDT:USDT")
        price = df["c"].iloc[-1]
        ema = df["ema"].iloc[-1]

        if price > ema:
            return "🟢 BULLISH"
        else:
            return "🔴 BEARISH"
    except:
        return "UNKNOWN"

# ==============================
def scanner():
    while True:
        try:
            tickers = exchange.fetch_tickers()

            for sym in tickers:

                if ":USDT" not in sym:
                    continue

                df = get_data(sym)
                if df is None:
                    continue

                price = df["c"].iloc[-1]
                ema = df["ema"].iloc[-1]

                trend = "UP" if price > ema else "DOWN"

                move = abs(df["c"].iloc[-1] - df["c"].iloc[-5]) > price * 0.003
                vol_spike = df["v"].iloc[-1] > df["v"].iloc[-5] * 1.5

                if not (move and vol_spike):
                    continue

                signal = "LONG" if trend=="UP" else "SHORT"

                tp1 = price * 1.01
                tp2 = price * 1.02
                tp3 = price * 1.03
                sl = price * 0.98

                safe = sym.replace("/","").replace(":","")

                signal_cache.append({
                    "id": safe,
                    "sym": sym,
                    "signal": signal,
                    "entry": price,
                    "tp1": tp1,
                    "tp2": tp2,
                    "tp3": tp3,
                    "sl": sl
                })

        except:
            time.sleep(5)

# ==============================
def open_trade(data, cid):
    positions.append({
        **data,
        "remaining": 1.0,
        "ai_status": "HOLD"
    })
    send(f"🚀 {data['sym']} açıldı", cid)

# ==============================
def manage():
    while True:
        for p in positions[:]:
            try:
                price = exchange.fetch_ticker(p["sym"])["last"]
            except:
                continue

            pnl = ((price - p["entry"]) / p["entry"]) * 50 * p["remaining"]
            pnl = round(pnl,2)

            df = get_data(p["sym"])
            if df is None:
                continue

            ema = df["ema"].iloc[-1]
            trend = "UP" if price > ema else "DOWN"

            p["ai_status"] = "HOLD" if trend=="UP" else "EXIT"

            if p["ai_status"] == "EXIT":
                send(f"⚠️ AI EXIT {p['sym']}", p["chat"])

        time.sleep(5)

# ==============================
@bot.message_handler(commands=['panel'])
def panel(msg):

    cid = msg.chat.id

    total_profit = 0
    total_loss = 0

    try:
        headers = {
            "apikey": SUPA_KEY,
            "Authorization": f"Bearer {SUPA_KEY}"
        }

        r = requests.get(f"{SUPA_URL}/rest/v1/trades?select=*",
                         headers=headers)

        data = r.json()

        for t in data:
            if t["result"] > 0:
                total_profit += t["result"]
            else:
                total_loss += t["result"]

    except:
        pass

    net = total_profit + total_loss

    text = f"""
💀 SADIK PRO PANEL

💰 Kâr: {round(total_profit,2)}
📉 Zarar: {round(total_loss,2)}
📊 Net: {round(net,2)}

🤖 AI: AKTİF
🌍 Market: {market_status()}

━━━━━━━━━━━━━━
"""

    markup = InlineKeyboardMarkup()

    if not positions:
        text += "\n❗ Açık işlem yok\n"

    else:
        for p in positions:

            price = exchange.fetch_ticker(p["sym"])["last"]
            pnl = ((price - p["entry"]) / p["entry"]) * 50 * p["remaining"]
            pnl = round(pnl,2)

            text += f"\n{p['sym']} → {pnl} USDT | {p['ai_status']}\n"

            markup.row(
                InlineKeyboardButton("🟢 DEVAM", callback_data=f"keep_{p['id']}"),
                InlineKeyboardButton("⛔ KAPAT", callback_data=f"exit_{p['id']}")
            )

    bot.send_message(cid, text, reply_markup=markup)

# ==============================
@bot.callback_query_handler(func=lambda call: True)
def callback(call):

    cid = call.message.chat.id

    if call.data.startswith("exit_"):
        pid = call.data.split("_")[1]

        for p in positions:
            if p["id"] == pid:
                price = exchange.fetch_ticker(p["sym"])["last"]
                pnl = ((price - p["entry"]) / p["entry"]) * 50
                pnl = round(pnl,2)

                send(f"⛔ {p['sym']} kapatıldı {pnl} USDT", cid)
                positions.remove(p)
                break

    elif call.data.startswith("keep_"):
        send("🟢 DEVAM", cid)

# ==============================
threading.Thread(target=scanner, daemon=True).start()
threading.Thread(target=manage, daemon=True).start()

send(f"💀 BOT {VERSION} AKTİF")
bot.infinity_polling()
