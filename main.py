import os, time, ccxt, telebot, threading
import pandas as pd
import numpy as np
from openai import OpenAI

# ===== CONFIG =====
LEVERAGE = 10
BASE_USDT = 5
MODE = "PAPER"

# ===== TELEGRAM =====
bot = telebot.TeleBot(os.getenv("TELE_TOKEN"))
CHAT_ID = os.getenv("MY_CHAT_ID")

def send(msg):
    try:
        bot.send_message(CHAT_ID, msg)
    except:
        print(msg)

# ===== OPENAI =====
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ===== EXCHANGE =====
exchange = ccxt.bitget({
    "apiKey": os.getenv("BITGET_API"),
    "secret": os.getenv("BITGET_SEC"),
    "password": os.getenv("BITGET_PASS"),
    "options": {"defaultType": "swap"}
})

# ===== STATE =====
pending = {}
position = None

# ===== SYMBOL FIX =====
def fix_symbol(raw):
    raw = raw.upper()
    if "/" in raw:
        return raw
    return raw + "/USDT:USDT"

# ===== FEATURES =====
def features(sym):
    try:
        df = pd.DataFrame(exchange.fetch_ohlcv(sym,"1m",50),
                          columns=["t","o","h","l","c","v"])

        return {
            "price": float(df["c"].iloc[-1]),
            "trend": int(df["c"].ewm(9).mean().iloc[-1] > df["c"].ewm(21).mean().iloc[-1]),
            "volume": float(df["v"].iloc[-1])
        }
    except:
        return None

# ===== AI ANALYSIS =====
def ai_analyze(sym, f):
    prompt = f"""
You are a pro trader.

Coin: {sym}
Price: {f['price']}
Trend: {"UP" if f["trend"]==1 else "DOWN"}

Give:
Direction: LONG or SHORT
Confidence: 0-1
TP and SL

Short answer.
"""
    res = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[{"role":"user","content":prompt}],
        temperature=0.4
    )
    text = res.choices[0].message.content

    # basit parse
    direction = "LONG" if "LONG" in text.upper() else "SHORT"
    return text, direction

# ===== AI LIVE =====
def ai_live(sym, pnl):
    try:
        prompt = f"PnL: {pnl} USDT. Continue or exit?"
        res = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[{"role":"user","content":prompt}]
        )
        return res.choices[0].message.content
    except:
        return ""

# ===== PRICE =====
def price(sym):
    return exchange.fetch_ticker(sym)["last"]

# ===== ORDER =====
def order(sym, side, qty):
    if MODE == "REAL":
        exchange.set_leverage(LEVERAGE, sym)
        return exchange.create_market_order(sym, side, qty)
    return True

# ===== TELEGRAM =====
@bot.message_handler(func=lambda m: True)
def handle(m):
    global pending, position

    txt = m.text.upper()

    # ===== ANALIZ =====
    if "ANALIZ" in txt:
        raw = txt.split(" ")[1]
        sym = fix_symbol(raw)

        send(f"🔍 analiz ediliyor: {sym}")

        f = features(sym)
        if not f:
            send("❌ veri alınamadı (coin yanlış olabilir)")
            return

        result, direction = ai_analyze(sym, f)

        send(result)
        send("Girelim mi? EVET / HAYIR")

        pending = {"sym": sym, "dir": direction}

    # ===== AI COIN =====
    elif txt == "AI":
        sym = "BTC/USDT:USDT"

        f = features(sym)
        result, direction = ai_analyze(sym, f)

        send(f"🤖 AI fırsat: {sym}")
        send(result)
        send("Girelim mi? EVET / HAYIR")

        pending = {"sym": sym, "dir": direction}

    # ===== GİR =====
    elif txt == "EVET":
        sym = pending["sym"]
        direction = pending["dir"]

        pr = price(sym)
        qty = (BASE_USDT * LEVERAGE) / pr

        side = "buy" if direction == "LONG" else "sell"

        order(sym, side, qty)

        position = {
            "sym": sym,
            "entry": pr,
            "qty": qty,
            "side": direction,
            "peak": 0,
            "tp1": False
        }

        send(f"🚀 {sym} {direction} açıldı")

    # ===== KAPAT =====
    elif txt == "KAPAT":
        if not position:
            return

        pr = price(position["sym"])

        if position["side"] == "LONG":
            pnl = (pr - position["entry"]) * position["qty"]
        else:
            pnl = (position["entry"] - pr) * position["qty"]

        send(f"❌ kapandı {round(pnl,2)} USDT")
        position = None

    elif txt == "DEVAM":
        send("👍 devam")

# ===== LOOP =====
def loop():
    global position

    while True:
        try:
            if position:
                pr = price(position["sym"])

                if position["side"] == "LONG":
                    pnl = (pr - position["entry"]) * position["qty"]
                else:
                    pnl = (position["entry"] - pr) * position["qty"]

                if pnl > position["peak"]:
                    position["peak"] = pnl

                # TP1
                if pnl > 2 and not position["tp1"]:
                    position["tp1"] = True
                    send(f"🎯 TP1: {round(pnl,2)} USDT\nDEVAM / KAPAT")

                # AI yorum
                send("🧠 " + ai_live(position["sym"], round(pnl,2)))

                # trailing
                if position["peak"] > 3 and pnl < position["peak"] - 2:
                    send("⚠️ trailing exit")
                    position = None

                send(f"📊 {round(pnl,2)} USDT")

            time.sleep(20)

        except Exception as e:
            print(e)
            time.sleep(5)

# ===== START =====
threading.Thread(target=loop, daemon=True).start()

send("💀 V12000 FINAL AKTİF")
bot.infinity_polling()
