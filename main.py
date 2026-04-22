# ==============================
# 💀 SADIK BOT v20.3 FINAL
# ==============================

import os, time, ccxt, telebot, threading, requests
import pandas as pd
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

VERSION = "v20.3 PARTIAL TP"

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
history_cache = []
last_history_update = 0

# ==============================
def send(msg, cid=None):
    try:
        bot.send_message(cid or CHAT_ID, msg)
    except:
        pass

# ==============================
def get_data(sym):
    try:
        ohlcv = exchange.fetch_ohlcv(sym, "1m", limit=100)
        df = pd.DataFrame(ohlcv, columns=["t","o","h","l","c","v"])

        if len(df) < 10:
            return None

        df["ema"] = df["c"].ewm(20).mean()
        df["rsi"] = 100 - (100 / (1 + df["c"].pct_change().rolling(14).mean()))
        return df
    except:
        return None

# ==============================
def load_history():
    global history_cache, last_history_update

    if time.time() - last_history_update < 60:
        return history_cache

    try:
        headers = {
            "apikey": SUPA_KEY,
            "Authorization": f"Bearer {SUPA_KEY}"
        }

        r = requests.get(f"{SUPA_URL}/rest/v1/trades?select=*", headers=headers)

        history_cache = r.json()
        last_history_update = time.time()

        return history_cache

    except:
        return history_cache

# ==============================
def coin_filter(symbol):
    data = load_history()
    trades = [x for x in data if x.get("Symbol") == symbol]

    if len(trades) < 15:
        return True

    wins = [x for x in trades if x.get("pnl",0) > 0]
    winrate = len(wins) / len(trades)

    return winrate > 0.4

# ==============================
def ai_signal(df):
    try:
        price = df["c"].iloc[-1]
        ema = df["ema"].iloc[-1]
        rsi = df["rsi"].iloc[-1]

        momentum = df["c"].iloc[-1] - df["c"].iloc[-5]

        base_volume = df["v"].iloc[-5]
        if base_volume <= 0:
            return None, 0

        volume = df["v"].iloc[-1] / base_volume

        score_long = 0
        score_short = 0

        if price > ema:
            score_long += 30
        else:
            score_short += 30

        if rsi < 30:
            score_long += 20
        elif rsi > 70:
            score_short += 20

        if momentum > 0:
            score_long += 25
        else:
            score_short += 25

        if volume > 1.3:
            score_long += 15
            score_short += 15

        return ("LONG", score_long) if score_long > score_short else ("SHORT", score_short)

    except:
        return None, 0

# ==============================
def market_status():
    try:
        df = get_data("BTC/USDT:USDT")
        return "🟢 BULLISH" if df and df["c"].iloc[-1] > df["ema"].iloc[-1] else "🔴 BEARISH"
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

        requests.post(
            f"{SUPA_URL}/rest/v1/trades",
            headers=headers,
            json={"Symbol": sym, "pnl": pnl}
        )

    except Exception as e:
        print("SUPABASE ERROR:", e)

# ==============================
def calc_pnl(p, price):
    if p["signal"] == "LONG":
        pnl = (price - p["entry"]) / p["entry"] * p["size"]
    else:
        pnl = (p["entry"] - price) / p["entry"] * p["size"]
    return round(pnl,2)

# ==============================
def scanner():
    while True:
        try:
            tickers = exchange.fetch_tickers()

            for sym in tickers:

                if ":USDT" not in sym:
                    continue

                if not coin_filter(sym):
                    continue

                df = get_data(sym)
                if df is None:
                    continue

                signal, strength = ai_signal(df)

                if signal is None or strength < 60:
                    continue

                price = df["c"].iloc[-1]
                if price <= 0:
                    continue

                if signal == "LONG":
                    tp1, tp2, tp3, sl = price*1.01, price*1.02, price*1.03, price*0.98
                else:
                    tp1, tp2, tp3, sl = price*0.99, price*0.98, price*0.97, price*1.02

                safe = sym.replace("/","").replace(":","")

                signal_cache[safe] = {
                    "id": safe,
                    "sym": sym,
                    "entry": price,
                    "signal": signal,
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

🤖 Güç: %{strength}
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
        "tp1_done":False,
        "tp2_done":False,
        "chat":cid,
        "margin":5,
        "leverage":10,
        "size":50
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

            pnl_total = calc_pnl(p, price)

            if p["signal"] == "LONG":

                if not p["tp1_done"] and price >= p["tp1"]:
                    p["tp1_done"] = True
                    part = pnl_total * 0.5
                    p["size"] *= 0.5
                    p["sl"] = p["entry"]
                    daily_pnl += part
                    total_pnl += part
                    send(f"🎯 TP1 {p['sym']} +{round(part,2)} USDT")

                elif not p["tp2_done"] and price >= p["tp2"]:
                    p["tp2_done"] = True
                    part = pnl_total * 0.25
                    p["size"] *= 0.5
                    p["sl"] = p["tp1"]
                    daily_pnl += part
                    total_pnl += part
                    send(f"🎯 TP2 {p['sym']} +{round(part,2)} USDT")

                elif price >= p["tp3"]:
                    final = pnl_total
                    daily_pnl += final
                    total_pnl += final
                    save_trade(p["sym"], final)
                    send(f"🚀 TP3 {p['sym']} +{round(final,2)} USDT")
                    positions.remove(p)
                    continue

                if price <= p["sl"]:
                    final = pnl_total
                    daily_pnl += final
                    total_pnl += final
                    save_trade(p["sym"], final)
                    send(f"🛑 STOP {p['sym']} {round(final,2)} USDT")
                    positions.remove(p)
                    continue

            else:

                if not p["tp1_done"] and price <= p["tp1"]:
                    p["tp1_done"] = True
                    part = pnl_total * 0.5
                    p["size"] *= 0.5
                    p["sl"] = p["entry"]
                    daily_pnl += part
                    total_pnl += part
                    send(f"🎯 TP1 SHORT {p['sym']} +{round(part,2)} USDT")

                elif not p["tp2_done"] and price <= p["tp2"]:
                    p["tp2_done"] = True
                    part = pnl_total * 0.25
                    p["size"] *= 0.5
                    p["sl"] = p["tp1"]
                    daily_pnl += part
                    total_pnl += part
                    send(f"🎯 TP2 SHORT {p['sym']} +{round(part,2)} USDT")

                elif price <= p["tp3"]:
                    final = pnl_total
                    daily_pnl += final
                    total_pnl += final
                    save_trade(p["sym"], final)
                    send(f"🚀 TP3 SHORT {p['sym']} +{round(final,2)} USDT")
                    positions.remove(p)
                    continue

                if price >= p["sl"]:
                    final = pnl_total
                    daily_pnl += final
                    total_pnl += final
                    save_trade(p["sym"], final)
                    send(f"🛑 STOP SHORT {p['sym']} {round(final,2)} USDT")
                    positions.remove(p)
                    continue

        time.sleep(5)

# ==============================
def build_panel():
    text = f"""
💀 LIVE PANEL

📅 Günlük: {round(daily_pnl,2)} USDT
💰 Toplam: {round(total_pnl,2)} USDT

🌍 Market: {market_status()}
📈 Açık: {len(positions)}

━━━━━━━━━━━━━━
"""

    for p in positions:
        try:
            price = exchange.fetch_ticker(p["sym"])["last"]
            pnl = calc_pnl(p, price)
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

    markup.row(InlineKeyboardButton("🚨 EXIT ALL", callback_data="exit_all"))
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
                price = exchange.fetch_ticker(p["sym"])["last"]
                pnl = calc_pnl(p, price)

                global daily_pnl, total_pnl
                daily_pnl += pnl
                total_pnl += pnl

                save_trade(p["sym"], pnl)

                send(f"⛔ MANUAL EXIT {p['sym']} → {pnl} USDT", cid)

                positions.remove(p)
                break

    elif call.data == "exit_all":

        for p in positions[:]:
            price = exchange.fetch_ticker(p["sym"])["last"]
            pnl = calc_pnl(p, price)

            daily_pnl += pnl
            total_pnl += pnl

            save_trade(p["sym"], pnl)

            send(f"⛔ EXIT {p['sym']} → {pnl} USDT", cid)

            positions.remove(p)

# ==============================
threading.Thread(target=scanner, daemon=True).start()
threading.Thread(target=manage, daemon=True).start()
threading.Thread(target=live_panel, daemon=True).start()

send(f"💀 BOT {VERSION} AKTİF")
bot.infinity_polling()
