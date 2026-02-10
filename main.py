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

# Direkt One-way mod odaklı bağlantı
ex = ccxt.bitget({
    'apiKey': API_KEY,
    'secret': API_SEC,
    'password': PASSPHRASE,
    'options': {'defaultType': 'swap'},
    'enableRateLimit': True
})
bot = telebot.TeleBot(TELE_TOKEN)

# --- [2. AYARLARINIZ] ---
CONFIG = {
    'entry_usdt': 20.0,
    'leverage': 10,
    'tp1_ratio': 0.75,   # %75 Kar Al
    'max_test_trades': 2 # Test için sadece 2 işlem açar
}

# --- [3. YARDIMCI FONKSİYONLAR] ---
def round_amount(symbol, amount):
    try:
        market = ex.market(symbol)
        prec = market['precision']['amount']
        return round(amount, int(-math.log10(prec))) if prec < 1 else int(amount)
    except: return round(amount, 2)

@bot.message_handler(commands=['durum', 'bakiye'])
def send_status(message):
    try:
        balance = ex.fetch_balance()
        usdt_free = balance.get('USDT', {}).get('free', 0)
        bot.reply_to(message, f"💰 **Güncel Bakiye:** {usdt_free:.2f} USDT\n🦅 Radar Aktif (Test Modu)")
    except Exception as e:
        bot.reply_to(message, f"❌ Hata: {str(e)}")

# --- [4. ANA TEST DÖNGÜSÜ] ---
def simple_test_loop():
    count = 0
    bot.send_message(MY_CHAT_ID, "🚀 **HIZLI TEST BAŞLIYOR**\nMod: Tek Yönlü (One-way)\nHedef: İşlem açıp %75 TP ve SL dizmek.")
    
    while count < CONFIG['max_test_trades']:
        try:
            # En hacimli pariteyi al
            markets = ex.fetch_tickers()
            symbols = sorted([s for s in markets if '/USDT:USDT' in s], 
                             key=lambda x: markets[x]['quoteVolume'] or 0, reverse=True)
            
            for sym in symbols[:10]:
                if count >= CONFIG['max_test_trades']: break
                
                ex.set_leverage(CONFIG['leverage'], sym)
                ticker = ex.fetch_ticker(sym)
                entry = ticker['last']
                
                # SL/TP Seviyeleri (%0.7 mesafe)
                stop = entry * 0.993 
                tp1 = entry * 1.007
                amount = round_amount(sym, (CONFIG['entry_usdt'] * CONFIG['leverage']) / entry)
                
                # 1. Giriş (Long - Tek Yönlü)
                bot.send_message(MY_CHAT_ID, f"🔄 {sym} için işlem gönderiliyor...")
                ex.create_market_order(sym, 'buy', amount)
                time.sleep(2)

                # 2. Stop Loss (Tek Yönlü modda posSide YOKTUR)
                ex.create_order(sym, 'trigger_market', 'sell', amount, params={'stopPrice': stop, 'reduceOnly': True})
                
                # 3. %75 Kar Al
                tp_qty = round_amount(sym, amount * CONFIG['tp1_ratio'])
                ex.create_order(sym, 'trigger_market', 'sell', tp_qty, params={'stopPrice': tp1, 'reduceOnly': True})

                count += 1
                bot.send_message(MY_CHAT_ID, f"✅ **BAŞARILI!**\nParite: {sym}\nBitget 'Açık Emirler' kısmını şimdi kontrol edin. SL ve %75 TP orada olmalı.")
                time.sleep(10)
                
            time.sleep(30)
        except Exception as e:
            bot.send_message(MY_CHAT_ID, f"⚠️ Test Hatası: {str(e)}")
            time.sleep(15)

if __name__ == "__main__":
    threading.Thread(target=bot.infinity_polling, daemon=True).start()
    ex.load_markets()
    simple_test_loop()
