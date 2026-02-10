import ccxt
import telebot
import time
import os
import math

# --- [BAĞLANTILAR] ---
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
        prec = market['precision']['amount']
        return round(amount, int(-math.log10(prec))) if prec < 1 else int(amount)
    except: return round(amount, 2)

def start_test():
    bot.send_message(MY_CHAT_ID, "🚀 TEK YÖNLÜ MOD AKTİF: Emirler gönderiliyor...")
    
    # Test için BTC/USDT seçildi
    sym = 'BTC/USDT:USDT'
    
    try:
        # Borsa modunu bot tarafında Tek Yönlü'ye zorla
        ex.set_position_mode(False, sym) 
        time.sleep(1)
        
        ex.set_leverage(10, sym)
        ticker = ex.fetch_ticker(sym)
        entry = ticker['last']
        
        # Test parametreleri: %1 Stop, %1 TP
        stop = entry * 0.99  
        tp1 = entry * 1.01   
        amount = round_amount(sym, (20.0 * 10) / entry)

        # 1. Giriş Emri (En garantili format)
        ex.create_market_order(sym, 'buy', amount)
        time.sleep(1)

        # 2. Stop Loss (Borsanın beklediği sade format)
        ex.create_order(sym, 'trigger_market', 'sell', amount, params={'stopPrice': stop, 'reduceOnly': True})
        
        # 3. TP1 (%75)
        tp1_qty = round_amount(sym, amount * 0.75)
        ex.create_order(sym, 'trigger_market', 'sell', tp1_qty, params={'stopPrice': tp1, 'reduceOnly': True})

        bot.send_message(MY_CHAT_ID, f"✅ İŞLEM BAŞARILI!\n{sym} açıldı.\nStop Loss ve %75 TP emirleri dizildi. Lütfen Bitget'ten kontrol edin.")
        
    except Exception as e:
        bot.send_message(MY_CHAT_ID, f"⚠️ Hata: {str(e)}\n(Not: Eğer borsa mod hatası verirse, Bitget uygulamasından Position Mode'u 'One-way' yapıp tekrar deneyin.)")

if __name__ == "__main__":
    ex.load_markets()
    start_test()
