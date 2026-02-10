import ccxt
import telebot
import time
import os
import threading
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

# --- [2. TEST AYARLARI] ---
CONFIG = {
    'entry_usdt': 20.0,
    'leverage': 10,
    'tp1_ratio': 0.75,   # %75 Kâr Al
    'max_test_trades': 2 # Sadece 2 işlem açıp duracak
}

active_trades_count = 0

def round_amount(symbol, amount):
    try:
        market = ex.market(symbol)
        prec = market['precision']['amount']
        if prec < 1:
            step = int(-math.log10(prec))
            return round(amount, step)
        return int(amount)
    except: return round(amount, 2)

# --- [3. HIZLI TEST ANALİZİ] ---
def quick_test_logic(symbol):
    try:
        # Son 2 muma bak, yön neyse ona dal (Test için)
        bars = ex.fetch_ohlcv(symbol, timeframe='1m', limit=3)
        if bars[-1][4] > bars[-2][4]: return 'buy'
        else: return 'sell'
    except: return None

# --- [4. ANA TEST DÖNGÜSÜ] ---
def main_loop():
    global active_trades_count
    bot.send_message(MY_CHAT_ID, "🚀 TEST BAŞLADI: Bot 2 tane deneme işlemi açacak. Lütfen Bitget'ten Stop ve TP emirlerini kontrol edin.")
    
    markets = ex.fetch_tickers()
    # En hacimli coinleri seç (Hemen işlem gelsin diye)
    test_symbols = sorted([s for s in markets if '/USDT:USDT' in s], 
                         key=lambda x: markets[x]['quoteVolume'] if markets[x]['quoteVolume'] else 0, 
                         reverse=True)[:15]

    for sym in test_symbols:
        if active_trades_count >= CONFIG['max_test_trades']:
            break

        side = quick_test_logic(sym)
        if side:
            try:
                ex.set_leverage(CONFIG['leverage'], sym)
                ticker = ex.fetch_ticker(sym)
                entry = ticker['last']
                
                # Test için %1 Stop, %1 TP koyalım
                stop = entry * 0.99 if side == 'buy' else entry * 1.01
                tp1 = entry * 1.01 if side == 'buy' else entry * 0.99
                
                amount = round_amount(sym, (CONFIG['entry_usdt'] * CONFIG['leverage']) / entry)
                pos_side = 'long' if side == 'buy' else 'short'
                exit_side = 'sell' if side == 'buy' else 'buy'

                # 1. Giriş Emri
                ex.create_market_order(sym, side, amount, params={'posSide': pos_side})
                time.sleep(1)

                # 2. Stop Loss Emri
                ex.create_order(sym, 'trigger_market', exit_side, amount, params={'stopPrice': stop, 'reduceOnly': True, 'posSide': pos_side})
                
                # 3. TP1 Emri (%75)
                tp1_qty = round_amount(sym, amount * CONFIG['tp1_ratio'])
                ex.create_order(sym, 'trigger_market', exit_side, tp1_qty, params={'stopPrice': tp1, 'reduceOnly': True, 'posSide': pos_side})

                active_trades_count += 1
                bot.send_message(MY_CHAT_ID, f"✅ TEST {active_trades_count} AÇILDI!\nParite: {sym}\nGiriş: {entry}\nStop: {stop}\nTP1 (%75): {tp1}\n\nLütfen Bitget'te 'Açık Emirler' kısmını kontrol edin.")
                
            except Exception as e:
                print(f"Hata: {e}")
        
        time.sleep(2)

    bot.send_message(MY_CHAT_ID, "🏁 Test işlemleri tamamlandı. Emirleri kontrol ettikten sonra beni tekrar 'Güvenli SMC' moduna alabilirsiniz.")

if __name__ == "__main__":
    ex.load_markets()
    main_loop()
