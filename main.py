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

# --- [2. BAKİYE KOMUTU - TAMİR EDİLDİ] ---
@bot.message_handler(commands=['bakiye'])
def get_balance(message):
    try:
        # Bakiye çekme yöntemini güncelledim
        bal = ex.fetch_balance({'type': 'swap'})
        total = bal['info']['data']['available'] if 'available' in bal['info']['data'] else bal['total']['USDT']
        bot.reply_to(message, f"💰 **Güncel Bakiye:** {total} USDT") [cite: 2026-02-12]
    except Exception as e:
        bot.reply_to(message, f"⚠️ Bakiye Hatası: {e}")

@bot.message_handler(commands=['durum'])
def get_status(message):
    bot.reply_to(message, "📡 Radar Aktif\n📈 İşlem Taranıyor...")

# --- [3. DENEMELİK İŞLEM AÇICI (TEST)] ---
def open_test_trade():
    """Bot başlar başlamaz bir işlem açmayı dener."""
    try:
        symbol = 'DOGE/USDT:USDT' # Örnek test koini
        p = float(ex.fetch_ticker(symbol)['last'])
        amt = (10.0 * 10) / p # 10 USDT'lik 10x işlem
        ex.set_leverage(10, symbol)
        ex.create_order(symbol, 'market', 'buy', amt, params={'posSide': 'long', 'tdMode': 'isolated'})
        bot.send_message(MY_CHAT_ID, f"🧪 **TEST İŞLEMİ AÇILDI!**\nKoin: {symbol}\nFiyat: {p}") [cite: 2026-02-12]
    except Exception as e:
        bot.send_message(MY_CHAT_ID, f"⚠️ Test İşlemi Açılamadı: {e}")

# --- [4. ANA RADAR DÖNGÜSÜ] ---
def main_loop():
    # TEST İŞLEMİNİ BAŞLAT
    open_test_trade()
    
    while True:
        # (Burada V22'deki tarama ve monitor fonksiyonları aynen devam edecek)
        # ... [cite: 2026-02-14]
        time.sleep(10)

if __name__ == "__main__":
    # Bakiye ve komutların donmaması için polling en üstte çalışmalı
    threading.Thread(target=main_loop, daemon=True).start()
    bot.infinity_polling(timeout=20)
