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

# 'positionMode': True ayarı Hedge modu zorunlu kılar
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

# --- [2. MÜHÜRLEYİCİ TEST] ---
def run_final_test():
    bot.send_message(MY_CHAT_ID, "🚀 **SON TEST BAŞLADI**\nBTC'ye dalıyorum. Lütfen borsanın HEDGE modda olduğunu teyit edin.")
    
    try:
        sym = 'BTC/USDT:USDT'
        ex.set_leverage(10, sym)
        ticker = ex.fetch_ticker(sym)
        entry = ticker['last']
        
        # %1 Mesafe ile SL/TP
        stop = entry * 0.99 
        tp1 = entry * 1.01
        amount = round_amount(sym, (20.0 * 10) / entry)
        
        # 1. GİRİŞ (LONG)
        ex.create_market_order(sym, 'buy', amount, params={'posSide': 'long'})
        bot.send_message(MY_CHAT_ID, "✅ 1/3: BTC Pozisyonu açıldı.")
        time.sleep(2)

        # 2. STOP LOSS (LONG KAPAT)
        ex.create_order(sym, 'trigger_market', 'sell', amount, 
                         params={'stopPrice': stop, 'reduceOnly': True, 'posSide': 'long'})
        bot.send_message(MY_CHAT_ID, "✅ 2/3: Stop Loss dizildi.")
        
        # 3. %75 TP1 (LONG KAPAT)
        tp_qty = round_amount(sym, amount * 0.75)
        ex.create_order(sym, 'trigger_market', 'sell', tp_qty, 
                         params={'stopPrice': tp1, 'reduceOnly': True, 'posSide': 'long'})
        bot.send_message(MY_CHAT_ID, "✅ 3/3: %75 Kar Al dizildi.")

        bot.send_message(MY_CHAT_ID, "🏁 **İŞLEM TAMAM!** Bitget 'Açık Emirler' kısmına bakabilirsin.")
        
    except Exception as e:
        bot.send_message(MY_CHAT_ID, f"❌ Hata: {str(e)}")

if __name__ == "__main__":
    ex.load_markets()
    run_final_test()
