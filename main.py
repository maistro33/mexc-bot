# ==============================
# 💀 SADIK BOT v17 AI TRADER
# ==============================

import os, time, ccxt, telebot, threading, requests, uuid
import pandas as pd
from openai import OpenAI
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

VERSION = "v17 AI TRADER"

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
best_signal = None

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
        df["vol_mean"] = df["v"].rolling(10).mean()
        return df
    except:
        return None

# ==============================
# 🧠 GELİŞMİŞ AI ANALİZ
def ai_analyze(sym):
    try:
        df = get_data(sym)
        if df is None:
            return None

        price = df["c"].iloc[-1]
        ema = df["ema"].iloc[-1]
        vol = df["v"].iloc[-1]
        vol_mean = df["vol_mean"].iloc[-1]

        prompt = f"""
Symbol: {sym}
Price: {price}
EMA: {ema}
Volume: {vol}
Avg Volume: {vol_mean}

Kurallar:
- LONG / SHORT / NONE karar ver
- Confidence (0-1)
- Kısa sebep

Format:
DECISION: LONG
CONFIDENCE: 0.75
REASON: ...
"""

        r = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role":"user","content":prompt}]
        )

        txt = r.choices[0].message.content.upper()

        signal = "NONE"
        if "LONG" in txt:
            signal = "LONG"
        elif "SHORT" in txt:
            signal = "SHORT"

        # confidence parse
        conf = 0.5
        try:
            if "CONFIDENCE" in txt:
                conf = float(txt.split("CONFIDENCE:")[1].split()[0])
        except:
            pass

        return {
            "sym": sym,
            "signal": signal,
            "entry": price,
            "text": txt,
            "confidence": conf
        }

    except Exception as e:
        print("AI:", e)
        return None

# ==============================
def scanner():
    global best_signal

    while True:
        try:
            tickers = exchange.fetch_tickers()

            pairs = [
                (s, v["quoteVolume"])
                for s, v in tickers.items()
                if ":USDT" in s and v["quoteVolume"]
            ]

            pairs = [p for p in pairs if p[1] > 3_000_000]
            pairs.sort(key=lambda x: x[1], reverse=True)
            top = [p[0] for p in pairs[:30]]

            for sym in top:

                if any(x in sym for x in ["BTC","ETH","BNB"]):
                    continue

                data = ai_analyze(sym)
                if not data:
                    continue

                # 🔥 CONFIDENCE FİLTRE
                if data["confidence"] < 0.65:
                    continue

                if data["signal"] == "NONE":
                    continue

                best_signal = data

                markup = InlineKeyboardMarkup()
                markup.add(
                    InlineKeyboardButton("✅ GİR", callback_data="enter"),
                    InlineKeyboardButton("❌ PAS", callback_data="pass")
                )

                send(f"""
🤖 AI SİNYAL

{data['sym']}
{data['signal']} ({data['confidence']})

{data['text']}
""")

                bot.send_message(CHAT_ID, "İşlem:", reply_markup=markup)
                break

        except Exception as e:
            print("SCAN:", e)

        time.sleep(60)

# ==============================
# 💾 TRADE AÇ
def open_trade(data, cid):
    trade_id = str(uuid.uuid4())

    positions.append({
        "id": trade_id,
        **data,
        "remaining": 1.0,
        "ai_status": "HOLD",
        "chat": cid
    })

    # Supabase kayıt
    try:
        headers = {
            "apikey": SUPA_KEY,
            "Authorization": f"Bearer {SUPA_KEY}",
            "Content-Type": "application/json"
        }

        requests.post(f"{SUPA_URL}/rest/v1/trades", headers=headers, json={
            "id": trade_id,
            "symbol": data["sym"],
            "entry": data["entry"],
            "reason": data["text"]
        })
    except:
        pass

    send(f"🚀 {data['sym']} açıldı", cid)

# ==============================
# 🧠 AI EXIT ANALİZ
def ai_exit_decision(p, price):

    try:
        prompt = f"""
Trade: {p['sym']}
Entry: {p['entry']}
Current: {price}

Kar mı zarar mı bak.
EXIT mi HOLD mu karar ver.
"""

        r = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role":"user","content":prompt}]
        )

        txt = r.choices[0].message.content.upper()

        return "EXIT" if "EXIT" in txt else "HOLD"

    except:
        return "HOLD"

# ==============================
# 🔁 AI LEARNING
def ai_learn(p, pnl):
    try:
        prompt = f"""
Trade sonucu:
Symbol: {p['sym']}
PnL: {pnl}
AI Reason: {p['text']}

Bu trade neden başarılı/başarısız oldu?
Kısa öğrenme yaz.
"""

        r = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role":"user","content":prompt}]
        )

        learn = r.choices[0].message.content

        send(f"🧠 AI LEARN:\n{learn}", p["chat"])

    except:
        pass

# ==============================
def manage():
    while True:
        for p in positions[:]:
            try:
                price = exchange.fetch_ticker(p["sym"])["last"]
            except:
                continue

            pnl = ((price - p["entry"]) / p["entry"]) * 50
            pnl = round(pnl,2)

            decision = ai_exit_decision(p, price)
            p["ai_status"] = decision

            if decision == "EXIT":
                send(f"⚠️ AI EXIT {p['sym']} {pnl} USDT", p["chat"])

                # Supabase update
                try:
                    headers = {
                        "apikey": SUPA_KEY,
                        "Authorization": f"Bearer {SUPA_KEY}",
                        "Content-Type": "application/json"
                    }

                    requests.patch(f"{SUPA_URL}/rest/v1/trades?id=eq.{p['id']}",
                                   headers=headers,
                                   json={"exit": price, "result": pnl})
                except:
                    pass

                ai_learn(p, pnl)

                positions.remove(p)

        time.sleep(5)

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
            if t.get("result"):
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
            pnl = ((price - p["entry"]) / p["entry"]) * 50
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

    global best_signal
    cid = call.message.chat.id

    if call.data == "enter" and best_signal:
        open_trade(best_signal, cid)

    elif call.data == "pass":
        send("⛔ PAS", cid)

    elif call.data.startswith("exit_"):
        pid = call.data.split("_")[1]

        for p in positions:
            if p["id"] == pid:
                price = exchange.fetch_ticker(p["sym"])["last"]
                pnl = ((price - p["entry"]) / p["entry"]) * 50
                pnl = round(pnl,2)

                send(f"⛔ {p['sym']} kapatıldı {pnl} USDT", cid)
                ai_learn(p, pnl)
                positions.remove(p)
                break

    elif call.data.startswith("keep_"):
        send("🟢 DEVAM", cid)

# ==============================
threading.Thread(target=scanner, daemon=True).start()
threading.Thread(target=manage, daemon=True).start()

send(f"💀 BOT {VERSION} AKTİF")
bot.infinity_polling()
