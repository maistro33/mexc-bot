import ccxt
import telebot
import time
import os
import threading

# --- [BAĞLANTILAR] ---
# Buradaki değişkenleri ortam değişkenlerinden veya doğrudan tırnak içine yazarak doldurabilirsin
MEXC_API = os.getenv('MEXC_API')
MEXC_SEC = os.getenv('MEXC_SEC')
TELE_TOKEN = os.getenv('TELE_TOKEN')
MY_CHAT_ID = os.getenv('MY_CHAT_ID')

# Borsaya Bağlan
ex = ccxt.mexc({
    'apiKey': MEXC_API, 
    'secret': MEXC_SEC, 
    'options': {'defaultType': 'swap'}, 
    'enableRateLimit': True
})
bot = telebot.TeleBot(TELE_TOKEN)

# --- [TEST AYARLARI] ---
CONFIG = {
    'trade_amount': 20.0,           # İşlem tutarı (USDT)
    'leverage': 10,                 # Kaldıraç
    'symbol': 'SOL/USDT:USDT'       # Test için kullanılacak koin
}

def instant_trade_test():
    symbol = CONFIG['symbol']
    bot.send_message(MY_CHAT_ID, f"🚀 TEST BAŞLATILDI: {symbol} için anında işlem açılıyor...")
    
    try:
        # 1. Kaldıraç ve Margin Tipi Ayarı (Hata Düzeltildi)
        # openType 1: İzole, positionType 1: Long
        ex.set_leverage(CONFIG['leverage'], symbol, {
            'openType': 1,     
            'positionType': 1  
        })
        print(f"✅ Kaldıraç {CONFIG['leverage']}x olarak ayarlandı.")

        # 2. Güncel Fiyatı Al ve Miktarı Hesapla
        ticker = ex.fetch_ticker(symbol)
        price = ticker['last']
        # Miktar = (Para x Kaldıraç) / Fiyat
        amount = (CONFIG['trade_amount'] * CONFIG['leverage']) / price
        
        # 3. PİYASA EMRİ (MARKET ORDER) GÖNDER
        print(f"🛒 {amount} adet için alım emri gönderiliyor...")
        order = ex.create_market_order(symbol, 'buy', amount)
        
        # 4. BİLGİLENDİRME
        msg = (f"✅ **TEST BAŞARILI!**\n\n"
               f"🪙 **Koin:** {symbol}\n"
               f"💰 **Giriş Fiyatı:** {price}\n"
               f"↕️ **Yön:** LONG (Alış)\n\n"
               f"Borsayı kontrol et. Pozisyon açıldıysa botu durdurup asıl koda geçebiliriz.")
        bot.send_message(MY_CHAT_ID, msg)
        print("İşlem başarıyla gerçekleşti.")

    except Exception as e:
        error_msg = f"❌ Test Hatası: {str(e)}"
        print(error_msg)
        bot.send_message(MY_CHAT_ID, error_msg)

if __name__ == "__main__":
    # Döngüye girmeden sadece bir kez çalıştırır
    instant_trade_test()
