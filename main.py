import os, time, ccxt, telebot
import pandas as pd

# ===== TELEGRAM =====
TOKEN = os.getenv("TELE_TOKEN")
CHAT_ID = os.getenv("MY_CHAT_ID")

bot = telebot.TeleBot(TOKEN) if TOKEN else None

def send(msg):
    try:
        if bot and CHAT_ID:
            bot.send_message(CHAT_ID, msg)
            print("📩 gönderildi")
        else:
            print("Telegram yok:", msg)
    except Exception as e:
        print("Telegram hata:", e)

# ===== EXCHANGE =====
exchange = ccxt.bitget({
    "apiKey": os.getenv("BITGET_API"),
    "secret": os.getenv("BITGET_SEC"),
    "password": os.getenv("BITGET_PASS"),
    "options": {"defaultType": "swap"},
    "enableRateLimit": True
})

SYMBOL = "BTC/USDT:USDT"

# ===== DATA =====
def get_data():
    try:
        ohlcv = exchange.fetch_ohlcv(SYMBOL, "5m", limit=50)

        if not ohlcv or len(ohlcv) == 0:
            return None

        df = pd.DataFrame(ohlcv, columns=["t","o","h","l","c","v"])

        if len(df) < 5:
            return None

        return df

    except Exception as e:
        print("Veri hata:", e)
        return None

# ===== ANALİZ (CRASH FIX) =====
def analyze(df):
    try:
        if df is None or len(df) < 5:
            return None, None

        df["ema"] = df["c"].ewm(span=20).mean()

        last = df.iloc[-1]

        trend = "LONG" if last["c"] > last["ema"] else "SHORT"
        price = float(last["c"])

        return trend, price

    except Exception as e:
        print("Analyze hata:", e)
        return None, None

# ===== TRADE =====
last_signal = None

def check_trade(signal, price):
    global last_signal

    if signal is None:
        return

    if signal == last_signal:
        return

    last_signal = signal

    msg = f"""
💀 TRADE

📊 {SYMBOL}
📈 {signal}
💰 {price}
"""
    print(msg)
    send(msg)

# ===== MAIN =====
def run():
    print("💀 BOT AKTİF")

    while True:
        try:
            df = get_data()

            if df is None:
                print("❌ veri yok → bekleniyor")
                time.sleep(10)
                continue

            signal, price = analyze(df)

            if signal is None:
                print("❌ analiz yok")
                time.sleep(5)
                continue

            print("🔍", signal, price)

            check_trade(signal, price)

            time.sleep(20)

        except Exception as e:
            print("💀 CRASH ENGELLENDİ:", e)
            time.sleep(5)

# ===== START =====
run()
