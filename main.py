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
        return round(amount, int(-math.log10(prec))) if prec < 1 else int(amount)
    except: return round(amount, 2)

# --- [2. MÜHÜRLEYİCİ TEST OPERASYONU] ---
def run_final_test():
    bot.send_message(MY_CHAT_ID, "🚀 TEST BAŞLADI: BTC'ye dalıyorum, emirleri dizip haber vereceğim...")
    
    try:
        sym = 'BTC/USDT:USDT'
        ex.set_leverage(10, sym)
        ticker = ex.fetch_ticker(sym)
        entry = ticker['last']
        
        # Test Seviyeleri (%0.5 mesafe)
        stop = entry * 0.995 
        tp1 = entry * 1.005
        amount = round_amount(sym, (20.0 * 10) / entry)
        
        # 1. Giriş (Hedge Mode - Long)
        ex.create_market_order(sym, 'buy', amount, params={'posSide': 'long'})
        bot.send_message(MY_CHAT_ID, "✅ 1/3: BTC Long pozisyonu açıldı.")
        time.sleep(2)

        # 2. Stop Loss (Hedge Mode - Long Kapat)
        ex.create_order(sym, 'trigger_market', 'sell', amount, 
                         params={'stopPrice': stop, 'reduceOnly': True, 'posSide': 'long'})
        bot.send_message(MY_CHAT_ID, "✅ 2/3: Stop Loss emri borsaya iletildi.")
        
        # 3. %75 Kar Al (Hedge Mode - Long Kapat)
        tp_qty = round_amount(sym, amount * 0.75)
        ex.create_order(sym, 'trigger_market', 'sell', tp_qty, 
                         params={'stopPrice': tp1, 'reduceOnly': True, 'posSide': 'long'})
        bot.send_message(MY_CHAT_ID, "✅ 3/3: %75 Kâr Al (TP1) emri borsaya iletildi.")

        bot.send_message(MY_CHAT_ID, f"🏁 **TEST TAMAMLANDI!**\nŞimdi Bitget'e girin, BTC 'Açık Emirler' kısmında Stop ve TP'yi göreceksiniz. Oradaysalar bu iş bitmiştir!")
        
    except Exception as e:
        bot.send_message(MY_CHAT_ID, f"⚠️ Hata oluştu: {str(e)}")

if __name__ == "__main__":
    ex.load_markets()
    run_final_test()
