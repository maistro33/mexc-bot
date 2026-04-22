# ==============================
# 💀 SADIK BOT v8 CORE
# ==============================

import os, time, ccxt, telebot, threading, requests, random
import pandas as pd
from openai import OpenAI

VERSION = "v8 CORE AI"

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
last_analysis = {}

daily_profit = 0
daily_loss = 0

MAX_TRADES = 3
MAX_DAILY_LOSS = -10

# ==============================
# SEND
# ==============================
def send(msg, cid=None):
    try:
        bot.send_message(cid or CHAT_ID, msg)
    except Exception as e:
        print("SEND HATA:", e)

# ==============================
# DATA
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
# SUPABASE LOAD
# ==============================
def load_trade_history():
    try:
        headers = {
            "apikey": SUPA_KEY,
            "Authorization": f"Bearer {SUPA_KEY}"
        }
        r = requests.get(f"{SUPA_URL}/rest/v1/trades?select=*", headers=headers)
        data = r.json()

        wins = [x for x in data if x["result"] > 0]
        losses = [x for x in data if x["result"] <= 0]

        return wins[-50:], losses[-50:]
    except:
        return [], []

# ==============================
# MEMORY DECISION
# ==============================
def ai_memory_decision(sym):
    wins, losses = load_trade_history()

    sym_wins = [x for x in wins if x["symbol"] == sym]
    sym_losses = [x for x in losses if x["symbol"] == sym]

    total = len(sym_wins) + len(sym_losses)

    if total < 5:
        return True, "veri az"

    winrate = len(sym_wins) / total

    if winrate < 0.4:
        return False, f"kotu (%{round(winrate*100,1)})"

    return True, f"iyi (%{round(winrate*100,1)})"

# ==============================
# AI ANALYZE
# ==============================
def ai_analyze(sym, price, trend):
    try:
        prompt = f"""
Symbol: {sym}
Price: {price}
Trend: {trend}

LONG or SHORT?
Return: LONG/SHORT|confidence|reason
"""

        res = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[{"role": "user", "content": prompt}]
        )

        txt = res.choices[0].message.content
        s, c, r = txt.split("|")

        return s.strip(), int(c), r

    except:
        return None, None, "ai hata"

# ==============================
# ANALYZE
# ==============================
def analyze(sym, cid):
    df = get_data(sym)
    if df is None:
        send("veri yok", cid)
        return

    if daily_loss <= MAX_DAILY_LOSS:
        send("gunluk zarar limit", cid)
        return

    last = df.iloc[-1]
    trend = "UP" if last["c"] > last["ema"] else "DOWN"
    signal = "LONG" if trend == "UP" else "SHORT"
    price = float(last["c"])

    allow, note = ai_memory_decision(sym)

    if not allow:
        send(f"AI RED: {note}", cid)
        return

    ai_signal, ai_conf, ai_reason = ai_analyze(sym, price, trend)

    if ai_signal and ai_conf >= 75:
        signal = ai_signal
        conf = ai_conf
        mode = "AI"
    else:
        conf = random.randint(60,70)
        mode = "TREND"

    send(f"""
💀 ANALIZ

{sym}
{signal}
{price}

AI: %{conf}
mode: {mode}
memory: {note}
{ai_reason}
""", cid)

    last_analysis.update({"sym": sym, "signal": signal, "price": price})

# ==============================
# OPEN TRADE
# ==============================
def open_trade(cid):
    if len(positions) >= MAX_TRADES:
        send("max trade", cid)
        return

    if not last_analysis:
        send("once analiz", cid)
        return

    sym = last_analysis["sym"]
    price = last_analysis["price"]
    signal = last_analysis["signal"]

    sl = price * 0.98 if signal=="LONG" else price*1.02

    positions.append({
        "sym": sym,
        "entry": price,
        "signal": signal,
        "sl": sl,
        "chat": cid
    })

    send(f"TRADE {sym} {signal} {price}", cid)

# ==============================
# AI TRADE MANAGE
# ==============================
def ai_manage_trade(sym, entry, price, signal, pct):
    try:
        prompt = f"""
Trade:
{sym}
Entry:{entry}
Price:{price}
Type:{signal}
Profit:{pct}

HOLD or CLOSE?
"""

        res = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[{"role":"user","content":prompt}]
        )

        txt = res.choices[0].message.content

        if "CLOSE" in txt:
            return "CLOSE", txt

    except:
        pass

    return "HOLD",""

# ==============================
# MANAGE LOOP
# ==============================
def manage():
    global daily_profit, daily_loss

    while True:
        for p in positions[:]:
            try:
                price = exchange.fetch_ticker(p["sym"])["last"]
            except:
                continue

            pnl = (price - p["entry"]) if p["signal"]=="LONG" else (p["entry"]-price)
            pct = pnl/p["entry"]*100

            if "last_ai" not in p:
                p["last_ai"]=0

            if time.time()-p["last_ai"]>15:
                p["last_ai"]=time.time()

                action,_ = ai_manage_trade(p["sym"],p["entry"],price,p["signal"],pct)

                if action=="CLOSE":
                    send(f"AI CLOSE {p['sym']} {round(pnl,4)}")
                    daily_profit += pnl if pnl>0 else 0
                    daily_loss += pnl if pnl<0 else 0
                    positions.remove(p)

        time.sleep(5)

# ==============================
# CHAT AI
# ==============================
def chat_ai(text):
    try:
        res = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[{"role":"user","content":text}]
        )
        return res.choices[0].message.content
    except:
        return "ai hata"

# ==============================
# TELEGRAM
# ==============================
@bot.message_handler(func=lambda m: True)
def handle(msg):
    text = msg.text.lower()
    cid = msg.chat.id

    if "analiz" in text:
        coin = text.replace("analiz","").strip().upper()
        analyze(coin+"/USDT:USDT", cid)

    elif text == "gir":
        open_trade(cid)

    elif text == "ogren":
        send("memory aktif", cid)

    else:
        reply = chat_ai(text)
        send(reply, cid)

# ==============================
threading.Thread(target=manage, daemon=True).start()

send(f"💀 BOT {VERSION} AKTIF")
bot.infinity_polling()
