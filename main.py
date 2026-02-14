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

def virtual_trade():
    bot.send_message(MY_CHAT_ID, "🛡️ **SANAL TAKİP MODU AKTİF:** Bot fiyatı izliyor, borsa emri beklenmiyor...")
    
    try:
        symbol = 'SOL/USDT:USDT'
        ticker = ex.fetch_ticker(symbol)
        entry_price = ticker['last']
        amt = (10.0 * 10) / entry_price 
        
        # Hedefler
        sl_level = round(entry_price * 0.985, 4) # %1.5 Zarar Kes
        tp_level = round(entry_price * 1.03, 4)  # %3 Kar Al
        
        ex.set_leverage(10, symbol)
        
        # 1. Pozisyonu Aç
        ex.create_order(symbol, 'market', 'buy', amt, params={'posSide': 'long'})
        bot.send_message(MY_CHAT_ID, f"🚀 Giriş yapıldı: {entry_price}\n🎯 TP: {tp_level}\n🛑 SL: {sl_level}\nBot nöbete başladı...")

        # 2. Takip Döngüsü (Bot burada bekçilik yapar)
        while True:
            try:
                current_ticker = ex.fetch_ticker(symbol)
                current_price = current_ticker['last']
                
                # Kar Al Kontrolü
                if current_price >= tp_level:
                    ex.create_order(symbol, 'market', 'sell', amt, params={'posSide': 'long', 'reduceOnly': True})
                    bot.send_message(MY_CHAT_ID, f"✅ **KAR ALINDI!** Fiyat: {current_price}\nİşlem bot tarafından kapatıldı.")
                    break
                
                # Zarar Kes Kontrolü
                if current_price <= sl_level:
                    ex.create_order(symbol, 'market', 'sell', amt, params={'posSide': 'long', 'reduceOnly': True})
                    bot.send_message(MY_CHAT_ID, f"🛑 **STOP OLUNDU!** Fiyat: {current_price}\nZarar kesildi.")
                    break
                
                # Her 5 saniyede bir kontrol et (Borsayı yormadan)
                time.sleep(5)
                
            except Exception as e:
                print(f"Döngü hatası: {e}")
                time.sleep(10)

    except Exception as e:
        bot.send_message(MY_CHAT_ID, f"❌ HATA: {e}")

if __name__ == "__main__":
    virtual_trade()
