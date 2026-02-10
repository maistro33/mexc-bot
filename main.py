import ccxt
import telebot
import time
import os
import math
import threading

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

# --- [2. HIZLI TEST AYARLARI] ---
CONFIG = {
    'entry_usdt': 20.0,
    'leverage': 10,
    'tp1_ratio': 0.75,
    'max_test_trades': 2 # Sadece 2 işlem açıp duracak
}

active_test_count = 0

def round_amount(symbol, amount):
    try:
        market = ex.market(symbol)
        prec = market['precision']['amount']
        return round(amount, int(-math.log10(prec))) if prec < 1 else int(amount)
    except: return round(amount, 2)

# --- [3. HIZLI TEST DÖNGÜSÜ] ---
def quick_test_loop():
    global active_test_count
    bot.send_message(MY_CHAT_ID, "🚀 HIZLI TEST MODU: Analiz beklenmiyor, ilk fırsata dalınacak!")
    
    while active_test_count < CONFIG['max_test_trades']:
        try:
            markets = ex.fetch_tickers()
            # En hacimli 5 pariteyi al (Hemen işlem gelsin diye)
            symbols = sorted([s for s in markets if '/USDT:USDT' in s], 
                             key=lambda x: markets[x]['quoteVolume'] or 0, reverse=True)[:5]
            
            for sym in symbols:
                if active_test_count >= CONFIG['max_test_trades']: break
                
                # Borsa Moduna Göre Ayarla
                pos_mode = ex.fetch_position_mode(sym)
                is_hedge = pos_mode['hedge']
                
                ex.set_leverage(CONFIG['leverage'], sym)
                ticker = ex.fetch_ticker(sym)
                entry = ticker['last']
                
                # Test için çok yakın hedefler (%0.5 Stop, %0.5 TP)
                stop = entry * 0.995 
                tp1 = entry * 1.005
                amount = round_amount(sym, (CONFIG['entry_usdt'] * CONFIG['leverage']) / entry)
                
                # Giriş (LONG)
                params = {'posSide': 'long'} if is_hedge else {}
                ex.create_market_order(sym, 'buy', amount, params=params)
                time.sleep(1)

                # SL ve TP Emirleri
                close_params = {'stopPrice': stop, 'reduceOnly': True}
                if is_hedge: close_params['posSide'] = 'long'
                
                ex.create_order(sym, 'trigger_market', 'sell', amount, params=close_params) # Stop
                
                tp_params = close_params.copy()
                tp_params['stopPrice'] = tp1
                tp_qty = round_amount(sym, amount * CONFIG['tp1_ratio'])
                ex.create_order(sym, 'trigger_market', 'sell', tp_qty, params=tp_params) # %75 TP

                active_test_count += 1
                bot.send_message(MY_CHAT_ID, f"✅ TEST İŞLEMİ {active_test_count} AÇILDI!\nParite: {sym}\nLütfen Bitget 'Açık Emirler' kısmını kontrol edin.")
                time.sleep(5)
                
            time.sleep(10)
        except Exception as e:
            bot.send_message(MY_CHAT_ID, f"⚠️ Test hatası: {str(e)}")
            time.sleep(10)

if __name__ == "__main__":
    threading.Thread(target=bot.infinity_polling, daemon=True).start()
    ex.load_markets()
    quick_test_loop()
