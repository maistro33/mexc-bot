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

# Bitget V2 API Yapılandırması
ex = ccxt.bitget({
    'apiKey': API_KEY,
    'secret': API_SEC,
    'password': PASSPHRASE,
    'options': {
        'defaultType': 'swap',
        'broker': 'CCXT'
    },
    'enableRateLimit': True
})
bot = telebot.TeleBot(TELE_TOKEN)

def round_amount(symbol, amount):
    try:
        market = ex.market(symbol)
        step = market['precision']['amount']
        return round(math.floor(amount / step) * step, 4)
    except: return round(amount, 3)

# --- [2. OPERASYON] ---
def run_bridge_test():
    bot.send_message(MY_CHAT_ID, "🛠️ **V2 SİSTEMİ DEVREDE**\nHedge Mode doğrulanıyor ve işlem başlatılıyor...")
    
    try:
        symbol = 'BTC/USDT:USDT'
        ex.load_markets()
        
        # API'YE MODU TEKRAR HATIRLATIYORUZ
        try:
            ex.set_position_mode(True, symbol)
        except:
            pass # Zaten o moddaysa hata verebilir, geçiyoruz.

        ex.set_leverage(10, symbol)
        ticker = ex.fetch_ticker(symbol)
        entry = ticker['last']
        
        # Hedefler
        stop = round(entry * 0.99, 1) 
        tp1 = round(entry * 1.01, 1)
        amount = round_amount(symbol, (20.0 * 10) / entry)
        
        # 1. GİRİŞ (Hedge Mode Parametresiyle)
        ex.create_order(symbol, 'market', 'buy', amount, params={'posSide': 'long'})
        bot.send_message(MY_CHAT_ID, "✅ 1/3: Giriş başarılı (Hedge Mode aktif).")
        time.sleep(2)

        # 2. STOP LOSS
        ex.create_order(symbol, 'market', 'sell', amount, params={
            'posSide': 'long',
            'stopLossPrice': stop,
            'reduceOnly': True
        })
        bot.send_message(MY_CHAT_ID, f"✅ 2/3: Stop Loss dizildi: {stop}")

        # 3. %75 KÂR AL
        tp_qty = round_amount(symbol, amount * 0.75)
        ex.create_order(symbol, 'market', 'sell', tp_qty, params={
            'posSide': 'long',
            'takeProfitPrice': tp1,
            'reduceOnly': True
        })
        bot.send_message(MY_CHAT_ID, f"✅ 3/3: %75 TP1 dizildi: {tp1}")

        bot.send_message(MY_CHAT_ID, "🏁 **TEBRİKLER SADIK BEY!**\nSistem V2 üzerinden Hedge moduna uyum sağladı.")

    except Exception as e:
        bot.send_message(MY_CHAT_ID, f"❌ SON ANALİZ: {str(e)}")

if __name__ == "__main__":
    run_bridge_test()
