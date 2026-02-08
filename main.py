import ccxt
import telebot
import time
import os
import threading

# --- [BAĞLANTILAR] ---
# Not: Bilgileri os.getenv ile çekemiyorsan doğrudan tırnak içine yazabilirsin.
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

# --- [ANINDA TEST AYARI] ---
CONFIG = {
    'trade_amount': 20.0,
    'leverage': 10,
    'symbol': 'SOL/USDT:USDT'
}

def instant_trade_test():
    symbol = CONFIG['symbol']
    bot.send_message(MY_CHAT_ID, f"🚀 **ATEŞLEME TESTİ BAŞLADI:** {symbol} için market emri gönderiliyor...")
    
    try:
        # 1. Kaldıraç ve Marjin Ayarı (Hata Düzeltildi)
        # openType 1: Isolated (İzole), positionType 1: Long
        ex.set_leverage(CONFIG['leverage'], symbol, {
            'openType': 1,     
            'positionType': 1  
        })

        # 2. Miktar Hesaplama
        ticker = ex.fetch_ticker(symbol)
        price = ticker['last']
        amount = (CONFIG['trade_amount'] * CONFIG['leverage']) / price
        
        # 3. PİYASA EMRİ GÖNDER
        order = ex.create_market_order(symbol, 'buy', amount)
        
        bot.send_message(MY_CHAT_ID, f"✅ **İŞLEM BAŞARIYLA AÇILDI!**\n\nBorsayı kontrol et, SOL pozisyonunu gördüğünde botu durdur. Hemen ardından asıl strateji koduna geçelim.")
        print("Test başarılı, borsa emri kabul etti.")

    except Exception as e:
        # Eğer hala hata verirse burası detaylı mesaj gönderecek
        error_msg = str(e)
        bot.send_message(MY_CHAT_ID, f"❌ **Hala Erişim Sorunu Var:**\n{error_msg}")
        print(f"Hata: {error_msg}")

if __name__ == "__main__":
    # Döngü yok, sadece bir kez dener
    instant_trade_test()
