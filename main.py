import ccxt
import telebot
import time
import os
import threading

# --- [BAĞLANTILAR] ---
MEXC_API = os.getenv('MEXC_API')
MEXC_SEC = os.getenv('MEXC_SEC')
TELE_TOKEN = os.getenv('TELE_TOKEN')
MY_CHAT_ID = os.getenv('MY_CHAT_ID')

ex = ccxt.mexc({
    'apiKey': MEXC_API, 
    'secret': MEXC_SEC, 
    'options': {'defaultType': 'swap'}, 
    'enableRateLimit': True
})
bot = telebot.TeleBot(TELE_TOKEN)

# --- [KOMUTLAR] ---
@bot.message_handler(commands=['bakiye'])
def check_balance(message):
    try:
        # Chat ID doğrulaması
        if str(message.chat.id) != str(MY_CHAT_ID):
            return
        
        balance = ex.fetch_balance()
        usdt = balance['total'].get('USDT', 0)
        bot.reply_to(message, f"💰 **Güncel Kasa:** {usdt:.2f} USDT\n📡 Radar çalışıyor, sinyal bekleniyor.")
    except Exception as e:
        bot.reply_to(message, f"❌ Bakiye çekilemedi: {str(e)}")

def main_worker():
    # Başlangıç mesajı
    try:
        bot.send_message(MY_CHAT_ID, "🚀 Sadık Bey, Bot bakiye ve işlem yetkileriyle aktif edildi!")
    except:
        print("Telegram ID veya Token hatalı!")

    while True:
        # Buraya sinyal tarama döngüsü gelecek (önceki kodlardaki gibi)
        time.sleep(30)

if __name__ == "__main__":
    # Döngüyü ayrı bir kolda başlat
    t = threading.Thread(target=main_worker)
    t.daemon = True
    t.start()
    
    # Telegram'ı ana kolda çalıştır (Komutlara anında cevap vermesi için)
    bot.infinity_polling()
