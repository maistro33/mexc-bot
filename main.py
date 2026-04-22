# ==============================
# 💀 SADIK BOT v12 FINAL PRO
# ==============================

import os, time, ccxt, telebot, threading, requests
import pandas as pd
from openai import OpenAI
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

VERSION = "v12 FINAL PRO"

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
event_log = []

# ==============================
def send(msg, cid=None):
    try:
        bot.send_message(cid or CHAT_ID, msg)
    except Exception as e:
        print("SEND:", e)

def log_event(text):
    event_log.append(f"{time.strftime('%H:%M:%S')} - {text}")
    if len(event_log) > 30:
        event_log.pop(0)

# ==============================
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
    except Exception as e:
        print("SUPABASE:", e)

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

            for sym, data in tickers.items():

                if ":USDT" not in sym:
                    continue
                if any(x in sym for x in ["BTC","ETH","BNB"]):
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

                tp1 = price * 1.01 if signal=="LONG" else price * 0.99
                tp2 = price * 1.02 if signal=="LONG" else price * 0.98
                tp3 = price * 1.03 if signal=="LONG" else price * 0.97
                sl = price * 0.98 if signal=="LONG" else price * 1.02

                safe = sym.replace("/","").replace(":","")

                signal_cache[safe] = {
                    "id": safe,
                    "sym": sym,
                    "signal": signal,
                    "entry": price,
                    "tp1": tp1,
                    "tp2": tp2,
                    "tp3": tp3,
                    "sl": sl
                }

                markup = InlineKeyboardMarkup()
                markup.add(InlineKeyboardButton("✅ GİR", callback_data=f"enter|{safe}"))

                send(f"""
💀 AKILLI SİNYAL

📊 {sym}
📈 {signal}
💰 {round(price,4)}

🎯 TP1: {round(tp1,4)}
🎯 TP2: {round(tp2,4)}
🎯 TP3: {round(tp3,4)}
🛑 SL: {round(sl,4)}
""")

                bot.send_message(CHAT_ID, "GİR:", reply_markup=markup)
                time.sleep(2)

            time.sleep(15)

        except Exception as e:
            print("SCANNER:", e)
            time.sleep(5)

# ==============================
def open_trade(data, cid):
    positions.append({
        **data,
        "tp1_done": False,
        "tp2_done": False,
        "chat": cid,
        "ai_status": "HOLD",
        "awaiting_decision": False,
        "exit_timer": 0,
        "remaining": 1.0
    })

    log_event(f"OPEN {data['sym']}")
    send(f"🚀 TRADE AÇILDI {data['sym']}", cid)

# ==============================
def manage():
    while True:
        for p in positions[:]:
            try:
                price = exchange.fetch_ticker(p["sym"])["last"]
            except:
                continue

            # USDT PnL
            pnl_percent = ((price - p["entry"]) / p["entry"]) if p["signal"]=="LONG" else ((p["entry"] - price) / p["entry"])
            pnl_usdt = round(pnl_percent * 50 * p["remaining"], 2)

            df = get_data(p["sym"])
            if df is None:
                continue

            ema = df["ema"].iloc[-1]
            trend = "UP" if price > ema else "DOWN"

            # AI
            p["ai_status"] = "HOLD" if trend == "UP" else "EXIT"

            # AI EXIT UYARI
            if p["ai_status"] == "EXIT" and not p["awaiting_decision"]:
                p["awaiting_decision"] = True
                p["exit_timer"] = time.time()

                markup = InlineKeyboardMarkup()
                markup.row(
                    InlineKeyboardButton("🟢 DEVAM", callback_data=f"keep_{p['id']}"),
                    InlineKeyboardButton("⛔ EXIT", callback_data=f"exit_{p['id']}")
                )

                bot.send_message(p["chat"], f"""
🤖 AI UYARI

📊 {p['sym']}
Trend: DOWN
Karar: EXIT

⏳ 30 sn içinde karar ver
""", reply_markup=markup)

            # SMART WAIT
            if p["awaiting_decision"]:
                if trend == "UP":
                    p["awaiting_decision"] = False
                    send(f"🟢 DÜZELTME {p['sym']}", p["chat"])

                elif time.time() - p["exit_timer"] > 30:
                    send(f"⛔ AUTO EXIT {p['sym']} ({pnl_usdt} USDT)", p["chat"])
                    save_trade(p["sym"], pnl_usdt)
                    positions.remove(p)
                    continue

            # TP SYSTEM
            if p["signal"]=="LONG":

                if not p["tp1_done"] and price >= p["tp1"]:
                    p["tp1_done"] = True
                    p["remaining"] -= 0.5
                    send(f"🎯 TP1 {p['sym']} +{pnl_usdt} USDT")

                    p["sl"] = p["entry"]

                elif not p["tp2_done"] and price >= p["tp2"]:
                    p["tp2_done"] = True
                    p["remaining"] -= 0.25
                    send(f"🎯 TP2 {p['sym']} +{pnl_usdt} USDT")

                elif price >= p["tp3"]:
                    send(f"🚀 TP3 {p['sym']} +{pnl_usdt} USDT")
                    save_trade(p["sym"], pnl_usdt)
                    positions.remove(p)
                    continue

                if price <= p["sl"]:
                    send(f"🛑 STOP {p['sym']} {pnl_usdt} USDT")
                    save_trade(p["sym"], pnl_usdt)
                    positions.remove(p)
                    continue

        time.sleep(5)

# ==============================
@bot.message_handler(commands=['panel'])
def panel(msg):

    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("📊 Durum", callback_data="panel_status"),
        InlineKeyboardButton("📈 Trades", callback_data="panel_trades")
    )
    markup.row(
        InlineKeyboardButton("📡 Log", callback_data="panel_log")
    )

    bot.send_message(msg.chat.id, "💀 PRO PANEL", reply_markup=markup)

# ==============================
@bot.callback_query_handler(func=lambda call: True)
def callback(call):
    cid = call.message.chat.id

    if call.data.startswith("enter|"):
        data = signal_cache.get(call.data.split("|")[1])
        if data:
            open_trade(data, cid)

    elif call.data == "panel_status":
        send(f"📊 Açık işlem: {len(positions)}", cid)

    elif call.data == "panel_trades":

        if not positions:
            send("Açık işlem yok", cid)
            return

        for p in positions:

            try:
                price = exchange.fetch_ticker(p["sym"])["last"]
            except:
                continue

            pnl_percent = ((price - p["entry"]) / p["entry"]) if p["signal"]=="LONG" else ((p["entry"] - price) / p["entry"])
            pnl_usdt = round(pnl_percent * 50 * p["remaining"], 2)

            markup = InlineKeyboardMarkup()
            markup.row(
                InlineKeyboardButton("🟢 DEVAM", callback_data=f"keep_{p['id']}"),
                InlineKeyboardButton("⛔ EXIT", callback_data=f"exit_{p['id']}")
            )

            send(f"""
📊 {p['sym']}

💰 Entry: {round(p['entry'],4)}
📈 Fiyat: {round(price,4)}

💵 PnL: {pnl_usdt} USDT
📦 Kalan: %{int(p['remaining']*100)}

🤖 AI: {p['ai_status']}

TP1: {'✅' if p['tp1_done'] else '⏳'}
TP2: {'✅' if p['tp2_done'] else '⏳'}
""", cid)

            bot.send_message(cid, "Seç:", reply_markup=markup)

    elif call.data.startswith("keep_"):
        pid = call.data.split("_")[1]
        for p in positions:
            if p["id"] == pid:
                p["awaiting_decision"] = False
                send(f"🟢 DEVAM {p['sym']}", cid)

    elif call.data.startswith("exit_"):
        pid = call.data.split("_")[1]
        for p in positions:
            if p["id"] == pid:
                price = exchange.fetch_ticker(p["sym"])["last"]
                pnl_percent = ((price - p["entry"]) / p["entry"]) if p["signal"]=="LONG" else ((p["entry"] - price) / p["entry"])
                pnl_usdt = round(pnl_percent * 50 * p["remaining"], 2)

                send(f"⛔ EXIT {p['sym']} → {pnl_usdt} USDT", cid)
                save_trade(p["sym"], pnl_usdt)
                positions.remove(p)
                break

    elif call.data == "panel_log":
        send("\n".join(event_log[-10:]) if event_log else "Log boş", cid)

# ==============================
threading.Thread(target=scanner, daemon=True).start()
threading.Thread(target=manage, daemon=True).start()

send(f"💀 BOT {VERSION} AKTIF")
bot.infinity_polling()
