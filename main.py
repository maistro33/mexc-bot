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
    bot.send_message(MY_CHAT_ID, "🛠️ **V2 PROTOKOLÜ:** Pozisyon bazlı TP/SL yükleniyor...")
    
    try:
        # 1. Pozisyon Kontrolü
        pos = ex.fetch_positions()
        if any(float(p['contracts']) > 0 for p in pos):
            bot.send_message(MY_CHAT_ID, "❌ Lütfen açık işlemi kapatıp öyle başlat.")
            return

        symbol = 'SOL/USDT:USDT'
        price = ex.fetch_ticker(symbol)['last']
        amt = (10.0 * 10) / price 
        
        # Fiyatları yuvarlamak Bitget için kritiktir
        sl = round(price * 0.98, 4) # %2 Stop
        tp = round(price * 1.04, 4) # %4 TP
        
        ex.set_leverage(10, symbol)
        
        # 2. POZİSYONU AÇ
        bot.send_message(MY_CHAT_ID, f"🚀 {symbol} LONG açılıyor...")
        ex.create_order(symbol, 'market', 'buy', amt, params={'posSide': 'long'})
        
        time.sleep(3) # Pozisyonun borsaya düşmesi için bekle

        # 3. POZİSYON BAZLI TP/SL (Bu metod hata payını sıfırlar)
        # Bitget V2 API formatına uygun özel gönderim:
        try:
            ex.private_post_v2_mix_order_batch_create_tpsl_order({
                'symbol': symbol.replace('/USDT:USDT', 'USDT'), # SOLUSDT formatı
                'productType': 'usdt-futures',
                'marginCoin': 'USDT',
                'planType': 'pos_tpsl', # Pozisyon bazlı TP/SL
                'holdSide': 'long',
                'takeProfitPrice': str(tp),
                'stopLossPrice': str(sl)
            })
            bot.send_message(MY_CHAT_ID, f"✅ **TP/SL YÜKLENDİ!**\nTP: {tp}\nSL: {sl}")
        except Exception as e:
            # Eğer V2 özel metod hata verirse, standart CCXT set_margin_mode üzerinden dene
            ex.set_margin_mode('crossed', symbol)
            ex.edit_order(None, symbol, 'market', 'buy', amt, params={
                'stopLossPrice': sl,
                'takeProfitPrice': tp,
                'posSide': 'long'
            })
            bot.send_message(MY_CHAT_ID, "⚠️ Alternatif yöntemle TP/SL denendi.")

        bot.send_message(MY_CHAT_ID, "🏁 Kontrol et, şimdi dolmuş olmalı!")

    except Exception as e:
        bot.send_message(MY_CHAT_ID, f"❌ SİSTEM HATASI: {e}")

if __name__ == "__main__":
    test_run()
