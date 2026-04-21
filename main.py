import os, time, ccxt, requests, telebot, random, threading
import pandas as pd
import numpy as np

# ===== TELEGRAM (FIX) =====
TOKEN = os.getenv("TELE_TOKEN")
CHAT_ID = os.getenv("MY_CHAT_ID")

bot = telebot.TeleBot(TOKEN) if TOKEN else None

def send(msg):
    try:
        if bot and CHAT_ID:
            bot.send_message(CHAT_ID, msg)
            print("📩 Telegram gönderildi")
        else:
            print("❌ Telegram ayar yok")
    except Exception as e:
        print("❌ Telegram hata:", e)

# ===== CONFIG =====
SYMBOL = "BTC/USDT:USDT"
TIMEFRAME = "5m"

# ===== EXCHANGE =====
exchange = ccxt.bitget({
    "apiKey": os.getenv("BITGET_API"),
    "secret": os.getenv("BITGET_SEC"),
    "password": os.getenv("BITGET_PASS"),
    "options": {"defaultType": "swap"},
    "enableRateLimit": True
})

# ===== RSI =====
def compute_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(period).mean()
    rs = gain / (loss + 1e-9)
    return 100 - (100 / (1 + rs))

# ===== DATA =====
def get_data():
    try:
        df = pd.DataFrame(exchange.fetch_ohlcv(SYMBOL, TIMEFRAME, 100),
                          columns=["t","o","h","l","c","v"])
        return df
    except Exception as e:
        print("❌ veri yok:", e)
        return None

# ===== AI ANALİZ =====
def analyze(df):
    df["ema"] = df["c"].ewm(span=20).mean()
    df["rsi"] = compute_rsi(df["c"])

    last = df.iloc[-1]

    trend = "LONG" if last["c"] > last["ema"] else "SHORT"
    strength = abs(last["c"] - last["ema"]) / last["c"]
    confidence = min(100, strength * 10000)

    return trend, confidence

# ===== TRADE =====
last_signal = None

def trade(signal, price, confidence):
    global last_signal

    if signal == last_signal:
        return

    last_signal = signal

    tp = price * 1.01 if signal == "LONG" else price * 0.99
    sl = price * 0.98 if signal == "LONG" else price * 1.02

    msg = f"""
💀 V13000 AI TRADE

📊 {SYMBOL}
📈 Sinyal: {signal}
💰 Fiyat: {price}

🎯 TP: {tp}
🛑 SL: {sl}
📊 Güç: {confidence:.2f}
"""

    print(msg)
    send(msg)

# ===== START =====
def run():
    print("💀 V13000 FINAL AKTİF")
    send("🚀 BOT BAŞLADI")

    while True:
        df = get_data()

        if df is None:
            time.sleep(10)
            continue

        trend, confidence = analyze(df)
        price = df["c"].iloc[-1]

        print(f"🔍 {SYMBOL} → {trend} ({confidence:.2f})")

        if confidence > 10:
            trade(trend, price, confidence)

        time.sleep(20)

run()
