# ==============================
# 💀 SADIK BOT v8.7 FINAL
# ==============================

import os, time, ccxt, telebot, threading, requests
import pandas as pd
from openai import OpenAI
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

VERSION = "v8.7 FINAL AI"

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
signal_cache = {}

# ==============================
def send(msg, cid=None):
    try:
        bot.send_message(cid or CHAT_ID, msg)
    except Exception as e:
        print("SEND:", e)

# ==============================
def save_trade(sym, pnl):
    try:
        headers = {
            "apikey": SUPA_KEY,
            "Authorization": f"Bearer {SUPA_KEY}",
            "Content-Type": "application/json"
        }

        requests.post(
            f"{SUPA_URL}/rest/v1/trades",
            headers=headers,
            json={"symbol": sym, "result": pnl}
        )

    except Exception as e:
        print("SUPABASE:", e)

# ==============================
def load_history():
    try:
        headers = {
            "apikey": SUPA_KEY,
            "Authorization": f"Bearer {SUPA_KEY}"
        }

        r = requests.get(
            f"{SUPA_URL}/rest/v1/trades?select=*",
            headers=headers
        )

        data = r.json()

        wins = [x for x in data if x["result"] > 0]
        losses = [x for x in data if x["result"] <= 0]

        return wins, losses

    except:
        return [], []

# ==============================
def ai_memory(sym):
    wins, losses = load_history()

    sym_w = [x for x in wins if x["symbol"] == sym]
    sym_l = [x for x in losses if x["symbol"] == sym]

    total = len(sym_w) + len(sym_l)

    if total < 5:
        return True

    winrate = len(sym_w) / total

    return winrate > 0.4

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

                if not ai_memory(sym):
                    continue

                trend = "UP" if price > ema else "DOWN"

                move = abs(df["c"].iloc[-1] - df["c"].iloc[-5]) > price * 0.003
                vol_spike = df["v"].iloc[-1] > df["v"].iloc[-5] * 1.5

                if move and vol_spike:

                    signal = "LONG" if trend=="UP" else "SHORT"

                    tp1 = price * 1.01 if signal=="LONG" else price * 0.99
                    tp2 = price * 1.02 if signal=="LONG" else price * 0.98
                    tp3 = price * 1.03 if signal=="LONG" else price * 0.97
                    sl = price * 0.98 if signal=="LONG" else price * 1.02

                    safe = sym.replace("/","").replace(":","")

                    signal_cache[safe] = {
                        "sym": sym,
                        "signal": signal,
                        "price": price,
                        "tp1": tp1,
                        "tp2": tp2,
                        "tp3": tp3,
                        "sl": sl
                    }

                    markup = InlineKeyboardMarkup()
                    markup.add(
                        InlineKeyboardButton(
                            "✅ GİR",
                            callback_data=f"enter|{safe}"
                        )
                    )

                    send(f"""
💀 AKILLI SİNYAL

📊 {sym}
📈 {signal}
💰 {round(price,4)}

🎯 TP1: {round(tp1,4)}
🎯 TP2: {round(tp2,4)}
🎯 TP3: {round(tp3,4)}
🛑 SL: {round(sl,4)}
""", CHAT_ID)

                    bot.send_message(CHAT_ID, "Trade aç?", reply_markup=markup)

                    time.sleep(5)

            time.sleep(20)

        except Exception as e:
            print("SCANNER:", e)
            time.sleep(10)

# ==============================
def open_trade(data, cid):
    positions.append({
        **data,
        "tp1_done": False,
        "tp2_done": False,
        "chat": cid
    })

    send(f"🚀 TRADE AÇILDI {data['sym']}", cid)

# ==============================
def manage():
    while True:
        for p in positions[:]:
            try:
                price = exchange.fetch_ticker(p["sym"])["last"]
            except:
                continue

            pnl = (price - p["entry"]) if p["signal"]=="LONG" else (p["entry"]-price)

            if p["signal"]=="LONG":

                if not p["tp1_done"] and price >= p["tp1"]:
                    p["tp1_done"] = True
                    p["sl"] = p["entry"]
                    send(f"🎯 TP1 {p['sym']}")

                elif not p["tp2_done"] and price >= p["tp2"]:
                    p["tp2_done"] = True
                    send(f"🎯 TP2 {p['sym']}")

                elif price >= p["tp3"]:
                    send(f"🚀 TP3 {p['sym']}")
                    save_trade(p["sym"], pnl)
                    positions.remove(p)
                    continue

                if price <= p["sl"]:
                    send(f"🛑 STOP {p['sym']}")
                    save_trade(p["sym"], pnl)
                    positions.remove(p)
                    continue

            else:

                if not p["tp1_done"] and price <= p["tp1"]:
                    p["tp1_done"] = True
                    p["sl"] = p["entry"]

                elif not p["tp2_done"] and price <= p["tp2"]:
                    p["tp2_done"] = True

                elif price <= p["tp3"]:
                    save_trade(p["sym"], pnl)
                    positions.remove(p)
                    continue

                if price >= p["sl"]:
                    save_trade(p["sym"], pnl)
                    positions.remove(p)
                    continue

        time.sleep(5)

# ==============================
@bot.callback_query_handler(func=lambda call: True)
def callback(call):
    cid = call.message.chat.id

    if call.data.startswith("enter|"):
        safe = call.data.split("|")[1]

        data = signal_cache.get(safe)

        if not data:
            send("veri yok", cid)
            return

        open_trade(data, cid)

# ==============================
threading.Thread(target=scanner, daemon=True).start()
threading.Thread(target=manage, daemon=True).start()

send(f"💀 BOT {VERSION} AKTIF")
bot.infinity_polling()
