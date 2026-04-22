# ==============================
# 💀 SADIK BOT v19 PRO LIVE TRADER
# ==============================

import os, time, ccxt, telebot, threading, requests
import pandas as pd
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

VERSION = "v19 PRO LIVE"

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

daily_pnl = 0
total_pnl = 0

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
    if price > ema: score += 40
    if momentum > price * 0.002: score += 30
    if volume > 1.2: score += 30

    return min(score,100)

# ==============================
def market_status():
    try:
        df = get_data("BTC/USDT:USDT")
        return "🟢 BULLISH" if df["c"].iloc[-1] > df["ema"].iloc[-1] else "🔴 BEARISH"
    except:
        return "UNKNOWN"

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
    except:
        pass

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

                strength = ai_strength(df)
                if strength < 70:
                    continue

                price = df["c"].iloc[-1]
                trend = "LONG" if price > df["ema"].iloc[-1] else "SHORT"

                safe = sym.replace("/","").replace(":","")

                signal_cache[safe] = {
                    "id": safe,
                    "sym": sym,
                    "entry": price,
                    "signal": trend,
                    "tp1": price*1.01,
                    "tp2": price*1.02,
                    "tp3": price*1.03,
                    "sl": price*0.98
                }

                markup = InlineKeyboardMarkup()
                markup.add(InlineKeyboardButton("✅ GİR", callback_data=f"enter|{safe}"))

                send(f"""
💀 SİNYAL

{sym}
{trend}
{round(price,4)}

TP1: {round(price*1.01,4)}
TP2: {round(price*1.02,4)}
TP3: {round(price*1.03,4)}
SL: {round(price*0.98,4)}

Güç: %{strength}
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
        "remaining":1.0,
        "tp1_done":False,
        "tp2_done":False,
        "chat":cid
    })

    send(f"🚀 AÇILDI {data['sym']}", cid)

# ==============================
def manage():
    global daily_pnl, total_pnl

    while True:
        for p in positions[:]:

            try:
                price = exchange.fetch_ticker(p["sym"])["last"]
            except:
                continue

            pnl = ((price - p["entry"]) / p["entry"]) * 50 * p["remaining"]
            pnl = round(pnl,2)

            # TP
            if not p["tp1_done"] and price >= p["tp1"]:
                p["tp1_done"]=True
                p["remaining"]-=0.5
                send(f"🎯 TP1 {p['sym']} +{pnl}")

            elif not p["tp2_done"] and price >= p["tp2"]:
                p["tp2_done"]=True
                p["remaining"]-=0.25
                send(f"🎯 TP2 {p['sym']} +{pnl}")

            elif price >= p["tp3"]:
                send(f"🚀 TP3 {p['sym']} +{pnl}")
                daily_pnl += pnl
                total_pnl += pnl
                save_trade(p["sym"], pnl)
                positions.remove(p)
                continue

            # STOP
            if price <= p["sl"]:
                send(f"🛑 STOP {p['sym']} {pnl}")
                daily_pnl += pnl
                total_pnl += pnl
                save_trade(p["sym"], pnl)
                positions.remove(p)
                continue

        time.sleep(5)

# ==============================
def build_panel():

    text = f"""
💀 LIVE TRADER PANEL

📅 Günlük: {round(daily_pnl,2)} USDT
💰 Toplam: {round(total_pnl,2)} USDT

🌍 Market: {market_status()}
📈 Açık: {len(positions)}

━━━━━━━━━━━━━━
"""

    for p in positions:

        try:
            price = exchange.fetch_ticker(p["sym"])["last"]
            pnl = ((price - p["entry"]) / p["entry"]) * 50 * p["remaining"]
            pnl = round(pnl,2)

            emoji = "🟢" if pnl>=0 else "🔴"

            text += f"{p['sym']} → {pnl} USDT {emoji}\n"

        except:
            continue

    return text

# ==============================
def panel_keyboard():

    markup = InlineKeyboardMarkup()

    for p in positions:
        markup.row(
            InlineKeyboardButton(f"🟢 DEVAM {p['sym']}", callback_data=f"keep_{p['id']}"),
            InlineKeyboardButton(f"⛔ STOP {p['sym']}", callback_data=f"exit_{p['id']}")
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

    m = bot.send_message(panel_chat_id, "⏳ YÜKLENİYOR...")
    panel_message_id = m.message_id

# ==============================
def live_panel():

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
                send(f"⛔ MANUAL EXIT {p['sym']}", cid)
                positions.remove(p)
                break

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
