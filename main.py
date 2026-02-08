import ccxt
import telebot
import time
import os
import threading

# --- [BAĞLANTILAR] ---
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

CONFIG = {
    'trade_amount': 20.0,           # Test için 20 USDT
    'leverage': 10,                 
    'tp1_close_ratio': 0.75,        
    'symbols': ['SOL/USDT:USDT']    # Testi hızlıca görmek için SOL seçildi
}

# --- [TEST İÇİN BASİTLEŞTİRİLMİŞ SİNYAL] ---
def get_smc_signal(symbol):
    # STRATEJİ DEVRE DIŞI: Test için her zaman 'buy' döndürür
    ticker = ex.fetch_ticker(symbol)
    return 'buy', ticker['last']

# --- [ANA ÇALIŞMA DÖNGÜSÜ] ---
def main_worker():
    bot.send_message(MY_CHAT_ID, "🚀 TEST BAŞLATILDI: Koşul beklemeden işlem açılıyor...")
    
    for symbol in CONFIG['symbols']:
        side, price = get_smc_signal(symbol)
        if side:
            try:
                # Kaldıraç Ayarla
                ex.set_leverage(CONFIG['leverage'], symbol)
                
                # Miktarı Hesapla
                amount = (CONFIG['trade_amount'] * CONFIG['leverage']) / price
                
                # İŞLEMİ AÇ
                ex.create_market_order(symbol, side, amount)
                
                msg = (f"🎯 **TEST BAŞARILI, İŞLEM AÇILDI!**\n\n"
                       f"🪙 **Koin:** {symbol}\n"
                       f"💰 **Giriş:** {price}\n"
                       f"⚠️ Lütfen borsadan kontrol et ve işlemi manuel kapat.")
                bot.send_message(MY_CHAT_ID, msg)
                
                # İşlem açıldıktan sonra döngüyü kır (Sadece 1 işlem için)
                return 
            except Exception as e:
                bot.send_message(MY_CHAT_ID, f"❌ Hata: {str(e)}")
                return

if __name__ == "__main__":
    # Test için doğrudan çalıştırıyoruz
    main_worker()
