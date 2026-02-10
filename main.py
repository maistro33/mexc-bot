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
    'options': {'defaultType': 'swap'},
    'enableRateLimit': True
})
bot = telebot.TeleBot(TELE_TOKEN)

def round_amount(symbol, amount):
    try:
        market = ex.market(symbol)
        step = market['precision']['amount']
        return round(math.floor(amount / step) * step, 4)
    except: return round(amount, 3)

# --- [2. HATASIZ TEST OPERASYONU] ---
def run_final_test():
    bot.send_message(MY_CHAT_ID, "🚀 **AYARLAR TAMAM! TEST BAŞLIYOR**\nSingle-Asset modunda BTC operasyonu başlıyor...")
    
    try:
        symbol = 'BTC/USDT:USDT'
        ex.load_markets()
        ex.set_leverage(10, symbol)
        
        ticker = ex.fetch_ticker(symbol)
        entry = ticker['last']
        
        # Test Seviyeleri (%1.0 aralık)
        stop = round(entry * 0.99, 1) 
        tp1 = round(entry * 1.01, 1)
        amount = round_amount(symbol, (20.0 * 10) / entry)
        
        # 1. GİRİŞ (LONG)
        ex.create_market_order(symbol, 'buy', amount, params={'posSide': 'long'})
        bot.send_message(MY_CHAT_ID, f"✅ 1/3: BTC Long açıldı.\nFiyat: {entry}")
        time.sleep(2)

        # 2. STOP LOSS (Plan Order Metodu)
        ex.privatePostMixOrderPlacePlanOrder({
            'symbol': 'BTCUSDT_UMCBL',
            'marginCoin': 'USDT',
            'size': str(amount),
            'triggerPrice': str(stop),
            'triggerType': 'market_price',
            'side': 'sell',
            'orderType': 'market',
            'posSide': 'long',
            'reduceOnly': 'true'
        })
        bot.send_message(MY_CHAT_ID, f"✅ 2/3: Stop Loss dizildi.\nSeviye: {stop}")

        # 3. %75 KÂR AL (Özel Ayarınız)
        tp_qty = round_amount(symbol, amount * 0.75)
        ex.privatePostMixOrderPlacePlanOrder({
            'symbol': 'BTCUSDT_UMCBL',
            'marginCoin': 'USDT',
            'size': str(tp_qty),
            'triggerPrice': str(tp1),
            'triggerType': 'market_price',
            'side': 'sell',
            'orderType': 'market',
            'posSide': 'long',
            'reduceOnly': 'true'
        })
        bot.send_message(MY_CHAT_ID, f"✅ 3/3: %75 Kâr Al dizildi.\nSeviye: {tp1}")

        bot.send_message(MY_CHAT_ID, "🏁 **MÜKEMMEL SONUÇ!**\nBitget 'Planlı Emirler' (Plan Orders) kısmına bakabilirsin Sadık Bey. Bu iş bu sefer bitti!")

    except Exception as e:
        bot.send_message(MY_CHAT_ID, f"❌ TEKNİK HATA: {str(e)}")

if __name__ == "__main__":
    run_final_test()
