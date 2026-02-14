import ccxt
import os
import telebot

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
    print("🚀 TEST BAŞLADI...")
    bot.send_message(MY_CHAT_ID, "🧪 **TEST BAŞLADI:** Hemen bir işlem açılıyor...")
    
    try:
        # En hacimli ilk koini seç (Hızlı test için)
        tickers = ex.fetch_tickers()
        symbol = [s for s in tickers if '/USDT:USDT' in s and 'BTC' not in s][0]
        
        price = tickers[symbol]['last']
        amt = (5.0 * 10) / price # 5 USDT x 10 Kaldıraç
        
        # Test için dar limitler
        sl = price * 0.99  # %1 Stop
        tp = price * 1.01  # %1 TP
        
        ex.set_leverage(10, symbol)
        
        # 1. Market Giriş
        order = ex.create_order(symbol, 'market', 'buy', amt)
        print(f"✅ Giriş Yapıldı: {symbol}")
        
        # 2. TP ve SL Emirleri
        ex.create_order(symbol, 'market', 'sell', amt, params={
            'stopLossPrice': sl, 
            'takeProfitPrice': tp
        })
        
        msg = (f"🎯 **TEST İŞLEMİ AÇILDI!**\n"
               f"Koin: {symbol}\n"
               f"Giriş: {price}\n"
               f"🛑 SL: {sl:.4f}\n"
               f"✅ TP: {tp:.4f}\n\n"
               f"Şimdi borsadan (Bitget) açık emirlerini kontrol et!")
        bot.send_message(MY_CHAT_ID, msg)
        print("🚀 TEST BAŞARIYLA TAMAMLANDI. Bot duruyor.")

    except Exception as e:
        bot.send_message(MY_CHAT_ID, f"❌ TEST HATASI: {e}")
        print(f"Hata: {e}")

if __name__ == "__main__":
    test_run()
