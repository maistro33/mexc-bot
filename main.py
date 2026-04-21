import ccxt
import pandas as pd
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
# 🌐 PROXY (SADECE BITGET)
# =====================
proxy = "http://bwfwxtag:l64c0islq59i@31.59.20.176:6754"

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
# 📩 TELEGRAM (ULTRA FIX)
# =====================
def send(msg):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

        session = requests.Session()
        session.trust_env = False  # 💀 ENV proxy tamamen kapat

        response = session.post(
            url,
            data={
                "chat_id": CHAT_ID,
                "text": msg
            },
            timeout=10
        )

        print("📩 Telegram gönderildi:", response.status_code)

    except Exception as e:
        print("❌ Telegram hata:", e)

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
# 🧠 ANALİZ
# =====================
def analyze(df):
    df["ema"] = df["close"].ewm(span=20).mean()

    delta = df["close"].diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss
    df["rsi"] = 100 - (100 / (1 + rs))

    last = df.iloc[-1]

    trend = "LONG" if last["close"] > last["ema"] else "SHORT"

    strength = abs(last["close"] - last["ema"]) / last["close"]
    confidence = min(100, strength * 10000)

    return trend, confidence

# =====================
# 💰 TRADE (SPAM ENGEL)
# =====================
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

# =====================
# 🚀 MAIN
# =====================
def run():
    print("💀 V13000 FINAL AKTİF")

    send("🚀 BOT BAŞLADI")  # 🔥 TEST

    while True:
        df = get_data()

        if df is None:
            print("❌ veri yok")
            time.sleep(10)
            continue

        trend, confidence = analyze(df)
        price = df["close"].iloc[-1]

        print(f"🔍 {SYMBOL} → {trend} ({confidence:.2f})")

        if confidence > 10:
            trade(trend, price, confidence)

        time.sleep(20)

# =====================
# START
# =====================
run()
