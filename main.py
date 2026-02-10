import ccxt
import telebot
import time
import os
import math

# --- [1. BAĞLANTILAR] ---
API_KEY = os.getenv('BITGET_API')
API_SEC = os.getenv('BITGET_SEC')
PASSPHRASE = os.getenv('BITGET_PASSPHRASE')
TELE_TOKEN = os.getenv('TELE_TOKEN')
MY_CHAT_ID = os.getenv('MY_CHAT_ID')

# 'positionMode': True -> Borsadaki Hedge (Çift Yönlü) moduyla tam uyum sağlar.
ex = ccxt.bitget({
    'apiKey': API_KEY,
    'secret': API_SEC,
    'password': PASSPHRASE,
    'options': {'defaultType': 'swap', 'positionMode': True},
    'enableRateLimit': True
})
bot = telebot.TeleBot(TELE_TOKEN)

def round_amount(symbol, amount):
    try:
        market = ex.market(symbol)
        prec = market['precision']['amount']
        # Miktarı borsanın kabul ettiği hassasiyete yuvarlar
        step = market['precision']['amount']
        return round(math.floor(amount / step) * step, 4)
    except: return round(amount, 2)

# --- [2. TEST OPERASYONU] ---
def final_test():
    bot.send_message(MY_CHAT_ID, "🚀 **KONTROL EDİLMİŞ TEST BAŞLADI**\nBTC'ye dalınıyor. Parametreler: Hedge Mode + %75 TP1 + SL")
    
    try:
        sym = 'BTC/USDT:USDT'
        ex.load_markets()
        ex.set_leverage(10, sym)
        
        ticker = ex.fetch_ticker(sym)
        entry = ticker['last']
        
        # Test Seviyeleri: %1.0 mesafe (Hata payını azaltmak için aralığı net tuttum)
        stop = round(entry * 0.99, 1) 
        tp1 = round(entry * 1.01, 1)
        
        # 20 USDT giriş, 10x kaldıraç
        amount = round_amount(sym, (20.0 * 10) / entry) 
        
        # 1. GİRİŞ (LONG)
        # params={'posSide': 'long'} -> "Bu bir Long pozisyon açılışıdır"
        ex.create_market_order(sym, 'buy', amount, params={'posSide': 'long'})
        bot.send_message(MY_CHAT_ID, f"✅ 1/3: BTC Long açıldı (Fiyat: {entry})")
        time.sleep(2)

        # 2. STOP LOSS (LONG KAPAT)
        # params={'posSide': 'long', 'reduceOnly': True} -> "Açık olan Long'u kapat/azalt"
        ex.create_order(sym, 'trigger_market', 'sell', amount, 
                         params={
                             'stopPrice': stop, 
                             'reduceOnly': True, 
                             'posSide': 'long'
                         })
        bot.send_message(MY_CHAT_ID, f"✅ 2/3: Stop Loss dizildi (Seviye: {stop})")
        
        # 3. %75 KAR AL (TP1)
        tp_qty = round_amount(sym, amount * 0.75)
        ex.create_order(sym, 'trigger_market', 'sell', tp_qty, 
                         params={
                             'stopPrice': tp1, 
                             'reduceOnly': True, 
                             'posSide': 'long'
                         })
        bot.send_message(MY_CHAT_ID, f"✅ 3/3: %75 Kâr Al dizildi (Seviye: {tp1})")

        bot.send_message(MY_CHAT_ID, "🏁 **İŞLEM BAŞARIYLA TAMAMLANDI!**\nBitget 'Açık Emirler' kısmını kontrol et Sadık Bey. Bu sefer her şey yerli yerinde olmalı.")
        
    except Exception as e:
        # Hata mesajını detaylı gönderir ki nerede takıldığını görelim
        error_msg = str(e)
        bot.send_message(MY_CHAT_ID, f"❌ TEST HATASI: {error_msg}")

if __name__ == "__main__":
    final_test()
