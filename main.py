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
    bot.send_message(MY_CHAT_ID, "🧪 **TP/SL TESTİ BAŞLADI:** Bir saniye içinde işlem açılacak...")
    
    try:
        # 1. Test için uygun bir koin seç (BTC/ETH hariç rastgele biri)
        tickers = ex.fetch_tickers()
        symbol = [s for s in tickers if '/USDT:USDT' in s and 'BTC' not in s and 'ETH' not in s][0]
        
        price = tickers[symbol]['last']
        amt = (5.0 * 10) / price # 5 USDT x 10 Kaldıraç
        
        # Test için çok dar hedefler (%0.5)
        sl = price * 0.995 # %0.5 Stop
        tp = price * 1.005 # %0.5 TP
        
        ex.set_leverage(10, symbol)
        
        # 2. MARKET GİRİŞ (Alış)
        order = ex.create_order(symbol, 'market', 'buy', amt)
        bot.send_message(MY_CHAT_ID, f"✅ Giriş Başarılı: {symbol}\nŞimdi TP/SL gönderiliyor...")
        
        time.sleep(2) # Borsanın pozisyonu işlemesi için kısa bekleme

        # 3. TP ve SL EMİRLERİ (Bitget Tetikleyici/Planlı Emir Yapısı)
        # Zarar Durdur
        ex.create_order(symbol, 'limit', 'sell', amt, None, {
            'stopPrice': sl,
            'triggerType': 'market',
            'reduceOnly': True
        })
        
        # Kâr Al
        ex.create_order(symbol, 'limit', 'sell', amt, None, {
            'stopPrice': tp,
            'triggerType': 'market',
            'reduceOnly': True
        })
        
        msg = (f"🎯 **TEST TAMAMLANDI!**\n\n"
               f"Lütfen Bitget uygulamasında şuraya bak:\n"
               f"1. **Açık Pozisyonlar:** İşlemi gör.\n"
               f"2. **Planlı Emirler (Trigger/Plan Orders):** Burada SL ({sl:.4f}) ve TP ({tp:.4f}) emirlerini görmelisin.")
        bot.send_message(MY_CHAT_ID, msg)

    except Exception as e:
        bot.send_message(MY_CHAT_ID, f"❌ TEST HATASI: {e}")

if __name__ == "__main__":
    test_run()
