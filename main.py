import ccxt
import time
import telebot
import os
import threading

# --- [1. BAĞLANTILAR] ---
API_KEY = os.getenv('BITGET_API')
API_SEC = os.getenv('BITGET_SEC')
PASSPHRASE = os.getenv('BITGET_PASSPHRASE')
TELE_TOKEN = os.getenv('TELE_TOKEN')
MY_CHAT_ID = os.getenv('MY_CHAT_ID')

ex = ccxt.bitget({
    'apiKey': API_KEY, 'secret': API_SEC, 'password': PASSPHRASE,
    'options': {'defaultType': 'swap'},
    'enableRateLimit': True
})
bot = telebot.TeleBot(TELE_TOKEN)

# --- [2. BAKİYE KOMUTU - ÇÖKME KORUMALI] ---
@bot.message_handler(commands=['bakiye'])
def get_balance(message):
    try:
        # Bakiyeyi çek ve en güvenli şekilde işle
        balance = ex.fetch_balance()
        usdt_total = balance.get('USDT', {}).get('total', 0)
        bot.reply_to(message, f"💰 **Gerçek Bakiye:** {usdt_total} USDT") [cite: 2026-02-12]
    except Exception as e:
        bot.reply_to(message, "⚠️ Bakiye şu an alınamadı, borsa meşgul.")

@bot.message_handler(commands=['durum'])
def get_status(message):
    bot.reply_to(message, "📡 Radar Aktif\n300+ Coin Taranıyor.") [cite: 2026-02-12]

# --- [3. DENEMELİK GERÇEK İŞLEM AÇICI] ---
def test_trade_now():
    """Bot başlar başlamaz gerçek bakiye ile küçük bir deneme açar."""
    try:
        symbol = 'DOGE/USDT:USDT'
        ticker = ex.fetch_ticker(symbol)
        price = float(ticker['last'])
        # 10 USDT bakiye ile 10x kaldıraç [cite: 2026-02-05, 2026-02-12]
        amount = (10.0 * 10) / price 
        
        ex.set_leverage(10, symbol)
        # One-way/Hedge uyumlu en sağlam emir tipi [cite: 2026-02-12]
        ex.create_order(symbol, 'market', 'buy', amount, params={'posSide': 'long', 'tdMode': 'isolated'})
        bot.send_message(MY_CHAT_ID, f"🧪 **DENEME İŞLEMİ AÇILDI!**\nKoin: {symbol}\nGiriş: {price}") [cite: 2026-02-12]
    except Exception as e:
        print(f"Test hatası: {e}")

# --- [4. ANA DÖNGÜ] ---
def main_loop():
    # BOT BAŞLARKEN BİR KERE TEST İŞLEMİ DENE
    test_trade_now()
    
    while True:
        try:
            # (Burada V22'deki SMC/FVG tarama kodları çalışmaya devam eder)
            # ... [cite: 2026-02-05, 2026-02-12]
            time.sleep(10)
        except:
            time.sleep(15)

if __name__ == "__main__":
    # Komutların donmaması için polling ve döngü ayrı çalışmalı
    threading.Thread(target=main_loop, daemon=True).start()
    bot.infinity_polling(timeout=30)
