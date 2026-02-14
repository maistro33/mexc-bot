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
    bot.send_message(MY_CHAT_ID, "🛠️ **KESİN ÇÖZÜM MODU:** TP ve SL pozisyonun içine tek tek işleniyor...")
    
    try:
        # 1. Açık işlem varsa yeni açma (Bakiye koruması)
        pos = ex.fetch_positions()
        active = [p for p in pos if float(p['contracts']) > 0]
        if len(active) > 0:
            bot.send_message(MY_CHAT_ID, "❌ **DUR:** Mevcut işlemin var. Lütfen onu kapatıp kodu tekrar başlat.")
            return

        symbol = 'SOL/USDT:USDT'
        price = ex.fetch_ticker(symbol)['last']
        amt = (10.0 * 10) / price # 10 USDT bakiye x 10 kaldıraç
        
        sl = round(price * 0.985, 4) # %1.5 Stop
        tp = round(price * 1.03, 4)  # %3 TP
        
        ex.set_leverage(10, symbol)
        
        # 2. POZİSYONU AÇ
        bot.send_message(MY_CHAT_ID, f"🚀 {symbol} LONG açılıyor...")
        ex.create_order(symbol, 'market', 'buy', amt, params={'posSide': 'long'})
        
        # Borsanın pozisyonu görmesi için bekliyoruz
        time.sleep(3) 

        # 3. ÖNCE STOP LOSS'U POZİSYONUN İÇİNE GÖM
        try:
            ex.create_order(symbol, 'market', 'sell', amt, params={
                'stopLossPrice': sl,
                'posSide': 'long',
                'reduceOnly': True
            })
            bot.send_message(MY_CHAT_ID, f"🛑 **SL BAŞARIYLA EKLENDİ:** {sl}")
        except Exception as e:
            bot.send_message(MY_CHAT_ID, f"⚠️ SL Hatası: {e}")

        time.sleep(1.5)

        # 4. SONRA TAKE PROFIT'İ POZİSYONUN İÇİNE GÖM
        try:
            ex.create_order(symbol, 'market', 'sell', amt, params={
                'takeProfitPrice': tp,
                'posSide': 'long',
                'reduceOnly': True
            })
            bot.send_message(MY_CHAT_ID, f"✅ **TP BAŞARIYLA EKLENDİ:** {tp}")
        except Exception as e:
            bot.send_message(MY_CHAT_ID, f"⚠️ TP Hatası: {e}")

        bot.send_message(MY_CHAT_ID, "🏁 **İŞLEM TAMAM:** Şimdi pozisyonun içine bak, rakamları orada görmelisin!")

    except Exception as e:
        bot.send_message(MY_CHAT_ID, f"❌ KRİTİK SİSTEM HATASI: {e}")

if __name__ == "__main__":
    test_run()
