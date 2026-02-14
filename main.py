import ccxt
import os
import telebot
import time

# --- [BAĞLANTILAR] ---
ex = ccxt.bitget({
    'apiKey': os.getenv('BITGET_API'), 
    'secret': os.getenv('BITGET_SEC'), 
    'password': os.getenv('BITGET_PASSPHRASE'),
    'options': {'defaultType': 'swap'}, 
    'enableRateLimit': True
})
bot = telebot.TeleBot(os.getenv('TELE_TOKEN'))
MY_CHAT_ID = os.getenv('MY_CHAT_ID')

def test_run():
    bot.send_message(MY_CHAT_ID, "🛠️ **V4 SON DENEME:** Emirler tek tek ve gecikmeli gidiyor...")
    
    try:
        symbol = 'SOL/USDT:USDT'
        price = ex.fetch_ticker(symbol)['last']
        amt = (10.0 * 10) / price 
        
        sl = round(price * 0.98, 4)
        tp = round(price * 1.05, 4)
        
        ex.set_leverage(10, symbol)
        
        # 1. ADIM: POZİSYONU AÇ
        ex.create_order(symbol, 'market', 'buy', amt, params={'posSide': 'long'})
        bot.send_message(MY_CHAT_ID, "🚀 Pozisyon açıldı. 5 saniye bekleniyor...")
        
        time.sleep(5) # Borsanın kendine gelmesi için uzun süre

        # 2. ADIM: SADECE STOP LOSS GÖNDER
        try:
            ex.create_order(symbol, 'market', 'sell', amt, params={
                'stopLossPrice': sl,
                'posSide': 'long'
            })
            bot.send_message(MY_CHAT_ID, f"🛑 SL eklendi: {sl}")
        except Exception as e:
            bot.send_message(MY_CHAT_ID, f"❌ SL Hatası: {e}")

        time.sleep(2) # İki emir çakışmasın diye bekleme

        # 3. ADIM: SADECE TAKE PROFIT GÖNDER
        try:
            ex.create_order(symbol, 'market', 'sell', amt, params={
                'takeProfitPrice': tp,
                'posSide': 'long'
            })
            bot.send_message(MY_CHAT_ID, f"✅ TP eklendi: {tp}")
        except Exception as e:
            bot.send_message(MY_CHAT_ID, f"❌ TP Hatası: {e}")

    except Exception as e:
        bot.send_message(MY_CHAT_ID, f"⚠️ Genel Hata: {e}")

if __name__ == "__main__":
    test_run()
