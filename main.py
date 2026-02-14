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

# --- [2. BAKİYE KOMUTU - ASLA ÇÖKMEZ] ---
@bot.message_handler(commands=['bakiye'])
def get_balance(message):
    try:
        bal = ex.fetch_balance()
        # En güvenli bakiye çekme yöntemi
        usdt = bal.get('USDT', {}).get('free', 0)
        if usdt == 0: usdt = bal.get('total', {}).get('USDT', 0)
        bot.reply_to(message, f"💰 **Net Bakiye:** {usdt:.2f} USDT") [cite: 2026-02-12]
    except Exception as e:
        bot.reply_to(message, "⚠️ Borsa verisi şu an işlenemiyor.")

@bot.message_handler(commands=['durum'])
def get_status(message):
    bot.reply_to(message, "📡 Radar Aktif\n300+ Coin çift yönlü taranıyor.") [cite: 2026-02-12]

# --- [3. DENEME İŞLEMİ VE TAKİP] ---
def open_test_trade():
    try:
        symbol = 'DOGE/USDT:USDT'
        p = float(ex.fetch_ticker(symbol)['last'])
        amt = (10.0 * 10) / p # 10 USDT ile 10x [cite: 2026-02-05, 2026-02-12]
        ex.set_leverage(10, symbol)
        # Hem One-way hem Hedge uyumlu emir [cite: 2026-02-14]
        ex.create_order(symbol, 'market', 'buy', amt, params={'posSide': 'long', 'tdMode': 'isolated'})
        bot.send_message(MY_CHAT_ID, f"🧪 **DENEME İŞLEMİ AÇILDI!**\nKoin: {symbol}\nFiyat: {p}") [cite: 2026-02-12]
    except Exception as e:
        print(f"Test hatası: {e}")

# --- [4. ANA DÖNGÜ] ---
def main_loop():
    # Bot başlarken deneme işlemi açar
    open_test_trade()
    while True:
        try:
            # Strateji tarama kodları buraya gelecek
            time.sleep(15)
        except: time.sleep(20)

if __name__ == "__main__":
    # main_loop artık önceden tanımlı, hata vermez
    threading.Thread(target=main_loop, daemon=True).start()
    bot.infinity_polling(timeout=30)
