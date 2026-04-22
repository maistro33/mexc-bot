# ==============================
# 💀 SADIK BOT v8.6 PRO MULTI TP
# ==============================

import os, time, ccxt, telebot, threading, requests
import pandas as pd
from openai import OpenAI
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

VERSION = "v8.6 PRO MULTI TP"

TOKEN = os.getenv("TELE_TOKEN")
CHAT_ID = os.getenv("MY_CHAT_ID")
OPENAI_KEY = os.getenv("OPENAI_API_KEY")

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

# ==============================
def send(msg, cid=None):
    try:
        bot.send_message(cid or CHAT_ID, msg)
    except:
        pass

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
# SCANNER + AI SIGNAL
# ==============================
def scanner():
    while True:
        try:
            tickers = exchange.fetch_tickers()

            for sym, data in tickers.items():
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

                if move and vol_spike:

                    signal = "LONG" if trend=="UP" else "SHORT"

                    tp1 = price * 1.01 if signal=="LONG" else price * 0.99
                    tp2 = price * 1.02 if signal=="LONG" else price * 0.98
                    tp3 = price * 1.03 if signal=="LONG" else price * 0.97
                    sl = price * 0.98 if signal=="LONG" else price * 1.02

                    markup = InlineKeyboardMarkup()
                    markup.add(
                        InlineKeyboardButton("✅ GİR", callback_data=f"enter_{sym}_{signal}_{price}_{tp1}_{tp2}_{tp3}_{sl}")
                    )

                    bot.send_message(CHAT_ID, f"""
💀 AKILLI SİNYAL

📊 {sym}
📈 {signal}
💰 {round(price,4)}

🎯 TP1: {round(tp1,4)}
🎯 TP2: {round(tp2,4)}
🎯 TP3: {round(tp3,4)}
🛑 SL: {round(sl,4)}
""", reply_markup=markup)

                    time.sleep(5)

            time.sleep(20)

        except Exception as e:
            print("SCANNER:", e)
            time.sleep(10)

# ==============================
# OPEN TRADE
# ==============================
def open_trade(sym, signal, price, tp1, tp2, tp3, sl, cid):

    positions.append({
        "sym": sym,
        "entry": float(price),
        "signal": signal,
        "tp1": float(tp1),
        "tp2": float(tp2),
        "tp3": float(tp3),
        "sl": float(sl),
        "tp1_done": False,
        "tp2_done": False,
        "chat": cid
    })

    send(f"🚀 TRADE AÇILDI {sym} {signal}", cid)

# ==============================
# MANAGE (MULTI TP)
# ==============================
def manage():
    while True:
        for p in positions[:]:
            try:
                price = exchange.fetch_ticker(p["sym"])["last"]
            except:
                continue

            # LONG
            if p["signal"]=="LONG":

                # TP1
                if not p["tp1_done"] and price >= p["tp1"]:
                    p["tp1_done"] = True
                    p["sl"] = p["entry"]
                    send(f"🎯 TP1 HIT {p['sym']} → SL ENTRY")

                # TP2
                elif not p["tp2_done"] and price >= p["tp2"]:
                    p["tp2_done"] = True
                    send(f"🎯 TP2 HIT {p['sym']}")

                # TP3
                elif price >= p["tp3"]:
                    send(f"🚀 TP3 FULL CLOSE {p['sym']}")
                    positions.remove(p)
                    continue

                # TRAILING
                new_sl = price * 0.995
                if new_sl > p["sl"]:
                    p["sl"] = new_sl

                if price <= p["sl"]:
                    send(f"🛑 STOP {p['sym']}")
                    positions.remove(p)
                    continue

            # SHORT
            else:

                if not p["tp1_done"] and price <= p["tp1"]:
                    p["tp1_done"] = True
                    p["sl"] = p["entry"]
                    send(f"🎯 TP1 HIT {p['sym']} → SL ENTRY")

                elif not p["tp2_done"] and price <= p["tp2"]:
                    p["tp2_done"] = True
                    send(f"🎯 TP2 HIT {p['sym']}")

                elif price <= p["tp3"]:
                    send(f"🚀 TP3 FULL CLOSE {p['sym']}")
                    positions.remove(p)
                    continue

                new_sl = price * 1.005
                if new_sl < p["sl"]:
                    p["sl"] = new_sl

                if price >= p["sl"]:
                    send(f"🛑 STOP {p['sym']}")
                    positions.remove(p)
                    continue

        time.sleep(5)

# ==============================
# CALLBACK
# ==============================
@bot.callback_query_handler(func=lambda call: True)
def callback(call):
    cid = call.message.chat.id

    if call.data.startswith("enter_"):
        _, sym, signal, price, tp1, tp2, tp3, sl = call.data.split("_")
        open_trade(sym, signal, price, tp1, tp2, tp3, sl, cid)

# ==============================
threading.Thread(target=scanner, daemon=True).start()
threading.Thread(target=manage, daemon=True).start()

send(f"💀 BOT {VERSION} AKTIF")
bot.infinity_polling()
