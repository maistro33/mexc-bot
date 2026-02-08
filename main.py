import ccxt
import telebot
import time
import os
import threading

# --- [BAĞLANTILAR] ---
# Railway Variables kısmından çekilir
MEXC_API = os.getenv('MEXC_API')
MEXC_SEC = os.getenv('MEXC_SEC')
TELE_TOKEN = os.getenv('TELE_TOKEN')
MY_CHAT_ID = os.getenv('MY_CHAT_ID')

# Borsaya Bağlan (Vadeli İşlemler)
ex = ccxt.mexc({
    'apiKey': MEXC_API, 
    'secret': MEXC_SEC, 
    'options': {'defaultType': 'swap'}, 
    'enableRateLimit': True
})
bot = telebot.TeleBot(TELE_TOKEN)

def instant_trade():
    symbol = 'SOL/USDT:USDT'
    amount_usdt = 20.0
    leverage = 10
    
    try:
        # 1. Başlangıç Mesajı
        bot.send_message(MY_CHAT_ID, f"🚀 **TEST BAŞLADI:** {symbol} için anında emir gönderiliyor...")
        
        # 2. Kaldıraç Ayarı (MEXC'nin istediği zorunlu parametrelerle)
        # openType 1: Isolated, positionType 1: Long
        ex.set_leverage(leverage, symbol, {
            'openType': 1,     
            'positionType': 1  
        })
        
        # 3. Güncel Fiyat ve Miktar Hesabı
        ticker = ex.fetch_ticker(symbol)
        price = ticker['last']
        amount = (amount_usdt * leverage) / price
        
        # 4. MARKET EMRİ GÖNDER
        order = ex.create_market_order(symbol, 'buy', amount)
        
        # 5. BAŞARI MESAJI
        bot.send_message(MY_CHAT_ID, f"✅ **İŞLEM BAŞARIYLA AÇILDI!**\n💰 Giriş: {price}\n⚙️ Kaldıraç: {leverage}x\n\nBorsayı kontrol et ve pozisyonu manuel kapat.")
        
    except Exception as e:
        # Hata durumunda detaylı mesaj gönderir (403 vb.)
        bot.send_message(MY_CHAT_ID, f"❌ **İŞLEM HATASI:** {str(e)}")

# --- [KOMUTLAR] ---
@bot.message_handler(commands=['bakiye'])
def check_balance(message):
    try:
        balance = ex.fetch_balance()
        usdt = balance['total'].get('USDT', 0)
        bot.reply_to(message, f"💰 **Güncel Kasa:** {usdt:.2f} USDT")
    except Exception as e:
        bot.reply_to(message, f"❌ Hata: {str(e)}")

if __name__ == "__main__":
    # Bot başlar başlamaz işlemi dener
    instant_trade()
    
    # Komutları (bakiye vb.) dinlemeye başlar
    bot.infinity_polling()
