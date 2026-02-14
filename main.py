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
    bot.send_message(MY_CHAT_ID, "🚀 **SON NOKTA TESTİ:** Planlı Emirler protokolü...")
    
    try:
        symbol = 'SOL/USDT:USDT'
        price = ex.fetch_ticker(symbol)['last']
        amt = (10.0 * 10) / price 
        
        sl = round(price * 0.98, 4)
        tp = round(price * 1.05, 4)
        
        ex.set_leverage(10, symbol)
        
        # 1. ADIM: POZİSYONU AÇ
        # Sadece giriş emri gönderiyoruz, içine hiçbir TP/SL karıştırmıyoruz.
        ex.create_order(symbol, 'market', 'buy', amt, params={'posSide': 'long'})
        bot.send_message(MY_CHAT_ID, "📈 Pozisyon açıldı. Planlı emirler yükleniyor...")
        
        time.sleep(3)

        # 2. ADIM: STOP LOSS (PLANLI EMİR OLARAK)
        # Bitget'in reddedemeyeceği 'trigger' formatı:
        try:
            ex.create_order(symbol, 'limit', 'sell', amt, None, {
                'stopPrice': sl,
                'triggerType': 'market',
                'posSide': 'long',
                'reduceOnly': True
            })
            bot.send_message(MY_CHAT_ID, f"🛑 SL Planlı Emirlere Eklendi: {sl}")
        except Exception as e:
            bot.send_message(MY_CHAT_ID, f"⚠️ SL Hatası: {e}")

        time.sleep(1)

        # 3. ADIM: TAKE PROFIT (PLANLI EMİR OLARAK)
        try:
            ex.create_order(symbol, 'limit', 'sell', amt, None, {
                'stopPrice': tp,
                'triggerType': 'market',
                'posSide': 'long',
                'reduceOnly': True
            })
            bot.send_message(MY_CHAT_ID, f"✅ TP Planlı Emirlere Eklendi: {tp}")
        except Exception as e:
            bot.send_message(MY_CHAT_ID, f"⚠️ TP Hatası: {e}")

    except Exception as e:
        bot.send_message(MY_CHAT_ID, f"❌ SİSTEM HATASI: {e}")

if __name__ == "__main__":
    test_run()
