# ==============================
# 💀 SADIK BOT v16 FULL SYSTEM
# ==============================

import os, time, ccxt, telebot, threading, requests
import pandas as pd
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

VERSION = "v16 FULL SYSTEM"

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
def market_status():
    try:
        df = get_data("BTC/USDT:USDT")
        price = df["c"].iloc[-1]
        ema = df["ema"].iloc[-1]
        return "🟢 BULLISH" if price > ema else "🔴 BEARISH"
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
                    "sl": sl
                }

                markup = InlineKeyboardMarkup()
                markup.add(InlineKeyboardButton("✅ GİR", callback_data=f"enter|{safe}"))

                send(f"""
💀 AKILLI SİNYAL

📊 {sym}
📈 {signal}
💰 {round(price,4)}
""")

                bot.send_message(CHAT_ID, "GİR:", reply_markup=markup)
                time.sleep(2)

            time.sleep(15)

        except:
            time.sleep(5)

# ==============================
def open_trade(data, cid):
    positions.append({
        **data,
        "remaining": 1.0,
        "tp1_done": False,
        "tp2_done": False,
        "ai_status": "HOLD",
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

            pnl = ((price - p["entry"]) / p["entry"]) * 50 * p["remaining"]
            pnl = round(pnl,2)

            df = get_data(p["sym"])
            if df is None:
                continue

            ema = df["ema"].iloc[-1]
            trend = "UP" if price > ema else "DOWN"

            p["ai_status"] = "HOLD" if trend=="UP" else "EXIT"

            # TP SYSTEM
            if p["signal"]=="LONG":

                if not p["tp1_done"] and price >= p["tp1"]:
                    p["tp1_done"] = True
                    p["remaining"] -= 0.5
                    send(f"🎯 TP1 {p['sym']} +{pnl} USDT")

                elif not p["tp2_done"] and price >= p["tp2"]:
                    p["tp2_done"] = True
                    p["remaining"] -= 0.25
                    send(f"🎯 TP2 {p['sym']} +{pnl} USDT")

                elif price >= p["tp3"]:
                    send(f"🚀 TP3 {p['sym']} +{pnl} USDT")
                    positions.remove(p)
                    continue

                if price <= p["sl"]:
                    send(f"🛑 STOP {p['sym']} {pnl} USDT")
                    positions.remove(p)
                    continue

        time.sleep(5)

# ==============================
def build_panel():

    text = f"""
💀 SADIK LIVE PANEL

🌍 Market: {market_status()}
📈 Açık İşlem: {len(positions)}

━━━━━━━━━━━━━━
"""

    total = 0

    for p in positions:
        try:
            price = exchange.fetch_ticker(p["sym"])["last"]
            pnl = ((price - p["entry"]) / p["entry"]) * 50 * p["remaining"]
            pnl = round(pnl,2)

            total += pnl

            emoji = "🟢" if pnl >= 0 else "🔴"

            text += f"\n{p['sym']} → {pnl} USDT {emoji} | {p['ai_status']}\n"

        except:
            continue

    text += f"\n💰 Toplam: {round(total,2)} USDT"

    return text

# ==============================
def panel_keyboard():

    markup = InlineKeyboardMarkup()

    for p in positions:
        markup.row(
            InlineKeyboardButton(f"🟢 DEVAM {p['sym']}", callback_data=f"keep_{p['id']}"),
            InlineKeyboardButton(f"⛔ KAPAT {p['sym']}", callback_data=f"exit_{p['id']}")
        )

    markup.row(
        InlineKeyboardButton("🚨 EXIT ALL", callback_data="exit_all")
    )

    return markup

# ==============================
@bot.message_handler(commands=['panel'])
def panel(msg):

    global panel_message_id, panel_chat_id

    panel_chat_id = msg.chat.id

    m = bot.send_message(panel_chat_id, "⏳ PANEL YÜKLENİYOR...")
    panel_message_id = m.message_id

# ==============================
def live_panel():

    global panel_message_id, panel_chat_id

    while True:

        if panel_message_id:

            try:
                bot.edit_message_text(
                    build_panel(),
                    chat_id=panel_chat_id,
                    message_id=panel_message_id,
                    reply_markup=panel_keyboard()
                )
            except:
                pass

        time.sleep(4)

# ==============================
@bot.callback_query_handler(func=lambda call: True)
def callback(call):

    cid = call.message.chat.id

    if call.data.startswith("enter|"):
        data = signal_cache.get(call.data.split("|")[1])
        if data:
            open_trade(data, cid)

    elif call.data.startswith("exit_"):
        pid = call.data.split("_")[1]
        for p in positions:
            if p["id"] == pid:
                send(f"⛔ EXIT {p['sym']}", cid)
                positions.remove(p)
                break

    elif call.data.startswith("keep_"):
        send("🟢 DEVAM", cid)

    elif call.data == "exit_all":
        for p in positions[:]:
            send(f"⛔ EXIT {p['sym']}", cid)
            positions.remove(p)

# ==============================
threading.Thread(target=scanner, daemon=True).start()
threading.Thread(target=manage, daemon=True).start()
threading.Thread(target=live_panel, daemon=True).start()

send(f"💀 BOT {VERSION} AKTİF")
bot.infinity_polling()
