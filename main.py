import ccxt
import pandas as pd
import numpy as np
import time
import os
import requests

# =====================
# 🔐 AYARLAR
# =====================
API_KEY = os.getenv("BITGET_API")
API_SECRET = os.getenv("BITGET_SECRET")
API_PASS = os.getenv("BITGET_PASS")

TELEGRAM_TOKEN = os.getenv("TG_TOKEN")
CHAT_ID = os.getenv("TG_CHAT")

SYMBOL = "BTC/USDT:USDT"
TIMEFRAME = "5m"

# =====================
# 🌐 PROXY
# =====================
proxy = "http://bwfwxtag:l64c0islq59i@31.59.20.176:6754"

# =====================
# 🔌 EXCHANGE
# =====================
exchange = ccxt.bitget({
    "apiKey": API_KEY,
    "secret": API_SECRET,
    "password": API_PASS,
    "enableRateLimit": True,
    "options": {"defaultType": "swap"},
    "proxies": {
        "http": proxy,
        "https": proxy
    }
})

# =====================
# 📩 TELEGRAM
# =====================
def send(msg):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": CHAT_ID, "text": msg})
    except:
        print("Telegram hata")

# =====================
# 📊 VERİ ÇEK
# =====================
def get_data():
    try:
        ohlcv = exchange.fetch_ohlcv(SYMBOL, TIMEFRAME, limit=100)
        df = pd.DataFrame(ohlcv, columns=["time","open","high","low","close","volume"])
        return df
    except Exception as e:
        print("❌ veri alınamadı:", e)
        return None

# =====================
# 🧠 AI ANALİZ
# =====================
def analyze(df):
    df["ema"] = df["close"].ewm(span=20).mean()
    df["rsi"] = 100 - (100 / (1 + df["close"].pct_change().rolling(14).mean()))

    last = df.iloc[-1]

    trend = "LONG" if last["close"] > last["ema"] else "SHORT"
    strength = abs(last["close"] - last["ema"])

    confidence = min(100, strength * 1000)

    return trend, confidence

# =====================
# 💰 TRADE
# =====================
def trade(signal, price):
    size = 10  # USDT

    tp = price * 1.01 if signal == "LONG" else price * 0.99
    sl = price * 0.98 if signal == "LONG" else price * 1.02

    msg = f"""
💀 V13000 AI TRADE

📊 {SYMBOL}
📈 Sinyal: {signal}
💰 Fiyat: {price}

🎯 TP: {tp}
🛑 SL: {sl}
"""

    print(msg)
    send(msg)

# =====================
# 🚀 MAIN LOOP
# =====================
def run():
    print("💀 V13000 FINAL AKTİF")

    while True:
        df = get_data()

        if df is None:
            print("❌ veri yok → bekleniyor...")
            time.sleep(10)
            continue

        trend, confidence = analyze(df)
        price = df["close"].iloc[-1]

        print(f"🔍 {SYMBOL} → {trend} ({confidence:.2f})")

        if confidence > 5:
            trade(trend, price)

        time.sleep(20)

# =====================
# START
# =====================
run()
