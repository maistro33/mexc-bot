# ==============================
# 💀 SADIK BOT v17 FINAL AI SYSTEM
# ==============================

import os, time, ccxt, telebot, threading, requests
import pandas as pd
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

VERSION = "v17 FINAL AI"

TOKEN = os.getenv("TELE_TOKEN")
CHAT_ID = os.getenv("MY_CHAT_ID")

SUPA_URL = os.getenv("SUPABASE_URL")
SUPA_KEY = os.getenv("SUPABASE_KEY")

bot = telebot.TeleBot(TOKEN)

exchange = ccxt.bitget({
    "apiKey": os.getenv("BITGET_API"),
    "secret": os.getenv("BITGET_SEC"),
    "password": os.getenv("BITGET_PASS"),
    "options": {"defaultType": "swap"},
    "enableRateLimit": True
})

positions = []
signal_cache = {}

panel_message_id = None
panel_chat_id = None

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
def ai_strength(df):
    price = df["c"].iloc[-1]
    ema = df["ema"].iloc[-1]
    momentum = abs(df["c"].iloc[-1] - df["c"].iloc[-5])
    volume = df["v"].iloc[-1] / df["v"].iloc[-5]

    score = 0
    if price > ema:
        score += 40
    if momentum > price * 0.002:
        score += 30
    if volume > 1.2:
        score += 30

    return min(score,100)

# ==============================
def ai_learn():
    try:
        headers = {"apikey": SUPA_KEY,"Authorization": f"Bearer {SUPA_KEY}"}
        r = requests.get(f"{SUPA_URL}/rest/v1/trades?select=*",
                         headers=headers)
        data = r.json()

        if not data:
            return 60

        good = [x for x in data if x["result"] > 0]
        bad = [x for x in data if x["result"] <= 0]

        avg_good = sum(x["strength"] for x in good)/len(good) if good else 70
        avg_bad = sum(x["strength"] for x in bad)/len(bad) if bad else 40

        return (avg_good + avg_bad)/2

    except:
        return 60

# ==============================
def save_trade(sym, pnl, strength):
    try:
        headers = {
            "apikey": SUPA_KEY,
            "Authorization": f"Bearer {SUPA_KEY}",
            "Content-Type": "application/json"
        }
        requests.post(
            f"{SUPA_URL}/rest/v1/trades",
            headers=headers,
            json={
                "symbol": sym,
                "result": pnl,
                "strength": strength
            }
        )
    except:
        pass

# ==============================
def is_recovery(df):
    price = df["c"].iloc[-1]
    ema = df["ema"].iloc[-1]
    momentum = df["c"].iloc[-1] - df["c"].iloc[-3]
    return price > ema and momentum > 0

# ==============================
def scanner():
    while True:
        try:
            threshold = ai_learn()
            tickers = exchange.fetch_tickers()

            for sym in tickers:

                if ":USDT" not in sym:
                    continue

                df = get_data(sym)
                if df is None:
                    continue

                strength = ai_strength(df)

                if strength < threshold:
                    continue

                price = df["c"].iloc[-1]
                ema = df["ema"].iloc[-1]

                trend = "UP" if price > ema else "DOWN"
                signal = "LONG" if trend=="UP" else "SHORT"

                tp1 = price * 1.01
                tp2 = price * 1.02
                tp3 = price * 1.03
                sl = price * 0.98

                safe = sym.replace("/","").replace(":","")

                signal_cache[safe] = {
                    "id": safe,
                    "sym": sym,
                    "signal": signal,
                    "entry": price,
                    "tp1": tp1,
                    "tp2": tp2,
                    "tp3": tp3,
                    "sl": sl,
                    "strength": strength
                }

                markup = InlineKeyboardMarkup()
                markup.add(
                    InlineKeyboardButton("✅ GİR",
                    callback_data=f"enter|{safe}")
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

🤖 Güç: %{strength}
""")

                bot.send_message(CHAT_ID,"GİR:",reply_markup=markup)
                time.sleep(2)

            time.sleep(15)

        except:
            time.sleep(5)

# ==============================
def open_trade(data, cid):
    positions.append({
        **data,
        "remaining":1.0,
        "tp1_done":False,
        "tp2_done":False,
        "ai_last_state":"STRONG",
        "awaiting_decision":False,
        "timer":0,
        "chat":cid
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

            df = get_data(p["sym"])
            if df is None:
                continue

            strength = ai_strength(df)

            # STATE
            if strength >= 70:
                state="STRONG"
            elif strength >=40:
                state="RISKY"
            else:
                state="EXIT"

            if state != p["ai_last_state"]:
                p["ai_last_state"]=state

                if state=="RISKY":
                    send(f"⚠️ Zayıflıyor {p['sym']} %{strength}",p["chat"])

                elif state=="EXIT":
                    p["awaiting_decision"]=True
                    p["timer"]=time.time()

                    markup=InlineKeyboardMarkup()
                    markup.row(
                        InlineKeyboardButton("🟢 DEVAM",
                        callback_data=f"keep_{p['id']}"),
                        InlineKeyboardButton("⛔ ÇIK",
                        callback_data=f"exit_{p['id']}")
                    )

                    bot.send_message(p["chat"],f"""
⛔ AI KRİTİK

{p['sym']}
Güç %{strength}

Çıkalım mı?
⏳ 30 sn
""",reply_markup=markup)

            # SMART WAIT
            if p["awaiting_decision"]:
                if is_recovery(df):
                    p["awaiting_decision"]=False
                    send(f"🟢 DÜZELTME {p['sym']}",p["chat"])
                elif time.time()-p["timer"]>30:
                    send(f"⛔ EXIT {p['sym']}",p["chat"])
                    pnl=0
                    save_trade(p["sym"],pnl,p["strength"])
                    positions.remove(p)
                    continue

            # TP
            pnl=((price-p["entry"])/p["entry"])*50*p["remaining"]

            if not p["tp1_done"] and price>=p["tp1"]:
                p["tp1_done"]=True
                p["remaining"]-=0.5
                send(f"🎯 TP1 {p['sym']} +{round(pnl,2)}")

            elif not p["tp2_done"] and price>=p["tp2"]:
                p["tp2_done"]=True
                p["remaining"]-=0.25
                send(f"🎯 TP2 {p['sym']} +{round(pnl,2)}")

            elif price>=p["tp3"]:
                send(f"🚀 TP3 {p['sym']} +{round(pnl,2)}")
                save_trade(p["sym"],pnl,p["strength"])
                positions.remove(p)
                continue

        time.sleep(5)

# ==============================
@bot.callback_query_handler(func=lambda call: True)
def callback(call):

    cid=call.message.chat.id

    if call.data.startswith("enter|"):
        data=signal_cache.get(call.data.split("|")[1])
        if data:
            open_trade(data,cid)

    elif call.data.startswith("exit_"):
        pid=call.data.split("_")[1]
        for p in positions:
            if p["id"]==pid:
                send(f"⛔ EXIT {p['sym']}",cid)
                positions.remove(p)
                break

    elif call.data.startswith("keep_"):
        send("🟢 DEVAM",cid)

# ==============================
threading.Thread(target=scanner,daemon=True).start()
threading.Thread(target=manage,daemon=True).start()

send(f"💀 BOT {VERSION} AKTİF")
bot.infinity_polling()
