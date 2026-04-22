# ==============================
# 💀 SADIK BOT v10 SMART EXIT
# ==============================

import os, time, ccxt, telebot, threading, requests
import pandas as pd
from openai import OpenAI
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

VERSION = "v10 SMART EXIT"

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

# ==============================
def log_event(text):
    event_log.append(f"{time.strftime('%H:%M:%S')} - {text}")
    if len(event_log) > 20:
        event_log.pop(0)

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
    try:
        wins, losses = load_history()
        sym_w = [x for x in wins if x["symbol"] == sym]
        sym_l = [x for x in losses if x["symbol"] == sym]
        total = len(sym_w) + len(sym_l)
        if total < 5:
            return True
        winrate = len(sym_w) / total
        return winrate > 0.4
    except:
        return True

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
                try:
                    if not sym or not isinstance(sym, str):
                        continue
                    if ":USDT" not in sym:
                        continue
                    if any(x in sym for x in ["BTC","ETH","BNB"]):
                        continue
                    if data is None:
                        continue
                    if "quoteVolume" not in data:
                        continue
                except:
                    continue

                df = get_data(sym)
                if df is None:
                    continue

                if not ai_memory(sym):
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
                    "sym": sym,
                    "signal": signal,
                    "entry": price,
                    "tp1": tp1,
                    "tp2": tp2,
                    "tp3": tp3,
                    "sl": sl
                }

                markup = InlineKeyboardMarkup()
                markup.add(
                    InlineKeyboardButton("✅ GİR", callback_data=f"enter|{safe}")
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

                time.sleep(3)

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
        "chat": cid,
        "ai_status": "HOLD",
        "last_ai_report": 0,
        "awaiting_decision": False,
        "exit_timer": 0
    })
    log_event(f"OPEN {data['sym']}")
    send(f"🚀 TRADE AÇILDI {data['sym']}", cid)

# ==============================
def manage():
    while True:
        for p in positions[:]:
            try:
                ticker = exchange.fetch_ticker(p["sym"])
                price = ticker["last"]
            except:
                continue

            pnl = (price - p["entry"]) if p["signal"]=="LONG" else (p["entry"]-price)

            # ======================
            # 🤖 AI EXIT TRIGGER
            df = get_data(p["sym"])
            if df is not None:
                ema = df["ema"].iloc[-1]
                trend = "UP" if price > ema else "DOWN"

                if trend == "DOWN" and p["signal"] == "LONG":
                    if not p["awaiting_decision"]:
                        p["awaiting_decision"] = True
                        p["exit_timer"] = time.time()

                        markup = InlineKeyboardMarkup()
                        markup.row(
                            InlineKeyboardButton("🟢 DEVAM", callback_data=f"keep_{p['sym']}"),
                            InlineKeyboardButton("⛔ ÇIK", callback_data=f"exit_{p['sym']}")
                        )

                        send(f"""
🤖 AI UYARI

📊 {p['sym']}
Trend: DOWN
Karar: EXIT

⏳ 30 saniye içinde karar ver
""", p["chat"])

                        bot.send_message(p["chat"], "Seç:", reply_markup=markup)

            # ======================
            # 🧠 SMART WAIT
            if p["awaiting_decision"]:

                df = get_data(p["sym"])
                if df is not None:
                    ema = df["ema"].iloc[-1]
                    price = df["c"].iloc[-1]
                    trend = "UP" if price > ema else "DOWN"

                    if trend == "UP":
                        p["awaiting_decision"] = False
                        send(f"🟢 DÜZELTME - DEVAM {p['sym']}")
                        continue

                if time.time() - p["exit_timer"] > 30:
                    send(f"⛔ CONFIRMED EXIT {p['sym']}")
                    save_trade(p["sym"], pnl)
                    positions.remove(p)
                    continue

            # ======================
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

                new_sl = price * 0.995
                if new_sl > p["sl"]:
                    p["sl"] = new_sl

                if price <= p["sl"]:
                    send(f"🛑 STOP {p['sym']}")
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
        if data:
            open_trade(data, cid)

    elif call.data.startswith("keep_"):
        sym = call.data.split("_")[1]
        for p in positions:
            if p["sym"] == sym:
                p["awaiting_decision"] = False
                send(f"🟢 DEVAM {sym}", cid)

    elif call.data.startswith("exit_"):
        sym = call.data.split("_")[1]
        for p in positions:
            if p["sym"] == sym:
                price = exchange.fetch_ticker(p["sym"])["last"]
                pnl = (price - p["entry"]) if p["signal"]=="LONG" else (p["entry"]-price)
                send(f"⛔ MANUAL EXIT {sym}", cid)
                save_trade(p["sym"], pnl)
                positions.remove(p)
                break

# ==============================
threading.Thread(target=scanner, daemon=True).start()
threading.Thread(target=manage, daemon=True).start()

send(f"💀 BOT {VERSION} AKTIF")
bot.infinity_polling()
