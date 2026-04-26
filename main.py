# ==============================
# 💀 SADIK BOT v22.4 PRO FIX FULL
# ==============================

import os, time, ccxt, telebot, threading, requests
import pandas as pd
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

VERSION = "v22.4 PRO FIX FULL"

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

closed_trades = []

panel_message_id = None
panel_chat_id = None

daily_pnl = 0
total_pnl = 0

history_cache = []
last_history_update = 0

TP_TOLERANCE = 0.002
MIN_CONFIDENCE = 90

# ==============================
# 🔴 FIX: REAL SIZE (fallback kaldırıldı)
def get_real_size(sym):
    try:
        data = exchange.fetch_positions()
        for p in data:
            if p["symbol"] == sym:
                return float(p.get("contracts", 0))
    except:
        pass
    return 0

# ==============================
def smart_tp_sl(price, signal):
    fee = 0.0012
    if signal == "LONG":
        return (
            price*(1+fee+0.01),
            price*(1+fee+0.025),
            price*(1+fee+0.05),
            price*0.99
        )
    else:
        return (
            price*(1-fee-0.01),
            price*(1-fee-0.025),
            price*(1-fee-0.05),
            price*1.01
        )

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
def safe_send(text, cid=None, markup=None):
    while True:
        try:
            if markup:
                bot.send_message(cid or CHAT_ID, text, reply_markup=markup)
            else:
                bot.send_message(cid or CHAT_ID, text)
            break
        except Exception as e:
            if "Too Many Requests" in str(e):
                time.sleep(8)
            else:
                break

def send(msg, cid=None):
    safe_send(msg, cid)

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
def market_direction():
    try:
        df = get_data("BTC/USDT:USDT")
        if df is None:
            return "NEUTRAL"
        if df["c"].iloc[-1] > df["ema"].iloc[-1]:
            return "BULL"
        else:
            return "BEAR"
    except:
        return "NEUTRAL"

# ==============================
def load_open_positions():
    try:
        data = exchange.fetch_positions()

        for pos in data:
            if float(pos.get("contracts", 0)) == 0:
                continue

            sym = pos["symbol"]
            entry = float(pos["entryPrice"])
            side = pos["side"]

            signal = "LONG" if side == "long" else "SHORT"

            tp1, tp2, tp3, sl = smart_tp_sl(entry, signal)

            if any(p["sym"] == sym for p in positions):
                continue

            safe = sym.replace("/","").replace(":","")

            size = float(pos.get("contracts",0))

            positions.append({
                "id": safe,
                "sym": sym,
                "entry": entry,
                "signal": signal,
                "tp1": tp1,
                "tp2": tp2,
                "tp3": tp3,
                "sl": sl,
                "tp1_done": False,
                "tp2_done": False,
                "chat": CHAT_ID,
                "margin": 3,
                "leverage": 10,
                "size": 30,
                "initial_size": size,
                "realized": 0,
                "max_profit":0
            })

    except Exception as e:
        send(f"❌ LOAD ERROR: {e}")

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
            sent_count = 0

            for sym in tickers:

                if len(positions) >= 1:
                    break

                if sent_count >= 5:
                    break

                if ":USDT" not in sym:
                    continue

                if any(p["sym"] == sym for p in positions):
                    continue

                if not coin_filter(sym):
                    continue

                df = get_data(sym)
                if df is None:
                    continue

                signal, strength = ai_signal(df)
                if signal is None or strength < MIN_CONFIDENCE:
                    continue

                market = market_direction()
                if signal == "LONG" and market == "BEAR":
                    continue
                if signal == "SHORT" and market == "BULL":
                    continue

                price = df["c"].iloc[-1]

                tp1, tp2, tp3, sl = smart_tp_sl(price, signal)

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

                safe_send(f"""
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

                safe_send("GİR:", markup=markup)

                sent_count += 1
                time.sleep(4)

            time.sleep(25)

        except Exception as e:
            print("SCANNER:", e)
            time.sleep(5)

# ==============================
def open_trade(data, cid):

    if any(p["sym"] == data["sym"] for p in positions):
        send(f"⚠️ ZATEN AÇIK: {data['sym']}", cid)
        return

    if len(positions) >= 3:
        send("⚠️ SADECE 1 İŞLEM İZİN", cid)
        return

    try:
        side = "buy" if data["signal"] == "LONG" else "sell"
        exchange.set_leverage(10, data["sym"])
        amount = 30 / data["entry"]
        exchange.create_market_order(data["sym"], side, amount)
        send(f"✅ GERÇEK AÇILDI {data['sym']}", cid)

        time.sleep(2)
        real_size = get_real_size(data["sym"])

    except Exception as e:
        send(f"❌ ORDER HATA: {e}", cid)

    positions.append({
        **data,
        "tp1_done":False,
        "tp2_done":False,
        "chat":cid,
        "margin":3,
        "leverage":10,
        "size":30,
        "initial_size": real_size,
        "realized":0,
        "max_profit":0
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

            if pnl_total > p.get("max_profit",0):
                p["max_profit"] = pnl_total

            if p.get("max_profit",0) > 3:
                trail = p["max_profit"] * 0.7
                if pnl_total < trail:
                    p["sl"] = price

            # TP1
            if not p["tp1_done"]:
                if (p["signal"]=="LONG" and price>=p["tp1"]) or (p["signal"]=="SHORT" and price<=p["tp1"]):
                    size = p["initial_size"] * 0.5
                    exchange.create_market_order(
                        p["sym"],
                        "sell" if p["signal"]=="LONG" else "buy",
                        size
                    )
                    p["tp1_done"] = True
                    p["sl"] = p["entry"]
                    send(f"🎯 TP1 {p['sym']} {round(pnl_total,2)} USDT")

            # TP2
            if not p["tp2_done"]:
                if (p["signal"]=="LONG" and price>=p["tp2"]) or (p["signal"]=="SHORT" and price<=p["tp2"]):
                    size = p["initial_size"] * 0.25
                    exchange.create_market_order(
                        p["sym"],
                        "sell" if p["signal"]=="LONG" else "buy",
                        size
                    )
                    p["tp2_done"] = True
                    p["sl"] = p["tp1"]
                    send(f"🎯 TP2 {p['sym']} {round(pnl_total,2)} USDT")

            # FINAL CLOSE
            if (p["signal"]=="LONG" and (price <= p["sl"] or price >= p["tp3"])) or \
               (p["signal"]=="SHORT" and (price >= p["sl"] or price <= p["tp3"])):

                remaining = get_real_size(p["sym"])
                if remaining > 0:
                    exchange.create_market_order(
                        p["sym"],
                        "sell" if p["signal"]=="LONG" else "buy",
                        remaining
                    )

                final = p["realized"] + pnl_total
                daily_pnl += final
                total_pnl += final
                save_trade(p["sym"], final)

                closed_trades.append({
                    "sym": p["sym"],
                    "pnl": round(final,2)
                })

                send(f"⛔ KAPANDI {p['sym']} {round(final,2)} USDT")
                positions.remove(p)

        time.sleep(5)

# ==============================
# PANEL / CALLBACK / THREADS — AYNEN KORUNDU

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

    text += "\n📊 SON İŞLEMLER:\n"
    for t in closed_trades[-5:]:
        emoji = "🟢" if t["pnl"] >= 0 else "🔴"
        text += f"{t['sym']} → {t['pnl']} USDT {emoji}\n"

    return text

def panel_keyboard():
    markup = InlineKeyboardMarkup()

    for p in positions:
        markup.row(
            InlineKeyboardButton(f"🟢 DEVAM {p['sym']}", callback_data=f"keep_{p['id']}"),
            InlineKeyboardButton(f"⛔ STOP {p['sym']}", callback_data=f"exit_{p['id']}")
        )

    markup.row(InlineKeyboardButton("🚨 EXIT ALL", callback_data="exit_all"))
    return markup

@bot.message_handler(commands=['panel'])
def panel(msg):
    global panel_message_id, panel_chat_id
    panel_chat_id = msg.chat.id
    m = bot.send_message(panel_chat_id, "⏳ PANEL YÜKLENİYOR...")
    panel_message_id = m.message_id

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

                try:
                    remaining = get_real_size(p["sym"])
                    if remaining > 0:
                        exchange.create_market_order(
                            p["sym"],
                            "sell" if p["signal"]=="LONG" else "buy",
                            remaining
                        )
                except Exception as e:
                    send(f"❌ MANUAL CLOSE ERROR: {e}", cid)

                price = exchange.fetch_ticker(p["sym"])["last"]
                pnl = calc_pnl(p, price)

                final = p["realized"] + pnl

                global daily_pnl, total_pnl
                daily_pnl += final
                total_pnl += final

                save_trade(p["sym"], final)

                closed_trades.append({
                    "sym": p["sym"],
                    "pnl": round(final,2)
                })

                send(f"⛔ MANUAL EXIT {p['sym']} → {round(final,2)} USDT", cid)

                positions.remove(p)
                break

    elif call.data == "exit_all":

        for p in positions[:]:

            try:
                remaining = get_real_size(p["sym"])
                if remaining > 0:
                    exchange.create_market_order(
                        p["sym"],
                        "sell" if p["signal"]=="LONG" else "buy",
                        remaining
                    )
            except Exception as e:
                send(f"❌ EXIT ALL ERROR: {e}", cid)

            price = exchange.fetch_ticker(p["sym"])["last"]
            pnl = calc_pnl(p, price)

            final = p["realized"] + pnl

            daily_pnl += final
            total_pnl += final

            save_trade(p["sym"], final)

            closed_trades.append({
                "sym": p["sym"],
                "pnl": round(final,2)
            })

            send(f"⛔ EXIT {p['sym']} → {round(final,2)} USDT", cid)

            positions.remove(p)

    elif call.data.startswith("keep_"):
        pid = call.data.split("_")[1]
        for p in positions:
            if p["id"] == pid:
                send(f"🟢 DEVAM {p['sym']}", cid)
                break

# ==============================
def clean_signal_cache():
    while True:
        try:
            if len(signal_cache) > 100:
                signal_cache.clear()
        except:
            pass
        time.sleep(300)

# ==============================
load_open_positions()

threading.Thread(target=scanner, daemon=True).start()
threading.Thread(target=manage, daemon=True).start()
threading.Thread(target=live_panel, daemon=True).start()
threading.Thread(target=clean_signal_cache, daemon=True).start()

send(f"💀 BOT {VERSION} AKTİF")
bot.infinity_polling()
