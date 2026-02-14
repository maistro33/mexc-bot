import ccxt
import os
import telebot
import time

# --- [BAĞLANTILAR] ---
API_KEY = os.getenv('BITGET_API')
API_SEC = os.getenv('BITGET_SEC')
PASSPHRASE = os.getenv('BITGET_PASSPHRASE')
TELE_TOKEN = os.getenv('TELE_TOKEN')
MY_CHAT_ID = os.getenv('MY_CHAT_ID')

ex = ccxt.bitget({
    'apiKey': API_KEY, 'secret': API_SEC, 'password': PASSPHRASE,
    'options': {'defaultType': 'swap'}, 'enableRateLimit': True
})
bot = telebot.TeleBot(TELE_TOKEN)

def test_run():
    bot.send_message(MY_CHAT_ID, "⚠️ **SON DENEME:** Bitget V2 Protokolü ile TP/SL yükleniyor...")
    
    try:
        # 1. Mevcut pozisyonları kontrol et (Üst üste açmayı önlemek için)
        pos = ex.fetch_positions()
        active = [p for p in pos if float(p['contracts']) > 0]
        if len(active) > 0:
            bot.send_message(MY_CHAT_ID, "❌ HATA: Zaten açık işlemin var. Lütfen kapatıp tekrar dene.")
            return

        # 2. Sembol seçimi
        symbol = 'SOL/USDT:USDT' # Test için sabit ve likit bir koin
        price = ex.fetch_ticker(symbol)['last']
        amt = (5.0 * 10) / price 
        
        sl = round(price * 0.985, 4) # %1.5 Stop
        tp = round(price * 1.03, 4)  # %3 TP
        
        ex.set_leverage(10, symbol)
        
        # 3. ANA GİRİŞ VE TP/SL'Yİ TEK PAKETTE GÖNDER (En Garanti Yol)
        # Bitget V2 API, giriş emriyle birlikte parametreleri bu formatta kabul eder
        params = {
            'stopLossPrice': sl,
            'takeProfitPrice': tp,
            'posSide': 'long',
            'holdSide': 'long',
            'mgnMode': 'crossed'
        }
        
        bot.send_message(MY_CHAT_ID, f"🚀 {symbol} girişi yapılıyor...")
        ex.create_order(symbol, 'market', 'buy', amt, None, params)
        
        bot.send_message(MY_CHAT_ID, f"🎯 **İŞLEM AÇILDI!**\nLütfen şimdi POZİSYONUN İÇİNE bak.\nEğer yine yoksa, Bitget 'Hedge Mode' ayarın API erişimini kısıtlıyor olabilir.")

    except Exception as e:
        bot.send_message(MY_CHAT_ID, f"❌ SİSTEM HATASI: {e}")

if __name__ == "__main__":
    test_run()
